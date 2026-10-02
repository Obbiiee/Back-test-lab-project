# Boundaries

Market data loaders → replay/live candle aggregation → CandleChart (native Lightweight Charts). Replay reveals market data; it does not own drawings.

Independent domains:
- Trading: simulator/useTrading, RiskReward controller/layer, native chart annotations. Owns orders, positions and entry/SL/TP.
- Drawing: canonical model → DrawingManager/Registry → creation/interaction controllers → official Series Primitive views/renderers. React hook connects lifecycle and low-frequency state to chart.
- Indicators: custom runtime retired, no new engine.

Canonical geometry is TIME + PRICE. Pixels are transient projection/interaction data. Selection, hover and drag are runtime state, never canonical serialized fields. Missing exact timestamps use deterministic interpolation/extrapolation between actual chart coordinates; body drag applies equal calendar-time and price deltas. Trading and Drawing stay separate. Persistence must not silently mutate geometry. `chart/LegacyObjectPersistence.js` protects old mixed records/backups while the trading compatibility bridge owns Risk/Reward objects.
