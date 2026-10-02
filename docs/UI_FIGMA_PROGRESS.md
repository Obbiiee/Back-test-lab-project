# Figma workspace and drawing tools

The default frontend uses the local Figma design reference. Its source remains read-only.
The original backend-connected App.jsx remains in source; the engine is set aside for this UI pass.

## Current scope

- Figma layout: header, grouped toolbar, right rail, replay controls, order ticket, positions terminal and journal/calendar.
- TradingView Lightweight Charts supplies candles, volume, pan, zoom and axes. Default XAU/USD uses sampled live Gold API prices, polling every 30 seconds. Demo remains available separately.
- All 77 drawing menu choices are implemented: 13 lines/channels, 14 Fibonacci/Gann, 10 patterns, 12 prediction/measurement tools, 13 brushes/shapes, 11 annotations and 4 icons.
- Click the requested anchors (one to eight points). Freehand uses dragging. Enter finishes Path; Escape cancels an unfinished object.
- Drag objects or handles; edit color, width, text, font size, time and price. Undo/redo, duplicate, delete, eraser, lock, hide, magnet and Keep drawing are available.
- Object tree supports selection and per-object edit/hide/lock/delete.
- Drawings persist in browser local storage per preview timeframe and survive refresh.
- Zoom selects a region. Export chart previews a PNG with visible drawings and offers Download PNG.
- Regression uses closes; anchored VWAP uses HLC3 weighted by volume. Volume Profile distributes OHLCV volume across each candle's price range.
- SMA 20, EMA 20, EMA 50 and volume indicators can be toggled.

## Practical limits

Drawing geometry is implemented by this project on top of Lightweight Charts, not the licensed TradingView Advanced Charts drawing engine. Native TradingView parity is not asserted for custom Gann and related geometry. Harmonic/Elliott patterns are manual drawings, not automatic detection. Volume Profile is marked as an OHLCV estimate; precise price-by-volume requires finer candles or trade-level data. Orders, analytics and account functions remain UI previews.

## Validation

- Production build, ESLint and npm run test:drawings pass.
- Math checks cover time interpolation/extrapolation, irregular intervals, regression, anchored VWAP, zero volume and volume conservation.
- Geometry rendering covers 75 non-position tools, including coincident anchors; long/short positions are checked in the browser.
- Browser creation checks cover all 77 menu tools. Multi-point and two-point tools were rechecked against committed objects, excluding draft previews.
- Browser checks cover endpoint/whole-object dragging, locks, hide/show, eraser, undo, duplication, editable text/table, colors, width, region zoom, repeated brush strokes, refresh persistence and export including drawings. No console errors observed.

## Reference documentation

- [Regression Trend](https://www.tradingview.com/support/solutions/43000518108-regression-trend-drawing-tool/)
- [Parallel Channel](https://www.tradingview.com/support/solutions/43000518117-parallel-channel/)
- [Pitchfan](https://www.tradingview.com/support/solutions/43000518143-pitchfan-drawing-tool/)
- [TradingView drawings list](https://www.tradingview.com/charting-library-docs/latest/ui_elements/drawings/Drawings-List/)

See LIVE_XAU_RISK_REWARD.md for current live-feed details and limitations.

Historical update: HistData.com M1 archive added with 24,448 actual candles (1–25 September 2026 UTC), source markers and Riwayat ON/OFF. See HISTORICAL_XAU.md.
