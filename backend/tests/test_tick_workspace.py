"""Actual cache/PG rollback and causal workspace projection acceptance."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import os
from threading import Barrier, Event, local
import unittest
import uuid
from unittest.mock import patch

from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from execution.research import ResearchApplication
from execution.research_fixture import WARMUP_NS, STEP_NS
from execution.research_fixture import research_provider, START_NS
from execution.workspace import display_candles, FixtureTimelineCache
from ticks.timeline import TickTimeline
from infrastructure.database import migrate
from tests.test_research_sessions import method, review_request
from ticks.provider import SyntheticTickProvider

DSN=os.getenv('BTL_TEST_DATABASE_URL')


class DisplayTests(unittest.TestCase):
    def test_exact_mid_utc_boundaries_gaps_incomplete_and_no_future(self):
        def group(second,bid,ask):
            return dict(timeNs=str(second*1000000000),events=[dict(timeNs=str(second*1000000000),bid=bid,ask=ask)])
        groups=[group(59,'100.01','100.02'),group(60,'101.01','101.02'),group(181,'99.01','99.02')]
        chart=display_candles(groups,str(181000000000),'1m',0)
        self.assertEqual([b['time'] for b in chart['candles']],[0,60,180])
        self.assertEqual(chart['candles'][0]['open'],'100.015')
        self.assertEqual([b['incomplete'] for b in chart['candles']],[False,False,True])
        self.assertFalse(chart['volumeAvailable'])
        self.assertTrue(all('volume' not in b for b in chart['candles']))
        with self.assertRaises(ContractError):display_candles(groups,'60000000000','1m',0)
        with self.assertRaises(ContractError):display_candles(list(reversed(groups)),'181000000000','1m',0)
        with self.assertRaises(ContractError):display_candles(groups,'181000000000','M',0)
        partial=display_candles(groups,'181000000000','1m',9)
        self.assertTrue(partial['candles'][0]['partialWindow'])
        with self.assertRaises(ContractError):FixtureTimelineCache(SyntheticTickProvider([]))

    def test_immutable_fixture_timeline_cache_is_shared_across_short_lived_adapters(self):
        provider=research_provider()
        scope=TrustedScope('workspace:shared-fixture-cache:'+uuid.uuid4().hex,'fixture:operator')
        session='session:shared-fixture-cache:'+uuid.uuid4().hex
        timeline=TickTimeline(provider,provider.dataset_id,provider.dataset_version,str(START_NS))
        timeline.seek(str(WARMUP_NS))
        checkpoint=timeline.checkpoint()
        first=FixtureTimelineCache(provider)
        first.seed(scope,session,timeline)
        expected=first.window(scope,session,checkpoint,last_only=True)
        second=FixtureTimelineCache(provider)
        with patch('execution.workspace.TickTimeline.resume',side_effect=AssertionError('unexpected cold resume')):
            actual=second.window(scope,session,checkpoint,last_only=True)
        self.assertEqual(actual,expected)

    def test_cold_restores_for_independent_sessions_do_not_hold_global_cache_lock(self):
        base=research_provider()
        rendezvous=Barrier(2, timeout=5)
        per_thread=local()
        class ConcurrentProvider:
            dataset_id=base.dataset_id
            dataset_version=base.dataset_version
            def describe(self, dataset_id, dataset_version):
                return base.describe(dataset_id, dataset_version)
            def read_page(self, dataset_id, dataset_version, after_token=None, max_events=1024):
                if not getattr(per_thread,'joined',False):
                    per_thread.joined=True
                    rendezvous.wait()
                return base.read_page(dataset_id,dataset_version,after_token,max_events)
        provider=ConcurrentProvider()
        cache=FixtureTimelineCache(provider,allow_injected_synthetic=True)
        timeline=TickTimeline(base,base.dataset_id,base.dataset_version,str(START_NS))
        timeline.seek(str(WARMUP_NS))
        checkpoint=timeline.checkpoint()
        scopes=[TrustedScope('workspace:restore-parallel:'+uuid.uuid4().hex,'fixture:operator') for _ in range(2)]
        sessions=['session:restore-parallel:'+uuid.uuid4().hex for _ in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(cache.window,scopes[i],sessions[i],checkpoint,last_only=True) for i in range(2)]
            rows=[future.result(timeout=10) for future in futures]
        self.assertEqual(rows[0],rows[1])


@unittest.skipUnless(DSN,'Actual isolated PostgreSQL required; skips are not PASS')
class TickWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(DSN)

    def setUp(self):
        self.scope=TrustedScope('workspaceqa:'+uuid.uuid4().hex,'fixture:operator')
        self.app=ResearchApplication(DSN,self.scope)
        m=method();self.app.create_method(m)
        self.session='session:'+uuid.uuid4().hex
        self.app.create_session(dict(id=self.session,name='Workspace QA',methodId=m['id'],initialBalance='10000',startPeriod='2020-01'))

    def command(self,view,steps=4):
        return dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',sessionId=self.session,
            commandId='advance:'+uuid.uuid4().hex,expectedRevision=view['state']['revision'],kind='ADVANCE',
            payload={'targetNs':str(int(view['state']['throughNs'])+steps*STEP_NS)})

    def view(self,tf='1m'):return self.app.workspace(self.session,{'timeframe':tf})

    def test_timeframe_is_display_only_bounded_window_and_cold_recovery(self):
        first=self.view();five=self.view('5m')
        self.assertEqual(first['state'],five['state'])
        self.assertEqual(len(first['chart']['candles']),31)
        self.assertEqual(len(five['chart']['candles']),7)
        self.assertEqual(first['chart']['candles'][0],dict(time=1577836800,open='2000.05',high='2000.2',low='2000.05',close='2000.2',event_count=4,incomplete=False,partialWindow=False))
        for _ in range(60):
            self.app.apply(self.session,self.command(first,16));first=self.view()
        self.assertEqual(first['state']['nextGroupIndex'],'1081')
        self.assertEqual(first['chart']['windowStartGroup'],'57')
        self.assertTrue(first['chart']['candles'][0]['partialWindow'])
        self.assertLessEqual(len(first['chart']['candles']),512)
        cold=ResearchApplication(DSN,self.scope)
        self.assertEqual(canonical_bytes(cold.workspace(self.session,{'timeframe':'1m'})),canonical_bytes(first))
        for forbidden in ('advanceTargets','endOfDataset','manifest','evidenceCatalog'):
            self.assertNotIn(forbidden,repr(first))
        with self.assertRaises(ContractError):self.view('M')

    def test_speculative_cache_after_rollback_cannot_reveal_future(self):
        from execution.postgres import pack as native_pack
        before=self.view();command=self.command(before)
        def fail(value):
            if value.get('artifact')=='BTL-TICK-EXECUTION-COMPACT-DELTA-1':raise RuntimeError('QA before SQL publication')
            return native_pack(value)
        with patch('execution.postgres.pack',side_effect=fail),self.assertRaises(RuntimeError):
            self.app.apply(self.session,command)
        self.assertEqual(canonical_bytes(self.view()),canonical_bytes(before))
        receipt=self.app.apply(self.session,command)
        after=self.view()
        self.assertEqual(after['state'],receipt['state'])
        self.assertEqual(after['quote']['timeNs'],str(WARMUP_NS+4*STEP_NS))
        self.assertEqual(self.app.apply(self.session,command),receipt)

    def test_concurrent_snapshot_does_not_read_speculative_successor(self):
        before=self.view();started,release=Event(),Event()
        cache=self.app._ResearchApplication__timeline_cache
        native=cache.reveal
        def held(*args,**kwargs):
            result=native(*args,**kwargs);started.set()
            if not release.wait(60):raise AssertionError('QA release missing')
            return result
        with patch.object(cache,'reveal',side_effect=held),ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.app.apply,self.session,self.command(before))
            try:
                self.assertTrue(started.wait(10))
                old=self.view()
                self.assertEqual(canonical_bytes(old),canonical_bytes(before))
            finally:release.set()
            receipt=future.result()
        after=self.view()
        self.assertEqual(after['state'],receipt['state'])
        self.assertEqual(after['state']['nextGroupIndex'],'125')
        self.assertEqual(after['quote']['timeNs'],str(WARMUP_NS+4*STEP_NS))
        # Actual reviewed market order still flows through this same cached controller.
        review=self.app.review(review_request(after))
        self.app.confirm(self.session,dict(reviewId=review['review']['command']['commandId'],reviewHash=review['reviewHash']))
        pending=self.view();self.app.apply(self.session,self.command(pending,1))
        filled=self.view()
        order=filled['state']['orders'][review['review']['command']['commandId']]
        self.assertEqual(order['status'],'ACTIVE')
        self.assertEqual(order['entryPrice'],filled['quote']['ask'])
