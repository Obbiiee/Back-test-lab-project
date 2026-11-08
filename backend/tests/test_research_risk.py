"""Regression coverage for analytics risk joins beyond the active-order cap."""
import unittest

from execution.research_risk import fetch_review_pins


class Query:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql, self.params = sql, params
        return self

    def fetchall(self):
        return self.rows


class ResearchRiskTests(unittest.TestCase):
    def test_review_pin_join_returns_all_cumulative_orders_without_128_limit(self):
        ids = [f'order:{index:03d}' for index in range(240)]
        rows = [(order_id, b'payload', 'a' * 64, 'b' * 64, index + 1)
                for index, order_id in enumerate(ids)]
        db = Query(rows)

        actual = fetch_review_pins(db, 'workspace:qa', 'session:qa', ids)

        self.assertEqual(len(actual), 240)
        self.assertEqual(db.params, ('workspace:qa', 'session:qa', ids))
        self.assertNotIn('LIMIT', db.sql.upper())

    def test_empty_order_page_does_not_query_review_store(self):
        db = Query([])
        self.assertEqual(fetch_review_pins(db, 'workspace:qa', 'session:qa', []), [])
        self.assertIsNone(db.sql)


if __name__ == '__main__':
    unittest.main()
