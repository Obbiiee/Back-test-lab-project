"""Compact Tick Parquet is the default of the local stack source builder and of the production provisioning environment. No database; synthetic only."""
import tempfile
import unittest
from pathlib import Path

from deploy.local.synthetic_source import ensure_source, source_environment
from deploy.site.app_provision import COMPACT_KEYS, managed_env, merge_env


class CompactDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="riksora-compact-default-")
        cls.compact = ensure_source(cls._tmp.name, 4096, log=lambda _m: None)                          # default format
        cls.parquet = ensure_source(cls._tmp.name, 4096, log=lambda _m: None, source_format="parquet")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_default_source_is_compact_only(self):
        info = self.compact
        self.assertEqual(info["format"], "compact")
        base = Path(self._tmp.name) / "4096-compact"
        self.assertTrue((base / "compact" / "compact.json").is_file())
        self.assertFalse((base / "reference-monthly").exists())                    # no Monthly Parquet copy is kept
        self.assertEqual(info["datasetId"], self.parquet["datasetId"])
        self.assertEqual(info["version"], self.parquet["version"])                  # same dataset identity either way

    def test_provisioned_environment_pins_the_compact_source(self):
        env = managed_env(self.compact)
        self.assertEqual(env["BTL_QA_SYNTHETIC_MONTHLY_ROOT"], self.compact["monthly"])
        self.assertEqual(env["BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256"], self.compact["manifestHash"])
        for key in COMPACT_KEYS:
            self.assertIn(key, env)
        self.assertEqual(env["BTL_PRODUCT_PROFILE"], "staging")
        self.assertEqual(env["BTL_ENTITLEMENT_ENFORCE"], "1")

    def test_parquet_environment_has_no_compact_pins(self):
        env = managed_env(self.parquet)
        for key in COMPACT_KEYS:
            self.assertNotIn(key, env)
        self.assertEqual(env, {k: v for k, v in env.items() if k in source_environment(self.parquet) or k.startswith("BTL_PRODUCT")
                               or k.startswith("BTL_ENTITLEMENT") or k == "BTL_RESEARCH_WORKERS"})

    def test_rerun_keeps_foreign_keys_and_drops_stale_compact_pins(self):
        existing = "\n".join(["BTL_TICK_CHECKPOINT_FORMAT=compact-v2", "BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256=" + "a" * 64,
                              "BTL_QA_SYNTHETIC_COMPACT_QUALITY_SHA256=" + "b" * 64, "BTL_QA_SYNTHETIC_MONTHLY_ROOT=/old/root", "NOT_A_PAIR"])
        merged = merge_env(existing, managed_env(self.parquet))                     # switching back to parquet: stale pins must vanish
        self.assertEqual(merged["BTL_TICK_CHECKPOINT_FORMAT"], "compact-v2")        # the checkpoint format set by v2_promote.sh survives
        self.assertNotIn("BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256", merged)
        self.assertEqual(merged["BTL_QA_SYNTHETIC_MONTHLY_ROOT"], self.parquet["monthly"])
        again = merge_env(existing, managed_env(self.compact))
        self.assertEqual(again["BTL_QA_SYNTHETIC_COMPACT_MANIFEST_SHA256"], self.compact["compactManifestHash"])


if __name__ == "__main__":
    unittest.main()
