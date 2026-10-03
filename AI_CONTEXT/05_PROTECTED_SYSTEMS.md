# Protected boundaries

Change these only when the authorized task explicitly requires it, with relevant regression coverage:

- Market/Data: `frontend/src/market/{candles,history,useGoldMarket,useReplayMarket}.js`; historical files `frontend/public/market/`, `data/`.
- Replay: `frontend/src/market/useReplayMarket.js`, replay controls in `frontend/src/FigmaWorkspace.jsx`; separate backend code `backend/engine/replay/`, `backend/services/replay_service.py`.
- Trading/orders: `frontend/src/trading/{simulator,useTrading}.js`, OrderTicket/PositionsPanel/Journal; `backend/engine/trading/`.
- Risk/Reward: `frontend/src/trading/RiskReward*`, `TradingLayer.jsx`.
- Native annotations: `frontend/src/trading/{chartAnnotations.js,TradingLevels.jsx}`; CandleChart integration.
- Legacy storage/compatibility: `frontend/src/chart/{LegacyObjectPersistence.js,ChartObjectBridge.js,ChartObjectOverlay.jsx}`; `backtest-drawings-v2:*` and backups. Do not migrate, drop unknown records or overwrite backups casually.
- Drawing foundation: `frontend/src/drawings/{DrawingManager,DrawingRegistry,DrawingTypes}.js`, `models/TrendLine.js`, primitives and creation/interaction controllers. Preserve TIME + PRICE.
- Archives: `frontend/legacy/`, `legacy/`; do not reorganize or reactivate.
- Regression assertions/evidence: `frontend/tests/`, `backend/tests/`, storage fixtures in `docs/` referenced by tests. Never weaken tests or remove required evidence.

This is not blanket protection of the entire repository. Narrow infrastructure/context work is permitted within its own scope.

- Indicator foundation: `frontend/src/indicators/`. Calculators receive only chart-visible candle copies, never raw future data or domain stores; preserve config validation, output timestamp validation, error isolation and owned-series cleanup. Legacy indicator runtime remains retired. Native Volume stays separate. Reference indicator is test-only; authorized production catalog is exactly SMA/EMA/Bollinger Bands; additional products, panes and persistence require separate authorization.

- New drawing persistence/history: `DrawingPersistence.js`, `DrawingHistory.js`; `backtest-drawing-manager-v1:*`. Preserve schema, canonical fields, commit boundaries and trading isolation. History resets on reload; no cross-tab merge/backend sync.

- Source-of-truth hygiene: `frontend/src/main.jsx` is the single entrypoint. Preserve intentional compatibility exports and test-dependent archives/storage fixtures. Do not reintroduce duplicate runtime trees or remove files based only on absence from the production graph. `test:repository` checks these boundaries; update its allowlist only with documented evidence.
