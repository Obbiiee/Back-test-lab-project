# Trading layer separation — phases 1–3

Date: 2026-10-02. Scope: protect the current state, isolate trading from drawings, verify trading, then stop. No primitive, indicator or replay optimization has been added.

## Protect current state

- Active checkout: `C:/Users/kuchi/OneDrive/Dokumen/Backtest lab`.
- Remote: `https://github.com/Obbiiee/Back-test-lab-project.git`, branch `main`; baseline HEAD `9bf062b`.
- Initial working tree: two untracked documents from the previous audit (`OPEN_SOURCE_NOTICES.md` and `docs/OFFICIAL_LIGHTWEIGHT_CHARTS_AUDIT.md`), no tracked modifications. These documents were retained.
- Existing source archive remains at `legacy/preview-before-drawing-2026-10-02/`; no archive or historical dataset was deleted.
- Current application entry remains `frontend/src/main.jsx` → `FigmaWorkspace.jsx` → `CandleChart.jsx`.
- Drawing persistence: `backtest-drawings-v2:<sessionId>`, usually `XAUUSD-live-<timeframe>`. The value is an array of objects containing `id`, `type`, and `points: [{time, price}]`; optional properties include text, styling, locked/hidden, screenAnchor and risk sizing fields.
- Long/short objects retain their existing `long-position` / `short-position` type names. Anchors are Entry, SL, TP and optional width/end anchor. Risk settings include accountSize, riskMode, riskValue, lotSize, pointValue, leverage, tickSize and quantityPrecision.
- Paper account remains `backtest-paper-account-v1`; replay cursor remains `backtest-replay-time-v1`; workspace timeframe remains `backtest-workspace-interval-v1`. Their producers and formats were not changed.
- Additional persistence identified: market sample cache `backtest-xau-goldapi-sampled-1m-v1` in `useGoldMarket.js` and favorites `backtest-favorites-v1` in `FigmaWorkspace.jsx`; neither was migrated.
- Existing drawing runtime inventory: `DrawingGeometry.jsx`, `DrawingsLayer.jsx`, `drawings/tools.js`; unused community adapters `NativeDrawings.jsx` / `drawings/native.js`. Indicators: active `movingAverage` in `CandleChart.jsx` and unused `indicators/calculations.js`.
- Protected market/replay inventory: `market/useGoldMarket.js`, `useReplayMarket.js`, `candles.js`, `history.js`, `public/market/decade/`; trading inventory: `trading/useTrading.js`, `simulator.js`, `OrderTicket.jsx`, `PositionsPanel.jsx`, `Journal.jsx`. Backend `engine/market_data`, `engine/replay`, `engine/trading`, `services/replay_service.py` and API remain untouched.
- Final changes are available in the local working tree for review. This task did not create a commit or push these changes.

## Files modified / added

| File | Change |
| --- | --- |
| `frontend/src/components/CandleChart.jsx` | Route trading objects to TradingLayer; delegate creation/resize/settings to trading controller; keep existing host toolbar/history; use compatibility persistence; compose both overlay layers in chart export. |
| `frontend/src/FigmaWorkspace.jsx` | Order popup seed conversion now comes from the trading domain; UI and popup behavior retained. |
| `frontend/src/components/DrawingsLayer.jsx` | Legacy drawing wrapper excludes trading objects. Legacy geometry and drawing tools remain active. |
| `frontend/src/components/TradingLevels.jsx` | Compatibility export to the trading-owned component. |
| `frontend/src/drawings/position.js` | Compatibility export to the trading-owned Risk/Reward calculation. |
| `frontend/src/drawings/tools.js` | Trading tool definitions now originate in the trading domain; toolbar registry retains compatible names. Shared coordinate helpers are re-exported. |
| `frontend/src/chart/coordinates.js` | Existing time/logical mapping extracted unchanged, usable without importing a drawing engine. |
| `frontend/src/chart/ChartObjectOverlay.jsx` | Existing projection and pointer plumbing extracted as shared chart infrastructure; accepts rendering/anchor policies from each layer. |
| `frontend/src/chart/ChartObjectBridge.js` | Separate drawing collection and RiskRewardController; retain object ordering and combined snapshots for existing toolbar, JSON and undo/redo. |
| `frontend/src/chart/LegacyObjectPersistence.js` | Safe v2 compatibility loading/saving, original JSON backup, retention of unsupported records and protection against invalid JSON/stale namespace writes. |
| `frontend/src/trading/RiskRewardController.js` | Trading-owned collection, registry, creation, resizing constraints and normalization. No drawing runtime dependency. |
| `frontend/src/trading/riskReward.js` | Existing sizing/P&L math and order seed conversion moved to trading. |
| `frontend/src/trading/RiskRewardGeometry.jsx` | Existing position boxes, labels and statistics extracted without redesign. |
| `frontend/src/trading/RiskRewardSettings.jsx` | Existing trading-specific settings extracted without redesign. |
| `frontend/src/trading/RiskRewardLayer.jsx` | Dedicated trading overlay and handle projection; respects chart tool input modes. |
| `frontend/src/trading/TradingLevels.jsx` | Existing order/position interaction component moved unchanged. |
| `frontend/src/trading/TradingLayer.jsx` | Composes Risk/Reward and active order/position interactions independently of DrawingsLayer. |
| `frontend/src/trading/chartAnnotations.js` | Existing native markers and price-line synchronization moved to trading. |
| `frontend/tests/trading-separation.test.mjs` | Regression coverage for ownership, sizing/order seeds, anchor constraints, replay settlement, native annotations and lossless persistence. |
| `frontend/package.json` | Added `test:trading-separation` script only. |
| `docs/TRADING_LAYER_SEPARATION_PREVIEW.jpg` | Browser verification image from isolated local test session. |

## Dependencies discovered

- React `^19.2.8`, Vite `^8.3.0`, Lightweight Charts `^5.2.1`.
- Community `lightweight-charts-drawing ^0.2.5` remains installed; its NativeDrawings adapter remains unused by the active chart. Removing it is deferred to phase 4.
- No dependencies were installed, removed or upgraded. `package-lock.json` is unchanged.
- No proprietary TradingView source or new third-party code was copied.

## Risk/Reward separation

Trading owns its controller, object collection, creation/resize constraints, calculation, settings, renderer, order seed and native trade annotations. The drawing layer receives only non-trading objects. Trading modules do not import a drawing engine.

The chart still coordinates toolbar commands, shared history and selection for backward compatibility. Shared pointer/projection infrastructure is intentionally chart-owned. It is not a DrawingManager. Risk/Reward state is not owned by a drawing renderer and cannot be cleared by unmounting the drawing layer. The upcoming DrawingManager must use only the drawing collection; explicit existing global toolbar commands retain their previous behavior on planning objects.

Risk/Reward planning objects remain separate from executed simulator positions. Deleting or editing a planning object does not close or amend an executed position. Native order handles still amend the simulator independently. At overlapping levels, order handles retain their existing higher interaction priority.

## Order system status

`simulator.js`, `useTrading.js`, `OrderTicket.jsx`, market/replay hooks and backend engines were not modified. Existing Buy/Sell, Market/Limit/Stop, Entry/SL/TP, sizing, paper positions, cancellations and trade settlement remain in place. Native annotations still use `createSeriesMarkers` and `createPriceLine`.

## Drawing data status

- Existing v2 key and array schema retained, including unknown object fields.
- Original valid array JSON is copied once to `<key>:before-trading-separation` before the first write. Existing backups are not overwritten.
- Unsupported/malformed object records are not rendered, but are retained when saving accepted records. The original exact JSON remains in the backup.
- Invalid JSON/non-array values are not overwritten. Storage failures disable persistence for that load rather than deleting data.
- Original keys and legacy source archives are retained. No timeframe-independent namespace migration has happened; that belongs to a later phase.
- Switching timeframe preserves the previous behavior: objects belong to the existing timeframe namespace and reappear when returning to it. This phase does not claim cross-timeframe object visibility.

## Verification

| Check | Result |
| --- | --- |
| Build | PASS, Vite production build. |
| Lint | PASS, no errors/warnings. |
| `test:trading-separation` | PASS: independent ownership, both directions, creation/SL/TP/entry/end resizing, unchanged sizing, order seeds, replay TP exits, native annotations, shared snapshot compatibility, unknown/invalid data preservation and storage denial. |
| `test:trading` | PASS: Buy/Sell, market/limit/stop, SL/TP, gaps, conservative OHLC settlement, partial closes, live ticks and duplicate-candle protection. |
| `test:drawings` | PASS: existing geometry/math for 88 tools and irregular/coincident anchors. |
| `test:market` | PASS: aggregation/provider seam, all chunks and 11 timeframes; 3,486,461 M1 candles validated. |
| Browser | PASS for the scenarios below; captured console errors: none. |

Browser testing used `http://localhost:5173/`, a separate storage origin from the user's main `http://127.0.0.1:5173/` preview. Paper orders and planning objects created during testing were confined to that test origin. Temporary viewport override was reset.

Verified in the browser:

- Chart/candlesticks, native crosshair and price/time labels; volume remains unavailable for this dataset, with no invented values.
- Long and Short Position creation; correct separation of DOM objects between drawing and trading overlays.
- Short Risk/Reward settings changed to 3:1; undo restored the original anchors and redo reapplied the change.
- Create order opened the existing popup with corresponding Entry, SL, TP, side and quantity.
- A Buy Stop order submitted from Risk/Reward entered the simulator; its native SL handle amended the order; cancellation worked.
- A Buy market position stayed open after replay advanced from 12:00 to 12:30 UTC on 2024-06-03; unrealized P&L updated.
- Risk/Reward SL and TP handles changed their prices without changing their timestamps; Entry drag retained both risk/reward price distances; lock prevented drag.
- Legacy Trend Line could be placed across a Risk/Reward object; deleting that line left Risk/Reward intact.
- Zoom, pan and responsive resize retained canonical anchors.
- Pan into April 2024 loaded history preceding the initially displayed May data while the replay quote and open position remained unchanged.
- Timeframe 30m → 1h → 30m retained the open simulator position and restored exactly the original planning anchors on returning to 30m.
- Reload restored Risk/Reward anchors and the persisted open position.
- Chart export produced an image containing the trading planning overlay after splitting the SVG layers.

## Regressions / blockers

No regression was found in the automated suites or browser scenarios above. No blocker for completing phases 1–3. These checks are representative regression coverage, not a claim that every possible trading scenario was manually exercised.

## Next recommended phase

Phase 4: retire only the old non-trading drawing runtime, preserving its original data and migration references. Keep the trading controller/layer and the compatibility boundary. Do not start phase 4 automatically as part of this task.

DrawingManager, new primitives, indicators, namespace migration and replay performance optimization are explicitly deferred. This session stops after phases 1–3.
