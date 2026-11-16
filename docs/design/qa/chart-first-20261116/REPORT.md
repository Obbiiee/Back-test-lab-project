# RIKSORA Product V1 — chart-first terminal (2026-11-16)

Branch `claude/chart-first-terminal-20261116`, from `origin/main` `4fc9939` (frontend only:
`frontend/src/tickAlpha/`, `CandleChart.jsx` two small props/commands, tests, this folder).
No backend, financial reducer, contract, dataset or evidence change.

## Evidence limits (read first)

* No PostgreSQL / backend service exists on this machine, so **browser QA ran against a
  deterministic SYNTHETIC harness** (`frontend/tests/qa/mock-tick-alpha-server.mjs`) that
  reproduces the tick-alpha HTTP contract and the real timeline's *bounded advance*
  (64 groups per ADVANCE, `pendingTargetNs` must be resumed with the same target). It is a UI
  harness, **not a trading engine**: fills/PnL in it prove nothing about backend correctness.
  Backend/PostgreSQL gates were **NOT RUN**.
* Not exercised at all (**NOT VERIFIED**): Google/account login, Logout→Login→Resume through the
  account transport, historical (Exness) source mode, real Protocol enforcement by the server
  (only the UI side was observed), Jump against real session durability.
* Real-device touch, Safari/Firefox: NOT VERIFIED. Browser pane = Chromium.

## Feature matrix (audit at `4fc9939` → now)

| Capability | Before | Now |
|---|---|---|
| Play / Pause | IMPLEMENTED | IMPLEMENTED (rewritten; one request in flight, 500 ms cadence, no timer leak) |
| Step Tick | IMPLEMENTED | IMPLEMENTED (one replay interval; Shift+→) |
| Replay speed | PARTIAL (labels "1/4/16 intervals / step" = batch, misleading) | IMPLEMENTED 1×,2×,5×,10×,20× = market seconds revealed per real second; batch per request is derived (rate × 0.5 s), documented in the control's tooltip |
| Next Candle | MISSING | IMPLEMENTED: backend ADVANCE to the UTC bucket end (last ns of the active-timeframe bucket) for 1m…D; gaps/weekends need no special case (calendar target); resumed with the *same* target until reached |
| Previous Candle | MISSING | **BLOCKED (by design)**: timeline is forward-only (`BACKWARD_ADVANCE`, `REFUSED_REWIND_REQUIRES_FORK`, `timeline_v2.py` advance_through/seek); no rewind button was added (no dummy) |
| Jump to Next Event | MISSING in this HEAD (no Jump code, no durable queue here) | PARTIAL: candle-by-candle ADVANCE until a pending/open order changes (fill/exit/cancel); stops at the *end of the candle containing the event* (cursor does not land on the exact tick); enabled only with a pending/open order; capped at 240 candles |
| Cancel Jump / Next Candle / Seek | MISSING | IMPLEMENTED: stops after the in-flight committed chunk; committed state is never rolled back |
| Continue saved replay | MISSING | IMPLEMENTED: unfinished target persisted per Session (`replayPending.js`, navigation hint only) and finished with the same target, also after reload |
| Go to Time | IMPLEMENTED | IMPLEMENTED (forward only, cancel, progress) |
| Timeframe switching | IMPLEMENTED (select) | IMPLEMENTED (quick M1/M5/M15/H1/H4/D1 buttons; select on phone); pauses play |
| Drawing tools / Long-Short planning | IMPLEMENTED | unchanged (thin left toolbar 40 px) |
| Indicators | IMPLEMENTED | unchanged |
| Fit / Latest / Follow | PARTIAL (Fit only) | IMPLEMENTED (`Latest` command, `Follow` toggle in `CandleChart`) |
| Method & Protocol Mode | IMPLEMENTED | unchanged; UI observed: Quick disabled, Plan forced, Market removed, TP/qty/risk derived (no inputs), checklist shown, Review mandatory |
| Planned & Quick execution, Review/Confirm | IMPLEMENTED | unchanged (observed in harness: Quick buy → review → confirm → fill marker) |
| Journal / Analytics | IMPLEMENTED | unchanged, still reachable (terminal tabs, rail, dialog) |
| Session resume | IMPLEMENTED | IMPLEMENTED + replay target resume |
| Terminal resize | IMPLEMENTED | default now **collapsed (24 px) for a Session with no saved preference**; saved heights respected |
| Pair search | MISSING | IMPLEMENTED in the Pair dialog (only XAUUSD selectable; others stay "Soon") |
| Focus / fullscreen | PARTIAL (phone "wide" only) | IMPLEMENTED: one click, Fullscreen API when allowed else CSS, Esc or the highlighted **Exit focus** button, desktop and phone |
| Provenance without eating space | PARTIAL | IMPLEMENTED: `i` popover in the toolbar replaces two disclosure rows |
| Mobile workspace | PARTIAL (page scrolled, replay hidden behind sticky bar at 390×844) | IMPLEMENTED: one-screen column, no horizontal overflow, safe-area padding, order sheet already a bottom sheet |

## Layout / CSS

`alphaChartFirst.css` is the single owner of Session-workspace geometry (viewport column; chart
= `flex:1` between fixed strips; heights from the real container, no plot px). Removed (not
overridden) from older files: chart host `height:460/420/360px` and `min-height:340/180px`,
`min-height:520px` workspace, absolute/floating replay pill and floating rail (`@media 1001px`
block), the `@media(min-width:761)` overflow block, `is-wide` height hacks, the Laptop theme's
10 px padding/gaps/radii/52 px tool width/64 px rail/pill replay (colours kept), phone
`clamp()` chart height and sticky order bar, plus 19 rules for classes that no longer render.
Remaining: dead *declarations* inside shared rules were left untouched where mixed with live
ones; phone/laptop themes still carry decorative styling (not geometry).

## Popup / dialog alignment (follow-up pass)

One language everywhere: dialogs = light card with blue lip (order, review, journal, news, source, pair, tools, **Indicators**, now restyled); small popovers = navy panel (info, Go to time, Session settings, drawing-group menus, **Objects panel**, drawing settings, floating drawing controls). Fixed: drawing-group menu items were squeezed to 34 px; Indicators dialog was legacy grey and narrow on phone (now full-width bottom sheet); Go to time popup was white on phone; popovers now exclusive and close on outside press or Escape. Checked programmatically at 1000×700 and 390×844: every dialog inside the viewport. Not re-shot at every size; screenshots in this folder predate this pass.

## Chart plot size (CSS px; plot = `.alpha-chart-host`)

| Viewport | Before | After (default) | After (Focus) |
|---|---|---|---|
| 1440×900 | 1291×345 = 90 % × 38 % | 1360×671 = 94 % × 75 % | 1360×787 = 94 % × 87 % |
| 1920×1080 | not measured | 1840×851 = 96 % × 79 % | — |
| 1366×768 | not measured | 1286×539 = 94 % × 70 % | — |
| 768×1024 | not measured | 688×771 = 90 % × 75 % | — |
| 390×844 | chart ≈ 260–560 px clamp, replay bar hidden under sticky order bar (screenshot) | 390×479 = 100 % × 57 % | — |
| 360×800 | not measured | 360×435 = 100 % × 54 % | 360×577 = 100 % × 72 % |
| 844×390 | not measured | 764×230 = 91 % × 59 % (terminal collapsed) | — |

No horizontal overflow and no page scroll at any of the seven sizes (`scrollWidth == innerWidth`).
Screenshots: this folder (`baseline-1440x900.jpg` is low-res; `after-390x844-v1.jpg` predates
two phone fixes; `after-844x390…` shows the expanded-terminal overlay sheet).

## Replay QA (harness; all PASS unless noted)

Play/Pause (5 requests in 3.2 s at 2×, 0 after pause), speeds listed, Step Tick (15 s), Next M1
(00:00:59.999…), Next H1 (≈34 resumed ADVANCE calls, 1.5 s), Next D1 across the closed weekend
(Fri→Sat→Mon, completes), Next M1 into a closed market (no ticks, target reached), cancel in the
middle of Next Event (cursor stays, Continue saved shown), Continue after **page reload**
(finishes the same target), Go to Time, rapid triple click = exactly one candle, double Play click
idempotent, end-of-dataset path coded (not reached in harness: **NOT VERIFIED**), timeframe change
pauses play.

**Finding (not fixed, backend contract):** a single ADVANCE reveals at most 64 timestamp groups,
so Next Candle on high timeframes is many sequential commands (D1 ≈ 540 calls in the harness).
Latency against the real backend is NOT VERIFIED; a larger per-call budget would be a backend
change and was not made.

## Tests

* `npm run lint` PASS; `vite build` PASS (146 modules).
* `npm run test:regression`: 30 registered tests, all PASS (incl. new `test:replay-controls`,
  `test:tick-alpha`, `test:repository` bundle allow-list, `test:phase16/18.6/18.8/18.9`,
  `test:stitch-analytics` using the existing backend venv via a junction).
* Backend Python/PostgreSQL suites: NOT RUN (no PostgreSQL here).

## Follow-up fixes (second audit)

Phone **Chart** button now collapses the terminal (it was a no-op); a click while another request runs now says so instead of doing nothing, and Play simply skips that tick; chart timeframe is remembered per Session across reload; `LOCAL_BUSY`/`RATE_LIMITED` are retried with bounded back-off (harness: 3 refusals then success) and a stale revision is reconciled by reloading the Session before continuing the same target.

Still open: needs the real backend — account-transport behaviour of hundreds of sequential commands, the 256-advance-target limit of non-indexed fixture Sessions at Play cadence, loss of the saved target if browser storage is cleared while the server holds a pending target (`ADVANCE_IN_PROGRESS`), a lighter view endpoint to avoid reloading chart+analysis per partial advance. No automated browser tests are committed (manual QA only).

## Polish pass (third)

Chart legend (latest revealed candle O/H/L/C + observed Bid/Ask and exact decimal spread, labelled as the execution basis), Session statistics chips (open P/L, trades, win rate from the server projection), a trade toast for committed fills and exits (server strings only), 0.5x playback speed, shortcut list in the info popover. Bug found and fixed while testing: a rejected Step tick overwrote the saved unfinished ADVANCE target, making Continue saved loop on ADVANCE_IN_PROGRESS; an unfinished ADVANCE target is now never overwritten and blocks other replay actions until continued. Verified in the synthetic harness at 1000x700 and 390x844 (toast, legend, chips, guard); not re-measured at the seven sizes.

## Roadmap (P2, not built)

Multi-chart layouts, social strategies, drag-to-modify live orders, exact-tick landing for Jump
(needs an event-aware backend advance), persisting timeframe across reload.
