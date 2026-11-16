# Chart-first replay controls ported onto the PR #53 base (2026-11-16)

Branch `claude/chart-first-on-53-20261116`, from `58b3cb9` (head of PR #53). Stacked on #53: it contains
only the files below and does not touch the backend, the financial reducer or any contract.
The earlier main-based work stays in PR #56 (`claude/chart-first-terminal-20261116`).

## What was ported (and what was deliberately not)

| Item | On #53 |
|---|---|
| Replay controls (one system): Play/Pause, Step ticks, Next candle (UTC bucket end), Continue saved replay, Go to time, 0.5×–20× playback rate, Cancel | `AlphaReplayControls.jsx`, docked strip under the plot (the old floating pill is gone, its dead CSS removed) |
| Jump to Next Event | **#53's own server-side `jump-next-event` is kept** (`onJump` in `TickAlpha.jsx`: durable, committed events, progress, cancel, resume); the control only drives it. No approximate fallback exists on this base |
| Unfinished ADVANCE target | The server's `pendingReplayTargetNs` is the only source; no browser storage. Verified in the harness: reload with empty localStorage shows Continue and finishes the same target. Observed hosted Sessions use #53's `replay-to` (SEEK) path for Next candle / Go to time |
| Scrubber | `AlphaReplayScrubber.jsx`: pans revealed history only (chart `goto` command); future time = proposal + Go confirm, then the existing forward SEEK/replay-to; keyboard and touch |
| Chart legend (O/H/L/C + observed Bid/Ask + exact spread), trade toast (fill/exit from committed server rows) | `AlphaLegend.jsx`, `AlphaTradeToast.jsx` |
| Chained replay calls | `onReplay` now reads the latest committed view (`viewRef`) and returns `{view,reached,revealed}`; a gap crossed without ticks is success, a stalled target is refused |
| Terminal default collapsed (24 px) for a Session with no saved preference | `AlphaTerminal.jsx` |
| Layout CSS rebuild (single geometry owner, popup alignment, phone one-screen column) | **NOT ported.** #53's product CSS (`tickAlpha.css` 95 KB + `alphaProduct.css`) has its own, much larger cascade; rebuilding it is a separate job. Only new markup carries new CSS (`alphaReplayStrip.css`) |

Existing contracts preserved: accessible names `Play replay`/`Pause replay`, `Step ticks`, `Jump to Next Event`,
`Cancel search`, `Continue saved replay`, `Replay speed`; `tests/tick-alpha.test.mjs` now reads
`AlphaReplayControls.jsx` too (the strings moved out of `AlphaWorkspace.jsx`); `terminal-viewports-qa.cjs`
selector updated (`.alpha-replay-strip`). Not re-run: the Playwright journeys (`riksora-browser-journey.mjs`,
`order-flow-qa.cjs`) need the real backend.

## Plot size (CSS px, plot = `.alpha-chart-host`), #53 + port

| Viewport | Plot | % of viewport |
|---|---|---|
| 1920×1080 | 1792×794 | 94 % × 74 % |
| 1440×900 | 1312×614 (was 1312×536 on bare #53: +78 px, terminal collapsed) | 91 % × 68 % |
| 1366×768 | 1238×482 | 91 % × 63 % |
| 768×1024 | 640×686 | 83 % × 67 % |
| 390×844 | 390×490 (page scrolls on this base) | 100 % × 58 % |
| 360×800 | 360×464 | 100 % × 58 % |
| 844×390 | 818×334 (page scrolls) | 97 % × 86 % |

No horizontal overflow at any size. #53's own chrome (padding, rail, header) keeps the plot below the
main-based layout of PR #56 (e.g. 68 % vs 75 % at 1440×900); that is the unported layout rebuild above.
Only 1440×900 was measured on bare #53 (no other "before").

## Evidence

* Harness (synthetic UI mock of the tick-alpha contract incl. `jump-next-event` and `pendingReplayTargetNs`;
  not an engine): Next M1/H1, Step, Play/Pause, partial-advance resume, Continue after reload with empty storage,
  Jump cancel/resume/event + toast, legend, scrubber render.
* `npm run lint` PASS; `vite build` PASS; 43 registered frontend tests PASS, 0 FAIL (includes `test:replay-controls`,
  `test:tick-alpha`, `test:repository`).
* **NOT RUN:** `test:stitch-analytics` (needs Python `msgspec`, absent from the shared venv; not installed to avoid
  altering it); backend/PostgreSQL suites; Playwright journeys; real-backend Jump/replay-to; hosted account
  (observed) Next candle via `replay-to`. VPS1 untouched.
