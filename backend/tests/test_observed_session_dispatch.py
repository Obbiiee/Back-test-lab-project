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

        cases = ((LEGACY, False), (QA_ARCHIVE, False), (P0_PRODUCT_ARCHIVE, True),
                 (INTEGRATION_PRODUCT_ARCHIVE, True))
        for artifact, expected in cases:
            state = {'artifact': artifact}
            if artifact != LEGACY: state['orderArchive'] = {}
            with self.subTest(artifact=artifact):
                self.assertIs(_observed_session_uses_product_archive(FakeDb(state),
                    'workspace:test', 'session:test'), expected)

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

    def test_integration_session_terminal_