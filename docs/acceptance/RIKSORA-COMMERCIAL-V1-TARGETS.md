# RIKSORA Commercial V1 — Capacity Target & Definition of Done

> Owner target baseline: 2026-11-13. Status: TARGET APPROVED FOR PLANNING; **NOT ACCEPTED / NOT LAUNCH-READY**.
>
> This is a finite *release acceptance specification*, not a second roadmap, permission to alter frozen contracts, permission to use real market data, or authorization for deployment, charging, merge, or VPS access.
> The long-term plan remains [ROADMAP.md](../ROADMAP.md); operational authorization remains [AI_CONTEXT/04_CURRENT_PHASE.md](../../AI_CONTEXT/04_CURRENT_PHASE.md), safety rules remain [AGENTS.md](../../AGENTS.md), and implementation evidence belongs to the existing [V1 Integration Register](RIKSORA-V1-FREEZE-INTEGRATION-REGISTER-20261108.md).

## 1. Exact product promise

RIKSORA Commercial V1 is a hosted, authenticated, multi-tenant tick-level *historical simulation/backtesting* product: Method → Session → chart/replay → reviewed/confirmed planned order or supported quick execution → deterministic tick execution → immutable receipt → Journal/Analytics → logout/login/resume. Simulated fills are not live/broker fills, and uncertain tick chronology, missing coverage, unsupported conversion, or source qualification must be surfaced explicitly.

Do **not** advertise real-time brokerage, live execution, automated profitability, complete market realism, or validated market accuracy from synthetic QA evidence.

### Minimum supported SKU

- One instrument per Session; preserve existing canonical financial/provenance/no-lookahead contracts and supported trading modes.
- Intended launch catalog: 16 named instruments (AUDUSD, EURGBP, NZDUSD, USDCHF, AUDJPY, CADJPY, EURUSD, GBPUSD, NZDJPY, USDCAD, CHFJPY, EURJPY, EURNZD, GBPJPY, USDJPY, XAUUSD), with planned Jan 2023–Oct 2025 historical coverage (34 months × 16 = 544 instrument-months). Every advertised instrument-month requires verified qualified source, immutable manifest/hash, actual usable coverage, correct instrument precision and **documented commercial use/display/retention rights**; missing months must be disclosed or excluded. The historical catalog is a *target*, not a current inventory or rights assertion.
- If all 544 instrument-months cannot be qualified, the owner must explicitly approve a narrower and accurately described paid-Beta SKU **before** sales; no silent substitution with synthetic data.

## 2. Capacity target: one VPS, clear meaning of 'trader'

Deployment profile under test: 6 vCPU / 16 GiB RAM single VPS, with API, PostgreSQL and workers co-resident as proposed (verify actual topology). Codex/development processes may share the host; never assume six exclusive worker CPUs. `BTL_RESEARCH_WORKERS` now configures the bounded queue/native pool from 1 through 4, with default 2. The four-slot setting is configurable but remains a **target configuration**, not capacity acceptance evidence.

**V1 GO capacity target: 20 simultaneously active, independently authenticated traders, with a planned ratio of five active traders per each of four workers.**

Definitions (do not conflate):
- An **active trader** has a live authenticated product Session and performs UI/API work, potentially with a backtest submitted or queued. A trader is not a CPU core, and a 'five traders/worker' ratio does **not** mean five heavy backtests concurrently inside one worker.
- A **worker** executes no more than one admitted CPU-heavy native job at a time unless a separate correct and benchmarked design proves otherwise.
- **Heavy concurrent jobs** under the four-worker profile: up to four running at once, with bounded queued jobs. Admission, per-user limits, fairness, TTL, job deadline and lease recovery must be compatible with measured full-job/chunk duration and must never silently drop financial work.
- Capacity must be measured on the actual target VPS, not inferred from a local KVM, a single synthetic throughput number, or a sequential browser test.

**Normal-load acceptance workload:**
- 20 independent identities and Sessions, 60-minute coordinated real-browser/API test, external/separate load generator if feasible.
- Across the hour, each of 20 traders submits **one 262,144-tick financial-active backtest** (20 complete histories/hour in aggregate), staggered with a documented seeded arrival schedule. Each includes at least one true entry and exit via the canonical engine, committed receipt, Journal and Analytics, not a scanner-only job. No more than four heavy jobs should execute concurrently.
- During those jobs, all 20 keep using a representative mix of chart navigation, Method/Session, review/confirm, Journal/Analytics, polling, and save/resume; record operation mix and request rate.
- Repeat the full normal-load profile twice in independently reset runs with identical seed/configuration. A separate burst test submits eight financial-active jobs close together; queued jobs must remain visible, eventually finish or explicitly fail/reconcile, never disappear.
- Add a lower-cost 2,048-tick functional 20-browser journey to isolate UI/identity defects from heavy-engine throughput; this *alone* cannot pass the commercial-capacity gate.
- Test 1, 2, 3, and 4-worker profiles with a worker ceiling of one effective vCPU each. Choose the final worker count based on throughput, latency, database pressure and spare system resources. Four workers is the target, not a mandate to overcommit.

### Performance acceptance SLOs (candidate engineering contract, must be measured)

At the **20-trader normal workload**, in **both** independent runs:
- Interactive authenticated API endpoints (non-heavy requests) p95 <= 2.0 s and p99 <= 5.0 s.
- Async submit/status endpoints p95 <= 0.5 s and p99 <= 1.5 s; the response may be 'queued' with a durable ID.
- Each 262,144-tick *full financial-active history* job reaches durable terminal completion with p95 end-to-end <= 15 minutes, and normal-load queue wait p95 <= 5 minutes. Measure from submission, and report p50/p95/p99 of queue, execution, and full journey separately. If the current chunk/deadline model makes this impossible, record FAIL/BLOCKED; do not redefine 'full job' as a 30-second chunk.
- Burst-of-eight jobs: all receive durable accepted/explicitly refused outcomes, no hidden timeouts; any accepted jobs reach terminal state and are recoverable. Report waiting time rather than masking queue pressure.
- No unexplained 5xx, silent dropped jobs, duplicate financial results, or missing terminal status. Intentional bounded 429/SERVICE_BUSY is acceptable only if correctly surfaced and retry/recovery tested, with counts disclosed.
- No service OOM, swap-driven degradation, unsafe disk decline or safety-gate override; capture CPU, cgroup memory, per-worker RSS, PostgreSQL pressure, storage delta, queue depth, CPU throttling and **effective** affinity/quota/exclusivity. Retain the stricter applicable existing host runbook gates.

A launch capacity statement is allowed only as: "Passed 20 simultaneous active traders under the documented workload on the specified VPS", never "20 simultaneous full-history CPU jobs", "20 users forever", or "20 users for any dataset".

## 3. Correctness and reliability gates — zero-tolerance

**PASS only if all relevant evidence is reproducible:**
- Frozen canonical tick order/bid/ask, exact arithmetic, spread/cost/PnL, entry/SL/TP, partial close, no-lookahead, identical-time ambiguity, chronology/gap and uncertainty handling remain correct. SHA-256/canonical bytes, event head, state, immutable receipt, Journal and Analytics parity match current golden fixtures.
- Include at least one pending-order entry and SL/TP terminal fill in representative long workload; add separate mixed-order/stress fixtures so a single completed trade is not misrepresented as realistic activity.
- Two independent test cohorts complete 20/20 required product journeys (login, create/open Session, replay, entry/exit, receipt, Journal, Analytics, logout/login/resume), with tenant isolation.
- Cancellation, stale revision, idempotent retries, worker death before/after commit, lease recovery, queue FIFO/fairness, restart and cold resume all pass with **zero** duplicate committed financial receipts, lost committed results, cross-tenant access or unreconciled job.
- Regression/CI on the *final remote release-candidate SHA* succeeds: backend directed and broad relevant suites, actual browser E2E, Parquet/source/serializer, PostgreSQL migrations, finance golden, lint/build, and resource tests. A PASS on a parent SHA is insufficient.

## 3A. Timeframe-aware chart prehistory, indicator warm-up and causal paging (Commercial V1)

**This refines, and does NOT replace**, the prior owner-approved [Market Data Standard — Human-selected Beta chart prehistory (2026-10-19)](../MARKET_DATA_STANDARD.md#human-selected-beta-chart-prehistory--2026-10-19): **at least two calendar years of qualified, read-only OHLC prehistory before the Session trading start must be accessible to both Free and Pro** for each advertised eligible instrument, subject to actual verified coverage and honest gaps. A fixed initial display count is not a substitute for two calendar years of eligible historical availability. Tick execution authority remains independent from chart OHLC.

### User-visible behavior and defaults

1. **Initial chart viewport:** request/display the latest **up to 500 complete, causally available candles of the trader's selected chart timeframe**, strictly before the chosen initial backtest entry point. Do not fetch all two years into the browser at once; maintain an incremental, bounded chart page. If fewer than 500 exist within qualified history, show actual count and coverage limitation, never invent candles.
2. **Timeframe semantics:** '500 candles' means **500 bars in the active timeframe**, not 500 base M1 candles, not a constant elapsed number of minutes, and not a fixed number of ticks. Supported chart/replay-to timeframe choices observed in Product V1: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `D`; gate unsupported combinations explicitly rather than silently downgrading to another timeframe. Example: H1 → up to 500 one-hour bars; D → up to 500 completed daily bars. Exchange calendars, weekends, gaps, holidays and source session boundaries still apply.
3. **Indicator warm-up:** default initial computation budget of **up to 1,000 causally available bars in EACH indicator's required input timeframe**, fetched/calculated independently of the 500 visually shown, with versioned indicator parameters and explicit readiness status. 1,000 is a **default budget, not a guarantee that every indicator is converged**. Determine actual history requirements from each indicator (including longer EMA or multi-timeframe dependencies), and fetch additional verified prehistory *on demand* when needed and permitted, or display `INSUFFICIENT_HISTORY`/warming-up rather than inventing old bars or incorrectly claiming full readiness.
4. **Scroll left:** load older history incrementally, normally **500–1,000 bars per backward page in the requested timeframe**. Server enforces bounded size and cursor, stable ordering, immutable dataset/version, timezone/calendar/price-side provenance, consistent OHLC aggregation and clear insufficient-coverage signaling; avoid whole-history browser loads or one-provider-read per candle.
5. **Changing timeframe:** recalculate/obtain bars and indicator warm-up for the NEW timeframe using its own timeframe-specific candle count and cache identity. Preserve cursor/start boundary, drawings' TIME+PRICE anchors, chart state where appropriate, and every trading/financial state; do not make a timeframe switch rewrite committed financial execution or reveal future bars.
6. **No-lookahead and prior context:** before Session start, historical candles may inform analysis, drawing and indicator warm-up **without placing or settling trades**. At any replay cursor, show only candles that are fully closed and available by that cursor; the current forming candle may show only the already revealed portion, never its later high, low or close. Time bucket boundaries, gap policy, UTC/session timezone, price basis and deterministic aggregation must follow the [Market Data Standard](../MARKET_DATA_STANDARD.md). Chart OHLC **never** determines tick execution fills.
7. **Shared preprocessing and efficiency:** prefer immutable qualified OHLC sidecar / indexed cached timeframe aggregations derived with versioned rules from the appropriate authorized source, rather than repeatedly scanning/replaying millions of raw ticks for chart preload. Cache keys must include instrument, source dataset/version, side/basis, timeframe, aggregation version and available-time/cursor clipping. Cached *final* bars must not be served as future information to earlier replay cursors.

### Specific acceptance tests — all mandatory for chart-history GO

- At least **500 available closed bars** at Session start: assert exactly the right 500 contiguous-in-observed-series bars and correct timeframe, earliest/latest timestamps, price side, OHLC, UTC/session alignment and source gaps; separately test an honest <500 insufficient-history case.
- Deterministic fixtures for **M1, M5, H1 and D**, plus compatibility of all supported timeframe choices. For a common point in historical time, 500 bars at different timeframes are demonstrably different time spans. Test session/day boundaries, weekends, market gaps, year boundary and DST/timezone policies where relevant.
- Indicator warm-up requests up to 1,000 verified bars in indicator input timeframe independently of 500 displayed; test EMA200-style longer convergence, insufficient data/partially formed bars, optional additional history, and multi-timeframe indicators if supported. Indicator availability must never silently turn into an execution signal before its causal readiness.
- Paginate left 500–1,000 bars per bounded request, no duplicates/missing IDs across adjacent pages, stable ordering/cursors, no cross-dataset cache contamination, and reproducible candle aggregation.
- Switch M5 → H1 → M5 and verify correct candle count, indicator values, drawing anchors, Session time/revision, no-lookahead and immutable financial state/receipts.
- Simulate a replay cursor in the middle of an H1 candle: neither a cached closed H1 candle's future high/low/close nor any provider/index future-suffix capability may leak into chart/indicator/analysis.
- **Two-year qualified OHLC accessibility** is a separate gating test per advertised supported instrument, for Free and Pro, not satisfied solely by a successful 500-candle first page. Explicit PARTIAL/BLOCKED if qualified prehistory or commercial display rights are unavailable.
- During the 20-trader capacity test, measure the impact of concurrent initial 500-bar chart load, 1,000-bar warm-up, page-back and timeframe switching on API p95/p99, process RAM, object-store egress and CPU; do not count a trivial blank or cached fixture as full production acceptance.

**Implementation state (2026-11-13): TARGET RECORDED; NOT TESTED as Commercial V1 acceptance.** No code or protected dataset is changed by this specification.

## 4. Data, security, operations and paid-product gates

**Market data:** Each live advertised dataset has legally verified commercial processing/display and retention rights, immutable hashes, bounded loading, authentic coverage/quality and provenance; any missing/incomplete/ambiguous data is not silently treated as verified. Synthetic data remains visibly TEST ONLY and cannot substantiate commercial historical accuracy.

**Security:** HTTPS, authenticated user/workspace ownership and tenant isolation, rate limits, secret handling, safe Session boundaries, no raw card storage, audit logs, relevant abuse tests and sensitive-data protections. Independently test a user cannot access another user's Session, trades, dataset entitlements or receipts.

**Persistence/operations:** Restartable workers and correct long-job lease/deadline behavior, monitored queue depth/CPU/RAM/disk/latency, alerting on failed/stuck jobs and storage pressure, restore test from fresh backup, evidence of recovery objective (initial target RPO <=24h and RTO <=4h; revise only through explicit owner decision and disclosure). No production cutover without reviewed rollback steps.

**Billing:** Real entitlement enforcement by server, quota/reset consistency, provider-signed webhook verification, replay/idempotency, failure/cancellation/refund policy, and end-to-end sandbox checkout tests. A permitted low-value live charge/refund test on approved merchant configuration is required before collecting live customer payments. Price, currency, provider fees, tax/compliance, terms and privacy copy require owner approval. Never test real charges without explicit authorization.

**Product UX:** Desktop plus a defined mobile viewport complete critical flow; recoverable status for queued/rejected/failed jobs, truthful progress, explicit data limitations, no unexplained browser dead end.

**Economics:** Capture measured cost drivers (CPU-seconds per full job, memory, DB growth per Session/trade/job, object-storage/egress, payment fees, VPS charges); produce reproducible margin and break-even sensitivity scenarios for active users. Target initial commercially viable gross margin >=60% under the chosen paid tier and measured usage profile, subject to owner approval of pricing and real tariffs. If costs are unknown, this gate remains NOT VERIFIED; do not invent a per-customer cost. Existing approximately Rp300k/month VPS *planning budget* is not an independently verified total infrastructure price.

## 5. Final release decision

All gates must have explicit PASS / FAIL / BLOCKED / NOT TESTED with immutable evidence URL/path, exact commit SHA, host specs, source/dataset hashes, configuration, date, measured percentiles, sample counts and named owner approval.

**GO for limited paid Beta** requires:
1. Correctness/recovery/tenant security: PASS.
2. Data rights and specifically advertised catalog: PASS (or owner-approved explicitly narrower SKU).
3. 20-trader two-run capacity and SLOs on the real target VPS: PASS.
4. Backup/restore, monitoring and operational rollback: PASS.
5. Billing/entitlement and approved customer/legal terms: PASS.
6. Real economics and acceptable margin: PASS.
7. Final remote-SHA CI/E2E, owner review and explicit production/deployment/payment authorization: PASS.

Any missing critical item is **HOLD**, not a fractional 'percent complete' or permission to sell. Failed tests cannot be bypassed by lowering security, financial or resource gates. A narrower launch SKU or capacity claim requires explicit owner scope amendment; it must not inherit the full V1 claim.

## 6. Acceptance sequencing

A. Baseline and one-worker financial-active CPU/RAM/DB/queue measurements on representative prepared Monthly Parquet; isolate benchmark generator/storage-conversion time.

B. Harden configurable two-to-four worker pool without changing financial semantics; profile one-worker cohorts and control queue/lease/job deadline behavior, preserving existing limits until reviewed.

C. Controlled 5 → 10 → 15 → 20 real-browser trader cohorts; stop and report on safety, integrity or SLO failures. Test four-worker 20-user full profile twice plus burst. Do not extrapolate five active traders/worker as an observed fact before step C.

D. Finish data licensing/coverage, billing, security, backup, mobile/desktop acceptance and pricing validation; publish evidence in existing integration register/current phase, not a competing tracker.

E. Freeze release candidate, verify all final-SHA CI and gates, and obtain separate owner GO before any external launch.

### Current baseline, not acceptance

- Repository worker pool accepts `BTL_RESEARCH_WORKERS=1..4` (default 2); configuration wiring has unit coverage. Actual multi-worker capacity and four-slot resource safety remain unproven.
- Local synthetic real-browser ten-trader cohort has passed functional journeys, but older interactive p95/p99 exceeded candidate targets. A local 20-user cohort was blocked by host resource gate.
- 524,288-tick synthetic financial-active engine replay passed in local KVM with one closed trade, not an end-to-end long durable worker on target VPS.
- No 20-user / four-worker real-VPS capacity PASS, complete rights-qualified launch catalog, live billing evidence or verified Commercial V1 unit economics exists in this checkpoint.

### Local worker-capacity checkpoint (2026-11-12, continued)

This checkpoint is local Linux KVM synthetic software evidence only. It does not satisfy product browser, VPS, historical-data, or Commercial V1 capacity acceptance.

- Worker pool wiring: `BTL_RESEARCH_WORKERS=1..4`, default `2`; bounded queue worker count, native child slots, and exchange executor use the same parsed count. Invalid values fail closed. Configuration tests: 4/4 PASS. Real 2–4 worker load and resource safety: NOT TESTED.
- Authenticated API → PostgreSQL 16.15 durable queue/native child → canonical Monthly Parquet → financial reducer → durable receipt → CLOSED Journal → Analytics: PASS for 2,048 synthetic ticks. One identity/session, 34 queue jobs (create, quote setup, 32 bounded advances), one trade, ENTRY_FILL + EXIT_FILL, balance `10000.7`. Repeat confirm returned the same result. The harness invokes `queue.work_one` serially; the configured pool default was 2, and concurrent service-worker lifecycle/one-worker pool throughput was not tested.
- Fixture: `riksora-synthetic-financial-monthly-v1`, seed `20261112`, label `SYNTHETIC / TEST ONLY`; dataset version `d12c77000573eb1acce8e56b0297b6f3909cce2d066f44e246c450a61ca57d86`; source-member SHA-256 `1c8bb56a4a211129ce59ddffb5fb1e94bcf4b343f9cf276c6d9d3ad5ba8cf37f`; Parquet manifest SHA-256 `3629f511796ed1a7cb22c094afd053d984237063c45f8a269f449c2fa5ed57f`.
- Three initial 2,048-tick repeats plus a post-merge-commit verification now exist; they are not an optimization before/after. Runs 1–3 are detailed in the integration register. The fourth unbound run measured journey 11.958 s, worker CPU/wall 3.207/3.959 s, queue wait p50/p95/p99 11.103/15.504/15.570 ms over 34 jobs, child peak RSS 184,410,112 B, DB growth 876,544 B. All four used the same synthetic identity/hash and produced one CLOSED trade with identical retry-confirm behavior. One affinity-limited run pinned the API/test process and native child, not PostgreSQL; CPU 5 was not exclusive. These tiny-fixture repetitions do not establish heavy-job throughput or optimization ROI. `/proc` reported zero process `read_bytes`; physical disk I/O is not established. Endpoint-latency decomposition and browser-visible time: NOT TESTED.
- A serial durable-queue attempt at 65,536 ticks failed after 167.659 s with `REFUSED_RECOVERY_LIMIT` (`fixtureSteps`); a 16,320-tick probe also failed with that code after 109.060 s. The legacy fixture controller contract is `MAX_STEPS=256`, and `TickTimeline` stores each accepted advance target in its checkpoint. Splitting API work into durable queue jobs does not reset this same Session checkpoint. No limit was changed. Durable full-history completion at 65,536/131,072/262,144 ticks: BLOCKED by the frozen Session checkpoint budget; the 65,536 and 16,320 outcomes are FAIL for those attempted test runs, not data corruption or a successful full replay.
- Test harness now snapshots queue/worker metrics as each job completes because operational `research_jobs` retention is capped at 32. The retention policy was not changed. Focused regression: worker-pool config, queue contract, worker deadline, and synthetic financial fixture **37/37 PASS**. Real 2,048-tick journey **1/1 PASS**. The two larger attempts above **FAIL** at the step guard.
- Browser/UI journey, chart page/timeframe/warm-up, mixed multi-order workload, multi-trader 1/2/3/5 cohorts, actual 1–4 worker scaling, 262,144 full durable history, and actual target VPS: NOT TESTED or BLOCKED as stated. Qualified two-year chart prehistory remains BLOCKED on qualified source rights/coverage.

### Performance ROI decisions — local engine evidence only

These are engineering disposition decisions, **not durable-worker capacity claims**. Existing before/after figures are single measurements from earlier synthetic engine-only runs; the requested three-run same-workload confirmation is still required before attributing Commercial V1 capacity gains.

| Candidate | Decision | Measured CPU saved per synthetic 65,536-tick engine pass | Worker-capacity implication |
|---|---|---:|---|
| Verified one-row-group Parquet cache / avoid repeated decode and hash validation | RETEST | About 256.35 CPU-s versus the earlier uncached run (473.24 → 216.89 CPU-s including setup+replay; single run per side) | Theoretical 2.18× CPU-bound engine throughput only; durable queue/worker benefit is unmeasured. Keep the implementation pending repeated ROI/parity confirmation. |
| Canonical accumulator, msgspec-after-normalization, and timeline hot-path optimization (combined; effects cannot be separated honestly) | RETEST | About 120.10 CPU-s versus the cached pre-optimization run (216.89 → 96.79 CPU-s including setup+replay; single run per side) | Theoretical 2.24× CPU-bound engine throughput only; not a worker-capacity multiplier. Exact canonical byte/hash golden tests pass. |
| Provider page-copy reduction (8,192-tick profiled diagnostic) | RETEST | 7.443 CPU-s in one profiled run (70.285 → 62.842 CPU-s; about 10.6%) | Below the 15–20% end-to-end promotion bar and profiler-instrumented; durable-worker capacity saved is unknown, so no capacity credit. |
| Jump preview/replay reuse as a compute optimization | REJECT for CPU-capacity claims; retain the user-facing Jump feature | On the measured 1,024-tick A/B, Jump used about 1.45 more CPU-s (2.809 vs 1.359) and was 2.07× slower by wall time | At that sample it would reduce compute-limited throughput to about 0.48× normal replay; no CPU saving is shown. A new algorithm requires causal parity and a new benchmark. |
| Rust/PyO3 hot-loop replacement | REJECT for production adoption; no prototype justified yet | 0 CPU-s measured/saved | No capacity impact established. Reconsider only after a profile isolates a suitable hot loop and an isolated candidate demonstrates roughly 2× end-to-end gain or a major memory reduction with full parity/recovery. |

No candidate currently qualifies for Commercial V1 capacity credit: the promising Python/Arrow savings lack three-run repetition and a durable-worker comparison, while the durable 65,536-tick path is blocked by the existing 256-step Session checkpoint limit. No Rust/native dependency is added.

**DoD status on 2026-11-13: NOT DONE / HOLD.** The next engineering blocker is a reviewed, backward-compatible durable timeline checkpoint compaction/continuation design that can represent long Sessions without relaxing financial, causal, or recovery guarantees. That changes frozen checkpoint/recovery behavior and needs Owner authorization before implementation.
