"""Authored real V2-provider/checkpoint integration; not a broker or SQL proof."""
from copy import deepcopy
from pathlib import Path
import json
import hashlib
import tempfile
import unittest

from contracts.canonical import canonical_bytes, content_hash
from contracts.models import MethodPolicy
from execution.observed_profile import ObservedExecutionProfile
from execution.observed_kernel import apply, seed_state, validate_snapshot, validate_state
from execution.contracts import validate_state as old_validate_state
from ticks.compact_v2 import CompactDatasetBuilder
from ticks.contracts import event_id
from ticks.contracts_v2 import ZERO_VERSION, canonical_v2_bytes, hash_v2
from ticks.provider import SyntheticTickProvider
from ticks.storage_v2 import DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline

S=10**9
BASE=json.loads((Path(__file__).parent/'fixtures/observed_profile_vectors.json').read_text())['profiles'][0]['profile']


class ObservedKernelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.handles=[];self.serial=0
        self.policy=MethodPolicy('method:qa','a'*64,'FREE_STYLE',False,())

    def tearDown(self):
        for obj in reversed(self.handles):
            try:obj.close()
            except Exception:pass
        self.tmp.cleanup()

    def setup_stream(self,quotes,policy=None,diagnostic=False):
        fixture=SyntheticTickProvider([dict(ordinal=str(i+1 if diagnostic else i),timeNs=str(t),bid=b,ask=a,sequence=None) for i,(t,b,a) in enumerate(quotes)])
        desc=fixture.describe(fixture.dataset_id,fixture.dataset_version)
        meta={k:desc[k] for k in ('datasetId','providerId','feedId','instrumentId','providerSymbol','evidenceClass','adapterVersion','validatorVersion','ordering')}
        meta.update(datasetId='authored:observed:'+fixture.dataset_version,providerId='AUTHORED_OBSERVED_QA',feedId='qa:observed:XAUUSD',instrumentId='qa:XAUUSD',providerSymbol='XAUUSD',evidenceClass='PROVIDER_OBSERVATION',adapterVersion='AUTHORED-OBSERVED-QA-1')
        folder=self.root/'store';b=CompactDatasetBuilder(folder,meta,desc['sources'],{'authored':True})
        try:
            position=None
            while True:
                page=fixture.read_page(fixture.dataset_id,fixture.dataset_version,position,256)
                for row in page['events']:
                    e=deepcopy(row);e.update(datasetId=meta['datasetId'],datasetVersion=ZERO_VERSION,providerId=meta['providerId'],feedId=meta['feedId'],instrumentId=meta['instrumentId'],eventId=event_id(meta['providerId'],meta['feedId'],e['provenance']['memberHash'],e['rawOrdinal']))
                    e['quality'].update(freshness='UNKNOWN',gapBefore='UNKNOWN_SILENCE',evidenceHash=None);b.append(e)
                position=page['nextToken']
                if position is None:break
            if diagnostic:
                raw_bad=dict(ordinal='0',timeNs=str(S//2),bid='2301',ask='2300')
                bad_hash=hashlib.sha256(json.dumps(raw_bad,sort_keys=True,separators=(',',':')).encode()).hexdigest();src=desc['sources'][0]
                record=dict(sourceId=src['sourceId'],memberHash=src['memberHash'],rawOrdinal='0',timeNs=str(S//2),code='CROSSED_QUOTE',rawRecordHash=bad_hash)
                block=dict(artifact='BTL-TICK-EVIDENCE-BLOCK-2',blockIndex='0',coverage=[],gaps=[dict(startNs=str(S//2),endNs=str(S//2+1),kind='MISSING_DATA',evidenceHash=bad_hash)],diagnostics=[record],rights={'class':'UNKNOWN','evidenceHash':None})
                version=b.finish(evidence_blocks=iter([block]),audit_record=lambda r:r==record)
            else:version=b.finish()
            b.store.db.execute('PRAGMA journal_mode=DELETE')
        finally:b.store.close()
        raw=deepcopy(BASE);raw['primary']=dict(datasetId=meta['datasetId'],datasetVersion=version,providerId=meta['providerId'],feedId=meta['feedId'],feedInstrumentId=meta['instrumentId'],providerSymbol='XAUUSD',evidenceClass='PROVIDER_OBSERVATION')
        self.profile=ObservedExecutionProfile.from_wire(raw);self.provider=DiskTickProvider(folder,version,read_only=True);self.handles.append(self.provider)
        self.timeline=IndexedTickTimeline(self.provider,meta['datasetId'],version,str(quotes[0][0]),log_folder=self.root/'logs');self.handles.append(self.timeline)
        self.state=seed_state('session:qa',self.profile,policy or self.policy,self.timeline.checkpoint())

    def raw(self,kind,payload,command=None):
        self.serial+=1
        return dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=self.state['sessionId'],commandId=command or 'command:'+str(self.serial),expectedRevision=self.state['revision'],kind=kind,payload=payload)

    def command(self,kind,payload,command=None):
        self.state,events=apply(self.state,self.raw(kind,payload,command));return events

    def advance(self,t):
        frame=self.timeline.advance_through(str(t),self.timeline.cursor);cp=self.timeline.checkpoint()
        self.state,events=apply(self.state,self.raw('ADVANCE',dict(targetNs=str(t))),reveal=frame,checkpoint=cp)
        return events,frame

    def open(self,side='LONG',size='0.01',**changes):
        basis=self.state['quoteBasis'];entry=basis['ask' if side=='LONG' else 'bid'] if basis else '2300.1'
        payload=dict(side=side,orderType='MARKET',workflow='QUICK',entry=entry,quantity=size,sl=None,tp=None,riskPercent='1',observations=[]);payload.update(changes)
        self.command('OPEN',payload,command='order:z');return payload

    def test_long_uses_ask_then_bid_preserves_unknown_and_event_chain(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301'),(2*S,'2302','2302.1')]);self.advance(0);self.open();entry,frame=self.advance(S)
        self.assertEqual(entry[0]['detail']['price'],'2301');self.assertEqual(entry[0]['detail']['evidence']['rawQualities'][0]['freshness'],'UNKNOWN')
        before=deepcopy(frame);self.command('CLOSE',dict(orderId='order:z',quantity=None));exit_,_=self.advance(2*S)
        self.assertEqual(exit_[0]['detail']['price'],'2302');self.assertEqual(self.state['balance'],'10001');self.assertEqual(self.state['orders']['order:z']['status'],'CLOSED');self.assertEqual(frame,before)
        self.assertEqual(exit_[0]['model'],'CONDITIONAL_OBSERVED_TICK_SIMULATION')
        with self.assertRaises(ValueError):old_validate_state(self.state)

    def test_short_bid_entry_ask_exit_and_exact_partial_postings(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2299','2299.1'),(2*S,'2297','2297.1'),(3*S,'2296','2296.1')]);self.advance(0);self.open('SHORT','0.02');entry,_=self.advance(S)
        self.assertEqual(entry[0]['detail']['price'],'2299');self.command('CLOSE',dict(orderId='order:z',quantity='0.01'));first,_=self.advance(2*S)
        self.assertEqual((first[0]['detail']['grossPosted'],self.state['orders']['order:z']['remaining']),('1.9','0.01'))
        self.command('CLOSE',dict(orderId='order:z',quantity=None));self.advance(3*S);self.assertEqual(self.state['balance'],'10004.8')

    def test_nonidentical_equal_time_market_outcome_unresolved_without_posting(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301'),(S,'2301.9','2302')]);self.advance(0);self.open();events,frame=self.advance(S)
        self.assertTrue(self.state['unresolved']);self.assertEqual(self.state['balance'],'10000');self.assertEqual(self.state['orders']['order:z']['status'],'UNRESOLVED')
        self.assertFalse(any(e['kind']=='ENTRY_FILL' for e in events));self.assertEqual(len(frame['groups'][0]['events']),2)
        self.assertEqual(events[0]['detail']['reason'],'UNRESOLVED_EQUAL_TIME_ORDER')

    def test_identical_ties_common_outcome_once_and_all_members_retained(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301'),(S,'2300.9','2301')]);self.advance(0);self.open();events,frame=self.advance(S)
        fills=[e for e in events if e['kind']=='ENTRY_FILL'];self.assertEqual(len(fills),1)
        self.assertEqual(len(fills[0]['detail']['evidence']['eventIds']),2);self.assertTrue(fills[0]['detail']['evidence']['chronologyLimited']);self.assertEqual(len(frame['groups'][0]['events']),2)

    def test_no_action_differing_tie_records_limitation_without_inventing_sequence(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301'),(S,'2301.9','2302')]);self.advance(0)
        self.open(orderType='LIMIT',workflow='PLANNED',entry='2200',sl='2190',tp='2210');events,_=self.advance(S)
        self.assertFalse(self.state['unresolved']);self.assertEqual(events[0]['kind'],'CHRONOLOGY_LIMITATION');self.assertIsNone(self.state['quoteBasis'])

    def test_silence_over_60_seconds_before_entry_is_unresolved(self):
        self.setup_stream([(0,'2300','2300.1'),(61*S,'2300.9','2301')]);self.advance(0);self.open();events,_=self.advance(61*S)
        self.assertEqual(events[0]['detail']['reason'],'UNRESOLVED_OBSERVED_SILENCE');self.assertEqual(self.state['balance'],'10000');self.assertFalse(self.state['financial'])

    def test_exact_60_second_boundary_is_usable_then_empty_revealed_silence_unresolved(self):
        self.setup_stream([(0,'2300','2300.1'),(60*S,'2300.9','2301')]);self.advance(0);self.open();events,_=self.advance(60*S)
        self.assertTrue(any(e['kind']=='ENTRY_FILL' for e in events));self.assertFalse(self.state['unresolved'])
        events,_=self.advance(120*S+1);self.assertTrue(self.state['unresolved']);self.assertEqual(self.state['balance'],'10000')
        self.assertEqual(events[0]['detail']['reason'],'UNRESOLVED_OBSERVED_SILENCE')

    def test_precision_not_rounded_and_missing_or_stale_market_basis_refused(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9001','2301')]);original=deepcopy(self.state)
        with self.assertRaisesRegex(ValueError,'UNRESOLVED_RISK_QUOTE'):self.open()
        self.assertEqual(self.state,original);self.advance(0)
        with self.assertRaisesRegex(ValueError,'REFUSED_STALE_QUOTE'):self.open(entry='2300')
        self.open();events,_=self.advance(S);self.assertEqual(events[0]['detail']['reason'],'UNRESOLVED_QUOTE_PRECISION');self.assertEqual(self.state['balance'],'10000')

    def test_future_or_truncated_diagnostics_and_revisions_refused_without_state_mutation(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301')]);self.advance(0);self.open();before=deepcopy(self.state)
        frame=self.timeline.advance_through(str(S),self.timeline.cursor);cp=self.timeline.checkpoint();raw=self.raw('ADVANCE',dict(targetNs=str(S)))
        for mutate in ('future','truncated','identity','stale'):
            bad=deepcopy(frame);cmd=deepcopy(raw)
            if mutate=='future':bad['throughNs']=str(S+1)
            if mutate=='truncated':bad['diagnostics']['truncated']=True
            if mutate=='identity':bad['datasetId']='wrong:dataset'
            if mutate=='stale':cmd['expectedRevision']-=1
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):apply(self.state,cmd,reveal=bad,checkpoint=cp)
            self.assertEqual(self.state,before)

    def test_protocol_fixed_plan_checklist_and_manual_intervention_rules_retained(self):
        policy=MethodPolicy('method:protocol','b'*64,'PROTOCOL',True,('condition:one',),'1','2')
        self.setup_stream([(0,'2300','2300.1'),(S,'2199.9','2200')],policy);self.advance(0)
        with self.assertRaises(ValueError):self.open()
        payload=dict(orderType='LIMIT',workflow='PLANNED',entry='2200',sl='2190',tp='2220',observations=[dict(conditionId='condition:one',outcome='PASS')])
        with self.assertRaises(ValueError):self.open(size='0.09',**payload)
        self.open(size='0.1',**payload);self.advance(S)
        with self.assertRaises(ValueError):self.command('CLOSE',dict(orderId='order:z',quantity=None))

    def test_half_even_posting_and_corrupt_account_refusal(self):
        self.setup_stream([(0,'2299.8','2299.9'),(S,'2299.9','2300'),(2*S,'2300.005','2300.105')]);self.advance(0);self.open();self.advance(S)
        self.command('CLOSE',dict(orderId='order:z',quantity=None));events,_=self.advance(2*S)
        self.assertEqual((events[0]['detail']['grossExact'],events[0]['detail']['grossPosted']),('0.005','0'))
        bad=deepcopy(self.state);bad['balance']='10000.01'
        with self.assertRaises(ValueError):validate_state(bad)

    def test_more_than_256_advances_and_cold_checkpoint_preserve_exact_state(self):
        self.setup_stream([(i*S,'2300','2300.1') for i in range(300)])
        for i in range(300):
            self.advance(i*S)
            if i==149:
                cp=self.timeline.checkpoint();self.timeline.close();self.timeline=IndexedTickTimeline.resume(self.provider,cp,log_folder=self.root/'logs');self.handles.append(self.timeline);validate_snapshot(self.state,cp)
        cp=self.timeline.checkpoint();validate_snapshot(self.state,cp)
        self.assertEqual((self.state['revision'],self.state['nextGroupIndex']),(300,'300'))
        self.assertLess(len(canonical_v2_bytes(cp)),2048);self.assertNotIn('advanceTargets',str(cp));self.assertEqual(self.state['balance'],'10000')


    def test_prefix_hash_rejects_quote_or_quality_changes_with_unchanged_source_identity(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301')]);self.advance(0);self.open()
        frame=self.timeline.advance_through(str(S),self.timeline.cursor);cp=self.timeline.checkpoint();raw=self.raw('ADVANCE',dict(targetNs=str(S)));before=deepcopy(self.state)
        for field,value in [('bid','2300.8'),('quality',dict(frame['groups'][0]['events'][0]['quality'],freshness='CONFIRMED',evidenceHash='1'*64))]:
            bad=deepcopy(frame);bad['groups'][0]['events'][0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):apply(self.state,raw,reveal=bad,checkpoint=cp)
            self.assertEqual(self.state,before)

    def test_causal_diagnostic_without_new_quote_blocks_live_fill(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301')],diagnostic=True);self.advance(0);self.open()
        events,frame=self.advance(S//2)
        self.assertEqual(len(frame['diagnostics']['records']),1);self.assertEqual(frame['groups'],[])
        self.assertEqual(events[0]['detail']['reason'],'UNRESOLVED_DIAGNOSTIC');self.assertTrue(self.state['unresolved']);self.assertEqual(self.state['balance'],'10000')

    def test_known_diagnostic_invalidates_risk_basis_until_next_usable_observation(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301')],diagnostic=True);self.advance(0);self.advance(S//2)
        self.assertIsNone(self.state['quoteBasis']);self.assertFalse(self.state['unresolved'])
        with self.assertRaisesRegex(ValueError,'UNRESOLVED_RISK_QUOTE'):self.open()
        self.advance(S);self.open();self.assertEqual(self.state['orders']['order:z']['status'],'PENDING')


    def test_private_known_incomplete_evidence_cannot_be_waived_by_conditional_model(self):
        self.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301')]);self.advance(0);self.open()
        frame=self.timeline.advance_through(str(S),self.timeline.cursor);cp=self.timeline.checkpoint()
        # Authored private-source refusal case, not a claim that the frozen
        # current 42.19 producer emits anything other than UNKNOWN coverage.
        frame['coverage'][0]['status']='INCOMPLETE'
        prefix=hash_v2(dict(schemaVersion=2,artifact='BTL-TICK-PREFIX-STEP-2',previousHash=self.state['sourcePrefixHash'],throughNs=frame['throughNs'],groups=frame['groups'],coverage=frame['coverage'],diagnostics=frame['diagnostics']))
        frame['visiblePrefixHash']=prefix;frame['cursor']['visiblePrefixHash']=prefix;cp['cursor']['visiblePrefixHash']=prefix
        state,events=apply(self.state,self.raw('ADVANCE',dict(targetNs=str(S))),reveal=frame,checkpoint=cp)
        self.assertEqual(events[0]['detail']['reason'],'UNRESOLVED_KNOWN_COVERAGE');self.assertEqual(state['balance'],'10000');self.assertTrue(state['unresolved'])
