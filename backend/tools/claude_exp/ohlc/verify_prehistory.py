"""Read-only verification of OHLC-only prehistory objects delivered ready-made (no importer, nothing is modified or published).
  python -m tools.claude_exp.ohlc.verify_prehistory <prehistory root> [--pairs A,B] --report OUT.jsonl
Per pair-month: SHA-256 list (optional), object sha256 and counts from the manifest, strict bar sanity (ascending bar starts, positive prices, h >= max(o,c), l <= min(o,c)),
M3..D1 equal to a roll-up of the delivered M1 (so the nine timeframes are mutually consistent), evidence class/basis/rights labels, and month continuity."""
import argparse, hashlib, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.claude_exp.ohlc import engine, ohlc_only                    # noqa: E402


def check_month(mdir: Path):
    problems, man = [], json.loads((mdir / "manifest.json").read_text())
    if man.get("artifact") != "BTL-CLAUDE-OHLC-MONTH-1" or man.get("transformVersion") != engine.TRANSFORM_VERSION: problems.append("artifact/transform")
    if man.get("priceBasis") != "BID": problems.append(f"basis {man.get('priceBasis')}")
    if man.get("rights") != "UNKNOWN": problems.append(f"rights {man.get('rights')}")
    if "NOT_EXECUTION" not in str(man.get("evidence")): problems.append(f"evidence {man.get('evidence')}")
    cols = {}
    for name, o in man["objects"].items():
        raw = (mdir / f"{name}.parquet").read_bytes()
        if hashlib.sha256(raw).hexdigest() != o["sha256"] or len(raw) != o["bytes"]: problems.append(f"{name} sha/bytes")
        c = engine.from_parquet_bytes(raw); cols[name] = c
        if len(c["t"]) != o["count"]: problems.append(f"{name} count")
        if len(c["t"]) and (bool(np.any(np.diff(c["t"]) <= 0)) or bool(np.any(c["o"] <= 0)) or bool(np.any(c["h"] < np.maximum(c["o"], c["c"]))) or bool(np.any(c["l"] > np.minimum(c["o"], c["c"])))):
            problems.append(f"{name} bar sanity")
    m1 = cols["M1"]
    for name, sec in engine.TIMEFRAMES[1:]:
        r = ohlc_only.roll_up({k: m1[k] for k in "tohlc"}, sec)
        if not all(np.array_equal(r[k], cols[name][k]) for k in "tohlc"): problems.append(f"{name} != roll-up of M1")
    return man, cols, problems


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("root"); ap.add_argument("--pairs", default=""); ap.add_argument("--report", required=True)
    a = ap.parse_args(); root = Path(a.root); want = set(filter(None, a.pairs.split(",")))
    out = open(a.report, "w")
    for pdir in sorted(p for p in root.iterdir() if p.is_dir()):
        if want and pdir.name not in want: continue
        sha_file = root / f"SHA256SUMS_{pdir.name}.txt"; sha = {}
        if sha_file.exists():
            for line in sha_file.read_text().splitlines():
                if line.strip(): d, _, n = line.partition("  "); sha[n.strip()] = d
        src = next(d for d in pdir.iterdir() if d.is_dir()); bid = src / "BID"; prev_close = None; months = 0; bars = 0
        for mdir in sorted(bid.iterdir()):
            man, cols, problems = check_month(mdir)
            for f in mdir.iterdir():
                key = f"{pdir.name}/{src.name}/BID/{mdir.name}/{f.name}"
                if sha and key in sha and hashlib.sha256(f.read_bytes()).hexdigest() != sha[key]: problems.append(f"sha list {f.name}")
                if sha and key not in sha: problems.append(f"not in sha list {f.name}")
            m1 = cols["M1"]; months += 1; bars += len(m1["t"])
            gap = None
            if prev_close is not None: gap = round(abs(int(m1["o"][0]) - prev_close) / int(man["priceScaleDenominator"]) * 2, 6)
            prev_close = int(m1["c"][-1]); den = int(man["priceScaleDenominator"])
            rec = dict(pair=pdir.name, month=mdir.name, status="OK" if not problems else "FAILED", problems=problems, m1Bars=int(len(m1["t"])), d1Bars=int(len(cols["D1"]["t"])),
                       scaleDen=den, source=man["source"].get("provider"), tzRule=man["source"].get("timeZoneRule"), openGapToPrevClose=gap, manifestHash=man["source"]["manifestHash"])
            out.write(json.dumps(rec) + "\n"); out.flush()
        print(pdir.name, "months", months, "m1 bars", bars, flush=True)


if __name__ == "__main__":
    main()
