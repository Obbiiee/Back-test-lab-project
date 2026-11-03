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

Open for C-02: mobile tap-to-place flow and two-finger cancel for the research tools; move Long/Short onto the shared panel.

### C-05 indicator settings — DONE

Inputs / Style / Placement tabs per instance: per-output visible, colour, thickness 1–5, solid/dashed/dotted, opacity, histogram rising/falling colours, reset style; overlay ↔ own pane, move pane up/down, pane height, reference lines; hide, duplicate, remove; search and categories. Persisted sparsely in `backtest-indicators-v1:`. Evidence: `tests/c05-indicator-settings.test.mjs`, `tests/qa/indicators-qa.cjs`, `docs/qa/issue-21/c05/`.

### C-06 core indicators — DONE (50 registered)

43 added to the original 7. Conventions and golden-test method: [terminal-indicators.md](terminal-indicators.md). Evidence: `tests/c06-indicators.test.mjs` (22,573 points against an independent Python reference; causality and degenerate input for all 50).

### C-07 volume — shown as unavailable

V01–V12 listed and disabled with the reason (quote-only data). No synthetic volume.

### C-03, C-04, C-08, C-09

Next. Tracked in the PR description as each batch lands.

## Integration gaps (for Codex, no backend change made here)

| Screen | Need | Status |
|---|---|---|
| Terminal drawings | Server-side drawing storage per account/Session (currently browser localStorage, account-scoped key) | MISSING route; local-only label stays |
| Volume indicators V01–V12 | Qualified traded-volume source | Quote-only Bid/Ask data: shown as unavailable, never synthesised |
