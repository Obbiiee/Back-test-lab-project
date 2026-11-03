# Terminal drawing & indicator inventory (Issue #21)

Living checklist for [Issue #21](https://github.com/Obbiiee/back-test-lab-project/issues/21). Base: `main` @ `8ba3489`. Design spec: Draft PR #20 (`docs/RIKSORA_DESIGN_FREEZE_V1/` 10–15). Branch: `claude/terminal-drawings-indicators-v1`.

A tool is only ticked when it can be created, has working Properties controls, survives reload and timeframe change, and has an automated test.

## C-00 audit of `main` (before this branch)

**Two drawing systems exist.**

| System | Files | Used by | State |
|---|---|---|---|
| Research primitives (canvas, Lightweight Charts series primitive) | `src/drawings/*` (`DrawingManager`, `TrendLinePrimitive`, `hitTesting`, `DrawingPersistence` v1) | Tick Alpha / Session terminal (`researchOnly`) | 9 types. Create, select, drag anchors/body, lock, hide, delete, undo/redo, v1 storage. **Style was fixed**: colour `#58a6ff`, width 2, no dash/opacity/fill, no Properties panel, no coordinate editor, no layer order, Text was 12px only, Fib levels fixed 0–1. |
| Legacy SVG objects (`ChartObjectOverlay`, `RiskRewardController`) | `src/chart/*`, `src/trading/*`, settings form inside `CandleChart.jsx` | Long/Short Position planning (all modes) | Entry/SL/TP with R:R settings, coordinates form. Untouched by this branch except where noted. |

**Indicators** (`src/indicators/*`): 7 registered (SMA, EMA, Bollinger, RSI, MACD, ATR, Stochastic). Parameters editable (periods/multiplier), show/hide, remove, 16-instance cap, v1 storage. **No per-output style** (colour/width fixed in the registry), no pane move, no pane height, no placement change.

**Baseline tests** on `main`: 28 of 29 `test:*` scripts pass in Linux. `test:stitch-analytics` fails before and after this branch because it shells out to `backend/venv/Scripts/python.exe` (Windows path), an environment issue, not a code failure.

## Checkpoint status

### C-01 shared Drawing Properties foundation — DONE

- One registry-driven editor (`src/drawings/DrawingProperties.jsx`) with tabs **Style / Coordinates / Text / Levels / Object**. Controls with no effect for a tool are hidden (`CAPABILITIES` in `drawingStyle.js`).
- Style: colour presets + picker + hex, thickness 1–6 px with live preview, solid/dashed/dotted, opacity 0–100 %, fill colour/opacity, extend left/right, price/time labels, reverse.
- Coordinates: exact UTC time + price per anchor; ▲▼ N ticks (Session `tickSize`, decimal-safe), ◀▶ N bars (displayed timeframe), whole-drawing move, Shift = 10×, ArrowUp/Down in the price field, arrow keys on the chart nudge the selected drawing.
- Text: content, font size 10–32, Plex Mono / Inter (self-hosted), **Bold**, *Italic*, text colour, background or none, border, align, position.
- Levels (Fib): per-row value, show/hide, colour, add/remove, defaults (0 · .236 · .382 · .5 · .618 · .786 · 1 shown; 1.272 · 1.618 available).
- Object: visible, lock, layer **front / forward / backward / back**, rename, duplicate, delete. Object Tree shows top layer first with the same actions.
- Undo/redo covers drawing edits only; bursts from one control coalesce into one step.
- Persistence v2 (`DrawingDocumentStore`, key `backtest-drawing-manager-v2:`): stable UUID, type, anchors, sparse style, name, layer order. v1 documents load as the upgrade source and their bytes are never rewritten. Unknown/hostile records keep the namespace read-only; a newer write from another tab is not overwritten.
- Renderer and hit testing share one geometry description (`drawingShapes.js`) so every style change is also clickable where it is drawn.
- Evidence: `tests/c01-drawing-properties.test.mjs` (unit), `tests/qa/terminal-qa.cjs` (real browser, 10 steps), screenshots in `docs/qa/issue-21/c01/`.

### C-02 nine existing drawings + Long/Short — partly

| # | Tool | Properties | Tests |
|---|---|---|---|
| 1 | Trend Line | style, extend L/R, price labels, coords | ✓ |
| 2 | Ray | style, price labels, coords | ✓ |
| 3 | Horizontal Line | style, price label, coords (price only) | ✓ |
| 4 | Vertical Line | style, UTC time label, coords (time only) | ✓ |
| 5 | Rectangle | style, fill, extend L/R, coords | ✓ |
| 6 | Arrow | style (head scales with width), coords | ✓ |
| 7 | Fibonacci Retracement | style, level rows, band fill, extend, reverse, labels | ✓ |
| 8 | Text | full text tab | ✓ |
| 9 | Measure | style, label size | ✓ |
| 26/27 | Long / Short Position | existing R:R settings form (legacy system) | existing `test:stitch-trading`, `test:trading-separation` |

Mobile flow (done): tap tool → tap anchors → tap select → finger-drag handles → bottom-sheet stepper. Two fixes: (1) a two-finger pinch with a tool armed used to place anchor A; anchors placed during a multi-touch gesture are now rolled back and the synthetic click after it is ignored; (2) a finger drag on a handle was cancelled by the browser's pan gesture; while a drawing is selected the chart sets `touch-action: none`, restored when nothing is selected. Evidence: `tests/qa/mobile-touch-qa.cjs` (6 steps on a 390×844 touch profile), `tests/c03-professional-drawings.test.mjs` (touch guard), screenshots `docs/qa/issue-21/c02/`.

Still open for C-02: Long/Short keep their dedicated Entry/SL/TP form (legacy system that feeds the server review/confirm flow); moving them onto the shared panel is scheduled with C-09 so the trading path is changed once and tested end to end.

### C-05 indicator settings — DONE

Inputs / Style / Placement tabs per instance: per-output visible, colour, thickness 1–5, solid/dashed/dotted, opacity, histogram rising/falling colours, reset style; overlay ↔ own pane, move pane up/down, pane height, reference lines; hide, duplicate, remove; search and categories. Persisted sparsely in `backtest-indicators-v1:`. Evidence: `tests/c05-indicator-settings.test.mjs`, `tests/qa/indicators-qa.cjs`, `docs/qa/issue-21/c05/`.

### C-06 core indicators — DONE (50 registered)

43 added to the original 7. Conventions and golden-test method: [terminal-indicators.md](terminal-indicators.md). Evidence: `tests/c06-indicators.test.mjs` (22,573 points against an independent Python reference; causality and degenerate input for all 50).

### C-07 volume — shown as unavailable

V01–V12 listed and disabled with the reason (quote-only data). No synthetic volume.

### C-03 professional drawings D10–D25 — DONE

All 16 tools: created with the real mouse/touch flow, full Properties (shared style + tool-specific controls), hit-tested where drawn, undo/redo, Object Tree, persisted in v2 storage and restored on reload. Shared renderer and hit geometry in `src/drawings/professionalShapes.js`; pure math in `src/drawings/professionalGeometry.js`.

| # | Tool | Anchors · input | Calculation / geometry | Tool-specific Properties | Notes |
|---|---|---|---|---|---|
| 10 | Extended Line | 2 clicks | segment extended both ways | price labels | |
| 11 | Horizontal Ray | 1 click | from anchor to right edge | price label | |
| 12 | Cross Line | 1 click | horizontal + vertical through anchor | price + UTC time labels | |
| 13 | Parallel Channel | 3 clicks: A, B baseline, C width | parallel through C (price offset at C) | fill, middle line, extend L/R | |
| 14 | Regression Trend | 2 clicks: start/end time | least squares on **revealed** closes between the times; bands ± k·σ(residual) | band deviation 0–5, fill, extend right | handles snap to the fit; bars not yet revealed are never read |
| 15 | Fibonacci Extension | 3 clicks: A, B, C | level = C + (B − A)·r; defaults 0 · .382 · .618 · 1 · 1.272 · 1.618 · 2 · 2.618 (0/.618/1/1.618/2.618 shown) | level rows, band fill, labels, extend | |
| 16 | Fibonacci Channel | 3 clicks: A, B baseline, C width | parallels at r·width; defaults 0 · .236 · .382 · .5 · .618 · .786 · 1 · 1.618 | level rows, band fill, labels, extend | |
| 17 | Rotated Rectangle | 3 clicks: A, B edge, C height | height = C's perpendicular distance (screen) | fill | |
| 18 | Ellipse | 2 clicks: bounding corners | inscribed ellipse | fill | |
| 19 | Polyline | click per node (2–64); Done / Enter / double-click; Backspace removes | path; closed polygon when fill > 0 | insert / remove node | creation bar with Done/Undo node/Cancel |
| 20 | Brush | press-drag | decimated ≥3 px, ≤512 points | colour, width, opacity | chart pan paused while the tool is active |
| 21 | Highlighter | press-drag | as Brush; defaults yellow, 10 px, 35 % | colour, width, opacity | |
| 22 | Anchored Text | 1 click + text | pin + label above anchor | full Text tab | defaults centred, bold |
| 23 | Callout | 2 clicks (anchor, label) + text | leader line + framed label | full Text tab | leader previewed while typing |
| 24 | Price Range | 2 clicks | Δ price, ticks on Session tick size, % | fill, label size | |
| 25 | Date Range | 2 clicks | revealed bars in range, elapsed d/h/m | fill, label size | |

Evidence: `tests/c03-professional-drawings.test.mjs`, `tests/qa/drawings-pro-qa.cjs` (25 real-browser steps), screenshots `docs/qa/issue-21/c03/`.

### C-04 extended professional tools — DONE (22 tools)

Shapes in `src/drawings/extendedShapes.js`. Every tool has the shared Style/Coordinates/Object tabs; levelled tools have editable level rows; markers have their own controls.

| Tool | Anchors | Geometry | Specific Properties |
|---|---|---|---|
| Pitchfork / Schiff / Modified Schiff | 3 (pivot A, B, C) | median from origin through mid(B,C); tines through B and C. Origin: A / (A.time, mid price A–B) / mid(A,B) | extra parallels (0.5, 1.5, 2 × half-width), fill, extend |
| Fib Time Zone | 2 (time A, B) | verticals at A + (B−A)·{0,1,2,3,5,8,13,21,34,55,89} | level rows, UTC time labels |
| Trend-Based Fib Time | 3 | verticals at C + (B−A)·r | level rows, time labels |
| Fib Speed Resistance Fan | 2 | rays from A to (B.x, A + (B−A)·r) | level rows, band fill, labels |
| Fib Circles | 2 | circles around mid(A,B), radius ½·AB·r | level rows, labels |
| Fib Speed Resistance Arcs | 2 | half circles around B facing A, radius AB·r | level rows, labels |
| Fib Wedge | 3 (apex A, B, C) | arcs AB·r inside the smaller A→B / A→C sweep | level rows, fill |
| Gann Fan | 2 | A→B is 1×1 (user scale); 1×8 … 8×1 rays | level rows (ratio), labels |
| Gann Box | 2 | grid at 0 · .25 · .382 · .5 · .618 · .75 · 1 both ways, diagonals | level rows, fill |
| ABCD / XABCD | 4 / 5 | labelled path; leg ratios from canonical prices (BC/AB, CD/BC; plus AB/XA, AD/XA) | fill (XABCD), labels |
| Head and Shoulders | 7 | labelled path, neckline through both neck pivots | extend neckline |
| Triangle Pattern | 4 | path + converging A–C / B–D lines | fill, extend right |
| Elliott Impulse / Correction | 6 (0–5) / 4 (0-A-B-C) | labelled path, labels above highs / below lows | label size |
| Cyclic Lines | 2 (base, interval) | verticals every A→B | repeats 1–100 |
| Date and Price Range | 2 | Δ price · % · ticks and bars · duration | fill |
| Price Label | 1 | price tag at anchor | label size |
| Icon Marker | 1 | own glyphs: circle, square, diamond, triangles, star, flag, cross | icon, size 8–48 |
| Arrow Marker | 1 | arrow tip on the anchor, up or down | direction, size |

Pattern tools are manual annotations only: nothing is detected or forecast. Fans, circles, arcs and Gann angles are drawn in the current screen scaling (as on any chart); the stored anchors are always TIME+PRICE. Evidence: `tests/c04-extended-drawings.test.mjs`, `tests/qa/drawings-ext-qa.cjs` (26 browser steps), screenshots `docs/qa/issue-21/c04/`.

### C-08 performance & responsive — DONE

Measured with `tests/qa/performance-qa.cjs` (headless Chromium, dev build, Vite on 5179). Load: 512 revealed 1m candles + the previous calendar month via the existing `chart-history` API (served by a Playwright route, 89 pages × 512 = 44,640 past candles, 45,152 total, within the 50k policy), 100 stored drawings of mixed types, 16 indicator instances (SMA, EMA, BB, RSI, MACD, ATR, Stochastic, Supertrend, Ichimoku, Keltner, HMA, ADX, CCI, PSAR, Pivots, Squeeze).

| Metric | Result | Gate |
| --- | --- | --- |
| Load (incl. 89 API pages) | 2.4–2.8 s | — |
| JS heap after forced GC | 482 MB (bare chart: 44 MB) | recorded |
| Frame time pan/zoom/hover p50 / p95 | 16.7 / 16.8 ms | p95 < 50 ms |
| Worst single frame | 33–350 ms across runs, 0–1 long tasks | < 500 ms |
| Hover | 50–59 moves/s | — |
| Select a drawing among 100 | 0.23–0.25 s incl. 100 ms settle (was 14–16 s) | < 1 s |
| Viewports 320 / 375 / 390 / 844×390 landscape / 768 / 1024 / 1440 | no horizontal overflow, chart and drawing tools reachable | all |

Fixes found by this run:
- `AlphaWorkspace` passed `transition={{kind:'forward'}}` — a new object every render — so any UI change (e.g. selecting a drawing) re-ran the candle sync and recomputed all 16 indicators over 45k candles. Now a frozen module constant.
- Regression Trend fit and Date Range bar count use binary search (`lowerBound`/`upperBound`) instead of scanning all bars.
- `IndicatorControls` imported `outputStyle` from the series adapter, which pulled lightweight-charts into the entry bundle (entry 113 → 184 kB gzip). The helpers now live in `src/indicators/indicatorStyle.js`; entry is 125 kB gzip vs 113 kB on `main` (+12 kB: indicator catalog/registry, which `FigmaWorkspace` already loads eagerly). Chart chunk 37 kB gzip (main 20 kB) for 47 tools + 50 indicators.

Heap: most of the 482 MB is 16 indicators × ~45k points held by lightweight-charts and the engine. Acceptable on desktop; on low-memory phones a user loading a full month of 1m history with 16 indicators may feel it. A follow-up candidate is computing indicators only over a bounded window — not done here because it changes indicator warm-up semantics.

Evidence: `docs/qa/issue-21/c08/results.json`, screenshots `docs/qa/issue-21/c08/`.

### C-09 integration — DONE (UI side; finance/API sign-off is Codex's)

`tests/qa/order-flow-qa.cjs` drives the real terminal against Codex's **unchanged** local backend (`python -m execution.local_api`, PostgreSQL 16, migrated with `infrastructure.database.migrate`) and the synthetic fixture source (`/?tick-alpha=local`, Vite on 5196 — the backend's CORS allow-list). 12 steps:

1. Normal replay (Session stepped tick by tick to 01:00) vs jump (second Session seeks straight to 01:00): the 60 completed 1m candles are identical and no candle is later than the cursor in either.
2. Long Position drawn → nothing sent to the server.
3. Create order → ticket prefilled from the drawing (Buy / Long, SL below / TP above, rounded to the price grid); still nothing sent.
4. A forbidden order (Buy Limit above Ask) → server review refused (409), no confirm step, nothing committed.
5. Valid market intent → `POST /reviews` 200 → "Confirm reviewed order" shows server values → nothing committed before Confirm.
6. Confirm → `POST …/confirm` 200; the order is `PENDING` at the confirm time and fills only on the next revealed quote (e.g. 01:00:00 pending → 01:01:00 filled), shown on the chart and in the terminal.
7. Drawing Undo removes the planning drawing; the committed order is unchanged and no cancel/close is sent.
8. Seek with an order on the books → refused by the server (`REFUSED_REWIND_REQUIRES_FORK`), shown to the user, cursor unchanged.
9. Reload → versioned drawing document (`backtest-drawing-manager-v2`), versioned indicator settings and the server-side position all return.
10–12. Phone 390×844 with touch: Long and Short Position → Create order → ticket fits the screen; Short gives Sell / Short with SL above and TP below; nothing sent.

Limits: the synthetic fixture covers about 8.5 hours (2,048 ticks × 15 s), so "Jump 72h" was verified as jump-vs-normal over the range the fixture has. A literal 72-hour jump needs the Exness historical store (`BTL_EXNESS_STORE`), which is not in this environment. Long/Short keep their existing settings dialog and SVG layer (working and tested above); moving them onto the shared canvas Properties panel is left as a separate change so this PR does not alter the trading path.

Evidence: `docs/qa/issue-21/c09/` (screenshots, `results.json`, `orders-after-replay.txt`, `ticket-fields.json`).

## Integration gaps (for Codex, no backend change made here)

| Screen | Need | Status |
|---|---|---|
| Terminal drawings | Server-side drawing storage per account/Session (currently browser localStorage, account-scoped key) | MISSING route; local-only label stays |
| Volume indicators V01–V12 | Qualified traded-volume source | Quote-only Bid/Ask data: shown as unavailable, never synthesised |
| Order review refusal | Specific reason codes from `POST /reviews` (today a Buy Limit above Ask returns generic `INVALID_INPUT`) | UI shows the code as given; a specific code would let the ticket explain the fix |
| Seek refusal copy | `REFUSED_REWIND_REQUIRES_FORK` also blocks a forward seek while an order is open; the UI copy says "replay an earlier time" | Copy follows the existing server mapping; wording can be generalised once Codex confirms the rule |
| 72h jump evidence | Exness historical store for QA | Not available here; jump verified on the synthetic fixture range |
