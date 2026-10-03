# Phase 12 — Indicator Panes checkpoint

## Authorization and baseline

Human-authorized Phase 12 only: official multi-pane integration, RSI/MACD/ATR/Stochastic and minimal existing indicator controls. Local main and actual GitHub origin/main matched expected `90f36b236ff26782cc235c30188b0bc64c8cf11f` before source edits. No new dependency, chart, indicator engine, splitter, persistence, backend or later-phase implementation.

## Official API and ownership

Installed Lightweight Charts 5.2.1 APIs verified against local typings and [official pane documentation](https://tradingview.github.io/lightweight-charts/docs/panes). Existing IndicatorSeriesAdapter owns runtime instance → pane handle and instance → output-key series maps. Trusted specs declare placement price/pane, optional validated range/references and cross-parameter validation. Canonical config remains exactly id/type/parameters/visible; no pane index is serialized.

Each pane-type instance calls chart.addPane(true), then official chart.addSeries(definition, options, pane.paneIndex()) for all outputs. The preserved empty pane permits atomic partial-creation cleanup. Overlay definitions retain price placement and pane 0. Native Volume remains pane 0. Native layout.panes.enableResize is enabled; initial setStretchFactor(0.35) retains more space for price. Multiple panes share one chart/time scale. No user pane drag/merge/order persistence.

Indexes are read from the pane handle at use/removal, never permanently cached. Removal releases reference lines, all owned series, then the empty pane via removePane(current index); sibling series and price pane are not removed. Failed calculation or partial adapter creation/update clears all outputs/references/pane of that instance. Subsequent synchronization can recreate it. Hide/show retains the owned pane and series, changes series visibility and reference line visibility. Hidden panes remain blank by design, not orphaned. Attach/detach/chart replacement/StrictMode remount follow the same existing engine lifecycle.

RSI/Stochastic references use createPriceLine on their first output series, removePriceLine on cleanup, and lineVisible on hide/show. Thresholds are not fake instances. Fixed 0–100 autoscale providers are trusted adapter options derived from range specs; calculators do not call chart APIs.

## Formula, seed and warmup contracts

Index numbers below are zero-based; only timestamps of revealed input are emitted.

| Indicator | Contract | First valid index |
| --- | --- | --- |
| RSI | Period default14, integer2–1000. Seed gain/loss arithmetic means of the first N close changes (requires N+1 candles). Then Wilder average = (previous×(N−1)+current)/N. RSI = 100−100/(1+gain/loss). No losses with gain →100; no gains with loss →0; both zero →50. Range0–100, references70/30. | N; default14 |
| MACD | Fast12/slow26/signal9, integer1–1000, fast<slow. Fast/slow EMA use unchanged Phase11 first-N SMA seeds and alpha2/(N+1). MACD = fastEMA−slowEMA. Signal is the same SMA-seeded EMA over valid MACD values; histogram = MACD−signal. Valid MACD points can precede signal/histogram warmup; unavailable outputs are empty arrays, not NaN or future points. | MACD slow−1; signal/histogram slow+signal−2; defaults25/33 |
| ATR | Period14, integer1–1000. TR=max(high−low,abs(high−previousClose),abs(low−previousClose)); first bar TR=high−low because prior close is absent. Seed mean first N TRs, then Wilder smoothing. | N−1; default13 |
| Stochastic | %K period14/%D period3, integer1–1000. Raw %K=100×(close−rolling lowest low)/(rolling highest high−lowest low). Zero range →50. %D=SMA of last D valid %K values. Both bounded0–100; references80/20. No extra slow-%K smoothing. | K−1 and K+D−2; defaults13/15 |

Known vectors are independent arithmetic expectations. RSI closes[1,2,3,2,2,5], N2 →[100,50,50,650/7]. MACD closes[1,2,3,10,4], fast2/slow3/signal2 →MACD[.5,1.5,1/6], signal[1,4/9], histogram[.5,−5/18]. ATR TR[2,4,3,5], N2 →[3,3,4]. Stochastic known close/OHLC windows verify raw K and D separately; flat high=low yields finite50.

## Safety and automated validation

All four calculators receive the existing frozen revealed-input copies only. Deterministic repeated-prefix output, hidden future OHLC mutation invariance, N→N+1 causal prefix equality, revealed-only timestamps and finite/range values tested independently. Registry rejects invalid placement/range/reference/parameter combinations. Cross-field MACD validation runs before config mutation. Phase11 SMA/EMA/Bollinger calculator files and engine remain unchanged.

Passed full authoritative suite: Phase4,5,6,7,8,9,10,11,12; trading-separation; trading; drawings; market (all 3,486,461 M1 candles and eleven timeframes); repository; AI bundle. Production build and lint passed. Bundle generated and hash-verified after context/config changes. Repository graph:55 reachable production files plus two intentional compatibility exports.

Phase12 lifecycle tests cover multiple panes/output ownership, native-series types, price preservation, references/hide/update/remove, middle removal/reindex/re-add, append/rewind/prepend/timeframe, error cleanup/recovery, chart replacement, repeated detach/remount, type replacement and failed initial creation with no orphan pane/series. Phase10 only updates authorized product exclusions; Phase11 only updates the production registry integration name. Unrelated assertions and Phase4 source were not weakened.

## Actual browser evidence

Isolated origin port5189; test-only harness uses real CandleChart, useReplayMarket, productionRegistry and IndicatorControls under StrictMode. Instrumentation forwards the official third pane-index argument and reads real series/panes/reference APIs. No test hooks are imported by production main.

- Added all seven products. Price pane had candlestick/Volume plus five overlay series; dedicated panes had RSI1, MACD3 (line/line/histogram), ATR1, Stochastic2. References70/30 and80/20 were scoped to their correct panes.
- Native separator drag changed price height304.8→248 and RSI53.6→110.4. No custom splitter.
- Edited MACD6/13/4; fast=slow rejected and valid config retained. Edited RSI7, ATR7, Stochastic7/2. RSI hide/show hid/restored both references. Removed middle MACD pane; remaining ATR/Stochastic reindexed correctly and all five overlay outputs stayed pane0. Re-added MACD; added a second independent RSI pane, then removed it.
- Replay next1717416000→1717416900; all output endpoints followed revealed input. Existing rewind bucket semantics retained; second backward step returned every endpoint to1717416000, removing future points.
- 15m/1h switch and history prepend to1711933200 recomputed outputs. Unmount released all13 indicator series for eight instances; remount restored exactly13 across five dedicated panes. Native candle/Volume series are excluded from instrumentation's indicator count.
- Zoom/pan/viewport resize980×800 preserved chart/series rendering; viewport override reset. Native Volume remained on price pane. Explicit synthetic volume in fixture verified histogram/show/hide; production historical volume is not meaningful and was not fabricated.
- Click on indicator pane while Trend Line active created no drawing. All eight drawing types then created/serialized in the price pane: Trend Line, Horizontal/Vertical Lines, Rectangle, Fibonacci, Arrow, Text, Measure. Long and Short RiskReward objects rendered and selected in the price pane, clipped from indicator panes.
- Production workspace independently added all seven indicators. Simulator Buy opened a position; Next candle updated P&L to−$126.70; Close position removed it. Native trading marker/price line remained on price chart. No external or live-money trading.
- Final captured console warnings/errors:zero in fixture and production tabs. Ignored proof captures:frontend/tests/artifacts/phase12-final.png and phase12-ui.png.

## Protected-system and complete diff review

No edits to market loaders/replay semantics, simulator/useTrading, RiskReward controller/geometry/layer, native Volume setup/data path, native trading annotations, legacy storage adapter/schema, drawing model/manager/primitives/persistence/history, archives, datasets, backend, dependencies or lockfile. No unrelated UI redesign/refactor.

Four narrow protected integration edits were technically necessary for panes: drawing TIME+PRICE helper rejects non-price chart events; drawing hover skips indicator-pane bounds; CandleChart price picking/RiskReward placement rejects non-price panes/out-of-price bounds; existing RiskReward SVG is clipped to the current price pane and rejects out-of-price coordinates. These guards retain single-pane behavior, canonical geometry and separate ownership. Phase4–9/trading-separation regressions and actual browser drawing/RiskReward verification cover them.

Created (6):
- frontend/src/indicators/paneCalculations.js
- frontend/src/indicators/productionRegistry.js (one composed production catalog; overlayRegistry remains the unchanged Phase11 subset)
- frontend/tests/phase12.test.mjs
- frontend/tests/phase12-browser.jsx
- frontend/tests/phase12.html
- docs/PHASE12_INDICATOR_PANES.md (checkpoint evidence, not a new authority)

Modified (20):
- frontend/src/indicators/IndicatorRegistry.js
- frontend/src/indicators/IndicatorSeriesAdapter.js
- frontend/src/indicators/indicatorValidation.js
- frontend/src/components/IndicatorControls.jsx
- frontend/src/FigmaWorkspace.jsx
- frontend/src/components/CandleChart.jsx
- frontend/src/chart/ChartObjectOverlay.jsx
- frontend/src/drawings/timeCoordinates.js
- frontend/src/drawings/interaction/DrawingInteractionController.js
- frontend/tests/phase10.test.mjs
- frontend/tests/phase11.test.mjs
- frontend/package.json
- frontend/scripts/ai-bundle.config.json
- AI_CONTEXT/01_PROJECT_STATE.md
- AI_CONTEXT/02_ARCHITECTURE.md
- AI_CONTEXT/03_PHASE_HISTORY.md
- AI_CONTEXT/04_CURRENT_PHASE.md
- AI_CONTEXT/05_PROTECTED_SYSTEMS.md
- AI_CONTEXT/07_TEST_COMMANDS.md
- docs/ROADMAP.md

Deleted:none. Existing onboarding/workflow authorities remain unchanged; existing state/architecture/history/status/protection/tests/roadmap owners extended. Roadmap table's old Phase11 PLANNED label corrected to history reference alongside Phase12; historical reports/appendix preserved. Operational status centralized in04_CURRENT_PHASE:completed12, next13 awaiting scope/authorization, no active authorized implementation.

## Limits and checkpoint

Full recomputation/setData policy remains; no incremental optimization. RSI/ATR/EMA/MACD linear in loaded candles, raw Stochastic O(candles×K), existing Bollinger O(candles×period). No throughput/FPS guarantee or indicator parity claim against proprietary implementations. Loaded-prefix seed/history-prepend effects are deterministic and expected. Many panes in a fixed-height chart become compact; user can resize native separators, but no persistent heights/order/merge or unlimited-space layout engine. Hidden panes retain owned blank space. Reload discards runtime configs/layout. No additional indicators, VWAP, scripts, signals, alerts or Phase13 work.

Commit/normal push follow validated diff review. Actual final local/remote SHA equality and clean0/0 synchronization are reported after push in the final response; no self-referential commit SHA in this report. STOP after Phase12 checkpoint.
