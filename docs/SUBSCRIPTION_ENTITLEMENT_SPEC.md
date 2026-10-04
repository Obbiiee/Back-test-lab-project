# Backtest Lab — Subscription & Entitlement Specification

Status: product/architecture authority for future subscription work. This document does not authorize implementation or finalize price.

## Core monetization principle

**Do not sell correctness. Sell research capacity, depth and convenience.**

Free and paid users must use the same canonical replay/execution semantics. Subscription tier must not deliberately reduce no-look-ahead correctness, execution correctness, protocol semantics, or available market-data fidelity merely to make Free results inferior.

Where Precision execution is possible from the selected dataset, entitlement must not intentionally substitute a less-correct engine for Free users.

Free/Pro subscription is independent from **Free Mode / Protocol Mode** and **Quick Trade / Planned Trade**.

## Free tier — daily tradable research window

The intended Free experience is a complete, credible Backtest Lab workflow with a capacity limit.

### Daily allowance

- A Free user may activate **one tradable historical window of up to one calendar month per daily entitlement period**.
- The exact reset timezone/time and anti-abuse mechanics are implementation decisions to be defined before launch; they must be deterministic and visible to the user.
- Once a window is activated, trading/replay execution is allowed inside that window.
- The user may make multiple valid trades inside the activated window; the limit is the research window, not an arbitrary trade-count penalty.
- The daily allowance must be enforced server-side once cloud entitlements exist.

### Historical context outside the tradable window

Earlier historical data needed for legitimate chart context should remain viewable/read-only where data rights and product availability permit.

The user may use that context for analysis such as:
- support/resistance;
- market structure/trend;
- drawings;
- indicators;
- contextual review.

Historical context outside the active Free tradable window must not silently become executable/tradable merely because it is visible.

The product must visually distinguish **viewable context** from the **active tradable window** without changing the fundamental chart workflow.

### Open-position boundary rule

A subscription/window boundary must never manufacture a trade outcome.

If a valid order/position is opened within the Free tradable window and remains active when the nominal calendar window ends, Backtest Lab may continue consuming the minimum subsequent market data necessary to resolve that already-open lifecycle according to the applicable strategy/protocol and execution rules.

Examples include reaching SL/TP, a permitted manual close, cancellation/expiry where applicable, or another canonical terminal state.

This continuation:
- does not grant a new general tradable month;
- must not allow unrelated new entries outside the entitled window;
- must preserve no-look-ahead and normal execution semantics;
- ends when the outstanding authorized lifecycle is resolved.

The next new Free tradable-window allowance becomes available according to the next daily entitlement period.

## Free trading capabilities

Subject to normal product/data availability, Free should retain the core experience:
- professional chart workflow;
- canonical Precision-capable execution path;
- no-look-ahead guarantees;
- Quick Trade;
- Planned Trade;
- Free Mode;
- Protocol Mode;
- core drawing/trading interaction;
- core indicator workflow;
- journal/history needed to understand the completed session.

Protocol Mode must not be treated as synonymous with a paid subscription.

## Free results — Basic Statistics

Free results should provide enough evidence for the user to understand the session rather than functioning as a crippled demo.

Initial Basic Statistics target:
- total completed trades;
- wins / losses;
- win rate;
- realized net P&L;
- total R;
- average R;
- profit factor;
- maximum drawdown.

Exact definitions must use the canonical statistics/ledger contracts. Additional basic metrics may be added later without weakening the monetization principle.

Advanced research surfaces may be Pro-gated or quota-limited, including capabilities such as deeper MAE/MFE analysis, large Monte Carlo workloads, parameter research, robustness analysis, walk-forward research, cross-feed comparison, advanced reporting, larger cloud storage/compute and higher AI-research allowances.

## Pro tier

Pro uses the **same canonical engine and fundamental UX** without the Free daily one-month tradable-window restriction.

Subject to dataset coverage, licensing, infrastructure safeguards and fair-use/resource policy, Pro users may choose substantially larger/arbitrary research periods and conduct repeated experiments without the Free daily window gate.

Pro should primarily unlock:
- greater historical research capacity;
- more/larger saved experiments;
- advanced analytics/research;
- greater compute/storage quotas;
- advanced comparison/validation workflows;
- higher automation/AI allowances where applicable.

“Unlimited” in product copy must never override genuine infrastructure, licensing, abuse-prevention or fair-use constraints; those constraints must be transparent and must not falsify research results.

## UX continuity

Upgrading must not feel like switching to another trading application.

Chart, drawings, Quick/Planned workflows, Free/Protocol modes, order semantics and core navigation should remain structurally consistent. Entitlements unlock capacity/research surfaces in-place.

Upgrade prompts should appear at meaningful entitlement boundaries, not interrupt the user's first complete core backtesting experience unnecessarily.

## Integrity rules

1. Never degrade execution accuracy solely because the user is Free.
2. Never truncate an already-authorized open position in a way that changes its outcome merely to enforce a subscription boundary.
3. Never hide future candles visually while allowing the engine/indicator/rules layer to read them.
4. Never present a deliberately inadequate Free sample as statistically conclusive.
5. Never conflate subscription Free with trading Free Mode.
6. Entitlement checks control access/capacity; canonical domain engines control market/execution/research truth.
7. Pricing, exact quotas beyond the agreed daily tradable-window concept, reset mechanics and commercial packaging require separate product decisions.

## Intended product loop

```text
FREE
Choose market/context
    -> activate one-month tradable window
    -> use the real Backtest Lab workflow/engine
    -> complete trades/protocol
    -> receive Basic Statistics
    -> return on a later daily allowance or upgrade for greater research capacity

PRO
Same workflow/engine
    -> broader research periods
    -> repeated/larger experiments
    -> advanced research/analytics/compute
```
