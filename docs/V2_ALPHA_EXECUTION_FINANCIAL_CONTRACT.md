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


### Scoped engine2 Session/review/journal service freeze - 2026-10-17

Within the existing authenticated Session integration grant, first materialize a server-private service with TrustedScope and separate immutable engine2 metadata/reviews plus mutable journal notes. Do not mount HTTP or change Claude UI in this foundation. Existing immutable Method records/validator are shared; v1 metadata/catalogue must not encounter v2 Session records. Server-owned16-symbol short authored fixtures are explicitly not one month of acquired history. Source/profile pins are selected server-side; changing registry versions never rewrites an existing Session. Session core plus metadata creation is atomic/idempotent and exact initial money cannot silently round. Creation starts at revision0 without hidden warming/financial actions.

Review artifact2 binds command2, method/profile, current revision/clock and the immutable basis checkpoint hash. Validate source/risk outside the financial row lock; recheck exact basis before the short immutable review insert. DB constraints bind the basis checkpoint and prevent review creation after command confirmation. A review is not an accepted order/fill. Confirmation accepts only stored review identity/hash, verifies proposed risk equals the frozen review before financial commit, and publishes the original durable receipt plus separately reconciled current view. Identical retries return the old receipt without resetting current state; changed hashes, stale revisions, forged scope/source/profile and retrospective reviews refuse. Raw OPEN/FORK are not product service commands; old private engine diagnostics remain unchanged. No new reset/duplicate workflow.

Confirmed R0 enrichment joins only immutable reviews with matching committed command hash/revision and matching accepted order risk at one coherent read snapshot; never derive R0 after entry. Notes preserve canonical Session/dataset/order identity and optimistic note revisions, bounded text/tags/count, and never modify the financial ledger. Display data is a bounded already-revealed primary prefix only; source display failure leaves committed evidence accessible with explicit unavailable display, never guessed data or an assertion that an acknowledged command rolled back. Runtime/schema/native crash/restore/restricted-role/scoped gates remain mandatory. Verified HTTP membership/entitlement, browser cutover, actual Google/payment/real-data acceptance remain dependent checkpoints, not claims from TrustedScope fixtures.

Authored independent service outcome before implementation: EURUSD fixture Bid/Ask at t0=1.1/1.10002, t1=1.10005/1.10007, t2=1.1001/1.10012. LONG0.01 lot, planned entry1.10002/SL1.09902, zero USD fees pins R0=1USD before fill. Actual entry t1 Ask1.10007 and exit t2 Bid1.1001 yield posted net0.03USD, final10000.03 and R=3/100. Do not change this literal to match implementation.


The v2 service preserves existing review UX semantics: the immutable raw request hash controls review retry identity; MARKET reference entry is derived server-side from the latest eligible revealed Bid/Ask. Protocol derives its fixed risk/RR target and optional recommended quantity, and fills missing checklist outcomes only as NOT_ASSESSED; it never fabricates PASS. FreeStyle supplied quantity is preserved. Canonical command values are materialized before immutable review/confirmation. Note retries with the exact prior expected revision/text/tags return the existing note without incrementing its revision. Financial commands return their durable receipt alone; callers fetch the current view separately, avoiding both stale receipt rewind and a display outage falsely appearing to roll back a commit.


Scoped engine2 service acceptance (2026-10-17): Full431 backend/zero skips/752.775seconds on fresh isolated SCRAM PostgreSQL with normal shutdown PASS; focused6/zero skips/33.170seconds PASS. Baseline frontend regression/lint/build136/release, independent Node6x3/16profile references and repository/bundle PASS. Covers16 pinned demo Sessions, exact0.03USD/3/100R, cold source-outage receipt/journal parity, concurrent review/confirm, hostile workspace/hash/stale/raw-command refusal, Protocol checklist, atomic Session/review rollback, restricted runtime/DB guards and funded empty-target restore. Existing full-suite worker-death financial gates remain passed. No HTTP/UI cutover, acquired market month, Google/payment-provider or paid Beta acceptance. Initial test used the wrong response balance level; corrected assertion to account.balance without runtime weakening. Windows npm wrapper initially failed before regression; direct existing Node entrypoints passed.


## Historical observation model review — 2026-10-26 (PROPOSED, NOT FROZEN)

The continuous XAU2024 target authorizes source-binding work, but does not itself supply provider completeness/freshness evidence or amend section13. Current raw HF ticks have UNKNOWN freshness/gaps/coverage; existing engine2 accepts authored synthetic sources only. A structural publication and bit-perfect source parity cannot establish those missing facts. Under the frozen strict model, uncertainty affecting an order must remain UNRESOLVED with no affected fill/PnL/account posting. This review grants no runtime exception or source-quality promotion.

Concrete owner decision for the next financial checkpoint: retain strict behavior and implement historical observation/replay with explicit unresolved trading, OR separately authorize a new persisted engine/model family for CONDITIONAL_OBSERVED_TICK_SIMULATION. The latter operates only on actually recorded Bid/Ask events in their accepted timestamp groups, with its assumptions attached to every Session/result; it never claims complete market history, provider freshness, liquidity, broker execution or eligibility under the existing strict model. Canonical dataset identity, event IDs, source bytes/precision/provenance/UNKNOWN quality and42.17/42.19 projections stay unchanged. No old profile, Session, result or hash is reinterpreted.

Proposed explicitly simulated baseline for review: XAUUSD/USD account,100units per simulated lot,0.01lot step/minimum,100lot maximum,2decimal USD postings with existing half-even arithmetic, zero commission/slippage/latency. Represented price grid0.001/scale1000 reflects the measured serialized research source, not a broker minimum tick. These are model assumptions, not independently evidenced broker terms. Each assumption, source version and model policy must be hashed into its new profile. Actual orders/prices remain exact; no OHLC settlement or invented intrabar path. Ambiguous equal-time outcomes remain unresolved. Recorded silences exceeding an explicit60second research gap guard make affected live orders/positions unresolved; shorter unknown intervals remain disclosed as conditional observation assumptions, never upgraded source coverage. Results/metrics must distinguish conditional simulations from strict accepted execution and separately report unresolved items.

Before implementing that conditional branch, owner authorization must expressly approve this financial-model exception/version. Then freeze the new family under this owner, author independent literal goldens and prove old-model byte/financial/uncertainty parity, durable causal checkpoint/receipt recovery, exact risk/cost arithmetic, actual full-source pin/parity, browser persistence and per-user measurements before mounting. No production deployment or rights acceptance follows from model approval. Until approval, only source publication/parity and other already authorized nonfinancial prerequisites proceed.


## Conditional observed-tick simulation — owner-authorized amendment (2026-10-27, FROZEN)

### Authorization and precedence

The owner was explicitly told the five remaining stages, including historical order/PnL integration, and that a separate model required explicit permission under the frozen-contract rule. The owner's next instruction was **"kerjakan sampe 5"**. In that immediate context this authorizes implementing stages1–5 and the separately proposed conditional simulation, rather than another request to implement only nonfinancial helpers. Record this scope; do not claim the owner attested broker terms, source coverage/rights or production deployment. This amendment activates the existing proposal only for the NEW family below. Section13 and existing v1/v2 profiles, canonical bytes, hashes, Sessions and strict refusal behavior remain unchanged.

### New immutable model family

- engineVersion `BTL-TICK-EXECUTION-OBSERVED-1` and model `CONDITIONAL_OBSERVED_TICK_SIMULATION`; separate profile/state/event/command/result artifacts and dispatch. No synthetic relabel, transparent old-row migration or old-profile admission widening.
- Canonical symbol XAUUSD, USD quote/account, simulated contract100units/lot, lot step/minimum0.01, maximum100, tickSize0.001/priceScale1000, moneyScale2 with existing exact ROUND_HALF_EVEN. Zero commission/slippage/latency is an explicit simulation assumption, not broker evidence. No FX conversion.
- Prices and quantities remain exact decimal strings/Fractions/scaled values. Off-grid or excessive precision is refused/unresolved, NEVER silently rounded, truncated or changed at ingestion. This restriction may leave HF quotes unresolved; source fidelity takes precedence over obtaining fills.
- Profile content/hash binds all assumptions, explicit60,000,000,000ns observed-silence guard, exact canonical dataset ID/version/provider/feed/instrument/symbol and PROVIDER_OBSERVATION evidence class. Accept only an operator-selected qualified source; structural publication alone remains insufficient. HF2024 and Exness2025 identities are separate and never spliced/aliased or silently crossed by a Session.
- Every Session/result/event/export carries the new family/profile/model identity; analyses distinguish conditional simulated results, refusals and unresolved orders. UNRESOLVED entries never become zero-PnL completed trades or disappear from denominators without explicit accounting.

### Profile wire freeze

`BTL-OBSERVED-EXECUTION-PROFILE-1` has EXACT keys: schemaVersion, artifact, engineVersion, model, symbol, baseCurrency, quoteCurrency, accountCurrency, primary, conversion, tickSize, priceScale, contractSize, lotStep, minLot, maxLot, moneyScale, commissionModel, commissionPerLotSide, commissionCurrency, slippageModel, latencyModel, maxObservedSilenceNs. schemaVersion=1, baseCurrency=XAU, conversion=null and every numeric/cost/model value is exactly the fixed canonical assumption above (silence is the decimal string60000000000). primary has EXACT keys datasetId, datasetVersion, providerId, feedId, feedInstrumentId, providerSymbol, evidenceClass; providerSymbol=XAUUSD/evidenceClass=PROVIDER_OBSERVATION, valid non-synthetic IDs and64lowercasehex datasetVersion. Profile bytes are existing BTL-CJSON-1 bounded to16384bytes; profileHash=SHA256 of those exact bytes. No optional/default/unknown keys, numeric coercions, booleans or source quality fields. Codec validity is not source qualification/admission.

### Evidence and causal behavior

Operate solely on recorded revealed Bid/Ask atomic timestamp groups. Raw UNKNOWN freshness/coverage/gaps, source precision/provenance/event IDs/duplicates and trustedSequence=null remain unchanged in source storage AND execution inputs. There is no manufacture of CONFIRMED/DECLARED_COMPLETE evidence, synthetic manifest or source admission. The model conditionally assumes the usable observations within its stated guard suffice for its recorded-event simulation; it never claims complete underlying markets, liquidity, broker fills or independent ordering.

Use existing side/direction rules: long entry Ask and liquidation Bid; short entry Bid and liquidation Ask; pending trigger/fill and same-event protective semantics follow sections8–11. First observed eligible quote determines gap-through fill, never an unobserved threshold or candle path. Fixed Protocol restrictions and exact risk/quantity/partial allocation/half-even postings remain those of existing financial owners.

If an outcome-affecting non-identical equal-time group cannot establish one permitted financial outcome, mark affected pending/active positions UNRESOLVED with no fabricated fill. Identical quote groups may yield one common outcome while preserving all canonical members and recording the full group identity; this is not deduplication or trusted row ordering. Non-identical groups with provably no financial action retain an explicit chronology limitation. Invalid/crossed quotes, declared stale/invalid evidence, outcome-affecting diagnostics and incompatible precision remain unresolved/refused rather than conditionally accepted.

The explicit silence guard uses only observations/revealed time already available to the controller. A live pending/active order that encounters more than60seconds without a usable observed quote becomes UNRESOLVED before any subsequent fill; known session-closure metadata does not silently waive this model guard. Advancing revealed time past that guard without a quote also makes live exposure unresolved. Risk preview/market basis must use an already revealed unambiguous quote not older than60seconds at command availability; missing/stale/ambiguous basis refuses, never reads ahead. Do not resolve historical uncertainty retroactively from future groups, EOF, future gaps or calendar schedules. A new Session/start is explicit; unresolved prior history is never reset in place.

All42.17/42.19 bounds, atomic timestamp groups, causal clipping and controller-only provider/storage/index/EOF/sidecar capabilities stay frozen. Durable indexed checkpoints and immutable receipt/event hashes replace neither source admission nor financial CAS. Keep bounded work/page/event/order limits and serialized revision/idempotency semantics; do not merely raise256-step/source-history limits to pretend annual continuation works. New-family Session persistence must support bounded durable continuation without replaying an ever-growing list of advance targets.

### Implementation and acceptance sequence

1. Freeze this amendment, independent literal profile/arithmetic/ambiguity/gap goldens and exact family identity before runtime implementation; normal document/repository/bundle/diff/Git closure.
2. Implement separate profile/model and pure reducer/math without changing old v1/v2 admission; prove literal hashes, long/short Bid/Ask, exact risk/lot rounding, half-even and cost assumptions, gaps/ties/precision/refusal/no-look-ahead and old-model byte/financial parity.
3. Bind qualified readonly historical source and causal indexed checkpoint, transactional receipts/recovery/retries/concurrency/tenant isolation and event-derived analysis. Complete representative actual-source financial proof before mounting.
4. Integrate existing Method/Session/catalog/chart/order/review/confirm/journal/analysis/reload with explicit reference-OHLC provenance; run actual desktop/mobile historical browser journeys and failure/cold recovery cases. Do not add a third UI or describe a helper as hosted acceptance.
5. Complete annual2025canonical intake/parity under explicit resource/source pins, full2024parity, sustained representative historical capacity measurements and numerical budgets under the existing capacity owner. Cost/user requires the actual bill; if absent, retain UNKNOWN and a measured-capacity formula, not an invented charge. Rights, privileged production-backup/installer verification and the owner's explicit production-switch approval remain independent release gates. Stage5 authorizes measurement/release preparation, not a production restart or symlink switch.


### Separate pure reducer implementation boundary — 2026-10-27

The first reducer checkpoint remains controller-private and UNMOUNTED. New artifacts are BTL-OBSERVED-EXECUTION-{SEED,STATE,COMMAND,EVENT,CHECKPOINT}-1, with the frozen engine/model/profile identity. Commands have schemaVersion/artifact/sessionId/commandId/expectedRevision/kind/payload; supported pure intents are OPEN,CANCEL,CLOSE,ADVANCE,END. OPEN uses the existing exact plan/Method/Protocol validator and requires an already revealed unambiguous risk quote at most60seconds old. MARKET planning entry must match current Ask(long)/Bid(short), while actual fill waits for the next eligible recorded replay event. Unsupported fork/seek/router integration remains a separate controller gate; never mutate an existing Session/profile to make it work.

The immutable-account proposal state pins dataset/version/profile/Method, start/through, monotonically counted groups/events, source checkpoint hash, source prefix hash and source cursor revision. The prefix hash must be reconstructed from the exact unchanged frozen42.17step before any proposed action, preventing unnoticed changes to quote price or raw quality despite identical source event IDs. Source checkpoints stay separate and controller-only; only opaque hashes are in financial state. No provider/index/EOF/file handle enters it. Old v1/v2 bytes and source inputs are unchanged.

Retain the existing128order and256event-per-transition safety limits; no ever-growing advance-target list exists. Every order retains its acceptance balance/basis hash so later Protocol validation cannot accidentally use a changed balance. Account cash equals initial cash plus the sum of exact per-exit half-even postings; fixed fees are zero. Sorted order-ID traversal makes events/cash/state deterministic after canonical serialization and cold recovery. Entry/exit evidence includes all group event IDs, actual sides/prices and distinct UNMODIFIED raw quality values with the conditional model identity. No row is promoted to a confirmed quote or independent market sequence.

Live exposure encountering ambiguous differing equal-time outcomes, unusable precision/quality, causal diagnostics, known incomplete evidence or the observed60second guard becomes UNRESOLVED before an affected fill. Same-price groups produce only their common outcome, retaining all canonical members; non-identical no-action groups record chronology limitation. Invalid known evidence also invalidates a risk basis until a subsequent usable observation. Pending END expires without a guessed fill; active END becomes unresolved. Source reveal may continue after unresolved/end for charting, without financial recovery/reset in place.

The frozen42.19producer projects UNKNOWN coverage, not a comprehensive known-gap trading guard. A private new-family controller MUST preserve the original reveal/prefix and separately enforce bounded causally clipped known-gap guards from qualified source evidence before publishing financial receipts. Sources requiring an unsupported guard are refused, never silently treated as complete. The pure reducer's conservative authored INCOMPLETE-frame refusal test is not proof that the frozen producer supplies such coverage. Mandatory next gates are gap-guard/source admission, transactional receipts/CAS/idempotency/worker-death recovery, source-outage event-derived journal/statistics and actual existing website workflow. Pure proposed SIMULATED_FILL events are not published fills or durable account postings until those gates pass.


### First admitted-source/durable-controller capability — 2026-10-27

Operator configuration must pin an independently reviewed full-source qualification receipt hash and protected0400archive/0500directory, exact root/profile identity and event count. Normal structural publication or codec validity is never admission. Accepted proof kinds are the qualified full-day readonly proof, fully matched monthly qualification or full binary-source parity snapshot; unmatched/incomplete receipts refuse. The FIRST controller capability admits EMPTY evidence catalogs only. Any nonempty catalog is REFUSED_UNSUPPORTED_OBSERVED_SIDECARS, not inspected to derive an unrestricted future-gap trading hint or silently ignored. This is a supported-capability gate in trusted operator configuration, never a public arbitrary-file/source query. No actual source quality/rights is promoted: raw UNKNOWN remains unchanged. New capability for nonempty sidecars requires its own bounded causal guard qualification before mounting; current actual normal sources have empty catalogs.

The new observed store uses existing opaque tick tables without modifying old model dispatch/schema. Every current snapshot must match the immutable checkpoint at the same revision. Expensive source/reducer work happens outside the financial row lock. The write transaction rechecks exact prior state/checkpoint hashes, command/revision CAS and immutable source/profile/Method/start context, validates the entire event chain and balances against posted deltas, and atomically inserts immutable command/events/checkpoint plus the new session tip. Only successful COMMIT publishes durable conditional SIMULATED_FILL. Before-commit process death publishes nothing; after-commit loss retries the identical immutable receipt. Exact command-ID/payload reuse returns the old receipt before any source access; mismatched reuse refuses. TrustedScope remains mandatory and all SQL is workspace/session scoped.

New result artifact BTL-OBSERVED-EXECUTION-RESULT-1 has exact keys schemaVersion,artifact,commandId,commandHash,state,events,eventCount,eventFromSequence,eventsComplete,nextEventSequence,replay,durable,model. events is the first at-most64events, with explicit total/continuation fields; ALL at-most256per-transition events remain individually committed and hash chained. Journal pages are at most64, never silently omit additional events or exceed the canonical result budget. replay is null for non-ADVANCE, otherwise exact throughNs/exhaustedThroughBoundary, never provider EOF/index/root metadata. Source-admission paths/receipts/row counts/capabilities are controller-private; receipts expose only new-family financial state and bounded committed events. History and prior receipts remain readable with no market files/provider access. Event-derived statistics and actual authenticated website/review flow are still separate mandatory gates.
