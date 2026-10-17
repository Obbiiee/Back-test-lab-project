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


## Additive local conversion foundation — 2026-10-17 (not execution v1)

Human-approved sixteen-symbol local engineering includes an unmounted exact quote-currency-to-USD primitive. Existing system blueprint section Causal USD conversion foundation owns this additive seam's complete-group, causal, identity, quality and sign/side/rounding rules. It does not amend any frozen v1 profile, reducer, financial command, ledger entry or old Session hash, and is not a settlement/evidence eligibility authority. A later versioned controller/financial checkpoint must prove accepted conversion-source membership, complete causally selected groups, durable quote/route identity, risk/partial-close/cost semantics and unchanged v1 goldens before integration. Imported Dukascopy UNKNOWN evidence remains unresolved, not upgraded by this helper or a recent timestamp.


## Additive Beta execution v2 design — separately versioned, not implemented (2026-10-17)

This is a concrete proposal under the existing contract owner. All normative v1 rules remain frozen. Human requested the paid-Beta journey and sixteen symbols; the latest human instruction explicitly continues the Beta engineering journey. Implement this as separately validated additive v2 checkpoints, without rewriting frozen v1. Repository instruction still requires stopping if an actual frozen v1/42.17/42.19 rule must change. A new version must not migrate or reinterpret old Session/profile/event hashes.

1. **Version dispatch and scope.** Add a separate v2 engine/profile/state/event/receipt family. Dispatch by persisted engine version, never by currently selected symbol or request flag; unknown versions refuse. Existing v1 commands and Sessions remain on the existing exact reducer/goldens. New v2 Sessions select exactly one of the16 catalogue symbols and USD account currency. No simultaneous portfolio replay, native non-USD accounts, triangulation or broker-fill claim. Authenticated workspace ownership and durable review/confirmation remain mandatory. Catalogue does not establish provider eligibility.
2. **Profile pin.** Version2 profiles explicitly pin canonical symbol, base/quote/account currencies, source provider/feed/instrument, represented price precision, tickSize/priceScale, contractSize, lotStep/min/max, moneyScale, cost currency/model/rate, slippage/latency model, and optional conversion source/route/maxAge. Reject unknown fields, implicit provider defaults and unsupported precision. For authored sandbox FX only, propose100000 base units per simulated lot, labelled SIMULATED_LOT_CONVENTION; this is not a broker specification or screenshot Value Pair. Operator/source-specific parameters must be explicit/pinned before any actual dataset use. Existing XAUUSD profile remains unchanged. Fees remain exact USD under the proposed initial model; foreign-denominated fee models refuse rather than silently reuse a P&L quote.
3. **Source acceptance and causality.** Register primary and conversion datasets controller-side, pin complete immutable source/version/evidence identities before Session creation. Primary and conversion sources must each pass their existing acceptance boundary. Do not turn group hashes, operator labels, monotonic timestamps or source age into authentication/freshness proof. Frozen42.19 V2 coverage stays UNKNOWN without a separately authorized causal evidence contract; real imported UNKNOWN data therefore remains unresolved. Only authored synthetic completeness/freshness fixtures can initially qualify the v2 sandbox path. Provider/storage/index/EOF/unrestricted sidecars never enter a consumer view.
4. **Selection algorithm.** At each eligible primary atomic timestamp group t, process the conversion timeline only through t. Finish all bounded continuation pages to that boundary before using its latest complete group; never infer latest selection from one caller row. Select the greatest complete conversion timestamp <=t; retain the entire group, its acknowledged timeline prefix and pinned evidence. Never select a price from a future group or retry using an older good group after the latest group is invalid. Differing quotes at an equal timestamp remain conservatively ambiguous, including trusted-sequence groups. Equivalent prices retain all event refs and original order trust. Staleness uses exact ns and profile-pinned1ns..60s maximum; UNKNOWN freshness/gaps never become confirmed because the quote is recent. All loops/pages/groups/bytes have explicit frozen-compatible bounds; budget exhaustion yields unresolved without partial publication.
5. **Conversion and precision.** Existing unmounted conversion foundation supplies signed direct/inverse Bid/Ask and exact rational units. GBP/NZD use direct USD pair BID for gains, ASK for losses; JPY/CAD/CHF use inverse ASK for gains, BID for losses. USD is identity. Compute gross in the instrument quote currency, preserve exact rational gross/conversion/cost allocations, then round at the explicitly versioned USD ledger posting boundary using half-even. Partial closes allocate original entry costs by exact units with the final close receiving the exact remainder; no per-event rounded subtotal is later relabelled exact. Session ledger and statistics reconcile from the same posted events; unrealized marks stay distinct from realized cash.
6. **Risk and intent.** USD risk budgets cannot be divided directly by a foreign quote-currency stop distance. A reviewed intent pins its causal conversion evidence and calculates adverse signed stop loss including supported costs in USD, with lot-step floor and exact bounds. Confirmation checks Session/review/profile/route/evidence identities and revisions; price/evidence changes invalidate the intent. Missing/unknown/stale/ambiguous conversion yields no executable intent. Protocol restrictions and manual-action/partial-close permissions remain enforced. Never estimate with candles or use a future stop-time rate as entry-time knowledge.
7. **Atomic durable receipt.** A v2 transaction binds command/idempotency identity, predecessor/successor state and event hashes, primary checkpoint, every used conversion checkpoint/group/event ref, conversion convention/profile hashes, asOf times, exact quote-currency and converted values and posted USD deltas. PostgreSQL commits all acknowledged financial transitions and checkpoint references together under existing workspace locks/revision checks. On failure, no acknowledged half-converted fill or orphan financial receipt. Provider/timeline speculative logs are not financial authority; a retry reconstructs only from acknowledged pins. Same command ID plus different intent/evidence refuses; identical retries return the same receipt.
8. **Unresolved policy.** When primary execution would need unavailable conversion evidence, record an explicit UNRESOLVED reason and affected order identity under the new contract; never post a guessed USD amount. Exact commit semantics for cursor/event progression are frozen by authored vectors before implementation: quote revelation may be acknowledged with an unresolved event, while no simulated fill/cash posting occurs. Consumer receives only bounded revealed reasons, not future presence/EOF/sidecar details. No silent fallback to USD, old source, OHLC, latest wall-clock quote or last raw row.
9. **Cold recovery/fork.** Persist version/pins with immutable Session identity. Cold read, retry, process death before/after commit, dataset substitution, logout/revocation and fork must reproduce exact posted cash and source proofs. Fork retains parent version and proofs; conversion versions do not silently upgrade. Browser/cache projections never choose the engine or restore speculative financial state. Legacy rollback leaves all v1 Sessions untouched.
10. **Acceptance before mounting.** Author literal independent vectors for16 symbol identities, signed direct/inverse rates, risk sizing, entry/exit/partial/cost allocation, stale/missing/gapped/unknown/equal-time cases, future mutation and simultaneous primary/conversion timestamps. Test real provider/timeline selection (including >one page), cold restore, authenticated foreign-workspace refusals, idempotent concurrency, worker death at both commit boundaries, native empty-target dump/restore, and v1 golden byte/hash invariance. Full zero-skip backend/frontend/build/distribution/bundle and real browser Session review/confirm/replay/journal/cold restore are required for a mounted checkpoint. No paid external Beta label until existing capacity/reference/recovery/security/data rights/identity/payment/cohort/HTTPS gates pass.

**Implementation boundary:** latest human Beta journey grant covers additive v2 engineering with authored synthetic evidence, preserving every frozen v1 and42.17/42.19 rule. It does not authorize changing old contracts, promoting real source rights/quality, buying services, fabricating Google/payment acceptance or public launch. Freeze and validate literal vectors per additive checkpoint before mounting.


### Authored v2 financial proposal materialization — 2026-10-17

Next additive checkpoint materializes exact entry-cost/exit-value/risk proposals for immutable synthetic profiles, without Session mutation, reducer dispatch or financial commit. Primary quote evidence is a complete pre-accepted atomic group at exactly decision time, matching primary pins; differing prices, invalid quality or missing evidence refuse. Quote hash alone cannot authenticate source membership. Entry buys at Ask for LONG/sells at Bid for SHORT; exit uses opposite side. Values use source precision/tick grid and bounded exact quantities, never candle paths.

Exit gross is exact quote-currency (signed exit-entry x simulated contract x lots), converted once using the pinned causal convention. Posted USD gross and exit commission each round once half-even. Cash delta equals those posted values; entry costs have already been posted, so are not subtracted twice. Exact rational values/evidence remain alongside posted values. Net including allocated entry costs remains a separately derived reporting value, not another cash posting. Entry-cost allocation proves closed-before and allocation-before match the original posted cost/quantity; the last close receives the exact remainder. No arbitrary caller allocation can become financial authority.

Planned risk converts a negative one-lot stop loss using decision-time FX, adds both USD commissions and floors to lot steps. It is a model estimate, not a stop-fill/budget guarantee under gaps or later FX movement. Check proposed size against its hypothetical posted stop loss/fees. If rounding alone exceeds budget, recompute conservatively with up to half a USD minor unit per rounded component reserved (gross plus two fees when enabled); at most two candidate evaluations, no unbounded decrement loop. Refuse invalid geometry, insufficient size or unsupported bounds rather than silently clip or fabricate evidence. No future stop-time exchange rate is used to size entry. Actual intent/Protocol/controller/transaction acceptance remains mandatory before these proposals can be mounted.


### Synthetic v2 state and native receipt integration - 2026-10-17

The additive kernel_v2/controller_v2/postgres_v2 family implements bounded authored synthetic Session transitions. Frozen v1 runtime, vectors, physical schema and42.17/42.19 remain unchanged. Literal execution_v2.json fixes all16-symbol outcomes, inverse short loss, partial fees and Protocol sizing before reducer implementation. Real offline imports and UNKNOWN disk-source coverage are not execution eligible. No public HTTP dispatch, Google/payment acceptance or frontend cutover belongs to this checkpoint.

OPEN obtains conversion proof only at the acknowledged primary clock. FreeStyle preserves requested quantity with its own risk estimate; Protocol additionally requires the step-floored recommendation, fixed risk/RR, planned geometry and checklist. Market/limit/stop activation and opposite-side protective/manual/partial exits require complete primary groups. Non-equivalent equal-time quotes that can change finances remain unresolved. Each complete group is speculative together: failed FX/model evidence never publishes a half-fill. END never invents exits. Exact fee allocation and separate posted gross/fees reconcile cash. Compact financial proof hashes and pinned dataset/version/group references bind full evidence without duplicating whole source groups per fill.

Existing opaque tick tables store version-tagged snapshots, commands, events and checkpoints. A repeatable read validates scope, prior receipt and revision. Source acceptance/recovery, FX joins and arithmetic occur outside the financial row lock. The short write transaction rechecks receipt/revision/prepared-state hashes, validates event chaining and cash/gross/fee deltas against simulated-fill postings, then atomically commits all financial records. Publication follows COMMIT. Identical retries return the receipt before provider work, including source outage; conflicting reused IDs refuse. Fork inherits historical profile/source identity and leaves its parent unchanged. Only bounded state/events are projected, never private checkpoints/provider/sidecar handles.

Native acceptance covers all literal symbols, cold reconstruction, concurrent dedup/CAS, workspace refusal, restricted runtime, process death at both commit boundaries and dump/empty-target restore. This remains internal synthetic integration. Browser verification is deferred to the next mounted authenticated Session/review/journal checkpoint because no product route changed. SEEK and full product acceptance are not claimed. Bounded authored recovery logs and per-request reconstruction are not long-history capacity certification.


Checkpoint validation: full backend418/zero skips/789.698seconds on fresh isolated SCRAM PostgreSQL, native recovery and normal shutdown. Final native10/zero skips/41.752seconds after strengthening test-only fixtures: crash before/after COMMIT now crosses an actual EURGBP exit converted to USD12000; dump/empty-target restore preserves a funded closed AUDUSD receipt/cash11000. Baseline frontend regression/lint/build/release, repository/bundle and independent Node6x3/16profile vectors pass. Initial full discovery failed because a newly appended test method sat below the module entry point; fixed test placement, without weakening runtime. A new gap fixture initially put SL at entry Bid, correctly causing an immediate exit; corrected its intended input to test the later quote, keeping separate gap-beyond-stop coverage. No performance/reference/browser/SaaS acceptance is inferred.
