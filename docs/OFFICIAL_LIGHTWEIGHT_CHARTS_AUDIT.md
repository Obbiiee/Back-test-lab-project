# Official Lightweight Charts migration audit

> Historical Phase 1 snapshot; statements about missing panes/legacy indicators describe that checkpoint. Current source ownership and reference evaluation: [Phase 18.5 audit](PHASE18_5_ARCHITECTURE_REFERENCE_AUDIT.md).

Date: 2026-10-02 (Asia/Jakarta). Phase 1 only; no application code or dependencies changed by this audit.

## Baseline and protected components

- React 19.2.8 / Vite 8.3.0 manifests; installed Lightweight Charts 5.2.1.
- Latest official GitHub release checked: v5.2.1. No chart upgrade is necessary at this point.
- Entry: frontend/src/main.jsx -> FigmaWorkspace.jsx -> components/CandleChart.jsx.
- createChart creates one chart; CandlestickSeries, HistogramSeries and three LineSeries share its main pane. Lower indicator panes are not implemented.
- Native time/price scales, crosshair, markers, price lines and responsive ResizeObserver already work in CandleChart.jsx.
- Market: useGoldMarket loads HistData decade chunks progressively and polls sampled Gold API quotes separately. Archive contains 3,486,461 M1 candles across 120 months.
- Replay: useReplayMarket exposes only bars through the replay cursor and aggregates the selected timeframe. Do not replace this engine.
- Trading: useTrading and simulator.js manage paper positions/orders. Backend replay/trading code also exists but is not the active workspace data flow. Preserve both.
- Risk/Reward: long/short objects are rendered inside DrawingsLayer.jsx with positionStats, settings and Create order integration. Preserve these objects and their interaction behavior.
- TradingLevels.jsx supplies draggable order interaction labels. Native createPriceLine already supplies Entry/SL/TP lines. Preserve interaction controls while preventing duplicate line rendering during subsequent migration.
- Popup Order UI is independent of the chart drawing migration and must remain intact.

## Classification

| Category | Findings |
| --- | --- |
| AVAILABLE OFFICIAL | Native Candlestick/Bar/Line/Area/Histogram series, scales, crosshair, price lines, markers, panes, updates and resizing; official toolkit, catalog packages and primitive examples below. |
| ALREADY IMPLEMENTED | Candlesticks, volume histogram, scales, crosshair labels, trade markers, Entry/SL/TP price lines, responsive chart, progressive history and replay integration. |
| CAN REPLACE CUSTOM CODE | Non-position SVG drawing geometry with official primitives; movingAverage function with an official calculation adapter; price-level drawing with native createPriceLine; optional tooltip/annotations/session shading with official examples. |
| NEEDS CUSTOM IMPLEMENTATION | Host toolbar wiring, selection/drag/settings, undo/redo, JSON persistence, managers/registry, adapting examples to app state, advanced calculations without verified upstream equivalents. Official examples are foundations rather than a complete interactive drawing product. |
| NOT OPEN SOURCE / DO NOT COPY | TradingView Advanced Charts/Charting Library proprietary source and its drawing engine. Do not claim community packages are TradingView official packages. |

## Published official plugin catalog

Source: https://tradingview.github.io/lightweight-charts/plugins

All 10 current catalog entries:

1. Accessibility — @tradingview/lwc-plugin-accessibility.
2. Brushable Area Series — @tradingview/lwc-plugin-brushable-area-series.
3. Dual Range Histogram Series — @tradingview/lwc-plugin-dual-range-histogram-series.
4. HLC Area Series — @tradingview/lwc-plugin-hlc-area-series.
5. Image Watermark — @tradingview/lwc-plugin-image-watermark.
6. Pretty Histogram Series — @tradingview/lwc-plugin-pretty-histogram-series.
7. Rounded Candles Series — @tradingview/lwc-plugin-rounded-candles-series.
8. Stacked Area Series — @tradingview/lwc-plugin-stacked-area-series.
9. Stacked Bars Series — @tradingview/lwc-plugin-stacked-bars-series.
10. Vertical Line — @tradingview/lwc-plugin-vertical-line.

Toolkit: @tradingview/lwc-toolkit, upstream manifest 1.0.0, Apache-2.0, peer Lightweight Charts ^5.0.0. Provides primitive base classes, dimensions and time helpers; not a drawing/indicator manager. Exact npm versions and their peer dependencies must be checked before installation.

Practical first candidates: toolkit + Vertical Line; text watermark can use the native text-watermark API before considering image watermark. Accessibility follows after the chart migration stabilizes. Alternate series types are catalogued, not installed solely to increase package count.

## Official examples available for adaptation

Source: https://tradingview.github.io/lightweight-charts/plugin-examples/

- Drawings: Trend Line, Vertical Line, Rectangle Drawing Tool, Anchored Text, User Defined Price Lines, Partial Price Line.
- Analysis/UX: Bands Indicator, Volume Profile, Expiring Price Alerts, User Price Alerts, Tooltip, Delta Tooltip, Session Highlighting, Highlight Bar Crosshair, Overlay Price Scale.
- Custom series examples beyond published packages: GroupedBars, Heatmap, Lollipop, Shaded Background, Whisker Box.
- These are source examples. Do not assume every example has an npm package, production-ready editing, serialization or history support.
- The requested analysis-indicator source folder could not be retrieved during this audit. SMA/Average/Median/Weighted Close/Momentum/Percent Change/Correlation/Ratio/Spread/Sum/Product source and license must be individually verified before claiming they are reused. EMA/RSI/MACD/ATR and other advanced calculations are not assumed to be turnkey native indicators.

## Existing custom code and migration hazards

- DrawingsLayer.jsx + DrawingGeometry.jsx + drawings/tools.js implement active SVG drawing placement, projection and interaction.
- NativeDrawings.jsx + drawings/native.js exist but are not mounted by CandleChart. They wrap lightweight-charts-drawing 0.2.5, a community MIT package, not TradingView official source.
- CandleChart contains active custom SMA/EMA calculation. indicators/calculations.js contains EMA/RSI/MACD additions that are not wired into the active chart.
- Risk/Reward shares DrawingsLayer with the other drawing types; deleting this file wholesale would remove a protected feature.
- Legacy source snapshots must remain archives. Saved user drawing JSON must be preserved before removing tool types or changing the schema.
- Persistence currently keys drawings by mode and timeframe, so cross-timeframe persistence requires an explicit migration policy.
- Candle and volume setData run on every candle-array change; indicators also recompute full arrays. Later distinguish append/update from history prepend, rewind, reset and timeframe switch before switching to update.
- XAU sources have no usable volume (zero); volume profiles/VWAP must not pretend these values represent genuine traded volume. Optional volume-based analysis needs actual volume-bearing input or an explicit unavailable state.

## Ordered implementation gates

1. Audit baseline (this document).
2. Isolate and preserve the existing Risk/Reward branch, then remove active non-position custom drawing/indicator UI and code; preserve saved data and archives.
3. Verify chart, replay and Risk/Reward interactions without adding features.
4. Integrate toolkit/official primitive lifecycle into separate drawing and indicator managers.
5. Add primitives one at a time using pinned upstream source and license notices.
6. Wire supported drawing controls, settings and serialization; no phantom tools.
7. Build an indicator registry with separate calculation/render adapters; reuse verified official sources first.
8. Use native lower panes on the same chart.
9. Keep native volume and replay alignment; retain unavailable-volume semantics.
10. Add official tooltip foundation and retain native markers/crosshair.
11. Add local alert CRUD without notification backend.
12. Optional session highlights (document UTC/timezone and DST policy).
13. Optional volume profile with data validity and performance checks.
14. Evaluate accessibility package against stable chart lifecycle.
15. Incremental updates and profiling; bulk setData remains valid for history prepend/reset/rewind.

After each implementation gate: build, relevant tests and browser console checks; block subsequent gates on regressions. This document does not claim implementation gates 2–15 are complete.

## Sources

- https://github.com/tradingview/lightweight-charts/releases/tag/v5.2.1
- https://tradingview.github.io/lightweight-charts/plugins
- https://tradingview.github.io/lightweight-charts/plugin-examples/
- https://tradingview.github.io/lightweight-charts/docs/panes
- https://github.com/tradingview/lightweight-charts/blob/master/packages/lwc-toolkit/package.json
- https://github.com/tradingview/lightweight-charts/blob/master/LICENSE
