# Frontend execution matrix

Scope: frontend and presentation only. Codex owns API, auth, ledger, storage and market data. No deploy, no merge to `main`, no backend, finance or dataset change, no CP6A-10 benchmark, Annual PASS or VPS work. Merges and rollout need separate founder approval.

Visual source: design canvas artifact `5AHxbsfoT3xdaxuMi4mJMb`. Workflow source: PR #20 `docs/RIKSORA_DESIGN_FREEZE_V1/`. Tokens: `docs/design-tokens.md`. Backend requests: `docs/codex-api-requests.md`.

## PR state (checked on GitHub 2026-11-06, not from PR descriptions)

| PR | Branch @ head | Owner | Done and tested | Open / HOLD | Blocked on |
|---|---|---|---|---|---|
| #20 Integrated design | `design/riksora-integrated-freeze-v1-20261104` @ e81814a (draft) | founder/Codex docs | Used as the workflow contract | none from frontend | Owner approval (docs only) |
| #36 Terminal | `claude/terminal-drawings-indicators-v1` @ 7585607 (draft) | Claude | C-01…C-13, C-14 phone confirm sheet + Pick-from-chart (870bd20), C-14b draw search, local-only labels, landscape header, mobile gate numbers (7585607) | HOLD: low-memory phone (16 indicators ≈ 435 MB heap at 45k candles; windowing proposed as its own checkpoint); virtual keyboard on a real phone; 72h Jump (B07); cross-device drawings (B08) | Codex finance/API sign-off on review/confirm receipts, source profile, execution golden vectors |
| #38 Terminal preview | `codex/issue-37-terminal-preview` @ e75454f (draft) | Codex | not frontend-owned | Built on an older #36 head; #36 ships `previewOnly`, so a rebase only needs the preview files. Claude does not touch this branch or its deploy scripts | Codex rebase; administrator/owner approval for the installer |
| #39 Product frontend | `claude/product-frontend-v1` (draft, stacked on #36) | Claude | CP1, CP2, CP3, remediation P0/P1 (cc67d19, 5138b35, e25a691, 6985334), CP4 (efd3dbe), #36 C-14 merged (fd9a5ce), round 2 (9802ecb, df209de, 07bfb9c, 2f617a5, c360620, 587b99d) | Terms/Privacy pages; hosted account E2E (account routes are mocked in QA); the round-2 confirm fix is only on #39 (the #36 branch still has the C-14 sheet that says "not placed" on any failure; port it if #36 is merged on its own) | Codex DTOs listed below; REQ-02 receipt |
| #40 Storage proposal | `docs/session-storage-efficiency-20261105` @ c75e286 (draft) | Codex | Docs only | Frontend impact: none; the Continue card and Session overview read `GET /sessions/{id}`, so that DTO must stay stable | Owner + Codex |

## Acceptance table (founder remediation 2026-11-06)

| Issue | Files | Fix commit | Test proof | Result |
|---|---|---|---|---|
| P0 wizard guessed `maxPeriod` from the start year and treated a range as eligibility | `periodAvailability.js`, `AlphaSessionWizard.jsx` | cc67d19 | `test:period-availability` (cross-year, gap, rights, expiry, unknown schema, instrument change); `wizard-period-qa` 6/6 (refusal → Period, 409 → Review + same id, payload keys unchanged, 390/320) | PASS (frontend). Exact months: HOLD on Codex REQ-01 |
| P0 instrument shown but not sent | `AlphaSessionWizard.jsx`, `docs/codex-api-requests.md` | cc67d19 | Review states "pinned from this workspace's server profile"; payload unchanged | PASS (honest). Second instrument: HOLD on versioned `instrumentId` |
| P1 SearchableSelect activated disabled options after typing | `AlphaSelect.jsx` | 5138b35 | `select-qa` 4/4 (typing, Enter on disabled, Home/End/Arrow skip, Escape focus, Tab, outside click, long labels 320, touch sheet) | PASS |
| P1 phone sheet had no focus trap / scroll lock | `AlphaSelect.jsx`, `alphaProduct.css` | 5138b35 | `select-qa` phone step (aria-modal, Tab cycle, body overflow locked/restored, backdrop, Close) | PASS |
| P1 Journal drafts lost on navigation | `AlphaJournalPage.jsx`, `noteDrafts.js`, `productRoute.js` | e25a691 | `test:note-drafts`; `journal-drafts-qa` 7/7 (reload restore, picker/sidebar/Back guard, Cancel confirm, stale revision against the real API) | PASS |
| P1 `--lab-*` vs `--rk-*` token split | `riksoraBrand.css`, `alphaProduct.css`, `tickAlpha.css` | 6985334 | Product pages pixel-identical before/after; terminal QA suites green; AccessLint 0 | PASS |
| CP4 account/help/status/landing | `AlphaHelp.jsx`, `capabilities.js`, `AlphaHome.jsx`, `AlphaAccount.jsx` | efd3dbe | `cp4-qa` 4/4 (honesty checks, 3 pages × 8 viewports); AccessLint 0 | PASS. Google OIDC stays Not live until Codex gives the release SHA and `/auth/providers` contract |
| #36 phone REVIEW_EXACT / COMMIT_PENDING sheet | `AlphaReviewSheet.jsx` | 870bd20 | `review-sheet-qa` 7/7 (bottom sheet, arming delay, one confirm under double tap, Escape locked while pending, stale and refused states injected) | PASS (UI). Finance sign-off: HOLD on Codex |
| #36 Pick-from-chart mini ticket | `AlphaPickTicket.jsx`, `planningIntent.js` | 870bd20 | `review-sheet-qa` pick steps (grid price, focus, Escape, Quick → Plan disclosure, no review sent, 44 px at 390) | PASS |
| #36 menu clutter | `AlphaWorkspace.jsx` | 7585607 | `terminal-viewports-qa` Draw search step | PASS (search); further grouping open |
| #36 gestures / viewports / rotation / reduced motion | `tickAlpha.css` | 7585607 | `terminal-viewports-qa` 12/12 (9 viewports incl. 667×375 fix); `mobile-touch-qa` 6/6 | PASS. Virtual keyboard: HOLD (needs a real phone) |
| #36 heap profiling | `performance-qa.cjs`, `docs/terminal-mobile-gate.md` | 7585607 | Measured attribution; phone 390 at 4× CPU recorded | HOLD (windowing proposed separately) |
| #36 local-only persistence label | `AlphaWorkspace.jsx`, `IndicatorControls.jsx` | 7585607 | `terminal-viewports-qa` label check | PASS |
| Windows-path suites | `tests/stitch-analytics.test.mjs` (used by `scripts/regression.mjs`) | this checkpoint | Root cause: the default interpreter was hard-coded to `backend/venv/Scripts/python.exe`. Now platform-aware (`venv/bin/python` off Windows), `BTL_RESEARCH_PYTHON` still wins. With a Linux venv: `test:stitch-analytics` PASS and `test:regression` PASS (all registered tests) | PASS when a backend venv exists; the suite still needs Python + backend requirements installed |
| `tests/alpha-drawing-spike.test.mjs` | none | none | Fails on the base branch too (not in package scripts) | Pre-existing |

## Acceptance table (founder remediation round 2, 2026-11-06)

| Issue | Files | Fix commit | Test proof | Result |
|---|---|---|---|---|
| P0 false "order not placed" after a commit whose refresh failed, or on any transport error | `confirmOutcome.js`, `TickAlpha.jsx`, `AlphaReviewSheet.jsx`, `client.js`, `accountClient.js` | 9802ecb | `test:confirm-outcome`; `confirm-outcome-qa` 7/7 against the real local backend: (a) POST 200 + refresh 503 → "Order saved" + Reload, (b) commit + lost response → unknown → GET finds it, (c) real server 409 → refused, no order, (d) 503 → unknown, banner, orders locked, no resubmit, (e) double tap → 1 POST, (f) Back held / reload → no false claim, 1 POST each, (g) reconciliation finds saved, or Session moved on → not saved. Every case counts /confirm POSTs and watches the DOM for "not placed" | PASS (frontend). Receipt contract: **HOLD: CODEX RECEIPT INSPECTION** (REQ-02) |
| P1 `writeDraft` returned true without storage | `noteDrafts.js`, `AlphaJournalPage.jsx` | df209de | `test:note-drafts` (absent, null, throwing accessor, quota); `journal-drafts-qa` blocked + full storage at 390: warning, summary "not kept", leave dialog "Leave and lose text" | PASS |
| P1 every Journal exit | `AlphaJournalPage.jsx`, `productRoute.js` | df209de | `journal-drafts-qa` 13/13: picker, sidebar, Back, Forward, Open replay (no load on Keep editing), Account link (another document, no double prompt), direct URL (browser prompt), Cancel; Keep editing and Leave | PASS |
| P1 PARTIAL instrument with AVAILABLE months | `periodAvailability.js`, `AlphaSessionWizard.jsx`, REQ-01 | 07bfb9c | `test:period-availability` fixtures PARTIAL / RIGHTS_BLOCKED / QA_BLOCKED / PLANNED / unknown + GAP; `wizard-period-qa` 7/7 (PARTIAL stays closed with reason) | PASS (fail-closed). Meaning of PARTIAL: open question to Codex in REQ-01 |
| P1 hardcoded XAUUSD in the workspace | `display.js#sessionInstrument`, `TickAlpha.jsx`, `AlphaSourceDetails.jsx` | 2f617a5 | `session-instrument-qa` 3/3 (real profile + review payload keys unchanged; labeled EURUSD rewrite changes header, chip, aria, phone title, source details; missing instrument → "Instrument not stated", Buy/Sell locked) | PASS. Landing page copy still says XAUUSD (marketing copy for the local Alpha) |
| P1 AlphaSelect `aria-haspopup="listbox"` vs dialog panel | `AlphaSelect.jsx` | c360620 | `select-qa` 4/4 asserts haspopup=dialog, aria-controls=panel id while open, combobox controls listbox | PASS |
| UX: Session tables scroll sideways on phones | `AlphaProduct.jsx`, `alphaProduct.css` | 587b99d | Before/after in `docs/evidence/remediation-r2/ux-sessions-*`; `product-qa` 23/23 | PASS (bounded pass; workspace declutter not started) |

Evidence for round 2 is committed in `frontend/docs/evidence/remediation-r2/` so it is visible on GitHub.

## Shared components

| Component | File | Notes |
|---|---|---|
| SearchableSelect / InstrumentPicker / MethodPicker | `src/tickAlpha/AlphaSelect.jsx` | Combobox in a popover; guarded active option; modal phone sheet |
| Period availability | `src/tickAlpha/periodAvailability.js` | Fixed / unpublished / published modes; never infers months from a range |
| Note drafts + leave guard | `src/tickAlpha/noteDrafts.js`, `productRoute.js#setLeaveGuard` | Tab-scoped drafts; route guard for links, picker and Back |
| Capabilities | `src/tickAlpha/capabilities.js` | One source for Help, Account and landing status |
| Review sheet / Pick ticket | `src/tickAlpha/AlphaReviewSheet.jsx`, `AlphaPickTicket.jsx` | Confirm step states (review, pending, saved, refused, stale, unknown); chart pick → draft field |
| Confirm outcome | `src/tickAlpha/confirmOutcome.js` | COMMITTED / REFUSED / STALE / UNKNOWN and read-only reconciliation |
| Chart settings popover | `src/tickAlpha/AlphaChartSettings.jsx` | Fit, Grid, Crosshair, Volume (disabled: no source volume), Full screen |
| StatePanel / PageHead | `src/tickAlpha/AlphaShell.jsx` | loading, empty, filtered, error+retry, offline, unavailable |

## Backend dependencies

REQ-01 start months (and the meaning of PARTIAL); REQ-02 confirmation receipt; versioned `instrumentId` on `POST /sessions`; Session list with cursor and counts; Method edit/archive; 16-instrument availability; entitlements/quota; Trash/Restore; cross-Session journal; Method analytics aggregation; Google OIDC release contract; plan/billing; drawing sync (B08); 72h Jump (B07). Until each exists, the UI says "not published yet" and shows no estimate.

## Rollback

Every checkpoint is its own commit on a draft branch; nothing is merged or deployed. Reverting a checkpoint is `git revert <sha>` on the same branch (no force-push). #39 depends on #36 through merge commits e101165 and fd9a5ce.
