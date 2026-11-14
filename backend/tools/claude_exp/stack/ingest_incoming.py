"""Receive compact tick datasets sent from the laptop: verify, then (optionally) publish the nine OHLC timeframes (MID) to the local object store.

Layout accepted (as produced by tools/claude_exp/convert_histdata_compact.py / convert_dukascopy_month.py):
  <root>/<PAIR>/<YYYY-MM>/compact.json , DONE.json , <YYYY-MM>/ticks.parquet
Sequential, single process, low priority (nice), bounded: it never touches PostgreSQL, the network or anything outside <root> and <store>.
Rights stay UNKNOWN (private QA only). Nothing is ever re-sorted, de-duplicated or repaired: a dataset that fails is reported and skipped.

  python -m tools.claude_exp.stack.ingest_incoming verify  --root ~/data/incoming/compact [--sha256-list FILE] [--pairs EURUSD,..] --report OUT.jsonl
  python -m tools.claude_exp.stack.ingest_incoming publish --root ~/data/incoming/compact --store ~/data/ohlcstore --report OUT.jsonl [--pairs ..]
(run from backend/, project Python 3.13). publish verifies first (shallow) and is idempotent: an existing identical object is not rewritten.
"""
import argparse, json, os, shutil, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from market_data.compact_tick import CompactTickReader          # noqa: E402


def datasets(root, pairs):
    for pdir in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        if pairs and pdir.name not in pairs:
            continue
        for mdir in sorted(p for p in pdir.iterdir() if p.is_dir() and (p / "compact.json").exists()):
            yield pdir.name, mdir.name, mdir


def load_sha_list(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            digest, _, name = line.partition("  ")
            out[name.strip().lstrip("*").replace("\\", "/")] = digest
    return out


def check(pair, month, mdir, sha_list, deep):
    rec = dict(pair=pair, month=month, status="OK", problems=[])
    t0 = time.perf_counter()
    try:
        manifest = json.loads((mdir / "compact.json").read_text())
        done = json.loads((mdir / "DONE.json").read_text()) if (mdir / "DONE.json").exists() else None
        rec.update(manifestHash=manifest["manifestHash"], eventCount=manifest["eventCount"], priceScale=manifest["priceScale"],
                   rights=(manifest.get("rights") or {}).get("class"), crossed=(manifest.get("quality") or {}).get("crossedQuotes"))
        if done is None:
            rec["problems"].append("DONE.json missing")
        else:
            if done.get("status") != "OK": rec["problems"].append(f"DONE status {done.get('status')}")
            if done.get("manifestHash") != manifest["manifestHash"]: rec["problems"].append("manifestHash != DONE.json")
            if done.get("rows") != manifest["eventCount"]: rec["problems"].append("eventCount != DONE.json rows")
        if rec["rights"] != "UNKNOWN":
            rec["problems"].append(f"rights class {rec['rights']} (expected UNKNOWN)")
        if sha_list is not None:
            for f in sorted(p for p in mdir.rglob("*") if p.is_file()):
                key = f"{pair}/{month}/{f.relative_to(mdir).as_posix()}"
                import hashlib
                h = hashlib.sha256()
                with open(f, "rb") as fh:
                    while b := fh.read(1 << 22): h.update(b)
                rel = f.relative_to(mdir).as_posix()
                # tolerate sha lists written relative to the root (PAIR/MONTH/file), to the pair (MONTH/file) or to the month folder (file)
                want = sha_list.get(key) or sha_list.get(f"{month}/{rel}") or (sha_list.get(rel) if "/" in rel or len({k for k in sha_list if k.endswith('compact.json')}) <= 1 else None)
                if want is None: rec["problems"].append(f"not in sha list: {key}")
                elif want != h.hexdigest(): rec["problems"].append(f"sha256 mismatch: {key}")
        reader = CompactTickReader(mdir, expected_manifest_hash=manifest["manifestHash"])
        reader.verify_all(deep=deep)
        rec["verified"] = "deep" if deep else "files-hash"
    except Exception as error:
        rec["problems"].append(f"{type(error).__name__}: {str(error)[:200]}")
    rec["status"] = "OK" if not rec["problems"] else "FAILED"
    rec["seconds"] = round(time.perf_counter() - t0, 1)
    return rec


def main():
    os.nice(10)
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("verify", "publish"))
    ap.add_argument("--root", required=True); ap.add_argument("--report", required=True); ap.add_argument("--pairs", default="")
    ap.add_argument("--sha256-list"); ap.add_argument("--store"); ap.add_argument("--shallow", action="store_true")
    ap.add_argument("--min-free-gb", type=float, default=30.0)
    a = ap.parse_args()
    pairs = set(filter(None, a.pairs.split(",")))
    sha_list = load_sha_list(a.sha256_list) if a.sha256_list else None
    if a.mode == "publish":
        if not a.store: raise SystemExit("--store required")
        from tools.claude_exp.ohlc import engine
        from tools.claude_exp.ohlc.store import LocalObjectStore
        store = LocalObjectStore(a.store)
    done_keys = set()
    rp = Path(a.report)
    if rp.exists():                                   # resumable: skip pair-months already OK in the report
        for line in rp.read_text().splitlines():
            r = json.loads(line)
            if r.get("status") == "OK": done_keys.add((r["pair"], r["month"]))
    n_ok = n_bad = 0
    with open(rp, "a") as out:
        for pair, month, mdir in datasets(a.root, pairs):
            if (pair, month) in done_keys: continue
            if shutil.disk_usage(a.root).free < a.min_free_gb * 2**30:
                print("STOP: free disk below reserve", flush=True); break
            rec = check(pair, month, mdir, sha_list, deep=(a.mode == "verify" and not a.shallow))
            if a.mode == "publish" and rec["status"] == "OK":
                t0 = time.perf_counter()
                try:
                    reader = CompactTickReader(mdir, expected_manifest_hash=rec["manifestHash"])
                    manifest_key, stats = engine.publish_month(store, reader, pair, month, rights="UNKNOWN")
                    rec.update(published=manifest_key, publishSeconds=round(time.perf_counter() - t0, 2))
                except Exception as error:
                    rec["status"] = "FAILED"; rec["problems"].append(f"publish {type(error).__name__}: {str(error)[:200]}")
            out.write(json.dumps(rec) + "\n"); out.flush()
            n_ok += rec["status"] == "OK"; n_bad += rec["status"] != "OK"
            print(pair, month, rec["status"], rec["problems"][:2], flush=True)
    print(json.dumps(dict(ok=n_ok, failed=n_bad)), flush=True)


if __name__ == "__main__":
    main()
