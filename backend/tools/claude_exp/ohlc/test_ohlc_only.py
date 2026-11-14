"""OHLC-only importer: M1 exported from the tick engine and re-imported through the OHLC-only path must roll up to IDENTICAL M3..D1 bars; strict refusals."""
import csv, io, random, sys, tempfile, unittest
from pathlib import Path
from decimal import Decimal

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from market_data.compact_tick import write_compact, CompactTickReader      # noqa: E402
from tools.claude_exp.ohlc import engine, ohlc_only as oo                  # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore                   # noqa: E402

NS, SCALE = 10**9, 5


def world():
    rnd = random.Random(5)
    t0 = int(np.datetime64("2026-03-02T00:00:00", "ns").astype(np.int64))
    rows, p, t = [], 1.1, t0
    for i in range(30000):
        t += rnd.choice([0, 1, 7, 90, 450]) * 10**8
        p = min(1.3, max(0.9, p + rnd.uniform(-0.0003, 0.0003)))
        rows.append(dict(timeNs=str(t), bid=f"{p:.5f}", ask=f"{p + 0.0001:.5f}", rawOrdinal=str(i)))
    root = Path(tempfile.mkdtemp(prefix="oo-")) / "c"
    m = write_compact(root, rows, parent=dict(datasetId="local:test:oo", datasetVersion="e" * 64), scale=SCALE)
    return CompactTickReader(root, expected_manifest_hash=m["manifestHash"]), rows


class OhlcOnly(unittest.TestCase):
    def test_m1_reimport_rolls_up_identically_to_the_tick_engine(self):
        reader, rows = world()
        cols, _ = engine.build_month(reader, "2026-03", "BID")
        m1 = cols["M1"]; den = 2 * 10**SCALE
        buf = io.StringIO(); w = csv.writer(buf); w.writerow(["time", "open", "high", "low", "close"])
        fmt = lambda v: str(Decimal(int(v)) / den)
        for i in range(len(m1["t"])):
            w.writerow([int(m1["t"][i]) // NS, fmt(m1["o"][i]), fmt(m1["h"][i]), fmt(m1["l"][i]), fmt(m1["c"][i])])
        got = oo.read_m1(buf.getvalue(), "csv", SCALE)
        for name, sec in engine.TIMEFRAMES:
            r = oo.roll_up(got, sec)
            for k in "tohlc":
                self.assertTrue(np.array_equal(r[k], cols[name][k]), f"{name}.{k}")

    def test_histdata_ascii_with_fixed_est_offset(self):
        text = "20260302 190000;1.100000;1.100500;1.099800;1.100200;0\n20260302 190100;1.100200;1.100300;1.100100;1.100250;0\n"
        c = oo.read_m1(text, "histdata-ascii", 6, tz_offset_min=-300)
        self.assertEqual(int(c["t"][0]) // NS, int(np.datetime64("2026-03-03T00:00:00", "s").astype(np.int64)))      # 19:00 EST = 00:00 UTC next day
        self.assertEqual(int(c["o"][0]), 1100000 * 2)

    def test_refusals_never_repair(self):
        bad = {
            "duplicate": "time,open,high,low,close\n60,1,1,1,1\n60,1,1,1,1\n",
            "reverse": "time,open,high,low,close\n120,1,1,1,1\n60,1,1,1,1\n",
            "not on minute": "time,open,high,low,close\n61,1,1,1,1\n",
            "high below close": "time,open,high,low,close\n60,1,1,1,2\n",
            "low above open": "time,open,high,low,close\n60,1,2,1.5,1.7\n",
            "zero price": "time,open,high,low,close\n60,0,0,0,0\n",
            "precision loss": "time,open,high,low,close\n60,1.1234567,1.1234567,1.1234567,1.1234567\n",
        }
        for name, text in bad.items():
            with self.assertRaises(oo.OhlcOnlyError, msg=name):
                oo.read_m1(text, "csv", 5)

    def test_published_objects_are_marked_display_only_and_served_with_the_catalog(self):
        from tools.claude_exp.ohlc import service as svc
        reader, rows = world()
        cols, _ = engine.build_month(reader, "2026-03", "BID"); m1 = cols["M1"]; den = 2 * 10**SCALE
        store = LocalObjectStore(tempfile.mkdtemp(prefix="oo-s-"))
        man = oo.publish_month(store, "TESTUSD", "2026-03", "BID", {k: m1[k] for k in "tohlc"}, scale=SCALE, source_sha256="f" * 64, source_label="unit-test")
        self.assertEqual(man["evidence"], oo.EVIDENCE)
        self.assertEqual(man["objects"]["M1"]["quoteCount"], 0)
        T = int(m1["t"][-1]) + 60 * NS
        service = svc.ChartService(store, {"TESTUSD": None}, {"s": svc.Session("s", "u", "TESTUSD", "f" * 64, "BID", T)}, {"tok": "u"})
        out = service.bars("tok", "s", "H1", 1000, T)      # an older page: no forming bar (no tick reader exists for OHLC-only months)
        self.assertGreater(out["count"], 0)
        self.assertEqual(out["basis"], "BID")


if __name__ == "__main__":
    unittest.main()
