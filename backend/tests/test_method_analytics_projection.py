"""Bounded analytics projection tests using synthetic committed-analysis results."""
import unittest
from unittest.mock import MagicMock, patch

from application.models import TrustedScope
from execution.analysis import metrics
from execution.research import ResearchApplication, method_policy


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
        db.execute.return_value.fetchall.return_value = [(session_id,) for session_id in states]
        manager = MagicMock()
        manager.__enter__.return_value = db
        app._method = lambda _db, _method_id: record
        metadata = {'artifact': 'BTL-LOCAL-SESSION-1', 'methodHash': policy.definition_hash}
        app._session = lambda _db, session_id: (metadata, record, states[session_id], {})

        def committed(_db, state):
            status = (analysis_status or {}).get(state['sessionId'], 'COMPLETE')
            return {'status': status,
                    'reason': 'SYNTHETIC_INCOMPLETE' if status != 'COMPLETE' else None,
                    'metrics': metrics(completed_by_session.get(state['sessionId'], []))
                    if status == 'COMPLETE' else None}

        app._committed_analysis = committed
        app._durable_session_metrics = lambda _db, _state: None
        return app, policy, manager

    def state(self, session_id, *, profile_hash='profile:stable', event_count=12, currency='USD'):
        return {'sessionId': session_id, 'revision': 4, 'nextEventIndex': event_count,
                'profileHash': profile_hash, 'engineVersion': 'engine:stable',
                'profile': {'accountCurrency': currency}, 'eventHash': 'a' * 64,
                'datasetId': 'synthetic:dataset', 'datasetVersion': 'b' * 64}

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

    def test_incomplete_session_is_excluded_and_lifetime_event_count_is_not_capped(self):
        incomplete = {'session:one': self.state('session:one'), 'session:two': self.state('session:two')}
        app, policy, manager = self.app(incomplete, {}, {'session:two': 'UNAVAILABLE'})
        with patch('execution.research.connect', return_value=manager):
            result = app.method_analytics(policy.method_id)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['excludedSessions'], [{'sessionId': 'session:two', 'reason': 'SYNTHETIC_INCOMPLETE'}])

        overflow = {'session:one': self.state('session:one', event_count=4097)}
        app, policy, manager = self.app(overflow, {})
        with patch('execution.research.connect', return_value=manager):
            result = app.method_analytics(policy.method_id)
        self.assertEqual((result['status'], result['metrics']['tradeCount']), ('COMPLETE', 0))
        self.assertEqual(result['includedSessions'][0]['tradeCount'], 0)

    def test_method_analytics_uses_durable_session_metrics_without_event_fold(self):
        states = {'session:one': self.state('session:one', event_count=9001)}
        app, policy, manager = self.app(states, {})
        durable = metrics([{'net': '6', 'rMultiple': None, 'durationNs': '40'}])
        app._durable_session_metrics = lambda _db, _state: durable

        def no_fold(*_args):
            raise AssertionError('durable Session metrics must bypass full event folding')

        app._committed_analysis = no_fold
        with patch('execution.research.connect', return_value=manager):
            result = app.method_analytics(policy.method_id)

        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['completedTradeNet'], '6')
        self.assertEqual(result['metrics']['tradeCount'], 1)


if __name__ == '__main__':
    unittest.main()
