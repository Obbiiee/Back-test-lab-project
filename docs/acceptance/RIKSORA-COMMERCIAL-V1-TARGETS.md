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

Deployment profile under test: 6 vCPU / 16 GiB RAM single VPS, with API, PostgreSQL and workers co-resident as proposed (verify actual topology). Codex/development processes may share the host; never assume six exclusive worker CPUs. The default repository queue and native worker pool currently have two slots; four is a **target configuration**, not present acceptance evidence.

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

- Repository currently has two queue workers and two native slots; four worker configuration is unimplemented/unproven.
- Local synthetic real-browser ten-trader cohort has passed functional journeys, but older interactive p95/p99 exceeded candidate targets. A local 20-user cohort was blocked by host resource gate.
- 524,288-tick synthetic financial-active engine replay passed in local KVM with one closed trade, not an end-to-end long durable worker on target VPS.
- No 20-user / four-worker real-VPS capacity PASS, complete rights-qualified launch catalog, live billing evidence or verified Commercial V1 unit economics exists in this checkpoint.

**DoD status on 2026-11-13: NOT DONE / HOLD.**
