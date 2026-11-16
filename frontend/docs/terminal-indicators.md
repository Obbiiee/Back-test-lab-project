# Terminal indicators (Issue #21 C-05 / C-06 / C-07)

50 indicators are registered in `src/indicators/productionRegistry.js` (the original 7 first, unchanged, then 43 added by C-06). Calculators live in `src/indicators/proCalculations.js`. Each spec has `category`, `version: 1`, `description` and, where needed, `constraint` / `notes`. If a formula convention ever changes, bump that spec's `version`.

## Pinned conventions

| Topic | Convention |
|---|---|
| EMA seed | SMA of the first N valid values, then α = 2/(N+1). Used by DEMA, TEMA, ZLEMA, Keltner, TSI, PPO, TRIX, Elder Ray. |
| RMA / Wilder | SMA seed, then (prev·(N−1)+x)/N. Used by ATR, NATR, Supertrend, Keltner ATR, Alligator (SMMA of hl2), RSI inside Stoch RSI, ADX. |
| True range | Bar 0 = high − low; later bars use the previous close. |
| Standard deviation | Population (÷N), same as Bollinger Bands. |
| HMA | WMA(2·WMA(N/2) − WMA(N), round(√N)). |
| ZLEMA | EMA of 2·x − x[lag], lag = ⌊(N−1)/2⌋. |
| KAMA | Efficiency N, fast 2, slow 30; seed = close at bar N−1. |
| Supertrend | hl2 ± m·ATR(Wilder), ratcheting bands; the first bar starts in a downtrend. Points are coloured green (up) or red (down). |
| Parabolic SAR | Wilder; initial direction from bar 1 vs bar 0; SAR clamped to the two prior bars' extremes. |
| Ichimoku | Leading spans are shifted forward onto later **revealed** bars only, and the lagging span at bar i is the close of bar i+26. Nothing is drawn beyond the last revealed bar, so no future quote is read. |
| Alligator shifts | Same rule: a shift moves a value onto a later revealed bar. |
| Pivot points | From the prior **completed UTC day** (classic, Fibonacci, Camarilla). No pivot on the first day. |
| Average Daily Range | Mean high−low of the last N completed UTC days. |
| Williams Fractals | A fractal is emitted only after its right-side bars exist (confirmed). |
| ZigZag | `confirmed` pivots never move. `provisional` (last leg) can change as bars arrive and is labelled as repainting. |
| DPO | Causal variant: close[N/2+1 bars ago] − SMA(N). The classic centred DPO looks ahead and is not used. |
| Squeeze Momentum | LazyBear variant: momentum = linreg(close − avg(Donchian mid, SMA), N); squeeze dot white when Bollinger is inside Keltner. |
| Williams %R / Stoch RSI | A flat range returns the midpoint (−50 / 50) instead of dividing by zero. |
| Linear Regression Channel | Rolling fit ± k · residual population standard deviation (volume-free). |

## Evidence

- `tests/c06-indicators.test.mjs` compares every output point of 42 indicators (77 outputs, 22,573 points) with `tests/fixtures/c06-golden.json`, produced by an independent Python/pandas implementation (`tests/fixtures/c06_reference.py`, regenerate with `python3 tests/fixtures/c06_reference.py > tests/fixtures/c06-golden.json`). Tolerance 1e-8 relative.
- The same test checks all 50 types for causality (output at cuts of 60/150/250 bars never changes when later bars arrive; ZigZag provisional excluded), and that empty, one-bar, five-bar and flat input never throws or emits non-finite values.
- `tests/c05-indicator-settings.test.mjs`: style validation, live series options, pane order, pane height, overlay ↔ pane, histogram colours, persistence round trip and read-only fallback.
- `tests/qa/indicators-qa.cjs`: real-browser run (desktop, tablet 768, phone 390). Screenshots in `docs/qa/issue-21/c05/`.

## Settings (C-05)

Each instance stores only what differs from the defaults: `style[output] = {visible, color, lineWidth 1–5, lineStyle solid|dashed|dotted, opacity, positiveColor/negativeColor (histograms)}`, `placement` (an overlay can move to its own pane; a pane study cannot overlay price), `paneHeight` 0.1–1, `references` (≤6, pane only). Array order is pane order. Storage stays `backtest-indicators-v1:<workspace>`; old configs load unchanged, and an invalid stored document keeps the namespace read-only.

## Volume (C-07)

V01–V12 (Volume, Volume MA, VWMA, VWAP, Anchored VWAP, OBV, MFI, A/D, CMF, Chaikin Osc., Volume Profile, CVD) are listed in the catalog as disabled with the reason. The data is Bid/Ask quotes only, so no volume or tick count is synthesised.
