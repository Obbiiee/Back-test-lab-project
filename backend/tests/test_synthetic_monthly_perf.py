"""Small determinism check for the synthetic-only Parquet performance fixture."""
import tempfile
import unittest
from pathlib import Path

from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
from tests.synthetic_monthly_perf import build_dataset


class SyntheticMonthlyPerformanceFixtureTests(unittest.TestCase):
    def test_generator_is_deterministic_and_writes_two_canonical_months(self):
        source_a, events_a = build_dataset(1024)
        source_b, events_b = build_dataset(1024)
        self.assertEqual(source_a, source_b)
        self.assertEqual(events_a, events_b)
        with tempfile.TemporaryDirectory(prefix="riksora-synth-perf-") as temporary:
            root = Path(temporary) / "ticks"
            published = write_monthly_parquet(root, iter(events_a), source_a,
                expected_version=events_a[0]["datasetVersion"], row_group_size=64)
            provider = MonthlyParquetProvider(root,
                expected_dataset_id=source_a["datasetId"],
                expected_dataset_version=events_a[0]["datasetVersion"],
                expected_manifest_hash=published["manifestHash"])
            self.assertEqual([entry["month"] for entry in published["files"]],
                             ["2020-01", "2020-02"])
            self.assertEqual(provider.verify_all()["eventCount"], len(events_a))
            self.assertTrue(all(event["quality"]["freshness"] == "CONFIRMED"
                                for event in provider.iter_range(
                                    int(source_a["range"]["startNs"]),
                                    int(source_a["range"]["endNs"]))))


if __name__ == "__main__":
    unittest.main()
