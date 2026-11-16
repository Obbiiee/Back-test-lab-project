"""Bounded synthetic tests for Exness 2024–2026 acquisition preparation."""
from pathlib import Path
import tempfile
import unittest
import zipfile

from contracts.primitives import ContractError
from ticks.exness_v2 import ExnessIngestion
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

    def test_official_four_column_shape_validates_and_enters_existing_v2_importer(self):
        path = self.root / "tick-history-fixture.csv"
        path.write_text(
            "Symbol,Timestamp,Bid,Ask\n"
            "EURUSD,2024-01-03 00:00:00.000Z,1.083210,1.083230\n"
            "EURUSD,2024-01-03 00:00:00.000Z,1.083220,1.083240\n",
            encoding="utf-8")
        report = validate_csv_month(path, original_symbol="EURUSD", year=2024, month=1)
        self.assertEqual((report["recordCount"], report["equalTimestampAdjacentRows"]), (2, 1))
        importer = ExnessIngestion(path, self.root / "v2-store", packing=(2, 1, 1))
        try:
            result = importer.run()
        finally:
            importer.builder.store.close()
        self.assertEqual(result["acceptedRows"], 2)
        self.assertEqual(result["provenance"], "UNVERIFIED")

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
        source = self.root / "source.zip"
        parquet = self.root / "ticks.parquet"
        manifest = self.root / "manifest.json"
        source.write_bytes(b"synthetic source")
        parquet.write_bytes(b"synthetic parquet payload")
        manifest.write_bytes(b"synthetic manifest")
        self.assertEqual(checkpoint.status(partition), "PENDING")
        checkpoint.mark_verified(partition, source_path=source, parquet_path=parquet,
                                 manifest_path=manifest)
        reloaded = Checkpoint(checkpoint_path)
        self.assertTrue(reloaded.verified(partition, source_path=source, parquet_path=parquet,
                                         manifest_path=manifest))
        source.write_bytes(b"changed source")
        self.assertFalse(reloaded.verified(partition, source_path=source, parquet_path=parquet,
                                           manifest_path=manifest))

    def test_zip_path_traversal_fails_closed_without_extraction(self):
        archive = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("../ticks.csv", "synthetic only")
        with self.assertRaises(ContractError):
            inspect_zip(archive)


if __name__ == "__main__":
    unittest.main()
