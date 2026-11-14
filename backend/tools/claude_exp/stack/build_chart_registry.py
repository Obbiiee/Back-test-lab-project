"""Install verified, ready-made OHLC-only prehistory objects into the VPS object store and build the chart registry (JSON) for BTL_CHART_REGISTRY.

  python -m tools.claude_exp.stack.build_chart_registry --store ~/data/ohlcstore --prehistory ~/data/incoming/ohlc_prehistory --tick-root ~/data/incoming/compact2 --basis BID --out ~/data/chart_registry.json
Installation = copying delivered files to the same keys through the store API (immutable: an existing identical object is skipped, a different one is refused); nothing is converted
or recomputed. Run `python -m tools.claude_exp.ohlc.verify_prehistory` first. The registry lists, per instrument, every source dataset that holds the basis in the store (prehistory and tick-derived months).
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.claude_exp.ohlc import engine                           # noqa: E402
from tools.claude_exp.ohlc.store import LocalObjectStore           # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True); ap.add_argument("--prehistory"); ap.add_argument("--tick-root", required=True); ap.add_argument("--basis", default="BID")
    ap.add_argument("--out", required=True); ap.add_argument("--dataset-prefix", default="local:histdata-utc:{pair}:")
    a = ap.parse_args()
    store = LocalObjectStore(a.store); installed = skipped = 0
    if a.prehistory:
        root = Path(a.prehistory)
        for pdir in sorted(p for p in root.iterdir() if p.is_dir()):
            for src in pdir.iterdir():
                for f in sorted(src.rglob("*")):
                    if f.is_file():
                        key = f"ohlc/{engine.TRANSFORM_VERSION}/{pdir.name}/{f.relative_to(pdir).as_posix()}"
                        try:
                            if store.exists(key) if hasattr(store, "exists") else False:
                                skipped += 1; continue
                        except Exception:
                            pass
                        store.put_immutable(key, f.read_bytes()); installed += 1
    base = Path(a.store) / "ohlc" / engine.TRANSFORM_VERSION
    rules = []
    for inst in sorted(p.name for p in base.iterdir() if p.is_dir()):
        hashes = []
        for src in sorted((base / inst).iterdir()):
            months = sorted(x.name for x in (src / a.basis).iterdir()) if (src / a.basis).is_dir() else []
            if months:
                hashes.append((months[0], src.name))
        hashes.sort(reverse=True)                                  # newest month first; one dataset holds one instrument-month, so order only matters for duplicates
        rules.append(dict(datasetIdPrefix=a.dataset_prefix.format(pair=inst), instrument=inst, sourceHashes=[h for _, h in hashes], tickRoot=str(Path(a.tick_root) / inst)))
    Path(a.out).write_text(json.dumps(dict(schemaVersion=1, store=str(Path(a.store)), basis=a.basis, rules=rules), indent=1))
    print(json.dumps(dict(installedObjects=installed, skippedExisting=skipped, instruments=len(rules), datasetsPerInstrument=sorted({len(r["sourceHashes"]) for r in rules}))))


if __name__ == "__main__":
    main()
