"""Bounded synthetic tests for Exness 2024–2026 acquisition preparation."""
from pathlib import Path
import tempfile
import unittest
import zipfile

from contracts.primitives import ContractError
from ticks.exness_monthly import (
    Checkpoint, INSTRUMENTS, inspect_zip, partition_for, plan, required_partitions,
    validate_csv_month,
)


class ExnessMonthlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_target_is_exactly_544_month_instrument_partitions(self):
        rows = required_partitions()
        self.assertEqual(len(INSTRUMENTS), 16)
        self.assertEqual(len(rows), 544)
        self.assertEqual(plan()["partitionCount"], 544)
        self.assertEqual(plan()["acquisition"], "BLOCKED_RIGHTS_AND_SOURCE_ACCESS_UNVERIFIED")
        self.assertEqual((rows[0].original_symbol, rows[0].period), ("AUDUSD", "2024-01"))
        self.assertEqual((rows[-1].original_symbol, rows[-1].period), ("XAUUSD", "2026-10"))
        gold = partition_for("XAUUSD", 2025, 6)
        self.assertEqual(gold.relative_path.as_posix(),
                         "datasets/exness/XAUUSD/year=2025/month=06/ticks.parquet")

    def test_account_suffix_never_aliases_canonical_symbol(self):
        with self.assertRaises(ContractError):
            partition_for("XAUUSDm", 2025, 6)

    def test_csv_preserves_ties_and_exact_duplicates_and_reports_observed_only(self):
        path = self.root / "fixture.csv"
        path.write_text(
            "Exness,Symbol,Timestamp,Bid,Ask\n"
            "exness,EURUSD,2024-01-31 23:59:59.000Z,1.00001,1.00003\n"
            "exness,EURUSD,2024-01-31 23:59:59.000Z,1.00001,1.00003\n"
            "exness,EURUSD,2024-01-31 23:59:59.000Z,1.00002,1.00004\n",
            encoding="utf-8")
        report = validate_csv_month(path, original_symbol="EURUSD", year=2024, month=1)
        self.assertEqual(report["recordCount"], 3)
        self.assertEqual(report["equalTimestampAdjacentRows"], 2)
        self.assertEqual(report["exactDuplicateAdjacentRowsPreserved"], 1)
        self.assertEqual(report["ties"], "UNTRUSTED")
        self.assertEqual(report["coverage"], "OBSERVED_ROWS_ONLY_NOT_COMPLETE_MONTH")
        self.assertEqual(report["rights"], "UNKNOWN")

    def test_csv_rejects_symbol_spoof_month_overflow_and_reversal(self):
        cases = (
            "exness,XAUUSDm,2024-01-01 00:00:00.000Z,1,2",
            "exness,EURUSD,2024-02-01 00:00:00.000Z,1,2",
            "exness,EURUSD,2024-01-02 00:00:00.000Z,1,2\n"
            "exness,EURUSD,2024-01-01 00:00:00.000Z,1,2",
        )
        for body in cases:
            with self.subTest(body=body):
                path = self.root / "bad.csv"
                path.write_text("Exness,Symbol,Timestamp,Bid,Ask\n" + body + "\n", encoding="utf-8")
                with self.assertRaises(ContractError):
                    validate_csv_month(path, original_symbol="EURUSD", year=2024, month=1)

    def test_zip_metadata_inspection_and_checkpoint_are_resumable(self):
        archive = self.root / "sample.zip"
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("EURUSD.csv", "synthetic only")
        inspected = inspect_zip(archive)
        self.assertEqual(len(inspected["sha256"]), 64)
        self.assertTrue(inspected["members"][0]["isCsv"])
        partition = partition_for("EURUSD", 2024, 1)
        checkpoint_path = self.root / "checkpoint.json"
        checkpoint = Checkpoint(checkpoint_path)
        hashes = {key: "a" * 64 for key in ("source_sha256", "parquet_sha256", "manifest_sha256")}
        self.assertEqual(checkpoint.status(partition), "PENDING")
        checkpoint.mark_verified(partition, **hashes)
        reloaded = Checkpoint(checkpoint_path)
        self.assertTrue(reloaded.verified(partition, **hashes))
        self.assertFalse(reloaded.verified(partition, source_sha256="b" * 64,
                                            parquet_sha256="a" * 64,
                                            manifest_sha256="a" * 64))

    def test_zip_path_traversal_fails_closed_without_extraction(self):
        archive = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("../ticks.csv", "synthetic only")
        with self.assertRaises(ContractError):
            inspect_zip(archive)


if __name__ == "__main__":
    unittest.main()
