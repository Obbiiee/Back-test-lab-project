"""Persisted artifact routing across legacy, Product and QA Sessions."""
import unittest
from unittest.mock import patch

from contracts.primitives import ContractError
from execution.observed_session_dispatch import (
    INTEGRATION_PRODUCT_ARCHIVE, LEGACY, P0_PRODUCT_ARCHIVE, QA_ARCHIVE,
    dispatch_observed_session, observed_session_format,
)
from execution.observed_kernel import PRODUCT_ORDER_RETENTION_V1, seed_state, validate_state
from execution.observed_order_archive_product_v1 import append, advance, summary, verify_complete
from execution.observed_order_archive_v1 import append as p0_append, summary as p0_summary
from execution.observed_order_archive_v1 import verify_record as verify_p0_record
from execution.observed_order_archive_product_v1 import verify_record as verify_integration_record
from execution.observed_postgres import (ObservedExecutionStore, checked_result_value,
    compact_receipt_v1, expand_compact_receipt_v1)
from execution.observed_state_delta_v3 import (encode_compact_base, encode_compact_delta,
    reconstruct_complete)
from contracts.canonical import content_hash
from cloud.research import _observed_session_uses_product_archive
from execution.postgres import pack
from application.models import TrustedScope
from tests import test_observed_kernel as kernel_fixtures


class ObservedSessionDispatchTests(unittest.TestCase):
    def test_hosted_router_uses_persisted_artifact_to_select_product_runtime(self):
        class FakeCursor:
            def __init__(self, row): self.row = row
            def fetchone(self): return self.row

        class FakeDb:
            def __init__(self, state):
                raw, sha = pack(dict(schemaVersion=1, state=state))
                self.row = {'payload': raw, 'content_hash': sha}
            def execute(self, *_args): return FakeCursor(self.row)

        cases = ((LEGACY, 'none'), (QA_ARCHIVE, 'qa-v1'),
                 (P0_PRODUCT_ARCHIVE, 'p0-v1'), (INTEGRATION_PRODUCT_ARCHIVE, 'integration-v1'))
        for artifact, expected_codec in cases:
            state = {'artifact': artifact}
            if artifact != LEGACY: state['orderArchive'] = {}
            with self.subTest(artifact=artifact):
                self.assertEqual(_observed_session_uses_product_archive(FakeDb(state),
                    'workspace:test', 'session:test'), expected_codec)

    def test_legacy_session_has_no_archive_and_keeps_legacy_lifetime_contract(self):
        selected = dispatch_observed_session({'artifact': LEGACY})
        self.assertEqual(selected.archive_codec, 'none')
        self.assertEqual(selected.archive_table, None)
        self.assertEqual(selected.lifetime_order_cap, 128)

    def test_p0_and_integration_product_keep_their_own_archive_formats(self):
        p0 = dispatch_observed_session({'artifact': P0_PRODUCT_ARCHIVE, 'orderArchive': {}})
        integrated = dispatch_observed_session({'artifact': INTEGRATION_PRODUCT_ARCHIVE, 'orderArchive': {}})
        self.assertEqual(p0.archive_codec, 'p0-v1')
        self.assertEqual(p0.archive_table, 'btl.tick_terminal_order_archive_v1')
        self.assertEqual(integrated.archive_codec, 'integration-v1')
        self.assertEqual(integrated.archive_table, 'btl.tick_terminal_orders')
        self.assertIsNone(p0.lifetime_order_cap)
        self.assertIsNone(integrated.lifetime_order_cap)
        self.assertEqual(p0.active_order_cap, integrated.active_order_cap)

    def test_qa_archive_is_not_promoted_to_product(self):
        selected = dispatch_observed_session({'artifact': QA_ARCHIVE, 'orderArchive': {}})
        self.assertEqual(selected.archive_codec, 'qa-v1')
        self.assertEqual(selected.lifetime_order_cap, 512)

    def test_unknown_or_malformed_persisted_artifacts_fail_closed(self):
        for state in ({'artifact': 'BTL-FUTURE-1'}, {'artifact': LEGACY, 'orderArchive': {}}):
            with self.subTest(state=state), self.assertRaises(ContractError):
                dispatch_observed_session(state)
        with self.assertRaises(ContractError):
            observed_session_format(None)

    def test_integration_product_archive_keeps_its_own_summary_and_chain(self):
        fx = kernel_fixtures.ObservedKernelTests(); fx.setUp()
        self.addCleanup(fx.tearDown)
        fx.setup_stream([(0, '2300', '2300.1')])
        state = seed_state('session:integration-format', fx.profile, fx.policy,
            fx.timeline.checkpoint(), order_retention_policy=PRODUCT_ORDER_RETENTION_V1,
            terminal_order_archive_v1=True)
        self.assertEqual(dispatch_observed_session(state).archive_codec, 'integration-v1')
        validate_state(state, order_retention_policy=PRODUCT_ORDER_RETENTION_V1)
        order = {'status': 'CANCELLED', 'grossPosted': '0'}
        record = append(state['orderArchive'], session_id=state['sessionId'], revision=1,
            order_id='order:integration', order=order)
        archived = advance(state['orderArchive'], [record])
        self.assertEqual(archived['artifact'], 'BTL-OBSERVED-TERMINAL-ORDER-ARCHIVE-1-SUMMARY')
        self.assertEqual(verify_complete([record], archived, collect=True)['orders']['order:integration'], order)

    def test_integration_session_terminal_order_transition_uses_p44_archive_codec(self):
        from execution.observed_kernel import apply
        fx = kernel_fixtures.ObservedKernelTests(); fx.setUp()
        self.addCleanup(fx.tearDown)
        fx.setup_stream([(0, '2300', '2300.1')])
        state = seed_state('session:integration-lifecycle', fx.profile, fx.policy,
            fx.timeline.checkpoint(), order_retention_policy=PRODUCT_ORDER_RETENTION_V1,
            terminal_order_archive_v1=True)
        base = encode_compact_base(state)
        chain_hash = base['stateHash']
        deltas = []

        def persist_delta(previous, current):
            nonlocal chain_hash
            delta = encode_compact_delta(previous, current, chain_hash)
            deltas.append(delta)
            chain_hash = delta['body']['recordHash']

        def command(kind, payload, command_id):
            return dict(schemaVersion=1, artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',
                sessionId=state['sessionId'], commandId=command_id,
                expectedRevision=state['revision'], kind=kind, payload=payload)

        frame = fx.timeline.advance_through('0', fx.timeline.cursor)
        before = state
        state, _, _ = apply(state, command('ADVANCE', {'targetNs': '0'}, 'integration:advance'),
            reveal=frame, checkpoint=fx.timeline.checkpoint(),
            order_retention_policy=PRODUCT_ORDER_RETENTION_V1, terminal_order_archive_v1=True,
            archived_order_lookup=lambda oid: None)
        persist_delta(before, state)
        plan = dict(side='LONG', orderType='LIMIT', workflow='PLANNED', entry='2290',
            quantity='0.01', sl='2289', tp='2291', riskPercent='1', observations=[])
        before = state
        state, _, rows = apply(state, command('OPEN', plan, 'order:integration-lifecycle'),
            order_retention_policy=PRODUCT_ORDER_RETENTION_V1, terminal_order_archive_v1=True,
            archived_order_lookup=lambda oid: None)
        persist_delta(before, state)
        self.assertEqual(rows, [])
        before = state
        cancel = command('CANCEL', {'orderId': 'order:integration-lifecycle'}, 'integration:cancel')
        state, events, rows = apply(state, cancel, order_retention_policy=PRODUCT_ORDER_RETENTION_V1,
            terminal_order_archive_v1=True, archived_order_lookup=lambda oid: None)
        persist_delta(before, state)
        self.assertEqual(len(rows), 1)
        self.assertEqual(state['orders'], {})
        self.assertEqual(state['orderArchive']['artifact'],
            'BTL-OBSERVED-TERMINAL-ORDER-ARCHIVE-1-SUMMARY')
        self.assertEqual(verify_complete(rows, state['orderArchive'], collect=True)['count'], 1)
        validate_state(state, order_retention_policy=PRODUCT_ORDER_RETENTION_V1)
        recovered = reconstruct_complete(base, deltas, state['revision'])
        self.assertEqual(recovered, state)
        checked = checked_result_value(dict(schemaVersion=1,
            artifact='BTL-OBSERVED-EXECUTION-RESULT-1', commandId=cancel['commandId'],
            commandHash=content_hash(cancel), state=state, events=events, eventCount=len(events),
            eventFromSequence=state['nextEventIndex']-len(events), eventsComplete=True,
            nextEventSequence=None, replay=None, durable=True, model=state['model']), cancel,
            order_retention_policy=PRODUCT_ORDER_RETENTION_V1)
        receipt = compact_receipt_v1(checked, content_hash(state), chain_hash)
        expanded = expand_compact_receipt_v1(receipt, cancel, recovered, chain_hash,
            order_retention_policy=PRODUCT_ORDER_RETENTION_V1)
        self.assertEqual(expanded['state'], state)
        self.assertEqual(expanded['events'], events)

    def test_product_store_routes_each_persisted_codec_and_verifies_its_records(self):
        store = ObservedExecutionStore('synthetic-dsn', order_retention_policy=PRODUCT_ORDER_RETENTION_V1,
            product_order_archive_v1=True, state_storage_format='compact-v1')
        p0_state = {'artifact': P0_PRODUCT_ARCHIVE, 'orderArchive': {}}
        integration_state = {'artifact': INTEGRATION_PRODUCT_ARCHIVE, 'orderArchive': {}}
        self.assertEqual(store._archive_table(p0_state), 'btl.tick_terminal_order_archive_v1')
        self.assertEqual(store._archive_table(integration_state), 'btl.tick_terminal_orders')
        p0_order = {'status': 'CANCELLED', 'grossPosted': '0'}
        p0_record = p0_append(p0_summary(artifact='BTL-TERMINAL-ORDER-ARCHIVE-1'),
            session_id='session:p0', revision=1, order_id='order:p0', order=p0_order,
            artifact='BTL-TERMINAL-ORDER-ARCHIVE-1')
        integration_order = {'status': 'CANCELLED', 'grossPosted': '0'}
        integration_record = append(summary(), session_id='session:integration', revision=1,
            order_id='order:integration', order=integration_order)
        store._verify_archive_record(p0_state, p0_record, expected_sequence=0)
        store._verify_archive_record(integration_state, integration_record, expected_sequence=0)

    def test_archive_writer_supplies_only_the_selected_table_columns(self):
        store = ObservedExecutionStore('synthetic-dsn', order_retention_policy=PRODUCT_ORDER_RETENTION_V1,
            product_order_archive_v1=True, state_storage_format='compact-v1')
        states = (
            ({'artifact': P0_PRODUCT_ARCHIVE, 'orderArchive': {}},
             p0_append(p0_summary(artifact='BTL-TERMINAL-ORDER-ARCHIVE-1'),
                session_id='session:p0-write', revision=3, order_id='order:p0-write',
                order={'status': 'CANCELLED', 'grossPosted': '0'},
                artifact='BTL-TERMINAL-ORDER-ARCHIVE-1'), False),
            ({'artifact': INTEGRATION_PRODUCT_ARCHIVE, 'orderArchive': {}},
             append(summary(), session_id='session:integration-write', revision=3,
                order_id='order:integration-write', order={'status': 'CANCELLED', 'grossPosted': '0'}), True),
        )
        for state, record, integration in states:
            calls = []
            class FakeDb:
                def execute(self, query, params): calls.append((query, params))
            store._insert_archive_record(FakeDb(), 'workspace:archive-write',
                state['sessionId'] if 'sessionId' in state else record['sessionId'], state, record)
            query, params = calls[0]
            self.assertEqual('terminal_status' in query, integration)
            self.assertEqual(len(params), 9 if integration else 8)
            if integration:
                self.assertEqual(params[4], 'CANCELLED')
            self.assertIn(store._archive_table(state), query)

    def test_archive_artifact_identity_and_hash_chain_are_not_interchangeable(self):
        """The parallel archive wire formats stay versioned even with equal fields."""
        order = {'status': 'CANCELLED', 'grossPosted': '0', 'reason': 'synthetic-contract-test'}
        p0_head = p0_summary(artifact='BTL-TERMINAL-ORDER-ARCHIVE-1')
        integration_summary = summary()
        p0_record = p0_append(p0_head, session_id='session:contract', revision=3,
            order_id='order:contract', order=order,
            artifact='BTL-TERMINAL-ORDER-ARCHIVE-1')
        integration_record = append(integration_summary, session_id='session:contract', revision=3,
            order_id='order:contract', order=order)

        expected_fields = {'schemaVersion', 'artifact', 'sessionId', 'sequence',
            'finalizedRevision', 'orderId', 'previousHash', 'order', 'orderHash', 'recordHash'}
        self.assertEqual(set(p0_record), expected_fields)
        self.assertEqual(set(integration_record), expected_fields)
        self.assertNotEqual(p0_record['artifact'], integration_record['artifact'])
        self.assertNotEqual(p0_record['previousHash'], integration_record['previousHash'])
        self.assertNotEqual(p0_record['orderHash'], integration_record['orderHash'])
        self.assertNotEqual(p0_record['recordHash'], integration_record['recordHash'])
        verify_p0_record(p0_record)
        verify_integration_record(integration_record)
        with self.assertRaises(ContractError):
            verify_p0_record(integration_record)
        with self.assertRaises(ContractError):
            verify_integration_record(p0_record)

    def test_integration_archive_history_pages_keep_cursor_and_revision_binding(self):
        store = ObservedExecutionStore('synthetic-dsn', order_retention_policy=PRODUCT_ORDER_RETENTION_V1,
            product_order_archive_v1=True, state_storage_format='compact-v1')
        summary_state = summary()
        records = []
        for sequence in range(3):
            record = append(summary_state, session_id='session:pages', revision=sequence+1,
                order_id=f'order:pages:{sequence}',
                order={'status': 'CANCELLED', 'grossPosted': str(sequence)})
            records.append(record)
            summary_state = advance(summary_state, [record])
        state = {'artifact': INTEGRATION_PRODUCT_ARCHIVE, 'sessionId': 'session:pages',
            'revision': 9, 'orderArchive': summary_state}

        class FakeCursor:
            def __init__(self, rows=()): self.rows = list(rows)
            def fetchone(self): return self.rows[0] if self.rows else None
            def fetchall(self): return self.rows

        class FakeDb:
            def execute(self, query, params=()):
                if 'ORDER BY sequence DESC LIMIT 1' in query:
                    return FakeCursor([(2, records[-1]['recordHash'])])
                if 'AND sequence=%s' in query:
                    record = records[params[-1]]
                    raw, sha = pack(record)
                    return FakeCursor([(record['sequence'], record['orderId'],
                        record['finalizedRevision'], record['recordHash'], raw, sha)])
                if 'sequence>%s ORDER BY sequence LIMIT' in query:
                    return FakeCursor([(r['sequence'], r['recordHash'], *pack(r)) for r in records
                        if r['sequence'] > params[-2]][:params[-1]])
                return FakeCursor()
            def __enter__(self): return self
            def __exit__(self, *_args): return False

        with patch('execution.observed_postgres.connect', return_value=FakeDb()), \
             patch.object(store, '_read', return_value={'state': state}), \
             patch.object(store, '_verify_order_archive'):
            scope = TrustedScope('workspace:pages', 'actor:pages')
            first = store.order_history_page(scope, 'session:pages', maximum=2)
            self.assertEqual([row['sequence'] for row in first['records']], [0, 1])
            self.assertEqual(first['nextCursor'], {'revision': 9, 'afterSequence': 1})
            second = store.order_history_page(scope, 'session:pages', after_sequence=1,
                revision_pin=9, maximum=2)
            self.assertEqual([row['sequence'] for row in second['records']], [2])
            self.assertIsNone(second['nextCursor'])


if __name__ == '__main__':
    unittest.main()
