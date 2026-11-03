# 10 — Claude Frontend: Exact Click-by-Click Navigation and State Map

**Status:** developer-ready interaction specification for review. Target routes are app presentation contract, not claim deployed. Consult [01 product flows](01_PRODUCT_UX_FLOWS.md), [05 verified API map](05_API_INTEGRATION_CONTRACT.md), and [canonical Method/Session spec](../TRADING_METHOD_SESSION_SPEC.md) BEFORE implementation. Every label here may be translated to UI language, but behavior and navigation must stay unambiguous.

**Product language:** Use **Trading Method** and **Session**, not alternating Strategy/Experiment names in primary navigation. Method types **Free Style / Protocol**, subscription tiers **Free / Pro**; clearly distinct. The icon/logo and dashboard visual language remain approved RIKSORA design. Top-level route names below are target URLs with safe compatibility for existing `?page=` and `?session=` links. Claude must not hijack historical bookmarks.

## NAV-0 Universal navigation, hierarchy, and persistent state

**Desktop app header** left: metallic R/RIKSORA logo (click → Methods hub), current workspace selector if applicable (click → list, selecting reloads scoped account/Session after auth), app tabs `Methods`, `Sessions`, `Catalog`, `Research` (only available authorized features), `Help`. Right: source/service status, user avatar dropdown (`Account`, `Billing`, `Trash`, `Sign out`). In Replay use compact context breadcrumb `Methods / [Method] / [Session] / Replay`; clicking any ancestor returns to detail without resetting backend cursor. **Method name** opens Method overview; **Session name** opens Session Overview; **symbol** opens source/eligibility detail in a side panel; **dataset version** opens provenance. Bottom save status shows `Saved revision N`, `Syncing`, `Checking command`, `Unavailable` and never fake local settled success.

**Mobile app navigation** bottom sticky `Methods`, `Sessions`, `Replay` (only for an existing selected Session), `Analytics`, `Account`; Catalog accessible via `Sessions → New Session → Choose symbol` and Account/menu, plus a top Search affordance. No horizontal navigation overflow; accessible overflow menu for Help, Catalog, Status and Logout. In replay, use single-line back breadcrumb with method/session and a quick Session Overview action. For width 320, abbreviate labels with matching accessible names; do not suppress financial status text. Tablet 600–1023 uses condensed left rail + responsive workspace.

**Back/forward and deep links:** desktop or mobile deep link to Session triggers authentication → verify actor/workspace → fetch current Session pin/revision → render Session Overview; no blind movement of cursor. Back from Confirm returns to Order Draft with unchanged draft unless source revision changes; Back from a committed order returns to replay with server state, never unsends it. Closing a drawer/dialog returns focus to the invoking control. Switching method/account while confirmation pending requires explicit cancel or reconcile check, never loses committed receipt.

**Unambiguous global states**: `INITIAL`, `LOADING`, `READY`, `EMPTY`, `OFFLINE`, `AUTH_REQUIRED`, `RIGHTS_BLOCKED`, `QA_BLOCKED`, `PARTIAL_SOURCE`, `ENTITLEMENT_BLOCKED`, `QUEUED`, `RECONCILING`, `STALE`, `UNRESOLVED`, `ERROR`. Display what a user can do next; no button active on an unsupported endpoint.

## NAV-1 Public → Authentication

| Starting surface / control | Click or input | Next screen or visible effect | Server requirement / edge |
| --- | --- | --- | --- |
| `/` hero **Start researching** | click | `/auth`; after verified login → `/app/methods` | returnUrl safe same-origin path only |
| Landing **See data coverage** | click | Public catalog summary: admitted symbols only, never all 16 claimed available | API source status; public subset or clearly static 'planned' |
| `/auth` **Continue with Google** | click | verified secure OAuth/PKCE; return to account / workspace; explicit linking if account conflict | Google proof, never silently merge email |
| `/auth` email + password **Sign in** | submit | loading, error inline or verified Methods hub | login token only appropriate secure memory/client; expiry handled |
| **Create account** | click | register form; required fields and validation; verify email instructions | registration/verification source |
| **Forgot password** | click → submit email | confirmation with privacy-neutral copy; reset link entry | no user existence leak |
| **Link Google or Email** in Account | explicit action | verified proof-of-possession and conflict/abort flow | linking API **not assumed implemented** |
| Logged-in avatar **Sign out** | click | clear authenticated requests, private response/cache/Service Worker data and UI; go landing/auth | server revoke where available; no Session delete |

No financial write from auth flow. Footer Terms/Privacy links should exist and disclose actual status if legal copy not yet finalized; do not ship fake legal placeholders as production documents.

## NAV-2 New Method to first Session

1. `/app/methods` with no Methods: central **Create Your First Method** button → `/app/methods/new`; explanatory Free Style vs Protocol cards, no fabricated performance.
2. Click **Free Style**: fields `Method name` (required), `Description/Hypothesis` optional, optional tags; RR and risk per-order remain flexible. Click **Protocol**: required Method name, fixed RR positive and exact, risk basis/value, ≥1 checklist condition, enforcement switch ON/OFF. Tooltips define ON requires all PASS; OFF preserves observed statuses but does not allow forbidden market/Quick/manual actions.
3. **Add checklist condition** adds named editable row; **Remove** removes only a draft row; invalid final zero conditions blocks Protocol Save. **Risk mode selector** uses only modes supported by actual contract; unknown mode must not be presented. **Preview Method Rules** opens summary, no write.
4. **Save Method** posts once with correlation ID. Loading disables duplicate submit. Success → `/app/methods/:methodId` showing saved name, exact type, rules and **Create Session** primary CTA. API refusal → field error and preserve draft; timeout → reconcile Method list before retry.
5. **Method Overview**: tabs `Sessions` (default), `Analytics`, `Rules`, `Journal/Notes` where supported. **New Session** → `/app/sessions/new?method=<id>`. **Archive Method** opens destructive confirmation: archived Method remains with history and cannot silently delete prior ledger; future Session creation only if allowed. **Method Analytics** → scope Method with instrument filters and comparability disclosures.
6. `/app/sessions/new` asks `Method` (prefilled, type read-only), `Session name`, `Symbol`, `Source/feed` (only qualified), `Eligible start period`, `Initial balance` and `Account currency` (USD for current scope); selected item shows source quality and version badge.
7. **Choose Symbol** → catalog drawer `U06`, 16 listed slots; blocked/planned entries **not selectable**, click them for reasons/coverage. Pick available instrument → return setup with pinned source+profile. **Start date** calendar disables unavailable dates; no promise of all five years. Change symbol invalidates source and start date selections, asks user to choose eligible period.
8. **Create Session** → server checks Method, quota, data/version/profile, membership, start; success → `/app/sessions/:sessionId` Overview. **Open Replay** → `/app/sessions/:sessionId/replay`; chart begins with server reveal cursor, never from fresh current market data. No data-file clone; creation does not read whole market year.

## NAV-3 Return user, overview, and archive

| Screen / control | Action | Result / state |
| --- | --- | --- |
| Methods hub Method card | click title | Method Overview, Sessions tab, current scope pinned |
| Methods hub **Resume last Session** | click | Session Overview (or directly Replay only when explicit action says Resume Replay) |
| Search Methods | type | case-insensitive client filter of bounded server results; empty result message and clear button |
| Session list **Filter by Method / Symbol / Status / last worked** | change | query/URL state sync, no Session mutation |
| Session row / card | click | Session Overview summary, source/period/Method identity |
| Session Overview **Resume Replay** | click | fetch authoritative revision/cursor → Replay |
| Session Overview **Analytics** | click | Session Analytics |
| Session Overview **Journal** | click | Journal scoped to Session |
| Session Overview **Delete / Move to Trash** | confirm | server move to Trash (Free 30-day policy), no immediate ledger purge |
| Trash **Restore** | click | server checks Free 5/5 quota; success returns saved list, refusal explains slot requirement |
| Session Overview **Duplicate/fork** | click | if supported, separate versioned Session with lineage and declared fork point; not overwrite prior trades |
| Back to Method | click | Method Overview with Session list/selection preserved |

## NAV-4 Trading terminal UI actions — authoritative behavior

| Control clicked | Immediate UI effect | Server or market effect | Cannot do |
| --- | --- | --- | --- |
| Symbol/source badge | opens qualified source detail drawer | GET catalog/source metadata only | switch active Session's immutable source pin |
| Timeframe 1m/3m/5m/15m/30m/1h/2h/4h/D | updates display candles and indicator rendering | bounded revealed chart query | trigger order, reset replay, load future |
| Candlestick/price style | chart view setting only where implemented | none | change financial side/quote |
| Fit / Reset chart | fit current revealed content | none | seek virtual replay time |
| Indicator button | opens searchable available indicator picker | none | install unsupported indicator as enabled |
| Drawing tool | activates explicit chart drawing mode | creates local draft, later persist via authorized research storage | post a trade merely by drawing |
| Objects | opens selected drawing/indicator hierarchy | selected object persisted on Save where supported | drop canonical fills |
| **Buy at Ask** | opens Free Style Quick ticket, Buy preselected | none until server Review+Confirm | immediate fill |
| **Sell at Bid** | opens Free Style Quick ticket, Sell preselected | none until server Review+Confirm | immediate fill |
| Long/Short Position tool | drag/tap anchors creates Planned draft, opens planner | no order until review+confirm | place order with mouse-down |
| **Review Order** | request validated frozen quote/profile/risk snapshot | server REVIEW operation only | commit financial fill |
| **Confirm Order** | pending confirmation, disable duplicate submit | idempotent server commit of order intent | assume market fill happened now |
| **Cancel confirmation** | close without new write | none | cancel already committed order |
| **Play/Pause** | animation/controlled ADVANCE requests, pause on user input | bounded tick chronology on server | use browser P&L |
| **Step** | one bounded replay advance (configured batch) | ADVANCE command with revision/id | skip necessary quote evidence |
| **Jump to Next Event** | one click, no popup; progress while scanning | exact server 72h UTC event search/advance | auto-expire unfilled pending |
| **Go to UTC date** | date/time popover and eligibility preview | SEEK subject to frozen rewind/fork/visibility rules | rewind committed finance in place |
| Pending row **Cancel** | confirmation, then server CANCEL | ledger cancellation if still pending | fake close an open position |
| Open Free Style row **Close/Partial** | quantity modal + review, server command | earliest eligible liquidation-side tick | immediate guaranteed exit price |
| Active Protocol position | locks manual exit/SL amend controls with explanation | server independently refuses forbidden command | client override |
| Journal tab **Add note** | linked order/Session note editor, Save | versioned note write only | rewrite trade |
| Analysis tab | computed statistics/curve from ledger | GET read-only analytics | naive mixed-currency portfolio sum |
| Download report | open formats/size/source-licensing disclosure | bounded async export | export licensed raw market tick without approval |

### Replay terminal command-state details

`READY → ADVANCE_QUEUED → RUNNING → RECONCILE → READY`; `UNRESOLVED` disables further affected financial commands; `EOF` disables forward but leaves history available; `OFFLINE` disables all financial actions, safely retains unsubmitted draft; `STALE_REVISION` reloads exact current Session then requires user review, never auto-reissues. On `Jump` if event exists, stop at first **causally valid** timestamp group and show affected order/position; else show "No eligible event in next 72h. Pending orders unchanged." On source gap/last covered time show exact boundary and status, no invented quote.

## NAV-5 Analytics / notes / billing and app lifecycle

- `/app/sessions/:id/analytics`: summary tiles and drawings tab with filters `all / long / short / period` (if supported); click equity point → matching executed event/trade; click completed-trade table row → detail with quote/evidence and linked Journal; disabled statistics show reason. Back to Session Overview or Replay preserves cursor.
- `/app/methods/:id/analytics`: `All eligible Sessions` scope, `Instrument` filter, source/period comparability warning, Session comparison table, click any Session → its analytics; no false combined account equity.
- `/app/journal`: search across authorized Sessions and Method, filter `observations / trades / pending / unresolved`; click row → Session Journal/evidence and optional "Open chart at revealed point" only if original Session allows navigation.
- `/app/account`: verified identity, linked auth methods, plan/quota, status, delete account export only when proper API exists; blocked controls replaced by truthful explanation.
- `/app/billing`: actual Free/Pro entitlements, daily reset label, supported checkout sandbox/production state. Billing never alters financial truth. Purchase state waits for server-confirmed entitlements; no optimistic Pro.
- PWA app icon launch → recover last safe route after verified identity, inspect Session; background app pauses animation, resume checks server. Logout wipes private cache. No offline financial command queue, no locally simulated fills.

## QA: mandatory click paths

`NAV-001` first-time Free Style → Method → Session → Planned order → review/confirm → resume → analytics.
`NAV-002` Protocol ON checkbox FAIL, Quick refused; OFF preserves NOT_ASSESSED but still refuses Market and manual close.
`NAV-003` 72h Jump no trigger maintains pending; next trigger/SL/TP parity with normal replay.
`NAV-004` stale/timed-out Confirm does not duplicate commit; refresh and same command ID inspect.
`NAV-005` mobile back gesture from order review never sends order; app background/resume no hidden clock.
`NAV-006` deep link to foreign Session denies access; account switch clears stale visible quotes and caches.
`NAV-007` 16 catalog slots never present blocked/missing provider as selectable.
`NAV-008` all navigation is keyboard/touch accessible and screen-reader labeled; 320–1440 widths.
