# RIKSORA product screens U01–U16: inventory and checkpoint plan

Baseline: branch `claude/product-frontend-v1` from PR #36 head `6fbcc67` (C-01…C-12 kept). Other refs checked: main `8ba3489`, PR #20 design pack `e81814a`, PR #38 preview `e75454f`. This branch depends on PR #36 and should be merged after it. It does not depend on PR #38 and does not touch backend code.

Visual source: the RIKSORA design canvas artboards (AuthSignIn, AuthStates, Strategies, Statistics, NewSession, Journal, Account, SystemStates, Workspace, MobileTrading). Behaviour source: `docs/RIKSORA_DESIGN_FREEZE_V1/01, 10–13, 17` plus the founder instruction of 5 Nov 2026 on PR #36.

Status values:
- **existing**: a usable screen is already there.
- **partial**: something exists, but it is missing states or the right structure.
- **missing**: there is no screen.
- **backend-blocked**: the screen can only be honest once Codex adds the named field or route.

## 1. Data the frontend actually has today

| Transport | Routes used | DTO fields available |
| --- | --- | --- |
| Local (`127.0.0.1:5188/api/v1/tick-alpha`, localhost only) | `GET /catalog` | `methods[]`: id, name, kind, rr, riskPercent, checklistOn, conditions<br>`sessions[]`: id, name, methodId, initialBalance, startPeriod, datasetId/Version<br>one `profile` (instrumentId, feedId, providerId, tickSize, lot rules)<br>`label`, `startPeriod` |
| | `POST /methods`, `POST /sessions` | create only. No update, archive, list paging or delete. |
| | `GET /sessions/{id}` | metadata, method, quote, `state` (balance, throughNs, revision, ended, unresolved, orders) |
| | `POST /sessions/{id}/view` | the above plus candles and `analysis` (Session metrics, equity window, orders, completed) |
| | `GET/POST /sessions/{id}/journal`, `/bootstrap`, `/commands`, `/confirm`, `/chart-history` | Session-scoped |
| Account (`/api/v1/auth/*`, `/api/v1/workspaces/*`, HTTPS only) | login, me, logout, logout-all, register, verify, request-verify-token, forgot/reset-password | bearer token held in memory only<br>workspaces list/create<br>research routes mirror the local ones under `/workspaces/{id}/research` |

There is no Method description or hypothesis, no created/updated/last-used time, no per-Session cursor or order counts in the catalog, no multi-instrument catalog, no Method or instrument aggregation, no trash, no plan/usage, and no Google OAuth route.

## 2. Screen inventory

Legend for the "Fix in" column:
- **CP1**: the frontend checkpoint that comes next.
- **CP2–CP4**: later checkpoints.
- **Codex**: the backend gap must close first.

| ID | Screen | Route today → target | Component today | Status | Missing / gap | Fix in |
| --- | --- | --- | --- | --- | --- | --- |
| U01 | Landing, help, legal | `?page=home` (local) → `/` public | `AlphaHome.jsx` | partial | Coverage section must say only what is admitted (one synthetic or XAUUSD feed today).<br>Terms/Privacy/Status pages are missing.<br>No "16 pairs" claims. | CP4 |
| U02 | Sign in, register, verify, recover | `?page=account` → same plus `&auth=signin\|register\|verify\|forgot\|reset` | `AlphaAccount.jsx` (six-button mode switcher) | partial | One card per job (canvas AuthSignIn/AuthStates).<br>Password reveal.<br>Generic anti-enumeration success.<br>Expired-session and HTTPS-required states.<br>Return to the allowed deep link after sign-in.<br>Google shown as unavailable (no provider contract).<br>Token stays in memory, so a refresh means signing in again. | CP1 |
| U03 | My Methods (dashboard) | none (the hub is Session-first) → `?page=methods` (default after sign-in or local open) | `AlphaSessions.jsx` | partial | Method-first list.<br>Continue-research card.<br>Search, filter by type, sort.<br>First-use "Create your first Method".<br>Empty, filtered-empty and error states.<br>The summary has only what the catalog proves: Method count and Session count. | CP1 (last-used, hypothesis and activity are Codex) |
| U04 | Method create / rules | modal `dialog==='method'` → `?page=method-new` | form in `TickAlpha.jsx` | partial | Full page with type cards and a Protocol rules section (RR, risk, checklist ON/OFF, conditions).<br>Summary panel "How this Method trades".<br>Hypothesis field blocked (no DTO field).<br>Edit and archive blocked. | CP1 create; edit is Codex |
| U05 | Method overview (tabs Overview / Sessions / Analytics / Rules) | none → `?page=method&method=<id>&tab=` | none | missing | Header (name, type).<br>Sessions table (name, instrument, start month, starting balance, Open).<br>Rules tab read-only.<br>New Session.<br>Cursor and order counts per Session need N reads, so they are not loaded in a list (Codex list DTO). | CP1 |
| U06 | Data catalog (16 targets) | Data source dialog → `?page=catalog` | `AlphaSourceDetails.jsx` | partial | The 16-target list with status needs a catalog-availability DTO. Until then only the one admitted profile is shown as Available, and the rest is an explicit "status not published" list (no invented status). | CP2 (Codex for statuses) |
| U07 | New Session wizard | modal `dialog==='session'` → `?page=session-new&method=<id>` | form in `TickAlpha.jsx` | partial | Steps Method → instrument/source → eligible period → initial USD balance → summary.<br>Symbol change resets the period.<br>Quota from the backend is missing (Codex). | CP2 |
| U08 | Session overview / trash | none (opening a Session goes straight to replay) → `?session=<id>&view=overview` | none | missing | From `GET /sessions/{id}`: method, source pin, cursor UTC, revision, starting vs current committed balance (labelled differently), pending/open/closed/unresolved counts.<br>Resume, Journal, Analytics.<br>Trash is Codex. | CP2 |
| U09 | Replay terminal | `?session=<id>` | `TickAlpha.jsx`, `AlphaWorkspace.jsx` | existing (C-01…C-12) | Breadcrumb Method › Session and saved state.<br>Jump 72h is Codex B07. | CP3 consistency only |
| U10 | Order Draft → Review → Confirm | ticket in `TickAlpha.jsx` | `AlphaOrderPresentation.jsx` | existing | Mobile REVIEW_EXACT/COMMIT_PENDING full sheet.<br>Pick-from-chart mini-ticket. | CP3 |
| U11 | Journal / trade detail | dialog `journal` → `?session=<id>&view=journal` | `AlphaJournal.jsx`, terminal tabs | partial | Page form with filters (UTC, side, status).<br>Detail drawer with provenance.<br>Cross-Session journal needs a list route (Codex). | CP3 |
| U12 | Session analytics | terminal tab Analysis → `?session=<id>&view=analytics` | `AlphaTerminal.jsx` | partial | Full page with scope header, primary row (net, N, win rate with denominator, expectancy, PF, max DD), committed balance path with an accessible table, and exclusions.<br>Values only from `analysis`. | CP1 layout, CP3 complete |
| U13 | Method analytics + instrument breakdown | none → `?page=method&method=<id>&tab=analytics` | none | backend-blocked | Needs a server aggregation route (pooled eligible counts, expectancy R, PF, Session inclusion/exclusion).<br>The frontend shows the layout with a "not published yet" state plus a per-Session table of links. No client averaging. | CP1 layout; numbers are Codex |
| U14 | Account, usage/plan | `?page=account` signed-in state → `?page=account&tab=` | `AlphaAccount.jsx` | partial | Identity, security (sign out / sign out all), workspace memberships.<br>Plan/usage unavailable (no entitlement DTO).<br>Checkout unavailable. | CP4 |
| U15 | Help / support / status | `AlphaFeedback.jsx` dialog → `?page=help` | `AlphaFeedback.jsx` | partial | Help topics, data limitations FAQ, report issue (local only).<br>Status unknown unless an endpoint exists. | CP4 |
| U16 | AI scenarios | none | none | out of V1 | Not shown. No disabled fake button. | none |

Cross-cutting shell pieces (all status **missing** today):
- Desktop sidebar: My Methods, Sessions, Data Catalog, Journal, Analytics, with Account and Help at the bottom.
- Mobile 5 tabs: Methods, Sessions, Replay (requires a Session), Analysis, Account.
- Breadcrumbs.
- State components: loading, empty, filtered-empty, error+retry, offline, expired-auth, forbidden, unavailable.

## 3. Backend gaps for Codex (frontend keeps working on isolated fixtures)

| Screen | Action | DTO field / route needed | Today | Fixture | Blocked live state | Acceptance |
| --- | --- | --- | --- | --- | --- | --- |
| U03/U05 | Show hypothesis and last used | `method.description`, `method.createdAtUtc`, `method.lastUsedAtUtc` | MISSING | local synthetic backend only | field hidden; card says "Last used: not recorded" | Card renders the server value; hidden when absent |
| U03/U05 | Session list with cursor and counts | `GET /sessions?methodId=&cursor=&limit=` returning throughNs, revision, pending/open/closed/unresolved, updatedAtUtc | MISSING (catalog has metadata only) | same | the list shows start month and starting balance only | No per-Session view calls from list screens |
| U04 | Edit / archive Method | `PATCH /methods/{id}` with expectedRevision, evidence lock, archive | MISSING | none | Rules tab read-only, Archive not shown | 409 on locked evidence shown inline |
| U06/U07 | 16-target catalog status | `GET /catalog/instruments` with status AVAILABLE/PARTIAL/QA_BLOCKED/RIGHTS_BLOCKED/PLANNED, eligible ranges, feed/version, rights | MISSING (single profile) | none (no invented status) | one Available row plus "Status not published" for the other targets | Only AVAILABLE rows selectable |
| U07 | Quota | `GET /entitlements` (active Sessions used/limit, reset tz) | MISSING | none | "Limits are checked when you create" | Refusal code shown inline |
| U08 | Trash/restore | `POST /sessions/{id}/trash`, `/restore`, `GET /sessions?state=TRASHED` | MISSING | none | not shown | 30-day expiry from server |
| U11 | Cross-Session journal | `GET /journal?methodId=&sessionId=&cursor=` | MISSING (per Session only) | none | Journal page requires a Session pick | Paged, bounded |
| U13 | Method analytics | `GET /methods/{id}/analytics?instrument=&from=&to=` with pooled eligible N, wins, expectancyR, profitFactor, included/excluded Sessions with reasons | MISSING | none (no invented numbers) | "Method analytics is not published yet" plus per-Session links | No client averaging of win rates; no stitched equity |
| U02 | Google sign-in and linking | OAuth provider routes + link-with-proof | MISSING on this branch | none | Google button disabled with reason | Never merge by email |
| U14 | Plan / usage / checkout | entitlement + billing status | MISSING | none | "Plans are not live yet" | No payment form |

## 4. Checkpoint order

1. **CP1: shell, auth, My Methods, Method overview, analytics layout.**
   - Product shell: sidebar + 5-tab mobile nav, with routing through query params so that old `?session=` and `?page=account` links still work.
   - `AlphaAccount` rebuilt per canvas AuthSignIn/AuthStates. After sign-in it goes to My Methods, or back to the allowed deep link.
   - My Methods page from the catalog.
   - Method create page (full form).
   - Method overview with Overview/Sessions/Rules tabs and an Analytics tab layout with the honest "not published" state.
   - Session analytics page layout reading `view.analysis`.
   - Shared state components.
   - QA: first-user and returning-user flows on local.
2. **CP2: catalog and Session.** Catalog page (honest statuses), New Session wizard, Session overview (starting vs current committed balance).
3. **CP3: replay and records.** Replay header breadcrumb and saved state, mobile review/commit-pending sheet, Journal page, Session analytics complete.
4. **CP4: public and account.** Landing coverage section, Account/plan/help/status pages, legal placeholders linking to owner-provided text.

Each checkpoint ships: lint, the registered unit/regression tests, browser QA at 1440/1280/1024×768/768/390/375/320 and landscape, AccessLint scan, screenshots that match the commit SHA, a commit and push, and a PR update. Design done is not the same as backend done, deployed, or release PASS.

Rollback: the branch is stacked on PR #36. Reverting the CP merge restores the C-12 shell. No storage keys change, and existing `?session=`/`?page=account` links keep working.
