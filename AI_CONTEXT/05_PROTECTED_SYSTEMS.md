# Protected boundaries

- Trading analysis: preserve canonical-account ownership, partial exit vs completed-position distinction, exact realized balance/metric contracts, finite-data issues, CSV fidelity and memoization independent of cursor-only changes. Both existing workspace reset actions must be guarded before any replay/account operation; Cancel itself performs none. Do not infer initial risk, session metadata or floating-equity history. Reference contracts: [Phase 14 checkpoint](../docs/PHASE14_TRADING_UX_BACKTEST_ANALYSIS.md).

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

- Indicator foundation: `frontend/src/indicators/`. Calculators receive only chart-visible candle copies, never raw future data or domain stores; preserve config validation, output timestamp validation, error isolation and owned-series cleanup. Legacy indicator runtime remains retired. Native Volume stays separate. Reference indicator is test-only; authorized production catalog is exactly SMA/EMA/Bollinger Bands/RSI/MACD/ATR/Stochastic. Preserve official dedicated pane ownership, reference lifecycle, and current-index derivation; additional products, indicator/pane persistence or layout engines require separate authorization.

- New drawing persistence/history: `DrawingPersistence.js`, `DrawingHistory.js`; `backtest-drawing-manager-v1:*`. Preserve schema, canonical fields, commit boundaries and trading isolation. History resets on reload; no cross-tab merge/backend sync.

- Source-of-truth hygiene: `frontend/src/main.jsx` is the single entrypoint. Preserve intentional compatibility exports and test-dependent archives/storage fixtures. Do not reintroduce duplicate runtime trees or remove files based only on absence from the production graph. `test:repository` checks these boundaries; update its allowlist only with documented evidence.

- Replay optimization: transition metadata is a hint, never a market-data source. Preserve actual revealed-prefix validation, full chart/reference trading fallbacks, completion-acknowledged single-flight scheduling and cancellation. Keep existing rewind restrictions for trading state; historical prepend must not become new trading events. Indicator calculators, native Volume and pane ownership remain independent.

- Local Tick Review: preserve exact artifact/report versions, hash consistency disclosures, loopback opt-in/default-entry behavior, quote reveal/bounds and cancellation. Viewer remains read-only and memory-only; never connect its supplied reports to account settlement or treat reviewed references/hash consistency as provider certification. Existing system blueprint Section 42.11 owns the boundary.


- Local historical delivery: backend/market_data preserves immutable raw-byte version identity, exact decimals, corruption refusal, explicit pagination, UNKNOWN/AMBIGUOUS and null financial outputs. Local transport cannot serve externally; caller research filter is not a trusted Session bound. Future cloud adapters require identity/membership and scoped data rights. Do not mount PersonalLocalPolicy publicly or connect to account settlement by implication.


- Tick-native target: MARKET_DATA_STANDARD owns the no-OHLC-settlement migration invariant. Current candle compatibility code/results must not be relabelled as compliant, removed or silently migrated. Section 42.14 authorizes audit only; keep Quote/Request/Passport/golden wire contracts unchanged until separately authorized versioning. Raw provider data stays private; no certainty promotion or candle fallback in the future tick authority.

- Frozen tick boundary: existing blueprint 42.15 is the single V1 contract owner; its synthetic examples are not market evidence. Preserve legacy evidence/viewer/Passport/account wire contracts, explicit UNKNOWN states, raw-ordinal versus trusted-order distinction and revealed-only capabilities. No OHLC fallback or production migration is authorized by a contract-freeze checkpoint.

- Tick infrastructure: backend/ticks implements frozen 42.15 under 42.16 evidence. Preserve source/hash identity, strict exact prices/ns, atomic tie groups, UNKNOWN evidence, controller-only advance and revealed-only consumer capability. Never import candle/trading/account engines into it or treat synthetic chronology as fills/provider certification. Production cutover, execution, settlement and real adapters need separate human authorization.
