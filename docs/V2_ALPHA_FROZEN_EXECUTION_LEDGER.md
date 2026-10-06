# Backtest Lab v2 Alpha — Frozen Execution Ledger

> **Purpose:** deterministic checkpoint order from current repository state to closed v2 Alpha.
>
> This ledger is a plan, not current implementation authorization. A human may authorize the whole frozen journey; after that, Work follows this ledger without redesign or routine choice requests, stopping only for a defined hard invalidation, safety/permission requirement, or failed Git/validation gate that cannot be repaired within the checkpoint.

## Global checkpoint rule

Every checkpoint:
`VERIFY → IMPLEMENT/SPIKE → TEST → REVIEW DIFF → UPDATE FACTUAL DOCS → COMMIT → PUSH → VERIFY REMOTE EQUALITY/CLEAN TREE → NEXT`.

A failed test is repaired in the same checkpoint. It does not trigger architecture improvisation.

## Journey

### PF-0 — Plan Freeze Integrity
**Input:** Frozen Spec + Decision Register + STITCH-0 + Work Execution Plan.
**Do:** cross-check links, authority, contradictions and repository baseline.
**Pass:** no contradictory owner; operational authority remains explicit.
**Runtime:** none.

### S-1 — Drawing Donor Spike
**Do:** execute DT-DRAW against exact pinned OpenAlgo then OpenCharts fallback.
**Output:** evidence report + selected owner.
**No:** production migration/deletion.
**Pass:** selected branch determined mechanically by DT-DRAW.

### S-2 — Drawing Migration
**Condition:** only if S-1 selects donor; otherwise mark N/A and retain current.
**Do:** adapter, persistence migration/refusal, parity, browser/replay tests.
**Pass:** current eight MUSTs preserved, rollback proven.
**Delete:** no old runtime until S-7 consolidation.

### S-3 — Indicator Donor Spike
**Do:** execute DT-IND using current seven authored semantics.
**Output:** selected calculator/host combination.

### S-4 — Indicator Migration
**Condition:** only accepted S-3 portions.
**Pass:** numerical vectors, warmup, truncation/no-look-ahead, panes, replay, browser.

### S-5 — Trading Visualization Stitch
**Do:** evaluate/adapt donor presentation for Long/Short, order/position/brackets.
**Boundary:** UI event→BTL command→BTL authority→canonical projection.
**Pass:** donor cannot settle fills/PnL; existing trading UX parity.

### S-6 — Analytics Primitive Stitch
**Do:** ResearchCalculator boundary; adopt only semantic-parity primitives.
**Pass:** authored vectors; BTL grouping/Passport/orchestration unchanged.

### S-7 — Stitch Consolidation
**Do:** remove only proven-dead superseded code, update notices/owners, full frontend regression.
**Pass:** one owner per capability; rollback/migration fixtures preserved.

### M-1 — 42.18 Provenance Reconciliation
**Do:** verify preserved branch/commit; diff exact draft; selectively reconcile to 42.17 + 42.19.
**No:** wholesale merge, benchmark resume, execution.
**Pass:** sidecar semantics conform; V1 unchanged.

### M-2 — V2 Disk Provider / Atomic Publication
**Do:** immutable partitioned storage, manifest/checksum, staging→atomic publish, bounded handles/memory.
**Pass:** synthetic golden dataset publication + corrupt/partial refusal.

### M-3 — Streaming Validation / Time Index
**Do:** bounded validation and immutable index.
**Pass:** ordering/duplicate/bid-ask/chunk/checksum/index fixtures; peak memory bounded independent of full dataset size.

### M-4 — Indexed Timeline
**Do:** seek >= timestamp, range read, resume, partition crossing, cancel.
**Pass:** deterministic equal-time semantics; random seeks avoid scan-from-start.

### M-5 — Authorized Dataset Benchmark
**Do:** rights-safe local/private ingestion benchmark.
**Pass:** complete report for ingest/index/RSS/random seek/sequential throughput/corruption/sidecar.
**Branch:** follow DT-STORAGE if performance fails.
**No:** Git raw provider data.

### M-6 — Tick→Candle Aggregator
**Do:** revealed-only timeframe buckets with pinned side/bucket policy.
**Pass:** golden candles; truncation invariance; no future access.

### M-7 — Market Data Service Boundary
**Do:** bounded internal APIs/read ports for timeline/range/replay.
**Pass:** limits/cancel/ownership; no browser raw-tick flood.

### X-1 — Execution V1 Contract Freeze
**Do:** exact command/event schema and edge-case semantics under Frozen Spec.
**Must settle:** market/limit/stop; pending; cancel; long/short; bid/ask; SL/TP; gap; equal-time; costs; partial exit; idempotency/revision; rejected/unresolved.
**Pass:** golden scenario table complete before engine code.

### X-2 — Pure Tick Execution Engine
**Do:** deterministic implementation independent of UI/storage transport.
**Pass:** golden/property tests; same inputs→same events; speed/frame invariant; ambiguity fails closed.

### X-3 — Canonical Event/Trade Log
**Do:** append-only logical events with source evidence/revision/version.
**Pass:** replay/rebuild canonical position history; duplicate commands cannot double-settle.

### X-4 — Account/PnL Projection
**Do:** exact financial projection from canonical events; versioned execution costs.
**Pass:** reconciliation fixtures including partial exits.
**Legacy:** v1 stays MODELLED and separate.

### Q-1 — Durable Session Contract
**Do:** canonical state/lifecycle/revisions/ownership.
**Pass:** small-state invariant; no dataset copy per user.

### Q-2 — Session Persistence / Restore
**Do:** durable checkpoints and committed revision restore.
**Pass:** kill/restart/restore deterministic continuation; stale revision refused; no duplicate settlement.

### Q-3 — Replay Worker Pool / Backpressure
**Do:** bounded workers, queue, cancellation, fair scheduling, paused release.
**Pass:** overload queues/throttles/rejects rather than unbounded growth.

### Q-4 — Cache Decision
**Do:** execute DT-CACHE using random-cursor benchmark.
**Output:** explicit NO-CACHE or bounded-cache implementation.
**Pass:** deterministic equality cache on/off if implemented.

### R-1 — Method Canonicalization
**Do:** versioned Method model using existing prototype/spec as input.
**Pass:** immutable historical versions, inclusion/exclusion preserved.

### R-2 — Protocol Canonicalization
**Do:** versioned risk/RR/pending/intervention/checklist/sample rules.
**Pass:** configured defaults such as 1:1.25 / max 4 live in Protocol, not engine constants.

### R-3 — Experiment Passport Completion
**Do:** bind dataset+Method+Protocol+engine+execution+calculator lineage.
**Pass:** canonical hash/version fixtures.

### R-4 — Session/Method/Protocol Product Integration
**Do:** migrate memory-only prototype concepts to real domain/session commands.
**Pass:** Quick/Planned; review/confirmation; visible locks/deviations; default v1 rollback preserved until cutover.

### R-5 — Journal Canonical Projection
**Do:** journal references canonical trades/events.
**Pass:** notes cannot mutate financial truth; exports preserve identity.

### R-6 — ResearchCalculator Boundary + Basic Metrics
**Do:** canonical immutable inputs and versioned outputs.
**Pass:** count/WLBE/PnL/win rate/avg/expectancy/PF/DD/streak/R/duration/reconciliation vectors.

### R-7 — MAE/MFE
**Do:** compute only where revealed event path permits.
**Pass:** no hidden-future/path fabrication.

### R-8 — Seeded Monte Carlo
**Do:** reproducible distributions for terminal outcome/DD/streak/explicit threshold probabilities.
**Pass:** pinned RNG algorithm/seed in Passport.

### R-9 — Advanced Research Gate
**Decision:** regime/robustness/destruction/OOS are post-core-alpha by default.
**Do now only if already marked MUST by release requirement; otherwise DEFER without blocking first closed cohort.

### I-1 — Core Integration Gate
**Require:** accepted S owner(s), M-4/M-5/M-6, X-2/X-3/X-4, Q-2, R-1/R-2/R-3.
**Do:** produce actual authority graph; prove no dual settlement authority.
**Pass:** one deterministic end-to-end synthetic experiment.

### I-2 — v2 API Composition
**Do:** compose existing FastAPI/contracts/Postgres/workspace with market/session/execution/research.
**Pass:** strict versioned transport; auth/ownership; bounded payloads.

### I-3 — Frontend v2 Adapter/Cutover Flag
**Do:** explicit v2 path; v1 remains rollback during acceptance.
**Pass:** authored v1/v2 compatibility scenarios; no mixed authority.

### I-4 — Identity/Workspace UI Integration
**Do:** login/verification/workspace product flow using existing backend.
**Pass:** server authorization, hostile tenant tests, browser flow.

### I-5 — Browser Delivery Budget
**Do:** throttle/coalesce candles/current quote/events/progress without changing engine.
**Pass:** engine hashes identical across UI update rates.

### H-1 — Observability
**Do:** session/replay/worker/queue/resource/API/dataset/restore/version telemetry.
**Pass:** diagnose golden injected failures without secrets.

### H-2 — Security/Tenant Hardening
**Do:** object-level authorization, body/rate/resource limits, TLS/secrets/dependency review.
**Pass:** A↛B read/write; hostile inputs bounded.

### H-3 — Backup/Restore / Recovery
**Do:** DB/session/dataset/index recovery drills.
**Pass:** documented measured recovery; no silent evidence corruption.

### H-4 — Worst-Case Load 10
**Do:** random historical cursors, mixed speeds/orders/pause/reconnect.
**Record:** p50/p95/p99, CPU/RAM/I/O/queue/errors/hashes.
**Branch:** DT-PERFORMANCE/DT-CACHE.

### H-5 — Failure Injection
**Do:** worker/API/DB restart, missing/corrupt chunk/index, disk/permission pressure where safe, disconnect, stale revision, interrupted save/publication.
**Pass:** fail closed/recover per contract.

### L-1 — Data Rights Launch Gate
**Do:** verify exact Alpha dataset audience/storage/display/derived/retention rights.
**Pass:** external-compatible rights OR external Alpha blocked while engineering remains internal.
**Never:** infer permission from technical access.

### L-2 — Internal Alpha
**Users:** project team/internal authorized users.
**Pass:** no unresolved severity-1/2 correctness/data/security defect; recovery and telemetry usable.

### L-3 — Closed Alpha 5
**Pass:** release gate healthy for defined observation window/sample; record incidents and product funnel.

### L-4 — Closed Alpha 15
Same frozen release gate; capacity profile rerun.

### L-5 — Closed Alpha 30
Same gate.

### L-6 — Closed Alpha 50
Same gate.

### L-7 — Closed Alpha 100
Same gate; cost/user and support burden included.

### L-8 — Beta Readiness Review
**Do:** product usefulness/retention, reliability, cost, rights, incidents, security, recovery, capacity, limitations.
**Output:** GO / HOLD / POST-ALPHA FIX ledger.
**No:** automatic beta launch.

## Journey completion

The frozen journey is complete at L-8. Post-Alpha parking-lot work requires a new planning/freeze cycle; it is not silently appended to this ledger.
