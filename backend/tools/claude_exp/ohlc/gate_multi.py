"""G5 (multi-month) / G6 (one year) materialisation of a multi-month compact source: wall, CPU, peak RSS, objects, bytes per month and total.
Optional per-month oracle equality (--oracle): naive and slow, one month at a time, so memory stays bounded.
  python -m tools.claude_exp.ohlc.gate_multi --src DIR --months 2026-05,2026-06 --label G5 [--oracle] --out result.json
"""
import argparse
import json
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from market_data.compact_tick import CompactTickReader      # noqa: E402
from tools.claude_exp.ohlc import engine, oracle              # noqa: E402
from tools.claude_exp.ohlc.bench import measure                # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore       # noqa: E402


def equal_to_oracle(reader, month):
    y, m = int(month[:4]), int(month[5:])
    start = int(np.datetime64(f"{y:04d}-{m:02d}-01", "ns").astype(np.int64))
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    end = int(np.datetime64(f"{ny:04d}-{nm:02d}-01", "ns").astype(np.int64))
    den, ticks = 10 ** reader.scale, []
    for block in reader.iter_blocks(start, end, atomic=False):
        for t, b, a in zip(block["ts_ns"].tolist(), block["bid"].tolist(), block["ask"].tolist()):
            ticks.append((t, f"{Fraction(b, den)}", f"{Fraction(a, den)}"))
    expect = oracle.all_timeframes(ticks)
    cols, _ = engine.build_month(reader, month, "MID")
    for name, _w in engine.TIMEFRAMES:
        c, e = cols[name], expect[name]
        if len(e) != len(c["t"]):
            return False
        for i, bar in enumerate(e):
            if (bar["t"], bar["n"], bar["first"], bar["last"]) != (int(c["t"][i]), int(c["n"][i]), int(c["first"][i]), int(c["last"][i])) or \
                    any(Fraction(int(c[k][i]), 2 * den) != bar[k] for k in "ohlc"):
                return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--months", required=True); ap.add_argument("--label", required=True)
    ap.add_argument("--oracle", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args()
    reader = CompactTickReader(a.src)
    months = a.months.split(",")
    store = LocalObjectStore(tempfile.mkdtemp(prefix="gate-multi-"))
    per = []

    def go():
        for mo in months:
            t0 = time.perf_counter()
            mf, _ = engine.publish_month(store, reader, "SYNTH", mo, rights="SYNTHETIC")
            per.append(dict(month=mo, seconds=round(time.perf_counter() - t0, 3), bytes=sum(o["bytes"] for o in mf["objects"].values())))
    _, m = measure(go)
    res = dict(gate=a.label, label="SYNTHETIC", months=len(months), wall=round(m["wall"], 3), cpu=round(m["cpu"], 3), peakRssMB=m["peakRssMB"],
               rssBaseMB=m["rssBaseMB"], writeMB=m["writeMB"], totalBytes=sum(p["bytes"] for p in per), puts=store.counters.snapshot(), perMonth=per)
    if a.oracle:
        res["oracleEquality"] = {mo: ("IDENTICAL" if equal_to_oracle(reader, mo) else "MISMATCH") for mo in months}
    else:
        res["oracleEquality"] = "NOT_RUN"
    print(json.dumps(res))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
