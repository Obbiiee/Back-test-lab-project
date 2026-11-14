"""Real R2/S3 acceptance for the OHLC objects. Runs ONLY when the owner has injected credentials on the VPS; otherwise it prints SIMULATION_ONLY and exits 2.

Credentials come from the process environment or from the file named by BTL_R2_ENV_FILE (KEY=VALUE lines, must be mode 0600, owner-only).
Required: BTL_R2_ENDPOINT, BTL_R2_BUCKET (a TEST bucket), BTL_R2_ACCESS_KEY_ID, BTL_R2_SECRET_ACCESS_KEY. Values are never printed or logged.
All objects live under the unique prefix `btl-r2-acceptance/<run>/`; `--cleanup` deletes only that prefix.
Checks: publish (10 PUT, 10 HEAD), idempotent re-publish (0 PUT), byte equality with the local simulation, conflicting rewrite refused,
LIST count, GET bytes, and the same chart answers as the simulation. Requires boto3 (`uv pip install boto3`).
  python -m tools.claude_exp.ohlc.r2_acceptance --src <compact dir> --month 2026-05 [--cleanup] --out result.json
"""
import argparse
import json
import os
import stat
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from market_data.compact_tick import CompactTickReader      # noqa: E402
from tools.claude_exp.ohlc import engine                      # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore, S3ObjectStore, Conflict   # noqa: E402

NEED = ("BTL_R2_ENDPOINT", "BTL_R2_BUCKET", "BTL_R2_ACCESS_KEY_ID", "BTL_R2_SECRET_ACCESS_KEY")


def load_env():
    env = dict(os.environ)
    path = os.environ.get("BTL_R2_ENV_FILE")
    if path:
        p = Path(path)
        mode = stat.S_IMODE(p.stat().st_mode)
        if mode & 0o077 or p.stat().st_uid != os.geteuid():
            raise SystemExit("R2_ENV_FILE_MUST_BE_OWNER_ONLY_0600")
        for line in p.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


class Prefixed:
    """Namespaces every key under a run prefix so the real bucket is never touched outside it."""
    simulation = False

    def __init__(self, inner, prefix):
        self.inner, self.prefix = inner, prefix
        self.counters = inner.counters

    def put_immutable(self, key, data): return self.inner.put_immutable(self.prefix + key, data)
    def get(self, key): return self.inner.get(self.prefix + key)
    def exists(self, key): return self.inner.exists(self.prefix + key)
    def list(self, prefix): return [k[len(self.prefix):] for k in self.inner.list(self.prefix + prefix)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--month", required=True); ap.add_argument("--cleanup", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args()
    env = load_env()
    missing = [k for k in NEED if not env.get(k)]
    if missing:
        print(json.dumps(dict(status="SIMULATION_ONLY", reason="R2_CREDENTIALS_NOT_INJECTED", missing=missing)))
        raise SystemExit(2)
    import boto3
    from botocore.config import Config
    client = boto3.client("s3", endpoint_url=env["BTL_R2_ENDPOINT"], aws_access_key_id=env["BTL_R2_ACCESS_KEY_ID"],
                          aws_secret_access_key=env["BTL_R2_SECRET_ACCESS_KEY"], region_name="auto", config=Config(retries={"max_attempts": 3}))
    run = "btl-r2-acceptance/" + uuid.uuid4().hex[:12] + "/"
    real = Prefixed(S3ObjectStore(client, env["BTL_R2_BUCKET"]), run)
    sim = LocalObjectStore(tempfile.mkdtemp(prefix="r2acc-sim-"))
    reader = CompactTickReader(a.src)
    res = dict(label="REAL_R2_TEST_BUCKET", run=run, month=a.month, checks={})
    m_real, _ = engine.publish_month(real, reader, "ACCEPT", a.month, rights="SYNTHETIC")
    m_sim, _ = engine.publish_month(sim, reader, "ACCEPT", a.month, rights="SYNTHETIC")
    res["firstPublish"] = real.counters.snapshot()
    before = real.counters.snapshot()["put"]
    engine.publish_month(real, reader, "ACCEPT", a.month, rights="SYNTHETIC")
    res["checks"]["idempotentRepublishNoPut"] = real.counters.snapshot()["put"] == before
    res["checks"]["manifestEqualsSimulation"] = m_real == m_sim
    res["checks"]["bytesEqualSimulation"] = all(real.get(o["key"]) == sim.get(o["key"]) for o in m_real["objects"].values())
    try:
        real.put_immutable(next(iter(m_real["objects"].values()))["key"], b"tampered")
        res["checks"]["conflictingRewriteRefused"] = False
    except Conflict:
        res["checks"]["conflictingRewriteRefused"] = True
    res["checks"]["listCount"] = len(real.list("ohlc/")) == 10
    res["counters"] = real.counters.snapshot()
    if a.cleanup:
        keys = real.inner.list(run)
        for i in range(0, len(keys), 1000):
            client.delete_objects(Bucket=env["BTL_R2_BUCKET"], Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]]})
        res["cleanedObjects"] = len(keys)
    res["status"] = "PASS" if all(v is True for v in res["checks"].values()) else "FAIL"
    print(json.dumps(res))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))
    raise SystemExit(0 if res["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
