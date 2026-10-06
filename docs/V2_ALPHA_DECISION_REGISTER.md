# Backtest Lab v2 Alpha — Frozen Decision Register & Change Control

> This register exists to prevent architecture drift during execution. Decisions marked **FROZEN** are not reopened because a new library, idea, benchmark trick, AI suggestion or aesthetic preference appears.

## 1. Frozen decisions

| ID | Status | Decision |
|---|---|---|
| ADR-PROD-001 | FROZEN | v2 Alpha is a trustworthy manual historical replay/research product, not automated/live trading. |
| ADR-SCOPE-001 | FROZEN | Alpha MUST/NOT scope is owned by V2_ALPHA_FROZEN_SPEC.md; new ideas go to parking lot. |
| ADR-ARCH-001 | FROZEN | One authority chain: evidence → dataset → timeline → virtual clock → execution → canonical events → account/journal/research. |
| ADR-CHART-001 | FROZEN | Lightweight Charts remains default renderer unless STITCH's predefined donor gate proves replacement net-positive. |
| ADR-OSS-001 | FROZEN | Commodity OSS enters through adapters; donor libraries do not own BTL financial/research truth. |
| ADR-DRAW-001 | FROZEN | Drawing choice uses OpenAlgo → OpenCharts → KEEP decision tree, based on predefined gates; no subjective mid-build switch. |
| ADR-IND-001 | FROZEN | Indicator replacement may be mixed calculator/host; causality and semantic parity outrank catalog size. |
| ADR-ANALYTICS-001 | FROZEN | Mature analytics primitives may replace calculators; BTL owns canonical grouping, provenance, Passport and orchestration. |
| ADR-DATA-001 | FROZEN | Future precision settlement is tick-native; OHLC alone never settles v2 precision trades. |
| ADR-DATA-002 | FROZEN | Provider/feed identity and dataset version/hash remain attached through research. |
| ADR-DATA-003 | FROZEN | Unknown/missing evidence remains unknown; no silent repair/interpolation/fabrication. |
| ADR-STORAGE-001 | FROZEN | Partitioned immutable disk storage + index is default; Parquet/Arrow-compatible approach is preferred subject to frozen benchmark gate, not ideology. |
| ADR-EXEC-001 | FROZEN | BTL owns execution authority. Donor chart/trading UI cannot settle fills/PnL. |
| ADR-EXEC-002 | FROZEN | Bid/ask transaction sides are explicit and versioned; replay/UI speed cannot affect outcome. |
| ADR-LEGACY-001 | FROZEN | v1 MODELLED results remain labelled legacy/modelled; never relabel as tick-observed. |
| ADR-SESSION-001 | FROZEN | Sessions are durable small state; workers are ephemeral/replaceable. |
| ADR-CACHE-001 | FROZEN | Shared cache is optional optimization, never correctness dependency. |
| ADR-PROTOCOL-001 | FROZEN | Risk/RR/pending/intervention rules belong to versioned Protocol, not hard-coded universal engine behavior. |
| ADR-PASSPORT-001 | FROZEN | Serious research results bind immutable dataset/method/protocol/engine/calculator lineage. |
| ADR-DB-001 | FROZEN | PostgreSQL remains application durable database for v2 Alpha; no DB rewrite. |
| ADR-API-001 | FROZEN | FastAPI composition remains backend API direction; no framework rewrite. |
| ADR-FRONTEND-001 | FROZEN | React/Vite remains frontend; no framework rewrite. |
| ADR-INFRA-001 | FROZEN | Start single-node/simple hosted topology; complexity is introduced only by predefined measured gates. |
| ADR-REDIS-001 | FROZEN | No Redis-compatible dependency until benchmark demonstrates a concrete shared coordination/cache need. |
| ADR-RUST-001 | FROZEN | No Rust rewrite until profiling proves a required hot path cannot meet the frozen envelope after algorithm/data-layout/process improvements. |
| ADR-K8S-001 | FROZEN | No Kubernetes for v2 Alpha. |
| ADR-RIGHTS-001 | FROZEN | Accessibility is not redistribution permission; rights gate is independent from engineering completion. |
| ADR-RELEASE-001 | FROZEN | Closed rollout is INTERNAL→5→15→30→50→100; progression is evidence-gated. |
| ADR-WORK-001 | FROZEN | Execute one ledger checkpoint per validated Git checkpoint unless a bounded journey is explicitly authorized. |
| ADR-CHANGE-001 | FROZEN | Normal execution findings choose a predefined branch; they do not reopen strategy. |

## 2. Predefined decision trees

### DT-DRAW
Evaluate current BTL, pinned OpenAlgo and pinned OpenCharts before selection using the exact MUST gates and lexicographic ranking in `V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md`. A disqualified candidate cannot win. Do not search for a fourth engine during the frozen journey.

### DT-IND
Evaluate calculator and host layers separately. Semantic parity, warmup, visible-prefix causality, replay/timeframe and pane lifecycle are MUST gates. Rank qualifying candidates by the deterministic rubric in `V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md`. Mixed calculator/host outcome is allowed. Catalog size never overrides correctness.

### DT-ANALYTICS
1. Define metric semantics first.
2. Compare candidate library output with authored fixtures.
3. Adopt only metrics with matching/explicitly accepted semantics.
4. Otherwise retain/build the small pure BTL calculator.
5. Never delegate Passport/orchestration/grouping authority.

### DT-STORAGE
1. Benchmark the frozen candidate layout on authorized representative data.
2. Required properties: immutable versioning, bounded reads, random seek, sequential replay, corruption detection, atomic publication.
3. If candidate satisfies correctness and the current hardware envelope → adopt.
4. If performance fails, optimize partition/index/compression parameters first.
5. If still fails, evaluate one alternative columnar/binary layout using the same benchmark.
6. No database/distributed-system redesign unless both bounded candidates fail the required envelope.

### DT-CACHE
1. Run random-cursor load test without shared cache.
2. If target cohort meets latency/RAM/I/O envelope → NO CACHE.
3. If it fails primarily because repeated immutable chunks are reread/decompressed, introduce a byte-bounded shared cache and rerun.
4. If failure is elsewhere, cache is not the fix.
5. Cache-disabled deterministic hashes must equal cache-enabled hashes.

### DT-PERFORMANCE
Optimization order is frozen:
1. prove correctness;
2. profile;
3. data layout/index;
4. bounded chunking/prefetch;
5. algorithmic hot path;
6. process concurrency;
7. optional cache;
8. compiled/Rust hot path only under ADR-RUST-001;
9. distributed infrastructure only after single-node evidence.

### DT-CAPACITY
At each cohort:
- PASS → advance only after all release gates pass;
- FAIL resource/latency → profile and follow DT-PERFORMANCE;
- FAIL correctness/data/security/recovery → fix same subsystem and rerun;
- do not lower correctness to meet capacity.

### DT-DATA-RIGHTS
- rights permit intended audience/storage/display → launch candidate;
- rights permit personal/internal only → internal engineering only;
- rights unclear → UNVERIFIED, no external launch;
- rights revoked → stop serving affected data, retain only legally permitted metadata/evidence.

### DT-EVIDENCE
- sufficient ordered bid/ask chronology → process under pinned execution profile;
- missing side/sequence/coverage can alter outcome → UNRESOLVED/AMBIGUOUS;
- corrupt evidence → REFUSE;
- never fallback to OHLC precision settlement.

## 2A. Additional frozen decisions after PF-0 hardening

- **ADR-EXEC-003 FROZEN:** exact Alpha execution/financial semantics are owned by `V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md`; X-1 cannot redesign them.
- **ADR-SESSION-002 FROZEN:** committed financial sessions never rewind; backward exploration forks immutable lineage.
- **ADR-UNCERTAINTY-001 FROZEN:** outcome-changing uncertainty commits no fill/P&L and propagates as UNRESOLVED.
- **ADR-AGG-001 FROZEN:** Alpha presentation candles use revealed bid/ask mid with UTC epoch-aligned buckets per Data/Ops contract.
- **ADR-RIGHTS-002 FROZEN:** rights are checked before provider-specific production integration and again before external cohort.
- **ADR-SLO-001 FROZEN:** Alpha reference hardware/SLO/resource gates are owned by Data/Ops contract.
- **ADR-RESEARCH-002 FROZEN:** advanced regime/OOS/destruction/multiple-testing work is post-Alpha for first cohort.
- **ADR-MIGRATION-001 FROZEN:** v1 financial truth is not silently migrated; per-store matrix is owned by Data/Ops contract.
- **ADR-TRANSACTION-001 FROZEN:** command dedup + canonical events + account/order/session revision commit atomically.
- **ADR-SECURITY-001 FROZEN:** external Alpha requires the frozen threat-model gates.
- **ADR-DEPENDENCY-001 FROZEN:** no opportunistic major dependency upgrades during journey.

- **ADR-CAPACITY-001 FROZEN:** accepted heavy work is bounded by benchmark-derived admission, queue, worker, DB and browser budgets; overload rejects before heavy allocation.
- **ADR-RECOVERY-001 FROZEN:** indexed resume/recovery avoids complete-prefix positioning and mass recovery obeys the same bounded admission controls.
- **ADR-OBSERVABILITY-001 FROZEN:** Alpha capacity telemetry is required but bounded-cardinality/non-authoritative; observability failure cannot corrupt or block committed financial truth.

## 3. Hard invalidation conditions

A FROZEN decision may be reopened only if at least one is evidenced:

1. license/legal terms make the planned use impermissible;
2. data rights make the intended launch mode impermissible;
3. security vulnerability cannot be acceptably mitigated within the frozen architecture;
4. a mandatory correctness invariant is mathematically/technically impossible under the decision;
5. reproducible benchmark shows the frozen design cannot meet an already-defined required product envelope after its predefined optimization tree is exhausted;
6. required upstream is unavailable/abandoned in a way that blocks supported deployment and no pinned safe version is acceptable;
7. two frozen decisions are proven contradictory;
8. the human explicitly changes the Alpha business/product requirement.

“Found a cooler library,” “AI recommends another stack,” “implementation is annoying,” “credits are running out,” or “this might be cleaner” are NOT hard invalidations.

## 4. Change request protocol

On hard invalidation:

```text
STOP implementation.
CR-ID:
Invalidated ADR(s):
Evidence:
Why predefined fallback cannot resolve it:
Affected checkpoints:
Affected data/migrations:
Security/license/rights impact:
Options considered:
Recommended minimal change:
Regression/benchmark plan:
Rollback:
Human approval required: YES
```

No implementation of the revised architecture begins until the change request is approved and the affected spec/ledger/ADR is re-frozen.

## 5. Parking lot rule

All non-invalidating discoveries are recorded for post-Alpha. They cannot alter current Alpha scope or checkpoint order. Examples: social features, AI agents, extra markets, new chart engines, mobile app, live broker, L2/L3, novel databases, extra analytics.

## 6. Autonomous execution meaning

“Without intervention” means:
- Work does not ask the human to choose among normal implementation alternatives already covered by this register;
- Work executes the predefined branch produced by tests/benchmarks;
- a failed acceptance test causes repair/retry within the same frozen design;
- a checkpoint completes only with evidence and Git gates;
- the journey continues to the next authorized ledger checkpoint when the human has explicitly authorized the complete frozen journey.

It does **not** mean bypassing security, licensing, rights, destructive-operation safeguards, failed tests or a genuine hard invalidation.
