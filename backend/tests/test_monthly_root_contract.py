"""Operator-pinned Monthly Parquet roots; no Arrow or network required."""
import unittest
from pathlib import Path

from contracts.primitives import ContractError
from market_data.monthly_root import (monthly_object_path, monthly_root_from_environment,
                                      parse_s3_monthly_root, pin_monthly_root,
                                      s3_worker_environment)


class MonthlyRootContractTests(unittest.TestCase):
    def test_s3_root_is_canonical_and_requires_a_safe_nonempty_prefix(self):
        self.assertEqual(parse_s3_monthly_root("s3://btl-qa-data/monthly/ticks/"),
                         ("s3://btl-qa-data/monthly/ticks", "btl-qa-data", "monthly/ticks"))
        self.assertEqual(pin_monthly_root("s3://btl-qa-data/monthly/ticks"),
                         "s3://btl-qa-data/monthly/ticks")

    def test_rejects_unsafe_s3_authorities_and_paths(self):
        for root in (
            "https://btl-qa-data/monthly/ticks",
            "s3://user:secret@btl-qa-data/monthly/ticks",
            "s3://btl-qa-data:9000/monthly/ticks",
            "s3://btl-qa-data/monthly/../ticks",
            "s3://btl-qa-data/monthly//ticks",
            "s3://btl-qa-data/monthly/%2e%2e/ticks",
            "s3://btl-qa-data/monthly/ticks?versionId=secret",
            "s3://btl-qa-data/monthly/ticks#fragment",
            "s3://127.0.0.1/monthly/ticks",
        ):
            with self.subTest(root=root), self.assertRaises(ContractError):
                parse_s3_monthly_root(root)

    def test_local_root_must_be_absolute_and_is_canonicalized(self):
        directory = Path.cwd() / "monthly-test-root"
        self.assertEqual(pin_monthly_root(str(directory)), str(directory.resolve()))
        with self.assertRaises(ContractError):
            pin_monthly_root("relative/monthly")

    def test_manifest_children_stay_inside_local_or_pinned_s3_root(self):
        root = Path.cwd() / "monthly-test-root"
        self.assertEqual(monthly_object_path("s3://unused", "bucket/prefix",
                                             "2026-11/ticks.parquet"),
                         "bucket/prefix/2026-11/ticks.parquet")
        self.assertEqual(monthly_object_path(root.resolve(), "", "2026-11/ticks.parquet"),
                         str((root / "2026-11" / "ticks.parquet").resolve()))
        for relative in ("../escape.parquet", "2026-11/../../escape",
                         "2026-11//ticks.parquet", "/absolute.parquet",
                         "2026-11\\ticks.parquet", "2026-11/./ticks.parquet"):
            with self.subTest(relative=relative), self.assertRaises(ContractError):
                monthly_object_path("s3://unused", "bucket/prefix", relative)

        with self.assertRaises(ContractError):
            monthly_object_path(root.resolve(), "", "../escape.parquet")

    def test_worker_pin_is_all_or_nothing_and_canonicalizes_s3(self):
        values = ("1", "s3://btl-qa-data/monthly/ticks/", "synthetic:qa",
                  "a" * 64, "b" * 64)
        self.assertEqual(monthly_root_from_environment(values),
                         "s3://btl-qa-data/monthly/ticks")
        self.assertEqual(monthly_root_from_environment((None,) * 5), None)
        for invalid in (("1", "s3://bucket/../ticks", "synthetic:qa", "a" * 64, "b" * 64),
                        ("1", "relative", "synthetic:qa", "a" * 64, "b" * 64),
                        (None, "/qa/monthly", "synthetic:qa", "a" * 64, "b" * 64),
                        ("1", None, "synthetic:qa", "a" * 64, "b" * 64)):
            with self.subTest(values=invalid), self.assertRaises(ContractError):
                monthly_root_from_environment(invalid)

    def test_s3_worker_receives_only_standard_auth_and_region_settings(self):
        parent = {"AWS_ACCESS_KEY_ID": "qa-access", "AWS_SECRET_ACCESS_KEY": "qa-secret",
                  "AWS_SESSION_TOKEN": "qa-token", "AWS_REGION": "us-east-1",
                  "AWS_ENDPOINT_URL": "http://127.0.0.1:9000", "UNRELATED_SECRET": "hidden"}
        forwarded = s3_worker_environment("s3://btl-qa-data/monthly/ticks", parent)
        self.assertEqual(set(forwarded), {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                                         "AWS_SESSION_TOKEN", "AWS_REGION"})
        self.assertEqual(s3_worker_environment("C:\\qa\\monthly", parent), {})
        with self.assertRaises(ContractError):
            s3_worker_environment("s3://btl-qa-data/../outside", parent)


if __name__ == "__main__":
    unittest.main()
