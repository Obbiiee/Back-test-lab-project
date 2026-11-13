"""Randomised parity: many real-tick windows x random ties/gaps x step sizes x trader styles. Claude jump path must equal the reference."""
import sys, random, json, shutil, collections
sys.path.insert(0, ".")
from parity import *

def build(seed, n):
    rnd = random.Random(seed)
    base = read_real_rows(n * 9)[(seed % 8) * n:(seed % 8) * n + n]
    rows, shift = [], 0
    tie_p = rnd.choice([0, 0, 1 / 1500, 1 / 500])
    gap_idx = set(rnd.sample(range(200, n - 50), rnd.choice([0, 1, 3])))
    for i, (ts, ask, bid) in enumerate(base):
        if i in gap_idx: shift += rnd.randint(70_000, 400_000)
        rows.append((ts + shift, ask, bid))
        if tie_p and rnd.random() < tie_p:
            d = rnd.choice([0.2, -0.2, 0.7]); rows.append((ts + shift, f"{float(ask)+d:.3f}", f"{float(bid)+d:.3f}"))
    return rows, dict(tie_p=tie_p, gaps=len(gap_idx))

if __name__ == "__main__":
    seeds, n = int(sys.argv[1]), int(sys.argv[2]); allok, kinds, rowsout = True, collections.Counter(), []
    for seed in range(seeds):
        rows, info = build(seed, n)
        step = random.Random(seed + 99).choice([60, 300, 900]); mix = seed % 2 == 1
        r = run(n, step_s=step, mix=mix, rows_override=rows)
        cs = r["_cs"]; ok = all(r["parity"].values()) and r["admission_reconstruction_mismatches"] == 0
        allok &= ok
        for e in cs.log: pass
        kinds.update(x["kind"] for x in [] )
        rowsout.append(dict(seed=seed, mix=mix, step=step, **info, ok=ok, baseCpu=r["baseline"]["cpu"], claudeCpu=r["claude"]["cpu"],
                            fills=r["baseline"]["fills"], unresolved=r["baseline"]["unresolved"], stats=r["claude"]["stats"],
                            firstDiff=r.get("firstDiff")))
        shutil.rmtree(r["_work"], ignore_errors=True)
        print(json.dumps(rowsout[-1], default=str), flush=True)
    print("ALL_PARITY_OK" if allok else "PARITY_FAILURE", f"{sum(x['ok'] for x in rowsout)}/{len(rowsout)}")
