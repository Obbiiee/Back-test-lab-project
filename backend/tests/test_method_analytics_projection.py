"""Bounded analytics projection tests using synthetic committed-analysis results."""
import unittest
from unittest.mock import MagicMock, patch

from application.models import TrustedScope
from execution.research import ResearchApplication, method_policy
from execution.method_analytics_projection import MethodAnalyticsAccumulator, legacy_session_item


def method():
    return {'schemaVersion': 1, 'artifact': 'BTL-LOCAL-METHOD-1', 'id': 'method:analytics',
            'name': 'Synthetic analytics', 'kind': 'FREE_STYLE', 'checklistOn': False,
            'conditions': [], 'riskPercent': None, 'rr': None}


class MethodAnalyticsProjectionTests(unittest.TestCase):
    def app(self, states, completed_by_session, analysis_status=None):
        app = ResearchApplication.__new__(ResearchApplication)
        app.dsn = 'authored:no-database'
        app.scope = TrustedScope('workspace:analytics', 'actor:analytics')
        record = method()
        policy = method_policy(record)
        db = MagicMock()
        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def fetchall(self):
                return self.rows

        def execute(sql, params=None):
            if sql.startswith('SELECT session_id FROM btl.tick_research_sessions'):
                _workspace, _method, after, maximum = params
                selected = sorted(key for key in states if key > after)[:maximum]
                return Rows([(session_id,) for session_id in selected])
            return Rows([])

        db.execute.side_effect = execute
        manager = MagicMock()
        manager.__enter__.return_value = db
        app._method = lambda _db, _method_id: record
        metadata = {'artifact': 'BTL-LOCAL-SESSION-1', 'methodHash': policy.definition_hash}
        app._session = lambda _db, session_id: (metadata, record, states[session_id], {})

        def committed(_db, state):
            status = (analysis_status or {}).get(state['sessionId'], 'COMPLETE')
            return {'status': status, 'reason': 'SYNTHETIC_INCOMPLETE' if status != 'COMPLETE' else None,
                    'completed': completed_by_session.get(state['sessionId'], [])}

        app._committed_analysis = committed
        return app, policy, manager

    def state(self, session_id, *, profile_hash='profile:stable', event_count=12, currency='USD'):
        return {'sessionId': session_id, 'revision': 4, 'nextEventIndex': event_count,
                'profileHash': profile_hash, 'engineVersion': 'engine:stable',
                'profile': {'accountCurrency': currency}, 'eventHash': 'a' * 64,
                'datasetId': 'synthetic:dataset', 'datasetVersion': 'b' * 64}

    def test_legacy_trade_rows_reduce_to_exact_bounded_session_contribution(self):
        state = self.state('session:legacy')
        completed = [
            {'net': '3/2', 'durationNs': '10'},
            {'net': '-2', 'durationNs': '20'},
            {'net': '0', 'durationNs': '30'},
        ]
        item = legacy_session_item(state, completed)
        accumulator = MethodAnalyticsAccumulator('method:analytics', 'a' * 64)
        accumulator.include(item)
        result = accumulator.result()
        self.assertEqual(result['completedTradeNet'], '-0.5')
        self.assertEqual((result['metrics']['tradeCount'], result['metrics']['wins'],
                          result['metrics']['losses'], result['metrics']['breakeven']),
                         (3, 1, 1, 1))
        self.assertEqual(result['metrics']['averageDurationNs'],
                         {'numerator': '20', 'denominator': '1'})

    def test_positive_committed_trade_projection_pools_sessions_without_cross_session_streaks(self):
        states = {key: self.state(key) for key in ('session:one', 'session:two', 'session:three')}
        # These rows stand for completed positions returned by committed event
        # projection; no account balance/equity series is combined.
        completed = {'session:one': [{'id': 'win', 'net': '5', 'rMultiple': None, 'durationNs': '10'}],
                     'session:two': [{'id': 'loss', 'net': '-2', 'rMultiple': None, 'durationNs': '20'}],
                     'session:three': [{'id': 'flat', 'net': '0', 'rMultiple': None, 'durationNs': '30'}]}
        app, policy, manager = self.app(states, completed)
        with patch('execution.research.connect', return_value=manager):
            result = app.method_analytics(policy.method_id)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['completedTradeNet'], '3')
        self.assertEqual((result['metrics']['tradeCount'], result['metrics']['wins'],
                          result['metrics']['losses'], result['metrics']['breakeven']), (3, 1, 1, 1))
        self.assertNotIn('maxWinStreak', result['metrics'])
        self.assertNotIn('maxLossStreak', result['metrics'])
        self.assertFalse(result['balancesCombined'])
        self.assertEqual([item['tradeCount'] for item in result['includedSessions']], [1, 1, 1])

    def test_incompatible_financial_units_fail_closed(self):
        states = {'session:one': self.state('session:one'),
                  'session:two': self.state('session:two', currency='EUR')}
        app, policy, manager = self.app(states, {})
        with patch('execution.research.connect', return_value=manager):
            result = app.method_analytics(policy.method_id)
        self.assertEqual((result['status'], result['reason']), ('UNAVAILABLE', 'INCOMPATIBLE_FINANCIAL_UNITS'))
        self.assertIsNone(result['metrics'])

    def test_method_scans_more_than_128_sessions_in_bounded_keyset_batches(self):
        states = {f'session:{index:03d}': self.state(f'session:{index:03d}')
                  for index in range(130)}
        completed = {session_id: [{'id': 'win', 'net': '1', 'durationNs': '10'}]
                     for session_id in states}
        app, policy, manager = self.app(states, completed)
        with patch('execution.research.connect', return_value=manager):
            result = app.method_analytics(policy.method_id)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['metrics']['tradeCount'], 130)
        self.assertEqual(result['completedTradeNet'], '130')
        self.assertEqual(result['includedSessionCount'], 130)
        self.assertEqual(len(result['includedSessions']), 128)
        self.assertTrue(result['includedSessionsTruncated'])

    def test_incomplete_session_is_excluded_without_blocking_other_sessions(self):
        incomplete = {'session:one': self.state('session:one'), 'session:two': self.state('session:two')}
        app, policy, manager = self.app(incomplete, {}, {'session:two': 'UNAVAILABLE'})
        with patch('execution.research.connect', return_value=manager):
            result = app.method_analytics(policy.method_id)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['excludedSessions'], [{'sessionId': 'session:two', 'reason': 'SYNTHETIC_INCOMPLETE'}])

        overflow = {'session:one': self.state('session:one', event_count=4097)}
        app, policy, manager = self.app(overflow, {}, {'session:one': 'UNAVAILABLE'})
        with patch('execution.research.connect', return_value=manager):
            result = app.method_analytics(policy.method_id)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['excludedSessions'], [
            {'sessionId': 'session:one', 'reason': 'SYNTHETIC_INCOMPLETE'}])
        self.assertEqual(result['metrics']['tradeCount'], 0)


if __name__ == '__main__':
    unittest.main()
