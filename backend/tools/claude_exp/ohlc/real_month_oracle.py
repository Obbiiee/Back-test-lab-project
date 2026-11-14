"""Acceptance of PUBLISHED OHLC objects against the independent oracle on a REAL month (private QA, rights UNKNOWN).

  python -m tools.claude_exp.ohlc.real_month_oracle <compact month dir (v1 or v2)> <object store dir> <instrument> <YYYY-MM> <out.json>
Reads the published nine timeframe objects back from the store (the artifact that will be served), rebuilds every bar with the oracle (exact Fractions,
no shared aggregation code) and requires identical t, n, first, last and exact o/h/l/c for all nine timeframes. The oracle is slow by design (about 2 minutes per 1.4 M ticks).
"""
import json, sys, time
from fractions import Fraction
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.claude_exp import compact2                              # noqa: E402
from tools.claude_exp.ohlc import engine, oracle                   # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore           # noqa: E402


def main():
    src, store_dir, instrument, month, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    reader = compact2.open_compact(src)
    den = 10 ** reader.scale
    store = LocalObjectStore(store_dir)
    manifest = next(json.loads(store.get(k)) for k in store.list(f"ohlc/{engine.TRANSFORM_VERSION}/{instrument}/")
                    if k.endswith(f"/MID/{month}/manifest.json") and json.loads(store.get(k)).get("sourceManifestHash", reader.manifest["manifestHash"]) is not None)
    t0 = time.perf_counter(); ticks = []
    for block in reader.iter_blocks(0, 2**62, atomic=False):
        for t, b, a in zip(block["ts_ns"].tolist(), block["bid"].tolist(), block["ask"].tolist()):
            ticks.append((t, f"{Fraction(b, den)}", f"{Fraction(a, den)}"))
    expect = oracle.all_timeframes(ticks)
    t_oracle = time.perf_counter() - t0
    d2 = 2 * den
    result = dict(month=month, instrument=instrument, ticks=len(ticks), oracleSeconds=round(t_oracle, 1), timeframes={}, status="IDENTICAL")
    for name, _ in engine.TIMEFRAMES:
        c = engine.from_parquet_bytes(store.get(manifest["objects"][name]["key"]))
        e = expect[name]; same = len(e) == len(c["t"])
        first_bad = None
        if same:
            for i, bar in enumerate(e):
                if (bar["t"], bar["n"], bar["first"], bar["last"]) != (int(c["t"][i]), int(c["n"][i]), int(c["first"][i]), int(c["last"][i])) or \
                        any(Fraction(int(c[k][i]), d2) != bar[k] for k in "ohlc"):
                    same, first_bad = False, i; break
        result["timeframes"][name] = dict(bars=len(e), identical=same, firstDivergentBar=first_bad)
        if not same: result["status"] = "MISMATCH"
    Path(out).write_text(json.dumps(result, indent=1)); print(json.dumps(result))


if __name__ == "__main__":
    main()
