"""Opt-in Compact source wiring of the product's synthetic QA source (default OFF). Synthetic only; no database."""
import os
import tempfile
import unittest
from unittest.mock import patch

from cloud import research, worker
from contracts.primitives import ContractError
from market_data.compact_monthly_provider import CompactBackedMonthlyProvider
from market_data.monthly_parquet import MonthlyParquetProvider
from tests.benchmark_canonical_engine import _engine_only_financial_replay
from tests.test_compact_monthly_provider import build

GOLDEN_EVENT_HEAD = "a0bb4d57f1b01a958ee11f3161d92ad8d3cfeabf6c4c9b35b2e2e2471d8fb77b"


def env(root, f, manifest_hash, compact=None):
    values = {"BTL_QA_SYNTHETIC_MONTHLY_ENABLE": "1", "BTL_QA_SYNTHETIC_MONTHLY_ROOT": str(root),
              "BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID": f["manifest"]["datasetId"],
              "BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION": f["version"], "BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256": manifest_hash}
    if compact:
        values.update(BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256=compact[0], BTL_QA_SYNTHETIC_COMPACT_QUALITY_SHA256=compact[1])
    return values


class CompactSourceWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="riksora-compact-wiring-")
        cls.f = build(cls._tmp.name, 512, 128)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        research.close_operator_catalogs()
        self.addCleanup(research.close_operator_catalogs)

    def clean_environment(self, values):
        keep = {k: v for k, v in os.environ.items() if not k.startswith("BTL_QA_SYNTHETIC_")}
        return patch.dict(os.environ, {**keep, **values}, clear=True)

    def test_default_is_unchanged_monthly_parquet(self):
        f = self.f
        with self.clean_environment(env(f["ref_root"], f, f["reference_manifest"]["manifestHash"])):
            provider = research._synthetic_monthly_provider()
        self.assertIs(type(provider), MonthlyParquetProvider)

    def test_compact_pins_select_the_compact_backed_source_and_the_engine_result_is_identical(self):
        f = self.f
        values = env(f["compact_root"], f, f["adopted"]["manifestHash"], (f["compact"]["manifestHash"], f["quality_hash"]))
        with self.clean_environment(values):
            provider = research._synthetic_monthly_provider()
            self.assertIs(type(provider), CompactBackedMonthlyProvider)
            self.assertIs(research._synthetic_monthly_provider(), provider)           # same pin: cached, not rebuilt
            outcome = _engine_only_financial_replay(provider)["outcome"]
        self.assertEqual(outcome["eventHead"], GOLDEN_EVENT_HEAD)
        self.assertEqual(outcome["orderStatus"], "CLOSED")

    def test_half_configured_or_changed_compact_pins_are_refused(self):
        f = self.f
        half = env(f["compact_root"], f, f["adopted"]["manifestHash"])
        half["BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256"] = f["compact"]["manifestHash"]          # quality pin missing
        with self.clean_environment(half):
            with self.assertRaises(ContractError):
                research._synthetic_monthly_provider()
        good = env(f["compact_root"], f, f["adopted"]["manifestHash"], (f["compact"]["manifestHash"], f["quality_hash"]))
        with self.clean_environment(good):
            research._synthetic_monthly_provider()
        changed = env(f["compact_root"], f, f["adopted"]["manifestHash"], (f["compact"]["manifestHash"], "0" * 64))
        with self.clean_environment(changed):
            with self.assertRaises(ContractError) as raised:
                research._synthetic_monthly_provider()
        self.assertEqual(raised.exception.code, "SOURCE_PIN_CHANGED")

    def test_worker_environment_passes_both_pins_only_together(self):
        f = self.f
        values = env(f["compact_root"], f, f["adopted"]["manifestHash"], (f["compact"]["manifestHash"], f["quality_hash"]))
        with self.clean_environment(values):
            passed = worker._environment("postgresql://unused")
        self.assertEqual(passed["BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256"], f["compact"]["manifestHash"])
        self.assertEqual(passed["BTL_QA_SYNTHETIC_COMPACT_QUALITY_SHA256"], f["quality_hash"])
        half = {k: v for k, v in values.items() if k != "BTL_QA_SYNTHETIC_COMPACT_QUALITY_SHA256"}
        with self.clean_environment(half):
            with self.assertRaises(ContractError):
                worker._environment("postgresql://unused")
        with self.clean_environment(env(f["ref_root"], f, f["reference_manifest"]["manifestHash"])):
            self.assertNotIn("BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256", worker._environment("postgresql://unused"))


if __name__ == "__main__":
    unittest.main()
