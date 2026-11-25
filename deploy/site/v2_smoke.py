"""Production smoke test for the public application (synthetic data only). Creates one throw-away SYNTHETIC account (smoke-<stamp>@example.com, Free tier), one Method and one
Session, replays the Free window through the durable worker, and checks which checkpoint format the database holds. Never touches an existing account.

  python v2_smoke.py --expect v1|v2     exit 0 = PASS. Prints one JSON line. Secrets come from ~/.config and are never printed.
"""
import argparse, hashlib, http.client, json, secrets, sys, time, uuid
from pathlib import Path
import psycopg

H = Path.home()
FEB1_NS = 1580515200 * 10**9
V2_TAG = b"BTL-TICK-COMPACT-CHECKPOINT-1"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--expect", choices=("v1", "v2"), required=True); a = ap.parse_args()
    db = dict(l.split("=", 1) for l in (H / ".config/riksora-db.env").read_text().split() if "=" in l)
    dsn = f"host=127.0.0.1 port=54450 dbname=btl user=btl_owner password={db['PG_OWNER_PASSWORD']}"
    out, started = dict(expect=a.expect, steps=[]), time.monotonic()
    email, token = f"smoke-{time.strftime('%Y%m%d%H%M%S')}@example.com", secrets.token_urlsafe(48)
    with psycopg.connect(dsn, autocommit=True) as c:
        uid = uuid.uuid4()
        c.execute("INSERT INTO btl.users(id,email,hashed_password,is_active,is_superuser,is_verified,password_enabled) VALUES (%s,%s,%s,true,false,true,false)", (uid, email, "x" * 60))
        c.execute("INSERT INTO btl.auth_sessions(token_hash,user_id) VALUES (%s,%s)", (hashlib.sha256(token.encode()).hexdigest(), uid))

    def call(method, path, body=None, job=None):
        conn = http.client.HTTPConnection("127.0.0.1", 8010, timeout=60)
        h = {"Host": "riksora.com", "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.77", "Authorization": "Bearer " + token}
        if job: h["X-BTL-Job"] = job
        data = None
        if body is not None: h["Content-Type"] = "application/json"; data = json.dumps(body)
        conn.request(method, path, data, h); r = conn.getresponse(); raw = r.read()
        try: return r.status, json.loads(raw)
        except Exception: return r.status, {"raw": raw[:80].decode(errors="replace")}

    def step(name, ok, detail=""):
        out["steps"].append(dict(step=name, ok=bool(ok), detail=str(detail)[:160]))
        if not ok: raise SystemExit(finish(False))

    def poll(job_id, root, limit=120):
        for _ in range(limit * 2):
            s, j = call("GET", root + "/jobs/" + job_id)
            if j.get("state") in ("SUCCEEDED", "FAILED", "EXPIRED", "RECONCILE_REQUIRED"): return j
            time.sleep(.5)
        return {"state": "TIMEOUT"}

    def finish(ok):
        out["ok"], out["seconds"] = ok, round(time.monotonic() - started, 1)
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute("DELETE FROM btl.auth_sessions WHERE user_id=%s", (uid,))                       # the throw-away bearer token only; evidence rows stay (immutable)
        print(json.dumps(out)); return 0 if ok else 1

    s, p = call("GET", "/api/v1/auth/providers"); step("providers", s == 200 and p.get("researchConfigured") is True and p.get("password") is False, p)
    s, ws = call("POST", "/api/v1/workspaces", {"name": "v2 smoke"}); step("workspace", s == 201, s); wid = ws["id"]; root = f"/api/v1/workspaces/{wid}/research"
    s, e = call("GET", root + "/entitlements"); step("entitlements free enforced", s == 200 and e.get("tier") == "FREE" and e["sessions"]["limit"] == 1, e.get("tier"))
    mid = "method:" + uuid.uuid4().hex
    s, _ = call("POST", root + "/methods", {"schemaVersion": 1, "artifact": "BTL-LOCAL-METHOD-1", "id": mid, "name": "smoke", "kind": "FREE_STYLE", "checklistOn": False, "conditions": [], "riskPercent": None, "rr": None}); step("method", s == 200, s)
    sid = "session:" + uuid.uuid4().hex
    job = str(uuid.uuid4()); s, r = call("POST", root + "/sessions", {"id": sid, "name": "smoke", "methodId": mid, "initialBalance": "10000", "startPeriod": "2020-01"}, job=job)
    step("session create accepted", s in (200, 202), s)
    if s == 202: step("session create job", poll(r["jobId"], root).get("state") == "SUCCEEDED", "job")
    s, sm = call("GET", root + f"/sessions/{sid}/summary"); step("summary", s == 200, s)
    start_ns = (1577836800 + 1800) * 10**9      # 2020-01-01 00:30 UTC, the first replay position the UI uses; a large first ADVANCE leaves a pending target that replay-run correctly refuses (ADVANCE_IN_PROGRESS)
    s, r = call("POST", root + f"/sessions/{sid}/commands", {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": sid, "commandId": "command:" + uuid.uuid4().hex,
                "expectedRevision": sm["revision"], "kind": "ADVANCE", "payload": {"targetNs": str(start_ns)}}, job=str(uuid.uuid4()))
    step("advance to first tick", s in (200, 202) and (s == 200 or poll(r["jobId"], root).get("state") == "SUCCEEDED"), s)
    s, sm = call("GET", root + f"/sessions/{sid}/summary")
    request = dict(schemaVersion=1, artifact="BTL-REPLAY-RUN-1", runId=uuid.uuid4().hex, segment=0, sessionId=sid, expectedRevision=sm["revision"], targetNs=str(FEB1_NS - 1))
    s, r = call("POST", root + f"/sessions/{sid}/replay-run", request, job=str(uuid.uuid4())); step("replay-run accepted", s == 202, s)
    job_id, done = r["jobId"], None
    for _ in range(60):
        done = poll(job_id, root, 60)
        if done.get("state") != "SUCCEEDED": step("replay-run job", False, done.get("state")); break
        if not (done.get("result") or {}).get("continuationJobId"): break
        job_id = done["result"]["continuationJobId"]
    step("replay-run reached the Free window end", (done.get("result") or {}).get("targetReached") is True, (done.get("result") or {}).get("targetReached"))
    s, sm = call("GET", root + f"/sessions/{sid}/summary"); step("cursor inside the Free window", int(sm["throughNs"]) >= FEB1_NS - 120 * 10**9 and int(sm["throughNs"]) < FEB1_NS, sm["throughNs"])
    s, r = call("POST", root + f"/sessions/{sid}/replay-run", dict(request, runId=uuid.uuid4().hex, expectedRevision=sm["revision"], targetNs=str(FEB1_NS + 10**9)), job=str(uuid.uuid4()))
    step("Free window boundary enforced", s == 409 and r.get("detail") in ("WINDOW_BOUNDARY", "WINDOW_ENDED_CONTINUATION_ONLY"), r.get("detail"))
    with psycopg.connect(dsn) as c:
        rows = c.execute("SELECT payload FROM btl.tick_checkpoints WHERE session_id=%s", (sid,)).fetchall()
        rows += c.execute("SELECT payload FROM btl.tick_sessions WHERE session_id=%s", (sid,)).fetchall()
    has_v2 = any(V2_TAG in bytes(x[0]) for x in rows)
    out["checkpointFormat"] = "v2" if has_v2 else "v1"
    step("checkpoint format is " + a.expect, has_v2 == (a.expect == "v2"), out["checkpointFormat"])
    return finish(True)


if __name__ == "__main__":
    sys.exit(main())
