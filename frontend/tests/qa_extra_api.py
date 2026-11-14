"""Extra API instance for the multi-process capacity test (QA/measurement only; loopback; same code as the product app).

Started by the QA harness (RIKSORA_QA_API_INSTANCES=K) as a separate OS process. Inherits the harness environment (the synthetic Monthly
Parquet pin), receives the runtime DSN/secret on stdin (never on argv) and serves the same `cloud.app.create_app` on its own port with the
harness's self-signed certificate. All instances share one PostgreSQL queue; worker slots are fenced by global advisory locks, so total
concurrent jobs stay bounded by the configured worker count.
"""
import json, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / 'backend')]


def main():
    cfg = json.loads(sys.stdin.readline())
    import uvicorn
    from cloud.app import create_app
    from tests.test_identity import RecordingDelivery
    app = create_app(cfg['dsn'], cfg['secret'], RecordingDelivery(), rate_limit=cfg['rate_limit'], sandbox_reset_timezone='UTC')
    uvicorn.run(app, host='127.0.0.1', port=cfg['port'], ssl_certfile=cfg['cert'], ssl_keyfile=cfg['key'],
                proxy_headers=True, forwarded_allow_ips='127.0.0.1', access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
