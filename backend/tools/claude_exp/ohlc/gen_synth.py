"""Deterministic SYNTHETIC EURUSD-like compact tick source (random-walk mid, fixed spread, weekday sessions, equal timestamps allowed).
Not market data; no rights question. Used to measure the engines on a host that holds no real data.
  python -m tools.claude_exp.ohlc.gen_synth --out DIR --months 1 --ticks-per-month 1444646 [--start 2026-05]
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from market_data.compact_tick import write_compact      # noqa: E402

NS = 10**9


def month_ticks(year, month, n, rng):
    first = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())
    nxt = int(datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc).timestamp())
    days = [d for d in range((nxt - first) // 86400) if datetime.fromtimestamp(first + d * 86400, timezone.utc).weekday() < 5]
    day_idx = np.sort(rng.integers(0, len(days), n))
    sec = rng.integers(0, 86400 * 10, n) * (NS // 10)
    t = np.array(days, dtype=np.int64)[day_idx] * 86400 * NS + first * NS + sec
    t.sort(kind="stable")
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--months", type=int, default=1)
    ap.add_argument("--ticks-per-month", type=int, default=1_444_646); ap.add_argument("--start", default="2026-05"); ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    y, m = map(int, a.start.split("-"))
    parts, price = [], 1.1
    for _ in range(a.months):
        t = month_ticks(y, m, a.ticks_per_month, rng)
        steps = rng.normal(0, 0.00003, len(t)).cumsum() + price
        steps = np.clip(steps, 0.9, 1.3); price = float(steps[-1])
        parts.append((t, steps)); y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    def rows():
        i = 0
        for t, p in parts:
            for tt, pp in zip(t.tolist(), p.tolist()):
                yield {"timeNs": str(tt), "bid": f"{pp:.5f}", "ask": f"{pp + 0.00012:.5f}", "rawOrdinal": str(i)}
                i += 1
    man = write_compact(Path(a.out), rows(), parent=dict(datasetId="synthetic:eurusd-like", datasetVersion="b" * 64), scale=5)
    print("WROTE", man["manifestHash"], sum(len(t) for t, _ in parts), "ticks")


if __name__ == "__main__":
    main()
