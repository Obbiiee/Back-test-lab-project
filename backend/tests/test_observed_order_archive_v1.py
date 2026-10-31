"""Bounded pure contract tests for the isolated QA terminal-order archive."""
from copy import deepcopy
import unittest

from contracts.primitives import ContractError
from execution.observed_order_archive_v1 import (append, advance, summary,
                                                 verify_complete)
from execution.observed_kernel import QA_ORDER_RETENTION_V3,apply,seed_state,validate_state
from tests import test_observed_kernel as kernel_fixtures


def terminal(number, status='CANCELLED', gross='0'):
    # Full logical order record shape is retained; this unit fixture exercises
    # archive encoding, while kernel/PG lifecycle coverage belongs to the
    # integration gate.
    return dict(side='LONG', orderType='LIMIT', workflow='PLANNED', entry='9',
                quantity='0.01', sl='8', tp='10', riskPercent='1', observations=[],
                status=status, availableNs='1', remaining='0.01', entryPrice=None,
                entryFillRef=None, entryCost='0', exitRequest=None,
                grossPosted=gross, riskBalance='10000', riskBasisHash='0'*64)


class ObservedOrderArchiveV1Tests(unittest.TestCase):
    def test_bounded_append_cold_reconstruction_and_integrity_rejection(self):
        base=summary();rows=[]
        for n in range(3):
            row=append(base,session_id='session:archive-test',revision=n+1,
                      order_id=f'order:archive:{n}',order=terminal(n))
            rows.append(row);base=advance(base,[row])
        restored=verify_complete(rows,base,collect=True)
        self.assertEqual(set(restored['orders']),{f'order:archive:{n}' for n in range(3)})
        self.assertEqual(len(restored['orders']),3)
        for broken in (rows[:2], [rows[1],rows[0],rows[2]]):
            with self.assertRaises(ContractError):verify_complete(broken,base)
        corrupt=deepcopy(rows);corrupt[1]['order']['grossPosted']='1'
        with self.assertRaises(ContractError):verify_complete(corrupt,base)

    def test_kernel_terminal_transition_leaves_only_hot_orders_and_preserves_account(self):
        fx=kernel_fixtures.ObservedKernelTests();fx.setUp()
        try:
            fx.setup_stream([(0,'2300','2300.1'),(10**9,'2300.9','2301')])
            legacy=seed_state('session:legacy-retention-v3',fx.profile,fx.policy,fx.timeline.checkpoint())
            with self.assertRaisesRegex(ContractError,'REFUSED_POLICY'):
                validate_state(legacy,order_retention_policy=QA_ORDER_RETENTION_V3)
            state=seed_state('session:archive-kernel',fx.profile,fx.policy,fx.timeline.checkpoint(),
                order_retention_policy=QA_ORDER_RETENTION_V3,qa_order_archive_v1=True)
            def do(kind,payload,cid):
                raw=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',
                    sessionId=state['sessionId'],commandId=cid,expectedRevision=state['revision'],
                    kind=kind,payload=payload)
                return apply(state,raw,order_retention_policy=QA_ORDER_RETENTION_V3,qa_order_archive_v1=True,
                    archived_order_lookup=lambda oid:None)
            frame=fx.timeline.advance_through('0',fx.timeline.cursor);cp=fx.timeline.checkpoint()
            raw=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=state['sessionId'],
                commandId='archive:advance:0',expectedRevision=0,kind='ADVANCE',payload={'targetNs':'0'})
            state,_,rows=apply(state,raw,reveal=frame,checkpoint=cp,
                order_retention_policy=QA_ORDER_RETENTION_V3,qa_order_archive_v1=True,
                archived_order_lookup=lambda oid:None)
            plan=dict(side='LONG',orderType='LIMIT',workflow='PLANNED',entry='2290',quantity='0.01',
                sl='2289',tp='2291',riskPercent='1',observations=[])
            state,_,rows=do('OPEN',plan,'order:archive:first');self.assertEqual(rows,[])
            state,_,rows=do('CANCEL',{'orderId':'order:archive:first'},'archive:cancel:first')
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['order']['status'],'CANCELLED')
            self.assertEqual(state['orders'],{});self.assertEqual(state['orderArchive']['count'],1)
            self.assertEqual(state['realizedGross'],'0');self.assertEqual(state['balance'],'10000')
            validate_state(state,order_retention_policy=QA_ORDER_RETENTION_V3)
            state,_,_=do('OPEN',dict(plan,entry='2280',sl='2279',tp='2281'),'order:archive:second')
            self.assertEqual(set(state['orders']),{'order:archive:second'})
            with self.assertRaisesRegex(ValueError,'REFUSED_DUPLICATE_ORDER_ID'):
                apply(state,dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',
                    sessionId=state['sessionId'],commandId='order:archive:first',expectedRevision=state['revision'],
                    kind='OPEN',payload=plan),order_retention_policy=QA_ORDER_RETENTION_V3,
                    qa_order_archive_v1=True,archived_order_lookup=lambda oid:rows[0]['order'] if oid=='order:archive:first' else None)
        finally:fx.tearDown()

    def test_archive_state_still_rejects_the_129th_active_order_without_mutation(self):
        fx=kernel_fixtures.ObservedKernelTests();fx.setUp()
        try:
            fx.setup_stream([(0,'2300','2300.1')])
            state=seed_state('session:archive-active-cap',fx.profile,fx.policy,fx.timeline.checkpoint(),
                order_retention_policy=QA_ORDER_RETENTION_V3,qa_order_archive_v1=True)
            raw=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=state['sessionId'],
                commandId='archive:advance:0',expectedRevision=0,kind='ADVANCE',payload={'targetNs':'0'})
            frame=fx.timeline.advance_through('0',fx.timeline.cursor);cp=fx.timeline.checkpoint()
            state,_,_=apply(state,raw,reveal=frame,checkpoint=cp,
                order_retention_policy=QA_ORDER_RETENTION_V3,qa_order_archive_v1=True,
                archived_order_lookup=lambda oid:None)
            plan=dict(side='LONG',orderType='LIMIT',workflow='PLANNED',entry='2290',quantity='0.01',
                sl='2289',tp='2291',riskPercent='1',observations=[])
            for index in range(128):
                raw=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=state['sessionId'],
                    commandId=f'active:{index}',expectedRevision=state['revision'],kind='OPEN',payload=plan)
                state,_,_=apply(state,raw,order_retention_policy=QA_ORDER_RETENTION_V3,qa_order_archive_v1=True,
                    archived_order_lookup=lambda oid:None)
            self.assertEqual(len(state['orders']),128)
            before=deepcopy(state)
            raw=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=state['sessionId'],
                commandId='active:128',expectedRevision=state['revision'],kind='OPEN',payload=plan)
            with self.assertRaisesRegex(ContractError,'REFUSED_ACTIVE_ORDER_LIMIT'):
                apply(state,raw,order_retention_policy=QA_ORDER_RETENTION_V3,qa_order_archive_v1=True,
                    archived_order_lookup=lambda oid:None)
            self.assertEqual(state,before)
        finally:fx.tearDown()

    def test_closed_stop_tp_financial_state_matches_legacy_kernel(self):
        quotes=[(0,'2300','2300.1'),(10**9,'2300.9','2301'),
                (2*10**9,'2302','2302.1'),(3*10**9,'2303','2303.1')]
        archive_fx=kernel_fixtures.ObservedKernelTests();archive_fx.setUp();archive_fx.setup_stream(quotes)
        legacy_fx=kernel_fixtures.ObservedKernelTests();legacy_fx.setUp();legacy_fx.setup_stream(quotes)
        try:
            archive_state=seed_state('session:archive-financial',archive_fx.profile,archive_fx.policy,
                archive_fx.timeline.checkpoint(),order_retention_policy=QA_ORDER_RETENTION_V3,
                qa_order_archive_v1=True)
            legacy_state=seed_state('session:archive-financial',legacy_fx.profile,legacy_fx.policy,
                legacy_fx.timeline.checkpoint())
            archive_events=[];legacy_events=[];archive_records=[]
            def step(fx,state,kind,payload,cid,archive):
                raw=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',
                    sessionId=state['sessionId'],commandId=cid,expectedRevision=state['revision'],
                    kind=kind,payload=payload)
                kwargs={}
                if kind=='ADVANCE':
                    frame=fx.timeline.advance_through(payload['targetNs'],fx.timeline.cursor)
                    kwargs.update(reveal=frame,checkpoint=fx.timeline.checkpoint())
                if archive:
                    return apply(state,raw,order_retention_policy=QA_ORDER_RETENTION_V3,
                        qa_order_archive_v1=True,archived_order_lookup=lambda _:None,**kwargs)
                return apply(state,raw,**kwargs)
            archive_state,events,_=step(archive_fx,archive_state,'ADVANCE',{'targetNs':'0'},'financial:quote:0',True);archive_events+=events
            legacy_state,events=step(legacy_fx,legacy_state,'ADVANCE',{'targetNs':'0'},'financial:quote:0',False);legacy_events+=events
            plan=dict(side='LONG',orderType='STOP',workflow='PLANNED',entry='2301.5',quantity='0.01',
                sl='2300.5',tp='2302.5',riskPercent='1',observations=[])
            archive_state,events,_=step(archive_fx,archive_state,'OPEN',plan,'order:financial:stop',True);archive_events+=events
            legacy_state,events=step(legacy_fx,legacy_state,'OPEN',plan,'order:financial:stop',False);legacy_events+=events
            archive_state,events,_=step(archive_fx,archive_state,'ADVANCE',{'targetNs':str(2*10**9)},'financial:entry',True);archive_events+=events
            legacy_state,events=step(legacy_fx,legacy_state,'ADVANCE',{'targetNs':str(2*10**9)},'financial:entry',False);legacy_events+=events
            archive_state,events,archive_records=step(archive_fx,archive_state,'ADVANCE',{'targetNs':str(3*10**9)},'financial:tp',True);archive_events+=events
            legacy_state,events=step(legacy_fx,legacy_state,'ADVANCE',{'targetNs':str(3*10**9)},'financial:tp',False);legacy_events+=events
            self.assertEqual([e['kind'] for e in archive_events].count('ENTRY_FILL'),1)
            self.assertEqual([e['kind'] for e in archive_events].count('EXIT_FILL'),1)
            self.assertEqual(archive_events,legacy_events)
            self.assertEqual(archive_state['balance'],legacy_state['balance'])
            self.assertEqual(archive_state['realizedGross'],legacy_state['realizedGross'])
            self.assertEqual(archive_records[0]['order'],legacy_state['orders']['order:financial:stop'])
            self.assertEqual(archive_state['orderArchive']['grossPosted'],archive_state['realizedGross'])
            self.assertEqual(archive_state['orders'],{})
            validate_state(archive_state,order_retention_policy=QA_ORDER_RETENTION_V3)
        finally:
            archive_fx.tearDown();legacy_fx.tearDown()


if __name__ == '__main__':
    unittest.main()
