# Backtest Lab — Engineering Master Plan & Source Provenance

> Planning authority for engineering direction. This file does **not** grant implementation authorization and does not replace `AI_CONTEXT/04_CURRENT_PHASE.md`.
> Audit baseline: GitHub `main` at `7d259dbe6f3dbab69b2f24e39c61401dc279cc5b` (2026-10-06 review).

## 1. Purpose

This document exists so a future human, ChatGPT, Codex, or other coding agent can answer five questions without reconstructing the project from chat history:

1. What is actually implemented now?
2. What architecture are we converging toward?
3. Which upstream/open-source projects informed each subsystem?
4. What must be built next, and what must **not** be built yet?
5. What evidence is required before advancing toward alpha, beta, and production?

Operating principle: **mature before launch; complexity must be earned by measured need.**

## 2. Authority order

Before any work, read in this order:

1. `AGENTS.md`
2. `AI_CONTEXT/00_START_HERE.md`
3. `AI_CONTEXT/01_PROJECT_STATE.md`
4. `AI_CONTEXT/02_ARCHITECTURE.md`
5. `AI_CONTEXT/04_CURRENT_PHASE.md` — sole operational authorization/status owner
6. `AI_CONTEXT/05_PROTECTED_SYSTEMS.md`
7. `AI_CONTEXT/06_WORKFLOW_RULES.md`
8. `AI_CONTEXT/07_TEST_COMMANDS.md`
9. `docs/MARKET_DATA_STANDARD.md`
10. `docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md`
11. `docs/ROADMAP.md`
12. this document for cross-system engineering direction/source provenance
13. `docs/AI_HANDOFF.md` only as an operational mailbox, never as architecture authority

If these disagree, current factual/operational authority wins. Never infer authorization from a roadmap slot or this plan.

## 3. Audited repository state

### Active local product

- React 19 + Vite 8.
- TradingView Lightweight Charts 5.2.1.
- Production frontend source is `frontend/src/`.
- Approx. ten years XAUUSD M1 candle archive: 3,486,461 validated M1 candles, eleven aggregated timeframes.
- Browser replay, drawings, seven indicator families, manual trading UX, news research, journal/basic analysis and local persistence are implemented as documented in `01_PROJECT_STATE.md`.
- Existing v1 is local/browser-first; it is not evidence that the future cloud backend is wired to the production workspace.

### Backend seams already present

Repository contains standalone/unwired or selectively composed seams including:
- `backend/contracts/`
- `backend/application/`
- `backend/infrastructure/`
- `backend/identity/`
- `backend/workspace/`
- `backend/precision/`
- `backend/engine/market_data/`
- `backend/engine/replay/`
- `backend/engine/trading/`
- `backend/cloud/`

Do not treat directory existence as production integration. Check current authority and tests before claiming runtime ownership.

### Current tick/data checkpoint

The 42.x work has moved architecture toward a **tick-native authoritative target**:
- canonical tick/provider/timeline contract frozen;
- synthetic provider/timeline foundation completed;
- scalable V2 storage/index contract frozen;
- interrupted 42.18 runtime draft preserved separately;
- 42.19 reconciles bounded sidecar evidence access;
- full Exness benchmark is not complete;
- public delivery, settlement/account cutover, frontend cutover and cloud market-data service remain unimplemented/deferred unless separately authorized.

This supersedes older directional wording that could be read as “candle execution forever.” Candles remain important as derived visualization/fast research data, but high-fidelity execution target uses authoritative tick evidence when available.

## 4. Product target

Backtest Lab is a manual trading research laboratory, not merely a chart and not primarily an algorithmic-trading bot.

Core target:
- professional interactive chart workspace;
- deterministic historical replay;
- tick-accurate execution path where evidence supports it;
- explicit execution assumptions where evidence does not;
- manual order workflow;
- journal and canonical trade/event log;
- Strategy/Method + Session + Protocol;
- Experiment Passport and reproducibility;
- statistical evidence, Monte Carlo, robustness/destruction, regime and OOS/walk-forward research;
- multi-user SaaS later;
- community/social and AI assistance only after core evidence and product demand justify them.

The moat should be the combination of **interactive manual replay + research protocol + reproducibility + evidence integrity**, not reimplementing commodity infrastructure for its own sake.

## 5. Target system architecture

```text
Provider/source data
  -> Provider Adapter
  -> Validation / evidence classification
  -> Canonical QuoteTick
  -> Immutable Dataset + Version + Hash
  -> Partitioned storage
  -> Time index / Data Catalog
  -> Range/Chunk Reader
  -> Bounded Shared Cache
  -> Replay Service / bounded workers
  -> Independent Session Virtual Clock
  -> Tick Execution Engine
  -> Canonical Event/Trade Log
  -> Tick-to-Candle Aggregator
  -> Throttled UI delivery
  -> Lightweight Charts workspace

Canonical Event/Trade Log
  -> Journal
  -> Experiment Passport
  -> Research jobs
  -> Statistical evidence / Monte Carlo / robustness / OOS
```

Correctness must not depend on cache hits, worker affinity, browser frame rate, or users sharing the same historical time.

## 6. Canonical market-data rules

### Source of truth

1. Raw provider/source artifact is immutable evidence.
2. Canonical normalized dataset is versioned and hash-identifiable.
3. Tick order is execution truth when authoritative tick evidence exists.
4. Candles are derived projections/cache/visualization; never silently invent intrabar order.
5. If only candle evidence exists, same-candle SL/TP ambiguity must be explicit and governed by a versioned assumption/policy.
6. Missing provider fields stay missing/unknown. Never manufacture timestamps, volume, sequence, spread, bid/ask, or certainty.
7. Provider + instrument + dataset version are part of identity.

Candidate QuoteTick contract:
```text
provider_id
instrument_id
dataset_id
dataset_version
ts_event?
ts_init?
bid_price_int
ask_price_int
price_scale
bid_size?
ask_size?
sequence?
flags?
source_evidence_id
```

Use fixed-point integer price representation where the canonical contract supports it; avoid introducing floating-point ambiguity into execution semantics.

### Storage target

CSV is import/interchange, not the intended large runtime format.

Target logical hierarchy:
```text
provider / instrument / dataset_version / year / month / day-or-chunk
```

Physical format must be benchmarked. Parquet/Arrow is the default candidate for columnar immutable chunks, not a religious requirement. Preserve a format/version manifest and checksums.

## 7. Multi-user replay architecture

Historical users have independent virtual clocks. This is expected behavior, not an edge case.

Session state should remain small:
```text
session_id
workspace/user ownership
dataset_id/version
cursor/timestamp
virtual clock/replay speed
orders
positions
balance/equity state
experiment/protocol identity
RNG seed where applicable
committed revision
```

Do **not**:
- copy the full market dataset per user;
- load the full dataset into RAM;
- reserve one heavy process/container for every paused user;
- make correctness depend on shared-cache overlap.

Preferred lifecycle:
```text
CREATED -> ACTIVE -> PAUSED -> SUSPENDED -> RESTORED -> ACTIVE -> COMPLETED
```

Paused/suspended sessions persist state and may release compute workers. Workers are replaceable; session truth is durable.

## 8. Resource safety

Every scalable component needs a bound.

Required contracts before public alpha:
- maximum market-data cache memory;
- deterministic eviction behavior;
- maximum active heavy replay jobs per process/host;
- queue/backpressure behavior when capacity is exceeded;
- request/response and stream payload limits;
- browser update budget;
- timeout/cancellation semantics;
- session checkpoint/recovery semantics.

Overload must degrade by queueing/throttling/rejecting bounded work, not by unbounded allocation.

## 9. Browser delivery

Never stream every raw tick to the browser merely because the execution engine processes every tick.

Server/engine may process raw precision events while UI receives bounded:
- candle updates;
- current bid/ask/price projection;
- order/fill/position events;
- replay progress;
- research/job status.

UI delivery frequency is a presentation concern and must not alter execution outcome.

## 10. Execution Engine V1

First high-fidelity target:
- market order;
- limit order;
- stop order;
- pending-order lifecycle;
- long/short;
- SL/TP;
- bid/ask side correctness;
- spread;
- versioned commission model;
- versioned slippage model;
- partial/full exit only when explicitly in scope;
- deterministic ordering for equal timestamps;
- gap policy;
- canonical execution event log.

Not alpha prerequisites unless evidence/product scope changes:
- L2/L3 reconstruction;
- queue-position simulation;
- exchange matching engine;
- sophisticated latency topology;
- market impact;
- smart order routing;
- live broker execution.

## 11. Replay invariants

- No look-ahead.
- Output at time T must not change when observations after T are physically removed (truncation-invariance where applicable).
- 1x/5x/MAX replay speeds must produce the same committed execution result.
- Seek/navigation cannot silently bypass settlement or reveal future evidence.
- Replay state, account/execution state, journal/event log and research revision must have an explicit committed relationship.
- Dataset/version/engine semantics must be recoverable from the resulting experiment.

## 12. Research architecture

Execution/replay produces canonical evidence. Research consumes it; research calculators do not own market execution.

Order of capability:
1. descriptive metrics;
2. expectancy and uncertainty;
3. MAE/MFE;
4. Monte Carlo and drawdown/streak distributions;
5. RR counterfactual laboratory using historical path evidence;
6. regime analysis;
7. robustness/Strategy Destruction;
8. OOS/walk-forward;
9. multiple-testing controls where inferentially appropriate;
10. portfolio/correlation;
11. behavioral/forward-vs-tested audit.

Long-running work belongs in bounded background jobs after measured need. Do not put Monte Carlo/large grids in the interactive replay loop.

## 13. Experiment Passport

Every serious result should identify enough provenance to reproduce it:
- dataset ID/version/content hash;
- provider/instrument/period;
- Strategy/Method ID + version/hash;
- Protocol ID + version/hash;
- execution-assumption version;
- engine/calculator version;
- regime-definition version where used;
- RNG algorithm + seed where used;
- planned vs actual sample;
- exclusion summary;
- lineage/hypothesis family;
- result version.

A result without provenance is descriptive output, not a reproducible research artifact.

## 14. Open-source/source provenance map

Policy labels:
- **USE**: dependency/component may be directly adopted after normal license/security/version review.
- **ADAPT**: use APIs/patterns or bounded code only with provenance/license compliance.
- **REFERENCE**: learn architecture/algorithms; do not import code by default.
- **EVALUATE**: potentially useful but license/product-fit/performance must be reviewed before dependency adoption.
- **DEFER**: not justified now.

| Area | Upstream | License observed at audit | Decision | What Backtest Lab uses/learns |
|---|---|---|---|---|
| Financial chart | https://github.com/tradingview/lightweight-charts | Apache-2.0 + attribution/NOTICE obligations | USE | Active chart engine, official series/panes/primitives |
| Official chart plugin toolkit | same TradingView repo/packages | verify exact package before adoption | EVALUATE | Prefer official toolkit/plugins before custom replacement where they reduce code without losing UX |
| Drawing reference | https://github.com/deepentropy/lightweight-charts-drawing | MIT (existing notice) | REFERENCE only currently | Historical reference; package uninstalled |
| Deterministic event/trading architecture | https://github.com/nautechsystems/nautilus_trader | LGPL-3.0 | REFERENCE | canonical event model, data catalog, adapters, virtual clocks, data/execution separation, deterministic processing |
| Backtest jobs/data-provider patterns | https://github.com/QuantConnect/Lean | Apache-2.0 | REFERENCE/ADAPT selectively | provider/cache boundaries, independent jobs, scheduling/resource isolation |
| Tick/microstructure simulation | https://github.com/nkaz001/hftbacktest | MIT | REFERENCE | tick replay, latency/queue/L2-L3 ideas for later fidelity; not alpha scope |
| Vectorized research | https://github.com/polakowo/vectorbt | Apache-2.0 + Commons Clause in current project | EVALUATE/REFERENCE | research/benchmark ideas; do not make commercial product depend on it without license review |
| API | FastAPI ecosystem | verify pinned packages | USE where already selected | backend HTTP boundary |
| Relational truth | PostgreSQL | PostgreSQL License | USE | users/workspaces/experiments/trades/metadata |
| Columnar storage | Apache Arrow / Parquet | Apache-2.0 projects/spec ecosystem | USE candidate | immutable tick chunks/interchange/query efficiency |
| Cache/coordination | Redis-compatible ecosystem | product/license varies | DEFER until benchmark | hot cache, jobs, locks only when measured need exists |

Before copying/adapting source code, record exact upstream repository, commit/tag, file, license, modifications and NOTICE obligations. Architecture inspiration is not the same as source-code incorporation.

### Explicit non-adoption decisions

Do not wholesale embed or rewrite Backtest Lab around NautilusTrader, LEAN, hftbacktest or vectorbt. Their product goals differ. Backtest Lab keeps its manual interactive/research UX and uses upstream projects as references or bounded components.

Do not adopt proprietary TradingView Advanced Charts/Trading Platform code into the public repository without a separately verified license/product-fit decision.

## 13A. v2 Alpha execution decomposition

For the complete workstream DAG, checkpoint scopes, dependencies, acceptance gates, rollback rules, STOP conditions and Work/Codex task-selection algorithm, read [v2 Alpha Work Execution Plan](V2_ALPHA_WORK_EXECUTION_PLAN.md). This is planning authority only; it does not override operational authorization in `AI_CONTEXT/04_CURRENT_PHASE.md`.

## 14A. Stitch-first consolidation

Before extending commodity v2 subsystems, read [STITCH-0 OSS Replacement & Consolidation Audit](STITCH_0_OSS_REPLACEMENT_AUDIT.md). It owns the current cross-subsystem KEEP / REPLACE-CANDIDATE / ADAPT / REFERENCE planning map and the migration gates. It does **not** grant implementation authorization. Operational authorization remains exclusively in `AI_CONTEXT/04_CURRENT_PHASE.md`.

## 15. Dependency intake gate

Before adding a dependency:
1. prove the capability is needed;
2. search existing code and mature OSS first;
3. identify official upstream;
4. pin/record version;
5. inspect license and redistribution/commercial obligations;
6. inspect maintenance/activity/security posture;
7. compare build-vs-adopt complexity;
8. benchmark if performance-sensitive;
9. add NOTICE/provenance;
10. add tests;
11. update this map if architectural;
12. commit/push only after repository gates pass.

## 16. Testing model

Required layers as applicable:
- unit tests;
- contract tests;
- property/invariant tests;
- synthetic golden tick fixtures;
- deterministic replay tests;
- truncation/no-look-ahead tests;
- integration tests;
- persistence/restart tests;
- browser tests;
- performance benchmarks;
- concurrency/load tests;
- failure/recovery tests;
- security/tenant-isolation tests.

Golden fixtures should include difficult ordering:
- equal timestamps;
- duplicate input;
- out-of-order input;
- bid/ask spread changes;
- gaps;
- SL and TP near the same interval;
- pending activation followed by exit;
- invalid/corrupt chunk;
- boundary between partitions.

## 17. Worst-case capacity benchmark

Never certify capacity using only users clustered around one historical date.

Required scenario family:
- 10 -> 25 -> 50 -> 100 concurrent sessions;
- uniformly/randomly distributed historical cursors;
- minimal cache overlap;
- mixed replay speeds;
- periodic MAX bursts;
- mixed timeframes;
- active orders;
- bounded cache deliberately smaller than total working dataset;
- pause/resume and reconnect during load.

Measure at least:
- p50/p95/p99 replay-step or service latency;
- CPU;
- process/host RAM;
- disk throughput/IOPS where available;
- decompression/query throughput;
- cache hit/miss/eviction;
- queue wait/depth;
- error/cancellation rate;
- session recovery;
- deterministic output hashes.

Capacity claims must name hardware, dataset/version, build, test profile and limits.

## 18. Failure engineering

Before public alpha intentionally test:
- worker/process death;
- API restart;
- DB restart where cloud path is in scope;
- client disconnect/reconnect;
- cache eviction under pressure;
- corrupt/missing chunk;
- invalid index;
- duplicate/out-of-order tick;
- disk-full/permission failure where practical;
- partial import/publication;
- interrupted session save;
- stale revision conflict.

Expected principle: durable session/evidence truth survives replaceable compute workers; corrupted evidence fails closed rather than silently becoming valid market history.

## 19. Security and multi-tenancy gates

Before external multi-user launch:
- verified authentication;
- server-side authorization;
- workspace ownership on every user resource;
- no trust in client-supplied tenant identity;
- object-level access tests (User A cannot fetch User B);
- rate/body/resource limits;
- secret management;
- TLS;
- input validation;
- dependency/security scans;
- backup + restore proof;
- audit events for sensitive mutations;
- signed/expiring private object access where applicable.

## 20. Market-data rights registry

Technical ingestion is not publication permission.

Every provider/dataset should eventually have:
```text
provider
source URL/evidence
acquisition method
instrument
coverage
personal-use status
commercial-use status
storage permission
display permission
redistribution permission
derived-data status
retention constraints
attribution requirements
license/evidence timestamp
review status
```

Allowed statuses should distinguish at least:
`UNVERIFIED`, `PERSONAL_ONLY`, `COMMERCIAL_ALLOWED`, `REDISTRIBUTION_ALLOWED`, `RESTRICTED`.

Never promote personal-local evidence to public SaaS data without rights evidence.

## 21. Observability gate

Before meaningful external alpha, expose enough telemetry to diagnose:
- active/paused sessions;
- replay throughput/latency;
- CPU/RAM;
- storage latency/throughput;
- cache utilization/hit/eviction;
- worker utilization;
- queue depth/wait;
- API errors;
- dataset/chunk failures;
- session restore failures;
- build/engine/dataset version.

Logs must avoid unnecessary secrets/sensitive user content.

## 22. Alpha scope

Alpha should be small but trustworthy.

Core quality target:
- chart;
- core drawings;
- indicators;
- historical navigation;
- replay;
- manual market/pending orders;
- correct SL/TP;
- risk sizing UX;
- spread/execution assumptions;
- journal;
- basic statistics;
- save/resume;
- deterministic evidence.

Not required for first alpha:
- social network;
- AI research assistant;
- live broker connection;
- L2/L3 simulation;
- broad instrument catalog;
- enterprise microservices;
- Kubernetes;
- complex portfolio research;
- native mobile app.

Initial data may deliberately be one provider + XAUUSD + ~6 months if rights permit. This validates product/UX/operations, **not strategy robustness across market regimes**.

## 23. Progressive release gates

No calendar deadline automatically advances a gate.

```text
Internal -> 5 users -> 15 -> 30 -> 50 -> 100 -> Beta
```

Advance only when relevant:
- correctness passes;
- deterministic replay passes;
- data integrity passes;
- performance within measured capacity;
- no unresolved severe crash/data-loss issue;
- recovery passes;
- telemetry is sufficient;
- user feedback does not reveal a blocking trust/usability failure.

Product funnel to measure:
`signup -> open market -> start replay -> place trade -> finish session -> review result -> return`.

Repeat use/retention matters more than raw visits.

## 24. Infrastructure evolution

### Local/current
Browser + local/static data + isolated backend research seams.

### First hosted
Reverse proxy/TLS -> web -> API -> PostgreSQL + market-data storage/backups.

### Scale only after evidence
CDN/web fleet -> API instances -> bounded queue -> replay/research workers -> shared object/market storage + PostgreSQL; bounded cache/coordination introduced when benchmarks justify it.

Do not introduce Kubernetes, microservices, distributed databases, Redis, or Rust services merely because the roadmap eventually has many users.

## 25. Performance escalation rule

Optimize in this order:
1. correctness;
2. measure;
3. data layout/index;
4. bounded chunking/prefetch;
5. algorithmic hot path;
6. process-level concurrency;
7. caching;
8. native/Rust hot path if profiling proves value;
9. distributed infrastructure only after single-node evidence.

Rust is a tool for demonstrated hot paths, not a project identity requirement.

## 26. Immediate engineering sequence from current 42.x state

This sequence is planning, not authorization:

1. Verify actual local/GitHub state and preserved 42.18 provenance.
2. Resume preserved 42.18 only under explicit authorization and against frozen 42.17 + 42.19.
3. Implement/validate 42.19 sidecar evidence access semantics.
4. Complete scalable V2 storage/index publication.
5. Complete disk-bounded validation and immutable time index.
6. Complete indexed timeline positioning.
7. Ingest/benchmark authorized private local dataset without claiming public rights.
8. Review measured RAM/I/O/CPU and data-quality evidence.
9. Only then authorize canonical Tick Execution Engine V1.
10. Add tick-to-candle aggregation without making candle path execution authority.
11. Define frontend cutover/migration separately; preserve v1 until equivalence is proven.
12. Add durable independent session lifecycle.
13. Add bounded shared cache.
14. Add bounded concurrency/backpressure.
15. Run random-timeline worst-case load benchmark.
16. Run recovery/failure suite.
17. Complete external-alpha security/telemetry gates.
18. Start progressive closed alpha.

Each step may split into smaller checkpoints. Never bundle several risky authority changes just to move faster.

## 27. Definition of Done for an engineering checkpoint

A checkpoint is not complete because code exists.

Required as applicable:
- baseline verified;
- scope and non-goals explicit;
- authority checked;
- implementation minimal to scope;
- unit/contract/golden/integration tests pass;
- relevant regression passes;
- build/lint/static checks pass;
- benchmark if performance claim/change exists;
- browser evidence if UI behavior changes;
- no-look-ahead/determinism proof if temporal/execution behavior changes;
- docs/AI context updated where factual state changed;
- dependency/license notices updated where needed;
- diff reviewed;
- no secrets/private market datasets committed;
- commit;
- push;
- actual remote equality verified;
- working tree clean;
- next checkpoint stated but not auto-authorized.

## 28. Future-AI decision algorithm

Whenever asked “what next?”:

1. Read current authority and this plan.
2. Verify remote/local baseline if local tools are available.
3. Identify the nearest incomplete prerequisite on the immediate sequence.
4. Check whether it is already authorized.
5. If not authorized, propose one bounded checkpoint/prompt; do not implement.
6. Search existing code and OSS provenance map before designing new infrastructure.
7. Preserve protected systems and current v1 behavior unless migration is explicitly authorized.
8. Prefer tests/benchmarks that falsify assumptions.
9. After completion, update factual authority and this plan only if architecture/source decisions changed.
10. Never infer completion from a draft, folder name, roadmap phase, or partial benchmark.

## 29. Known planning gaps to close before public alpha

- explicit bounded-cache numerical policy derived from benchmark;
- session suspension/restoration contract;
- worker/backpressure contract;
- browser event-delivery budget;
- canonical Tick Execution V1 semantics;
- tick-to-candle aggregation ownership;
- frontend cutover/migration plan;
- real provider commercial/redistribution rights;
- hardware-specific capacity envelope;
- production backup/restore RPO/RTO targets;
- external-alpha privacy/telemetry policy;
- operational incident/runbook.

These are deliberate open decisions, not permission to invent values prematurely.

## 30. Anti-rush rule

The project does not advance because a month, phase number, credit quota, or coding-agent session is ending.

When evidence is incomplete:
**STOP -> preserve work -> record blocker -> resolve contract/data/test -> continue.**

A slower validated checkpoint is preferred to a fast release that can produce incorrect execution, lose sessions, expose another user's data, or collapse under expected load.
