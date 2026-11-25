"""The `visual` synthetic demo profile: deterministic, candle-like, canonical contracts valid. Synthetic only; temporary files."""
import statistics
import tempfile
import unittest
from pathlib import Path

from deploy.local import visual_source as v
from execution.research_fixture import START_NS
from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
from ticks.contracts import TickManifest


class VisualSourceTests(unittest.TestCase):
    def test_same_seed_gives_the_same_ticks_and_dataset_version(self):
        a, member_a, _ = v.build_manifest(2048)
        b, member_b, _ = v.build_manifest(2048)
        self.assertEqual(a, b)
        self.assertEqual(member_a, member_b)
        self.assertNotEqual(TickManifest.from_wire(a).version, TickManifest.from_wire(v.build_manifest(2048, seed=7)[0]).version)

    def test_ticks_look_like_candles_and_stay_bounded(self):
        rows = list(v._rows(60_000, v.DEFAULT_SEED, START_NS, v.STEP_NS))
        bid = [float(r["bid"]) for r in rows]
        spreads = [float(r["ask"]) - float(r["bid"]) for r in rows]
        self.assertTrue(1500 <= min(bid) and max(bid) <= 2500)
        self.assertTrue(0.10 <= min(spreads) and max(spreads) <= 0.60)
        self.assertTrue(all(int(rows[i + 1]["timeNs"]) - int(rows[i]["timeNs"]) == v.STEP_NS for i in range(100)))
        candles = [bid[i:i + 5] for i in range(0, 5000, 5)]              # 5 ticks = one 1-minute candle
        with_body = sum(1 for c in candles if c[0] != c[-1])
        self.assertGreater(with_body / len(candles), 0.9)                  # the fixture had 0% (one tick per candle)
        self.assertGreater(statistics.median(max(c) - min(c) for c in candles), 0.1)

    def test_canonical_manifest_and_monthly_parquet_round_trip(self):
        count = 1024
        manifest, _member, _quality = v.build_manifest(count)
        version = TickManifest.from_wire(manifest).version
        self.assertEqual(manifest["datasetId"], v.DATASET_ID)
        self.assertEqual(manifest["rights"], {"class": "SYNTHETIC", "evidenceHash": None})
        self.assertEqual(manifest["evidenceClass"], "SYNTHETIC_CONTRACT_ONLY")
        with tempfile.TemporaryDirectory(prefix="riksora-visual-") as directory:
            root = Path(directory) / "monthly"
            written = write_monthly_parquet(root, v.iter_events(count, manifest), manifest, expected_version=version, row_group_size=256)
            provider = MonthlyParquetProvider(root, expected_dataset_id=v.DATASET_ID, expected_dataset_version=version,
                                              expected_manifest_hash=written["manifestHash"])
            self.assertEqual(provider.verify_all()["eventCount"], count)
            first = next(provider.iter_range(START_NS, START_NS + count * v.STEP_NS))
        self.assertEqual(first["rawOrdinal"], "0")
        self.assertEqual(first["timeNs"], str(START_NS))

    def test_bounds_are_enforced(self):
        with self.assertRaises(ValueError):
            v.build_manifest(1000)                       # not a multiple of the chunk size
        with self.assertRaises(ValueError):
            v.build_manifest(2_000_000)


if __name__ == "__main__":
    unittest.main()
