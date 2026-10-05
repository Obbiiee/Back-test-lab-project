import io
import unittest
from datetime import datetime, timezone

from contracts.primitives import ContractError
from precision.histdata import parse_tick, inspect_ticks


class HistDataTickTests(unittest.TestCase):
    def test_fixed_est_milliseconds_and_untrusted_ordinal(self):
        quote = parse_tick("20250701 120000123,100.001,100.002,0\r\n", 7, "authored")
        self.assertEqual(quote.time_ns, 1751389200123000000)
        self.assertEqual(str(quote.bid), "100.001")
        self.assertEqual(quote.event_id, "authored:7")
        self.assertIsNone(quote.source_sequence)
        self.assertFalse(quote.fresh)
        self.assertEqual(datetime.fromtimestamp(quote.time_ns//10**9, timezone.utc).hour, 17)

    def test_invalid_rows_refused(self):
        for row in ("20250230 120000000,100,101,0", "20250101 250000000,100,101,0",
                    "20250101 120000000,102,101,0", "20250101 120000000,NaN,101,0",
                    "20250101 120000000,100,101,-1", "20250101 120000000,100,101",
                    "20250101 120000000,0,101,0"):
            with self.subTest(row=row), self.assertRaises(ContractError):
                parse_tick(row, 1, "authored")

    def test_ties_repeats_and_gaps_preserved(self):
        row = "20250101 120000000,100,101,0\n"
        lines = (row, row, "20250101 120101001,100,100,0\n")
        report = inspect_ticks(iter(lines), "authored")
        self.assertEqual((report["rows"], report["timestamp_ties"], report["adjacent_repeats"]), (3, 1, 1))
        self.assertEqual((report["gaps_over_60s"], report["zero_spread"]), (1, 1))
        self.assertEqual(report["max_gap_ns"], "61001000000")
        self.assertFalse(report["coverage_complete"])

    def test_malformed_and_out_of_order_poison_acceptance(self):
        lines = ("20250101 120001000,100,101,0\n", "bad\n", "20250101 120000000,100,101,0\n")
        report = inspect_ticks(iter(lines), "authored")
        self.assertEqual((report["invalid_rows"], report["out_of_order"], report["structural_status"]),
                         (1, 1, "REJECT"))

    def test_bounds_and_empty(self):
        self.assertEqual(inspect_ticks(iter(()), "authored")["structural_status"], "EMPTY")
        with self.assertRaises(ContractError):
            inspect_ticks(io.StringIO("bad\nbad\n"), "authored", max_rows=1)
        with self.assertRaises(ContractError):
            parse_tick("20250101 120000000,100,101,0", True, "authored")

    def test_streaming_repeatability_and_exact_spread(self):
        raw = "20250101 120000000,100.00000000000000000001,100.00000000000000000003,0\n"
        first = inspect_ticks(io.StringIO(raw), "authored")
        self.assertEqual(first, inspect_ticks(io.StringIO(raw), "authored"))
        self.assertEqual(first["min_spread"], "0.00000000000000000002")


if __name__ == "__main__":
    unittest.main()
