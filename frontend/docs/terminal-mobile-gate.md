# Terminal mobile gate (C-14, 2026-11-06)

Measured in headless Chromium in this container. There is no real low-memory phone here, so the numbers are a browser measurement, not a device certification.

## JS heap at the largest chart the API allows

45,152 candles (512 revealed + one previous month of 1m context), 100 drawings, 16 indicators. Heap is `JSHeapUsedSize` after a forced GC (CDP), from `tests/qa/performance-qa.cjs` and a one-off attribution probe.

| Load | Heap (MB) |
|---|---|
| 512 candles, nothing else | 10.0 |
| 45k candles, 0 drawings, 0 indicators | 44.0 |
| 45k candles + 100 drawings | 45.0 |
| 45k candles + 1 single-line indicator (SMA, EMA, RSI, ATR, HMA, ADX, CCI, PSAR) | ≈ 56 |
| + Bollinger / Keltner / MACD (3 lines) | ≈ 80 |
| + Ichimoku | 105.6 |
| + Pivots | 126.4 |
| 45k candles + all 16 indicators | 480.4 |
| Full load (C-08 desktop) | 482.3 |
| Same full load at 390×844, 4× CPU throttle | 480.9 → 482.3 after pan; load 8.7 s; pan frame p50 33 ms, p95 100 ms, max 483 ms |

**Finding.** Drawings cost about 1 MB. Each indicator output line costs about 12 MB at 45k candles, so 16 indicators account for ~435 MB of the ~480 MB. Candles alone are ~44 MB.

**Not changed in this checkpoint.** Bounded windowing of indicator series (compute on the full revealed prefix, hand only the visible range plus a margin to the chart) would preserve indicator semantics, because computation still uses every revealed candle and nothing beyond the replay cursor. It touches the indicator adapter that C-08 tuned for 45k candles, so it is proposed as its own checkpoint with before/after heap and frame numbers, not folded into C-14.

**Status (C-14): HOLD.** See C-15 below.

## C-15 rendered series window (founder follow-up 2026-11-06)

**Attribution.** A probe handed each indicator series only its last 2,000 points; the calculation was unchanged. The heap at 45k candles with 16 indicators fell from 480.9 MB to 138.6 MB. That splits the original heap like this:

- about 340 MB was the chart library's own per-point storage of the indicator series;
- about 94 MB was the calculated outputs the engine keeps;
- about 45 MB was candles.

React rerenders and hydration are not the cost. The heap at 45k candles without indicators is 44.8 MB, and drawings add about 1 MB.

**Change** (`src/indicators/IndicatorSeriesAdapter.js`). `IndicatorEngine` still calculates every indicator over the whole revealed prefix. Only the data handed to the chart is bounded:

- the visible time range plus one visible span on each side, at least 4,000 points;
- re-sliced only when the view comes within a quarter span of an edge, or after zooming far back in;
- series of up to 12,000 points are handed over whole. At 5,120 candles a re-slice cost up to 470 ms per far pan to save 7 MB, so the threshold leaves that case unchanged.

**Why the semantics do not change.**

- Each rendered point is the same object the full calculation produced (`tests/indicator-window.test.mjs`).
- A window never contains a bar the full series lacks, so nothing past the last revealed bar appears.
- Warmup, convergence, confirmed fractals, ZigZag repaint labels and pane ownership are all computed before slicing.
- Candle series and drawings are not windowed.
- Screenshots taken after a far pan are byte-identical before and after this change for 45k×8, 45k×16 (desktop), 45k×16 (390 px phone) and 5k×16.

**Measured** with `node tests/qa/terminal-memory-profile.cjs OUT_DIR http://127.0.0.1:5179`: the real AlphaWorkspace, a labeled synthetic chart-history generator, and heap read after a forced GC. Each cell shows before → after. "Far pan" is 20 full-width drags back into history.

| View | Candles | Indicators | Heap MB | Load ms | Frame p50/p95/max ms | Long tasks (max ms) | Far pan p95 / max ms, long tasks (max) |
|---|---|---|---|---|---|---|---|
| 1440 | 512 | 0 | 11.1 → **11.1** | 1235 → 1193 | 16.7/16.8/16.8 → 16.7/16.7/16.8 | 0 (0) → 0 (0) | — → — |
| 1440 | 512 | 1 | 11.4 → **11.4** | 1261 → 1184 | 16.7/16.7/16.8 → 16.7/16.7/16.8 | 0 (0) → 0 (0) | — → — |
| 1440 | 512 | 8 | 13.9 → **13.9** | 1383 → 1346 | 16.7/16.7/16.8 → 16.7/16.7/16.8 | 0 (0) → 0 (0) | — → — |
| 1440 | 512 | 16 | 16.2 → **16.3** | 1628 → 1462 | 16.7/16.7/16.8 → 16.7/16.8/33.3 | 0 (0) → 0 (0) | — → — |
| 1440 | 5120 | 0 | 15.5 → **15.5** | 1337 → 1420 | 16.7/16.8/16.8 → 16.7/16.7/16.8 | 0 (0) → 0 (0) | 16.8 / 33.3, 0 (0) → 16.7 / 16.8, 0 (0) |
| 1440 | 5120 | 1 | 16.8 → **16.8** | 1364 → 1451 | 16.7/16.7/16.8 → 16.7/16.7/16.8 | 0 (0) → 0 (0) | 16.8 / 16.8, 0 (0) → 16.8 / 16.8, 0 (0) |
| 1440 | 5120 | 8 | 34.7 → **34.7** | 1623 → 1668 | 16.7/16.7/16.8 → 16.7/16.8/16.8 | 0 (0) → 0 (0) | 16.8 / 16.8, 0 (0) → 16.8 / 16.8, 0 (0) |
| 1440 | 5120 | 16 | 63.1 → **63.1** | 1968 → 1883 | 16.7/16.8/16.8 → 16.7/16.8/16.8 | 0 (0) → 0 (0) | 16.8 / 33.4, 0 (0) → 16.7 / 16.8, 0 (0) |
| 1440 | 45152 | 0 | 44.9 → **44.8** | 2167 → 2125 | 16.7/16.7/16.8 → 16.7/16.8/16.8 | 0 (0) → 0 (0) | 16.8 / 16.8, 0 (0) → 16.7 / 16.8, 0 (0) |
| 1440 | 45152 | 1 | 56.4 → **47.8** | 2062 → 2037 | 16.7/16.7/16.8 → 16.7/16.8/16.8 | 0 (0) → 0 (0) | 16.7 / 16.8, 0 (0) → 16.7 / 33.4, 0 (0) |
| 1440 | 45152 | 8 | 206.9 → **86.8** | 2463 → 2333 | 16.7/16.8/16.8 → 16.7/16.7/16.8 | 0 (0) → 0 (0) | 16.8 / 16.8, 0 (0) → 16.7 / 16.8, 0 (0) |
| 1440 | 45152 | 16 | 480.9 → **154.3** | 2519 → 2711 | 16.7/16.7/33.4 → 16.7/16.7/16.8 | 0 (0) → 0 (0) | 16.7 / 83.4, 4 (95) → 16.8 / 33.4, 0 (0) |
| 390 · 4× CPU | 45152 | 8 | 206.8 → **86.3** | 5949 → 6222 | 16.7/33.4/50.1 → 16.7/33.4/83.3 | 4 (58) → 10 (91) | 33.3 / 66.7, 5 (70) → 33.4 / 50.1, 6 (63) |
| 390 · 4× CPU | 45152 | 16 | 480.8 → **153.3** | 6477 → 7317 | 16.7/50/83.4 → 16.7/50.1/99.9 | 19 (87) → 28 (88) | 50 / 150, 50 (163) → 50.1 / 83.4, 65 (93) |

**Reading.**

- At 45k candles the heap falls from 481 MB to 154 MB with 16 indicators, and from 207 MB to 87 MB with 8. Nothing changes at 512 or 5k candles.
- Desktop frame times are unchanged.
- On the 390 px phone at 4× CPU, frame times stay in the same noisy band: p95 is 50 ms either way, and the worst far-pan frame went from 150 to 83 ms. Long-task counts vary from run to run. Drawing 16 indicator panes is the cost there. Windowing fixes memory, not phone rendering cost.

**Status.**

- Memory: PASS for the simulated budget (154 MB at the API maximum).
- Low-memory phone acceptance: **HOLD** until it is measured on a real device.
- **Proposal for owner review (not implemented):** on phones (≤ 760 px), show at most 8 indicators by default and keep the rest stored but hidden until enabled. The measured phone frame p95 is 33 ms at 8 indicators vs 50 ms at 16.

## Viewports, orientation, gestures, motion

`tests/qa/terminal-viewports-qa.cjs` (real local API): 320×640, 375×667, 390×844, 768×1024, 1024×768, 1280×800, 1440×900, 844×390 and 667×375. Each one: no horizontal overflow, chart visible, replay controls in view, confirm sheet actions reachable without scrolling. Rotation 390×844 → 844×390 with the pick ticket open keeps it in view. Reduced motion stops the sheet and ticket animations. The phone Draw sheet searches all 47 tools.

Gesture arbitration (tap vs. draw, handle drag, pinch without anchors, brush) stays covered by `tests/qa/mobile-touch-qa.cjs`.

**Fixed here:** phone landscape (≤ 500 px tall, ≤ 1000 px wide) used the portrait two-row header from C-13 and pushed the replay controls off screen at 667×375; landscape now keeps the single-row, chart-first header.

**HOLD:** the virtual keyboard cannot be emulated in headless Chromium; the ticket inputs need a check on a real phone.

## Persistence

Drawings and indicators are stored in this browser only (`localStorage`, scoped per workspace and Session). The object tree, the phone Draw sheet and the indicator studio now say so. Cross-device sync needs a Codex storage and compare-and-swap contract (B08); none is assumed.
