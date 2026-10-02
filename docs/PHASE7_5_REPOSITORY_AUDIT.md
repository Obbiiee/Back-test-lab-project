# Phase 7.5 repository audit — before cleanup

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
