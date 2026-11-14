"""HistData-UTC monthly zips -> verified compact parquet datasets (one dataset per pair-month). Resumable, read-only on the source.

  python tools/claude_exp/convert_histdata_compact.py --src <HistData-UTC dir> --out <output dir> [--workers 3] [--pairs EURUSD,...]

Per pair-month directory:  <out>/<PAIR>/<YYYY-MM>/compact.json + one parquet per UTC month (market_data.compact_tick, derived, non-authoritative)
Plus <out>/catalog.json with row counts, bytes, manifest hashes, source zip SHA-256, crossed-quote counts.
Every month is verified after writing (manifest hash, per-file SHA-256, deep check) and its row count must equal the source row count.
Nothing here grants data rights: the source rights stay UNKNOWN.
"""
import argparse, csv, hashlib, io, json, sys, time, zipfile
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from market_data.compact_tick import write_compact, CompactTickReader

JPY = ("JPY",)


def decimals_for(pair):
    return 3 if pair.endswith(JPY) else 5


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(1 << 22):
            h.update(b)
    return h.hexdigest()


def member_sha(zpath):
    h = hashlib.sha256()
    with zipfile.ZipFile(zpath) as z, z.open(z.namelist()[0]) as f:
        while b := f.read(1 << 22):
            h.update(b)
    return h.hexdigest()


def rows(zpath, counter):
    with zipfile.ZipFile(zpath) as z, z.open(z.namelist()[0]) as raw:
        rd = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        if next(rd) != ["timestamp", "bid", "ask"]:
            raise ValueError("unexpected header")
        for i, (ts, bid, ask) in enumerate(rd):
            counter[0] = i + 1
            yield dict(timeNs=str(int(ts) * 1_000_000), bid=bid, ask=ask, rawOrdinal=str(i))


def convert(task):
    zpath, pair, ym, out = task
    zpath, out = Path(zpath), Path(out)
    month = f"{ym[:4]}-{ym[4:]}"
    final = out / pair / month
    done = final / "DONE.json"
    if done.exists():
        return json.loads(done.read_text())
    t0 = time.perf_counter()
    zsha = sha256_file(zpath)
    msha = member_sha(zpath)
    ds = f"local:histdata-utc:{pair}:{month}:{msha[:24]}"
    dv = hashlib.sha256(f"{ds}|{zsha}".encode()).hexdigest()
    dec = decimals_for(pair)
    for attempt in range(3):             # more decimals than expected -> retry with one more, never round
        stage = final.parent / (month + ".tmp")
        if stage.exists():
            import shutil; shutil.rmtree(stage)
        counter = [0]
        try:
            m = write_compact(stage, rows(zpath, counter), parent=dict(datasetId=ds, datasetVersion=dv), scale=dec + attempt)
            break
        except Exception as e:
            if attempt == 2 or "scale" not in str(e).lower() and "decimal" not in str(e).lower() and "price" not in str(e).lower():
                return dict(pair=pair, month=month, status="FAILED", error=f"{type(e).__name__}: {e}"[:300])
    r = CompactTickReader(stage, expected_manifest_hash=m["manifestHash"])
    r.verify_all(deep=True)
    ok = (m["eventCount"] == counter[0])
    if not ok:
        return dict(pair=pair, month=month, status="FAILED", error=f"row count {m['eventCount']} != source {counter[0]}")
    size = sum(f["bytes"] for f in m["files"])
    rec = dict(pair=pair, month=month, status="OK", rows=m["eventCount"], groups=m["groupCount"], bytes=size, decimals=dec + attempt,
               crossed=m["quality"]["crossedQuotes"], maxGroupSize=m["quality"]["maxGroupSize"], manifestHash=m["manifestHash"],
               sourceZipSha256=zsha, sourceMemberSha256=msha, datasetId=ds, seconds=round(time.perf_counter() - t0, 1))
    (stage / "DONE.json").write_text(json.dumps(rec))
    if final.exists():
        import shutil; shutil.rmtree(final)
    stage.rename(final)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=3); ap.add_argument("--limit", type=int, default=0); ap.add_argument("--pairs", default="")
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    want = set(filter(None, a.pairs.split(",")))
    tasks = []
    for pdir in sorted(p for p in src.iterdir() if p.is_dir()):
        if want and pdir.name not in want:
            continue
        for z in sorted(pdir.glob("HISTDATA_UTC_*_T*.zip")):
            tasks.append((str(z), pdir.name, z.stem.split("_T")[-1], str(out)))
    if a.limit:
        tasks = tasks[:a.limit]
    out.mkdir(parents=True, exist_ok=True)
    print(f"{len(tasks)} pair-months, {a.workers} workers", flush=True)
    recs, failed, t0 = [], [], time.perf_counter()
    with Pool(a.workers) as pool:
        for i, r in enumerate(pool.imap_unordered(convert, tasks), 1):
            (recs if r["status"] == "OK" else failed).append(r)
            if r["status"] != "OK":
                print("FAILED", r, flush=True)
            if i % 10 == 0 or i == len(tasks):
                gb = sum(x["bytes"] for x in recs) / 1e9
                print(f"{i}/{len(tasks)} done, {gb:.2f} GB written, {time.perf_counter()-t0:.0f}s, failed {len(failed)}", flush=True)
    recs.sort(key=lambda r: (r["pair"], r["month"]))
    (out / "catalog.json").write_text(json.dumps(dict(
        artifact="BTL-CLAUDE-COMPACT-CATALOG-1", derived=True, authoritative=False, rights="UNKNOWN",
        note="Derived compact parquet from local HistData-UTC copies; per-month files pinned by SHA-256 in each compact.json.",
        totalRows=sum(r["rows"] for r in recs), totalBytes=sum(r["bytes"] for r in recs), failed=failed, months=recs), indent=1))
    print("DONE", len(recs), "ok", len(failed), "failed", flush=True)


if __name__ == "__main__":
    main()
