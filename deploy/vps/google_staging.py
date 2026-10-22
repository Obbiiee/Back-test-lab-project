"""Explicit Google staging compositions, never a production data acceptance.

No installation, migration, role grant or live configuration happens on import.
Metadata-only default keeps research absent. The separate demo factory opts into
the existing authored synthetic v2 simulator, never real data or payments.
"""
from contextlib import asynccontextmanager

from cloud.app import create_app


AUTH_PATHS = frozenset({
    '/api/v1/auth/me', '/api/v1/auth/logout', '/api/v1/auth/logout-all',
    '/api/v1/auth/google/start', '/api/v1/auth/google/callback',
    '/api/v1/auth/google/exchange',
})
WORKSPACE_METHODS = {
    '/api/v1/workspaces': frozenset({'GET', 'POST'}),
    '/api/v1/workspaces/{workspace_id}': frozenset({'GET'}),
}
_DEMO_PREFIX = '/api/v1/workspaces/{workspace_id}/research-v2'
DEMO_METHODS = {
    _DEMO_PREFIX + '/access': frozenset({'GET'}),
    _DEMO_PREFIX + '/catalog': frozenset({'GET'}),
    _DEMO_PREFIX + '/methods': frozenset({'POST'}),
    _DEMO_PREFIX + '/sessions': frozenset({'POST'}),
    _DEMO_PREFIX + '/sessions/{session_id}': frozenset({'GET'}),
    _DEMO_PREFIX + '/sessions/{session_id}/{operation}': frozenset({'GET', 'POST'}),
}


class NoEmailDelivery:
    async def send(self, *args, **kwargs):
        raise RuntimeError('EMAIL_DISABLED_IN_GOOGLE_STAGING')


class DemoAuthAdmission:
    """Keep authentication at30/IP/min while allowing interactive replay IO."""
    def __init__(self, app, dsn):
        from identity.boundary import IdentityBoundary
        self.app = app
        self.rate = IdentityBoundary(app, dsn, limit=30)

    async def __call__(self, scope, receive, send):
        if (scope['type'] == 'http' and scope.get('scheme') == 'https'
                and scope.get('path', '').startswith('/api/v1/auth/')):
            from starlette.responses import JSONResponse
            try:
                ip = (scope.get('client') or ('unknown',))[0]
                admitted = await self.rate._attempt('demo-auth:' + ip, 30)
            except Exception:
                return await JSONResponse({'detail': 'SERVICE_UNAVAILABLE'}, status_code=503,
                    headers={'Cache-Control': 'no-store'})(scope, receive, send)
            if not admitted:
                return await JSONResponse({'detail': 'RATE_LIMITED'}, status_code=429,
                    headers={'Cache-Control': 'no-store', 'Retry-After': '60'})(scope, receive, send)
        await self.app(scope, receive, send)


@asynccontextmanager
async def metadata_lifespan(app):
    # Metadata requests need no research worker or scheduler.
    yield


def _google_required(google):
    if not all(google.get(k) for k in (
        'google_client_id', 'google_client_secret', 'google_redirect_uri'
    )):
        raise ValueError('GOOGLE_CONFIGURATION_REQUIRED')


def _restrict_routes(app, allowed):
    def permitted(route, prefix=''):
        path = prefix + getattr(route, 'path', '')
        if path in AUTH_PATHS:
            return True
        methods = frozenset(getattr(route, 'methods', ()))
        return path in allowed and bool(methods) and methods <= allowed[path]
    kept = []
    for route in app.router.routes:
        # FastAPI can retain included routers lazily, without a direct path.
        # Inspect only this newly constructed app's routers, before first use.
        original = getattr(route, 'original_router', None)
        context = getattr(route, 'include_context', None)
        if original is not None and context is not None:
            original.routes[:] = [r for r in original.routes if permitted(r, context.prefix)]
            if original.routes:
                kept.append(route)
        elif permitted(route):
            kept.append(route)
    app.router.routes[:] = kept
    app.router.lifespan_context = metadata_lifespan


def create_google_staging_app(dsn, auth_secret, *, workspace_metadata=False, **google):
    if type(workspace_metadata) is not bool:
        raise ValueError('WORKSPACE_OPT_IN_MUST_BE_BOOLEAN')
    _google_required(google)
    app = create_app(dsn, auth_secret, NoEmailDelivery(), **google)
    _restrict_routes(app, WORKSPACE_METHODS if workspace_metadata else {})

    @app.get('/api/v1/auth/providers')
    async def providers():
        return {'schemaVersion': 1, 'password': False,
                'googleConfigured': True, 'billingConfigured': False}
    return app


def create_google_demo_app(dsn, auth_secret, **google):
    """Separate opt-in short synthetic simulator, no password/payment/member API.

    Existing v2 source/profile guards, Free quotas and no-look-ahead stay intact.
    Never use this factory as evidence of acquired or licensed real history.
    """
    _google_required(google)
    if any(k in google for k in ('sandbox_reset_timezone', 'sandbox_event_secret', 'sandbox_billing')):
        raise ValueError('DEMO_CONFIGURATION_FIXED')
    request_limit = google.pop('rate_limit', 600)
    if type(request_limit) is not int or not 60 <= request_limit <= 1200:
        raise ValueError('BOUNDED_DEMO_REQUEST_LIMIT_REQUIRED')
    app = create_app(dsn, auth_secret, NoEmailDelivery(), sandbox_reset_timezone='UTC',
                     rate_limit=request_limit, **google)
    _restrict_routes(app, {**WORKSPACE_METHODS, **DEMO_METHODS})
    app.add_middleware(DemoAuthAdmission, dsn=dsn)

    @app.get('/api/v1/auth/providers')
    async def providers():
        return {'schemaVersion': 1, 'password': False, 'googleConfigured': True,
                'billingConfigured': False, 'demoConfigured': True}
    return app


_METADATA_GRANTS = (
    'GRANT USAGE ON SCHEMA btl TO {}',
    'GRANT SELECT,INSERT ON btl.workspaces,btl.memberships TO {}',
    'GRANT UPDATE(id) ON btl.workspaces TO {}',
    'GRANT UPDATE(user_id) ON btl.memberships TO {}',
)


def _runtime_role(db, role):
    if role != 'btl_app':
        raise ValueError('EXPECTED_RUNTIME_ROLE')
    row = db.execute(
        'SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls '
        'FROM pg_roles WHERE rolname=%s', (role,)
    ).fetchone()
    if row is None or any(row):
        raise ValueError('UNSAFE_RUNTIME_ROLE')
    if db.execute("SELECT pg_has_role(%s,'btl_owner','MEMBER')", (role,)).fetchone()[0]:
        raise ValueError('RUNTIME_OWNER_MEMBERSHIP')
    if db.execute('SELECT current_user=%s', (role,)).fetchone()[0]:
        raise ValueError('OPERATOR_CONNECTION_REQUIRED')
    if db.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='btl' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=%s)) "
        "OR EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='btl' "
        "AND nspowner=(SELECT oid FROM pg_roles WHERE rolname=%s))", (role, role)
    ).fetchone()[0]:
        raise ValueError('RUNTIME_OWNS_DATABASE_OBJECTS')


def grant_workspace_metadata(dsn, role='btl_app'):
    """Explicit operator operation; existing migrated database and role only.

    Adds only metadata create/list/get permissions. Identity permissions must
    already exist. Never creates users, schemas, tables or application OWNERs.
    """
    from psycopg import sql
    from infrastructure.database import connect
    with connect(dsn) as db:
        _runtime_role(db, role)
        for statement in _METADATA_GRANTS:
            db.execute(sql.SQL(statement).format(sql.Identifier(role)))


def grant_google_demo_runtime(dsn):
    """Explicit operator opt-in; no migration, role creation or privileged tier.

    Preserves the API role's inability to mint sandbox plan events. The private
    schema is pre-existing. Existing Google identity permissions are prerequisite.
    """
    from psycopg import sql
    from infrastructure.database import connect
    statements = (*_METADATA_GRANTS,
        'GRANT SELECT,INSERT ON btl.tick_sessions,btl.tick_commands,btl.tick_events,btl.tick_checkpoints TO {}',
        'GRANT UPDATE(revision,payload,content_hash) ON btl.tick_sessions TO {}',
        'GRANT SELECT,INSERT ON btl.tick_methods,btl.tick_v2_research_sessions,btl.tick_v2_order_reviews TO {}',
        'GRANT SELECT,INSERT,UPDATE ON btl.tick_v2_journal_notes TO {}',
        'GRANT SELECT,INSERT,UPDATE ON btl.v2_access_accounts,btl.v2_access_sessions TO {}',
        'GRANT SELECT,INSERT ON btl.v2_access_windows TO {}',
        'GRANT SELECT ON btl.sandbox_access_events TO {}')
    with connect(dsn) as db:
        _runtime_role(db, 'btl_app')
        for statement in statements:
            db.execute(sql.SQL(statement).format(sql.Identifier('btl_app')))
