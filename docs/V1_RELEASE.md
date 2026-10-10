# Local v1 release and acceptance evidence

This remains the historical v1 guide for the explicit `/?legacy=local` rollback route. The current local tick/Exness default and required services are described in the [root run guide](../README.md) and [authoritative commands](../AI_CONTEXT/07_TEST_COMMANDS.md#local-exness-workspace); this v1 record does not certify that later dataset or change its acceptance scope.

This is the release evidence/user guide, not a second roadmap, workflow or Definition of Done. Current phase/authorization belongs to AI_CONTEXT/04_CURRENT_PHASE.md; the sole roadmap remains ROADMAP.md. Strategic Lab Protocol/product/website blueprints remain preserved post-v1 direction unless required by existing phase MUST scope.

## Run the existing application

Use Node 22.19 or a Vite-compatible supported Node version. From frontend: `npm ci`, then `npm run dev -- --host 127.0.0.1`. Open the address Vite prints; a local server must remain running. For the production build: `npm run build`, then `npm run preview -- --host 127.0.0.1`. Do not open index.html directly or assume a previously used port is still available. No backend, login or database server is required.

Historical replay uses tracked local market files and the disclosed historical provider limits in HISTORICAL_XAU.md. Live sampled quotes use the existing external Gold API and require internet. Google font loading is cosmetic; system sans-serif fallback remains. Neither live quotes nor synthetic news fixtures are a licensed ten-year economic-news dataset. News import contract, timezone/availability and coverage limitations are in PHASE14_5_ECONOMIC_NEWS.md.

## Storage and recovery

Account, drawings, favorites and replay preferences belong to the browser origin (scheme/host/port); changing port changes the storage namespace. News datasets use separate versioned IndexedDB. Closing the local server does not itself clear browser storage. Do not clear site data to resolve a warning. Malformed/future account/drawing records are preserved; some sessions remain in memory until the original storage is reviewed. Keep the tab open after a save warning. Browser storage is not a backup service or atomic multi-tab collaboration.

Export raw exits/grouped completed positions from Analysis before intentionally resetting account activity. CSV retains financial/research evidence but is not a full account restore format. Keep original canonical imported news JSON; news offers previous-dataset recovery. Indicators are runtime-only and must be added again after reload. Drawing Undo/Redo is runtime-only; canonical drawings persist. New chart drawings have their own controls/history; Risk/Reward objects retain separate trading ownership and legacy toolbar/tree controls.

## Release candidate audit (Phase 17)

Feature scope is frozen to the existing local/manual backtesting product. No Phase 19+, backend/cloud/company/AI/billing additions. Phase 14.5 checkpoint 5308a7a, Phase 16 checkpoint 388f2b0 and Phase 15 checkpoint 6ef3b5f were independently pushed and verified local=origin=actual GitHub main, clean 0/0.

Post-UI full registered regression passed: entire decade data, all drawing model/interaction/history/persistence tests, seven causal indicators/panes, exact replay/account/series differential checks, playback acknowledgement/cancellation, simulator/partial exits, Analysis/CSV/reset guards, strict economic-news mutation/truncation/navigation/storage/index checks and repository/bundle controls. Lint/build passed. Evidence details/measurement limits remain with individual phase reports.

Actual cold build on a new isolated localhost origin started replay from 2024-06-03 12:00 with a clean $100,000 account. A Trend Line was created and canonical DOM evidence showed TIME+PRICE anchors; separate drawing Undo/Redo removed/restored it, and changing 30m→1h plus cold reload preserved the identical record. The existing legacy object tree did not list new-domain drawings; its labels were clarified rather than merging the protected domains. Desktop/mobile modal/terminal checks are recorded in PHASE15_FIGMA_UI.md. Final acceptance is recorded below.

Distribution retains the chart attribution link and public/licenses notices/license texts. Installed runtime LICENSE bytes are retained for Lightweight Charts, React, React DOM and Scheduler. Tagged chart NOTICE and inspected upstream fancy-canvas/tslib license sources are recorded in OPEN_SOURCE_NOTICES.md. This is a dependency inventory, not legal certification or permission to redistribute market/news provider data.

## Known limits

Single local XAUUSD workspace; no full proprietary TradingView library, cloud sync, authentication or real order execution. New drawing object tree/properties expansion, Ray, advanced indicator persistence, provider-specific news imports, complete historical economic news acquisition and advanced research statistics remain outside the implemented release scope. Current factual capabilities/boundaries remain in AI_CONTEXT/01_PROJECT_STATE.md. Narrow tables scroll and the product remains desktop-first. Performance measurements are non-gating observations, not a guarantee of FPS or playback throughput. Every OS/device, storage-quota condition, cross-tab race and assistive technology is not certified.

The final acceptance evidence below supersedes the earlier preparation notes; the final commit/push and remote equality must still be verified for the reported checkpoint.

Phase 18 local release preparation: package/lock version 1.0.0, no changed dependency versions. `npm run build` and `npm run audit:release` passed; the audit verifies shipped history catalog and retained license artifacts, and excludes disposable QA seed code. Full acceptance remains pending below until the final audit/checkpoint.

## Final v1.0 acceptance

Acceptance was performed against the Phase 18 checkpoint 4ff98d12e2cbbebe8ebcf8c5752e2bca0cc4b6fb. All five phase checkpoints were normal pushes, verified local=origin=actual GitHub main with clean 0/0; no force push or destructive reset was used. The 25 documentation commits from adopted baseline 388f54c remain in history; no files were deleted. One current-phase/workflow/roadmap authority remains. Phase 19/v2.0 implementation was not started.

| Gate | Evidence / outcome |
| --- | --- |
| Full regression | All registered tests passed after Phase 18, including 3,486,461 M1 candles and all domain/phase/repository/bundle suites. |
| Lint / production build | Passed; 101 modules; main 339.25 kB (106.72 gzip), chart 241.04 kB (77.06 gzip), CSS 45.42 kB (10.32 gzip). Size observations are not performance guarantees. |
| Distribution | audit:release passed package/lock 1.0.0, installed chart 5.2.1, shipped history catalog/licenses and exclusion of QA seed code. |
| Protected boundaries | Baseline diff is empty for market/replay modules, simulator, replaySettlement, backtestAnalysis calculators, indicators and drawing domain. Chart/React integration changes preserve those contracts. |
| Cold browser trading | Clean-origin replay 2024-06-03 12:00; Buy 0.1 lots, 1h manual step, 50% then final close: two exit rows, one completed position, $27.53 realized, $100,027.53 balance, reconciliation true. Unicode notes survived cold reload. |
| Cold browser indicators/drawing | All seven production indicators added without console errors. Trend Line canonical record survived Undo/Redo, 30m→1h and reload; pointer resize 150→210, zoom and pan left identical TIME+PRICE bytes. Other tool geometry/edit/delete/lock/hide is covered by full deterministic domain tests and earlier phase browser evidence. |
| Cold browser news | Real chooser import of synthetic canonical fixture; complete coverage and exact revealed chart mappings. Existing entry/each-exit derived context appeared without altering financial totals. Next event 14:00 at 1h settled raw endpoint 14:59 (3540-second disclosed overshoot), with correct strict eligible details and no console errors/warnings. |
| UI / persistence | Cold desktop/narrow checks and storage-corruption/legacy safety described in Phase 15/16 reports; browser-origin data remains separate from user preview. |
| CSV | Serialization, Unicode roundtrip and anchor/Blob download lifecycle tests passed. Real browser export click showed no error, but IAB automation did not return a download artifact; this browser-file observation is explicitly unverified, not reported as a saved-file pass. |
| Dependency / security | Phase 16 point-in-time audit reported zero known vulnerabilities; bounded active-source sink/credential checks passed again. No claim of comprehensive security certification. |

File chooser automation took an unusually long time to return despite eventual successful import; this host/tool latency is not attributed to application import performance. Every OS/device, live quota exhaustion and atomic multi-tab safety remain unverified as noted above. No additional provider news-data rights or cloud readiness are claimed.

The local v1 scope passes the required product/regression/release gates with these disclosed validation limits. The final repository checkpoint records acceptance; report its actual Git SHA only after successful normal push, remote equality and clean 0/0. Future work requires separate human authorization, existing context/roadmap reading and preserved boundaries. STOP before v2.0.
