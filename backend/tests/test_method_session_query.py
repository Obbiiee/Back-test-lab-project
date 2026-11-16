"""Synthetic SQL contracts for bounded Method analytics Session scans."""
import unittest

from execution.method_session_query import (
    METHOD_ANALYTICS_BATCH_SIZE, method_session_batch,
)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeDb:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        after = params[2] if 'session_id>%s' in sql else None
        eligible = [row for row in self.rows if after is None or row[0] > after]
        return FakeCursor(eligible[:params[-1]])


class MethodSessionQueryTests(unittest.TestCase):
    def test_sessions_are_scanned_in_bounded_keyset_batches(self):
        rows = [(f'session:{index:03d}', b'meta', 'a' * 64)
                for index in range(METHOD_ANALYTICS_BATCH_SIZE + 3)]
        db = FakeDb(rows)
        first, more = method_session_batch(db, 'workspace:one', 'method:one')
        self.assertEqual(len(first), METHOD_ANALYTICS_BATCH_SIZE)
        self.assertTrue(more)
        sql, params = db.calls[0]
        self.assertIn('ORDER BY session_id LIMIT %s', sql)
        self.assertNotIn('OFFSET', sql.upper())
        self.assertEqual(params[-1], METHOD_ANALYTICS_BATCH_SIZE + 1)

        second, more = method_session_batch(db, 'workspace:one', 'method:one',
            after=first[-1][0])
        self.assertEqual([row[0] for row in second], [row[0] for row in rows[-3:]])
        self.assertFalse(more)
        self.assertIn('session_id>%s', db.calls[1][0])


if __name__ == '__main__':
    unittest.main()

