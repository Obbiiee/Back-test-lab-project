"""SQL-shape contracts for revision-pinned Analytics pages without PostgreSQL."""
import unittest

from contracts.primitives import ContractError
from execution.analytics_page_query import closed_trade_rows


class FakeCursor:
    def __init__(self, rows=(), row=None):
        self.rows = list(rows)
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeDb:
    def __init__(self, rows=(), anchor=True):
        self.rows = list(rows)
        self.anchor = anchor
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((sql, params))
        if sql.startswith("SELECT order_id"):
            return FakeCursor(row=(params[-1],) if self.anchor else None)
        return FakeCursor(rows=self.rows)


class AnalyticsPageQueryTests(unittest.TestCase):
    def test_cursor_page_uses_tuple_keyset_and_no_offset(self):
        candidates = [(i, f"trade:{i}", b"row", "a" * 64) for i in (7, 8, 9)]
        db = FakeDb(candidates)
        rows, more = closed_trade_rows(db, "workspace:one", "session:one", limit=2,
            offset=0, total=100, cursor=(5, "trade:5"), event_count=200)
        self.assertEqual([row[0] for row in rows], [7, 8])
        self.assertTrue(more)
        query, params = db.calls[-1]
        self.assertIn("(last_sequence,order_id COLLATE \"C\")>(%s,%s::text COLLATE \"C\")", query)
        self.assertIn('ORDER BY last_sequence,order_id COLLATE "C" LIMIT %s', query)
        self.assertNotIn("OFFSET", query.upper())
        self.assertEqual(params, ("workspace:one", "session:one", 5, "trade:5", 3))

    def test_offset_compatibility_page_remains_bounded_and_checks_projection_count(self):
        rows, more = closed_trade_rows(FakeDb([(i, str(i), b"r", "a" * 64) for i in range(4)]),
            "workspace:one", "session:one", limit=3, offset=6, total=9)
        self.assertEqual(len(rows), 3)
        self.assertTrue(more)

    def test_cursor_anchor_must_be_a_closed_projected_order(self):
        with self.assertRaises(ContractError):
            closed_trade_rows(FakeDb(anchor=False), "workspace:one", "session:one", limit=8,
                offset=0, total=1, cursor=(5, "trade:5"), event_count=20)
        with self.assertRaises(ContractError):
            closed_trade_rows(FakeDb(), "workspace:one", "session:one", limit=8,
                offset=0, total=1, cursor=(20, "trade:5"), event_count=20)


if __name__ == "__main__":
    unittest.main()
