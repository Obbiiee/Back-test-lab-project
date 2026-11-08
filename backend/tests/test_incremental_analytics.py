import unittest

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import ContractError
from execution.analysis import metrics as canonical_metrics, project
from execution.incremental_analytics import add_trade, metrics, record, verify
from tests.test_execution_goldens import goldens
from tests.test_tick_execution import exercise


class IncrementalAnalyticsTests(unittest.TestCase):
    def test_incremental_exact_metrics_match_canonical_fold(self):
        rows = [
            {'id': 'order:one', 'net': '5', 'rMultiple': {'numerator': '3', 'denominator': '2'},
             'durationNs': '10'},
            {'id': 'order:two', 'net': '-2', 'rMultiple': None, 'durationNs': '20'},
            {'id': 'order:three', 'net': '0', 'rMultiple': {'numerator': '1', 'denominator': '2'},
             'durationNs': '30'},
            {'id': 'order:four', 'net': '7', 'rMultiple': None, 'durationNs': '40'},
        ]
        projection = record('session:analytics', 4, 'a' * 64)
        for row in rows:
            projection = add_trade(projection, row)
        self.assertEqual(metrics(projection), canonical_metrics(rows))
        self.assertEqual((metrics(projection)['maxWinStreak'], metrics(projection)['maxLossStreak']), (1, 1))

    def test_projection_is_bound_to_exact_session_event_head_and_hash(self):
        projection = record('session:analytics', 4, 'a' * 64)
        raw = canonical_bytes(projection)
        digest = content_hash(projection)
        self.assertEqual(verify(raw, digest, session_id='session:analytics',
            through_sequence=4, event_head='a' * 64), projection)
        with self.assertRaises(ContractError):
            verify(raw, digest, session_id='session:analytics',
                through_sequence=5, event_head='a' * 64)
        with self.assertRaises(ContractError):
            verify(raw, '0' * 64, session_id='session:analytics',
                through_sequence=4, event_head='a' * 64)

    def test_projection_rejects_semantically_invalid_totals_even_with_recomputed_hash(self):
        value = record('session:analytics', 4, 'a' * 64)
        value['totals']['wins'] = 1
        value['contentHash'] = content_hash({key: item for key, item in value.items()
                                             if key != 'contentHash'})
        raw = canonical_bytes(value)
        with self.assertRaises(ContractError):
            verify(raw, content_hash(value), session_id='session:analytics',
                   through_sequence=4, event_head='a' * 64)

    def test_incremental_aggregate_matches_every_frozen_golden_scenario(self):
        for case in goldens()['scenarios']:
            with self.subTest(case=case['id']):
                harness = exercise(case)
                events = harness.store.events[(harness.scope.workspace_id, harness.session)]
                canonical = project(harness.state, events, None)
                aggregate = record(harness.session, harness.state['nextEventIndex'],
                                   harness.state['eventHash'])
                for trade in canonical['completed']:
                    aggregate = add_trade(aggregate, trade)
                self.assertEqual(metrics(aggregate), canonical_metrics(canonical['completed']))


if __name__ == '__main__':
    unittest.main()
