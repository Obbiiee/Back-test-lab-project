"""Public Google-only API (loopback 127.0.0.1:8010, reached only through Caddy). Composition: deploy/vps/google_staging.create_google_staging_app with
workspace metadata only: the route table is pruned to Google/auth endpoints and workspace create/list/get; research, execution, billing, support and
password endpoints do not exist in this process. Secrets come from files/environment prepared by the operator; nothing is printed."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
HOME = Path.home()


def main():
    import uvicorn
    from deploy.vps.google_staging import create_google_staging_app
    db = dict(line.split('=', 1) for line in (HOME / '.config' / 'riksora-db.env').read_text().split() if '=' in line)
    secret = (HOME / '.config' / 'riksora-auth-secret').read_text().strip()
    dsn = f"host=127.0.0.1 port=54450 dbname=btl user=btl_app password={db['PG_APP_PASSWORD']}"
    app = create_google_staging_app(dsn, secret, workspace_metadata=True,
                                    google_client_id=os.environ['BTL_GOOGLE_CLIENT_ID'], google_client_secret=os.environ['BTL_GOOGLE_CLIENT_SECRET'],
                                    google_redirect_uri=os.environ['BTL_GOOGLE_REDIRECT_URI'])
    uvicorn.run(app, host='127.0.0.1', port=8010, proxy_headers=True, forwarded_allow_ips='127.0.0.1', access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
