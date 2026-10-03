# Phase 13 — Replay optimization and playback controls

## Authorization and baseline

Human scope authorized Phase 13 only. Original verified local/GitHub baseline: `7ed7c4f83d84d506a1913b8be289ca6eba7f9829`. Work was paused before commit. On resume, actual GitHub main had advanced to `4a3fe98b04185bf06c1b156f508109c3e347c248`. Work stopped as instructed; the human explicitly authorized auditing/adopting that baseline. Its only change was docs/IDEA_BACKLOG.md. A normal fast-forward retained that document and all uncommitted Phase 13 work. This is the final parent checkpoint. No Phase 14 implementation, new dependency, dataset mutation, worker, backend or competing context authority.

## Transition contract and chart updates

useReplayMarket retains the exact reference cursor algorithm, revealed-prefix slicing, aggregation, chunk loading, saved date and end policy. The cursor calculation is extracted unchanged into advanceReplayIndex for independent differential testing. State increments a revision for start, stop, forward, rewind and prepend. Published optimization hint contains only kind/revision/timeframe, never candles or raw hidden data. Timeframe is also the chart viewport identity, forcing full replacement. Forward classification derives append versus latest-bucket replacement from the actual revealed arrays.

forwardChange validates the previous historical prefix by TIME/OHLC/Volume values, requires the same previous latest timestamp and strictly ordered finite new TIME/OHLC values. Only that latest bucket may change. An accepted change updates that bucket when needed and appends subsequent revealed buckets using official Lightweight Charts series.update. Installed 5.2.1 typings document that equal timestamp replaces the latest bar and newer timestamp appends. No historicalUpdate flag or removal API is used.

No hint, reset/start/stop, rewind, prepend, session/timeframe change, mismatched prefix or failed incremental call uses the safe full series.setData path. A failed partial update is recovered by replacing the complete authoritative revealed array. Remount clears the previous-array cache. Existing viewport following/prepend shift logic is retained. Volume still maps only the same revealed candles and fully calls its native histogram setData.

## Scheduler and trading

PlaybackScheduler has one cancellable timeout and an in-flight revision acknowledgement. The timeout requests one step, then waits for a different committed revision before scheduling again. A speed change without acknowledgement cannot queue another step. React effects configure it after committed chart/replay updates. Pause cancels synchronously; effect cleanup, session loading/end/exit and unmount invalidate timer generations. End clears the playing request. Remount starts paused. Speeds are exactly 1×/2×/5×/10×/20× through a small selector in the existing controls. Manual next from both controls pauses playback. CPU processing takes priority over requested nominal rate.

useTrading delegates replay settlement to a small pure replaySettlement helper. A proven raw forward append plus an account cursor at/after the previous prefix endpoint settles only newly revealed suffix candles. A changed latest bucket, account behind the previous prefix, reset/jump/prepend/rewind/ambiguous hint uses the original reference scan. The original lastTime checks still prevent prepended historical bars becoming new trading events. Live tick handling is unchanged. Previous remains disabled when orders, positions or closed trades exist; no trading time travel was added. simulator.js is byte-unchanged, including fill/SL-first/pending-entry/partial/P&L policies.

Prefix validation is still O(history); suffix settlement avoids the additional complete-history settlement loop, not all historical reads. No unsupported O(1) or simulator speedup claim.

## Indicators and anti-look-ahead

All seven calculators, engine and adapter remain unchanged. Frozen revealed-only input, normalization, timestamp validation, warmup, error isolation, full calculation/setData and official pane/reference lifecycle remain the reference path. No stateful incremental indicator calculator was introduced, so exact differential equality is required; no floating-point tolerance weakens comparisons.

test:phase13 runs 581 accepted incremental and nine full transitions across forward append/latest replacement, reset/restart/stop, safe rewind, history prepend, timeframe replacement and misleading hints. It compares chart candles/latest quote/Volume, every output of SMA/EMA/Bollinger/RSI/MACD/ATR/Stochastic and the entire account/balance/orders/positions/trades against full reference behavior. Deterministic UUIDs align equivalent simulator event identities solely inside the test. Market/Limit/Stop orders exercise fills and exits. Partial API failure recovery is tested. Cursor reference cases cover all eleven timeframes and end/bucket boundaries.

Hidden future OHLC/volume mutations preserve revealed input, chart data, indicator output, account/latest quote and cursor results. Metadata contains no market data. Scheduler fake-clock tests cover every speed, unacknowledged backpressure, speed changes, pause/resume, end, stale callbacks and remount/disposal. Existing Phase 10–12 causality tests remain intact.

## Performance evidence

Non-gating bench:phase13: 5000 initial revealed candles, seven default indicators and 100 forward steps. Measured total 8442.51 ms, mean 84.43 ms/step, p95 152.36 ms/step. Candle API counts: one full replacement plus 100 incremental updates versus 101 full replacements in the reference sequence. Indicator calculations: 700 full, zero incremental.

This measures CPU prefix validation/calculation with mock series operation counts, not browser rendering/FPS. No comparative wall-clock speedup claim. Aggregation, Volume and indicators remain full; 20× is a requested interval, not guaranteed throughput. Timing has no CI threshold.

## Actual browser verification

Isolated port5190. Test-only fixture uses actual CandleChart, useReplayMarket, useReplayPlayback, useTrading, production registry, controls and official series/pane APIs under StrictMode. Snapshot comparisons use semantic fields, accounting for native candle series excluding Volume and object property ordering. No fixture instrumentation enters production imports.

- With seven indicators active, all five speeds advanced and paused. Observed revision ranges: 38→39 at1×, 39→42 at2×, 42→51 at5×, 51→64 at10×, 64→78 at20×. Actual operation observation: 3 full replacements/78 candle updates at that snapshot. Candle/Volume/all seven indicator outputs exactly matched reference calculations on real data.
- Pause stayed at revision78 after1200 ms. Resume and 2×→10× changes while playing worked. Unmount at revealed bucket1717498800 retained that endpoint after1200 ms; remount started paused. Manual next and safe previous retained original bucket semantics and reference series equality.
- Start at2026-09-25T00:55Z reached raw dataset end, stopped playing and disabled advancement. Exit cleared active replay; restart at2024-06-03T12Z restored the selected revealed prefix. The last chart timestamp is its timeframe bucket, not the raw final minute.
- Pan/zoom, 15m↔1h and viewport980×800 worked. Historical prepend changed first bucket1714521600→1711933200 and count2155→4175; non-following viewport shifted exactly2020 logical bars, preserving the viewed times. Trading lastTime stayed unchanged. Candle/Volume/indicator reference comparisons passed.
- Native separator resized price304.8→260 and RSI53.6→98.4. RSI hide/show worked. Removing middle MACD released its three outputs and reindexed ATR/Stochastic; re-add restored one owned pane. Chart unmount released all indicator series; remount restored exactly12 outputs across four owned indicator panes, retaining price/Volume ownership.
- All eight drawings created via actual price-pane clicks: Trend Line, Horizontal/Vertical Lines, Rectangle, Fibonacci, Arrow, Text, Measure. Text form saved content; Measure displayed derived labels. Their canonical JSON and persisted bytes remained unchanged through pan/zoom/resize/prepend/timeframe and chart remount; all eight restored. Long/Short RiskReward objects rendered/selectable; Create order triggered the existing callback. Existing v1/v2 storage schemas unchanged.
- Synthetic Volume data existed only in fixture to visibly verify histogram/show/hide. Native production history Volume remains unchanged and is not meaningful; production data was not fabricated.
- Real fixture Simulator Buy/next/close produced entry2331.135, exit2331.208, size0.1, P&L+$0.73 and balance100000.73. Previous stayed disabled after the closed trade. Production workspace independently added all seven indicators, played20×/paused and restored eight drawings. Production order ticket Buy1 at2342.365 then Next to2342.675 showed+$31.00 and closed through the existing panel. No external financial transaction.
- Final captured warn/error console entries: zero in fixture and production. Temporary viewport override reset. Ignored captures: frontend/tests/artifacts/phase13-final.png and phase13-ui.png.

## Validation, boundaries and file inventory

Full Phase4–13, trading-separation, trading, drawings, market, repository and AI bundle tests passed; build/lint and bundle generation/hash verification passed. Market test validates all3486461 M1 bars and eleven timeframes. Repository graph:59 production files plus two retained compatibility exports. An initial legacy drawing test invoked from the repository root failed because its Vite SSR fixture requires frontend working directory; rerun through its authoritative npm command passed. No assertion was removed for that failure.

Phase10/12 source assertions previously mandated unconditional candlestick setData; these narrow assertions now require the authorized synchronization helper and preserved full replacement fallback. All indicator, Volume, pane and domain assertions remain. Complete source/new-file/context/config diff reviewed; changes confined to authorized replay/chart/useTrading integration, one selector style rule and supporting tests/docs. No simulator/calculator/adapter/drawing/RiskReward/native annotation/history dataset/backend/archive/dependency/lockfile changes.

Created (9):
- frontend/src/market/PlaybackScheduler.js
- frontend/src/market/replayTransitions.js
- frontend/src/market/useReplayPlayback.js
- frontend/src/trading/replaySettlement.js
- frontend/tests/phase13.test.mjs
- frontend/tests/phase13-benchmark.mjs
- frontend/tests/phase13-browser.jsx
- frontend/tests/phase13.html
- docs/PHASE13_REPLAY_OPTIMIZATION.md

Modified (16):
- frontend/src/FigmaWorkspace.jsx
- frontend/src/FxWorkspace.css
- frontend/src/components/CandleChart.jsx
- frontend/src/market/useReplayMarket.js
- frontend/src/trading/useTrading.js
- frontend/tests/phase10.test.mjs
- frontend/tests/phase12.test.mjs
- frontend/package.json
- frontend/scripts/ai-bundle.config.json
- AI_CONTEXT/01_PROJECT_STATE.md
- AI_CONTEXT/02_ARCHITECTURE.md
- AI_CONTEXT/03_PHASE_HISTORY.md
- AI_CONTEXT/04_CURRENT_PHASE.md
- AI_CONTEXT/05_PROTECTED_SYSTEMS.md
- AI_CONTEXT/07_TEST_COMMANDS.md
- docs/ROADMAP.md

Deleted:none. Existing state/architecture/history/status/protection/tests/roadmap owners extended; onboarding/workflow remain single unchanged authorities. One checkpoint evidence report, no competing roadmap/workflow/phase tracker. The new remotely-added idea backlog is preserved. Bundle allowlist includes the reviewed replay/trading source dependencies and Phase13 tests.

## Limits and checkpoint policy

Full aggregation/calculations/Volume and linear prefix validation still limit throughput. No workers/WASM/ticks/multisymbol/indicator persistence/pane persistence/Phase14. Current end policy remains the existing loaded-data policy; optimization does not redefine chunk/network semantics. Runtime indicator configurations and pane sizes are not persisted. Scheduler accepts only committed revisions, not a target FPS.

Normal commit/push and actual local/remote SHA equality, clean working tree and0/0 synchronization are verified and reported after push; no self-referential final commit hash inside its own report. The operational pointer owns the next-phase status. Final next prompt must request Phase14 planning/scope only, forbid implementation before separate authorization, and end STOP.
