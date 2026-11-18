# Indicator look-back needs and the Free chart rule (2026-11-18)

Status: implementation register, not architecture authority. Purpose: let the owner set one consistent look-back policy later. Nothing here changes a financial contract.

## 1. What is enforced today (owner decision 2026-11-18, "for now")
* **Free:** a Free account never receives candles older than the start of its activated month. Enforced on the server for every response:
  * `POST /sessions/{id}/chart-history` (frozen `BTL-PAST-CHART-CONTEXT-1`, the month before the Session) is refused with `CHART_CONTEXT_PRO_ONLY` (409) for Free.
  * `GET /sessions/{id}/chart-bars` (`BTL-CHART-HISTORY-PAGE-1`, up to 5,000 candles) is clipped by the server using the entitlement ledger. The browser cannot supply or lower the floor (a client `floor_ns` is ignored; tested). Paging ends at the floor (`hasMore=false`, `historyExhausted=true`).
  * Candles of the activated month itself come from revealed ticks and stay cursor-bound (nothing after the cursor).
* **Pro:** unchanged, full available history (the chart registry decides what exists). The public application has no chart registry configured yet, so `chart-bars` answers "unavailable" for everyone there today; the rule is tested with a stub and by unit tests.
* Leak review: server responses are clipped per request, so a shared server cache cannot hand a Free account older bars. The browser may keep bars it received while it was Pro (a Pro→Free downgrade); those are the user's own earlier data and are not re-served by the server.

## 2. Look-back each indicator needs (from `frontend/src/indicators`)
Periods are user parameters (1..1000). Numbers below are the defaults; "bars" are candles of the selected timeframe.

| Indicator family | Defaults | Bars before the first valid value | Converges only after |
|---|---|---|---|
| SMA, WMA, HMA, ZLEMA, LINREG, Donchian, StdDev, Bollinger | period 20 | period (20) | exact at period |
| EMA, DEMA, TEMA, KAMA | 20 / 10 | ~period, but seeding error remains | about 3 to 5 × period |
| RSI, RMA, ATR, NATR, ADX, DMI (Wilder smoothing) | 14 | 2 × period for ADX/DMI, period otherwise | about 3 × period (recursive) |
| MACD | 12/26/9 | 26 + 9 | about 100 bars |
| Stochastic, Stoch RSI | 14/3 | 14..28 | exact after the windows fill |
| Supertrend, Keltner | ATR 10 + EMA 20 | 20 | about 60 bars |
| ADR (daily range) | 14 **days** | 14 days of D1 data | exact |
| Any indicator, maximum allowed period | 1000 | 1000 | 3000+ for recursive ones |

## 3. What the Free rule does to them
* The Session cursor starts at the beginning of the activated month, so at the start of the month every indicator is **short of history**: on M1 the first ~20 to 100 bars are not valid for most defaults, and periods of 200 or more are not valid for hours or days.
* On higher timeframes one month contains few candles (about 22 D1, about 88 H4, about 22 × 24 = 528 H1 in a 5-day-week market). Period-200 indicators on D1 or H4 never become valid inside a Free month, and ADR(14 days) is valid only in the second half of the month.
* Recursive indicators (EMA, RSI, ATR, ADX) in a Free month are numerically different from the same indicator computed with the earlier month available. That is a visible difference between Free and Pro for the same bar, which must be explained to users or removed by a policy.

## 4. Policy options for the owner (not implemented)
1. **Strict month (current):** simplest, consistent with the entitlement; document that indicators warm up inside the month.
2. **Fixed warm-up allowance for Free:** allow a bounded number of candles before the month (for example 500 bars of the chosen timeframe, or the larger of 3 × the longest active period and 200 bars). It must be defined in bars, not in months, and it must be served only as derived, non-authoritative display data.
3. **Warm-up for indicators only, never for the chart:** compute the indicator on the server or ship the extra bars flagged "indicator warm-up", never drawn as candles. Highest effort.
Any option other than 1 reveals data older than the activated month and therefore needs an explicit owner decision and an entitlement rule that matches the Terms text.

## 5. Open items for the policy
* The frozen past-context artifact is "previous calendar month"; a bar-based allowance would be a new additive artifact.
* Timeframe aggregation (D1/H4 boundaries) at the start of the month needs one rule (session-day boundary) shared by chart and indicators.
