"""Commercial V1 capacity acceptance (20 active traders, one 262,144-tick financial-active job each within one hour): feasibility gate and seeded schedule.

What it does, honestly: it does NOT claim a capacity result. It (1) states the contract bounds that the durable path enforces (read from the code), (2) computes from
MEASURED engine rates whether the target job can finish inside them and how much compute the whole hour would need, (3) writes the seeded arrival schedule
(20 staggered arrivals over 3,600 s, plus a burst of eight within 10 s) that the load driver replays, and (4) exits 2 with BLOCKED_BY_CONTRACT when the target job
cannot be carried by the durable path. Measurements themselves are taken by frontend/tests/http_load_cohort.py (CPU per role, peak RSS, queue wait, latency, WAL).
"""
import argparse
import json
import random
import sys
from pathlib import Path

TARGET_TICKS, TRADERS, HOUR_S, BURST = 262_144, 20, 3600, 8
# Measured engine-only rates of the frozen reducer (ticks/s on one core): AI_CONTEXT/04_CURRENT_PHASE.md local run (656-714) and
# docs/benchmarks/CLAUDE_VPS_MEASUREMENTS_2026-11-14.md section on baseline throughput on this VPS (650-1,250).
RATE_LOW, RATE_HIGH = 650, 1250
GROUPS_PER_ADVANCE = 64                # execution/controller.py preview scan bound


def contract_bounds():
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from execution import contracts
    from cloud import queue
    return dict(maxSteps=contracts.MAX_STEPS, groupsPerAdvance=GROUPS_PER_ADVANCE, workers=queue.WORKERS,
                queueTtlSeconds=60, workerDeadlineSeconds=30, globalAdmission=16, perUserAdmission=2)


def feasibility(ticks=TARGET_TICKS, traders=TRADERS, workers=4):
    b = contract_bounds()
    max_groups_per_session = b["maxSteps"] * b["groupsPerAdvance"]          # one tick per timestamp group in the best case
    per_job_s = (ticks / RATE_HIGH, ticks / RATE_LOW)
    compute_core_s = (traders * per_job_s[0], traders * per_job_s[1])
    blockers = []
    if ticks > max_groups_per_session:
        blockers.append(f"a Session can persist at most MAX_STEPS x groups-per-advance = {b['maxSteps']} x {b['groupsPerAdvance']} = {max_groups_per_session} timestamp groups; "
                        f"{ticks} ticks need at least that many groups when every tick has its own timestamp (REFUSED_RECOVERY_LIMIT observed at 16,320 and 65,536 ticks)")
    if per_job_s[0] > b["workerDeadlineSeconds"]:
        blockers.append(f"one job needs {per_job_s[0]:.0f}-{per_job_s[1]:.0f} s of single-core engine time but the native job deadline is {b['workerDeadlineSeconds']} s "
                        f"(only chunked continuation can bridge this, and it is capped by the checkpoint budget above)")
    return dict(ticks=ticks, traders=traders, workers=workers, bounds=b, perJobEngineSeconds=[round(x, 1) for x in per_job_s],
                hourComputeCoreSecondsEngineOnly=[round(x) for x in compute_core_s],
                averageCoresNeededEngineOnly=[round(x / HOUR_S, 2) for x in compute_core_s],
                workerSlotCoreSecondsAvailable=workers * HOUR_S,
                engineComputeFitsWorkerSlots=compute_core_s[1] <= workers * HOUR_S,
                verdict="BLOCKED_BY_CONTRACT" if blockers else "FEASIBLE_UNDER_CONTRACT", blockers=blockers)


def schedule(seed=20261115, traders=TRADERS, hour_s=HOUR_S, burst=BURST):
    """Stratified jitter: trader i arrives uniformly inside its own slot of hour/traders seconds, so arrivals are spread but not periodic. Reproducible from the seed."""
    rng = random.Random(seed)
    slot = hour_s / traders
    normal = [dict(trader=i + 1, arrivalS=round(i * slot + rng.random() * slot, 3), ticks=TARGET_TICKS) for i in range(traders)]
    burst_rows = [dict(trader=i + 1, arrivalS=round(rng.random() * 10, 3), ticks=TARGET_TICKS) for i in range(burst)]
    return dict(seed=seed, hourSeconds=hour_s, normalLoad=normal, burstOfEight=sorted(burst_rows, key=lambda r: r["arrivalS"]),
                activityMix="after submitting, each trader polls its job and keeps using chart pages, Journal/Analytics reads and save/resume at the driver's think-time (see http_driver.py)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schedule-out", type=Path)
    ap.add_argument("--seed", type=int, default=20261115)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    plan = dict(feasibility=feasibility(workers=args.workers), schedule=schedule(args.seed))
    if args.schedule_out:
        args.schedule_out.write_text(json.dumps(plan, indent=1))
    print(json.dumps(plan["feasibility"], indent=1))
    return 2 if plan["feasibility"]["verdict"] != "FEASIBLE_UNDER_CONTRACT" else 0


if __name__ == "__main__":
    sys.exit(main())
