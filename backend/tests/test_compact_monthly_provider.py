"""Compact-backed monthly source: the unchanged canonical engine over plain Compact files equals the Monthly Parquet reference.

Synthetic data only (SYNTHETIC / TEST ONLY). Temporary directories; nothing persists.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from contracts.primitives import ContractError
from market_data.compact_monthly_provider import (CompactBackedMonthlyProvider, admission_record, adopt_monthly_manifest,
                                                 write_adopted_manifest)
from market_data.compact_tick import write_compact
from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
from tests.benchmark_canonical_engine import _engine_only_financial_replay
from tests.synthetic_financial_monthly import build_manifest, iter_events
from ticks.contracts import TickManifest


def build(directory, count, row_group_size):
    manifest, _member, quality_hash = build_manifest(count)
    version = TickManifest.from_wire(manifest).version
    base = Path(directory)
    ref_root, compact_root = base / "monthly", base / "compact"
    reference = write_monthly_parquet(ref_root, iter_events(count, manifest), manifest, expected_version=version,
                                      row_group_size=row_group_size)
    compact = write_compact(compact_root, iter_events(count, manifest), parent=dict(datasetId=manifest["datasetId"], datasetVersion=version),
                            scale=2, evidence_class="SYNTHETIC_CONTRACT_ONLY", rights={"class": "SYNTHETIC", "evidenceHash": None})
    reference_manifest = json.loads((ref_root / "manifest.json").read_bytes())
    adopted = write_adopted_manifest(compact_root, reference_manifest, compact)
    ref = MonthlyParquetProvider(ref_root, expected_dataset_id=manifest["datasetId"], expected_dataset_version=version,
                                 expected_manifest_hash=reference["manifestHash"])
    comp = CompactBackedMonthlyProvider(compact_root, admission=admission_record(quality_hash), expected_manifest_hash=adopted["manifestHash"],
                                        expected_compact_manifest_hash=compact["manifestHash"], expected_dataset_id=manifest["datasetId"],
                                        expected_dataset_version=version)
    return dict(manifest=manifest, version=version, ref=ref, comp=comp, quality_hash=quality_hash, compact=compact, adopted=adopted,
                reference_manifest=reference_manifest, compact_root=compact_root, ref_root=ref_root)


class CompactBackedMonthlyProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="riksora-compact-monthly-")
        cls.f = build(cls._tmp.name, 4096, 512)            # 4,096 one-minute ticks: crosses the 2020-01 / 2020-02 boundary

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_dataset_identity_and_canonical_authority_are_unchanged(self):
        f = self.f
        self.assertEqual(f["comp"].dataset_version, f["ref"].dataset_version)
        self.assertEqual(f["comp"].describe(f["comp"].dataset_id, f["comp"].dataset_version),
                         f["ref"].describe(f["ref"].dataset_id, f["ref"].dataset_version))
        canonical = {k: v for k, v in f["adopted"].items() if k not in ("files", "manifestHash")}
        self.assertEqual(canonical, {k: v for k, v in f["reference_manifest"].items() if k not in ("files", "manifestHash")})
        self.assertEqual([e["rowGroups"] for e in f["adopted"]["files"]], [e["rowGroups"] for e in f["reference_manifest"]["files"]])

    def test_every_range_group_page_and_window_equals_the_reference(self):
        f, ref, comp = self.f, self.f["ref"], self.f["comp"]
        first = int(f["manifest"]["range"]["startNs"]); end = int(f["manifest"]["range"]["endNs"])
        self.assertEqual(list(comp.iter_range(first, end)), list(ref.iter_range(first, end)))
        mid, span = first + (end - first) // 3, (end - first) // 5
        self.assertEqual(list(comp.iter_range(mid, mid + span)), list(ref.iter_range(mid, mid + span)))
        self.assertEqual(list(comp.iter_groups(mid, mid + span)), list(ref.iter_groups(mid, mid + span)))
        token_a = token_b = None
        pages = 0
        while True:
            pa = ref.read_page(ref.dataset_id, ref.dataset_version, token_a, 64)
            pb = comp.read_page(comp.dataset_id, comp.dataset_version, token_b, 64)
            self.assertEqual(pa, pb)
            pages += 1
            token_a, token_b = pa["nextToken"], pb["nextToken"]
            if pa["endOfDataset"]:
                break
        self.assertEqual(pages, 4096 // 64)
        self.assertEqual(ref.read_page(ref.dataset_id, ref.dataset_version, None, 64, start_index=1000),
                         comp.read_page(comp.dataset_id, comp.dataset_version, None, 64, start_index=1000))
        for through in (first, mid, end - 1):
            self.assertEqual(comp.read_revealed_window(through, 32), ref.read_revealed_window(through, 32))
        self.assertEqual(comp.first_time_for_month("2020-02"), ref.first_time_for_month("2020-02"))
        self.assertEqual(comp.verify_all()["eventCount"], ref.verify_all()["eventCount"])

    def test_a_modified_compact_file_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="riksora-compact-tamper-") as directory:
            f = build(directory, 512, 128)
            target = next(Path(f["compact_root"]).glob("*/ticks.parquet"))
            data = bytearray(target.read_bytes())
            data[len(data) // 2] ^= 0xFF
            target.write_bytes(bytes(data))
            with self.assertRaises(ContractError):
                f["comp"].verify_all()

    def test_a_wrong_admission_hint_cannot_pass_because_canonical_hashes_decide(self):
        f = self.f
        bad = CompactBackedMonthlyProvider(f["compact_root"], admission=admission_record("0" * 64), expected_manifest_hash=f["adopted"]["manifestHash"],
                                           expected_compact_manifest_hash=f["compact"]["manifestHash"])
        with self.assertRaises(ContractError) as raised:
            list(bad.iter_range(int(f["manifest"]["range"]["startNs"]), int(f["manifest"]["range"]["endNs"])))
        self.assertEqual(raised.exception.code, "CHILD_HASH_MISMATCH")

    def test_wrong_pins_and_a_foreign_compact_parent_are_refused(self):
        f = self.f
        with self.assertRaises(ContractError):
            CompactBackedMonthlyProvider(f["compact_root"], admission=admission_record(f["quality_hash"]), expected_manifest_hash="1" * 64,
                                         expected_compact_manifest_hash=f["compact"]["manifestHash"])
        with self.assertRaises(ContractError):
            CompactBackedMonthlyProvider(f["compact_root"], admission=admission_record(f["quality_hash"]), expected_manifest_hash=f["adopted"]["manifestHash"],
                                         expected_compact_manifest_hash="2" * 64)
        with tempfile.TemporaryDirectory(prefix="riksora-compact-foreign-") as directory:
            other = build(directory, 512, 128)
            foreign_root = Path(directory) / "foreign"
            foreign = write_compact(foreign_root, iter_events(512, other["manifest"]), parent=dict(datasetId=other["manifest"]["datasetId"], datasetVersion="3" * 64),
                                    scale=2, evidence_class="SYNTHETIC_CONTRACT_ONLY", rights={"class": "SYNTHETIC", "evidenceHash": None})
            adopted = write_adopted_manifest(foreign_root, other["reference_manifest"], foreign)
            with self.assertRaises(ContractError) as raised:
                CompactBackedMonthlyProvider(foreign_root, admission=admission_record(other["quality_hash"]), expected_manifest_hash=adopted["manifestHash"],
                                             expected_compact_manifest_hash=foreign["manifestHash"])
            self.assertEqual(raised.exception.code, "IDENTITY_CONFLICT")

    def test_unchanged_engine_over_compact_files_gives_the_golden_financial_hashes(self):
        with tempfile.TemporaryDirectory(prefix="riksora-compact-engine-") as directory:
            f = build(directory, 512, 128)
            self.assertEqual(f["version"], "0509fd1f3402f53c669c85087e64dca75dd75ddeccf18efc08c142c5980901e7")
            reference = _engine_only_financial_replay(f["ref"])["outcome"]
            compact = _engine_only_financial_replay(f["comp"])["outcome"]
        self.assertEqual(compact, reference)
        self.assertEqual(compact["orderStatus"], "CLOSED")
        self.assertEqual(compact["fillKinds"], ["ENTRY_FILL", "EXIT_FILL"])
        self.assertEqual(compact["eventHead"], "a0bb4d57f1b01a958ee11f3161d92ad8d3cfeabf6c4c9b35b2e2e2471d8fb77b")
        self.assertEqual(compact["financialStateHash"], "93312dc81a86f62a8ff1c722b84da9cbe30f1165fb64b0210e35ffa896e87fc3")
        self.assertEqual(compact["financialReceiptEvidenceHash"], "56b6a392fc4b14592e88c25dce31f245429ca9633329766f3ef8732f4644213b")
        self.assertEqual(compact["analyticsHash"], "6ee75c65d76be7bb89f921c888717af1d0e92e76a618e1a06c966fef40d39c22")

    def test_compact_files_alone_are_enough_once_the_monthly_parquet_reference_is_deleted(self):
        with tempfile.TemporaryDirectory(prefix="riksora-compact-only-") as directory:
            f = build(directory, 512, 128)
            shutil.rmtree(f["ref_root"])                                   # no Monthly Parquet copy exists any more
            self.assertFalse(f["ref_root"].exists())
            self.assertEqual(sorted(p.name for p in Path(f["compact_root"]).iterdir() if p.is_file()), ["compact.json", "manifest.json"])
            self.assertEqual(f["comp"].verify_all()["status"], "PASS")
            outcome = _engine_only_financial_replay(f["comp"])["outcome"]
        self.assertEqual(outcome["eventHead"], "a0bb4d57f1b01a958ee11f3161d92ad8d3cfeabf6c4c9b35b2e2e2471d8fb77b")
        self.assertEqual(outcome["financialStateHash"], "93312dc81a86f62a8ff1c722b84da9cbe30f1165fb64b0210e35ffa896e87fc3")


if __name__ == "__main__":
    unittest.main()
