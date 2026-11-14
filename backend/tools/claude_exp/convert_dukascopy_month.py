r"""One Dukascopy tick CSV (dukascopy-node: timestamp,askPrice,bidPrice,askVolume,bidVolume) -> zip (unchanged bytes) + verified compact parquet.

  python tools/claude_exp/convert_dukascopy_month.py --csv usdcad_2026-07.csv --pair USDCAD --month 2026-07 --zip-out <Dukascopy\USDCAD> --out <parquet root>

The CSV is stored byte-for-byte inside the zip. The parquet dataset is derived, non-authoritative, rights UNKNOWN."""
import argparse, csv, hashlib, json, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from market_data.compact_tick import write_compact, CompactTickReader


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True); ap.add_argument("--pair", required=True); ap.add_argument("--month", required=True)
    ap.add_argument("--zip-out", required=True); ap.add_argument("--out", required=True); ap.add_argument("--decimals", type=int, default=5)
    a = ap.parse_args()
    src = Path(a.csv); ym = a.month.replace("-", "")
    zdir = Path(a.zip_out); zdir.mkdir(parents=True, exist_ok=True)
    zpath = zdir / f"DUKASCOPY_{a.pair}_T{ym}.zip"
    if zpath.exists():
        raise SystemExit(f"refusing to overwrite {zpath}")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(src, arcname=src.name)
    with zipfile.ZipFile(zpath) as z:
        assert z.testzip() is None
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    zsha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    counter = [0]

    def rows():
        with open(src, newline="") as f:
            rd = csv.reader(f)
            if next(rd) != ["timestamp", "askPrice", "bidPrice", "askVolume", "bidVolume"]:
                raise ValueError("unexpected header")
            for i, (ts, ask, bid, _av, _bv) in enumerate(rd):
                counter[0] = i + 1
                yield dict(timeNs=str(int(ts) * 1_000_000), bid=bid, ask=ask, rawOrdinal=str(i))

    ds = f"local:dukascopy:{a.pair}:{a.month}:{sha[:24]}"
    dv = hashlib.sha256(f"{ds}|{zsha}".encode()).hexdigest()
    final = Path(a.out) / a.pair / f"{a.month}-dukascopy"
    if final.exists():
        raise SystemExit(f"refusing to overwrite {final}")
    stage = final.parent / (final.name + ".tmp")
    m = write_compact(stage, rows(), parent=dict(datasetId=ds, datasetVersion=dv), scale=a.decimals)
    CompactTickReader(stage, expected_manifest_hash=m["manifestHash"]).verify_all(deep=True)
    assert m["eventCount"] == counter[0]
    rec = dict(pair=a.pair, month=a.month, source="dukascopy-node", rows=m["eventCount"], crossed=m["quality"]["crossedQuotes"],
               bytes=sum(f["bytes"] for f in m["files"]), manifestHash=m["manifestHash"], csvSha256=sha, zipSha256=zsha, datasetId=ds,
               zip=str(zpath), derived=True, authoritative=False, rights="UNKNOWN")
    (stage / "DONE.json").write_text(json.dumps(rec, indent=1))
    stage.rename(final)
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
