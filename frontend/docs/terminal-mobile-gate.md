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

**Status: HOLD** for low-memory mobile release until that checkpoint lands or the product caps indicators on phones.

## Viewports, orientation, gestures, motion

`tests/qa/terminal-viewports-qa.cjs` (real local API): 320×640, 375×667, 390×844, 768×1024, 1024×768, 1280×800, 1440×900, 844×390 and 667×375. Each one: no horizontal overflow, chart visible, replay controls in view, confirm sheet actions reachable without scrolling. Rotation 390×844 → 844×390 with the pick ticket open keeps it in view. Reduced motion stops the sheet and ticket animations. The phone Draw sheet searches all 47 tools.

Gesture arbitration (tap vs. draw, handle drag, pinch without anchors, brush) stays covered by `tests/qa/mobile-touch-qa.cjs`.

**Fixed here:** phone landscape (≤ 500 px tall, ≤ 1000 px wide) used the portrait two-row header from C-13 and pushed the replay controls off screen at 667×375; landscape now keeps the single-row, chart-first header.

**HOLD:** the virtual keyboard cannot be emulated in headless Chromium; the ticket inputs need a check on a real phone.

## Persistence

Drawings and indicators are stored in this browser only (`localStorage`, scoped per workspace and Session). The object tree, the phone Draw sheet and the indicator studio now say so. Cross-device sync needs a Codex storage and compare-and-swap contract (B08); none is assumed.
