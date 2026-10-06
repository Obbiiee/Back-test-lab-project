# Backtest Lab v2 Alpha — Execution, Financial & Evidence Contract v1

Status: **FROZEN PLAN CONTRACT**. Planning authority only until operationally authorized.

## 1. Scope and epistemic taxonomy

v2 Alpha distinguishes:
- `OBSERVED_FEED_EVENT`: a canonical provider quote/event actually present in the pinned dataset.
- `SIMULATED_FILL`: deterministic fill produced by Execution Profile v1 from observed feed events. It is never represented as an actual broker fill.
- `UNRESOLVED`: available evidence cannot establish a unique permitted execution outcome.
- `REFUSED`: command/data violates a contract and no financial event is committed.
- `LEGACY_MODELLED`: pre-v2 candle/scalar result retained as historical compatibility evidence.

Only `SIMULATED_FILL` changes the v2 simulated account. `OBSERVED_FEED_EVENT` alone never claims liquidity or broker execution.

## 2. Alpha instrument/profile boundary

Alpha precision execution supports only an instrument profile that supplies all of:
- canonical instrument XAUUSD;
- provider/feed identity;
- quote currency USD;
- account currency USD;
- positive exact tick_size;
- positive exact price_scale;
- positive exact contract_size;
- positive exact lot_step;
- min_lot and max_lot;
- ordered bid/ask evidence meeting the precision eligibility gate.

No FX conversion is performed in v1. A profile requiring non-USD conversion is `REFUSED_UNSUPPORTED_PROFILE`.

All canonical prices, quantities and money use scaled integers or Decimal/exact decimal strings at boundaries. Binary float is not financial authority.

## 3. Arithmetic

Let:
- `Q` = quantity in lots after lot-step rounding;
- `C` = contract_size units per lot;
- `P0` = entry price;
- `P1` = exit price.

Gross realized P&L:
- long: `(P1 - P0) * C * Q`;
- short: `(P0 - P1) * C * Q`.

Account currency is USD in Alpha, so no conversion term exists.

Money is calculated at full exact internal precision and rounded to the profile's money_scale only at a committed money event using **ROUND_HALF_EVEN**. Price inputs must already conform to tick_size; invalid price precision is refused, not silently rounded. Requested quantity is rounded **down toward zero** to lot_step for risk sizing; if below min_lot after rounding, refuse. User-entered explicit quantity not conforming to lot_step is refused.

Risk-sized quantity:
`floor_to_lot_step(risk_budget / (abs(entry-stop) * contract_size + per_lot_entry_exit_cost_budget))`.
The execution profile must expose the cost-budget terms used by the risk preview. If an exact cost cannot be known before execution, the preview labels the assumption/version.

## 4. Costs

Execution Profile v1 explicitly supplies:
- commission model: NONE or fixed USD per lot per side;
- slippage model: NONE for Alpha baseline;
- latency model: ZERO for Alpha baseline.

A profile may use nonzero fixed commission. Unsupported variable/tiered commission is refused rather than approximated. Commission is committed on each simulated fill side proportional to filled quantity. Spread is inherent in bid/ask and is not added again as a separate fee.

Future slippage/latency models require a new execution-profile version; they cannot silently change v1 history.

## 5. Command serialization

Each session is a single logical writer:
- every mutating command carries `session_id`, unique `command_id`, and expected `session_revision`;
- commands commit in server-authoritative serialized order;
- stale expected revision → REFUSED_STALE_REVISION;
- same command_id + byte-identical canonical payload → return prior committed result;
- same command_id + different payload → REFUSED_IDEMPOTENCY_CONFLICT;
- financial event append + resulting account/session revision commit atomically in one durable transaction boundary;
- retry after process failure uses durable command/event identity and cannot double-settle.

Workers may compute, but only the serialized session commit path advances financial truth.

## 6. Quote processing order

Canonical timeline order:
1. increasing event timestamp;
2. trustworthy provider sequence when supplied and declared valid;
3. otherwise source ordinal is retained only as evidence.

If multiple same-timestamp records lack trustworthy sequence and alternative order can change activation, SL/TP, exit, account or research outcome, processing stops for that affected execution path as `UNRESOLVED_EQUAL_TIME_ORDER`. The engine does not choose source ordinal as truth.

If alternative orders are outcome-equivalent, the common outcome may commit and the chronology limitation is recorded.

## 7. Market orders

A confirmed market command is eligible at the **first canonical quote event strictly available at or after the command's virtual-time availability boundary**.

- buy fills at observed ask;
- sell fills at observed bid;
- no interpolation;
- no fill before command availability;
- if no eligible quote before dataset/session end → EXPIRED/UNRESOLVED_NO_QUOTE, no fill.

The exact event reference is attached to SIMULATED_FILL.

## 8. Pending orders

Trigger and fill are evaluated on transaction side:

| Order | Trigger | Baseline fill |
|---|---|---|
| Buy Limit | ask <= limit | min(observed ask, limit) |
| Sell Limit | bid >= limit | max(observed bid, limit) |
| Buy Stop | ask >= stop | observed ask |
| Sell Stop | bid <= stop | observed bid |

Limit price improvement is allowed because the observed executable side is better than the limit; stop gap-through fills at the first observed transaction-side quote after trigger, not at the unobserved stop price.

A pending order cannot trigger before its committed activation revision/time. Cancel wins only if its serialized command commits before the triggering quote is processed. Otherwise the trigger/fill event wins and later cancel is refused as no longer pending.

## 9. Protective exits

For an active long:
- SL triggers when bid <= SL; fill = first observed bid.
- TP triggers when bid >= TP; fill = first observed bid.

For an active short:
- SL triggers when ask >= SL; fill = first observed ask.
- TP triggers when ask <= TP; fill = first observed ask.

Gap-through uses first observed liquidation-side quote; never the unobserved threshold. Within one trustworthy ordered quote event, a single liquidation-side price cannot simultaneously be both a valid positive-distance SL and TP for a valid position. If malformed geometry makes that possible, refuse the plan before activation.

## 10. Pending activation and protective exit on same event

After a pending entry triggers/fills on event E:
1. commit entry fill at E;
2. protective conditions are evaluated beginning with the same event E using the resulting position and liquidation side;
3. if the same observed quote establishes an immediately crossed protective threshold, the exit may commit on E;
4. this ordering is deterministic and recorded.

## 11. Partial/manual exit

Free Style supports manual partial/full exit. Protocol behavior inherits the frozen Trading UX contract.

- partial quantity must conform to lot_step and be >0 and < remaining quantity;
- full close may use exact remaining quantity even if legacy migration produced a non-step residual; such migrated residual must be explicitly labelled;
- exit uses first eligible observed liquidation-side quote at/after command availability;
- each exit has its own fill/cost event;
- realized P&L is proportional to exited quantity;
- remaining position retains original entry identity/price basis and accumulated entry costs are allocated proportionally by exact quantity;
- no closed-position summary exists until remaining quantity is zero; individual exit rows remain canonical evidence.

## 12. Protocol precedence

`docs/TRADING_METHOD_SESSION_SPEC.md` Frozen Trading UX Specification v1 is the product authority for Protocol behavior. Therefore Alpha Protocol is:
- Planned;
- pending Limit/Stop only;
- no Quick Protocol;
- no direct Market Protocol;
- locked risk/RR/derived size as defined there;
- checklist ON blocks unless all required conditions PASS;
- checklist OFF records actual NOT_ASSESSED/FAIL/PASS without inventing compliance;
- discretionary SL/TP intervention, early/manual/partial close on active fixed-RR Protocol position is refused;
- pending cancellation before trigger is permitted as abandonment evidence.

The newer Alpha documents may narrow infrastructure around this contract but do not broaden these rules without a human-approved contract revision.

## 13. Uncertainty propagation

If uncertainty can change a financial outcome:
- no affected fill/P&L/account mutation commits;
- affected order/position transitions to `UNRESOLVED` terminal research state;
- session may continue only for non-financial inspection/export; new financial commands are blocked until user forks a new session before the unresolved boundary;
- journal displays unresolved evidence, not a trade result;
- Passport records reason/evidence refs;
- performance metrics exclude unresolved items from denominators and report unresolved count separately;
- no “conservative” or “optimistic” substitution.

## 14. Rewind/fork

Before any committed financial event, backward navigation is allowed within revealed/authorized data.

After the first committed financial event:
- authoritative session cursor cannot move backward;
- “rewind” creates a **new forked session** with new session_id and lineage to parent + fork timestamp/revision;
- fork state is reconstructed only from parent evidence valid at/before fork point;
- parent remains immutable;
- reset that discards an uncommitted draft is allowed; committed financial history is never silently deleted/undone.

## 15. Transaction invariant

For every accepted financial transition, the durable transaction atomically records:
1. command dedup identity/result;
2. canonical event(s);
3. account projection revision;
4. order/position state;
5. session revision/cursor required to reproduce the commit.

Crash before commit → none visible. Crash after commit → all visible. Derived journal/research may be rebuilt from canonical events and cannot be the only copy of financial truth.

## 16. Golden examples required before engine code

X-1 is now **verification/materialization**, not product design. Tests must cover:
- market buy/sell next eligible quote;
- buy/sell limit with improvement;
- buy/sell stop gap-through;
- long/short SL and TP;
- activation + same-event exit;
- trustworthy same-time sequence;
- outcome-equivalent unsequenced tie;
- outcome-changing unsequenced tie → UNRESOLVED;
- stale command;
- duplicate identical command;
- duplicate conflicting command;
- cancel-before-trigger / trigger-before-cancel serialization;
- partial then full exit;
- fixed commission;
- invalid tick/lot precision;
- dataset end before eligible quote;
- worker crash before/after atomic commit;
- Protocol prohibited manual action;
- rewind → fork, never mutation.
