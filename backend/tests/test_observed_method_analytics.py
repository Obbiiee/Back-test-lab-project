"""Synthetic Method analytics aggregation contracts; no database required."""
import unittest

from contracts.primitives import ContractError
from execution.method_analytics_projection import (
    MethodAnalyticsAccumulator, summarize,
)


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

    def test_streaming_aggregate_removes_lifetime_session_list_cap(self):
        accumulator = MethodAnalyticsAccumulator('method:one', 'a' * 64)
        unit = ('profile:one', 'observed:v1', 'USD')
        for index in range(130):
            accumulator.include(dict(unit=unit,
                projection=projection(1, 1, 0, 0, '1', '0', '1', '10'),
                session=session(f'session:{index:03d}', 1)))
        result = accumulator.result()
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['metrics']['tradeCount'], 130)
        self.assertEqual(result['completedTradeNet'], '130')
        self.assertEqual(result['includedSessionCount'], 130)
        self.assertEqual(len(result['includedSessions']), 128)
        self.assertTrue(result['includedSessionsTruncated'])

    def test_excluded_session_details_are_bounded_and_counted(self):
        accumulator = MethodAnalyticsAccumulator('method:one', 'a' * 64)
        for index in range(140):
            accumulator.exclude(dict(sessionId=f'session:{index:03d}',
                reason='ANALYTICS_PROJECTION_NOT_READY'))
        result = accumulator.result()
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['excludedSessionCount'], 140)
        self.assertEqual(len(result['excludedSessions']), 128)
        self.assertTrue(result['excludedSessionsTruncated'])

    def test_incompatible_unit_is_seen_even_when_its_projection_is_missing(self):
        accumulator = MethodAnalyticsAccumulator('method:one', 'a' * 64)
        accumulator.observe_unit(('profile:one', 'observed:v1', 'USD'))
        accumulator.include(dict(unit=('profile:one', 'observed:v1', 'USD'),
            projection=projection(1, 1, 0, 0, '1', '0', '1', '10'),
            session=session('session:one', 1)))
        accumulator.observe_unit(('profile:two', 'observed:v1', 'EUR'))
        accumulator.exclude(dict(sessionId='session:missing', reason='ANALYTICS_PROJECTION_NOT_READY'))
        result = accumulator.result()
        self.assertEqual(result['status'], 'UNAVAILABLE')
        self.assertEqual(result['reason'], 'INCOMPATIBLE_FINANCIAL_UNITS')
        self.assertIsNone(result['metrics'])

    def test_durable_snapshot_round_trip_preserves_totals_and_bounded_details(self):
        accumulator = MethodAnalyticsAccumulator('method:one', 'a' * 64)
        unit = ('profile:one', 'observed:v1', 'USD')
        for index in range(140):
            accumulator.include(dict(unit=unit,
                projection=projection(1, 1, 0, 0, '3/2', '0', '3/2', '10'),
                session=session(f'session:{index:03d}', 1)))
        accumulator.exclude(dict(sessionId='session:legacy', reason='LEGACY'))
        snapshot = accumulator.snapshot()
        restored = MethodAnalyticsAccumulator.restore(snapshot,
            method_id='method:one', method_hash='a' * 64)
        self.assertEqual(restored.result(), accumulator.result())
        self.assertEqual(restored.included_count, 140)
        self.assertEqual(len(restored.included_sessions), 128)
        self.assertEqual(restored.totals['positive'].numerator, 210)
        snapshot['includedSessions'][0]['sessionId'] = 'mutated'
        self.assertEqual(restored.included_sessions[0]['sessionId'], 'session:000')

    def test_durable_snapshot_rejects_corrupt_or_unbounded_state(self):
        accumulator = MethodAnalyticsAccumulator('method:one', 'a' * 64)
        accumulator.include(dict(unit=('profile:one', 'observed:v1', 'USD'),
            projection=projection(1, 1, 0, 0, '1', '0', '1', '10'),
            session=session('session:one', 1)))
        snapshot = accumulator.snapshot()
        bad_count = dict(snapshot)
        bad_count['totals'] = dict(snapshot['totals'], tradeCount=True)
        with self.assertRaises(ContractError):
            MethodAnalyticsAccumulator.restore(bad_count,
                method_id='method:one', method_hash='a' * 64)
        bad_window = dict(snapshot)
        bad_window['includedSessions'] = snapshot['includedSessions'] * 129
        with self.assertRaises(ContractError):
            MethodAnalyticsAccumulator.restore(bad_window,
                method_id='method:one', method_hash='a' * 64)


if __name__ == '__main__':
    unittest.main()

