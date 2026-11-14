"""Real-data chart probe (private QA, rights UNKNOWN): 9 timeframes paged back from a cursor over per-month datasets (catalog across datasets).
  python -m tools.claude_exp.stack.real_chart_probe <compact root PAIR dir> <ohlc store> <PAIR> <cursor ISO> <out.json>"""
import json, statistics, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.claude_exp import compact2                                    # noqa: E402
from tools.claude_exp.ohlc import engine, service as svc                 # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore                 # noqa: E402


def main():
    root, store_dir, pair, cursor_iso, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
    store = LocalObjectStore(store_dir)
    prefixes = sorted({k.split("/")[3] for k in store.list(f"ohlc/{engine.TRANSFORM_VERSION}/{pair}/")}, reverse=True)
    month_dirs = {d.name: d for d in root.iterdir() if (d / "compact.json").exists() or (d / "compact2.json").exists()}
    readers = {}
    def reader_for(ns):
        m = datetime.fromtimestamp(ns // 10**9, timezone.utc).strftime("%Y-%m")
        if m not in readers: readers[m] = compact2.open_compact(month_dirs[m])
        return readers[m]
    T = int(datetime.fromisoformat(cursor_iso).replace(tzinfo=timezone.utc).timestamp()) * 10**9
    sessions = {"s": svc.Session("s", "u", pair, prefixes[0], "MID", T, source_hashes=prefixes)}
    service = svc.ChartService(store, {pair: reader_for}, sessions, {"tok": "u"}, cache_objects=64)
    res = dict(pair=pair, cursor=cursor_iso, datasets=len(prefixes), timeframes={})
    for phase in ("cold", "warm"):
        for tf in svc.TF_SECONDS:
            t0 = time.perf_counter(); total, pages, lat, before, oldest, more = 0, 0, [], None, None, True
            while total < 5000 and more:
                t1 = time.perf_counter()
                o = service.bars("tok", "s", tf, 512 if before is None else 1000, before)
                lat.append((time.perf_counter() - t1) * 1000); total += o["count"]; pages += 1; before = o["nextBefore"]; more = o["hasMore"]
                oldest = before
            row = dict(candles=total, pages=pages, totalMs=round((time.perf_counter() - t0) * 1000, 1), maxPageMs=round(max(lat), 1),
                       oldestBar=datetime.fromtimestamp(oldest / 1e9, timezone.utc).strftime("%Y-%m-%d") if oldest else None, reached5000=total >= 5000, hasMoreHistory=more)
            res["timeframes"].setdefault(tf, {})[phase] = row
    res["cacheHits"], res["cacheMisses"] = service.hits, service.misses
    Path(out).write_text(json.dumps(res, indent=1)); print(json.dumps(res))


if __name__ == "__main__":
    main()
