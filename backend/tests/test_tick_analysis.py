"""Independent frozen vectors, exact summaries and actual PG lifecycle projection."""
from copy import deepcopy
from fractions import Fraction
import os
import unittest
import uuid

from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from execution.analysis import project, metrics, MAX_ANALYSIS_EVENTS
from execution.research import ResearchApplication
from execution.research_fixture import STEP_NS
from infrastructure.database import connect, migrate
from tests.test_execution_goldens import goldens
from tests.test_tick_execution import exercise, Harness, provider_for, open_plan
from tests.test_research_sessions import method, review_request

DSN=os.getenv('BTL_TEST_DATABASE_URL')


class AnalysisGoldenTests(unittest.TestCase):
    def test_every_frozen_vector_reconciles_without_rounding_partial_net_twice(self):
        for case in goldens()['scenarios']:
            with self.subTest(case=case['id']):
                h=exercise(case);state=h.state;events=h.store.events[(h.scope.workspace_id,h.session)]
                before=canonical_bytes(state)
                out=project(state,iter(events),None)
                self.assertEqual(out['account']['balance'],case['balance'])
                self.assertEqual(Fraction(out['account']['netCashChange']),Fraction(case['balance'])-10000)
                self.assertEqual(out['metrics']['tradeCount'],sum(o['status']=='CLOSED' for o in state['orders'].values()))
                if out['completed']:
                    self.assertEqual(Fraction(out['completed'][0]['net']),Fraction(case['balance'])-10000)
                    self.assertIsNone(out['completed'][0]['rMultiple'])
                self.assertEqual(canonical_bytes(state),before)
                self.assertIsNone(out['account']['equityIndicative'])
                if case['id']=='partial-then-full-fixed-commission':
                    self.assertEqual(out['completed'][0]['commission'],'0.4')
                    self.assertEqual(out['completed'][0]['net'],'25.6')
                if case['id']=='changing-untrusted-tie':
                    self.assertEqual(out['metrics']['unresolved'],1)
                    self.assertEqual(out['metrics']['tradeCount'],0)

    def test_exact_ratios_completed_denominator_and_breakeven_breaks_streaks(self):
        result=metrics([{'net':v} for v in ['10','20','0','-5','-10','0','30']])
        self.assertEqual((result['wins'],result['losses'],result['breakeven']),(3,2,2))
        self.assertEqual(result['winRate'],dict(numerator='3',denominator='7'))
        self.assertEqual(result['expectancy'],dict(numerator='45',denominator='7'))
        self.assertEqual(result['profitFactor'],dict(numerator='4',denominator='1'))
        self.assertEqual((result['maxWinStreak'],result['maxLossStreak']),(2,2))
        for key in ('winRate','averageWin','averageLoss','expectancy','profitFactor'):
            self.assertIsNone(metrics([])[key])
        self.assertIsNone(metrics([{'net':'10'}])['profitFactor'])

    def test_short_mark_uses_revealed_ask_and_future_mark_is_unavailable(self):
        case=next(c for c in goldens()['scenarios'] if c['id']=='market-short')
        h=Harness(provider_for(case));h.call('OPEN',open_plan(case['open']),name='short:mark')
        h.through(case['rows'][0][0])
        quote=dict(timeNs=str(case['rows'][0][0]),bid=case['rows'][0][1],ask=case['rows'][0][2])
        events=h.store.events[(h.scope.workspace_id,h.session)];state=h.state
        expected=(Fraction(state['orders']['short:mark']['entryPrice'])-Fraction(quote['ask']))*100*Fraction(case['open']['quantity'])
        self.assertEqual(Fraction(project(state,events,quote)['account']['unrealizedIndicative']),expected)
        quote['timeNs']=str(int(state['throughNs'])+1)
        self.assertIsNone(project(state,events,quote)['account']['unrealizedIndicative'])

    def test_corrupt_missing_future_chain_and_over_budget_refuse_without_partial_success(self):
        h=exercise(goldens()['scenarios'][0]);state=h.state;events=h.store.events[(h.scope.workspace_id,h.session)]
        with self.assertRaises(ContractError):project(state,events[1:],None)
        wrong=deepcopy(events);wrong[-1]['detail']['balanceDelta']='999'
        with self.assertRaises(ContractError):project(state,wrong,None)
        future=deepcopy(state);future['throughNs']='0'
        with self.assertRaises(ContractError):project(future,events,None)
        def must_not_read():
            raise AssertionError('No event allocation above the analysis budget')
            yield
        large=deepcopy(state);large['nextEventIndex']=MAX_ANALYSIS_EVENTS+1
        refused=project(large,must_not_read(),None)
        self.assertEqual(refused['status'],'UNAVAILABLE')
        self.assertNotIn('metrics',refused)


@unittest.skipUnless(DSN,'Actual isolated PostgreSQL required; skips are not PASS')
class AnalysisPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(DSN)

    def setUp(self):
        self.scope=TrustedScope('analysisqa:'+uuid.uuid4().hex,'fixture:operator')
        self.app=ResearchApplication(DSN,self.scope)
        m=method();self.app.create_method(m)
        self.session='session:'+uuid.uuid4().hex
        self.app.create_session(dict(id=self.session,name='Analysis QA',methodId=m['id'],initialBalance='10000',startPeriod='2020-01'))

    def view(self):return self.app.workspace(self.session,{'timeframe':'1m'})

    def apply(self,kind,payload):
        view=self.view()
        raw=dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',sessionId=self.session,
            commandId='command:'+uuid.uuid4().hex,expectedRevision=view['state']['revision'],kind=kind,payload=payload)
        self.app.apply(self.session,raw)
        return raw

    def advance(self):
        self.apply('ADVANCE',{'targetNs':str(int(self.view()['state']['throughNs'])+STEP_NS)})

    def test_actual_pending_partial_close_completed_mark_history_and_cold_reload(self):
        first=self.view();review=self.app.review(review_request(first));order_id=review['review']['command']['commandId']
        self.app.confirm(self.session,dict(reviewId=order_id,reviewHash=review['reviewHash']))
        self.assertEqual(self.view()['analysis']['orders'][0]['status'],'PENDING')
        self.advance();active=self.view()
        self.assertEqual(active['analysis']['orders'][0]['entryPrice'],active['quote']['ask'])
        self.assertEqual(active['analysis']['account']['unrealizedIndicative'],'-1')
        partial=self.apply('CLOSE',{'orderId':order_id,'quantity':'0.04'})
        self.assertEqual(self.app.apply(self.session,partial)['state'],self.view()['state'])
        self.advance();part=self.view()
        self.assertEqual(part['analysis']['orders'][0]['remaining'],'0.06')
        self.assertEqual(part['analysis']['metrics']['tradeCount'],0)
        self.apply('CLOSE',{'orderId':order_id,'quantity':None});self.advance();done=self.view()
        closed=done['analysis']['completed'][0]
        self.assertEqual((closed['gross'],closed['net']),('-1.8','-1.8'))
        self.assertEqual(closed['durationNs'],str(2*STEP_NS))
        self.assertEqual(done['analysis']['account']['balance'],'9998.2')
        self.assertEqual(done['analysis']['metrics']['maxDrawdown'],'1.8')
        self.assertEqual(done['analysis']['provenance']['eventHead'],done['state']['eventHash'])
        self.assertEqual(len(done['analysis']['annotations']),3)
        cold=ResearchApplication(DSN,self.scope)
        self.assertEqual(canonical_bytes(cold.workspace(self.session,{'timeframe':'1m'})),canonical_bytes(done))
        with connect(DSN) as db:
            total=db.execute('SELECT count(*) FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s',(self.scope.workspace_id,self.session)).fetchone()[0]
        self.assertEqual(total,done['state']['nextEventIndex'])

    def test_projection_scans_bounded_pages_beyond_recent_event_window(self):
        # Exact PG seed remains unchanged while >256 harmless pre-financial seeks
        # prove that latest-event truncation cannot erase the accepted order.
        initial=self.view()
        review=self.app.review(review_request(initial));order_id=review['review']['command']['commandId']
        self.app.confirm(self.session,dict(reviewId=order_id,reviewHash=review['reviewHash']))
        self.apply('CANCEL',{'orderId':order_id})
        from execution.engine import emit
        # Publishing this synthetic acceptance setup uses the actual locked store;
        # each command stays within the frozen 256-event bound.
        def batch(values):
            def op(current,cp):
                proposal=deepcopy(current);emitted=[]
                for _ in values:emit(proposal,emitted,'SESSION_SEEK',classification='ACCEPTED_COMMAND',throughNs=proposal['throughNs'])
                return proposal,cp,emitted,None
            current=self.app.inspect(self.session)
            raw=dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',sessionId=self.session,
                commandId='qa:'+uuid.uuid4().hex,expectedRevision=current['state']['revision'],kind='SEEK',payload={'targetNs':initial['state']['throughNs']})
            return self.app.store.run(self.scope,raw,op)
        batch(range(250));batch(range(20));view=self.view()
        self.assertEqual(len(view['events']),256)
        self.assertEqual(view['eventWindowStart'],16)
        self.assertEqual(view['analysis']['status'],'COMPLETE')
        self.assertEqual(view['analysis']['orders'][0]['status'],'CANCELLED')
        self.assertEqual(view['analysis']['orders'][0]['id'],order_id)
        self.assertEqual(view['analysis']['metrics']['tradeCount'],0)
        self.assertEqual(view['analysis']['provenance']['eventHead'],view['state']['eventHash'])


@unittest.skipUnless(DSN,'Actual isolated PostgreSQL required; skips are not PASS')
class AlphaAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(DSN)

    def journey(self,protocol):
        scope=TrustedScope('alphaaccept:'+uuid.uuid4().hex,'fixture:operator')
        app=ResearchApplication(DSN,scope);m=method('PROTOCOL' if protocol else 'FREE_STYLE',protocol)
        app.create_method(m);session='session:'+uuid.uuid4().hex
        app.create_session(dict(id=session,name='Protective exit acceptance',methodId=m['id'],initialBalance='10000',startPeriod='2020-01'))
        view=app.workspace(session,{'timeframe':'1m'})
        request=review_request(view,True)
        request['draft'].update(side='SHORT' if protocol else 'LONG',orderType='STOP' if protocol else 'LIMIT',
            workflow='PLANNED',entry='2005.9' if protocol else '2006',sl='2006.4' if protocol else '2005',
            tp=None if protocol else '2008',quantity=None,riskPercent=None if protocol else '1')
        if protocol:
            before=canonical_bytes(view)
            with self.assertRaises(ContractError):app.review(request)
            self.assertEqual(canonical_bytes(app.workspace(session,{'timeframe':'1m'})),before)
            request['draft']['observations']=[dict(conditionId='condition',outcome='PASS')]
        reviewed=app.review(request);order=reviewed['review']['command']['commandId']
        receipt=app.confirm(session,dict(reviewId=order,reviewHash=reviewed['reviewHash']))
        self.assertEqual(app.confirm(session,dict(reviewId=order,reviewHash=reviewed['reviewHash'])),receipt)
        pending=app.workspace(session,{'timeframe':'1m'})
        self.assertEqual(pending['analysis']['orders'][0]['status'],'PENDING')
        target=str(int(pending['state']['throughNs'])+24*STEP_NS)
        app.apply(session,dict(schemaVersion=1,artifact='BTL-TICK-EXECUTION-COMMAND-1',sessionId=session,
            commandId='advance:'+uuid.uuid4().hex,expectedRevision=pending['state']['revision'],kind='ADVANCE',payload={'targetNs':target}))
        done=app.workspace(session,{'timeframe':'1m'});five=app.workspace(session,{'timeframe':'5m'})
        self.assertEqual(done['state'],five['state']);self.assertEqual(done['analysis'],five['analysis'])
        self.assertEqual(done['analysis']['provenance']['eventHead'],done['state']['eventHash'])
        self.assertEqual(done['analysis']['metrics']['tradeCount'],1)
        self.assertEqual(len(done['analysis']['annotations']),2)
        self.assertEqual(canonical_bytes(ResearchApplication(DSN,scope).workspace(session,{'timeframe':'1m'})),canonical_bytes(done))
        return done

    def test_freestyle_reviewed_limit_long_stops_from_bid_and_reloads_exactly(self):
        done=self.journey(False);row=done['analysis']['completed'][0]
        self.assertEqual((row['side'],row['entryPrice'],row['exitPrice'],row['exitReason'],row['net']),('LONG','2006','2005','SL','-100'))
        self.assertEqual(done['analysis']['account']['balance'],'9900')
        self.assertEqual(done['analysis']['metrics']['losses'],1)

    def test_protocol_pass_short_stop_target_uses_ask_and_one_completed_position(self):
        done=self.journey(True);row=done['analysis']['completed'][0]
        self.assertEqual((row['side'],row['entryPrice'],row['exitPrice'],row['exitReason'],row['net']),('SHORT','2005.9','2004.9','TP','200'))
        self.assertEqual(done['analysis']['account']['balance'],'10200')
        self.assertEqual(done['analysis']['metrics']['wins'],1)
        self.assertIsNone(row['rMultiple'],'Do not invent explicitly unpinned R0')
