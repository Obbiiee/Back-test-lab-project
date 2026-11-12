"""Exact domain/revealed-boundary acceptance; memory adapter is test-only."""
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
import unittest
from unittest.mock import patch

from application.models import TrustedScope
from contracts.canonical import content_hash, canonical_bytes
from contracts.models import MethodPolicy
from contracts.primitives import ContractError, require
from execution.contracts import command_wire, money, risk_quantity, profile_wire
from execution.controller import ExecutionController
from execution.engine import advance, submit
from ticks.provider import SyntheticTickProvider
from ticks.timeline import TickTimeline
from tests.test_execution_goldens import goldens


class CompactSnapshotCacheTests(unittest.TestCase):
    def test_compact_cache_retains_ten_active_sessions_and_remains_bounded(self):
        from execution.postgres import (
            _COMPACT_CACHE, _COMPACT_CACHE_MAX, PostgresExecutionStore,
        )

        original = deepcopy(_COMPACT_CACHE)
        try:
            _COMPACT_CACHE.clear()
            store = PostgresExecutionStore('cache-test-dsn')
            expected = {}
            for index in range(10):
                workspace = f'workspace:{index}'
                session = f'session:{index}'
                state = {'schemaVersion': 1, 'index': index, 'revision': index}
                controller = {'cursor': index}
                chain_hash = f'chain:{index}'
                store._cache_write(workspace, session, state, controller, chain_hash)
                expected[(workspace, session)] = (state, controller, chain_hash)

            self.assertGreaterEqual(_COMPACT_CACHE_MAX, 10)
            self.assertLessEqual(len(_COMPACT_CACHE), _COMPACT_CACHE_MAX)
            for (workspace, session), (state, controller, chain_hash) in expected.items():
                pointer = {
                    'revision': state['revision'],
                    'stateHash': content_hash(state),
                    'chainHash': chain_hash,
                    'controller': controller,
                }
                self.assertEqual(store._cache_read(workspace, session, pointer), state)

            for index in range(_COMPACT_CACHE_MAX):
                store._cache_write(f'workspace:extra:{index}', f'session:extra:{index}',
                                   {'schemaVersion': 1, 'index': index, 'revision': index},
                                   {'cursor': index}, f'chain:extra:{index}')
            self.assertEqual(len(_COMPACT_CACHE), _COMPACT_CACHE_MAX)
        finally:
            _COMPACT_CACHE.clear()
            _COMPACT_CACHE.update(original)


class MemoryStore:
    """Only tests pure proposals/orchestration; not a durable production store."""
    def __init__(self):
        self.sessions, self.receipts, self.events = {}, {}, {}

    def create(self, scope, state, checkpoint):
        key = scope.workspace_id, state["sessionId"]
        self.sessions[key] = deepcopy((state, checkpoint))
        self.events[key] = []

    def run(self, scope, raw, operation):
        command = command_wire(raw)
        key = scope.workspace_id, command["sessionId"]
        state, checkpoint = deepcopy(self.sessions[key])
        dedup = key + (command["commandId"],)
        sha = content_hash(command)
        if dedup in self.receipts:
            expected, result = self.receipts[dedup]
            require(sha == expected, "command", "REFUSED_IDEMPOTENCY_CONFLICT")
            return deepcopy(result)
        require(state["revision"] == command["expectedRevision"], "revision", "REFUSED_STALE_REVISION")
        state, checkpoint, events, replay = operation(state, checkpoint)
        state["revision"] += 1
        result = {"state":state,"events":events,"replay":replay}
        self.sessions[key] = deepcopy((state, checkpoint))
        self.receipts[dedup] = sha, deepcopy(result)
        self.events[key] += deepcopy(events)
        return deepcopy(result)

    def inspect(self, scope, session_id, after_sequence=0, maximum=64):
        key = scope.workspace_id, session_id
        return {"state":deepcopy(self.sessions[key][0]), "events":deepcopy(self.events[key][after_sequence:after_sequence+maximum])}


def provider_for(case):
    rows = [dict(ordinal=str(i), timeNs=str(row[0]), bid=row[1], ask=row[2],
                 sequence=str(row[3]) if len(row) > 3 else None) for i,row in enumerate(case["rows"])]
    return SyntheticTickProvider(rows, chunk_size=1, trusted=case.get("trusted",False),
                                 execution_fixture=case.get("authoredQuality",True))


def profile_for(case=None):
    case = case or {}
    p = deepcopy(goldens()["profile"])
    if "commission" in case:
        p.update(commissionModel="FIXED_PER_LOT_SIDE", commissionPerLotSide=case["commission"])
    if "contractSize" in case:
        p["contractSize"] = case["contractSize"]
    return p


def open_plan(plan):
    return dict(plan, workflow="QUICK" if plan["orderType"] == "MARKET" else "PLANNED",
                riskPercent="1", observations=[])


def command(session, name, revision, kind, payload):
    return dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-1", sessionId=session,
                commandId=name, expectedRevision=revision, kind=kind, payload=payload)


class Harness:
    def __init__(self, provider, profile=None, policy=None, store=None, scope=None, session="fixture:session"):
        self.store = store or MemoryStore()
        self.scope = scope or TrustedScope("fixture:workspace", "fixture:actor")
        self.session, self.counter = session, 0
        self.controller = ExecutionController(self.store, provider)
        self.controller.create(self.scope, session, profile or profile_for(), policy)

    @property
    def state(self):
        return self.controller.inspect(self.scope, self.session)["state"]

    def call(self, kind, payload=None, name=None, expected=None):
        self.counter += 1
        raw = command(self.session, name or f"c{self.counter}", self.state["revision"] if expected is None else expected, kind, payload or {})
        return self.controller.apply(self.scope, raw)

    def through(self, time):
        while True:
            result = self.call("ADVANCE", {"targetNs":str(time)})
            if result["replay"]["exhaustedThroughBoundary"]:
                return result


def exercise(case, store=None, scope=None, session="fixture:session"):
    h = Harness(provider_for(case), profile_for(case), store=store, scope=scope, session=session)
    if "seekBeforeOpen" in case:
        h.call("SEEK", {"targetNs":case["seekBeforeOpen"]})
    try:
        h.call("OPEN", open_plan(case["open"]), name="order:1")
    except ContractError as error:
        if case.get("refusal") != error.code:
            raise
        return h
    if case.get("cancelBeforeAdvance"):
        h.call("CANCEL", {"orderId":"order:1"})
    if "manualExits" in case:
        for request in case["manualExits"]:
            h.through(request["after"])
            h.call("CLOSE", {"orderId":"order:1", "quantity":request["quantity"]})
            h.through(request["through"])
    elif max(row[0] for row in case["rows"]) >= int(h.state["throughNs"]):
        h.through(max(row[0] for row in case["rows"]))
    if case.get("cancelAfterAdvance"):
        try:
            h.call("CANCEL", {"orderId":"order:1"})
        except ContractError as error:
            if case.get("refusal") != error.code:
                raise
        else:
            raise AssertionError("Expected cancel refusal")
    if case.get("end"):
        h.call("END")
    return h


def assert_case(test, case, h):
    inspected = h.controller.inspect(h.scope, h.session, maximum=256)
    fills = [e for e in inspected["events"] if e["classification"] == "SIMULATED_FILL"]
    test.assertEqual([[e["kind"],e["detail"]["price"]] for e in fills], case["fills"])
    test.assertEqual(inspected["state"]["balance"], case["balance"])
    for fill in fills:
        test.assertEqual(fill["datasetVersion"], inspected["state"]["datasetVersion"])
        test.assertIn("evidence", fill["detail"])
        test.assertEqual(fill["detail"]["executionModel"], "QUOTE_BASELINE_NOT_BROKER_FILL")
    if "reason" in case:
        test.assertIn(case["reason"], [e["detail"].get("reason") for e in inspected["events"]])
    if "orderStatus" in case:
        from execution.analysis import project
        # Use the controller's committed event view so the same golden can
        # validate both in-memory and durable PostgreSQL adapters.
        history=project(inspected["state"],iter(inspected["events"]),None)
        archived=next(row for row in history['orders'] if row['id']=='order:1')
        test.assertEqual(archived["status"], case["orderStatus"])
    if "exitNets" in case:
        test.assertEqual([e["detail"]["netRealized"] for e in fills if e["kind"] == "EXIT_FILL"],case["exitNets"])
    if case.get("chronologyLimited"):
        test.assertTrue(fills[0]["detail"]["evidence"]["chronologyLimited"])
        test.assertIsNone(fills[0]["detail"]["evidence"]["quote"])
        test.assertEqual(len(fills[0]["detail"]["evidence"]["eventIds"]), 2)


class TickExecutionTests(unittest.TestCase):
    def test_next_event_preview_clamps_to_first_committed_financial_boundary(self):
        from execution.workspace import FixtureTimelineCache
        from execution.jump_next_event import advance_command
        case=next(value for value in goldens()['scenarios'] if value['id']=='buy-limit-improvement')
        provider=provider_for(case);scope=TrustedScope('fixture:jump-workspace','fixture:jump-actor')
        session='fixture:jump-session';store=MemoryStore()
        cache=FixtureTimelineCache(provider,allow_injected_synthetic=True)
        controller=ExecutionController(store,provider,cache)
        controller.create(scope,session,profile_for(case))
        opening=command(session,'order:1',0,'OPEN',open_plan(case['open']))
        controller.apply(scope,opening)
        request=dict(schemaVersion=1,artifact='BTL-JUMP-NEXT-EVENT-1',requestId='d'*32,
                     sessionId=session,expectedRevision=1,timeframe='1m')
        end=int(provider.describe(provider.dataset_id,provider.dataset_version)['range']['endNs'])-1

        def next_jump(expected):
            saved,checkpoint=store.sessions[(scope.workspace_id,session)]
            preview=controller.preview_next_event(scope,saved,checkpoint,str(end))
            raw=advance_command({**request,'targetNs':preview['targetNs']},expected,
                                'BTL-TICK-EXECUTION-COMMAND-1')
            return preview,controller.apply(scope,raw)

        _, checkpoint = store.sessions[(scope.workspace_id, session)]
        _, timeline_entry = cache._entry(scope, session, checkpoint)
        with patch.object(timeline_entry.timeline, 'advance_through',
                          wraps=timeline_entry.timeline.advance_through) as traversals:
            first_preview,first=next_jump(1)
            self.assertEqual(traversals.call_count,1,
                             'The committed ADVANCE should reuse the verified Jump preview traversal')
        self.assertEqual(first_preview['targetNs'],'1')
        self.assertEqual(first_preview['previewGroups'],1,
                         'Jump preview should stop at the first causal financial candidate')
        self.assertEqual([event['kind'] for event in first['events']],['ENTRY_FILL'])
        _, checkpoint = store.sessions[(scope.workspace_id, session)]
        _, timeline_entry = cache._entry(scope, session, checkpoint)
        with patch.object(timeline_entry.timeline, 'advance_through',
                          wraps=timeline_entry.timeline.advance_through) as traversals:
            second_preview,second=next_jump(2)
            self.assertEqual(traversals.call_count,1,
                             'The committed exit ADVANCE should reuse its verified Jump traversal')
        self.assertEqual(second_preview['targetNs'],'2')
        self.assertEqual(second_preview['previewGroups'],1,
                         'Jump preview should stop at the first causal exit candidate')
        self.assertEqual([event['kind'] for event in second['events']],['EXIT_FILL'])

        normal=Harness(provider_for(case),profile_for(case),session=session,
                       scope=TrustedScope('fixture:normal-workspace','fixture:normal-actor'))
        normal.call('OPEN',open_plan(case['open']),name='order:1')
        normal.through(str(end))
        jumped=controller.inspect(scope,session,maximum=256)
        ordinary=normal.controller.inspect(normal.scope,normal.session,maximum=256)
        financial=lambda rows:[(event['kind'],event['orderId'],event['detail']) for event in rows
                               if event['classification']=='SIMULATED_FILL']
        self.assertEqual(financial(jumped['events']),financial(ordinary['events']))
        self.assertEqual(jumped['state']['balance'],ordinary['state']['balance'])
        self.assertEqual(jumped['state']['realizedGross'],ordinary['state']['realizedGross'])

    def test_jump_golden_parity_for_pending_protection_and_tie_events(self):
        from execution.workspace import FixtureTimelineCache
        from execution.jump_next_event import advance_command
        case_ids={'market-long','market-short','buy-limit-improvement','sell-limit-improvement',
            'buy-stop-gap','sell-stop-gap','long-sl-gap','short-sl-gap','long-tp-gap',
            'short-tp-gap','activation-same-event-exit','trusted-tie',
            'equivalent-untrusted-tie','changing-untrusted-tie'}
        for case in goldens()['scenarios']:
            if case['id'] not in case_ids:
                continue
            with self.subTest(case=case['id']):
                provider=provider_for(case)
                scope=TrustedScope('fixture:jump-parity-workspace','fixture:jump-parity-actor')
                session='fixture:jump-parity-session'
                store=MemoryStore()
                controller=ExecutionController(store,provider,FixtureTimelineCache(
                    provider,allow_injected_synthetic=True))
                controller.create(scope,session,profile_for(case))
                controller.apply(scope,command(session,'order:1',0,'OPEN',open_plan(case['open'])))
                normal=Harness(provider_for(case),profile_for(case),session=session,scope=scope)
                normal.call('OPEN',open_plan(case['open']),name='order:1')
                end=int(provider.describe(provider.dataset_id,provider.dataset_version)['range']['endNs'])-1
                request=dict(schemaVersion=1,artifact='BTL-JUMP-NEXT-EVENT-1',requestId='e'*32,
                    sessionId=session,timeframe='1m')
                for _ in range(64):
                    saved,checkpoint=store.sessions[(scope.workspace_id,session)]
                    if saved['unresolved'] or saved['ended']:
                        break
                    preview=controller.preview_next_event(scope,saved,checkpoint,str(end))
                    if not preview['previewGroups'] and int(saved['throughNs'])>=end:
                        break
                    receipt=controller.apply(scope,advance_command({**request,
                        'targetNs':preview['targetNs']},saved['revision'],
                        'BTL-TICK-EXECUTION-COMMAND-1'))
                    if not receipt['events'] and int(receipt['state']['throughNs'])<=int(saved['throughNs']):
                        break
                normal.through(str(end))
                jumped=controller.inspect(scope,session,maximum=256)
                ordinary=normal.controller.inspect(normal.scope,normal.session,maximum=256)
                financial=lambda rows:[(event['kind'],event['orderId'],event['detail']) for event in rows
                    if event['classification']=='SIMULATED_FILL']
                self.assertEqual(financial(jumped['events']),financial(ordinary['events']))
                self.assertEqual(jumped['state']['balance'],ordinary['state']['balance'])
                self.assertEqual(jumped['state']['realizedGross'],ordinary['state']['realizedGross'])

    def test_all_authored_financial_goldens(self):
        for case in goldens()["scenarios"]:
            with self.subTest(case=case["id"]):
                assert_case(self,case,exercise(case))

    def test_terminal_orders_leave_hot_state_and_cumulative_orders_are_unbounded(self):
        from execution.analysis import project
        from execution.terminal_order_archive import GENESIS, record, terminal_orders, verify
        case=goldens()["scenarios"][0];h=Harness(provider_for(case))
        genesis=deepcopy(h.state);plan=open_plan(case["open"])
        archived=[];previous=GENESIS
        for index in range(240):
            order_id=f'order:{index}'
            h.call('OPEN',plan,name=order_id)
            self.assertEqual(set(h.state['orders']),{order_id})
            before=deepcopy(h.state)
            first=len(h.store.events[(h.scope.workspace_id,h.session)])
            h.call('CANCEL',dict(orderId=order_id),name=f'cancel:{index}')
            self.assertEqual(h.state['orders'],{})
            events=h.store.events[(h.scope.workspace_id,h.session)][first:]
            values=terminal_orders(before,h.state,events)
            archived_order=record(session_id=h.session,sequence=index,revision=h.state['revision'],
                order_id=order_id,order=values[order_id]['order'],events=values[order_id]['events'],
                previous_hash=previous)
            verify(archived_order,session_id=h.session,sequence=index,previous_hash=previous)
            archived.append(archived_order);previous=archived_order['recordHash']
        self.assertEqual(h.state['nextEventIndex'],480)
        self.assertEqual(len(archived),240)
        self.assertEqual(archived[-1]['order']['status'],'CANCELLED')
        result=project(h.state,iter(h.store.events[(h.scope.workspace_id,h.session)]),None)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(result['metrics']['tradeCount'],0)
        self.assertEqual(len(result['orders']),240)

    def test_closed_order_archive_projection_preserves_financial_event_details(self):
        from execution.terminal_order_archive import terminal_orders, record, verify, GENESIS
        case=next(row for row in goldens()['scenarios'] if row['id']=='partial-then-full-fixed-commission')
        h=Harness(provider_for(case),profile=profile_for(case))
        h.call('OPEN',open_plan(case['open']),name='trade:archive')
        h.through(1)
        h.call('CLOSE',dict(orderId='trade:archive',quantity='0.04'))
        h.through(2)
        h.call('CLOSE',dict(orderId='trade:archive',quantity=None))
        before=deepcopy(h.state);first=len(h.store.events[(h.scope.workspace_id,h.session)])
        h.through(3);after=h.state
        events=h.store.events[(h.scope.workspace_id,h.session)][first:]
        projected=terminal_orders(before,after,events)['trade:archive']
        archived=record(session_id=h.session,sequence=0,revision=after['revision'],
            order_id='trade:archive',order=projected['order'],events=projected['events'],
            previous_hash=GENESIS)
        verify(archived,session_id=h.session,sequence=0,previous_hash=GENESIS)
        self.assertEqual(archived['order']['status'],'CLOSED')
        self.assertEqual([event['kind'] for event in archived['terminalEvents']],['EXIT_FILL'])
        self.assertEqual(archived['terminalEvents'][0]['detail']['gross'],'18')

    def test_exact_rounding_risk_sizing_and_profile_refusal(self):
        with localcontext() as ctx:
            ctx.prec = 4
            self.assertEqual(money(Fraction("0.005"),2),"0")
            self.assertEqual(money(Fraction("0.015"),2),"0.02")
            self.assertEqual(money(Fraction("-0.015"),2),"-0.02")
            self.assertEqual(risk_quantity("100","101","98",profile_for()),"0.33")
            self.assertEqual(risk_quantity("100","101","98",profile_for({"commission":"2"})),"0.32")
        p=profile_for();p["accountCurrency"]="EUR"
        with self.assertRaisesRegex(ContractError,"REFUSED_UNSUPPORTED_PROFILE"):profile_wire(p)
        for value in (True,0.01,"NaN"):
            p=profile_for();p["tickSize"]=value
            with self.assertRaises(ContractError):profile_wire(p)
        p=profile_for();p["commissionModel"]="VARIABLE"
        with self.assertRaisesRegex(ContractError,"REFUSED_UNSUPPORTED_PROFILE"):profile_wire(p)

    def test_retry_stale_and_conflicting_command_without_state_change(self):
        case=goldens()["scenarios"][0];h=Harness(provider_for(case))
        raw=command(h.session,"order",0,"OPEN",open_plan(case["open"]))
        first=h.controller.apply(h.scope,raw)
        h.through(2);saved=canonical_bytes(h.state)
        self.assertEqual(h.controller.apply(h.scope,raw),first)
        self.assertEqual(canonical_bytes(h.state),saved)
        conflict=deepcopy(raw);conflict["payload"]["quantity"]="0.2"
        with self.assertRaisesRegex(ContractError,"REFUSED_IDEMPOTENCY_CONFLICT"):h.controller.apply(h.scope,conflict)
        with self.assertRaisesRegex(ContractError,"REFUSED_STALE_REVISION"):h.call("END",expected=0)
        self.assertEqual(canonical_bytes(h.state),saved)

    def test_speed_batch_and_reconstruction_invariance(self):
        case=goldens()["scenarios"][12]
        h1=Harness(provider_for(case));h2=Harness(provider_for(case))
        for h in (h1,h2):h.call("OPEN",open_plan(case["open"]),name="order")
        h1.through(2)
        h2.through(1);h2.through(2)
        a=h1.controller.inspect(h1.scope,h1.session,maximum=256)
        b=h2.controller.inspect(h2.scope,h2.session,maximum=256)
        self.assertEqual(a["events"],b["events"])
        self.assertEqual(a["state"]["balance"],b["state"]["balance"])
        self.assertEqual(a["state"]["orders"],b["state"]["orders"])

    def test_seek_reset_before_financial_history_and_forbidden_rewind(self):
        case=goldens()["scenarios"][0];h=Harness(provider_for(case))
        h.call("SEEK",{"targetNs":"2"});h.call("SEEK",{"targetNs":"1"})
        h.call("OPEN",open_plan(case["open"]),name="order")
        h.through(2)
        # The already-revealed group at1 is never consumed retroactively.
        self.assertEqual([e["detail"]["price"] for e in h.controller.inspect(h.scope,h.session,maximum=256)["events"] if e["kind"]=="ENTRY_FILL"],["105"])
        saved=canonical_bytes(h.state)
        with self.assertRaisesRegex(ContractError,"REFUSED_REWIND_REQUIRES_FORK"):h.call("SEEK",{"targetNs":"1"})
        self.assertEqual(canonical_bytes(h.state),saved)

    def test_revealed_only_input_future_groups_and_evidence_refused(self):
        case=goldens()["scenarios"][0];p=provider_for(case);h=Harness(p)
        h.call("OPEN",open_plan(case["open"]),name="order")
        t=TickTimeline(p,p.dataset_id,p.dataset_version,"1")
        ack=t.advance_through("2",t.cursor)
        saved=deepcopy(h.state)
        with self.assertRaisesRegex(ContractError,"REFUSED_FUTURE_EVIDENCE"):
            advance(saved,ack["groups"],[],ack["diagnostics"],"1")
        with self.assertRaisesRegex(ContractError,"REFUSED_FUTURE_EVIDENCE"):
            advance(saved,[],[{"startNs":"1","endNs":"3","status":"UNKNOWN","evidenceHash":None}],ack["diagnostics"],"2")
        self.assertEqual(h.state,saved)
        inspected=h.controller.inspect(h.scope,h.session)
        self.assertNotIn("controller",inspected)
        self.assertNotIn("advanceTargets",repr(inspected))
        for name in ("provider","read_page","describe","evidence_sidecar","index"):
            self.assertFalse(hasattr(h.controller,name))

    def test_input_copy_group_identity_and_malformed_geometry(self):
        case=goldens()["scenarios"][0];h=Harness(provider_for(case));saved=deepcopy(h.state)
        raw=command(h.session,"order",0,"OPEN",open_plan(case["open"]))
        new,events=submit(saved,raw);new["orders"]["order"]["entry"]="999";events[0]["detail"]["plan"]["entry"]="888"
        self.assertEqual(h.state,saved);self.assertEqual(raw["payload"]["entry"],"101")
        raw["payload"]["sl"]="106"
        with self.assertRaisesRegex(ContractError,"REFUSED_GEOMETRY"):submit(saved,raw)
        p=provider_for(case);t=TickTimeline(p,p.dataset_id,p.dataset_version,"1");ack=t.advance_through("1",t.cursor)
        ack["groups"][0]["groupId"]="0"*64
        with self.assertRaisesRegex(ContractError,"REFUSED_GROUP_IDENTITY"):advance(saved,ack["groups"],ack["coverage"],ack["diagnostics"],"1")

    def test_missing_data_gap_keeps_prior_entry_and_no_exit_pnl(self):
        rows=[dict(ordinal=str(i),timeNs=str(time),bid=bid,ask=ask,sequence=None) for i,(time,bid,ask) in enumerate([(1,"100","101"),(3,"110","111")])]
        proof="1"*64
        p=SyntheticTickProvider(rows,execution_fixture=True,
            gaps=[dict(startNs="2",endNs="3",kind="MISSING_DATA",evidenceHash=proof)],
            coverage=[dict(startNs="1",endNs="2",status="DECLARED_COMPLETE",evidenceHash=proof),
                      dict(startNs="3",endNs="4",status="DECLARED_COMPLETE",evidenceHash=proof)])
        h=Harness(p);h.call("OPEN",open_plan(goldens()["scenarios"][0]["open"]),name="order")
        h.through(1);h.through(3)
        result=h.controller.inspect(h.scope,h.session,maximum=256)
        self.assertEqual([e["kind"] for e in result["events"] if e["classification"]=="SIMULATED_FILL"],["ENTRY_FILL"])
        self.assertTrue(result["state"]["unresolved"]);self.assertEqual(result["state"]["balance"],"10000")
        with self.assertRaisesRegex(ContractError,"REFUSED_UNRESOLVED_SESSION"):h.call("CLOSE",{"orderId":"order","quantity":None})

    def test_already_processed_atomic_group_cannot_fill_a_later_command(self):
        case=goldens()["scenarios"][0];p=provider_for(case);h=Harness(p)
        h.through(1)
        h.call("OPEN",open_plan(case["open"]),name="later:order")
        t=TickTimeline(p,p.dataset_id,p.dataset_version,"1");ack=t.advance_through("1",t.cursor)
        saved=deepcopy(h.state)
        with self.assertRaisesRegex(ContractError,"REFUSED_REPEATED_GROUP"):
            advance(saved,ack["groups"],[],ack["diagnostics"],"1")
        self.assertEqual(h.state,saved)

    def test_protocol_guard_reused_and_cannot_be_bypassed(self):
        case=dict(rows=[[1,"100","101"],[2,"106","107"]])
        policy=MethodPolicy("fixture:protocol","1"*64,"PROTOCOL",True,("condition",),Decimal("1"),Decimal("2"))
        h=Harness(provider_for(case),policy=policy)
        plan=dict(side="LONG",orderType="LIMIT",workflow="PLANNED",entry="101",quantity="0.5",sl="99",tp="105",riskPercent="1",observations=[{"conditionId":"condition","outcome":"PASS"}])
        for changes in ({"workflow":"QUICK","orderType":"MARKET"},{"quantity":"0.4"},{"riskPercent":"2"},{"tp":"106"},{"observations":[]}):
            invalid=dict(plan,**changes)
            with self.assertRaisesRegex(ContractError,"PROTOCOL_BLOCKED"):h.call("OPEN",invalid)
        h.call("OPEN",plan,name="order");h.through(1)
        for size in (None,"0.1"):
            with self.assertRaisesRegex(ContractError,"PROTOCOL_BLOCKED"):h.call("CLOSE",{"orderId":"order","quantity":size})
        h.through(2);self.assertEqual(h.state["balance"],"10250")
        from execution.analysis import project
        history=project(h.state,iter(h.store.events[(h.scope.workspace_id,h.session)]),None)
        self.assertEqual(history['orders'][0]["observations"],[{"conditionId":"condition","outcome":"PASS"}])

    def test_equivalent_no_action_untrusted_group_and_size_bounds(self):
        case=dict(rows=[[1,"100","101"],[1,"101","102"],[2,"105","106"]])
        h=Harness(provider_for(case))
        plan=open_plan(dict(side="LONG",orderType="STOP",entry="105",quantity="0.1",sl="99",tp="110"))
        h.call("OPEN",plan,name="order");h.through(1)
        self.assertFalse(h.state["unresolved"]);self.assertEqual(h.state["orders"]["order"]["status"],"PENDING")
        self.assertIn("CHRONOLOGY_LIMITATION",[e["kind"] for e in h.controller.inspect(h.scope,h.session)["events"]])
        h.through(2);self.assertEqual(h.state["orders"]["order"]["entryPrice"],"106")
        raw=command(h.session,"end",h.state["revision"],"END",{});raw["providerHandle"]={}
        with self.assertRaises(ContractError):command_wire(raw)
        with self.assertRaises(ContractError):h.controller.inspect(h.scope,h.session,maximum=257)


if __name__=="__main__":
    unittest.main()
