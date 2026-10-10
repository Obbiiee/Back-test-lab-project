# Backtest Lab v2 Alpha — Frozen Execution Ledger

> **Purpose:** deterministic checkpoint order from current repository state to closed v2 Alpha.
>
> This ledger is a plan, not current implementation authorization. A human may authorize the whole frozen journey; after that, Work follows this ledger without redesign or routine choice requests, stopping only for a defined hard invalidation, safety/permission requirement, or failed Git/validation gate that cannot be repaired within the checkpoint.

## Global checkpoint rule

Every checkpoint:
`VERIFY → IMPLEMENT/SPIKE → TEST → REVIEW DIFF → UPDATE FACTUAL DOCS → COMMIT → PUSH → VERIFY REMOTE EQUALITY/CLEAN TREE → NEXT`.

A failed test is repaired in the same checkpoint. It does not trigger architecture improvisation.

## Journey

### Alpha product closure mapping after local V2.2 (2026-10-10)

This is a reconciliation of the existing checkpoints against [the scope amendment](V2_ALPHA_FROZEN_SPEC.md#0a-human-approved-alpha-product-closure-amendment-2026-10-10), not another roadmap or a claim that the old complete frozen journey already passed. Current-phase alone owns authorization/progress. Accepted V21/STITCH/V22 capabilities are reused with their actual limits; rerun validation when changed, not whole implementation from scratch. Preserve original ledger entries/history below.

| Existing checkpoint | Remaining product closure work / gate |
| --- | --- |
| PF-0 | Normalize scope, screens, minimum measurement and supplemental drawing decision; deterministic authority/bundle tests; no runtime change |
| S-1 / conditional S-2 | Pin and test the one supplemental drawing candidate against BTL/LC5 and Ray; migrate accepted portions only, otherwise minimal existing-owner Ray; preserve JSON/history/rollback |
| R-4 / I-3 | Apply the design-owner screen checklist to the one current workspace; fix Method/Session wording, source credit, order/News presentation and terminal/replay usability; human-approved local chart reference and original research_home; keep all domain restrictions |
| R-5 | Connect genuine journal notes/export to canonical trade identities without account mutation |
| R-6 / R-7 / R-8 | Close pinned initial-risk/basic metric, causal MAE/MFE and frozen seeded-bootstrap gaps; missing evidence remains unavailable; no QuantStats wholesale adoption |
| H-1 | Implement the minimum bounded event/optional-survey/cost measurement slice through vendor-neutral adapters; disabled/outage operation cannot affect finance |
| I-4 / I-2 | Compose existing identity/workspace into hosted-ready product paths; real verification/recovery/logout/tenant tests, not a fake login or exposing the loopback personal service |
| Q-3 / I-5 / H-2 through H-5 | Close only actual admission/browser/security/recovery/capacity gaps against the existing quantitative contracts; preserve successful applicable evidence |
| L-1 / L-2 | Separate internal product acceptance from external rights; full end-to-end browser/release regression and honest limitations; no external claim while rights/source eligibility are unresolved |
| L-3 onward | Cohort admission/deployment requires its actual rights/security/capacity/operator gate; no procurement or public deployment by implication |

Each row is decomposed into narrow checkpoint commits using the same owners. Stop on material data/contract/provenance/security/remote conflicts; do not stop just because an intermediate authorized checkpoint succeeds. External-rights blockers do not forbid safe internal engineering. No source certainty promotion, additional-year ingestion, draft merge, live broker, AI/community, billing, chart rewrite or professional full-catalog expansion.

### PF-0 — Plan Freeze Integrity
**Input:** Frozen Spec + Decision Register + STITCH-0 + Work Execution Plan.
**Do:** cross-check links, authority, contradictions and repository baseline.
**Pass:** no contradictory owner; operational authority remains explicit.
**Runtime:** none.

### S-1 — Drawing Donor Spike
**Do:** evaluate current BTL + exact pinned OpenAlgo + exact pinned OpenCharts under the common frozen rubric, then execute DT-DRAW ranking.
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

## S-7 bounded product acceptance classification

This records the human-authorized S-1–S-7 result boundary; it does not rewrite the frozen future journey or authorize V2.2. Existing specs remain the future capability owners. Implementation status here is **local synthetic Functional Alpha**, not professional catalog/capacity/historical-market acceptance. Fib Retracement maps to the runtime label Fibonacci Retracement; Long/Short are research geometry whose Create order seeds only a reviewed BTL intent. Arrow/Measure are extra minimum tools outside the professional 25.

```json
{
  "CLASSIFICATION": "STITCH_S7_BOUNDED_ACCEPTANCE",
  "drawing": {
    "implemented": [
      "Trend Line",
      "Horizontal Line",
      "Vertical Line",
      "Fib Retracement",
      "Rectangle",
      "Text",
      "Long Position",
      "Short Position"
    ],
    "deferred": [
      "Ray",
      "Extended Line",
      "Horizontal Ray",
      "Cross Line",
      "Parallel Channel",
      "Regression Trend",
      "Fib Extension",
      "Fib Channel",
      "Rotated Rectangle",
      "Circle/Ellipse",
      "Polyline/Path",
      "Brush",
      "Highlighter",
      "Anchored Text",
      "Callout",
      "Price Range",
      "Date Range"
    ]
  },
  "additional_alpha_drawings": [
    "Arrow",
    "Measure"
  ],
  "indicators": {
    "implemented": [
      "SMA",
      "EMA",
      "Bollinger Bands",
      "RSI",
      "MACD",
      "ATR",
      "Stochastic"
    ],
    "unavailable": [
      "Volume"
    ],
    "deferred": [
      "VWAP",
      "Anchored VWAP",
      "ADX",
      "DMI",
      "CCI",
      "MFI",
      "OBV",
      "ROC",
      "Momentum",
      "Williams %R",
      "Parabolic SAR",
      "Donchian Channels",
      "Keltner Channels",
      "Ichimoku Cloud",
      "Pivot Points",
      "Aroon",
      "Choppiness Index"
    ]
  },
  "deferred_owners": {
    "drawing": "docs/DRAWING_ENGINE_SPEC.md",
    "indicators": "docs/INDICATOR_ENGINE_SPEC.md",
    "workspace": "docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md",
    "identity": "docs/V2_ALPHA_FROZEN_EXECUTION_LEDGER.md#i-4--identityworkspace-ui-integration",
    "precision": "docs/ROADMAP.md"
  },
  "acceptance_level": "LOCAL_SYNTHETIC_FUNCTIONAL_ALPHA_ONLY",
  "professional_catalog_complete": false,
  "historical_precision_accepted": false,
  "v22_authorized": false
}
```

| Capability | Bounded acceptance and remaining gap | Deferred owner / rationale |
|---|---|---|
| Eight canonical primitives + Long/Short | Current BTL manager/primitives and dedicated research geometry retained after pinned comparison; create/select/drag/handles/history/hide/lock/persistence covered by existing test owners. S-7 actual browser covers eight creations, TIME+PRICE stability, delete/undo/redo and Long planning journey. No universal full-style/grouping promise. | Drawing spec for remaining 17; minimum-tool KEEP wins frozen rubric, donor catalog alone cannot bypass acceptance. |
| Object Tree, group/ungroup, multi-select, reorder, named templates, clipboard/style catalog | DEFERRED; selected-object controls and history exist, but no accepted hierarchical canonical Drawings+Indicators tree. Legacy geometry prototypes are not canonical professional acceptance. | Drawing + Indicator specs; new common interaction/model/history scope requires a bounded grant. |
| Magnet OFF/WEAK/STRONG with OHLC targets | DEFERRED; existing legacy boolean magnet is not the professional three-mode/eligible-target implementation and is not exposed as that promise in tick alpha. | Drawing spec; shared anchor/interaction acceptance is future work. |
| Seven indicator families / Volume | Accepted calculator/host KEEP; add/edit/hide/remove/multiple instances/panes/revealed-only prefix tested. Per-Session tick-alpha config now persists locally. Volume explicitly unavailable without source volume; tick counts are never invented volume. | Indicator spec for expanded 17, pane reorder/resize UI, source/style/favorites/templates/workspace undo. v1 runtime-only configs are not silently migrated. |
| Multi-chart | DEFERRED; one chart per workspace only. | System blueprint; synchronized cursor/layout/performance is outside bounded STITCH. |
| Default v1 → tick workspace consolidation | DEFERRED; opt-in local tick path is accepted, default v1/Figma path remains recoverable legacy/modelled. Both reuse LC5/CandleChart; they do not share settlement authority. | System blueprint / ADR-MIGRATION; changing default and legacy financial import/retirement require separate explicit acceptance. |
| Login/dashboard/workspace account UI | DEFERRED product composition; earlier backend identity/tenant foundations are not a working local tick login UI or public SaaS. | Existing I-4 and system blueprint; no cloud/auth/public-launch grant in STITCH. |
| Trading presentation | Accepted narrow MIT quote-direction/review adaptation, intent-only Long/Short seed, server review/confirmation, pending/Protocol, canonical fill markers/history/Analysis. Six-dot terminal drag/keyboard and focus remain shared existing owners. | Existing trading/Method/Session specs for richer redesign/order/news/dashboard requests; donor stores/LTP/PnL remain excluded. |
| Historical feed, Exness V2 benchmark, scale/closed cohort, advanced research | DEFERRED/unaccepted; fixtures verify execution invariants, not real-feed broker fidelity. R0/MAE/MFE/MC unavailable is explicit. | Existing ROADMAP V2.2 + frozen storage/metrics owners. Preserved 42.18/42.20 bytes and partial benchmark remain untouched. |

No migration donor superseded production code in S-2/S-4, so no runtime deletion is justified. Retain compatibility exports, Phase 3/golden/storage fixtures, v1 rollback and historical knowledge. [STITCH audit](STITCH_0_OSS_REPLACEMENT_AUDIT.md) owns measured evidence, licenses and limitations; operational status remains only in current-phase.

### D-0 — Early Data Mode / Rights Gate
**Do:** apply the frozen rights matrix before provider-specific production integration.
**Pass:** provider is classified EXTERNAL-CANDIDATE, INTERNAL-ONLY, UNVERIFIED or REJECTED with evidence.
**Fallback:** internal/synthetic engineering continues without pretending external rights.

### M-1 — 42.18 Provenance Reconciliation
**Do:** verify preserved branch/commit; diff exact draft; selectively reconcile to 42.17 + 42.19.
**No:** wholesale merge, benchmark resume, execution.
**Pass:** sidecar semantics conform; V1 unchanged.

### M-2 — V2 Disk Provider / Atomic Publication
**Do:** immutable partitioned storage, manifest/checksum, staging→atomic publish, bounded handles/memory.
**Pass:** synthetic golden dataset publication + corrupt/partial refusal.

### M-3 — Streaming Validation / Time Index
**Do:** bounded validation and immutable index.
**Pass:** ordering/duplicate/bid-ask/chunk/checksum/index fixtures; peak memory bounded independent of full dataset size, including duplicate/diagnostic state; GAP-001/GAP-006 negative invariants pass.

### M-4 — Indexed Timeline
**Do:** seek >= timestamp, range read, resume, partition crossing, cancel.
**Pass:** deterministic equal-time semantics; random seek and late-history resume avoid scan-from-start/O(historical-prefix) positioning; bounded reconstruction and GAP-002/GAP-007 pass.

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

### X-1 — Execution V1 Contract Materialization
**Do:** materialize wire schemas/state machine/golden vectors strictly from `V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md`.
**No:** product-semantic design choices.
**Pass:** every frozen golden scenario has an exact expected event/account outcome or expected UNRESOLVED/REFUSED result before engine code.

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
**Pass:** overload queues/throttles/rejects before heavy allocation rather than unbounded growth; queue is itself bounded/durable, per-user/global limits apply, worker ownership is exclusive, authority is revalidated, and recovery uses the same admission path (GAP-005/GAP-013/GAP-021/GAP-022).

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
**Do:** implement exactly `V2_ALPHA_RESEARCH_METRICS_CONTRACT.md`.
**Pass:** side/partial-exit/boundary/unresolved golden vectors; no hidden-future/path fabrication.

### R-8 — Seeded Monte Carlo
**Do:** implement the descriptive bootstrap contract in `V2_ALPHA_RESEARCH_METRICS_CONTRACT.md`.
**Pass:** golden PRNG vectors, seed reproducibility, N<30 refusal, reported percentiles.

### R-9 — Advanced Research
**Status:** POST-ALPHA / NOT ON THIS ALPHA CRITICAL PATH.
**Do:** record DEFERRED and continue. A later planning cycle is required.

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
**Pass:** engine hashes identical across UI update rates; chart/history/cache/request state remains within an explicit browser budget and ordinary responses/history are bounded (GAP-008/GAP-009/GAP-020).

### H-1 — Observability
**Do:** session/replay/worker/queue/resource/API/dataset/restore/version telemetry.
**Pass:** diagnose golden injected failures without secrets; bounded-cardinality telemetry covers active/queued/rejected work, queue wait, CPU/RAM/I/O, DB pool/query pressure, throughput, latency, deterministic mismatches, recovery and browser delivery without becoming an unbounded dependency (GAP-014/GAP-024).

### H-2 — Security/Tenant Hardening
**Do:** object-level authorization, body/rate/resource limits, TLS/secrets/dependency review.
**Pass:** A↛B read/write; hostile inputs bounded; production DB connections are pooled/bounded with headroom, outer protection cannot create unbounded DB pressure, and release installs pinned dependencies (GAP-010/GAP-011/GAP-018).

### H-3 — Backup/Restore / Recovery
**Do:** DB/session/dataset/index recovery drills.
**Pass:** documented measured recovery; no silent evidence corruption; backup/restore procedure is certified at representative Alpha DB size rather than relying on an unmeasured fixed timeout (GAP-017).

### H-4 — Worst-Case Load 10
**Do:** random historical cursors, mixed speeds/orders/pause/reconnect.
**Record:** p50/p95/p99, CPU/RAM/I/O/queue/errors/hashes.
**Branch:** DT-PERFORMANCE/DT-CACHE.
**Also certify:** admission limits, queue/DB/browser/telemetry budgets and applicable `V2_ALPHA_CAPACITY_FAILURE_HARDENING_CONTRACT.md` gates.

### H-5 — Failure Injection
**Do:** worker/API/DB restart, missing/corrupt chunk/index, disk/permission pressure where safe, disconnect, stale revision, interrupted save/publication.
**Pass:** fail closed/recover per contract; execute the complete minimum failure matrix in `V2_ALPHA_CAPACITY_FAILURE_HARDENING_CONTRACT.md`, including financial all-or-none commit, duplicate retry, exclusive worker ownership, mass recovery, queue saturation and telemetry failure (GAP-012/GAP-023).

### L-1 — Final Data Rights Re-verification
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

### R-5 canonical journal evidence

The existing [system architecture evidence](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#alpha-canonical-journal-implementation-evidence--2026-10-11) owns durable scoped notes, independent note CAS, canonical complete JSON export and actual validation/limits. No financial authority or roadmap changes. The operational pointer and authorization remain solely in AI_CONTEXT/04_CURRENT_PHASE.md; Git closure precedes already-authorized R-6.
