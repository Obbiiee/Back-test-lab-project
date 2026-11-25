"""Run the whole current product on your own machine, from nothing, with one command (SYNTHETIC data only; no market data, no external services).

    python deploy/local/dev_stack.py up        # first run: PostgreSQL, data, migrations, frontend build, HTTPS server, a ready-to-use account
    python deploy/local/dev_stack.py reset     # stop and delete everything this tool created (the repository is untouched)

What `up` does, in order (every step is idempotent, so a second run just starts the server):
  1. initialises a private PostgreSQL cluster under <home>/pg and starts it on 127.0.0.1 (never your system database);
  2. creates the owner/runtime roles and the `btl` database, then applies the product's own migrations and grants;
  3. generates the synthetic Monthly Parquet source once (January-March 2020, one tick per minute, starting at the product fixture start);
  4. builds the frontend with VITE_HOSTED_ENTRY=1 so https://localhost behaves like the public site (landing, /app, sign-in, workspace);
  5. serves API + frontend over HTTPS with a self-signed certificate (the product refuses plain HTTP; your browser will warn once);
  6. registers and verifies one account and prints its credentials. Email codes for any other sign-up are printed in this terminal.

Requirements: Python 3.12 or 3.13 with `pip install -r backend/requirements.lock`, PostgreSQL 16+ binaries (initdb, pg_ctl), Node 20+ (first run only).
Linux, macOS and Windows through WSL2 are supported; native Windows is not (the product's worker and database tooling are POSIX-first).
"""
import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]

DEFAULT_HOME = ROOT / '.local' / 'dev'
FIXED_EMAIL = 'dev@example.com'          # the email validator rejects reserved domains such as .local


def say(message):
    print(message, flush=True)


def fail(message):
    raise SystemExit('ERROR: ' + message)


# ---------------------------------------------------------------------------------------------------------------- preflight
def check_platform():
    if os.name == 'nt':
        fail('Native Windows is not supported. Install WSL2 (wsl --install -d Ubuntu), clone the repository inside it and run the same command there.')
    if sys.version_info < (3, 12):
        fail(f'Python 3.12 or newer is required (this is {sys.version.split()[0]}).')
    try:
        import fastapi, psycopg, pyarrow, uvicorn, cryptography, httpx  # noqa: F401
    except ImportError as error:
        fail(f'Missing Python package ({error.name}). Run: pip install -r backend/requirements.lock')


def find_pg_bin(explicit):
    candidates = [explicit, os.environ.get('PG_BIN')] + [str(Path(p).parent) for p in [shutil.which('initdb')] if p]
    candidates += [str(p) for p in sorted(Path('/usr/lib/postgresql').glob('*/bin'), reverse=True)] + ['/opt/homebrew/opt/postgresql@16/bin', '/usr/local/opt/postgresql@16/bin']
    for candidate in candidates:
        if candidate and (Path(candidate) / 'initdb').exists() and (Path(candidate) / 'pg_ctl').exists():
            return Path(candidate)
    fail('PostgreSQL binaries (initdb, pg_ctl) were not found. Install PostgreSQL 16+ or pass --pg-bin /path/to/bin.')


def free_port(port):
    with socket.socket() as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(('127.0.0.1', port)) != 0


# ---------------------------------------------------------------------------------------------------------------- state
class Home:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.secrets_file = self.path / 'secrets.json'
        if self.secrets_file.exists():
            self.secrets = json.loads(self.secrets_file.read_text())
        else:
            self.secrets = {'auth': secrets.token_hex(48), 'owner': secrets.token_urlsafe(18), 'app': secrets.token_urlsafe(18), 'account': secrets.token_urlsafe(18)}
            self.secrets_file.write_text(json.dumps(self.secrets))
            os.chmod(self.secrets_file, 0o600)

    @property
    def pg(self):
        return self.path / 'pg'


def run(command, **kwargs):
    try:
        return subprocess.run([str(part) for part in command], check=True, capture_output=True, text=True, **kwargs)
    except subprocess.CalledProcessError as error:
        detail = ((error.stderr or '') + (error.stdout or '')).strip()[-1500:]
        raise SystemExit(f'ERROR: command failed: {" ".join(str(part) for part in command[:3])} ...\n{detail}\n'
                         'Hint: if it says "Address already in use", another program holds that port; pick another with --port / --pg-port.')


# ---------------------------------------------------------------------------------------------------------------- PostgreSQL
def start_postgres(home, pg_bin, port):
    if not (home.pg / 'PG_VERSION').exists():
        say('Creating the private PostgreSQL cluster...')
        run([pg_bin / 'initdb', '-D', home.pg, '-U', 'postgres', '--auth=trust', '-E', 'UTF8'])
    socket_dir = Path(tempfile.gettempdir()) / f'riksora-dev-{port}'      # unix socket paths are length-limited, so keep this short
    socket_dir.mkdir(exist_ok=True)
    status = subprocess.run([str(pg_bin / 'pg_ctl'), '-D', str(home.pg), 'status'], capture_output=True, text=True)
    if status.returncode != 0:
        if not free_port(port):
            fail(f'Port {port} is already in use; pass another --pg-port.')
        say(f'Starting PostgreSQL on 127.0.0.1:{port}...')
        run([pg_bin / 'pg_ctl', '-D', home.pg, '-o', f'-p {port} -k {socket_dir} -c listen_addresses=127.0.0.1 -c max_connections=100',
             '-l', home.path / 'pg.log', '-w', 'start'])
    return socket_dir


def stop_postgres(home, pg_bin):
    subprocess.run([str(pg_bin / 'pg_ctl'), '-D', str(home.pg), '-m', 'fast', '-w', 'stop'], capture_output=True, text=True)


def provision_database(home, port):
    import psycopg
    admin = f'host=127.0.0.1 port={port} dbname=postgres user=postgres'
    with psycopg.connect(admin, autocommit=True) as db:
        existing = {row[0] for row in db.execute('SELECT rolname FROM pg_roles')}
        if 'btl_owner' not in existing:
            db.execute(f"CREATE ROLE btl_owner LOGIN PASSWORD '{home.secrets['owner']}'")
        if 'btl_app' not in existing:
            db.execute(f"CREATE ROLE btl_app LOGIN PASSWORD '{home.secrets['app']}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
        if not db.execute("SELECT 1 FROM pg_database WHERE datname='btl'").fetchone():
            db.execute('CREATE DATABASE btl OWNER btl_owner')
    from deploy.vps.ops import migrate_and_grant
    migrate_and_grant(f"host=127.0.0.1 port={port} dbname=btl user=btl_owner password={home.secrets['owner']}")


# ---------------------------------------------------------------------------------------------------------------- frontend, TLS
def build_frontend(home, rebuild):
    out = home.path / 'web'
    if (out / 'index.html').exists() and not rebuild:
        return out
    npm = shutil.which('npm')
    if not npm:
        fail('Node/npm was not found (needed once to build the frontend). Install Node 20+ or build it yourself into ' + str(out))
    frontend = ROOT / 'frontend'
    say('Installing frontend dependencies and building (first run only; takes a minute or two)...')
    if not (frontend / 'node_modules').exists():
        subprocess.run([npm, 'ci'], cwd=frontend, check=True)
    environment = {**os.environ, 'VITE_HOSTED_ENTRY': '1'}
    subprocess.run([npm, 'exec', '--', 'vite', 'build', '--outDir', str(out), '--emptyOutDir'], cwd=frontend, check=True, env=environment)
    shutil.rmtree(out / 'market', ignore_errors=True)               # the sample market archive is not part of the product build
    for sample in out.glob('sample_*.csv'):
        sample.unlink()
    return out


def ensure_certificate(home):
    cert, key = home.path / 'tls-cert.pem', home.path / 'tls-key.pem'
    if cert.exists() and key.exists():
        return cert, key
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    private = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=825))
                   .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'), x509.IPAddress(__import__('ipaddress').ip_address('127.0.0.1'))]), critical=False)
                   .sign(private, hashes.SHA256()))
    key.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(key, 0o600)
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return cert, key


# ---------------------------------------------------------------------------------------------------------------- app
class ConsoleDelivery:
    """Email stand-in: records the message and prints the code so you can finish any sign-up locally."""
    def __init__(self):
        self.messages = []

    async def send(self, email, purpose, token):
        self.messages.append((email, purpose, token))
        say(f'[email to {email}] {purpose} code: {token}')

    def token(self, email, purpose):
        return [token for recipient, kind, token in self.messages if recipient == email and kind == purpose][-1]


def build_app(home, port, enforce, workers, info, web):
    os.environ.update({
        'BTL_PRODUCT_PROFILE': 'staging' if enforce else 'development', 'BTL_ENTITLEMENT_ENFORCE': '1' if enforce else '0', 'BTL_ENTITLEMENT_RESET_TIMEZONE': 'UTC',
        'BTL_RESEARCH_WORKERS': str(workers), 'BTL_TICK_CHECKPOINT_FORMAT': 'compact-v2'})
    from deploy.local.synthetic_source import source_environment
    os.environ.update(source_environment(info))
    from cloud.app import create_app
    from starlette.responses import FileResponse, RedirectResponse
    from starlette.staticfiles import StaticFiles
    delivery = ConsoleDelivery()
    dsn = f"host=127.0.0.1 port={port} dbname=btl user=btl_app password={home.secrets['app']}"
    app = create_app(dsn, home.secrets['auth'], delivery, rate_limit=30, sandbox_reset_timezone='UTC')

    @app.get('/app', include_in_schema=False)
    async def application_entry():            # the official application entry, same as on the public site
        return RedirectResponse('/?page=account', status_code=302)

    class Spa(StaticFiles):                   # unknown paths fall back to the single-page app, like the public site
        async def get_response(self, path, scope):
            try:
                return await super().get_response(path, scope)
            except Exception:
                return FileResponse(web / 'index.html')
    app.mount('/', Spa(directory=str(web), html=True), name='web')
    return app, delivery


def bootstrap_account(home, https_port, delivery, email):
    """Register + verify the ready-to-use account through the real API (first run only)."""
    import httpx
    base = f'https://localhost:{https_port}'
    deadline = time.time() + 90
    with httpx.Client(base_url=base, verify=False, timeout=10) as client:
        while time.time() < deadline:
            try:
                if client.get('/api/v1/auth/providers').status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            say('WARNING: the server did not answer in time; account bootstrap skipped.')
            return False
        password = home.secrets['account']
        registered = client.post('/api/v1/auth/register', json={'email': email, 'password': password})
        if registered.status_code == 201:
            verified = client.post('/api/v1/auth/verify', json={'token': delivery.token(email, 'verification')})
            return verified.status_code == 200
        return client.post('/api/v1/auth/login', data={'username': email, 'password': password}).status_code == 200


def up(arguments):
    check_platform()
    pg_bin = find_pg_bin(arguments.pg_bin)
    home = Home(arguments.home)
    if not free_port(arguments.port):
        fail(f'Port {arguments.port} is already in use; pass another --port.')
    start_postgres(home, pg_bin, arguments.pg_port)
    try:
        provision_database(home, arguments.pg_port)
        from deploy.local.synthetic_source import ensure_source
        info = ensure_source(home.path / 'data', arguments.ticks, log=say, source_format=arguments.source_format)
        web = build_frontend(home, arguments.rebuild_frontend)
        cert, key = ensure_certificate(home)
        app, delivery = build_app(home, arguments.pg_port, arguments.enforce, arguments.workers, info, web)
        ready = {}

        def announce():
            ready['ok'] = bootstrap_account(home, arguments.port, delivery, arguments.email)
            say('')
            say('=' * 72)
            say(f'  RIKSORA is running:   https://localhost:{arguments.port}/')
            say(f'  Application entry:    https://localhost:{arguments.port}/app')
            say(f'  Sign in with email:   {arguments.email}')
            say(f"  Password:             {home.secrets['account']}")
            say('  The browser warns about the self-signed certificate once: continue anyway.')
            say(f"  Free/Pro rules:       {'ENFORCED (1 new Session per UTC day for Free)' if arguments.enforce else 'not enforced locally (use --enforce to test Free/Pro)'}")
            import datetime
            last = (datetime.datetime(2020, 1, 1) + datetime.timedelta(minutes=arguments.ticks - 1)).strftime('%Y-%m-%d')
            say(f'  Data: SYNTHETIC / TEST ONLY, 2020-01-01 to {last}, one tick per minute (start a Session in January 2020).')
            say('  Stop with Ctrl+C.')
            say('=' * 72)
            if not ready['ok']:
                say('WARNING: the ready-made account could not be prepared; register one on the sign-in page (the code is printed here).')

        threading.Thread(target=announce, daemon=True).start()
        import uvicorn
        uvicorn.run(app, host='127.0.0.1', port=arguments.port, ssl_certfile=str(cert), ssl_keyfile=str(key), access_log=False, log_level='warning')
    finally:
        if not arguments.keep_db:
            stop_postgres(home, pg_bin)


def reset(arguments):
    home = Path(arguments.home).resolve()
    if not home.exists():
        say('Nothing to remove.')
        return
    if not ((home / 'secrets.json').exists() or (home / 'pg' / 'PG_VERSION').exists()):
        fail(f'{home} does not look like a local-stack home; refusing to delete it.')
    try:
        pg_bin = find_pg_bin(arguments.pg_bin)
    except SystemExit:
        pg_bin = None
    if pg_bin and (home / 'pg' / 'PG_VERSION').exists():
        subprocess.run([str(pg_bin / 'pg_ctl'), '-D', str(home / 'pg'), '-m', 'immediate', '-w', 'stop'], capture_output=True, text=True)
    shutil.rmtree(home)
    say(f'Removed {home}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', nargs='?', default='up', choices=['up', 'reset'])
    parser.add_argument('--home', default=str(DEFAULT_HOME), help='where the stack keeps its database, data, build and secrets (default: .local/dev, ignored by Git)')
    parser.add_argument('--port', type=int, default=8443, help='HTTPS port of the app (default 8443)')
    parser.add_argument('--pg-port', type=int, default=54460, help='port of the private PostgreSQL (default 54460)')
    parser.add_argument('--pg-bin', help='directory with initdb and pg_ctl (default: PATH, PG_BIN or the usual install locations)')
    parser.add_argument('--ticks', type=int, default=131072, help='synthetic ticks (131072 = Jan-Mar 2020; 65536 is faster to generate)')
    parser.add_argument('--workers', type=int, default=2, choices=[1, 2, 3, 4], help='research worker slots (default 2)')
    parser.add_argument('--email', default=FIXED_EMAIL, help='email of the ready-made account')
    parser.add_argument('--source-format', choices=['parquet', 'compact'], default='parquet', help='storage of the synthetic ticks: Monthly Parquet (default) or plain Compact Tick Parquet read directly by the engine')
    parser.add_argument('--enforce', action='store_true', help='enforce the Free/Pro rules (default: off locally so you can test freely)')
    parser.add_argument('--rebuild-frontend', action='store_true', help='rebuild the frontend even if a build exists')
    parser.add_argument('--keep-db', action='store_true', help='leave PostgreSQL running when the app stops')
    arguments = parser.parse_args()
    (up if arguments.command == 'up' else reset)(arguments)


if __name__ == '__main__':
    main()
