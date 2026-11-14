"""Edge cases for compact v2 (lossless re-encoding). Run from backend/: python -m unittest tools.claude_exp.test_compact2"""
import random
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from market_data.compact_tick import write_compact, CompactTickReader      # noqa: E402
from contracts.primitives import ContractError                              # noqa: E402
from tools.claude_exp import compact2 as C                                  # noqa: E402

PARENT = dict(datasetId="local:test:c2", datasetVersion="c" * 64)


def v1(events, scale=5, block_rows=65536):
    root = Path(tempfile.mkdtemp(prefix="c2-")) / "v1"
    write_compact(root, events, parent=PARENT, scale=scale, block_rows=block_rows)
    return root


def roundtrip(events, scale=5, block_rows=65536):
    src = v1(events, scale, block_rows)
    dst = Path(tempfile.mkdtemp(prefix="c2-")) / "v2"
    C.encode_month(src, dst)
    return src, dst, C.verify_equal(src, dst)


def ev(rows):
    return [{"timeNs": str(t), "bid": b, "ask": a, "rawOrdinal": str(i)} for i, (t, b, a) in enumerate(rows)]


class Compact2(unittest.TestCase):
    def test_equal_timestamps_crossing_block_boundaries(self):
        t, rows = 1_700_000_000_000_000_000, []
        for i in range(500):
            if i % 7:
                t += 1_000_000
            rows.append((t, f"1.{10000 + i % 90:05d}", f"1.{10010 + i % 90:05d}"))
        for block in (1, 3, 7, 64, 500):
            self.assertEqual(roundtrip(ev(rows), block_rows=block)[2], 500)

    def test_crossed_and_zero_spread_quotes(self):
        rows = [(1_700_000_000_000_000_000 + i * 1_000_000, "1.20000", "1.19990" if i % 5 == 0 else "1.20000" if i % 3 == 0 else "1.20010") for i in range(300)]
        src, dst, n = roundtrip(ev(rows))
        self.assertEqual(C.CompactV2Reader(dst).manifest["quality"]["crossedQuotes"], CompactTickReader(src).manifest["quality"]["crossedQuotes"])
        self.assertGreater(CompactTickReader(src).manifest["quality"]["crossedQuotes"], 0)

    def test_sub_millisecond_timestamps_use_nanosecond_unit(self):
        rows = [(1_700_000_000_000_000_000 + i * 1_000_001, "1.00000", "1.00010") for i in range(200)]
        src, dst, n = roundtrip(ev(rows))
        self.assertEqual(C.CompactV2Reader(dst).manifest["files"][0]["timeUnitNs"], 1)

    def test_millisecond_timestamps_use_millisecond_unit(self):
        rows = [(1_700_000_000_000_000_000 + i * 1_000_000, "1.00000", "1.00010") for i in range(200)]
        src, dst, n = roundtrip(ev(rows))
        self.assertEqual(C.CompactV2Reader(dst).manifest["files"][0]["timeUnitNs"], 1_000_000)

    def test_month_boundary_and_random_walk(self):
        rnd = random.Random(3)
        t, p, rows = 1_746_057_600_000_000_000 - 3_000_000_000, 100000, []         # 2025-04-30 23:59:57
        for _ in range(3000):
            t += rnd.choice([0, 1, 5, 400, 90_000]) * 1_000_000
            p = max(10, p + rnd.randint(-40, 40))
            s = rnd.choice([0, 5, 10, 30])
            rows.append((t, f"{p / 100000:.5f}", f"{(p + s) / 100000:.5f}"))
        src, dst, n = roundtrip(ev(rows), block_rows=257)
        self.assertEqual(n, 3000)
        self.assertEqual(len(C.CompactV2Reader(dst).manifest["files"]), 2)

    def test_windowed_reads_match_v1(self):
        rows = [(1_700_000_000_000_000_000 + i * 2_000_000, "1.00000", f"1.{10 + i % 9:05d}") for i in range(2000)]
        src, dst, _ = roundtrip(ev(rows), block_rows=100)
        a, b = CompactTickReader(src), C.CompactV2Reader(dst)
        for lo, hi in ((0, 2**62), (1_700_000_000_300_000_000, 1_700_000_001_000_000_000), (1_700_000_003_999_000_000, 1_700_000_004_000_000_001)):
            x, y = a.read_range(lo, hi), b.read_range(lo, hi)
            for col in x:
                self.assertTrue(np.array_equal(x[col], y[col]), col)
        ga, gb = list(a.iter_groups(0, 2**62)), list(b.iter_groups(0, 2**62))
        self.assertEqual(len(ga), len(gb))

    def test_non_contiguous_ordinals_are_refused(self):
        rows = ev([(1_700_000_000_000_000_000 + i * 1_000_000, "1.00000", "1.00010") for i in range(50)])
        for i, e in enumerate(rows):
            e["rawOrdinal"] = str(i * 2)
        src = v1(rows)
        with self.assertRaises(ContractError):
            C.encode_month(src, Path(tempfile.mkdtemp()) / "v2")

    def test_tampered_file_is_detected(self):
        rows = [(1_700_000_000_000_000_000 + i * 1_000_000, "1.00000", "1.00010") for i in range(100)]
        src, dst, _ = roundtrip(ev(rows))
        f = next(dst.rglob("ticks2.parquet"))
        raw = bytearray(f.read_bytes())
        raw[len(raw) // 2] ^= 0xFF
        f.write_bytes(bytes(raw))
        with self.assertRaises(Exception):
            C.CompactV2Reader(dst).verify_all()

    def test_refuses_to_overwrite_and_pins_the_v1_source(self):
        rows = ev([(1_700_000_000_000_000_000 + i * 1_000_000, "1.00000", "1.00010") for i in range(50)])
        src = v1(rows)
        dst = Path(tempfile.mkdtemp()) / "v2"
        m = C.encode_month(src, dst)
        self.assertEqual(m["derivedFrom"]["manifestHash"], CompactTickReader(src).manifest["manifestHash"])
        with self.assertRaises(ContractError):
            C.encode_month(src, dst)


if __name__ == "__main__":
    unittest.main()
