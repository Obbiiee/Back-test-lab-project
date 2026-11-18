# Multi-pair and multi-method inside one Session: backend audit and design (2026-11-18)

Status: implementation register and design proposal, **not an architecture authority and not implemented**. Owner instruction (2026-11-18): this is mandatory for Commercial V1, the backend must be examined first, and a frontend dropdown that only switches the chart is not acceptable. This note is that examination. Its conclusion is that the feature needs a **new financial contract** and three inputs that do not exist yet, so it is **BLOCKED**, with a staged plan below.

## 1. What the backend is today (evidence from the code)
| Fact | Where |
|---|---|
| The frozen execution profile accepts only `instrumentId == "XAUUSD"` with `quoteCurrency == accountCurrency == "USD"`; anything else is refused `REFUSED_UNSUPPORTED_PROFILE` | `backend/execution/contracts.py` (`profile_wire`) |
| A Session carries one dataset and one profile: Session metadata fields are `id name methodId methodHash datasetId datasetVersion profileHash startPeriod initialBalance` | `execution/research.py` (`BTL-LOCAL-SESSION-1`), `seed_state(...)` |
| The reducer refuses any tick whose `instrumentId` differs from the profile's `feedInstrumentId` (`REFUSED_DATASET_MISMATCH`) and checks provider, feed and dataset identity per atomic group | `execution/engine.py` (group identity check) |
| The replay timeline is one provider over one dataset; the checkpoint (V1 advance log, V2 compact index) stores one cursor | `execution/controller.py`, `ticks/timeline.py` |
| Exactly one Method per Session, fixed at creation (`methodId`, `methodHash`); command kinds are OPEN, ADVANCE, SEEK, CANCEL, CLOSE, END; Method analytics aggregate by the Session's Method | `execution/research.py`, `execution/method_analytics_store.py`, `execution/contracts.py` |
| The order rows I inspected (`execution/analysis.py`) are built from the plan and fills; I found no instrument or Method field on an order or a trade | `execution/analysis.py` |
| The "v2" sandbox (`research_v2.py`) has a `symbol` field but one fixed synthetic period and is not a multi-symbol engine | `execution/research_v2.py` |

Consequence: a dropdown that swaps the chart would show prices that the engine does not hold. Orders, margin, PnL, SL/TP, pending orders and the checkpoint all assume exactly one instrument and one Method.

## 2. Data and specification facts that bound the feature (from `RIKSORA-INSTRUMENT-MATRIX-20261115.md`)
* 16 pairs have verified tick months (352 or 544 instrument-months for 2024-01..2026-10; **no 2023 ticks**), but **data rights are UNKNOWN** for all of them (private QA only; HistData terms silent, Dukascopy text is personal-use).
* **11 of the 16 pairs are not USD-quoted** (the JPY, GBP, NZD, CAD and CHF crosses). The reducer's money model requires quote = account currency, so these need a point-in-time conversion rule and rate source that do not exist (marked MISSING).
* **Contract size, lot rules and pip conversion are MISSING for 15 pairs.** Only XAUUSD has an observed profile.
Therefore "16 pairs PASS" cannot be claimed from any fixture, and the real-data part cannot start until rights, specifications and conversion are decided.

## 3. Proposed design (additive, isolated from the XAUUSD contract)
Principle: keep `BTL-TICK-EXECUTION-COMMAND-1` and every existing Session byte-for-byte unchanged; introduce a **new, versioned multi-instrument contract** used only by new Sessions that opt in.
1. **Profile set.** A Session pins a set of instrument profiles (`profileSetHash`), each with its own tick size, contract size, lot rules and quote currency. The USD-only restriction is lifted only for profiles whose conversion rule is explicit and tested (USD-quoted first: EURUSD, GBPUSD, AUDUSD, NZDUSD, XAUUSD).
2. **One timeline.** A fan-in over the per-instrument monthly providers with a deterministic total order `(timeNs, instrumentIndex, rawOrdinal)`. A timestamp group stays atomic per instrument; ties between instruments are ordered by `instrumentIndex`, never by arrival. The revealed frontier is one `throughNs` for the Session; an instrument with no tick at that time keeps its last revealed quote (never a future one), so there is no look-ahead across instruments.
3. **State.** `quotes` becomes a map by instrument; `orders` carry `instrumentId` and `methodId` stamped at creation and immutable afterwards (this gives the required attribution: a later Method switch never rewrites an old trade). Balance, equity, margin and PnL stay account-level in USD; positions and pending orders on other instruments keep being evaluated on every tick of their own instrument whatever the chart shows.
4. **Method switching.** The active Method is a Session-level pointer recorded in the event log; each new order copies it. Journal and Method analytics aggregate by the order's `methodId`, not by the Session's.
5. **Checkpoint.** The V2 compact checkpoint gains a per-instrument cursor (`cursors[instrumentIndex]`) and the fan-in position; V1 Sessions are untouched.
6. **Entitlements.** Free: pair and Method switching is allowed inside the activated month with no extra quota (one Session, one month, all instruments of that month). Pro: unlimited months. The window floor and ceiling apply to every instrument timeline.
7. **Frontend.** Instrument selector bound to Session state (switching changes only the *view* instrument and the instrument of the next order; open positions on other instruments stay visible in a position list), chart per instrument, pair and Method columns in the Journal, Method selector in the order ticket. It is built only after the backend contract passes its parity gates.

## 4. Acceptance gates for the design (all must pass before the feature is called DONE)
* Parity: a multi-instrument Session equals N single-instrument references on every instrument's fills, prices and PnL (cash is the sum), on identical data.
* Cross-instrument no-look-ahead test: a fill on instrument A never uses a quote of B later than the frontier.
* Month-boundary and year-boundary parity for the multi-instrument timeline (reusing `test_pro_long_sessions` structure).
* Attribution test: switch Method between two orders; the earlier trade keeps its Method; analytics sum correctly.
* Pending order and open position on instrument B stay correct while the user views and trades instrument A.
* Checkpoint, SIGKILL and V1→V2 tests for the new cursors.
* Free quota/window tests across instruments; browser E2E desktop and mobile.
* Evidence separated: synthetic (can be built now with two or three authored instruments) versus real (blocked on rights, specifications, conversion).

## 5. What can be done without the owner and what cannot
* Can be built and tested now, isolated: items 2 to 5 with **synthetic USD-quoted instruments** (for example three authored pairs), including all gates in section 4 except real data. This is a multi-week engineering task touching the reducer's state model, the provider fan-in, the checkpoint and the Journal; it must not be squeezed into a patch to the validated XAUUSD engine.
* Needs the owner or outside input: data rights; contract specifications for each pair; conversion rule and rate source for non-USD quotes; which pairs make the first release; whether Method switching is per Session pointer (proposed) or per order.

## 6. Status
**BLOCKED / NOT IMPLEMENTED.** No partial multi-pair or multi-method behaviour was added to the product, deliberately: a half implementation would put unvalidated money logic in front of users.
