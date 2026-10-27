"""Conditional committed analysis; authored fixtures are not market benchmarks."""
from copy import deepcopy
from fractions import Fraction
import os,unittest
from contracts.canonical import canonical_bytes,content_hash
from execution.observed_analysis import LedgerFold,ObservedStatistics
from tests import test_observed_kernel as kernel_fixtures
S=kernel_fixtures.S
from tests import test_observed_postgres as pg_fixtures
command=pg_fixtures.command;DSN=pg_fixtures.DSN
from infrastructure.database import connect
from execution.postgres import pack


class ObservedAnalysisTests(unittest.TestCase):
    def setUp(self):self.fx=kernel_fixtures.ObservedKernelTests();self.fx.setUp()
    def tearDown(self):self.fx.tearDown()
    def start(self,quotes):
        self.fx.setup_stream(quotes);self.fold=LedgerFold(self.fx.state)
    def advance(self,t):
        events,_=self.fx.advance(t)
        for e in events:self.fold.consume(e)
    def call(self,kind,payload,cid=None):
        events=self.fx.command(kind,payload,command=cid)
        for e in events:self.fold.consume(e)
    def opening(self,cid="order:z",**change):
        p=dict(side='LONG',orderType='MARKET',workflow='QUICK',entry=self.fx.state['quoteBasis']['ask'],quantity='0.01',sl=None,tp=None,riskPercent='1',observations=[]);p.update(change);self.call('OPEN',p,cid)
    def project(self):return self.fold.project(self.fx.state)

    def test_exact_partial_closed_trade_never_infers_retrospective_risk(self):
        self.start([(0,'2300','2300.1'),(S,'2300.9','2301'),(2*S,'2302','2302.1'),(3*S,'2303','2303.1')]);self.advance(0);self.opening(quantity='0.02',sl='2299');self.advance(S)
        self.call('CLOSE',dict(orderId='order:z',quantity='0.01'));self.advance(2*S)
        partial=self.project();self.assertEqual(partial['metrics']['closed'],0);self.assertEqual(partial['account']['balance'],'10001');self.assertEqual(partial['metrics']['realizedNetCompleted'],'0')
        self.assertEqual([item['kind'] for item in partial['annotations']],['ENTRY_FILL','EXIT_FILL'])
        self.call('CLOSE',dict(orderId='order:z',quantity=None));self.advance(3*S);r=self.project()
        self.assertEqual((r['metrics']['closed'],r['metrics']['wins'],r['account']['balance']),(1,1,'10003'))
        self.assertEqual(r['completed'][0]['grossExact'],'3');self.assertEqual(r['completed'][0]['exitFills'],2);self.assertIsNone(r['metrics']['totalR']);self.assertEqual(r['completed'][0]['rReason'],'PREENTRY_REVIEW_RISK_NOT_JOINED');self.assertFalse(r['markToMarketAvailable'])
        self.assertEqual([item['kind'] for item in r['annotations']],['ENTRY_FILL','EXIT_FILL','EXIT_FILL'])

    def test_short_loss_drawdown_no_stop_r_is_explicitly_unavailable(self):
        self.start([(0,'2300','2300.1'),(S,'2300','2300.1'),(2*S,'2301','2301.1')]);self.advance(0);self.opening(side='SHORT',entry='2300');self.advance(S);self.call('CLOSE',dict(orderId='order:z',quantity=None));self.advance(2*S);r=self.project()
        self.assertEqual((r['metrics']['losses'],r['metrics']['maxDrawdown']),(1,'1.1'));self.assertEqual(r['metrics']['averageLoss'],dict(numerator='-11',denominator='10'));self.assertEqual(r['metrics']['maxDrawdownRate'],dict(numerator='11',denominator='100000'));self.assertIsNone(r['metrics']['totalR']);self.assertEqual(r['completed'][0]['rReason'],'PREENTRY_REVIEW_RISK_NOT_JOINED')

    def test_unresolved_and_expired_are_not_completed_fills(self):
        self.start([(0,'2300','2300.1'),(S,'2300.9','2301'),(S,'2301.9','2302')]);self.advance(0);self.opening();self.advance(S);r=self.project();self.assertEqual((r['metrics']['unresolved'],r['metrics']['closed'],r['account']['balance']),(1,0,'10000'))
        self.call('END',{});self.assertEqual(self.project()['metrics']['closed'],0)

    def test_completion_order_is_event_order_and_shared_metrics_are_reused(self):
        self.start([(0,'2300','2300.1'),(S,'2300.9','2301'),(2*S,'2302','2302.1'),(3*S,'2303','2303.1')]);self.advance(0);self.opening(cid='order:z');self.opening(cid='order:a');self.advance(S)
        self.call('CLOSE',dict(orderId='order:z',quantity=None));self.advance(2*S);self.call('CLOSE',dict(orderId='order:a',quantity=None));self.advance(3*S);r=self.project()
        self.assertEqual([row['id'] for row in r['completed']],['order:z','order:a']);self.assertEqual((r['metrics']['tradeCount'],r['metrics']['maxWinStreak']),(2,2));self.assertEqual(r['metrics']['averageWin'],dict(numerator='3',denominator='2'))

    def test_tampered_chain_cash_tip_and_financial_flag_refuse(self):
        self.start([(0,'2300','2300.1'),(S,'2300.9','2301')]);events,_=self.fx.advance(0);bad=deepcopy(events[0]);bad['previousHash']='0'*64
        with self.assertRaises(ValueError):self.fold.consume(bad)
        for e in events:self.fold.consume(e)
        bad=deepcopy(self.fx.state);bad['balance']='10001'
        with self.assertRaises(ValueError):self.fold.project(bad)
        bad=deepcopy(self.fx.state);bad['financial']=True
        with self.assertRaises(ValueError):self.fold.project(bad)


@unittest.skipUnless(DSN,'Requires exclusive native PostgreSQL; skipped is not acceptance')
class ObservedStatisticsPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):pg_fixtures.ObservedPostgresTests.setUpClass()
    def setUp(self):self.fx=pg_fixtures.ObservedPostgresTests();self.fx.setUp();self.stats=ObservedStatistics(self.fx.store)
    def tearDown(self):self.fx.tearDown()

    def test_committed_cold_source_outage_statistics_are_identical(self):
        f=self.fx;f.call('ADVANCE',dict(targetNs='0'));f.call('OPEN',f.opening(),cid='order:one');f.call('ADVANCE',dict(targetNs=str(S)));f.call('CLOSE',dict(orderId='order:one',quantity=None));f.call('ADVANCE',dict(targetNs=str(2*S)))
        expected=self.stats.inspect(f.scope,f.sid);self.assertEqual(expected['account']['balance'],'10001');self.assertEqual(expected['metrics']['closed'],1)
        f.source.close();offline=f.root/'offline';f.folder.rename(offline)
        try:self.assertEqual(canonical_bytes(expected),canonical_bytes(ObservedStatistics(f.store).inspect(f.scope,f.sid)))
        finally:offline.rename(f.folder)
        from application.models import TrustedScope
        with self.assertRaisesRegex(ValueError,'RESOURCE_UNAVAILABLE'):self.stats.inspect(TrustedScope('another','actor'),f.sid)

    def test_bounded_incremental_more_than4096_events_and_corrupt_tail_refusal(self):
        # Authored nonfinancial SQL journal scalability fixture, not 5000 engine
        # commands or a market replay benchmark. No new source event is forged.
        f=self.fx;before,_=f.store.prepare(f.scope,command(f.sid,'peek',0,'END'));state=deepcopy(before['state']);previous=state['eventHash'];rows=[]
        for i in range(5000):
            e=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-EVENT-1',engineVersion=state['engineVersion'],model=state['model'],sessionId=f.sid,datasetId=state['datasetId'],datasetVersion=state['datasetVersion'],profileHash=state['profileHash'],methodHash=state['policy']['definitionHash'],sequence=i,previousHash=previous,kind='REPLAY_ADVANCED',classification='OBSERVED_FEED_EVENT',orderId=None,detail={})
            e['eventId']=content_hash(e);previous=e['eventId'];raw,sha=pack(e);rows.append((f.scope.workspace_id,f.sid,'authored:journal',e['eventId'],i,raw,sha))
        state.update(revision=1,nextEventIndex=5000,eventHash=previous);snapshot=dict(before,state=state);raw,sha=pack(snapshot)
        with connect(DSN) as db:
            fixture_raw,fixture_sha=pack(dict(schemaVersion=1,artifact='AUTHORED-NONFINANCIAL-JOURNAL-FIXTURE-1'))
            db.execute('INSERT INTO btl.tick_commands VALUES (%s,%s,%s,1,%s,%s,%s)',(f.scope.workspace_id,f.sid,'authored:journal',fixture_sha,fixture_raw,fixture_sha))
            with db.cursor() as cursor:cursor.executemany('INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)',rows)
            db.execute('INSERT INTO btl.tick_checkpoints VALUES (%s,%s,1,%s,%s)',(f.scope.workspace_id,f.sid,raw,sha));db.execute('UPDATE btl.tick_sessions SET revision=1,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s',(raw,sha,f.scope.workspace_id,f.sid))
        for count in range(1,5):
            r=self.stats.inspect(f.scope,f.sid);self.assertEqual((r['status'],r['processedEvents']),('BUILDING',count*1024));self.assertIsNone(r['metrics'])
        r=self.stats.inspect(f.scope,f.sid);self.assertEqual((r['status'],r['metrics']['closed']),('COMPLETE',0));self.assertEqual(len(self.stats._folds),1)
        # Corruption is represented by a missing immutable row in an independently
        # constructed fixture, using its privileged QA setup connection only.
        with connect(DSN) as db:
            db.execute('ALTER TABLE btl.tick_events DISABLE TRIGGER USER');db.execute('DELETE FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence=4999',(f.scope.workspace_id,f.sid));db.execute('ALTER TABLE btl.tick_events ENABLE TRIGGER USER')
        cold=ObservedStatistics(f.store)
        for _ in range(4):self.assertEqual(cold.inspect(f.scope,f.sid)['status'],'BUILDING')
        with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):cold.inspect(f.scope,f.sid)

    def test_lru_eviction_and_bounded_curve_do_not_cap_lifetime_history(self):
        f=self.fx
        for i in range(65):
            sid='session:cache:'+str(i)
            f.c.create(f.scope,sid,f.fx.profile,f.fx.policy,period='1970-01')
            self.assertEqual(self.stats.inspect(f.scope,sid)['status'],'COMPLETE')
        self.assertEqual(len(self.stats._folds),64)
        self.assertEqual(self.stats.inspect(f.scope,'session:cache:0')['account']['balance'],'10000')
        self.assertEqual(len(self.stats._folds),64)
