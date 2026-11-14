# Dual Engine Challenge V1 — Linux VPS measurements (Claude side), 2026-11-14

Branch `claude/dual-engine-v1-20261114`. Authorization: owner addendum of 2026-11-14 in `AGENTS.md`.
Host: Ubuntu 24.04, 6 vCPU, 15.6 GiB RAM, no swap, NVMe. This IS the target-class host (6 vCPU / 16 GiB).
Toolchain (user-space, no sudo): Python 3.13.18, PostgreSQL 17.12 (micromamba), Node 22.23.5, numpy 2.5.4, pyarrow 26.0.0.

**Data: every number below is SYNTHETIC.** No EURUSD file was on the VPS, so no real or rights-unknown data was used.
Synthetic source = `ohlc/gen_synth.py` (seeded random-walk mid, fixed spread, weekday sessions, equal timestamps), 1,444,646 ticks per month, same size as the earlier real month.
Absolute numbers therefore describe this code on this host, not market behaviour.

## What was NOT measured (read first)
- **No side-by-side with the Codex engine.** Codex's engine code was not available on this branch; the OHLC rows are the Claude candidate only. The product cohort rows are the Codex-built product baseline (replay/queue/worker) and do **not** include the Claude chart path.
- The OHLC seam (`claude_ohlc_seam.py`) was proven by tests against the oracle and the frozen frontend validator, but it was **off** during the browser cohorts, so there is no browser time-to-first-chart with the Claude objects.
- Cohorts 1, 2, 5, 10 ran **once each** (no median/range across repeats). Cohorts 20 and 50 were **not run**: the cohort-10 run peaked at 2.8 GiB of the 4 GiB cgroup (70%) and 11.9 GiB MemAvailable minimum, and memory grows roughly linearly with browsers, so cohort 20 would exceed the 80% stop line of the addendum.
- Real R2: **not run** (no credentials injected). `r2_acceptance.py` refuses without them and prints `SIMULATION_ONLY`; its logic is tested only against an in-memory S3 fake. The adapter is still prototype-only.
- Google login and Midtrans: not exercised (keys not present, by design).
- PG WAL, R2 PUT/GET/LIST on a real bucket, browser heap/fps, one-year oracle equality: not measured.

## A. OHLC materialisation (Claude engine, 9 timeframes, MID per tick) — 5 repeats, median
| Gate | Ticks | Wall s (range) | CPU s | Peak RSS MB | Output bytes | Oracle equality |
|---|---:|---|---:|---:|---:|---|
| G0 | 2,048 | 0.016 (0.014-0.035) | 0.023 | 119.6 | 15,772 | IDENTICAL |
| G1 | 65,536 | 0.027 (0.024-0.027) | 0.034 | 123.8 | 63,189 | IDENTICAL |
| G2 | 262,144 | 0.061 (0.060-0.066) | 0.079 | 127.6 | 204,259 | IDENTICAL |
| G3 | 1,000,000 | 0.186 (0.181-0.200) | 0.248 | 137.2 | 730,737 | IDENTICAL |
| G4 | 1,444,646 | 0.286 (0.275-0.294) | 0.374 | 157.6 | 1,049,001 | IDENTICAL |
| G5 | 3 x 1,444,646 | 0.816 (clean run, 1 repeat) | 1.094 | 157.3 | 3,282,093 | IDENTICAL (3 months, oracle run separately) |
| G6 | 12 x 1,444,646 | 3.076 (1 repeat) | 3.963 | 200.7 | 12,089,139 | NOT_RUN (oracle needs ~27 min per year here) |

Per instrument-month: 10 objects, 10 PUT (+10 HEAD for the immutability check). One year = 120 PUTs, 12.1 MB. RSS includes ~68-136 MB interpreter and library baseline.
The independent oracle took 134.7 s for G4 on this host; it is a reference, not a candidate.

## B. Serving (HTTP loopback, local object-store SIMULATION, 9 timeframes x first page 512 + page 1000)
| Phase | Requests | p50 ms | p95 ms | p99 ms | Mean payload B | Store GETs |
|---|---:|---:|---:|---:|---:|---:|
| cold, late in month | 18 | 3.52 | 69.76 (first request) | 69.76 | 27,685 | 10 (1.05 MB) |
| warm, late in month | 360 | 2.72 | 4.78 | 5.96 | 27,685 | 0 |
Server plus loopback only. Not browser time.

## C. Product baseline cohorts (real browsers, real API, PostgreSQL 17, 2 workers, auth limit 30/min, cgroup 4 GiB / 4 CPU)
Journey per user: register, verify, login, method, session, order with receipt, jump to entry/exit, journal and analytics, logout/login resume. Raw reports: `docs/benchmarks/vps-cohorts/product_cohort_N.json`.

| Cohort | Journeys PASS | Closed trades | Busy 429/503 | cgroup mem peak | Service RSS peak | Browsers RSS peak (sum) | MemAvailable min | PG queue max q/run |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1/1 | 1 | 0 | 0.60 GiB | 298 MiB | 886 MiB | 13.8 GiB | 1 / 1 |
| 2 | 2/2 | 2 | 0 | 0.86 GiB | 441 MiB | 1.43 GiB | 13.5 GiB | 1 / 2 |
| 5 | 5/5 | 5 | 0 | 1.64 GiB | 460 MiB | 3.56 GiB | 12.7 GiB | 3 / 2 |
| 10 | 10/10 | 10 | 0 | 2.61 GiB | 473 MiB | 6.68 GiB | 11.9 GiB | 6 / 2 |

API latency, ms (p50 / p95), selected write routes `POST /research/...`:
| Route | c1 | c2 | c5 | c10 |
|---|---|---|---|---|
| sessions (create) | 49 / 49 | 56 / 63 | 99 / 122 | 88 / 229 |
| sessions/{id}/view | 47 / 54 | 54 / 79 | 85 / 236 | 98 / 268 |
| sessions/{id}/jump-next-event | 46 / 48 | 53 / 68 | 79 / 295 | 135 / 323 |
| sessions/{id}/confirm | 88 / 103 | 90 / 93 | 147 / 295 | 187 / 359 |
Cohort 10 p99 for `view` was 316 ms, for `confirm` 361 ms. PG round trip p99: 18 / 22 / 128 / 105 ms for cohorts 1 / 2 / 5 / 10. Database growth 0.8-1.9 MB. Zero failures, zero swap, CPU throttling present only in cohorts 2-10 (small).
Cohort 10 hold time was 227 s versus 37 s at cohort 5: the 10-user run paces auth starts (2.1 s apart) to stay under the 30/min limit, so hold time is partly pacing, not only load.

## D. Findings that changed code
- The seam's first draft produced prices 10x too large (decimal digit off-by-one); the oracle-equality test caught it before anything was served. Fixed in `claude_ohlc_seam.py`.
- The browser harness could not start on this host: Chromium's sandbox is blocked by AppArmor (`apparmor_restrict_unprivileged_userns=1`) and the host has no fonts/libs. Fix, all user-space and opt-in: libraries and fonts from conda-forge, and `RIKSORA_QA_NO_SANDBOX=1` honoured by the two harness `.mjs` files (default behaviour unchanged). Used only against the harness's own local app on 127.0.0.1; do not use it for any external page.

## Claim labels
- **Proven (this host, synthetic data):** engine equals the oracle for G0-G5; seam output equals the oracle for nine timeframes and is accepted by the frozen frontend validator; product journeys PASS at 1/2/5/10 concurrent real-browser users with zero failures; Google and Midtrans report not configured and Google endpoints answer 404.
- **Hypothesis:** the same behaviour on real EURUSD, at 16 instruments x 34 months, and above 10 traders.
- **Prototype only:** the S3/R2 adapter and `r2_acceptance.py`; the object store here is a local directory.
- **Needs production-like acceptance:** real R2 counts and egress, Claude objects in the browser path, Codex side-by-side on the same oracle, load above 10, real-data rights.

## E. Follow-up (2026-11-14): 3 repeats, cohort 20, seam-on run — all SYNTHETIC, same host
Raw reports: `docs/benchmarks/vps-cohorts/repeats/`. Same harness and settings as section C (2 workers, auth limit 30/min, real Chromium per trader, cgroup 4 GiB / 400% CPU for cohorts 1-10).
Guard: host MemAvailable < 20% of RAM kills the run (never tripped); harness gates (MemAvailable >= 10 GiB, disk, no swap) unchanged.

### E1. Repeats (3 runs per cohort, 12/12 PASS, 0 busy 429/503). Median (min-max)
| Cohort | Hold s | cgroup mem peak GiB | Host MemAvailable min GiB | PG max queued | cgroup CPU cores avg | Worst per-route p99 ms |
|---:|---|---|---|---:|---|---|
| 1 | 23.95 (23.68-23.96) | 0.61 (0.60-0.63) | 13.87 (13.67-13.88) | 1 | 0.71 | 127 (127-143) |
| 2 | 24.71 (24.56-25.68) | 0.85 (0.84-0.87) | 13.65 (13.35-13.65) | 2 | 1.29 | 212 (197-251) |
| 5 | 31.19 (30.51-31.28) | 1.69 (1.67-1.70) | 12.79 (12.55-12.80) | 3 | 2.43 | 546 (543-593) |
| 10 | 226.56 (226.31-227.16) | 2.59 (2.58-2.61) | 11.91 (11.75-11.93) | 7 | 0.81 | 641 (480-685) |
Cohort 10 hold time and CPU average are dominated by auth pacing (30/min limit), not by compute load. The worst-route p99 is the journal pages route.

### E2. Cohort 20 — FAILED twice, recorded as NOT PASSED
Harness caps the cgroup at 5 GiB, so cohort 20 ran with MemoryMax=5G (cohort 10 peaked at 2.6 GiB; roughly linear growth predicts ~5 GiB).
- Run 1: 19/20 reached the last step; one trader's UI timed out (30 s, `logout_resume`, "My Methods" heading). No OOM, no resource gate trip. `BROWSER_JOURNEY_FAILED`.
- Run 2: harness stop gate `CAPACITY_RESOURCE_STOP` (MemAvailable below the existing 10 GiB gate).
Cohort 50 was not attempted (prior gate failed). No gate or timeout was changed to pass.

### E3. Seam-on cohort 5
`BTL_CLAUDE_OHLC_ROOT` set with a synthetic 2019-12 store: cohort 5 PASS, but **no object in the store was read** (atime unchanged): the browser gate journey never requests past-chart history, so this run does NOT measure the Claude chart path in the browser. Only proof: enabling the seam does not break the journey. Browser time-to-first-chart with Claude objects remains NOT MEASURED.

### E4. Capacity statement (this host, synthetic, product baseline, label: measured on real browsers, needs production-like acceptance)
Proven: 10 concurrent active traders, 3/3 repeat PASS, no failures, memory peak 2.6 GiB, MemAvailable min 11.8 GiB.
Not proven / failed: 20 (2 of 2 attempts failed against existing gates). So the proven ceiling here is 10, the upper limit is between 10 and 20 under the existing gates. Not inferred: real-market data, longer sessions, the Claude chart path, sustained (not 1-journey) activity, real R2.
