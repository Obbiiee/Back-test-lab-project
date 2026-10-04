# Backtest Lab — Trading Modes, Strategy Rules & Lab Protocol Specification

> **CURRENT AUTHORITY NOTICE:** Free Style / Protocol is a **Trading Method type**, not an independent per-trade Trading Mode. The canonical product model is defined in [Trading Method & Session Model Specification](TRADING_METHOD_SESSION_SPEC.md). Any conflicting legacy wording below is superseded. Free Style may use Quick or Planned execution. Protocol is Planned-only, must submit a pending Limit or Stop order, does not permit direct Market entry, and does not permit discretionary manual close after trigger. Protocol follows "plan your trade, trade your plan." Domain/rules validation must enforce these constraints.

> Trading Method ownership, Session inheritance, locked RR/risk planner behavior and cross-session research are defined in [Trading Method & Session Model Specification](TRADING_METHOD_SESSION_SPEC.md). Free Style/Protocol trading behavior is independent from Free/Pro subscription entitlement.

Status: architecture authority for future trading/rules/research work. This document does not authorize implementation.

## Two independent dimensions
Trading Mode: FREE | PROTOCOL.
Order Method: QUICK | PLANNED.

These dimensions are independent and all supported paths converge on one canonical execution pipeline.

## Free Mode
Discretionary backtesting. Supported modifications/interventions may be performed. Every action still enters canonical history/ledger so later analysis can explain what the trader actually did.

## Protocol Mode
An experiment/strategy protocol governs behavior. Each governed action resolves to:
- ALLOW
- BLOCK
- TRACK_VIOLATION

BLOCK must be enforced by domain/rules validation, not merely disabled CSS. TRACK_VIOLATION executes when otherwise valid but records violation provenance.

## Quick Trade
Designed for minimal-interaction entry: BUY/SELL -> order/position -> supported SL/TP and management afterward. In Protocol Mode it exists only when the protocol permits the required workflow.

## Planned Trade
Long/Short Position -> Entry + SL + TP -> risk -> calculated size/RR -> review -> PLACE ORDER. The position object is Trade Planner + Risk Calculator + Order Creator. PLACE ORDER emits the same canonical Order Request used by Quick Trade.

## Strategy rules
The model should accommodate Setup, Inclusion, Exclusion, Entry, SL, TP, RR, Risk, Session, Max Orders, Early Close, Partial Close, Move SL, Move TP, Cancel Order and Intervention policy.

Protocol examples may lock fixed RR/risk and prohibit early close/intervention. Exact strategy values are experiment configuration, not universal product defaults.

## Lab Protocol
Before a formal experiment, lock or version as applicable:
Hypothesis; Strategy Version; Dataset Version/identity; Period; Sample Target; Inclusion/Exclusion; Entry/SL/TP rules; RR; Risk; Session; Execution Profile; Intervention Policy; Stopping Rule; relevant engine/calculator versions.

Material changes after lock create a new protocol/experiment version rather than rewriting prior evidence.

## Compliance research
Ledger/trade evidence should support COMPLIANT / VIOLATION classification and the rule/action involved, enabling analysis of protocol-compliant trades versus discretionary violations without falsifying the original experiment.

## Enforcement path
```text
Trading Mode
    ↓
Order Method
    ↓
Canonical Order Request / Action
    ↓
Strategy Rules + Protocol Validation
    ↓
Execution Engine
    ↓
Canonical Trade/Event Ledger
    ↓
Journal / Analysis / Research
```

## UX
Protocol restrictions must explain the reason for a blocked action. UI can guide and prevent mistakes but is not the security/correctness boundary. Do not invent additional trading modes/order methods without an explicit product decision.
