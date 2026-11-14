"""Standalone chart service process for the combined capacity test (QA/measurement only, loopback, prototype auth).

Serves the Claude cursor-bound chart API (ohlc/service.py, unchanged) from a local-directory object store (SIMULATION of R2) over a
compact tick reader (for the forming candle). Sessions s-1..s-N / tokens tok-1..tok-N are pre-created at a fixed cursor.
A loopback-only QA endpoint POST /__qa/advance?session=..&seconds=.. moves a session cursor like the replay owner would.
  python -m tools.claude_exp.stack.chart_server --store DIR --source-compact DIR --source-hash H --traders N [--port P]
"""
import argparse, json, sys, threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from market_data.compact_tick import CompactTickReader          # noqa: E402
from tools.claude_exp.compact2 import open_compact              # noqa: E402  (v1 or v2 compact tick month)
from tools.claude_exp.ohlc import service as svc                # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore        # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True); ap.add_argument("--source-compact", required=True); ap.add_argument("--source-hash", required=True)
    ap.add_argument("--traders", type=int, required=True); ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--cursor", default="2026-01-01T00:00:00"); ap.add_argument("--cache-objects", type=int, default=64)
    a = ap.parse_args()
    root = Path(a.source_compact)
    manifest = json.loads(((root / "compact2.json") if (root / "compact2.json").exists() else (root / "compact.json")).read_text())
    reader = open_compact(root, expected_manifest_hash=manifest["manifestHash"])
    cursor = int(datetime.fromisoformat(a.cursor).replace(tzinfo=timezone.utc).timestamp()) * 10**9
    sessions = {f"s-{i}": svc.Session(f"s-{i}", f"u{i}", "EURUSD", a.source_hash, "MID", cursor) for i in range(1, a.traders + 1)}
    tokens = {f"tok-{i}": f"u{i}" for i in range(1, a.traders + 1)}
    service = svc.ChartService(LocalObjectStore(a.store), {"EURUSD": reader}, sessions, tokens, cache_objects=a.cache_objects)
    metrics = []
    base = svc.make_handler(service, metrics)

    class H(base):
        def do_POST(self):
            u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                assert u.path == "/__qa/advance"
                s = sessions[q["session"]]
                service.advance(q["session"], s.cursor_ns + int(q["seconds"]) * 10**9)
                code, body = 200, b"{}"
            except Exception:
                code, body = 400, b"{}"
            self.send_response(code); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    server.daemon_threads = True
    print(json.dumps({"ready": True, "port": server.server_address[1]}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
