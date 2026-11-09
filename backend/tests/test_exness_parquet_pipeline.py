"""Synthetic-only end-to-end tests for Exness CSV/ZIP monthly Parquet intake."""
from pathlib import Path
import json
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch
import zipfile

from contracts.primitives import ContractError
from market_data.monthly_parquet import MonthlyParquetProvider
from ticks.exness_monthly import INSTRUMENTS, partition_for
from ticks.exness_parquet_pipeline import (
    ExnessInventory, estimate_capacity, inspect_publication_recovery,
    measure_sample, process_csv_source, process_zip_member,
    recover_interrupted_publication, validate_rights_evidence,
)


class ExnessParquetPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.csv = self.root / "SYNTHETIC_ONLY_EURUSD.csv"
        self.csv.write_text(
            "Symbol,Timestamp,Bid,Ask\n"
            "EURUSD,2024-01-31 23:59:59.999Z,1.0832100,1.0832300\n"
            "EURUSD,2024-01-31 23:59:59.999Z,1.0832200,1.0832400\n"
            "EURUSD,2024-02-01 00:00:00.000Z,1.0832300,1.0832500\n",
            encoding="utf-8")
        self.output = self.root / "datasets" / "exness"
        self.inventory_path = self.output / "inventory.json"

    def tearDown(self):
        self.temp.cleanup()

    def run_fixture(self):
        return process_csv_source(self.csv, "EURUSD", self.output,
            inventory_path=self.inventory_path, synthetic_fixture=True, row_group_size=2)

    def test_csv_to_parquet_parity_random_seek_ties_and_logical_mapping(self):
        result = self.run_fixture()
        self.assertEqual((result["status"], result["observedTargetMonths"], result["completed"]),
                         ("COMPLETE", 2, 2))
        jan = partition_for("EURUSD", 2024, 1)
        feb = partition_for("EURUSD", 2024, 2)
        jan_root = next((self.output / "EURUSD" / "year=2024" / "month=01").glob("source=*"))
        feb_root = next((self.output / "EURUSD" / "year=2024" / "month=02").glob("source=*"))
        self.assertTrue((jan_root / "2024-01" / "ticks.parquet").is_file())
        self.assertTrue((feb_root / "2024-02" / "ticks.parquet").is_file())
        rows = json.loads(self.inventory_path.read_bytes())
        self.assertEqual(rows["partitionCount"], 544)
        self.assertEqual(rows["partitions"][ExnessInventory.key(jan)]["status"], "VERIFIED")
        self.assertEqual(rows["partitions"][ExnessInventory.key(feb)]["status"], "VERIFIED")
        self.assertEqual(rows["partitions"][ExnessInventory.key(jan)]["providerRelativePath"],
                         "2024-01/ticks.parquet")
        self.assertIn("source={sourceRevision}",
                      rows["partitions"][ExnessInventory.key(jan)]["logicalPathTemplate"])
        rows["partitions"][ExnessInventory.key(jan)].pop("logicalPathTemplate")
        rows["partitions"][ExnessInventory.key(jan)].pop("providerRelativePath")
        self.inventory_path.write_text(json.dumps(rows), encoding="utf-8")
        upgraded_inventory = ExnessInventory(self.inventory_path, rights_ready=True)
        self.assertEqual(upgraded_inventory.partitions[ExnessInventory.key(jan)]["providerRelativePath"],
                         "2024-01/ticks.parquet")

        jan_result = next(row for row in result["partitions"] if row["period"] == "2024-01")
        provider = MonthlyParquetProvider(jan_root,
            expected_dataset_id=jan_result["datasetId"],
            expected_dataset_version=jan_result["datasetVersion"],
            expected_manifest_hash=jan_result["manifestHash"])
        self.assertEqual(provider.verify_all()["eventCount"], 2)
        manifest = provider.manifest
        group_time = int(manifest["files"][0]["firstTimeNs"])
        events = list(provider.iter_range(group_time, group_time + 1))
        self.assertEqual([event["rawOrdinal"] for event in events], ["0", "1"])
        self.assertEqual([event["bid"] for event in events], ["1.08321", "1.08322"])
        self.assertEqual([event["ask"] for event in events], ["1.08323", "1.08324"])
        groups = list(provider.iter_groups(group_time, group_time + 1))
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["events"]), 2)

        feb_result = next(row for row in result["partitions"] if row["period"] == "2024-02")
        feb_provider = MonthlyParquetProvider(feb_root,
            expected_dataset_id=feb_result["datasetId"],
            expected_dataset_version=feb_result["datasetVersion"],
            expected_manifest_hash=feb_result["manifestHash"])
        feb_time = int(feb_provider.manifest["files"][0]["firstTimeNs"])
        self.assertEqual([row["rawOrdinal"] for row in
                          feb_provider.iter_range(feb_time, feb_time + 1)], ["2"])
        self.assertEqual(feb_provider.manifest["sourceManifest"]["rights"]["class"], "SYNTHETIC")

    def test_restart_skips_published_month_and_continues_after_failure(self):
        original = __import__("ticks.exness_parquet_pipeline", fromlist=["write_monthly_parquet"]).write_monthly_parquet
        calls = []

        def fail_second(root, *args, **kwargs):
            calls.append(Path(root).name)
            if "month=02" in str(root):
                raise OSError("synthetic crash before publication")
            return original(root, *args, **kwargs)

        with patch("ticks.exness_parquet_pipeline.write_monthly_parquet", fail_second):
            first = self.run_fixture()
        self.assertEqual(first["completed"], 1)
        self.assertEqual(next(row for row in first["partitions"] if row["period"] == "2024-02")["status"], "FAILED")
        jan_root = next((self.output / "EURUSD" / "year=2024" / "month=01").glob("source=*"))
        jan_manifest_sha = __import__("hashlib").sha256((jan_root / "manifest.json").read_bytes()).hexdigest()

        with patch("ticks.exness_parquet_pipeline.write_monthly_parquet", wraps=original) as writer:
            resumed = self.run_fixture()
        self.assertEqual(resumed["completed"], 2)
        self.assertEqual(writer.call_count, 1)
        self.assertEqual(__import__("hashlib").sha256((jan_root / "manifest.json").read_bytes()).hexdigest(),
                         jan_manifest_sha)
        self.assertTrue(all(row["status"] == "VERIFIED" for row in resumed["partitions"]))

    def test_zip_member_pipeline_and_provider_rights_gate(self):
        valid_result = self.run_fixture()
        self.assertEqual(valid_result["status"], "COMPLETE")
        archive = self.root / "SYNTHETIC_ONLY.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            output.writestr("folder/EURUSD.csv", self.csv.read_bytes())
        blocked_inventory = self.root / "blocked.json"
        blocked = process_zip_member(archive, "folder/EURUSD.csv", "EURUSD",
            self.root / "blocked-data", inventory_path=blocked_inventory)
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertFalse((self.root / "blocked-data").exists())
        self.assertEqual(json.loads(blocked_inventory.read_bytes())["partitionCount"], 544)
        self.assertTrue(all(row["status"] == "BLOCKED" for row in
                            json.loads(blocked_inventory.read_bytes())["partitions"].values()))

        # Losing a rights-evidence file blocks new acquisition, without
        # rewriting already verified evidence into a different data status.
        reopened = process_zip_member(archive, "folder/EURUSD.csv", "EURUSD",
            self.output, inventory_path=self.inventory_path)
        self.assertEqual(reopened["status"], "BLOCKED")
        inventory = json.loads(self.inventory_path.read_bytes())["partitions"]
        self.assertEqual(inventory[ExnessInventory.key(partition_for("EURUSD", 2024, 1))]["status"], "VERIFIED")
        self.assertEqual(inventory[ExnessInventory.key(partition_for("EURUSD", 2024, 2))]["status"], "VERIFIED")

        result = process_zip_member(archive, "folder/EURUSD.csv", "EURUSD",
            self.output, inventory_path=self.inventory_path, synthetic_fixture=True, row_group_size=2)
        self.assertEqual((result["status"], result["completed"], result["archiveMemberSha256"] != ""),
                         ("COMPLETE", 2, True))

    def test_crash_lock_recovery_is_explicit_and_preserves_staging(self):
        target = self.root / "publish-root"
        stage = self.root / ".publish-root.staging-test"
        stage.mkdir()
        lock = self.root / ".publish-root.publish.lock"
        lock.write_text("pid=2147483647\n", encoding="ascii")
        inspection = inspect_publication_recovery(target)
        self.assertEqual(inspection["status"], "STALE_LOCK_REQUIRES_EXPLICIT_RECOVERY")
        self.assertEqual(inspection["stagingPaths"], [str(stage)])
        with self.assertRaises(ContractError):
            recover_interrupted_publication(target)
        result = recover_interrupted_publication(target, confirm_stale_lock=True)
        self.assertEqual(result["status"], "RETRY_FROM_SOURCE_START")
        self.assertTrue(stage.is_dir())
        self.assertFalse(lock.exists())

    def test_corrupt_source_and_incomplete_rights_fail_closed(self):
        bad = self.root / "SYNTHETIC_ONLY_bad.csv"
        bad.write_text("Symbol,Timestamp,Bid,Ask\n"
                       "EURUSD,2024-01-02 00:00:01.000Z,1.1,1.2\n"
                       "EURUSD,2024-01-02 00:00:00.000Z,1.1,1.2\n", encoding="utf-8")
        result = process_csv_source(bad, "EURUSD", self.output,
            inventory_path=self.inventory_path, synthetic_fixture=True)
        self.assertEqual(result["status"], "FAILED")
        self.assertFalse((self.output / "EURUSD").exists())

        evidence = self.root / "rights-evidence.json"
        evidence.write_text(json.dumps({"schemaVersion": 1,
            "artifact": "RIKSORA-EXNESS-RIGHTS-EVIDENCE-1", "reviewer": "synthetic-test",
            "providerEntity": "synthetic fixture", "evidenceSha256": "a" * 64,
            "permissions": {"automatedAcquisition": True, "privateStorage": True,
                "commercialCompute": True, "derivedPresentation": True,
                "redistribution": False, "retention": True}}), encoding="utf-8")
        import hashlib
        with self.assertRaises(ContractError):
            validate_rights_evidence(evidence, hashlib.sha256(evidence.read_bytes()).hexdigest())

    def test_streaming_parser_memory_stays_bounded_and_capacity_requires_all_symbols(self):
        with self.csv.open("w", encoding="utf-8") as stream:
            stream.write("Symbol,Timestamp,Bid,Ask\n")
            for index in range(2000):
                stream.write(f"EURUSD,2024-01-02 00:{index // 60:02d}:{index % 60:02d}.000Z,1.1,1.2\n")
        from ticks.exness_parquet_pipeline import _source_rows
        tracemalloc.start()
        count = sum(1 for _ in _source_rows(self.csv, "EURUSD"))
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertEqual(count, 2000)
        self.assertLess(peak, 2 * 1024 * 1024)

        zip_path = self.root / "sample.zip"
        parquet_path = self.root / "sample.parquet"
        zip_path.write_bytes(b"synthetic zip sample")
        parquet_path.write_bytes(b"synthetic parquet sample")
        measured = measure_sample(zip_path, self.csv, parquet_path)
        samples = {symbol: {"originalSymbol": symbol, "sampleMonth": "2024-01", "measured": True,
            "zipBytes": measured["zipBytes"], "csvBytes": measured["csvBytes"],
            "parquetBytes": measured["parquetBytes"], "zipSha256": measured["zipSha256"],
            "csvSha256": measured["csvSha256"], "parquetSha256": measured["parquetSha256"]}
            for symbol in INSTRUMENTS}
        estimate = estimate_capacity(samples, available_bytes=10**9, reserve_bytes=10**6)
        self.assertEqual(estimate["status"], "PASS_ESTIMATE_ONLY")
        with self.assertRaises(ContractError):
            estimate_capacity({"EURUSD": samples["EURUSD"]}, available_bytes=10**9, reserve_bytes=10)


if __name__ == "__main__":
    unittest.main()
