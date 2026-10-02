import unittest
from datetime import datetime, timezone

from engine.market_data import import_csv

HEADER = "timestamp,open,high,low,close,volume\n"


def rows(*lines):
    return HEADER + "\n".join(lines) + "\n"


GOOD = rows(
    "2026-01-05 00:00:00,100,102,99,101,10",
    "2026-01-05 01:00:00,101,103,100,102,11",
    "2026-01-05 02:00:00,102,104,101,103,12",
)


class ImporterTests(unittest.TestCase):
    def test_valid_file_is_accepted(self):
        r = import_csv(GOOD, "xauusd", "1h", "UTC")
        self.assertTrue(r.ok)
        self.assertEqual(r.symbol, "XAUUSD")
        self.assertEqual(len(r.candles), 3)
        self.assertEqual(r.first_time, datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(r.gap_count, 0)
        self.assertEqual(r.errors, [])

    def test_invalid_ohlc_reports_row_number_and_rejects_everything(self):
        text = rows(
            "2026-01-05 00:00:00,100,102,99,101,10",
            "2026-01-05 01:00:00,101,100,99,102,11",  # high < close
        )
        r = import_csv(text, "XAUUSD", "1h")
        self.assertFalse(r.ok)
        self.assertEqual(r.candles, [])  # tidak ada data yang diterima diam-diam
        self.assertEqual(r.invalid_rows, 1)
        self.assertEqual(r.errors[0].row, 3)  # baris 1 = header

    def test_low_greater_than_high(self):
        r = import_csv(rows("2026-01-05 00:00:00,100,99,101,100,1"), "XAUUSD", "1h")
        self.assertFalse(r.ok)

    def test_non_numeric_and_negative_and_nan(self):
        for bad in ("abc,102,99,101", "100,102,99,-1", "100,nan,99,101", "0,102,99,101"):
            r = import_csv(rows(f"2026-01-05 00:00:00,{bad},1"), "XAUUSD", "1h")
            self.assertFalse(r.ok, bad)

    def test_bad_timestamp(self):
        r = import_csv(rows("kemarin,100,102,99,101,1"), "XAUUSD", "1h")
        self.assertFalse(r.ok)
        self.assertIn("format waktu", r.errors[0].message)

    def test_duplicate_timestamp(self):
        text = rows(
            "2026-01-05 00:00:00,100,102,99,101,1",
            "2026-01-05 00:00:00,100,102,99,101,1",
        )
        r = import_csv(text, "XAUUSD", "1h")
        self.assertFalse(r.ok)
        self.assertEqual(r.duplicate_rows, 1)

    def test_out_of_order_is_error_not_silently_sorted(self):
        text = rows(
            "2026-01-05 02:00:00,100,102,99,101,1",
            "2026-01-05 01:00:00,100,102,99,101,1",
        )
        r = import_csv(text, "XAUUSD", "1h")
        self.assertFalse(r.ok)
        self.assertEqual(r.out_of_order_rows, 1)
        self.assertEqual(r.candles, [])

    def test_missing_required_column(self):
        r = import_csv("timestamp,open,high,low\n2026-01-05 00:00:00,1,2,1\n", "XAUUSD", "1h")
        self.assertFalse(r.ok)
        self.assertEqual(r.errors[0].code, "missing_columns")

    def test_gap_is_warning_only(self):
        text = rows(
            "2026-01-05 00:00:00,100,102,99,101,1",
            "2026-01-05 01:00:00,100,102,99,101,1",
            "2026-01-05 05:00:00,100,102,99,101,1",  # 3 candle hilang
            "2026-01-05 06:00:00,100,102,99,101,1",
        )
        r = import_csv(text, "XAUUSD", "1h")
        self.assertTrue(r.ok)
        self.assertEqual(r.gap_count, 1)
        self.assertIn("3 candle", r.warnings[-1].message)

    def test_timeframe_mismatch_warning(self):
        r = import_csv(GOOD, "XAUUSD", "15m")
        self.assertTrue(r.ok)
        self.assertTrue(any(w.code == "timeframe_mismatch" for w in r.warnings))

    def test_timezone_conversion_jakarta(self):
        r = import_csv(rows("2026-01-05 07:00:00,100,102,99,101,1"), "XAUUSD", "1h", "Asia/Jakarta")
        self.assertEqual(r.candles[0].time, datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc))

    def test_timezone_conversion_new_york_winter(self):
        r = import_csv(rows("2026-01-05 09:00:00,100,102,99,101,1"), "XAUUSD", "1h", "America/New_York")
        self.assertEqual(r.candles[0].time, datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc))

    def test_explicit_offset_overrides_selected_timezone(self):
        r = import_csv(rows("2026-01-05T07:00:00+07:00,100,102,99,101,1"), "XAUUSD", "1h", "America/New_York")
        self.assertEqual(r.candles[0].time, datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc))

    def test_semicolon_delimiter_and_metatrader_dates(self):
        text = "timestamp;open;high;low;close\n2026.01.05 00:00;100;102;99;101\n"
        r = import_csv(text, "XAUUSD", "1h")
        self.assertTrue(r.ok)

    def test_bad_parameters(self):
        self.assertFalse(import_csv(GOOD, "", "1h").ok)
        self.assertFalse(import_csv(GOOD, "XAUUSD", "2h").ok)
        self.assertFalse(import_csv(GOOD, "XAUUSD", "1h", "Mars/Olympus").ok)
        self.assertFalse(import_csv("", "XAUUSD", "1h").ok)

    def test_optional_bid_ask_spread(self):
        text = "timestamp,open,high,low,close,bid,ask,spread\n2026-01-05 00:00:00,100,102,99,101,100.9,101.1,0.2\n"
        r = import_csv(text, "XAUUSD", "1h")
        self.assertTrue(r.ok)
        self.assertEqual(r.candles[0].spread, 0.2)
        bad = "timestamp,open,high,low,close,bid,ask\n2026-01-05 00:00:00,100,102,99,101,101.5,101.1\n"
        self.assertFalse(import_csv(bad, "XAUUSD", "1h").ok)


if __name__ == "__main__":
    unittest.main()
