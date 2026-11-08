"""Synthetic Method analytics aggregation contracts; no database required."""
import unittest

from contracts.primitives import ContractError
from execution.method_analytics_projection import summarize


def projection(count, wins, losses, breakeven, positive, negative, net, duration):
    return {'tradeCount': count, 'wins': wins, 'losses': losses,
            'breakeven': breakeven, 'positive': positive, 'negative': negative,
            'net': net, 'durationNs': duration}


def session(session_id, trade_count):
    return {'sessionId': session_id, 'revision': 7, 'datasetId': 'dataset:one',
            'datasetVersion': 'd' * 64, 'profileHash': 'profile:one',
            'engineVersion': 'observed:v1', 'eventHead': 'e' * 64,
            'tradeCount': trade_count}


class MethodAnalyticsProjectionTests(unittest.TestCase):
    def test_pools_exact_per_session_summaries_without_order_rows(self):
        included = [
            {'unit': ('profile:one', 'observed:v1', 'USD'),
             'projection': projection(2, 1, 1, 0, '5', '2', '3', '40'),
             'session': session('session:one', 2)},
            {'unit': ('profile:one', 'observed:v1', 'USD'),
             'projection': projection(1, 0, 0, 1, '0', '0', '0', '30'),
             'session': session('session:two', 1)},
        ]
        result = summarize('method:one', 'a' * 64,
                           {item['unit'] for item in included}, included, [])
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['completedTradeNet'], '3')
        self.assertEqual((result['metrics']['tradeCount'], result['metrics']['wins'],
                          result['metrics']['losses'], result['metrics']['breakeven']),
                         (3, 1, 1, 1))
        self.assertEqual(result['metrics']['winRate'],
                         {'numerator': '1', 'denominator': '3'})
        self.assertEqual(result['metrics']['averageWin'],
                         {'numerator': '5', 'denominator': '1'})
        self.assertEqual(result['metrics']['averageLoss'],
                         {'numerator': '-2', 'denominator': '1'})
        self.assertEqual(result['metrics']['averageDurationNs'],
                         {'numerator': '70', 'denominator': '3'})
        self.assertEqual({item['sessionId'] for item in result['includedSessions']},
                         {'session:one', 'session:two'})
        self.assertFalse(result['balancesCombined'])
        self.assertNotIn('maxWinStreak', result['metrics'])
        self.assertNotIn('maxLossStreak', result['metrics'])

    def test_mixed_units_fail_closed_without_metrics(self):
        included = [{'unit': ('profile:one', 'observed:v1', 'USD'),
                     'projection': projection(1, 1, 0, 0, '1', '0', '1', '10'),
                     'session': session('session:one', 1)}]
        result = summarize('method:one', 'a' * 64,
            {('profile:one', 'observed:v1', 'USD'), ('profile:two', 'observed:v1', 'EUR')},
            included, [{'sessionId': 'session:legacy', 'reason': 'ANALYTICS_PROJECTION_NOT_READY'}])
        self.assertEqual((result['status'], result['reason']),
                         ('UNAVAILABLE', 'INCOMPATIBLE_FINANCIAL_UNITS'))
        self.assertIsNone(result['metrics'])
        self.assertEqual(result['includedSessions'], [])

    def test_invalid_projection_counts_are_rejected(self):
        included = [{'unit': ('profile:one', 'observed:v1', 'USD'),
                     'projection': projection(True, 1, 0, 0, '1', '0', '1', '10'),
                     'session': session('session:one', 1)}]
        with self.assertRaises(ContractError):
            summarize('method:one', 'a' * 64,
                      {('profile:one', 'observed:v1', 'USD')}, included, [])

    def test_inconsistent_exact_sums_are_rejected(self):
        included = [{'unit': ('profile:one', 'observed:v1', 'USD'),
                     'projection': projection(1, 1, 0, 0, '2', '0', '1', '10'),
                     'session': session('session:one', 1)}]
        with self.assertRaises(ContractError):
            summarize('method:one', 'a' * 64,
                      {('profile:one', 'observed:v1', 'USD')}, included, [])


if __name__ == '__main__':
    unittest.main()
