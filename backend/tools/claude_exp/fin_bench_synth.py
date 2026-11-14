"""Financial head-to-head on a deterministic SYNTHETIC tick stream (no rights question; not market history).

Candidates: `baseline` = the repository's reference financial reducer as integrated at the common baseline (PR #55 head f941eba,
Codex integration), and `claude` = ClaudeSession jump engine. Both are driven by the identical scripted trader (common.drive) and compared
event-by-event (parity.run). One process = one (n, scenario, repeat); wall/CPU of each engine are measured by parity.run itself.
  python -m tools.claude_exp.fin_bench_synth N SCENARIO REPEAT OUT.json      (run from backend/, project Python)
Scenarios: swing (step 3600 s, tp/sl wide), pending (mix=True), scalp (step 20 s, tp/sl tight), eventheavy (step 60 s, tp 150 sl 100).
"""
import json, os, resource, shutil, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parity import run          # noqa: E402
from common import set_instrument   # noqa: E402

SCEN = {"swing": dict(step_s=3600, tp=5000, sl=3000, mix=False), "pending": dict(step_s=600, tp=1500, sl=1000, mix=True),
        "scalp": dict(step_s=20, tp=300, sl=200, mix=False), "eventheavy": dict(step_s=60, tp=150, sl=100, mix=True)}


def synth_rows(n, seed=11):
    """[(ts_ms, ask, bid)] 3-decimal prices (XAUUSD-like scale 3), weekdays only, duplicate timestamps allowed, strictly ordered."""
    rng = np.random.default_rng(seed)
    start_ms = 1_735_689_600_000          # 2025-01-01 UTC (Wed); span ~ 20 weekdays
    span = 20 * 86_400_000
    ts = np.sort(rng.integers(0, span, n)) + start_ms
    mid = 2000.0 + np.cumsum(rng.normal(0, 0.05, n))
    mid = np.clip(mid, 1500, 2500)
    bid = np.round(mid, 3); ask = np.round(mid + 0.35, 3)
    return [(int(t), f"{a:.3f}", f"{b:.3f}") for t, a, b in zip(ts.tolist(), ask.tolist(), bid.tolist())]


def main():
    n, scen, rep, out = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
    set_instrument(3, "0.40")
    rows = synth_rows(n)
    t0 = time.perf_counter(); cpu0 = time.process_time()
    r = run(n, "clean", rows_override=rows, **SCEN[scen])
    total_cpu, total_wall = time.process_time() - cpu0, time.perf_counter() - t0
    work = r.pop("_work")
    for k in ("_cs", "_src", "_profile", "_seed", "_rows", "_cdir", "_manifest", "_groups"):
        r.pop(k, None)
    r.update(scenario=scen, repeat=rep, syntheticDataset="seeded random walk, scale 3, weekdays, duplicate timestamps possible",
             processTotalCpuS=round(total_cpu, 2), processTotalWallS=round(total_wall, 2),
             peakRssMbProcess=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1))
    Path(out).write_text(json.dumps(r, indent=1, default=str))
    shutil.rmtree(work, ignore_errors=True)
    print(scen, n, rep, "parity", r["parity"]["eventsEqual"], "base cpu", r["baseline"]["cpu"], "claude cpu", r["claude"]["cpu"])


if __name__ == "__main__":
    main()
