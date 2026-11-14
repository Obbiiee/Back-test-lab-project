"""Financial parity on REAL EURUSD ticks: reference reducer (repo baseline) vs Claude jump engine, and the Claude engine on compact v1 vs compact v2.

Real data (rights UNKNOWN: private QA only, never commercial evidence). A slice of the first N ticks of a verified v1 month is used as the input.
  python -m tools.claude_exp.fin_parity_v2 <v1 month dir> <N> <scenario> <out.json> [offset]        (run from backend/)
Legs: (1) baseline reducer vs ClaudeSession on a compact written by parity.run (v1);  (2) the same slice re-encoded to compact v2 and read by ClaudeSession
through `open_compact`; compare final state, stats and the full event list of leg (2) against leg (1) and against the baseline.
"""
import json, os, shutil, sys, tempfile, time, zipfile, hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np                                                    # noqa: E402
from market_data.compact_tick import CompactTickReader                # noqa: E402
from tools.claude_exp import compact2 as C2                           # noqa: E402
from parity import run, semantic, _orders_view                        # noqa: E402
from common import set_instrument, drive, policy                      # noqa: E402
from claude_session import ClaudeSession, AdmittedSource             # noqa: E402

SCEN = {"swing": dict(step_s=3600, tp=5000, sl=3000, mix=False), "pending": dict(step_s=600, tp=1500, sl=1000, mix=True),
        "eventheavy": dict(step_s=60, tp=150, sl=100, mix=True), "scalp": dict(step_s=20, tp=300, sl=200, mix=False),
        "scalp_tight": dict(step_s=10, tp=30, sl=20, mix=False), "pending_tight": dict(step_s=30, tp=40, sl=30, mix=True)}   # tight targets: many fills on EURUSD


def price(v, scale=5):
    return f"{v // 10**scale}.{v % 10**scale:0{scale}d}"


def main():
    v1dir, n, scen, out = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
    offset = int(sys.argv[5]) if len(sys.argv) > 5 else 0          # first tick of the slice (default 0)
    set_instrument(5, "0.00040")
    rd = CompactTickReader(v1dir)
    a = rd.read_range(0, 2**62)
    ts, bid, ask = a["ts_ns"][offset:offset + n], a["bid"][offset:offset + n], a["ask"][offset:offset + n]
    assert bool(np.all(ts % 1_000_000 == 0)), "source must be millisecond precision"
    rows = [(int(t) // 1_000_000, price(int(k)), price(int(b))) for t, k, b in zip(ts, ask, bid)]
    tmp = Path(tempfile.mkdtemp(prefix="finpar-"))
    z = tmp / "identity.zip"                                          # only its member hash is used (dataset identity); rows come from the real ticks
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("EURUSD_slice.csv", "timestamp,bid,ask\n" + "\n".join(f"{t},{b},{k}" for t, k, b in rows))
    month = v1dir.name
    r = run(n, "clean", rows_override=rows, hd=dict(zip=str(z), pair="EURUSD", month=month), **SCEN[scen])
    res = dict(scenario=scen, ticks=n, sliceOffset=offset, source=str(v1dir.name), rights="UNKNOWN (private QA only)", baseline=r["baseline"], claude_v1=r["claude"], parity_baseline_vs_claude_v1=r["parity"],
               ingest_s=r["ingest_engine_s"], admission_mismatches=r["admission_reconstruction_mismatches"])
    # ---- leg 2: same slice as compact v2 -> ClaudeSession through open_compact
    v1c = r["_cdir"]; v2c = tmp / "v2"
    m2 = C2.encode_month(v1c, v2c)
    res["compact_bytes"] = dict(v1=r["compact_bytes"], v2=sum(f["bytes"] for f in m2["files"]))
    from copy import deepcopy
    src1 = r["_src"]
    src2 = AdmittedSource(v2c, src1.adm, expected_manifest_hash=m2["manifestHash"])
    start, end = rows[0][0] * 1_000_000, rows[-1][0] * 1_000_000
    sc = SCEN[scen]

    def leg(src):
        cs = ClaudeSession(src, r["_profile"], policy(), deepcopy(r["_seed"]), archive=False)
        c0, t0 = time.process_time(), time.perf_counter()
        ev = drive(cs.advance_through, lambda k, pl, cid: cs.command(k, pl, cid), lambda: cs.state, start, end, sc["step_s"], sc["tp"], sc["sl"], sc["mix"])
        return cs, ev, dict(cpu=round(time.process_time() - c0, 2), wall=round(time.perf_counter() - t0, 2), balance=cs.state["balance"], stats=cs.stats,
                            fills=sum(e["kind"] in ("ENTRY_FILL", "EXIT_FILL") for e in ev), unresolved=cs.state["unresolved"])
    cs1, ev1, res["claude_v1_rerun"] = leg(src1)          # same drive, v1 source (control: must equal parity.run's own Claude leg)
    cs2, ev2, res["claude_v2"] = leg(src2)                # same drive, v2 source read through open_compact
    st = lambda c: (c.state["balance"], _orders_view(c.state["orders"], False), c.state["realizedGross"], c.state["lastObservedNs"], c.state["nextGroupIndex"], c.stats)
    res["claude_v1_rerun_equals_parity_run_claude"] = (res["claude_v1_rerun"]["balance"] == res["claude_v1"]["balance"] and res["claude_v1_rerun"]["fills"] == res["claude_v1"]["fills"])
    res["claude_v2_vs_claude_v1"] = dict(finalStateAndStatsEqual=(st(cs1) == st(cs2)), eventsEqual=(semantic(ev1) == semantic(ev2)), rawEventsEqual=(ev1 == ev2), events=len(semantic(ev2)))
    if not res["claude_v2_vs_claude_v1"]["eventsEqual"]:
        for x, y in zip(semantic(ev1), semantic(ev2)):
            if x != y:
                res["firstDivergentEvent"] = dict(v1=x, v2=y); break
    res["status"] = "PASS" if (res["parity_baseline_vs_claude_v1"]["eventsEqual"] and res["claude_v1_rerun_equals_parity_run_claude"]
                               and res["claude_v2_vs_claude_v1"]["finalStateAndStatsEqual"] and res["claude_v2_vs_claude_v1"]["eventsEqual"]) else "FAIL"
    Path(out).write_text(json.dumps(res, indent=1, default=str))
    print(scen, n, res["status"], "| fills", res["baseline"]["fills"], res["claude_v1"]["fills"], res["claude_v2"]["fills"], "| balance", res["baseline"]["balance"],
          res["claude_v1"]["balance"], res["claude_v2"]["balance"], "| cpu base/c1/c2", res["baseline"]["cpu"], res["claude_v1"]["cpu"], res["claude_v2"]["cpu"], flush=True)
    shutil.rmtree(tmp, ignore_errors=True); shutil.rmtree(r["_work"], ignore_errors=True)


if __name__ == "__main__":
    main()
