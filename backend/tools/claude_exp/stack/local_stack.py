"""Boot the REAL product stack (PostgreSQL + FastAPI identity/workspace/research API + queue worker + built frontend) on one machine.

QA/local tooling only. It uses the product's own `ops.migrate_and_grant`, `cloud.app.create_app` and static build; it adds exactly two
local stand-ins that the VPS replaces with real services: an outbox instead of SMTP (verification tokens are appended to a file, never sent)
and a small gateway instead of Caddy (serves dist/ and adds the X-Forwarded-* headers the identity boundary requires).

  python local_stack.py setup   --pg-port 54329 --pg-bin <postgres bin>     # roles + database + migrations + grants
  python local_stack.py api     --pg-port 54329 [--port 8001]               # API (the queue worker runs inside its lifespan)
  python local_stack.py gateway --dist <frontend/dist> [--port 8080]         # open http://app.localhost:8080
Secrets for the local roles are fixed local-only strings; nothing here is a deployment secret.
"""
import argparse, asyncio, http.client, json, os, secrets, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))

OWNER_PW, APP_PW = "owner-local-only", "app-local-only"
STATE = Path(os.environ.get("BTL_LOCAL_STATE", Path.home() / ".riksora_local_stack"))


def dsn(user, pw, port, db="btl"):
    return f"host=127.0.0.1 port={port} dbname={db} user={user} password={pw}"


def setup(a):
    import psycopg
    with psycopg.connect(f"host=127.0.0.1 port={a.pg_port} dbname=postgres user=postgres", autocommit=True) as db:
        have = {r[0] for r in db.execute("SELECT rolname FROM pg_roles")}
        if "btl_owner" not in have:
            db.execute(f"CREATE ROLE btl_owner LOGIN PASSWORD '{OWNER_PW}'")
        if "btl_app" not in have:
            db.execute(f"CREATE ROLE btl_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD '{APP_PW}'")
        if not db.execute("SELECT 1 FROM pg_database WHERE datname='btl'").fetchone():
            db.execute("CREATE DATABASE btl OWNER btl_owner")
    from deploy.vps.ops import migrate_and_grant
    migrate_and_grant(dsn("btl_owner", OWNER_PW, a.pg_port))
    print("SETUP_DONE migrations applied, runtime role granted")


class Outbox:
    """Local stand-in for SMTP: the verification/recovery token goes to a JSON-lines file."""
    def __init__(self, path):
        self.path = Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)

    async def send(self, email, purpose, token):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(at=time.time(), email=email, purpose=purpose, token=token)) + "\n")


def api(a):
    import uvicorn
    from cloud.app import create_app
    secret_file = STATE / "auth_secret"
    STATE.mkdir(parents=True, exist_ok=True)
    if not secret_file.exists():
        secret_file.write_text(secrets.token_urlsafe(72))
    app = create_app(dsn("btl_app", APP_PW, a.pg_port), secret_file.read_text(), Outbox(STATE / "outbox.jsonl"),
                     rate_limit=a.rate_limit, sandbox_reset_timezone="UTC")
    config = uvicorn.Config(app, host="127.0.0.1", port=a.port, proxy_headers=True, forwarded_allow_ips="127.0.0.1", access_log=False)
    loop = asyncio.SelectorEventLoop if os.name == "nt" else asyncio.new_event_loop
    asyncio.run(uvicorn.Server(config).serve(), loop_factory=loop)


def gateway(a):
    dist = Path(a.dist).resolve()
    types = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".json": "application/json",
             ".webmanifest": "application/manifest+json", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".csv": "text/csv"}

    class G(BaseHTTPRequestHandler):
        def log_message(self, *x): pass

        def _proxy(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else None
            c = http.client.HTTPConnection("127.0.0.1", a.api_port, timeout=60)
            h = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection", "x-forwarded-for", "x-forwarded-proto")}
            h.update({"X-Forwarded-Proto": "https", "X-Forwarded-For": "127.0.0.1", "Host": "127.0.0.1"})
            c.request(self.command, self.path, body, h)
            r = c.getresponse(); data = r.read()
            self.send_response(r.status)
            for k, v in r.getheaders():
                if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

        def do_POST(self): self._proxy()
        do_PUT = do_PATCH = do_DELETE = do_POST

        def do_GET(self):
            if self.path.startswith("/api/v1/"):
                return self._proxy()
            p = (dist / self.path.split("?")[0].lstrip("/")).resolve()
            if not (p.is_file() and dist in p.parents):
                p = dist / "index.html"
            data = p.read_bytes()
            self.send_response(200); self.send_header("Content-Type", types.get(p.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)

    print(f"gateway on http://app.localhost:{a.port}  (dist {dist})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), G).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup"); s.add_argument("--pg-port", type=int, default=54329); s.set_defaults(f=setup)
    s = sub.add_parser("api"); s.add_argument("--pg-port", type=int, default=54329); s.add_argument("--port", type=int, default=8001)
    s.add_argument("--rate-limit", type=int, default=300); s.set_defaults(f=api)
    s = sub.add_parser("gateway"); s.add_argument("--dist", required=True); s.add_argument("--port", type=int, default=8080)
    s.add_argument("--api-port", type=int, default=8001); s.set_defaults(f=gateway)
    a = ap.parse_args(); a.f(a)
