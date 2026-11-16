import unittest
from types import SimpleNamespace
from unittest.mock import patch

from execution.analysis_cache import AnalysisProjectionCache
from execution.research import ResearchApplication


class AnalysisProjectionCacheTests(unittest.TestCase):
    def test_key_tracks_complete_revision_and_quote_scope(self):
        args = dict(
            dsn='postgresql://qa/db',
            workspace_id='workspace:a',
            session_id='session:a',
            revision=3,
            event_head='a' * 64,
            quote=None,
        )
        key = AnalysisProjectionCache.key(**args)
        self.assertNotEqual(key, AnalysisProjectionCache.key(**{**args, 'revision': 4}))
        self.assertNotEqual(key, AnalysisProjectionCache.key(**{**args, 'event_head': 'b' * 64}))
        self.assertNotEqual(key, AnalysisProjectionCache.key(**{**args, 'workspace_id': 'workspace:b'}))
        self.assertNotEqual(key, AnalysisProjectionCache.key(**{**args, 'dsn': 'postgresql://other/db'}))
        self.assertNotEqual(key, AnalysisProjectionCache.key(**{**args, 'quote': {'bid': '10'}}))

    def test_entries_are_immutable_copies_and_bounded_lru(self):
        cache = AnalysisProjectionCache(max_bytes=64, max_entry_bytes=64)
        first = {'schemaVersion': 1, 'rows': ['first']}
        second = {'schemaVersion': 1, 'rows': ['second']}
        self.assertTrue(cache.put('first', first))
        first['rows'].append('mutated-after-put')
        self.assertEqual(cache.get('first'), {'schemaVersion': 1, 'rows': ['first']})
        self.assertTrue(cache.put('second', second))
        self.assertLessEqual(cache.byte_size, 64)
        self.assertIsNone(cache.get('first'))
        self.assertEqual(cache.get('second'), {'schemaVersion': 1, 'rows': ['second']})

    def test_oversized_projection_bypasses_cache(self):
        cache = AnalysisProjectionCache(max_bytes=64, max_entry_bytes=32)
        self.assertFalse(cache.put('large', {'schemaVersion': 1, 'payload': 'x' * 100}))
        self.assertEqual(cache.byte_size, 0)
        self.assertIsNone(cache.get('large'))

    def test_committed_projection_hit_skips_event_refold_and_returns_copy(self):
        app = ResearchApplication.__new__(ResearchApplication)
        app.dsn = 'postgresql://isolated-cache-test'
        app.scope = SimpleNamespace(workspace_id='workspace:cache-regression')
        state = dict(sessionId='session:cache-regression', revision=17,
                     eventHash='c' * 64, nextEventIndex=0)
        expected = {'schemaVersion': 1, 'orders': [], 'metrics': {'closed': 0}}

        class DB:
            def execute(self, *_args):
                raise AssertionError('cache hit must not query the event ledger')

        with patch('execution.research.project', return_value=expected) as project_call, \
             patch.object(app, '_research_risk'):
            first = app._committed_analysis(DB(), state)
            first['metrics']['closed'] = 99
            second = app._committed_analysis(DB(), state)

        self.assertEqual(project_call.call_count, 1)
        self.assertEqual(second['metrics']['closed'], 0)
        self.assertIsNot(first, second)

    def test_checkpoint_dependent_quote_projection_bypasses_cache(self):
        app = ResearchApplication.__new__(ResearchApplication)
        app.dsn = 'postgresql://isolated-quote-cache-test'
        app.scope = SimpleNamespace(workspace_id='workspace:quote-cache-regression')
        state = dict(sessionId='session:quote-cache-regression', revision=18,
                     eventHash='d' * 64, nextEventIndex=0)
        result = {'schemaVersion': 1, 'orders': [], 'metrics': {'closed': 0}}

        class DB:
            def execute(self, *_args):
                raise AssertionError('empty event prefix should not query')

        with patch('execution.research.project', return_value=result) as project_call, \
             patch.object(app, '_research_risk'):
            app._committed_analysis(DB(), state)
            app._committed_analysis(DB(), state, {'bid': '10'})

        self.assertEqual(project_call.call_count, 2)


if __name__ == '__main__':
    unittest.main()
