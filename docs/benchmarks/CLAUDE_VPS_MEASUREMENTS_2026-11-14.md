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

## F. Server-side capacity with an HTTP driver (no browsers) — SYNTHETIC, same host, product baseline
Why: in section C/E the Chromium generators (about 7 GB RSS at cohort 10) dominate memory/CPU, so "10 pass / 20 fail" described the generator. Here each trader is an HTTP client replaying the API journey that one real browser trader performed (recorded by the opt-in `RIKSORA_QA_RECORD_API` hook; template `backend/tools/claude_exp/stack/api_journey_template.json`, 38 calls, one closed trade; `totalOrders` checked per cycle). Path: API -> PostgreSQL 17 durable queue (admission 16 global / 2 per user, TTL 60 s) -> native worker -> synthetic Monthly Parquet (2,048-tick fixture) -> receipt -> journal. Code: `backend/tools/claude_exp/stack/http_driver.py`, `frontend/tests/http_load_cohort.py`, opt-in `RIKSORA_QA_HTTP_DRIVER=1`.
Settings: 3 full journeys per trader, 1 s think time, 0.3 s start stagger, auth IP limit 1200 and a distinct X-Forwarded-For per trader (trusted-proxy emulation; all synthetic traders otherwise share 127.0.0.1), busy refusals retried exactly as the frontend client does. cgroup 4 GiB / 400% CPU. Gates: MemAvailable >= 10 GiB, disk, no swap, host CPU > 80% for 5 s (never tripped).
LIMITS: the fixture is tiny, so worker cost per job is far below a real-month session: these are UPPER bounds for product capacity. Claude OHLC/R2 path not involved.

### F1. 2 workers (product default)
| Traders | Journeys done | Failed traders | Busy refusals (QUEUE_CAPACITY) | Throughput journeys/min | Job end-to-end p95 (max) s | Queue max q / oldest wait s | Host CPU p95 / max % | cgroup mem GiB |
|---:|---|---:|---:|---:|---|---|---|---:|
| 1 | 3/3 | 0 | 0 | 1.9 | 2.8 (2.8) | 1 / 0.2 | 12 / 21 | 0.46 |
| 2 | 6/6 | 0 | 0 | 3.7 | 3.0 (3.0) | 1 / 0.1 | 20 / 34 | 0.46 |
| 5 | 15/15 | 0 | 0 | 9.2 | 5.2 (5.2) | 2 / 1.7 | 34 / 45 | 0.47 |
| 10 (3 runs) | 30/30 each | 0 | 0 | 14.8 / 15.7 / 15.5 | 5.2 (5.4) | 6-7 / 3.4-3.8 | 41-42 / 48-50 | 0.46-0.48 |
| 20 (2 valid runs) | 55/60, 59/60 | 3, 1 | 9, 17 (recovered) | 18.0 / 19.2 | 8-11 (11-14) | 16 / 9.9-10.6 | 50-52 / 58 | 0.46 |
| 50 (1 run) | 142/150 | 3 | 7,858 (2 unrecovered) | 18.2 | 25 (52) | 16 / 23.3 | 67 / 72 | 0.50 |
The first cohort-20 attempt (`c20_invalid_stale_connection_bug.json`) is INVALID: a driver bug (reused idle keep-alive connection), fixed by one reconnect, as a browser does.
Failures at 20/50 are `poll:404` (an accepted job no longer found when polled) and `submit:429` after retries are exhausted. Likely cause (code reading, not proven): `cloud/queue.py:245` deletes finished jobs beyond the 15 newest, globally, at every submit, so an owner can poll after its finished job was pruned.
Throughput stops growing at about 18-19 journeys/min from 20 traders onward while CPU p95 is 50-67% and memory 0.5 GiB: the limit is worker slots + queue admission (16), not RAM/CPU.

### F2. Worker count  (3/4-worker parts INVALID — see F5)
- 4 workers (addendum maximum), cgroup 4 CPU: WORSE. Cohort 20: 58/60, 11.1 journeys/min, job max 93 s, `RECONCILE_REQUIRED`, CPU throttled 0.48 s; cohort 50: 126/150, 8 failed traders (`poll:404`, `FAILED`, `RECONCILE_REQUIRED`), CPU throttled 10.7 s, jobs RUNNING up to 38 with 4 workers (leases lost). Hypothesis: native workers + API + PostgreSQL + driver exceed the 4-CPU cgroup, delaying the API-process heartbeat thread (5 s, lease 30 s). Not isolated.
- 1 worker, cohorts 1/5/10: PASS 3/3, 5/5... all journeys done; at 10 traders 13.0 journeys/min, queue 8, oldest wait 9.6 s. cgroup CPU (whole stack: API + worker + PostgreSQL + driver) 0.20 / 0.66 / 1.02 cores = 3.4 / 11.1 / 16.9 % of 6 vCPU. API process incl. live worker slot 0.10 / 0.36 / 0.56 cores; PostgreSQL 0.01-0.03 cores (CPU of exited per-job native processes is not included, so the process figures are lower bounds). 2 workers at 10 traders: whole stack 1.5 cores (25%).

### F3. Capacity statement (HTTP driver, this host, synthetic tiny fixture) — UPPER BOUND, needs production-like acceptance
- Clean (0 failures, 0 busy refusals, journey cycle p95 about 40 s): up to 10 active traders with 2 workers, 3/3 repeats.
- Degraded but functional: 20 (1-3 traders per run hit `poll:404`, queue full, job waits 10 s).
- Saturated: 50 (throughput flat, 7,858 busy refusals, waits 23-52 s).
- Server is not CPU/RAM-limited here; it is limited by 2 worker slots and the frozen queue limits. More workers did not help on 4 CPUs.

### F4. [INVALID — HARNESS ARTIFACT, superseded by F5] 3 and 4 workers with the full 6-CPU cgroup
cgroup CPUQuota 600% (harness maximum), memory 4 GiB. CPU throttling was 0 in all four runs and host CPU p95 stayed 43-64% (max 79%), yet more workers still did not help.
| Workers | Traders | Journeys | Failed traders | Throughput journeys/min | Job p95 / max s | Max RUNNING rows | Host CPU p95/max % |
|---:|---:|---|---:|---:|---|---:|---|
| 2 (F1, 4 CPU) | 20 | 55/60, 59/60 | 3, 1 | 18.0 / 19.2 | 8-11 / 11-14 | 2 | 50-52 / 58 |
| 3 | 20 | 60/60 | 0 | 13.6 | 33 / 65 | 16 | 47 / 62 |
| 4 | 20 | 58/60 | 1 | 11.0 | 33 / 91 | 17 | 43 / 57 |
| 2 (F1, 4 CPU) | 50 | 142/150 | 3 | 18.2 | 25 / 52 | 2 | 67 / 72 |
| 3 | 50 | 140/150 | 4 | 20.0 | 42 / 94 | 24 | 64 / 76 |
| 4 | 50 | 135/150 | 6 | 17.0 | 63 / 94 | 40 | 62 / 79 |
Observed: with 3-4 workers job end-to-end times cluster around 33 s (the 30 s native deadline/lease plus polling) and RUNNING rows exceed the worker count (16-40 RUNNING with 3-4 workers), with `RECONCILE_REQUIRED` (a queued mutating job passing its 60 s TTL), `FAILED` and `poll:404`. Throughput at 20 traders is LOWER with 3-4 workers than with 2. Cause not identified (not CPU, not memory); needs a code-level investigation of the worker/lease path in `cloud/queue.py` and `cloud/worker.py` (not changed here: frozen limits). Practical result on this host and fixture: 2 workers is the best-measured setting; 3 gives at most a marginal throughput gain at 50 traders with more failures; 4 is worse.


## F5. CORRECTION: the 3/4-worker results in F2/F4 were a harness mis-configuration, not a product defect
Cause (proved by trace, `trace_invalid_w3_slots_mismatch.jsonl`): the harness `--worker-count N` only patched `cloud.queue.WORKERS`, while the native slot pool `cloud.worker._slots` (and its exchange thread pool) is sized at import from `BTL_RESEARCH_WORKERS` (default 2). With N=3/4 there were N queue loops but only 2 native slots, so the 3rd/4th concurrent job raised `RuntimeError: Native worker slots unavailable` (66 of 480 claims) AFTER the claim, leaving the job RUNNING until the 30 s lease expired. That produced the ~33 s job times, the RUNNING rows above the worker count and the RECONCILE_REQUIRED/FAILED states. The earlier statements "more workers is worse", "2 is best" and "cause not CPU" are WITHDRAWN. The 2-worker and 1-worker results are unaffected (pool size matched). Safeguard added: `http_load_cohort.py` now refuses to run (HARNESS_WORKER_POOL_MISMATCH) unless queue workers, native slots and exchange threads are equal; workers are set with the product variable `BTL_RESEARCH_WORKERS`.

### F5a. Correct pools, 6-CPU cgroup (4 GiB), HTTP driver, 3 journeys/trader, 20 traders
| Workers | Journeys done | Failed traders | Throughput journeys/min | Job p95 s (max) | Max RUNNING | Host CPU p95 / max % |
|---:|---|---:|---:|---|---:|---|
| 2 (F1, 4-CPU cgroup) | 55/60, 59/60 | 3, 1 | 18.0 / 19.2 | 8-11 (11-14) | 2 | 50-52 / 58 |
| 3 | 51/60 | 4 | 23.2 | 5.2 (8.1) | 3 | 69 / 82 |
| 4 | 47/60, 50/60 | 5, 4 | 24.2 / 24.6 | 3.1-3.3 (5.4) | 4 | 76 / 88 |
50 traders: 3 workers 120/150 (15 failed, 2,378 QUEUE_CAPACITY + 16 SERVICE_BUSY refusals, 25.5 journeys/min, host CPU p95 80 / max 88); 4 workers: stopped by the 80% host CPU gate (`CAPACITY_CPU_GATE_80PCT`), not a completed run.
More workers DO raise throughput (+22% at 3, +27% at 4 versus 2 at 20 traders) and shorten job waits, as expected. They also push host CPU to 76-88%, i.e. the addendum's 80% line, which is the practical limit of this host.

### F5b. Remaining failure `poll:404` is explained by finished-job retention (verified, product limit)
`cloud/queue.py:245` keeps only the 15 newest finished jobs globally (RETAINED_LIMIT 32 - GLOBAL_LIMIT 16 - 1). In the 4-worker run the count of finished job rows stayed at 15-17 (max 22) for 119 one-second samples (`trace_w4_prune_check.jsonl`). A trader that polls after 15 other jobs finished finds its result deleted (HTTP 404). The faster the pool completes jobs, the shorter the retention window (about 15 jobs / (jobs per second)), so failures appear as throughput rises (20 traders: 1-5 failed traders in every configuration). This is a design limit in a frozen contract, not changed here. Implication: the concurrent-trader ceiling with the current retention rule is set by completion rate x poll delay, not by CPU/RAM.

## G. Full-trader capacity: product journey + 9 timeframes x 5,000-candle chart history, one host — SYNTHETIC
What one simulated trader does: website journey through API/PostgreSQL durable queue/native worker/Parquet (section F journey, 3 journeys, 1 s think time) AND, at the same time, the chart: at session open 9 timeframes (M1..D1) each loaded as first page 512 then older pages of 1,000 until >= 5,000 candles (about 6 requests per timeframe, 54 per open), then a forming-candle poll about every 2 s, a timeframe switch every 15 s, and a cursor advance (+60 s) after every Jump. Candles before the start point come from precomputed OHLC objects; the forming candle after the start point is rebuilt from M1 bars plus the tick prefix of the current minute, never future ticks (`ohlc/service.py`, no-lookahead tests unchanged). The chart service runs as a separate process (`stack/chart_server.py`), prototype auth (token map), local-directory object store = SIMULATION of R2 (no network, no R2 cost).
Data: synthetic EURUSD-like, 237 months (2006-06 .. 2026-02, 30,000 ticks per month, 7.11 M ticks), start point 2026-01-01 00:00 UTC. Store: 2,370 objects, 186.8 MB (about 0.79 MB per instrument-month at this tick density; the earlier real-density month was 1.05-1.14 MB). History depth reached: M1..H4 5,512 candles per timeframe, D1 5,110 (needs about 19 years of weekdays). Pre-2023 history would be OHLC-only in the product; here it is generated from synthetic ticks for convenience.
Settings: 3 workers (`BTL_RESEARCH_WORKERS=3`, pool verified) unless stated, cgroup 6 CPU / 4 GiB, auth IP limit 1200 with distinct X-Forwarded-For per trader, driver parses only paging fields of chart pages (the browser would decode candles; driver CPU 1-6 s per run). Gates: MemAvailable >= 10 GiB, disk, no swap, host CPU > 80% for 5 s.
Raw: `docs/benchmarks/vps-cohorts/combined/`.

| Traders | Workers | Result | Failed traders | Chart errors | Busy refusals | Journeys/min | Product job p95 s | Chart 9-TF open p50 / p95 s | Chart page p95 ms (first512 / older1000) | Host CPU p50 / p95 / max % | Queue max / oldest wait s |
|---:|---:|---|---:|---:|---:|---:|---:|---|---|---|---|
| 1 | 3 | PASS (1 journey) | 0 | 0 | 0 | 2 | 1.3 | 1.0 / 1.0 | 237 / 76 | - | 1 / 0.2 |
| 5 | 3 | PASS | 0 | 0 | 0 | 8.9 | - | 1.8 / 2.0 | 102 / 153 | - / 44 / 57 | 2 / 0.4 |
| 10 | 3 | PASS (2 runs) | 0 | 0 | 0 | 15.6-15.9 | 3.0-3.1 | 5.2-5.3 / 6.2-6.4 | 183-365 / 477-486 | 37 / 58-61 / 65-69 | 5-6 / 1.7 |
| 10 | 2 | PASS | 0 | 0 | 0 | 15.2 | - | 6.3 / 7.5 | 268 / 408 | 32 / 53 / 56 | 7 / 4.2 |
| 20 | 3 | FAIL (2 of 20 traders) | 2 | 0 | 0 | 21.8 | 5.4-8.1 | 9.5 / 11.0 | 270 / 528 | 56 / 72 / 93 | 15 / 6.0 |
| 20 | 2 | FAIL (3 of 20 traders) | 3 | 0 | 7 | 17.0 | 8-11 | 11.2 / 12.5 | 244 / 423 | 42 / 63 / 84 | 16 / 10.3 |
| 20 | 4 | STOPPED by 80% CPU gate at 15 s | - | - | - | - | - | - | - | 62 / 97 / 97 | - |
| 50 | 3 | STOPPED by 80% CPU gate at 15 s | - | - | - | - | - | - | - | 65 / 93 / 93 | - |
(The first combined series, with a heavier JSON-parsing generator, gave the same pass/fail picture: 5 and 10 PASS, 20 and 50 stopped or failed.)

Findings
1. VALID, PROVEN capacity on this host (synthetic, tiny 2,048-tick replay fixture): 10 simultaneously active full-experience traders, 2 or 3 workers, zero failures, zero chart errors, zero busy refusals, host CPU p95 53-61%, memory 0.5-0.6 GiB, chart page p95 under 0.5 s, 9-timeframe chart open about 5-7 s when all 10 open at once.
2. 20 traders is NOT valid: 2-3 traders per run lose a job result (`poll:404`, the 15-finished-job retention rule at `cloud/queue.py:245`, verified in section F5b), the queue reaches its 16 limit, and the CPU peak reaches 93%.
3. The CPU peak is the session-open burst: opening 9 timeframes x 5,000 candles costs about 2 CPU-seconds on the single-process Python chart service (20 CPU-s for 10 opens; about 1.3 cores for the first 15 s at 50 traders). Steady state is cheap (forming-candle poll p50 4-5 ms, p95 under 12 ms). Staggered opens, a multi-process chart service or caching ready pages would remove most of the burst; none tested.
4. Cost per full journey (1 closed trade, 38 API calls, charts open): about 5.8 CPU-seconds server-side (173 s for 30 journeys at 10 traders: API + workers + chart service; PostgreSQL 0.19 s), PostgreSQL growth about 0.1-0.2 MB per journey. It is an upper bound per trade because session creation amortizes over more trades; 120 trades per Session was NOT measured.
5. D1 needs 5,000 candles = about 19 years = about 235 monthly objects: with the object cache of 64 each D1 open touches many objects. On real R2 (tens of ms per GET) cache the OHLC objects on the VPS SSD (about 190 MB per instrument at this density, about 1.1 MB x 237 for real density).
NOT measured: real R2 latency/cost, real browsers with the Claude chart (the frontend still uses the frozen 512-bar previous-month context), real-month-size replay sessions (worker RSS and CPU per large Session), 120-trade Sessions, 12+ instruments, cohort sizes between 10 and 20, any cohort at 50 beyond the first 15 s.

## H. Why more workers do not simply add capacity on this 6-vCPU host (diagnosis) — SYNTHETIC
Method: per-role CPU/RSS sampled every second from the cgroup (`cpuByRole`), HTTP driver, 20 traders, 3 journeys each, client patient (busy refusals retried up to about 5 min) with client-side recovery of pruned job results (`poll:404`, resubmit with the same job/command id; NOT current frontend behaviour; counts are in `retentionRecoveries`). Raw: `docs/benchmarks/vps-cohorts/diagnosis/`.

### H1. Product only, worker pool 2 / 3 / 4 (pool verified), 6-CPU cgroup
| Workers | Journeys ok | Journeys/min | Native worker CPU avg / p95 / max (cores) | API process CPU avg / p95 / max | PostgreSQL avg | Host CPU p50 / p95 / max % | Queue max / oldest wait s |
|---:|---|---:|---|---|---:|---|---|
| 2 | 60/60 | 18.9 | 0.91 / 1.67 / 1.89 | 0.55 / 0.99 / 1.22 | 0.06 | 42 / 57 / 67 | saturated (16 / ~10 s in earlier runs) |
| 3 | 60/60 | 22.8 | 1.32 / 2.49 / 2.66 | 0.62 / 1.05 / 1.17 | 0.07 | 51 / 69 / 77 | 15 / 6 |
| 4 | 60/60 | 27.5 | 1.64 / 3.05 / 4.04 | 0.70 / 1.02 / 1.24 | 0.07 | 61 / 78 / 95 | 12 / 3.7 |
With chart (2 workers): 60/60, 19.1 journeys/min, chart service process avg 0.26 / p95 1.46 / max 1.82 cores, host CPU 45 / 64 / 83 %.
Readings: (a) each native worker averages only about 0.4 core (about 40% duty) but bursts to about 1 core, so N workers burst to about N cores at the same moment; (b) PostgreSQL is negligible (0.06-0.07 core); (c) the API process (one Python process) reaches about 1 core at p95 in every configuration; (d) at 4 workers the 6-vCPU host reaches 78-95% CPU at the burst peaks, i.e. the owner's 80% stop line, with API about 1 + workers about 3.5 + chart burst up to 1.8 + OS.

### H2. Several API processes (extra instances share the same PostgreSQL queue; worker slots are global advisory locks, so total running jobs stay <= pool size), 4 workers, 20 traders, 1.5 s arrival spacing
| API processes | Result | Journeys/min | API process CPU p95 (each) | Native worker CPU p95 | Host CPU p95 / max % |
|---:|---|---:|---|---:|---|
| 1 | 57/60 (1 trader failed, 2 SERVICE_BUSY); an earlier 0.3 s-spacing run 60/60, 27.9 | 25.7 | 0.90 | 2.76 | 77 / 86 |
| 2 | 60/60, no recoveries needed | 26.8 | 0.53 / 0.55 | 3.21 | 88 / 91 |
| 3 | stopped by the 80% CPU gate after 35 s | - | 0.30 / 0.71 | 3.12 | 89 / 91 |
Two API processes split the API load (about 0.5 core each instead of 0.9) and worked correctly (zero failures), but throughput did not rise: at 20 traders with 4 workers the run is bounded by trader pacing (1 s think time, about 34 s per journey => about 35 journeys/min ceiling) rather than by capacity, and the queue is no longer saturated (oldest wait 1.4 s). So the claim "the API process is the bottleneck" is NOT proven; the single-process 1-core ceiling is a latent limit that only matters at higher load. With 2-3 API processes every extra instance also cold-starts its own native slots and re-admits the pinned source on first use (hypothesis, not isolated), which adds a CPU burst at the start that trips the 80% gate.
Single runs per cell; no confidence ranges.

### H3. Answer: spec vs design
- Hard design limit: the pool is 1-4 slots (`worker_config.MAX_WORKER_COUNT = 4`, global advisory-lock slots 310..313). More than 4 concurrent jobs needs a product change (contract), not hardware.
- Spec limit on this host, with the 80% stop line: 6 vCPU cannot absorb 4 native workers bursting (about 1 core each) + API (about 1) + chart opens (up to about 1.8) + PostgreSQL + OS. Practical setting here: 2-3 workers; 4 only if the CPU gate is relaxed or the host has about 8+ vCPU (estimate: 4 + 1 + 1 + 0.3 + 0.3 + headroom = about 7-8 vCPU).
- Software items that would raise the ceiling without more CPU (not implemented, not measured): warm all native slots at startup (only slot 0 is warmed), a multi-process chart service or cached ready pages (open burst about 2 CPU-s per trader), and a finished-job retention that cannot prune results before their owner polls (`cloud/queue.py:245`).
- Target of 100 simultaneous traders was attempted and NOT reached inside the gates: 3 workers 30 traders 58/60 journeys (1 trader failed); 50/75/100 traders and 2-worker 50 traders were stopped by the 80% CPU gate in the first 35 s (no completed run). 15 simultaneous (same instant) full-experience traders passed 3/3; 18 failed.
