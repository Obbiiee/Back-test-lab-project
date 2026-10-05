# Phase 14 — Trading UX and Backtest Analysis

## Authorization and baseline

Human authorized only the MUST scope from the Phase 14 planning report. Initial branch main, local HEAD, fetched origin/main and actual GitHub main were exactly 8d9b1eb438714ded4f9daa6232742ef129278f32; working tree clean and ahead/behind 0/0. The plan was supplied in chat and reviewed with the implementation authorization; no second roadmap, workflow or context system was created.

## Implemented behavior

The existing bottom terminal has one Analysis tab, retaining its splitter, layout and main chart lifecycle. Read-only backtestAnalysis projects the canonical simulator account; no second account, execution engine, analytics persistence or hidden candle input. It groups exit records by positionId, preserves exit-record order and exposes completed/open-partial/incomplete groups. A partial 50% close plus the remaining close is two exits and one completed position. Journal explicitly labels its records/calendar counts as exits.

Summary includes completed positions, winners/losers/break-even, all-exit realized P&L, completed-position win rate, average win/loss, expectancy and profit factor. A small SVG displays realized USD balance against exit sequence, separate from the native price chart. Current and maximum balance drawdown/drawdown percentage are derived from those events, not historical floating equity. Position detail includes actual entry, every available exit, final completion, elapsed seconds, P&L, side, per-exit tags/strategy and the existing canonical note callback. Open/incomplete groups do not claim a final completed exit. Legacy/incomplete data stays visible and is not repaired or written back by the projection.

Two dependency-free CSV exports serialize raw exit records and completed groups. UTF-8 BOM, quoted fields, doubled quotes and CRLF records preserve numbers, UTC, Unicode, commas and multiline notes. Grouped tags/strategy/notes use JSON arrays with exit identities inside CSV fields so different partial notes are retained. Existing pnl is used, with no second commission deduction.

Both existing reset paths (new replay and exit replay) pass a shared guard before pause/start/stop/reset. Orders, positions or exit records request confirmation. Cancel invokes no replay/account action; Confirm invokes the original action. Confirmation traps keyboard focus, supports Escape and restores focus. Existing asynchronous replay-start failure behavior remains unchanged. It does not pause running playback merely by asking for confirmation; ongoing playback/live updates can continue naturally until Confirm. Cancel does not rewind natural progress.

## Exact analytics contracts

- A completed group needs a nonempty string positionId, no active position with that ID, finite canonical P&L and consistent valid original fields, and positive exited sizes totaling initialSize within max(1e-9, initialSize * 1e-9). Missing/duplicate exit identity, invalid price/time/size, negative duration, inconsistent original fields or reversed exit timestamps produce issues and exclude ambiguous groups. Unknown active identity prevents completion claims. Open partial groups also reconcile exited plus remaining size.
- P_j is the sum of canonical exit pnl in a completed group. Winners: P_j > 1e-8 USD; losers: P_j < -1e-8; the rest are break-even. No intermediate currency rounding. Gross profit/loss use strictly positive/negative canonical group P&L, including tiny amounts classified break-even by the tolerance.
- Realized P&L = sum of every exit pnl, including partial profits of open positions. Win rate = 100 * winners / completed count, with BE in denominator. Average win = gross profit / winners; average loss = absolute gross loss / losers; unavailable without that denominator. Expectancy = sum completed-group P&L / completed count, USD per completed position.
- Profit factor = gross profit / absolute gross loss. No loss with positive profit displays infinity; both zero displays a dash. Empty win rate/expectancy/averages display a dash, not fabricated percentages.
- B_0 = initialBalance; B_k = B_0 + cumulative exit pnl in original append order. Equal timestamps retain simulator record order. Peak includes B_0; drawdown = peak - B_k; percentage = 100 * drawdown / peak only for a positive peak. Maximum amount and maximum percentage are independently taken across events. Duration = last recorded exit time - actual entry time, UTC seconds; completed duration is only presented as completed for complete groups.
- Reconciliation difference = balance - initialBalance - realized P&L. Floating accumulation tolerance is max(1e-8 USD, Number.EPSILON * max(1, abs(balance), abs(initialBalance), abs(realizedP&L)) * max(1, exitCount) * 8). This allows accumulated floating arithmetic noise without modifying any canonical amount. Mismatch is surfaced.
- Invalid/non-finite P&L makes realized totals and the subsequent curve unavailable. Initial balance failures, grouping ambiguity and reconciliation failures are reported; canonical records are retained. No initial SL/risk, session identity, symbol or timeframe metadata is invented.

## Browser evidence

Actual browser used isolated origin http://127.0.0.1:5191, leaving the user's other origins untouched. Fixture imports real CandleChart, replay/playback/useTrading, RiskReward, OrderTicket, PositionsPanel, Journal and confirmation component; counters and download observation remain test-only.

- Empty account displayed zero counts, unavailable win rate/expectancy/PF and initial balance without NaN.
- Actual Long Position chart click -> Create order seeded Buy Limit at 2330.8795880612656, SL2322.799378281107, TP2338.9597978414245, size0.42902. Next replay step filled it; close50% recorded +7.044764497792939 while completed count remained zero. Close remainder produced two exits, one winner, total +14.089528995585878 and duration1620 seconds. UI profit factor displayed infinity (JSON snapshots serialize Infinity to null).
- Editing the first exit note to Unicode, a comma, quotes and a newline retained identical financial metrics and restored after full reload. Terminal remount reconstructed identical analysis. Chart instance counter remained2 (initial StrictMode setup/cleanup), scheduler counter1, across terminal/tab mount changes. Two cursor requests and timeframe/pan/prepend left summary unchanged; projection counter stayed4 before/after cursor-only changes. No price-chart or scheduler recreation from Analysis.
- Both CSV buttons generated real Blob/download-anchor requests with expected filenames. Fixture observed actual Blob contents: raw714 characters and grouped884 characters at that checkpoint; raw multiline Unicode preserved and grouped notes preserved in JSON fields. Browser download-event retrieval timed out; filesystem delivery was not observable through that API. Payload and DOM download dispatch were independently verified; automated Blob/anchor/revocation and CSV parser roundtrips passed. This is not a claim that a saved desktop file was inspected.
- Short Position -> Create order seeded Sell Limit. Cancel pending left zero exit records/completed positions. Market Sell then next/full close produced -7.30, one loser, zero-percent win rate and7.30 realized max drawdown.
- Both start and exit Cancel preserved exact fixture account/revision/active/raw endpoint. Confirm exit restored100000 with empty orders/positions/trades and inactive replay. Confirm start cleared the former history and began a new replay.
- Reloading a legacy fixture with no positionId/initialSize displayed two explicit issues, the original exit/note,12 realized P&L and zero completed positions. No fabricated original size or grouping.
- Production workspace independently placed Market Buy1 at2331.135, advanced to2329.868, closed50% then the remainder: two exits/one loser,-126.70, balance99873.30, max drawdown126.70. Existing six-dot splitter expanded the terminal and resized the existing price chart. Actual start Cancel preserved history; Confirm start reset it; actual exit Confirm with an open position cleared it using the existing reset path.
- Final memo/export integration was rechecked on a separate localhost:5191 origin with all seven indicators active: cursor advanced, projection count2 stayed2, chart count2 stayed2 and scheduler count1 stayed1. Market Buy/next/close produced one reconciled completed position and the raw CSV download dispatch still worked after memoization.
- Final warn/error console entries: zero in fixture and production after corrected development errors/reloads. Ignored screenshot: frontend/tests/artifacts/phase14-ui.jpg. Temporary viewport override is cleared at task completion.

## Performance

Recorded Phase13 reference:5000 revealed candles, seven indicators,100 steps; total8442.51ms, mean84.43ms, p95152.36ms. Re-running unchanged bench:phase13 during this task measured9248.04ms/92.48ms/178.28ms. Mock native API counts remained one full chart replacement plus100 updates and700 full indicator calculations.

First panel comparison while other development/browser work was active varied widely: closed means104.65/111.06ms, open90.04/164.30ms. The164.30ms outlier triggered investigation. Quiet repeat gave closed43.93/48.23ms and open52.02/52.49ms; measured dependency-check time was then added to distinguish calculation cost from overall timing variability. Final quiet alternating run:

| Panel | Total ms | Mean ms | p95 ms | Initial projection ms | Dependency checks over100 steps ms | Projection calculations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Closed |4900.92|49.01|73.20|0.04|1.671|0|
| Open |4792.58|47.93|63.52|12.41|1.924|1|
| Open |4621.55|46.22|61.79|5.93|2.305|1|
| Closed |4921.02|49.21|63.51|0|1.549|0|

Open-panel benchmark has500 completed exits. Projection runs once at mount; stable trade/position/balance inputs cause no recalculation over100 cursor-only steps. Analysis receives stable trades/projection/note-callback props and is React.memo-wrapped, avoiding its SVG/list render when only the cursor changes. The parent also avoids copying/reversing exit history in the Analysis branch. Actual React fixture counts separately confirm that behavior (StrictMode deliberately doubles initial calculation). Timing varies with host load/JIT/GC; no consistent material open-panel regression was observed in quiet repeats. No comparative speedup, FPS or guaranteed20× throughput claim. This benchmark models panel memo dependencies and CPU calculations with mock chart APIs; it does not measure React/SVG/browser rendering or claim huge-history rendering is constant time.

## Validation and protected boundaries

Phase4–14, trading separation, trading, drawings, market, repository and AI bundle suites passed; production build/lint passed. Market suite validates all3486461 M1 candles/eleven timeframes. Phase13 retains581 incremental and nine full reference transitions and exact chart/Volume/seven-indicator/account equality, hidden future OHLC/Volume mutation tests and scheduler controls. Phase14 adds financial vectors, partial grouping, completeness/legacy errors, duplicate IDs, tolerance, finite-data failures, note invariance, JSON reconstruction, cursor/hidden-input independence, real simulator integration, reset guards, actual CSV parser roundtrip and Blob download lifecycle. No old test assertion was weakened.

Protected integration changes: FigmaWorkspace wraps its two reset handlers without changing their actions; PositionsPanel adds a derived Analysis branch; Journal labels existing exit records accurately. Simulator/useTrading, scheduler/replaySettlement, incremental/full fallback, market/history/dataset, indicator calculators/adapter/panes, Volume, CandleChart, drawing/history/persistence, RiskReward/annotations and backend are unchanged. Existing account/drawing storage schemas, dependencies and lockfile are unchanged.

## File inventory and context ownership

Created10 files:
- frontend/src/trading/backtestAnalysis.js
- frontend/src/trading/BacktestAnalysis.jsx
- frontend/src/trading/backtestExport.js
- frontend/src/trading/replayResetGuard.js
- frontend/src/trading/ReplayResetConfirmation.jsx
- frontend/tests/phase14.test.mjs
- frontend/tests/phase14-benchmark.mjs
- frontend/tests/phase14-browser.jsx
- frontend/tests/phase14.html
- docs/PHASE14_TRADING_UX_BACKTEST_ANALYSIS.md

Modified13 files: frontend/src/FigmaWorkspace.jsx, frontend/src/FxWorkspace.css, frontend/src/trading/PositionsPanel.jsx, frontend/src/trading/Journal.jsx, frontend/package.json, frontend/scripts/ai-bundle.config.json; existing AI_CONTEXT state/architecture/history/current-phase/protected/test-command owners and docs/ROADMAP.md. Deleted:none. No cleanup, new dependencies or competing authorities. This report owns checkpoint evidence only. Onboarding/workflow remain unchanged; volatile operational values remain solely in04_CURRENT_PHASE.

## Limits and checkpoint completion

No SHOULD/DEFER, R-multiple, initial-risk schema, historical floating equity, filters/streaks, session archive/metadata redesign, backend/cloud, execution-cost changes, economic news or Phase15 redesign. Existing storage error/recovery behavior remains unchanged. Large record collections are rendered as a local read-only list/SVG; virtualization and archival remain deferred. CSV exports data, not a restore/import mechanism. Natural playback can continue during a reset question; Cancel itself makes no state changes.

Normal commit/push, actual remote/local SHA equality, clean working tree and0/0 sync are completion gates verified in the final response after push. No self-referential final SHA is embedded in its own commit. Next prompt must request human scope definition/planning for Phase14.5, prohibit implementation before separate authorization, and STOP. No next phase is started.

### First supplied price — authorized simulation gap policy

The human explicitly authorized using the first available price after a jump for entry, TP and SL. The frontend simulator now shares one symmetric pricing rule for Buy/Sell Limit/Stop entry, SL, TP and partial TP. A known opening crossing precedes later unknown intrabar extremes; a pending order marketable at open also evaluates an immediate opening exit before the close. Example: existing Buy entry 1, TP 3, next open/observed tick 4 exits at 4, even if the subsequent candle reverses through SL. Gap entry and immediate exit use that same available price, not a fictitious threshold fill.

This is a MODELLED execution policy, not evidence of broker fills, historical tick completeness or liquidity. For OHLC, only the open is known first; hidden intrabar jumps cannot be inferred from high/low. Non-opening intrabar level touches and dual-touch SL-first modelling retain their previous simulation behavior. Backend precision ambiguity and null fill/PnL remain unchanged. No historical account rewrite, schema migration, provider/data changes, replay cutover or dependency change.

Acceptance extends existing trading tests across Buy/Sell, candle/tick gap TP/SL and Limit/Stop entries, opening TP versus later SL, partial exits, exact balance, repeat-bar refusal and four immediate pending opening exits. Existing Phase 14 browser harness adds an isolated Gap policy scenarios action: sixteen authored scenarios passed with no console warnings/errors. These authored scenarios are not market measurements. Full frontend regression, lint, production build and release audit PASS; repository/bundle tests and generation/verification PASS (135 files); backend full-suite rerun is exempt because backend code/contracts/consumers are unchanged. Normal push, actual GitHub equality and clean 0/0 are required before completion; STOP after this narrow task.
