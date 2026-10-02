# Phase 4 — retire legacy non-trading drawing runtime

Completed locally on 2026-10-02. Phase 5 has not started. The working tree also
contains the previously completed Phase 1–3 separation; this report describes
only the additional Phase 4 changes. No commit or push was made in this phase.

| Required result | Status / evidence |
| --- | --- |
| Legacy drawing runtime | RETIRED. Main chart imports TradingLayer only. Old geometry, drafts, freehand, eraser, demonstration, line context actions, Alt drawing shortcuts and non-trading toolbar groups are inactive/removed. |
| Legacy drawing data | PRESERVED. Same `backtest-drawings-v2:<sessionId>` keys and JSON schema. Non-trading/unknown records remain opaque, with original field values and interleaved order. |
| Indicator runtime | Custom SMA/EMA calculation, LineSeries, subscriptions, controls and dialog RETIRED. Indicator layer empty. Existing native volume series remains as part of the unchanged chart. |
| Community library | `lightweight-charts-drawing` uninstalled from package.json/package-lock.json; no executable import remains. Lightweight Charts 5.2.1 remains installed. |
| Trading Layer | WORKING; ownership retained. Orders, native markers/price lines and order popup remain unchanged. |
| Risk/Reward | WORKING: Long/Short create, settings, Entry/SL/TP drag, lock, delete/undo, Create Order and load/save. |
| Build | PASS (`npm run build`). |
| Lint | PASS, zero errors/warnings (`npm run lint`). Historical snapshot intentionally excluded. |
| Trading separation | PASS (`test:trading-separation`). |
| Trading simulation | PASS (`test:trading`). |
| Market | PASS (`test:market`): all decade chunks, 3,486,461 M1 candles, OHLC/timestamps, 11 timeframes. |
| Legacy geometry reference | PASS (`test:drawings`), 88 tools, irregular times, coincident anchors and volume conservation, using archived source. |
| Phase 4 protection | PASS (`test:phase4`): exact unchanged bytes, mixed/null/unknown records, editing/delete/undo, backup preservation, corrupt JSON, prototype-name types and empty namespaces. |
| Browser console | CLEAN: no error entries on isolated app tab. |
| Storage before/after | PASS: exact byte equality of all three initial drawing keys after retirement + reload. Separate interaction snapshot also retains every retired/unknown record and pre-existing backup. |
| Blockers | None for Phase 4. |

## Files modified / added for Phase 4

- `frontend/src/components/CandleChart.jsx`: remove legacy renderer, creation paths and indicators; restore only valid risk/reward into runtime while persistence retains everything else.
- `frontend/src/FigmaWorkspace.jsx`: retain cursor and Long/Short toolbar UX, magnet/lock/hide/delete/keep/favorites controls; remove legacy menus and indicator dialog. Existing favorite preferences are retained but unsupported favorites are not displayed. Workspace layout and popup JSX unchanged.
- `frontend/src/FigmaWorkspace.css`: remove indicator-only/freehand/eraser/draft rules; retain shared Risk/Reward and trading styles.
- `frontend/src/chart/ChartObjectOverlay.jsx`: retain TIME + PRICE projection, resize and drag plumbing for Risk/Reward; remove unused freehand/eraser/demo/anchored-text code. Shared `.drawings-layer` CSS/export hook is still used by Risk/Reward; it does not activate DrawingsLayer.
- `frontend/src/chart/LegacyObjectPersistence.js`: retain original record slots/order and opaque records; skip writes when unchanged; preserve existing backup and disable saving on invalid JSON/storage failure.
- `frontend/src/trading/RiskRewardController.js`: type recognition uses own registry entries, preventing unknown prototype names from being misidentified as trading objects. Ownership and creation/resize math unchanged.
- `frontend/src/trading/RiskRewardLayer.jsx`: remove retired eraser mode from its neutral cursor allowlist; Risk/Reward ownership/rendering remains in Trading Layer.
- `frontend/package.json`, `frontend/package-lock.json`: remove unused community package; add Phase 4 regression script.
- `frontend/eslint.config.js`: exclude the explicitly archived historical snapshot.
- `frontend/tests/drawings.test.mjs`, `frontend/tests/trading-separation.test.mjs`: legacy reference assertion/imports target archived source, retaining existing assertions.
- `frontend/tests/phase4.test.mjs`: storage and runtime-retirement regressions.
- `frontend/tests/browser/phase4.html`: disposable origin test fixture, seed guard, snapshot/reload UI. Not an application entry point and not part of production build.
- `frontend/legacy/phase3/README.md`, full Phase 3 source snapshot, this report, storage snapshots/screenshots, `OPEN_SOURCE_NOTICES.md`.

## Files retired from active source

All source contents were copied before cleanup to `frontend/legacy/phase3/src/`;
archive byte equality was checked before removing active copies:

- `components/DrawingsLayer.jsx`
- `components/DrawingGeometry.jsx`
- `components/NativeDrawings.jsx` (archive suffix `.reference.txt`)
- `components/LeftToolbar.jsx`
- `drawings/tools.js`
- `drawings/native.js` (archive suffix `.reference.txt`)
- `indicators/calculations.js`
- unused `App.jsx` and `App.css` from the older entry point

Compatibility `drawings/position.js`, coordinates, ChartObjectBridge and shared
projection remain; Trading Layer imports no retired drawing engine. No
DrawingManager, official drawing primitives, indicator engine or namespace
migration was introduced.

## Protected scope verified

Hash comparison against the Phase 3 snapshot confirms unchanged market modules,
OrderTicket, PositionsPanel, Journal, useTrading, simulator, TradingLayer,
TradingLevels, RiskRewardGeometry, RiskRewardSettings, chartAnnotations,
riskReward calculations/order conversion and FxWorkspace.css. Dataset/provider,
history/aggregation, replay, paper account and backend were not modified. Main
existing preview on port 5173 still returns HTTP 200.

## Browser verification

Used an isolated disposable origin on port 5180, without touching the user's
existing port 5173 storage. Seeded mixed legacy/trading/unknown JSON plus an
existing backup and an unopened timeframe key, then loaded the old runtime,
captured BEFORE, retired it, reloaded and captured AFTER before editing objects.

Verified candles and native crosshair; zoom/pan; viewport resize (1440×960 and
980×800); TIME + PRICE anchors unchanged by view movement; history loading into
April when panning backward from May/June; 30m → 1h → 30m; replay steps; Long/Short
creation and settings; Entry/SL/TP drag and lock; delete/undo; Create Order into
the existing centered popup; Buy Stop placement/cancel; Market Buy with SL/TP;
native SL amend to 2321.450; visible Buy marker/native price lines; position
survives replay and reload. Object tree contains only four risk/reward objects,
with no legacy lines/rectangle/text/fib. No legacy tool or indicator button is
available. Screenshot and console inspection completed.

Evidence:

- `PHASE4_STORAGE_BEFORE.json` / `PHASE4_STORAGE_AFTER.json`: exactly equal, including whitespace, record order, unknown fields and existing backup.
- `PHASE4_STORAGE_AFTER_INTERACTIONS.json`: intentional new/edited trading objects; legacy records and original backup intact. Visiting 1h adds its safe backup; the original 1h payload remains byte-identical.
- `PHASE4_HISTORY_PREVIEW.jpg`: older April history loaded.
- `PHASE4_TRADING_PREVIEW.jpg` / `PHASE4_FINAL_PREVIEW.jpg`: candles, Buy marker/native lines, Risk/Reward and surviving position.
- `PHASE4_ORDER_POPUP.jpg`: existing centered Order popup.

Stopped after Phase 4. Awaiting Phase 5 instructions.
