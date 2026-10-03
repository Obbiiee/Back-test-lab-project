# Boundaries

Market data loaders → replay/live candle aggregation → CandleChart (native Lightweight Charts). Replay reveals market data; it does not own drawings.

Independent domains:
- Trading: simulator/useTrading, RiskReward controller/layer, native chart annotations. Owns orders, positions and entry/SL/TP.
- Drawing: canonical model → DrawingManager/Registry → creation/interaction controllers → official Series Primitive views/renderers. React hook connects lifecycle and low-frequency state to chart.
- Indicators: custom runtime retired, no new engine.

Canonical geometry is TIME + PRICE. Pixels are transient projection/interaction data. Selection, hover and drag are runtime state, never canonical serialized fields. Missing exact timestamps use deterministic interpolation/extrapolation between actual chart coordinates; body drag applies equal calendar-time and price deltas. Trading and Drawing stay separate. Persistence must not silently mutate geometry. `chart/LegacyObjectPersistence.js` protects old mixed records/backups while the trading compatibility bridge owns Risk/Reward objects.

DrawingManager committed snapshots → DrawingHistory (100 runtime actions) and DrawingPersistence → version-1 localStorage. Current single XAUUSD workspace uses `main:XAUUSD`, shared across timeframes and live/historical/replay modes; cursor and timeframe never partition storage. Restore validates through registry/models and rebuilds primitives. Pointer movement previews only; release commits once. Unsupported storage stays read-only, preserving original bytes. Lock blocks geometry but allows selection/deletion; hidden objects neither render nor hit-test.

Directory ownership: `frontend/src/` is the sole active implementation (45 reachable files plus two intentional compatibility exports). `frontend/tests/` owns regressions and browser harnesses; `frontend/scripts/` owns infrastructure/data downloads. `frontend/legacy/phase3/` supplies historical geometry fixtures; root `legacy/` supplies historical snapshots. Standalone `backend/` and sample `data/` are not part of the workspace runtime. `docs/` preserves checkpoint reports/fixtures; new disposable evidence belongs in ignored `docs/_generated/` or `frontend/tests/artifacts/`. AI_BUNDLE is generated and ignored.

Core tools extend the same registry, creation controller and official series primitive. Horizontal/Vertical Lines store one TIME + PRICE anchor and drag only their price/time axis respectively. Rectangle stores exactly two anchors; four corners are derived for rendering/hit-testing/resize. A shared projectGeometry function keeps rendering and hit-testing aligned; no annotation supplies autoscaleInfo. The v1 persistence adapter and history/manager need no schema changes.

Advanced tools use the same immutable model factory, creation workflow, renderer and hit-testing. Fib stores only A/B; levels are derived (0 at B, 1 at A). Arrowhead is transient. Measure derives signed price/percentage/elapsed seconds and fractional bar distance using existing timestamp-to-logical interpolation; bar distance varies with the chart timeframe. Text adds only a validated text field to its v1 record and a transient React editor; DrawingManager.setText respects locks and commits once. No trading APIs are used by these tools.
