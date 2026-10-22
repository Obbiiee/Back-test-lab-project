"""Opt-in Google staging with persisted workspace metadata only.

No installation, migration, role grant or live configuration happens on import.
Research, financial, membership administration and password routes stay absent.
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


class NoEmailDelivery:
    async def send(self, *args, **kwargs):
        raise RuntimeError('EMAIL_DISABLED_IN_GOOGLE_STAGING')


@asynccontextmanager
async def metadata_lifespan(app):
    # Metadata requests need no research worker or scheduler.
    yield


def create_google_staging_app(dsn, auth_secret, *, workspace_metadata=False, **google):
    if type(workspace_metadata) is not bool:
        raise ValueError('WORKSPACE_OPT_IN_MUST_BE_BOOLEAN')
    if not all(google.get(k) for k in (
        'google_client_id', 'google_client_secret', 'google_redirect_uri'
    )):
        raise ValueError('GOOGLE_CONFIGURATION_REQUIRED')
    app = create_app(dsn, auth_secret, NoEmailDelivery(), **google)
    def permitted(route, prefix=''):
        path = prefix + getattr(route, 'path', '')
        if path in AUTH_PATHS:
            return True
        methods = frozenset(getattr(route, 'methods', ()))
        return (workspace_metadata and path in WORKSPACE_METHODS
                and bool(methods) and methods <= WORKSPACE_METHODS[path])
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

    @app.get('/api/v1/auth/providers')
    async def providers():
        return {'schemaVersion': 1, 'password': False,
                'googleConfigured': True, 'billingConfigured': False}
    return app


def grant_workspace_metadata(dsn, role='btl_app'):
    """Explicit operator operation; existing migrated database and role only.

    Adds only metadata create/list/get permissions. Identity permissions must
    already exist. Never creates users, schemas, tables or application OWNERs.
    """
    from psycopg import sql
    from infrastructure.database import connect
    if role != 'btl_app':
        raise ValueError('EXPECTED_RUNTIME_ROLE')
    with connect(dsn) as db:
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
        for statement in (
            'GRANT USAGE ON SCHEMA btl TO {}',
            'GRANT SELECT,INSERT ON btl.workspaces,btl.memberships TO {}',
            'GRANT UPDATE(id) ON btl.workspaces TO {}',
            'GRANT UPDATE(user_id) ON btl.memberships TO {}',
        ):
            db.execute(sql.SQL(statement).format(sql.Identifier(role)))
