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

Once locked, the protocol definition used by existing evidence must not be silently edited. If the user wants materially different rules, RR, risk or checklist definition, they create a **new Trading Method**. The product does not require Protocol versioning as a user workflow; prior Method evidence remains attached to the original immutable Method.

A Session inheriting a Protocol method does not ask the user to choose Free Style/Protocol again.

## Protocol checklist

A Protocol method must contain **at least one** user-defined checklist condition. The user may define one, five, or any supported number of conditions; the product does not impose a fixed checklist count beyond the minimum of one.

Checklist execution enforcement is a method-level setting that may be ON or OFF:
- **ON:** every checklist condition defined by the locked Protocol method must be satisfied before an order may be executed. Failure to satisfy any condition blocks execution at the protocol/domain validation boundary.
- **OFF:** the execution flow does **not** require or display the checklist as a pre-order step. Checklist enforcement does not block execution. The Method definition may retain its checklist configuration, but execution must not force checklist interaction while enforcement is OFF.

Checklist state must be captured with the trade/protocol evidence so Research can later analyze outcomes against conditions. There is no X-of-Y threshold model in the current product contract.

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

Protocol methods use **Planned execution only**. Quick Buy/Sell is not permitted under a Protocol method. A user who wants discretionary Quick execution should use a Free Style method.

Protocol follows the product principle **"plan your trade, trade your plan."** A Protocol trade must be submitted as a planned **pending order**. The user may choose a supported **Limit** or **Stop** pending order according to the setup; direct Market entry is not a Protocol execution path.

Once a Protocol position is triggered/open, **manual close is not permitted**. The planned lifecycle must resolve through the canonical preplanned exit/risk rules (for example SL/TP and other explicitly supported protocol terminal rules), rather than discretionary early closure.

The product must not ask the user to re-select the method type at Session creation. Protocol execution must preserve locked RR, locked risk and checklist enforcement at the domain-validation boundary, not only in UI controls.

## Session model

A Session is a persistent research container belonging to exactly one Trading Method.

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

Multiple Sessions may reference the same Trading Method.

Example:
- Breakout S/R v1 -> XAUUSD Session;
- Breakout S/R v1 -> EURUSD Session;
- Breakout S/R v1 -> GBPUSD Session.

Because the Trading Method identity is shared, Research may compare evidence across instruments, periods and Sessions while retaining each Session's feed, execution profile and dataset provenance.

This supports questions such as which instruments or market conditions show stronger evidence for a given method without conflating differently defined strategies.

## Persistent Sessions and segments

A Session persists beyond a single monthly entitlement segment and has **no product concept of "research finished."** Evidence may continue accumulating over time. The absence of a Finish state must not be interpreted as proof/validation of a strategy.

Within the same Session, appended monthly segments must proceed **chronologically**. A user cannot skip from an earlier completed segment to an arbitrary later month while preserving the same continuous Session equity path. A non-contiguous research period requires a separate Session/research context.

For Free entitlement, a later daily allowance may be used to continue an existing Session with another eligible monthly segment, or to create/use a different eligible Session according to the Subscription & Entitlement Specification.

A Session may therefore accumulate evidence over time. **Starting balance is set only when the Session is created. Thereafter balance/equity continues chronologically across appended monthly segments; continuation must not ask for or silently reset starting balance.** Prior evidence must remain immutable/reproducible when later segments are appended.

Pro may expose a long date range as one continuous research experience while the engine internally uses monthly or other deterministic segments for caching, checkpoints, recovery, integrity and compute. Internal segmentation must not force repetitive monthly UX on Pro.

## Research maturity

A Session/research body does not become scientifically valid merely because the user presses a Finish button.

The product may express evidence maturity using states such as:
- Early;
- Developing;
- Sufficient;
- Robust.

Maturity recommendations should consider multiple dimensions such as trade count, elapsed/tested time, coverage of relevant market conditions/regimes, and relevant data/execution quality. **Cross-pair/pair coverage is not a Research Maturity requirement.** A method intended for one instrument must not be penalized merely because it was not tested on unrelated instruments. Exact thresholds require later research/product validation.

The system must not claim a strategy is proven or valid solely because an arbitrary trade-count threshold has been reached.

## Session duplication, reset and evidence integrity

- Session duplication is not part of the intended workflow.
- Free entitlement does not provide Session reset/restart.
- **Session reset/restart is not a product workflow for any tier.** To rerun or start a separate experiment, create a new Session. This preserves provenance rather than rewriting accumulated evidence.
- If rules materially change, create a **new Trading Method** rather than mutating the evidence contract. Existing evidence-bearing Methods are not edited into a different strategy.

## Trading Method lifecycle

- A Trading Method that already owns Session/trade/research evidence must not be hard-deleted through the normal product workflow. It may be **Archived**, preserving all linked evidence and research integrity.
- A Trading Method with no evidence and no dependent research may be deleted.
- Archiving a Method does not rewrite or detach its historical Sessions.
- An Archived Trading Method cannot be used to create a new Session. The user must restore/unarchive the Method before using it for new research. Existing Sessions/evidence remain reviewable according to normal entitlement and retention rules.
- Material rule changes are represented by creating another Trading Method, not by editing the evidence-bearing Method or requiring a user-facing versioning workflow.

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
