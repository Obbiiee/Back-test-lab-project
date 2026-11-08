"""Operator-pinned Monthly Parquet roots; no Arrow or network required."""
import unittest
from pathlib import Path

from contracts.primitives import ContractError
from market_data.monthly_root import (monthly_object_path, parse_s3_monthly_root,
                                      pin_monthly_root)


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


if __name__ == "__main__":
    unittest.main()
