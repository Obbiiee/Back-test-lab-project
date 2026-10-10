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

## 12. S-1 equal drawing comparison — 2026-10-10

This section extends the existing evidence owner; Sections 1–11 remain the historical STITCH-0 planning audit. The newer frozen [ledger](V2_ALPHA_FROZEN_EXECUTION_LEDGER.md) owns S-1…S-7 ordering; [DT-DRAW](V2_ALPHA_DECISION_REGISTER.md) and [selection rubric](V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md#7-stitch-selection-rubric) own choice. The old OpenAlgo-first ADR summary was normalized to the existing equal-comparison rule without changing that rule. Human chat explicitly authorized adopting `9fbf762` + `4e4dbef` and S-1…S-7, with a separate validated Git checkpoint per S phase and STOP before V2.2. Adopted starting baseline: `4e4dbef51814b5e1635ad4f903d49acbc71c63ff`, clean/equal 0/0 at reconciliation.

**Validated S-1 choice: KEEP.** The completion marker is conditional on the mandatory normal Git checkpoint/equality gate. Automatic approval review initially could not execute remote verification because its usage limit was reached. After its stated reset time passed, a new read-only request through the same review succeeded and actual GitHub main was still `4e4dbef`. No approval bypass occurred. S-2 advancement waits for the actual S-1 push/equality/clean 0/0 check.

### Exact candidates and scope

| Candidate | Inspected immutable revision / license | Inspected entry / production disposition |
|---|---|---|
| Current BTL | Starting baseline above; existing repository code with Lightweight Charts 5.2.1 (Apache-2.0) / existing notices | `frontend/src/drawings/useDrawingTools.js`, Manager/registry/primitives/history/persistence; retained |
| OpenAlgo Charts 2.6.0 | `marketcalls/openalgo-charts` at `8b4cffe41a8e8fda96c286d608625dac1ec36e53`; Apache-2.0; LICENSE SHA-256 `ede6b8620b0f3598fc4982a2f238a62c1cb9283cfbadf0b0efa9d13888b344cd` | `src/draw/index.ts`; external isolated clone + ignored generated bundle, no production import/package |
| OpenCharts 0.1.0 | `dylanpersonguy/OpenCharts` at `785d1f18cc1ca67b0246031b2b9a08cb5cb60264`; MIT, Copyright OpenCharts Contributors; LICENSE SHA-256 `c176d7d04a302024f7332a1e7c37606b09bf688bbae89683b20e0b6a16bb1a65` | `src/lib/chart-plugins/drawing-tools/manager.ts`; package declares LC ^4.2.0, isolated primitive nevertheless rendered on actual LC 5.2.1; no production import/package |

The test refuses changed pins or dirty source clones. Pin/source license links: [OpenAlgo](https://github.com/marketcalls/openalgo-charts/tree/8b4cffe41a8e8fda96c286d608625dac1ec36e53), [OpenCharts](https://github.com/dylanpersonguy/OpenCharts/tree/785d1f18cc1ca67b0246031b2b9a08cb5cb60264). License acceptability for this local evaluation is established; distribution would retain exact license/copyright/NOTICE and identify adapted files. No donor source is vendored or shipped here. No chart-engine replacement, dataset acquisition, dependency install or execution/financial change occurred. Candidate source inspection found no reason to grant drawing code financial/provider authority; no critical/high finding is asserted from a security scan that was not performed. Existing production dependency/release checks remain required.

### Common capability map and observed gates

| BTL minimum | OpenAlgo tool ID | OpenCharts native tool / discrepancy |
|---|---|---|
| Trend Line | `trend-line` | `trendline` |
| Horizontal Line | `horizontal-line` | `horizontal`; native schema retains price but drops anchor time |
| Vertical Line | `vertical-line` | `vertical` |
| Rectangle | `rectangle` | `rectangle` |
| Fibonacci Retracement | `fib-retracement` | `fibonacci` |
| Arrow | `arrow` | `arrow` |
| Text | `text` | `text`; default placement text must be mapped/edited |
| Measure | `measure` | `measure`; preview-only, excluded from stored DrawingType and onAdd |

`frontend/tests/stitch-drawing.test.mjs` executes all eight BTL lifecycle cases with immutable fractional TIME+PRICE anchors, irregular bar spacing, create/select/body drag, lock refusal/hide, delete/undo/redo, prefix/timeframe anchor stability, cold persistence and read-only future-schema byte preservation. Existing Phase 7 and Phase 9 vectors also passed in this run. Donor mode builds the actual pinned entries and executes OpenAlgo eight-model lifecycle + JSON round-trip, and OpenCharts native commitPlacement for every minimum. It asserts the latter produces exactly seven persisted objects and no horizontal anchor time: these are reproduced gaps, not silently repaired PASS results.

The new loopback-only comparison fixture (`frontend/tests/browser/stitch-drawing.html`, port 5204) uses the same 80 authored candles, with a five-minute gap, fractional drawing timestamps and the installed **LC 5.2.1** renderer. Browser observations:

- **BTL:** all eight render; all canonical records persist across Zoom, Pan, chart-height resize, timeframe projection and a 40-bar revealed prefix. Cold page reload + Load restored canonical records exactly. Native Trend Line creation, body drag, endpoint resize and locked drag refusal passed; hidden selection clears and Text edit passed. Existing production creation/interactions are retained, not replaced by this test-only placement helper.
- **OpenAlgo:** all eight render and can each be placed individually through actual pointer clicks. Native body drag, endpoint resize where applicable, delete and undo passed separately for Trend, Horizontal, Vertical, Rectangle, Fib, Arrow and Measure. Blank newly placed Text required the visible Edit Text action and targeting its label; then Text body drag/delete/undo passed as well. That first blank-label failure is not hidden or treated as a donor regression proof. Eight anchor/Text snapshots survived Zoom/Pan/resize/timeframe/replay-prefix and cold reload; lock/hide/Text update passed through donor APIs. `fromJSON` normalizes schema/key order; compare canonical anchors/Text rather than falsely requiring JSON property-order identity. Incoming model arrays must be cloned, and BTL metadata/options/storage/Text-edit ownership require an adapter. This is viable isolated rendering, not accepted production migration.
- **OpenCharts:** seven persisted types render on LC5; Measure appears as a transient overlay. Seven native snapshots survived the same transformations and cold reload. Native Measure never emitted onAdd, and Horizontal Line omitted time. Therefore the unmodified native schema fails two shared persistence/canonical gates. A bounded adapter would need retained BTL metadata/horizontal time, a stored Measure implementation, and BTL history/save ownership; none is silently claimed complete.

The first OpenAlgo irregular fixture pointer attempt exposed a missing host `dataLayer.length` and unsafe nonfinite index conversion. That fixture was corrected against the pinned host contract, then all eight pointer cases were rerun with empty error lists. Earlier failed attempts are not acceptance evidence. The regular original preparation fixture and its three untracked worktree files remain preserved. The donor evaluation does not certify HiDPI/mobile parity, large-history performance or a chart-engine cutover. These are not invented from the authored fixture.

No provider/storage/index/account handle is passed to drawing modules. Production drawing code continues receiving only BTL's revealed chart prefix; stored future planning anchors are drawings, not invented future market evidence. The fixture's authored source array is a test controller input, not a consumer API. Production causal/execution boundaries were not modified. Unknown/legacy user storage remains untouched because there is no production migration.

### Measured cost and deterministic choice

Measured with installed Rolldown, minified ESM, Node gzip; React external for the BTL hook entry. This compares drawing entries, not full application bundles or identical upstream app surfaces.

| Entry | Modules | Minified bytes | gzip bytes | Nonblank source lines in entry closure |
|---|---:|---:|---:|---:|
| BTL hook | 15 | 23,405 | 7,841 | 775 (811 across all retained drawing source) |
| OpenAlgo draw | 51 | 217,397 | 67,311 | 16,210 |
| OpenCharts manager | 8 | 35,442 | 10,279 | 2,134 |

Gross incremental gzip relative to retained entry: +59,470 OpenAlgo; +2,438 OpenCharts, before any production adapter; zero selected-path delta for KEEP. Measured candidate-specific fixture glue: OpenAlgo 15 nonblank lines / 4,180 bytes, OpenCharts 7 / 1,561 bytes, plus shared coordinate/buttons/report plumbing. Compact fixture formatting makes line count a poor complexity proxy; these are prototype numbers, **not** a production adapter estimate or a claim that 811 BTL lines can be deleted. KEEP adds zero production adapter LOC and retains 811 drawing lines. Neither upstream widget replaces BTL's storage/history/projection/causality boundary for free. Entry source LOC is explicitly not BTL-maintained adapter LOC. The first ranking component decides the winner, so later ranking components need no guessed production migration implementation. Both browser-served donor bundles were SHA-256 identical to the freshly pin-checked test builds.

One authored eight-case local observation (not a capacity/latency SLO): BTL lifecycle median 0.977 ms/max 5.028 ms; OpenAlgo lifecycle median 1.419 ms/max 7.768 ms. OpenCharts placement-only median 0.057 ms/max 1.508 ms is **not comparable** to those complete lifecycle timings and does not win on that number. Small sample, cold/warm process variability and 80-bar browser workload prevent historical/production-performance claims. The test records fresh observations in ignored `tests/artifacts/stitch-drawing-metrics.json`.

**Mechanically supported choice: KEEP current BTL.** BTL uses zero semantic production-module rewrites and zero new runtime dependencies. Any donor production path requires at least rewriting the `useDrawingTools.js` lifecycle/factory boundary to invoke a donor adapter rather than current Manager/creation/interactions; thus its first ranking component is at least one. Extra features cannot override that first component. OpenCharts additionally has reproduced native MUST failures until an unaccepted adapter repairs them. Even granting OpenAlgo's viable bounded adapter full parity, it cannot beat 0 at the first ranking component. No subjective feature-count preference or fourth library search changes this result. This retains the official OSS LC renderer/primitives foundation; it does not claim a donor UI has been adopted or the professional 25-tool catalog is complete.

Migration/rollback design: KEEP causes no storage migration and preserves current namespace/version and unknown bytes. Optional future donor adoption would retain the current implementation behind an explicit factory, map TIME+PRICE/options/text/metadata into a BTL-owned versioned snapshot, refuse unknown schemas without writing, and prove reverse round-trip/one-action history/causal prefix before cutover. No old runtime is deleted. Under the frozen ledger S-2 would be a separately recorded KEEP/N/A checkpoint **only after S-1 Git closure**, not an automatic declaration in this in-progress report.

### Validation / remaining closure

PASS: authored BTL vectors; donor-mode clean exact pins, size/source measurements and lifecycle/native-gap vectors; **all registered frontend regression tests** (including existing 88 legacy geometry tools, production drawing/history/persistence, seven indicator families, causal replay, trading, news, Method/Session and tick-alpha boundaries); lint; production build (120 modules); release distribution/licenses/QA-seed exclusions; repository single-authority checks; AI bundle generation/hash verification/safety (188 files); independent Node six golden vectors repeated three times; protected 42.20 15 raw/Git blobs and 42.18 seven raw fingerprints/unchanged branch refs; complete scope diff and whitespace review. Donor mode was rerun after measurement instrumentation was added. Browser checks above are separate actual observations, not inferred from unit tests. Default sandbox runs initially failed on OneDrive/root `realpath` EPERM and SSR `module is not defined`; the same unchanged tests passed through approved host filesystem access. No test/legacy/runtime weakening was used.

Backend full regression is exempt for this unmounted test/documentation-only change: no backend, runtime product import, financial/data/protocol contract or dependency is changed; prior V21-6 results are historical, not rerun evidence. Normal commit/push and fresh local/origin/actual GitHub equality + clean 0/0 remain the final closure gate; do not announce completion or start S-2 before they pass. V2.2 remains outside the authorization.

## 13. S-2 conditional drawing migration — KEEP / N/A

S-1 closed at `b6fa6bf424d3a3b9a9ae5c69c9c885318215ed96`: normal push succeeded, local main = origin/main = actual GitHub main, working tree clean and ahead/behind 0/0. This is the verified S-2 starting baseline. The ledger explicitly makes migration conditional on a selected donor. DT-DRAW selected KEEP, so **migration is N/A**, not a missing implementation or an adopted donor claim.

DrawingManager, canonical v1 drawing storage, one-action bounded DrawingHistory, registry/creation/interaction/primitives and current chart hooks remain the sole production drawing owners. No second controller, adapter, storage namespace, schema conversion or feature deletion is introduced. Existing unknown/future/legacy namespace refusal and byte preservation remain unchanged. The S-1 old-vs-donor fixtures are retained as repeatable evidence; no source/dataset/protected draft is removed. Required rollback is current BTL itself, with no migration to undo.

Validation: S-1 actual browser and full regression evidence is retained, not falsely claimed as a fresh S-2 run. For this documentation-only conditional checkpoint, product browser/build/lint/full backend/frontend reruns are exempt; repository authority/bundle freshness/safety, protected fingerprints and complete documentation-only diff are required fresh. Normal commit/push/equality/clean 0/0 closes S-2 before the already-authorized S-3 comparison. Nothing here authorizes V2.2 or changes the professional 25-tool target into completed work.

## 14. S-3 calculator and host comparison — 2026-10-10

Starting baseline S-2 `f6e638dc221ebbfff93c85f041890d20609b9bc9`: freshly verified local/origin/actual GitHub equality, clean 0/0. Clean exact donor pins/licenses from Section 12 rechecked. `test:stitch-indicators` is isolated: default mode runs BTL goldens; optional `BTL_SPIKE_DONOR_ROOT` builds pinned source into ignored artifacts without downloads/installs. No donor source is redistributed, production dependency/runtime/contract is changed, or second authority is created.

### Calculator evidence

Seven hand-computed goldens cover SMA/EMA seed, population BB, Wilder RSI, SMA-seeded MACD/signal, first-bar ATR and Stochastic. Common inputs: empty/one/two bars, nonlinear five-bar vector, authored true ranges, flat zero-range prices, 60-bar nonlinear prices and decimated timeframe-shaped input. Every prefix is checked against clipped full output and a mutated unseen suffix; inputs remain immutable. Representation glue only maps settings/key names, null warmup to absent points and histogram colors. Donor numerics are never repaired. OpenAlgo descriptor EMA uses SMA seed; its separate first-value-seeded base kernel was not falsely substituted.

| Family | OpenAlgo descriptor | OpenCharts function |
|---|---|---|
| SMA, EMA, BB, MACD | common-vector numerical/warmup parity | common-vector numerical/warmup parity |
| RSI | flat = 100 versus BTL 50: FAIL | flat = 100 versus BTL 50: FAIL |
| ATR | first-bar range included: parity | first range skipped; `[3.5,4.25]` from time 220 versus BTL `[3,3,4]` from 160: FAIL |
| Stochastic | zero span yields absent K/D versus BTL 50: FAIL | parity including flat 50 |

Both donors pass supplied-prefix causality/input immutability. This does not certify unrestricted donor data orchestration. Inspected OpenCharts VWAP uses `volume || 1`; fabricated volume cannot enter the tick path. VWAP remains outside this seven-family evaluation and unadopted.

Installed Rolldown minified calculator entries: BTL 2,247 bytes / 922 gzip / 3 modules; OpenAlgo seven descriptors 50,427 / 15,930 / 22; OpenCharts calculator file 3,730 / 1,407 / 2. OpenAlgo includes descriptor/tail/timeframe metadata. These are scoped entries, not full-app, CPU capacity or large-history numerical acceptance.

### Host evidence and independent choice

Actual LC 5.2.1 browser fixture on loopback 5205 rendered seven BTL families plus independent RSI: six panes (price plus five oscillator instances), no engine errors. Hide/edit RSI, 35-bar truncation, decimated 5m-shaped projection, full-prefix restoration, height resize, removal/reindex and detach/attach passed. Removing one RSI reduced to five panes; clearing returned to one. The test TF projection is not production aggregation; production timeframe acceptance remains S-7. No provider/storage/account capability is passed.

The actual pinned OpenCharts React `useIndicators` hook mounted against the same LC5 chart reproducibly failed native `addLineSeries` (`i.addLineSeries is not a function`); an error boundary displayed refusal. This expected donor failure is recorded separately, not reported as a clean console. Source uses type-keyed instances and named price scales rather than independent LC5 panes; a host rewrite is required. Working LC5 is not downgraded.

OpenAlgo's own registry/context/tail chart host is source-inspected, not browser-certified here. It is not a drop-in LC5 IndicatorSeriesAdapter; an LC5 lifecycle/pane/plot adapter or unauthorized whole-engine replacement would be necessary. Calculator parity does not imply acceptance of its host.

**DT-IND: KEEP BTL calculators + KEEP BTL host, independently.** BTL passes current authored semantics with zero semantic production rewrites, added dependencies or new adapter LOC. Even parity donor functions require replacing a production registry binding/adapter (at least one semantic module); native gaps require more repair. Either donor host requires replacing the factory/adapter boundary (at least one), versus BTL zero. The first lexicographic cost selects KEEP; catalog size cannot override it. Gross calculator gzip delta +15,008 OpenAlgo / +485 OpenCharts before adapters; selected path zero. No production adapter LOC estimate or deletion count is invented. Existing configurations/persistence/rollback stay with BTL.

Validation PASS: fresh full registered frontend regression including Phase 10–13 panes/persistence/no-look-ahead, lint/build (120 modules), release distribution, repository/bundle (192 files) and protected-draft fingerprints. Browser observations above are actual interactions. Full backend exempt for unmounted tests/docs-only changes; no backend/financial/provider contract changed. Normal commit/push/actual equality/clean 0/0 is mandatory before conditional S-4 KEEP/N/A. No expanded catalog or V2.2 completion is claimed.

## 15. S-4 conditional indicator migration — KEEP / N/A

S-3 closed at `166571672733a79eb94c600f6d43d776ebd57366`: normal push, local/origin/actual GitHub equality, main clean 0/0. The frozen ledger allows migration only for accepted donor portions. DT-IND retained both calculators and host, so both migration branches are N/A. Numerical compatibility of a subset is not a donor-selection override.

Current productionRegistry, IndicatorEngine, IndicatorSeriesAdapter and versioned configuration persistence remain sole owners; no adapter, namespace/schema migration, dependency, chart-engine downgrade or old implementation deletion. Rollback is the unchanged retained path; unknown storage bytes remain preserved. S-3 pinned fixtures and measured gaps stay available. This conditional checkpoint adds documentation only: fresh repository/bundle/preservation/diff checks required, browser/lint/build/full frontend/backend exempt. S-3 runtime/browser passes are retained historical evidence, not new runs. Complete normal push/equality/clean 0/0 before already-authorized S-5; STOP remains before V2.2 after S-7.

## 16. S-5 trading presentation stitch — 2026-10-10

Verified starting S-4 `82ff59833367802aa8a6be243a64b860f1933902`, clean local/origin/actual equality 0/0. Inspected the same exact pinned OpenCharts OrderPanel/OrderConfirmDialog and OpenAlgo PositionMarker/order host. OpenCharts presentation is adapted narrowly into AlphaOrderPresentation: paired Buy/Ask and Sell/Bid draft buttons, selected state, exact reviewed rows and side-colored heading. Removed donor store/API, one-click submit, float quantity, projected margin/TP-PnL, and icon/UI dependencies. OpenAlgo marker imports its own LTP PnL/host; retained LC native actual-fill markers/brackets instead. Neither donor financial engine is adopted.

Exact upstream MIT license/copyright is preserved in public/licenses/opencharts-LICENSE.txt (Section 12 SHA), distribution NOTICE and root notices, with revision/modification header in the adapted component. Zero package/lock dependency changes. The two small presentation components consume only supplied quote/server-reviewed strings and callback intents. Existing UI event → BTL review → confirmation/hash → durable command → eligible Bid/Ask tick → canonical projection remains the sole transaction path.

Long/Short drawing Create order now copies geometry into Planned LIMIT draft. Real browser exposed the existing fourth width anchor; the bridge/test use the actual four-anchor controller and ignore width/geometry quantity/PnL. First raw fractional chart level was correctly refused by server PRICE_PRECISION. Final bridge explicitly rounds proposed intent to **Session-owned tickSize**, with exact integer arithmetic and collapse refusal; notice tells the user to review proposed values. Drawings/source quotes/fills remain unchanged. Protocol ignores drawing target/quantity/risk; server derives target and size from immutable Method. No automatic review, confirmation or fill on drawing selection.

Actual production-browser QA created a new Free Method/Long Session and separate existing Protocol-ON Method Session. Drawing-to-draft left revision 0/balance10000 unchanged; reviewed grid intent 2005.44/2004.38/2006.49 yielded server quantity0.94, then cancellation left no order. Authored Long LIMIT 2006/SL2005/TP2008 reviewed as 1 lot, confirmed PENDING, filled at2006 after tick advance, then SL2005/net−100/balance9900/duration270s; Analysis one loss/drawdown100. Protocol NOT_ASSESSED refused without revision change; PASS Short STOP2005.9/SL2006.4 reviewed server TP2004.9/2lots, confirmed pending, then Ask exit2004.9/net200/balance10200/duration330s. Completed rows remained identical at5m and cold reload. Another Protocol pending intent was cancelled via existing confirmation with no cash settlement. Modal focus trap/cancel and donor headings were observed; production console had no errors/warnings. This is synthetic quote simulation, not broker/historical acceptance.

Validation: all registered frontend regression, new intent/SSR exact-string/XSS vectors, lint, build122modules, distribution/license gate PASS. TickAlpha chunk grew from32.02KB/9.83gzip to34.47/10.73; CSS7.88/2.10 to8.92/2.31. Full backend discovery executed233/zero skips in703.904s:230 passed, three native restore gates failed because the supplied PG binary path did not exist. After reading actual running binary location, unchanged restore tests passed in separate1+2 test runs (7.257s/18.833s); no backend repair/weakening. A fresh correctly configured full run is reserved for S-7 final gate; the initially failed run is not relabelled all-PASS. Fresh repository/bundle/preservation/diff and normal Git checkpoint/equality/clean0/0 close S-5 before S-6. Backend/runtime contracts/providers/data/dependencies/protected drafts remain unchanged; no expanded catalog, public launch or V2.2 claim.

## 17. S-6 ResearchCalculator and QuantStats evaluation — 2026-10-10

Baseline: clean/equal S-5 `604bbb2f352a8e170ded1136ef2219fc8a404f21`. DT-ANALYTICS retains `execution.analysis.metrics`; grouping/provenance/Protocol, exact committed cash drawdown and orchestration remain BTL. Responsibility mapping belongs to the [existing metrics contract](V2_ALPHA_RESEARCH_METRICS_CONTRACT.md#s-6-researchcalculator-boundary--existing-runtime-mapping).

Official `ranaroussi/quantstats` pinned clean at `9ef4c6d0a4ffe7831f6ebba6a5824fd33a90c05a` / 0.0.86; Apache-2.0, Copyright 2019–2025 Ran Aroussi. LICENSE.txt SHA256 `3ddf9be5c28fe27dad143a5dc76eea25222ad1dd68934a047064e56ed2fa40c5`; stats.py SHA256 `2f7f7e936bb1daebe01b4f76419a82351dfcad5348bb05df85de73da56632d36`. External clone only, no donor source redistribution or production dependency. Optional oracle executes original selected function/class AST bodies and required pure helpers using existing NumPy 2.3.5/Pandas 3.0.1; no package initialization/feed/plots. This certifies scoped comparison, **not whole-package integration**. `prepare_returns=False` is the supplied public option, not patched arithmetic.

Completed-position net `[200,0,-100,0]` yields BTL 4 trades/1 win/1 loss/2 BE, win rate 1/4 and expectancy 25; native QuantStats win_rate 1/2 and avg_return 50 exclude zeros. Average win 200/loss -100 and PF 2 agree on this sample; empty mean NaN versus null, no-loss PF Infinity versus null, all-zero PF 0 versus null. Native BE-broken streaks match 2. Binary-float `[9007199254740993,-9007199254740992]` mean 0 differs from exact BTL 1/2. Positive cash equity `[100,110,105,120,90]` matches 25% drawdown and prefix equality; native detection treats sub-unit cash `[0.5,0.4]` as returns. This is a representation/semantic guard gap, not a proven future leak. Immutability and BTL decimal/empty/no-loss/missing-R goldens pass.

Decision: KEEP the existing small pure exact calculator. Matching means/streak primitives alone do not justify Pandas/NumPy and money conversion while required denominators/null/precision differ. No donor grouping/Passport, metric redefinition or advanced metrics implementation. QuantStats remains a future return-series research reference behind this boundary. Default `test:stitch-analytics` runs the BTL no-dependency oracle; optional donor mode is explicit/pinned and never auto-installs/fetches.

Validation: pinned comparison/default goldens PASS. Full frontend regression/lint/build/distribution, repository/bundle/determinism and preserved drafts are closure gates. Fresh correctly configured PostgreSQL backend discovery **233 PASS, zero skips, 701.669 seconds**, not relabelled S-5 configuration failures. No backend/runtime/financial contract/dependency/data change. Browser exemption applies to this unmounted test/documentation seam; actual integrated acceptance follows S-7. Full diff and normal Git/equality/clean0/0 precede S-7; no V2.2/full historical benchmark claim.

## 18. S-7 integrated consolidation and acceptance — 2026-10-10

Starting baseline clean/equal S-6 `1aa849081cb0579c3ca7360294f37eb3841867ab`. The [existing execution ledger classification](V2_ALPHA_FROZEN_EXECUTION_LEDGER.md#s-7-bounded-product-acceptance-classification) now explicitly covers all professional 25 drawing names, extra Arrow/Measure, baseline seven indicator families/Volume and all expanded 17; it owns the bounded status/deferral matrix with existing future owners. Deterministic repository tests derive catalogs from their specs and reject omissions/duplicates. This is not professional-complete or historical-precision acceptance.

### Accepted owners and small integration repair

LC5/CandleChart remains renderer; BTL DrawingManager owns the eight canonical primitives; existing ObjectController/RiskRewardController owns the distinct Long/Short research geometry. BTL IndicatorRegistry/Engine/SeriesAdapter remain calculators/rendering owner; `workspacePreferences` is the single local preference adapter for new tick-alpha per-Session indicator configuration, using existing `instanceConfig` validation. BTL review/command/controller/tick execution/PostgreSQL alone own financial state; canonical Analysis projection and exact `metrics` remain research authority. S-5 adapted OpenCharts presentation cannot calculate fills/PnL, and no competing donor store/engine was introduced. Default v1 is separately preserved legacy/modelled, not silently migrated.

Actual browser reproduced lost indicators after reload. Fixed only local research config persistence in existing preference owner: 16-instance/32KiB cap, version/workspace/known-field/config validation, unique bounded IDs, unknown/corrupt bytes read-only, changed-other-tab refusal, denied/quota status and memory-only fallback. Session-keyed workspace initialization restores config; timeframe changes reuse it. No financial schema/provider/wire contract change; v1 runtime-only configs remain unmigrated. Existing Phase16 tests add roundtrip/edit/hide/remove/isolation and malformed/future/foreign/quota vectors. No old production owner became superseded in KEEP/N/A S-2/S-4, so **no code/fixture/knowledge deletion** was justified; two reviewed compatibility exports and all rollback fixtures remain.

### Production browser evidence

Build served on isolated loopback5196 against accepted QA PostgreSQL/API5188; user5173 route untouched. Created all eight canonical drawing types through actual pointer/Text editor in Protocol Session. Horizontal lock/hide/show/history; delete/undo/redo and later undo restored the QA sample. TIME+PRICE bytes survived native wheel zoom, pan, 1m↔5m, Fit, cold reload and actual iframe resize375/780/1280. Comparison after deliberate delete/undo used the **new current drawing baseline**, not the earlier pre-delete snapshot. All three widths had client/body/scroll widths exactly375/780/1280 and identical drawing bytes. Six-dot drag changed terminal310→392px; Home collapsed24px and Enter/ArrowUp restored310px. Backend rewind refused `REFUSED_REWIND_REQUIRES_FORK` without financial change. Existing earlier S-1/S-3 lifecycle/handle/pane/numeric goldens remain applicable; this does not certify a new professional group/magnet/style catalog.

RSI period7 and hidden SMA20 survived timeframe/reload; switching to Long Session showed zero indicators and reopening Protocol restored both. Added the other five families, all seven restored; removed Stochastic/reload showed6 then re-added7. Actual pane rendering and controls remained usable; source volume stayed unavailable. In a fresh **QA STITCH S7 Free** Method / **QA STITCH S7 Journey** Session, added RSI/Long research drawing, reviewed Long LIMIT2006/SL2005/TP2008 at1lot/1% from balance10000. Confirmation produced PENDING/revision1 with cash unchanged; first16ticks yielded ACTIVE fill2006 and indicative−80, next16ticks closed SL2005/net−100/cash9900/duration270s/revision3. Closed rows and Analysis agreed:1loss,expectancy−100,drawdown100/1%, explicitly unavailable R/MAE/MFE/MC. Protocol S-5 Short history remained net200/balance10200/revision5 and identical at5m; NOT_ASSESSED refusal/locked exits/cancel evidence is in Section16, not falsely re-run here.

Stopped only verified QA PID9568 owning5188 with matching local_api command; restarted the same accepted QA database (newPID27116), no reset/migration. Cold reload retained new Long row byte-for-byte/event head `8bbccd104518b3ea435d301a178486ec132912d405cb75295173588a22a711eb`/9900/RSI. Reopening Protocol retained all drawing bytes/seven indicators/Short row/event head `0313112af10908e0f3558a8d4151f123bb21ad8dd3a9031c04e9913dc56e8d33`/10200. Production console warnings/errors were empty; expected OpenCharts LC4-host error belongs only to isolated S-3 fixture.

### Security, distribution, regression and limits

Registry audit found high GHSA-68fv-2mgg-jv7q in dev-transitive source-map-js1.2.1 (PostCSS/Vite). [Reviewed advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q) identifies patched1.2.2. Targeted update with install scripts disabled changed exactly one package/one lock entry1.2.1→1.2.2, no manifest/major/runtime dependency upgrade. Fresh full npm audit:0 advisories across171 dependencies. This scoped check and source heuristics are not public-SaaS security certification.

Fresh full registered frontend regression (including S-6, intent/grid, preferences and canonical goldens), lint, production build122modules and distribution/license checks PASS after patch. New catalog coverage test/repository/bundle determinism and independent Node6goldens×3/preserved42.20 15raw+Git and42.18 sevenraw gates PASS. Full backend unchanged: fresh correctly configured233PASS/zero skips/701.669s from Section17 remains applicable. Latest build TickAlpha34.74KB/10.80gzip; main336.56/105.94. No source map fix weakening/major upgrade, dataset/provider/financial runtime change, public deployment or full Exness benchmark. Final bundle regeneration/hash verification, complete diff, normal main commit/push/actual GitHub equality/clean0/0 close the authorized journey. STOP before V2.2; 700k/later private progress remains incomplete.

## 19. Supplemental Alpha drawing evaluation — 2026-10-10

Starting clean/equal baseline `3dee7f238e9a27b8038e9ae2829f3da43ad88810`. The CR-ALPHA-20261010 exception permits one additional donor. Inspected source `deepentropy/lightweight-charts-drawing`, exact Git `72290d3165682ec7bd28f96af7f9354184982dda`, package0.5.1, LC peer^5.0.0, MIT copyright2026deepentropy. License SHA256 `b1b58e33e717a3a4c20415ede120fab0e51ef552165b10b86affc0047dd0bd3b`. No donor install/postinstall or production dependency change. Existing Rolldown compiles51 modules into an ignored ESM fixture:210464minified/64270gzip bytes. This is the full exported entry, not a measured production tree-shaken budget.

Authored same irregular100/200/500-time vector projects150.25 correctly to20.05px but native inverse returns51; the existing continuous bridge round-trips150.25. With a chart global index offset the donor projects110.05 where actual-series interpolation remains20.05. Native parseDrawings accepts invalid time/Infinity/future-kind, backfills input style in place, and returns[] for the BTL versioned envelope. These are reproduced integration gaps, not production corruption: original storage was never handed to the donor. Host validation/cloning/history adapters are feasible; the donor explicitly leaves history/settings/editor/storage to its host, so their absence alone is not a failure.

Actual loopback5206 browser on LC5.2.1,80 authored bars including a gap: fractional canonical1700000735.25 native inverse1700000720, host inverse exact. After zoom/pan the same mismatch remains; at16-bar5m it returns1700000600 while host stays exact. Resize,zoom,pan,timeframe preserve native saved anchors and console/error list is empty. This checks coordinate integration, not the whole donor tool catalog, capacity or financial correctness. The first sandbox-bound server was unreachable; unchanged isolated server restarted outside that restriction, successful browser evidence above. Supplemental fixture does not change user5173 or accepted private datasets.

Selection under existing lexicographic correctness/change rubric: full native runtime fails the required fractional/irregular coordinate gate as supplied. Repair would need coordinate-runtime fork/injection plus strict schema translation/refusal, immutable ownership, host history and text integration. A core-only adapter can keep BTL coordinates/history/storage and sceneOf Ray; that bounded alternative was actually exercised. Importing the broad scene dispatcher alone still brings unrelated tools and a new style translation surface. Select KEEP existing eight drawing lifecycle owners and LC5 primitives, with ADAPT of only the donor's small Ray endpoint extension from sceneExtendedSegment in S-2 (MIT attribution/exact source pin required). That avoids semantic rewrites and new runtime dependencies while supplying the missing Ray. Its body hit/handles must cover the rendered extension, and all nine types must pass existing persistence/history/timeframe browser gates before acceptance. This is a selective open-source adaptation, not adoption of the entire donor engine, nor a claim that all native donor MUSTs pass. No old drawing system or raw JSON was deleted/migrated.

Validation: supplemental pinned compile/vectors PASS, retained authored lifecycle PASS; repository/bundle/goldens and complete diff/preserved draft gates precede normal commit/push/equality. Browser coordinate observations as above; backend/build exemption applies to this unmounted fixture-only checkpoint. S-2 runtime must run frontend regression/lint/build/distribution and actual chart browser lifecycle. Earlier700k/42.20 remains partial historical progress. External Alpha and complete product acceptance remain pending.

## 20. Alpha Ray integration — 2026-10-11

Starting clean/equal `1e9d590dcdce37e542aef128e0334e18de2cbec2`. Adopted only the selected small MIT Ray endpoint normalization; rayGeometry.js marks exact upstream pin/source and BTL offscreen correction. Existing manager, official LC5 primitive, canonical two-anchor model, strict version1 persistence and one-action history remain the same owners. Renderer extends a transient screen endpoint; hit-testing includes the extension while A/B handles retain actual anchors. Forward/reverse/vertical/degenerate/offscreen geometry and behind-origin misses are covered. Ray is in Alpha toolbar and retained legacy menu, with a distinct icon. Upstream license and modified-source notice ship in the production distribution and AI bundle. Zero new runtime dependencies; no parser import, chart replacement or storage migration.

Extended Phase9 tests exercise Ray create/cancel, malformed anchor refusal, handle/body edit, drag coalescing, cancellation, lock/hide/delete/undo/redo, mixed old/new JSON reload and finite canonical TIME+PRICE. The initial full regression failed only the historical Phase5 exact-eight catalog assertion; updated that explicit expected catalog to include the authorized Ray and re-ran the complete registered regression PASS. Original pinned eight-donor comparison explicitly retains its old eight samples; the supplemental tests are separate. Lint/production build/distribution PASS; final124-module build ships the license and retains TradingView attribution. Backend is unchanged, so previous final292zero-skip/actual-PG evidence remains applicable, not falsely re-run.

Actual production dev5173: created a separate Alpha drawing verification Method / Alpha drawing journey December2015 Session. Ray placed through toolbar, extension selected, lock/unlock controls worked,5m/Fit and cold reload retained the ray. Account remains10000/revision0, no financial command/trust promotion. An immediate first pair of clicks during React tool activation only started the draft; the next click completed it. No bogus success attributed to that initial draft. Cold startup loading completed normally; final chart showed the restored Ray and console warnings/errors were empty.

Actual authored LC5.2.1 fixture5204: all nine registered types seeded; canonical JSON unchanged through Zoom,Pan,Resize,Timeframe,Replay prefix and Load, with no errors. An isolated Ray created by two pointer clicks was dragged through the rendered extension; one Undo restored exact original JSON and Redo exact moved JSON. Locked drag left exact JSON unchanged; hide set visiblefalse; delete produced zero objects and Undo restored; Save/cold reload preserved exact drawing JSON. Console empty. Existing original eight interaction/Text/Long/Short separation tests remain applicable. This is the bounded nine-tool Alpha drawing slice, not full professional25 catalog, browser-capacity or external-product acceptance. Normal repository/bundle/goldens/protection/diff/push/equality gates precede the next authorized workspace UX checkpoint; no old source/draft/data deletion,700k/42.20 remains partial history.

Final repository gate initially refused the new donor LICENSE from the intentionally narrow bundle allowlist. Added only that exact required notice path, retaining asset/data exclusions; re-run repository/bundle determinism/hash verification PASS. Protected42.18 seven and42.20 fifteen fingerprints remain identical; independent Node6goldens x3 PASS. No unrelated fixture or source was admitted.
