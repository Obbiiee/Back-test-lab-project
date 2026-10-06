# STITCH-0 — OSS Replacement & Consolidation Audit

> **Status:** planning/audit only. This document does not authorize runtime replacement, dependency installation, deletion, migration, or phase advancement. Operational authority remains `AI_CONTEXT/04_CURRENT_PHASE.md`.
>
> **PLAN-FREEZE SUPERSESSION:** The donor facts/inventory in this audit remain useful historical evidence, but its proposed STITCH-1 selection sequence and subjective acceptance wording are superseded by `V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md`, `V2_ALPHA_DECISION_REGISTER.md`, and `V2_ALPHA_FROZEN_EXECUTION_LEDGER.md`. Current BTL, pinned OpenAlgo and pinned OpenCharts must all be evaluated under the common frozen rubric before selection. “OpenAlgo first, fallback if fail” is no longer the selection algorithm.
>
> **Audit baseline:** GitHub `main` reviewed 2026-10-06 after the Engineering Master Plan was linked from AI onboarding.

## 1. Objective

Backtest Lab has a working local v1 plus partially built v2/backend seams. Before extending commodity subsystems, v2 Alpha will use a **stitch-first** policy:

1. keep Backtest Lab-specific domain truth;
2. replace or retire bounded commodity implementations when mature OSS is demonstrably better;
3. isolate adopted OSS behind Backtest Lab adapters/contracts;
4. never replace a subsystem only because an upstream README lists more features;
5. migrate one subsystem at a time with parity/regression evidence and an explicit rollback path.

The desired outcome is not “maximum third-party code.” It is **minimum custom commodity maintenance while preserving deterministic Backtest Lab behavior and product IP**.

## 2. Decision vocabulary

- **KEEP** — current Backtest Lab ownership remains.
- **FULL-REPLACE CANDIDATE** — upstream may replace the bounded implementation if a spike proves compatibility.
- **PARTIAL-REPLACE** — upstream owns a primitive/calculator/presentation layer; Backtest Lab retains domain orchestration.
- **ADAPT** — reuse patterns/APIs or bounded source only after provenance/license review.
- **REFERENCE** — learn from upstream; no dependency/source import by default.
- **RETIRE** — old implementation may be deleted only after replacement acceptance.
- **DEFER** — not required for v2 Alpha.

No FULL-REPLACE decision is final until its migration spike passes the gates in this document.

## 3. Current Backtest Lab inventory relevant to stitching

### Chart
- React 19 + Vite 8.
- TradingView Lightweight Charts 5.2.1 is the active renderer.
- Existing attribution/license distribution is already handled.
- Current chart integration is coupled to replay, drawings, indicators, native Volume, annotations and terminal behavior.

### Drawings
Current canonical domain has exactly eight persisted drawing types:
- Trend Line
- Horizontal Line
- Vertical Line
- Rectangle
- Fibonacci Retracement
- Arrow
- Text
- Measure

The implementation already owns TIME+PRICE canonical geometry, DrawingManager/Registry, creation/interaction controllers, projection/hit-testing, selection, handles, drag, lock/hide, undo/redo, persistence and cross-timeframe projection. Missing advanced functionality includes magnet, richer properties/object tree, advanced tools and broader drawing catalog.

### Indicators
Current catalog has exactly seven families:
- SMA
- EMA
- Bollinger Bands
- RSI
- MACD
- ATR
- Stochastic

Indicator Engine consumes chart-visible candles only and owns validated immutable configs/output plus Lightweight Charts series/pane lifecycle. Native Volume is separate. Multiple runtime instances, edit/apply, hide and remove exist; persistence and a broad catalog do not.

### Trading visualization and execution
Current frontend has Long/Short Risk/Reward, market/limit/stop and pending simulation, entry/SL/TP, chart price lines/markers and paper account behavior. This remains candle/scalar-price MODELLED production behavior. The newer tick/provider/timeline path is isolated/unmounted and must not be conflated with current frontend settlement.

### Replay
Current frontend replay is candle/M1-chunk based and has commit-acknowledged playback, manual stepping and revealed-prefix safeguards. The target v2 execution authority is tick-native, deterministic and independent of presentation rate.

### Analytics/journal
Current Analysis is intentionally small and pure: completed positions, win/loss/break-even, realized P&L, win rate, average win/loss, expectancy, profit factor and realized balance/drawdown projection. Journal notes and raw/grouped CSV export exist. There is no broad research-calculator suite yet.

### Backend/product seams
Identity, PostgreSQL persistence, workspace ownership, contracts/intake, precision evidence and tick-provider/timeline foundations exist in bounded forms. Their existence is not proof of public deployment or frontend integration.

## 4. Donor audit

### 4.1 OpenAlgo Charts
Official upstream: https://github.com/marketcalls/openalgo-charts

Observed public project characteristics at audit:
- Apache-2.0;
- standalone from-scratch canvas financial chart engine, not a Lightweight Charts plugin;
- modular tiers for base chart, indicators, drawings, transforms, profile/order-flow, trade, WebGL, widget and workspace;
- current public README advertises 105 built-in indicators and 87 drawing tools;
- drawing tier includes a headless drawing controller;
- trade tier includes order/position/bracket tooling;
- base includes replay, feeds, bar cache, chart state and trading overlays;
- host supplies market data.

**Critical compatibility fact:** OpenAlgo's draw/indicator/trade tiers belong to the OpenAlgo chart ecosystem. They must not be assumed drop-in compatible with the current Lightweight Charts v5 workspace.

Decision:
- whole chart engine: **EVALUATE / not approved for replacement**;
- drawings: **FULL-REPLACE CANDIDATE**, gated by engine-coupling spike;
- indicators: **FULL/PARTIAL-REPLACE CANDIDATE**, gated by visible-prefix/no-look-ahead and pane lifecycle tests;
- trading visual overlays: **PARTIAL-REPLACE CANDIDATE**;
- replay presentation: **ADAPT/REFERENCE**;
- replay/execution authority: **DO NOT ADOPT**.

### 4.2 OpenCharts
Official upstream: https://github.com/dylanpersonguy/OpenCharts

Observed characteristics:
- MIT project code, with Apache-2.0 Lightweight Charts obligations for adapted/chart portions;
- built around Lightweight Charts v4.x, therefore architecturally closer to current Backtest Lab than OpenAlgo but not version-compatible by assumption;
- drawing engine, indicator layer, plugins, bid/ask lines, terminal/paper-trading UI and backend-agnostic patterns.

Decision:
- whole terminal: **REFERENCE, not wholesale replacement**;
- drawing/plugin implementation: **ADAPT CANDIDATE** if OpenAlgo engine coupling makes migration too expensive;
- trading-terminal UX: **REFERENCE/ADAPT**;
- execution truth/account authority: **KEEP Backtest Lab**.

### 4.3 QuantStats
Official upstream: https://github.com/ranaroussi/quantstats

Observed characteristics:
- Apache-2.0;
- Python/pandas/numpy portfolio analytics;
- mature statistics/reporting surface.

Decision:
- basic/reusable financial-statistics primitives: **PARTIAL-REPLACE CANDIDATE** behind a Backtest Lab research adapter;
- Experiment Passport, Method/Protocol semantics, trade grouping, canonical event identity and research orchestration: **KEEP Backtest Lab**;
- do not make interactive replay depend synchronously on a heavy analytics/reporting library.

### 4.4 NautilusTrader
Official upstream: https://github.com/nautechsystems/nautilus_trader

Decision remains **REFERENCE** for canonical events, provider adapters, data catalog, virtual clocks, deterministic processing and data/execution separation. Do not wholesale embed it into v2 Alpha without a new explicit architecture decision and license review.

### 4.5 QuantConnect LEAN
Official upstream: https://github.com/QuantConnect/Lean

Apache-2.0 upstream. Use as **REFERENCE/ADAPT selectively** for data-provider boundaries, independent backtest jobs, scheduling and resource isolation. Do not replace the manual interactive Backtest Lab product with LEAN.

### 4.6 hftbacktest
Official upstream: https://github.com/nkaz001/hftbacktest

Its tick-by-tick, latency, queue-position and L2/L3 simulation targets a deeper microstructure problem than v2 Alpha requires.

Decision: **REFERENCE/DEFER**. Use later to challenge execution semantics if/when provider evidence supports those fields. Do not import HFT complexity into the initial XAUUSD manual-replay alpha.

## 5. Replacement matrix

| Backtest Lab subsystem | Current maturity | Donor | STITCH-0 decision | Expected v2 Alpha action |
|---|---|---|---|---|
| Chart renderer | mature v1 | OpenAlgo / OpenCharts | KEEP pending comparative spike | retain Lightweight Charts initially |
| Drawing catalog/controller | good foundation, narrow catalog | OpenAlgo draw; OpenCharts fallback | FULL-REPLACE CANDIDATE | spike first |
| Indicator calculators/catalog | correct narrow catalog | OpenAlgo indicators | PARTIAL/FULL-REPLACE CANDIDATE | spike after drawing |
| Indicator host/pane lifecycle | integrated with LC v5 | OpenAlgo/OpenCharts | KEEP or ADAPT | preserve if donor coupling is high |
| Risk/Reward drawing UI | working custom | OpenAlgo trade | PARTIAL-REPLACE CANDIDATE | donor presentation, own domain |
| Order/position/bracket visuals | working but bounded | OpenAlgo trade / OpenCharts | PARTIAL-REPLACE CANDIDATE | donor visuals through adapter |
| Current candle replay controls | mature local v1 | OpenAlgo/OpenCharts | KEEP until tick cutover | UX ideas only |
| Tick replay authority | isolated foundation/incomplete v2 | Nautilus/hftbacktest patterns | KEEP | build Backtest Lab-specific |
| Execution authority | legacy modelled + future tick target | Nautilus/hftbacktest patterns | KEEP | build Backtest Lab-specific |
| Basic analytics calculators | small custom set | QuantStats | PARTIAL-REPLACE CANDIDATE | adapter/golden-test spike |
| Journal/trade evidence | useful domain behavior | none compelling | KEEP | evolve canonical log |
| Method/Session/Protocol | prototype/contracts | none | KEEP | build ourselves |
| Experiment Passport/lineage | contracts/planning | none | KEEP | build ourselves |
| Identity | bounded mature ecosystem integration | existing FastAPI ecosystem | KEEP | integrate, do not reinvent |
| PostgreSQL persistence | implemented bounded backend | PostgreSQL | KEEP | integrate |
| Market-data storage/index | 42.x interrupted v2 | Arrow/Parquet + own contracts | KEEP/ADAPT primitives | resume separately when authorized |
| Cache | not yet justified | mature cache ecosystem | DEFER | add only after benchmark |
| Job queue/workers | future need | mature OSS | ADOPT later | do not build queue primitive ourselves |
| Observability | future need | mature OSS | ADOPT later | standard telemetry, own domain metrics |

## 6. What v2 Alpha must still build itself

After successful stitching, the following remain Backtest Lab-owned because they define correctness, reproducibility or product differentiation:

1. **Market Evidence & Dataset Identity**
   - provider/instrument/dataset/version/hash;
   - rights/evidence metadata;
   - immutable publication semantics;
   - explicit unknown/ambiguous evidence.

2. **Provider normalization adapter**
   - initial alpha target can remain one provider + XAUUSD + bounded history;
   - never manufacture unavailable provider fields.

3. **Tick storage/index integration**
   - partition/manifest/index/sidecar publication contracts;
   - disk-bounded validation;
   - immutable time index;
   - bounded reads.

4. **Authoritative Tick Timeline & Virtual Clock**
   - deterministic ordering;
   - independent user cursors/clocks;
   - pause/resume/seek semantics without look-ahead.

5. **Tick Execution Engine V1**
   - market/limit/stop;
   - pending lifecycle;
   - long/short;
   - bid/ask correctness;
   - SL/TP;
   - spread;
   - versioned costs/slippage;
   - deterministic equal-time ordering;
   - canonical execution events.

6. **Tick-to-Candle aggregation**
   - derived presentation data;
   - execution truth must not silently fall back to candle ambiguity.

7. **Durable Session Engine**
   - dataset/version/cursor/clock/account/orders/positions/experiment identity;
   - CREATED/ACTIVE/PAUSED/SUSPENDED/RESTORED/COMPLETED lifecycle;
   - replaceable workers, durable session truth.

8. **Method / Protocol domain**
   - inclusion/exclusion;
   - risk and RR rules;
   - planned vs actual sample;
   - protocol enforcement and deviations.

9. **Experiment Passport**
   - dataset hash;
   - method/protocol hash;
   - engine/execution/calculator versions;
   - RNG seed where applicable;
   - lineage/result version.

10. **Research Orchestration**
    - canonical trade/equity input;
    - calculators behind adapters;
    - Monte Carlo/robustness/regime/OOS later in bounded jobs;
    - provenance for every serious result.

11. **Multi-user orchestration and resource policy**
    - bounded worker concurrency;
    - backpressure;
    - session checkpoint/recovery;
    - cache policy based on benchmark;
    - browser delivery budget.

12. **Backtest Lab UI/domain adapters**
    - isolate chart/drawing/indicator/trade donor APIs from Backtest Lab contracts;
    - donor replacement must not change execution outcomes.

## 7. Proposed stitching sequence

### STITCH-1 — Drawing compatibility spike
No big-bang migration. Create an isolated spike comparing:
A. OpenAlgo draw + required OpenAlgo base engine;
B. OpenCharts drawing/plugin approach against Lightweight Charts v5;
C. current Backtest Lab drawing engine.

Acceptance questions:
- Can TIME+PRICE canonical anchors round-trip without loss?
- Can replay/timeframe changes preserve drawings?
- Can persistence remain Backtest Lab-owned or version-migrated safely?
- Can selection/drag/hit-testing behave at least as well as current v1?
- What bundle/runtime cost is added?
- How many custom LOC can actually be retired?
- Are attribution/NOTICE obligations clear?
- Is rollback possible without touching trading/execution?

Outcome must be one of KEEP, ADAPT, PARTIAL-REPLACE or FULL-REPLACE. Do not migrate production during the spike.

### STITCH-2 — Drawing migration
Only if STITCH-1 proves net benefit. Introduce adapter, parity fixtures and migration/rollback. Retire old runtime only after browser/regression acceptance.

### STITCH-3 — Indicator spike/migration
Compare current seven calculators/host with donor calculators/catalog. Preserve:
- visible-prefix-only inputs;
- no look-ahead;
- deterministic outputs;
- pane lifecycle;
- replay speed independence.

A broad catalog is not sufficient evidence of correctness.

### STITCH-4 — Trading visualization
Evaluate donor order/position/bracket presentation. Backtest Lab execution remains authoritative. UI callbacks issue domain commands; donor state cannot settle fills or P&L.

### STITCH-5 — Analytics primitives
Define a language/process-neutral ResearchCalculator contract. Compare existing basic metrics with QuantStats using golden fixtures. Adopt only primitives with explicit semantics matching Backtest Lab. Keep grouping, canonical event log, Protocol, Passport and orchestration.

### STITCH-6 — Commodity infrastructure review
Before building queue/cache/telemetry primitives, choose mature components only when v2 Alpha load tests prove need. No Redis/Kubernetes/microservice escalation by default.

### STITCH-7 — Consolidation
- remove dead/duplicate implementations only after accepted replacements;
- update notices/provenance;
- freeze one owner per capability;
- run full regression/build/lint/browser tests;
- produce v2 Alpha architecture map;
- then return to Backtest Lab-specific build scope.

## 8. Migration gates for every replacement

A replacement is accepted only if all applicable gates pass:

1. **Capability parity:** every v2 Alpha MUST currently owned by the old subsystem is mapped.
2. **Correctness:** deterministic golden fixtures and domain invariants pass.
3. **No-look-ahead:** donor receives only data available at the current replay boundary.
4. **Domain isolation:** donor cannot become execution/account/research authority accidentally.
5. **Persistence:** existing user state has an explicit preserve/migrate/reject policy.
6. **Performance:** benchmark old vs candidate on representative history.
7. **Bundle/resource cost:** measured, not guessed.
8. **License/provenance:** exact repo/tag/commit/file/license/NOTICE recorded.
9. **Maintenance:** upstream activity/API stability assessed.
10. **Rollback:** old behavior can be restored during migration until acceptance.
11. **Regression:** trading, replay, market, drawings, indicators, journal, build and lint as applicable.
12. **Deletion proof:** old code is deleted only after import/reference/runtime checks prove it is unreachable.
13. **Git gate:** normal commit/push, actual remote equality, clean tree.
14. **Authority:** replacement completion updates factual architecture/history, but never auto-authorizes the next phase.

## 9. Quantitative planning estimate — not a completion claim

If the donor spikes succeed:
- chart/drawing/indicator/trading-presentation/basic-analytics commodity surface could be largely supplied by mature components;
- existing backend commodity foundations already cover additional plumbing;
- **roughly 70–80% of v2 Alpha capability may come from retained Backtest Lab code + mature OSS/standard infrastructure**;
- the remaining **roughly 20–30% is disproportionately difficult and valuable Backtest Lab-specific engineering**: evidence, tick truth, deterministic replay, execution, durable sessions, Protocol, Passport and research orchestration.

These are planning estimates, not LOC percentages, schedule promises or evidence that v2 Alpha is 70–80% complete today.

## 10. Explicit non-goals of stitching

STITCH does not authorize:
- automatic OpenAlgo chart-engine replacement;
- copying arbitrary upstream source;
- replacing tick/execution authority with a donor engine;
- deleting Lightweight Charts or existing v1 before parity;
- resuming preserved 42.18;
- ingesting/publishing private market data;
- public deployment;
- adding Redis/Kubernetes/Rust merely because donor projects use them;
- advancing roadmap phase numbers.

## 11. Next authorized decision required

STITCH-0 ends with this audit.

Recommended next human authorization:
**STITCH-1 DRAWING COMPATIBILITY SPIKE — isolated evaluation only, no production migration or deletion.**

In parallel, the interrupted 42.18 market-data work remains governed by frozen 42.17 + 42.19 and requires its own separate authorization. STITCH planning must not silently resume it.
