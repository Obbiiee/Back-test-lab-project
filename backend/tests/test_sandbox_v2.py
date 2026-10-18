"""Native HTTPS ASGI sandbox tests; no real merchant, browser or SMTP claim."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import os,secrets,uuid,unittest,time,hmac,hashlib
from unittest.mock import patch
from cloud.app import create_app
from cloud.sandbox_access import SandboxAccess
from contracts.canonical import canonical_bytes,content_hash
from contracts.primitives import ContractError
from infrastructure.database import migrate,connect
from tests.test_identity import client,RecordingDelivery,PASSWORD
from tests.test_research_sessions import method
from tests.test_kernel_v2 import opening
from tests.test_execution_v2_postgres import command
from execution.research_fixture_v2 import START_NS,STEP_NS

DSN=os.getenv('BTL_TEST_DATABASE_URL')
@unittest.skipUnless(DSN,'Requires isolated native PostgreSQL; skip is not acceptance')
class SandboxV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(DSN)
    def setUp(self):
        self.delivery=RecordingDelivery();self.secret=secrets.token_urlsafe(48)
        self.app=create_app(DSN,secrets.token_urlsafe(48),self.delivery,rate_limit=1000,sandbox_reset_timezone='UTC',sandbox_event_secret=self.secret)
        self.client=client(self.app);self.actor,self.headers=self.account()
        self.ws=self.workspace();self.root='/api/v1/workspaces/'+self.ws+'/research-v2'
        self.m=method();self.post('/methods',self.m)
        self.sid='session:demo';self.rev=0;self.post('/sessions',self.raw(self.sid))
        self.path='/sessions/'+self.sid
    def account(self):
        email=uuid.uuid4().hex+'@example.com'
        r=self.client.post('/api/v1/auth/register',json=dict(email=email,password=PASSWORD));self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.client.post('/api/v1/auth/verify',json=dict(token=self.delivery.token(email,'verification'))).status_code,200)
        token=self.client.post('/api/v1/auth/login',data=dict(username=email,password=PASSWORD));self.assertEqual(token.status_code,200,token.text)
        return r.json()['id'],{'Authorization':'Bearer '+token.json()['access_token']}
    def workspace(self):
        r=self.client.post('/api/v1/workspaces',headers=self.headers,json=dict(name='Sandbox QA'));self.assertEqual(r.status_code,201,r.text);return r.json()['id']
    def raw(self,sid):return dict(id=sid,name='Demo',methodId=self.m['id'],initialBalance='10000',startPeriod='2020-01',symbol='EURUSD')
    def post(self,path,raw,status=200,root=None):
        r=self.client.post((root or self.root)+path,headers=self.headers,json=raw)
        self.assertEqual(r.status_code,status,r.text);return r.json()
    def get(self,path,status=200):
        r=self.client.get(self.root+path,headers=self.headers);self.assertEqual(r.status_code,status,r.text);return r.json()
    def call(self,kind,payload):
        result=self.post(self.path+'/commands',command(self.sid,'cmd:'+str(self.rev),self.rev,kind,payload));self.rev=result['state']['revision'];return result
    def grant(self,tier='PRO',sequence=1,event_id=None):
        raw=dict(schemaVersion=1,artifact='BTL-SANDBOX-ACCESS-EVENT-1',id=event_id or 'event:'+uuid.uuid4().hex,accountId=self.actor,sequence=sequence,tier=tier,expiresAt=str(int(time.time())+3600),mode='SANDBOX')
        signature=hmac.new(self.secret.encode(),canonical_bytes(raw),hashlib.sha256).hexdigest()
        return SandboxAccess(DSN,'UTC',event_secret=self.secret).event(raw,signature),signature
    def test_exact_order_statistics_journal_and_honest_sandbox_status(self):
        self.post(self.path+'/commands',command(self.sid,'denied',0,'ADVANCE',dict(targetNs=str(START_NS))),409)
        first=self.post(self.path+'/activate',{});self.assertEqual(self.post(self.path+'/activate',{}),first)
        self.call('ADVANCE',dict(targetNs=str(START_NS)))
        review=self.post(self.path+'/review',dict(id='order:one',expectedRevision=self.rev,payload=opening(entry='999',sl='1.09902')))
        request=dict(reviewId=review['id'],reviewHash=content_hash(review))
        receipt=self.post(self.path+'/confirm',request);self.rev=receipt['state']['revision']
        self.call('ADVANCE',dict(targetNs=str(START_NS+STEP_NS)))
        self.call('CLOSE',dict(orderId='order:one',quantity=None))
        self.call('ADVANCE',dict(targetNs=str(START_NS+2*STEP_NS)))
        stats=self.get(self.path+'/statistics');self.assertEqual(stats['account']['balance'],'10000.03')
        self.assertEqual(stats['metrics']['totalR'],dict(numerator='3',denominator='100'))
        self.assertEqual(self.post(self.path+'/confirm',request),receipt)
        self.assertEqual(self.get(self.path)['state']['revision'],self.rev)
        note=dict(orderId='order:one',expectedNoteRevision=0,text='Verified',tags=['qa'])
        self.post(self.path+'/journal',note);self.assertEqual(len(self.get(self.path+'/journal')['notes']),1)
        access=self.get('/access');self.assertEqual((access['tier'],access['mode'],access['fundsCollected']),('FREE','SANDBOX',False))
        self.post(self.path+'/commands',command(self.sid,'outside',self.rev,'ADVANCE',dict(targetNs=first['endNs'])),409)
    def test_five_saved_account_wide_atomic_quota_trash_restore(self):
        for i in range(4):self.post('/sessions',self.raw('session:'+str(i)))
        ws=self.workspace();root='/api/v1/workspaces/'+ws+'/research-v2';self.post('/methods',self.m,root=root)
        self.post('/sessions',self.raw('session:six'),409,root=root)
        with connect(DSN) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',(ws,'session:six')).fetchone()[0],0)
        self.post(self.path+'/trash',{});self.post('/sessions',self.raw('session:six'),root=root)
        self.post(self.path+'/restore',{},409)
        self.grant();self.post(self.path+'/restore',{})
        self.assertEqual(self.get('/access')['savedSessions'],6)
        self.assertEqual(self.get(self.path)['metadata']['id'],self.sid)
    def test_timeframe_view_is_read_only_causal_and_scoped(self):
        self.post(self.path+'/activate',{})
        self.call('ADVANCE',dict(targetNs=str(START_NS+4*STEP_NS)))
        before=self.get(self.path)
        for timeframe in ('1m','3m','5m','15m','30m','1h','2h','4h','D'):
            value=self.post(self.path+'/view',dict(timeframe=timeframe))
            self.assertEqual(value['state'],before['state'])
            self.assertEqual(value['chart']['timeframe'],timeframe)
            self.assertTrue(all(c['time']*1000000000<=int(before['state']['throughNs']) for c in value['chart']['candles']))
        for raw in ({},{'timeframe':'1s'},{'timeframe':None},{'timeframe':'1m','source':'real'}):self.post(self.path+'/view',raw,422)
        _,other=self.account()
        self.assertEqual(self.client.post(self.root+self.path+'/view',headers=other,json={'timeframe':'1m'}).status_code,404)
        self.assertEqual(self.client.post(self.root+self.path+'/view',json={'timeframe':'1m'}).status_code,401)
        self.assertEqual(self.get(self.path)['state'],before['state'])
    def test_daily_concurrent_activation_global_account_and_pro(self):
        self.post('/sessions',self.raw('session:two'))
        paths=[self.path+'/activate','/sessions/session:two/activate']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda path:self.client.post(self.root+path,headers=self.headers,json={}),paths))
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        self.assertEqual(self.get('/access')['freeActivationAvailable'],False)
        self.grant()
        for path in paths:self.post(path,{})
        self.assertEqual(self.get('/access')['tier'],'PRO')
    def test_event_signature_replay_expiry_order_and_policy_pins(self):
        access=SandboxAccess(DSN,'UTC',event_secret=self.secret);raw,sig=self.grant()
        self.assertEqual(access.event(raw,sig),raw)
        with self.assertRaises(ContractError):access.event(raw,'0'*64)
        changed={**raw,'tier':'FREE'};signed=hmac.new(self.secret.encode(),canonical_bytes(changed),hashlib.sha256).hexdigest()
        with self.assertRaisesRegex(ContractError,'IDEMPOTENCY_CONFLICT'):access.event(changed,signed)
        with self.assertRaisesRegex(ContractError,'STALE_BILLING_EVENT'):self.grant(sequence=1)
        self.grant('FREE',2);self.assertEqual(self.get('/access')['tier'],'FREE')
        self.grant('PRO',3)
        with patch.object(SandboxAccess,'now',return_value=datetime.now(timezone.utc)+timedelta(days=2)):
            self.assertEqual(self.get('/access')['tier'],'FREE')
        with connect(DSN) as db:
            with self.assertRaisesRegex(ContractError,'ACCESS_POLICY_DRIFT'):SandboxAccess(DSN,'Asia/Jakarta').lock(db,self.actor)
    def test_verified_membership_source_boundary_disabled_default_and_logout(self):
        self.assertEqual(self.client.get(self.root+'/catalog').status_code,401)
        _,other=self.account();self.assertEqual(self.client.get(self.root+'/catalog',headers=other).status_code,404)
        self.assertEqual(self.client.get(self.root+'/catalog?source=real',headers=self.headers).status_code,403)
        self.assertEqual(self.client.get(self.root+'/catalog',headers={**self.headers,'x-btl-source':'historical'}).status_code,403)
        old=client(create_app(DSN,secrets.token_urlsafe(48),self.delivery,rate_limit=1000))
        self.assertEqual(old.get(self.root+'/catalog',headers=self.headers).status_code,404)
        self.assertEqual(self.client.post('/api/v1/auth/logout',headers=self.headers).status_code,204)
        self.assertEqual(self.client.get(self.root+'/catalog',headers=self.headers).status_code,401)

    def test_user_deactivation_waits_through_inner_commit(self):
        from threading import Event
        from execution.research_v2 import ResearchApplicationV2
        entered,release=Event(),Event();original=ResearchApplicationV2.create_method
        record=method();marker='sandbox_revoke_'+uuid.uuid4().hex
        def held(app,raw):
            entered.set();self.assertTrue(release.wait(8));return original(app,raw)
        def revoke():
            with connect(DSN) as db:
                db.execute("SELECT set_config('application_name',%s,true)",(marker,))
                db.execute('UPDATE btl.users SET is_active=false WHERE id=%s',(self.actor,))
        with patch('cloud.research_v2.ResearchApplicationV2.create_method',held),ThreadPoolExecutor(max_workers=2) as pool:
            writing=pool.submit(self.client.post,self.root+'/methods',headers=self.headers,json=record)
            try:
                self.assertTrue(entered.wait(5));revoking=pool.submit(revoke);blocked=False;deadline=time.monotonic()+4
                while time.monotonic()<deadline:
                    with connect(DSN) as db:blocked=db.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event_type='Lock')",(marker,)).fetchone()[0]
                    if blocked:break
                    time.sleep(.01)
                self.assertTrue(blocked)
            finally:release.set()
            self.assertEqual(writing.result(timeout=10).status_code,200);revoking.result(timeout=10)
        self.assertEqual(self.client.get(self.root+'/catalog',headers=self.headers).status_code,401)
        with connect(DSN) as db:self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s',(self.ws,record['id'])).fetchone()[0],1)
    def test_actual_restricted_role_and_immutable_capacity_evidence(self):
        import psycopg
        from psycopg import sql
        from contextlib import contextmanager
        from infrastructure.database import grant_identity_runtime,grant_workspace_runtime
        from cloud.sandbox_access import grant_sandbox_access_runtime
        from cloud.research_v2 import run
        role='sandbox_role_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        grant_identity_runtime(DSN,role);grant_workspace_runtime(DSN,role);grant_sandbox_access_runtime(DSN,role)
        @contextmanager
        def restricted(dsn):
            with connect(dsn) as db:
                db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)));yield db
        access=SandboxAccess(DSN,'UTC',event_secret=self.secret)
        with patch('cloud.research_v2.connect',restricted),patch('execution.research_v2.connect',restricted),patch('execution.postgres_v2.connect',restricted):
            run(access,uuid.UUID(self.actor),uuid.UUID(self.ws),'activate',(self.sid,))
            value=run(access,uuid.UUID(self.actor),uuid.UUID(self.ws),'apply',(self.sid,command(self.sid,'advance',0,'ADVANCE',dict(targetNs=str(START_NS)))))
            self.assertTrue(value['durable'])
            run(access,uuid.UUID(self.actor),uuid.UUID(self.ws),'create_session',(self.raw('session:runtime'),))
            self.assertEqual(run(access,uuid.UUID(self.actor),uuid.UUID(self.ws),'access',())['savedSessions'],2)
        for table in ('v2_access_windows','sandbox_access_events','v2_access_accounts'):
            with self.assertRaises(psycopg.DatabaseError):
                with restricted(DSN) as db:db.execute('DELETE FROM btl.'+table)
        with self.assertRaises(psycopg.DatabaseError):
            with restricted(DSN) as db:db.execute('UPDATE btl.v2_access_sessions SET actor_id=%s WHERE actor_id=%s',(str(uuid.uuid4()),self.actor))
    def test_reset_timezone_clock_boundary_and_trash_retention(self):
        stamp=datetime(2026,10,17,17,1,tzinfo=timezone.utc)
        with connect(DSN) as db:
            with patch.object(SandboxAccess,'now',return_value=stamp):
                self.assertEqual(SandboxAccess(DSN,'UTC').status(db,self.actor)['entitlementDay'],'2026-10-17')
                self.assertEqual(SandboxAccess(DSN,'Asia/Jakarta').status(db,self.actor)['entitlementDay'],'2026-10-18')
        self.post(self.path+'/activate',{});self.post(self.path+'/trash',{})
        self.assertEqual(self.get(self.path)['savedState'],'TRASHED')
        with patch.object(SandboxAccess,'now',return_value=datetime.now(timezone.utc)+timedelta(days=31)):
            self.post(self.path+'/restore',{},409)
        self.assertEqual(self.get(self.path)['state']['revision'],0)

    def test_native_restore_preserves_capacity_window_pro_receipt_and_trash(self):
        import psycopg,tempfile
        from psycopg import sql
        from pathlib import Path
        from infrastructure.database import backup,restore
        activated=self.post(self.path+'/activate',{});event,sig=self.grant();self.post(self.path+'/trash',{})
        info=psycopg.conninfo.conninfo_to_dict(DSN);name='sandbox_restore_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
        restored=psycopg.conninfo.make_conninfo(**{**info,'dbname':name})
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'sandbox.dump';sha=backup(DSN,target,os.environ['BTL_PG_BIN']);restore(restored,target,sha,os.environ['BTL_PG_BIN'])
        cold=client(create_app(restored,secrets.token_urlsafe(48),RecordingDelivery(),rate_limit=1000,sandbox_reset_timezone='UTC'))
        status=cold.get(self.root+'/access',headers=self.headers);self.assertEqual(status.status_code,200,status.text)
        self.assertEqual((status.json()['tier'],status.json()['freeActivationAvailable'],status.json()['savedSessions']),('PRO',False,0))
        view=cold.get(self.root+self.path,headers=self.headers);self.assertEqual(view.json()['savedState'],'TRASHED')
        self.assertEqual(cold.post(self.root+self.path+'/restore',headers=self.headers,json={}).status_code,200)
        self.assertEqual(cold.post(self.root+self.path+'/activate',headers=self.headers,json={}).json(),activated)
        self.assertEqual(SandboxAccess(restored,'UTC',event_secret=self.secret).event(event,sig),event)
    def test_saved_quota_race_and_disabled_payment_events(self):
        for i in range(3):self.post('/sessions',self.raw('session:r'+str(i)))
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda i:self.client.post(self.root+'/sessions',headers=self.headers,json=self.raw('session:race'+str(i))),range(2)))
        self.assertEqual(sorted(r.status_code for r in responses),[200,409])
        self.assertEqual(self.get('/access')['savedSessions'],5)
        access=SandboxAccess(DSN,'UTC')
        with self.assertRaisesRegex(ContractError,'SANDBOX_EVENTS_DISABLED'):access.event({},'0'*64)
        http=client(self.app);http.base_url='http://testserver'
        self.assertEqual(http.get(self.root+'/access',headers=self.headers).status_code,426)

    def test_separate_operator_role_can_sign_grant_but_api_role_cannot(self):
        import psycopg
        from psycopg import sql
        from contextlib import contextmanager
        from cloud.sandbox_access import grant_sandbox_access_runtime,grant_sandbox_event_runtime
        api_role='sandbox_api_'+uuid.uuid4().hex;event_role='sandbox_event_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:
            for role in (api_role,event_role):db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        grant_sandbox_access_runtime(DSN,api_role);grant_sandbox_event_runtime(DSN,event_role)
        raw=dict(schemaVersion=1,artifact='BTL-SANDBOX-ACCESS-EVENT-1',id='event:role:'+uuid.uuid4().hex,accountId=self.actor,sequence=1,tier='PRO',expiresAt=str(int(time.time())+3600),mode='SANDBOX')
        sig=hmac.new(self.secret.encode(),canonical_bytes(raw),hashlib.sha256).hexdigest()
        @contextmanager
        def restricted(role):
            with connect(DSN) as db:
                db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)));yield db
        @contextmanager
        def operator(dsn):
            with restricted(event_role) as db:yield db
        with patch('cloud.sandbox_access.connect',operator):
            self.assertEqual(SandboxAccess(DSN,'UTC',event_secret=self.secret).event(raw,sig),raw)
        with self.assertRaises(psycopg.DatabaseError):
            with restricted(api_role) as db:db.execute('INSERT INTO btl.sandbox_access_events SELECT event_id,actor_id,sequence,payload,content_hash FROM btl.sandbox_access_events LIMIT 0')
        with self.assertRaises(psycopg.DatabaseError):
            with restricted(event_role) as db:db.execute('SELECT * FROM btl.tick_sessions LIMIT 0')
        self.assertEqual(self.get('/access')['tier'],'PRO')


class SandboxConfigurationTests(unittest.TestCase):
    def test_disabled_default_explicit_timezone_and_separate_key(self):
        secret='q'*64
        with self.assertRaises(ValueError):
            create_app('authored:no-database',secret,RecordingDelivery(),sandbox_reset_timezone='UTC',sandbox_event_secret=secret)
        with self.assertRaises(ContractError):SandboxAccess('authored:no-database','Invalid/Timezone')
        app=create_app('authored:no-database',secret,RecordingDelivery())
        self.assertFalse(any('research-v2' in getattr(route,'path','') for route in app.routes))
