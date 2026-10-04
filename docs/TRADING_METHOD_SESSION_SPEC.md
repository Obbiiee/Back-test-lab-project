# Backtest Lab — Trading Method & Session Model Specification

Status: cross-phase product/domain authority. This document defines the intended Trading Method → Session research model. It does not by itself authorize runtime implementation.

## Core hierarchy

```text
User
  -> Trading Method
      -> Session
          -> Monthly Segment(s)
              -> Trades
                  -> Canonical Events
```

A backtest must belong to a Trading Method. Trading Method defines what style/rules are being researched; Session defines a concrete research context such as instrument/feed/start period/account.

Research may aggregate evidence upward from Trade → Segment/Period → Session → Instrument → Trading Method, while preserving provenance.

## First-use onboarding

If a user has no Trading Method, the primary onboarding path is:

Register/Login -> Create First Trading Method -> choose Free Style or Protocol -> configure/create method -> Create Session -> Backtest Workspace.

Once at least one method exists, normal Dashboard/session flows replace first-method onboarding.

## Trading Method types

### Free Style

A Free Style method represents discretionary trading.

- Method has an identity/name and may have descriptive metadata.
- RR and risk are not protocol-locked by the method.
- Quick Trade and Planned Trade are both available in the workspace when otherwise supported.
- User actions remain recorded in the canonical ledger so discretionary behavior can still be analyzed.
- Free Style is a trading-method type and is unrelated to Free/Pro subscription entitlement.

### Protocol

A Protocol method represents rule-constrained research.

At minimum, creation requires:
- method name;
- locked RR;
- locked risk per trade;
- at least one checklist condition.

Once locked, the protocol definition used by existing evidence must not be silently edited. Material changes require a new method/protocol version so prior evidence remains reproducible.

A Session inheriting a Protocol method does not ask the user to choose Free Style/Protocol again.

## Protocol checklist

A Protocol method must contain at least one checklist condition.

Checklist state must be captured with the trade/protocol evidence so Research can later analyze outcomes against conditions.

**OPEN PRODUCT DECISION:** the exact enforcement semantics are not yet frozen. Do not invent whether every Required item must pass, whether a configurable minimum X-of-Y is sufficient, or whether both concepts coexist. This requires explicit human approval before implementation.

## Locked RR behavior in Planned Position tools

For a Protocol method, the Long/Short Position planning tool must actively help preserve the locked RR.

Example for a long trade with RR 1:1:
- user establishes Entry and SL;
- the planner derives TP from Entry-to-SL distance and locked RR;
- moving SL recomputes TP so RR remains 1:1;
- moving Entry recomputes dependent geometry according to the canonical planner rules;
- TP must not be freely manipulated into a value that violates the locked protocol.

For Free Style methods, supported Entry/SL/TP geometry remains discretionary.

UI locking is not the enforcement boundary. Before execution, the canonical Order Request must pass protocol/domain validation. A request that violates the locked RR must be blocked even if it bypasses normal UI controls.

## Locked risk behavior

Protocol risk per trade is fixed by the method version.

Given account/equity basis defined by the Risk Engine and a user-defined Entry/SL distance, the planner/risk engine derives the permitted position size so the intended risk remains consistent with the locked protocol, subject to instrument/execution constraints such as tick size, contract size, lot step, minimum/maximum lot and applicable costs.

Changing stop distance changes derived size rather than silently changing the protocol risk target.

## Order methods

Free Style methods may use both Quick and Planned order methods in the same workspace when supported.

Protocol order-method behavior must follow the locked protocol definition. The product must not ask the user to re-select the method type at Session creation.

Any future decision about whether a Protocol version locks one order method, permits multiple order methods, or applies per-action policy must be represented explicitly in the protocol contract rather than inferred by UI.

## Session model

A Session is a persistent research container belonging to exactly one Trading Method/version.

At creation, target inputs include:
- Trading Method;
- Session name;
- one instrument/pair;
- one immutable feed/provider identity for that Session;
- user-defined starting balance;
- starting historical month/period.

Timeframe is not locked at Session creation. The user may switch supported timeframes inside the workspace while all no-look-ahead and multi-timeframe rules remain intact.

One Session is bound to one instrument/pair. Testing the same Trading Method on another instrument requires another Session.

Feed/provider identity cannot be changed mid-Session. A different feed requires a separate research context rather than silently mixing evidence.

## Cross-session and cross-instrument research

Multiple Sessions may reference the same Trading Method/version.

Example:
- Breakout S/R v1 -> XAUUSD Session;
- Breakout S/R v1 -> EURUSD Session;
- Breakout S/R v1 -> GBPUSD Session.

Because the method/version identity is shared, Research may compare evidence across instruments, periods and Sessions while retaining each Session's feed, execution profile and dataset provenance.

This supports questions such as which instruments or market conditions show stronger evidence for a given method without conflating differently defined strategies.

## Persistent Sessions and segments

A Session persists beyond a single monthly entitlement segment.

For Free entitlement, a later daily allowance may be used to continue an existing Session with another eligible monthly segment, or to create/use a different eligible Session according to the Subscription & Entitlement Specification.

A Session may therefore accumulate evidence over time. Prior evidence must remain immutable/reproducible when later segments are appended.

Pro may expose a long date range as one continuous research experience while the engine internally uses monthly or other deterministic segments for caching, checkpoints, recovery, integrity and compute. Internal segmentation must not force repetitive monthly UX on Pro.

## Research maturity

A Session/research body does not become scientifically valid merely because the user presses a Finish button.

The product may express evidence maturity using states such as:
- Early;
- Developing;
- Sufficient;
- Robust.

Maturity recommendations should consider multiple dimensions such as trade count, elapsed/tested time and coverage of relevant market conditions/regimes. Exact thresholds require later research/product validation.

The system must not claim a strategy is proven or valid solely because an arbitrary trade-count threshold has been reached.

## Session duplication, reset and evidence integrity

- Session duplication is not part of the intended workflow.
- Free entitlement does not provide Session reset/restart.
- Reset/restart may be a paid entitlement, but must preserve research-integrity semantics and must not silently rewrite historical evidence.
- If rules materially change, create/version the Trading Method/Protocol rather than mutating the evidence contract.

## Sharing

A Session Overview/Report may support a read-only share link before the full Community product exists.

Sharing must not mutate the source Session and must respect privacy, entitlement and data-rights constraints.

## Separation of concerns

Trading Method type (Free Style/Protocol) is independent from subscription tier (Free/Pro).

Do not conflate:
- Free Style with Free subscription;
- Protocol with Pro subscription;
- Session with Trading Method;
- monthly entitlement segment with Session lifetime;
- planner geometry with executed account state.
