"""Real local Method/Session/review integration, not prototype settlement."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import unittest
import uuid

from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from infrastructure.database import connect,migrate
from execution.research import ResearchApplication
from execution.research_fixture import WARMUP_NS,STEP_NS,research_provider
from execution.local_api import create_local_app,body
from fastapi.testclient import TestClient

DSN=os.getenv('BTL_TEST_DATABASE_URL')


class OperationalObservationTests(unittest.TestCase):
    def test_fixed_cardinality_bounded_window_disabled_and_nonblocking_contention(self):
        from execution.observability import OperationalMetrics,OPERATIONS
        metrics=OperationalMetrics()
        for i in range(300):
            metrics.observe('admitted')
            metrics.observe('completed','secret-user:'+str(i),duration=i/1000,status=409,response_bytes=100)
        result=metrics.snapshot()
        self.assertEqual(result['latencyWindow'],256)
        self.assertEqual(set(result['routeCounts']),set(OPERATIONS))
        self.assertEqual((result['active'],result['admitted'],result['statusCounts']['refused']),(0,300,300))
        self.assertNotIn('secret-user',json.dumps(result))
        self.assertIsNone(OperationalMetrics(enabled=False).snapshot()['latencySeconds']['p50'])
        metrics.lock.acquire()
        try:
            self.assertFalse(metrics.observe('admitted'))
            self.assertEqual(metrics.snapshot()['status'],'INCOMPLETE')
        finally:metrics.lock.release()
        self.assertEqual(metrics.snapshot()['status'],'DISABLED_OR_INCOMPLETE')


def method(kind='FREE_STYLE',on=False):
    return dict(schemaVersion=1,artifact='BTL-LOCAL-METHOD-1',id='method:'+uuid.uuid4().hex,name='QA Method',kind=kind,
                checklistOn=on,conditions=[] if kind=='FREE_STYLE' else [dict(id='condition',label='Setup valid')],
                riskPercent=None if kind=='FREE_STYLE' else '1',rr=None if kind=='FREE_STYLE' else '2')


def review_request(view,protocol=False):
    return dict(sessionId=view['metadata']['id'],requestId='order:'+uuid.uuid4().hex,expectedRevision=view['state']['revision'],
                planId='plan:qa' if protocol else None,planRevision=0 if protocol else None,
                draft=dict(side='LONG',orderType='LIMIT' if protocol else 'MARKET',workflow='PLANNED' if protocol else 'QUICK',
                           entry='2005' if protocol else '2000',quantity=None if protocol else '0.1',sl='2003' if protocol else None,
                           tp=None,riskPercent=None if protocol else '1',observations=[]))


class FixturePageTests(unittest.TestCase):
    def test_cached_pages_preserve_bytes_and_cannot_be_mutated(self):
        provider=research_provider()
        first=provider.read_page(provider.dataset_id,provider.dataset_version,None,64)
        before=canonical_bytes(first)
        first['events'][0]['bid']='9999'
        first['nextToken']['afterRawOrdinal']='9999'
        self.assertEqual(canonical_bytes(provider.read_page(provider.dataset_id,provider.dataset_version,None,64)),before)
        descriptor=provider.describe(provider.dataset_id,provider.dataset_version)
        descriptor['ordering']['ties']='UNTRUSTED'
        self.assertEqual(provider.describe(provider.dataset_id,provider.dataset_version)['ordering']['ties'],'TRUSTED_SEQUENCE')
        with self.assertRaises(ContractError):provider.read_page(provider.dataset_id,'0'*64,None,64)


class SessionSummaryProjectionTests(unittest.TestCase):
    def test_exact_committed_cash_count_and_no_market_capabilities(self):
        from unittest.mock import patch, MagicMock
        app=ResearchApplication.__new__(ResearchApplication);app.dsn='authored:no-database'
        state=dict(sessionId='session:summary',revision=7,throughNs='123',datasetId='fixture:summary',
                   datasetVersion='a'*64,profileHash='b'*64,profile={'accountCurrency':'USD'},
                   initialBalance='10000',balance='9999.12345678',
                   orders={'closed':{'status':'CLOSED'},'partial':{'status':'ACTIVE'},
                           'cancelled':{'status':'CANCELLED'},'pending':{'status':'PENDING'}},
                   unresolved=True,ended=False)
        app._session=MagicMock(return_value=({'id':state['sessionId']},{},state,{}))
        before=deepcopy(state)
        with patch('execution.research.connect') as connect_mock:
            result=app.summary(state['sessionId'])
        self.assertEqual((result['balance'],result['netCashChange'],result['completedTrades']),('9999.12345678','-0.87654322',1))
        self.assertEqual((result['revision'],result['throughNs'],result['unresolved']),(7,'123',True))
        self.assertEqual(state,before)
        self.assertFalse({'orders','controller','quote'} & result.keys())
        connect_mock.return_value.__enter__.return_value.execute.assert_called_once_with(
            'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')

    def test_missing_or_corrupt_scoped_snapshot_is_not_a_fabricated_summary(self):
        from unittest.mock import patch, MagicMock
        app=ResearchApplication.__new__(ResearchApplication);app.dsn='authored:no-database'
        for code in ('RESOURCE_UNAVAILABLE','CORRUPT_RECORD','REFUSED_DATASET_VERSION'):
            app._session=MagicMock(side_effect=ContractError(code,'session'))
            with patch('execution.research.connect'),self.assertRaises(ContractError) as error:
                app.summary('session:missing')
            self.assertEqual(error.exception.code,code)


@unittest.skipUnless(DSN,'Real isolated PostgreSQL required; skips are not PASS')
class ResearchSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.scope=TrustedScope('researchqa:'+uuid.uuid4().hex,'fixture:operator')
        self.app=ResearchApplication(DSN,self.scope)

    def test_summary_is_scoped_read_only_and_never_reconstructs_market(self):
        from unittest.mock import patch
        view, _ = self.create()
        session = view['metadata']['id']
        before = canonical_bytes(self.app.inspect(session))
        with patch.object(self.app, '_quote', side_effect=AssertionError('no market reads')), \
             patch.object(self.app, 'inspect', side_effect=AssertionError('no event replay')), \
             patch.object(self.app, 'workspace', side_effect=AssertionError('no chart reconstruction')):
            result = self.app.summary(session)
        self.assertEqual((result['balance'], result['netCashChange'], result['completedTrades']), ('10000','0',0))
        self.assertEqual(result['revision'], view['state']['revision'])
        self.assertEqual(result['throughNs'], view['state']['throughNs'])
        self.assertFalse(result['unresolved'])
        self.assertEqual(canonical_bytes(self.app.inspect(session)), before)
        foreign = ResearchApplication(DSN, TrustedScope('foreign:'+uuid.uuid4().hex,'fixture:foreign'))
        with self.assertRaises(ContractError) as error:
            foreign.summary(session)
        self.assertEqual(error.exception.code, 'RESOURCE_UNAVAILABLE')
        foreign.close()

    def test_summary_counts_closed_positions_not_partial_exits_and_matches_durable_analysis(self):
        view, _ = self.create()
        session = view['metadata']['id']
        request = review_request(view)
        reviewed = self.app.review(request)
        self.app.confirm(session, dict(reviewId=request['requestId'], reviewHash=reviewed['reviewHash']))
        def command(kind, payload):
            current = self.app.inspect(session)['state']
            return self.app.apply(session, dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',
                sessionId=session,commandId='summary:'+uuid.uuid4().hex,expectedRevision=current['revision'],
                kind=kind,payload=payload))
        def advance():
            current = self.app.inspect(session)['state']
            return command('ADVANCE',{'targetNs':str(int(current['throughNs'])+STEP_NS)})
        advance()
        state = self.app.inspect(session)['state']
        order_id = next(iter(state['orders']))
        self.assertEqual(state['orders'][order_id]['status'],'ACTIVE')
        command('CLOSE',dict(orderId=order_id,quantity='0.05'))
        advance()
        self.assertEqual(self.app.summary(session)['completedTrades'],0)
        command('CLOSE',dict(orderId=order_id,quantity=None))
        advance()
        summary = self.app.summary(session)
        workspace = self.app.workspace(session,{'timeframe':'1m'})
        self.assertEqual(summary['completedTrades'],1)
        self.assertEqual(summary['completedTrades'],workspace['analysis']['metrics']['tradeCount'])
        self.assertEqual(summary['balance'],workspace['state']['balance'])
        cold = ResearchApplication(DSN,self.scope)
        self.assertEqual(cold.summary(session),summary)
        cold.close()

    def create(self,kind='FREE_STYLE',on=False):
        m=method(kind,on);self.app.create_method(m)
        body=dict(id='session:'+uuid.uuid4().hex,name='QA Session',methodId=m['id'],initialBalance='10000',startPeriod='2020-01')
        return self.app.create_session(body),body

    def advance(self,view,steps=1):
        return self.app.apply(view['metadata']['id'],dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',
            sessionId=view['metadata']['id'],commandId='advance:'+uuid.uuid4().hex,expectedRevision=view['state']['revision'],
            kind='ADVANCE',payload={'targetNs':str(int(view['state']['throughNs'])+steps*STEP_NS)}))

    def test_method_inheritance_immutable_and_idempotent_creation(self):
        view,body=self.create('PROTOCOL',True)
        self.assertEqual(view['state']['policy']['kind'],'PROTOCOL')
        self.assertEqual(view['state']['policy']['definitionHash'],view['metadata']['methodHash'])
        self.assertEqual(view['metadata']['datasetVersion'],view['state']['datasetVersion'])
        self.assertEqual(self.app.create_session(body),view)
        changed=dict(body,initialBalance='20000')
        with self.assertRaisesRegex(ContractError,'REFUSED_IDEMPOTENCY_CONFLICT'):self.app.create_session(changed)
        changed=deepcopy(view['method']);changed['rr']='3'
        with self.assertRaisesRegex(ContractError,'REFUSED_IDEMPOTENCY_CONFLICT'):self.app.create_method(changed)
        self.assertEqual(self.app.inspect(body['id']),view)

    def test_protocol_checklist_on_off_and_server_sizing_bypass_refused(self):
        view,_=self.create('PROTOCOL',True);raw=review_request(view,True)
        with self.assertRaisesRegex(ContractError,'PROTOCOL_BLOCKED'):self.app.review(raw)
        raw['draft']['observations']=[dict(conditionId='condition',outcome='PASS')]
        reviewed=self.app.review(raw)
        payload=reviewed['review']['command']['payload']
        self.assertEqual(payload['tp'],'2009');self.assertEqual(payload['quantity'],'0.5')
        for patch in ({'quantity':'0.6'},{'riskPercent':'2'},{'tp':'2010'},{'workflow':'QUICK','orderType':'MARKET'}):
            wrong=deepcopy(raw);wrong['requestId']='bad:'+uuid.uuid4().hex;wrong['draft'].update(patch)
            with self.assertRaises(ContractError):self.app.review(wrong)
        other,_=self.create('PROTOCOL',False)
        off=self.app.review(review_request(other,True))
        self.assertEqual(off['review']['command']['payload']['observations'],[dict(conditionId='condition',outcome='NOT_ASSESSED')])

    def test_confirmation_is_durable_review_only_and_duplicate_safe(self):
        from unittest.mock import patch
        view,_=self.create();raw=review_request(view)
        reviewed=self.app.review(raw)
        self.assertEqual(self.app.review(raw),reviewed)
        self.assertEqual(self.app.inspect(view['metadata']['id'])['state']['orders'],{})
        confirm=dict(reviewId=raw['requestId'],reviewHash=reviewed['reviewHash'])
        with connect(DSN) as db:
            prior=json.loads(bytes(db.execute('SELECT payload FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',
                            (self.scope.workspace_id,raw['sessionId'])).fetchone()[0]))['controller']
        with patch('execution.controller.TickTimeline.resume',side_effect=AssertionError('Order confirmation must not replay ticks')):
            with ThreadPoolExecutor(max_workers=4) as pool:
                receipts=list(pool.map(lambda _:self.app.confirm(raw['sessionId'],confirm),range(8)))
        self.assertTrue(all(r==receipts[0] for r in receipts))
        self.assertTrue(receipts[0]['durable'])
        self.assertEqual(receipts[0]['state']['revision'],1)
        self.assertEqual(len(receipts[0]['state']['orders']),1)
        with connect(DSN) as db:
            after=json.loads(bytes(db.execute('SELECT payload FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',
                            (self.scope.workspace_id,raw['sessionId'])).fetchone()[0]))['controller']
        self.assertEqual(after,prior)
        with self.assertRaisesRegex(ContractError,'REFUSED_IDEMPOTENCY_CONFLICT'):
            self.app.confirm(raw['sessionId'],dict(confirm,reviewHash='0'*64))
        changed=deepcopy(raw);changed['draft']['quantity']='0.2'
        with self.assertRaisesRegex(ContractError,'REFUSED_IDEMPOTENCY_CONFLICT'):self.app.review(changed)
        with self.assertRaisesRegex(ContractError,'REFUSED_UNREVIEWED_COMMAND'):
            self.app.apply(raw['sessionId'],reviewed['review']['command'])

    def test_stale_review_and_actual_fill_reload_without_reset(self):
        view,body=self.create();old=self.app.review(review_request(view))
        self.advance(view)
        with self.assertRaisesRegex(ContractError,'REFUSED_STALE_REVISION'):
            self.app.confirm(body['id'],dict(reviewId=old['review']['command']['commandId'],reviewHash=old['reviewHash']))
        view=self.app.inspect(body['id']);new=self.app.review(review_request(view))
        self.app.confirm(body['id'],dict(reviewId=new['review']['command']['commandId'],reviewHash=new['reviewHash']))
        view=self.app.inspect(body['id']);self.advance(view)
        saved=self.app.inspect(body['id'])
        self.assertEqual(saved['state']['orders'][new['review']['command']['commandId']]['status'],'ACTIVE')
        fresh=ResearchApplication(DSN,self.scope)
        self.assertEqual(canonical_bytes(fresh.inspect(body['id'])),canonical_bytes(saved))
        self.assertEqual(fresh.create_session(body),saved)
        self.assertEqual(saved['quote']['timeNs'],saved['state']['throughNs'])
        for forbidden in ('controller','advanceTargets','endOfDataset','manifest','chunks','evidenceCatalog'):
            self.assertNotIn(forbidden,repr(saved))
        self.assertGreater(int(saved['state']['throughNs']),WARMUP_NS)

    def test_corrupt_and_older_records_preserved_fail_closed(self):
        view,body=self.create();saved=self.app.catalog()
        with connect(DSN) as db:
            # Unique QA namespace; operator corruption injection, never user data.
            db.execute('ALTER TABLE btl.tick_methods DISABLE TRIGGER immutable_tick_methods')
            try:
                db.execute('UPDATE btl.tick_methods SET payload=payload || %s::bytea WHERE workspace_id=%s',(b' ',self.scope.workspace_id))
            finally:
                db.execute('ALTER TABLE btl.tick_methods ENABLE TRIGGER immutable_tick_methods')
        for read in (lambda:self.app.catalog(),lambda:self.app.inspect(body['id'])):
            with self.assertRaisesRegex(ContractError,'CORRUPT_RECORD'):read()
        self.assertEqual(view['state']['balance'],'10000');self.assertEqual(len(saved['methods']),1)
        invalid=method();invalid['schemaVersion']=2
        with self.assertRaises(ContractError):self.app.create_method(invalid)
        # An unsupported persisted version stays on disk; refusal never resets it.
        older_scope=TrustedScope('olderqa:'+uuid.uuid4().hex,'fixture:operator')
        older_app=ResearchApplication(DSN,older_scope);record=method();older_app.create_method(record)
        record['schemaVersion']=2
        raw=json.dumps(record,sort_keys=True,separators=(',',':')).encode()
        with connect(DSN) as db:
            db.execute('ALTER TABLE btl.tick_methods DISABLE TRIGGER immutable_tick_methods')
            try:
                db.execute('UPDATE btl.tick_methods SET payload=%s,content_hash=%s WHERE workspace_id=%s',
                           (raw,hashlib.sha256(raw).hexdigest(),older_scope.workspace_id))
            finally:db.execute('ALTER TABLE btl.tick_methods ENABLE TRIGGER immutable_tick_methods')
        with self.assertRaises(ContractError):older_app.catalog()
        with connect(DSN) as db:
            self.assertEqual(bytes(db.execute('SELECT payload FROM btl.tick_methods WHERE workspace_id=%s',
                             (older_scope.workspace_id,)).fetchone()[0]),raw)

    def test_atomic_creation_failure_leaves_no_orphan_engine(self):
        from unittest.mock import patch
        m=method();self.app.create_method(m)
        body=dict(id='failed:'+uuid.uuid4().hex,name='Failure',methodId=m['id'],initialBalance='10000',startPeriod='2020-01')
        native=self.app.store._insert
        def fail_after_seed(*args):
            native(*args);raise RuntimeError('QA crash before metadata publication')
        with patch.object(self.app.store,'_insert',fail_after_seed),self.assertRaises(RuntimeError):self.app.create_session(body)
        with connect(DSN) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,body['id'])).fetchone()[0],0)
        self.assertEqual(self.app.create_session(body)['state']['revision'],0)


@unittest.skipUnless(DSN,'Real isolated PostgreSQL required; skips are not PASS')
class LocalAlphaBoundaryTests(unittest.TestCase):
    def setUp(self):
        migrate(DSN)
        self.client=TestClient(create_local_app(DSN),base_url='http://127.0.0.1:5188',client=('127.0.0.1',60000),
                               headers={'Origin':'http://127.0.0.1:5196','X-BTL-Local':'1'})

    def tearDown(self):
        self.client.close()

    def test_summary_transport_is_read_only_and_local_boundary_is_preserved(self):
        app=ResearchApplication(DSN);m=method();app.create_method(m)
        session='session:'+uuid.uuid4().hex
        app.create_session(dict(id=session,name='Summary transport QA',methodId=m['id'],initialBalance='10000',startPeriod='2020-01'))
        before=canonical_bytes(app.inspect(session))
        path='/api/v1/tick-alpha/sessions/'+session+'/summary'
        response=self.client.get(path)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json(),app.summary(session))
        self.assertEqual(response.headers['cache-control'],'no-store')
        measured=self.client.get('/api/v1/tick-alpha/measurement/operational').json()
        self.assertEqual(measured['routeCounts']['summary'],1)
        self.assertEqual(self.client.get(path,headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(canonical_bytes(app.inspect(session)),before)
        app.close()

    def test_telemetry_sink_failure_cannot_block_or_duplicate_financial_commit(self):
        from unittest.mock import patch
        app=ResearchApplication(DSN);m=method();app.create_method(m)
        session='session:'+uuid.uuid4().hex
        view=app.create_session(dict(id=session,name='Telemetry failure QA',methodId=m['id'],initialBalance='10000',startPeriod='2020-01'))
        request=review_request(view);reviewed=app.review(request)
        app.confirm(session,dict(reviewId=request['requestId'],reviewHash=reviewed['reviewHash']))
        before=app.inspect(session)
        raw=dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',sessionId=session,
                 commandId='command:'+uuid.uuid4().hex,expectedRevision=before['state']['revision'],
                 kind='ADVANCE',payload={'targetNs':str(int(before['state']['throughNs'])+STEP_NS)})
        path='/api/v1/tick-alpha/sessions/'+session+'/commands'
        with patch('execution.observability.OperationalMetrics.observe',side_effect=RuntimeError('Authored sink unavailable')):
            reply=self.client.post(path,json=raw)
            self.assertEqual(reply.status_code,200,reply.text)
            retry=self.client.post(path,json=raw)
            self.assertEqual(retry.content,reply.content)
        saved=app.inspect(session)
        self.assertEqual(saved['state']['revision'],raw['expectedRevision']+1)
        self.assertTrue(any(event['kind']=='ENTRY_FILL' for event in saved['events']))
        with patch('execution.observability.OperationalMetrics.snapshot',side_effect=RuntimeError('Authored sink unavailable')):
            self.assertEqual(self.client.get('/api/v1/tick-alpha/measurement/operational').status_code,503)
        self.assertEqual(app.inspect(session),saved)

    def test_operational_disabled_does_not_change_canonical_workspace(self):
        app=ResearchApplication(DSN);m=method();app.create_method(m)
        session='session:'+uuid.uuid4().hex
        app.create_session(dict(id=session,name='Operational no-op QA',methodId=m['id'],initialBalance='10000',startPeriod='2020-01'))
        before=canonical_bytes(app.inspect(session))
        disabled=TestClient(create_local_app(DSN,observability=False),base_url='http://127.0.0.1:5188',client=('127.0.0.1',60000),headers={'Origin':'http://127.0.0.1:5196','X-BTL-Local':'1'})
        try:
            self.assertEqual(disabled.post('/api/v1/tick-alpha/sessions/'+session+'/view',json={'timeframe':'1m'}).status_code,200)
            report=disabled.get('/api/v1/tick-alpha/measurement/operational')
            self.assertEqual(report.status_code,200)
            self.assertEqual(report.json()['status'],'DISABLED_OR_INCOMPLETE')
            self.assertNotIn(session,report.text)
            self.assertNotIn(DSN,report.text)
        finally:disabled.close();app.close()
        self.assertEqual(canonical_bytes(ResearchApplication(DSN).inspect(session)),before)

    def test_bootstrap_transport_has_strict_seed_and_no_caller_evidence(self):
        app=ResearchApplication(DSN);m=method();app.create_method(m)
        session='session:'+uuid.uuid4().hex
        app.create_session(dict(id=session,name='Bootstrap transport QA',methodId=m['id'],initialBalance='10000',startPeriod='2020-01'))
        path='/api/v1/tick-alpha/sessions/'+session+'/bootstrap'
        before=canonical_bytes(app.inspect(session))
        response=self.client.post(path,json={'seed':42})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(response.json()['status'],'INSUFFICIENT_SAMPLE')
        for raw in ({'seed':0},{'seed':True},{'seed':42,'completed':[]},{'seed':42,'provider':'arbitrary'}):
            self.assertEqual(self.client.post(path,json=raw).status_code,409)
        self.assertEqual(self.client.post(path,json={'seed':42},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(canonical_bytes(app.inspect(session)),before)
        app.close()

    def test_host_peer_origin_custom_header_preflight_and_no_secret_errors(self):
        self.assertEqual(self.client.get('/api/v1/tick-alpha/catalog').status_code,200)
        for headers in ({'Origin':'https://evil.example'},{'Host':'evil.example'},{'X-BTL-Local':'0'}):
            self.assertEqual(self.client.get('/api/v1/tick-alpha/catalog',headers=headers).status_code,403)
        option=self.client.options('/api/v1/tick-alpha/catalog',headers={'Access-Control-Request-Method':'POST'})
        self.assertEqual(option.status_code,204)
        self.assertEqual(option.headers['access-control-allow-origin'],'http://127.0.0.1:5196')
        for content in ('{"id":"a","id":"b"}','{"x":NaN}','[]','x'*32769):
            reply=self.client.post('/api/v1/tick-alpha/methods',content=content,headers={'Content-Type':'application/json'})
            self.assertIn(reply.status_code,(409,413))
            self.assertNotIn(DSN,reply.text)
        reply=self.client.get('/api/v1/tick-alpha/sessions/unknown')
        self.assertEqual(reply.status_code,409);self.assertEqual(reply.headers['cache-control'],'no-store')
        remote=TestClient(create_local_app(DSN),base_url='http://127.0.0.1:5188',client=('192.0.2.1',60000))
        try:
            self.assertEqual(remote.get('/api/v1/tick-alpha/catalog',headers={'Origin':'http://127.0.0.1:5196','X-BTL-Local':'1'}).status_code,403)
        finally:remote.close()
        import anyio
        class SlowBody:
            async def stream(self):
                await anyio.sleep(6)
                yield b'{}'
        with self.assertRaises(TimeoutError):anyio.run(body,SlowBody())

    def test_overload_refuses_before_entering_worker_and_slots_recover(self):
        from threading import Event,Lock
        from unittest.mock import patch
        ready,release=Event(),Event();lock=Lock();started=0
        def held(_):
            nonlocal started
            with lock:
                started+=1
                if started==2:ready.set()
            if not release.wait(10):raise AssertionError('QA worker was not released')
            return {'methods':[]}
        with patch.object(ResearchApplication,'catalog',held),ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(self.client.get,'/api/v1/tick-alpha/catalog')
            second=pool.submit(self.client.get,'/api/v1/tick-alpha/catalog')
            try:
                self.assertTrue(ready.wait(5))
                refused=self.client.get('/api/v1/tick-alpha/catalog')
                self.assertEqual(refused.status_code,429);self.assertEqual(refused.json()['detail'],'LOCAL_BUSY')
                self.assertEqual(started,2)
            finally:release.set()
            self.assertEqual(first.result().status_code,200);self.assertEqual(second.result().status_code,200)
        self.assertEqual(self.client.get('/api/v1/tick-alpha/catalog').status_code,200)
