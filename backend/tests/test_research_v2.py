"""Native service acceptance on an isolated database only."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import os, unittest, uuid, tempfile
from pathlib import Path
from contextlib import contextmanager
import psycopg
from psycopg import sql
from unittest.mock import patch
from application.models import TrustedScope
from contracts.canonical import content_hash
from contracts.primitives import ContractError
from infrastructure.database import migrate, connect, backup, restore
from execution.research_v2 import ResearchApplicationV2
from execution.research_fixture_v2 import START_NS, STEP_NS, catalogue
from tests.test_research_sessions import method
from tests.test_kernel_v2 import opening
from tests.test_execution_v2_postgres import command

DSN=os.getenv('BTL_TEST_DATABASE_URL')

@unittest.skipUnless(DSN,'Requires isolated native PostgreSQL; skip is not acceptance')
class ResearchV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): migrate(DSN)
    def setUp(self):
        self.scope=TrustedScope('service2:'+uuid.uuid4().hex,'fixture:actor')
        self.app=ResearchApplicationV2(DSN,self.scope)
        self.method=method(); self.app.create_method(self.method)
        self.sid='session:eurusd'; self.rev=0
        self.raw=dict(id=self.sid,name='Demo',methodId=self.method['id'],initialBalance='10000',startPeriod='2020-01',symbol='EURUSD')
        self.app.create_session(self.raw)
    def call(self,kind,payload=None):
        result=self.app.apply(self.sid,command(self.sid,'command:'+str(self.rev),self.rev,kind,payload))
        self.rev=result['state']['revision'];return result
    def review(self,rid='order:one'):
        return self.app.review(self.sid,dict(id=rid,expectedRevision=self.rev,payload=opening(entry='999',sl='1.09902')))
    def test_exact_confirmed_risk_cash_and_cold_journal(self):
        self.call('ADVANCE',dict(targetNs=str(START_NS)))
        review=self.review();self.assertEqual(review['command']['payload']['entry'],'1.10002')
        self.assertEqual(review['estimate']['risk']['plannedRequestedLossUsdExact'],dict(numerator='1',denominator='1'))
        request=dict(reviewId=review['id'],reviewHash=content_hash(review))
        receipt=self.app.confirm(self.sid,request);self.rev=receipt['state']['revision']
        self.call('ADVANCE',dict(targetNs=str(START_NS+STEP_NS)))
        self.call('CLOSE',dict(orderId=review['id'],quantity=None))
        self.call('ADVANCE',dict(targetNs=str(START_NS+2*STEP_NS)))
        stats=self.app.statistics(self.sid)
        self.assertEqual(stats['account']['balance'],'10000.03')
        self.assertEqual(stats['completed'][0]['rMultiple'],dict(numerator='3',denominator='100'))
        note=dict(orderId=review['id'],expectedNoteRevision=0,text='Observed setup',tags=['qa'])
        saved=self.app.edit_note(self.sid,note);self.assertEqual(self.app.edit_note(self.sid,note),saved)
        cold=ResearchApplicationV2(DSN,self.scope)
        self.assertEqual(cold.statistics(self.sid),stats)
        self.assertEqual(cold.journal(self.sid)['notes'],[saved])
        with patch('execution.research_v2.binding',side_effect=RuntimeError('offline')):
            self.assertEqual(cold.confirm(self.sid,request),receipt)
            view=cold.inspect(self.sid)
            self.assertEqual(view['displayStatus'],'SOURCE_DISPLAY_UNAVAILABLE')
            self.assertEqual(view['state']['balance'],'10000.03')
        self.assertEqual(cold.inspect(self.sid)['state']['revision'],self.rev)
    def test_all_symbols_creation_identity_and_no_future_projection(self):
        self.assertEqual(len(catalogue()),16)
        for item in catalogue():
            raw={**self.raw,'id':'session:'+item['symbol'],'symbol':item['symbol']}
            meta=self.app.create_session(raw);self.assertEqual(self.app.create_session(raw),meta)
            view=self.app.inspect(raw['id'])
            self.assertEqual(view['state']['revision'],0)
            self.assertEqual(view['chart']['candles'],[])
            self.assertIsNone(view['quote'])
            self.assertNotIn('controller',view)
        bad={**self.raw,'initialBalance':'10000.001'}
        with self.assertRaises(ContractError):self.app.create_session(bad)
        bad={**self.raw,'symbol':'GBPUSD'}
        with self.assertRaisesRegex(ContractError,'IDEMPOTENCY_CONFLICT'):self.app.create_session(bad)
        other=ResearchApplicationV2(DSN,TrustedScope('other:'+uuid.uuid4().hex,'fixture:actor'))
        for operation in (lambda:other.inspect(self.sid),lambda:other.statistics(self.sid),lambda:other.journal(self.sid)):
            with self.assertRaisesRegex(ContractError,'RESOURCE_UNAVAILABLE'):operation()
    def test_review_concurrency_hash_staleness_and_raw_command_refusal(self):
        self.call('ADVANCE',dict(targetNs=str(START_NS)))
        with ThreadPoolExecutor(max_workers=3) as pool: reviews=list(pool.map(lambda _:self.review(),range(3)))
        self.assertTrue(all(r==reviews[0] for r in reviews))
        review=reviews[0];req=dict(reviewId=review['id'],reviewHash=content_hash(review))
        with self.assertRaisesRegex(ContractError,'REVIEW_HASH'):self.app.confirm(self.sid,{**req,'reviewHash':'0'*64})
        with self.assertRaisesRegex(ContractError,'PRODUCT_COMMAND'):
            self.app.apply(self.sid,review['command'])
        with ThreadPoolExecutor(max_workers=3) as pool: receipts=list(pool.map(lambda _:self.app.confirm(self.sid,req),range(3)))
        self.assertTrue(all(r==receipts[0] for r in receipts));self.rev=receipts[0]['state']['revision']
        stale=self.review('order:stale');self.call('ADVANCE',dict(targetNs=str(START_NS+STEP_NS)))
        with self.assertRaisesRegex(ContractError,'STALE_REVISION'):
            self.app.confirm(self.sid,dict(reviewId=stale['id'],reviewHash=content_hash(stale)))
        with connect(DSN) as db:
            count=db.execute('SELECT count(*) FROM btl.tick_v2_order_reviews WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,self.sid)).fetchone()[0]
        self.assertEqual(count,2)

    def test_restricted_runtime_and_database_evidence_guards(self):
        from execution.research_v2 import grant_research_v2_runtime
        role='service2_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:
            db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        grant_research_v2_runtime(DSN,role)
        @contextmanager
        def restricted(dsn):
            with connect(dsn) as db:
                db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
                yield db
        with patch('execution.research_v2.connect',restricted), patch('execution.postgres_v2.connect',restricted):
            self.call('ADVANCE',dict(targetNs=str(START_NS)))
            review=self.review();receipt=self.app.confirm(self.sid,dict(reviewId=review['id'],reviewHash=content_hash(review)))
            self.rev=receipt['state']['revision']
            saved=self.app.edit_note(self.sid,dict(orderId=review['id'],expectedNoteRevision=0,text='Runtime note',tags=[]))
            self.assertEqual(self.app.journal(self.sid)['notes'],[saved])
        for table in ('tick_v2_research_sessions','tick_v2_order_reviews'):
            for query in ('DELETE FROM btl.'+table,'UPDATE btl.'+table+' SET content_hash=content_hash'):
                with self.assertRaises(psycopg.DatabaseError):
                    with restricted(DSN) as db:db.execute(query)
        with self.assertRaises(psycopg.DatabaseError):
            with restricted(DSN) as db:
                db.execute('UPDATE btl.tick_v2_journal_notes SET note_revision=note_revision WHERE workspace_id=%s',(self.scope.workspace_id,))
        # Even a privileged insert may not retrospectively attach a review.
        with self.assertRaises(psycopg.DatabaseError):
            with connect(DSN) as db:
                db.execute('INSERT INTO btl.tick_v2_order_reviews SELECT workspace_id,session_id,%s,basis_revision,basis_checkpoint_hash,command_hash,payload,content_hash FROM btl.tick_v2_order_reviews WHERE workspace_id=%s',('retrospective',self.scope.workspace_id))
    def test_native_empty_target_restore_preserves_review_note_and_statistics(self):
        self.call('ADVANCE',dict(targetNs=str(START_NS)))
        review=self.review();request=dict(reviewId=review['id'],reviewHash=content_hash(review))
        receipt=self.app.confirm(self.sid,request);self.rev=receipt['state']['revision']
        self.call('ADVANCE',dict(targetNs=str(START_NS+STEP_NS)))
        self.call('CLOSE',dict(orderId=review['id'],quantity=None))
        self.call('ADVANCE',dict(targetNs=str(START_NS+2*STEP_NS)))
        self.app.edit_note(self.sid,dict(orderId=review['id'],expectedNoteRevision=0,text='Restored',tags=['qa']))
        before=self.app.inspect(self.sid);journal=self.app.journal(self.sid)
        self.assertEqual(before['analysis']['account']['balance'],'10000.03')
        info=psycopg.conninfo.conninfo_to_dict(DSN);name='service2_restore_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        target_dsn=psycopg.conninfo.make_conninfo(**{**info,'dbname':name})
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'service.dump';sha=backup(DSN,target,os.environ['BTL_PG_BIN'])
            restore(target_dsn,target,sha,os.environ['BTL_PG_BIN'])
        cold=ResearchApplicationV2(target_dsn,self.scope)
        self.assertEqual(cold.inspect(self.sid),before)
        self.assertEqual(cold.journal(self.sid),journal)
        self.assertEqual(cold.confirm(self.sid,request),receipt)

    def test_atomic_session_and_review_failure_and_protocol_checklist(self):
        raw={**self.raw,'id':'session:rollback'}
        native=self.app.store._insert
        def interrupted(*args):
            native(*args)
            raise RuntimeError('injected before metadata commit')
        with patch.object(self.app.store,'_insert',side_effect=interrupted):
            with self.assertRaises(RuntimeError):self.app.create_session(raw)
        with connect(DSN) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,raw['id'])).fetchone()[0],0)
        self.app.create_session(raw)
        self.call('ADVANCE',dict(targetNs=str(START_NS)))
        calls=[0]
        @contextmanager
        def fail_after_insert(dsn):
            calls[0]+=1
            with connect(dsn) as db:
                yield db
                if calls[0]==2:raise RuntimeError('injected before review commit')
        with patch('execution.research_v2.connect',fail_after_insert):
            with self.assertRaises(RuntimeError):self.review()
        self.assertEqual(calls[0],2)
        with connect(DSN) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_v2_order_reviews WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,self.sid)).fetchone()[0],0)
        self.assertEqual(self.app.inspect(self.sid)['state']['orders'],{})
        proto=method('PROTOCOL',True);self.app.create_method(proto)
        raw={**self.raw,'id':'session:protocol','methodId':proto['id']};self.app.create_session(raw)
        self.app.apply(raw['id'],command(raw['id'],'advance',0,'ADVANCE',dict(targetNs=str(START_NS))))
        payload=opening(entry='1.1',sl='1.099',kind='LIMIT',workflow='PLANNED')
        payload.update(quantity=None,tp=None,riskPercent=None)
        req=dict(id='planned',expectedRevision=1,payload=payload)
        with self.assertRaises(ContractError):self.app.review(raw['id'],req)
        payload['observations']=[dict(conditionId='condition',outcome='PASS')]
        review=self.app.review(raw['id'],req)
        self.assertEqual(review['command']['payload']['tp'],'1.102')
        self.assertEqual(review['command']['payload']['riskPercent'],'1')
        self.assertEqual(review['command']['payload']['quantity'],review['estimate']['risk']['recommendedQuantity'])
