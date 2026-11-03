# 01 — Complete Product UX Workflows: Desktop, Mobile, Installable App

**Authority:** [approved product direction](../PRODUCT_DESIGN_BLUEPRINT.md), [frozen Method/Session/Protocol UX](../TRADING_METHOD_SESSION_SPEC.md), [subscription boundaries](../SUBSCRIPTION_ENTITLEMENT_SPEC.md). This file supplies implementation detail, not competing trading semantics. Routes below are target frontend navigation, NOT a claim these paths already run in production.

## User journey / sitemap

```text
Public Home → Sign In / Register / Verify / Recover
  → Methods (first use: create Method)
     → Create Method: FREE_STYLE or PROTOCOL
     → Method Overview (Sessions, Rules, Analytics, Instrument comparisons)
       → Create Session (one instrument / one feed / one pinned dataset version)
          → Session Overview → Replay Workspace
             ├ Chart, source quality, indicators, Objects, Drawings
             ├ Play/Pause/Step / one-click Jump next event, fixed 72h UTC
             ├ Quick or Planned Draft → Server Review → Confirm
             ├ Pending, Positions, History, Journal, Optional Setup Marker
             ├ Session Analytics → Trade/evidence detail
             └ Resume existing Session (same source+Method pin)
       → Instrument-within-Method Analytics → Method Analytics
  → Instrument Catalog / Status
  → Account / Subscription / Trash / Support
  → [Later] AI Scenario Research
```

## Complete screen inventory and states

| ID | Screen / purpose | Required primary actions | Error/empty/permission states |
| --- | --- | --- | --- |
| U01 | Public home, pricing, help/legal/status | actual coverage/rights and register | data planned vs admitted; no fake claims |
| U02 | Login/email verification/Google/recover/link | secure verified identity | expired/duplicate/unlinked; no silent account merge |
| U03 | Methods hub/first-use | Create Method, search, Resume last Session | empty Method requires creation |
| U04 | Method editor | FREE_STYLE or PROTOCOL once, save, archive | Protocol missing RR/risk/checklist; immutable rules after evidence |
| U05 | Method overview | Sessions, rules, instrument Analytics, new Session | no Sessions, no supported normalized stats |
| U06 | Instrument catalog/detail | list exact 16, inspect version/feed/quality/eligible dates | AVAILABLE/PARTIAL/QA_BLOCKED/RIGHTS_BLOCKED/PLANNED |
| U07 | Session creation | select Method, instrument/feed/time/start balance | source rights/coverage/profile/quota refusal |
| U08 | Session overview/trash | Resume, prior results, safe Delete/Restore | quota5/5, deleted30d, source missing |
| U09 | Replay terminal | Play/Pause/Step, 72h Jump, chart/pan/draw, orders | no lookahead, unresolved, EOF, queue busy |
| U10 | Order Draft → Review → Confirm | Planned Entry/SL/TP, Quick ticket, exact revision | stale review, Protocol refusal, missing quote |
| U11 | Pending/Positions/History/Journal | inspect, cancel eligible pending, notes, optional Mark/Skip setup | no trade vs pending vs unresolved |
| U12 | Session Analytics | trade metrics/curve, filters, inspect evidence | N=0, undefined R/FX, excluded data |
| U13 | Method Analytics | instrument-by-Method and Session comparison | overlapping research, incompatible capital/FX |
| U14 | Account/billing/quota | manage verified identity and plan; logout | offline, expired, billing sandbox/not live |
| U15 | Support/feedback/status | help, incident and product explanation | offline/unknown provider quality |
| U16 | Future AI scenarios | explicit scenario definition, run deterministic evaluator | not in V1 release; cannot infer missing opportunities |

All screens require desktop, tablet, mobile web and installable PWA layouts and IDLE/LOADING/EMPTY/READY/BLOCKED/STALE/ERROR states. No placeholder data labeled as real.

## Flow A — first Method and Session

1. User logs in and verifies account. Same real user with email and Google must explicitly link credentials after proof of possession; matching email **alone** is not linking proof.
2. New user opens U03 with "Create First Method". Choose `FREE_STYLE` or `PROTOCOL` **only at Method creation**; enter name and rules; display locked Protocol RR/risk/checklist and enforcement ON/OFF. Material Protocol changes require new Method.
3. U05 creates Session inheriting Method type. User selects one of the exact 16 symbols **only if qualified/admitted for chosen period**; pins original provider/feed/version/profile, start date, USD balance. No synthetic source substitution.
4. U09 loads only revealed historical candles, agreed chart/drawings, server Session cursor and pending/positions. U10 drafts a Planned position or Free Style Quick; chart anchor edits and numeric edits stay exact/synchronized; server Review then explicit Confirm.
5. After 1 valid lifecycle, user can journal, review Session analytics, close app/reload and Resume with the same immutable event history, Method and dataset identity. Method Analytics correctly groups other Sessions of this Method.

## Flow B — Free Style and Protocol

**Free Style:** mixed Quick and Planned entries; Quick Buy/Sell opens a ticket **without executing**; explicit review/confirm. Supported manual/partial exits and amendments permitted only within frozen contract. Price/lot display labels simulation, quote side and costs.

**Protocol:** Planned **pending Limit/Stop only**. Locked RR and risk sizing; moving Entry/SL recalculates derived TP and lot; checklist ON blocks unless all required PASS; OFF records actual PASS/FAIL/NOT_ASSESSED without fabricated PASS. No Quick, Market, active-position manual/partial close, or ad-hoc SL/TP modification. Pending cancellation before trigger is distinct, legal and journaled. Server refuses bypass even when frontend controls are hidden.

## Flow C — Jump next event

**Single click, no duration picker:** advance toward first trading-relevant event within **72 elapsed UTC hours**, processing every necessary intermediate quote. No event: reveal entire eligible 72h history at once, preserve all independent pending orders; no OCO/automatic expiry/invalidation. Source EOF or uncertain chronology: stop and explain, no invented fill. All resulting money/order state must hash-match chronological Play/Step on same commands; hidden future price may only be used in private controller and never delivered to UI or indicators.

## Flow D — analytics and source quality

Session includes separate completed trades, pending/open/unresolved counts, net realized cash, R only when valid, win rate with denominator, expectancy, profit factor, drawdown plus ledger/journal drilldown. Method scope groups by instrument and eligibility; repeated time windows/non-independent trades disclosed. No sum of mismatched account P&L, no fabricated portfolio equity/MDD and no present-day FX conversion for historical research. Source coverage, gaps, ambiguous ties and fee/slippage assumption always visible.

## Flow E — Free/Pro entitlement and lifecycle

Free account: **one tradable historical calendar-month segment per daily allowance**, maximum **five active/saved Sessions**, delete to Trash **30 days**. Chart context outside paid/tradable segment is read-only where permitted; open positions may resolve across segment boundary under canonical contract, not force-closed. Free and Pro share equal execution truth; Pro unlocks capacity/research depth, not trading correctness. Upgrade prompt near the actual quota boundary, never on a missing financial result.

## Flow F — optional opportunity notes and future AI

"Mark setup" / "Skipped setup" stores at-decision-time observed note with Method/Session/time/source, level label and author; NOT a real order or complete event detector. AI hypothetical scenarios are future separate versioned research jobs; only deterministic replay or complete eligible opportunity evidence may produce comparisons. Preserve original transactions. No forced implementation of AI scenario engine before current product beta.

## On every UI error

- Stale revision: refresh server state and require re-review.
- Timeout after Confirm: reconcile command/job receipt by ID; **never automatic second order**.
- Auth/logout/account switch: discard bearer/private caches and cancel stale requests; retain only non-financial drafts where secure.
- Offline/PWA background: informational shell allowed, **no local queued financial commands**, request current Session after reconnect.
- Unresolved source/FX quote: visibly distinguish research impossibility from loss-making trade.
- Narrow touch: chart drawing mode distinct from pan/zoom; order ticket always accessible without hover.

**Review signoff:** Claude maps each U-ID to desktop/mobile/PWA screen, component tree, required API DTO and deterministic mocks. Codex maps each U-ID to available backend routes and missing API contract additions before coding; reviewer enforces linked test evidence.
