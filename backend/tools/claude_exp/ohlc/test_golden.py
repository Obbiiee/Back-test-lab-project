"""Golden tests: engine (compact tick -> nine timeframes) must equal the independent oracle exactly, for every case in the brief.

    python -m unittest tools.claude_exp.ohlc.test_golden        (run from backend/, project-pinned Python)
"""
import random
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from market_data.compact_tick import write_compact, CompactTickReader     # noqa: E402
from tools.claude_exp.ohlc import oracle, engine                           # noqa: E402

NS = 10**9
PARENT = dict(datasetId="local:test:ohlc", datasetVersion="a" * 64)


def ts(text):
    base, _, frac = text.partition(".")
    return int(datetime.fromisoformat(base).replace(tzinfo=timezone.utc).timestamp()) * NS + int(frac.ljust(9, "0")[:9] or 0)


def months_of(ticks):
    return sorted({datetime.fromtimestamp(t // NS, timezone.utc).strftime("%Y-%m") for t, _, _ in ticks})


def reader_for(ticks, scale):
    root = Path(tempfile.mkdtemp(prefix="ohlc-t-")) / "c"
    events = ({"timeNs": str(t), "bid": b, "ask": a, "rawOrdinal": str(i)} for i, (t, b, a) in enumerate(ticks))
    m = write_compact(root, events, parent=PARENT, scale=scale)
    return CompactTickReader(root, expected_manifest_hash=m["manifestHash"])


def engine_bars(reader, ticks, basis="MID"):
    """All nine timeframes over every month present, as {tf: [dict(Fraction)]} to compare with the oracle."""
    den = 2 * 10 ** reader.scale
    out = {name: [] for name, _ in engine.TIMEFRAMES}
    for month in months_of(ticks):
        cols, _ = engine.build_month(reader, month, basis)
        for name, _ in engine.TIMEFRAMES:
            c = cols[name]
            for i in range(len(c["t"])):
                out[name].append(dict(t=int(c["t"][i]), o=Fraction(int(c["o"][i]), den), h=Fraction(int(c["h"][i]), den), l=Fraction(int(c["l"][i]), den),
                                      c=Fraction(int(c["c"][i]), den), n=int(c["n"][i]), first=int(c["first"][i]), last=int(c["last"][i])))
    return out


class Golden(unittest.TestCase):
    def check(self, ticks, scale=5, basis="MID"):
        expect = oracle.all_timeframes(ticks, basis)
        got = engine_bars(reader_for(ticks, scale), ticks, basis)
        for name, _ in oracle.TIMEFRAMES:
            self.assertEqual(got[name], expect[name], f"{name} differs ({basis})")
        return got

    def test_single_tick(self):
        got = self.check([(ts("2026-05-04T10:00:30"), "1.10000", "1.10002")])
        self.assertEqual(got["D1"][0]["o"], Fraction("1.10001"))

    def test_equal_timestamp_different_quote_keeps_source_order(self):
        t = ts("2026-05-04T10:00:00")
        got = self.check([(t, "1.00000", "1.00010"), (t, "1.00500", "1.00510"), (t, "0.99000", "0.99010"), (t, "1.00100", "1.00110")])
        bar = got["M1"][0]
        self.assertEqual((bar["o"], bar["c"]), (Fraction("1.00005"), Fraction("1.00105")))
        self.assertEqual((bar["h"], bar["l"], bar["n"]), (Fraction("1.00505"), Fraction("0.99005"), 4))

    def test_gap_and_weekend_create_no_candles(self):
        ticks = [(ts("2026-05-01T21:59:59"), "1.1", "1.2"), (ts("2026-05-03T22:05:00"), "1.3", "1.4")]
        got = self.check(ticks, scale=1)
        for name in ("M1", "M5", "H1", "H4", "D1"):
            self.assertEqual(len(got[name]), 2, name)

    def test_cross_month_and_cross_year(self):
        ticks = [(ts("2025-12-31T23:59:59.5"), "1.10000", "1.10010"), (ts("2026-01-01T00:00:00.2"), "1.10020", "1.10030"),
                 (ts("2026-01-01T00:00:00.2"), "1.10040", "1.10050"), (ts("2026-01-31T23:59:59.9"), "1.20000", "1.20010"),
                 (ts("2026-02-01T00:00:00"), "1.21000", "1.21010")]
        got = self.check(ticks)
        self.assertEqual([b["t"] for b in got["D1"]], [ts("2025-12-31T00:00:00"), ts("2026-01-01T00:00:00"), ts("2026-01-31T00:00:00"), ts("2026-02-01T00:00:00")])

    def test_bid_mid_ask_are_different_series(self):
        ticks = [(ts("2026-05-04T10:00:00"), "1.00000", "1.00010"), (ts("2026-05-04T10:00:01"), "1.00020", "1.00040")]
        mid, bid, ask = (self.check(ticks, basis=b)["M1"][0] for b in ("MID", "BID", "ASK"))
        self.assertEqual((mid["c"], bid["c"], ask["c"]), (Fraction("1.0003"), Fraction("1.0002"), Fraction("1.0004")))

    def test_mid_is_per_tick_not_average_of_side_highs(self):
        ticks = [(ts("2026-05-04T10:00:00"), "1.00000", "1.01000"), (ts("2026-05-04T10:00:01"), "1.00300", "1.00310")]
        h_mid = self.check(ticks, basis="MID")["M1"][0]["h"]
        h_bid = self.check(ticks, basis="BID")["M1"][0]["h"]
        h_ask = self.check(ticks, basis="ASK")["M1"][0]["h"]
        self.assertEqual(h_mid, Fraction("1.005"))
        self.assertEqual((h_bid + h_ask) / 2, Fraction("1.0065"))      # what a wrong "average the side highs" would give
        self.assertNotEqual(h_mid, (h_bid + h_ask) / 2)

    def test_extreme_precision_and_large_prices(self):
        self.check([(ts("2026-05-04T10:00:00"), "0.12345678", "0.12345679"), (ts("2026-05-04T10:00:01"), "99999.99999999", "100000.00000001")], scale=8)
        self.check([(ts("2026-05-04T10:00:00"), "2000.123", "2000.456"), (ts("2026-05-04T10:00:59.999"), "2001.001", "2001.002")], scale=3)

    def test_empty_source(self):
        class Empty:
            scale = 5
            def iter_blocks(self, *a, **k):
                return iter(())
        cols, stats = engine.build_month(Empty(), "2026-05", "MID")
        self.assertTrue(all(len(cols[n]["t"]) == 0 for n, _ in engine.TIMEFRAMES))
        self.assertEqual(stats["ticks"], 0)
        self.assertEqual(oracle.all_timeframes([])["M1"], [])

    def test_out_of_order_source_is_refused_by_both(self):
        bad = [(ts("2026-05-04T10:00:05"), "1.1", "1.2"), (ts("2026-05-04T10:00:01"), "1.1", "1.2")]
        with self.assertRaises(oracle.CorruptSource):
            oracle.all_timeframes(bad)

        class Stub:
            scale = 1
            def iter_blocks(self, *a, **k):
                yield dict(ts_ns=np.array([b[0] for b in bad], dtype=np.int64), bid=np.array([11, 11]), ask=np.array([12, 12]))
        with self.assertRaises(engine.CorruptSource):
            engine.build_month(Stub(), "2026-05", "MID")

    def test_non_positive_price_refused(self):
        class Stub:
            scale = 1
            def iter_blocks(self, *a, **k):
                yield dict(ts_ns=np.array([ts("2026-05-04T10:00:00")], dtype=np.int64), bid=np.array([0]), ask=np.array([12]))
        with self.assertRaises(engine.CorruptSource):
            engine.build_month(Stub(), "2026-05", "MID")

    def test_block_boundaries_do_not_change_results(self):
        """Row groups of the compact source are 65,536 ticks; shrink it so every bucket straddles a block boundary."""
        rnd = random.Random(7)
        t, ticks = ts("2026-05-04T00:00:00"), []
        for _ in range(3000):
            t += rnd.choice([0, 1, 3, 40, 900, 7000]) * 10**6
            p = 1 + rnd.random() / 50
            ticks.append((t, f"{p:.5f}", f"{p + 0.00010:.5f}"))
        root = Path(tempfile.mkdtemp(prefix="ohlc-b-")) / "c"
        events = ({"timeNs": str(a), "bid": b, "ask": c, "rawOrdinal": str(i)} for i, (a, b, c) in enumerate(ticks))
        m = write_compact(root, events, parent=PARENT, scale=5, block_rows=97)
        got = engine_bars(CompactTickReader(root, expected_manifest_hash=m["manifestHash"]), ticks)
        expect = oracle.all_timeframes(ticks)
        for name, _ in oracle.TIMEFRAMES:
            self.assertEqual(got[name], expect[name], name)

    def test_random_sources_match_oracle(self):
        for seed in range(60):
            rnd = random.Random(seed)
            t = ts(rnd.choice(["2025-12-30T20:00:00", "2026-02-27T22:00:00", "2026-05-01T00:00:00", "2026-06-30T23:00:00"]))
            ticks, p = [], 1 + rnd.random()
            for _ in range(rnd.choice([1, 2, 50, 400])):
                t += rnd.choice([0, 0, 1, 7, 61, 3599, 86_399, 200_000]) * rnd.choice([1, 10**6, 10**9])
                p = max(0.01, p + rnd.uniform(-0.01, 0.01))
                spread = rnd.choice([0.00001, 0.0001, 0.0005])
                ticks.append((t, f"{p:.5f}", f"{p + spread:.5f}"))
            self.check(ticks, scale=5, basis=rnd.choice(["MID", "BID", "ASK"]))

    def test_publication_is_deterministic_and_immutable(self):
        from tools.claude_exp.ohlc.store import LocalObjectStore, Conflict
        ticks = [(ts("2026-05-04T10:00:00"), "1.10000", "1.10010"), (ts("2026-05-04T10:07:00"), "1.10020", "1.10030")]
        reader = reader_for(ticks, 5)
        a, b = LocalObjectStore(tempfile.mkdtemp()), LocalObjectStore(tempfile.mkdtemp())
        ma, ka = engine.publish_month(a, reader, "TESTUSD", "2026-05", rights="SYNTHETIC")
        mb, kb = engine.publish_month(b, reader, "TESTUSD", "2026-05", rights="SYNTHETIC")
        self.assertEqual(ma, mb)
        for name, _ in engine.TIMEFRAMES:
            self.assertEqual(a.get(ma["objects"][name]["key"]), b.get(mb["objects"][name]["key"]), name)
        puts = a.counters.put
        engine.publish_month(a, reader, "TESTUSD", "2026-05", rights="SYNTHETIC")           # idempotent: no new PUT
        self.assertEqual(a.counters.put, puts)
        key = ma["objects"]["M1"]["key"]
        with self.assertRaises(Conflict):
            a.put_immutable(key, b"different")
        self.assertEqual(ma["volume"][:4], "NONE")


if __name__ == "__main__":
    unittest.main()
