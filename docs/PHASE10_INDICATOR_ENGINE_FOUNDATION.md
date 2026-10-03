# Phase 10 — Indicator Engine Foundation checkpoint

Evidence only. Existing AI_CONTEXT/04_CURRENT_PHASE.md owns status/authorization; 06_WORKFLOW_RULES.md owns workflow; docs/ROADMAP.md remains the sole roadmap.

Baseline: `e7448ea67106996a7ed0853d22af4d262772973b`, `main`, origin `https://github.com/Obbiiee/Back-test-lab-project.git`. Local and remote matched before implementation. The submitted human prompt authorizes exactly this foundation. Final commit/remote equality/clean status are reported after push, avoiding a self-referential hash in this commit.

## Architecture and scope

Chart-visible candles → IndicatorEngine → registered pure calculation → normalized TIME + VALUE output → IndicatorSeriesAdapter. Lightweight Charts 5.2.1/React/Vite remain unchanged; no dependencies added. Official [chart addSeries/removeSeries](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IChartApi) and [series setData/applyOptions](https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi) APIs were checked against installed typings and current 5.2 documentation.

- IndicatorRegistry: trusted specification registration/lookup, type/output/warmup validation and scalar parameter defaults/validators. Production registry is empty. No SMA/EMA/BB/VWAP/RSI/MACD/ATR/Stochastic or product menu.
- indicatorValidation: frozen canonical id/type/parameters/visible configs; rejects extra fields, malformed config, invalid values and unknown parameters. Candles are strictly chronological, copied/frozen, containing only public OHLC/time/optional volume fields. Output contains unique revealed timestamps, finite values and optional color; sorting is deterministic. Pixels and chart objects never enter configs.
- IndicatorEngine: create/update/replace/remove, duplicate protection, visible state, explicit warmup, read-only snapshots/output, full recomputation, per-instance error reporting. Invalid config/data updates fail before mutation. Calculator/adapter failures remove stale series, while good instances continue; later successful computation recovers an instance.
- IndicatorSeriesAdapter: official line/histogram attach/setData/visibility/remove/detach. Full replacement safely handles append, rewind, historical prepend and timeframe replacement. Attach is idempotent; chart replacement releases old series; detach/dispose are repeatable.
- CandleChart: optional mount-time registry plus reactive configs/error callback. Exactly the existing candlestick `candles` array is fed after candlestick setData. Config validation failure retains previous valid configuration; an optional callback reports it. Chart teardown detaches indicators before chart.remove; StrictMode cleanup/re-attach works. No chart recreation for config changes. Native Volume remains on its original path.

The replay audit confirmed useReplayMarket takes state.bars.slice(0,index+1), aggregates it, and workspace passes replay.candles into CandleChart. Indicator domain does not import market/replay/trading/drawings, global stores, storage, DOM or backend. Replay semantics were not modified. Tests also protect against reverse dependencies from the protected domains.

## Anti-look-ahead and validation

The deterministic test uses a visible prefix of three candles, changes the hidden future close, and proves prefix output is identical. Revealing additional candles produces only their now-visible timestamps; rewind removes future output. Calculators see frozen copies without extra future fields. Future timestamps, duplicate timestamps, non-finite output and mutation attempts fail safely. Test-only causal close-line preserves existing prefix values after append. Historical prepend and timeframe replacement recompute sorted output.

PASS: test:phase4–10, test:trading-separation, test:trading, test:drawings (88 archived geometries), test:market (3,486,461 M1 candles, eleven timeframes), test:repository, test:ai-bundle, build, lint, ai:bundle, ai:bundle:verify. Phase 4 assertions remain unchanged: its banned names/shortcuts target the retired runtime, and the new isolated API passes without weakening any assertion. Phase 10 separately checks no legacy renderer/movingAverage/indicator command resurrection.

Test coverage: spec/type/default/parameter/instance validation, duplicate IDs, frozen input/config/output, deterministic prefix, warmup, output normalization/future rejection, append/rewind/prepend/timeframe, multiple instances, visibility/config changes, atomic rejection, isolated calculation/mutation/adapter failure and recovery, remove/detach/reattach/chart replacement/dispose with no live mock series remaining; input immutability, domain isolation and native Volume integration.

## Executed browser verification

Isolated localhost port 5186; test harness uses actual CandleChart, actual useReplayMarket and official adapter under React StrictMode. Test-only TEST_LINE spec/instrumentation lives in frontend/tests/phase10-browser.jsx, never production imports/UI.

- Yellow reference close-line rendered. Replay moved 2,155 → 2,156 points, matching input count and latest visible timestamp. No future point. 15m → 1h recomputed 540 points; loading older history produced 1,045 ordered points with earlier first timestamp and unchanged latest timestamp. Repeated timeframe/replay and reload remained functional.
- Disable visually hid the line; Remove released the owned series (active count zero). Enable restored one. Unmount released series; remount restored exactly one under StrictMode.
- Resize to 980×800, zoom and pan worked; temporary viewport override reset. Drawing JSON stayed identical through viewport/timeframe/replay changes.
- All eight Phase 5–9 drawing types created alongside reference output, including actual Text form save. Reload restored all eight. Automated existing editing/history/lock/hide/storage regressions remain intact.
- Long and Short Risk/Reward created; Create order callback triggered. Existing full workspace opened its actual order ticket, placed a simulated Buy market order, advanced replay, and manually closed the position; closed-position table recorded its result. No live broker action.
- Existing native Volume rendered and toggled independently using explicitly labeled synthetic test volume values, because this historical OHLC dataset has no meaningful volume. No production/data-loader change or Volume migration.
- Fixture hot-reload initially produced a duplicate-createRoot warning; root retention was fixed. Fresh final fixture tab and full workspace tab have zero console errors. Final screenshot: ignored frontend/tests/artifacts/phase10-final.png. Test tabs are temporary; user storage/origins are untouched.

## Files, diff review and limits

Created: frontend/src/indicators/{IndicatorRegistry,indicatorValidation,IndicatorEngine,IndicatorSeriesAdapter}.js; frontend/tests/{phase10.test.mjs,phase10.html,phase10-browser.jsx}; this checkpoint report.

Modified: frontend/src/components/CandleChart.jsx (narrow config/data/lifecycle integration); frontend/package.json (test command); frontend/scripts/ai-bundle.config.json (reviewed implementation/test allowlist); existing AI_CONTEXT/01_PROJECT_STATE, 02_ARCHITECTURE, 03_PHASE_HISTORY, 04_CURRENT_PHASE, 05_PROTECTED_SYSTEMS, 07_TEST_COMMANDS; docs/ROADMAP.md. No deletions, dependency/lock changes or unrelated refactors. No source edits to market/replay/trading/drawing/native annotations/legacy persistence, backend, historical data or archives. Production graph: 49 reachable files plus two retained compatibility exports. Workflow/onboarding authorities are reused, with no duplicate owners.

Limits: full recomputation/setData favors correctness over incremental optimization; large catalogs/performance are unbenchmarked. Specs are trusted reviewed pure functions, not a sandbox: hostile JS closures could access globals, so each future calculator needs causal/purity tests. No user scripting. One output series per instance; multi-output/panes await separate scope. Registry chosen at mount; config can change dynamically. No indicator persistence/catalog/property UI/cloud. Browser testing is a smoke check, not exhaustive device QA. No known blocker after validation.

Prepared validated context checkpoint requires normal commit/push, remote HEAD equality and a clean synchronized working tree to complete the final gate. Phase 11 was not implemented; next work is scope definition/planning only, requiring human authorization before implementation.
