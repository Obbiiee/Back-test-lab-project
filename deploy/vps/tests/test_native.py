"""Separate fresh PostgreSQL QA only. Missing DSN is failure, never PASS/skip."""
import os,secrets,sys,unittest,uuid
from pathlib import Path
import psycopg
from psycopg import sql
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from deploy.vps.ops import migrate_and_grant
from deploy.vps.runtime import database_guard
from deploy.vps.settings import ConfigurationError
from infrastructure.database import connect
from cloud.app import create_app
from tests.test_identity import client,RecordingDelivery,PASSWORD
from tests.test_research_sessions import method

class DeploymentNativeTests(unittest.TestCase):
    def test_restricted_runtime_migrations_guards_and_actual_requests(self):
        dsn=os.environ.get('BTL_TEST_DATABASE_URL');self.assertTrue(dsn,'Fresh isolated PostgreSQL required')
        password=secrets.token_urlsafe(32)
        with psycopg.connect(dsn,autocommit=True) as db:
            db.execute('CREATE ROLE btl_owner NOLOGIN')
            db.execute(sql.SQL('CREATE ROLE btl_app LOGIN PASSWORD {}').format(sql.Literal(password)))
        migrate_and_grant(dsn)
        info=psycopg.conninfo.conninfo_to_dict(dsn);limited=psycopg.conninfo.make_conninfo(**{**info,'user':'btl_app','password':password})
        database_guard(limited)
        with self.assertRaises(ConfigurationError):database_guard(dsn)
        with connect(dsn) as db:db.execute('GRANT btl_owner TO btl_app')
        with self.assertRaisesRegex(ConfigurationError,'OWNER_MEMBERSHIP'):database_guard(limited)
        with connect(dsn) as db:db.execute('REVOKE btl_owner FROM btl_app')
        with connect(dsn) as db:db.execute('ALTER ROLE btl_app SUPERUSER')
        with self.assertRaisesRegex(ConfigurationError,'RUNTIME_ROLE'):database_guard(limited)
        with connect(dsn) as db:db.execute('ALTER ROLE btl_app NOSUPERUSER')
        with connect(dsn) as db:db.execute('ALTER SCHEMA btl OWNER TO btl_app')
        with self.assertRaisesRegex(ConfigurationError,'RUNTIME_OWNS_SCHEMA'):database_guard(limited)
        with connect(dsn) as db:db.execute(sql.SQL('ALTER SCHEMA btl OWNER TO {}').format(sql.Identifier(info['user'])))
        # ALTER OWNER rewrites schema ACLs. Prove the fixture changed privileges,
        # then use the shipped idempotent operator to restore explicit grants.
        with connect(dsn) as db:self.assertFalse(db.execute("SELECT has_schema_privilege('btl_app','btl','USAGE')").fetchone()[0])
        with self.assertRaisesRegex(ConfigurationError,'RUNTIME_SCHEMA_USAGE'):database_guard(limited)
        migrate_and_grant(dsn);database_guard(limited)
        delivery=RecordingDelivery();http=client(create_app(limited,secrets.token_urlsafe(48),delivery,rate_limit=1000,sandbox_reset_timezone='UTC'))
        email=uuid.uuid4().hex+'@example.com';r=http.post('/api/v1/auth/register',json=dict(email=email,password=PASSWORD));self.assertEqual(r.status_code,201)
        self.assertEqual(http.post('/api/v1/auth/verify',json=dict(token=delivery.token(email,'verification'))).status_code,200)
        token=http.post('/api/v1/auth/login',data=dict(username=email,password=PASSWORD));self.assertEqual(token.status_code,200)
        headers={'Authorization':'Bearer '+token.json()['access_token']}
        workspace=http.post('/api/v1/workspaces',headers=headers,json=dict(name='Deployment QA'));self.assertEqual(workspace.status_code,201)
        root='/api/v1/workspaces/'+workspace.json()['id']
        self.assertEqual(http.get(root+'/research/catalog',headers=headers).status_code,200)
        self.assertEqual(http.get(root+'/research-v2/catalog',headers=headers).status_code,200)
        m=method();self.assertEqual(http.post(root+'/research-v2/methods',headers=headers,json=m).status_code,200)
        raw=dict(id='session:deploy',name='Deploy QA',methodId=m['id'],initialBalance='10000',startPeriod='2020-01',symbol='EURUSD')
        self.assertEqual(http.post(root+'/research-v2/sessions',headers=headers,json=raw).status_code,200)
        self.assertEqual(http.post(root+'/research-v2/sessions/session:deploy/activate',headers=headers,json={}).status_code,200)
        with self.assertRaises(psycopg.DatabaseError):
            with connect(limited) as db:db.execute('INSERT INTO btl.sandbox_access_events SELECT * FROM btl.sandbox_access_events LIMIT 0')
        with connect(dsn) as db:db.execute("UPDATE public.btl_migrations SET checksum=repeat('f',64) WHERE version=(SELECT min(version) FROM public.btl_migrations)")
        with self.assertRaisesRegex(ConfigurationError,'MIGRATIONS_NOT_CURRENT'):database_guard(limited)

if __name__=='__main__':unittest.main()
