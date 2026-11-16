import tempfile
import unittest
from pathlib import Path

from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
from tests.benchmark_canonical_engine import (_engine_only_financial_replay,
    recommended_financial_chunk_size)
from tests.synthetic_financial_monthly import (build_manifest, fixture_identity,
    iter_events)
from ticks.contracts import TickManifest


class SyntheticFinancialMonthlyTests(unittest.TestCase):
    def test_financial_benchmark_selects_bounded_chunk_size_for_scale(self):
        self.assertEqual(recommended_financial_chunk_size(262_144), 256)
        self.assertEqual(recommended_financial_chunk_size(263_168), 512)
        self.assertEqual(recommended_financial_chunk_size(1_048_576), 512)

    def test_streaming_manifest_supports_more_than_legacy_262144_raw_rows(self):
        # The previous generator packed <=2,048 rows into each one-megabyte
        # canonical source artifact and capped the source list at 128. The new
        # JSONL member hash and bounded 256-event canonical chunks do not pack history
        # into one command/object or relax the canonical node budget.
        count = 263_168
        manifest, member_hash, _ = build_manifest(count)
        checked = TickManifest.from_wire(manifest)
        self.assertEqual(sum(chunk["eventCount"] for chunk in manifest["chunks"]), count)
        self.assertEqual(len(manifest["sources"]), 1)
        self.assertEqual(checked.wire["sources"][0]["memberHash"], member_hash)
        self.assertGreater(int(manifest["range"]["endNs"]) - int(manifest["range"]["startNs"]),
                           30 * 24 * 60 * 60 * 1_000_000_000)
        self.assertLess(len(checked._bytes), 1_048_576)
        first = next(iter_events(count, manifest))
        self.assertEqual(first["rawOrdinal"], "0")
        self.assertEqual(first["datasetVersion"], checked.version)
        self.assertTrue(fixture_identity(count, manifest)["label"].startswith("SYNTHETIC"))

    def test_max_bounded_streaming_manifest_fits_frozen_canonical_node_budget(self):
        # 1,048,576 rows are represented by 2,048 bounded 512-event chunks;
        # no raw history is embedded in a single canonical artifact and the
        # frozen normalizer budget remains unchanged.
        count = 1_048_576
        manifest, member_hash, _ = build_manifest(count, chunk_size=512)
        checked = TickManifest.from_wire(manifest)
        self.assertEqual(len(checked.wire["chunks"]), 2_048)
        self.assertEqual(sum(chunk["eventCount"] for chunk in checked.wire["chunks"]), count)
        self.assertLess(len(checked._bytes), 1_048_576)
        self.assertEqual(checked.version,
            "b66fec5060ce462785cc60d9eeffe77b9559f204913f980cb37ccb2199f868d3")
        self.assertEqual(member_hash,
            "8b99727e98aee97ba7d4bf74580531ac887faf6293b541447c3339d680a01a7f")

    def test_canonical_monthly_parquet_financial_lifecycle_closes_trade(self):
        count = 512
        source_manifest, member_hash, _ = build_manifest(count)
        version = TickManifest.from_wire(source_manifest).version
        with tempfile.TemporaryDirectory(prefix="riksora-financial-test-") as directory:
            root = Path(directory) / "monthly"
            parquet_manifest = write_monthly_parquet(root,
                iter_events(count, source_manifest), source_manifest,
                expected_version=version, row_group_size=128)
            self.assertEqual(version,
                "0509fd1f3402f53c669c85087e64dca75dd75ddeccf18efc08c142c5980901e7")
            provider = MonthlyParquetProvider(root,
                expected_dataset_id=source_manifest["datasetId"],
                expected_dataset_version=version,
                expected_manifest_hash=parquet_manifest["manifestHash"])
            result = _engine_only_financial_replay(provider)
        outcome = result["outcome"]
        self.assertEqual(outcome["orderStatus"], "CLOSED")
        self.assertEqual(outcome["fillKinds"], ["ENTRY_FILL", "EXIT_FILL"])
        self.assertEqual(outcome["closedTrades"], 1)
        self.assertNotEqual(outcome["realizedGross"], "0")
        self.assertEqual(len(member_hash), 64)
        self.assertEqual(result["replay"]["ticksProcessed"], count)
        self.assertEqual(outcome["eventHead"],
            "a0bb4d57f1b01a958ee11f3161d92ad8d3cfeabf6c4c9b35b2e2e2471d8fb77b")
        self.assertEqual(outcome["financialStateHash"],
            "93312dc81a86f62a8ff1c722b84da9cbe30f1165fb64b0210e35ffa896e87fc3")
        self.assertEqual(outcome["financialReceiptEvidenceHash"],
            "56b6a392fc4b14592e88c25dce31f245429ca9633329766f3ef8732f4644213b")
        self.assertEqual(outcome["analyticsHash"],
            "6ee75c65d76be7bb89f921c888717af1d0e92e76a618e1a06c966fef40d39c22")


if __name__ == "__main__":
    unittest.main()
