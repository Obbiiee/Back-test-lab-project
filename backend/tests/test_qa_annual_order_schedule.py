import unittest

from tests.qa_historical_day_v2 import annual_order_acceptance_upper_bound, annual_order_decision_stages


class AnnualOrderScheduleTests(unittest.TestCase):
    def test_week_month_and_leap_year_limits(self):
        self.assertEqual(annual_order_acceptance_upper_bound(7), 33)
        self.assertEqual(annual_order_acceptance_upper_bound(30), 125)
        self.assertEqual(annual_order_acceptance_upper_bound(366), 1469)
        self.assertLess(annual_order_acceptance_upper_bound(366), 4096)

    def test_four_utc_slots_per_day_are_unique_and_in_order(self):
        for days in (7, 30, 366):
            stages = annual_order_decision_stages(days)
            self.assertEqual(len(stages), days * 4)
            self.assertEqual(sorted(stages)[:4], [0, 6, 12, 18])
            self.assertEqual(sorted(stages)[-4:], [(days-1)*24, (days-1)*24+6,
                                                   (days-1)*24+12, (days-1)*24+18])

    def test_unsupported_stage_length_refuses(self):
        for days in (1, 2, 3, 31, 365, True, 7.0):
            with self.subTest(days=days):
                with self.assertRaises(ValueError):
                    annual_order_decision_stages(days)
                with self.assertRaises(ValueError):
                    annual_order_acceptance_upper_bound(days)


if __name__ == '__main__':
    unittest.main()
