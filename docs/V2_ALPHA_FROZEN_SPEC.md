# Backtest Lab v2 Alpha — Frozen Product & Engineering Specification

> **PLAN-FREEZE candidate.** This specification freezes the intended v2 Alpha product, system ownership and execution policy. It is not evidence that the runtime already implements these behaviors.
>
> Operational implementation authorization remains governed by `AI_CONTEXT/04_CURRENT_PHASE.md`. Once the PLAN-FREEZE journey is accepted, normal execution follows the frozen ledger and decision rules; redesign is prohibited except through the hard-invalidation process in the Decision Register.

## 0. Normative hardening overlay

This specification is interpreted together with:
- [Execution, Financial & Evidence Contract v1](V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md);
- [Data, Operations & Release Contract v1](V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md);
- [Research Metrics Contract v1](V2_ALPHA_RESEARCH_METRICS_CONTRACT.md);
- the existing [Frozen Trading UX Specification v1](TRADING_METHOD_SESSION_SPEC.md).

Precedence for overlapping subjects:
1. operational authorization/status: `AI_CONTEXT/04_CURRENT_PHASE.md`;
2. market-data evidence/fidelity policy: `MARKET_DATA_STANDARD.md`;
3. Protocol/Method/Session user workflow: `TRADING_METHOD_SESSION_SPEC.md`;
4. v2 execution/financial/evidence semantics: `V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md`;
5. data/aggregation/operations/release gates: `V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md`;
6. research metric formulas: `V2_ALPHA_RESEARCH_METRICS_CONTRACT.md`;
7. this file for Alpha scope and system ownership;
8. Decision Register for choice/change rules;
9. Frozen Execution Ledger for order of work.

A lower item cannot broaden or contradict a higher subject owner. Material conflict is a hard invalidation, not an invitation to choose.

## 1. Alpha promise

A closed-alpha user can authenticate, open an authorized XAUUSD historical dataset, start or restore an independent replay session, inspect a TradingView-like chart, use core drawings and indicators, define or select a Method, optionally run under a Protocol, place manual market/limit/stop orders with explicit risk/SL/TP, replay without look-ahead, receive deterministic tick-evidence-based execution when evidence is sufficient, journal/review the resulting canonical trades, and inspect reproducible basic research tied to an Experiment Passport.

If required evidence is insufficient for an execution claim, the system refuses/marks the outcome unresolved rather than silently falling back to OHLC ordering.

## 2. Alpha MUST

- verified user identity and private workspace;
- one supported launch instrument: XAUUSD/Gold with provider identity preserved;
- one rights-approved launch dataset path; bounded initial history is acceptable;
- independent user replay sessions;
- authoritative tick timeline where the launch mode claims precision execution;
- candles derived for visualization;
- chart navigation/replay;
- the eight existing minimum drawing capabilities: Trend Line, Horizontal Line, Vertical Line, Rectangle, Fibonacci Retracement, Arrow, Text and Measure;
- seven current indicator families at minimum;
- market, limit and stop;
- long and short;
- pending lifecycle/cancel;
- SL/TP;
- explicit bid/ask side semantics;
- explicit spread/cost profile;
- risk-based order UX;
- canonical event/trade log;
- account/balance/PnL reconciliation;
- save/pause/resume/restore;
- Method;
- Quick and Planned session concepts;
- optional Protocol with enforceable frozen rules;
- Experiment Passport;
- journal;
- basic descriptive research + R/path metrics required by the execution ledger;
- deterministic/no-look-ahead tests;
- tenant isolation;
- bounded workers/backpressure;
- recovery;
- telemetry;
- data-rights gate;
- progressive closed-alpha rollout.

## 3. NOT in initial Alpha

No scope expansion for:
- live broker execution;
- L2/L3 order-book or queue-position simulation;
- market impact/smart routing;
- AI trading/strategy generation;
- automated strategy execution;
- social/community;
- native mobile;
- huge multi-asset catalog;
- advanced portfolio optimization;
- Kubernetes;
- distributed database;
- Rust rewrite;
- arbitrary plugin marketplace;
- public raw tick download unless separately licensed;
- advanced research beyond frozen alpha gates merely because a library exposes it.

These belong to post-alpha parking lot unless a hard business requirement formally changes.

## 4. Existing-system disposition

| Existing asset | Alpha disposition | Rule |
|---|---|---|
| React/Vite frontend | KEEP | no framework rewrite |
| Lightweight Charts 5.2.1 | KEEP DEFAULT | replace only if frozen STITCH decision tree selects a demonstrably superior path |
| 8-drawing engine | STITCH CANDIDATE | preserve until accepted replacement parity |
| 7 indicator engine/calculators | STITCH CANDIDATE | visible-prefix/no-look-ahead semantics are protected |
| native Volume | KEEP | independent from indicator replacement |
| candle replay v1 | KEEP AS COMPAT/ROLLBACK | not precision execution authority |
| v1 trading simulator/account | KEEP AS COMPAT/ROLLBACK | migrate behind v2 authority; never relabel historical MODELLED results |
| Risk/Reward tool | KEEP DOMAIN / STITCH PRESENTATION | domain command belongs to BTL |
| Analysis/journal | KEEP/MIGRATE | become projections over canonical v2 events |
| economic-news research | KEEP | no Alpha expansion required |
| Method/Session prototype | KEEP AS PROTOTYPE EVIDENCE | canonicalize, do not promote memory-only demo as production |
| backend contracts/application | KEEP | compose; do not create competing contract layer |
| PostgreSQL persistence | KEEP | durable source for supported application state |
| FastAPI identity | KEEP | compose into hosted product |
| workspace ownership | KEEP | server-side tenant authority |
| precision/evidence policy | KEEP | evidence may only retain/downgrade uncertainty |
| canonical tick/provider/timeline V1 | KEEP | foundation for v2 truth |
| 42.17 storage/index contract | KEEP | normative storage direction |
| preserved 42.18 draft | RECONCILE SELECTIVELY | never wholesale merge |
| 42.19 sidecar contract | KEEP | reconciliation authority |
| decade M1 candles | KEEP FOR CHART/COMPAT | not tick execution truth |
| private provider samples | PRIVATE EVIDENCE ONLY | never publish without rights |
| AI/social/live-broker ideas | DEFER | post-alpha |

## 5. Final authority chain

```text
Provider source evidence
   ↓
Provider Adapter
   ↓
Canonical Tick + Dataset Identity/Version/Hash
   ↓
Immutable Storage + Time Index
   ↓
Authoritative Tick Timeline
   ↓
Session Virtual Clock
   ↓
Tick Execution Authority
   ↓
Canonical Event/Trade Log
   ├──► Account projection
   ├──► Journal projection
   ├──► Experiment Passport
   └──► Research calculators/jobs

Revealed ticks
   ↓
Tick→Candle Aggregator
   ↓
Chart / Drawings / Indicators / UI

UI commands ───────────────► domain authorities above
UI/donor libraries NEVER settle financial truth.
```

Exactly one owner per truth. Presentation may be replaced; authority may not be duplicated.

## 6. Market-data behavior freeze

- UTC internally; preserve source timezone/provenance.
- Fixed-point integer/exact-decimal representation; no binary-float invented precision in canonical financial evidence.
- Preserve provider symbol/feed identity even when normalized to XAUUSD.
- Raw/source evidence immutable where rights permit.
- Normalization/validation creates versioned derived artifacts; never overwrite prior experiment identity.
- Missing fields remain missing.
- Equal timestamps without trustworthy sequence remain chronology-limited; source ordinal does not manufacture venue sequence.
- Invalid/corrupt evidence fails closed.
- Gaps are reported, not interpolated.
- Bid/ask historical spread is preserved when supplied.
- Candles are derived from revealed events only.
- No OHLC-only settlement in target v2 Alpha precision mode.
- If launch data cannot support the required precision claim, launch mode must be explicitly downgraded/refused; it cannot silently model intrabar truth.

## 7. Execution behavior freeze

Exact v2 Alpha execution and financial semantics are frozen by `V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md`. X-1 materializes/verifies schemas and golden vectors; it does not choose product semantics. The following summary is non-exhaustive:

- Long market entry consumes/uses the buy side (ask); long liquidation tests the sell side (bid).
- Short market entry uses the sell side (bid); short liquidation tests the buy side (ask).
- Pending trigger side follows the side required to transact under the selected versioned execution profile.
- An observed quote crossing establishes feed-path eligibility, not proof of broker liquidity/fill.
- No interpolation between discrete historical quotes as observed fill evidence.
- Spread, commission, slippage/latency assumptions are versioned execution-profile inputs; missing historical facts are not fabricated.
- Market/limit/stop, activation, cancellation, SL/TP and exits produce canonical events.
- Equal-time ordering follows trustworthy provider sequence when available; otherwise unresolved ordering that can change outcome must not be guessed.
- Replay speed/browser refresh cannot affect event order or fills.
- Duplicate command IDs are idempotent/refused according to frozen revision rules, never double-settled.
- Gap behavior must be explicit in C1 and must never invent an intermediate observed price.
- Partial exit is supported only under the frozen C1 semantics and must reconcile to the same canonical position identity.
- Manual early close is allowed in Free/Quick mode; a Protocol may forbid it and record/refuse violations according to its frozen rule.
- Existing v1 MODELLED outcomes remain historical compatibility artifacts, never silently migrated into OBSERVED tick outcomes.

## 8. Session behavior freeze

States:
`CREATED → ACTIVE ↔ PAUSED → SUSPENDED → RESTORED → ACTIVE → COMPLETED`.

Rules:
- each session pins dataset/version and virtual cursor;
- session state is small and durable;
- paused/suspended sessions do not require dedicated heavy workers;
- worker death cannot be session death;
- restore resumes from committed revision only;
- stale client revisions are rejected;
- committed financial events are not undone by chart navigation;
- backward navigation cannot bypass settlement; where incompatible with committed trades, cannot rewind the authoritative financial session; backward exploration forks a new session with lineage under the Execution Contract;
- timeframe/chart changes do not alter execution chronology;
- one user's cursor/cache behavior cannot change another user's result.

## 9. Method / Protocol freeze

Method is versioned descriptive strategy identity:
- instrument scope;
- setup;
- inclusion;
- exclusion;
- tags/notes;
- immutable historical versions.

Session may be Quick or Planned.

Protocol is optional but, once attached/started, version-pinned:
- risk policy;
- RR policy;
- pending/order limits;
- early-close/intervention permission;
- checklist requirements;
- sample target/period where planned;
- deviation semantics.

Existing preferred protocol defaults such as RR 1:1.25 and maximum four pending orders are product defaults/configuration, not universal engine constants. The Protocol version owns them.

Changing a Method/Protocol for future work creates a new version; historical experiments retain the original.

## 10. Experiment Passport freeze

Every reproducible experiment binds at minimum:
- dataset/provider/feed/instrument/version/hash;
- period;
- Method version/hash;
- Protocol version/hash or explicit none;
- execution-profile/version;
- engine version;
- calculator/research version;
- regime version if used;
- RNG algorithm/seed if used;
- planned vs actual sample;
- exclusions/deviations;
- lineage/hypothesis family;
- result version.

A result without sufficient provenance may be displayed as legacy/non-reproducible but cannot be promoted to reproducible research.

## 11. Research Alpha freeze

Required before closed Alpha:
- trade count;
- wins/losses/break-even;
- realized P&L;
- win rate;
- average win/loss;
- expectancy;
- profit factor;
- drawdown;
- streaks;
- R-multiple;
- MAE/MFE where event path permits;
- duration/distribution summaries;
- reconciliation status;
- seeded Monte Carlo for outcome/DD/streak distributions.

Regime, destruction/robustness, OOS/walk-forward and multiple-testing controls are POST-ALPHA for the first closed cohort and are not Alpha release blockers.

## 12. UI freeze

The target remains a TradingView-like manual research workspace, not a generic quant IDE.

- chart remains primary surface;
- drawing/indicator controls are presentation;
- Long/Short planning opens risk/order review;
- order confirmation precedes authoritative command submission;
- Method/Session context is visible;
- Protocol restrictions are visible before action;
- journal/analysis derive from canonical identity;
- replay controls operate virtual time, not financial truth directly;
- UI may throttle/coalesce visual updates but never execution processing;
- no raw-tick flood to browser by default.

## 13. Persistence/versioning freeze

Version all durable semantic contracts:
- dataset;
- tick encoding;
- drawing persistence;
- Method;
- Protocol;
- execution profile/semantics;
- event/account schema;
- Passport;
- research result.

Migration is explicit: READ → VALIDATE → MIGRATE OR REFUSE. Never silently reinterpret old evidence under new semantics.

## 14. Hosted Alpha infrastructure freeze

Initial architecture remains simple:
```text
TLS/reverse proxy
   ↓
Web frontend
   ↓
FastAPI/API composition
   ├─ PostgreSQL
   ├─ market-data storage/index
   └─ bounded replay/research workers
```

A cache/coordination service is not mandatory. Add one only through the frozen performance decision rule. No Kubernetes/microservice decomposition before measured need.

## 15. Resource-safety freeze

Before external Alpha every untrusted/burst resource must have a configured bound:
- request body;
- range/page;
- active heavy jobs;
- queue;
- worker memory/process;
- cache bytes if present;
- browser event/update rate;
- session checkpoint size;
- timeout;
- cancellation;
- file handles;
- decompression/read chunk.

When capacity is exceeded: queue, throttle or reject explicitly; never allocate unboundedly.

## 16. Security/recovery freeze

Alpha requires:
- verified identity;
- server-side workspace/object authorization;
- A cannot read/write B;
- TLS;
- secret separation;
- input/body/rate limits;
- dependency/security review;
- backup/restore;
- worker/API/DB restart behavior;
- session restore;
- corrupt dataset refusal;
- audit/diagnostic events without secrets.

## 17. Launch-data freeze

Technical product completion and public data rights are separate gates.

Closed Alpha may use only a dataset whose permitted audience/use is documented for that launch mode. If only personal/internal rights are established, external Alpha cannot use that dataset; the engineering plan continues using synthetic/private acceptance while procurement/rights resolves.

Launch history length is a configured product constraint after rights/coverage evidence. Six months is only a candidate product-validation window, never a substitute for dataset quality, rights or strategy-robustness evidence.

## 18. Alpha release ladder

`INTERNAL → 5 → 15 → 30 → 50 → 100 → BETA REVIEW`.

No automatic cohort increase. The frozen release gate evaluates:
- correctness;
- deterministic hashes;
- unresolved severity-1/2 defects;
- data integrity;
- p95/p99 latency/resource envelope;
- recovery;
- tenant/security findings;
- telemetry sufficiency;
- rights;
- support/incidents.

Failure means fix the same checkpoint and re-run; it does not invite redesign.

## 19. Completion meaning

“v2 Alpha complete” means the frozen Alpha promise is implemented and evidenced. It does not mean every future Backtest Lab idea is built.

All new ideas discovered during execution go to a parking lot and cannot enter Alpha unless the Decision Register hard-invalidation/change-control process approves a plan revision.
