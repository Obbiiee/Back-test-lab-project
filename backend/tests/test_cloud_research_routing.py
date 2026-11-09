"""Fail-closed selection between operator-pinned and synthetic Session routes."""
import unittest

from cloud.research_routing import (method_analytics_family, monthly_provider_required,
                                    observed_route, validate_source_selection)
from contracts.primitives import ContractError


class ResearchRoutingTests(unittest.TestCase):
    def test_method_analytics_rejects_mixed_session_engines(self):
        self.assertEqual(method_analytics_family([
            ('s-local', 'BTL-LOCAL-SESSION-1'),
            ('s-observed', 'BTL-OBSERVED-RESEARCH-SESSION-1'),
        ]), 'mixed')

    def test_method_analytics_selects_one_family_or_empty(self):
        self.assertEqual(method_analytics_family([]), 'empty')
        self.assertEqual(method_analytics_family([('s1', 'BTL-LOCAL-SESSION-1')]), 'local')
        self.assertEqual(method_analytics_family([('s1', 'BTL-OBSERVED-RESEARCH-SESSION-1')]), 'observed')

    def test_monthly_provider_is_opened_only_for_source_reading_operations(self):
        for operation in ('create_session', 'inspect', 'workspace', 'bootstrap', 'replay', 'chart_history'):
            with self.subTest(operation=operation):
                self.assertTrue(monthly_provider_required(operation))
        for operation in ('review', 'confirm', 'apply', 'summary', 'journal',
                          'journal_page', 'terminal_order_page', 'command_result', 'method_analytics'):
            with self.subTest(operation=operation):
                self.assertFalse(monthly_provider_required(operation))

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


    def test_missing_or_unknown_source_is_refused_before_queue_admission(self):
        class Catalog:
            _entries = {'catalog:month': {'period': '2024-01'}}
            def selection(self, key, period):
                if (key, period) != ('catalog:month', '2024-01'):
                    raise ContractError('OBSERVED_PERIOD_UNAVAILABLE', 'source')

        catalog = Catalog()
        for payload in ({'id': 'session:test'},
                        {'id': 'session:test', 'sourceKey': 'unknown', 'period': '2024-01'}):
            with self.subTest(payload=payload):
                with self.assertRaises(ContractError) as raised:
                    validate_source_selection(payload, catalog)
                self.assertEqual(raised.exception.code, 'INVALID_INPUT')

    def test_valid_catalog_source_is_preflighted(self):
        class Catalog:
            _entries = {'catalog:month': {'period': '2024-01'}}
            def selection(self, key, period):
                self.asserted = (key, period)
                return object()

        catalog = Catalog()
        validate_source_selection({'sourceKey': 'catalog:month', 'period': '2024-01'}, catalog)
        self.assertEqual(catalog.asserted, ('catalog:month', '2024-01'))

    def test_monthly_synthetic_catalog_preflights_and_uses_tick_route(self):
        class MonthlyCatalog:
            _entries = {('monthly:fixture', '2024-01'): {'eligibility': 'SYNTHETIC'}}
            def selection(self, key, period):
                return self._entries[(key, period)]
            def resolve(self, key, period):
                raise AssertionError('API preflight must not open object storage')

        monthly = MonthlyCatalog()
        payload = {'sourceKey': 'monthly:fixture', 'period': '2024-01', 'startPeriod': '2024-01'}
        self.assertEqual(validate_source_selection(payload, None, monthly), 'MONTHLY_SYNTHETIC')
        self.assertFalse(observed_route('create_session', (payload,), None, monthly))

    def test_monthly_catalog_missing_stale_or_non_synthetic_entries_fail_closed(self):
        class MonthlyCatalog:
            _entries = {('monthly:fixture', '2024-01'): {'eligibility': 'SYNTHETIC'},
                        ('monthly:licensed', '2024-02'): {'eligibility': 'RIGHTS_EVIDENCE_PINNED'}}
            def selection(self, key, period):
                if (key, period) not in self._entries:
                    raise ContractError('REFUSED_SOURCE_NOT_AVAILABLE', 'source')
                return self._entries[(key, period)]
            def resolve(self, key, period):
                raise AssertionError('non-synthetic entries must not be resolved')

        catalog = MonthlyCatalog()
        for payload in ({'sourceKey': 'monthly:fixture', 'period': '2024-02', 'startPeriod': '2024-02'},
                        {'sourceKey': 'monthly:licensed', 'period': '2024-02', 'startPeriod': '2024-02'},
                        {'sourceKey': 'monthly:fixture', 'period': '2024-01', 'startPeriod': '2024-02'}):
            with self.subTest(payload=payload), self.assertRaises(ContractError):
                validate_source_selection(payload, None, catalog)


if __name__ == '__main__':
    unittest.main()
