# Phase 11 — Overlay Indicators checkpoint

## Scope and baseline

Authorized Phase 11 only. Baseline local main and origin/main both verified as `f465ab5c655ae81503d6a9562c1f0486821b67f9` before source edits. Exactly SMA, EMA and Bollinger Bands added to the existing Phase 10 engine and production workspace. No dependency added or lockfile changed. Phase 12 was not started.

## Contracts and ownership

- SMA: close mean of the last N revealed candles, inclusive of the current candle. Default 20; integer 1–1000. First output at index N−1, none before it; N=1 is exactly close.
- EMA: default 20; integer 1–1000. First output is the SMA of the first N revealed closes. Subsequent EMA = alpha × current close + (1−alpha) × previous EMA, alpha = 2/(N+1). No first-close seed.
- Bollinger: default period 20, multiplier 2; integer period 2–1000 and finite multiplier >0 and <=20. Basis is inclusive SMA; deviation = sqrt(sum((close−basis)^2)/N), population denominator N. Upper/lower = basis +/- multiplier × deviation.
- All calculators are pure, deterministic and consume frozen chart-visible candle copies. They emit TIME + VALUE only; output timestamps must belong to the input. No future/raw replay dataset, market/drawing/trading imports, mutation, storage or network APIs.
- Registry preserves the legacy single-output contract while adding a named outputs specification. Bollinger declares exactly basis, upper and lower, all official Lightweight Charts LineSeries. Adapter ownership is a nested instance-ID/output-key map, avoiding concatenated-key collisions. Entire output validates before sync. Creation/update failure removes every owned output for that instance; hide/show/remove/detach apply to all three lines.
- CandleChart's Phase 10 integration is unchanged. FigmaWorkspace supplies the production registry and runtime-only configurations. IndicatorControls supports defaults, multiple instances, staged parameter editing with Apply, rejected invalid values, hide/show and remove. Native Volume stays on its existing path.

## Automated evidence

Full required suite passed: Phase 4–11, trading-separation, trading, drawings, market, repository and AI bundle tests. Production build, lint, bundle generation and hash verification passed. Phase 4 source was unchanged. Phase 10's product-catalog exclusion alone was updated to permit the newly authorized SMA/EMA; exclusions for retired reference and unauthorized products remain.

Known closes [1,2,3,10,4], period 3: SMA [2,5,17/3]; EMA [2,6,5], proving the first EMA is SMA(1,2,3)=2. Bollinger deviations sqrt(2/3), sqrt(38/3), sqrt(86/9). Closes [1,3], period 2 and multiplier 2 yield basis 2, upper 4 and lower 0, proving population deviation. Tests cover bounds/defaults, warmup, immutable input, deterministic recomputation, prefix-only/future-modification equality, invalid/future output, multiple-instance independence, atomic multi-output cleanup, injected adapter failure/recovery and repeated lifecycle replacement.

Non-gating mock-series stress: 12 instances / 20 outputs / 5,000 candles, creation plus recomputation approximately 167–237 ms on this host. This is not an FPS or million-candle benchmark.

## Browser evidence

Real browser used isolated local origin port 5187. Test-only fixture uses actual CandleChart, useReplayMarket, production registry/UI and official series; instrumentation observes actual addSeries/removeSeries/setData/applyOptions. Fixture is unreachable from production main.

- Default SMA/EMA/Bollinger rendered together. SMA edited to 5, Bollinger to period 10 / multiplier 3; multiplier 0 rejected while valid config retained. Hide/show affected all three Bollinger lines; removal released all three.
- Four instances (SMA5, EMA20, Bollinger20/2, SMA20) owned exactly six actual series. Different SMA periods visibly differed.
- Replay next advanced last time from 1717416000 to 1717416900. Rewind across the candle bucket removed future output; every line returned to the revealed endpoint. Existing backward-step bucket semantics preserved.
- Timeframe 15m/1h recomputed; history prepend moved first input to 1711933200 without exposing future candles. Unmount released all six series; StrictMode remount restored exactly six.
- All eight drawing types created and serialized: Trend Line, Horizontal Line, Vertical Line, Rectangle, Fibonacci, Arrow, Text and Measure. Rendered alongside indicators during zoom, pan, resize to 980×800 and timeframe changes, retaining TIME + PRICE anchors. Two-point creation was checked with separate observed clicks after toolbar state settled.
- Long and Short RiskReward created/rendered. One test Short object removed through its existing selected toolbar. Long remained functional. Protected implementation unchanged.
- Native Volume show/hide rendered alongside overlays. Actual dataset has no meaningful volume; histogram rendering used explicitly synthetic fixture-only values, not invented production data.
- Production root UI opened and added all three indicators. Simulator Buy market order opened a position; Next candle updated P&L; Close position removed it. Native trading annotation was visible. No real trading service or money involved.
- Browser console at completion: zero captured warnings/errors in both fixture and production tabs. Screenshots: ignored `frontend/tests/artifacts/phase11-final.png` and `phase11-ui.png`.

## File inventory and diff review

Created:
- frontend/src/indicators/overlayCalculations.js
- frontend/src/indicators/overlayRegistry.js
- frontend/src/components/IndicatorControls.jsx
- frontend/src/components/IndicatorControls.css
- frontend/tests/phase11.test.mjs
- frontend/tests/phase11-browser.jsx
- frontend/tests/phase11.html
- docs/PHASE11_OVERLAY_INDICATORS.md (checkpoint evidence, not a new authority)

Modified:
- frontend/src/indicators/IndicatorRegistry.js
- frontend/src/indicators/indicatorValidation.js
- frontend/src/indicators/IndicatorEngine.js
- frontend/src/indicators/IndicatorSeriesAdapter.js
- frontend/src/FigmaWorkspace.jsx (indicator imports/state/control/chart props only)
- frontend/tests/phase10.test.mjs (authorized catalog exclusion only)
- frontend/package.json (Phase 11 command only)
- frontend/scripts/ai-bundle.config.json (authoritative implementation/test inclusion)
- AI_CONTEXT/01_PROJECT_STATE.md
- AI_CONTEXT/02_ARCHITECTURE.md
- AI_CONTEXT/03_PHASE_HISTORY.md
- AI_CONTEXT/04_CURRENT_PHASE.md
- AI_CONTEXT/05_PROTECTED_SYSTEMS.md
- AI_CONTEXT/07_TEST_COMMANDS.md
- docs/ROADMAP.md

Deleted: none. No edits to market/replay implementation, trading/simulator/RiskReward/native annotations, drawing models/controllers/primitives/persistence/history, legacy storage, archives, datasets, backend or lockfile. Source graph is 53 reachable files plus two intentional compatibility exports. Existing authority owners extended; START_HERE/workflow remain the sole existing authorities. Current phase points to completed 11 and awaiting human authorization for 12; roadmap remains docs/ROADMAP.md. Historical Phase 10 reports remain factual and unchanged.

## Limits and checkpoint procedure

Indicators remain runtime-only; reload clears configurations. No panes, VWAP, RSI, MACD, ATR, Stochastic, scripts, alerts, signals or automation. Full recomputation/setData remains the existing synchronization policy. SMA/EMA are linear; Bollinger uses a centered per-window variance calculation O(candles × period), favoring numerical clarity over streaming optimization. Seed depends on the loaded revealed prefix and can change when older history is prepended. This is expected and tested. No claim of exact vendor EMA parity or arbitrary custom-script isolation.

Commit and normal push to origin/main follow final tests and full diff review. Final local/remote SHA and clean/synchronized verification are reported in the final response rather than embedding a self-referential commit hash in this file. STOP after this checkpoint; Phase 12 requires a separately authorized scope.
