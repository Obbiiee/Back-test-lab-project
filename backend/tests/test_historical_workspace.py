"""Historical composition goldens: actual disk port, causal view, no false fills."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import tempfile
import unittest
import uuid

from application.models import TrustedScope
from contracts.models import MethodPolicy
from execution.historical import HistoricalSource, IndexedTimelineCache, published_version
from execution.contracts import seed_state
from execution.engine import submit, advance
from ticks.exness_v2 import ExnessIngestion


def monthly_source(path):
    """Authored sparse quotes, never a provider-completeness declaration."""
    csv = path/'months.csv'
    csv.write_text('Exness,Symbol,Timestamp,Bid,Ask\n'
        'exness,XAUUSDm,2015-08-10 00:00:00.000Z,1100.001,1100.003\n'
        'exness,XAUUSDm,2015-11-15 00:00:00.000Z,2200.001,2200.003\n'
        'exness,XAUUSDm,2015-11-15 00:00:00.000Z,2200.002,2200.004\n'
        'exness,XAUUSDm,2015-12-21 00:00:00.000Z,3300.001,3300.003\n', encoding='utf-8')
    importer = ExnessIngestion(csv,path/'month-dataset')
    try: version=importer.run()['datasetVersion']
    finally: importer.builder.store.close()
    return HistoricalSource(path/'month-dataset',version,log_root=path/'month-logs')


class HistoricalWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.start = datetime(2015, 8, 10, tzinfo=timezone.utc)
        rows = ['Exness,Symbol,Timestamp,Bid,Ask']
        for i in range(96):
            stamp = (self.start+timedelta(seconds=i//2)).strftime('%Y-%m-%d %H:%M:%S.000Z')
            rows.append(f'exness,XAUUSDm,{stamp},{1100+i%4}.001,{1100+i%4}.003')
        self.csv = self.path/'source.csv';self.csv.write_text('\n'.join(rows)+'\n', encoding='utf-8')
        ingestion = ExnessIngestion(self.csv, self.path/'dataset')
        try:
            self.stats = ingestion.run()
        finally:
            ingestion.builder.store.close()
        self.source = HistoricalSource(self.path/'dataset', self.stats['datasetVersion'], log_root=self.path/'sessions')
        self.scope = TrustedScope('local:historical-test', 'local:operator')
        self.cache = IndexedTimelineCache(self.source)
        self.session = 'session:historical'
        timeline = self.cache.new_timeline(self.scope, self.session, self.source.start_ns)
        self.checkpoint = timeline.checkpoint()
        self.cache.seed(self.scope, self.session, timeline)

    def tearDown(self):
        self.cache.close()
        self.tmp.cleanup()

    def test_publication_and_profile_bind_actual_source_without_certifying_it(self):
        self.assertEqual(published_version(self.path/'dataset'), self.stats['datasetVersion'])
        self.assertEqual(self.source.profile['providerId'], 'exness')
        self.assertEqual(self.source.profile['feedInstrumentId'], 'exness:XAUUSDm')
        self.assertEqual(self.source.start_period, '2015-08')
        self.assertIn('UNKNOWN', self.source.label)

    def test_complete_ties_exact_quotes_and_no_future_capability(self):
        result, saved = self.cache.reveal(self.scope,self.session,self.checkpoint,str(self.source.start_ns+3*10**9))
        self.assertEqual(len(result['groups']),4)
        self.assertEqual([len(g['events']) for g in result['groups']],[2]*4)
        rows = self.cache.window(self.scope,self.session,saved)
        self.assertEqual(rows[0]['events'][0]['bid'],'1100.001')
        self.assertTrue(all(g['order']=='UNTRUSTED' for g in rows))
        self.assertTrue(all(int(g['timeNs'])<=self.source.start_ns+3*10**9 for g in rows))
        wire=json.dumps(rows)
        for hidden in ('endOfDataset','directories','positionLogHash','archive.sqlite','sourceCatalogHash'):
            self.assertNotIn(hidden,wire)

    def test_abandoned_speculation_recovers_original_committed_prefix(self):
        _, first = self.cache.reveal(self.scope,self.session,self.checkpoint,str(self.source.start_ns+2*10**9))
        original = self.cache.window(self.scope,self.session,first)
        self.cache.reveal(self.scope,self.session,first,str(self.source.start_ns+6*10**9))
        self.assertEqual(self.cache.window(self.scope,self.session,first),original)
        result, recovered=self.cache.reveal(self.scope,self.session,first,str(self.source.start_ns+3*10**9))
        self.assertEqual(len(result['groups']),1)
        self.assertEqual(recovered['cursor']['nextGroupIndex'],'4')

    def test_cross_worker_reuse_and_cold_recovery_do_not_change_prefix(self):
        with ThreadPoolExecutor(max_workers=1) as pool:
            _, saved=pool.submit(self.cache.reveal,self.scope,self.session,self.checkpoint,str(self.source.start_ns+4*10**9)).result()
            first=pool.submit(self.cache.window,self.scope,self.session,saved).result()
        self.cache.close();self.cache=IndexedTimelineCache(self.source)
        with ThreadPoolExecutor(max_workers=1) as pool:
            self.assertEqual(pool.submit(self.cache.window,self.scope,self.session,saved).result(),first)

    def test_unknown_coverage_keeps_money_unchanged_and_order_unresolved(self):
        policy=MethodPolicy('method:test','0'*64,'FREE_STYLE',False,())
        state=seed_state(self.session,self.source.dataset_id,self.source.version,str(self.source.start_ns),self.source.profile,policy)
        command=dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',sessionId=self.session,
                     commandId='order:real',expectedRevision=0,kind='OPEN',
                     payload=dict(side='LONG',orderType='MARKET',workflow='QUICK',entry='1100.001',quantity='0.1',
                                  sl=None,tp=None,riskPercent='1',observations=[]))
        state,_=submit(state,command)
        result,_=self.cache.reveal(self.scope,self.session,self.checkpoint,str(self.source.start_ns+10**9))
        final,events=advance(state,result['groups'],result['coverage'],result['diagnostics'],result['throughNs'])
        self.assertTrue(final['unresolved'])
        self.assertEqual(final['balance'],'10000')
        self.assertFalse(any(e['classification']=='SIMULATED_FILL' for e in events))

    def test_wrong_dataset_checkpoint_is_refused(self):
        bad=deepcopy(self.checkpoint);bad['cursor']['datasetVersion']='f'*64
        with self.assertRaises(ValueError):self.cache.window(self.scope,self.session,bad)

    def test_start_month_refuses_malformed_missing_and_foreign_year_without_fallback(self):
        self.assertEqual(self.source.start_for_period('2015-08'),self.source.start_ns)
        for period in (None,201508,'2015-8','2015-13','2015-08-01','２０１５-08','2016-08','2015-01','2015-09'):
            with self.subTest(period=period), self.assertRaisesRegex(ValueError,'REFUSED_HISTORICAL_PERIOD'):
                self.source.start_for_period(period)

    def test_late_month_reveals_only_its_actual_atomic_quote_group_and_recovers(self):
        source=monthly_source(self.path)
        start=source.start_for_period('2015-11')
        self.assertEqual(datetime.fromtimestamp(start//10**9,timezone.utc),datetime(2015,11,15,tzinfo=timezone.utc))
        cache=IndexedTimelineCache(source)
        try:
            timeline=cache.new_timeline(self.scope,'session:late',start)
            checkpoint=timeline.checkpoint();cache.seed(self.scope,'session:late',timeline)
            result,saved=cache.reveal(self.scope,'session:late',checkpoint,str(start+1800*10**9))
            self.assertEqual(len(result['groups']),1)
            self.assertEqual(result['groups'][0]['order'],'UNTRUSTED')
            self.assertEqual([e['bid'] for e in result['groups'][0]['events']],['2200.001','2200.002'])
            self.assertEqual(result['coverage'],[dict(startNs=str(start),endNs=result['throughNs'],status='UNKNOWN',evidenceHash=None)])
            original=cache.window(self.scope,'session:late',saved)
            cache.close();cache=IndexedTimelineCache(source)
            self.assertEqual(cache.window(self.scope,'session:late',saved),original)
            for absent in ('1100.001','3300.001','endOfDataset','indexContentHash'):
                self.assertNotIn(absent,json.dumps(original))
        finally:cache.close()

    def test_window_memo_is_exact_checkpoint_bound_and_returns_defensive_copies(self):
        _, first = self.cache.reveal(self.scope,self.session,self.checkpoint,str(self.source.start_ns+2*10**9))
        original = self.cache.window(self.scope,self.session,first)
        changed = self.cache.window(self.scope,self.session,first)
        changed[0]['events'][0]['bid'] = '9999'
        self.assertEqual(self.cache.window(self.scope,self.session,first),original)
        self.assertEqual(self.cache.window(self.scope,self.session,first,last_only=True),original[-1:])
        _, later = self.cache.reveal(self.scope,self.session,first,str(self.source.start_ns+5*10**9))
        self.assertGreater(len(self.cache.window(self.scope,self.session,later)),len(original))
        self.assertEqual(self.cache.window(self.scope,self.session,first),original)

    def test_progressive_selection_keeps_final_group_and_original_event_identity(self):
        from ticks.storage_v2 import DiskTickProvider
        importer=ExnessIngestion(self.csv,self.path/'subset',first_rows=3)
        try: result=importer.run()
        finally: importer.builder.store.close()
        self.assertEqual(result['acceptedRows'],4)
        self.assertEqual(result['sourceSelection'],{'kind':'FIRST_COMPLETE_TIMESTAMP_GROUPS','requestedRows':3})
        self.assertEqual(result['source']['sha256'],self.stats['source']['sha256'])
        full=DiskTickProvider(self.path/'dataset',self.source.version)
        selected=DiskTickProvider(self.path/'subset',result['datasetVersion'])
        try:
            def events(provider):
                pos=provider.locate_v2(provider.dataset_id,provider.dataset_version,str(self.source.start_ns))['position']
                return provider.read_page_v2(provider.dataset_id,provider.dataset_version,pos,4)['events']
            self.assertEqual([e['eventId'] for e in events(full)],[e['eventId'] for e in events(selected)])
            self.assertNotEqual(full.dataset_id,selected.dataset_id)
            self.assertEqual(events(selected)[-1]['rawOrdinal'],'3')
        finally: full.close();selected.close()


@unittest.skipUnless(os.getenv('BTL_TEST_DATABASE_URL'), 'Real PostgreSQL required; not a release PASS')
class HistoricalApplicationTests(unittest.TestCase):
    def setUp(self):
        from execution.research import ResearchApplication
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        start = datetime(2015,8,10,tzinfo=timezone.utc)
        rows = ['Exness,Symbol,Timestamp,Bid,Ask']
        for i in range(120):
            stamp=(start+timedelta(minutes=i//2)).strftime('%Y-%m-%d %H:%M:%S.000Z')
            rows.append(f'exness,XAUUSDm,{stamp},1100.001,1100.003')
        source=self.path/'authored.csv';source.write_text('\n'.join(rows)+'\n',encoding='utf-8')
        importer=ExnessIngestion(source,self.path/'dataset')
        try: version=importer.run()['datasetVersion']
        finally: importer.builder.store.close()
        self.source=HistoricalSource(self.path/'dataset',version,log_root=self.path/'logs')
        self.dsn=os.environ['BTL_TEST_DATABASE_URL']
        self.scope=TrustedScope('historicalqa:'+uuid.uuid4().hex,'local:operator')
        self.app=ResearchApplication(self.dsn,self.scope,historical_source=self.source)
        self.method=dict(schemaVersion=1,artifact='BTL-LOCAL-METHOD-1',id='method:'+uuid.uuid4().hex,
                         name='Historical QA',kind='FREE_STYLE',checklistOn=False,conditions=[],riskPercent=None,rr=None)
        self.app.create_method(self.method)
        self.body=dict(id='session:'+uuid.uuid4().hex,name='Historical QA',methodId=self.method['id'],
                       initialBalance='10000',startPeriod='2015-08')

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def test_durable_review_unknown_refusal_cold_reload_and_duplicate_create(self):
        from execution.research import ResearchApplication
        from tests.test_research_sessions import review_request
        original=self.app.create_session(self.body)
        view=self.app.workspace(self.body['id'],{'timeframe':'1m'})
        self.assertEqual(view['quote']['ask'],'1100.003')
        self.assertEqual(self.app.create_session(self.body),original)
        self.assertEqual(self.app.workspace(self.body['id'],{'timeframe':'1m'}),view)
        reviewed=self.app.review(review_request(view))
        self.app.confirm(self.body['id'],{'reviewId':reviewed['review']['command']['commandId'],'reviewHash':reviewed['reviewHash']})
        state=self.app.inspect(self.body['id'])['state']
        self.app.apply(self.body['id'],dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',
            sessionId=self.body['id'],commandId='advance:'+uuid.uuid4().hex,expectedRevision=state['revision'],
            kind='ADVANCE',payload={'targetNs':str(int(state['throughNs'])+60*10**9)}))
        final=self.app.workspace(self.body['id'],{'timeframe':'5m'})
        self.assertTrue(final['state']['unresolved'])
        self.assertEqual(final['analysis']['account']['balance'],'10000')
        self.assertFalse(any(e['classification']=='SIMULATED_FILL' for e in final['events']))
        self.app.close();self.app=ResearchApplication(self.dsn,self.scope,historical_source=self.source)
        self.assertEqual(self.app.workspace(self.body['id'],{'timeframe':'5m'}),final)
        for hidden in ('archive.sqlite','positionLogHash','endOfDataset','indexContentHash'):
            self.assertNotIn(hidden,json.dumps(final))

    def test_local_source_routing_is_explicit_and_never_falls_back(self):
        from fastapi.testclient import TestClient
        from execution.local_api import create_local_app
        headers={'Origin':'http://127.0.0.1:5196','X-BTL-Local':'1'}
        for configured in (True,False):
            with TestClient(create_local_app(self.dsn,historical_source=self.source if configured else None),
                            base_url='http://127.0.0.1:5188',client=('127.0.0.1',60000),headers=headers) as client:
                real=client.get('/api/v1/tick-alpha/catalog',headers={'X-BTL-Source':'historical'})
                self.assertEqual(real.status_code,200 if configured else 409)
                if configured:self.assertIn('EXNESS',real.json()['label'])
                synthetic=client.get('/api/v1/tick-alpha/catalog',headers={'X-BTL-Source':'synthetic'})
                self.assertEqual(synthetic.status_code,200)
                self.assertEqual(synthetic.json()['label'],'SYNTHETIC / TEST ONLY')
                self.assertEqual(client.get('/api/v1/tick-alpha/catalog',headers={'X-BTL-Source':'unknown'}).status_code,409)

    def test_month_selection_preserves_old_session_pins_and_survives_durable_reload(self):
        from execution.research import ResearchApplication
        source=monthly_source(self.path)
        scope=TrustedScope('historicalmonthsqa:'+uuid.uuid4().hex,'local:operator')
        app=ResearchApplication(self.dsn,scope,historical_source=source)
        try:
            app.create_method(self.method)
            first=dict(self.body,id='session:'+uuid.uuid4().hex)
            original=app.create_session(first)
            later=dict(first,id='session:'+uuid.uuid4().hex,startPeriod='2015-11')
            created=app.create_session(later)
            view=app.workspace(later['id'],{'timeframe':'1m'})
            self.assertEqual(created['metadata']['startPeriod'],'2015-11')
            self.assertEqual(view['quote']['bid'],'2200.002')
            self.assertEqual(view['quote']['ask'],'2200.004')
            self.assertEqual(view['state']['balance'],'10000')
            self.assertFalse(view['state']['unresolved'])
            self.assertEqual(app.create_session(first),original)
            for period in ('2015-09','2016-11','2015-13'):
                with self.assertRaisesRegex(ValueError,'REFUSED_HISTORICAL_PERIOD'):
                    app.create_session(dict(later,id='session:'+uuid.uuid4().hex,startPeriod=period))
            self.assertEqual(len(app.catalog()['sessions']),2)
            app.close();app=ResearchApplication(self.dsn,scope,historical_source=source)
            self.assertEqual(app.create_session(later),created)
            self.assertEqual(app.workspace(later['id'],{'timeframe':'1m'}),view)
            self.assertEqual(app.inspect(first['id']),original)
            self.assertEqual(app.catalog()['startPeriod'],'2015-08')
        finally:app.close()
