# Backtest Lab — Subscription & Entitlement Specification

Status: product/architecture authority for future subscription work. This document does not authorize implementation or finalize price.

## Core monetization principle

**Do not sell correctness. Sell research capacity, depth and convenience.**

Free and paid users must use the same canonical replay/execution semantics. Subscription tier must not deliberately reduce no-look-ahead correctness, execution correctness, protocol semantics, or available market-data fidelity merely to make Free results inferior.

Where Precision execution is possible from the selected dataset, entitlement must not intentionally substitute a less-correct engine for Free users.

Free/Pro subscription is independent from **Trading Method type (Free Style / Protocol)** and execution workflow (Quick / Planned).

## Free tier — daily tradable research window

The intended Free experience is a complete, credible Backtest Lab workflow with a capacity limit.

### Daily allowance

- A Free user may activate **one tradable historical window of up to one calendar month per daily entitlement period**.
- The exact reset timezone/time and anti-abuse mechanics are implementation decisions to be defined before launch; they must be deterministic and visible to the user.
- **Activating the monthly segment immediately consumes that day's Free allowance**, even if the user later trades or replays only part of the activated month. The allowance is not prorated by days used.
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

Examples include reaching SL/TP, cancellation/expiry where applicable, or another canonical terminal state permitted by the Trading Method. Protocol positions do not gain a manual-close exception from the entitlement boundary.

This continuation:
- does not grant a new general tradable month;
- must not allow unrelated new entries outside the entitled window;
- must preserve no-look-ahead and normal execution semantics;
- ends when the outstanding authorized lifecycle is resolved.

The next new Free tradable-window allowance becomes available according to the next daily entitlement period.

## Free account/session capacity rules

- The Free daily tradable allowance does **not** accumulate. If unused for a daily entitlement period, it expires rather than banking additional monthly segments.
- A Free user may keep a maximum of **5 active/saved Sessions**.
- At the five-Session limit, creating another active Session requires freeing a slot or upgrading to an applicable paid entitlement.
- Deleting an active Session moves it to **Trash for 30 days** before permanent deletion. A trashed Session does not consume one of the five active/saved Free Session slots.
- Restoring a Session from Trash makes it active/saved again and therefore consumes a slot. If the Free account is already at 5/5 active/saved Sessions, restore is blocked until the user frees a slot or obtains an applicable higher entitlement.
- Session reset/restart is not a product workflow for Free or Pro. A separate experiment starts as a new Session.
- Session duplication is not part of the intended product workflow.
- A Free user with an available daily allowance may apply it to continuing an eligible prior Session or to starting an eligible new Session.
- If a Pro user later returns to Free, prior research/results remain reviewable; new research actions follow current Free entitlements rather than destroying historical evidence.

## Persistent Free backtest sessions

A Backtest Session is a persistent research container, not a disposable one-month backtest.

- A Free user may create a new Backtest Session or reopen a previous session.
- The daily Free allowance may be applied to one eligible session to add/continue one tradable monthly segment.
- A previous session remains reviewable after its tradable segment is completed.
- On a later entitlement day, the user may continue that same session with the next eligible monthly segment, preserving its canonical trade history and cumulative results.
- Alternatively, the user may spend that day's allowance on a new/different session.
- The entitlement is account-level daily research capacity; creating many session records must not multiply the daily tradable allowance.
- Continuation must preserve Trading Method identity, dataset/feed identity, execution profile and other reproducibility metadata. Material Method-rule changes require a new Trading Method rather than silently rewriting prior evidence.

### Dashboard and Session Overview

The Free dashboard should remain a lightweight work selector rather than exposing the full statistics of every experiment.

Primary dashboard actions:
- **New Backtest**
- **Previous Sessions / Your Sessions**

A previous-session card should primarily identify the session and its last activity/status. Detailed backtest results appear only after the user opens the session.

Opening a previous session leads to a dedicated **Session Overview** before continuation. The Session Overview is the canonical review surface for that session's accumulated basic results and should include:
- tested period / completed monthly segments;
- total trades, wins/losses and win rate;
- realized net P&L;
- total R and average R;
- profit factor;
- maximum drawdown;
- session/month progression;
- access to relevant trade history/journal;
- a primary **Continue Session** action.

### Interactive basic-result diagrams

Free Session Overview must include useful interactive basic-result visualization rather than intentionally degraded static charts.

Initial target:
- interactive Equity Curve;
- interactive Drawdown Curve;
- P&L / R view toggle where semantically valid;
- period/month filtering;
- tap/hover details for chart points;
- trade markers linked to relevant trade details where practical;
- monthly/session progression that makes completed segments and the next continuation point clear.

These diagrams derive from the same canonical ledger/statistics contracts as numeric results. Subscription tier must not change the mathematical truth of the same session.

Advanced research visualization and analysis may remain Pro-gated when they represent additional research depth (for example Monte Carlo, deep MAE/MFE, robustness, walk-forward, regime and cross-feed analysis), rather than a more-correct version of the Free result.

### Continue Session entitlement behavior

When **Continue Session** is selected:
- if the daily Free allowance is available, the user may activate the next eligible tradable monthly segment for that session and return to the Backtest Workspace;
- if the daily allowance has already been consumed, the Session Overview and prior results remain accessible, but a new tradable segment cannot be activated until the next allowance or an applicable upgrade;
- the existing open-position boundary rule still applies and must not manufacture outcomes.

## Free trading capabilities

Subject to normal product/data availability, Free should retain the core experience:
- professional chart workflow;
- canonical Precision-capable execution path;
- no-look-ahead guarantees;
- Quick Trade;
- Planned Trade;
- Free Style Trading Methods;
- Protocol Trading Methods;
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

Chart, drawings, supported execution workflows, Trading Method semantics, order semantics and core navigation should remain structurally consistent. Entitlements unlock capacity/research surfaces in-place.

Upgrade prompts should appear at meaningful entitlement boundaries, not interrupt the user's first complete core backtesting experience unnecessarily.

## Integrity rules

1. Never degrade execution accuracy solely because the user is Free.
2. Never truncate an already-authorized open position in a way that changes its outcome merely to enforce a subscription boundary.
3. Never hide future candles visually while allowing the engine/indicator/rules layer to read them.
4. Never present a deliberately inadequate Free sample as statistically conclusive.
5. Never conflate Free subscription with the Free Style Trading Method type.
6. Entitlement checks control access/capacity; canonical domain engines control market/execution/research truth.
7. Pricing, exact quotas beyond the agreed daily tradable-window concept, daily-entitlement reset timing/anti-abuse mechanics and commercial packaging require separate product decisions.

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


## Local sandbox access composition checkpoint - 2026-10-17

Existing journey grant permits an opt-in synthetic-only v2 API using verified identity and WorkspaceUnit membership locks retained through service commits. Enable only with an explicit reset timezone (UTC or Asia/Jakarta); the human reset choice is pending, so tests select their authored timezone and no default activation is assumed. Account-level serialization precedes all writes. Free keeps5 saved Sessions and one new calendar-month activation per local entitlement day across all workspaces; identical activation retries return existing evidence, conflicting same-day windows refuse. Activation consumes capacity immediately and pins Session/profile/dataset/month, independently from financial actions. Existing activated windows remain readable and executable within their immutable bounds. This demo source supports January2020 only; it does not claim a full historical month or support a later month. Outside-window ADVANCE is refused explicitly; open positions are never auto-settled. Source-backed lifecycle continuation is a dependent requirement before real multi-month rollout.

Account ownership admission is inserted atomically with the new v2 Session, and retries cannot acquire another owner's Session. Trash is a soft metadata state with30-day restoration, freeing a saved slot without rewriting/deleting financial evidence. Restoring checks current account capacity. No physical evidence purge is implemented by this sandbox checkpoint. Active owner-only writes and scoped member reads preserve existing ownership policy. Canonical domain correctness is identical at either tier.

Sandbox Pro may be assigned only by a separate server-verified HMAC test event with immutable event identity/hash, account, strictly increasing account sequence and bounded expiry. It means simulated entitlement, never funds collected, merchant confirmation or real subscription. No live provider, checkout, price/currency or card handling is introduced. Same-id altered event bytes refuse and stale account sequence refuses; expiration returns Free without deleting research. Pro remains subject to explicit128-demo saved-session resource bound, not a final commercial quota. Production pricing/quotas/provider/reset packaging and retention acceptance remain separate decisions.

All endpoints remain disabled unless explicitly configured; old v1 routes/identities stay unchanged. Body/content/source/query boundaries, bounded request admission, no-store responses and per-command exact receipt retries remain required. Verified HTTP/native concurrency/revocation/recovery and browser validation when a UI is mounted are required; an opt-in ASGI test is not external Beta acceptance. Claude frontend stays separate in this checkpoint.

This opt-in allowance namespace is explicitly V2_SANDBOX_ONLY. Legacy v1 admission is unchanged and not certified as commercially quota-enforced. Before paid rollout, every exposed write path must compose the same product entitlement policy, while preserving old reviewable evidence. Sandbox signed events are an operator/service test seam only, not a public provider webhook or completed checkout.


V2 sandbox access/transport acceptance (2026-10-17): Full443 backend/zero skips/723.340seconds on fresh isolated SCRAM PostgreSQL with normal shutdown PASS; focused11/zero skips/66.680seconds PASS before the final pure configuration test, which passed in full discovery. Baseline frontend regression/lint/build136/release, repository/bundle and independent Node6x3/16profile references PASS. Twelve new families prove explicit disabled default/config/key separation, HTTPS ASGI scope/TLS/source boundaries, exact0.03USD/3/100R/journal/receipt flow, v2 account-wide saved/activation races, Trash/restore/retention, signed test-event replay/order/expiry, UTC/WIB boundaries/policy pins, deactivation serialization, separate API/operator roles and native empty-target restore. No actual Google/merchant/provider webhook/checkout, acquired month, frontend/browser cutover or paid Beta acceptance. The first focused run failed because the response wrapper passed schemaVersion twice to dict(); a direct no-database reproduction isolated TypeError, fixed by the existing dictionary-merge pattern. No security or quota guard weakened. Runtime stayed frozen throughout final discovery. Reset choice remains an operator/human prerequisite; tests explicitly select authored policies and no application environment/data was changed.


Human decision (2026-10-17): Free daily sandbox allowance resets at00:00 UTC. This supersedes the earlier pending-reset wording for the current policy only. Pin UTC when opting in; changing an existing account timezone still refuses ACCESS_POLICY_DRIFT. Asia/Jakarta remains an authored clock-boundary test/configuration capability, not the selected current product policy. No automatic runtime enablement, provider activation, final commercial packaging or gate waiver.


## Indonesian provider comparison requested2026-10-18

Human requests a comparison, not merchant activation. Preliminary technical shortlist from official documentation:

| Provider | Observed integration | Fit for this Beta | Still needs evidence |
| --- | --- | --- | --- |
| Midtrans | Snap supports hosted redirect or popup. Official webhook docs specify SHA512(order_id+status_code+gross_amount+ServerKey) and transaction-status verification | First sandbox candidate: hosted checkout plus server reconciliation maps to existing provider-independent entitlement boundary | Actual merchant approval/product eligibility, enabled methods, fees/tax/settlement/refund terms, sandbox keys, price/duration and real notifications |
| Xendit | Payment Sessions supports hosted PAYMENT_LINK or embedded COMPONENTS, PAY/SAVE types, expiry and lifecycle webhooks; official IDR/ID one-time example | Equally viable hosted-checkout alternative; saved-method/recurring capabilities must not imply they are enabled for this business | Merchant activation, current fees/settlement/availability, exact webhook authentication/reconciliation contract and actual account capabilities |
| DOKU | DOKU Checkout provides hosted redirect/embedded page with method ordering, expiry and branding options; sandbox/demo and integration guide linked by official docs | Viable hosted-checkout alternative if its onboarding/methods/terms fit the business | Actual merchant account, fees/settlement/refund terms, exact notification signature and retry/reconciliation acceptance |

Engineering inference: start evaluation with Midtrans Snap hosted redirect to keep card entry on the provider page and use documented server-status reconciliation. This is not a cheapest-provider claim, commercial approval, chosen price or promise of recurring-payment availability. Xendit and DOKU remain alternatives until account eligibility and actual fee/settlement/refund quotes are compared. No live merchant account, purchase, KYC submission or payment integration was activated. Existing sandbox signed test events are not merchant payments. Never promote a redirect/client callback to paid entitlement; server order/account/amount/currency identity, authenticated notification, idempotency, replay/out-of-order/reversal and provider status must reconcile durably before granting access.

Sources inspected2026-10-18: [Midtrans Snap](https://docs.midtrans.com/docs/snap), [Midtrans notifications](https://docs.midtrans.com/docs/https-notification-webhooks), [Xendit Payment Sessions](https://docs.xendit.co/docs/payment-sessions-overview), [Xendit one-time IDR example](https://docs.xendit.co/docs/payment-1), [DOKU Checkout](https://docs.doku.com/accept-payments/integration-tools/doku-checkout). Earlier attempted documentation URLs returned404 and were replaced with the official current pages; no conclusions rely on those404s.


### Midtrans Snap sandbox provider seam - 2026-10-18

Human selected Midtrans Snap and authorizes continuation toward paid Beta. First bounded implementation is backend/cloud/midtrans.py, deliberately unmounted: fixed sandbox-only HTTPS endpoints, SB-Mid-server key required, immutable server-order pins (account/plan/whole-IDR/duration), hosted card checkout with secure=true and30-minute payment expiry. These are transport inputs, not a chosen commercial offer or durable order record. No production switch, environment activation, frontend or new database mutation. Caller must first durably persist its own immutable order; uncertain POST/timeout/invalid response cannot be retried blindly. A sandbox observation never means real funds collected or entitlement granted.

Webhook SHA512 authenticates exactly order_id+status_code+gross_amount+ServerKey with constant-time comparison. Notification transaction_status/fraud/currency/merchant are not covered by that signature, so authenticate_notification returns only the signed order identifier for server lookup. Fetch status independently from the fixed authenticated status endpoint; require exact stored order, merchant, IDR amount and optionally existing transaction identity. Unknown statuses/methods, absent currency/merchant/fraud or nonaccepted card fraud remain refused/HOLD. capture/settlement plus accept and200 yields PAID_EVIDENCE only; refund/partial refund/chargeback yields REVERSED. Durable ordering/idempotency/reversal/account-lock/expiry grants are a dependent checkpoint, not implemented or replaced by sandbox HMAC test events. No automatic charge, refund or tier mutation.

Use existing locked HTTPX0.28.1: fixed auth, connect5/read10second timeout, disabled environment proxies/redirects,64KiB decoded-response bound, duplicate/nonfinite/malformed JSON refusal and sanitized errors. Official Midtrans Python SDK evaluated from upstream snap.py/http_client.py: current request follows redirects and supplies no explicit timeout, so this bounded adapter uses already-locked HTTPX directly instead of adding that SDK. Official Snap request-body, notification and status documentation inspected2026-10-18. No vendor source copied. Authored offline fixtures only; actual merchant/card enablement, sandbox credentials, hosted-browser/provider/TLS acceptance and commercial price/duration remain absent.

Sources: https://docs.midtrans.com/reference/request-body-json-parameter ; https://docs.midtrans.com/docs/https-notification-webhooks ; https://docs.midtrans.com/reference/get-transaction-status ; https://github.com/Midtrans/midtrans-python-client .
