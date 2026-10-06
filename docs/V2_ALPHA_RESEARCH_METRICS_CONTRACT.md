# Backtest Lab v2 Alpha — Research Metrics Contract v1

Status: FROZEN PLAN CONTRACT.

Research consumes canonical v2 position evidence plus Passport identity and never reconstructs execution truth from candles. Unresolved positions are reported separately and excluded from performance denominators.

## Basic metrics
- trade_count = completed positions.
- win/loss/breakeven use final net realized P&L positive/negative/zero.
- win_rate = wins / completed positions; null when none.
- average_win and average_loss are arithmetic means of their respective completed-position net P&L.
- expectancy = arithmetic mean net P&L.
- profit_factor = gross positive net P&L / absolute gross negative net P&L; null when denominator is zero.
- cumulative equity follows canonical realized P&L/cost event order.
- drawdown = running peak equity minus current equity; percentage requires positive peak.
- BE breaks both win and loss streaks.
- duration = final exit event time minus first entry fill time.

## R multiple
If immutable pre-entry planned initial risk amount R0 is positive and pinned at confirmation, R_multiple = final net realized P&L / R0. Otherwise R is null; never infer R retrospectively.

## MAE/MFE
Use only precision-eligible revealed bid/ask events from first entry through final exit. Long liquidation mark is bid; short liquidation mark is ask. Favorable/adverse excursion is measured against canonical entry basis. Money exposure after partial exit uses remaining quantity. Entry/final-exit boundaries are included. If chronology uncertainty can change the excursion, return null with reason.

## Monte Carlo v1
This is descriptive trade-outcome bootstrap, not a market simulator or forecast.

Input unit: completed-position net R-multiple. Missing-R positions are excluded and counted.
- deterministic repository-owned PRNG with golden vectors must be frozen before calculator implementation;
- explicit integer seed; no hidden random seed;
- 10,000 paths;
- path length N = eligible completed positions;
- sample with replacement from observed R values;
- normalized path starts at 0R;
- report p5/p50/p95 terminal R, p50/p95/p99 maximum drawdown magnitude, and p50/p95/p99 longest negative-result streak;
- always disclose N, exclusions, seed, PRNG/version and path count;
- minimum N = 30; below this return INSUFFICIENT_SAMPLE.

Never label the bootstrap as probability of future profit.

## Advanced research
Regime classification, destruction tests, walk-forward/OOS and multiple-testing correction are POST-ALPHA for the first closed cohort and are not pre-Alpha release blockers.
