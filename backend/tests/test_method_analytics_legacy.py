"""Bounded legacy Session fold contracts without a database."""
import unittest
from unittest.mock import patch

from execution.method_analytics_projection import fold_legacy_session


def state():
    return dict(sessionId='session:legacy', revision=4, datasetId='dataset:one',
        datasetVersion='d' * 64, profileHash='profile:one',
        engineVersion='local:v1', eventHash='e' * 64,
        profile={'accountCurrency': 'USD'})


class LegacyMethodAnalyticsTests(unittest.TestCase):
    def test_verified_legacy_fold_reduces_trades_to_one_session_contribution(self):
        events = iter(({'sequence': 0}, {'sequence': 1}))
        completed = [
            {'net': '5/2', 'durationNs': '10'},
            {'net': '-1', 'durationNs': '20'},
        ]
        with patch('execution.analysis.project', return_value={
                'status': 'COMPLETE', 'completed': completed}) as project:
            result = fold_legacy_session(state(), events)

        project.assert_called_once()
        self.assertIs(project.call_args.args[1], events)
        item = result['item']
        self.assertEqual(item['projection'], dict(tradeCount=2, wins=1, losses=1,
            breakeven=0, positive='2.5', negative='1', net='1.5', durationNs='30'))
        self.assertEqual(item['session']['sessionId'], 'session:legacy')
        self.assertEqual(item['unit'], ('profile:one', 'local:v1', 'USD'))

    def test_unavailable_legacy_analysis_is_not_added_as_zero_trades(self):
        with patch('execution.analysis.project', return_value={
                'status': 'UNAVAILABLE', 'reason': 'REFUSED_ANALYSIS_LIMIT'}):
            result = fold_legacy_session(state(), iter(()))
        self.assertEqual(result, dict(status='UNAVAILABLE', reason='REFUSED_ANALYSIS_LIMIT'))


if __name__ == '__main__':
    unittest.main()
