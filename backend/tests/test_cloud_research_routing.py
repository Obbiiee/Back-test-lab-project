"""Fail-closed selection between operator-pinned and synthetic Session routes."""
import unittest

from cloud.research_routing import observed_route
from contracts.primitives import ContractError


class ResearchRoutingTests(unittest.TestCase):
    def test_without_operator_catalog_keeps_explicit_synthetic_qa_route(self):
        self.assertFalse(observed_route('create_session', ({'id': 'session:test'},), None))

    def test_operator_catalog_requires_public_source_key_for_new_session(self):
        with self.assertRaises(ContractError) as raised:
            observed_route('create_session', ({'id': 'session:test'},), object())
        self.assertEqual(raised.exception.code, 'INVALID_INPUT')

    def test_operator_catalog_routes_source_pinned_session_to_observed_engine(self):
        self.assertTrue(observed_route('create_session',
            ({'id': 'session:test', 'sourceKey': 'catalog:month'},), object()))

    def test_operator_catalog_keeps_catalog_and_method_creation_on_observed_engine(self):
        catalog = object()
        self.assertTrue(observed_route('catalog', (), catalog))
        self.assertTrue(observed_route('create_method', ({'id': 'method:test'},), catalog))

    def test_no_catalog_does_not_select_observed_engine(self):
        for operation in ('catalog', 'create_method', 'create_session', 'replay_to'):
            with self.subTest(operation=operation):
                self.assertFalse(observed_route(operation, (), None))


if __name__ == '__main__':
    unittest.main()
