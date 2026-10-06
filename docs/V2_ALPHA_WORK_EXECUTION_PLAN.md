# Backtest Lab v2 Alpha — Work Execution Plan

> **Role:** execution-planning authority beneath the Engineering Master Plan.
>
> **Important:** this file describes the complete intended work sequence but grants **no implementation authorization**. `AI_CONTEXT/04_CURRENT_PHASE.md` remains the sole operational authorization/status owner. A future Work/Codex agent must verify the actual repository state before executing any checkpoint.
>
> **Planning baseline:** GitHub `main` after STITCH-0, 2026-10-06.

## PLAN-FREEZE overlay

The detailed plan below is now constrained by three freeze documents:
- [Frozen Product & Engineering Specification](V2_ALPHA_FROZEN_SPEC.md)
- [Frozen Decision Register & Change Control](V2_ALPHA_DECISION_REGISTER.md)
- [Frozen Execution Ledger](V2_ALPHA_FROZEN_EXECUTION_LEDGER.md)

When this older decomposition leaves a routine choice open, the frozen specification/register/ledger resolves it. None of these planning files overrides operational authorization in `AI_CONTEXT/04_CURRENT_PHASE.md`.

## 0. Mission

Deliver a trustworthy **closed v2 Alpha** of Backtest Lab with:
- mature charting/drawing/indicator/trading presentation assembled from proven components where beneficial;
- authoritative tick-native market replay and execution where evidence supports it;
- no-look-ahead and deterministic outcomes;
- durable user/session/research state;
- Method + Protocol + Experiment Passport;
- journal and reproducible analytics;
- bounded multi-user resource behavior;
- explicit market-data rights;
- enough telemetry, recovery and security to safely invite progressively larger closed-alpha cohorts.

The goal is not maximum features. The goal is a small product whose results can be trusted.

## 1. Non-negotiable invariants

Every checkpoint must preserve these unless a later explicit architecture decision supersedes them:

1. Human authorization is required before implementation.
2. Existing local v1 remains the rollback reference until v2 parity/cutover is accepted.
3. No roadmap/planning document self-authorizes runtime work.
4. Market-data uncertainty is never silently upgraded to certainty.
5. Raw authoritative tick order is execution truth when such evidence exists.
6. Candles are derived presentation/research data, not hidden execution authority for tick mode.
7. No look-ahead: a component may consume only information revealed at the current virtual time.
8. Replay speed/UI update frequency must not change committed execution results.
9. Missing provider fields remain unknown; never fabricate timestamp, sequence, volume, spread, bid/ask or certainty.
10. Dataset/provider/instrument/version identity follows results through the Experiment Passport.
11. Workers are replaceable; durable session/evidence truth is not worker-local.
12. Shared cache may improve speed but cannot be required for correctness.
13. Every scalable resource has a bound before external alpha.
14. Donor OSS cannot silently become Backtest Lab execution/account/research authority.
15. Old code is deleted only after replacement parity, rollback evidence and unreachable-code proof.
16. No private/personal market dataset is redistributed without explicit rights evidence.
17. No performance/capacity claim without named hardware, dataset, build and workload.
18. No phase/checkpoint completion without required validation + commit + push + remote equality + clean tree.

## 2. Architecture lanes

Work is split into five lanes. Parallelism is allowed only where dependencies and repository ownership do not conflict.

### Lane A — STITCH / commodity consolidation
A0 STITCH-0 audit — COMPLETE planning
A1 Drawing compatibility spike
A2 Drawing migration if accepted
A3 Indicator compatibility spike
A4 Indicator migration if accepted
A5 Trading visualization adapter
A6 Analytics primitive adapter
A7 Commodity infrastructure selection
A8 Consolidation/dead-code retirement

### Lane B — Market-data truth
B0 Frozen canonical tick/provider/timeline contracts — existing
B1 Resume/reconcile preserved 42.18 runtime against frozen 42.17 + 42.19
B2 V2 disk provider + atomic publication
B3 Disk-bounded validation + immutable time index
B4 Indexed timeline positioning/range access
B5 Authorized private dataset ingestion benchmark
B6 Tick-to-candle derived aggregation
B7 Market-data service boundary for v2 integration

### Lane C — Execution and sessions
C1 Tick Execution Engine V1 contract
C2 Tick Execution Engine V1 implementation
C3 Canonical event/trade log
C4 Account/PnL settlement adapter
C5 Durable Session model
C6 Session persistence/checkpoint/restore
C7 Bounded replay workers/backpressure
C8 Shared cache only if benchmark justifies it

### Lane D — Research/product domain
D1 Method canonical model
D2 Protocol canonical model/enforcement
D3 Experiment Passport completion
D4 Session/Method/Protocol UI integration
D5 Journal migration to canonical event/trade log
D6 ResearchCalculator boundary
D7 Descriptive analytics
D8 MAE/MFE + R metrics
D9 Monte Carlo
D10 Regime/robustness/destruction
D11 OOS/walk-forward
D12 Multiple-testing controls only where inferentially needed

### Lane E — Productization
E1 v2 API composition
E2 frontend v2 adapter/cutover behind explicit boundary/flag
E3 authentication/workspace integration
E4 browser delivery throttling/budget
E5 observability
E6 security/tenant isolation
E7 backup/restore + recovery drills
E8 random-timeline load benchmark
E9 failure-injection benchmark
E10 data-rights launch review
E11 internal release
E12 closed-alpha waves 5 → 15 → 30 → 50 → 100
E13 beta-readiness review

## 3. Dependency DAG

```text
A0
 └─A1─(accept?)─A2─A3─(accept?)─A4─A5
                       └─────────────┐
A6───────────────────────────────────┤
A7 (later, evidence-driven)          │
                                    ▼
B0─B1─B2─B3─B4─B5─B6─B7──────────► INTEGRATION GATE I
             │                      │
             └──────────────┐       │
                            ▼       ▼
                         C1─C2─C3─C4─C5─C6─C7─(C8 if justified)
                               │      │
                               │      └──────────────┐
                               ▼                     ▼
                         D1─D2─D3─D4             E1/E2/E3
                               │                     │
                         D5─D6─D7─D8                ▼
                               │                 E4─E5─E6
                         D9─D10─D11                 │
                               │                    ▼
                              D12                E7─E8─E9
                                                     │
A8 ◄──────── after accepted replacements             ▼
                                              E10─E11─E12─E13
```

Rules:
- A-lane donor spikes may proceed without B/C runtime changes if separately authorized.
- B1 and onward must never be resumed merely because A-lane work exists.
- C2 requires stable B4 semantics at minimum; real-data acceptance additionally requires B5.
- D4/D5 depend on canonical execution/session identities, not legacy-only records.
- E2 cutover waits for Integration Gate I.
- C8 is optional and benchmark-triggered.
- A8 happens only after each accepted donor migration has proven parity.
- Public/beta progression waits for rights, security, recovery and capacity evidence.

## 4. Checkpoint template for Work/Codex

Before every implementation checkpoint, the agent must write/confirm:

```text
CHECKPOINT:
BASELINE:
AUTHORIZATION:
OBJECTIVE:
IN SCOPE:
OUT OF SCOPE:
FILES/DOMAINS EXPECTED:
PROTECTED BOUNDARIES:
UPSTREAM SOURCE + PIN (if OSS):
LICENSE/NOTICE:
MIGRATION/PERSISTENCE POLICY:
ROLLBACK:
ACCEPTANCE:
TESTS:
PERFORMANCE EVIDENCE:
DOC/CONTEXT UPDATES:
GIT COMPLETION GATES:
STOP CONDITIONS:
NEXT CHECKPOINT (planning only):
```

If any mandatory field cannot be resolved safely, STOP and report the ambiguity.

## 5. Lane A — STITCH execution details

### A1 — Drawing compatibility spike
**Purpose:** determine whether OpenAlgo Draw, OpenCharts-derived approach or current Backtest Lab drawing engine is the lowest-risk v2 owner.

Deliverables:
- exact upstream commit/tag/license inventory;
- isolated donor prototype, not production migration;
- mapping for all current eight drawing types;
- TIME+PRICE anchor round-trip test;
- replay/timeframe/zoom/pan/resize tests;
- persistence compatibility analysis;
- selection/drag/hit-test comparison;
- bundle/runtime/interaction benchmark;
- custom LOC/dependency delta;
- migration + rollback design;
- final KEEP / ADAPT / PARTIAL-REPLACE / FULL-REPLACE decision.

Hard stops:
- donor requires execution/account ownership;
- canonical geometry cannot round-trip;
- unacceptable look-ahead coupling;
- license/redistribution uncertainty;
- replacement requires a chart-engine migration whose benefits are not demonstrated.

No production deletion.

### A2 — Drawing migration
Only if A1 explicitly accepts replacement.

Required architecture:
```text
Backtest Lab Drawing Contract
        ↓
Drawing Adapter
        ↓
Accepted donor runtime
```

Backtest Lab retains persistence/version/migration authority unless A1 proves a safer explicit alternative.

Acceptance:
- current eight tools parity;
- donor-added tools may be enabled only if stable and intentionally exposed;
- old saved drawings have explicit preserve/migrate/refuse behavior;
- current trading RiskReward remains isolated;
- full drawing/replay/trading browser regression;
- rollback flag/path until acceptance;
- old runtime not deleted in same step unless unreachable proof and rollback requirements are already satisfied.

### A3 — Indicator compatibility spike
Compare current engine/calculators with donor indicator implementation.

Golden requirements:
- SMA, EMA, Bollinger, RSI, MACD, ATR, Stochastic numerical parity under explicitly documented formulas;
- warmup behavior;
- visible-prefix only;
- truncation invariance;
- timeframe/replay behavior;
- multi-instance/pane lifecycle;
- malformed-config isolation;
- bundle/performance impact.

Decision may be mixed: donor calculators + existing host, existing calculators + donor catalog, or full keep.

### A4 — Indicator migration
Use an adapter:
```text
revealed candles
   ↓
BTL Indicator Contract
   ↓
calculator adapter
   ↓
normalized TIME+VALUE outputs
   ↓
chart-series host
```

Never allow a donor to read unrevealed full-history arrays.

### A5 — Trading visualization adapter
Scope is presentation only:
- Long/Short position visualization;
- entry/SL/TP manipulation;
- pending/order/position markers;
- bracket visuals.

Boundary:
```text
Donor UI event → BTL command → BTL execution authority → canonical event → donor projection
```

Donor state never settles fills, balance or P&L.

### A6 — Analytics primitive adapter
Create a `ResearchCalculator` boundary. QuantStats or another accepted library may calculate compatible primitives, but Backtest Lab owns:
- canonical trade grouping;
- Method/Protocol meaning;
- Passport;
- dataset/execution provenance;
- orchestration;
- semantic labels.

Golden-test every adopted metric against authored fixtures and current basic analytics where semantics overlap.

### A7 — Commodity infrastructure selection
Triggered by measured need, not calendar phase.

Candidates:
- job queue/worker system;
- cache/coordination;
- telemetry;
- object storage/CDN;
- error tracking.

For each: NEED → benchmark/problem evidence → 2–3 mature candidates → license/ops/cost → bounded spike → choose/defer.

### A8 — Consolidation
Only after migrations are accepted:
- search imports/references/runtime reachability;
- delete superseded implementations;
- preserve migration fixtures;
- update notices;
- update architecture owners;
- run complete regression;
- measure bundle/repository complexity before/after.

## 6. Lane B — market-data truth

### B1 — Resume preserved 42.18 against 42.17 + 42.19
This is the nearest unfinished core prerequisite but requires separate explicit authorization.

Before code:
- verify current main;
- verify preserved branch/commit provenance;
- diff the seven preserved runtime/test blobs;
- reconcile sidecar evidence access against 42.19;
- do not merge the branch wholesale;
- selectively reapply only conforming work.

Acceptance:
- frozen contract conformance;
- bounded sidecar access;
- no evidence loss;
- V1 unchanged;
- no execution/settlement work.

### B2 — V2 disk provider + atomic publication
Build immutable, versioned dataset/chunk publication:
- provider/instrument/dataset/version hierarchy;
- manifests/checksums;
- staging then atomic publish;
- fail closed on corrupt/incomplete publication;
- bounded file handles/memory.

### B3 — Validation + immutable time index
Streaming/disk-bounded validation:
- schema;
- monotonic ordering;
- duplicate/out-of-order policy;
- bid/ask validity;
- chunk boundaries;
- evidence coverage;
- checksums;
- index build/verification.

No full-file RAM requirement.

### B4 — Indexed timeline positioning
Required operations:
- seek first >= timestamp;
- bounded range read;
- cursor resume;
- partition crossing;
- cancellation;
- deterministic equal-timestamp ordering;
- no scan-from-start requirement for arbitrary historical positioning.

### B5 — Private dataset benchmark
Only with authorized local dataset and rights-safe handling.

Measure:
- rows/ticks;
- raw/normalized/storage size;
- ingest throughput;
- index time;
- peak RSS;
- random seek latency;
- sequential replay throughput;
- corruption handling;
- sidecar coverage;
- full benchmark completion.

Private data remains outside Git/public assets.

### B6 — Tick-to-candle aggregation
Produce OHLC/derived presentation from revealed ticks:
- timeframe buckets;
- explicit boundary semantics;
- bid/ask/mid policy documented;
- no future tick access;
- exact comparison fixtures.

### B7 — v2 market-data service boundary
Expose bounded internal range/replay APIs. Do not send all raw ticks to browser by default.

## 7. Lane C — execution and durable sessions

### C1 — Tick Execution Engine V1 contract
Freeze before implementation:
- command/event vocabulary;
- market/limit/stop;
- pending activation/cancel;
- long/short;
- bid/ask side rules;
- SL/TP;
- opening/gap behavior;
- equal timestamp ordering;
- commission/slippage versions;
- partial exit policy;
- rejected order semantics;
- idempotency/revision behavior.

Golden scenarios must include:
- entry then SL/TP on later ticks;
- gap across entry/exit;
- pending activation + immediate exit;
- equal timestamp quotes;
- spread change;
- duplicate/replayed command;
- cancellation race;
- partition boundary.

### C2 — Execution implementation
Pure/deterministic core first. No UI dependency.

Property:
same dataset/version + same commands + same engine version → same canonical events.

Replay speed and browser frame rate cannot affect output.

### C3 — Canonical event/trade log
Append-only logical event history:
- command/request IDs;
- session;
- instrument;
- dataset/version;
- tick/source evidence reference;
- order lifecycle;
- fills;
- position changes;
- balance/PnL changes;
- timestamps/revisions;
- execution semantics version.

Journal/research consume this; they do not reconstruct truth independently.

### C4 — Account/PnL settlement adapter
Migrate legacy modelled account behavior behind a v2 account contract. Exact decimal/fixed-point policy must be explicit. Legacy compatibility remains available until v2 parity accepted.

### C5/C6 — Durable session model + restore
Session contains small state only:
- identity/ownership;
- dataset/version;
- cursor/virtual clock;
- orders/positions/account revision;
- Method/Protocol/Passport refs;
- replay settings;
- RNG seed where applicable.

Persist checkpoints so paused users do not retain dedicated heavy workers.

Recovery acceptance:
- kill worker;
- restore session;
- deterministic continuation;
- stale revision rejected;
- no duplicate settlement.

### C7 — Bounded workers/backpressure
Define:
- max active replay jobs/host;
- queue depth;
- timeout/cancel;
- fair scheduling;
- overload rejection;
- paused-session release.

### C8 — Shared cache
Implement only if E8/B5 measurements show benefit. Define byte limit and deterministic eviction. Correctness must remain identical with cache disabled.

## 8. Lane D — Method, Protocol, Passport and research

### D1 — Method
Canonical versioned Strategy/Method:
- name/version;
- instruments;
- setup description;
- inclusion rules;
- exclusion rules;
- optional tags/notes;
- immutable historical version references.

### D2 — Protocol
Versioned test discipline:
- fixed/default RR where configured;
- risk policy;
- max pending/order rules where configured;
- intervention/early-close permission;
- checklist;
- sample target;
- planned period;
- deviation event semantics.

Protocol enforcement produces evidence; it must not silently rewrite historical behavior.

### D3 — Experiment Passport
Must bind:
- dataset/provider/instrument/period/hash;
- Method version/hash;
- Protocol version/hash;
- execution/engine/calculator versions;
- regime definition;
- RNG algorithm/seed;
- planned vs actual sample;
- exclusions/deviations;
- lineage/hypothesis family;
- result version.

### D4 — UI integration
Quick and Planned workflows may coexist. UI must make clear:
- what is planned;
- what is locked;
- what is editable;
- what constitutes a deviation;
- what will be recorded.

### D5 — Journal migration
Journal becomes a projection/editor over canonical identities, not a separate financial truth.

### D6 — ResearchCalculator contract
Inputs are explicit immutable result/equity/trade series with Passport provenance. Outputs are versioned and reproducible.

### D7/D8 — Descriptive + path/risk metrics
Minimum alpha research:
- count;
- win/loss/BE;
- expectancy;
- PF;
- realized/equity drawdown where evidence exists;
- streaks;
- R-multiple;
- MAE/MFE;
- duration;
- distribution summaries;
- reconciliation status.

### D9 — Monte Carlo
Versioned RNG/seed. Outputs distributions, not a promise:
- terminal outcome;
- max DD;
- losing streak;
- ruin/threshold probability where assumptions are explicit.

### D10–D12 — advanced research
Regime, Strategy Destruction, robustness, OOS/walk-forward and multiple-testing controls are post-core-alpha unless required for the chosen alpha promise. They must remain reproducible and Passport-bound.

## 9. Lane E — productization

### E1 — v2 API composition
Compose existing contracts, identity, workspace, persistence, market data, session, execution and research boundaries. Avoid a second competing API architecture.

### E2 — frontend cutover
Use an explicit v2 adapter/feature boundary:
- v1 remains available during migration;
- compare v1/v2 authored scenarios;
- no silent mixed execution authority;
- rollback documented.

### E3 — auth/workspace
Connect existing verified identity/workspace seams to product UI. Server decides authorization; never trust client tenant IDs.

### E4 — browser delivery budget
UI receives bounded:
- candles;
- current bid/ask;
- order/fill/position events;
- replay progress;
- job status.

Raw tick processing can remain server/engine-side.

### E5 — observability
Minimum:
- active/paused sessions;
- replay latency/throughput;
- worker/queue;
- CPU/RAM;
- storage I/O;
- cache if present;
- API errors;
- restore failures;
- dataset failures;
- build/engine/dataset version.

### E6 — security
- auth/verification;
- object-level ownership tests;
- tenant isolation;
- rate/body/resource limits;
- secret handling;
- TLS;
- input validation;
- dependency scans;
- private object access policy;
- audit events.

### E7 — recovery
Prove:
- DB backup/restore;
- session restore;
- dataset/index recovery/refusal;
- worker/API restart;
- explicit RPO/RTO targets only after measured/operational decision.

### E8 — worst-case load
Required profile:
- 10 → 25 → 50 → 100 sessions;
- random historical cursors;
- minimal cache overlap;
- mixed speeds/timeframes;
- MAX bursts;
- active orders;
- pause/resume/reconnect.

Record p50/p95/p99, CPU, RAM, disk, queue, errors, deterministic hashes.

### E9 — failure injection
Kill workers, restart API/DB, corrupt/miss chunks/index, disconnect clients, force cache pressure, partial publication/save and stale revisions. Fail closed where evidence integrity is affected.

### E10 — rights review
Every launch dataset must have recorded:
- source/acquisition;
- personal/commercial status;
- storage/display/redistribution;
- derived-data status;
- retention/attribution;
- evidence timestamp.

No rights evidence → no public dataset launch.

### E11/E12 — progressive closed alpha
Wave gates:
```text
INTERNAL
  ↓ healthy
5 users
  ↓ healthy
15
  ↓
30
  ↓
50
  ↓
100
```

Advance only if:
- no unresolved correctness bug;
- deterministic replay/execution stable;
- no evidence/data corruption;
- latency/resource envelope acceptable;
- restore works;
- no severe security/tenant issue;
- telemetry is sufficient to diagnose failures.

### E13 — beta-readiness
Review:
- product retention/usefulness;
- reliability;
- cost/user;
- data rights;
- support burden;
- incident history;
- security;
- recovery;
- capacity;
- unresolved model limitations.

Beta is a decision, not an automatic next phase.

## 10. Integration Gate I — v2 core convergence

Before frontend v2 cutover, require:
- accepted chart/drawing/indicator ownership;
- B4 indexed timeline complete;
- B5 benchmark evidence if real tick dataset is used;
- C2 execution engine deterministic;
- C3 canonical event log;
- C4 account adapter;
- C5/C6 session model/restore;
- D1–D3 Method/Protocol/Passport contracts;
- no unresolved dual-authority path.

Produce one architecture diagram showing the exact owner of:
market evidence → replay → execution → account → event log → journal/research → UI.

## 11. Testing matrix by change type

| Change | Minimum required evidence |
|---|---|
| Docs/planning only | repository/context/bundle checks; browser exempt with reason |
| Drawing/indicator UI | subsystem tests + replay/trading regressions + lint/build + browser |
| Trading visualization | trading separation + trading + replay + browser + no settlement ownership |
| Market-data core | backend contract/unit/property tests + disk bounds + corruption cases + vectors |
| Execution | golden ticks + property/determinism + no-look-ahead + replay-speed invariance |
| Session/persistence | concurrency + restart/restore + stale revision + failure tests |
| Analytics | authored vectors + semantic parity + provenance + no financial mutation |
| Auth/workspace | real isolated DB + ownership/hostile access + restart/restore |
| Load/perf | named hardware/dataset/build/workload + p50/p95/p99 + CPU/RAM/I/O |
| Release | full applicable regression + build/lint + security + recovery + Git gates |

Existing exact commands remain owned by `AI_CONTEXT/07_TEST_COMMANDS.md`. New checkpoints must extend that file rather than creating a second command authority.

## 12. OSS provenance rule

For every adopted/adapted donor record:
```text
component
official repository
exact tag/commit
exact files/package
license
copyright/NOTICE
adoption mode (USE/ADAPT/REFERENCE)
local adapter owner
modifications
security/version review date
upgrade policy
rollback policy
```

Never paste source first and investigate license later.

Current primary donors/candidates are owned by STITCH-0:
- OpenAlgo Charts;
- OpenCharts;
- QuantStats;
- NautilusTrader;
- QuantConnect LEAN;
- hftbacktest;
- Lightweight Charts;
- Arrow/Parquet and existing standard infrastructure.

## 13. Data and privacy rule

Repository must contain:
- schemas;
- tiny synthetic/golden fixtures;
- public-safe metadata;
- hashes/manifests where rights permit.

Repository must not contain:
- private full provider files;
- credentials;
- personal access tokens;
- paid feed secrets;
- private quote reports that reveal restricted data.

## 14. Versioning and migration policy

Every durable contract needs a version. At minimum:
- dataset format;
- tick schema;
- execution semantics;
- account/event schema;
- drawing persistence;
- Method;
- Protocol;
- Passport;
- research result.

Migration rules:
1. read old version;
2. validate;
3. migrate explicitly or refuse safely;
4. never silently reinterpret old evidence under new semantics;
5. preserve original provenance;
6. test round-trip/idempotency where applicable.

## 15. Rollback strategy

Until closed-alpha cutover is accepted:
- v1 remains the known-good product reference;
- donor migrations remain adapter-isolated;
- v2 frontend activation is explicit;
- data migrations are versioned/non-destructive where practical;
- execution result migration never rewrites historical results silently;
- deployment rollback must not require deleting user evidence.

## 16. Definition of v2 Alpha

v2 Alpha is **not** “all roadmap features.”

It is ready for closed users when:
- core chart/drawing/indicator UX is stable;
- tick dataset/replay path is deterministic;
- execution V1 works for intended order types;
- account/event log reconcile;
- save/resume works;
- Method/Protocol/Passport capture reproducible tests;
- journal/basic research works;
- authentication/workspace isolation works for hosted alpha;
- market-data rights match launch mode;
- resource limits/backpressure exist;
- recovery is proven;
- observability can diagnose failures;
- internal + progressive cohort gates pass.

Not required for initial alpha:
- L2/L3;
- queue-position simulation;
- market impact;
- live broker execution;
- native mobile;
- huge multi-asset catalog;
- social/community;
- AI trading;
- Kubernetes;
- distributed database;
- Rust rewrite;
- advanced portfolio optimization.

## 17. Work selection algorithm

When the user says “lanjut”, “kerjakan berikutnya”, or Work must choose the next task:

1. read `AGENTS.md` and all AI_CONTEXT owners;
2. read Engineering Master Plan;
3. read STITCH-0 and this plan;
4. fetch actual `main` and local state;
5. read `04_CURRENT_PHASE.md`;
6. identify the nearest incomplete prerequisite in this DAG;
7. check whether that exact checkpoint is human-authorized;
8. if not authorized: prepare a bounded implementation prompt/plan only and STOP;
9. if authorized: execute only that checkpoint;
10. run applicable tests;
11. update factual architecture/history/status;
12. commit;
13. push normally;
14. verify actual remote HEAD == local HEAD, clean tree and 0/0;
15. report evidence;
16. state next checkpoint without auto-starting it.

Never choose work based on the highest roadmap number, novelty, remaining AI credits or what seems visually exciting.

## 18. Recommended next decisions from current state

Current planning recommends two independent next authorizations; they must not be silently combined:

**Track A — STITCH-1 Drawing Compatibility Spike**
- isolated donor evaluation;
- no production migration/deletion;
- determines OpenAlgo vs OpenCharts vs KEEP.

**Track B — B1 / preserved 42.18 reconciliation**
- verify preserved draft;
- selectively resume only against frozen 42.17 + 42.19;
- no execution/settlement;
- complete storage/index prerequisite.

If only one agent is working, prefer one checkpoint at a time. If separate agents work in parallel, they must own disjoint files/domains and each checkpoint must retain its own validation/commit boundary.

## 19. STOP conditions

Stop immediately and report instead of improvising if:
- repository baseline differs materially from expected authority;
- working tree contains protected/unexplained user changes;
- license or data rights are uncertain for the proposed distribution;
- donor requires unplanned architecture replacement;
- golden parity fails;
- no-look-ahead/determinism fails;
- benchmark exceeds resource bounds and no bounded fallback exists;
- private data would enter Git;
- migration could destroy user evidence;
- tests fail outside the understood scope;
- push/remote equality cannot be proven;
- implementation is not explicitly authorized.

## 20. Planning completion

This document completes the **v2 Alpha work decomposition**, not the implementation.

It is intentionally detailed enough that a future Work/Codex session can locate the next task, understand dependencies and acceptance, and know when to STOP without reconstructing the product plan from chat history.
