"""Small synthetic application regressions, with explicit mocked SQL boundaries."""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

from application.models import TrustedScope
from contracts.primitives import ContractError
from execution.observed_kernel import PRODUCT_ORDER_RETENTION_V1
from execution.observed_order_archive_v1 import PRODUCT_STATE_ARTIFACT
from execution.observed_postgres import ObservedExecutionStore
from execution.observed_research import ObservedResearchApplication, _stored_observed_state
from execution.postgres import pack, unpack
from tests import test_observed_kernel as fixtures


class ObservedProductApplicationTests(unittest.TestCase):
    def test_stored_format_uses_default_tuple_rows_for_snapshot_and_compact(self):
        state = dict(schemaVersion=1, artifact=PRODUCT_STATE_ARTIFACT)
        for pointer in (dict(schemaVersion=1, state=state), dict(schemaVersion=1, revision=0)):
            with self.subTest(pointer=pointer):
                db = MagicMock()
                db.execute.return_value.fetchone.side_effect = [pack(pointer), pack(dict(schemaVersion=1, state=state))]
                self.assertEqual(_stored_observed_state(db, 'workspace:test', 'session:test'), state)
                for call in db.execute.call_args_list:
                    self.assertEqual(call.args[1], ('workspace:test', 'session:test'))

    def test_product_creation_inserts_product_genesis_and_legacy_remains_legacy(self):
        fx = fixtures.ObservedKernelTests()
        fx.setUp()
        try:
            fx.setup_stream([(0, '2300', '2300.1')])
            for product in (True, False):
                with self.subTest(product=product):
                    db = MagicMock()
                    db.execute.return_value.fetchone.return_value = None
                    cache = SimpleNamespace(new_timeline=lambda *_: fx.timeline, seed=MagicMock(), discard=MagicMock())
                    source = SimpleNamespace(cache=cache, start_for_period=lambda *_args, **_kwargs: '0')
                    app = ObservedResearchApplication.__new__(ObservedResearchApplication)
                    app.dsn = 'unused'; app.scope = TrustedScope('workspace:test', 'actor:test')
                    app.catalog = SimpleNamespace(selection=lambda *_: fx.profile, resolve=lambda _: source)
                    app.store = ObservedExecutionStore('unused', state_storage_format='compact-v1',
                        product_order_archive_v1=product, order_retention_policy=PRODUCT_ORDER_RETENTION_V1 if product else None)
                    app._existing = lambda *_: None
                    app._method = lambda *_: dict(schemaVersion=1, artifact='BTL-LOCAL-METHOD-1', id='method:test',
                        name='Test', kind='FREE_STYLE', checklistOn=False, conditions=[], riskPercent=None, rr=None)
                    app.inspect = lambda _: {'created': True}
                    @contextmanager
                    def connection(_dsn):
                        yield db
                    with patch('execution.observed_research.connect', connection), \
                            patch('execution.product_method_lifecycle.require_active_method'), \
                            patch('execution.method_analytics_store.add_session') as add_rollup:
                        result = app.create_session(dict(id='session:test', name='Test', methodId='method:test',
                            initialBalance='10000', sourceKey='fixture', period='1970-01', day=None))
                    self.assertEqual(result, {'created': True})
                    inserts = [call.args[1] for call in db.execute.call_args_list
                               if call.args[0].startswith('INSERT INTO btl.tick_checkpoints')]
                    self.assertEqual(len(inserts), 1)
                    add_rollup.assert_called_once()
                    genesis = unpack(*inserts[0][-2:])['state']
                    self.assertEqual(genesis['artifact'], PRODUCT_STATE_ARTIFACT if product else 'BTL-OBSERVED-EXECUTION-STATE-1')
                    self.assertEqual('orderArchive' in genesis, product)
                    cache.seed.assert_called_once()
        finally:
            fx.tearDown()

    def test_legacy_full_projection_retains_details_across_pages(self):
        app = ObservedResearchApplication.__new__(ObservedResearchApplication)
        app.scope = TrustedScope('workspace:test', 'actor:test')
        state = {'revision': 7, 'eventHash': 'a'*64}
        pages = [dict(status='COMPLETE', provenance=dict(revision=7, eventHead='a'*64),
                      completed=[{'id': str(i)} for i in range(start, stop)],
                      orderDetails={str(i): {'sl': None, 'tp': None} for i in range(start, stop)},
                      nextTradeOffset=next_) for start, stop, next_ in ((0, 64, 64), (64, 65, None))]
        app.statistics = MagicMock()
        app.statistics.inspect.side_effect = pages
        result = app._complete_statistics('session:test', state)
        self.assertEqual(len(result['completed']), 65)
        self.assertEqual(set(result['orderDetails']), {str(i) for i in range(65)})

    def test_full_projection_refuses_revision_change_between_pages(self):
        app = ObservedResearchApplication.__new__(ObservedResearchApplication)
        app.scope = TrustedScope('workspace:test', 'actor:test')
        app.statistics = MagicMock()
        app.statistics.inspect.side_effect = [
            dict(status='COMPLETE', provenance=dict(revision=7), completed=[], orderDetails={}, nextTradeOffset=64),
            dict(status='COMPLETE', provenance=dict(revision=8), completed=[], orderDetails={}, nextTradeOffset=None)]
        with self.assertRaises(ContractError) as error:
            app._complete_statistics('session:test', {'revision': 7, 'eventHash': 'a'*64})
        self.assertEqual(error.exception.code, 'REFUSED_STALE_REVISION')

    def test_full_projection_refuses_a_stale_first_page_before_loading_more(self):
        app = ObservedResearchApplication.__new__(ObservedResearchApplication)
        app.scope = TrustedScope('workspace:test', 'actor:test')
        app.statistics = MagicMock()
        app.statistics.inspect.return_value = dict(status='COMPLETE', provenance=dict(revision=6),
            completed=[], orderDetails={}, nextTradeOffset=64)
        with self.assertRaises(ContractError) as error:
            app._complete_statistics('session:test', {'revision': 7, 'eventHash': 'a'*64})
        self.assertEqual(error.exception.code, 'REFUSED_STALE_REVISION')
        app.statistics.inspect.assert_called_once()
