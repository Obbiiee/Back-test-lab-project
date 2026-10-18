"""Explicit migration/grants only; separately mounted owner config, never API startup."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'backend'))
from deploy.vps.settings import read_json,connection,need,ConfigurationError

def migrate_and_grant(dsn):
    from infrastructure.database import migrate,connect,grant_runtime,grant_workspace_runtime
    from identity.google_store import grant_google_runtime
    from cloud.sandbox_access import grant_sandbox_access_runtime
    migrate(dsn)
    with connect(dsn) as db:
        role=db.execute("SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname='btl_app'").fetchone()
        need(role is not None and role[0] and not any(role[1:]),'CREATE_RESTRICTED_RUNTIME_ROLE_FIRST')
        need(not db.execute("SELECT pg_has_role('btl_app','btl_owner','MEMBER')").fetchone()[0],'OWNER_MEMBERSHIP')
    for grant in (grant_runtime,grant_workspace_runtime,grant_google_runtime,grant_sandbox_access_runtime):grant(dsn,'btl_app')
    with connect(dsn) as db:
        # Existing v1 routes remain compatible until the separately accepted v2 UI cutover.
        db.execute('GRANT SELECT ON public.btl_migrations TO btl_app')
        db.execute('GRANT SELECT,INSERT ON btl.tick_research_sessions,btl.tick_order_reviews TO btl_app')
        db.execute('GRANT SELECT,INSERT,UPDATE ON btl.tick_journal_notes TO btl_app')

def main():
    need(sys.argv[1:]==['migrate'],'OPERATION')
    config=read_json('/run/secrets/owner_config');need(set(config)=={'BTL_DATABASE_URL'},'OWNER_CONFIG_KEYS')
    migrate_and_grant(connection(config['BTL_DATABASE_URL'],'btl_owner'))
    print('EXPLICIT_MIGRATION_AND_GRANTS_COMPLETED_NOT_RELEASE_ACCEPTANCE')

if __name__=='__main__':
    try:main()
    except Exception as error:print('VPS_OPERATOR_REFUSED:'+(str(error) if isinstance(error,ConfigurationError) else type(error).__name__),file=sys.stderr);raise SystemExit(1) from None
