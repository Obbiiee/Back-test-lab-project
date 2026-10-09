# V2.2 Precision Beta — Engineering Design Candidate (planning only)

**Date:** 2026-10-09  
**Status:** PROPOSED / CONDITIONAL DESIGN APPROVAL — NOT IMPLEMENTATION AUTHORITY  
**Planning branch:** `planning/v22-precision-beta-20261009`  
**Read baseline:** `main@c408183530f460f6849617ae33831c699ee6ef59` (V21-2 completed, V21-3 active at time of review).  
**Ownership:** This is a non-authoritative proposal. Existing `docs/ROADMAP.md`, `docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md`, `docs/MARKET_DATA_STANDARD.md`, `AI_CONTEXT/04_CURRENT_PHASE.md`, `AI_CONTEXT/06_WORKFLOW_RULES.md`, and frozen 42.17/42.19 remain authoritative. Do not merge this file as an operational grant.

## Decision and scope

V2.2 demonstrates evidence-bounded, reproducible historical tick simulation on the **existing single V2.1 financial engine**, with verified data coverage, indexed bounded storage, precision reference checks, crash recovery, and actionable issue evidence. It does **not** assert broker-realized fills, intrabar certainty without evidence, public redistribution rights, cloud SaaS readiness, or commercial launch.

**Do not interrupt V21-3 → V21-6.** Their separately authorized checkpoints and Git closure must complete before a V2.2 implementation grant. This document may be reviewed independently; no runtime, dependencies, operational pointers, protected history, or market data change in this planning branch.

## Entry gate V22-0 — reconcile reality before implementation

- Read actual post-V21-6 Git HEAD, working tree, test evidence, browser alpha report, `AI_HANDOFF.md`, authority docs and protected draft hashes.
- Map implemented V2.1 engine, Method/Session, PostgreSQL event/command/checkpoint, workspace adapters, browser analysis, and tests. Reuse them. No second ledger, order engine or independent browser settlement.
- Preserve 42.17/42.19 hierarchy and sidecar authority, timestamp-group atomicity, bounded causal RevealedView, and 42.20 draft isolation. No direct full-data provider/index handles in consumer.
- Record real dataset availability, source license/retention, named hardware, benchmark workload, failure budgets and release audience. Unknown rights mean **no external redistribution**.
- Define a requirement-to-code-to-test traceability register with explicit owner and evidence link; mark every assertion as proposed, verified, blocked, or superseded.

## Work breakdown and strict acceptance

| Checkpoint | Deliverable | PASS evidence | Hard fail |
|---|---|---|---|
| V22-0 | Baseline, authority, dependency, risk and benchmark register | Post-V21-6 remote/local equality; no active conflicting edits; measured environment | Unclear baseline, incompatible frozen contract |
| V22-1 | Immutable dataset passport, real coverage intervals, provider/rights matrix | Source identity, hashes, parser/normalizer versions, gaps and retention constraints | Filename year treated as complete, unknown rights labeled allowed |
| V22-2 | Bounded streaming validator + risk-tier sampling | Every record structurally checked; counts reconciled; anomalies/ties retained with reasons; deterministic rerun | Silent repair, dropping or reordering raw evidence |
| V22-3 | V2 indexed ingest, manifest/sidecar, seek, cancellation and atomic publish | Full representative dataset run, index-vs-linear oracle, bounded peak memory, crash-injection recovery | Lost tick, partial published dataset, future data leak |
| V22-4 | Independent precision oracle + property/differential tests | Long/short Bid/Ask, order activation, fees, rounding, gap, tie, SL/TP, uncertainty, accounting, anti-look-ahead | False determinate settlement, unexplained money divergence |
| V22-5 | Minimal evidence issue reporter and reproducible fixture | Seeded defect → report → safe evidence → replay → regression → impact identification | PII leak, ungrounded “reproduced” label |
| V22-6 | Fault/security/concurrency/performance/restore suite | Named hardware and cold/warm workloads; fixed budgets; durable retry; isolation and recovery | State divergence, privilege bypass, unbounded resource use |
| V22-7 | Browser E2E and beta decision packet | Complete traceability register, documented limitations, all critical gates passed, independent review | Open critical bug, missing mandatory evidence |

Each checkpoint requires its own human-authorized scope, diff review, appropriate tests, docs-only browser exemption if applicable, commit/push/remote equality/clean state. The plan does not authorize automatic V22-0→7 progression.

## Contract 1 — event time and execution causality

Represent distinct `source_event_time`, `source_precision`, `source_ordinal`, `available_at` (if proven), `engine_sequence`, command acceptance/activation evidence, and provider ordering trust. A deterministic storage order is **not** evidence of market chronology. The engine may use only revealed authorized events; no future tick, future gap, EOF, unrestricted index metadata, or backdated order activation. A command placed inside an equal-time group must not retroactively observe or fill from already-consumed events. Pin execution model assumptions per experiment.

## Contract 2 — uncertainty and financial ledger

`DETERMINATE`: outcome proved under pinned feed/model and all admissible event orders; **not** a broker fill claim. `CONDITIONAL`: labeled scenario with explicit assumptions, separate ID, events, ledger and statistics. `UNRESOLVED`: evidence insufficient, including proof search resource exhaustion. Equal timestamp alone does not imply ambiguity; order-invariant outcome may be proved using a sound bounded algorithm. If ambiguity can change any financial state, freeze authoritative ledger at last proved checkpoint; chart-only replay may continue. Subsequent official settlements cannot silently proceed on a guessed balance. Never collapse branches into one observed equity curve. Track affected trades and downstream experiments, not merely tied timestamps.

## Contract 3 — durable consistency

One authoritative financial engine and one transaction boundary for accepted command, idempotency key, order/fill/event/account mutation and acknowledged cursor/checkpoint. At-least-once processing may be internal, but externally visible financial effect must be exactly once under retry. Crash before commit leaves no partial settlement; crash after commit before response returns the same receipt. Recovery verifies dataset version/hash, engine/profile, event-log offset, cursor and ledger; inconsistency fails closed. Ingestion uses staged artifacts and atomic publication after manifest/index/sidecar validation; no half-visible dataset. Dataset retention/licensing may prevent later rerun; report `REPRODUCTION_UNAVAILABLE`, not fabricated reproduction.

## Contract 4 — data evidence, license and reproducibility

Source bytes retained only where rights permit; normalized, validated, derived and indexed artifacts get immutable versions. Never silently correct outliers, spread, source ordering, timestamp resolution, or duplicates. Audit coverage by actual intervals; e.g. an Exness 2015 file beginning in August is partial-year. Pin source/product/feed ID, instrument, raw/normalized hashes, parser/normalizer/schema, precision and timezone policy, index format, engine build, financial rounding rules, execution profile, session/method snapshot, experiment config, seed where applicable, and test fixture provenance. Data quality approval and public distribution license approval are independent.

## Contract 5 — issue evidence and security

Report includes dataset/engine/profile identity, bounded revealed tick range, order/command/event references, reproducible state snapshot or safe hash, expected/actual outcome, severity and optional user-approved screenshot. Strip secrets, tokens and unrelated personal data. Apply size/retention/access/abuse controls; honor provider redistribution restrictions. Issue lifecycle: reported → triaged → reproduced OR unavailable → fixed → regression-tested → verified → closed. Query affected experiment lineage on any financial fix; do not mutate historical result silently.

## Contract 6 — benchmark, costs and acceptance integrity

Do not invent PASS thresholds. Before optimization, register machine CPU/RAM/disk, dataset and size, exact workload, cold/warm cache, ingest ticks/sec, seek p50/p95/p99, replay throughput, peak RSS, I/O amplification, concurrent sessions, cancellation/restart, storage footprint and per-session cost. Include tiny oracle fixtures, representative real samples and **complete** large ingestion. Previous interrupted ~700k-row progress is not a full Exness benchmark. Freeze numerical limits before optimization; publish raw runs, variance and known bottlenecks. Avoid claiming 1,000 concurrent users from a single-user test.

## Senior reviewer threat model and negative tests

| ID | Failure injection | Required invariant |
|---|---|---|
| N01 | SL and TP possible within unordered equal-time events | No false definitive P&L |
| N02 | Ambiguous trade followed by new order | No authoritative downstream balance without proof |
| N03 | Duplicate command after timeout | One receipt/economic effect |
| N04 | Worker crash before/after commit | Ledger, event offset and cursor reconcile |
| N05 | Corrupt/missing index or sidecar | Fail closed; no skipped/future events |
| N06 | Order created mid-group or at replay boundary | No backdated activation/look-ahead |
| N07 | Duplicate, outlier, gap, partial-year feed | Preserved evidence and truthful coverage |
| N08 | Dataset/parser/profile changed after experiment | New identity/rerun, not retroactive rewriting |
| N09 | Browser refresh or parallel session commands | Same durable authoritative state; isolation |
| N10 | Bug report with token/PII/provider restricted data | Redaction, authorization, minimal disclosure |
| N11 | Branch proof reaches resource limit | Unresolved, never assumed invariant |
| N12 | Cold seek and concurrent ingest on low-cost hardware | Meets predeclared limits or release NO-GO |

## Critical path and anti-scope-creep

`V21-6 closure → V22-0 → V22-1/2 → V22-3 → V22-4 → V22-6 → V22-7`. V22-5 can be designed alongside V22-3/4, but must consume their existing evidence/version IDs, not invent a second provenance model. Legal/data rights review is parallel but blocks external beta release. Do not build payments, CRM, social features, algorithmic trading, new provider integrations without evidence, or a replacement tick engine inside V2.2.

## Devil's Advocate decision register

- **P0 unresolved financial propagation:** contract proposed; empirical test pending.
- **P0 causal ordering / activation:** contract proposed; empirical test pending.
- **P0 durable replay/ledger recovery:** contract proposed; real DB fault injection pending.
- **P1 independent oracle accidentally mirrors production:** require separately authored small reference and reviewed golden cases.
- **P1 exponential ambiguity search:** bounded proof; resource exhaustion is unresolved.
- **P1 rights withdrawal vs reproducibility:** retention-aware evidence and explicit unavailable status.
- **P1 hardware cost and scale:** measured, frozen budget pending.
- **P1 data provider divergence:** feed-specific evidence, no silent provider blending.

**Engineering verdict:** DESIGN CANDIDATE / REQUEST EMPIRICAL EVIDENCE. No runtime correctness, license clearance, benchmark completion or beta readiness is certified by this planning document.

## Promotion / handoff rule

When Codex completes V21-6 and STOPs, rebase/reconcile this **planning-only branch** against current main after explicit review; compare with existing architecture authority, incorporate accepted decisions into their owning docs, record separately authorized V22-0 in current-phase authority, then run required documentation checks and normal commit/push/equality gates. Do not merge this proposal automatically and do not edit V2.1 master files during the ongoing journey.


---

## Design hardening amendment — Review 4 (2026-10-09)

**Target:** near-complete specification with objectively measurable gates, **not** a claimed 99% software correctness probability. Every unresolved issue is assigned a class, owner, trigger, test/evidence, release disposition, and (only where safe) user-report route. This amendment is a proposal and does not override authority or authorize implementation.

### H1 — Formal state-machine contract (P0)

Canonical durable state is the product of these orthogonal machines, with transitions applied atomically where financial effects occur:

| Machine | States | Authorized transitions | Invalid transition response |
|---|---|---|---|
| Session | DRAFT, READY, RUNNING, PAUSED, COMPLETED, BLOCKED | DRAFT→READY after validated method/profile/dataset; READY→RUNNING; RUNNING↔PAUSED; RUNNING/PAUSED→COMPLETED only after obligations resolved; any active→BLOCKED on evidence/integrity failure | Reject, no partial mutation |
| Order | DRAFT, REVIEWED, ACCEPTED, ARMED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED, UNRESOLVED | DRAFT→REVIEWED→ACCEPTED→ARMED; ARMED→PARTIALLY_FILLED/FILLED/CANCELLED/EXPIRED/UNRESOLVED; PARTIALLY_FILLED→FILLED/CANCELLED/UNRESOLVED | Reject, preserve original receipt; Protocol forbids disallowed manual changes |
| Position | OPEN, PARTIALLY_CLOSED, CLOSED, UNRESOLVED | OPEN→PARTIALLY_CLOSED/CLOSED/UNRESOLVED; PARTIALLY_CLOSED→PARTIALLY_CLOSED/CLOSED/UNRESOLVED; UNRESOLVED only resolves by proven invariant or explicitly isolated conditional replay | No negative quantity, duplicate close, or state promotion without proof |
| Evidence | DETERMINATE, CONDITIONAL, UNRESOLVED | DETERMINATE may fork labeled CONDITIONAL cases; UNRESOLVED→DETERMINATE only with additional admissible evidence or sound proof; resource exhaustion remains UNRESOLVED | No implicit conversion to determinate |
| Replay | INITIALIZED, SEEKING, PAUSED, PLAYING, STOPPED, ERROR | Explicit controller-acknowledged transitions; seek/reset invalidate stale in-flight command epochs; financial state restored from matching durable checkpoint | Reject stale epoch and future reveal |
| Dataset publication | STAGING, VALIDATING, READY, PUBLISHED, QUARANTINED, RETIRED | STAGING→VALIDATING→READY→PUBLISHED only after hash/index/sidecar validation; bad artifact→QUARANTINED; retirement preserves lawful historical references | Never expose partial index |

The implementation may use different internal enum names, but must provide a **mapping table** and equivalent transition semantics before code changes. No blanket promise of reversible UNRESOLVED state; reopening a proved historical result creates a new experiment version, never silent history rewrite.

**Global invariants:**
1. `filled_qty + cancelled_qty + remaining_qty = accepted_qty` in instrument units, with explicit decimal quantization and no negative component.
2. Per-position `sum(closed_qty) <= sum(opened_qty)`; each economic fill has a unique durable ID and one ledger posting set.
3. Double-entry or independently reconciled cash/equity/realized-PnL/fees/margin accounting, including partial exits and concurrent positions, with decimal-safe arithmetic and documented rounding.
4. Protocol RR, risk, permitted order type, checklist and intervention rules are pinned at acceptance; rejected commands have zero economic effect.
5. Unresolved financial effects freeze only the causally affected authoritative state/experiment; unrelated experiments remain isolated.
6. Exactly-once economic effect requires durable unique keys and transactionally consistent command receipt, event log, cursor and account snapshot.
7. Any state transition is replayable from the authoritative log/checkpoint with byte-identical canonical serialization under the same pinned versions.

**Required model-based test generator:** enumerate allowed/forbidden transitions and interleavings for 1/2/3 simultaneous positions, multiple partial exits, cancel/fill races, same-timestamp event groups, restart/retry, session reopen and seek epochs; assert invariants on every step, not only end balances. Verify independent reconciliation after each generated trace. Explicitly test liquidation/margin-call scenarios as *model assumptions*, not historical broker truth.

### H2 — Execution-model capability and epistemic labels (P0)

| Claim | Tick Bid/Ask alone | Additional requirement | Display label |
|---|---|---|---|
| Observed quoted side at a timestamp | Supported if source/precision validated | Feed provenance and ordering trust | OBSERVED_QUOTE |
| Quote touched entry/SL/TP under pinned algorithm | Conditional on chronology and activation evidence | Side-specific trigger semantics, tie/gap handling | MODEL_TRIGGER |
| Simulated fill price and quantity | Not a real-world fact | Explicit execution profile, latency, spread, slippage, sizing, commissions, fill policy | SIMULATED_FILL |
| Executable broker fill, queue position, available liquidity | Not provable from L1 Bid/Ask | Broker/order-book/trade confirmations as appropriate | NOT_PROVEN |
| Margin, stop-out, swap, overnight financing | Not inferable from quotes | Versioned broker/account profile and calendar; otherwise unresolved | PROFILE_ASSUMPTION |
| Generalization to another broker/feed/time | Not proven | Out-of-sample evidence and feed comparison | RESEARCH_HYPOTHESIS |

Default product wording: **“Hasil simulasi berdasarkan data dan model eksekusi yang dipilih; bukan bukti fill broker aktual.”** Every export and experiment passport carries the same evidence label. No “tick-accurate broker fill” marketing claim without relevant proof.

### H3 — Uncertainty for partial closes, hedging and margin (P0)

Define uncertainty dependencies as a directed graph: source tick/event → order activation/trigger → fill quantity/price → position inventory/realized P&L/fees → account cash/equity/margin → risk validation of later commands → later fills and analytics. If a disputed event can alter a downstream node, mark it tainted and stop authoritative propagation; deterministic unaffected nodes may continue only after proof of independence. Multiple positions sharing an account generally share equity/margin dependencies. Branching creates **independent account ledgers and position inventories**, not just alternative exit prices. Cap branch count, depth, CPU and storage using a predeclared budget; on cap exhaustion return `UNRESOLVED_RESOURCE_LIMIT`. Never average alternative outcomes into an official ledger.

### H4 — Independent oracle and metamorphic test charter (P1)

Oracle must be separately authored from the production settlement functions and not import their core execution/rounding implementation. Independently compute small, auditable decimal fixtures for long/short Bid/Ask, spreads, fee rounding, partial exits, margin and simultaneous positions. Freeze hand-calculated vectors with a written derivation and an external reviewer sign-off. Add metamorphic properties: replay chunk boundaries cannot change settled result; retry/restart cannot change result; slicing revealed history at T must equal running full history and stopping at T; chart timeframe cannot change tick settlement; dataset reindex must preserve canonical event identity and outcomes; shifting all prices by a constant (when profile allows) preserves appropriately adjusted differences. Differential tests alone are insufficient if both implementations share the same assumption.

### H5 — V1 → V2 migration and comparability (P1)

Preserve legacy V1 candle-based experiments as **LEGACY_OHLC** with their original model/version. Never silently relabel them tick-native, recalculate old balances in place, or claim performance equivalence. A V2 re-run is a new experiment linked by `supersedes/compares_to`, pinned to a new dataset and model, with a comparison report of coverage, trigger semantics, costs, and unresolved trades. UI/API/export must show both labels and refuse apples-to-apples aggregate metrics without a clear warning. Old sessions remain readable or explicitly unsupported; migration must not mutate existing evidence.

### H6 — Dataset confidence / ambiguity impact report (P1)

For each feed/instrument/period: actual first/last event; expected vs observed coverage intervals; records/unique timestamps; duplicate/tie groups; source ordering trust; timestamp precision; bid<=ask violations; nonpositive/implausible quotes; spreads; stale-side windows; discontinuities; gaps; parse rejects; index consistency; normalization changes; unresolved trade count and affected-trade ratio **only where a valid denominator exists**. Report uncertainty per instrument, session, execution profile and strategy. Separate **data anomaly rate**, **simulated-trade uncertainty rate**, and **broker fill unknowns**: they are not interchangeable. No global “data 99% accurate” claim derived from row count. If a trade's causal outcome is unprovable, mark it unresolved, not silently exclude it from win-rate denominator.

### H7 — Cost, performance and user-scale envelope (P1)

Define single-user private-beta reference machine, realistic XAUUSD data volume, concurrent active sessions, retention days, issue-report upload budget, storage/backup multiplier, provider license limits, CPU/IO contention, bandwidth/egress, and target operating cost per active user-month. Separate one-time ingestion cost from steady-state replay and support cost. Compute marginal cost by observed resource usage, not a fixed VPS price divided by a guessed user count. Include worst-case ambiguity branching and malicious repeated seeks. Freeze explicit numeric p95/p99/RSS/IO/throughput budgets after representative measurements **before** performance tuning. If target cannot be met on chosen hardware, narrow release audience rather than relaxing correctness gates.

### H8 — User-reporting system: safe residual-risk channel, not a correctness substitute

**Mandatory pre-beta blockers (never delegate to user reports):** financial ledger divergence; double settlement; causal look-ahead; false determinate outcome; unbounded memory/disk or branch explosion; crash recovery corruption; authentication/authorization bypass; private-data or provider-license leakage; inability to recover/restore user session; unknown critical execution model semantics. A P0/P1 issue affecting money or evidence integrity causes fail-closed, release NO-GO, and where deployed a scoped kill switch/rollback and affected-experiment notice.

**Eligible user-reported residuals after gates pass:** cosmetic/UI layout, device/browser compatibility, minor navigation, confusing labels, low-severity nonfinancial latency, documentation requests, feature suggestions, and bounded edge cases already handled safely as UNRESOLVED. Users may report a financial bug, but reporting is **detection**, not permission to leave known critical faults unresolved.

**Report schema:** report_id; user-consented contact (optional); build/engine/profile/dataset identity; reproducible session/experiment IDs or redacted references; issue category/severity; expected vs actual; bounded revealed tick slice if license allows; safe screenshot optional; command/event hashes; environment; reproduction steps; consent and retention expiry. Default no raw market data, credentials, secrets, user PII, or private broker account identifiers in exported bundles. Size limits, rate limits, access control, deletion/retention policy and user-visible report status required.

**Triage SLA proposal (must be staffed before public beta):** P0 immediate stop/containment on detection; P1 fix before wider rollout; P2 prioritized for next planned patch; P3 backlog. Do not promise exact response hours until operating capacity is funded. User-facing issue state: RECEIVED → TRIAGED → REPRODUCED / NEEDS_INFO / UNAVAILABLE → FIXED → VERIFIED → CLOSED. Financial fix triggers lineage impact scan and revalidation of affected experiment versions. Do not silently alter prior results.

### H9 — Quantified acceptance without invented percentages

Track requirement coverage `verified_requirements / total_applicable_requirements`, risk-weighted test coverage, mutation-test score where meaningful, independently reviewed critical contracts, unresolved critical count, repeatability across seeds, and measured performance against frozen budgets. **Do not translate these ratios into probability that software is 99% correct.** A release may be called “near-complete against specification” only if 100% of P0/P1 requirements have evidence, 0 open P0/P1 bugs, all critical negative tests pass, source rights are adequate for the actual audience, reproducible restore and browser E2E pass, and remaining P2/P3 issues are documented, bounded and user-reportable. Exact numerical coverage thresholds for noncritical items are to be set in V22-0 and approved before tests.

**Traceability matrix columns:** requirement ID; authority owner; risk/severity; design clause; implementation owner/path; test ID; evidence artifact/hash; environment; result; reviewer; waiver rationale (P2/P3 only); issue link; affected experiment lineage; closure date. No waiver for P0/P1 or unknown license rights.

### H10 — Expanded adversarial acceptance cases

| ID | Scenario | Required evidence |
|---|---|---|
| N13 | Two open positions, one ambiguous partial close changes free margin | Shared account freezes or fully separated sound conditional branches |
| N14 | Cancel and fill race during crash/retry | One accepted terminal outcome per causal proof, no negative remaining quantity |
| N15 | Session reopened after engine/parser version changes | Pinned old replay or explicitly incompatible; no silent reinterpretation |
| N16 | V1 OHLC results displayed beside V2 tick results | Visible fidelity labels, separate experiment IDs, no false aggregation |
| N17 | Oracle and engine share rounding bug | Independent hand-derived vectors and mutation test detect error |
| N18 | 99% of quotes valid but all strategy entries fall in gaps | Trade-impact metric exposes unacceptable uncertainty |
| N19 | User reports sensitive screenshot or provider-restricted tick slice | Redaction, access/retention and export denial tested |
| N20 | Malicious rapid seek, parallel sessions and report uploads | Bounded resources, isolation and backpressure |
| N21 | Data rights revoked after previous experiment | Lawful retention/deletion, explicit reproduction-unavailable label |
| N22 | Historical profile lacks margin/liquidity/latency evidence | Simulation assumption or unresolved; no broker-accuracy claim |
| N23 | Recovery from backup after partial restore | Manifest/ledger/cursor hashes reconcile or fail closed |
| N24 | Financial fix changes prior experiment outcomes | Impact list and versioned rerun; old evidence never overwritten |

### H11 — Final decision register

| Item | Design status | Implementation evidence | Release disposition |
|---|---|---|---|
| State machines and accounting invariants | SPECIFIED / REVIEW REQUIRED | Pending | Block until proven |
| Broker execution claim boundaries | SPECIFIED / REVIEW REQUIRED | Pending | Block misleading claims |
| Uncertainty with shared account | SPECIFIED / REVIEW REQUIRED | Pending | Block until proven |
| Independent oracle | TEST CHARTER READY | Pending | Block until proven |
| V1/V2 separation | SPECIFIED / REVIEW REQUIRED | Pending | Block until proven |
| Dataset confidence and trade impact | SPECIFIED / REVIEW REQUIRED | Pending | Block until measured |
| Cost/capacity budgets | MEASUREMENT PLAN READY | Pending | Scope audience to evidence |
| User reporting and triage | SPECIFIED / REVIEW REQUIRED | Pending | No public beta without operational owner |
| Real-feed rights and full Exness benchmark | UNKNOWN / INCOMPLETE | Pending | Block relevant release claims |

**Review-4 verdict:** substantially hardened **planning candidate**, not “99% verified”, not production-ready, not V2.2 implementation authority. The only honest route to a numerical quality claim is to collect independent empirical evidence against pre-registered requirements. No unproven financial correctness is delegated to users.


---

## Design hardening amendment — Review 5: scalable evidence verification

**Goal:** avoid expensive manual per-tick review while retaining soundness. A structurally valid quote is **not** automatically a true market quote, an ordered execution path, or a broker fill. Never convert an unchecked region into a verified assertion.

### Tiered verification pipeline

1. **Tier A — mandatory 100% automated streaming scan, O(N):** stream source once using bounded buffers; validate schema/types/decimal representation, nonnegative prices, Bid<=Ask policy with explicit exception handling, timestamps/precision/timezone, source identity, malformed rows, monotonicity *where source ordering contract permits*, duplicate/tie detection, range and gap summaries, count reconciliation, deterministic content hash, and stable provenance. Emit counters and anomaly intervals without retaining all rows in RAM. Preserve raw bytes where licensed. This scan is linear work, not human line-by-line review; speed depends on actual hardware and I/O.
2. **Tier B — 100% cheap partition checks:** compare chunk count/min/max time, first/last quote, source ordinal bounds, hashes, manifest/index coverage and deterministic re-read of all chunk boundaries; enforce no lost/duplicated ticks and atomic publication. Chunk size and hierarchy follow frozen 42.17/42.19; do not silently substitute a new layout.
3. **Tier C — stratified independent sampling:** reproducible seed, sample by month/session, spread regime, volatility, time of day, provider and anomaly class. Compare independently sourced feeds only where legally and technically available; record mismatches and source incompatibility. Statistical confidence describes the **sampled failure rate under its assumptions**, not proof of universal truth or broker fill. Define sample plan and escalation thresholds before seeing outcomes.
4. **Tier D — risk-triggered deep checks:** inspect 100% of detected anomalies, tied timestamps near order activation/SL/TP, suspicious spreads, gap crossings, price spikes, DST/timezone boundaries, ingestion discontinuities, and affected positions. Use bounded windows and targeted independent oracle, not full expensive re-simulation of every tick.
5. **Tier E — trade-time proof on demand:** evaluate each trade's causal revealed evidence; when all admissible orderings yield identical financial outcome, label `DETERMINATE` under the pinned model; if scenario assumptions determine a result, label `CONDITIONAL` and isolate its ledger; otherwise `UNRESOLVED`, freeze affected authoritative account state and downstream dependencies. Resource-limited proof returns `UNRESOLVED_RESOURCE_LIMIT`. Never simply skip unresolved trades from official win-rate denominator.
6. **Tier F — continuous incremental verification:** cache immutable verification receipts keyed by source/dataset hash, parser/normalizer/schema version, rule-set version, index version, oracle version and execution profile where applicable. Revalidate only affected partitions and dependent experiment lineage after a change; any source/version mismatch invalidates old verification claims. Schedule low-priority offline deep checks; not required to block interactive chart display, but no unverified region is promoted to financial certainty.

### Required classification of dataset regions

- `STRUCTURALLY_VALID`: all mandatory machine checks passed; **not** independently authenticated.
- `SUSPECT`: rule anomaly or disagreement; retain original evidence, mark bounded affected interval.
- `UNVERIFIED_SOURCE`: structural checks passed but authenticity/market representativeness not independently established; do not describe as source-verified.
- `UNRESOLVED_ORDERING`: sequence/availability uncertainty could alter the financial outcome.
- `QUARANTINED`: corrupt, incomplete, unsafe or rights-ineligible artifact; exclude from authoritative financial execution until policy permits.
- `VERIFIED_WITHIN_SCOPE`: explicitly name what was verified (structural, index, comparison, or financial model), exact scope, source and evidence; no blanket accuracy badge.

**Orthogonality:** dataset-quality labels are not the same as trade-outcome labels (`DETERMINATE`, `CONDITIONAL`, `UNRESOLVED`). A structurally valid but independently unverified quote can support a deterministic *model calculation* while still not proving actual market truth. Do not auto-mark every trade unresolved solely because L1 quotes lack broker fill proof; display the simulation/model caveat instead.

### Statistical sampling guardrails

For random independent sampling with zero observed failures, a rough one-sided 95% upper bound on the failure probability is `~3/n` (rule of three) **only under appropriate independent representative sampling assumptions**. Example: n=3,000 with zero observed failures suggests an upper bound near 0.1% for that sampled population, not that the dataset is “99.9% correct” or free of clustered corruption. Time-series defects cluster: stratify by time and regime, inspect all detected high-risk windows, and treat dependence appropriately. Any material discrepancy triggers escalation to adjacent windows, other months, affected sessions and independent source comparison; no silent acceptance.

### Performance and safety

One-pass streaming scan + partition index summary + bounded anomaly queue is the baseline. Prefer batch/vectorized decimal-safe parsing and bounded-memory I/O, but never sacrifice exact Bid/Ask precision or source ordering semantics for speed. Verify deterministic parallel partition processing and boundary continuity; benchmark serial vs parallel on actual representative full dataset before claiming speedups. No hard-coded throughput promise before measurements. Keep chart rendering and quote ingestion distinct from costly per-trade ambiguity proof.

### Verification receipt schema

`dataset_id, raw_hash, parser_version, normalizer_version, schema_version, validation_rules_hash, index_version, partition_id, record_count, min_max_time, boundary_hashes, anomaly_counts, coverage_intervals, sampling_seed, sampling_method, sampling_size, sampling_findings, independent_source_id_if_any, trade_impact_summary, verifier_version, reviewer, measured_runtime, peak_rss, status, artifact_hashes`.

### Additional negative acceptance tests

- **N25:** corruption in one middle partition detected despite clean first/last samples.
- **N26:** anomaly concentrated around rare trading entry windows; global random sample misses it but trade-time checks flag it.
- **N27:** same dataset reprocessed with different parser/rules; old receipts invalidated and dependent results versioned.
- **N28:** parallel validation reorders same-time events; byte-identical canonical event identity/order trust preserved.
- **N29:** structurally valid but fabricated source prices; system does not claim independent authenticity.
- **N30:** financial result requires unbounded tie permutations; result remains unresolved with bounded CPU/RAM.
- **N31:** a missing or duplicate tick across partition boundary is detected by full reconciliation.
- **N32:** source license disallows retaining raw snippets; issue report remains privacy/rights compliant.

**Review-5 verdict:** architecture is efficient in asymptotic design and conservative in evidentiary claims; actual throughput, false-negative rate and cost remain unverified until benchmark and sampling experiments. All P0/P1 safety gates still apply before beta; the user-report system is only a residual-risk channel.


---

## Design hardening amendment — Review 6: user-selected Next Available Quote Execution profile

**Decision source:** Product owner requests execution at the observed available tick quote even when price gaps across a TP/SL trigger; positive and negative slippage are reflected. This is a **simulation profile proposal**, not a claim about a specific broker's legal/exchange fill policy. Do not change V2.1 runtime or frozen contracts in this planning checkpoint.

### Profile identity and semantics

- ID: `NEXT_AVAILABLE_QUOTE_V1`; pinned in the immutable experiment execution profile/passport and exposed prominently in UI/export.
- Quote side: BUY position close uses **Bid**; SELL position close uses **Ask**. Entry-side semantics remain BUY Ask, SELL Bid. Source precision and decimal-safe calculations are preserved.
- For already-active TP/SL orders, the trigger is the **first controller-revealed, causally admissible quote** satisfying the relevant side-specific threshold. At that quote, the model fills the eligible remaining quantity at that **observed quote price**, even if better or worse than the TP/SL level. No synthetic intermediate tick, interpolation, or retroactive order activation.
- BUY TP triggers when Bid >= TP; BUY SL when Bid <= SL. SELL TP when Ask <= TP; SELL SL when Ask >= SL. The same quote-side semantics must be explicitly specified for entry/pending orders before implementation, rather than assuming TP/SL rules apply to every order type.
- Illustrative cases (assuming order active, trusted ordering, valid quote and full immediate simulated liquidity): BUY entry 1, TP 2, next Bid 8 => exit 8; BUY SL 0.5, next Bid 0.2 => exit 0.2; SELL TP 2, next Ask 1 => exit 1; SELL SL 3, next Ask 5 => exit 5.
- The profile assumes immediate execution at the eligible quote and full liquidity for the modeled order size. **Level-1 Bid/Ask does not prove executable volume or actual broker price improvement.** Therefore every fill is labeled `SIMULATED_FILL`, and a user-facing warning names the assumption. This profile is not necessarily the most conservative, and may overstate positive TP slippage. If model inputs cannot justify order activation, quote side, source chronology or event outcome, return `UNRESOLVED`, not an invented fill.
- Distinguish a **marketable TP/SL trigger modeled as quote execution** from a real resting limit order. Real limit orders have limit-price constraints; the product must not present the chosen model as faithful execution of all real-world TP limit orders. If a strict limit-order broker profile is added later, it requires a separate pinned profile with a different fill contract, not an implicit exception to this one.
- No discretionary post-trigger extra slippage or spread applied on top of the observed Bid/Ask unless a separately versioned and disclosed broker cost/slippage model explicitly requires it. Avoid double counting spread. Commissions/swap/financing remain separate, versioned assumptions.
- Missing feed periods and discontinuous timestamps do not automatically make a result unresolved: a valid first eligible quote may be used by this model, **provided** the selected feed, event ordering, order activation and no competing unknown outcome are sufficient. If missing evidence can change whether SL or TP was triggered first, mark `UNRESOLVED`; do not silently choose the favorable outcome.
- A tied timestamp group is atomic. If multiple admissible orderings produce different fills or account outcomes, prove invariance or return `UNRESOLVED` / isolated `CONDITIONAL`; do not pick an arbitrary row order.
- Protocol mode's no-manual-close, pending-only, pinned RR/risk rules remain unchanged. RR planned from levels may differ from **realized** RR due to slippage. Display both; never overwrite planned RR with realized RR.

### Required acceptance cases

| ID | Fixture | Expected |
|---|---|---|
| Q01 | BUY TP=2, first eligible Bid=8 | Exit=8, positive modeled slippage +6 |
| Q02 | BUY SL=0.5, first eligible Bid=0.2 | Exit=0.2, adverse modeled slippage -0.3 |
| Q03 | SELL TP=2, first eligible Ask=1 | Exit=1, favorable modeled slippage +1 (sell-position perspective) |
| Q04 | SELL SL=3, first eligible Ask=5 | Exit=5, adverse modeled slippage -2 |
| Q05 | Order accepted after same-timestamp quote | No retroactive fill |
| Q06 | Equal-time group allows both TP-first and SL-first outcomes | Unresolved unless invariant proof |
| Q07 | Quote gap with no competing ambiguous outcome | Fill at first admissible quote, not fabricated intermediate price |
| Q08 | Bid/Ask spread already included | No double spread charge |
| Q09 | Partial close with shared margin | Correct quantity/account ledger and uncertainty propagation |
| Q10 | Crash/retry at gap fill | Exactly one durable economic effect |
| Q11 | Chart timeframe change | Same tick-derived fill |
| Q12 | Export/reopen after profile version change | Original pinned profile and receipt preserved |

**Decision status:** user-approved behavioral intent, implementation pending explicit V2.2 authorization and reconciliation with existing frozen contract owners. Profile must be reviewed for fidelity and financial correctness before release.


---

## Review 7 — broker-rule completeness, 99% measurable gates, residual anomaly reporting

**Status:** design/research candidate only. References inspected 2026-10-09: QuantConnect LEAN latest-price fill model (https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/supported-models/latest-price-model), LEAN equity fill model (https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/supported-models/equity-model), Backtrader order execution (https://www.backtrader.com/docu/order-creation-execution/order-creation-execution/) and order types (https://www.backtrader.com/docu/order/). These are **reference behaviors**, not proof of a particular broker's execution. Compare licensed broker terms separately before naming a broker profile.

### Required rule inventory (single engine, versioned profile)
- **Order admission:** order type, side, minimum tick/lot, decimal precision, stop distance, risk limits, market/session availability, quote freshness, pending-order expiration, idempotent placement, explicit accepted/active timestamps.
- **Entry execution:** market BUY at eligible Ask / SELL at Bid; pending buy/sell limit vs stop vs stop-limit require separate trigger and fill state machines. Do not silently treat stop-limit as stop-market. Reject unsupported types rather than simulate incorrectly.
- **Exit execution:** BUY close Bid / SELL close Ask, active TP/SL/OCO linkage, next-available-quote profile, favorable/adverse gap behavior, no intermediate invented quote, no double spread or slippage.
- **Event ordering:** nanosecond precision if provided; same-timestamp atomic group, deterministic only where ordering evidence exists; no retroactive fill; TP-vs-SL ambiguity; market closed/reopen and weekend/holiday gaps; feed outage vs real market jump.
- **Execution capacity:** quote != tradeable size; explicitly assume full fill or add versioned partial-fill/liquidity model with independent evidence. Partial close, partial TP/SL, pending remaining quantity, cancellation races, stop activation and OCO cancellation all require accounting invariants.
- **Account ledger:** realized/unrealized P&L, spread, commission, swap/financing, contract size, pip/tick value, currency conversion, rounding, margin, margin calls, liquidation order, negative equity, deposits/withdrawals; broker-dependent parameters cannot be hardcoded as universal.
- **Replay/durability:** same fill across chart timeframes, seek/reset/resume, cancellation, crash/retry, duplicate commands, PostgreSQL recovery, provenance, export/reopen, versioned model migrations; every economic effect exactly once.
- **Data rights and quality:** source and license restrictions, missing quote/side, crossed market, stale timestamps, anomalous spikes, discontinuities, feed/provider disagreements, structural scan and partition hashes; structural validity != authenticity.
- **Protocol integrity:** locked planned RR/risk, pending-only where specified, no manual close, realized RR separate from planned RR; Free Style retains its own explicit contract.

### Explicit conflict-resolution and unsupported cases
A resting TP **limit order** must never be misrepresented as a guaranteed market execution at any price. Product owner's chosen `NEXT_AVAILABLE_QUOTE_V1` is a **clearly disclosed hypothetical quote-trigger fill model**, not universal broker semantics. LEAN and Backtrader demonstrate distinct limit, stop, and stop-limit behaviors, stale quote restrictions and gap rules. Build profile adapters with immutable semantics and common ledger, not multiple competing engines. Any rule that cannot be faithfully supported must be `UNSUPPORTED_PROFILE_RULE` or `UNRESOLVED` with clear scope.

### Operational 99% target — not “99% real broker fidelity”
- **100%** of mandatory invariants, known critical event-order cases, rights gates, and P0/P1 adversarial tests must pass. No unresolved critical bug accepted for release.
- **>=99%** of pre-registered *eligible, in-scope* scenario fixtures must have a correctly classified result (`DETERMINATE`, `CONDITIONAL`, `UNRESOLVED` or explicit `UNSUPPORTED`) verified against an independently authored oracle. Classification correctness is the metric, **not** proportion of determinate fills and **not** an assertion of market truth.
- Record numerator, denominator, excluded cases, coverage by order type and data regime, independent oracle version, and failure severity. A high aggregate score cannot hide a 0%-tested rare critical path. Target is a **release gate**, not a current achieved result.
- No percentage can be claimed until fixtures, tests, representative datasets and full benchmark have actually run. Use zero-tolerance for look-ahead, invented prices, corrupted financial ledger, duplicate settlement, source/license violations.

### User anomaly reporting (after mandatory internal gates)
- UI action **Report replay anomaly** on trade/event, with user-friendly categories: wrong entry/exit price, unexpected TP/SL, spread/slippage, gap, partial close, missing quote, account P&L/margin, replay inconsistency, other.
- Automatically attach a minimal **redacted reproducibility bundle**: experiment/passport ID, dataset/hash and license-safe provenance, parser/rules/index/engine/profile versions, event/position/order IDs, tick ordinal and bounded time window, model trigger and fill trace, expected vs observed, deterministic replay seed, relevant validation receipt and screenshot reference when user consents.
- Never automatically upload proprietary raw tick data, credentials, PII, or restricted market excerpts. Support report-only hashes and user consent; enforce access control, retention, deduplication and abuse throttling.
- Triage: P0 incorrect authoritative financial outcome, look-ahead, unauthorized data leak => immediately block/restrict affected scope and investigate; P1 repeatable severe misfill/ledger issue => gated remediation; P2 UX/diagnostic discrepancies => queue and report; P3 feature requests => backlog. Notify reporter of received/in-review/fixed/needs-evidence states without promising SLA not staffed.
- A report must not retroactively rewrite an immutable experiment. Fixes create versioned evidence/receipts and explicit re-run; preserve original audit lineage.
- Residual anomalies may be user-reported, but **known uncertainty is proactively labeled**; do not silently convert unknowns to profits and wait for users to complain.

### Expanded acceptance matrix
R01 market BUY/SELL correct quote side; R02 limit price constraint; R03 stop-market adverse gap; R04 stop-limit trigger without executable limit remains pending; R05 pending expiry at session boundary; R06 stale quote blocked; R07 OCO atomicity and same-time race; R08 partial fill then partial cancel; R09 contract-size and commission P&L; R10 swap/currency conversion; R11 margin liquidation with shared positions; R12 weekend gap; R13 duplicate command and crash recovery; R14 chart timeframe invariant; R15 invalid crossed Bid/Ask quarantine; R16 license-safe anomaly bundle; R17 profile version change invalidates comparison not history; R18 adversarial fixture with both outcomes possible remains unresolved; R19 missing volume cannot be marketed as broker-confirmed fill; R20 no critical failure hidden by aggregate 99% fixture score.

**Release note:** all R01–R20 are proposed fixtures, not executed tests. Main/V2.1 authority remains untouched.
