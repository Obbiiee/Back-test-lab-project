# Phase 7.5 repository audit — before cleanup

## Authorized pre-v2 cleanup execution — 2026-10-04

Baseline `a613f49d09ade31fb1ea938e99b7a3f0e27bfc83`, verified actual GitHub main. Clean local main was 25 documentation commits behind; the already-audited changes remained docs-only, and fast-forward-only reconciliation produced local/origin/GitHub equality and clean 0/0. No reset, rebase or discarded commit. The human explicitly authorized only the four deletions below, superseding the earlier conservative retention decision for those exact copies/evidence. No other KEEP/REVIEW item was removed.

| Removed path | Blob bytes | Pre-delete verification |
| --- | ---: | --- |
| docs/DRAWING_TOOLS_BROWSER_CHECKS.json | 8,512 | Old generated browser PASS matrix; no runtime/test/build/script/bundle/release or active-doc consumer. Historical validation summary and actual fixtures/tests remain. |
| legacy/preview-before-drawing-2026-10-02/src/assets/hero.png | 13,057 | Unused copy; SHA equality with retained Phase 3 counterpart. |
| legacy/preview-before-drawing-2026-10-02/src/assets/react.svg | 4,126 | Unused copy; SHA equality with retained Phase 3 counterpart. |
| legacy/preview-before-drawing-2026-10-02/src/assets/vite.svg | 8,709 | Unused copy; SHA equality with retained Phase 3 counterpart. |

Only generic template filenames appear in the original cleanup's historical text; those refer to removed active-tree files and preserved counterparts, not consumers of these snapshot paths. Full source/script/test/docs/spec searches found no new consumers. All four authorized candidates removed, none retained. Resolved deletion paths stayed inside the repository; no bulk archive deletion. Removed tracked content: 34,404 bytes (33.60 KiB), not compressed Git-history reduction. Source, dependencies, tests, market data, Phase 3 archive and all protected knowledge remain unchanged.

Validation: full registered frontend/domain/integration/anti-look-ahead/repository regression passed, including all decade data and retained legacy geometry fixtures. Lint/build/distribution audit passed; production asset names/hashes and 101-module count unchanged. Standalone backend tests are not part of the documented local-v1 release gate; backend and requirements have no diff. Actual isolated cold-build smoke: replay/chart, SMA/RSI, Trend Line create/undo/redo, TIME+PRICE equality through 1h→30m, existing Risk/Reward rendering, market paper order advance/close, journal and Analysis reconciliation (4 exits/3 positions/$27.81), persisted Strict synthetic news/markers and console check passed. News file import/CSV download were not re-exercised; retained domain tests and prior acceptance evidence cover them. AI bundle regeneration/verification, final diff review and normal commit/push/remote equality are required before reporting completion. Phase 19/v2.0 was not started.

## v1.0 maintenance audit — 2026-10-04

Verified clean baseline `efe9553622cce95cb9bc2a6501bf9e168bbd7869`: local main, origin/main and actual GitHub main equal, ahead/behind 0/0. Recent commits are the authorized v1.0 implementation/release checkpoints. This maintenance task is explicitly authorized independently of roadmap phases; Phase 19 remains unauthorized. The original Phase 7.5 audit below remains historical evidence.

Pre-deletion tracked inventory: 1,320 files, 285,653,548 bytes (working-tree file content, not compressed Git history). Reference audit covers tracked source, static/dynamic imports, tests, configurations, scripts, package metadata, bundle allowlist, archives and all documentation/planning.

| Classification | Evidence / decision |
| --- | --- |
| DELETE | `frontend/public/icons.svg` (5,031 bytes): original imported template sprite; no reference to its path, filename, sprite IDs or SVG `<use>` consumers anywhere else in tracked files. Not a production asset, test fixture, documented extension or roadmap dependency. Delete only this file. |
| KEEP | All AI_CONTEXT, roadmap, blueprints, Lab Protocol, release/research/planning/history documents. No competing authority or new report. |
| KEEP | Linked Phase 4–7 screenshots/storage proofs, separation evidence, market decade chunks, test/demo CSVs and synthetic news fixtures. Data and acceptance evidence remain intact. |
| KEEP | 81 reachable active source files and two documented compatibility exports; the latter are architectural/test compatibility, not dead code. All runtime/build/lint/download dependencies remain; `fflate` is used by both history download scripts. React types support development tooling. |
| UNCERTAIN → KEEP | Unlinked pre-phase screenshots (`DRAWING_TOOLS_PREVIEW`, `HISTORICAL_XAU_PREVIEW`, `LIVE_XAU_PREVIEW`, `ORDER_POPUP_PREVIEW`, `RISK_REWARD_PREVIEW`, `UI_FIGMA_PREVIEW`, `chart-decade`, `fx-replay-workflow`), archived prototypes/assets and standalone backend/sample generator. Lack of filename references does not prove absence of historical/design value. |
| KEEP / no tracked junk | No tracked dependency/build/bundle/cache/coverage/artifact directories or `.log`, `.tmp`, `.bak`, `.zip` junk. Existing ignored local dependencies/builds/bundle and browser evidence remain available for validation. |

Expected reduction: one obsolete template asset, 5,031 bytes (~4.9 KiB), zero dead-code modules, zero dependencies. No runtime source, data, storage contract, UX or engine changes. Validation results are recorded here after completion; see the existing test-command authority for commands.

Validation completed: full registered `test:regression` (including repository, unit/domain/integration, all decade chunks/11 timeframes, drawing history/persistence, indicators and anti-look-ahead/news/storage suites), lint, production build and release distribution audit passed. Build module count and asset hashes remain identical to the release baseline. Actual isolated production-build browser at port 5196: market/replay advanced, trend line create/undo/redo and reload restored TIME+PRICE anchors, SMA overlay/RSI pane rendered, Long Position transferred to order ticket, Buy 0.01 market order filled/advanced/closed, journal and analysis reconciled 3 exits/2 completed positions/$28.59 realized, persisted synthetic news Strict details/markers remained available. Reload retained account, Risk/Reward and drawings. Console error/warning log empty. Screenshot is ignored local evidence `frontend/tests/artifacts/v1-hygiene-smoke.jpg`; no new permanent report or tracked screenshot. News import/download behavior was not re-exercised in this smoke test; existing deterministic/full v1.0 acceptance evidence remains applicable because no related code changed. AI bundle regeneration/verification and final diff review are mandatory checkpoint gates.

Baseline: `bbe2627db324a91c5cde39bcd75b1cb29358b582`, clean `main`, origin `Obbiiee/Back-test-lab-project`. All eight AI_CONTEXT files and Phase 7 report were read before editing. No unexpected baseline discrepancy.

## Classification

| Category | Paths and evidence | Decision |
| --- | --- | --- |
| ACTIVE PRODUCTION | `frontend/index.html` → `src/main.jsx` → `FigmaWorkspace.jsx`; recursive relative static/dynamic imports reach 41 source files: workspace/styles, CandleChart, chart compatibility, market, trading and new drawing domain. `frontend/public/market/` and favicon are runtime resources. | Preserve exact bytes of the entire reachable source graph and data. |
| ACTIVE TEST | All twelve files under `frontend/tests/`: nine regression suites and three disposable browser fixtures. Drawing tests explicitly import archived tools/geometry; Phase 5/6 read prior storage snapshot pairs. Backend tests protect the standalone backend. | Keep all assertions, fixtures, evidence dependencies and paths. |
| ACTIVE INFRASTRUCTURE | Eight AI_CONTEXT docs; frontend package/lock, Vite/ESLint configuration, scripts; root ignore/attributes, open-source notices. Lock v3 root dependencies/devDependencies match package.json. | Keep; harden ignore/docs and add repository boundary validation. |
| LEGACY / ARCHIVE | `frontend/legacy/phase3/` (50 files), `legacy/preview-before-drawing-2026-10-02/` and one-file prototype (43 files). Separate entry points, excluded from active imports/lint/bundle. | Keep intact; explain purpose and historical status. |
| GENERATED / DISPOSABLE | Ignored AI_BUNDLE, frontend/dist, node_modules, .npm-cache, .history-downloads. docs has historical screenshots/console captures. | Keep existing ignored local output; clarify future output policy. Existing tracked evidence is linked by phase reports and/or tests, so retain. |
| OBSOLETE / DUPLICATE | Ten unreachable active-tree files listed below, each byte-identical to the existing Phase 3 archive. Default frontend template README is stale. | Delete only ten redundant copies; replace template documentation. |
| UNCERTAIN | Backend standalone API/source, data samples/generator, public sample CSV/icons, compatibility `components/TradingLevels.jsx`, `drawings/position.js`, historical reports/evidence. | Retain. Position compatibility is used by market/trading-separation tests; other compatibility documented by separation report. Absence from main import graph alone is insufficient. |

## Candidate deletions (documented before execution)

For each candidate, repository-wide reference searches excluded generated dependencies/output and separately checked archives, tests, scripts, AI allowlist and reports. None is imported by the 41-file production graph, package scripts, regression tests or bundle. Git history places them in initial import `d12df84`; identical copies remain in the existing Phase 3 archive. No new archive or competing source is created.

| Path | Category | References found | Safety / intended action |
| --- | --- | --- | --- |
| frontend/src/api/replayApi.js | OBSOLETE/DUPLICATE | Only dead ImportData; archive App/importer use archived API. | Delete active copy; archive identical. |
| frontend/src/components/ImportData.jsx | OBSOLETE/DUPLICATE | Self definition; archive App. Historical API docs describe old flow. | Delete active copy; preserve public CSV and archived importer/API. |
| frontend/src/components/AnalyticsPanel.jsx | OBSOLETE/DUPLICATE | Self definition; archive App. | Delete active copy; archive identical. |
| frontend/src/components/PositionTabs.jsx | OBSOLETE/DUPLICATE | Self definition; historical reference doc; archive App. | Delete active copy; retain historical document and archived implementation. |
| frontend/src/components/RightToolbar.jsx | OBSOLETE/DUPLICATE | Self definition; archive App. | Delete active copy; archive identical. |
| frontend/src/components/TopBar.jsx | OBSOLETE/DUPLICATE | Self definition; archive App. | Delete active copy; archive identical. |
| frontend/src/components/TradingPanel.jsx | OBSOLETE/DUPLICATE | Self definition; historical reference doc; archive App. | Delete active copy; current trading domain unaffected. |
| frontend/src/assets/hero.png | OBSOLETE/DUPLICATE | No active source/test/script/allowlist reference. | Delete redundant active copy; archive identical. |
| frontend/src/assets/react.svg | OBSOLETE/DUPLICATE | No active source/test/script/allowlist reference. | Delete redundant template asset; archive identical. |
| frontend/src/assets/vite.svg | OBSOLETE/DUPLICATE | No active source/test/script/allowlist reference. | Delete redundant template asset; archive identical. |

No move/rename is planned. No historical evidence deletion is planned: report references give these captures durable checkpoint value, and current automated tests cannot reproduce the original browser observations. Historical documentation will be indexed/labelled rather than rewritten wholesale. Active production code, datasets, archived contents and test assertions remain untouched.

## Verification gates

Full build/lint/Phase 4–7/trading/drawings/market/AI infrastructure suites plus repository boundary checks. Real browser after cleanup: drawing CRUD/history/lock/visibility/reload/timeframe, zoom/pan/resize, replay, Risk/Reward and simulated pending-order popup/cancel. Update AI_CONTEXT only after these gates pass; regenerate/verify small bundle, review every diff, normal commit/push and remote/local hash verification. Phase 8 must not start.
