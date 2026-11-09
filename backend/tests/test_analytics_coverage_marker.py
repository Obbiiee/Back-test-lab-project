"""Versioned coverage marker keeps new analytics projections fail-closed."""
import unittest

from contracts.primitives import ContractError
from execution.journal_order_index import append


class AnalyticsCoverageMarkerTests(unittest.TestCase):
    class Result:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

        def fetchall(self):
            return []

    class DB:
        def __init__(self, marker):
            self.marker = marker
            self.statements = []

        def execute(self, query, _params=()):
            self.statements.append(query)
            if 'SELECT through_sequence,event_hash,order_count' in query:
                return AnalyticsCoverageMarkerTests.Result((7, 'b' * 64, 0, 0, self.marker))
            return AnalyticsCoverageMarkerTests.Result()

    def test_marked_session_refuses_commit_when_aggregate_row_is_missing(self):
        db = self.DB(1)
        state = {'nextEventIndex': 7, 'eventHash': 'b' * 64}
        with self.assertRaises(ContractError) as raised:
            append(db, 'workspace:a', 'session:a', state, state, [])
        self.assertEqual(raised.exception.code, 'CORRUPT_RECORD')
        self.assertFalse(any('UPDATE btl.tick_journal_projection_heads' in query
                             for query in db.statements))

    def test_unmarked_legacy_session_keeps_compatible_full_fold_path(self):
        db = self.DB(0)
        state = {'nextEventIndex': 7, 'eventHash': 'b' * 64}
        self.assertTrue(append(db, 'workspace:a', 'session:a', state, state, []))
        self.assertTrue(any('UPDATE btl.tick_journal_projection_heads' in query
                            for query in db.statements))


if __name__ == '__main__':
    unittest.main()
