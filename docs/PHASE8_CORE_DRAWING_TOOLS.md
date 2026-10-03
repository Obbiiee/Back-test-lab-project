# Phase 8 — Core Drawing Tools checkpoint

Scope: Horizontal Line, Vertical Line and Rectangle only. Existing Trend Line is the regression baseline. Phase 9 was not started. This report records evidence; it is not a phase/workflow/roadmap authority. Operational status remains in AI_CONTEXT/04_CURRENT_PHASE.md.

Baseline: `8d526754bc4aacf0449f4bc0065aea52b2cf6547`, branch `main`, origin `https://github.com/Obbiiee/Back-test-lab-project.git`. Final SHA and remote equality are verified after committing, and reported in the task completion message (not embedded self-referentially in this commit).

## Architecture and results

The existing React 19 / Vite / Lightweight Charts 5.2.1 foundation remains. The official open-source [Series Primitives API](https://tradingview.github.io/lightweight-charts/docs/plugins/series-primitives) supports rendering and lifecycle without replacing the engine or installing another drawing library. Existing DrawingManager, DrawingHistory and DrawingPersistence code is unchanged.

- Horizontal Line: one-click, one canonical time/price anchor; spans pane width; body drag changes price only. The time field is preserved even when the chart is panned.
- Vertical Line: one-click, one canonical time/price anchor; spans pane height; body drag changes time only. Existing timestamp interpolation/extrapolation is reused.
- Rectangle: two-click with live dashed draft, any anchor direction; exactly two canonical anchors. Four transient corners provide A/B/C/D handle resize. Body translation applies equal time/price deltas. Interior and border select the body; selected handles take precedence.
- Registry factories validate new models. Creation defaults to Trend Line for existing callers. The existing TrendLinePrimitive class/file retains its compatibility name while rendering all registered core shapes using shared projectGeometry, also used by hit-testing.
- Hidden objects do not paint or hit; locks block geometry but allow selection/deletion under the existing contract. Selection/draft/pixels never enter persistence. No autoscaleInfo is supplied.
- Storage document stays version 1; no migration, old Trend Lines restore. Save/load remains through the existing localStorage adapter, not a new import/export UI. History is runtime-only, bounded to 100 actions; reload intentionally resets history.
- Existing left toolbar gets three menu choices; favorites and chart hints recognize core tools. Existing small primitive controls use generic accessible labels. Overall UI layout is preserved.

## Validation

Passed: test:phase4, test:phase5, test:phase6, test:phase7, test:phase8, test:trading-separation, test:trading, test:drawings (88 archived geometry tools), test:market (3,486,461 M1 candles, eleven timeframes), test:repository, test:ai-bundle, production build and lint. Bundle generated and verified. Phase 5's exact registry inventory was expanded to exactly the four authorized types; no retirement/interaction/storage assertions were weakened.

Real browser verification used isolated localhost port 5184 and a copy of the existing Phase 7 fixture. Production/user preview storage was not used. Verified:

- Horizontal and Vertical creation, select, constrained drag, lock, hide/show and Delete/Backspace.
- Rectangle first-click draft, live dashed preview, Escape cancellation without a committed object, reverse-direction creation, four visible handles, derived-corner resize, equal body deltas, lock, hide/show and deletion.
- Undo/Redo restore/delete actions; Trend Line endpoint editing and keyboard Undo; empty-chart deselection.
- Reload restores exact canonical JSON; 15m → 1h → 15m and replay Next candle preserve canonical values and visibly project correctly.
- Zoom, pan and resize to 980×800 preserve canonical values; viewport reset afterward.
- Long/Short Risk/Reward creation, Long target drag, Create order ticket and placing/canceling a simulated Buy Stop remain functional; drawing JSON unchanged by trading edits. Temporary trading test objects removed.
- Storage contains all four drawing types. Legacy opaque records and backups preserved. Expected existing trading edits normalize whitespace only in the edited legacy trading namespace; untouched namespaces/backups retain original bytes. New drawing adapter never accesses legacy keys.
- Fresh final browser tab reports zero console errors. Earlier development hot-reload errors during a symbol rename were resolved; final reload/build/lint validate corrected imports.

Disposable screenshots: frontend/tests/artifacts/phase8-chart.png and phase8-final.png. These are ignored, not product assets. Automated tests cover all four rectangle orientations and corners, invalid models, axis no-op drags, one-action history/cancel, hidden rendering and no autoscale extension. Browser verification is a manual smoke test, not a claim of exhaustive device/performance QA.

## File inventory and diff review

Created (four files):
- frontend/src/drawings/models/CoreDrawing.js — shared immutable validation for the three registered new types.
- frontend/src/drawings/projectGeometry.js — transient projection shared by renderer and hit-testing.
- frontend/tests/phase8.test.mjs — deterministic authorized-tool regressions.
- docs/PHASE8_CORE_DRAWING_TOOLS.md — this durable checkpoint evidence; no competing authority.

Modified:
- frontend/src/drawings/DrawingTypes.js, DrawingRegistry.js, TrendLineCreation.js, primitives/TrendLinePrimitive.js, interaction/hitTesting.js, interaction/DrawingInteractionController.js, useDrawingTools.js, DrawingControls.jsx.
- frontend/src/FigmaWorkspace.jsx and components/CandleChart.jsx — narrow tool selection/placement/hint integration only.
- frontend/package.json, scripts/ai-bundle.config.json, tests/phase5.test.mjs — test command, new reachable bundle files and exact registry inventory.
- AI_CONTEXT/01_PROJECT_STATE.md, 02_ARCHITECTURE.md, 03_PHASE_HISTORY.md, 04_CURRENT_PHASE.md, 07_TEST_COMMANDS.md and docs/ROADMAP.md — existing owners extended with factual capabilities, evidence/commands and completed-history reference.

Deleted: none. No dependency change or lockfile change. No market/replay/trading/backend/data/archive source changed. Two new modules are reachable in the single production import graph (43 files plus two retained compatibility exports). Git diff reviewed and whitespace checked. Single context authorities retained; current phase points to Phase 9 scope definition awaiting human authorization. No blocker known after validation. Normal push and remote/local HEAD equality plus clean status are required final completion gates.
