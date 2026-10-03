# Actual product and repository state

- React 19 / Vite 8; installed Lightweight Charts 5.2.1 (package range ^5.2.1).
- XAUUSD approximately ten years: 3,486,461 validated M1 candles; eleven aggregated timeframes; progressive historical loading.
- Active frontend replay: `frontend/src/market/useReplayMarket.js` loads date-selected M1 chunks, aggregates the revealed prefix, steps timeframe buckets, loads older history, extends forward chunks, restores/saves replay date. Workspace controls play/pause/speed and stepping; engine also exposes backward step, while UI previous-candle control is disabled. Archived/backend modules are not evidence of active frontend capabilities.
- Trading: market/limit/stop and pending simulation, buy/sell positions, entry/SL/TP, independent Long/Short Risk/Reward, native markers and price lines.
- Drawing: DrawingManager/Registry, immutable TIME + PRICE Trend Line, Horizontal Line, Vertical Line and Rectangle models, official series primitive, separate creation/interaction controllers, A/B creation, draft, selection, shared projection/hit testing, four virtual Rectangle corner handles, endpoint/body drag and axis-constrained line editing, keyboard delete, ESC/cancel and cross-timeframe projection.
- Indicator runtime remains retired; native chart Volume series remains available.

All four drawing types persist in a separate version-1 localStorage namespace across reload, timeframe and replay changes. Canonical commit snapshots provide independent Undo/Redo (100 actions, runtime only), lock/unlock and hide/show. Malformed/future storage is preserved without overwrite; valid records can be recovered read-only. No magnet integration, advanced drawing tools, Indicator Engine, properties UI, object tree or legacy migration. Existing trading controls/history remain separate and do not imply these features exist for the new drawing domain.

Phase 7.5 repository cleanup removed ten unreachable copies already preserved byte-identically in Phase 3. The 41-file production import graph, compatibility exports, datasets, archives and existing test assertions remain unchanged. Root/frontend/docs READMEs identify the single active source; repository boundary tests and ignore rules protect future hygiene.
