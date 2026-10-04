# Local v1 release and acceptance evidence

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

Actual cold build on a new isolated localhost origin started replay from 2024-06-03 12:00 with a clean $100,000 account. A Trend Line was created and canonical DOM evidence showed TIME+PRICE anchors; separate drawing Undo/Redo removed/restored it, and changing 30m→1h plus cold reload preserved the identical record. The existing legacy object tree did not list new-domain drawings; its labels were clarified rather than merging the protected domains. Desktop/mobile modal/terminal checks are recorded in PHASE15_FIGMA_UI.md. Final acceptance after Phase 18 remains required.

Distribution retains the chart attribution link and public/licenses notices/license texts. Installed runtime LICENSE bytes are retained for Lightweight Charts, React, React DOM and Scheduler. Tagged chart NOTICE and inspected upstream fancy-canvas/tslib license sources are recorded in OPEN_SOURCE_NOTICES.md. This is a dependency inventory, not legal certification or permission to redistribute market/news provider data.

## Known limits

Single local XAUUSD workspace; no full proprietary TradingView library, cloud sync, authentication or real order execution. New drawing object tree/properties expansion, Ray, advanced indicator persistence, provider-specific news imports, complete historical economic news acquisition and advanced research statistics remain outside the implemented release scope. Current factual capabilities/boundaries remain in AI_CONTEXT/01_PROJECT_STATE.md. Narrow tables scroll and the product remains desktop-first. Performance measurements are non-gating observations, not a guarantee of FPS or playback throughput. Every OS/device, storage-quota condition, cross-tab race and assistive technology is not certified.

Final acceptance and final GitHub checkpoint will be recorded here after the authorized Phase 18 audit; until then this document does not declare v1.0 complete.

Phase 18 local release preparation: package/lock version 1.0.0, no changed dependency versions. `npm run build` and `npm run audit:release` passed; the audit verifies shipped history catalog and retained license artifacts, and excludes disposable QA seed code. Full acceptance remains pending below until the final audit/checkpoint.
