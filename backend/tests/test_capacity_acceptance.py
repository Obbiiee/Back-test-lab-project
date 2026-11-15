import unittest
from tools.claude_exp.stack import capacity_acceptance as c


class Plan(unittest.TestCase):
    def test_schedule_is_reproducible_staggered_and_within_the_hour(self):
        a, b = c.schedule(7), c.schedule(7)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c.schedule(8))
        times = [r["arrivalS"] for r in a["normalLoad"]]
        self.assertEqual(len(times), 20)
        self.assertEqual(times, sorted(times))
        self.assertTrue(all(i * 180 <= t < (i + 1) * 180 for i, t in enumerate(times)), "one arrival inside each 180 s slot")
        self.assertEqual(len(a["burstOfEight"]), 8)
        self.assertTrue(all(0 <= r["arrivalS"] < 10 for r in a["burstOfEight"]))

    def test_target_workload_is_blocked_by_the_frozen_bounds_and_a_small_one_is_not(self):
        big = c.feasibility()
        self.assertEqual(big["verdict"], "BLOCKED_BY_CONTRACT")
        self.assertEqual(len(big["blockers"]), 2)
        self.assertEqual(big["bounds"]["maxSteps"], 256)
        small = c.feasibility(ticks=2_048)
        self.assertEqual(small["verdict"], "FEASIBLE_UNDER_CONTRACT")

    def test_engine_compute_alone_would_fit_four_worker_slots(self):
        big = c.feasibility()
        self.assertTrue(big["engineComputeFitsWorkerSlots"])
        self.assertLess(big["averageCoresNeededEngineOnly"][1], 4)


if __name__ == "__main__":
    unittest.main()
