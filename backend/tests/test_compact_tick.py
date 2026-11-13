"""Synthetic-only regression for the derived compact tick projection."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

import numpy as np

from contracts.primitives import ContractError
from market_data.compact_tick import CompactTickReader, write_compact
from ticks.provider import SyntheticTickProvider

JAN_LAST = 1_706_745_599_999_999_990
FEB_FIRST = 1_706_745_600_000_000_000
PARENT_VERSION = "ab" * 32


def ev(ordinal, time_ns, bid, ask):
    return dict(timeNs=str(time_ns), bid=bid, ask=ask, rawOrdinal=str(ordinal))


def sample_events():
    base = 1_700_000_000_000_000_000
    out, ordinal = [], 0
    # ties (3 and 4 ticks) placed so that small blocks must split inside a timestamp group
    for step, copies in ((0, 1), (1, 3), (2, 1), (3, 4), (4, 2), (5, 1)):
        for k in range(copies):
            out.append(ev(ordinal, base + step * 1_000_000, f"1.{100 + ordinal}", f"1.{102 + ordinal}"))
            ordinal += 1
    return out


class CompactTickTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "compact"
        self.parent = dict(datasetId="synthetic:test", datasetVersion=PARENT_VERSION)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, events, **kwargs):
        kwargs.setdefault("block_rows", 3)
        kwargs.setdefault("evidence_class", "SYNTHETIC_CONTRACT_ONLY")
        kwargs.setdefault("rights", dict({"class": "SYNTHETIC"}, evidenceHash=None))
        return write_compact(self.root, iter(events), parent=self.parent, scale=5, **kwargs)

    def test_round_trip_is_exact_and_ordered(self):
        events = sample_events()
        manifest = self.write(events)
        reader = CompactTickReader(self.root, expected_manifest_hash=manifest["manifestHash"])
        data = reader.read_range(0, 2**62)
        self.assertEqual(len(data["ts_ns"]), len(events))
        self.assertEqual([int(t) for t in data["ts_ns"]], [int(e["timeNs"]) for e in events])
        self.assertEqual([int(o) for o in data["ordinal"]], [int(e["rawOrdinal"]) for e in events])
        self.assertEqual([reader.price(v) for v in data["bid"]], [Decimal(e["bid"]) for e in events])
        self.assertEqual([reader.price(v) for v in data["ask"]], [Decimal(e["ask"]) for e in events])
        self.assertEqual(reader.verify_all(deep=True)["eventCount"], len(events))
        self.assertEqual(manifest["parent"]["datasetVersion"], PARENT_VERSION)
        self.assertIs(manifest["authoritative"], False)
        self.assertEqual(manifest["quality"]["equalTimestampTicks"], 6)

    def test_timestamp_groups_are_atomic_across_row_groups(self):
        events = sample_events()
        self.write(events, block_rows=2)
        reader = CompactTickReader(self.root)
        seen = set()
        for block in reader.iter_blocks(0, 2**62, atomic=True):
            stamps = set(int(t) for t in block["ts_ns"])
            self.assertFalse(stamps & seen, "a timestamp group was split across blocks")
            seen |= stamps
        groups = list(reader.iter_groups(0, 2**62))
        self.assertEqual([len(g[1]["ts_ns"]) for g in groups], [1, 3, 1, 4, 2, 1])
        self.assertEqual(reader.manifest["quality"]["maxGroupSize"], 4)
        self.assertEqual(reader.manifest["groupCount"], 6)

    def test_range_is_end_exclusive_and_reveals_nothing_later(self):
        events = sample_events()
        self.write(events)
        reader = CompactTickReader(self.root)
        cut = int(events[5]["timeNs"])
        data = reader.read_range(0, cut)
        self.assertTrue(len(data["ts_ns"]) and int(data["ts_ns"].max()) < cut)
        later = [g for g in reader.iter_groups(0, cut)]
        self.assertTrue(all(ts < cut for ts, _ in later))
        self.assertEqual(len(reader.read_range(cut, cut)["ts_ns"]), 0)

    def test_crossed_quotes_are_flagged_not_repaired(self):
        events = [ev(0, 10, "1.10000", "1.10010"), ev(1, 11, "1.10020", "1.10010"), ev(2, 12, "1.10000", "1.10000")]
        self.write(events)
        reader = CompactTickReader(self.root)
        data = reader.read_range(0, 100)
        self.assertEqual([bool(x) for x in data["is_crossed"]], [False, True, False])
        self.assertEqual(reader.price(data["bid"][1]), Decimal("1.1002"))
        self.assertEqual(reader.manifest["quality"]["crossedQuotes"], 1)
        reader.verify_all(deep=True)

    def test_month_boundary_makes_one_file_per_utc_month(self):
        events = [ev(0, JAN_LAST - 2, "1.001", "1.003"), ev(1, JAN_LAST, "1.002", "1.004"),
                  ev(2, JAN_LAST, "1.003", "1.005"), ev(3, FEB_FIRST, "1.004", "1.006")]
        manifest = self.write(events)
        self.assertEqual([f["month"] for f in manifest["files"]], ["2024-01", "2024-02"])
        reader = CompactTickReader(self.root)
        self.assertEqual(len(reader.read_range(FEB_FIRST, FEB_FIRST + 1)["ts_ns"]), 1)
        self.assertEqual(len(reader.read_range(JAN_LAST - 5, FEB_FIRST + 1)["ts_ns"]), 4)
        reader.verify_all(deep=True)

    def test_tamper_and_pin_are_detected(self):
        manifest = self.write(sample_events())
        reader = CompactTickReader(self.root)
        path = self.root / manifest["files"][0]["path"]
        raw = bytearray(path.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        path.write_bytes(bytes(raw))
        with self.assertRaises(ContractError) as caught:
            reader.verify_all()
        self.assertEqual(caught.exception.code, "CHILD_HASH_MISMATCH")
        with self.assertRaises(ContractError):
            CompactTickReader(self.root, expected_manifest_hash="00" * 32)
        meta = self.root / "compact.json"
        meta.write_bytes(meta.read_bytes().replace(b'"authoritative":false', b'"authoritative":true'))
        with self.assertRaises(ContractError):
            CompactTickReader(self.root)

    def test_writer_refuses_bad_input_and_never_overwrites(self):
        bad = {
            "order": [ev(0, 20, "1.1", "1.2"), ev(1, 10, "1.1", "1.2")],
            "ordinal": [ev(0, 10, "1.1", "1.2"), ev(0, 11, "1.1", "1.2")],
            "precision": [ev(0, 10, "1.1234567", "1.2")],
            "nonpositive": [ev(0, 10, "0", "1.2")],
            "malformed": [ev(0, 10, "1e-3", "1.2")],
        }
        for name, events in bad.items():
            with self.subTest(name):
                with self.assertRaises(ContractError):
                    write_compact(Path(self.tmp.name) / f"bad-{name}", iter(events), parent=self.parent,
                                  scale=5, evidence_class="SYNTHETIC_CONTRACT_ONLY",
                                  rights=dict({"class": "SYNTHETIC"}, evidenceHash=None))
                self.assertFalse((Path(self.tmp.name) / f"bad-{name}").exists())
        self.write(sample_events())
        with self.assertRaises(ContractError) as caught:
            self.write(sample_events())
        self.assertEqual(caught.exception.code, "IMMUTABLE_ALREADY_PUBLISHED")

    def test_synthetic_label_requires_synthetic_rights(self):
        with self.assertRaises(ContractError):
            write_compact(self.root, iter(sample_events()), parent=self.parent, scale=5,
                          evidence_class="SYNTHETIC_CONTRACT_ONLY")

    def test_parity_with_authoritative_synthetic_provider(self):
        raw = [dict(ordinal="0", timeNs=str(JAN_LAST - 2), bid="1.001", ask="1.003", sequence=None),
               dict(ordinal="1", timeNs=str(JAN_LAST), bid="1.002", ask="1.004", sequence=None),
               dict(ordinal="2", timeNs=str(JAN_LAST), bid="1.003", ask="1.005", sequence=None),
               dict(ordinal="3", timeNs=str(FEB_FIRST), bid="1.004", ask="1.006", sequence=None)]
        source = SyntheticTickProvider(raw, chunk_size=2)
        wire, token = [], None
        while True:
            page = source.read_page(source.dataset_id, source.dataset_version, token, 16)
            wire.extend(page["events"])
            if page["endOfDataset"]:
                break
            token = page["nextToken"]
        manifest = write_compact(self.root, iter(wire), parent=dict(datasetId=source.dataset_id,
                                 datasetVersion=source.dataset_version), scale=3, block_rows=2,
                                 evidence_class="SYNTHETIC_CONTRACT_ONLY",
                                 rights=dict({"class": "SYNTHETIC"}, evidenceHash=None))
        reader = CompactTickReader(self.root, expected_manifest_hash=manifest["manifestHash"])
        data = reader.read_range(0, 2**62)
        expected = [(int(e["timeNs"]), Decimal(e["bid"]), Decimal(e["ask"]), int(e["rawOrdinal"])) for e in wire]
        actual = [(int(t), reader.price(b), reader.price(a), int(o))
                  for t, b, a, o in zip(data["ts_ns"], data["bid"], data["ask"], data["ordinal"])]
        self.assertEqual(actual, expected)
        self.assertEqual(reader.parent["datasetVersion"], source.dataset_version)

    def test_large_block_boundaries_match_numpy_reference(self):
        rng = np.random.default_rng(7)
        n = 20_000
        ts = np.sort(rng.integers(1_700_000_000_000_000_000, 1_700_000_100_000_000_000, n))
        events = [ev(i, int(ts[i]), f"1.{10000 + int(rng.integers(0, 500))}", f"1.{10600 + int(rng.integers(0, 500))}")
                  for i in range(n)]
        self.write(events, block_rows=4096)
        reader = CompactTickReader(self.root)
        data = reader.read_range(0, 2**62)
        self.assertTrue(np.array_equal(data["ts_ns"], ts))
        self.assertEqual(int(data["group_id"][-1]) + 1, len(np.unique(ts)))
        window = reader.read_range(int(ts[5000]), int(ts[15000]))
        self.assertTrue(np.array_equal(window["ts_ns"], ts[(ts >= ts[5000]) & (ts < ts[15000])]))
        reader.verify_all(deep=True)


if __name__ == "__main__":
    unittest.main()
