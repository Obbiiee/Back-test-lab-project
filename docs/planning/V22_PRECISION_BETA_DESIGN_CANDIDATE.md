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
