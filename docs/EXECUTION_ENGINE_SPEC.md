# Backtest Lab — Replay & Execution Engine Specification

Status: architecture authority for future replay/execution work. This document does not authorize implementation.

## Core separation
```text
Market Data -> Master Market Clock -> Time-Bounded View
                                  -> Chart / Indicators / News
                                  -> Replay Engine
                                  -> Execution Engine
                                  -> Orders / Positions / Account
                                  -> Canonical Trade/Event Ledger
                                  -> Journal / Research
```
The chart is visualization, never execution truth. Replacing the renderer must not change backtest results.

## Five sources of truth
1. Market truth: canonical versioned market data.
2. Time truth: Master Market Clock.
3. Execution truth: Execution Engine.
4. Trading truth: append-only canonical Trade/Event Ledger.
5. Research truth: Experiment/Protocol manifest and reproducibility identity.

## Replay modes
**Fast Replay:** candle/manual replay for training and lightweight iteration.

**Precision Replay:** chronological tick/quote replay for research-grade execution.

No-look-ahead is a hard contract. Every temporal consumer receives only information available at simulated time.

## Precision chronology rule
OHLC cannot prove whether SL or TP occurred first when both are inside one candle. Precision mode must never silently choose SL-first, TP-first or another synthetic path and call it exact.

Precision certification requires data that establishes event chronology, ideally historical Bid/Ask ticks. First chronological valid hit wins. If chronology cannot be established, expose uncertainty/lower quality or reject Precision certification.

Equal timestamps use trustworthy sequence IDs when available. Without sequence/order evidence, do not invent ordering.

## Bid/Ask
Execution uses the appropriate quote side and historical spread when available. Market feed and broker/execution profile are separate concepts.

## Execution Profile
May define commission, slippage model, latency model, lot limits, tick/contract rules, margin/leverage, swap/funding and trading hours. Profiles may include Ideal, Realistic, Custom or named broker profiles. Changing execution assumptions must be reproducible and visible in research results.

## Order lifecycle
Target order types include Market, Limit, Stop, Stop-Limit, SL, TP, Trailing and OCO where separately authorized.
Canonical lifecycle should support:
CREATED -> PENDING -> TRIGGERED -> PARTIALLY_FILLED -> FILLED -> CLOSED
and CANCELLED / REJECTED / EXPIRED where applicable.

## Account and position state
Canonical concepts: Balance, Equity, Used Margin, Free Margin, Floating P&L, Realized P&L, Drawdown. Position state includes entry/average price, size, SL, TP, partial exits, fees and realized/unrealized P&L.

## Canonical Trade/Event Ledger
Prefer append-only/event-sourced evidence such as ORDER_CREATED, ORDER_TRIGGERED, ORDER_FILLED, POSITION_OPENED, SL_CHANGED, TP_CHANGED, PARTIAL_CLOSE, POSITION_CLOSED, COMMISSION_CHARGED, SWAP_CHARGED and protocol-compliance events. Journal, statistics, equity and research derive from canonical events rather than chart objects.

## UI convergence
Free/Protocol and Quick/Planned do not create different execution engines.
```text
Quick Trade ----\
                 -> Canonical Order Request -> Rules Validation -> Execution Engine
Planned Trade --/
```
A drawing/planner never directly mutates account state.

## Validation
Use deterministic golden scenarios, truncation/no-look-ahead tests, chronology fixtures, gap cases, spread/cost/slippage fixtures, partial-fill/partial-close cases and reference-engine comparison only where semantics genuinely match.
