import io
import unittest
from datetime import datetime, timezone

from contracts.primitives import ContractError
from precision.histdata import parse_tick, inspect_ticks, provider_period_bounds


class HistDataTickTests(unittest.TestCase):
    def test_provider_calendar_is_fixed_est_across_dst_leap_and_year_boundaries(self):
        for period, start, end in (("2024-03", "2024-03-01T05:00:00+00:00", "2024-04-01T05:00:00+00:00"),
                                   ("2024-02", "2024-02-01T05:00:00+00:00", "2024-03-01T05:00:00+00:00"),
                                   ("2024-12", "2024-12-01T05:00:00+00:00", "2025-01-01T05:00:00+00:00")):
            lo, hi = provider_period_bounds(period)
            self.assertEqual(datetime.fromtimestamp(lo//10**9, timezone.utc).isoformat(), start)
            self.assertEqual(datetime.fromtimestamp(hi//10**9, timezone.utc).isoformat(), end)
        for bad in (None, "2024-1", "2024-13", "0000-01", "9999-12", "2024-03 "):
            with self.assertRaises(ContractError): provider_period_bounds(bad)

    def test_opt_in_period_check_keeps_next_utc_month_tail_and_exact_boundaries(self):
        rows=("20240101 000000000,100,101,0\n", "20240131 235959999,100,101,0\n")
        report=inspect_ticks(rows, "authored", expected_period="2024-01")
        self.assertTrue(report["source_period_compatible"])
        self.assertEqual(report["source_period_outside_rows"], 0)
        self.assertEqual(datetime.fromtimestamp(int(report["last_ns"])//10**9, timezone.utc).month, 2)
        report=inspect_ticks(("20231231 235959999,100,101,0\n", *rows, "20240201 000000000,100,101,0\n"),
                             "authored", expected_period="2024-01")
        self.assertEqual(report["source_period_outside_rows"], 2)
        self.assertFalse(report["source_period_compatible"])

    def test_opt_in_grid_reports_incompatibility_without_rounding_or_quality_promotion(self):
        line="20240131 235959999,2000.123456,2000.234567,0\n"
        before=parse_tick(line,1,"authored")
        coarse=inspect_ticks([line],"authored",expected_period="2024-01",price_quantum="0.01")
        fine=inspect_ticks([line],"authored",expected_period="2024-01",price_quantum="0.000001")
        self.assertFalse(coarse["price_grid_compatible"])
        self.assertEqual((coarse["off_grid_quotes"],coarse["off_grid_rows"]),(2,1))
        self.assertTrue(fine["price_grid_compatible"])
        self.assertEqual(fine["min_spread"],"0.111111")
        self.assertEqual(parse_tick(line,1,"authored"),before)
        self.assertFalse(before.fresh)
        self.assertFalse(fine["financial_admission"])
        self.assertFalse(fine["coverage_complete"])
        self.assertFalse(fine["side_freshness_verified"])

    def test_opt_in_preflight_empty_invalid_or_reversed_never_compatible(self):
        for rows in ([],["bad\n"],["20240102 000000000,100,101,0\n","20240101 000000000,100,101,0\n"]):
            report=inspect_ticks(rows,"authored",expected_period="2024-01",price_quantum="0.01")
            self.assertFalse(report["source_period_compatible"])
            self.assertFalse(report["price_grid_compatible"])
        for bad in (0, "0", "-1", "NaN", "1"*129):
            with self.assertRaises(ContractError): inspect_ticks([],"authored",price_quantum=bad)

    def test_default_inspection_shape_and_bound_are_preserved(self):
        report=inspect_ticks(["20250101 000000000,100,101,0\n"],"authored")
        for key in ("source_period", "price_quantum", "price_grid_compatible", "diagnostic_scope"):
            self.assertNotIn(key,report)
        with self.assertRaises(ContractError):
            inspect_ticks(["20250101 000000000,100,101,0\n"]*2,"authored",max_rows=1,expected_period="2025-01",price_quantum="0.01")

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
