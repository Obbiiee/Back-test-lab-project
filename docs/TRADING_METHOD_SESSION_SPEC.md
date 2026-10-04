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

Canonical type identifiers are `FREE_STYLE | PROTOCOL`. Session inherits its parent Method type; it does not select a competing Trading Mode. This is the single owner of this product contract, distinct from the currently implemented local paper-account model.

### Free Style

A Free Style method represents discretionary trading.

- Method has an identity/name and may have descriptive metadata.
- RR and risk are not protocol-locked by the method.
- Quick Trade and Planned Trade are both available in the workspace when otherwise supported; no protocol checklist is required.
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
- **ON:** every checklist condition defined by the locked Protocol method must be recorded as PASS before an order may be executed. Failure to satisfy any condition blocks execution at the protocol/domain validation boundary.
- **OFF:** checklist definition and available checklist state remain recorded as research evidence, including enforcement OFF and unavailable/not-assessed conditions. They do not block execution or force checklist interaction as a pre-order step. Never fabricate PASS or discard evidence because enforcement is OFF.

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

Protocol risk per trade is fixed by the immutable Trading Method definition. Internal schema/hash provenance does not introduce a required user-facing versioning workflow.

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

Execution-profile configuration uses sensible defaults with advanced configuration when needed; it is not mandatory first-run Session complexity.

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

## Trading UX handoff v1 — workflow authority

Phase 18.7 extends this existing owner; it does not create another Method or trading-workflow specification. This section owns conceptual workflow, units, interaction and handoff contracts. Implementation status and phase authorization remain in AI_CONTEXT, not here. Existing local v1 trading is not retroactively Protocol-compliant. Phase 18.8 will validate an explicitly labeled, memory-only prototype; a production Method/Session repository, ledger and migration remain future work. Phase 18.9 may freeze this contract under the human's explicit sequential authorization, superseding the older roadmap requirement for another approval at that point.

### Stage ownership

Trading Method → Session → Trading Plan → Position Tool → Order Ticket → Validation → Confirmation → Order → Position → Exit → Evidence → Journal → Analysis.

| Stage | Owns | Must not own |
| --- | --- | --- |
| Method | Immutable identity, FREE_STYLE/PROTOCOL, rule definition, locked risk/RR and checklist setting | Account balance, chart pixels, subscription tier |
| Session | Method reference/definition provenance, instrument/feed/dataset identity, start period/balance, execution profile, continuation | A competing method-type toggle, reinitializing balance on continuation |
| Plan | Draft intent, direction, TIME + PRICE anchors, editable geometry, checklist observations, revision | Fills, realized returns, fabricated PASS |
| Position Tool | View and interaction adapter over Plan; Entry/SL/TP/risk/size preview | Order submission or direct account writes |
| Ticket | Reviewed request fields and contextual reasons, cancellation | Bypassing domain restrictions or calculating canonical execution results |
| Validation | Instrument, session, funds/risk, geometry and method constraints against current revealed revision | Inferring unknown provenance or treating UI locks as enforcement |
| Confirmation | Explicit user acknowledgment of an immutable validated request snapshot | Automatic execution on placement, repeated submission |
| Order/Position/Exit | Existing execution owner when integrated; pending/trigger/partial/terminal transitions | Replacing raw replay settlement with display timeframe bars |
| Evidence | Append-only identities, observations, decisions, execution/exit records and provenance | Calling every exit a complete trade or rewriting original records |
| Journal/Analysis | Notes and projections of the same evidence identity | A second financial store or presumed compliance |

Future production adapter: planner → validated request boundary → existing execution service → canonical account/events → existing Journal/Analysis projections. No direct planner → simulator route. Current v1 `riskRewardOrderSeed` is a legacy preview adapter; its near-price Market and /100 conversion must not be used as future Protocol enforcement.

### Instrument and risk units

An InstrumentProfile identifies instrumentId, displaySymbol, quoteCurrency, priceDecimals, tickSize, pipSize (nullable), quantityUnit, contractSize, sizeStep/min/max (nullable if unknown), costs model and profile provenance. Unknown broker constraints stay unknown and block any claim of broker compatibility. Tick is the smallest supported profile price increment; pip is an optional explicitly declared reporting unit, never inferred from decimals. Monetary values are in quote currency unless a separately validated FX conversion profile exists.

The observed local v1 profile is XAUUSD, USD price, display precision 3, simulator size in lots and CONTRACT_SIZE=100 price units per lot. Those facts are simulator conventions, not certified broker/venue metadata. Existing tick settings are user preview settings, not authoritative feed tick size. The isolated prototype uses a disclosed DEMO profile: tick 0.001, 3 decimals, contract size 100, lots step 0.0001/min 0.0001/max 1000; these constraints are synthetic and must never be assigned to imported history as fact.

Prototype risk basis is starting simulated balance 100000 USD, unchanged by synthetic lifecycle actions. This choice is a preview assumption, not the future Risk Engine equity policy. A production risk profile must declare its basis (balance/equity snapshot), revision and costs; unknown basis refuses confirmation. Protocol locks both risk mode (PERCENT or CASH) and positive value at Method creation; no implicit 1% default as a research rule. Example fixtures use 1% and RR 2 only for repeatable validation.

Let d=+1 Buy, -1 Sell; stopDistance=(entry−SL)×d >0; rewardDistance=(TP−entry)×d >0; RR=rewardDistance/stopDistance. RiskBudget is CASH value or basis×percent/100. Under the explicit zero-cost demo profile, lotsRaw=RiskBudget/(stopDistance×contractSize); lots=floor(lotsRaw/sizeStep)×sizeStep. Do not round upward above budget. Reject below min/above max instead of silently enlarging/shrinking outside bounds. Planned loss=stopDistance×lots×contractSize; target preview=rewardDistance×lots×contractSize. These are intent previews, not guaranteed fills or outcomes. Missing/invalid SL means no risk-derived size. Tick-align accepted Entry/SL/TP; locked RR whose derived TP cannot satisfy tick precision is refused rather than silently distorted.

Current simulator P&L formula, zero commission convention, gap/open handling, conservative same-candle stops and pending-entry-bar close-only exit evaluation remain unchanged. Real spread/slippage/fees, margin/leverage, bid/ask, currency conversion and broker rounding need later profiles; no broker claims or hidden cost assumptions. Unknown costs are displayed, not converted to zero facts; the demo explicitly declares zero costs for UX only. Production must revalidate requested risk separately from realized gap loss.

### Method and Session identity

Session references immutable Method identity plus definition hash/schema provenance, never a user-facing Method version switch. No re-selecting FREE_STYLE/PROTOCOL. Its identity includes instrument, immutable feed/provider, dataset/version/hash, starting month, original balance/currency and execution profile identity. Display timeframe can change without changing these identities or revealing future OHLC. Appended periods remain chronological with continuous equity; no reset/duplicate/finished-Session workflow. Existing account/date/drawing keys do not prove Session identity: never silently migrate or invent historical IDs. Archived Methods cannot create Sessions. Material rule/RR/risk/checklist changes create another Method.

The prototype offers immutable sample Methods and a labeled sample Session, plus a draft Method form to demonstrate minimum one condition/risk/RR. Its feed is DEMO_SYNTHETIC, not a market provider; reload discards prototype state. Sample state is not written to account, drawing or news namespaces.

### Free Style journeys

Quick: choose Buy/Sell → compact ticket with Market quote/explicit quantity and optional exits → validate → review snapshot → Confirm simulation → active representation. Quick does not require a Protocol checklist or a planning object. Current price must be finite and revision-bound. Supported Free Style management may edit valid exits, cancel pending, partially exit or manually close; evidence records action even when discretionary. A Market request's entry is the current quote, not a stale draggable anchor.

Planned: Long/Short → place Entry → configure SL and TP → risk mode/value and derived quantity/RR → ticket (Market/Limit/Stop as otherwise valid) → validate → explicit review/confirmation → pending or active representation. Changing geometry refreshes preview, invalidates prior review and never mutates an account. Cancel ticket/review returns to unchanged draft; dismissing review does not cancel an existing pending order.

### Protocol journeys and restrictions

Protocol inherits Planned only, locked risk/RR and minimum one condition. Choose Long/Short → Entry/SL → TP derived as Entry+d×stopDistance×lockedRR → size derived from locked budget → checklist observations → pending Limit/Stop ticket → domain validation → explicit confirmation → pending representation. Entry/SL may change draft; TP/risk/RR remain locked and recomputed. Turning enforcement OFF belongs to an immutable sample Method variant, not a silent mid-evidence mutation. OFF skips checklist blocking/mandatory interaction but captures NOT_ASSESSED, FAIL or PASS as actually supplied.

ON requires every defined condition PASS. Missing, NOT_ASSESSED or FAIL yields PROTOCOL_BLOCKED with exact condition IDs/reasons. OFF does not override Quick/Market/locked risk/RR restrictions. Bypassed UI requests must also fail validation. Direct Market, Quick, early/manual/partial close or discretionary SL/TP intervention on an active fixed-RR Protocol position are refused. Automatic preplanned exit belongs to execution; prototype button is clearly a scenario, not a replay fill. Pending cancellation is permitted as abandonment with reason/evidence before trigger; cancellation never creates an exit/P&L. No extra Rule-Based Exit product is implemented here.

Categorical restrictions cannot become TRACK_VIOLATION. No current Method supplies an otherwise-permitted warning rule, so this contract does not invent an executable TRACK_VIOLATION example. Future explicit observational policies may attach a VIOLATION observation to an otherwise allowed action, without relaxing categorical refusal; ruleId, decision/reason and action identity are required. Refused attempts are evidence of refusal, not executed violating trades or invented compliant trades.

### Position Tool interaction

Geometry persists conceptually as TIME + PRICE only; pixels are transient. Long/Short direction must match SL loss side/TP reward side. States: idle, planning, editing, invalid, ready, awaiting_confirmation, locked, hidden. Select/drag anchors or numeric entry edits update only draft revision. In Protocol, Entry moves preserve stop distance where translated, SL edits derive TP, TP drag/edit is blocked. Free Style supports discretionary positive geometry. Tool lock prevents edits, not validation; hidden affects visualization only. Change direction creates a new reviewed draft, not silent mutation of confirmed intent. Separate drawing history/storage remains untouched.

Preview shows entry, SL, TP, risk amount/percent/basis, RR, quantity unit and rounded size, instrument assumptions, status/reason. Invalid geometry remains visible with explanation and disabled request conversion. Convert to ticket is explicit and copies a snapshot referencing planId/revision; subsequent edits invalidate pending review. Existing RiskRewardController geometry helpers may be adapted for prototype projection/interaction without replacing production drawing geometry.

### Ticket, validation and confirmation

Ticket includes Method/Session/plan provenance, requestId, draft revision, revealed quote revision, direction, order method/type, Entry, SL, TP, size, risk profile/budget, costs assumptions, checklist state and notes. Inherited identity is read-only. Free Style edits side/type/entry/size or risk-derived plan fields as appropriate; Market entry follows quote. Protocol locks type to Limit/Stop, risk/RR/TP-derived/size-derived; editable pending type and Entry/SL trigger revalidation. Missing instrument/quote/basis/rules, nonfinite/nonpositive input, wrong geometry, unsupported precision/size and stale revision are INVALID/REFUSED, never fallback success.

Validation stages: identity/provenance → numeric/instrument constraints → supported order relation (Buy Limit below quote, Sell Limit above; Stop opposite) → risk/geometry → Method restrictions → checklist when ON → current revision. Errors carry codes/field/reason; warnings disclose assumptions without bypassing errors. UI mirrors domain decisions and displays protocol-restricted reasons. Existing simulator validateOrder remains final numeric/execution validation when a production adapter is later authorized.

Ready → Review → immutable summary → explicit Confirm. Review identifies pending vs immediate entry, direction/levels/quantity/risk/method/checklist/assumptions. Quote/plan/method changes invalidate review; go back/edit must validate again. Cancel/Escape closes most local review/ticket and restores opener with no submission. Request identity is stable for a reviewed snapshot. Confirm records at most once: duplicate same request/snapshot returns prior result; reused identity with different payload is REFUSED_IDEMPOTENCY_CONFLICT; stale snapshot refuses. Future durable dedup belongs to execution/application service, not a React disable flag. Prototype keeps an in-memory dedup registry and never calls useTrading.place.

### Lifecycle and evidence

| State | Permitted next step / invariants |
| --- | --- |
| idle | choose Quick or start Planned draft |
| planning / editing | geometry/fields/checklist updates; no account writes |
| invalid / protocol_blocked | explain reasons; fix allowed fields or cancel; no confirm |
| ready | open ticket/review with validated snapshot |
| awaiting_confirmation | confirm once, cancel, or invalidate on revision change |
| pending | cancel before trigger; synthetic trigger only in prototype, real fill only execution owner |
| active_position | supported Free Style management; Protocol preplanned exit only |
| partially_exited | Free Style residual remains active; exit record is not completed position |
| closed | final execution evidence, read-only projections |
| cancelled | draft dismissal or pending abandonment distinguished; no fill/exit claim |

Event envelope: eventId, kind, request/plan/Method/Session identity, draft/quote revision, captured time, source (PROTOTYPE or canonical execution), instrument/feed/profile provenance, decision/reasons, checklist enforcement/condition observations and payload. Confirmation and refusal are separate from fill/exit. Actual fill/exit values, original/remaining size, cost evidence, entry/exit timestamps and engine policy are execution-owned. Unknown fields use null/NOT_ASSESSED; COMPLIANT requires actual sufficient assessed evidence, not a default badge. Notes reference event/position identity. Analysis consumes canonical exits and accounts; prototype displays a descriptive event timeline only and no canonical performance result.

### Protected integration and acceptance boundary

Prototype adapters do not import useTrading, persistence writers, replay settlement, account schemas or Analysis calculators. LWC chart uses synthetic revealed candles and existing geometric helper where safe. A separate entry selected explicitly by URL keeps local v1 default unchanged. No account/storage migration, market dataset write, indicator/news calculation or backend/cloud implementation. Terminal reuses 18.6 bounds/tokens. Future production integration needs explicit authority for Method/Session persistence, runtime validation, durable dedup/evidence, risk profile/basis, and plan-to-execution adapter; prototype success does not authorize these.

18.7 acceptance: owner/stage matrix, Quick and Planned Free Style, Protocol ON/OFF/refusal, risk/instrument assumptions, request confirmation/idempotency, state/evidence model and preservation boundaries are defined here. Validate context/repository/bundle controls; browser exemption applies to this documentation-only checkpoint. Prototype behavior and freeze evidence will be recorded here in subsequent authorized phases, without a competing specification.
