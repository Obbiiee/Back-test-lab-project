"""VPS entrypoint only. No startup migration or provider test-event secret."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'backend'))
from deploy.vps.settings import read_json,runtime,need,ConfigurationError

def database_guard(dsn):
    from infrastructure.database import connect,MIGRATIONS
    from infrastructure.codec import fingerprint
    with connect(dsn) as db:
        row=db.execute("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        need(row is not None and row[0]=='btl_app' and not any(row[1:]),'RUNTIME_ROLE')
        need(not db.execute("SELECT pg_has_role(current_user,'btl_owner','MEMBER')").fetchone()[0],'OWNER_MEMBERSHIP')
        need(db.execute("SELECT count(*) FROM pg_namespace WHERE nspname='btl' AND nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)").fetchone()[0]==0,'RUNTIME_OWNS_SCHEMA')
        need(db.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='btl' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)").fetchone()[0]==0,'RUNTIME_OWNS_TABLES')
        need(db.execute("SELECT has_schema_privilege(current_user,'btl','USAGE')").fetchone()[0],'RUNTIME_SCHEMA_USAGE')
        actual=dict(db.execute('SELECT version,checksum FROM public.btl_migrations').fetchall())
        expected={p.name:fingerprint(p.read_text(encoding='utf-8').encode('utf-8')) for p in MIGRATIONS.glob('[0-9][0-9][0-9]_*.sql')}
        need(actual==expected,'MIGRATIONS_NOT_CURRENT')

def main():
    if sys.argv[1:]==['health']:
        import urllib.request
        req=urllib.request.Request('http://127.0.0.1:8001/api/v1/auth/providers',headers={'X-Forwarded-Proto':'https'})
        with urllib.request.urlopen(req,timeout=5) as response:need(response.status==200,'API_HEALTH')
        return
    need(sys.argv[1:]==['serve'],'OPERATION')
    config=runtime(read_json('/run/secrets/runtime_config'))
    # Remove inherited secret/proxy overrides; this deployment has one explicit trust boundary.
    for key in list(os.environ):
        if key.startswith('BTL_'):del os.environ[key]
    os.environ.update(config)
    database_guard(config['BTL_DATABASE_URL'])
    import uvicorn
    from cloud.app import from_environment
    uvicorn.run(from_environment(),host='127.0.0.1',port=8001,proxy_headers=True,forwarded_allow_ips='127.0.0.1',access_log=False,workers=1)

if __name__=='__main__':
    try:main()
    except Exception as error:
        # No stack trace/DSN/token/code query in container logs.
        print('VPS_START_REFUSED:'+(str(error) if isinstance(error,ConfigurationError) else type(error).__name__),file=sys.stderr);raise SystemExit(1) from None
