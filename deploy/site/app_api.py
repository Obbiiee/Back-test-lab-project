"""Public application API for riksora.com (loopback 127.0.0.1:8010; Caddy proxies only /api/v1/auth/* and /api/v1/workspaces*).

The REAL product app (cloud.app.create_app: identity, workspaces, research Sessions on the durable queue with in-process native workers, Free/Pro
entitlement enforcement) minus everything a public Google-only beta must not expose: password registration/login/recovery/verification, member
administration, support intake and the OpenAPI document. Data is the repository-authored SYNTHETIC monthly Parquet only (never market data).
Compact checkpoint V2 is NOT enabled (it remains opt-in QA). Secrets come from files/environment prepared by the operator; nothing is printed."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
HOME = Path.home()

DENIED_PREFIXES = ('/api/v1/auth/register', '/api/v1/auth/login', '/api/v1/auth/forgot-password', '/api/v1/auth/reset-password', '/api/v1/auth/verify',
                   '/api/v1/auth/request-verify-token', '/api/v1/support', '/openapi.json')
DENIED_REGEX = r'^/api/v1/workspaces/\{[a-z_]+\}/members'


def prune(app):
    import re
    def denied(path):
        return path.startswith(DENIED_PREFIXES) or re.match(DENIED_REGEX, path) is not None or path == '/api/v1/auth/providers'
    kept = []
    for route in app.router.routes:
        original, context = getattr(route, 'original_router', None), getattr(route, 'include_context', None)
        if original is not None and context is not None:
            original.routes[:] = [r for r in original.routes if not denied(context.prefix + getattr(r, 'path', ''))]
            if original.routes:
                kept.append(route)
        elif not denied(getattr(route, 'path', '')):
            kept.append(route)
    app.router.routes[:] = kept

    @app.get('/api/v1/auth/providers')
    async def providers():
        return {'schemaVersion': 1, 'password': False, 'googleConfigured': True, 'billingConfigured': False, 'researchConfigured': True}


class NoEmailDelivery:
    async def send(self, *args, **kwargs):
        raise RuntimeError('EMAIL_DISABLED_IN_PUBLIC_BETA')


def main():
    import uvicorn
    from cloud.app import create_app
    db = dict(line.split('=', 1) for line in (HOME / '.config' / 'riksora-db.env').read_text().split() if '=' in line)
    secret = (HOME / '.config' / 'riksora-auth-secret').read_text().strip()
    dsn = f"host=127.0.0.1 port=54450 dbname=btl user=btl_app password={db['PG_APP_PASSWORD']}"
    app = create_app(dsn, secret, NoEmailDelivery(), rate_limit=30, sandbox_reset_timezone='UTC',
                     google_client_id=os.environ['BTL_GOOGLE_CLIENT_ID'], google_client_secret=os.environ['BTL_GOOGLE_CLIENT_SECRET'],
                     google_redirect_uri=os.environ['BTL_GOOGLE_REDIRECT_URI'])
    prune(app)
    uvicorn.run(app, host='127.0.0.1', port=8010, proxy_headers=True, forwarded_allow_ips='127.0.0.1', access_log=False, log_level='warning')


if __name__ == '__main__':
    main()
