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

## S-6 ResearchCalculator boundary — existing runtime mapping

The pure calculator boundary is the existing `backend/execution/analysis.py:metrics(completed)` callable; this names the existing seam, not a second service, wire schema or engine. Its caller supplies ordered completed-position rows with final exact decimal-string `net`. The callable returns counts, exact numerator/denominator strings and explicit null/unavailable research values according to the definitions above. It never accepts provider/storage/index handles, candles, future quotes, uncommitted orders or account mutation capabilities.

BTL `project` remains the owner of committed-event grouping, partial-close completion, causal fill validation, event-chain/account reconciliation, bounded 4096-event refusal, drawdown from exact cash postings, Session/Method/Passport provenance and orchestration. Open/unresolved positions do not enter completed-position denominators. At the original S-6 checkpoint, R0 was not pinned and research values were explicitly unavailable; evaluating a library did not implement them. Subsequent implementation evidence belongs to the [existing system blueprint](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#alpha-pinned-risk-and-basic-research-implementation-evidence--2026-10-11), with operational progress solely in [04_CURRENT_PHASE](../AI_CONTEXT/04_CURRENT_PHASE.md). FinancialEngine remains unchanged.

Any future numerical adapter must satisfy authored goldens at this boundary and preserve exact money/null/BE semantics before adoption. S-6 retains the current small pure calculator after the pinned QuantStats comparison; [STITCH audit Section 17](STITCH_0_OSS_REPLACEMENT_AUDIT.md#17-s-6-researchcalculator-and-quantstats-evaluation--2026-10-10) owns evidence and library limitations. No frozen metric definition is amended.

## R-8 deterministic bootstrap primitive freeze — 2026-10-11

This is the existing contract's pre-calculator PRNG freeze, not another roadmap or execution contract. Scope is descriptive resampling of already-completed canonical net R values; it grants no forecast, execution certainty, provider rights or external delivery. Algorithm/version: `BTL-XORSHIFT32-13-17-5-1`. The explicit integer seed is in1..4294967295; zero/boolean/string/fractional/out-of-range seeds are refused. It is a reproducible noncryptographic research primitive, never a security token generator.

State is an unsigned32-bit integer. Each word performs, in order, `x ^= (x << 13)`, `x ^= (x >> 17)`, `x ^= (x << 5)`, with modulo2^32 after each operation and a logical unsigned right shift. Nonzero seeds cycle through nonzero words. To sample N positions, let M=4294967295 and L=floor(M/N)*N; set u=next_word-1, reject u>=L, otherwise return u mod N. This avoids naive modulo bias over the primitive's nonzero output domain. Replacement draws continue one deterministic state across all10000 paths; input order is canonical completion order, never shuffled or sorted by profit.

Each path starts at0R and has exactly N replacement draws. Cash-style drawdown magnitude is running peak (initial0) minus current cumulative R. Negative streak counts consecutive draws with R<0; zero/positive reset it. Report sorted-sample nearest-rank quantiles: index ceil(p*10000)-1 for p in0.05/0.50/0.95/0.99. All input, path, drawdown and percentile arithmetic stays exact rational; display alone may round. N<30 returns INSUFFICIENT_SAMPLE before path computation. Existing128-position/4096-event accepted input budgets apply; larger input is refused, never truncated. Missing-R exclusions, seed, PRNG/version and10000-path count are always disclosed.

The following materialized vectors were independently computed in JavaScript before Python calculator implementation. All-one and all-negative30-position inputs must give terminal30/-30 respectively; their drawdown0/30 and longest negative streak0/30 are constant across every percentile. The mixed input below contains30 values, repeating[-1,0,2] ten times, seed1,10000 paths.

<!-- BTL-BOOTSTRAP-FROZEN-VECTORS-1 -->
```json
{
  "schemaVersion": 1,
  "artifact": "BTL-BOOTSTRAP-FROZEN-VECTORS-1",
  "prngVersion": "BTL-XORSHIFT32-13-17-5-1",
  "seed": 1,
  "firstWords": ["270369", "67634689", "2647435461", "307599695", "2398689233"],
  "firstSampleIndicesN3": [2, 0, 2, 1, 1],
  "mixed30": {
    "repeatedValues": ["-1", "0", "2"],
    "repeat": 10,
    "paths": 10000,
    "terminalP5P50P95": ["-1", "10", "21"],
    "drawdownP50P95P99": ["4", "7", "10"],
    "negativeStreakP50P95P99": [3, 5, 6]
  }
}
```

The freeze precedes calculator implementation. Its validation cannot be reported as a completed Monte Carlo runtime or Alpha acceptance.


## Additive engine2 committed-ledger projection - 2026-10-17

The existing Basic Statistics/Session-integration grant includes a separate internal engine2 projector and scoped native read. All frozen metric definitions above remain unchanged. Validate the current state, immutable revision0 genesis, complete event chain and final account/order reconciliation; read bounded pages in one repeatable-read snapshot. Above4096 events return explicit UNAVAILABLE before iterating, never partial performance as complete. Fork lineage remains explicitly unavailable until a validated parent-ledger stitch exists. No financial mutation or provider/quote recovery belongs to this projection.

Use posted USD gross and all posted entry/exit fees in final completed-position net. Partial exits affect cash immediately but enter trade-count/win-rate denominators only once the full position closes. All-position cash totals and completed-position net are separate quantities. Drawdown and its bounded interactive curve use exact committed cash postings in canonical event order, labelled balance/COMMITTED_CASH_POSTINGS; do not invent mark-to-market equity or FX rates. The existing pure metrics calculator remains shared. R stays null/excluded until immutable pre-entry confirmation evidence is joined; the unmounted kernel's risk estimate alone is not a confirmed-review Passport. No retrospective R0, new Monte Carlo, MAE/MFE, API route, UI acceptance, source rights or paid Beta acceptance is implied. Browser verification is deferred because this checkpoint is an unmounted backend projection.
