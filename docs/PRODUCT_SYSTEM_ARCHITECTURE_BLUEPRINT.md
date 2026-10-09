# Backtest Lab — Product & System Architecture Blueprint

> **Domain precedence (Phase 18.4):** [Trading Method & Session specification](TRADING_METHOD_SESSION_SPEC.md) owns current Method/Session semantics. Older mode/version language below is historical design/research terminology where it conflicts: Session inherits its Method, Protocol is Planned-only, checklist OFF retains evidence, and cross-pair coverage is not a maturity requirement. Technical version/hash provenance remains useful; it is not a mandatory user-facing Method-version workflow. These blueprints preserve strategic knowledge and do not authorize runtime changes.

> **Status:** Strategic architecture blueprint / living design document  
> **Scope:** Product architecture, system boundaries, data architecture, research architecture, deployment direction, and evolution from local v1 to research SaaS.  
> **Authority boundary:** This document describes intended architecture. It does **not** authorize implementation, change current phase status, or replace `docs/ROADMAP.md`, `AI_CONTEXT/04_CURRENT_PHASE.md`, completed history, or workflow/Definition of Done.

Related documents:
- [Research Thesis](BACKTEST_LAB_RESEARCH_THESIS.md)
- [Master Roadmap](ROADMAP.md)

---

# 1. Product North Star

Backtest Lab is a **research environment for evidence-based trading decisions**, not a signal seller and not an autonomous trading system.

```text
IDEA → TEST → VALIDATE → STRESS → SIZE → REPLICATE → FORWARD/LIVE → AUDIT → IMPROVE
```

Design principles:

1. Chart-first interaction.
2. Freedom First → Evidence Second → Guardrails Optional.
3. Observe quietly → Analyze deeply → Warn selectively → Never force.
4. Reproducibility over cosmetic complexity.
5. Raw market data is immutable; derived research objects are versioned.
6. Exploratory and confirmatory research must remain distinguishable.
7. Heavy analytics must not block replay UX.
8. Every result must be traceable to data, protocol, engine version, and assumptions.
9. Architecture evolves incrementally; do not prematurely distribute a system that works correctly as a modular monolith.

---

# 2. Architecture at a Glance

```mermaid
flowchart TB
    U[Trader / Researcher]
    UI[Web App — Chart First UX]
    API[Application API]
    RE[Research Orchestrator]
    ME[Market & Replay Engine]
    TE[Trading / Execution Engine]
    AE[Analytics Engine]
    RI[Research Integrity Engine]
    DB[(PostgreSQL)]
    OBJ[(Object / Dataset Storage)]
    CACHE[(Cache)]
    W[Background Workers]
    EXT[Market / Economic Data Sources]

    U --> UI
    UI --> API
    API --> ME
    API --> TE
    API --> RE
    RE --> AE
    RE --> RI
    ME --> TE
    TE --> AE
    API --> DB
    RE --> DB
    AE --> W
    RI --> W
    W --> DB
    W --> OBJ
    EXT --> OBJ
    EXT --> DB
    OBJ --> ME
    CACHE <--> API
```

**Initial production direction:** Next.js frontend + FastAPI backend + PostgreSQL. Redis/object storage/workers are introduced only when workloads justify them.

---

# 3. Layered System Design

```mermaid
flowchart TB
    A[Presentation Layer]
    B[Application / API Layer]
    C[Domain Layer]
    D[Research & Analytics Layer]
    E[Data Layer]
    F[Infrastructure Layer]

    A --> B --> C --> D --> E --> F
```

## 3.1 Presentation Layer

Responsibilities:
- chart rendering;
- drawings;
- indicators;
- replay controls;
- order interaction;
- journal;
- Analysis;
- Research/Lab Protocol UI;
- research reports;
- dashboard/workspace later.

The UI should not become the source of truth for trading/research rules.

## 3.2 Application/API Layer

Responsibilities:
- request validation;
- authentication/authorization later;
- use-case orchestration;
- idempotency;
- pagination/query limits;
- job submission;
- API contracts;
- response serialization.

## 3.3 Domain Layer

Pure business/research rules:
- replay state;
- orders/trades/positions;
- risk/reward;
- account/equity;
- strategy protocol;
- experiment lifecycle;
- inclusion/exclusion;
- market regime definitions;
- execution assumptions.

Domain logic should remain testable without browser/database/network dependencies.

## 3.4 Research & Analytics Layer

Contains:
- descriptive statistics;
- statistical evidence;
- RR Laboratory;
- MAE/MFE;
- Monte Carlo;
- survival analysis;
- regime analysis;
- robustness;
- multiple-testing correction;
- OOS/walk-forward;
- portfolio/correlation;
- behavioral/live audit.

## 3.5 Data Layer

Responsible for:
- canonical market data;
- economic events;
- user/workspace data;
- strategies;
- experiment protocols;
- sessions;
- trades;
- research results;
- audit/version history.

## 3.6 Infrastructure Layer

Deployment, observability, backups, queues/workers, caching, CI/CD, security controls, secrets, rate limiting and external integrations.

---

# 4. Frontend Blueprint

```mermaid
flowchart LR
    APP[Next.js App]
    CHART[Chart Workspace]
    DRAW[Drawing System]
    IND[Indicator System]
    REPLAY[Replay Controls]
    TRADE[Trading UX]
    JOURNAL[Journal]
    ANALYSIS[Analysis]
    LAB[Lab Protocol]
    REPORT[Research Report]

    APP --> CHART
    CHART --> DRAW
    CHART --> IND
    CHART --> REPLAY
    CHART --> TRADE
    APP --> JOURNAL
    APP --> ANALYSIS
    APP --> LAB
    APP --> REPORT
```

### Frontend state separation

**Ephemeral UI state**
- open panels;
- hover/selection;
- dialogs;
- temporary drawing interaction.

**Session state**
- replay cursor;
- visible range;
- active instrument/timeframe;
- open simulated positions.

**Persisted research state**
- protocol;
- experiment metadata;
- trades;
- exclusions;
- journal;
- result snapshots.

Do not persist everything merely because it can be persisted.

---

# 5. Market Data Architecture

## 5.1 Canonical pipeline

```mermaid
flowchart LR
    S[Source] --> I[Ingest]
    I --> V[Validate]
    V --> N[Normalize UTC / Symbol]
    N --> D[Deduplicate]
    D --> Q[Quality Checks]
    Q --> C[Canonical Dataset]
    C --> A[Aggregate Timeframes]
    C --> R[Replay Delivery]
```

### Canonical candle

```text
instrument_id
timestamp_utc
timeframe
open
high
low
close
volume?
source
dataset_version
quality_flags
```

Raw imported/source data should not be silently mutated. Corrections create a new dataset/version or auditable transformation.

## 5.2 Candle Mode

Primary mode for fast manual research:
- OHLC replay;
- timeframe aggregation;
- deterministic reveal;
- no look-ahead;
- explicit same-candle SL/TP ambiguity.

## 5.3 Tick / Intrabar Mode

Later high-fidelity layer:
- tick/bid/ask data;
- spread;
- execution ordering;
- intrabar path;
- slippage;
- more defensible SL/TP resolution.

```mermaid
flowchart TD
    M[Market Engine]
    M --> C[Candle Mode]
    M --> T[Tick / Intrabar Mode]
    C --> X[Shared Trading / Research Contracts]
    T --> X
```

The research layer must know which market/execution mode produced a result.

---

# 6. Replay Engine Blueprint

Core invariant:

> **At replay time t, no component may expose information from t+1 onward.**

```mermaid
stateDiagram-v2
    [*] --> Loaded
    Loaded --> Playing
    Playing --> Paused
    Paused --> Playing
    Playing --> Completed
    Paused --> Seeked
    Seeked --> Paused
    Completed --> [*]
```

Replay responsibilities:
- deterministic revealed range;
- play/pause/step;
- playback speed;
- high-water/no-look-ahead state;
- event/news synchronization;
- incremental chart updates;
- replay-safe indicator calculation;
- deterministic seed/context where applicable.

Replay does **not** calculate research conclusions.

---

# 6A. Temporal View, Replay State & Canonical Research Log

Temporal correctness should be enforced structurally where practical.

```text
Versioned Dataset
      ↓
TimeBoundedView(t)
      ↓
Replay / Indicators / News / Execution
      ↓
Canonical Event + Trade Log
      ↓
Research Compute
```

A temporal consumer should not receive unrestricted future observations merely because an index is available. Relevant features should support truncation-invariance tests: state/output at `t` remains unchanged when data after `t` is physically absent.

Replay/backtest lifecycle should converge on an explicit state/revision model so chart, replay cursor, trading settlement, journal/event log and later cloud resume cannot silently represent different committed moments. Exact state names are implementation decisions; the invariant is that a committed replay revision has an unambiguous canonical trading/research state.

Research analytics consume canonical logs/results rather than being embedded into the candle loop.

# 7. Trading & Execution Engine

```mermaid
flowchart LR
    INTENT[Order Intent] --> VALIDATE[Validate]
    VALIDATE --> PENDING[Pending/Open Order]
    PENDING --> FILL[Fill Model]
    FILL --> POS[Position]
    POS --> PART[Partial Exit]
    POS --> EXIT[Full Exit]
    PART --> POS
    EXIT --> CLOSED[Completed Position]
    CLOSED --> JOURNAL[Research Trade Record]
```

Canonical concerns:
- direction;
- entry;
- SL;
- TP;
- risk;
- quantity;
- fill price;
- commission;
- spread;
- slippage;
- partial exits;
- realized R;
- realized P/L;
- timestamps;
- execution assumptions.

The engine must distinguish **order intent**, **market simulation**, and **research record**.

---

# 8. Experiment Protocol Architecture

```mermaid
flowchart TD
    H[Hypothesis]
    H --> P[Protocol v1]
    P --> E[Experiment]
    E --> O[Opportunities]
    O --> T[TAKE]
    O --> X[EXCLUDE]
    T --> TR[Trade Dataset]
    X --> XR[Exclusion Dataset]
    TR --> RES[Results]
    XR --> RES
    P --> PASS[Experiment Passport]
    E --> PASS
    RES --> PASS
```

### Protocol object

```text
protocol_id
strategy_id
version
hypothesis
entry_rules
exit_rules
rr_policy
risk_policy
instrument_scope
timeframe
session_scope
inclusion_criteria
exclusion_criteria
planned_sample
stopping_rule
regime_definition_id
execution_assumption_id
created_at
locked_at?
```

Changing a material locked protocol field creates a new version/experiment rather than rewriting history.

---

# 9. Experiment Passport & Reproducibility

Every serious Lab Protocol result should be reconstructible from canonical identity/provenance such as:

```text
Dataset ID + Version + Content Hash
+ Strategy ID + Version + Definition Hash
+ Protocol ID + Version + Content Hash
+ RNG Algorithm + Seed
+ Engine / Research Calculator Version
+ Execution Assumption Version
+ Regime Definition Version
+ Trial / Strategy Lineage
= Experiment Identity
```

Hardware identity is not required by default. Prefer defined numeric semantics and versioned calculators; record additional environment metadata only where it materially affects reproducibility.

Candidate passport fields:
- experiment ID/hash;
- dataset content hash;
- strategy definition hash;
- protocol content hash;
- RNG algorithm/seed;
- trial/strategy lineage and experiment-family reference;
- user/workspace;
- strategy/version;
- instrument/timeframe;
- period;
- dataset/version;
- protocol/version;
- seed;
- engine build;
- execution model;
- regime algorithm;
- planned vs actual N;
- exclusion summary;
- result version.

A result without provenance is descriptive output, not a reproducible research artifact.

---

# 10. Research Engine Architecture

```mermaid
flowchart TB
    DATA[Experiment Dataset]
    BASIC[Basic Analytics]
    STAT[Statistical Evidence]
    RR[RR Laboratory]
    MFE[MAE / MFE]
    REG[Regime Analysis]
    DEST[Strategy Destruction]
    MC[Monte Carlo]
    SURV[Survival Risk]
    OOS[OOS / Walk Forward]
    PORT[Portfolio / Correlation]
    BEH[Behavioral Audit]
    REPORT[Research Report]

    DATA --> BASIC
    DATA --> STAT
    DATA --> RR
    DATA --> MFE
    DATA --> REG
    DATA --> DEST
    DATA --> MC
    MC --> SURV
    STAT --> OOS
    DEST --> OOS
    OOS --> PORT
    PORT --> BEH
    BASIC --> REPORT
    STAT --> REPORT
    RR --> REPORT
    REG --> REPORT
    DEST --> REPORT
    SURV --> REPORT
    OOS --> REPORT
    PORT --> REPORT
    BEH --> REPORT
```

## 10.1 Basic Analytics

Free/descriptive:
- trade count;
- wins/losses;
- WR;
- total P/L;
- total/average R;
- average win/loss;
- profit factor;
- equity;
- historical MaxDD;
- streaks;
- journal.

## 10.2 Statistical Evidence Engine

Candidate outputs:
- break-even baseline;
- uncertainty/confidence intervals;
- expectancy uncertainty;
- sample/effective sample diagnostics;
- power where meaningful;
- pre-registered vs exploratory status.

Never reduce evidence to a universal binary “good/bad strategy”.

---

# 11. RR Laboratory Architecture

RR Laboratory is **post-experiment counterfactual research**.

Wrong design:

```text
Original R × new RR = simulated result
```

Correct direction:

```mermaid
flowchart LR
    T[Original Trade Entry] --> P[Historical Price Path]
    P --> C1[Candidate RR A]
    P --> C2[Candidate RR B]
    P --> C3[Candidate RR C]
    C1 --> R[Compare outcomes]
    C2 --> R
    C3 --> R
    R --> S[WR / EV / DD / Streak / Robustness]
```

Alternative SL/TP must be evaluated against available historical path at appropriate resolution. Ambiguous paths must be marked rather than invented.

RR Lab output is exploratory unless independently validated.

---

# 12. Strategy Destruction Lab

```mermaid
flowchart TD
    B[Baseline Strategy] --> S1[Spread Stress]
    B --> S2[Slippage Stress]
    B --> S3[Entry Perturbation]
    B --> S4[SL / TP Perturbation]
    B --> S5[Parameter Neighborhood]
    B --> S6[Regime Stress]
    B --> S7[Sequence Stress]
    B --> S8[Execution Assumption Stress]
    S1 --> ROB[Robustness Profile]
    S2 --> ROB
    S3 --> ROB
    S4 --> ROB
    S5 --> ROB
    S6 --> ROB
    S7 --> ROB
    S8 --> ROB
```

Store baseline, perturbation specification, result, and engine/data version.

---

# 13. Research Integrity Engine

```mermaid
flowchart LR
    EXP[Exploration] --> FAMILY[Hypothesis Family]
    FAMILY --> RAW[Raw Tests]
    RAW --> CORR[Multiple-Testing Correction]
    CORR --> CAND[Candidate Hypothesis]
    CAND --> OOS[Fresh OOS]
    OOS --> REP[Replication]
```

Capabilities:
- append-only trial/strategy lineage;
- hypothesis-family registry;
- number of relevant tests;
- raw p-values;
- Bonferroni;
- Benjamini-Hochberg FDR/q-values;
- exploratory vs pre-registered labels;
- immutable audit trail;
- fresh OOS linkage.

Multiple-testing correction is **not** automatically applied to every stress test or merely because a trial counter increased. Trial history is provenance; the inferential question and hypothesis family determine whether/how Bonferroni, BH-FDR, DSR or another method is appropriate. Sensitivity analysis and inferential hypothesis testing remain distinct concepts.

---

# 14. Monte Carlo & Survival Engine

Inputs:
- empirical R distribution or explicit model;
- sequence/resampling method;
- risk model;
- number of trades;
- number of paths;
- seed;
- constraints/assumptions.

Outputs:
- terminal equity distribution;
- MaxDD distribution;
- losing streak distribution;
- recovery characteristics;
- threshold exceedance probabilities.

Inverse risk design:

```text
r_max = max { r : P(MaxDD >= D*) <= alpha }
```

Long-running simulations belong in background jobs rather than the interactive request path.

---

# 15. Market Regime Engine

Regime definition is a **versioned research object**.

```text
regime_definition_id
name
version
features
thresholds
lookback
warmup
classification_rules
engine_version
```

Examples:
- trend/range;
- low/normal/high volatility;
- session;
- economic-event windows.

No hidden subjective classification in Lab Protocol.

---

# 16. Economic News Architecture

```mermaid
flowchart LR
    SRC[Historical Economic Source] --> ING[Ingest]
    ING --> TZ[UTC Normalize]
    TZ --> MAP[Currency / Event Mapping]
    MAP --> VER[Dataset Version]
    VER --> MARK[Chart Markers]
    VER --> WINDOW[Pre / During / Post Windows]
    WINDOW --> LINK[Trade ↔ Event Context]
    LINK --> ANA[News Analytics]
```

Canonical event candidate:

```text
event_id
timestamp_utc
currency
event_name
category
impact
previous
forecast
actual
source
dataset_version
revision_metadata?
```

News is a research subsystem, not decorative chart icons.

---

# 17. Portfolio & Correlation Architecture

Only activate meaningful portfolio analysis when enough multi-strategy/multi-market data exists.

```mermaid
flowchart TD
    A[Strategy A Returns] --> C[Alignment Engine]
    B[Strategy B Returns] --> C
    D[Strategy C Returns] --> C
    C --> CORR[Strategy Return Correlation]
    C --> LOSS[Simultaneous Loss Analysis]
    CORR --> P[Portfolio Simulator]
    LOSS --> P
    P --> DD[Portfolio DD / Exposure / Monte Carlo]
```

Price correlation alone is insufficient. Strategy-return and concurrent-loss behavior matter.

---

# 18. Behavioral / Live Audit Architecture

```mermaid
flowchart LR
    TEST[Tested Protocol] --> COMP[Comparison]
    LIVE[Forward / Live Records] --> COMP
    COMP --> DRIFT[Execution Drift Components]
    DRIFT --> REPORT[Behavioral Audit]
```

Candidate components:
- ΔRisk;
- ΔEntry;
- ΔSL;
- ΔTP;
- ΔHoldingTime;
- rule violations;
- skipped opportunities;
- frequency changes.

Do not infer psychology. Report measurable behavior.

---

# 19. Data Model Blueprint

Conceptual relationships—not a locked production schema:

```mermaid
erDiagram
    USER ||--o{ WORKSPACE : owns
    WORKSPACE ||--o{ STRATEGY : contains
    STRATEGY ||--o{ STRATEGY_VERSION : versions
    STRATEGY_VERSION ||--o{ PROTOCOL : tested_by
    PROTOCOL ||--o{ EXPERIMENT : instantiates
    DATASET ||--o{ EXPERIMENT : supplies
    EXPERIMENT ||--o{ OPPORTUNITY : observes
    EXPERIMENT ||--o{ TRADE : records
    EXPERIMENT ||--o{ RESEARCH_RESULT : produces
    EXPERIMENT ||--|| EXPERIMENT_PASSPORT : identifies
    REGIME_DEFINITION ||--o{ EXPERIMENT : classifies
    EXECUTION_ASSUMPTION ||--o{ EXPERIMENT : simulates
    EXPERIMENT ||--o{ AUDIT_EVENT : traces
```

### Core tables/objects later

**Identity**
- users
- workspaces
- memberships

**Trading research**
- strategies
- strategy_versions
- protocols
- experiments
- opportunities
- trades
- trade_events
- journal_entries
- research_results

**Market**
- instruments
- datasets
- candles
- ticks later
- economic_events
- regime_definitions

**Reproducibility**
- experiment_passports
- execution_assumptions
- engine_versions
- audit_events

**Commercial**
- subscriptions
- entitlements
- usage_records

---

# 20. Storage Strategy

```mermaid
flowchart LR
    PG[(PostgreSQL)] --> META[Metadata / Users / Experiments / Trades]
    OBJ[(Object Storage)] --> BULK[Large datasets / exports / reports]
    CACHE[(Redis later)] --> HOT[Hot cache / jobs / ephemeral coordination]
```

### PostgreSQL
Use for relational/queryable product state.

### Object storage
Use later for large immutable datasets, exports, reports, artifacts and high-volume tick chunks where appropriate.

### Redis
Not mandatory at MVP. Introduce for:
- job queue coordination;
- rate limiting;
- short-lived cache;
- distributed locks where genuinely needed.

Avoid storing canonical research truth only in cache.

---

# 21. API Blueprint

Suggested API namespaces:

```text
/api/v1/auth
/api/v1/workspaces
/api/v1/instruments
/api/v1/datasets
/api/v1/replay
/api/v1/orders
/api/v1/trades
/api/v1/strategies
/api/v1/protocols
/api/v1/experiments
/api/v1/research
/api/v1/reports
/api/v1/jobs
```

Example experiment flow:

```text
POST /protocols
POST /experiments
POST /experiments/{id}/opportunities
POST /experiments/{id}/trades
POST /experiments/{id}/complete
POST /experiments/{id}/research-jobs
GET  /jobs/{id}
GET  /experiments/{id}/report
```

Contracts should be versioned and domain-oriented, not mirror database tables blindly.

---

# 22. Async Job Architecture

Heavy research must not freeze the chart.

```mermaid
sequenceDiagram
    participant UI
    participant API
    participant Queue
    participant Worker
    participant DB

    UI->>API: Request Monte Carlo / robustness
    API->>DB: Create research_job
    API->>Queue: Enqueue job
    API-->>UI: job_id
    Queue->>Worker: Execute
    Worker->>DB: Persist result + provenance
    UI->>API: Poll/subscribe status
    API-->>UI: completed result
```

Candidate heavy jobs:
- Monte Carlo;
- RR grid;
- robustness grids;
- walk-forward;
- portfolio simulation;
- report generation;
- large imports.

---

# 23. Free vs Paid Entitlement Architecture

Entitlements must be server-authoritative in SaaS mode.

```text
FREE
├─ Free Backtest
├─ Lab Protocol
├─ ≤ 1 month market window / experiment
└─ Basic Results

PAID
├─ Extended historical data
├─ Statistical Evidence
├─ RR Lab
├─ Monte Carlo / Survival
├─ Robustness / Destruction Lab
├─ OOS / Walk Forward
├─ Regime research
├─ Portfolio / Correlation
├─ Behavioral Audit
└─ Full Research Report
```

Do not fork the scientific protocol into an intentionally invalid “free methodology”. Monetize data depth and analysis depth.

---

# 24. Security & Multi-Tenancy

When cloud/multi-user arrives:

- every user-owned resource has explicit workspace ownership;
- authorization occurs server-side;
- tenant ID/workspace ID is never trusted solely from client input;
- rate limits;
- secure session/token lifecycle;
- CSRF/XSS/SQL injection protections as applicable;
- secrets outside source control;
- encrypted transport;
- backup/restore testing;
- audit events for sensitive mutations;
- signed/expiring URLs for private object storage;
- least-privilege service credentials.

Research data isolation is a product requirement, not an optional hardening task.

---

# 25. Performance Blueprint

Priority model:

1. Security and correctness are hard constraints.
2. Determinism/reproducibility where promised.
3. Lightweight by default: avoid unnecessary work.
4. Measure relevant render/CPU/memory/query/I/O behavior.
5. Optimize demonstrated bottlenecks.
6. Scale through preserved boundaries when evidence requires it.

Techniques:
- incremental chart updates;
- chunked candle loading;
- timeframe aggregation/cache;
- indexed time-series queries;
- bounded API responses;
- lazy research panels;
- background heavy computation;
- memoized/pure indicator calculations where appropriate;
- compression for bulk datasets;
- pagination;
- load tests before infrastructure guessing.

Do not move to microservices merely because the product may someday have many users. Do not replace official chart-library behavior with custom canvas/virtualization without measured evidence that rendering is the bottleneck.

---

# 26. Deployment Blueprint

## Stage A — Local v1

```text
Browser
  ↓
Local app / local service
  ↓
Imported market data
```

Goal: research correctness and professional manual backtesting.

## Stage B — First hosted deployment

```mermaid
flowchart TB
    DNS[Domain / DNS]
    RP[Reverse Proxy + TLS]
    WEB[Next.js]
    API[FastAPI]
    DB[(PostgreSQL)]
    VOL[(Backups / Storage)]

    DNS --> RP
    RP --> WEB
    RP --> API
    API --> DB
    DB --> VOL
```

A single VPS can host the early system while usage is modest.

## Stage C — Scaled SaaS

```mermaid
flowchart TB
    CDN[CDN / Edge]
    WEB[Web]
    API[API Instances]
    CACHE[(Redis)]
    DB[(Managed/PostgreSQL)]
    Q[Queue]
    W[Workers]
    OBJ[(Object Storage)]
    OBS[Observability]

    CDN --> WEB
    WEB --> API
    API --> CACHE
    API --> DB
    API --> Q
    Q --> W
    W --> DB
    W --> OBJ
    API --> OBJ
    API --> OBS
    W --> OBS
```

Scale based on measured bottlenecks, not imagined traffic.

---

# 27. CI/CD Blueprint

```mermaid
flowchart LR
    DEV[Change] --> GIT[Git Commit]
    GIT --> CI[CI]
    CI --> TEST[Test + Lint + Build]
    TEST --> GATE{Pass?}
    GATE -- No --> STOP[Stop]
    GATE -- Yes --> MAIN[Validated Main]
    MAIN --> DEPLOY[Deploy]
    DEPLOY --> SMOKE[Smoke / Health Check]
```

Production deployment later should support:
- reproducible builds;
- environment-specific configuration;
- migrations;
- rollback;
- health checks;
- deployment logs.

---

# 28. Observability

Minimum production signals:

**Application**
- request rate;
- error rate;
- latency;
- job failures;
- queue depth.

**Data**
- import failures;
- missing intervals;
- duplicate timestamps;
- dataset/version lineage.

**Research**
- engine version;
- job duration;
- failed simulations;
- result provenance.

**Infrastructure**
- CPU;
- memory;
- disk;
- DB connections;
- backup status.

Observability must not leak private strategy data into logs.

---

# 29. Versioning Rules

Version independently where appropriate:

```text
App Version
Engine Version
Dataset Version
Protocol Version
Strategy Version
Regime Definition Version
Execution Assumption Version
Research Result Version
```

A historical result must remain interpretable even after future engine upgrades.

---

# 30. AI Architecture Boundary

AI is a **research assistant**, not the canonical calculator.

AI may:
- summarize results;
- explain statistical concepts;
- surface anomalies;
- propose hypotheses;
- compare experiment reports;
- help construct protocol drafts.

AI must not silently:
- rewrite canonical trade history;
- fabricate market data;
- alter experiment parameters after results;
- replace deterministic calculations;
- claim a strategy will be profitable;
- receive autonomous real-money execution authority from this architecture.

```mermaid
flowchart LR
    DATA[Verified Research Results] --> AI[AI Research Assistant]
    AI --> INSIGHT[Explanation / Hypothesis]
    INSIGHT --> HUMAN[Human Decision]
    HUMAN --> NEW[New Protocol / Experiment]
```

---

# 31. Failure & Recovery Principles

Design for:
- browser refresh;
- interrupted replay;
- failed import;
- failed analytics job;
- worker restart;
- DB migration failure;
- partial network outage;
- stale client state.

Rules:
- writes should be idempotent where feasible;
- incomplete jobs have explicit state;
- canonical data is never inferred from a failed partial result;
- backups are useful only after restore has been tested;
- experiment provenance survives recovery.

---

# 32. Evolution by Product Version

| Version | Architectural identity |
|---|---|
| v1.0 | Local/manual research platform; validated replay/trading/analysis |
| v2.0 | Cloud multi-user foundation: API, PostgreSQL, auth, workspaces, cloud market data |
| v3.0 | Professional research: strategies, journal, analytics, regime, portfolio, Monte Carlo |
| v4.0 | High-fidelity execution: tick, bid/ask, spread, costs, slippage, intrabar |
| v5.0 | SaaS operations: subscriptions, teams, RBAC, collaboration, audit, admin |
| v6.0 | Quant research: datasets, experiments, parameter research, walk-forward, robustness, AI research assistant |
| v7.0 | External/live/paper/forward-testing infrastructure and algorithmic-readiness validation |

This table summarizes the existing roadmap. It does not authorize any future phase.

---

# 33. Architectural Non-Negotiables

1. No look-ahead.
2. Deterministic replay where deterministic behavior is promised.
3. Canonical trade/execution records.
4. Versioned research assumptions.
5. Reproducible Lab Protocol experiments.
6. Explicit ambiguity instead of invented certainty.
7. Exploration ≠ validation.
8. Multiple-testing awareness.
9. Fresh OOS/replication for stronger evidence.
10. Heavy analytics outside latency-sensitive chart interaction.
11. Server-authoritative ownership/entitlements in SaaS mode.
12. AI interprets verified results; deterministic engines calculate them.
13. No autonomous real-money execution within the current roadmap boundary.
14. Do not replace a working modular architecture with microservices without measured need.

---

# 34. Target Repository Structure

Conceptual target; existing validated paths must not be moved merely to match this diagram.

```text
apps/
  web/
  api/

engine/
  market/
  replay/
  execution/
  risk/
  indicators/
  statistics/
  monte_carlo/
  research_integrity/
  regime/
  robustness/
  portfolio/

research/
  protocols/
  experiments/
  reports/

data/
  import/
  validation/
  aggregation/

workers/
  research_jobs/

tests/
  unit/
  integration/
  regression/
  e2e/

docs/
  ROADMAP.md
  BACKTEST_LAB_RESEARCH_THESIS.md
  PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md
```

Repository refactoring should happen only under an explicitly authorized implementation phase.

---

# 35. One-Page Blueprint

```mermaid
flowchart TB
    USER[Trader / Researcher]
    UX[Chart-First Backtest Lab]
    CORE[Replay + Trading + Journal]
    PROTOCOL[Lab Protocol + Experiment Passport]
    DATA[Versioned Market / News / Trade Data]
    RESEARCH[Evidence + RR Lab + Regime + Robustness]
    RISK[Monte Carlo + Survival]
    INTEGRITY[Multiple Testing + OOS + Replication]
    PORT[Portfolio / Correlation]
    AUDIT[Behavioral / Live Audit]
    AI[AI Research Assistant]
    CLOUD[API + PostgreSQL + Workers + Object Storage]

    USER --> UX
    UX --> CORE
    CORE --> PROTOCOL
    PROTOCOL --> DATA
    DATA --> RESEARCH
    RESEARCH --> RISK
    RESEARCH --> INTEGRITY
    INTEGRITY --> PORT
    PORT --> AUDIT
    AUDIT --> AI

    CORE <--> CLOUD
    PROTOCOL <--> CLOUD
    DATA <--> CLOUD
    RESEARCH <--> CLOUD
```

## Final architecture thesis

> **Backtest Lab should feel simple at the chart, strict in the data, transparent in the assumptions, and deep in the research.**

The chart is the workspace.  
The experiment is the unit of research.  
The dataset is evidence.  
The passport makes evidence reproducible.  
The research engines measure uncertainty.  
The human remains the decision-maker.


---

# 36. Extensible Market Data & Indicator Import Boundary

> **Status:** Architecture direction, not current implementation authorization.

Backtest Lab must not be permanently coupled to Twelve Data, one broker feed, one file format, or only the indicators bundled with the application.

## Market Data Source Adapters

Canonical flow:

```text
Twelve Data / Broker / CSV / Parquet / Future Provider
                     ↓
              Provider Adapter
                     ↓
          Normalize + Validate
                     ↓
        Canonical Market Dataset
                     ↓
     Dataset Version + Content Hash
                     ↓
 Replay / OOS / Forward / Research
```

Initial development candidate:
- Twelve Data may be used as a low-cost/free trial source for forward-engine development where the selected symbol and account tier permit it.
- It is not a permanent provider dependency.
- Commercial display/redistribution rights must be re-verified before public use.

A provider adapter should describe source/provider identity, instrument mapping, price type where known, timestamp/timezone semantics, interval, latency/completeness metadata, and licensing/usage metadata where relevant.

New providers should be addable without rewriting Replay, Execution, Experiment Passport, or Research Compute.

## User Market-Data Import

Backtest Lab should support user-supplied market datasets through a validated import boundary.

Candidate formats:
- CSV first;
- additional structured formats such as Parquet later when justified;
- provider/API adapters separately.

Import must validate schema, timestamps, ordering, duplicates, gaps, numeric values, OHLC invariants, timezone semantics, instrument metadata, and file/resource limits. Imported datasets receive immutable version identity/content hash before research use.

Never silently merge incompatible providers or price semantics into one canonical experiment dataset.

## Indicator Extensibility

Built-in indicators remain deterministic/versioned research components, but the architecture should allow additional indicators to be imported or installed later.

Conceptual boundary:

```text
Built-in Indicator
Imported Indicator Definition
Future Approved Plugin
          ↓
   Indicator Contract
          ↓
TimeBounded Market View
          ↓
Deterministic Output Series
          ↓
Chart Pane / Overlay + Research
```

Minimum indicator contract should eventually define:
- stable indicator ID and version;
- name/metadata;
- parameters and validation schema;
- required input series;
- warm-up requirement;
- output series/panes;
- deterministic calculation semantics;
- no-look-ahead/time-bounded input;
- compatibility/version metadata.

## Safety Boundary for External Indicators

“Import indicator” must **not** mean executing arbitrary untrusted Python/JavaScript in the main application process.

Preferred progression:
1. import safe declarative indicator definitions/configuration where possible;
2. support approved/versioned plugin packages only after a plugin security model exists;
3. arbitrary user code, if ever supported, requires a separately designed sandbox with CPU/memory/time/network/filesystem limits and is not authorized by this blueprint.

External indicators must not gain implicit access to secrets, other users' data, billing, filesystem, network, or future replay observations.

## Reproducibility

An experiment using imported data or an external indicator must record enough identity to reproduce the claim, including applicable:
- Dataset ID/version/content hash;
- data provider/source;
- Indicator ID/version/definition hash;
- indicator parameters;
- engine/calculator version;
- execution model version.

Changing an imported indicator definition after an experiment must create a new version rather than silently changing historical results.

## Design Principle

**Import at the boundary; normalize into canonical contracts; keep the research core provider-neutral.**

This lets Backtest Lab start cheaply while preserving the ability to add better data feeds and a larger indicator ecosystem later.


---

# 37. Open-Source Dependency Adoption Plan

> Status: planning direction only; no installation or implementation is authorized here.

Backtest Lab should use open source for commodity infrastructure while keeping replay/execution semantics, Lab Protocol, Experiment Passport, research integrity, and evidence methodology product-owned.

## Adoption rule

Adopt a dependency only when there is a demonstrated need and the project has checked commercial licensing/attribution, maintenance, security, performance cost, architectural fit, and replacement boundaries. A planned candidate is not automatically an installed dependency.

## Candidate map

| Capability | Candidate | Planning status |
|---|---|---|
| Financial market chart | TradingView Lightweight Charts | Existing foundation |
| Browser end-to-end QA | Playwright | Evaluate, likely useful for v1 hardening |
| Backend API | FastAPI | Planned candidate for Phase 19 |
| Relational product state | PostgreSQL | Planned candidate for Phase 20 |
| Research visualization | Apache ECharts | Evaluate for advanced research UI |
| Columnar/dataframe transforms | Polars | Evaluate when measured workload justifies |
| Embedded analytical SQL and CSV/Parquet analysis | DuckDB | Evaluate when dataset/research workload justifies |
| Scientific/statistical primitives | SciPy | Evaluate for advanced research engines |
| Statistical inference/models | statsmodels | Evaluate for advanced research engines |
| Object storage | S3-compatible boundary | Defer implementation/provider choice |
| Background jobs | Lightweight worker/job abstraction | Defer library choice until heavy jobs exist |
| Authentication | Mature OIDC/session solution | Defer exact choice to cloud auth phase |
| Observability | OpenTelemetry-compatible instrumentation | Evaluate for production hardening |
| Dependency/security checks | Ecosystem-native CI tooling | Evaluate before public production |

## Visualization boundary

Keep Lightweight Charts for market/replay. Evaluate ECharts for research-specific views such as Monte Carlo distributions, drawdown/recovery distributions, regime heatmaps, parameter surfaces, robustness views, and portfolio/correlation visualizations.

## Data and research compute boundary

Potential future flow:

```text
Versioned Dataset / CSV / Parquet
              ↓
       DuckDB / Polars
              ↓
Deterministic Backtest Lab Research Logic
              ↓
     SciPy / statsmodels primitives
              ↓
 Canonical Research Result + Provenance
              ↓
       ECharts / Reports
```

DuckDB/Polars are analytical candidates, not replacements for PostgreSQL application state.

Libraries may provide primitives and execution machinery, but Backtest Lab remains authoritative for Lab Protocol, Experiment Passport, no-look-ahead, execution assumptions, canonical Event/Trade Log, hypothesis-family definition, multiple-testing policy, Monte Carlo experiment definition, survival/risk-sizing, Strategy Destruction, and evidence interpretation.

## QA priority

Playwright is a strong E2E candidate for replay/navigation, drawings/indicators, order lifecycle, Fixed-RR restrictions, checklist ON/OFF, timeframe switching without temporal leakage, reset/recovery, entitlements, and Free affiliate versus paid ad-free UI.

E2E tests complement deterministic unit/domain tests; they do not replace them.

## Infrastructure restraint

Do not introduce ClickHouse, Redis, Kafka/RabbitMQ, Kubernetes, vector databases, microservices, arbitrary user-code execution, or a custom chart renderer by default. Adopt heavier infrastructure only after a measured workload or concrete requirement proves the simpler architecture insufficient.

## Dependency gate

Before adoption, verify the exact package and license, attribution/NOTICE obligations, current maintenance, security posture, version-lock strategy, material transitive dependencies, and the replacement boundary for critical components.

## Rollout principle

**Do not install an OSS dependency because it appears on this plan. Install it at the phase where it eliminates a real problem.**

Quality order remains:

**Security + Correctness → Lightweight → Efficient → Measured → Scalable.**

# 38. Phase 19 — Backend architecture planning handoff

This section extends the existing architecture owner. It is a planning deliverable, not a production API, schema, deployment or implementation authorization. Baseline audited: `15102e55ab31bc6ec5b7e98067af45d58126dc83`, clean main equal to origin and actual GitHub. Operational authorization remains only in [04_CURRENT_PHASE](../AI_CONTEXT/04_CURRENT_PHASE.md). Product semantics remain in the [frozen Method/Session handoff](TRADING_METHOD_SESSION_SPEC.md#frozen-trading-ux-specification-v1); security in [SECURITY_ARCHITECTURE](SECURITY_ARCHITECTURE.md), engineering in [AI_ENGINEERING_GUARDRAILS](AI_ENGINEERING_GUARDRAILS.md), infrastructure/commercial/provider decisions in [SCALING_DATA_AI_DECISIONS](SCALING_DATA_AI_DECISIONS.md). This is not another roadmap or Definition of Done.

## 38.1 Observed baseline and direction

React/Vite + Lightweight Charts is the active workspace; local account, drawing and news repositories own their existing independent storage. The explicit trading UX prototype is memory-only. `backend/api/main.py` exposes a standalone FastAPI 0.4.0 prototype with a module-level ReplayService and in-memory datasets/sessions. Its replay/trading engines have standalone tests; frontend production does not depend on these endpoints. Current handlers use coarse validation/error mapping and development CORS (including null origin), with no production identity, membership, durable idempotency or transactional persistence. These are observed integration gaps, not authorization to repair or deploy the prototype.

Retain React/Vite and chart/engine behavior. Earlier Next.js language is strategic, not a frontend migration prerequisite. Plan FastAPI as the existing backend direction, with thin transport handlers and framework-independent use cases/domain contracts. No dependency is installed or endorsed as production-ready here; exact versions, compatibility, licenses and security must be verified at implementation. PostgreSQL remains the Phase 20 direction; schema/migrations, auth/token mechanics and ownership implementation belong to separately authorized phases. Do not silently promote the old Python engine to canonical execution or port the JS simulator: later integration needs differential fixtures and a human-approved execution-authority decision if parity fails.

## 38.2 Modular monolith and ownership

Initial deployment direction is one application with explicit modules and replaceable ports, not microservices. Domain imports must not depend on transport, SQL, vendor clients or UI. Handlers → application use cases → pure domain rules → repository/provider ports; composition supplies infrastructure adapters. Proposed module names are conceptual, not folders created by this task.

| Boundary | Owns / input-output | Must not own |
| --- | --- | --- |
| Presentation | TIME + PRICE planner, chart, draft, ticket/review, displayed errors and read projections | Canonical authorization, persisted financial outcomes or server credentials |
| Product application / Product DB port | Authorized Method/Session lifecycle, command sequencing, revisions, durable confirmation receipts, journal references | Research algorithms, provider-specific identifiers as product identity |
| Market / temporal view | Dataset manifests/rights, immutable feed identity, revealed revision and bounded candle/news access | Future observations in interactive consumers, trading outcomes |
| Execution domain port | Validated intent, deterministic replay settlement, pending/fill/partial/exit events and account reconciliation | Drawing state, HTTP handlers, AI decisions; no dual writer with v1 |
| Research Compute | Read-only canonical evidence snapshot, passport and versioned calculator → result artifact | Interactive replay loop, direct account mutation, unrestricted tenant data |
| Billing / Entitlement | Internal capability decision from auditable commercial state | Payment-provider status directly authorizing execution/research |
| AI Gateway | Authorized minimal context, bounded tool requests, provider abstraction | Financial truth, automatic orders, secrets in prompts |
| Integration / CRM | Allowlisted business projections and idempotent outbound integration | Canonical research ledger or blocking replay on CRM availability |

Only boundaries are planned for Billing, AI and CRM; no payment, subscription, AI or Odoo implementation. Product state cannot depend on their availability. Workers may later run separately using the same domain and contracts when measured workloads justify it. No Redis/queue/microservice requirement is introduced.

## 38.3 Request and API contract

Proposed versioned resources under `/api/v1` are contracts to implement later, not available routes. Workspace-scoped Methods/Sessions, Session command/confirmation receipts, bounded event/position projections, dataset manifest/temporal views, Experiment Passports/trial lineage and research-job status form the minimal seams. Avoid CRUD endpoints that let clients insert arbitrary canonical fills or P&L. Existing unversioned prototype routes stay unchanged and are not aliases for this contract.

Command envelope: schemaVersion, requestId/idempotencyKey, sessionId, method definition reference/hash, expectedSessionRevision, expectedQuoteRevision, instrument/feed/profile references, workflow/type/side, decimal levels/quantity/risk inputs, condition observations and planId/revision when Planned. The server resolves authoritative ownership/Method/Session/quote/profile; client values are assertions, not trusted policy. Store the reviewed request snapshot separately from resulting execution events. API contract names and wire DTOs require a reviewed schema before implementation.

Future flow: authenticated principal → membership/resource check → bounded runtime DTO validation → current Session/Method/profile/temporal-view resolution → independent domain validation (including Protocol ON/OFF) → explicit confirmed command → atomic revision/idempotency check plus execution/evidence write → committed receipt/projection. Drawing placement/draft/preview and ticket opening never execute a command. Cancellation before confirmation submits nothing; pending cancellation is a distinct recorded abandonment. Protocol OFF never bypasses fixed risk/RR or categorical restrictions. Unknown observations stay NOT_ASSESSED; no implicit PASS.

Confirmation dedup key is scoped to verified workspace + Session + operation + request identity, with a canonical payload digest. Same identity/payload returns the existing receipt even after later Session revisions; a conflicting payload refuses. New commands compare expected revision under the same transactional/serialization boundary as side effects. Concurrent confirmations cannot both execute; crash/retry cannot duplicate a fill. Reject stale commands before mutation. Receipts reference committed Session/event revisions; clients reconcile by receipt/state rather than retrying with new identities after uncertain delivery. Review expiry and dedup retention must be specified before implementation; receipt identity for financial actions must remain recoverable through retries/restore.

Use explicit domain errors (INVALID_INPUT, PROTOCOL_BLOCKED, STALE_REVISION, IDEMPOTENCY_CONFLICT, RESOURCE_UNAVAILABLE) and correlation IDs. Planned mapping: malformed input 400, failed numeric/domain validation 422, revision/idempotency conflicts 409, absent identity 401, denied access 403 or consistent non-disclosing 404; pending heavy work 202 with status reference. These are target conventions, not changes to current 400/404 prototype behavior. Bound pagination, upload sizes, query windows and concurrency; define measured limits before production, never unrestricted history by default.

## 38.4 Persistence-facing identity and evidence contracts

| Record | Required identity/content and invariants |
| --- | --- |
| Method definition | Stable methodId, workspace owner, Free Style/Protocol type, immutable definition reference/hash, conditions/enforcement/risk/RR policy. Technical snapshots do not create a mandatory user-facing version editor. Material changes preserve prior meaning. |
| Session / feed segment | Stable sessionId, inherited Method definition, instrument/feed/dataset version, starting balance and risk basis, costs/execution profile, committed revision and revealed boundary. Feed continuation creates an explicit linked segment rather than rewriting prior evidence. |
| Confirmed intent / receipt | Request identity, canonical digest, actual condition observations, reviewed quote/plan revisions, validation policy and committed outcome references. Client confirmation is not itself proof of fill. |
| Canonical event / trade log | Stable eventId, owner/session, monotonic per-Session sequence, event schema, engine/policy version, market time plus recorded UTC time, causal request/position/exit references, source, actual quantity/costs and resulting revision. Partial exit stays distinct from completed position. |
| Experiment Passport | Stable experimentId + immutable passport revision/content digest; dataset identity/version/hash, Method definition hash, protocol definition hash where applicable, engine/calculator version, execution assumptions/profile, instrument/feed/period, regime definition and RNG algorithm/seed when used, input snapshot/log boundary and trial/family references. Missing inputs prevent reproducibility certification. |
| Trial / strategy lineage | Append-only trialId, parent/family/experiment references, definition hashes, exploratory/confirmatory declaration and recorded reason/time; abandoned/failed/excluded attempts remain discoverable. Lineage does not automatically trigger multiple-testing correction. |
| Research result | Job/passport/input-snapshot identity, calculator/numeric policy/version, parameters/seed, artifact hash and diagnostics. A changed input/calculator produces a new result identity, not overwritten evidence. |

Append-only applies to canonical research/financial evidence: corrections append a linked superseding/correction event and projections retain prior meaning. Mutable notes/preferences remain separate. This does not forbid legally required erasure: implement privacy/retention policy and controlled auditable deletion/redaction at the appropriate phase; do not promise perpetual private-data retention. Event ledger is separate from sanitized operational logs. Projections must be rebuildable/reconciled; cache and RAM are not canonical truth. Atomic event/receipt/revision persistence is a Phase 20 design requirement, not an implemented transaction.

Hash contract proposal: SHA-256 over UTF-8 canonical JSON with schemaVersion; sorted object keys, preserved array order, explicit null vs absent semantics, UTC timestamps and normalized finite decimal strings (no NaN/Infinity or negative-zero ambiguity). Identity hash excludes mutable display labels, secrets and operational recorded times; evidence artifact digest may include recorded times. Cross-language golden vectors and exact decimal/rounding policies must be approved before any producer adopts this format. Content hash proves byte identity, not authenticity or compliance. Do not invent hashes, initial risk, cost metadata or timestamps for legacy records; preserve originals and label unavailable provenance.

## 38.5 Research job and temporal boundary

Proposed job input: verified owner, jobId/idempotency identity, passport/input artifact hashes, calculator version, parameters, optional RNG metadata and resource policy. State transitions: QUEUED → RUNNING → SUCCEEDED / FAILED / CANCELLED; CANCEL_REQUESTED is nonterminal, timeout is a classified failure. Progress is descriptive, never a research result. Durable status/result publication, bounded attempts, deadlines/concurrency/memory budgets and cooperative cancellation belong to the later adapter. At-least-once retries may recompute but cannot publish duplicate canonical results. Recheck ownership on submission/status/download and worker artifact resolution; results publish atomically only against matching snapshot identity.

Interactive replay, indicator, news and execution consumers receive only TimeBoundedView(revision, revealedTime), never an unrestricted dataset. Session settlement/event append and replay acknowledgement must describe the same committed revision. Research jobs may access a separately authorized completed evidence interval or retrospective price path; those results must remain labeled and cannot leak into a still-running strict replay view. Test physically truncated futures, not only UI-hidden fields. Heavy compute never runs in synchronous chart/order handling. No Monte Carlo/advanced analytics/worker runtime is built here.

## 38.6 Trust, adoption and acceptance gates

Browser storage and imported data are untrusted. Validate schema, numeric units, finite bounds, content size/hash and temporal availability at each boundary. Never accept principal, membership, entitlement or source claims from a hidden button/client-supplied workspace ID. Until production identity/membership exists, new private-resource paths must remain disabled or test-only with explicit injected principals, not publicly exposed without authorization. CORS is not authorization; development null-origin settings are not a deployment policy. Credentials belong to server secrets configuration, never frontend bundles, passports or logs. Token/session mechanics, CSRF policy and public launch checks remain with the security owner and later identity scope.

Implementation preparation order (within existing phase owners, no second roadmap): approve DTOs/golden fixtures and ports; separately authorize a narrow backend foundation; separately authorize Phase 20 persistence/migrations/restore; follow identity/workspace phases before private cloud exposure; then authorize one guarded production adapter with rollback and differential evidence. No automatic frontend rewrite, local storage upload/migration or Python engine switch. Existing `/` and prototype entry remain isolated until a reviewed cutover; never run two canonical execution writers. Exact limits, hash vectors, privacy retention, runtime engine parity and deployment/auth choices are implementation prerequisites, not hidden product decisions made by this document. Material contract conflicts require human resolution.

Future implementation acceptance matrix:

| Gate | Required proof before integration/release |
| --- | --- |
| Domain parity | Existing regression plus cross-runtime fixtures for risk/decimal rounding, order relations, pending/fill/partial/exit, costs and ambiguity; discrepancies block cutover |
| Confirmation/recovery | Same/different payload retries, concurrent confirmations, stale revisions, crash between commit/ack, restart/restore, receipt recovery; exactly one financial effect |
| Protocol/evidence | Quick/Market/locked fields/manual intervention refused even direct API; ON missing/FAIL blocks, OFF preserves observations; no fabricated compliance |
| Temporal integrity | Physical-future truncation invariance; quote/replay/settlement revisions consistent; research artifacts cannot reveal future data to strict replay |
| Ownership/security | Cross-tenant reads/writes/job artifacts/exports denied, bounded requests, sanitized errors/logs, no client secrets; existing security launch gate applies |
| Persistence/provenance | Append/correction lineage, immutable snapshots/hash vectors, missing legacy metadata retained, replayable projections and account reconciliation, backup/restore identity equality |
| Jobs/boundaries | Timeout/cancel/retry/resource limits and duplicate result publication tests; provider/CRM/AI outages cannot alter trading truth |
| Compatibility | Existing account/drawing/news storage untouched, full frontend regression/build/lint/release/bundle, future backend tests and actual browser cutover smoke |

Planning closure: only documentation/context and bundle allowlist change. Existing repository and AI-bundle controls validate authority/link inclusion; regenerate and verify the disposable bundle. Browser verification is exempt with reason: no runtime, UI, API, build entry, dependency, database or engine changes. This checkpoint closes Phase 19 planning only; Phase 19 implementation and Phase 20 remain unauthorized until explicitly requested by the human.

## 38.7 Authorized foundation checkpoint — implementation evidence

The human subsequently authorized only framework-independent contracts, pure validation, canonical serialization/hash fixtures and deterministic tests from clean verified `aa3b982728b3e7f36278bbbf8a5c6f24e6b410a6`. `backend/contracts/` now implements this narrow seam using Python standard library; no existing service/engine imports or integration. This is a completed foundation checkpoint, not all Phase 19/backend completion. Sections above retain their future integration meaning.

Frozen DTOs cover Method policy/condition observations, resolved Session/quote assertions, Command, ReviewedRequest, ConfirmedRequest, receipt comparison, event identity, Passport revision/identity, trial lineage, research-job input/state and temporal observations. Mutable lists are refused at tuple boundaries; exact IDs/categories/revisions/hash formats and aware timestamps are validated. Decimal inputs accept exact strings/ints/Decimal and refuse binary floats/bools, nonfinite values and unsupported forms. Pure command validation compares supplied context identity/revisions, market/pending relations, stop/target sides and Protocol Planned/pending/risk/RR/ON checks. OFF preserves FAIL/NOT_ASSESSED and still refuses categorical actions. RR comparison uses exact rational arithmetic independent of Decimal context. Context is an asserted future-server input, not authenticated principal evidence.

BTL-CJSON-1 is a project-local format, not RFC 8785. Root schemaVersion is exactly integer 1; keys sort by Unicode code point, arrays retain order, null remains explicit and absent remains absent. Strings are Unicode scalar sequences (no normalization); UTF-8 compact JSON escapes controls, quote and backslash. Integers are limited to safe 53-bit range; Decimal becomes a normalized exact string with no exponent/trailing fractional zero/negative zero; aware datetime becomes UTC ISO text with six fractional digits and Z. Ordinary strings retain their meaning: DTO schema distinguishes decimal/time fields, so generic numeric-looking strings are not coerced. Float, unsupported object types, naive time, excessive depth/collections/text/decimal exponent and unsupported root versions refuse. Identity builders include only defined DTO identity content; reviewed/recorded wall time is separate from command/passport identity. SHA-256 is content identity, never authorization, signature or invented compliance.

Six committed golden fixtures in `backend/tests/fixtures/contract_hash_vectors.json` cover decimal/time/Unicode, exponent expansion, absent field, Unicode-key sorting, integer-looking-key sorting and microseconds. Python tests compare exact expected bytes/digests across repeated runs. `backend/tests/verify_contract_vectors.mjs` independently renders the fixture subset with Node standard library and explicit sorted-key serialization, avoiding JS integer-key enumeration differences. Python contract tests also cover field-order invariance, array sensitivity, null vs absent, malformed numeric/category/ID/schema, immutability, stale revisions, Protocol bypass/refusal, confirmed-time ordering, receipt scope/conflict, Passport/RNG/job identity/deadlines/state and event revealed-time checks. Temporal view equals a physically truncated prefix and ignores changed future values; this proves only the new availability-view primitive, not a new engine or strict-delivery integration.

Validation: all 63 backend tests (53 retained + 10 new test methods with parameterized assertions) pass using existing venv; bundled Python independently passes the 10 foundation tests. Six Node golden vectors pass three repeated runs. Full registered frontend regression, lint/build/release pass. Final repository/bundle regeneration/verification and diff/Git gates close the checkpoint. No tests weakened, dependencies added, files deleted, routes/frontend/engine/storage/data changed. Browser exempt per this checkpoint's explicit authorization: contracts are unwired and no browser/product path changes. This is not a docs-only code change; no browser integration exists to exercise.

Limitations: immutable evidence DTOs do not implement append-only persistence, ancestry graph enforcement, durable receipts/concurrency/crash recovery, server identity/membership, numeric tick/lot/budget profiles, fill/settlement/P&L, SQL migrations, hash authenticity or workers. Protocol quantity-derived budget validation needs a separately authorized full instrument/risk-basis adapter; positive quantity alone is not proof of risk compliance. Job transitions describe policy only, not scheduled work; structural input bounds are not measured production quotas. New DTO schema/hash adoption remains isolated; external producers must pass these vectors and reviewed wire-boundary rules before integration. Further Phase 19 application/API scope must be defined and explicitly authorized; no Phase 20/persistence/auth/frontend cutover follows automatically.

Bundle boundary: the existing repository gate excludes backend source/fixtures from the frontend-focused disposable bundle. Attempted narrow inclusion was rejected and reverted; no test/allowlist boundary was weakened. The regenerated bundle includes this authoritative evidence and context; run backend validation in master. A future backend-specific bundle responsibility requires separately reviewed scope, not bypassing the existing gate here.

## 38.8 Application/API layer preparation — planning only

Hard baseline gate passed at `163558e07e034fabf43ae62c51c2947e6aa0fd3a`: local/origin/actual GitHub main equal, working tree clean, ahead/behind 0/0. This human-authorized task changes existing documentation/context only. The following is exactly one proposed implementation checkpoint, not implementation authorization or completion of Phase 19. Operational status remains in [04_CURRENT_PHASE](../AI_CONTEXT/04_CURRENT_PHASE.md).

### Audit and bounded objective

Foundation audit: frozen Command/ReviewedRequest/ConfirmedRequest, SessionContext, Observation, Receipt and EvidenceEvent can support an intent intake seam; pure validation/hash/retry helpers are already available. They do not resolve trusted ownership, store server-issued review, serialize concurrent confirmation, enforce durable dedup or write an event log. Passport/Lineage/ResearchJob primitives are independently testable and need no coupling to order intake. Existing FastAPI handlers call module-global ReplayService; its memory maps and Python engines perform actual standalone replay/trading simulation. Reusing those handlers/service for confirmation would violate the execution protection. Do not import or wrap them. Historical trading separation report is evidence of planning-object/executed-position independence, not a new runtime integration requirement.

Proposed objective: prove **Transport function → Application intent review/confirmation orchestration → immutable foundation validation → abstract atomic workflow port**, using test-only memory doubles. A confirmed result means **nonexecuting intent intake recorded in a disposable test scope**, never order submitted, pending order, position, fill, account mutation, P&L or production evidence. No execution port is needed for this checkpoint; introducing one adds no proof and remains deferred. No live HTTP endpoint, ASGI application, FastAPI router or browser client is needed.

### Responsibility and minimal ports

| Layer / category | Decision for next checkpoint |
| --- | --- |
| Foundation contracts/domain | Reuse unchanged DTO validation, canonical command hash, exact Protocol/revision rules and retry comparison. Do not copy business rules into handlers or orchestration. Profile/tick/lot/budget limitations stay explicit. |
| Application | Resolve test-injected trusted scope, access authoritative SessionContext through a scoped port, create/store reviewed immutable snapshot, enforce review identity, revalidate a new confirmation, build nonexecuting receipt/event and coordinate atomic publication/dedup. Never settle trades. |
| Transport/API | Two unmounted pure handler functions for strict JSON-to-DTO and safe response/error projection. Does not authenticate, resolve Method policy from payload, implement domain rules or expose a network route. |
| WorkflowScopePort — MUST | `run(scope, session_id, operation)` invokes operation with a scoped unit; SessionContext read, `find_review(request_id)`, `put_review(reviewed)`, `find_receipt(request_id)`, `commit_intake(confirmed, receipt, event)` share one serialization/atomic boundary. The conceptual unit also exposes next evidence sequence. Commit checks expected current context identity/revisions and succeeds all-or-none. No storage adapter ships outside tests. |
| ClockPort — MUST | `now_utc()` returns aware UTC time; fixed fake drives tests. Wall time is not replay time. Confirm-time ordering uses foundation validation. |
| IdSourcePort — MUST | `next_id(kind, scope, session_id, request_id)` yields validated receipt/event IDs; deterministic fake supplies reproducible sequences. Production randomness/collision/durability policy is deferred. |
| Separate Session/read repository | Evaluated but not a separate interface: scoped unit supplies SessionContext so read and commit cannot race across unrelated ports. Session lifecycle/creation/advancement remain out of scope. |
| Separate request/dedup/evidence stores | Evaluated and combined in WorkflowScopePort to avoid independent writes that publish receipt without event or vice versa. Port contract describes atomicity; memory fake demonstrates only in-process behavior, not durable guarantees. |
| Passport/lineage store and research-job dispatcher | DEFER. Intake must not create an experiment/trial, mutate lineage, submit research or schedule a worker. Existing pure job/passport validation remains unchanged. |
| Persistence / execution | DEFER all implementations. Future persistence adapter must honor the port contract under concurrency/crash/restart; future execution adapter requires distinct authorization and parity evidence. |

TrustedScope is a small immutable application input containing verified workspace identifier and server-side actor reference. It can be supplied only by explicit composition/test fixture, never deserialized from JSON/header/path into trusted identity. Constructor validation does not prove authorization; future identity/membership layer must verify it before injection. Request workspace assertion must match scope; Session resolution is scoped and returns RESOURCE_UNAVAILABLE for absent/wrong-scope records. Missing scope refuses before accessing state. Tests try cross-workspace request/review/receipt access. No default/demo principal, trust-on-first-request, membership provider or login implementation is proposed. Such handlers cannot be publicly mounted until future auth/authorization gates are met.

### Use cases, revisions and confirmation semantics

1. `review_command(scope, command)`: check scope/request identity; inside WorkflowScopePort obtain current SessionContext, call foundation `validate_command`, compute canonical command digest, create ReviewedRequest using injected clock. Store once by verified workspace + Session + requestId. Same identity/snapshot while current revisions remain valid returns original review including original reviewedAt; changed context makes an unconfirmed review retry stale, and different payload under the same identity refuses IDEMPOTENCY_CONFLICT. No receipt/event/execution yet. Read/validation failure stores nothing. Editing uses a new requestId and fresh review; prior intent is not overwritten.
2. `confirm_review(scope, session_id, request_id, payload_hash, expected_session_revision, expected_quote_revision)`: the caller supplies identifiers/assertions, not a full replacement command, Method, clock, checklist or outcome. Fetch the stored server-issued review inside the scoped unit; require hash/assertions match it. Find existing receipt before current-state freshness check: same identity/hash returns exact prior receipt, even if Session/quote later advances; different hash conflicts. New confirmation requires current Session/quote/profile/Method identity equal to reviewed snapshot and foundation `validate_confirmation`/`validate_command` success. Explicit command/revision identity is mandatory; unknown review refuses without creating one. Build one receipt and one CONFIRMED intent event; atomic commit prevents double logical publication. API repeat may report duplicate=true outside receipt identity; it must not generate new IDs/time/evidence.
3. Receipt/event fields are foundation DTOs wrapped in an application response labeled `INTENT_RECORDED_NOT_EXECUTED`, `source=PROTOTYPE`, `executionPerformed=false`, `durable=false`. Receipt committed_revision and event session_revision reference the resolved input Session revision; **do not increment or write Session/replay/account revisions**. Event sequence belongs only to the fake scoped intake evidence stream. `engine_version=NO_EXECUTION` is an explicit nonexecution marker, not a claim to invoke/version a trading engine. market_time is the revealed boundary; recorded_at comes from clock. Event payload_hash references the stored confirmed command; reviewed/confirmed snapshots and condition evidence remain linked in the unit. Do not emit FILL/EXIT/PENDING, fabricate compliance or claim canonical production execution source.

Clock/ID failures and commit failure must leave no partial receipt/event. The unit stages changes and publishes atomically only on success; concurrency tests use a serialized fake to prove one logical receipt/event in that fake scope. ID counters may consume a value on aborted attempts but never publish partial evidence; deterministic replay of a successful fixed-fixture run yields identical outputs. Process restart loses fake state; no durable or exactly-once financial effect claim is permitted. A future transactional implementation must test crash-after-commit-before-ack separately.

Review invalidation here is revision/identity-based. No arbitrary expiry, TTL, quota or order execution policy is introduced; production review expiry/dedup retention remains a separately reviewed prerequisite. Under Protocol, OFF skips checklist blocking only; missing observations remain NOT_ASSESSED, never added PASS. Quantity positivity is the current foundation check, not complete risk-sizing certification. These limitations must appear in responses/documentation so acceptance of intent cannot be confused with executable trade readiness.

### Minimum transport/API surface (unmounted)

Only `handle_review(json_bytes, trusted_scope, application)` and `handle_confirm(json_bytes, trusted_scope, application)` are proposed for the next checkpoint. Return frozen `ApiResponse(status, body_json_bytes)` with immutable UTF-8 JSON response bytes; no route registration/server launch. Future route names, if subsequently authorized, could be `POST /api/v1/sessions/{id}/command-reviews` and `POST /api/v1/sessions/{id}/command-confirmations`; they are unavailable and not part of the implementation checkpoint. No GET/catalog/job/export/CRUD API is proposed.

Review body: schemaVersion=1 and explicit Command wire fields mapped to the existing snake_case DTO (workspaceId, sessionId, requestId, methodId/methodHash, instrumentId/feedId/profileHash, sessionRevision/quoteRevision, workflow/side/orderType, entry/quantity/riskPercent, sl/tp, planId/planRevision, observations array of conditionId/outcome). Decimal values use exact strings; nullable optional fields map to explicit null defaults per Command identity_payload; missing required fields refuse. Review identity bytes always use the existing Command builder, not raw JSON. Confirm body: schemaVersion=1, sessionId, requestId, payloadHash, sessionRevision, quoteRevision, confirm=true (strict boolean). Reject missing/false confirm and supplied replacement levels/policies/scope/receipt/evidence. No user clock or actor fields accepted.

Strict transport decoder rejects duplicate object keys, unexpected fields, malformed UTF-8/JSON, wrong root/container types, nonfinite numeric constants, binary-float decimal values and bool-as-revision. Explicit bounded fixture limit: 64 KiB JSON body and at most 32 nested containers before DTO construction; these are seam safety bounds, not measured production quotas. Observation DTO validation and domain rules remain in foundation. Successful review returns 200 with normalized requestId, command hash, immutable snapshot, reviewedAt and REVIEWED_NOT_EXECUTED/executionPerformed=false/durable=false labels; successful confirmation/retry returns 200 with original receipt, event references and duplicate flag plus mandatory nonexecution labels. Neither returns 201/202 suggesting a created trade or scheduled work.

Planned safe error mapping: malformed wire input/unsupported schema/missing explicit confirmation → 400; invalid domain numeric/geometry/Protocol → 422; STALE_REVISION/IDEMPOTENCY_CONFLICT → 409; absent or mismatched trusted scope → 403; inaccessible/missing Session/review → consistent 404; unexpected port failure → sanitized 503, no internal exception/secret payload. Domain codes and field references are preserved where safe; never expose another workspace's identity. This mapping does not change current FastAPI prototype handlers. No authentication endpoint/token code is included.

### Exact proposed implementation boundary and MUST / MUST NOT

Add only `backend/application/__init__.py`, `ports.py`, `models.py`, `service.py`, `transport.py`; add `backend/tests/test_application.py`, `test_application_transport.py`, `application_fakes.py`. Test doubles (scoped units, fixed clock, deterministic IDs) exist only under backend/tests. Use standard library + existing contracts, no dependency changes. Existing docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md and relevant AI_CONTEXT owners may record evidence/status; existing ROADMAP may link the checkpoint. These filenames are the reviewed proposed allowlist, not permission to create them now.

MUST: reuse unchanged contracts; explicit trusted-scope injection; two described use cases; strict wire projection; scoped atomic review/receipt/evidence seam; exactly one nonexecuting logical outcome in serialized fake scope; same-payload repeat/changed-payload conflict semantics; new-command revision/Protocol validation; deterministic clock/ID fixtures and honest response labels; no live app composition. Prefer no additional ports/classes beyond what these tests require.

MUST NOT touch backend/api, backend/services, backend/engine, backend/contracts, existing backend tests/fixtures, frontend (source/tests/scripts/manifests/lock), historical datasets/data, drawings/indicators/news/account/replay, requirements/dependencies, database/schema/migrations, infrastructure/auth/providers/queue/workers, execution adapters or Phase 20+. No repository-wide refactor, production in-memory adapter, alternative trading engine or reinterpretation of frozen Method semantics. If existing contract changes are genuinely required, STOP and report the exact gap; this allowlist does not authorize them. Persistence is only an abstract future port responsibility; no SQL/ORM/SQLite/Redis/file store or durable queue.

### Acceptance test plan and stop gates

| Required case | Proof in the proposed checkpoint |
| --- | --- |
| Valid / malformed intake | Free Quick and Planned plus Protocol pending all-PASS review; direct malformed DTO/wire input refuses with no receipt/event. Wrong/unknown fields, duplicate JSON keys, bounds and confirm=false refuse. |
| Identity / trust | Missing scope, forged workspace/Method/profile, cross-scope Session/review/receipt refuse before mutation; JSON cannot inject TrustedScope. |
| Revisions / confirmation | Stale Session or quote at review/first confirmation, altered expected revision/hash, absent review and Method/profile change refuse; receipt retry after context advancement still returns original. |
| Protocol non-bypass | Direct transport/application Quick/Market/risk/RR/checklist violations fail. ON missing/FAIL blocks; OFF preserves FAIL/NOT_ASSESSED and categorical limits. |
| Duplicate / atomicity | Repeated and concurrent same-snapshot confirmations yield one logical receipt/event; changed payload conflicts; injected commit/clock/ID faults publish neither receipt nor event. Review idempotence retains original timestamp. |
| Deterministic evidence | Fixed-fixture repeated runs yield identical IDs/hash/snapshot/time/receipt/event; replay Session revision never advances; event time <= revealed bound; no fill/position/P&L created. |
| Temporal protection | Full vs physically truncated future fixtures resolve the same Session/review/confirmation result; changing future values cannot alter intake. No raw dataset/engine imports enter the application. |
| No execution/persistence | Import/dependency boundary tests reject engine/service/API/frontend/DB/provider imports; fake spy/fixtures confirm zero execution calls; all tests run without storage/server/network/auth/worker. |
| Regressions | All existing/new backend tests, full registered frontend regression/lint/build/release, unchanged Python/Node golden fixtures and repository/bundle gates pass. No weakened assertions or altered legacy behavior. |

This planning checkpoint uses applicable repository/AI-bundle controls and regenerated/verified bundle. Browser exemption: documentation/context only, no runtime/product path changed. Next implementation would also need a separately recorded exemption only while handlers remain unmounted and no browser path changes. Backend code stays excluded from the existing frontend-focused bundle; this owner carries handoff knowledge, not a second architecture system.

STOP after the current planning commit/push/equality checkpoint. Proposed implementation requires new explicit human authorization of this allowlist/MUST/test scope. Stop its future execution if a foundation modification, real execution, authenticated/public endpoint, persistence or material product decision is needed. Phase 19 as a whole remains incomplete; no Phase 20 start or automatic continuation.

## 38.9 Application/API intake — implementation evidence

Human authorization to complete remaining Phase 19 from verified clean `dc7b4512a1f5fd2931770efd4aeeec373de7d6ac` supersedes the implementation-not-authorized and intermediate STOP statements in historical Section 38.8. Its exact architectural allowlist/MUST/MUST NOT remains binding. The sole operational pointer is AI_CONTEXT/04_CURRENT_PHASE.md.

Implemented exactly five application files: `backend/application/{__init__,models,ports,service,transport}.py`; three new test files: `backend/tests/{application_fakes,test_application,test_application_transport}.py`. Existing foundation/contracts, API/services/engines, frontend, dependencies, data and existing tests remain unchanged. No files deleted.

IntakeApplication composes WorkflowScopePort, ClockPort and IdSourcePort. Its immutable TrustedScope must be injected by trusted composition; validating its constructor does not authenticate a user. Scoped review preserves the original server-issued immutable snapshot/hash/time. Confirmation accepts only stored-review identifiers/hash/revisions. New confirmation revalidates Protocol and context; same confirmed identity returns the original receipt/event/time even after context advances, without new IDs or events. Changed hash/revisions refuse. The scoped unit combines context/read/review/dedup/evidence publication in one atomic contract. find_receipt returns the original immutable IntakeResult bundle so replay cannot manufacture event details.

Two pure schemaVersion=1 handlers perform strict bounded UTF-8/JSON/DTO mapping and safe typed errors. Duplicate keys, unknown fields, float decimals, nonfinite numbers, bool revisions, invalid Unicode scalars, oversized/deep input and replacement confirmation commands refuse. Errors distinguish malformed/domain/stale/conflict/scope/missing/unavailable without exposing private exception payloads. These functions are **unmounted**: no FastAPI routes, server, frontend binding or live adapter.

Successful responses explicitly state NOT_EXECUTED, executionPerformed=false, durable=false, PROTOTYPE and no instrument-budget certification. Receipt/event refer to input Session revision, never increment it. CONFIRMED intent event uses NO_EXECUTION, revealed market boundary and injected wall time. No trade, fill, position, account mutation, Passport, trial or research job is created.

### Validation and limits

- Existing backend full discovery: **77 tests PASS** (53 legacy, 10 foundation, 14 new application/transport methods with multiple cases).
- Independent Node golden canonical bytes/hash: **6 vectors PASS across 3 repeated runs**; Python golden fixtures unchanged.
- New tests cover fixed-fixture repeatability, Protocol ON/OFF and bypass refusals, stale identity/revisions, forged scope/profile/Method, immutable review retry, malformed wire, exact prior outcome retry after advancement, 32 concurrent confirmations plus conflicting confirmations, clock/ID/staged-commit failures, commit-context race rollback, full/truncated/changed-future equivalence and import firewall.
- Full registered frontend regression, lint, production build and release distribution audit: **PASS**. Existing browser product paths/build output remain unchanged.
- Repository/context and AI bundle generation/verification are mandatory checkpoint gates. Existing frontend-focused bundle intentionally excludes backend source; these authority files preserve the backend handoff. No bundle allowlist broadened.
- Browser validation **exempt**, per explicit human instruction: all new code is unmounted and no browser-reachable path changed. No browser validation is claimed for backend functions.

Test-only serialized memory doubles demonstrate in-process atomic publication and one logical outcome in that fake. They do not establish durable transactions, restart recovery, financial exactly-once behavior or production workspace authorization. Only abstract ports ship in application; adapters exist solely in tests. Durable schema/store/migrations/crash/restore belong to Phase 20; identity/membership to Phase 21/22; production mounting requires those security prerequisites. No new dependency or infrastructure. Quantity positivity is not complete instrument risk sizing. Production tracing, quotas, review expiry/dedup retention and deployed load guarantees require later adapter/security review.

Continue automatically to the authorized Phase 19 completion audit after normal checkpoint Git equality/clean-tree verification. Do not start Phase 20.

## 38.10 Phase 19 completion audit

Scope comes from the existing ROADMAP Phase 19, frozen Method/Session handoff, Sections 38.1–38.8 and the human's whole-Phase-19 execution authorization. Starting gate: `dc7b4512a1f5fd2931770efd4aeeec373de7d6ac`, clean main, local/origin/actual GitHub equal, 0/0. Intake checkpoint `71c2abffc7e77060b49ebd68c66187d55ae78e47` was committed/pushed and independently verified equal/clean 0/0 before this audit. The historical planning-only statements earlier in Section 38 describe those earlier checkpoints; they do not negate subsequent implementation evidence.

The roadmap asks for production-oriented **architecture and persistence-facing contracts**. It does not authorize a deployed production trading backend. The implemented seam is framework-independent, validated and disconnected. The production product still uses the unchanged frontend v1; neither the existing standalone FastAPI prototype nor the new handlers is certified for public deployment. No remaining Phase 19 MUST requires a persistence/auth/worker adapter under this authority.

### Requirements disposition

| Phase 19 requirement / authority | Classification | Evidence and exact boundary |
| --- | --- | --- |
| Modular-monolith-first backend/service/API ownership — ROADMAP 19; 38.2 | IMPLEMENTED | contracts → application → abstract ports, separate transport; application import firewall tested. No microservices or extra dependency. |
| Product DB, Research Compute, Billing/Entitlement, AI Gateway, Integration/CRM separability — 38.2 | VERIFIED | Existing ownership table specifies inputs/outputs/firewalls; Product port is scoped, compute input is immutable. Billing/AI/CRM intentionally architectural boundaries only, as explicitly stated in 38.2. |
| Runtime validation and exact numeric/revision/identity rules — 38.3, 38.7, 38.8 | IMPLEMENTED | Existing immutable DTOs/validators and strict decoder; no duplicate Protocol business rules in transport. |
| Review Request and Confirmation Intake — 38.8 | IMPLEMENTED | IntakeApplication validates resolved context, stores immutable review and records nonexecuting intent; 14 new methods cover direct/application and transport journeys. |
| WorkflowScopePort / ClockPort / IdSourcePort — 38.8 | IMPLEMENTED | Three abstract composition ports; WorkflowUnit combines review/context/receipt/event transaction contract; deterministic test-only doubles. |
| Trusted identity and resource boundary — 38.6, 38.8 | IMPLEMENTED | TrustedScope must be composition-injected; missing scope fails before state access, payload workspace must match, wrong-scope Session/review refuses. Constructor is not authentication. |
| Versioned API DTO surface and error taxonomy — 38.3, 38.8 | IMPLEMENTED | schemaVersion=1 pure unmounted handlers; safe 400/422/409/403/404/503 projection. No routes/201/202/execution claim. |
| Bounded hostile wire input — 38.6, 38.8 | VERIFIED | Duplicate/unknown keys, UTF-8/Unicode errors, depth/size/types/float/nonfinite/bool revision/replacement confirmation refuse; error tests expose no private failure payload. |
| Protocol ON/OFF, categorical and locked risk/RR boundaries — frozen handoff; 38.8 | VERIFIED | Existing pure validators enforce rules; ON missing/FAIL blocks; OFF retains FAIL/NOT_ASSESSED and cannot bypass Quick/Market/risk/RR restrictions. No fabricated compliance. |
| Stale Session/quote and Method/profile identity — 38.3, 38.8 | VERIFIED | Review and first confirmation validate current context; altered identity/assertions refuse; fake commit-time race rolls back. |
| Retry/dedup, concurrent outcome and atomic intent — 38.8 | VERIFIED | Exact prior outcome after advancement; conflicting hash refuses; 32 concurrent calls yield one outcome in serialized fake; clock/IDs/staged-commit failures publish neither receipt nor event. This is not financial exactly-once or crash durability. |
| Deterministic evidence/nonexecution labels — 38.8 | IMPLEMENTED | Immutable Receipt/EvidenceEvent, linked canonical digest, fixed-clock/ID equality, revealed market time, PROTOTYPE/CONFIRMED/NO_EXECUTION. Input Session/replay/account revision unchanged. |
| Canonical event/trade-log architecture — ROADMAP 19; 38.4 | VERIFIED | Existing schema table formalizes event identity, causal references, source, quantity/costs, append/corrections and partial-exit distinction. DTO demonstrates intent identity only; it does not pretend to be a complete fill/position ledger. Existing v1 ledger unchanged. |
| Passport identity/provenance and immutable content hashes — ROADMAP 19; 38.4, 38.7 | IMPLEMENTED | Existing Passport DTO/versioned identity builder carries dataset/Method/profile/input/period/calculator/engine/trial plus optional protocol/regime/RNG; validation and canonical fixtures tested. Missing provenance is not invented or certified. |
| Trial/strategy lineage and exploratory vs confirmatory semantics — ROADMAP 19; 38.4, 38.7 | VERIFIED | Immutable LineageEntry and existing append-only/correction contract define parent/family/disposition/reason/time meaning; abandoned/failed/excluded records retained by future store. No automatic multiple-testing correction claim. |
| Canonical serialization / cross-language identity — 38.4, 38.7 | VERIFIED | BTL-CJSON-1/SHA-256: six immutable Python/Node golden vectors, three independent repeated Node runs. Exact decimal/time/Unicode/null/absent/sorted-key semantics; hash is neither authenticity nor authorization. |
| Research-job input/state/identity/deadline boundary — ROADMAP 19; 38.5, 38.7 | IMPLEMENTED | ResearchJobInput/ResearchJobState, job_transition and validate_job_input; strict states, matching workspace/passport/input/calculator/RNG and deadline. No job submission or result fabrication. |
| Heavy-compute separation — 38.2, 38.5, 38.8 | VERIFIED | No research/calculator/worker call on intake path. Research snapshot contracts are distinct from interactive replay. |
| No look-ahead — 38.5, 38.8 | VERIFIED | Foundation and application tests compare full vs physically truncated and altered futures; event time bounded by revealed context. Existing frontend market/news/replay causality regression retained. This proves current tested seam, not a future worker. |
| Execution firewall and canonical authority — 38.1, 38.6, 38.8 | VERIFIED | No legacy API/service/engine imports; no frontend wiring, account mutation, fill path, execution adapter or dual writer. Existing regression and source diff verify preservation. |
| Existing app/storage/news/drawing/indicator compatibility — 38.6 | VERIFIED | Full registered frontend regression/lint/build/release; no frontend/data/dependency/source modifications in this journey. |
| Single authority, context/handoff and Git workflow — AI_CONTEXT; 38.6 | VERIFIED | Existing owners updated, no new roadmap or documentation authority; repository negative drift tests and bundle controls pass. Backend intentionally remains outside frontend-focused AI bundle; evidence owner is included. |
| Browser verification policy — human authorization Section 10 | VERIFIED | Explicit exemption: new backend code is unmounted and no browser-reachable path changes; completion audit is docs-only. No claimed browser validation of handlers. |
| Durable persistence/schema/migrations/indexing/backup/restore — ROADMAP 20; 38.4, 38.6, 38.8 | DEFERRED BY DESIGN | Phase 20 explicitly persists Phase 19 provenance/transactions. Abstract port guarantees and test fake are prepared, not production storage. Crash-after-commit/ack, restart dedup, receipt recovery, durable append-only lineage and projection reconciliation require that adapter. |
| Auth/token/session lifecycle, membership and public private-resource endpoints — ROADMAP 21/22; 38.6, 38.8 | DEFERRED BY DESIGN | No auth product, default principal or public mount. Future identity/membership must verify scope; development prototype CORS remains unsuitable for deployment. |
| Production API catalog/CRUD/export/pagination, expiry/dedup-retention, correlation/observability and measured service limits — 38.3 future conventions; 38.8 minimum surface | DEFERRED BY DESIGN | Exact intake scope ships only two pure handlers. Before mounting, future composition must define operational correlation, measured quotas, retention/expiry and full security gates; this seam does not claim those services. |
| Durable job dispatcher/status/result publication/worker cancellation/retry budgets — 38.5; explicit DEFER in 38.8 | DEFERRED BY DESIGN | Pure state/input validation exists; later adapter must enforce resource policies and atomic result publication. No queue/Redis introduced without measured need. |
| Runtime Billing/AI/CRM/payment/provider integration — 38.2; later roadmap owners | OUT OF PHASE 19 | Only architectural isolation is required here. No secret/provider dependency, AI financial truth, subscription or CRM product implemented. |
| Advanced research/OOS/replication/statistical correction/Monte Carlo — ROADMAP 19 exclusion; later research phases | OUT OF PHASE 19 | Provenance/exploration labels prepare future work; no scientific validation or research calculator added, no fabricated certainty. |
| Production financial execution migration/broker/live money — 38.1, 38.6; later execution roadmap | OUT OF PHASE 19 | Requires separate parity/security/authority decision. Intent confirmation never equals a fill. No reinterpretation of frozen Method semantics. |

Every Phase 19 architectural MUST is covered above. DEFERRED BY DESIGN refers to explicit later adapters/phases in existing authority, not newly invented deferral. No material unresolved product decision or unexplained Phase 19 omission was found. Readable/recoverable canonical trade records remain a future integration prerequisite; current intent evidence is not presented as production financial evidence.

### Final acceptance gates

Final closure PASS: existing backend full discovery (77 tests, including foundation/application), independent Python/Node canonical fixtures (6 golden vectors, 3 repeated Node runs), all registered frontend regression commands, lint, production build (107 modules) and release distribution audit. Repository authority controls, AI-bundle determinism/safety tests and regenerated bundle verification also PASS (134 files); bundle freshness is rechecked after recording this evidence. Completion checkpoint diff is documentation/status only; implementation checkpoint contains exactly eight allowed new Python files plus six existing authority/evidence files. No deletion, dependency/market-data/protected-runtime/foundation modification or weakening of existing tests.

Browser exemption is justified above for both checkpoints. This is architecture/intake completion, **not production deployment readiness**. Final Git commit/push must independently establish local HEAD = origin/main = actual GitHub main, clean tree and 0/0 before success is reported; no self-referential final SHA is embedded in its own commit. Phase 20 remains unauthorized and unstarted. Validation commands live only in AI_CONTEXT/07_TEST_COMMANDS.md; operational phase fields only in 04_CURRENT_PHASE.md; future scope only in ROADMAP.


# 39. Phase 20 — Production persistence implementation scope

The human authorized the bounded 20→21→22 journey after verified Phase 19 closure. Extend this existing owner; no parallel roadmap/specification. Minimum Phase 20: PostgreSQL + Psycopg adapter for WorkflowScopePort, version/checksum-checked transactional migrations, row-locked Session scope, atomic immutable review/intake/evidence publication, restart/retry recovery, append-only Passport revision and lineage records, bounded scoped reads, CAS context advancement, least-privilege runtime role guidance and real pg_dump/pg_restore recovery drill. Canonical bytes/hashes remain BTL-CJSON-1. No implicit old account upload, execution adapter, broker, worker, chart/UI path, or Phase 23 data pipeline.

Acceptance requires a real isolated PostgreSQL database, not a SQLite substitute or mock-only claim: concurrent/retry/conflict/stale and rollback cases; fresh adapter restart returns original outcome; DB denies immutable updates/deletes; migration re-run/checksum mismatch; Passport/lineage scope/hash/version preservation; backup restored to a distinct empty DB with byte-identity comparison. Narrow indexes derive from actual scoped key/evidence queries, not speculative features. Public mounting waits for tested auth/workspace integration. Binary/driver setup is local QA infrastructure, not a repository dataset or deployed production service. Production credentials, encrypted storage/backups, retention, isolated infrastructure and external launch-security review remain deployment gates in SECURITY_ARCHITECTURE, not fabricated by localhost tests.

## 39.1 Implemented persistence and acceptance evidence

`backend/infrastructure/` implements a replaceable Psycopg 3.3.6 PostgreSQL adapter over unchanged Phase 19 contracts/application. Five code files and one versioned SQL migration own canonical DTO storage, WorkflowScopePort transaction units, Passport/lineage storage and explicit lifecycle CLI. `backend/tests/test_postgres.py` adds nine methods (eight real DB cases, one codec case). Existing backend requirements pin the sole new driver dependency; .env.example is placeholders only. No frontend/runtime/engine/data/old API change or file deletion.

Session row FOR UPDATE serializes same-scope review/context/confirmation. Canonical bytes and SHA-256 are stored together and checked on read; separate receipt/event rows have deferred reciprocal foreign keys. DB rollback covers staged writes and evidence sequence; new adapter/connection recovers the original confirmed result after later context advancement. Session CAS refuses stale revisions or changing inherited Method/feed/profile. Explicit admin lifecycle creates/advances context; confirmation never advances replay/financial state. Scoped parameterized lookups remain application-aware: TrustedScope still requires later verified membership injection, not merely constructor validation.

PostgreSQL triggers refuse UPDATE/DELETE/TRUNCATE of reviewed intents, receipts/events, Passport revisions and lineage declarations. A Passport revision change creates a new record; the same revision with different content conflicts. Each trial declaration is immutable; a correction/new declaration uses a new trial identity and explicit parent link rather than erasing evidence. No research worker/result or statistical certification. Composite primary/unique/FK indexes support actual scoped identities and sequence queries only; no speculative full-history index.

Migration runner holds a transaction advisory lock, records version/checksum and refuses missing/changed history. Checksum normalizes checkout LF/CRLF only; SQL changes still drift. Startup does not auto-migrate. A separate existing non-owner runtime role is granted only schema USAGE, scoped-table SELECT/INSERT and Session-context UPDATE; no role creation/password invention or DDL grants. Tests prove runtime cannot DROP/CREATE or DELETE evidence. Multi-tenant membership enforcement comes in Phase 22; a DB service role is not an end-user identity.

Real local PostgreSQL **18.6** was fetched through the official PostgreSQL-linked EDB binary source, extracted under OS temporary QA storage, bound only to 127.0.0.1:55432 with generated SCRAM credentials. It is not a deployed database or repository binary. All nine persistence tests PASS; full backend **86 tests PASS, no skips**. Twenty-four concurrent confirmations produce one logical nonexecuting result; failure after staged writes rolls back receipt/event/sequence. Real PostgreSQL stop/start preserves every canonical byte/hash. Native custom-format pg_dump → fresh distinct DB pg_restore preserves all review/intake/evidence/Passport/lineage bytes and recovers the same receipt. Tampered archive hash and nonempty restore target refuse. No existing DB is overwritten/dropped by the drill.

Full frontend regression/lint/build/release and six independent Node vectors × three runs PASS. Browser exemption: adapter is unmounted, no browser-reachable path changed; browser tests are not claimed for database code. Repository/bundle controls and final regenerated/verified bundle are checkpoint gates. Official transaction/lifecycle references: [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [PostgreSQL pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html), [official Windows binary direction](https://www.postgresql.org/download/windows/).

### Operator recovery procedure

From backend, configure BTL_DATABASE_URL through secrets/environment. Run `python -m infrastructure.database migrate --runtime-role EXISTING_NON_OWNER_ROLE` with migration-owner connection, then compose adapters with runtime connection. Do not run schema lifecycle using the runtime role. Production must configure trusted CA/TLS, connection budgets and nonpublic database networking.

Backup: `python -m infrastructure.database backup --file NEW_ARCHIVE` using a backup-authorized connection and BTL_PG_BIN/PATH. Store returned SHA-256 separately with controlled integrity/access policy. Restore only into a separately provisioned empty DB: set target BTL_DATABASE_URL, then `python -m infrastructure.database restore --file ARCHIVE --hash EXPECTED_SHA256`. Restore refuses a nonempty target and uses one transaction. Verify receipts and canonical bytes before any cutover. No automatic destructive rollback/down migration; rollback via tested restore to a distinct DB and reviewed cutover. Credentials stay out of subprocess command lines. pg_dump/restore archive is not encrypted by this code: encrypted/access-controlled backups, retention, off-host failure separation, operator role ownership and TLS remain deployment gates, per SECURITY_ARCHITECTURE.

Phase 20 persistence scope is implemented and validated, subject to checkpoint commit/push/equality. Continue only to authorized Phase 21 after that gate. Default v1 remains local; no account upload/migration or public deployment is implied.

# 40. Phase 21 — Authentication and identity scope

Following verified Phase 20 checkpoint, implement email/password identity through mature FastAPI Users (security-maintained project) and its default Argon2 password helper, PostgreSQL adapters for users and revocable opaque database sessions, verified-email login, bounded expiry/logout/logout-all, library verification/reset flows, token hashes at rest, rate/size protections and sanitized errors. No OAuth provider or MFA claimed; neither is mandatory for initial supported login method under ROADMAP 21. Delivery is injected through a real TLS SMTP adapter; QA uses only a recording test sink, no real user email is sent. Missing secret/delivery configuration refuses composition rather than supplying a demo/default principal.

A new explicitly composed backend factory owns versioned auth routes only; old unversioned FastAPI prototype and browser product remain untouched. Bearer transport avoids cookie CSRF state; no token stored by v1 frontend. Explicit auth/me and revocation use library active/verified identity. Before private resource mounting, Phase 22 must resolve persisted membership and resource scope. Public deployment still requires SECURITY_ARCHITECTURE launch gate, HTTPS, production secret/SMTP/DB configuration and review; this is tested backend functionality, not a cloud launch. Acceptance: real DB registration, verification, correct/wrong/unverified login, expiry/logout/all-session revocation, disabled identity, password validation, recovery invalid/reused tokens and password change invalidating sessions, hostile identity injection, shared rate bound and no plaintext password/token in DB/output/logs.

## 40.1 Implemented identity and validation

FastAPI Users **15.0.5** owns registration/authentication, Argon2 via pwdlib, signed verification/reset token validation and opaque token generation. It is security-maintained but in maintenance mode; no promise of new upstream features. We implement its database protocols rather than replacing cryptography. PostgreSQL migration 002 adds users, hashed opaque sessions, rate buckets and append-only security events. `identity/` owns adapters/policy/TLS SMTP/HTTP safety; `cloud/` owns an explicit new versioned factory/runner, isolated from old development API. Direct dependencies are pinned and backend/requirements.lock records all tested transitive versions; install with `python -m pip install -r requirements.lock`. No frontend dependency/data/engine/foundation changes.

Initial login method is **email/password**, the stated minimum assumption after no optional preference reply. Passwords require 15–128 Unicode scalar characters; raw passwords never persist. Registration cannot set ID, verified/active/admin flags or workspace identity. Login requires an active verified account. Library random opaque Bearer sessions expire after 1800 seconds (bounded configured lifetime), hash at rest, and revoke on logout/logout-all. No refresh token/browser localStorage implementation. Verification expires after 3600 seconds and cannot be replayed after verification; recovery after 1800 seconds is bound by the library to old password hash/audience. CAS permits only one concurrent reset; password change revokes all sessions atomically. Session publication re-locks the user row and compares authenticated password hash/active/verified flags, preventing stale login publication racing a password reset. No independent crypto/token format introduced.

HTTP composition requires database, explicit high-entropy secret and delivery; no demo principal/fallback. HTTPS-only boundary refuses plain HTTP (426), sets no-store/HSTS, caps streamed body at 16 KiB, and enforces shared DB rate windows: default 30 auth requests/IP/minute and 10 login/recovery/verify requests/account/operation/minute. Raw account/IP/password/token is not stored in rate buckets or audit. User-supplied forwarding headers do not set identity/rate keys. Server-generated correlation IDs and exception-class-only failure logs expose no private payload. Request validation errors never echo Pydantic secret inputs. Forgot-password known/unknown responses have the same status/body; this is response-shape evidence, **not a constant-time claim**. SMTP delivery timing, production load/IP topology, quotas and recovery UX require deployment review.

TLS SMTP adapter sends verification/recovery codes using SSL certificate validation and bounded network timeout. QA injects RecordingDelivery and sends **no external email**. Actual production SMTP credentials/service, CA/TLS configuration and high-entropy environment secret are not fabricated or activated in this task. OAuth/OIDC, MFA, frontend login/recovery screens and cloud/session cutover are not implemented; supported initial method is email/password backend API. All public-release security gates remain in SECURITY_ARCHITECTURE.

Nine new identity test methods cover registration/verification, hostile flags/identity injection, wrong/unverified/disabled login, token hash/Argon2 persistence, expiry and new-composition recovery, logout/all-session revocation, recovery replay/expiry/audience/concurrency, stale password snapshot, cross-client account rate bound, size/TLS/no-store/redacted errors, actual least-privilege role and fail-closed unavailable DB. Full backend **95 tests PASS, no skips**, including all nine identity methods and real PostgreSQL gates. Full frontend regression/lint/build/release and independent Node vectors PASS. Repository/AI-bundle tests and regenerated/verified bundle also PASS. Nonblocking existing-version compatibility note: Starlette 1.7 emits an HTTPX test-client deprecation warning; requests/tests pass, no warning is hidden or production browser issue claimed.

Browser exemption: no current browser-reachable product path changes. New factory routes are exercised with HTTPS ASGI requests against real PostgreSQL, not falsely described as browser/cloud deployment. Existing v1 API/replay/trading and default website are untouched.

### Identity operator composition

Provision/migrate with owner credentials, then grant an existing non-owner auth role using `python -m infrastructure.database migrate --identity-role EXISTING_ROLE`. Configure BTL_DATABASE_URL with that runtime role; BTL_AUTH_SECRET must be generated externally (at least 48 random bytes, encoded at least 64 characters), plus BTL_SMTP_HOST/USER/PASSWORD/SENDER. .env.example contains empty placeholders only. Configure direct BTL_TLS_CERT/KEY or a controlled TLS reverse proxy and explicit BTL_TRUSTED_PROXY_IPS; wildcard trust is refused. Backend `python -m cloud.serve` defaults loopback 8001 and chooses a Windows selector loop required by Psycopg, without changing the frontend/global event policy. HTTP without established trusted HTTPS scope remains denied. Startup never auto-migrates or invents users. Secret rotation invalidates outstanding verification/recovery signatures; explicit logout-all/DB revocation manages opaque sessions. Retention/session cleanup, breached-password policy, production load, email deliverability and incident controls require pre-public-launch review, not a claim earned by unit tests.

References: [FastAPI Users maintenance/features](https://fastapi-users.github.io/fastapi-users/latest/), [database strategy and logout](https://fastapi-users.github.io/fastapi-users/latest/configuration/authentication/strategies/database/), [UserManager hooks](https://fastapi-users.github.io/fastapi-users/latest/configuration/user-manager/). Phase 21 backend identity is implemented; Phase 22 membership/resource authorization is the next required checkpoint before private-resource composition.

# 41. Phase 22 — User/workspace ownership scope

After verified Phase 21 checkpoint, implement persisted workspaces with server-derived owner, OWNER/MEMBER membership and a bounded resource ownership registry for Backtests, Strategies, Drawings, Indicators, Preferences and research metadata. Registry stores references/names/revisions, **not** a cloud drawing/backtest-sync implementation or imported local account. Deny by default: verified/active DB identity + persisted membership are checked on every operation; ownership cannot be asserted from JSON/header/path alone. Owners manage existing verified-account membership; members may read workspace resource metadata but write only their own, while owner administers workspace metadata. No custom RBAC/teams/invitation-email product or Phase 23 dataset services.

Use scoped DB locks so membership/identity removal cannot race a protected operation. Owner membership must survive, resource scope/creator stay immutable, metadata edits/archive use expected revision, lists are bounded. New secure adapter resolves TrustedScope only inside authenticated membership/resource transaction and then runs unchanged nonexecuting intake; authoritative Method/Session context is provisioned only internally, never deserialized from a client. Optional versioned private intake endpoints may bind this adapter without financial execution; persistence labels must be honest. Existing pre-ownership records are retained and inaccessible through this model until explicitly registered, never automatically assigned to a user.

Acceptance: unauthenticated/disabled/unverified refusal; user A cannot read/edit/archive user B resources by changing IDs; member cannot elevate/manage owner or edit another creator; removed member denies retry; concurrent removal/write is serialized; forged scope/creator/hash/stale revision refuses; authenticated review/confirmation remains one nonexecuting durable outcome with all Protocol/revision guards. Real DB/FK/least-privilege, backup/restore after all schemas and existing full regression remain gates. No frontend migration/login screens or public deployment claim; STOP after final Phase 22 audit.

## 41.1 Implemented ownership and final journey audit

`backend/workspace/{policy,store,intake}.py` owns pure minimal permissions, scoped metadata transactions and the durable intake adapter. `cloud/workspaces.py` installs private versioned routes into the explicit factory only. Migrations 003/004 add workspaces/memberships/resource identities and locking guards; historical 001/002 are unchanged. Owner comes solely from active verified server identity. OWNER controls membership for existing verified accounts; MEMBER reads shared metadata and creates/writes its own resources, OWNER may administer all workspace resources. There are no custom roles, invitation mail, teams, subscriptions or implicit superuser bypass. Each caller's workspace list contains only persisted memberships.

Eight resource kinds are BACKTEST, STRATEGY, DRAWING, INDICATOR, PREFERENCE, EXPERIMENT, REPORT and RESEARCH_JOB. Registry persists bounded names, server UUIDs, creator/scope/kind and metadata revision; it does not claim drawing geometry/cloud artifacts, indicators' calculator configuration, saved/resumable cloud sessions or research worker payloads. Those remain the explicit later ROADMAP scopes (25/26/28 and research phases). No browser data is uploaded/adopted. Pre-existing unregistered Session/provenance namespaces remain preserved and inaccessible through private routes. Passport reading requires registered scoped EXPERIMENT plus matching canonical bytes/hash; no scientific result is invented.

All scoped writes/read-intake hold DB user, workspace, membership and relevant resource locks in one transaction. In-flight membership use linearizes before removal; all later calls refuse. Owner membership cannot be deleted/elevated/reassigned; workspace owner and resource scope/creator/kind/hash are immutable under DB triggers. Resource rename/archive requires exact expected revision, increments metadata revision only, retains archived row/audit and excludes it from active lookup. Lists use 1–50 row keyset pagination and actual user-membership/active-workspace indexes. Caller owner/creator/role/hash fields are rejected, not trusted. Unknown/foreign resources return 404; unauthorized metadata writes return 403. Private intake maps unavailable write permission to non-disclosing 404, not an infrastructure-error claim.

`MembershipWorkflow` constructs the existing TrustedScope inside verified ownership composition and runs unchanged PostgresUnit/application on the same locked connection. Authoritative Session/Method context is provisioned internally only; clients cannot create an execution context or bypass frozen Protocol rules. Concurrent confirmation/retries recover one exact durable receipt/event, even after quote advancement; stale new requests refuse. Successful HTTP composition states durable=true/POSTGRESQL, retaining NOT_EXECUTED/PROTOTYPE, executionPerformed=false and instrument-risk limitations. No fill, position, P&L, replay revision, engine migration or second financial writer exists. Old API remains separate and unsuitable for public deployment.

Runtime composition adds `--workspace-role EXISTING_ROLE` to the existing migration CLI, combined with `--runtime-role` and `--identity-role` where all adapters are composed. Grants do not include DDL, resource DELETE, workspace owner/name UPDATE or membership-role UPDATE. PostgreSQL FOR SHARE requires UPDATE privilege on at least one column: only immutable workspace.id and membership.user_id receive column UPDATE; DB triggers prevent identity mutation. A real restricted LOGIN role exercises private read/create and full review/confirmation intake; unauthorized DDL/destructive/identity writes refuse. A service-role connection is not an end-user principal or claimed DB RLS implementation; application scope is checked independently on every transaction. No public runtime credentials are provisioned here.

The HTTPS/body/no-store/correlation boundary now covers all `/api/v1/` requests with shared default 30/IP/minute; auth account/operation cap remains 10/minute. No raw token/IP/account is added to operational audit. Security audit rows add optional workspace/resource IDs, never private payloads. Existing response/DB time and pagination bounds are retained. Production traffic tuning, pooling, session/record retention, audit privacy and external security review remain existing SECURITY_ARCHITECTURE deployment gates.

Final acceptance: eight new real-PostgreSQL/HTTPS-ASGI ownership methods cover all resource kinds, cross-user refusal, owner/member/creator/revocation, forged fields, CAS/archive/pagination, DB identity protection, unregistered legacy refusal, scoped Passport, concurrent durable intake/Protocol, actual runtime permissions and native backup/restore. Full backend **103 tests PASS without skips**; strengthened restricted-role intake/restore case passes separately after adding that assertion. Native restore retains exact users/token hashes/memberships/resources/security events and original canonical intake/provenance; restored factory accepts original opaque session for authorized scope and denies foreign user. Real PostgreSQL stop/start also preserves the byte snapshot of all twelve canonical/identity/ownership tables; verified listen address is 127.0.0.1 and QA port 55432. Initial restart invocation used the default port and inherited a Windows pipe; that invocation was stopped, explicit configuration restored and the controlled snapshot/restart comparison rerun successfully. No existing database is overwritten or dropped. Canonical hashes certify integrity, not provenance authenticity or production security.

Full registered frontend regression, lint, production build (107 modules), release/distribution and independent Node golden vectors (six, three repetitions) PASS. Existing website `127.0.0.1:5173` displays chart/replay/terminal; News opens/closes without data change and captured console warning/error list is empty. New APIs are tested with HTTPS ASGI against real DB; **no frontend auth/workspace UI exists**, so browser verification does not falsely claim new backend product integration. Repository/context and AI bundle tests plus regenerated hash verification PASS (134 bundle files); freshness is rechecked after this evidence update. Backend remains deliberately outside the frontend-focused bundle, whose included authorities carry evidence. No tests/allowlist are weakened, no protected source/data/frontend/dependency changed in Phase 22, no files deleted or new documentation authority created.

Journey audit: Phase 20 persistence checkpoint `420f638f6d36cf8ebd9070c1891fefcd7b4cedfb` and Phase 21 identity checkpoint `f7492c8a88eb74c0a8bbf27eb0bbfbd1a646dbe6` each reached clean local/origin/actual GitHub equality and 0/0 before the next phase. Phase 22 preserves those boundaries and requires its own normal commit/push/equality. Default local v1 remains intact. SMTP delivery, public TLS/hosting, production secrets/backup encryption and launch review are **not activated or certified**; actual cloud backtest/sync/data/RBAC/worker products remain their existing later phases. Complete this bounded journey and STOP before Phase 23; no second roadmap or automatic continuation.

# 42. Phase 23 — Market-data service preparation (planning only)

The human asked to continue after the proposed Phase 23 audit/planning step. Baseline verified from actual repository: clean main `ef658338d74b501c327cb3c2baf884647436760e`, equal to origin and actual GitHub, ahead/behind 0/0. This section extends the existing architecture owner; ROADMAP alone owns future scope and 04_CURRENT_PHASE alone owns authorization. This checkpoint prepares a reviewable scope; it does not authorize data purchases, provider contact, cloud deployment, source changes or Phase 24 ingestion. No second roadmap/specification is created.

## 42.1 Current source and integration audit

The actual `frontend/public/market/decade/manifest.json` declares HistData.com XAUUSD bid M1, fixed EST UTC−5 converted to UTC, 3,486,461 candles from 2016-10-02T23:01:00Z to 2026-09-25T00:58:00Z. There are 120 UTC-month M1 chunks, eleven timeframe entries and nineteen original archive SHA-256 values. The current M1 artifact total is 167,286,066 bytes; largest chunk 1,555,439 bytes/31,753 rows. These are file-size observations, not performance/SLA measurements. Individual served-chunk hashes, immutable dataset version and cloud usage-rights evidence are not declared in the manifest. The historical report remains [HISTORICAL_XAU](HISTORICAL_XAU.md).

`useReplayMarket.js` fetches local static manifest/month chunks, keeps prefetched future rows internal and sends only the revealed prefix to existing aggregate/indicator/trading consumers. Higher-timeframe current buckets derive from that prefix. `useGoldMarket.js` separately samples Gold API and loads history; `history.js` validates rows/converts timezone and prevents mixed-feed OHLC. `download-decade.mjs` is a manual download/build utility, not an authenticated cloud pipeline. Volume 0 is a legacy missing-volume placeholder, not measured trading volume. Existing v1 distribution contains these static assets, so deploying its dist unchanged would still ship history publicly even if a new API were authenticated. **Do not publish that build as a rights-approved cloud product.** No local files are removed or repackaged by this planning task.

Phase 20–22 supply durable Product metadata, identity and membership. They do not supply dataset publication/grants, licensed data provider, private artifact storage, server replay progression or a browser login/data adapter. Existing backend API/engines remain separate prototypes; they must not become a second canonical execution authority merely to serve candles.

## 42.2 Evidence ownership and two separate audiences

The preparation checkpoint evaluated HistData, Dukascopy, Twelve Data and LSEG; the expanded, human-authorized research below supersedes that preliminary shortlist and cost snapshot. Section 42.5 onward owns the current provider comparison/licensing/cost decision record. The existing [Market Data Standard](MARKET_DATA_STANDARD.md#phase-23-research-specification--no-runtime-authorization) owns canonical requirements, fidelity, quality acceptance and registry/Passport semantics. No competing data standard is created.

The human expressly requires personal/internal research and public/commercial SaaS as separate lanes. Individual noncommercial use is not company-internal commercial use. A personal-only dataset cannot enter public catalogs, caches, browser assets, download URLs, derived-data delivery or authenticated customer accounts. Separate audience grants and publication boundaries are required; shared physical bytes are allowed only if both applicable grants permit the actual use. Unknown/expired/revoked rights deny use outside the evidenced scope. Code open-source licenses do not license market data. Preserve existing local history without representing its presence in public Git as redistribution permission.

## 42.3 Proposed minimal implementation scope, awaiting decisions

Recommended first engineering checkpoint: **isolated authenticated historical-data delivery**, one explicitly approved XAUUSD M1 dataset version per permitted audience; existing chart and ten-year local replay stay unchanged. The human selected both personal/internal and public/SaaS paths above, with strict source separation. Synthetic authored fixtures can validate each adapter/policy before real-data rights are supplied, but cannot close real-data coverage/public-launch acceptance. Coverage target is the existing ten-year window only if the selected source supports/licences it; shorter history must be disclosed rather than fabricated. Provider/budget/storage-license decisions remain open; no runtime authorization is inferred from the two-path research decision.

Proposed MUST for later explicit implementation authorization:

1. Provider-neutral dataset descriptor and immutable verified artifact version: source/feed/instrument, bid/ask/mid semantics, base interval, timestamp convention, actual coverage/gaps, missing-volume meaning, normalization version, bytes/hash, rights reference and publication state. Keep original archive hashes separate from normalized chunk hashes. Metadata hashing may use existing BTL-CJSON-1; raw chunk hashes cover declared artifact bytes, **not** a direct BTL-CJSON hash over legacy floating-point arrays. No invented price precision or silent source repricing.
2. Separate metadata/storage/read ports with explicit operator-only publication from validated, rights-approved artifacts. One shared dataset copy plus verified workspace access policy, not a full market copy per user. Product DB stores small metadata/grants, bulk bytes remain behind portable private storage abstraction. No new Redis/queue/TimescaleDB/CDN or distributed service without measurements. Publication validates everything before activating a new version; old references retain their version. Never serve arbitrary caller file paths/URLs or public unrestricted blob links.
3. Thin versioned FastAPI read boundary reusing existing active/verified identity, membership, TLS/error/rate safeguards. Server validates dataset access and, for a strict Session read, registered BACKTEST scope plus authoritative SessionContext revision/revealed bound. Client IDs/revision/cutoff are assertions, not rights or replay authority. Unregistered/foreign/withdrawn datasets deny; missing identity cannot fall back to the old prototype or static history. Proposed surface is scoped catalog/descriptor and paginated M1 range; exact DTO/routes are reviewed before coding.
4. Preserve no-look-ahead: strict Session responses cannot exceed the server-resolved revealed prefix. No completed D/W/M OHLC may be exposed just because its start precedes the cursor. Initial base service returns M1; future display adapter derives higher frames using the existing revealed-prefix aggregations. Existing M1 reveal convention remains unchanged; claiming true intrabar tick availability would require separately approved semantics. Offline prefetch/browser history mode and strict Session delivery are distinct capabilities; no bulk future download is implied.
5. Bounds proposed for acceptance, not measured throughput: 1–10,000 M1 rows/request, 1 MiB serialized response, 16 KiB request via existing boundary, bounded UTC range/keyset cursor tied to dataset/version/revision, existing 5s connect/10s lock/15s statement bounds and 30/IP/minute ceiling. Include explicit row/byte rejection or truthful continuation, no silent truncation/fabricated bars. Final limits require cold/warm/concurrent workload measurement and provider/license ceilings; shared/private cache keys must not bypass current permission or temporal checks.
6. Verify artifact checksums and OHLC/order/time invariants before publication/read; preserve gaps/unknown volume, never interpolate missing prices. Source/normalization identity travels with response/research references. On corruption/outage/changed revision, fail safely without changing account/replay state or switching feeds. Keep all provider credentials and private artifact/audit contents out of frontend/Git/logs.
7. Recovery and deployment gates: restore metadata plus private artifacts into a distinct environment, verify identical versions/hashes/access and retry outputs. Backup design follows existing security owner. Launch requires proven usage rights, public TLS/secrets/storage access controls, dependency/secret review and explicit deployment authorization. Testing a local service is not a cloud deployment certificate.

SHOULD after minimum evidence: compressed transfer, measured bounded caching, range-query metrics and provider comparison. DEFER under existing roadmap: automated/live acquisition/normalization/refresh pipeline (24), server save/resume/progression (25), cross-device sync (26), dashboard/login UI (27 or separately scoped UI checkpoint), cloud drawing/object payloads (28), broad tenant/RBAC features (29/55), tick-resolution service (39), multi-provider merging, news ingestion, workers, research engines, billing and AI. No frontend rewrite, changes to current replay/execution, local data deletion or new roadmap.

Proposed file boundary, not creation permission: new isolated `backend/market_data/` policies/use cases/ports, narrowly reviewed infrastructure storage/metadata migration and cloud route adapter, plus focused backend tests. Extend existing composition only after the DTO/security review. Keep backend/contracts/application/old API/services/engines, existing frontend/data and historical migrations unchanged unless a genuinely required change is explicitly approved. Reuse existing Pydantic/FastAPI/Psycopg rather than invent auth, financial execution or a vendor-coupled engine.

## 42.4 Acceptance and decision handoff

| Gate for future implementation | Required evidence |
| --- | --- |
| Rights | Sanitized reviewed evidence for exact source and independently approved personal/internal vs public storage/display/API/commercial mode; unknown/expired/revoked grants deny. Personal-only dataset refused in public catalogs, caches, direct/private downloads, derived OHLC and static build assets; authenticated SaaS user is still an external audience. |
| Integrity/version | Malformed/duplicate/out-of-order/nonfinite/bad OHLC/timezone/gap/volume cases, source/byte hash mismatch, immutable replacement and pinned prior identity. |
| Isolation | Unauthenticated/unverified/disabled caller, swapped workspace/dataset/session IDs, removed membership and changed policy deny, including caches/artifact access. |
| Temporal | Identical strict output under physically truncated/altered future rows, forged cutoff/stale revision refusal, range boundaries, partial higher-timeframe prevention and frozen reveal semantics. |
| Bounds | Row/byte/range/cursor/body/rate limits, path traversal/SSRF refusal, concurrent clients, cold/warm IO/memory/latency measurement and safe provider/storage failure. |
| Recovery | Native Product DB backup + separately verified dataset artifacts, distinct-target restore, exact descriptor/hash/pinned output and access preservation. |
| Compatibility | Full actual PostgreSQL backend, Node golden vectors, frontend regression/lint/build/release and repository/bundle gates. Actual browser smoke required when a browser adapter is authorized; no backend-only test can claim that integration. |
| Git/launch | Reviewed diff/context, normal checkpoint push, actual local/origin/GitHub equality/clean 0/0; public deployment separately gated. |

The human resolved audience scope: **both**, separately governed. Remaining decisions to finalize implementation: (a) separate internal/public monthly data budgets and provider choice/actual usage-rights evidence, (b) XAUUSD-only/M1/actual licensed history coverage, (c) isolated service first vs separately scoped frontend cutover. Exact attribution/storage/API/derived-data permissions require the selected provider's applicable agreement, not inferred from price. No payment, vendor message or deployment is sent on the human's behalf. Missing rights do not prevent this documentation checkpoint or synthetic service planning; they prevent claiming real-data public launch. These decisions and explicit finalized implementation authorization precede code changes.

The preparation checkpoint passed repository/bundle controls, regeneration/hash verification and diff review before normal push/equality at 4876c03. Browser was exempt for docs only. Its status was preparation after completed engineering Phase 22. The later research authorization and completion handoff below supersede preparation-only operational status, without authorizing cloud implementation.

## 42.5 Phase 23 authorized research — provider comparison

**Scope reconciliation:** two supplied authorizations now define Phase 23 as market-data strategy/provider research/licensing/cost planning, not service implementation. The human approved checkpointing the six existing drafts first. Preparation checkpoint `4876c037da1970867b1a353ad4fb886f94eadaa3` was normally pushed and verified local = origin/main = actual GitHub main, clean tree and 0/0 before this expanded research. Section 42.3 is a historical proposed engineering handoff, not an implementation MUST for this research task. Roadmap's cloud-service capability remains unimplemented; research completion must not mark that capability shipped. No Phase 24, purchase, contract acceptance, provider contact, credential entry, dataset download or runtime change.

All official evidence below was reviewed **2026-10-05 Asia/Jakarta**. `VERIFIED` means the stated page/contract or repository artifact was read, not that vendor data quality was certified. `PROVIDER CLAIM` is an untested product assertion; `UNCLEAR`/`LICENSE_REVIEW_REQUIRED` means unresolved. Exact last ticks and uninterrupted coverage cannot be inferred from marketing history length. No account-gated archive/API was accessed. Nine provider candidates are compared across linked tables rather than one unreadable 33-column table; row identity is the join key.

### Technical capability, coverage and fit

| Provider/product and official evidence | Gold identity | Tick/order and price sides | Timestamp/timezone | Earliest/latest coverage and known gaps | M1/API/bulk; technical fit |
| --- | --- | --- | --- | --- | --- |
| HistData Generic ASCII ticks / existing M1 [H1], [H2] | XAU/USD listed; exact contributing feed unknown | ASCII ticks specify bid+ask; spread derived from paired quotes. Last absent, mid can be derived but is not raw. Full ordered chronology/ties untested | Tick format milliseconds, fixed EST UTC−5 without DST | Tick XAU exact first/last UNKNOWN. Only stored **M1** independently verified 2016-10-02T23:01Z–2026-09-25T00:58Z, 3,486,461 bars; no inference of equivalent tick coverage | M1 bid, web archives/optional FTP; no supported historical REST API established. Best existing compatibility baseline; fidelity 4 now, tick candidate only after quality/rights checks |
| Dukascopy Historical Export / JForex history [D1], [D2] | XAUUSD spot-gold candidate; confirm exact export instrument/feed | Historical API ITick exposes bid/ask and sizes. Last not established, mid/spread derived. Quote chronology and ties require sample | JForex time semantics must be verified for selected export; API/examples use epoch time; no promise every export has identical precision/DST | Official reviewed pages do not establish exact XAU first/last ticks; ≥10-year requirement UNVERIFIED. No full gap scan | CSV export/JForex history, M1 side candles; high-fidelity research candidate. Download wrappers are not licenses |
| Darwinex historical asset tick FTP [W1], [W2] | XAUUSD listed, broker-specific feed | Provider-owned downloader reads separate bid/ask streams and reconstructs spread; synchronization/staleness needs validation. Last/mid not raw claims | Exact asset-file precision/timezone/order contract UNKNOWN; do not borrow the unrelated DARWIN index quote format | Official asset table says **2017-10-01** start; exact last event/gaps UNKNOWN. Less than ten years on review date | Free FTP for eligible live-account clients; ticks can derive M1. Broker-path research comparison, not whole-ten-year solution |
| FXCM Basic HDD / FXCM Pro price feed [F1], [F2] | Commodities/CFDs supported; exact XAU historical tick product must be confirmed | Basic HDD bid/ask **bars**, not tick proof; Pro describes historical bid/ask tick FX. Last/mid and gold tick coverage not established | Basic M1 range granularity; Pro tick precision/timezone/sequence UNKNOWN for XAU | HDD claims up to ten years; Pro FX history since 2009, free FX bars up to five years. None proves exact XAU tick first/last/gaps | Demo/live account HDD; Pro APIs/custom delivery. Promising negotiated broker-source SaaS tick route, not a certified gold feed |
| TrueFX historical download / Integral market data [T1], [T2] | Historical product lists currency pairs; XAU archive not established | FX top-of-book bid/offer ticks, milliseconds claimed; exact XAU ordering/Last UNKNOWN | Millisecond FX claim; gold timezone/sequence unverified | Exact XAU first/last UNKNOWN; no qualified gold coverage found | Download/internal analysis route; reject as current XAU primary candidate, retain for future FX research |
| Twelve Data time_series / Business [V1], [V2], [V3] | XAU spot listing in forex product; feed mapping needed | Documented time_series is OHLC, not paired historical bid/ask ordered ticks. Level 1/2/3 listed unsupported; live stream does not prove historical sequence | Forex API UTC by default; [composite currency methodology][V9] is weighted mid pricing, not raw broker Bid/Ask; bar resolution does not imply tick precision | Exact XAU M1 first/last UNKNOWN; general varying historical depth is not ten-year tick evidence | REST/WS; [historical support][V8] documents a 5,000-record request ceiling; no one-off full-history purchase promised. Practical **candle/display** candidate; reject for fidelity-1 requirement |
| Tick Data LLC spot Forex quote history [K1], [K2], [K3] | XAU pair availability UNKNOWN: product pair-list retrieval failed; gold futures must stay separate | Forex spec has paired bid/ask with contributor/region/city, no guaranteed Last in this format. Duplicate timestamp samples show why order cannot be guessed | Milliseconds; FX US Eastern/New York, explicit DST conversion required | General Forex product begins **2008-05-01**; exact XAU first/last/gaps UNKNOWN | ASCII bulk/M1 bid/paid API/update products. Professional high-fidelity benchmark conditional on actual XAU inclusion and rights |
| LSEG Tick History Instrument/Venue + redistribution [L1], [L2] | OTC and exchange content; confirm precise XAU RIC/contributor, not a generic gold-future substitute | L1/L2 historical quote/trade products; actual paired bid/ask, event order, Last depend on selected feed | Product-dependent; PCAP nanosecond marketing cannot be transferred to OTC XAU | General history back to 1996 claimed; exact XAU first/last/gaps UNKNOWN | DataScope API/extract/venue files/S3; strongest enterprise procurement path, not independently certified XAU dataset |
| Databento GLBX.MDP3 GC [B1], [B2], [B3] | **COMEX gold futures GC, not spot XAUUSD** | Event/order-book schemas supply quotes/trades; select MBP-1/MBO with validated event ordering, not sparse TBBO alone for every quote change. Last trade distinct from bid/ask | ns encoding; CME pre-2015-11-20 limited to ms, pre-2017-05-21 lacks full MBO; preserve source flags | GC catalog says **2010-06-06 UTC** start. Page instrument snapshot updated 2026-09-16 is not dataset last tick. Actual latest/gaps UNKNOWN | API/bulk/derived bars. High-fidelity **separate futures** research and licensing benchmark; rejected as direct spot-gold replacement |

No provider passes independently verified complete ten-year XAU ordered Bid/Ask + applicable legal storage rights in this desk research. That is a procurement/sample gate, not an excuse to invent a winner. Unknown Last/mid is not a negative assertion about all vendor products. [Market Data Standard](MARKET_DATA_STANDARD.md#quality-acceptance-and-procurement-sample-plan) owns the complete missing/duplicate/out-of-order/DST/session/spread/spike/scaling/revision/reliability checklist; no numeric provider quality scores were manufactured.

### Licensing matrix — each permission is independent

Flags describe **evidenced scope for this exact Backtest Lab use**, not grants Backtest Lab has acquired. Classifications can co-exist: PERSONAL_RESEARCH_ALLOWED, INTERNAL_COMMERCIAL_ALLOWED, PUBLIC_DISPLAY_ALLOWED, PUBLIC_COMMERCIAL_ALLOWED, REDISTRIBUTION_ALLOWED, DERIVED_DATA_ALLOWED; unresolved flags are LICENSE_REVIEW_REQUIRED, unsuitable products NOT_SUITABLE. Personal-only restriction is retained as PERSONAL_RESEARCH_ONLY where applicable. An allowed product offering is not an executed agreement.

| Provider | Personal / internal-business rights | Public display / commercial SaaS | Raw/API/export redistribution / derived candles | Current decision class |
| --- | --- | --- | --- | --- |
| HistData | Intended application downloads documented; precise research/business license not established [H1] | No explicit grant found | Neither public raw nor derived grant verified | LICENSE_REVIEW_REQUIRED; keep existing history, no public promotion |
| Dukascopy | Personal noncommercial download terms; organizational research and database/automated storage need specific permission [D3] | No blanket SaaS grant under website terms | Written permission/appropriate agreement required | PERSONAL_RESEARCH_ONLY within terms; DB/public LICENSE_REVIEW_REQUIRED |
| Darwinex | Live-client strategy R&D purpose offered [W1]; independent company-research rights unknown | Not established | Public/API/derived grant not established | Personal R&D product candidate; LICENSE_REVIEW_REQUIRED for exact retention and SaaS |
| FXCM | Basic app marketed for backtesting; business rights require actual account/feed terms | Pro explicitly offers internal business/redistribution use [F2], through applicable agreement | Negotiated scope; app access does not grant external historical API/export | LICENSE_REVIEW_REQUIRED; realistic negotiated route |
| TrueFX | Internal viewing/analysis licensed [T1]; commercial internal scope requires applicability review | Historical content dissemination disallowed by these terms | Widget exception does not license historical-content export; derivative permission not established | PERSONAL/internal scope only; NOT_SUITABLE for unlicensed SaaS/XAU archive |
| Twelve Data | Individual tiers personal/internal noncommercial [V4]; free tier non-display; commercial internal needs suitable agreement | Business display/distribution tiers exist, actual coverage/add-on agreement required | Raw delivery is distinct from display; reconstructible aggregates do not automatically escape source rights [V5] | LICENSE_REVIEW_REQUIRED until tier, source and application grant confirmed; candle route only |
| Tick Data LLC | Research product offered; license schedule required | No automatic customer SaaS grant established | Request negotiated onward/raw/derived permissions | LICENSE_REVIEW_REQUIRED; confirm XAU before purchasing |
| LSEG | Contracted research content | Explicit commercial redistribution offering [L2] | Negotiated raw/historical/derived scope and source/exchange permissions | LICENSE_REVIEW_REQUIRED for actual signed product schedule; scale candidate |
| Databento | Dataset-specific research license manager [B2] | Publisher rules flow through; generic delayed-data statements are not exact CME permission | Require exact GC/CME historical/derived/export terms; provider distribution license is not customer's sublicense | LICENSE_REVIEW_REQUIRED; separate futures only |

| Provider | Storage / cache / archive / API limits | Attribution | User, geography, sublicensing and termination |
| --- | --- | --- | --- |
| HistData | Long-term cache/backup rights UNKNOWN; FTP one IP/three connections/access term [H3] | Required data notices UNKNOWN; preserve provenance without inventing obligations | End-user/geographic/termination rights UNKNOWN; clarification required |
| Dukascopy | Website terms restrict database construction and automated access; exact historical feed agreement needed [D3] | Retain copyright/proprietary notices | Personal grant is not customer sublicensing; negotiated regions/users/retention UNKNOWN |
| Darwinex | Account-gated FTP; allowed mirrors/cache/reuse and acquisition limits UNKNOWN | UNKNOWN | Eligibility live account; tester/customer sharing, region and termination/deletion UNKNOWN |
| FXCM | HDD downloads/API product-specific retention/rates UNKNOWN | Contract-specific UNKNOWN | Institutional/professional Pro offering; tester counts/regions/termination UNKNOWN |
| TrueFX | Single-instance/internal purpose; no general hosted archive permission [T1] | Preserve source/proprietary identity; exact attribution UNKNOWN | Nontransferable/nonsublicensable; fees may change with notice; termination retention must be clarified |
| Twelve Data | Permitted retention/caching periods depend on subscription/docs/source; credential sharing/rate circumvention restricted [V5] | Applicable attribution/white-label agreement | Export restrictions apply. Terms require deleting data on termination: §12.5 access/use ends immediately, §16.2 deletion within 30 days; obtain written reconciliation, no permanent retention assumption |
| Tick Data LLC | Bulk/archive/API/update rights and limits require license schedule | Contract-specific UNKNOWN | Per-user/region/sublicense/termination/deletion UNKNOWN |
| LSEG | Contracted extraction/storage/backup/retention schedule, not unrestricted mirror | Source/contract-specific UNKNOWN | Content/user/region and end-product restrictions; termination/deletion UNKNOWN pending schedule |
| Databento | Publisher-specific storage/retention; API metered by binary uncompressed size [B4] | Publisher-specific UNKNOWN | Historical vs live fees/entitlements differ; user/region/termination require exact license |

UNKNOWN is not permission and not proof of an absolute prohibition. A private beta with unrelated testers is external use, even if free/invitation-only. Business-internal commercial use and individual personal use must not be conflated. Keep license evidence private with sanitized references in public Git; do not upload contracts/secrets or publish source artifacts to satisfy reproducibility. No legal permission is inferred from open-source downloaders, paid subscriptions or public URLs.

### Current pricing and payment triggers

Native currency USD unless stated; **price evidence date 2026-10-05**. Published options are not complete ten-year XAU quotes. Unspecified trial, annual, acquisition, tick/BidAsk/history surcharge, commercial/display/redistribution/derived fee, exchange/vendor/per-user/API overage, retention fee, minimum contract or setup fee is **UNKNOWN / CONTACT SALES / CUSTOM QUOTE**, never zero by omission. Taxes and actual foreign exchange excluded; no unsupported IDR conversion.

| Provider | Free/trial and personal/internal cost | Public/commercial cost | When payment/review becomes necessary |
| --- | --- | --- | --- |
| HistData [H3] | Web $0; optional FTP/SFTP **$27 / 15 days**, no monthly subscription claim | CUSTOM QUOTE / rights unestablished | Convenience/bulk-access purchase optional; commercial/external/storage transition requires rights review before acquisition/publication |
| Dukascopy [D1], [D3] | Historical export advertised free; price of approved automated research DB UNKNOWN | CUSTOM QUOTE; personal terms inadequate | Database/automation/business or tester/customer use needs permission before that use, not only after revenue |
| Darwinex [W1] | Tick FTP $0 to eligible live-account clients; account/funding/trading costs separate, not a free unconditional signup | CUSTOM QUOTE / no public grant | New account eligibility, organization/external audience or retained mirror requires review; do not open/fund a trading account just for this research |
| FXCM [F1], [F2], [F3] | Basic HDD free/demo account route; gold tick service fee CONTACT SALES; no fabricated $99 quote | Pro CUSTOM QUOTE | Need tick/longer exact gold coverage, commercial internal or customer redistribution; acquisition/tool fee separate from license |
| TrueFX [T1], [T2] | Historical System terms say no fee subject to later changes; eligibility/XAU history unresolved | Official search-index streaming claims **$4,950/$7,450 per month**; full current page returned no pricing, so current rates UNVERIFIED, not historical XAU/SaaS quotes | Streaming depth/connectivity or external-use agreement; paying streaming fee does not fix historical-gold coverage |
| Twelve Data Individual [V6] | Basic $0, 8 credits/min/800/day, non-display. Starting labels Grow **$29**, Pro **$99**, Ultra **$329/month**. Selected cards **$79/$229/$999**, annual billed **$790/$2,290/$9,990** | Individual price is not SaaS permission | Internal display requires suitable tier; quotas/history needs or commercial use trigger appropriate plan/agreement, not assumed price multiplication by customers |
| Twelve Data Business [V7] | Basic is not a public license | Venture **from $149/month**; configured card **$499**, annual **$4,990**. Enterprise **$1,099/month**, annual **$10,992**; Enterprise+ CUSTOM QUOTE. Display vs distribution differ; add-on/source fees require quote | First external display/distribution/customer access, storage needs or credit limit; specific application grant required before public beta |
| Tick Data LLC [K4] | No free full gold archive price verified; new-client minimum **$1,000**, returning **$500**, estimated-order policy excluding delivery-support fee/tax | CUSTOM QUOTE; research order is not SaaS grant | Exact XAU availability/sample and symbol-years first; historical purchase/update/API/support/redistribution scoped separately |
| LSEG [L1], [L2] | CUSTOM QUOTE; no public retail monthly/annual price verified | CUSTOM QUOTE for data + onward rights | Proven need for licensed XAU ticks/coverage/provenance; negotiate content and customer rights before launch, not after scaling |
| Databento [B2], [B4] | **$125** historical trial credits; usage-based acquisition quote by exact schema/period. CME Standard **$199/month**, Plus **$1,750/month**, Unlimited **$4,500/month**; Plus/Unlimited annual contract, additional license fees | Publisher/redistribution fees separate and dataset-specific | Credits exhausted, more history/schema/live/external delivery; gold futures scope only, no payment justified as XAU replacement |

Twelve Data business page was successfully retrieved during expanded research; its current prices supersede the earlier preparation's dated March-update-only evidence. Credit configurations expose different starting and selected-card prices; annual billed totals above are observed totals, not multiplication of rounded monthly labels. Tick Data minimum is not the price for ten years of XAU. Databento trial credits do not imply free ten-year quote history. No subscription/credential/account was created.

### Recommendations and provider tiers

| Stage / classification | Recommendation | Conditions and reasons |
| --- | --- | --- |
| START NOW / A: best $0 local development | Preserve existing HistData M1 as compatibility reference; use authored synthetic quotes for pipeline/ambiguity tests | No new spend or rights expansion; disclose candle fidelity. Synthetic inputs are labelled fixtures, never historical tick evidence. New real tick acquisition awaits rights/sample gates |
| A: free/low-cost personal tick shortlist | HistData ASCII Bid/Ask first; Dukascopy export next; Darwinex if already eligible | HistData closest to current source and paired ms format; Dukascopy technically promising but DB/automation restrictions matter; Darwinex shorter coverage/account gate. No unconditional legal DB recommendation |
| B: high-fidelity research shortlist | Rights-approved Dukascopy or HistData samples compared with negotiated Tick Data/LSEG exact XAU product | No measured winner without samples; Tick Data XAU listing and all exact coverage remain unconfirmed. Paid data is justified only by measured useful fidelity improvement |
| C: first public release | **Candle product:** quote Twelve Data Business display/distribution + storage/termination rights. **Observed tick product:** quote FXCM Pro and LSEG exact XAU historical onward rights | M1-only public release must disclose ambiguity; Twelve Data is not approved as fidelity-1 feed. FXCM XAU ticks need confirmation; LSEG enterprise route may exceed early budget. No personal archive migration into public |
| C / early SaaS revenue | Retain the licensed production version; renegotiate quotas/customer tier as actual usage grows | Paying users do not convert personal rights to public rights. No per-user linear retail-price assumption |
| D: enterprise / scale | LSEG redistribution benchmark; exact Tick Data/FXCM agreements if they meet XAU + rights + cost | Dataset-independent core, measured storage/delivery, license reporting and security; Databento only for separately introduced gold futures |
| E: negotiation required | Every proposed retained public XAU product; especially source archives and deletion/reproducibility conflict | No executed license or sales message exists. Contract/sample review precedes adoption |
| Rejected for this target | TrueFX unverified historical XAU; Twelve Data fidelity-1 ticks; FXCM Basic HDD as ticks; Databento GC as spot XAU substitute | Insufficient exact instrument or granularity. These can remain useful for different scoped products; no finding that all their data is bad |

No certified free ten-year ordered XAU Bid/Ask dataset with fully evidenced Backtest Lab retention/public rights was found. Keep the $0 development path while negotiating only when product fidelity or external audience requires it. Changing provider creates a new dataset/version/explicit experiment rerun under the [existing standard](MARKET_DATA_STANDARD.md#dataset-registry-and-passport-requirements), never silent experiment repricing. Multiple approved lanes can use different providers with segregated grants/storage/catalogs; no blend or dual execution authority.

### Storage scenarios — assumptions, not observed tick frequency

Use decimal GB. Assumed **260 trading days × 22 hours/day** = 20,592,000 active seconds/year. Illustrative quote rates **1 / 5 / 20 events/second** are workload scenarios, not provider observations. Assumed raw text **64 B/event**, normalized compact tick **40 B/event** (timestamp, prices and minimal sequence/flags), compression ratio **3:1** purely hypothetical. Real formats/optional sizes/precision/provenance may be larger; benchmark before procurement. Estimates retain both raw and normalized; neither compresses M1 into fake ticks.

| Years | Events, low / middle / high | Raw GB, low / middle / high | Normalized GB, low / middle / high | Both compressed GB, assumed 3:1 |
| --- | --- | --- | --- | --- |
| 1 | 20,592,000 / 102,960,000 / 411,840,000 | 1.318 / 6.589 / 26.358 | 0.824 / 4.118 / 16.474 | 0.714 / 3.569 / 14.277 |
| 5 | 102,960,000 / 514,800,000 / 2,059,200,000 | 6.589 / 32.947 / 131.789 | 4.118 / 20.592 / 82.368 | 3.569 / 17.846 / 71.386 |
| 10 | 205,920,000 / 1,029,600,000 / 4,118,400,000 | 13.179 / 65.894 / 263.578 | 8.237 / 41.184 / 164.736 | 7.139 / 35.693 / 142.771 |

Separate derived candle estimate at one-minute granularity: 343,200 bars/year. At assumed 48 B/side-bar, one side is 0.016474 GB/year; bid+ask M1 **0.032947 / 0.164736 / 0.329472 GB** for 1/5/10 years. Extra M5/M15/M30/H1/H4/D1 approximate **1.3216× M1** under this assumed schedule (about 0.4354272 GB for ten-year two-side compact base+higher bars), excluding indexes/metadata. These are compact design estimates; the actual repository's one-side JSON M1 total is **0.167286066 GB** for its actual 3,486,461 rows. Do not equate the assumed annual schedule with measured coverage.

Budget peak storage separately: e.g. raw+normalized+derived+20% index overhead, one retained old version and one backup can approach three artifact sets. Middle ten-year compressed raw+normalized is 35.693 GB; with derived 0.4354272 GB and 20% overhead ≈43.354 GB/set, three sets ≈130.062 GB. Compression/index/backup factors are assumptions, not a mandate to duplicate entire datasets per customer. Working normalization scratch may need uncompressed capacity.

### Cost scaling and total-data cost model

`TCO = one-time acquisition amortization + provider subscription + commercial/redistribution/source fees + API overage + storage + processing + backup + delivery/CDN + egress + user/enterprise fees + applicable taxes`. Unknown licensed data fees remain `L(stage)`; do not replace them with $0 or multiply individual subscriptions by users. Compute, DB, worker/TLS/CDN/logging/security and staffing quotes are not supplied by the data vendor.

Optional storage comparison uses official [Cloudflare R2 Standard pricing][S1], not an infrastructure selection: $0.015/GB-month, 10 GB free, Class A $4.50/million after 1m free, Class B $0.36/million after 10m free, storage egress $0. Billable units round up. Assumed one middle ten-year set rounded **44 GB** gives storage-only **$0.51/month**; three sets rounded **131 GB** gives **$1.815/month**, before other costs. Free allowances shared with the account's other workloads; ignore Infrequent Access here. No public bucket/URLs, account or R2 adapter is created. Free egress does not license data or cover API compute.

| Stage | Audience / illustrative workload | Acquisition and vendor/license decision | Storage + delivery illustration; total remains conditional |
| --- | --- | --- | --- |
| 0 Local development | One developer; existing data + synthetic tests | New acquisition/subscription $0; no public grant presumed | Existing disk incremental service bill $0; capacity/backup/electricity not assessed |
| 1 Internal research | One researcher, serious observed-tick needs | Legal free candidate after rights/sample review, or exact XAU quote from paid shortlist; Tick Data new-client minimum $1,000 is not a dataset quote | If cloud storage permitted: 131-GB scenario $1.815/month + processing/backup operations; total acquisition/license UNKNOWN |
| 2 Private beta | Assumed 20 external testers | External-use grant required before sharing; retail/internal license not sufficient | Assume 1,000 storage reads/user/month: 20,000 reads; R2 B $0 within unused free allowance. All actual license/compute costs additional |
| 3 Public beta | Assumed 100 active users, no revenue required | Candle path conditional Venture configuration from $149 / selected $499 + required add-ons; tick route CUSTOM QUOTE | 100,000 reads; B $0; storage $1.815 + `L(public-beta)` + app/processing costs |
| 4 Early SaaS | About 100 paying/active users | Exact distribution/storage grant, not merely Venture display. Selected Enterprise $1,099/month or $10,992/year illustrative, not selected contract | Same read model; data subtotal hypothetical $1,100.815/month **only if** selected Enterprise actually covers use; add-ons/compute/processing/acquisition/tax not included |
| 5 Growth | About 1,000 users | `L(1000)` bespoke thresholds/quotas; re-quote, do not reuse 100-user assumed grant | 1m reads; B $0 under assumptions; storage $1.815; TOTAL UNKNOWN + `L(1000)` + other costs |
| 6 Scale | About 10,000 users | `L(10000)` enterprise/redistribution/user reporting; negotiate actual peak concurrency and exports | 10m reads; B $0 if entire free allowance available; storage $1.815; TOTAL UNKNOWN. 100m reads instead adds **$32.40** storage B operations |
| 7 Large scale | 100k+ users, optional scenario | `L(100000+)`, direct source rights/multi-provider procurement after measured demand | At 100k × 1,000 reads, 100m reads gives B $32.40 + storage $1.815 = **$34.215** storage-only, not total SaaS cost |

User count is not concurrent capacity. Assumed one object read per illustrative request and fixed retained dataset are not observed cache efficiency; real chunking/range reads, validation and cache misses change billing. Data-storage costs can be small while licensing/API/compute dominate. Separate backup storage/operations and processing, with rights for each copy. No published complete XAU SaaS fee schedule supports a defensible all-in dollar total for 100/1k/10k users; the truthful answer is the model plus quote gates.

### Decision tree and next procurement checklist

1. Is the immediate task local development? Keep current labelled M1 and authored synthetic tests without new spend; do not claim precise historical execution.
2. Need observed intrabar history? Require exact XAU paired quotes, chronological evidence, representative quality sample and retained-research rights. Evaluate HistData/Dukascopy; Darwinex only within account/coverage limits. No rights or no sample → remain candle/ambiguous; do not buy merely to avoid uncertainty.
3. Source is personal-only or retention unknown? Keep it out of external catalogs/builds. Commercial internal research also needs its own review. A provider's free software license cannot promote it.
4. Public/private beta approaching? Secure explicit end-product display + server-to-browser delivery/derived/storage rights first. Compare Twelve Data for disclosed candle product, FXCM Pro/LSEG for verified XAU ticks. If fees/retention do not fit, defer public real data rather than use personal-only archives.
5. Need gold futures instead of spot? Separate scope/instrument/experiments; Databento is a relevant paid/trial benchmark, not a drop-in XAU feed.
6. Actual audience/quota/fidelity needs exceed grant or measured economics? Re-quote enterprise/scale, preserve version-pinned prior experiments, update grants/adapters without core rewrite. No automatic purchases or next-phase execution.

Before any authorized provider contact, prepare this **unsent** checklist for each shortlisted product: exact XAU feed/provider/contributor and decimal scale; first/last event and monthly gap inventory; bid/ask pairing and tie/order semantics; sampling/filters/raw-vs-corrected variants; sample rights/API/window/rate/bulk limits; personal versus business internal use; invitation-only/public/paying-user display; server-to-browser JSON/API/export and derived candles; original/normalized/backup retention and deletion after termination; attribution/white-label; concurrent/registered user and region limits/sublicensing; quote separating acquisition, monthly/annual, tick/BidAsk/history, commercial/display/redistribution/derived/source/per-user/overage/setup/minimum fees; trial; contract validity and evidence. Request written answers, not implied grants. Budget/provider selection and sales contact remain human decisions; this research checkpoint can close without purchasing.

### Official source register

All links accessed/reviewed 2026-10-05; page retrieval failures/unsupported product facts are explicitly disclosed above. Search snippets used only as official product claims when full fetch failed; no secondary technical/price/license assertion controls a decision.

[H1]: https://www.histdata.com/f-a-q/
[H2]: https://www.histdata.com/f-a-q/data-files-detailed-specification/
[H3]: https://www.histdata.com/download-by-ftp/
[D1]: https://www.dukascopy.com/swiss/english/marketwatch/historical/
[D2]: https://www.dukascopy.com/client/javadoc/com/dukascopy/api/ITick.html
[D3]: https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/
[W1]: https://www.darwinex.com/algorithmic-trading/tick-data
[W2]: https://github.com/darwinex/darwinexapis
[F1]: https://www.fxcmapps.com/en/apps/basic-historical-data-downloader
[F2]: https://www.fxcm.com/pro/market-data/fx-price-feed/
[F3]: https://www.fxcm.com/ca/trading-tools/trading-apps/
[T1]: https://www.truefx.com/truefx-terms-and-conditions/
[T2]: https://www.truefx.com/truefx-maintenance/
[V1]: https://twelvedata.com/forex
[V2]: https://twelvedata.com/docs
[V3]: https://support.twelvedata.com/en/articles/5179078-unsupported-data-types
[V4]: https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage
[V5]: https://twelvedata.com/terms
[V6]: https://twelvedata.com/pricing
[V7]: https://twelvedata.com/pricing-business
[V8]: https://support.twelvedata.com/en/articles/5214728-getting-historical-data
[V9]: https://support.twelvedata.com/en/articles/12528665-how-the-composite-currency-feed-works
[K1]: https://www.tickdata.com/product/historical-forex-data/
[K2]: https://www.tickdata.com/forex-faq/forex-data/
[K3]: https://s3-us-west-2.amazonaws.com/tick-data-s3/pdf/TickData_File_Format_Overview_Forex.pdf
[K4]: https://www.tickdata.com/fee-estimate
[L1]: https://www.lseg.com/en/data-analytics/market-data/data-feeds/tick-history
[L2]: https://www.lseg.com/en/data-analytics/market-data/data-redistribution
[B1]: https://databento.com/catalog/cme/GLBX.MDP3/futures/GC
[B2]: https://databento.com/pricing
[B3]: https://databento.com/docs/venues-and-datasets
[B4]: https://databento.com/docs/faqs/usage-pricing-and-data-credits
[S1]: https://developers.cloudflare.com/r2/pricing/

### Deliverable coverage and checkpoint boundary

| Requested deliverables | Existing owner / location |
| --- | --- |
| 1 Requirements; 2 execution fidelity | MARKET_DATA_STANDARD: target/fidelity and no-false-intrabar-certainty |
| 3 provider matrix; 4 free assessment; 5 paid assessment | This section: technical, price and stage/tier tables |
| 6 licensing; 7 current pricing; 8 payment triggers | This section: separate rights/constraints and price/trigger tables |
| 9 personal recommendation; 10 public recommendation | This section: START NOW/research vs candle-public/tick-public recommendations |
| 11 cost scaling | This section: Stage 0–7 and TCO model; unquoted fees explicitly unknown |
| 12 migration; 13 canonical architecture; 14 registry/provenance | Existing MARKET_DATA_STANDARD: immutable pipeline/provider boundary and Dataset Registry/Passport |
| 15 storage estimate | This section: calculated 1/5/10-year low/middle/high scenarios, explicit assumptions |
| 16 risks/unknowns; 17 provider questions; 18 decision tree | This section: evidence gaps/rights constraints and unsent procurement checklist/decision steps |

Requirements/execution fidelity/canonical architecture/registry/immutable migration/quality are owned by the extended MARKET_DATA_STANDARD. This Section 42.5 owns provider/free/paid comparisons, technical fit, licensing, dated pricing, payment triggers, recommendations, storage assumptions/cost scenarios, risks, questions and decision tree. Existing ROADMAP links this research subcheckpoint without completing the unimplemented cloud service. No new documentation owner/file, runtime, dependencies, migrations, data or test assertions are changed. The bundle context allowlist adds only the pre-existing MARKET_DATA_STANDARD so future agents receive its canonical authority; backend/source/data scope stays excluded. Browser exemption is explicit: only documents/context changed; backend/full product regression is not claimed rerun. Run existing documentation/repository/bundle gates, review diff, update existing context, normal commit/push/fetch/actual GitHub equality and clean 0/0, then STOP. No Phase 24 or production data integration is authorized.

Validation evidence for this research checkpoint: `test:repository` PASS (87 reachable production files and single-authority/negative-drift controls); `test:ai-bundle` PASS; `ai:bundle` regeneration and `ai:bundle:verify` PASS (135 files after adding only existing canonical-data authority). Read-only source-reference review verifies 33 defined references without unresolved identifiers. Storage arithmetic independently recalculated from the declared inputs. Diff review is limited to eight existing documentation/context owners and one bundle-context allowlist entry; no source/dependency/data/test change or deletion. Regenerate/reverify after this evidence addition; actual Git equality/clean 0/0 remains the post-push reporting gate.

## 42.6 Local precision scope — planning only

Human direction after research: local personal/internal research first, zero new purchases; paid providers remain a future evaluation path. This planning checkpoint does not authorize runtime implementation, acquisition or cloud deployment. Operational authorization belongs to AI_CONTEXT/04_CURRENT_PHASE.md. Existing ROADMAP phase numbering remains intact; neither the cloud service nor Phase 41–43 tick capabilities are completed by this plan.

Actual baseline `16d0cf2e278cb18987e09f83f110652f09ca9da2`: frontend/src/trading/simulator.js processCandle prioritizes SL when candle ranges reach both exits; pending-entry bars evaluate exits from the close. Its tick=true option uses a single close, not paired historical quotes with verified chronology. The separate backend trading prototype also models SL-first. Existing XAU history is bid M1. These modelled results cannot be relabelled as observed tick execution.

### MUST and evidence boundary

- The existing [Market Data Standard](MARKET_DATA_STANDARD.md) remains canonical for fidelity, quality, immutable versioning, exact numeric encoding and rights. Ordered feed-specific Bid/Ask supports observed quote-side crossings; quote crossings do not prove actual executable broker fills.
- Long exits use bid, short exits use ask under an explicit profile. Pending triggers, activation and latency must be specified; pre-activation events cannot close a later position. Missing/stale sides, unresolved timestamp ties, unknown activation or relevant gaps produce a reasoned ambiguous/unresolved result. No fabricated spread, interpolation or automatic SL-first/TP-first historical claim.
- Pin dataset/version/hash, evaluator/profile versions, source event identity, chronology confidence and coverage evidence. Preserve Passport/BTL-CJSON-1 contracts; define new tick encoding before implementation using reviewed exact decimals/scaled integers. A provider change creates a new dataset and explicit rerun.
- Replay consumes only revealed events; current buckets derive only from their revealed prefix. Stream bounded chunks for large history. Ten-year coverage remains a verified acquisition target, not a claim about unmeasured files. Insufficient sampling/completeness evidence cannot support an unqualified historical-first-hit claim.
- Personal data stays outside public assets, Git publication and release bundles. Acquisition, automation, local storage, normalization and backup rights require evidence. No provider has yet passed a downloaded sample benchmark; no purchase/contact/download is authorized here.

### Separately authorized engineering checkpoints

1. Fixture-only foundation: an isolated pure evaluator and canonical tick artifact contract, authored synthetic fixtures, existing contract conventions. Inputs include activation/profile, paired events and coverage/ordering evidence; outputs identify observed crossing, unresolved reason or no crossing. No account/PnL writer, simulator switch, network calls, database or UI. Confirm module placement against protected-system authority before coding.
2. Rights-approved sample/import: separately authorize one provider and acquisition scope; immutable local artifact/registry plus measured quality report. Check ties, gaps, precision, side coverage and deterministic import; compare same-feed tick-derived candles with native bars. Unknown rights block acquisition, not fixture engineering.
3. Opt-in local replay integration: separately authorize a settlement adapter after foundation acceptance. Preserve candle mode and historical result identity; disclose fidelity. Validate market/pending activation, partial exits, SL/TP, atomic settlement, prefix replay, timeframe derivation and save/load version pins. Do not adopt the separate backend prototype as production authority by assumption.

These are bounded checkpoints, not a second roadmap or automatic implementation authorization. Runtime integration must preserve drawing, indicators, news, sessions, account and replay contracts.

Foundation acceptance: reversed ordered paths with identical OHLC; TP-first/SL-first evidence; long bid/short ask; unresolved ties versus evidenced ordering; activation boundaries; missing/stale sides and relevant gaps; no-crossing intervals; exact decimal behaviour; deterministic hashes/results; input immutability and independence from unrevealed future events. Later integration adds pending/partial settlement and persistence tests plus product browser verification.

SHOULD: representative holidays/session boundaries, volatility and large-artifact performance after licensed samples exist. DEFER: paid procurement, public redistribution, cloud delivery, live trading, broker-fill certification and unrelated product features. Zero new purchases is the current budget target; disk/CPU needs and actual coverage must be measured later. Future paid evaluation uses Section 42.5's independent price/rights inventory.

Planning validation: repository and AI-bundle tests, regeneration/verification and complete diff review; normal commit/push and actual local/origin/GitHub equality with clean 0/0. Browser, runtime regression and build/lint are exempt because this checkpoint changes only documentation; previous results are not claimed rerun. STOP before implementation.

Planning validation evidence: test:repository PASS; test:ai-bundle PASS; ai:bundle and ai:bundle:verify PASS with 135 authoritative bundle files. Documentation-only diff review; no runtime, dependency or market-data changes. Remote equality remains the post-push gate.

## 42.7 Local quote-evidence foundation — implementation checkpoint

The human authorized the fixture-only checkpoint following Section 42.6. From clean/equal `c4cdc0da70af1c3118e86bbdf1aede409645ea5b`, `backend/precision/` adds an unmounted standard-library evaluator. No existing engine, route, account writer, import adapter or UI calls it. This is local-first data preparation, not completion of ROADMAP Phase 23 cloud delivery or Phase 41–43 tick capabilities. The earlier Phase 39 tick reference was corrected against the actual roadmap (39 is Monte Carlo).

BTL-TICK-EVIDENCE-1 reuses BTL-CJSON-1 without modifying Passport/canonical contracts. Frozen Quote/Request/Decision values retain instrument/feed, dataset/version/hash, profile version, source IDs/sequence, freshness/gap flags, exact Decimal prices and native integer nanosecond timestamps. Times serialize as decimal strings, avoiding unsafe JSON integer precision. Maximum revealed artifact is 1024 quotes within existing canonical node/size limits; this is not long-history streaming.

`evaluate` checks declared coverage and chronology, then tests long bid/short ask. Outcomes: OBSERVED_CROSSING, UNRESOLVED, NO_OBSERVED_CROSSING. Reasons distinguish gaps, missing/stale/crossed sides, ties, unknown same-time activation and invalid chronology/sequence. Trusted sequence and completeness are caller evidence assertions, not inferred/certified provider facts. NO_OBSERVED_CROSSING concerns supplied quotes, never proves absence of an intermediate unobserved price. Observed crossing returns actual quote price, not an invented broker fill at the threshold.

`evidence_bytes` and `load_evidence` provide deterministic serialization and strict SHA-256/canonical/schema/shape-checked roundtrip. They reject corruption, unknown fields, alternate encodings and hidden suffixes. Hashes establish byte integrity, not provenance authenticity. Evaluator accepts immutable inputs and excludes unrevealed chronological suffix before hashing, with no interpolation, sorting, quote repair or account mutation. Producer must provide an ordered prefix; this is not a raw-file validator.

Eleven new test methods cover reversed TP/SL paths sharing candle ranges, sides, ties/sequence, activation, coverage/quality refusal, duplicate/order errors, hidden-prefix independence, immutability/version identity, Decimal-context independence, exact roundtrip/corruption, bounds and maximum chunk. Pending triggers, partial exits, fills/PnL, sample imports, streaming and production integration remain deferred. No provider acquired/contacted/paid and no market data/dependency changed.

Validation: frontend full regression, lint, build and release audit PASS; independent Node canonical vectors PASS. Backend full discovery with isolated real PostgreSQL PASS: 114 tests, no skips. Initial discovery failed one existing account-rate test across its fixed-minute bucket; repeated unchanged authentication/test code away from that boundary passes. Existing Starlette/httpx deprecation warning remains. Final precision tests PASS after tightening oversized timestamp rejection (11 methods). Repository and AI-bundle tests, bundle regeneration and verification PASS after context updates (135 files; new backend sources remain outside the existing bundle scope). Browser exemption: isolated evaluator has no mounted API or browser consumer; production frontend is unchanged. QA PostgreSQL stopped after tests. Normal push/equality and clean 0/0 precede completion; STOP before sample acquisition or integration.

## 42.8 Personal HistData sample and offline parser checkpoint

From clean/equal `5ebfbfae8f83d77fe2e9f69732a53c95486b0e15`, the human authorized selecting/evaluating a free personal XAUUSD sample, with a local importer and replay integration conditional on evidence acceptance. This checkpoint completes the bounded sample evaluation and offline parsing seam; precision acceptance remains incomplete, so no replay cutover occurs. No Phase 24/cloud service/public-data launch or paid procurement is implied.

### Rights decision before acquisition (reviewed 2026-10-05)

HistData's [official FAQ](https://www.histdata.com/f-a-q/) offers downloads for backtesting/import. Its [download page](https://www.histdata.com/download-free-forex-data/) describes Generic ASCII import into third-party applications. Its [merge instructions](https://www.histdata.com/f-a-q/data-files-merge-tool/) explicitly describe local ZIP/CSV folders and locally produced merged files. These support the narrow operational decision to acquire one offered month and retain/import CSV for this user's personal local evaluation. This is an interpretation of the documented download/import purpose, not a negotiated license, a general commercial grant or proof of perpetual retention rights. Broader automated bulk collection, cloud backups, public display, raw/derived redistribution and SaaS are NOT approved. Retain the original copyright-bearing status sidecar; no separate attribution waiver is assumed. No vendor contact or account/payment was required.

Dukascopy was not acquired: its [Terms of Use, Restrictions on Use](https://www.dukascopy.com/swiss/english/legal-pages/terms-of-use/) allow limited personal downloading but separately restrict automation and database construction. Its technical export guide does not expressly reconcile those restrictions for this task. HistData was selected for this bounded local evaluation, not declared the best or globally complete feed. Public rights remain unresolved for both routes.

### Acquired evidence and reproducible measurements

Official download form: `https://www.histdata.com/download-free-forex-historical-data/?/ascii/tick-data-quotes/xauusd/2025/1`; fields identify ASCII/XAUUSD/T/202501. One archive is 40,095,748 bytes, SHA-256 `8653c8c14951e5b84315090f7e813ff38325223b59e1ad8c702e4e4fb78af51d`. Its CSV member is 260,920,170 bytes. Provider offers monthly files rather than one-hour download, so only one monthly archive was fetched and one hour selected for detailed tests. ZIP was streamed without extracting member paths; bounded acquisition caps compressed input at 64 MB. Original source bytes and copyright notice are retained.

All raw/selected data, normalized evidence, rights record and price-bearing quality report reside in `%LOCALAPPDATA%/Temp/btl-personal-xau-sample-202501/`, outside Git, OneDrive, public assets and release/bundle paths. This temporary machine-local location is not a durable registry or cloud backup. Repository records only audit metadata/counts/hashes and authored tests, not provider quote rows or price-bearing reports.

| Actual check | Result and boundary |
| --- | --- |
| Monthly member scan | 5,798,226 rows; zero adjacent timestamp ties and backward timestamps. This is lexical fixed-format chronology scanning, not full-month price/quality validation |
| Detailed sample | 2025-01-10 13:00–14:00 UTC, selected from fixed EST 08:00–09:00; 25,095 quotes |
| Validity/order | 25,095 valid, zero invalid/crossed/nonpositive/nonfinite rows; zero timestamp ties, backwards rows or adjacent exact repeats in the selected interval |
| Spread/gaps | Zero zero-spread rows; zero intervals >60 s; maximum observed inter-record interval 7.67 s. This is not proof that no quotes were lost |
| Additional rollover window | 2025-01-02 21:30–23:30 UTC; 1,835 quotes, zero invalid/tied/backward rows, one interval >60 s, maximum 3,606.684 s |
| Additional reopening window | 2025-01-12 22:30–2025-01-13 00:30 UTC; 6,208 quotes, zero invalid/tied/backward rows, one interval >60 s, maximum 144.212 s |
| Sample identity | Raw selected bytes SHA-256 `fea63cdacc275e8dccf5651d87b3a9a26c63626099f39763d78c490a692df826` |
| M1 cross-validation | Tick-derived bid OHLC matches all 60 existing same-feed M1 buckets exactly, zero missing/mismatched; read-only reference `frontend/public/market/decade/2025-01-1m.json`, SHA-256 `0a3d986c6eb0b151960076c4f5ea7b4b380ea7e370c2abe41c8c76a8fab58e8f` |
| Determinism/serialization | Repeated offline inspection identical; first 1024 quotes canonical-serialized and hash-checked roundtrip yields identical evaluator decision |
| Evaluator | UNRESOLVED / INSUFFICIENT_COVERAGE with coverage_complete=false; provider completeness is not manufactured to obtain TP/SL |

### Implemented seam and remaining acceptance

`backend/precision/histdata.py` parses the official [ASCII tick specification](https://www.histdata.com/f-a-q/data-files-detailed-specification/): four fields, millisecond timestamps, fixed UTC−5 without DST and exact Bid/Ask decimals. Original ordinal identifies rows but is not a trusted event sequence; volume is validated as source data, not promoted to measured market volume. Missing per-side update-age evidence leaves fresh=false. The bounded streaming inspector counts invalid/order/tie/adjacent-repeat/spread/gap evidence without sorting, deduplicating, filling or silently repairing. Maximum 100,000 rows per diagnostic interval. It never downloads, writes files, touches a database/account or integrates replay.

Six authored tests cover fixed-EST summer conversion/milliseconds, ordinal/freshness honesty, invalid calendar/fields/prices/volume, ties/repeats/gaps, poisoning by malformed/order errors, bounds/empty streams and deterministic exact spreads. Existing eleven evaluator tests remain intact. Native M1 and current simulator are untouched. Full backend discovery PASS: 120 methods, real isolated PostgreSQL, no skips; frontend full regression/lint/build/release and independent Node canonical vectors PASS. Existing Starlette/httpx deprecation warning remains; QA PostgreSQL stopped afterwards. Browser exempt for the unmounted offline seam with no product consumer. Repository and AI-bundle tests, regeneration and verification PASS (135 files) after context update; reverify final metadata edits before normal push, actual GitHub equality and clean 0/0.

Structural checks pass for three limited windows (33,138 inspected quotes); observed rollover/reopening gaps remain unclassified without an evidenced feed/session calendar. A gap may be closure or outage; neither explanation is assumed. Global completeness, source sequence at ties, per-side freshness, broader holidays/stress/filtering and decade interval coverage remain unverified. The provider sidecar also reports gaps; its aggregate interval numbers are provider claims, not our measurements. Do not promote this to fidelity-1 certification or historical broker-fill proof. Next scope should resolve evidence policy and extend representative personal sample testing, keeping uncertainty explicit. No automatic large-history acquisition or production integration; STOP after this checkpoint.

### 42.9 Local evidence policy and read-only audit checkpoint

From verified clean/equal cc203288d78002466fa99e02e48b16c5862fad88, the human authorized local progress retaining ambiguity. backend/precision/policy.py wraps the existing evaluator without changing BTL-TICK-EVIDENCE-1. [Market Data Standard](MARKET_DATA_STANDARD.md#evidence-promotion-and-truthful-outcomes) remains policy authority. Hash-bound ReviewedEvidence references are separately reviewed caller declarations, not automatic provider verification, signatures or grants. They retain or downgrade flags, never upgrade missing evidence. No wire certainty override is mounted.

Immutable BTL-PRECISION-POLICY-1 reports provide deterministic input/policy hashes and full revealed-interval issue scope. Outcomes are AMBIGUOUS, OBSERVED_QUOTE_CROSSING or NO_OBSERVED_CROSSING, always NOT_SIMULATED with null fill/PnL. Quote crossings do not prove broker executions. The read-only CLI takes an artifact and expected SHA-256 without certainty overrides or writes. Hidden future suffixes cannot affect reports. Candle modelling, financial writers, replay, dependencies and market datasets are unchanged.

Read-only assessments of the first 1,024 quotes in each existing private normal-hour, rollover and reopening window all remain AMBIGUOUS: coverage and freshness are unverified. Diagnostic silence counts are 0, 1 and 1; these cannot classify closure versus outage. Threshold scenarios on real quotes are authored, not actual trades. Deterministic repeat/future-suffix checks passed. Price-bearing reports stay outside Git/OneDrive/public assets. No new download, purchase or provider contact.

Thirteen new policy test methods cover references/flags, exact hash scope, chronology/activation/gaps, silence diagnostics, future isolation, canonical immutability, financial-claim refusal and read-only CLI. Full backend discovery passed 133 methods with real isolated PostgreSQL and no skips; QA server stopped afterwards. Full frontend regression, lint, production build, release audit and independent Node canonical vectors passed. Existing Starlette/httpx warning remains. Browser exempt for the unmounted module: no UI/API/product consumer changed. Repository and AI-bundle tests, regeneration and verification PASS (135 files); normal push/actual GitHub equality remain checkpoint gates.

Only this evidence-policy checkpoint is complete. Actual sample completeness/freshness remain unresolved; reference authenticity requires external review. Local Tick Review integration needs a separately bounded scope preserving ambiguity and forbidding fictional settlement. Cloud delivery and later roadmap phases remain unimplemented; STOP after this checkpoint.

## 42.10 Local Tick Review — bounded preparation, planning only

### Authorization and existing seams

From clean/equal 6f226c6750dc5e347174e21cd1ce83f280758108, the human accepted the proposal to begin a short Local Tick Review plan before bounded implementation. This checkpoint changes documentation only, not runtime. Operational status belongs to AI_CONTEXT/04_CURRENT_PHASE.md. This does not complete Phase 23 cloud delivery or ROADMAP Phase 41–43, introduce another roadmap, acquire data or authorize future implementation automatically.

Actual seams: backend/precision/evaluator.py owns immutable BTL-TICK-EVIDENCE-1 and evaluation; policy.py owns BTL-PRECISION-POLICY-1 assessment and a read-only CLI; histdata.py owns offline normalization/diagnostics. frontend/src/main.jsx is the sole React entrypoint, currently selecting FigmaWorkspace or its opt-in trading prototype. useTrading.js owns account mutation via simulator.js; replaySettlement.js owns candle settlement. The proposed reviewer must import none of these financial writers or the replay/market loaders. Existing chart and drawing code stay untouched.

Canonical evidence rules remain in [Market Data Standard](MARKET_DATA_STANDARD.md#evidence-promotion-and-truthful-outcomes); first-supplied-price MODELLED simulation remains in [existing trading owner](PHASE14_TRADING_UX_BACKTEST_ANALYSIS.md#first-supplied-price--authorized-simulation-gap-policy). The reviewer cannot convert either into broker-fill evidence.

### Proposed next implementation checkpoint — MUST only

A read-only, opt-in local viewer, entered through the existing main entrypoint at `/?tick-review=local` on a loopback origin. Default workspace and trading prototype behavior must remain unchanged; the reviewer is lazy-loaded and has a Back to workspace action. Fail closed on unsupported/nonlocal origins. This origin check prevents accidental product exposure, not authentication or a grant to redistribute data. No mounted backend route, local HTTP data service or cloud transport is required.

The user explicitly selects two already prepared private local files: the exact canonical tick artifact and its assessment produced by the existing Python CLI. Do not automatically search the filesystem, load archived monthly CSVs, download data, scan user folders or ship quote data in frontend/public. File contents stay in this review component's memory; no localStorage/IndexedDB, account writes, analytics, network upload, console quote logging or export/share action. Reset/replacement/unmount releases references and cancels pending reads so an older load cannot replace a newer selection. Original files are never modified. Rights stay bounded to the existing personal-local sample purpose in Section 42.8; public display/SaaS/cloud backup remain outside scope.

| Review responsibility | Required behavior |
| --- | --- |
| Import integrity | Bound each file to 1 MiB and tick count to 1,024; strict version/shape/type/canonical-byte validation before accepting. Preserve artifact bytes exactly; the CLI assessment may have exactly one terminal LF from stdout, which the report reader may remove before canonical verification (no arbitrary whitespace normalization). Verify artifact SHA-256 equals report.inputHash and report.policyHash equals canonical payload hash excluding policyHash. Bind any declaredEvidence.artifact_hash to inputHash. Reject unknown versions/fields, malformed input, cross-file mismatch, truncated/oversize files and financial claims. No partial success or stale previous result on failure. |
| Canonical parity | Browser codec is a bounded verifier of the existing BTL-CJSON-1 wire subset, not a new encoding. Use standard Web Crypto SHA-256, exact UTF-8 and existing golden vectors. Match Unicode code-point key ordering/escaping, safe integer limits, node/depth/string limits and exact canonical bytes; reject ambiguous alternate representations. Preserve timestamps/prices as strings/BigInt, never round them for evidence calculations. Do not change Passport or Python canonical contracts. |
| Trust disclosure | Matching hashes show consistency, not provider authenticity, signature, trustworthy execution or proof the evaluator was run. Render assessment as a supplied local evaluator report, including version/provenance and declarations; no browser certainty checkboxes or overrides. Do not rerun or duplicate TP/SL logic in JavaScript. Recognize that quoteDecision input hash describes the effective policy inputs, not necessarily the original artifact hash; never conflate those two identities. |
| Quote table | Original order, event ID, exact UTC timestamp with native precision, exact bid/ask strings, source sequence where supplied, freshness/gap declarations, elapsed time to prior visible quote. Pagination bounded to 50 rows. Display missing values as unknown; never sort, repair, fill gaps or call source ordinal trusted sequence. No chart engine replacement or new tick chart required. |
| Reveal boundary | Only artifact quotes at or before its horizon, with explicit activation/horizon and dataset/feed/version/profile identity. Clearly label this bounded supplied window, not entire month/decade. Strictly refuse future suffix rows rather than reveal them. No rewind/playback control or connection to workspace replay in this checkpoint. |
| Findings | Display AMBIGUOUS, OBSERVED_QUOTE_CROSSING or NO_OBSERVED_CROSSING from the validated report; show raw reason codes with plain-language explanation. Unknown coverage/freshness does not mean proven bad/stale data. Locate the observed event by ID only when present/consistent; quote price is not fill. Reject inconsistent supplied classifications/events rather than invent a replacement result. |
| Gaps | Show declared gaps and long-silence diagnostics separately. Use the report's positive bounded threshold and BigInt time arithmetic for table intervals. Diagnostic issues apply to the full supplied revealed interval. Silence does not identify market closure/outage, and later issues do not retroactively reorder an earlier crossing. |
| Financial separation | Always display NOT_SIMULATED, fill/PnL unavailable; reject non-null fill/PnL or settlement claims. The first-supplied-price simulation rule may be linked as a separate explanation but cannot be applied to this evidence report or account. No order entry, TP/SL editor or balance mutation. |
| Accessibility | Reuse current visual tokens and simple panel/table treatment; readable narrow layout, keyboard file selection/pagination/reset, visible loading/error/empty states and screen-reader labels. Render imported strings as text, never HTML. No overall redesign. |

Suggested narrow file footprint after explicit implementation authorization: new frontend/src/tickReview/LocalTickReview.jsx, ReviewImport.js and a scoped style file only if needed; small guarded lazy selection in existing main.jsx; focused new tests registered in the existing package test workflow plus an isolated browser harness. These proposed filenames are module responsibilities, not a second project/source tree. Prefer existing tokens/standard browser APIs; no new dependencies unless a demonstrated compatibility need is reviewed. Backend modules, contracts, private datasets and chart/replay/trading paths remain unchanged. The narrow main-entry/test-registration modifications need repository boundary regression; do not widen bundle scope without reviewed evidence.

### Existing provider evidence audit and remaining gaps

This checkpoint audits stored evidence in Sections 42.5/42.8, not a new provider guarantee or fresh legal review. Existing ASCII evidence specifies paired price columns, timestamps, fixed source timezone and import format. Existing measurements establish structural validity in limited windows and same-feed M1 agreement. Neither establishes all recorded-feed events, per-side update age, source sequence at ties, closed-session boundaries or authoritative broker execution. There is no stored reviewed evidence sufficient to promote the three real sample assessments; keep them AMBIGUOUS.

Future evidence requests, currently unsent: documented row semantics (fresh paired snapshot versus updates retaining the other side), applicable sampling/filtering/corrections, complete interval manifests and loss handling, authoritative timestamp/sequence semantics, instrument/feed session calendar and gap explanations. Any stronger semantics require source review and a new pinned artifact/version; references cannot upgrade existing false flags. Provider contact, new acquisition, paid feeds and public rights negotiation require separate authorization. The viewer can be useful while these facts remain unknown.

### Acceptance and protected limits for implementation

MUST acceptance: authored long/short crossing, no-crossing and ambiguous reports; missing sides/ties/activation/gaps/unknown freshness explanations; mismatched/tampered hashes, fabricated financial fields, duplicate/unknown fields, excessive depth/nodes/rows, malformed Unicode/time/price, unknown versions and hidden future refusal; raw strings cannot execute HTML; exact golden bytes/hash parity; cancellation/replacement/reset; table pagination and mobile/keyboard access. Authored data stays labeled synthetic. Manually selecting existing rights-approved real sample pairs should reproduce the current ambiguous findings without committing samples or price-bearing reports.

Run focused verifier/view tests, full frontend regression, lint/build/release, repository and AI-bundle tests plus regenerate/verify bundle; real browser test file selection, errors, table/reasons/reset, default workspace/prototype smoke and console checks on an isolated origin. Verify no account/storage/network side effects or imports of financial writers. Backend full regression is required only if implementation unexpectedly changes its consumers/contracts; such expansion is outside this proposed checkpoint and should be removed or separately scoped. Review complete diff, update existing authorities, commit/push and verify actual GitHub equality plus clean 0/0, then STOP.

DEFER: tick-driven account settlement/replay, large-history streaming/acquisition, coverage/freshness promotion without evidence, TP/SL model redesign, commissions/slippage/liquidity, production backend endpoints, database/cloud/login changes, public-data rights, new chart engine/drawings, UI redesign or paid procurement. No implementation started in this planning checkpoint. Documentation-only browser/product/backend regression exemption: no runnable path, tests or dependencies changed. Planning validation: repository single-authority/boundary tests and AI-bundle determinism/drift tests PASS; bundle regeneration/verification PASS (135 files). Final bookkeeping is reverified before normal Git checkpoint/equality and STOP.

## 42.11 Local Tick Review — implemented read-only checkpoint

Human implementation authorization followed Section 42.10 from verified clean/equal 7cc0c627c5e2fcede75aa8c0b918b650af3fc2e0. The existing frontend main entrypoint now supports `/?tick-review=local` only for exact loopback hostnames. LocalOrigin is the small eager gate; TickReviewEntry lazily loads LocalTickReview and its verifier. Other origins get a refusal screen. This is an accidental-exposure guard, not authentication or a redistribution grant. Default workspace/prototype selection remains unchanged. No new project, backend route, account/replay integration or dependency.

ReviewImport verifies two explicitly selected files using standard FileReader, fatal UTF-8 decoding and Web Crypto SHA-256. Bounded BTL-CJSON-1 wire verification matches existing golden bytes/hash, Unicode code-point key ordering and safe integers; schema/field/node/depth/price/time limits and canonical equality refuse alternate representations. Artifact bytes stay exact; reports may contain one CLI stdout LF or Windows CRLF only. The viewer checks original input, policy payload and effective gated-input hashes separately; reviewed references bind to original artifact identity. It verifies report shape/consistency and known event identity, not first-crossing execution logic: there is no second JavaScript evaluator. Matching self-consistent hashes neither authenticate a provider nor prove the evaluator ran. The supplied-report trust warning remains visible.

Limits: 1 MiB per file, 1,024 quote records, 50 rows per page. Exact original order/prices and native UTC nanoseconds remain strings/BigInt; contract times beyond browser Date range display exact epoch nanoseconds with an explicit calendar-range explanation rather than rounding or crashing. Missing sides, chronology/ties, gap and freshness declarations remain visible. Results are AMBIGUOUS / OBSERVED_QUOTE_CROSSING / NO_OBSERVED_CROSSING, always NOT_SIMULATED and null fill/PnL; non-null financial claims are rejected. The viewer cannot apply the separate gap simulation to account settlement. Metadata and preparation instructions use expandable details; authored metadata is labeled synthetic. Scoped styles reuse existing design tokens without changing the workspace.

Input replacement/reset/unmount cancels FileReader and invalidates pending reads/hash results. Failure removes old/partial results. Component memory is the only data destination: no account hook, storage write, upload, quote logging, export/share or market/replay loader. Existing root stylesheet/font resources remain ordinary application assets, not quote-data transport; this checkpoint does not claim a new offline distribution. No original file is rewritten. Existing private samples remain outside Git/public assets; no download/provider contact/purchase.

Validation evidence:
- New registered test:tick-review covers 18 durable Python-evaluator-authored synthetic artifact/report vectors, six existing canonical golden vectors plus Unicode/numeric-key ordering, positive 1,024-row acceptance, specific malformed-shape/price/future/oversize refusal, tamper/mismatch/financial claims, exact timestamps, bounds and delayed read/hash cancellation/replacement. Fixtures contain no provider data. Backend precision/evaluator/parser 30 methods and independent Node vectors PASS; legacy backend/auth/DB code is unchanged, so full DB-suite rerun is exempt for this bounded file-view seam.
- Full frontend regression, lint, production build and release audit PASS. Repository/bundle boundary and determinism tests PASS; regenerated bundle verification PASS (142 files). Final metadata edits are reverified before commit. Review component/verifier/codecs reside in the lazy chunk; default chart and trading remain owned by their existing modules.
- Actual isolated dev browser: paired file selection succeeds; authored long TP and short SL crossing, no-crossing and declared-gap ambiguity display correctly. 55-row fixture paginates 50/5. Malformed report and oversized artifact are refused with no stale result; Reset and keyboard Enter work. The existing private normal-hour artifact/report remains AMBIGUOUS with coverage/freshness/insufficient-coverage reasons, 50 visible rows and no fill/PnL. Private prices/reports were not published or added to fixtures.
- Legacy account seeded only through the existing isolated Phase 14 QA harness remains byte-identical in local/session storage on entering the viewer and after report replacement. Initial empty-storage checks also remain unchanged. Default workspace and existing trading prototype smoke PASS; review/default/prototype console checks show no warnings/errors. Mobile 390×844 initially exposed a 2px file-input overflow, corrected with bounded inputs; final page width equals viewport, table scroll stays inside its region. Temporary viewport was reset. Actual production-build browser on a separate loopback port also imports the existing normal-hour pair successfully: same AMBIGUOUS status/reasons, 50 rows and no console warnings/errors.

A reviewed narrow bundle addition includes exactly the five new frontend review modules/styles and two authored test/fixture files, so the changed main entrypoint's new dependencies and review evidence are available to future AI review. No backend/private data/vendor/dependency scope expansion; the bundle remains a nonrunnable disposable reference and golden vectors remain in their existing master location. No second documentation authority or roadmap was created.

All real-sample uncertainty is unchanged; this is evidence inspection, not historical broker-fill proof or tick settlement. Phase 23 cloud delivery and Phase 41–43 remain unimplemented. Next work needs a bounded evidence-review scope (existing source semantics/coverage/sequence/calendar), without promoting unknown flags or automatically acquiring/contacting/purchasing. Required Git completion: diff review, existing context/status update, normal commit/push, actual GitHub equality and clean 0/0, then STOP.


## 42.12 Existing precision-evidence review — ambiguity retained

The human asked to continue after discussing consecutive phases, explicitly retaining ambiguity for later per-trade inspection. From verified clean/equal `acbc4e27a49effb2adc5cfc6bb54d5ad2d01bb2b`, this bounded checkpoint audits existing code and recorded sample evidence and defines the review scope. It does not authorize three unspecified roadmap phases. No new provider claims, purchases, contacts, downloads, financial integration or cloud delivery. ROADMAP remains the sole roadmap; Section 42.6 remains the prior integration proposal, not an automatic execution instruction.

### Evidence inventory and disposition

| Question | Existing evidence | Disposition for this checkpoint |
| --- | --- | --- |
| Exact prices and time conversion | histdata.parse_tick uses exact decimals and fixed UTC−5; timestamps retain supplied milliseconds | Structural representation supported, not broker accuracy or sub-millisecond ordering |
| Recorded-feed completeness | Three limited-window measurements in Section 42.8; normal-hour tick bid OHLC matches 60 same-feed M1 bars | UNKNOWN; OHLC equivalence, quiet intervals and clean parsing do not prove all events present |
| Side freshness | Parser deliberately creates fresh=False; original rows do not carry per-side age evidence | UNKNOWN, not proof that sides are actually stale; do not override to true |
| Chronology and activation | Recorded sample has no measured ties/backwards rows; source ordinal is row identity, not trusted sequence | Preserve supplied order; equal-time activation remains unresolved; no claimed venue sequence |
| Silence/session meaning | Recorded maxima 7.67 s, 3,606.684 s and 144.212 s; no scoped feed calendar in artifacts | UNKNOWN closure versus outage; duration is diagnostic, not an automatic corruption classification |
| Decision integrity | Policy binds original/effective inputs; viewer validates canonical bytes and hashes | Integrity only, not provider authenticity or independent proof evaluator was executed |
| Trade settlement | Policy returns NOT_SIMULATED with null fill/PnL; viewer has no account/replay consumer | No actual tick trade execution, automatic settlement or trade-account association exists |

This is a source/recorded-evidence audit, not a fresh remeasurement of the monthly archive or a new provider licensing review. Private samples stay outside Git, cloud assets and AI bundles. Existing personal-local interpretation in Section 42.8 is neither expanded nor asserted current public/SaaS permission.

### Per-trade review boundary

The user may inspect one explicit LONG/SHORT threshold scenario with its pinned artifact/report in the current Local Tick Review. That scenario is not automatically an existing executed trade: the current contract has activation/horizon, SL/TP and side, but no canonical account trade ID, pending-entry rule, entry settlement or partial-exit lifecycle. Do not claim a trade review feature or financial reconciliation is implemented merely because scenario quotes are displayed.

For later human-reviewed cases, require the dataset/version/feed/profile, exact activation and horizon, side/thresholds, original artifact and report hashes, supplied event identity/order, coverage/freshness/sequence declarations and reasons. If mapped to a real account trade in a separately authorized future scope, retain its immutable trade identity and original MODELLED result separately; a review must never overwrite it. User annotations or visual inspection do not promote uncertainty. Proposed TP/SL, entry or gap-fill alternatives remain hypotheses until independently evidenced and explicitly implemented. Historical ambiguous cases retain their original identity even if a later dataset improves evidence.

No unresolved case is settled as TP or SL here. OBSERVED_QUOTE_CROSSING remains a supplied quote observation, not a broker fill; NO_OBSERVED_CROSSING does not exclude an unobserved crossing. The already-authorized frontend first-supplied-price simulation remains MODELLED under its existing Phase 14 owner; this audit does not change or relabel those results.

### Bounded handoff and acceptance

The next possible product task is a separately scoped, read-only per-trade/scenario review improvement: first identify whether the user wants inspecting manually supplied scenarios or linking existing MODELLED account trades. Define identity, activation semantics, privacy and preservation acceptance before implementing such a link. Provider-evidence remediation can wait until the user reviews ambiguous cases; it is not a prerequisite for inspection and is not silently pursued here. Unknown evidence remains unknown. No new paid feed, bulk download, calendar inference, confidence override, account settlement or cloud phase is included.

Phase 23 cloud delivery remains unimplemented; Phase 24 pipeline, Phase 25 cloud sessions and Phase 26 synchronization depend on their existing scoped contracts and must not be represented as completed by local evidence work. This review adds no competing phase numbering or roadmap.

Validation is documentation-only: repository/AI-bundle checks and regeneration/verification, plus focused existing precision and viewer tests as a conservative evidence-contract check. Browser, full product regression, lint/build and DB/auth rerun are exempt because no product/runtime/dependency/data/test files change; earlier browser or release results are not claimed rerun. Review complete diff, update existing context/status, commit/push normally, verify local/origin/actual GitHub equality and clean 0/0, report and STOP.

Validation results: test:repository PASS; test:ai-bundle PASS; test:tick-review PASS (18 authored pairs plus bounds/refusal/race cases); backend precision/policy/parser 30 methods PASS. No new provider samples were measured. Bundle regeneration/verification and normal Git equality remain final checkpoint gates.


## 42.13 Phase 23 local-first historical delivery infrastructure

The human explicitly resolved the prior local/cloud mismatch: implement for personal local use now, structure infrastructure for later publication, and defer paid data. This supersedes the earlier implementation prohibition for this isolated local delivery scope only. Baseline: clean/equal main 24c2b1d73a58e334d8049f55ad9f85728bb0e532. No procurement/contact/download/deployment or implicit public grant. This completes the bounded local delivery foundation, NOT the ROADMAP cloud launch capability. Existing Phase 20–22 identity/membership remain intact for a later reviewed authenticated adapter.

### Implemented product boundary

`backend/market_data/service.py` owns immutable dataset/chunk descriptors and a portable DataService over ArtifactStore and AccessPolicy protocols. `local.py` implements the explicit operator-selected directory adapter for existing HistData XAUUSD bid M1 files. `serve.py` implements the local-only FastAPI transport, reusing installed libraries rather than adding dependencies. No alternate trading engine, ingestion pipeline, account migration, frontend data cutover or second roadmap.

Activation scans and structurally validates every manifest M1 chunk before constructing the catalog. Version identity binds ordered normalized raw-byte hashes, byte sizes, counts, temporal boundaries, source/instrument/side and adapter normalization version. Archive hashes remain separate historical evidence. Reads recheck chunk bytes/hash and shape; corruption/change fails safely rather than silently rebuilding a version. Restart rebuilds the same identity from unchanged artifacts. New bytes require a new version and explicit request. Exact existing JSON decimal tokens are parsed as Decimal and returned as decimal strings, preserving the stored representation without inventing original provider precision. No deduplication, sorting, repricing, gap filling or fabricated volume.

The descriptor discloses PERSONAL_LOCAL, M1_OHLC, BID, unavailable volume, unknown completeness/freshness and publicDisplayApproved=false. This is preservation of the user's existing local dataset use, not a new legal grant or new rights verification. Original private tick files remain outside the service/Git/public assets. AMBIGUOUS remains explicit; responses have NOT_SIMULATED/null fill/PnL. Default frontend candle MODELLED execution and read-only tick viewer are unchanged.

Local routes:

- GET `/api/v1/local-market/dataset`: pinned descriptor/catalog, including chunk hashes but no filesystem paths.
- GET `/api/v1/local-market/candles?version=<catalog-version>&start=<UTC-seconds>&end=<exclusive-UTC-seconds>&limit=1000`: exact existing M1 rows, `more` and `nextAfter`. Subsequent page repeats the same version/range with `after=<nextAfter>`. No opaque cursor or server Session claim.
- Optional `revealedBefore` is a caller-controlled research filter: include a full minute only when candle time+60 <= bound. It is NOT a server-authoritative trading replay cutoff. Future adapter MUST resolve identity/workspace/BACKTEST/revision/revealed bound on the server under existing security contracts before strict Session delivery. No higher-timeframe responses are offered here.

Bounds: maximum 32-day range, requested limit 1–10,000, actual canonical page <=2,000 rows with explicit continuation (existing canonical node budget), 1 MiB response refusal, 2 MiB raw chunk, <=40,000 rows/chunk, <=240 chunks, <=2,048-byte query, two concurrent file-read workers and 30 requests/minute/process. Checksummed month reads are bounded and uncached; hashes are not provenance certification. Large pathological exact decimal responses may fail the canonical/byte limit rather than silently truncate. Missing intervals remain missing. No network provider/SSRF/file path query capability.

Only loopback binding is supported, with exact localhost/127.0.0.1 Host+port and loopback client validation, no trusted forwarded address, no CORS, no Origin-bearing/cross-site requests, no body/write methods, unknown/duplicate query refusal and no-store. This adapter is for same-machine personal tools; host/origin checks are not public authentication or protection from a compromised local machine. Do not reverse-proxy it as public SaaS. Its optional filter is not a security boundary. No secrets or quote rows are logged by access logging.

### Local runbook and future adapter

From backend, with the existing Python environment and installed backend requirements:

```powershell
./venv/Scripts/python.exe -m market_data.serve --root ../frontend/public/market/decade --port 5199
```

The root is operator configuration, never HTTP caller input. Startup validates 120 chunks before accepting connections; allow initial scan to finish. The default workspace remains served by its existing frontend process. This service adds API infrastructure, not a new screen or automatic chart switch. Stop with Ctrl+C. Reconstruct on restart from unchanged files; a changed catalog version must be explicitly selected, never silently adopted. Back up unchanged source directory/manifest outside public hosting according to applicable rights, restore into a distinct private directory and compare descriptor/version before use; authored restore/reopen test verifies determinism. No cloud backup is authorized here.

For later publication, implement a separately reviewed ArtifactStore/access/transport adapter using existing verified identity + workspace membership, immutable metadata/grants and private object storage. The current PersonalLocalPolicy must never be reused as cloud authorization. Unknown/revoked/public-ineligible rights deny serving real data. A paid provider can supply a separate version/feed without rewriting the service, but needs an explicit adapter/normalization contract and applicable license first. Authenticated SaaS is still external distribution. Preserve the two audience lanes. Phase 24 automated ingestion, Phase 25 sessions, Phase 26 sync and tick settlement are not included. Do not publish the unchanged frontend dist with its current personal dataset assets; moving real data behind a private adapter and removing publicly shipped data from a separately authorized distribution is a future launch gate, not a deletion in this task.

### Acceptance evidence and limits

Nine new authored tests cover exact immutable output/reopen identity, pagination/gaps/completed-prefix boundaries, mutation/version mismatch, path traversal/malformed inventory, bad prices/time/order, input/byte/page limits, public-audience refusal, origin/host/nonloopback/write/query refusal, rate limits and hidden-future quote-output independence. Existing precision/evaluator/parser 30 tests pass (39 total); six independent Node golden vectors pass. Full frontend regression/lint/build/release pass. No backend cloud/auth/DB schema or consumer changed, so full DB/auth rerun is exempt for this standalone local adapter; no skip is counted as a full release PASS. Browser adapter exemption: no frontend path changed; real localhost HTTP smoke exercises actual transport and existing data. Prior viewer browser evidence is not claimed rerun.

Actual local startup validates all 120 existing M1 chunks, 3,486,461 candles. Catalog version `7610c53c7a320f711bf63e7d91a66e07a1c6797af2ed45dc86761a8b46ccadea`; one actual 100-row localhost read measured 330 ms (single observation, not SLA), status LOCAL_RESEARCH/AMBIGUOUS with null fill/PnL. Initial request before the scan finished was refused; retry after startup succeeded. No source bytes were rewritten or copied. This test does not certify provider completeness, tick fidelity, cloud load, public rights or broker fills.

Required final gates: repository/bundle tests and generation/hash verification, complete diff review, current status/history updates, normal commit/push and actual local/origin/GitHub equality with clean 0/0. The bounded local scope closes; public cloud delivery stays DEFERRED pending separately scoped infrastructure/security/rights/deployment acceptance. STOP before Phase 24, frontend cutover or account/tick integration.


## 42.14 Tick-native decision, Exness candidate and migration audit

### Authorization, baseline and result boundary

Human-supplied master prompt authorizes ONLY actual repository audit, a minimal official Exness XAUUSD sample if available/permitted, semantic/quality and canonical compatibility assessment, and staged migration design. It expressly forbids engine replacement, financial settlement/account migration, deletion, large-history download or cloud publication. Baseline verified 2026-10-05: main 373a734b55fa851296046f1252ce4fa2e50ab075 = origin/main = actual GitHub main, clean working tree, ahead/behind 0/0. No pull/reset/stash/rebase/merge/reconciliation occurred. This checkpoint records the permanent target in the existing Market Data Standard; current runtime is still candle-based compatibility, not a shipped tick-native engine. No roadmap phase is advanced.

**Result:** repository/compatibility/migration audit completed; Exness XAUUSD sample acquisition is BLOCKED, and actual sample quality remains NOT_MEASURED. Do not count documentary examples as acquired data or claim all five sample-dependent gates passed. No parser was written for an unobserved format. No provider bytes, price rows, credentials, download script or account change enter Git.

### Existing ownership and reusable foundation

| Existing owner | What actually exists | Migration disposition |
| --- | --- | --- |
| backend/contracts/{primitives,canonical,models}.py | Exact Decimal conventions, BTL-CJSON-1/SHA-256, frozen request/Passport identity; nonexecuting intake | KEEP existing encoding/golden contracts unchanged; reference dataset/feed/profile/engine identity. Existing datetime contracts are microsecond-based, not a native-nanosecond stream |
| backend/precision/evaluator.py | Immutable Quote/Request/Decision, native integer nanoseconds serialized as decimal strings, exact bid/ask; bounded 1,024 revealed events; long bid/short ask exit evidence | KEEP version-1 evidence seam unchanged. Reuse evidence semantics, not as a full order/financial engine. No pending-entry/partial/latency/settlement lifecycle exists |
| backend/precision/policy.py | Reviewed scoped evidence retains/downgrades caller flags; AMBIGUOUS/quote crossing/no observed crossing, NOT_SIMULATED/null fill/PnL | KEEP as conservative review, never drive money from reports. Integrity/reference assertions are not provider certification |
| backend/precision/histdata.py | Offline fixed-EST parser/100k-row diagnostic; row identity not trusted sequence, fresh=False | KEEP provider-specific historical adapter. Exness requires separate adapter, never reuse EST conversion or silently relabel HistData |
| frontend/src/tickReview/* | Strict hash-bound bounded viewer; no crossing evaluator/account writer; loopback opt-in | KEEP current version-1 review unchanged; separately extend only for a versioned new artifact if necessary |
| backend/market_data/{service,local,serve}.py | Local-research M1 service over 120 existing chunks; immutable raw-byte versions; portable storage/access ports | KEEP M1 chart/regression service. Storage/access separation reusable conceptually; current Dataset descriptor and local loader are HistData BID M1-specific, not a ready TickDataProvider. Caller revealedBefore is NOT authoritative replay |
| frontend/src/market/{useReplayMarket,replayTransitions,PlaybackScheduler,useReplayPlayback}.js | Candle-index replay, validated suffix hints and acknowledgement-driven playback | MIGRATE event cursor/temporal boundary; KEEP scheduling/generation/acknowledgement concepts and appropriate regression tests |
| backend/engine/replay/replay_engine.py | Separate candle cursor/high-water prototype | DEPRECATE as execution progression target; KEEP compatibility tests and history until accepted replacement; do not promote it to a second authority |
| frontend/src/trading/AccountPersistence.js | Current local account byte preservation/version guards | KEEP legacy originals. Future tick results need explicit versioned namespace/account schema and migration authorization |
| frontend/src/trading/backtestAnalysis.js and backtestExport.js | Projections of account exits/realized values, no OHLC input | KEEP projection separation; later MIGRATE input eligibility/versioning, showing unresolved exclusions/denominator without inventing totals |
| backend/application, infrastructure, identity, workspace, cloud | Durable nonexecuting request intake/Passport plus verified membership adapters | KEEP unchanged; persisted request intake is not a financial ledger or tick settlement API |
| frontend/src/tradingUx/prototypeModel.js | Synthetic memory-only price/revision/risk demo with manual lifecycle actions; no ledger | KEEP UX reference. Never use its synthetic candles, trigger/plannedExit states or zero-cost assumptions as factual market execution |

Quote.fresh's generic constructor default is not source evidence: adapters must explicitly preserve UNKNOWN (as the current HistData adapter does). _prepare stops at the first future event and assumes an ordered supplied prefix; upstream must validate without silently sorting. Source ordinal currently fits event_id but has no dedicated raw ordinal/resolution/provenance fields. These limitations prevent treating the bounded evidence object as a complete canonical streaming dataset.

### Candle execution authority inventory

Search covered active frontend/backend and retained frontend/legacy/phase3 plus root legacy snapshot, excluding generated dependencies/provider data. Tests and docs are references, not additional execution authorities. Chart annotation/SL/TP dragging adjusts requests or draws levels; it does not independently settle them.

| Location / entrypoint | Current behavior | Classification and future action |
| --- | --- | --- |
| frontend/src/FigmaWorkspace.jsx: useTrading(replay.raw / market.liveBars) | Workspace supplies M1 replay or sampled live bars to financial hook, independently of display timeframe | MIGRATE to one canonical tick-event authority; do not feed display/aggregate candles to settlement |
| frontend/src/trading/simulator.js: placeOrder, validateOrder | Market entry uses quote.close; pending placement checks relative to scalar price | MIGRATE authoritative bid/ask entry, reviewed trigger-side profile and command activation ordering |
| same: processCandle | Pending high/low reach; availablePrice combines candle open with threshold; pending-entry bar uses close except opening entry/exit; opening exit precedes extremes; otherwise dual touches SL-first | MIGRATE all triggers/activation/SL/TP/partials/gap settlement to ordered quote events. Current available-price rule is MODELLED, not observed chronology |
| same: closePosition, pnl | Caller scalar price, JS Number, hard-coded contract size 100, zero commission, partial size/balance/trade writes | MIGRATE tick-linked fills and exact instrument/profile/fee/money model; do not reuse arbitrary scalar close as authoritative event |
| frontend/src/trading/useTrading.js: effect/place/close/equity | Replay calls settleReplay; live processCandle(...,true) collapses a sampled close into flat OHLC. Market/manual/full/partial close use quote.close; equity marks from that close | MIGRATE all writers/marking. tick=true is NOT historical paired Bid/Ask ticks; live sampling from Gold API cannot become a complete historical feed |
| frontend/src/trading/replaySettlement.js: settleReplay | Validated forward candle suffix or full scan calls processCandle | MIGRATE progression/evidence cursor; keep duplication/prefix/acknowledgement safeguards where applicable |
| backend/engine/trading/trading_engine.py: open_market, place_pending, _pending_fill_mid | Candle.close entry/comparison, high/low pending fill and opening min/max; floats and configured half-spread/slippage | DEPRECATE prototype authority; MIGRATE requirements to single new tick owner, not a parallel engine |
| same: process_candle, close_market | SL-first range tests, open/threshold min/max exits, close/manual scalar, constructed spread/slippage, float commission/PnL/balance | DEPRECATE candle settlement. REMOVE LATER only the obsolete execution path after accepted cutover; retain historical tests |
| backend/services/replay_service.py: next, jump, market_order, pending_order, close_position | Candle replay routes into TradingEngine including manual close at current_candle | DEPRECATE prototype execution API/use paths; future adapter must call the selected tick authority |
| backend/api/main.py: replay/order/close routes | Exposes the standalone ReplayService prototype; not mounted by production frontend | DEPRECATE for future execution; KEEP current compatibility, no route changed here |
| frontend/legacy/phase3/src/trading/{simulator,useTrading}.js and root legacy snapshot equivalents; archived App/replayApi | Retained older candle-model copies and old prototype service consumers, outside active import graph | KEEP historical/fixture code, DEPRECATE as reusable execution authority. No bulk deletion or reactivation |

REMOVE LATER applies only to unused execution call paths after consumers and migration-specific tests pass; it does not authorize removing archives, fixtures, chart candles or existing account results in this checkpoint. Current manual close/full/partial and market-entry paths are included, not just automatic TP/SL. Execution-derived statistics can inherit modelled PnL even when analytics itself consumes no candles.

### Candles and UI that remain

KEEP Lightweight Charts, CandleChart/indicator lifecycle, drawing TIME+PRICE projection, all existing ten-year M1 assets, historical importer and chart-only aggregation, news/research context and legacy comparison fixtures. Existing timeframes: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, D, W, M. UTC fixed-duration buckets; W begins Monday UTC, M begins calendar month UTC. Preserve these requirements, not only the shorter prompt list. Current aggregateCandles sorts candle bars; do not apply that routine to untrusted raw ticks.

Future derived candles use canonical revealed ticks only, separately named bid/ask sides (default display side explicitly pinned). Open = first valid revealed side price, high/low = extrema of revealed prefix, close = last valid revealed side price. Missing/empty intervals remain absent, with quality/session diagnostics; no carry-forward fabricated market candles or fabricated volume. Partial buckets remain partial until their boundary is reached. Unknown equal-time source order can make open/close unresolved even if extrema are computable: do not silently claim source ordering from file position. Existing chart conversion to JS Number is a visualization boundary only, not exact money/execution input. Feed changes never blend HistData candles with Exness execution as if one dataset. Existing native history stays separately labelled for comparison.

### Official Exness source and acquisition outcome (2026-10-05)

Primary sources reviewed:

- [Official tick-history form](https://www.exness.com/tick-history/): download archive for an instrument/period; bid/ask and indicative/informational purpose. Suffix/account variants are different feeds: requested XAUUSD is unsuffixed, not XAUUSDm/c or Raw_Spread. No actual selected XAUUSD account/product verified.
- [Official format explanation](https://insights.exness.com/trading-basics/forex-data/): documents CSV in ZIP and a USDJPY example with Symbol/Timestamp/Bid/Ask and a UTC Z timestamp with three fractional digits. This is a documentary example, not our acquired XAUUSD sample or proof of every file's delimiter/precision/semantics.
- [Official legal page](https://www.exness.com/legal-documents/): website copying requires express written permission. Copying website information without such permission is VERIFIED_RESTRICTED; no permission was obtained. Separate raw/derived-data commercial redistribution grants remain UNKNOWN. Explicit rights for personal programmatic normalization/storage/backups remain UNKNOWN; offered download/informational purpose is not a negotiated data license. No grant is fabricated.
- [API Terms](https://www.exness.com/cdn/media/docs/exness-api-terms-of-use.pdf): API-key terms apply to keys/account API access, not automatically a public tick-download license. No key generated, agreement accepted or authenticated endpoint called.

Actual browser opening of the official form failed with net::ERR_CERT_COMMON_NAME_INVALID. No certificate bypass performed. One separate ordinary certificate-validating HTTPS GET to the same official page returned HTTP 403, before any archive endpoint or instrument/date selection was available. This was not a guessed endpoint sweep; no unofficial mirror/repacked dataset, proxy evasion, CAPTCHA bypass, bulk script or vendor message used. Web research read official indexed/page content but could not select/download the form. No source-derived direct XAUUSD download URL was obtained. Acquisition is BLOCKED_TECHNICAL_AND_RIGHTS_UNRESOLVED, not a successful download or completed sample quality audit.

| Required sample/provenance field | Actual evidence |
| --- | --- |
| Provider/source candidate | Exness official tick-history; exact source URLs above |
| Instrument requested | XAUUSD; actual file/feed/account variant NOT_VERIFIED |
| Original filename / archive/member format | NOT_ACQUIRED; filenames unknown. Documentary candidate CSV/ZIP only |
| Acquisition timestamp / bytes / original archive or file hashes | N/A — no archive or raw quote file acquired |
| Normalized dataset ID/version/hash | N/A — no normalization artifact produced |
| Covered interval / first / last event / row count | NOT_MEASURED, not assumed from form options |
| Timestamp precision/timezone | Documentary UTC Z/milliseconds example for USDJPY; actual XAUUSD precision/timezone NOT_VERIFIED |
| Bid/ask fields, units and decimal scale | Candidate paired fields; actual XAUUSD spelling/delimiter/units/scale NOT_VERIFIED |
| Ordering, ties, same-time sequence, duplicate quotes | NOT_MEASURED; reviewed public sources do not establish trusted same-time sequence |
| Missing sides, malformed/crossed/nonfinite/nonpositive quotes | NOT_MEASURED |
| Spread/zero spread/abnormal spread | NOT_MEASURED; no fabricated anomaly threshold or broker tick size |
| Gaps/session boundaries/coverage | NOT_MEASURED; no inferred calendar or completeness certification |
| Licensing status | PERSONAL_LOCAL_RESEARCH_CANDIDATE; personal storage/normalization UNKNOWN; public copying without express permission VERIFIED_RESTRICTED; commercial SaaS/derived grants UNKNOWN |

No existing provider file was mislabeled as Exness. A source-provided CSV header, exact raw member and hash are required before implementing ExnessTickProvider parsing. The smallest available daily XAUUSD interval would be preferred; if only a month is offered, first confirm its bounded size/scope instead of silently expanding acquisition. Raw/archive/normalized/report bytes must be stored outside Git/OneDrive/public assets. Max archive/member/row limits, ZIP member traversal/compression bomb rejection and explicit EOF/partial coverage are required for later inspection. Preserve raw rows/order; count ties/repeats rather than dedup/sort. A bounded sample cannot certify ten-year/global completeness.

### Canonical compatibility and staged design (not implemented)

**Conditional structural fit:** if the actual file supplies UTC time and exact bid/ask, its values can map to existing Quote with integer native nanoseconds and Decimal. Convert UTC Z directly, never HistData's EST offset. Preserve original timestamp text/resolution and decimal scale in a separate versioned provider/registry envelope, since BTL-TICK-EVIDENCE-1 canonical decimal values deliberately normalize insignificant trailing zeros. Event_id can link artifact/member hash + raw ordinal; ordinal is not trusted_sequence. Coverage/freshness/ordering remain UNKNOWN unless specifically evidenced. Equal-time groups that materially change a decision remain UNRESOLVED.

Existing version-1 strict schemas/golden hashes cannot accept arbitrary added fields. Design a versioned canonical dataset/chunk envelope, referencing original hash/provenance and the existing event values. It needs provider/product/original symbol, instrument/feed/dataset/version, native timestamp/resolution, separate raw ordinal versus evidenced sequence, sides/quality/gap metadata and normalization/validator versions. Keep Passport identity conventions; do not mutate the frozen Passport or silently reduce ns to its microsecond SessionContext time. Streaming cursor needs dataset version + exact event identity/index/group, not time alone. Timestamp ties spanning chunk boundaries need atomic/group-preserving treatment; never add a fake nanosecond to make timestamps unique. No new envelope/provider API was coded here.

Target ownership follows the approved Market Data Standard:
Raw provider bytes → TickDataProvider adapter → immutable canonical dataset → Tick Market Timeline → prefix Tick Replay → one Tick Execution owner → lifecycle → atomic settlement → PnL → eligible statistics.
Parallel: canonical revealed events → deterministic side-specific candle aggregation → existing chart/indicators/drawings/research. Provider-specific parser/API terminates at adapter; engine consumes only canonical versioned events. ArtifactStore/AccessPolicy remain separate from execution. The current M1 service continues serving research, never becoming tick authority by renaming it.

The following are acceptance gates within the existing roadmap, not new phases or automatic authorization:

1. **Provider/sample gate:** obtain permitted small official XAUUSD sample, actual header/precision/side semantics, bounded structural diagnostics and provenance. Report ties/gaps/anomalies and unresolved rights. Permit synthetic contract engineering independently; real-data certification stays blocked.
2. **Canonical/provider gate (existing 41/42 responsibilities):** finalize versioned envelope and TickDataProvider/ExnessTickProvider boundary with authored + actual sample tests; raw ordinal distinct from trusted sequence; no float, sort, repair, suffix mixing or evidence promotion. Existing evidence/viewer bytes remain backward-compatible.
3. **Timeline/streaming/replay gate (41–43):** immutable chunks, event/group cursor, bounded reads, deterministic pause/resume/seek/prefix; no new financial writes yet. Test duplicate events, ties across chunks, hidden-future truncation/mutation, cancellation and dataset replacement. A caller cutoff is not enough for trusted replay.
4. **Derived visualization gate:** exact tick-prefix side candles across all eleven current timeframes; fixed UTC/week/month boundaries, no empty fills, missing volume explicit. Separate chart numeric conversion, causal indicators/news and existing drawing/timeframe geometry preserved. Candle stepping reveals all eligible tick groups up to its explicit target, not OHLC settlement.
5. **Execution-profile gate (44–49 responsibilities):** standalone fixture-tested canonical tick state machine, no production account writes. Long market entry ask / exit bid; short entry bid / exit ask. Proposed buy limit/stop triggers ask, sell limit/stop bid require profile review, exact boundary/latency/command-vs-event ordering. Request activation cannot use earlier ticks; same-time unknown activation remains unresolved. First supplied side quote after an evidenced trigger may support an explicit simulated available-price fill policy (including gaps), never an interpolated threshold or broker-fill claim. Pending/market/SL/TP/manual/partial exits, commissions/contract/lot/currency and money rounding must be pinned; broker liquidity/queue/slippage are not learned from quotes alone.
6. **Settlement/integration gate:** separately authorized versioned result/account schema, explicit LEGACY_MODELLED vs TICK_NATIVE namespaces, deterministic intent/event/idempotency and atomic balance/partial updates. Unresolved outcomes have no fabricated close/fill/PnL; define suspended position/session treatment before continuing dependent financial decisions. Never silently revert to OHLC. Statistics disclose unresolved counts/exclusions rather than assuming profitability or changing denominator invisibly. Earlier account bytes/results stay intact; reruns pin new identities.
7. **Consumer/retirement acceptance (including existing Phase 50 comparison):** migrate actual useTrading/replaySettlement/manual/order paths to one authority, test expected price/size/unit parity and intentionally different SL-first/spread/gap/activation outcomes. Candle direction/path agreement is not the oracle. Full frontend/backend/canonical/browser/security/persistence/differential gates precede any cutover; only then retire obsolete execution call paths. Keep compatibility candles/archives/tests, no removal authorized now.

**Recommendation:** NOT READY to authorize full tick-driven settlement or production migration. Ready to authorize a narrowly bounded canonical/provider contract and fixture-only timeline preparation if desired, while resolving official sample access and rights separately. Real Exness compatibility remains provisional until its actual bytes and semantics pass inspection. Ordering, completeness/freshness, activation/latency, exact financial profile, ns-vs-current timestamps, migration storage identity and trust boundaries are hard acceptance issues, not cosmetic parser work. No paid provider, authentication rewrite, UI redesign, database schema or cloud scope added.

### Validation for this audit

Changes are existing documents/context only. No runtime/inspection parser/dependency/data/test files changed. Required repository/AI-bundle tests, bundle generation/verification and diff review; focused existing precision and local-market tests may corroborate audited seams without certifying Exness. Browser/product/full release/DB rerun exempt for documentation only; the failed external form attempt is NOT successful browser/runtime validation. No historical test results are claimed rerun. Normal commit/push and actual remote equality/clean 0/0 required, then STOP. Future implementation requires human authorization.

Actual audit validation: test:repository PASS; test:ai-bundle PASS; test:tick-review PASS; 39 existing local-market/precision/policy/parser methods PASS; independent Node six golden vectors/three runs PASS. Bundle generation/verification and normal Git equality are final gates. These tests exercise existing code, not an Exness parser/sample or tick-native settlement.

## 42.15 Frozen canonical tick, provider and timeline contract — V1

Subsequent separately authorized implementation evidence is recorded in [42.16](#4216-canonical-synthetic-provider-and-authoritative-tick-timeline--implemented-checkpoint); the wire/ordering definitions below remain authoritative.

### Evidence and ownership

VERIFIED: baseline main/origin/actual GitHub 0e7e0804cdd6a428743eac0cfd24a7ca1436f691, clean 0/0. Existing Decimal, integer-ns Quote, BTL-CJSON-1/SHA-256 and conservative precision evidence are reusable as audited in 42.14. Existing production execution still uses candles/scalar prices. STILL UNKNOWN: Exness XAUUSD sample UNVERIFIED / NOT ACQUIRED; actual headers, timestamp resolution, order, ties, coverage, freshness and rights are not certified. No acquisition attempted here.

CONTRACT DECISION: this section is the single concrete tick/provider/timeline contract owner. MARKET_DATA_STANDARD owns product quality/invariant policy; ROADMAP owns future scope. The following V1 names are distinct artifact types, not modifications to BTL-TICK-EVIDENCE-1, its strict loader, Passport, account schemas or chart runtime. Freeze means implement these exact boundaries in the next separately authorized checkpoint; it does not mean runtime is implemented. No new roadmap or competing Quote model is introduced here.

Inspected owners: all AI_CONTEXT files, MARKET_DATA_STANDARD, ROADMAP, blueprint 42.7–42.14; contracts/primitives.py, canonical.py, models.py; precision/evaluator.py, policy.py, histdata.py; market_data/service.py, local.py; frontend market/replay and trading authorities listed in 42.14, backend TradingEngine/ReplayService; existing precision/contract tests and AI bundle configuration. No provider-specific fact is inferred from synthetic fixtures.

### Canonical artifact rules

All artifact objects use schemaVersion=1 plus the explicit artifact tag below; unknown keys/versions are errors, absent required keys are errors, nullable fields are explicit null. Use existing BTL-CJSON-1 sorted UTF-8 JSON and SHA-256, never JSON float numbers. Wire time/ordinal/index/sequence values are canonical unsigned decimal strings: ASCII digits, no leading zero except "0". Native time is Unix UTC ns, range 0..10^22; no datetime microsecond conversion. Prices are positive finite normalized decimal strings under existing decimal_text; no exponent, float, NaN, infinity or rounding. Original price scale/text is retained through provenance, not made significant in normalized numeric values. Content hashes are 64 lowercase hex. IDs use existing identifier restrictions. Limits are acceptance limits, not provider quality assertions.

| Artifact | Strict required fields / meaning |
| --- | --- |
| BTL-TICK-MANIFEST-1 | schemaVersion, artifact, datasetId, providerId, feedId, instrumentId, providerSymbol, evidenceClass, adapterVersion, validatorVersion, sources, range, ordering, coverage, gaps, rights, diagnostics, chunks |
| BTL-CANONICAL-TICK-1 | schemaVersion, artifact, datasetId, datasetVersion, providerId, feedId, instrumentId, eventId, timeNs, resolutionNs, bid, ask, rawOrdinal, trustedSequence, provenance, quality |
| BTL-TICK-CHUNK-1 | schemaVersion, artifact, datasetId, datasetVersion, chunkIndex, events |
| BTL-TICK-CURSOR-1 | schemaVersion, artifact, datasetId, datasetVersion, timelineVersion, generation, revision, sessionStartNs, throughNs, pendingTargetNs (nullable), visiblePrefixHash, nextGroupIndex, lastGroupId (nullable) |
| BTL-TICK-REVEAL-1 | schemaVersion, artifact, datasetId, datasetVersion, timelineVersion, generation, sessionStartNs, targetNs, throughNs, groups, coverage, diagnostics, visiblePrefixHash, cursor, exhaustedThroughBoundary |

Manifest nested shapes (all keys required): sources=[{sourceId, archiveHash:null|hash, memberHash, originalName, acquiredAtUtc:null|UTC text, sourceUrl:null|text, timestampConvention, resolutionNs, originalScalePolicy}]; range={startNs,endNs,endExclusive:true}; ordering={timestamps:"VERIFIED_NONDECREASING"|"UNKNOWN"|"INVALID",ties:"TRUSTED_SEQUENCE"|"UNTRUSTED",sequenceScope:null|id,sequenceEvidenceHash:null|hash}; coverage=[{startNs,endNs,status:"DECLARED_COMPLETE"|"INCOMPLETE"|"UNKNOWN",evidenceHash:null|hash}]; gaps=[{startNs,endNs,kind:"KNOWN_SESSION_CLOSED"|"MISSING_DATA"|"UNKNOWN_SILENCE",evidenceHash:null|hash}]; rights={class:"SYNTHETIC"|"PERSONAL_ONLY"|"PUBLIC_GRANTED"|"UNKNOWN",evidenceHash:null|hash}; chunks=[{chunkIndex,hash,eventCount,firstNs,lastNs}]. Counts are bounded JSON integers; positions are decimal strings. Sources <=128, chunks <=4096, coverage/gaps <=1024 each per manifest; longer histories use a separately versioned hierarchical manifest, not a silent limit increase. endNs is exclusive, lastNs inclusive observed event time. No event outside manifest range; empty datasets cannot be execution-ready.

Hash identity avoids cycles: build source-bound events first, hash their payloads with datasetVersion omitted; chunk hash is SHA-256 of BTL-CJSON-1 chunk payload with datasetVersion omitted both on the chunk and on every contained event. Manifest contains those hashes but no datasetVersion/self hash. datasetVersion = SHA-256 of canonical manifest bytes. Then materialize datasetVersion on event/chunk envelopes and verify by omitting only that field. A full envelope transport hash, if used, is explicitly named transportHash and never substituted for content hash. Event identity = SHA-256(BTL-CJSON-1({schemaVersion:1,artifact:"BTL-TICK-ID-1",providerId,feedId,memberHash,rawOrdinal})); provenance sourceId/memberHash must match one manifest source. ChunkIndex and rawOrdinal are zero-based; rawOrdinal counts original data records including quarantined records, not header lines. Cross-file source traversal is the manifest sources order. Source order is reproducibility metadata, not chronological evidence.

Per-event provenance={sourceId,memberHash,originalTimestamp}; original timestamp is the source text, max128 characters. resolutionNs is a positive decimal-string quantum (<=10^22) declared from source semantics; timeNs must be divisible by it. UTC conversion must be evidenced in source timestampConvention; no guessed timezone. Inputs finer than ns are rejected with UNSUPPORTED_RESOLUTION and preserved in diagnostics, never truncated. V1 normalized bid/ask are each positive decimal string or null. Missing sides are representable but not execution eligible. quality={evidenceHash:null|hash,quote:"VALID"|"MISSING_SIDE"|"CROSSED",freshness:"CONFIRMED"|"STALE"|"UNKNOWN",gapBefore:"NONE"|"KNOWN_SESSION_CLOSED"|"MISSING_DATA"|"UNKNOWN_SILENCE",duplicateOf:null|eventId}. Ask < bid implies CROSSED; ask == bid is valid zero spread. No repairs, side swaps, interpolated sides, outlier removal or forward-filled quotes. Adapter cannot default UNKNOWN freshness to confirmed. CONFIRMED/STALE freshness or non-UNKNOWN gap kind requires non-null quality.evidenceHash referencing reviewed source semantics; unreviewed hash alone cannot promote evidence. Gap/coverage claims need cited evidence to become stronger than UNKNOWN, and hashes only prove consistency, not truth.

Malformed/nonpositive/nonfinite prices or timestamp parse failure are not canonical quote values. Preserve {sourceId,memberHash,rawOrdinal,timeNs:null|valid ns,code,rawRecordHash} in bounded provider diagnostics; do not attach arbitrary raw text to UI. If time is known, block the corresponding interval with MISSING_DATA; if time cannot be bounded, dataset is not timeline-ready (UNLOCATED_INVALID_RECORD). Retaining a CROSSED or MISSING_SIDE event makes uncertainty visible; it is not authorization to settle using its other side. Diagnostics maintain total counts with bounded exemplars and truncation flag. Stream diagnostic records alongside their corresponding revealed group; untimed ingestion failures are opaque dataset rejection, not market-visible future row details.

Duplicate semantics: identical eventId + identical canonical payload is DUPLICATE_DELIVERY and rejected at ingestion (including across pages); conflicting payload under same ID is IDENTITY_CONFLICT and rejects dataset. Never silently deduplicate. Distinct rawOrdinal/eventId with equal quote values remain distinct observations; duplicateOf may document a suspected repeated source row only when referencing an earlier preserved event, never delete it or claim its cause. trustedSequence=null unless backed by source evidence. Non-null sequence is a decimal string scoped by manifest ordering.sequenceScope, with strictly increasing unique values within each equal-time group; missing/duplicate/conflicting sequences invalidate a claimed trusted group. Raw ordinal cannot fill missing sequence.

Additional strict nested rules: manifest evidenceClass is SYNTHETIC_CONTRACT_ONLY or PROVIDER_OBSERVATION (neither certifies fills); timestampConvention is a bounded evidenced description, not a guessed offset. originalScalePolicy is PRESERVE_RAW_TEXT; sourceUrl/originalName are bounded1024 text, acquiredAtUtc is UTC Z text at original precision. Non-null trustedSequence requires manifest sequenceScope and sequenceEvidenceHash; null in any group means that group is UNTRUSTED unless the manifest falsely claimed all groups trusted (then reject). Positive zero spread is valid; decimal validation inherits existing primitive magnitude/digit limits and requires canonical equality. Every encoded object must also fit existing BTL-CJSON-1 depth32/node16384/1MiB limits: the count ceiling is not a promise that 1024 large events fit. Never bypass canonical budgets; page construction stops at a record boundary, group overflow rejects GROUP_LIMIT atomically.

Coverage/gap intervals are sorted, non-overlapping, half-open and within range; gaps override contradictory completeness (reject contradictory manifest rather than downgrade silently). Synthetic declared evidence is marked synthetic and never promotes provider quality. Manifest UNTRUSTED tie-order can contain individually evidenced groups; a trusted claim must validate sequence uniqueness/progression at every source/page seam. Chunk entries are consecutive zero-based indices, eventCount1..1024, firstNs<=lastNs, byte hash as defined above. Strict diagnostic object={sourceId,memberHash,rawOrdinal,timeNs,code,rawRecordHash}; code is MALFORMED_PRICE, INVALID_TIMESTAMP, UNSUPPORTED_RESOLUTION, MISSING_SIDE, CROSSED_QUOTE, ORDER_REVERSAL or SUSPECT_REPEAT. Page diagnostics={records:[...],counts:{code:bounded integer},truncated:bool}; records<=128 and all rows preserve identity. Provider token={schemaVersion:1,artifact:"BTL-TICK-PAGE-TOKEN-1",datasetVersion,sourceIndex,afterRawOrdinal:null|string}; this exact source cursor is offline-only and checked against pinned manifest. Only successfully consumed records advance it. HTTP/auth/proxy tokens are adapter-private, never canonical fields.

Replay group uses the shape below, no extra fields. Reveal coverage uses the same clipped interval shape; diagnostics uses the page diagnostic shape but its counts include revealed records only. Reveal additionally requires sessionStartNs (wire ns string) and visiblePrefixHash. V1 defines this hash as a bounded chain: initial hash=SHA-256(BTL-CJSON-1({schemaVersion:1,artifact:"BTL-TICK-PREFIX-1",datasetId,datasetVersion,timelineVersion,generation,sessionStartNs,throughNs:sessionStartNs,groups:[],coverage:[],diagnostics:{records:[],counts:{},truncated:false}})); each advance hashes canonical {schemaVersion:1,artifact:"BTL-TICK-PREFIX-STEP-1",previousHash,throughNs,groups:new groups,coverage:revealed clipped interval delta,diagnostics:revealed diagnostic delta}. Each successful call atomically commits one bounded step and returns its chain hash; cursor revision increments even on silence. A completed same-target/current-cursor no-op leaves revision/hash unchanged. A specific controller advance schedule is pinned in replay acknowledgements; hash reproduction requires that schedule, while event/group content reproduction is schedule-independent. No in-progress update escapes on error. Full prefix arrays are not required in memory; readRevealed is bounded. Each advanceThrough call returns one bounded reveal step; host pumps successive calls with new cursors until exhaustedThroughBoundary=true. targetNs pins the requested boundary. While unfinished, throughNs is the last complete committed group time (or previous throughNs if no group), and coverage/diagnostics clip to that throughNs; only the final step advances throughNs to targetNs, including silence. All steps have same target; subscribers see only committed steps, never >target groups. No new-target request interleaves an unfinished advance. Controller checkpoints record target and step cursor for recovery.

Diagnostic content is version-bound: manifest diagnostics=[{hash,recordCount}] (<=4096 consecutive source-order blocks), each hash covers canonical {schemaVersion:1,artifact:"BTL-TICK-DIAGNOSTICS-1",datasetId,records,counts,truncated} with <=128 records and existing encoding budgets; no datasetVersion/self-hash cycle. Provider page diagnostic records must verify against these blocks and source record identities before reveal. Block-level total counts are offline-only; revealed counts are recomputed from eligible records, never copied from hidden totals. Unlocated invalid records prohibit timeline creation even if omitted from bounded exemplars. Source-boundary equal timestamps can join one complete group; overlap means an actual decrease, not equality.

### TickDataProvider V1 boundary (not implemented)

Pure provider port: describe(datasetId,datasetVersion) -> verified immutable manifest; readPage(datasetId,datasetVersion,afterToken:null|token,maxEvents:int) -> {artifact:"BTL-TICK-PAGE-1",schemaVersion:1,datasetId,datasetVersion,events,diagnostics,nextToken:null|token,endOfDataset:bool}. Tokens bind datasetVersion, source position and page schema, not wall time or caller-supplied array offsets. Enforce 1..1024 events and <=1MiB encoded page; oversize records fail explicitly. Success with zero events and non-null nextToken is allowed only for bounded diagnostic-only pages that advance source position; never infinite unchanged token loops. Cancellation returns no partial committed timeline update. Missing/corrupt chunk, stale token/version, unknown dataset, rights/access denial and bounded-limit errors are distinct failures, never empty-success/EOF.

Adapter may read CSV/ZIP/another API, but those details terminate here. Describe exposes instrument/feed/source/version, half-open time range, chronological confidence, coverage, provenance, rights and bounded diagnostics. Iteration is deterministic source order for a pinned immutable manifest. Provider declares VERIFIED_NONDECREASING only after validating the entire source's timestamp progression and source seam evidence; it must not sort/repair reversals. Hash-verified provider content does not certify provider coverage. An unverified order dataset can be inspected but cannot create an authoritative timeline. Full-range manifest/quality inspection is an offline ingestion capability, never handed directly to execution/strategy/market UI at replay time.

Page boundaries may split equal-time groups. The timeline owns bounded buffering and must request lookahead privately to know the group ended. Max equal-time group 1024 events /1MiB canonical bytes; an oversized group is GROUP_LIMIT, not a partial or secretly sorted group. Trust order is source-evidenced, not inferred from successful pagination. Exness production adapter remains prohibited until actual permitted sample semantics are verified. Local M1 ArtifactStore/AccessPolicy ports may inform adapter design; no descriptor renaming can turn candle data into ticks.

### Authoritative timeline/replay V1

Timeline factory verifies immutable manifest identity, eligible instrument/feed, VERIFIED_NONDECREASING timestamps and all loaded page/chunk hashes. Distinct source boundaries with overlapping/reversed timestamps reject ORDER_REVERSAL; no merge-sort. No historical source file is mutated. Timeline pins timelineVersion="BTL-TICK-TIMELINE-1" plus datasetId/version. Consumers receive only a reveal capability, not provider access, manifests with future counts/ranges, page tokens, raw files, buffered next ticks or diagnostic suffixes.

Group={groupId,timeNs,order:"TRUSTED_SEQUENCE"|"UNTRUSTED",events}. groupId hashes {schemaVersion:1,artifact:"BTL-TICK-GROUP-ID-1",datasetVersion,timeNs,eventIds:[...]} in source order. Group index is deterministic zero-based timeline position; even trusted group events retain source records while a separate sequenced projection orders by evidenced trustedSequence. This projection is permitted only within a verified tie group; never sorts timestamps. All members are revealed atomically. UNTRUSTED groups expose an unordered semantic set (deterministic source array for byte identity); consumers cannot execute member-by-member using array order. Equivalent-price ties do not automatically prove activation order or absence of another event.

API: advanceThrough(targetNs,expectedCursor) -> BTL-TICK-REVEAL-1 containing only newly revealed complete groups with timeNs<=targetNs plus clipped revealed coverage/diagnostics and successor cursor. targetNs >= previous throughNs; stale generation/cursor or identity mismatch fails without mutation. After exhaustedThroughBoundary=true, repeating the same target with the current successor cursor returns a consistent empty delta, never replays events to financial consumers; supplying any prior cursor is STALE_CURSOR, including a retried lost acknowledgement. Controller recovery reads committed cursor/view before retry, never guessing whether a delta committed. readRevealed(fromGroupIndex,maxGroups) returns only committed groups within this generation, bounded1024 groups/1MiB. nextGroup() is a host/replay-controller operation committing one atomic group; its resulting throughNs is that group's time. Market consumers cannot inspect the next group or request their own future advance.

At replay time T, events later than T never reach execution, candles, indicators, statistics, strategies or UI-visible market state. throughNs may advance through silence with no fabricated event; include gaps/UNKNOWN coverage clipped to [sessionStartNs,T], never disclose gap endpoints or diagnostics later than T. Full manifest identity is a pinned non-market identifier; no future prices/counts/min/max/precomputed candles are projected. Private EOF/lookahead flags cannot expose future event times: exhaustedThroughBoundary means all groups <=T committed, not end-of-dataset disclosure. A true endOfDataset flag belongs only to the offline provider API, not replay view. Visible-prefix hash excludes hidden payload/count metadata; includes pinned identity and visible groups/coverage. Hidden-suffix tests compare outputs within the same pinned identity; changing a real immutable manifest/version legitimately changes identity, not visible prices.

Seek/reset is controller-only, produces new generation (monotonic decimal string), clears subscribers/derived caches, creates an empty cursor, then deterministically reveals from explicit sessionStartNs through target. A complete replay view may include prior history for indicator warmup, but warmup events are not reexecuted as newly activated commands. This contract has no account, so it cannot authorize rewinding a financial ledger; existing trading rewind guards remain until separately approved migration. Persisted cursor resume must revalidate identity/group boundary and reconstruct the same prefix/coverage; no timestamp-only resume that skips ties. Dataset replacement creates a new timeline/generation, cancels in-flight reads and rejects late callbacks.

### Future execution input and ambiguity boundary

Execution accepts only immutable BTL-TICK-REVEAL-1 deltas from the trusted replay controller, together with separately versioned commands/profile and activation cursor. No candle/scalar close/legacy simulator callback is a valid quote. Command activation = {generation,afterGroupId:null|id,activationNs,relation:"AFTER_GROUP"|"BEFORE_LATER_TIME"|"UNKNOWN_SAME_TIME"}; all earlier events are ineligible. UNKNOWN_SAME_TIME cannot be converted to an invented within-group order, including when market tick ties have trusted sequence. A controller action after an acknowledged complete group may explicitly use AFTER_GROUP; user wall clock alone is insufficient.

Observed quote, trigger evidence, executable/fill model and financial settlement are four separate layers. Bid is observed sale-side quote; Ask is observed purchase-side quote; spread=Ask−Bid exact Decimal only if both sides valid. Long market buy uses Ask-side evidence, long exit Bid-side evidence; short entry Bid, short exit Ask. These identify sides, not guaranteed fills. A level-crossing quote or jump over multiple levels does not reveal intermediate trades, queue, liquidity or slippage. This checkpoint authorizes no limit/stop priority, fill/slippage/latency/fee policy. Future reviewed profile must supply those rules; otherwise UNRESOLVED_PROFILE and no settlement. Future triggers cannot infer threshold-price execution from crossed levels.

Future evidence result states: OBSERVED_QUOTE (valid visible paired quote), UNRESOLVED_ORDER, UNRESOLVED_ACTIVATION, UNRESOLVED_COVERAGE, UNRESOLVED_QUOTE, UNRESOLVED_PROFILE; transport/structural failures are explicit rejection, not market outcomes. If a path depends on uncertain order/invalid/missing/stale sides/gap, return the relevant unresolved state with supporting event/group reference; no simulated fill/PnL/closed trade. Do not assume a future valid quote erases an earlier unresolved crossing. Full lifecycle/suspended-position treatment and settlement are later authorized gates. Existing precision evaluator can be an explicit bounded evidence projection after representability checks; never silently map UNKNOWN freshness to True, truncate sequence/ns or use its crossing Decision as a financial fill.

Frontend simulator/useTrading/replaySettlement and backend TradingEngine/ReplayService require eventual migration exactly as inventoried in 42.14. Backend API prototype and archived frontend/legacy/phase3 and root snapshot copies must never be hidden OHLC fallback paths. They remain untouched now. Legacy MODELLED account bytes/results remain separate; future tick mode must not relabel them.

### Derived candle boundary

Canonical revealed tick groups -> side-specific aggregator -> chart/indicators/drawings, never execution. Preserve 1m,3m,5m,15m,30m,1h,2h,4h,D,W,M; fixed UTC buckets, Monday UTC W, calendar UTC M. Aggregate side explicitly BID or ASK, no midpoint substitution. Output identifies datasetVersion, throughNs, timeframe, side, bucketStartNs/endNs, open/high/low/close each exact string or null, completeness, ordering quality and provenance groups. Trusted first/last observed event defines open/close; differing untrusted boundary ties yield null open/close + UNRESOLVED_ORDER; extrema may still be determinable. Missing/crossed quotes cause quality diagnostics, not synthetic prices. Empty buckets absent; gaps stay disclosed; partial buckets remain partial; volume null unless source supports explicit units. Chart numeric conversion is display only. Final/partial candles and indicator inputs depend only on revealed prefix. Aggregator implementation is deferred.

### Synthetic fixture matrix — normative contract examples, not market evidence

The JSON below is the sole authored fixture matrix. Decimal strings/time ns are synthetic small values, not Exness/XAUUSD market observations. Rows abbreviate the event envelope: ordinal is rawOrdinal, sequence is trustedSequence, quality expectation follows the contract; the next checkpoint materializes full hash-bound envelopes. expected specifies representation/ingestion/group uncertainty, not fills, PnL or executed engine output. UNKNOWN coverage/freshness remains default; normal means structurally valid, not execution-certified. The test checks this matrix's expressiveness and canonical representability, not an unimplemented timeline.

<!-- BTL-TICK-CONTRACT-FIXTURES-1 -->
```json
{"schemaVersion":1,"artifact":"BTL-TICK-CONTRACT-FIXTURES-1","evidenceClass":"SYNTHETIC_CONTRACT_ONLY","resolutionNs":"1","cases":[
 {"id":"normal_ordered","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":null},{"ordinal":"1","timeNs":"200","bid":"1.2","ask":"1.3","sequence":null}],"expected":"ORDERED_SINGLETONS"},
 {"id":"changing_spread","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":null},{"ordinal":"1","timeNs":"200","bid":"1","ask":"1.4","sequence":null}],"expected":"PRESERVE_SPREAD"},
 {"id":"trusted_tie","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":"9"},{"ordinal":"1","timeNs":"100","bid":"2","ask":"2.1","sequence":"10"}],"expected":"ATOMIC_TRUSTED_GROUP"},
 {"id":"untrusted_tie","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":null},{"ordinal":"1","timeNs":"100","bid":"2","ask":"2.1","sequence":null}],"expected":"UNRESOLVED_ORDER"},
 {"id":"duplicate_delivery","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":null},{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":null}],"expected":"REJECT_DUPLICATE_DELIVERY"},
 {"id":"repeated_source_quote","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":null},{"ordinal":"1","timeNs":"100","bid":"1","ask":"1.1","sequence":null}],"expected":"PRESERVE_DISTINCT_EVENTS"},
 {"id":"timestamp_reversal","rows":[{"ordinal":"0","timeNs":"200","bid":"1","ask":"1.1","sequence":null},{"ordinal":"1","timeNs":"100","bid":"2","ask":"2.1","sequence":null}],"expected":"REJECT_ORDER_REVERSAL"},
 {"id":"gap","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":null},{"ordinal":"1","timeNs":"300","bid":"4","ask":"4.1","sequence":null}],"gap":{"startNs":"101","endNs":"300","kind":"UNKNOWN_SILENCE"},"expected":"UNRESOLVED_COVERAGE"},
 {"id":"missing_side","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":null,"sequence":null}],"expected":"UNRESOLVED_QUOTE"},
 {"id":"crossed_quote","rows":[{"ordinal":"0","timeNs":"100","bid":"2","ask":"1","sequence":null}],"expected":"UNRESOLVED_QUOTE"},
 {"id":"market_jump","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":null},{"ordinal":"1","timeNs":"200","bid":"4","ask":"4.1","sequence":null}],"levels":["3"],"expected":"OBSERVED_JUMP_NO_FILL"},
 {"id":"multiple_levels","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":null},{"ordinal":"1","timeNs":"200","bid":"4","ask":"4.1","sequence":null}],"levels":["2","3"],"expected":"NO_INTERMEDIATE_PATH_OR_FILL"},
 {"id":"ambiguous_activation","rows":[{"ordinal":"0","timeNs":"100","bid":"1","ask":"1.1","sequence":"9"},{"ordinal":"1","timeNs":"100","bid":"4","ask":"4.1","sequence":"10"}],"activationNs":"100","relation":"UNKNOWN_SAME_TIME","expected":"UNRESOLVED_ACTIVATION"},
 {"id":"malformed_price","raw":{"ordinal":"0","timeNs":"100","bid":"NaN","ask":"1"},"expected":"QUARANTINE_LOCATED_RECORD"},
 {"id":"unlocated_timestamp","raw":{"ordinal":"0","timeNs":"not-time","bid":"1","ask":"1.1"},"expected":"REJECT_UNLOCATED_INVALID_RECORD"}
]}
```

Next implementation acceptance must additionally exercise full strict schemas/hash tampering, ID conflicts, chunk seam duplicates/reversal/trusted sequence conflicts, ties split across pages/oversized groups, no-lookahead suffix mutation/truncation under pinned identity, clipped gap diagnostics, stale cursors/dataset replacement/cancellation, deterministic replay seek/reset/resume and invalid/finer-resolution timestamps. Matrix examples do not replace those behavioral tests.

### Exact next checkpoint and present validation scope

IMPLEMENT CANONICAL TICK PROVIDER + AUTHORITATIVE TICK TIMELINE/REPLAY USING SYNTHETIC FIXTURES, WITHOUT SETTLEMENT YET. Only after separate human authorization: add isolated frozen types under backend/ticks reusing contracts primitives/canonical; SyntheticTickProvider only; immutable manifest/chunk validation and bounded group timeline/cursors; tests above. No Exness parser until actual format/rights verified; no frontend wiring, candle aggregator, execution, account/PnL, database/cloud or retirement. Existing evidence and golden vectors remain unchanged. Canonical/provider fixture implementation is ready for bounded authorization, real-data readiness is not.

Contract decisions now freeze names, fields, hash identities, ordering/quality rules, limits, replay capability and future consumer boundary. Real provider data is needed to resolve timestamp convention/resolution, supported instrument/feed, sequence evidence, duplicate causes, freshness/coverage/session gaps, raw CSV/ZIP semantics and licensing; these cannot be filled from fixtures. Broker fill/slippage/cost/profile policy needs separate product evidence/authorization, not merely a CSV sample.

This checkpoint changes only documentation and a test-only fixture validation harness. Existing task-specific bundle allowlist is unchanged; its architecture owner includes the complete normative fixtures, while backend tests run in master. Run new contract-fixture unittest, existing precision/golden compatibility tests, repository/bundle tests and generation/verification, diff review and Git equality gates. No runtime/browser/full-release claim: those are exempt because production paths are unchanged. STOP after push/clean 0/0, do not implement the next checkpoint automatically.

Validation evidence: 28 focused unittest methods PASS (4 contract-specification/fixture checks plus 24 existing precision/policy methods); independent Node 6 golden vectors across 3 runs PASS; test:repository and test:ai-bundle PASS. Bundle generation/hash verification and normal Git equality are final gates. No provider/timeline runtime, browser, real-feed or full-release acceptance is claimed.

## 42.16 Canonical synthetic provider and authoritative tick timeline — implemented checkpoint

### Actual baseline and scope

Starting baseline 56d8735e29d90ec3582a9233ac4942d2ea98761a = local/origin/actual GitHub main, clean 0/0. Human authorized implementation of frozen Section 42.15 canonical/provider/timeline contracts using SYNTHETIC / TEST ONLY fixtures, without settlement. Section 42.15 remains the contract owner; this section records implementation/evidence, not a second schema or roadmap. No frozen field/hash/order semantics were replaced. Section 42.14 remains the candle-path migration inventory. Existing BTL-TICK-EVIDENCE-1, precision policy, Local Tick Review and financial/account/runtime code are unchanged.

### Implemented ownership

| File | Implemented responsibility |
| --- | --- |
| backend/ticks/__init__.py | Isolated unwired namespace; no API registration |
| backend/ticks/contracts.py | Frozen canonical tick/manifest bytes, strict exact-field/version/value validation, Decimal properties/native ns, source identity/resolution/quality/evidence, cyclic-free content hashing and local chunk validation |
| backend/ticks/provider.py | TickDataProvider Protocol, SyntheticTickProvider, immutable canonical pages/tokens, cancellation token and offline full-ingestion acceptance; cross-page/chunk IDs/ordinals/time/sequence and hash-bound diagnostics |
| backend/ticks/timeline.py | Controller-only TickTimeline, read-only RevealedView capability, bounded groups/deltas/cursor/hash chain, seek/reset/resume/cancellation and dataset replacement |
| backend/tests/test_tick_timeline.py | 21 synthetic acceptance methods, including original normative matrix, hostile artifacts/cursors, bounded traversal, private future state and lifecycle races |

CanonicalTick and TickManifest validate direct byte construction as well as wire factories. Wire copies cannot mutate their frozen canonical bytes. Prices use existing Decimal/canonical primitives, never floats; nanoseconds/resolution remain unsigned strings on wire. Manifest/chunk metadata rejects wrong identities, versions/hashes/ranges/provenance/source order. Exact duplicate delivery and conflicting identity reject; repeated quote values at distinct source ordinals remain separate events. Missing/crossed quotes are retained as explicit quality states; malformed price bytes are rejected from canonical quotes, and authored diagnostic records can represent quarantined invalid input with explicit missing-data intervals. No Exness/parser/provider facts are invented.

Provider-specific input ends at adapter: TickTimeline uses describe/read_page only. A port-only proxy splits tied events across pages/chunks in acceptance. Chunk hashes are rechecked before exposing loaded events; previously verified cached bytes stay immutable even if backing storage later changes. Offline ingestion rejects corrupt/truncated/stalled/foreign pages, source ordinal reversals, sequence conflicts, incomplete/unlocated diagnostics and false trusted-order declarations. Unknown freshness/coverage stays UNKNOWN; source/hash/evidence references are consistency assertions, not market certification.

### Replay lifecycle and causal boundary

Timestamp groups are atomic. Trusted sequence requires evidenced scope and increasing unique values; otherwise the group is explicitly UNTRUSTED, not an invented chronological array. Source ordinal stays separate. A revealed-only consumer has no provider, manifest, EOF, advance, seek or checkpoint API; normal consumption cannot obtain future ticks or future numeric metadata. This is a Python capability separation for trusted application composition, not a sandbox against arbitrary code reflection.

Controller advance_through returns at most 64 groups per committed step, subject to tighter canonical byte/node budgets; host pumps the same target while pending. Cursor identifies dataset/version, generation/revision, session start, through time, pending target, complete next-group index/last ID and visible prefix chain hash. Silence advances revision without fabricating ticks. Same-target/current-successor no-op is idempotent; stale/foreign/schema-boolean cursors reject. Metadata is clipped to throughNs and diagnostics counts are revealed-only; missing prices are never filled forward. Bounded-limit failures leave cursor/prefix unchanged; no silent partial serialization or EOF success.

Seek resets generation then replays complete groups to target; before-first/exact/between/ties/after-final are tested. Targets before sessionStart reject, and seek does not rewind any account ledger. Reset revokes old generation views and returns an empty prefix with the same dataset. Dataset replacement creates a new timeline/generation, retires the old controller/view and invalidates old cursors. Cancellation rolls back speculative groups with bounded buffered replay; reset during provider read rejects the late callback and reconstructs the new generation rather than committing old events.

Resume requires the controller-private checkpoint {cursor,advanceTargets}. This records the exact committed advance schedule already required by Section 42.15's schedule-sensitive prefix chain. Reconstruct and verify all cursor fields/hash before returning a resumed controller; cursor alone is not a trusted shortcut into hidden state. Continuous versus stopped/resumed replay produces identical subsequent groups and cursors. Generation resets intentionally change prefix identity, while immutable market groups remain reproducible.

### Synthetic acceptance and limitations

The normative fixture matrix remains solely in Section 42.15; tests read it rather than duplicate a competing fixture owner. Additional authored cases cover missing Bid and Ask, zero/very wide spread, bad Decimal/ordinal/sequence, chunk/hash/manifest tampering, ties across pages/chunks, oversized groups, silence/no-op/EOF, reset/seek/resume, incompatible cursors, cancellation, dataset replacement and callback races. All provider metadata says SYNTHETIC_CONTRACT_ONLY / SYNTHETIC / TEST_ONLY; fixture output is market chronology only, never fills/PnL.

SYNTHETIC adapter is intentionally an in-memory test store with one authored source and <=128 authored diagnostic exemplars. Its raw authored input and each artifact must fit existing canonical budgets. Generic ingestion supports manifest-declared diagnostic blocks from provider pages; incomplete/truncated/unlocated diagnostics cannot start an authoritative timeline. A reveal exceeding diagnostic/byte/node limits fails explicitly (REVEAL_LIMIT / canonical budget / GROUP_LIMIT); host must request a smaller bounded target, not discard diagnostics. Oversized atomic groups cannot be split. No production-size performance or ten-year tick benchmark is claimed.

Forward traversal buffers one page/chunk plus one group and bounded output rather than copying history every step. Offline ingestion keeps an event identity digest index; controller caches verified diagnostic exemplars and committed target acknowledgements. Memory is not claimed constant over arbitrary history. Prefix reads/seek/resume stream from provider and may scan the accepted prefix; future indexed storage/ack persistence can improve this through the existing port without changing market chronology. Synthetic provider stores its authored dataset in memory; no production disk/cloud streamer was added.

Exness remains UNVERIFIED / SAMPLE NOT ACQUIRED. No real provider dataset/adapter, candle aggregator, execution/SL/TP/fill model, settlement/PnL/account migration, frontend/backend cutover, cloud delivery or legacy deletion exists here. Eleven product timeframes and all existing candle research/compatibility paths are unchanged. NO TRADE MAY BE SETTLED FROM OHLC DATA ALONE remains the future execution invariant, not a claim that current legacy production already complies.

### Validation and next authorized boundary

Full backend discovery: 167 methods, 142 PASS, 25 explicit PostgreSQL/identity/workspace skips because no isolated database configured; skipped gates are not release PASS. This includes 21 new synthetic acceptance methods and existing evidence/golden contracts. Final narrow type/cursor/diagnostic checks were rerun after review. Independent Node six golden vectors across three runs PASS. Entire registered frontend regression, lint, production build and local release audit PASS. No actual browser run is claimed: new pure modules are unmounted and frontend/API behavior unchanged; existing unwired-foundation exemption applies. No database/auth/schema was modified.

Repository/bundle generation/verification, complete diff review, normal commit/push, actual local/origin/GitHub equality and clean 0/0 are final checkpoint gates. Bundle remains the existing partial allowlist: authoritative blueprint fixtures/context are included, backend code/tests run in master and are not silently added to the drawing-focused bundle.

Next separately authorized checkpoint: IMPLEMENT TICK EXECUTION ENGINE V1 ON TOP OF THE AUTHORITATIVE TICK TIMELINE, USING SYNTHETIC FIXTURES FIRST, WITHOUT CANDLE FALLBACK. Before financial production integration, unresolved profile/activation/trigger/fill/latency/cost/lifecycle decisions require explicit bounded authority; no assumptions are silently supplied by this timeline. STOP after this checkpoint; no automatic execution, aggregation or Exness integration.

## 42.17 Scalable tick storage and index contract — V2 freeze only

### Authority, baseline and scope

Human authorization: DESIGN & FREEZE SCALABLE TICK STORAGE / INDEX CONTRACT V2, planning and contract fixtures only. Starting main/local/origin/actual GitHub: 179b966e6d5c60ec44fcf004934de96dea23bdfd, clean 0/0. Sections 42.14–42.16, MARKET_DATA_STANDARD, existing canonical/precision/golden owners and actual backend/ticks code were inspected. This section alone owns the scalable extension; 42.15 remains the unchanged V1 authority, 42.16 historical implementation evidence. No second roadmap, architecture document or runtime implementation is introduced.

The human-supplied local Exness_XAUUSDm_2015.csv motivated this extension. Prior read-only measurement: 554,761,330 bytes / 8,698,581 quotes, observed 2015-08-10 00:00:00 UTC through 2015-12-31 22:00:04 UTC; all fractional timestamps .000Z, maximum observed tie 81. These are prior audit observations, NOT remeasured ingestion/benchmark evidence here. Provenance, rights, completeness and same-time sequence remain unverified. Historical NOT ACQUIRED statements in 42.14–42.16 describe those earlier checkpoints, not the present existence of a user-supplied local file. No source hash, official acquisition or permission is invented.

Three demonstrated V1 blockers: manifest <=4096 chunks with <=1024 events/chunk gives an upper count ceiling of 4,194,304 (encoding budgets may reduce it); validate_provider retains every eventId/hash in seen_ids; TickTimeline constructor validates the whole provider, and positioning/prefix reads scan from its beginning. A disk provider alone cannot resolve these. Keep V1 limits/identity/goldens/code unchanged; do not split a logical replay into unrelated V1 datasets to hide this problem.

### Fixed hierarchy, artifact budgets and capacity

Freeze exactly four storage levels: DATASET ROOT → DIRECTORY → PARTITION → CHUNK. Directory is necessary because two large descriptor arrays under the unchanged canonical node budget cannot safely achieve billion-event capacity with realistic tick payloads. No recursion, arbitrary child types or calendar dependency. Each logical child index is contiguous zero-based source-order position; physical filenames/SQLite layouts are implementation details, not identity. A month may span multiple partitions; a partition may span dates.

| Level | Maximum fan-out | Descriptor array | Artifact |
| --- | ---: | --- | --- |
| Dataset root | 256 directories | directories | BTL-TICK-DATASET-2 |
| Directory | 1024 partitions | children | BTL-TICK-DIRECTORY-2 |
| Partition | 256 chunks | children | BTL-TICK-PARTITION-2 |
| Chunk | 256 canonical V1 events | events | BTL-TICK-STORAGE-CHUNK-2 |

Exact count ceiling: 256 × 1024 × 256 × 256 = **17,179,869,184 events**. Maximum objects: 1 dataset root, 256 directories, 262,144 partitions, 67,108,864 chunks. This is structural capacity, NOT a throughput, hardware, disk-space or concurrency claim. All nonempty arrays may be smaller; no padding/synthetic ticks. Each artifact retains BTL-CJSON-1 depth32 / node16384 / 1MiB limits and array <=4096. The tighter applicable limit wins; event count is not a byte/node guarantee. Oversized individual event/group/artifact fails explicitly; split storage chunks or metadata containers at record boundaries, never split a revealed group. A root with 256 descriptors, a directory with 1024 descriptors and partition with 256 descriptors fit the node budget with the frozen shapes below; source/diagnostic/coverage metadata uses bounded sidecars so root growth never tracks N.

Metadata scale: each child descriptor has 7 fields / 8 canonical nodes. At saturation there are 67,371,264 storage descriptors, plus 67,108,864 time-index chunk descriptors and bounded sidecar references. A storage descriptor is capped at 2048 encoded bytes, so the storage descriptor bytes alone are <=137,976,348,672 bytes; this conservative bound is NOT expected compressed disk usage. Metadata is O(number of chunks), stored on disk, not one RAM list. Index hierarchy mirrors storage fan-outs; max 1 index root +256 index directories +262,144 index partition leaves. <=256 chunk descriptors per leaf, each <=2048 bytes; full artifacts still <=1MiB. Actual sizes/compression/memory require later measurements.

### Frozen wire shapes and acyclic identity

Every V2 artifact below uses schemaVersion=2, an exact artifact tag and exact listed fields, rejecting unknown/absent keys, duplicate JSON keys, floats, booleans masquerading as integers, noncanonical unsigned strings and unexpected versions. Reuse identifiers, hashes, decimal normalization and native integer ns rules from 42.15. Indices/counts on wire are canonical unsigned decimal strings <=10^22, not floats. Original provider/feed/instrument/symbol and source identity are exact; do not map XAUUSDm to XAUUSD. One root represents exactly one provider/feed/instrument/providerSymbol; every descendant/event must match its root. No mixed-symbol dataset.

Common descendant header H: schemaVersion, artifact, datasetId, datasetVersion, providerId, feedId, instrumentId. Root does not contain datasetVersion, because its canonical hash IS that version.

Storage descriptor D (exact): index, hash, eventCount, firstNs, lastNs, firstOrdinal, lastOrdinal. Ordinals here are dataset-global positions (0..N-1), NOT rawOrdinal or trustedSequence. N must be <=17,179,869,184. eventCount equals lastOrdinal-firstOrdinal+1; time range firstNs..lastNs is inclusive observed time, allowing equality at storage seams. Descriptor hash binds the entire child content; no filesystem pointer/absolute path is accepted in canonical identity.

| Artifact | Exact fields beyond schemaVersion/artifact or H |
| --- | --- |
| BTL-TICK-DATASET-2 | datasetId, providerId, feedId, instrumentId, providerSymbol, evidenceClass, adapterVersion, validatorVersion, range, ordering, eventCount, directories, sourceCatalogHash, evidenceCatalogHash, indexContentHash |
| BTL-TICK-DIRECTORY-2 | H plus directoryIndex, range, eventCount, children |
| BTL-TICK-PARTITION-2 | H plus directoryIndex, partitionIndex, range, eventCount, children |
| BTL-TICK-STORAGE-CHUNK-2 | H plus directoryIndex, partitionIndex, chunkIndex, firstOrdinal, events |
| BTL-TICK-SOURCE-CATALOG-2 | H plus sources (1..128, exact V1 source shapes) |
| BTL-TICK-EVIDENCE-CATALOG-2 | H plus children (<=256 sidecar descriptors: index, hash, firstNs, lastNs, recordCount) |
| BTL-TICK-EVIDENCE-BLOCK-2 | H plus blockIndex, coverage, gaps, diagnostics, rights |

range is {startNs,endNs,endExclusive:true}; root endNs=last observed time+1. Child ranges equal first observed time..last observed time+1. Ancestor descriptors/ranges/counts exactly aggregate descendants. Overlap of observed-time bounding intervals ONLY at equal seam timestamp is legitimate; actual timestamp decrease, ordinal overlap/gap, duplicate/missing/nonconsecutive child or dishonest range/count rejects. Every child has 1..fan-out entries and <=1MiB. Source catalog cannot overflow 128 sources in this frozen version: SOURCE_LIMIT, not silently merge sources. Evidence blocks use the V1 nested coverage/gap/rights/diagnostic-record shapes, <=128 total records/intervals per block. Each block's diagnostic identity is retained, never a truncated exemplar substituting for full validation. Evidence total bound: 256 blocks ×128 entries =32,768; overflow is EVIDENCE_LIMIT and not publication-ready. Unknown coverage/freshness and UNTRUSTED ties require no invented positive evidence. An unknown/unlocated invalid timestamp still prohibits timeline acceptance; malformed/nonpositive/nonfinite input is not a canonical price. No execution eligibility promotion.

Root ordering uses the exact V1 ordering shape and reviewed evidence requirements. Evidence blocks agree on one dataset-wide rights class/hash; no conflicting rights or diagnostic promotion. An empty evidence catalog implies UNKNOWN coverage/rights for PROVIDER_OBSERVATION, or SYNTHETIC rights for SYNTHETIC_CONTRACT_ONLY, with no affirmative market completeness or provider license claim; source catalog and event identities are still mandatory. All evidence-block refs and entries must be included in offline acceptance, even when absent from a replay window.

Content hash rule for EVERY V2 descendant, source/evidence sidecar and index node: SHA-256(BTL-CJSON-1(payload with only its top-level datasetVersion omitted)); for storage chunks additionally omit datasetVersion from each contained BTL-CANONICAL-TICK-1 event, exactly as V1 chunk cycle avoidance. No other field is omitted. Descendants are built bottom-up with provisional version, content-hashed, referenced by parents; root commits all directory/source/evidence/index hashes. datasetVersion=SHA-256(canonical root bytes). Then materialize this same version on every descendant/event. V2 chunk identity is explicitly a new artifact; existing BTL-TICK-CHUNK-1 hashes remain unchanged. CanonicalTick V1 field set, eventId derivation, rawOrdinal, originalTimestamp/resolution and quote semantics remain unchanged. Root version fixes all descendants, including index; modifying layout creates a new datasetVersion even if raw source bytes are the same. Raw member hashes and provider event IDs stay source-bound.

Existing canonical_bytes/content_hash public entry points enforce schemaVersion=1. Keep those gates and all golden bytes unchanged. A later separately named V2 encoder/hash entry point must enforce schemaVersion=2 while using exactly the same BTL-CJSON-1 normalization, sorted UTF-8 serialization and budgets; it does NOT normalize 2 to 1 before hashing. The test-only design encoder oracle reuses the existing internal normalization and independently gates version 2; no runtime encoder is implemented here. Nested CanonicalTick retains schemaVersion=1. Byte identity examples verify schemaVersion=2 is actually hashed and V1 still rejects it.

### Validation, bounded memory and publication lifecycle

Immutable artifacts live on local disk, content-addressed or addressed through a strictly validated private store. Implementer may choose standard-library SQLite for B-tree identity tables/navigation/work journal plus immutable canonical chunks. No new infrastructure dependency is authorized here. Raw source remains read-only/private, never Git/public assets. Sources must supply size/name/SHA-256 and preserved original rows/scale outside canonical numeric normalization.

Offline acceptance streams original source order, NEVER sorts market events. Validate one chunk plus one atomic group, <=4 active ancestor manifests, bounded sidecar/page buffers and previous seam state. Budget caches explicitly (future default <=64MiB; no unlimited cache); bounded storage pages and OS cache observations must be distinguished in benchmarks. Persistent UNIQUE sourceId/rawOrdinal and eventId→payload-hash tables on disk detect DUPLICATE_DELIVERY vs IDENTITY_CONFLICT across all chunks/partitions. Do not retain a dataset-wide Python dict/set. Quote repetition under distinct rawOrdinal/eventId stays separate. Future tests exercise actual disk uniqueness; test-only oracle here does not demonstrate RAM performance.

Validate root→directory→partition→chunk hash/range/count/identity edges, all source mappings, Decimal/ns/resolution, chronological seams, diagnostic/evidence catalog, and time-index cross-links. All event identities must be accepted before publish. Retain predecessor time/source/ordinal/sequence, group count/bytes and previous last boundary as bounded RAM state. Group <=1024 events and canonical group budgets unchanged; reset group state only after time changes, even across partitions/directories. No active validation table is executable market evidence.

Lifecycle: INGESTING → VALIDATING → INDEXING → FINALIZING → COMPLETE. PUBLISHED means local atomic visibility, not public redistribution. State transitions live in mutable private work journal, never in root hash. At transaction/checkpoint boundaries persist input hash/size, ingestion+validator versions, source byte/record offset, completed child hashes, previous seam/group state and disk uniqueness-table transaction position. Commit offsets/index/chunks together; unfinished chunks/groups remain staging. Restart verifies exact source bytes/hash and committed artifacts; rollback uncommitted tail and reread from the last committed record/group boundary, never skip records or trust stale offsets. Changed source/version/validator invalidates resume; retain previous work as rejected staging. Correctness may require reprocessing unfinished work; no promise of resuming arbitrary corrupt state.

FINALIZING verifies every referenced artifact, disk identity constraints, seam proofs, complete index and source hash; fsync artifacts/journal then atomically publish immutable root plus local completion receipt. Receipt exact fields: schemaVersion=2, artifact=BTL-TICK-COMPLETION-2, datasetId, datasetVersion, manifestHash, validatorVersion, indexContentHash, sourceCatalogHash. manifestHash=datasetVersion. Receipt is consistency evidence produced by trusted composition, not a self-certified license/security signature. Crash before publication yields INCOMPLETE_INGESTION; crash after atomic receipt/root publication yields the same immutable dataset if all hashes verify. Readers reject missing receipt/root/child and never interpret staging as EOF. On-disk database mutation after acceptance cannot bypass hash checks. Root pin + validated completion enables later runtime lazy descendant verification without full-history validation at every session open; untrusted receipt requires complete offline acceptance first.

### Immutable time index and controller-only capability

Index tree is fixed root→directory→partition leaf, matching storage hierarchy. Exact index shapes:

- BTL-TICK-TIME-ROOT-2: H plus children (<=256 index directory descriptors).
- BTL-TICK-TIME-DIRECTORY-2: H plus directoryIndex, children (<=1024 index partition descriptors).
- BTL-TICK-TIME-PARTITION-2: H plus directoryIndex, partitionIndex, partitionHash, chunks (<=256 entries).
- Internal index descriptor: index, hash, firstNs, lastNs (inclusive observed bounds).
- Leaf chunk entry: chunkIndex, chunkHash, firstNs, lastNs, firstOrdinal, lastOrdinal, firstGroupStart.
- firstGroupStart pointer P: directoryIndex, partitionIndex, chunkIndex, eventOffset, globalOrdinal, timeNs.
- BTL-TICK-INDEX-BINDING-2: schemaVersion, artifact, datasetId, datasetVersion, manifestHash, indexContentHash (all required).

Index node content omits version using the rule above; root.indexContentHash commits the time-root hash. Binding is created AFTER dataset hash: manifestHash=datasetVersion, indexContentHash must match root and time-root. Thus index is cryptographically pinned without a root↔index hash cycle. Each partition leaf binds its storage partitionHash; each chunk entry binds its chunkHash/range/ordinals. Index never asserts prices, freshness, closure or market chronology. Check hashes/versions and validate pointers against actual event at offset on access; index acceptance must prove completeness of every storage child and pointer, not merely hash internally consistent lies. Future backing database is a rebuildable acceleration cache, never substitute authority for these immutable artifacts.

Lookup is lower-bound on inclusive lastNs across root directory, directory partition, leaf chunk; choose FIRST candidate with lastNs>=requested time, including equal bounds (no bisect-right skip of a tie). Load chunk, lower-bound its source-order events. If candidate time equals that chunk's firstNs, follow firstGroupStart to earliest event of the complete group. If start is later inside chunk, walk to its first same-time event. Validate pointer's time and globalOrdinal, predecessor <group time (or dataset start), contiguous following members and successor >group time (or proven final EOF). Tail/head anchors are derived during ingestion; cross-partition/directory groups cannot be exposed partially. The <=1024 event group bounds recovery to <=1024 nonempty storage chunks in the worst case; usual full chunks reduce this, but no tighter packing is assumed. No invented chronology from chunk/global ordinals.

Semantics: before-first returns first full group; exact returns full equal-time group including any earlier-storage members; between groups returns next full group; after-final returns controller-private EOF, not a market consumer property. Unknown source coverage never changes this lower-bound rule into a continuity claim. Corrupt predecessor/successor/anchor, missing part of a group or a group overflow fails closed atomically. No nearest previous tick is forward-filled as a price.

Freeze optional IndexedTickDataProvider V2 capability separate from existing TickDataProvider V1. describe_v2(datasetId,datasetVersion)→root+completion+index binding; locate_v2(datasetId,datasetVersion,targetNs)→private position or private EOF; read_page_v2(datasetId,datasetVersion,position,maxEvents)→bounded canonical events/diagnostics and successor position. This is NOT passing a V2 root to V1 describe or reusing a V1 token under different semantics.

Position token exact shape: schemaVersion=2, artifact=BTL-TICK-POSITION-2, datasetId, datasetVersion, manifestHash, directoryIndex, partitionIndex, chunkIndex, eventOffset, globalOrdinal. Empty position is null only for private EOF. Locate returns {position,groupTimeNs}, both null at EOF, otherwise pointer identifies FIRST event of the complete lower-bound group. Page exact shape: schemaVersion=2, artifact=BTL-TICK-PAGE-2, datasetId, datasetVersion, events, diagnostics, nextPosition, endOfDataset. 1..256 requested events, <=1MiB / node budget; diagnostics V1 page shape <=128, no truncation. Position points to NEXT unread event; mid-group page position is allowed, locate position is always group start. Pages may cross seams or split ties; timeline owns complete atomic group. Validate next position progression, exact dataset/source binding and chunk offset; forged pointer cannot skip/reorder records in trusted traversal. Wrong dataset/version errors differ from true private EOF. Consumer never receives this capability, binding, pointer or total counts.

### Indexed timeline start, cursor, seek/resume and no-look-ahead

Future IndexedTickTimeline uses the optional V2 port; existing TickTimeline/SyntheticTickProvider and V1 cursor/chain remain unchanged. New timelineVersion=BTL-TICK-TIMELINE-2 explicitly separates identity. Initial sessionStartNs locates the first complete group >=start, not all history before start. Existing V1 advance clipping, bounded transactional reveals, UNKNOWN quality and trusted/untrusted sequence semantics are retained; group IDs still hash pinned datasetVersion/time/eventIds under the V1 group identity rule. No storage ordinal becomes trustedSequence.

V2 consumer cursor/reveal keep the exact V1 FIELD SETS but schemaVersion=2 and artifact=BTL-TICK-CURSOR-2 / BTL-TICK-REVEAL-2, timelineVersion above. nextGroupIndex is count of complete groups committed since sessionStart, NOT a dataset-global group index; lastGroupId/prefix chain use the same market semantics. Initial/step prefix objects use BTL-TICK-PREFIX-2 / BTL-TICK-PREFIX-STEP-2 with schemaVersion=2 and same remaining fields as V1, so no silent hash equivalence is claimed. Consumer sees only its committed prefix. Cancellation rolls back in-flight group/page/diagnostic state; reset increments generation, revokes views and repositions at sessionStart; dataset replacement pins a newly accepted root/version and retires old views. No mutable storage snapshot may be spliced into an existing generation.

Freeze controller-only checkpoint shape: schemaVersion=2, artifact=BTL-TICK-CHECKPOINT-2, cursor, advanceLogHash, positionLogHash. Private append-only disk logs store bounded blocks <=128 records / canonical budgets, hash-chain predecessor blocks, and pin dataset/timeline versions. Advance record: targetNs, predecessorCursorHash, successorCursorHash. Position record: groupIndex, position (start of group), groupId, successorCursorHash. Log hashes in checkpoint are tip hashes; logs are not market-consumer artifacts. No all-history schedule/list/group-count table in process RAM. Resume validates checkpoint/log chain and pinned completion, reconstructs from sessionStart via indexed provider and replays the exact recorded acknowledgement schedule to verify cursor/hash before returning; proportional to REPLAYED session prefix, not pre-session dataset history. A cursor alone never permits resume. Trusted persisted snapshots that avoid replay reconstruction are outside this frozen checkpoint; do not invent them.

Session prefix group navigation uses the private position-log disk index with explicit integrity verification; readRevealed rejects index>=nextGroupIndex and verifies groupId/source chunks. Seek resets generation and replays from indexed sessionStart to target (bounded pump), preserving prefix/hash semantics; jumping straight to seek target and pretending omitted session groups were revealed is forbidden. Starting a new late session is indexed; seeking far into an existing session may traverse that session's prefix. No misleading constant-time seek/resume claim.

Private log block exact shape: schemaVersion=2, artifact=BTL-TICK-ADVANCE-LOG-2 or BTL-TICK-POSITION-LOG-2, datasetId, datasetVersion, timelineVersion, generation, blockIndex, previousHash (null for first block), records (1..128 of the corresponding record shape above). Full canonical block hash, including pinned datasetVersion, is the log identity (no root cycle because session logs are not root children). Validate contiguous block indices, predecessor links, generation, cursor predecessor/successor hashes and agreement between the two logs. Any missing/mismatched block rejects resume; uncommitted tail is excluded by the checkpoint's pinned tips. Crash/cancel must atomically publish log tips with cursor only after complete group reveal commit. Tip checkpoint hashes do not authenticate an untrusted caller; host owns private durable state and verifies reconstruction. Disk lookups into position logs use verified block/record membership, never an unverified row offset.

Storage/controller may inspect future bytes to finish a group. RevealedView exposes only bounded read_revealed and cursor; no provider/index/manifest/completion/checkpoint/global ordinals/EOF/future groups/prices/coverage/diagnostic totals. Clip coverage and diagnostics to committed throughNs, recompute revealed counts; future source metadata hashes are opaque pinned identities, never numeric future information. Application capability separation remains for trusted composition, not a Python reflection sandbox. NO TRADE MAY BE SETTLED FROM OHLC DATA ALONE remains the target invariant; this checkpoint implements NO execution.

### Failure codes and conceptual complexity

Fail closed, without empty-success substitution: DATASET_MISMATCH, VERSION_MISMATCH, MANIFEST_HASH_MISMATCH, PARTITION_HASH_MISMATCH, CHUNK_HASH_MISMATCH, INDEX_HASH_MISMATCH, MISSING_DIRECTORY, MISSING_PARTITION, MISSING_CHUNK, MISSING_INDEX, DUPLICATE_PARTITION, RANGE_CONFLICT, COUNT_CONFLICT, ORDER_REVERSAL, INVALID_SOURCE_ORDINAL, DUPLICATE_DELIVERY, IDENTITY_CONFLICT, STALE_INDEX, CORRUPT_INDEX_POINTER, INCOMPLETE_INGESTION, INCOMPLETE_ATOMIC_BOUNDARY, GROUP_LIMIT, SOURCE_LIMIT, EVIDENCE_LIMIT, ARTIFACT_LIMIT, SCHEMA_MISMATCH, CANCELLED. Existing V1 errors remain unchanged. No skip/repair/sort/fabrication/interpolation/OHLC fallback.

Disk: O(N) market storage plus O(N) disk uniqueness tables and O(chunks) metadata. Stream validation O(N) event visits; B-tree uniqueness insertion approximately O(N log N), not falsely promised strict linear CPU. Hash/source verification requires reading complete input at ingestion, not every session start. RAM bounded by configured cache + constant depth + chunk/page/group/sidecar buffers, not all N identities. Timestamp navigation: binary lower bounds O(log256+log1024+log256) descriptor probes, bounded chunk scan plus atomic recovery <=1024 events/chunks. Runtime I/O/CPU is unmeasured. Forward replay is proportional to traversed session events/groups; prefix seek/resume can remain proportional to session history. Disk acknowledgement logs grow with session history; process RAM need not. No measured speed, billion-tick benchmark or concurrent-user claim.

Unresolved implementation choices (not frozen behavior): filesystem versus SQLite physical layout, compression codec, page-cache tuning, journal transaction granularity, native peak-memory tooling and local data directory. Later implementer must demonstrate bounds, crash safety and actual random-access/replay benchmarks; no heavyweight distributed infrastructure, data upload, public rights grant or frontend integration is inferred. All future Exness provenance/licensing/second-resolution/tie/gap limitations remain visible.

### Normative synthetic layout fixture and contract acceptance

The following is the sole V2 fixture owner; it is a tiny authored layout, not Exness or a production provider. Ordinals are distinct, all sequences absent, times in native ns. It intentionally splits a tie across chunks, partitions AND directories to protect against storage-driven semantics. Runtime-sized limits are verified arithmetically and with bounded canonical descriptor artifacts, not billions of real events.

<!-- BTL-TICK-STORAGE-CONTRACT-FIXTURES-2 -->
```json
{
  "schemaVersion": 2,
  "artifact": "BTL-TICK-STORAGE-CONTRACT-FIXTURES-2",
  "evidenceClass": "SYNTHETIC_CONTRACT_ONLY",
  "limits": {"directories": 256, "partitionsPerDirectory": 1024, "chunksPerPartition": 256, "eventsPerChunk": 256, "groupEvents": 1024, "capacity": "17179869184"},
  "layout": [
    [[["100", "200"]], [["200"]]],
    [[["200", "300"], ["400"]]]
  ],
  "lookups": [
    {"targetNs": "0", "expectedOrdinals": ["0"]},
    {"targetNs": "100", "expectedOrdinals": ["0"]},
    {"targetNs": "150", "expectedOrdinals": ["1", "2", "3"]},
    {"targetNs": "200", "expectedOrdinals": ["1", "2", "3"]},
    {"targetNs": "201", "expectedOrdinals": ["4"]},
    {"targetNs": "400", "expectedOrdinals": ["5"]},
    {"targetNs": "401", "expectedOrdinals": []}
  ]
}
```

Test-only oracle in backend/tests/test_tick_storage_contract_spec.py reads this fixture and uses existing CanonicalTick, BTL-CJSON-1, hashes and V1 validation. It is not importable production storage/index and does not certify performance. Required checks: V1/golden preservation; hierarchy/version/hash/source/instrument binding; explicit fan-outs and canonical budgets; child absence/hash/range/count/duplicate rejection; index wrong dataset/version/stale/mismatched link; all lower-bound cases; complete UNTRUSTED groups across seams; corrupt anchor/predecessor; incomplete publication. Future actual disk adapter must repeat these tests behaviorally plus crash/cancellation/reset/resume/no-lookahead and real measured benchmarks. Contract fixture success alone is not shipped V2 capability.

Validation evidence is recorded after running the applicable existing gates. Browser/full frontend build/product regression/database service exercise is exempt for documentation + test-only contract freeze: no mounted source/dependency/build configuration is modified. Existing V1 timeline, precision/evidence, golden, backend discovery, repository and AI bundle gates remain required; DB skips stay SKIP. Complete diff review must verify all backend/ticks runtime bytes and V1 fixture owner unchanged, no raw source/generated market artifacts/secrets/deletions.

Actual validation: 17 new contract methods PASS; full backend discovery 184 methods, 159 PASS and 25 explicit PostgreSQL/identity/workspace SKIP because isolated database is not configured (not release PASS). Includes unchanged V1 synthetic/timeline/precision/evidence/HistData/canonical tests. Independent Node reference: six golden vectors across three repeated runs PASS. Repository and AI-bundle deterministic/safety tests PASS. Final bundle generation/hash verification and Git remote equality are checkpoint completion gates. No browser, real ingestion, production time-index performance, memory benchmark or billion-tick runtime claim is made. Physical layout/compression/cache/transaction/measurement choices await separately authorized implementation.

Next separately authorized checkpoint: IMPLEMENT SCALABLE TICK STORAGE V2 + DISK-BOUNDED VALIDATION + TIME INDEX + INDEXED TIMELINE POSITIONING, PRESERVING V1 COMPATIBILITY; THEN INGEST AND BENCHMARK THE REAL EXNESS DATASET WITHOUT EXECUTION OR SETTLEMENT. Contract freeze only; no implementation, full Exness ingestion, execution, settlement, PnL, candle aggregation, frontend cutover or later roadmap phase started. Commit/push/actual Git equality/clean 0/0 then STOP, awaiting explicit authorization.

## 42.18 Scalable V2 implementation attempt — incomplete, contract reconciliation required

Human authorized implementation and full private local Exness benchmark from verified clean/equal main baseline 5184541cabfbac6bcb366f34d8cbac712d2575a1. Section 42.17 remains unchanged and normative. This section records an unfinished local attempt, not a completion checkpoint or new contract. No completed phase is added to history.

### Hard stop before changing the frozen provider contract

Section 42.17 requires offline acceptance of all evidence blocks, retained V1 coverage/gap semantics and clipped causal coverage/diagnostics. Its IndexedTickDataProvider defines describe_v2 returning root/completion/index binding, locate_v2 returning position/groupTimeNs, and read_page_v2 returning events/diagnostics/nextPosition/endOfDataset. Root contains only evidenceCatalogHash; page diagnostics contain V1 records/counts/truncated, not coverage/gap intervals. There is no specified bounded controller read of evidence sidecars. This creates an unresolved interface responsibility for nonempty evidence catalogs: a port-only indexed timeline cannot obtain those intervals from the frozen methods. Adding a metadata capability or extending a frozen response must be explicitly reconciled rather than silently redefining the contract.

Current draft supports empty evidence catalogs and conservatively UNKNOWN coverage; imports with nonempty catalogs reject EVIDENCE_LIMIT. This is a deliberate fail-closed **implementation limitation**, not a new zero-block contract limit. Silently ignoring positive or missing-data evidence, labelling all imported coverage UNKNOWN, loading all sidecars into memory, or coupling the timeline directly to a SQLite provider would not satisfy the target contract. The real Exness path has no affirmative coverage/provenance/rights evidence, but successful ingestion of that subset would not resolve general contract completeness. STOP invoked under the human's explicit hard-stop rule; no frozen shape changed.

### Preserved local draft and validation

Six new local files: backend/ticks/contracts_v2.py, storage_v2.py, exness_v2.py, timeline_v2.py, benchmark_v2.py, and backend/tests/test_tick_storage_v2.py. Draft uses standard-library SQLite WAL/FULL synchronization, content-addressed zlib-1 canonical payloads, disk UNIQUE event/source-ordinal and original-record hash indexes, bounded work journal, atomic private root/receipt publication, immutable navigation and a 16MiB measured-object cache. Indexed timeline has private hash-chained disk acknowledgement/position logs; consumer remains revealed-only. These files are uncommitted and are not advertised as a shipped complete V2 implementation.

One existing runtime line in backend/contracts/canonical.py uses an equivalent ASCII fast path in _text; non-ASCII still checks all surrogate code points and string length. Existing version gates, normalization, byte/hash rules and rejection semantics are retained. Unicode/size rejection cases and independent golden checks pass. This optimization must be reviewed explicitly; it is not a hidden frozen-contract change.

23 new small runtime tests PASS, including actual disk identity constraints, corruption/missing artifacts, hierarchy seams/ties across directories, index lower bounds and nested limits, incomplete publication, cancellation/finalization restart, cursor/reset/seek/resume/replacement, exact local CSV values and invalid-input rejection. Frozen 17 contract checks and V1 checks remain unchanged. Full backend discovery before the last two added cases: 205 methods, 180 PASS/25 explicit PostgreSQL-related SKIP; no configured isolated database, so skips are not release PASS. Entire frontend registered regression, lint, production build and local release distribution audit PASS. Independent Node six golden vectors across three runs PASS. No browser certificate claimed: infrastructure is unmounted; no frontend/API behavior changed. Final bundle/context/diff/Git completion gates have **not** been completed.

### Partial real-data observation — not a full benchmark

Source remains read-only: Exness_XAUUSDm_2015.csv. No raw CSV/ZIP, generated store, private price report or source credentials enter Git. Source hash is computed by ingestion and stored in the private journal; full dataset quality/count/coverage/storage/access/replay results are not reported as accepted evidence.

Three fresh ingestion attempts were deliberately interrupted: first at the last reported 200,000 rows to remove redundant ASCII character scanning; second at the last reported 300,000 rows to reuse already verified hashes and reduce transaction overhead; final measured attempt stopped for the contract hard stop after last progress 700,000 rows / 673.8923365 seconds, 36,102,144-byte cumulative peak Windows working set, 273,211,264 sampled disk bytes. Progress is not an exact final stop count; durable committed count/offset resides in the private journal. Earlier staging stores remain incomplete. The final private JSON report was not produced by the interrupted process; no final datasetVersion/completion receipt or completed source audit is claimed. These observations must not be extrapolated to full-file throughput, full-history bounded-memory acceptance, final storage size, or indexed/replay latency. Source provenance, licensing, completeness, freshness and same-time sequence remain UNVERIFIED/UNKNOWN.

Private staging resides under the machine's temporary BacktestLabTicksV2-5184541 folders, outside Git and OneDrive. SQLite rolls back any uncommitted bounded tail on reopen; no incomplete dataset is accepted as COMPLETE. Retain staging as incomplete until explicitly resumed or separately authorized cleanup. Original source was not modified.

Required next checkpoint: reconcile the evidence-sidecar/controller access responsibility in the existing Section 42.17, with bounded metadata access, all-block offline acceptance, causal clipping and no provider capability in RevealedView. Planning/contract authorization must not start financial execution. After the interface is reconciled, finish implementation, rerun full real-source ingestion/benchmark with final code, all applicable gates, authority update and normal commit/push/remote equality. **NO EXECUTION, SETTLEMENT, PNL, CANDLE AGGREGATOR OR FRONTEND CUTOVER WAS IMPLEMENTED.**

## 42.19 V2 evidence-sidecar access reconciliation — planning/contract only

This section extends the single frozen V2 authority in 42.17 solely for evidence access and causal projection. It supersedes the missing-access finding in 42.18 at specification level, not the unfinished runtime. CanonicalTick V1, existing V1 APIs/goldens, the three existing V2 methods, root/catalog/block field sets, descendant hash omissions, storage capacity/fan-outs, receipt/binding fields, atomic groups and timeline cursor/reveal/log/checkpoint fields remain unchanged. No runtime continuation, real benchmark, execution, settlement, aggregator, account mutation or frontend cutover is authorized by this checkpoint. No Exness-specific rule enters this generic contract.

### Baseline, provenance and checkpoint separation

Actual main/local/origin/GitHub baseline is 5184541cabfbac6bcb366f34d8cbac712d2575a1, ahead/behind 0/0. Working tree was already dirty and matches the interrupted 42.18 attempt: modified AI_CONTEXT/04_CURRENT_PHASE.md and this blueprint (42.18), one-line ASCII fast path in backend/contracts/canonical.py, and six untracked draft files named in 42.18. No unrelated edit was discovered. Those runtime/test draft bytes must remain unchanged during reconciliation. New changes here are documentation and a separate test-only contract oracle; they do not certify the preserved draft.

The first planning attempt stopped before commit because the human prohibited mixing the dirty runtime draft into planning. The subsequent explicit repository-reconciliation authorization permits Git-native separation. That historical conflict is now resolved without reset, stash, clean, merge, runtime rewriting or loss of input. Two local preservation refs were created from the same baseline:

- `codex/reconciliation-input-42-18-42-19` at `2c65d2d043530605df2b43633e64dfe8e97dc303`: exact-byte snapshot of all 14 initially changed runtime/test/planning files, retaining the historical mixed state and provenance. It is a preservation snapshot, not a completion checkpoint.
- `codex/preserve-42-18-draft` at `a62fbd4161a3956544d4d9611056c67a1313e998`: seven unchanged runtime/test files plus the historical 42.18 findings, excluding 42.19 planning/oracle changes. Attached worktree: `C:/Users/kuchi/.codex/worktrees/preserve-42-18/Backtest lab`. This branch is NOT merged into main and is not runtime acceptance.

Each preservation branch alone has path-specific `-text` rules in its own tracked .gitattributes to prevent Git normalizing the original bytes; storage_v2.py contains CRLF. These helper rules do not enter main. Existing Markdown hard breaks and all input bytes remain recoverable from the full snapshot. Main's canonical runtime is restored to baseline only after verifying the seven source/worktree/blob hashes; the six untracked runtime/test duplicates are removed only from main after preservation. The actual draft remains intact in its own worktree and immutable Git blobs. Main retains the historical 42.18 report as knowledge/provenance documentation, never its runtime code.

Pre-separation SHA-256 = post-separation worktree SHA-256 = preservation-commit blob SHA-256 for every row:

| 42.18 runtime/test file | Pre = post SHA-256 |
| --- | --- |
| backend/contracts/canonical.py | aa920232ca54b6d61a4b92b0a8949d88b3cc37aca986bffe5c746d77bbe2decf |
| backend/ticks/contracts_v2.py | 32afc7e598bfe1406fa35313504ea36013650617daf374a12a7bb758033a9733 |
| backend/ticks/storage_v2.py | d8348d1e790f25e43e5922bfacef8bc0789cc851a0cf9b767e7229f15a0f89bc |
| backend/ticks/exness_v2.py | 5c54d0b6ca10ee771aa4403b51887688fd220577b1110ab1d6e3620f3c1766ea |
| backend/ticks/timeline_v2.py | e61c2210092266ce1a2d444e9f25fd460fc21bc86483fcd1d20c8797e835e57d |
| backend/ticks/benchmark_v2.py | 8f2e46bc0c8ee542086980ed23405602c33214b2efb600cccf848b237a2bebd0 |
| backend/tests/test_tick_storage_v2.py | dc1aedbf5e1490c45184ca3f4c1025134186ad894febb2902d2e1b52459e5fb3 |

### A. Authoritative sidecars and immutable identity

A sidecar is a root-committed immutable metadata artifact, not a mutable provider note or work-journal row. Source catalog, evidence catalog and its evidence blocks are authoritative for **recorded source/declaration consistency**; navigation index is authoritative only for validated navigation, never market evidence. A hash/receipt does not certify provider truth, availability, licensing, completeness or sequence. Rights stay host/private; no automatic PUBLIC_GRANTED entitlement follows from a declaration.

Use the exact 42.17 source/evidence catalog/block shapes. Evidence catalog children have consecutive index strings, hash, firstNs, lastNs, recordCount; <=256 children. BlockIndex matches its descriptor. Each block contains <=128 combined coverage intervals, gap intervals and diagnostic records (rights is one required declaration, not an event). <=32,768 combined entries total, with tighter canonical budgets always winning. Descriptor recordCount equals that combined entry count. For nonempty blocks firstNs is the minimum interval start/diagnostic time, lastNs the maximum inclusive covered ns (endNs-1) or diagnostic time. Rights-only blocks use root startNs for both descriptor bounds and recordCount=0; an empty catalog conveys the defaults in 42.17. Descriptor time ranges may overlap because coverage and gaps are different streams; they are navigation hints, not evidence chronology. Array order is deterministic blockIndex order, not a market ordering claim.

All materialized sidecars must match datasetId/datasetVersion/providerId/feedId/instrumentId. Verify the pinned root hash equals datasetVersion/manifestHash, evidenceCatalogHash/sourceCatalogHash equal root references, every descendant hash follows the unchanged version-omission rule, and header versions match the root. No root hash cycle or additional root field is introduced. Changing any authoritative sidecar changes the datasetVersion. Missing, partial, malformed, foreign or corrupted sidecars cannot become accepted defaults or successful EOF.

### B–C. Controller ownership and bounded access API

Add one **controller-only** optional companion capability to IndexedTickDataProvider V2: `read_evidence_v2(request) -> page`. Implementations may compose separate storage/evidence adapters behind this capability. The timeline uses this generic port, never SQLite/filesystem internals; RevealedView receives neither the reader nor private request/page/cursor. Existing describe_v2/read_page_v2 response shapes are not expanded. Tick pages retain V1 diagnostic shape; evidence-window queries are the sole owner for sidecar interval projection and diagnostic delivery. Any diagnostic duplicated through a tick page must match the accepted sidecar identity and is not independently revealed twice.

Exact new request fields:

`schemaVersion=2, artifact="BTL-TICK-EVIDENCE-REQUEST-2", datasetId, datasetVersion, manifestHash, sessionStartNs, fromNs, throughNs, sourceFence, maxRecords, cursor`.

All ns/ordinals are the existing unsigned canonical strings. `sessionStartNs <= fromNs <= throughNs`; each internal window <=86,400,000,000,000 ns (24h). This is a metadata transport bound, not a new maximum session/advance/seek duration. Controller may issue multiple bounded queries for one staged reveal and must retain final reveal budgets. `maxRecords` is an integer 1..128, not bool. `sourceFence` is a list <=128 of exact `{sourceId, rawOrdinal}` pairs, unique and ordered by source-catalog order, derived only from accepted groups already committed or staged for this reveal. Each value is the greatest revealed rawOrdinal for that source in the current session. It is not trusted market sequence and does not import pre-session source history. No entry means no eligible diagnostic from that source. The host owns/validates this fence; an arbitrary caller's alleged replay time/fence is not an authorization credential.

Exact new private page fields:

`schemaVersion=2, artifact="BTL-TICK-EVIDENCE-PAGE-2", datasetId, datasetVersion, manifestHash, evidenceCatalogHash, requestHash, coverage, diagnostics, nextCursor`.

`requestHash` = SHA-256 of the full canonical request with cursor replaced by null; thus bounds, sourceFence and quota are fixed throughout pagination. `coverage` has the existing V1 interval shape. `diagnostics` has the existing records/counts/truncated shape, counts recomputed for this page and truncated=false. Combined returned coverage intervals plus diagnostics <=maxRecords and <=128, plus <=1MiB/node/depth budgets. A page may contain coverage only. Coverage is emitted once on the first page; no duplicate coverage on continuations. All canonical values/results are immutable snapshots or independent copies. Unsupported oversized evidence is explicit EVIDENCE_LIMIT/ARTIFACT_LIMIT, never truncated delivery.

Cursor is null for the initial query, otherwise exact `schemaVersion=2, artifact="BTL-TICK-EVIDENCE-CURSOR-2", datasetId, datasetVersion, manifestHash, evidenceCatalogHash, requestHash, blockIndex, entryOffset`. BlockIndex/entryOffset refer to the next unread flattened entry (coverage, then gaps, then diagnostics) of accepted blocks; validate bounds and canonical progression against accepted catalog/block contents. Index 256, offset 128 are not valid live positions. Cursor identities/queryHash must match request/page. `nextCursor=null` means the bounded query is exhausted, **not dataset EOF**. These cursors remain host-private navigation, not cryptographic proof of a consumer's authorization; controller starts at null and follows only validated successors, never accepts a consumer-supplied cursor.

Requests are time-window scoped, independent of chunk/partition packing; the reader validates catalog descriptors and streams potentially overlapping blocks, with at most one <=1MiB block, one bounded page, <=256 descriptors and <=128 source fences in active RAM. Total shared provider/controller cache remains <=64MiB; do not retain all <=256MiB of blocks. A request may inspect bounded future metadata privately to validate/filter it, but returns only the projection rules below. A private acceleration index is permitted only if independently rebuildable and hash-bound to the accepted catalog; no new authoritative index/root field is defined here. No array/list of all future gaps, all sidecars or all-history diagnostics is returned.

### D. Causal visibility, conservative classification and lifecycle

The existing interval schemas contain no evidence-publication time or complete causal dependency proof. An opaque evidenceHash, interval end or offline acceptance cannot prove a classification was knowable at replay time. **Therefore this frozen reconciliation does not promote DECLARED_COMPLETE, INCOMPLETE, KNOWN_SESSION_CLOSED or MISSING_DATA declarations into affirmative live replay coverage.** Their exact declarations remain validated in private sidecars for research/audit. Adding certified causal-availability declarations would require a separate explicit contract checkpoint; it is not required for the local conservative implementation to resume later.

Coverage returned for every nonzero requested [fromNs,throughNs) is one interval with status=UNKNOWN/evidenceHash=null. A zero-width window returns none. This normalization is deliberately independent of the existence, endpoints, kind, evidenceHash or count of private intervals. Do not emit UNKNOWN subsegments that encode hidden gap boundaries. A gap beginning before T and ending after T produces no endpoint/duration/classification disclosure; a wholly future gap produces no disclosure. Even a completed historical interval is not automatically certified by its endpoint. No inference of session closure, missing price path or continuity. This conservative mode retains authoritative declarations without converting retrospectively known metadata into live knowledge.

Diagnostic visibility is separately constrained: timeNs is located and <=throughNs, >=sessionStartNs, sourceId is in sourceFence, rawOrdinal <=that source's fence, and offline acceptance verified the exact original source record and source/member identity. Only row-local codes MALFORMED_PRICE, MISSING_SIDE, CROSSED_QUOTE and UNSUPPORTED_RESOLUTION are eligible under this contract; their occurrence is determined by that already-passed record alone. INVALID_TIMESTAMP without an independently valid location prevents publication; ORDER_REVERSAL/SUSPECT_REPEAT and any conclusion depending on later records remain private retrospective diagnostics, not consumer-visible live evidence. Unsupported diagnostic codes are rejected at ingestion; allowed but noncausal codes are retained privately. No free-text provider details, filenames, URLs, rights declarations or future acquisition metadata are returned to consumers. Visible diagnostics retain only the existing exact diagnostic record fields whose contents must be row-local; later analysis cannot be smuggled into code fields. A source fence is necessary to prevent a later raw record with an old timestamp from being exposed early.

The controller requests evidence for its tentative complete-group boundary and commits it atomically with that reveal's cursor/log tips. It deduplicates diagnostics by the V1 sourceId/rawOrdinal/code identity in private disk state; delivery in a newly eligible fence may have an old timeNs within the session. Earlier prefix bytes/hashes are never rewritten or retroactively promoted. Hidden suffix changes under a fixed pinned identity cannot alter earlier visible coverage, diagnostics, page count or market cursor; metadata continuations are never exposed to consumers. If fully collected evidence exceeds reveal budgets, reject without cursor mutation and require a smaller controller target; do not drop records. Cancellation rolls back staged metadata/fence/dedup state together with groups.

Dataset beginning: before first observed tick, no source fence exists, diagnostics are absent, coverage is UNKNOWN; root start/count are not projected. Dataset end: silence after last quote still returns UNKNOWN through the requested T; no clipping to root.endNs, final-gap length, positive closure, final diagnostic counts or EOF flag. An empty evidence catalog behaves identically for coverage. Zero-width advances at a group time may reveal new eligible row-local diagnostics but no interval. Full unresolved timestamp groups become visible atomically; neither a fence nor diagnostics can commit halfway through a group. Untrusted ties stay UNTRUSTED.

Seek resets generation and reconstructs the revealed session prefix using existing bounded acknowledgement rules, including metadata fences/dedup. Reset revokes old views/cursors/fences and starts with no visible diagnostics. Resume pins the same root/receipt/catalog, validates existing disk log hashes and replays the recorded acknowledgement schedule to reconstruct evidence deterministically; a new transport cursor is not a replay checkpoint. Dataset replacement retires all old metadata cursors/fences with the old generation and binds the replacement independently. Existing checkpoint field sets remain unchanged; derived fence/dedup state is rebuilt or stored as non-authoritative disk acceleration, never an unbound new resume authority. Consumer still has only revealed reads/cursor, no metadata API.

### E–F. Full offline validation, publication and recovery

Before atomic COMPLETE, stream **every** authoritative source/evidence/index artifact, including those outside all replay windows. Check exact schemas/version/header identities, root/manifest/content hashes, descriptor counts/bounds/ranges, consecutive block indices and size/node/depth limits. Validate V1 coverage/gap kinds and evidence requirements; each interval lies within the observed root range. Across all blocks each coverage stream and each gap stream is nonoverlapping in sorted time order; use bounded external/disk ordering checks rather than importing all records into process RAM. DECLARED_COMPLETE overlapping any gap is COVERAGE_CONFLICT, including across blocks. All rights declarations must agree with the root evidence class and each other. No hash alone proves an external license grant.

Diagnostics must be fully located, mapped to source/member hash, source ordinal and actual audited input, with accepted known codes and unique sourceId/rawOrdinal/code identities. Where invalid input is quarantined rather than rejected, require V1 MISSING_DATA bounds and conservative quality; no unlocated invalid timestamp can pass. Do not invent a tick for a diagnostic. Evidence catalog descriptors must exactly summarize actual block entries; duplicate/missing/conflicting entries cannot be hidden in pagination. An evidence interval does not claim a candle or price.

Old evidence shapes contain no chunk/partition reference fields; do not fabricate new ones. If an accepted event/source/diagnostic or private acceleration index references an existing source/event/chunk/partition, check existence, hash, identity, time/range and source ordinal agreement with the accepted hierarchy. All time-index cross-links/atomic anchors remain validated as in 42.17. No storage/index reference may establish positive coverage. Runtime verifies accessed immutable bytes against accepted root/catalog and validates projection/page/cursor bindings again; hash-valid but foreign or dishonest envelopes are not sufficient.

Use the existing INGESTING→VALIDATING→INDEXING→FINALIZING→COMPLETE lifecycle. Catalog/blocks/source/index bodies and the complete offline validation proof precede the unchanged root/receipt atomic publication. Partially written/missing/corrupt evidence makes the whole dataset INCOMPLETE_INGESTION or an explicit integrity failure, never an accepted empty catalog. Restart verifies input/source hash, adapter/validator identities, committed child hashes and bounded journal offsets; reprocess rolled-back staging and rerun full sidecar acceptance before publishing. Crash before publication leaves unavailable staging; crash after publication must return the identical immutable root and validated sidecars. No new physical technology/transaction model chosen by this planning checkpoint.

Failure names reuse frozen SCHEMA_MISMATCH, DATASET_MISMATCH, VERSION_MISMATCH, MANIFEST_HASH_MISMATCH, CHILD_HASH_MISMATCH, RANGE_CONFLICT, COUNT_CONFLICT, IDENTITY_CONFLICT, INCOMPLETE_INGESTION, EVIDENCE_LIMIT, ARTIFACT_LIMIT, CORRUPT_INDEX_POINTER and CANCELLED, plus existing V1 COVERAGE_CONFLICT/UNLOCATED_INVALID_RECORD/INCOMPLETE_DIAGNOSTICS where applicable. Missing sidecar is an explicit missing-child/incomplete error. A stale or forged evidence cursor is an explicit identity/query/pointer failure. No empty-success substitution, candle fallback or inferred market path.

### G. Adversarial no-look-ahead review

| Attempted leak/failure | Required prevention |
| --- | --- |
| Gap [100,300), T=200; reveal end or length | Uniform UNKNOWN [from,200); no raw interval/end/hash/kind exposed |
| Future gap versus no gap changes segment/page count | Same coverage projection; metadata pagination/controller work stays private |
| Gap classified only after a later quote | No affirmative live classification from legacy declarations, even after its end |
| Private catalog says complete/closed or PUBLIC_GRANTED | Retain private declaration; no live completeness, closure or licensing promotion |
| T exceeds final quote; empty reader page leaks EOF | UNKNOWN through requested T, no EOF/total/root bounds exposed |
| Future diagnostic uses an old timestamp | Source fence + source-record validation + row-local code restriction |
| Later heuristic appended to a diagnostic | Non-row-local codes/details remain private; reject unsupported wire fields |
| Mid-group source fence exposes the next tied row | Commit fences/evidence only with the whole atomic timestamp group |
| Foreign version/catalog or cursor replayed in a new query | Root/catalog/requestHash binding + pointer validation; reset/replacement revocation |
| Hash-valid range/count lies or conflict hidden in an unused block | Full all-block offline acceptance, disk cross-block consistency checks |
| Cancellation after metadata page but before reveal acknowledgement | Roll back staged dedup/fence/cursor/log tips; no partial consumer exposure |
| Resume ignores metadata or seek jumps over its session prefix | Reconstruct fences/diagnostics and exact prefix hash from the pinned schedule |
| Consumer calls sidecar API or infers total from a private token | Capability absent from RevealedView; no request/page/token/catalog counters projected |

Application capability isolation is for trusted host composition, not an arbitrary-Python reflection sandbox. Timing/I/O side-channel resistance against malicious same-process code is not certified. Hashes remain opaque identity; do not expose future numeric metadata with them.

### H. Impact on preserved 42.18 draft and next authorization

| Existing draft | Required later implementation work; no changes now |
| --- | --- |
| contracts_v2.py | Preserve storage hashes/shapes; add separate request/page/cursor validators and sidecar semantic validation |
| storage_v2.py | Keep bounded CAS/identity/journal/index framework; admit/validate all evidence blocks, implement generic bounded access, stop rejecting all nonempty catalogs |
| timeline_v2.py | Keep indexed groups and causal capability boundaries; stage query/fence/dedup with reveals, remove blanket rejection of valid diagnostics, reconstruct metadata on reset/seek/resume |
| exness_v2.py | Keep provider-specific parsing private; no generic assumption that Exness grants rights/coverage; empty catalog remains valid UNKNOWN |
| benchmark_v2.py | No rerun now; later full ingestion with final code and honest complete/partial measurements |
| test_tick_storage_v2.py and canonical.py | Preserve byte-for-byte; existing hierarchy/identity/tie/index/lifecycle/Unicode cases remain useful, not proof of evidence support |

Draft violations of the reconciled target: builder always emits an empty evidence catalog; reader rejects all nonempty catalogs; timeline rejects nonempty diagnostics and has no accepted-sidecar access or source fences/dedup reconstruction. These are incomplete capabilities, not proof of runtime conformity. Existing UNKNOWN coverage agrees with conservative projection, but it currently does not validate/retain nonempty declarations. No production V2 completion claim.

Later tests must cover nonempty multi-block evidence, cross-block overlap/conflicts, missing/foreign/corrupt/hash-valid lies, rights-only/empty catalogs, 128/256/32,768 and canonical budgets, deterministic bounded pagination/stale cursors, source-fence advancement, future/backdated/non-row-local diagnostics, hidden gap-boundary normalization, before-first/after-last equivalence, atomic ties, cancellation and metadata-aware reset/seek/resume/replacement. Ordinary tests remain small deterministic fixtures, not the real Exness file. Planning oracle tests validate the rules/fixture expectations only; they are not a provider or runtime benchmark.

Next possible implementation requires separate human authorization **after checkpoint separation is resolved**: resume the preserved draft against 42.17+42.19, complete sidecar validation/access/causal evidence, run full generic acceptance, then restart the full private Exness benchmark from an explicitly valid state, update existing authority and commit/push/verify. No execution, settlement, PnL, candle aggregator or frontend cutover. STOP at the present planning checkpoint.

### Normative small planning examples and validation scope

The diagnostics time scope is [sessionStartNs,throughNs], additionally restricted by sourceFence, not merely [fromNs,throughNs]: a row-local record can become eligible in a later fence while retaining an earlier timestamp. The transport's 24h bound applies to its coverage window. Repeated queries may rediscover eligible diagnostics; the controller's transactional disk dedup prevents repeat delivery. A private page returning no records may still advance its validated cursor across ineligible entries; it cannot stall or fabricate dataset EOF. This remains bounded by the 256/128 catalog/block limits, with no history-sized process set.

<!-- BTL-TICK-EVIDENCE-ACCESS-FIXTURES-2 -->
```json
{"schemaVersion":2,"artifact":"BTL-TICK-EVIDENCE-ACCESS-FIXTURES-2","requestFields":["schemaVersion","artifact","datasetId","datasetVersion","manifestHash","sessionStartNs","fromNs","throughNs","sourceFence","maxRecords","cursor"],"pageFields":["schemaVersion","artifact","datasetId","datasetVersion","manifestHash","evidenceCatalogHash","requestHash","coverage","diagnostics","nextCursor"],"limits":{"catalogBlocks":256,"blockEntries":128,"pageRecords":128,"sourceFences":128,"coverageWindowNs":"86400000000000","bytes":1048576,"cacheBytes":67108864},"eligibleCodes":["MALFORMED_PRICE","MISSING_SIDE","CROSSED_QUOTE","UNSUPPORTED_RESOLUTION"],"cases":[{"id":"straddling_gap","fromNs":"100","throughNs":"200","gapStartNs":"150","gapEndNs":"300","expected":"UNKNOWN"},{"id":"wholly_future_gap","fromNs":"100","throughNs":"200","gapStartNs":"300","gapEndNs":"400","expected":"UNKNOWN"},{"id":"past_declaration_without_availability_proof","fromNs":"100","throughNs":"200","gapStartNs":"100","gapEndNs":"150","expected":"UNKNOWN"},{"id":"before_first","fromNs":"0","throughNs":"50","gapStartNs":null,"gapEndNs":null,"expected":"UNKNOWN"},{"id":"beyond_private_eof","fromNs":"300","throughNs":"400","gapStartNs":null,"gapEndNs":null,"expected":"UNKNOWN"},{"id":"zero_width","fromNs":"200","throughNs":"200","gapStartNs":null,"gapEndNs":null,"expected":"EMPTY"}]}
```

The separate backend/tests/test_tick_evidence_access_contract_spec.py is a DESIGN ORACLE ONLY. It reads this single fixture owner, exercises conservative projection/row-local fences, query/cursor identity, all-block consistency and canonical limits using authored examples, and does not import/modify the V2 runtime drafts. Planning validation includes this oracle, unchanged 42.17/V1/precision/canonical tests, independent Node vectors, repository and bundle gates. Browser, frontend build/product regression, real dataset ingestion and database service tests are not claimed for this documentation/test-only checkpoint. Earlier 42.18 partial benchmark is not completion evidence. Results and dirty-checkpoint conflict are recorded before STOP; no history entry describes a pushed/completed phase until Git gates succeed.

Prior planning-attempt validation (before separation): 88 focused contract/V1/timeline/precision/HistData/canonical methods PASS, including six new planning-oracle methods; an initial oracle field-count assertion failed and was corrected without altering contract fields or runtime, then the full 88-method set passed. Independent Node six golden vectors across three runs PASS. Repository authority/boundary tests and AI-bundle determinism/safety tests PASS. Bundle generation/freshness verification PASS (142 files); all seven preserved runtime/test draft fingerprints match the starting audit. Complete diff/whitespace review PASS; the entire committed blueprint including 42.17 remains unchanged. Nothing staged or committed. Final local HEAD = origin/main = actual GitHub main = 5184541cabfbac6bcb366f34d8cbac712d2575a1, ahead/behind 0/0; working tree remains explicitly dirty. No SKIP in the 88-method set; browser/product/database-service/real-benchmark gates are NOT RUN for this planning-only checkpoint, not labelled PASS. This is specification validation, not runtime conformance. No commit/push performed because protected implementation drafts preclude a clean planning-only checkpoint under the supplied separation rule.

Repository reconciliation validation is run again on main without the seven runtime/test draft files and with the original canonical runtime. Only the six planning documentation owners, phase-history bookkeeping and backend/tests/test_tick_evidence_access_contract_spec.py may enter the main checkpoint. No preservation .gitattributes, draft source, raw CSV/ZIP, private staging store or benchmark artifact enters main. The contract content and fixture in 42.19 remain unchanged during separation. The existing 42.18 report remains historical partial evidence; preservation commits do not turn it into an accepted runtime release or complete benchmark. Separate human authorization is required to resume implementation. STOP after normal main commit/push/equality/clean 0/0 and final preservation fingerprint checks.

Actual reconciliation gates: all 88 focused contract/V1/timeline/precision/HistData/canonical methods PASS on main using the unchanged baseline canonical runtime, with zero SKIP/FAIL in the final run. Independent Node six golden vectors across three runs PASS; repository and AI-bundle deterministic/safety tests PASS. Seven pre/post worktree and preservation-commit blob hashes match; baseline 42.17, normative 42.19 content and its oracle bytes are unchanged. Complete main diff contains documentation and the test-only oracle, no runtime/data/dependency/frontend change. Bundle regeneration/verification and normal main Git checkpoint/equality are final completion gates. Browser, product build/full regression, database-service exercise and real Exness ingestion/benchmark NOT RUN for this repository/planning-only checkpoint, not labelled PASS. The earlier 700,000-row progress remains partial and interrupted. Preservation refs remain local and recoverable; only planning main is pushed in this checkpoint.


## 43. V2.1 tick-first functional integration / V2.2 precision validation — design decision

> **Planning only (2026-10-09).** Delivery checkpoints, acceptance criteria, non-goals and Git governance live in the existing `docs/ROADMAP.md` section “V2.1 Functional Alpha → V2.2 Precision Beta”. This section is architecture guidance, **not** a Phase 43 implementation authorization, an amendment to frozen Sections 42.17/42.19, or a claim that V2.1/V2.2 has shipped.

### Ownership and seams

- **Canonical tick data / time:** existing tick provider, authoritative ordered timeline, bounded cursor/seek and frozen evidence contract. Preserve unknown same-timestamp ordering as uncertainty unless evidence supplies a stable sequence.
- **Execution domain:** a **single** tick-driven command/event implementation, used with small fixture providers in V2.1 and disk-indexed historical providers in V2.2. Long entry Ask/exit Bid; short entry Bid/exit Ask. Pending activation, SL/TP, gaps, position/account arithmetic and idempotency must be explicitly specified and golden-tested. A quote-based model is not proof of broker fill.
- **Application:** Method/Session rules, Protocol checklist, review/confirmation, identity, state persistence, replay lifecycle and evidence provenance. Enforce rules at the domain boundary, not only by disabling UI controls.
- **Presentation:** reuse existing Lightweight Charts workspace, drawing, indicators, prototype UX and Analysis. Display candles may aggregate already-revealed ticks; OHLC must never decide execution. No independent synthetic trade status presented as authoritative.
- **Research/evidence:** all trading/Analysis views consume the same engine events with dataset/version/parameter/cost provenance. Unsupported settlement/margin models must be labeled unavailable; fixtures are explicitly marked as fixtures.

### Implementation dependency order

First reconcile actual repository and preserved 42.18 local draft; inspect whether the existing SyntheticTickProvider/Timeline can support a complete small-fixture tick vertical slice without completing V2 storage. Then establish engine-driven trade lifecycle and golden tests, followed by Method/Session persistence, chart integration, Analysis and UX acceptance. Large historical ingestion, full sidecar/storage benchmark, independent historical precision audit and stress belong to V2.2 unless a smaller prerequisite is proven necessary. No new alternative storage contract or second execution engine.

### Non-negotiable acceptance

V2.1: one new user can complete Method → Session → chart/drawings/indicators → tick replay → validated order → event-derived result/Analysis → save/reopen, in a real browser, without critical interaction blockers or cross-pane state divergence. Core correctness includes side-aware Bid/Ask, same-time ordering policy, gap, idempotency, seek/reset determinism and no look-ahead. V2.2: independently verified historical fidelity and reproducible resource/performance budgets on specified data/hardware, not unmeasured claims.

No runtime authorization arises from this section. `AI_CONTEXT/04_CURRENT_PHASE.md` must be updated through a separately scoped authorization; every checkpoint follows `AI_CONTEXT/06_WORKFLOW_RULES.md`.

### V21-0 repository reconciliation and fixture-first readiness evidence

The human requested the actual repository audit and then authorized its proposed reconciliation/readiness action. Incoming 4f140db, 6573c95 and f968cd5 changed only this owner, ROADMAP and AI_HANDOFF. They were adopted fast-forward-only from 2892e17 after exact preservation of the interrupted work. Pre-documentation main baseline was f968cd5ad7407b71f05ae7eea0959e18ff7b4489, equal to origin and actual GitHub main with clean 0/0. No reset, rebase, force push, blanket draft merge or historical-document deletion.

The 15 known 42.20 files were preserved as exact raw Git blobs in a local-only snapshot plus a separate managed worktree; every pre/post SHA-256 matched. Seven tracked files were restored only after preservation proof, and eight untracked files were moved to a private archive, not discarded. Original 42.18 worktree/ref and its seven fingerprints remain unchanged. The separate drawing spike has three fixture/preparation files; it neither selects a donor nor changes production. Preservation locations/refs and private process measurements are reported to the human locally, not published as machine paths here.

The active private benchmark was stopped in a recorded relocation attempt and resumed with the same ten runtime fingerprints from the preservation worktree against the same durable source-pinned store. This preserves the prior 42.20 authorization without mixing its runtime into V21-0. The benchmark remains incomplete; no publication, execution accuracy, full-dataset performance or release acceptance is inferred. Earlier 700k staging remains partial. Closing 42.20 still requires its actual full measurement and separate runtime/Git gates.

| Boundary | Actual readiness / missing work |
| --- | --- |
| Fixture ingress | Existing `backend/ticks/provider.py` SyntheticTickProvider accepts authored exact Bid/Ask, ns time, identity and optional trusted synthetic sequence; fixture provenance remains SYNTHETIC / TEST ONLY. |
| Replay/controller | Existing `backend/ticks/timeline.py` TickTimeline delivers atomic groups through RevealedView; controller alone owns advance/seek/reset/resume. Existing tests cover ties across pages/chunks, clipping, hidden future suffix, cancellation, stale cursor, reconstruction and replacement. |
| Large disk storage | Not necessary to exercise a small-fixture vertical slice. The incomplete 42.20 runtime stays separate; V1 limits are not raised and no alternate storage/provider engine is created. |
| Execution | Missing: a single exact, side-aware tick command/event domain under the existing Execution/Financial Contract. A revealed quote alone is not a fill. |
| Settlement/durability | Missing: simulated account/order/position transitions and atomic command/event/session dedup persistence. Existing application intake reports NOT_EXECUTED; it must not be relabelled settlement. |
| Browser | Existing FigmaWorkspace still invokes legacy candle useTrading. Method/Session demo is a prototype. Neither is a tick-driven trade result; integration awaits the implementation checkpoints. |

**V21-1 input is available; execution is not implemented.** Before engine code, materialize the existing frozen financial golden examples: side-aware market/limit/stop, SL/TP gap prices, same-event activation/exit, trusted/untrusted ties, idempotency/revision, cancellation order, exact lot/money precision, costs, partial/full exit, no-quote end, atomic recovery, Protocol restrictions and rewind/fork. Use RevealedView/acknowledged controller results only; unrestricted provider/index/sidecar handles never reach execution consumers. Keep the existing instrument/profile identities and explicit simulation/uncertainty taxonomy. No new fee, margin, slippage, broker-fill or candle-fallback assumption is permitted by readiness alone.

Validation on the reconciled main: 88 existing timeline/contract/precision/HistData/canonical methods PASS, zero skips; six independent Node canonical vectors across three runs, repository authority/boundary tests and bundle determinism/safety tests PASS. These test the foundation, not a missing execution engine. Regenerated bundle freshness and Git closure remain final gates. Production/browser/full-regression/build/database-service reruns are exempt for documentation-only changes; the separate private benchmark is not a substituted PASS. Applicable Git completion is verified after normal commit/push. Operational scope remains solely in 04_CURRENT_PHASE; changing the prior frozen Alpha ordering to the newer V2.1 sequence requires the next bounded human authorization.

### V21-1 authorized bounded implementation scope

After V21-0 at clean/equal eeea90fde90ef06432f0789d1a2e4a911a3d499b, the human submitted the supplied V21-1 implementation prompt. This authorizes only ROADMAP V21-1 and the minimal durable prerequisite mandated by the existing Execution/Financial Contract. It supersedes the old Alpha delivery order for this checkpoint, not frozen financial/storage/evidence semantics or the entire V2.1 journey. No merge of either preserved disk draft, new database, UI cutover, provider acquisition or V21-2 implementation.

Ownership/file boundary: new `backend/execution/{__init__,contracts,engine,controller,postgres,fixture_demo}.py` owns the one tick command/event reducer, controller-only coordination, adapter to the existing PostgreSQL connection, and explicitly opt-in synthetic CLI inspection. Add only `backend/infrastructure/migrations/005_tick_execution.sql` for isolated tick session/command/event/checkpoint tables; existing nonexecuting intake and v1 account stay intact. New authored `backend/tests/fixtures/tick_execution_v1.json`, `test_execution_goldens.py`, `test_tick_execution.py` and `test_tick_execution_postgres.py` own acceptance. The only existing tick-runtime extension permitted is an opt-in authored-quality argument in SyntheticTickProvider: its default outputs remain unchanged; assertions are hash-bound SYNTHETIC / TEST ONLY, never certification or promotion of real provider data. Extend existing bundle allowlist for these owners and the frozen financial contract; no dependency change.

Wire/state materialization uses existing BTL-CJSON-1/hash and exact Fraction/Decimal primitives. Profile pins canonical XAUUSD/USD, original synthetic feed/instrument identity, tick/price scale, contract/lot/money precision, NONE or fixed per-lot-side commission, NONE slippage and ZERO latency. Commands are strictly versioned, session/revision/idempotency bound. OPEN/CANCEL/CLOSE/ADVANCE/SEEK/END use one serialized controller path; before financial history, SEEK reconstructs the same bounded timeline; after financial history backward movement is refused and a separate child may fork only an explicit committed parent checkpoint. Parent evidence stays immutable. MethodPolicy is reused only as an injected frozen domain guard, with no Method/Session product/persistence integration.

FORK is a child-session command with command ID and expected initial revision zero, immutable parent Session/revision reference and durable retry/conflict handling; it changes no parent bytes. The existing `frontend/tests/repository.test.mjs` bundle boundary admits exactly the reviewed execution/reference/test files listed in the existing bundle config, with explicit negative cases for other backend, private/raw data, archives and production market artifacts. This is a bounded allowlist extension, not generic backend packaging or removal of bundle safety.

Pure execution receives only acknowledged revealed groups, clipped coverage/diagnostics and the pinned profile. It never holds provider/storage/index/sidecar handles or EOF. An untrusted group may commit a proven common outcome for identical executable quotes or no financial action; otherwise any potentially changing outcome fails closed as UNRESOLVED, with no speculative fill from that group. Market/pending/exits use observed transaction/liquidation sides and first observed gap price. Insufficient coverage/freshness or corrupt eligibility never gets candle fallback. Synthetic completeness/freshness assertions are fixture inputs, not market facts.

Durable boundary: existing PostgreSQL serializes each session with row locking and commits command dedup/result, append-only events, exact account/order state and controller checkpoint together. No process-memory fill is represented as durable. Bound state/orders, per-command event payload and fixture reconstruction; unsupported larger runs refuse rather than truncate. Production auth/API/user Session save/reopen/UI integration remains V21-2+ scope. An opt-in CLI runs authored fixtures through this same engine and durable adapter; it is an inspection surface, not another simulator.

Acceptance: materialize every frozen financial golden before engine code; actual Python pure/domain + real isolated PostgreSQL transaction/concurrency/restart/restore tests; existing tick/evidence/contract regression, independent Node vectors, full frontend regression/lint/build/release, repository/bundle validation and full diff/protected-byte review. No browser product route changes: record the limited unmounted-backend exemption, without claiming end-to-end V2.1 UI acceptance. Normal commit/push/remote equality/clean 0/0, then STOP before V21-2. Large Exness partial progress remains separate and cannot satisfy this checkpoint.

### V21-1 implementation and acceptance evidence

The authorized slice is implemented in the file boundary above. Existing canonical encoder, timeline, financial owner and all frozen 42.17/42.19 text remain unchanged. Golden JSON plus its independent exact-arithmetic validator were authored and passed before reducer implementation. The 24 scenarios cover both sides, all pending types, gap-through entry/SL/TP, same-event activation/exit, trusted and equivalent/changing untrusted ties, cancel serialization, partial/full exit with fixed commission, invalid lot/tick precision, no quote, unknown quality and half-even posting. Seven authored transaction expectations additionally cover stale/retry/conflict, crash-before/after commit, Protocol intervention and rewind/fork.

Full backend discovery: **212 methods PASS, zero skips**, against real isolated PostgreSQL 18.6 with existing Psycopg 3.3.6. The 22 new methods comprise two golden materialization checks, eleven domain/controller checks and nine real-database checks; each financial scenario runs through the actual durable adapter as well as the pure test seam. Real tests include twelve concurrent identical retries, workspace isolation, actual child-process death after all SQL but before COMMIT, actual death after COMMIT before response, original-receipt recovery, immutable-parent checkpoint fork, corrupt-record refusal, restricted-role writes and append-only/revision constraints. Native pg_dump/empty-target restore returns identical evidence and receipt. The test-only memory adapter makes no durability claim.

An initial full run found that the pre-existing identity redaction test requires a password field, absent from this isolated loopback QA DSN. Supplying a nonempty QA-only field resolved the configuration failure; the final entire run above passed without changing or weakening that test. The existing Starlette TestClient/httpx deprecation warning remains; dependency versions were not changed. A controller inspection-bound guard and repeated-group fence were completed and covered by the final run.

Actual opt-in CLI smoke: authored long 0.1 lot, contract size 100, Ask entry 101 → Bid exit 104, no commission; balance 10000 → **10030**, three committed events. After a controlled physical PostgreSQL fast shutdown/restart, inspection stdout remains byte-identical, SHA-256 `aa3181e4d1c6075524a0ceb5c2c4cb7c4ef947496a828b00f3c185831e86a2da`. Retrying the original ADVANCE returns the committed revision-2 receipt and leaves account/event bytes unchanged. This is exact synthetic simulation evidence, not broker liquidity or real-data precision acceptance.

Independent Node canonical vectors (six vectors across three runs), every registered frontend regression, lint, production build and local v1 release audit PASS. Existing bundle boundary is extended by an exact reviewed backend-file allowlist with negative raw/private/unreviewed cases; determinism, generation/freshness and repository authority validation are final documentation gates. All 15 interrupted 42.20 preservation worktree/blob hashes and seven original 42.18 hashes match the prior proof; both preservation refs and the separate drawing spike remain intact. Complete diff/protected-file review and normal main commit/push/actual remote equality with clean 0/0 finish closure; no self-referential commit hash is embedded here.

Limits: fixture admission is SYNTHETIC_CONTRACT_ONLY with at most 4096 events, 64 groups per acknowledgement, 1024 events per atomic group, 128 retained orders, 256 emitted events per command and 256 replay reconstruction steps; exceeding a bound refuses atomically rather than truncating financial truth. Exact profile arithmetic is bounded to prevent unbounded numeric inputs. Untrusted heterogeneous groups fail closed when an outcome might change; proven identical-quote/no-action common outcomes record chronology limits. Ambiguous coverage/freshness never becomes a fill through a candle assumption. No real provider, disk draft integration, ingestion/benchmark, margin/conversion/alternate cost model, public auth/API composition, product Session save/reopen, chart/Analysis cutover or full browser journey is accepted. Browser verification is exempt only for this unmounted backend/CLI slice with unchanged product routes; later integration retains real-browser gates. Operational status remains solely in 04_CURRENT_PHASE; V21-2 was not started. Historical 700k and later private ingestion progress remain partial, never a successful full benchmark.

### V21-2 authorized Method/Session integration scope

The human now authorizes the existing V21-2 through V21-6 Functional Alpha journey. V21-2 first connects immutable Methods, inherited Sessions, exact planning/checklist, explicit server-persisted review/confirmation and local save/reopen to the V21-1 engine. New `backend/execution/research.py`, `research_fixture.py` and `local_api.py` are application/controller/loopback transport adapters, never an alternative reducer. Migration 006 adds bounded, hash-checked immutable Method/Session metadata and review rows alongside existing tick tables; Session metadata + engine seed commit in one transaction. Existing nonexecuting intake, cloud identity/workspace, legacy v1 and preserved drafts remain untouched. No arbitrary state import or raw provider data.

An opt-in lazy `frontend/src/tickAlpha/` entry under `?tick-alpha=local` reuses the existing modal/focus primitives and prototype workflow concepts, but no prototype synthetic lifecycle/PnL. Default v1/prototype/viewer routes remain available. Durable state lives in existing PostgreSQL; reload reads that same state, never a second localStorage financial account. The browser receives only explicit user context, engine state/events and bounded already-revealed quotes. The fixed authored fixture is labelled SYNTHETIC / TEST ONLY; its profile and period are explicit, immutable Session inputs. Warmup reveals an initial prefix before orders, not future execution. Execution and risk arithmetic stay server-side.

Local API binds loopback with no trusted forwarded headers, validates peer/Host/Origin/custom request header, bounds streamed request size/concurrency and returns safe no-store errors. Only exact allowed local frontend origins receive CORS; this is local operator access, not public authentication/tenant deployment. OPEN is reachable only by confirming a persisted immutable review at its expected Session revision; stale/corrupt/older records fail closed and originals remain preserved. Material Method changes require a new Method. Session creation inherits type, profile/feed/version and original balance; reopening never resets it. Protocol checklist/risk/RR/quantity and manual-intervention guards remain enforced by the same domain. V21-3 later owns chart/replay/drawing integration, V21-4 the financial views, V21-5 scoped presentation and V21-6 final real-browser acceptance. Each retains its own tests, diff/context and normal Git gates; no automatic V2.2.

### V21-2 implementation and acceptance evidence

The authorized local adapter is implemented: immutable hash-checked Methods, inherited/pinned Sessions, atomic metadata plus engine seed, server-sized Protocol review, explicit reviewed-command confirmation and durable reopen. The fixed authored fixture contains 2048 exact Bid/Ask observations with 15-second spacing; 121 initially revealed observations provide warmup. It is SYNTHETIC / TEST ONLY, not historical January 2020 market data. The existing SyntheticTickProvider and TickTimeline still validate ingress and revealed evidence. A private immutable 64-event page cache returns fresh decoded objects; it does not relax canonical/timeline validation or expose provider metadata.

Transport is opt-in loopback only, with exact Host/Origin/custom-header checks, no public identity composition, 32 KiB JSON bodies, a five-second body deadline, two admitted workers, zero waiting heavy requests and explicit overload refusal. Catalogue bounds are 128 Methods and 128 Sessions; reviews are limited to 256 per Session. Inspection exposes the last 256 committed events, explicit window start and one already-revealed quote, never controller checkpoints, schedules or EOF. Financial values remain exact strings. Create retries keep their original ID; changed payloads conflict rather than replacing saved evidence.

Full backend discovery: **221 methods PASS, zero skips**, with actual isolated PostgreSQL. Nine new methods cover immutable fixture pages, hostile transport/body/overload boundaries, atomic creation failure, immutable inheritance/idempotent creation, Protocol ON/OFF and sizing bypass, concurrent duplicate confirmation, stale review, actual fill/reload and preserved corrupt/unsupported records. Eight concurrent confirmations return one durable order and identical receipt; a patched timeline resume proves confirmation does not replay ticks, and pre/post controller checkpoints match. Non-replay order commands now keep the checkpoint unchanged, avoiding the observed row-lock timeouts without changing financial/replay semantics. Initial response-schema and Decimal-wire retry errors were corrected and verified by the final entire run.

Actual browser: created Free Style and Protocol Methods/Sessions; cancel/Escape before confirmation produced no order; confirmation created one pending order. Protocol ON blocked NOT_ASSESSED, then PASS produced server-derived quantity/target. Reload and local-service restart preserved balance, revision and the pending order. The final service with admission/deadline checks reopened the same state. Alpha and default-v1 consoles were clean; the default chart/toolbar/replay/terminal still loaded. Full registered frontend regression, independent Node canonical vectors, lint, production build and local v1 distribution/release audit PASS. Bundle freshness, repository/determinism checks and normal Git equality/clean 0/0 close this checkpoint.

All 15 preserved 42.20 raw files/Git blobs and seven original 42.18 fingerprints/ref identities match. No preserved runtime, canonical encoder, timeline, financial contract, dependency, market dataset or default v1 financial system changed. Local application/API/UI adapters are added to the existing exact bundle allowlist. Planning drafts are ephemeral; confirmed reviews/orders and Method/Session state are durable. Chart/replay and financial-view integration are subsequent checkpoints, not accepted by this result. Historical 700k progress and the entire Exness benchmark remain incomplete. V2.2/public/cohort performance claims are not made.
### V21-3 authorized workspace integration scope

Following the validated V21-2 push, the existing journey authorizes workspace integration only. Reuse `frontend/src/components/CandleChart.jsx`, existing Lightweight Charts primitives/drawing persistence and production indicator registry. Add optional per-Session drawing namespace/storage and unavailable-volume flags with unchanged v1 defaults; no donor migration or replacement engine is selected. New alpha workspace/display adapters connect these existing owners to acknowledged tick state, timeframe and play/pause/step/seek/speed controls. Orders remain reviewed engine commands, never chart-derived settlement.

Controller-side only: add a bounded four-entry timeline/revealed-window cache for the immutable authored fixture. Cache identity binds workspace, Session and exact durable controller checkpoint; PostgreSQL CAS/dedup remains authoritative. Remove a consumed cache entry before mutation; failed commit never authorizes its speculative successor. Serialize cache reads/mutations, rebuild misses through existing TickTimeline.resume, retain at most 1024 already-revealed groups per entry, and never hand timeline/provider/checkpoint/EOF to the browser. Generic execution controllers retain their existing cold-validation default. Prove rollback, concurrent read/advance, cold reconstruction and future clipping rather than assuming cache correctness.

Derive at most 512 display candles using exact mid=(Bid+Ask)/2 and UTC epoch-aligned fixed-duration buckets, with no empty buckets, no forward-fill and no invented volume. A bounded revealed-window edge is explicitly partial; the current bucket is explicitly incomplete. This alpha exposes fixed-duration minute/hour/day intervals, not provider calendars or monthly/weekly assumptions. New coherent Session workspace projection uses one durable snapshot and only its revealed prefix; chart/indicator float conversion is presentation only. Financial rewind is refused under the frozen contract; separate new Session/fork is explicit, never hidden undo. Existing fixture/event/order/recovery bounds remain unchanged. Actual browser drawing create/move/edit/delete, indicator, timeframe, zoom/pan/resize and replay/no-look-ahead acceptance plus applicable full gates are required before this checkpoint closes.

### V21-3 implementation and acceptance evidence

The opt-in tick workspace now reuses existing Lightweight Charts, drawing primitives, Risk/Reward research measurements and the production indicator registry. Exact UTC mid-price candles are derived only from the durable revealed prefix; source volume is absent rather than substituted with tick counts. One coherent PostgreSQL snapshot binds state, quote, chart and committed event window. The four-entry immutable-fixture controller cache is keyed by exact durable checkpoint; actual rollback/concurrent-snapshot tests prove speculative future state cannot leak. Cache misses reconstruct through the original TickTimeline. No new settlement reducer, provider port, dataset, dependency or frozen-contract change.

Full backend discovery: **225 methods PASS, zero skips**, including four new workspace checks against real isolated PostgreSQL. Tests cover exact bucket boundaries, gaps, incomplete/partial windows, bounded 1024-group windows, cold reconstruction, rejected future/out-of-order data and unsupported calendar intervals, real rollback after speculative advance, concurrent old-snapshot reads, and actual fill matching revealed Ask. Final full frontend regression, lint, production build and local v1 release audit PASS. Repository/bundle generation, freshness, determinism and normal Git equality/clean 0/0 remain closure gates.

Actual browser QA exercised Trend/Horizontal/Vertical/Rectangle/Fibonacci/Arrow/Text/Measure creation, Trend move/endpoint resize, lock/hide/show/undo/redo, Long/Short research measurement creation/deletion, saved drawing reload and Session isolation, indicator add/edit/hide/show/remove, 1m/5m changes, zoom/pan/resize without serialized TIME+PRICE drift, tick step/speed/play/pause and pre-financial seek. Cursor changed from 00:30 to 00:34 on sixteen ticks, progressed during play, then explicit seek to 00:20 returned 21 revealed minute bars. Pause can finish one already-admitted acknowledgement; it schedules no further command. The seek control reads its actual native input at activation, avoiding stale edited dates. Services stopped across a session interruption; restarting the same PostgreSQL cluster recovered the durable Session and saved drawings. Console checks remain clear; the default v1 smoke remains separate and unchanged.

Limits: authored synthetic fixture only, at most 512 display bars/1024 revealed groups/four private cache entries; fixed 1m–D intervals only; sixteen concurrent displayed indicators. Indicator configurations are currently workspace-memory preferences, while drawings persist per Session independently of timeframe. Risk/Reward objects are research estimates, not orders/account evidence. Financial rewind remains refused, with another Session explicitly required; no browser fork claim. Source-volume, historical precision, large-data performance/SLO and the incomplete private benchmark are not accepted. The 15 preserved 42.20 blobs and seven original 42.18 fingerprints remain unchanged. Financial positions/history/Analysis and consolidated UX remain subsequent authorized checkpoints.

### V21-4 authorized trading and Analysis integration scope

The existing journey grant authorizes only the ROADMAP trading/Analysis checkpoint here. Add read-only `execution.analysis` over the single committed engine event chain, with exact cash reconciliation and basic completed-position metrics under the existing research contract. Use bounded 256-event database pages and a 4096-event projection budget; above that budget explicitly return unavailable, never a partial successful result. Retain at most 128 order summaries, 256 displayed cash postings and 512 fill annotations. Generic execution, canonical ticks/timeline and frozen contracts stay unchanged.

A coherent workspace snapshot binds chart, positions, closed trades, event-derived Analysis and dataset/engine/Method/profile/event-head provenance. Indicative liquidation-side marks use only the latest revealed Bid/Ask; they never post cash or enter completed-position denominators. Completed net sums actual committed cash postings, including entry commission and all partial exits, rather than rounding allocated partial nets a second time. Ratios remain exact numerator/denominator values; UI-only formatting is labelled. Cash drawdown follows committed cash event order; the bounded displayed path is not its calculation source. Unresolved positions remain separate and excluded.

Reuse official chart marker/price-line APIs for committed fill IDs and pending/active levels. Research drawings omit illustrative account/P&L labels in this alpha, without altering default v1 labels. Terminal manual/partial close and pending cancellation require explicit confirmation, frozen policy, expected revision and stable command identity on retry; closure still waits for a subsequent eligible tick. No amendment/alternate settlement or OHLC fallback. Existing reviewed schemas do not explicitly pin R0; R remains null under the frozen research rule, with missing-R exclusions and insufficient Monte Carlo sample disclosed. MAE/MFE, advanced research, alternate fees/margin/liquidity and broker precision are not accepted by this basic Analysis checkpoint. Require focused financial projection tests, actual DB/page/recovery evidence, applicable full gates and a real browser lifecycle before closure.

### V21-4 implementation and acceptance evidence

The read-only projection reconciles the complete accepted bounded committed event chain, account postings and order states within the same repeatable-read chart/quote snapshot. Six focused tests PASS: all 24 frozen financial scenarios, exact ratios/streaks/breakeven, corrupt/missing/future evidence refusal, budget refusal before event allocation, Short Ask marking, actual PostgreSQL partial/full close and cold recovery, and reconstruction beyond the latest 256-event display window. Completed net includes all position cash postings without double rounding partial allocations. Frozen engine, canonical ticks and controller contracts remain unchanged.

Actual browser proof on the authored fixture: pending Long market intent filled at Ask 2006.05; its Bid mark was -1 without a cash posting. Cancelling a partial-close dialog preserved the order; confirmed 0.04 partial close waited for a tick, then left 0.06 lots and -0.6 cash change. A subsequent full-close request waited for another tick and produced one completed position, three fill events, final exit Bid 2005.85, net -1.8, balance 9998.2 and 30-second duration. Positions/history/Analysis agree: one loss, expectancy -1.80, cash drawdown 1.8. Reload preserved revision/account; rewind was refused without mutation. A Protocol pending cancellation left balance 10000 without a fill. Official chart markers retained actual fill prices across 1m/5m; the candle mid never became an execution price.

Frontend full registered regression, lint, production build, local distribution audit and independent Node vectors PASS. A transient dev hot-reload hook warning occurred when changing the existing effect dependency list; a full reload preserved the Session and generated no new warning. Full backend discovery: **231 methods PASS, zero skips** with actual PostgreSQL (1044.815 seconds), including native crash/concurrency/restore and all prior gates. Repository/bundle generation/freshness/determinism and 15 preserved 42.20 / seven original 42.18 fingerprints PASS; complete diff review and normal push/equality/clean 0/0 are final closure gates. The separate drafts and incomplete historical benchmark are not integrated. Consolidated UX and final journey acceptance remain the next already-authorized checkpoints, not evidence supplied by this trading checkpoint.

### V21-5 authorized UX consolidation scope

From the separately pushed/equal clean V21-4 checkpoint, reuse the existing popup focus and panel-resize owners for the local tick alpha. Preserve the neutral light research surfaces/dark chart and all default v1 behavior. Address observed stale status in creation dialogs, loading being described as unavailable before connection completes, keyboard return focus after asynchronous review, replay continuing behind indicator tools, and access to long terminal evidence on narrow screens. Consolidate navigation, bounded resizable/collapsible terminal and clear action/refusal guidance without adding a second account, storage authority or execution path. No engine/backend/frozen contract/dependency/data change. Require real keyboard/modal/viewport/new-user checks plus the existing full gates; operational authorization remains only in 04_CURRENT_PHASE.

### V21-5 implementation and acceptance evidence

Reused existing popup focus and panel resize; explicit opener references preserve focus after asynchronous review, while omitted props retain default v1 behavior. Terminal six-dot pointer resize and keyboard arrows/Home/Enter/restore work, with independent scrollable account/table/Analysis/evidence content. Empty states explain the required tick. Status is cleared before opening creation/action dialogs, connection loading is explicit, obsolete StrictMode bootstrap stops before another workspace read, and Retry reopens the selected saved Session. Refusal guidance preserves the original code. Opening indicator/drawing tools pauses future replay scheduling without inventing cancellation of an admitted acknowledgement.

Actual responsive QA uses the real alpha in a disposable same-origin iframe at 375/780/1280-pixel viewports (browser override did not apply consistently to existing tabs). Each actual innerWidth matches its viewport and document scrollWidth, without global horizontal overflow; table/tool tabs scroll locally. Eight saved drawing objects remain byte-identical through resize. Narrow QA found inherited default-v1 CSS hiding Indicators; a tick-alpha-scoped override now keeps it reachable. Popup Tab wraps, Escape/Cancel returns to Create Method/Create Session/Indicators, asynchronous review cancellation returns to Review order, replay pauses behind indicators, and six-dot drag changes terminal 350 to 409 pixels. Console is clear in the fresh QA tab; default v1 account/chart remain separate. This is targeted usability validation, not a full accessibility certification.

Full backend 231 methods PASS with actual PostgreSQL/zero skips (591.859 seconds); full frontend registered regression, lint, final CSS rebuild/distribution audit, independent Node vectors and preserved draft fingerprints PASS. Repository/bundle freshness and normal checkpoint push/equality/clean 0/0 remain final gates. Backend/execution/frozen contracts/dependencies/data are unchanged. Final new-user lifecycle/release acceptance belongs to V21-6, not this UX checkpoint.

### V21-6 authorized final Functional Alpha acceptance scope

The existing journey grant authorizes final acceptance only after the separate V21-5 Git closure. Use the current production build on the isolated loopback QA origin and the actual persisted local service. Walk a new user through Method → Session → chart/drawing/indicator/replay → reviewed order → tick-driven protective exit → positions/history/Analysis → reload. Add focused real PostgreSQL reviewed Long SL and Protocol Short TP tests, including checklist refusal, duplicate confirmation, shared timeframe-independent Analysis and cold recovery. Retain all mandated full regression/lint/build/release/bundle/preservation/diff/Git gates. Update existing release/context owners; do not create another roadmap, merge preserved drafts, resume Exness benchmarking or begin V2.2. Completion remains contingent on actual acceptance and Git equality/clean 0/0.

### V21-6 Functional Alpha acceptance and release evidence

From clean/equal d1bc8332bcc4d34aa4002fa6295c8061a529c88d, final acceptance uses the production build on isolated loopback port 5196 and the persisted service on 5188. A new real-browser Method/Session journey adds SMA and a saved TIME+PRICE trend, changes 1m/5m without geometry drift, steps sixteen ticks and seeks before financial activity. Reviewed Free Style Long LIMIT entry Ask 2006 exits at Bid 2005 on SL: one completed loss, net -100, balance 9900, two fills and 270-second duration. History/Analysis/account agree. Restarting the verified QA API process and reloading retains exact event head c9559b42bb871d3384474bf8ef73761dd31e4ab0cfbc95dbbc0c9c641d396e0f, account and drawing bytes. Indicator settings intentionally remain memory preferences.

Production browser Protocol ON rejects an unassessed checklist without changing revision/balance. PASS yields server-derived two lots, entry 2005.9, SL 2006.4 and TP 2004.9; confirmation alone does not fill. Revealed ticks enter Short at Bid 2005.9 and exit at Ask 2004.9 on TP, with manual/partial close disabled: one completed win, net 200, balance 10200 and 330-second duration. Analysis excludes the earlier cancelled intent and agrees with history. Fresh production console has no warnings/errors. Prior V21-3 drawing/indicator/replay and V21-5 actual responsive/keyboard checks remain applicable; default v1 retains its separate modelled account and historical workspace.

Two added real PostgreSQL acceptance methods independently verify both protective journeys, checklist refusal, duplicate-confirmation idempotency, timeframe-independent financial projection and cold reconstruction. Full backend discovery: **233 methods PASS, zero skips**, 694.184 seconds, including all financial goldens and real database crash/concurrency/native restore gates. Full registered frontend regression, lint, production build and distribution audit PASS; independent Node vectors and preserved draft fingerprints PASS. Final repository/bundle freshness/determinism, complete diff review and normal Git checkpoint/equality/clean 0/0 are mandatory closure gates.

Release label is **V2.1 Functional Alpha**: one tick authority, coherent small-fixture browser workflow and durable local single-user research. Run instructions and honest user limits are in the existing root README; authoritative commands stay in AI_CONTEXT/07_TEST_COMMANDS.md. This adds acceptance tests/docs only, with no runtime, frozen contract, dependency or market-data changes. V2.2 remains separately scoped and unauthorized. All historical large-data evidence, including 700k and later private partial progress, remains incomplete; neither protected draft is merged or modified. Existing roadmap Section V2.2 owns future precision/scale/licensing/reliability planning; no new roadmap or public release is created.
