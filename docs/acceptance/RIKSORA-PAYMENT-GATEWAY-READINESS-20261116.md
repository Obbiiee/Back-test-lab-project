# RIKSORA — payment-gateway (Midtrans) readiness audit and public-site build (2026-11-16)

Status: **IMPLEMENTATION REGISTER / AUDIT, not an architecture authority.** Scope: the public website a payment-gateway reviewer sees, its truthfulness against the repository, and what still blocks a Midtrans application. Legal texts are **drafts for the owner and a legal adviser**, not legal advice. Commercial V1 stays **BLOCKED**; this document does not change any gate.

## 1. Verdict
- **Website content: built and tested (draft).** Landing, Pricing (Rupiah), About, Contact, Terms, Privacy and Refund pages exist in `frontend/src/site/`, Indonesian default plus English for the marketing pages.
- **Ready to submit to Midtrans: NO.** Blockers are owner-supplied facts (15 fields enforced by a release gate), a live public HTTPS domain, owner approval of the legal texts, and a decision on data-source rights (section 6). Nothing below invents those facts.

## 2. Midtrans criteria vs this repository
Source: Midtrans documentation, [website/application criteria](https://docs.midtrans.com/docs/what-are-the-website-or-application-criterias-for-registering-a-midtrans-account) and [legal documents](https://docs.midtrans.com/docs/what-are-the-legal-documents-required-for-midtrans-account-registration) (both read 2026-11-16).

| Midtrans criterion | Status | Evidence / what is missing |
|---|---|---|
| Website ready, active, accessible, matching the registered business category | **MISSING** | No public domain/TLS/server yet (`docs/acceptance/RIKSORA-GO-LIVE-PLAN-20261115.md` phases B/F). Site content itself is ready. The Midtrans page also accepts "a link that represents your business" as an alternative while the site is not live |
| Product/service information clear and complete | **DONE (draft)** | Home page: purpose, 8 evidenced differentiators, how it works, plans, limitations, FAQ |
| Prices shown in Rupiah | **DONE (needs owner value)** | Pricing page renders `Rp` from `siteConfig.js`; the price is intentionally `null` until the owner sets it |
| Legal documents (individual: KTP and NPWP; PT/CV: deed, ministry decree, director KTP/NPWP, company NPWP, NIB/SIUP) | **OWNER** | Not a repository matter |
| Prohibited business types | **CHECKED, see section 4** | |

Not required by the pages above but standard for reviewers and for Google OAuth: terms, privacy, refund policy and contact details. They are built (drafts).

## 3. What was built
| Area | Files | Notes |
|---|---|---|
| Public pages | `frontend/src/site/SiteApp.jsx`, `site.css` | `/` (home), `/?page=pricing|about|contact|terms|privacy|refund`, `&lang=en` for English. Hosted visitors always land here; the local review/prototype routes stay local-only (`entryRoute.js`) |
| Copy | `frontend/src/site/content.js` | Eight differentiators as CLAIMS with evidence files; legal drafts with placeholders |
| Plans | `frontend/src/site/plans.js` | Free/Pro rules; a test asserts they equal `backend/cloud/entitlements.py` `FREE_LIMITS` |
| Owner facts | `frontend/src/site/siteConfig.js` | Every business fact starts `null`; nothing invented |
| Release gate | `frontend/scripts/verify-site-config.mjs`, `npm run build:release` | Refuses to build for release until all 15 items are filled and legal approval dates are set; also compares price/period with `BTL_BILLING_AMOUNT_IDR` / `BTL_BILLING_DURATION_SECONDS` when present |
| Account plan panel | `frontend/src/tickAlpha/AccountPlan.jsx`, `accountPlan.js`, `tests/account-plan.test.mjs` | Free/Pro status and Buy Pro (redirect allow-list) inside the account page |
| Tests | `frontend/tests/site-content.test.mjs` (`npm run test:site`) | Evidence files exist; no profit/guarantee/get-rich phrases; both languages cover the same sections; disclaimers present; Free limits equal backend; Rupiah formatting; routing |

Free/Pro rules shown (single source `plans.js`, enforced by the server): Free = one new Session per UTC calendar month and one newly activated historical month per UTC day; continuing a Session or re-using an activated month costs nothing; resets at 00:00 UTC = 07:00 WIB. Pro = no quota on those two items; tier comes only from a paid, unexpired server-side order; **not auto-renewing** (the implementation sells one period per payment). Export, Journal and Analytics are not tier-gated in code, so the pages say they are included in both.

## 4. Midtrans prohibited categories vs the product
Source: [Midtrans: can all types of businesses accept payments](https://docs.midtrans.com/docs/can-all-types-of-businesses-accept-payments-through-midtrans) (15 restricted categories, page updated 2026-06-04).
- **Not mentioned anywhere on the page:** forex, foreign-exchange trading, trading education, trading software/signals, binary options, crypto, software/SaaS subscriptions. So the page does not prohibit a backtest-simulator subscription.
- **Touching us, handled in copy:** item 2 (misleading content) and item 9 (Ponzi and get-rich-quick schemes). The site makes no profit claim, states "simulation, not investment advice, past performance does not guarantee future results", and a test bans phrases such as guaranteed profit, risk-free, get rich quick.
- **Item 13 (software platforms processing payments for others):** not applicable; RIKSORA collects only its own subscription fee.
- Midtrans adds that "each business type and payment method may have different compliance requirements". **Confirm the category with Midtrans (contact form) before applying.** This is the owner's action; the page does not settle it.

## 5. Claims matrix: what the site says vs what the repository proves
| Claim on the site | Evidence | Status |
|---|---|---|
| Fills at Ask for buys, Bid for sells; stops trigger on recorded ticks; never settled from candles | `backend/execution/engine.py`, `backend/tests/test_tick_execution.py`; invariants in `AGENTS.md` | PROVEN (tests) |
| No look-ahead; same-timestamp ticks processed together | `backend/ticks/timeline.py`, `backend/tests/test_tick_timeline.py` | PROVEN (tests) |
| Immutable receipts; journal/statistics from recorded events | `backend/tests/test_tick_execution_postgres.py`, `backend/execution/journal_order_index.py` | PROVEN (tests) |
| Jump to next event | `backend/execution/jump_next_event.py`, `backend/tests/test_window_jump.py` | PROVEN (tests) |
| Market and planned orders, stop/target, risk-percent sizing, several open positions, cancel/close | `backend/tests/test_tick_execution.py`; hedging and averaging exercised in the capacity harness | PROVEN (tests + QA harness, synthetic data) |
| Win rate, profit factor, drawdown, average R, balance curve, CSV and PDF export | `backend/execution/analytics_projection.py`, `backend/cloud/export_results.py`, `backend/cloud/export_pdf.py` | PROVEN (tests) |
| Sessions resume after interruption without duplicate orders | `backend/tests/test_research_queue.py`, `backend/tests/test_replay_run.py` (SIGKILL cases) | PROVEN (tests) |
| Per-user isolation; Free/Pro limits enforced on the server | `backend/tests/test_cloud_research.py`, `backend/cloud/entitlements.py`, `backend/tests/test_entitlements.py` | PROVEN (tests) |
| Payments by Midtrans; no card data stored | `backend/cloud/midtrans.py`, `backend/tests/test_midtrans.py`, `backend/tests/test_billing.py` (redirect checkout; no card fields) | PROVEN in sandbox mode only |
| Pro does not renew automatically | `backend/cloud/billing.py` (one order = one `duration_seconds`) | TRUE by implementation |
| Currently focused on XAUUSD; other instruments later | `docs/acceptance/RIKSORA-INSTRUMENT-DATA-INVENTORY-20261115.md` (only XAUUSD has a product execution profile) | TRUE |
| "Instruments and periods shown in the app per catalog and data-source approval" | existing landing wording and catalog contract | TRUE, deliberately conservative |

Deliberately **not** claimed on the site: licensed real market data, a number of supported instruments, historical accuracy against a broker, long-Session scale (the compact checkpoint V2 is QA-only), or any capacity figure.

## 6. Gaps and blockers (honest)
1. **Owner facts (release gate, now 13 items):** legal name and form, address, email, phone, tax note, enabled payment methods, refund window and conditions, and the approval dates for terms, privacy and refund. The domain and the Pro prices are supplied (item 11). `npm run verify:site` lists exactly what is missing.
2. **Public HTTPS site:** domain, TLS, reverse proxy and server (phases B/F of the go-live plan). Needs root actions or the owner's hosting step.
3. **Midtrans integration is sandbox-only in code.** `backend/cloud/midtrans.py` documents "fixed sandbox endpoints; no production switch", and `GET /billing/sandbox/plan` reports `mode: SANDBOX, fundsCollected: false`. After the owner has a Midtrans merchant account, the sandbox flow can be exercised with sandbox keys. A production switch (live endpoints, live keys, public notification URL) is a separate code change that needs the owner's explicit approval, because the standing rule forbids real payments until then. Notification-signature checking and idempotent state handling are implemented and tested (`test_midtrans.py`, `test_payment_provider.py`, `test_billing.py`).
4. **Account plan panel: BUILT (this change).** `frontend/src/tickAlpha/AccountPlan.jsx` shows Free or Pro, quota use and the reset time, and, when the server reports billing configured and the user is on Free, the Pro offer (Rupiah, period, no auto-renewal) with a Buy Pro button. It opens only a Midtrans hosted page over HTTPS (allow-listed host, tested against look-alike and `javascript:` URLs, `frontend/tests/account-plan.test.mjs`). Still unverified end to end: a real browser run against a Midtrans sandbox account, which needs the owner's sandbox keys.
5. **Refund tooling:** refunds are manual through the Midtrans dashboard; there is no admin tool and no automatic Pro revocation on refund. The Refund page therefore promises only a manual process.
6. **Data-source rights are UNKNOWN for all 544 verified dataset-months** (private QA only by the owner's standing rule). The owner has chosen to set the data cost aside for planning, but this remains a legal exposure for a paid product and for the Terms (section 7 says market data is subject to its source terms). The site does not claim licensed data; resolve before taking money.
7. **Commercial V1 gates stay BLOCKED** (16-instrument profiles, real-data admission, remote backup and CI, etc.); see `RIKSORA-RELEASE-READINESS-20261115.md`.
8. **Legal review:** terms, privacy and refund are drafts. Indonesian personal-data law (UU PDP) rights and retention wording should be checked by a lawyer; the privacy draft states account deletion by request and that immutable financial simulation records follow the retention policy.
9. **Tax:** the price page needs the owner's VAT/PPN statement (`taxNote`).
10. **Support process:** contact details and response time are owner inputs; someone must actually answer the mailbox.

11. **Pro pricing and domain (owner decision 2026-11-16).** Domain `riksora.com`. Prices actually charged: **Rp 87.000 per month (30 days)** and **Rp 400.000 per year (365 days)**, not auto-renewing; the yearly price is 62 % below twelve monthly payments (computed on the page from the real prices, not from an invented list price). Any further discount is applied by Midtrans at checkout and is not advertised on the site as a "regular price". **Server gap:** billing supports exactly ONE plan (`BTL_BILLING_AMOUNT_IDR` + `BTL_BILLING_DURATION_SECONDS`). Selling a monthly and a yearly period needs multi-plan billing (plan id in checkout, plans list endpoint, tests); the release gate refuses to publish until the server plans equal the site prices. For the Midtrans website evaluation alone the static site is enough; the multi-plan change is needed before payments are taken.

## 7. Recommended submission sequence
1. Owner fills `frontend/src/site/siteConfig.js` and approves the three legal texts (dates).
2. `npm run test:site && npm run verify:site && npm run build:release` pass.
3. Deploy the static build behind HTTPS on the owner's domain (go-live plan phase B).
4. Ask Midtrans (contact form) to confirm the business category, then register with the website URL (or a representing link while the site is not live), the legal documents, and the sandbox keys.
5. Wire the sandbox checkout end to end, test pay/fail/expire/duplicate notification, then request production activation.
6. The in-app plan panel is built (gap 4); verify it in a real browser with the sandbox keys during step 5.

## 8. Verification run (2026-11-16)
- **Tests:** `npm run test:site` (evidence files exist, no profit or get-rich phrases, language parity, Free limits equal backend, Rupiah formatting, routing, owner name absent), `test:account-plan` (redirect allow-list, entitlement summary, Rupiah offer), and the existing `test:tick-alpha` and `test:tick-review` all pass. `npm run lint` is clean (the vendored Chromium under `tests/browser-tools` is now excluded from lint).
- **Release gate:** `npm run build:release` and `deploy/site/publish.sh` correctly REFUSE while the three legal-approval dates are missing (verified by running them).
- **Real browser (Chromium headless shell, Playwright):** 10 pages x desktop (1280) and mobile (390), Indonesian and English, served under a non-local hostname so the hosted entry route is exercised: **20/20 render with no console errors, no failed requests, no horizontal overflow, and no unresolved "[diisi pemilik]" placeholders**. Two layout defects found and fixed (three plan cards wrapped on desktop; section headings misaligned in the white sections).
- **Publish safety found by this audit:** `frontend/public/market/xauusd-history.json` (2.3 MB) and `public/sample_XAUUSD_1h.csv` are copied into every build; `deploy/site/publish.sh` excludes them and refuses to publish them (data rights are UNKNOWN), and refuses any file containing a private term from `~/.config/riksora-private-terms.txt` (kept outside the repository).
- **Live infrastructure:** `https://riksora.com` serves a neutral holding page over HTTPS (Let's Encrypt, valid to 2027-02-14), `www` redirects, `/api/*` answers 404; reachability confirmed from the owner's own network (`Test-NetConnection ... 443 True`).
- **Not verified:** a real-browser run of the account plan panel against a Midtrans sandbox (needs the owner's sandbox keys); the full site on the live domain (waits for the owner's approval of the legal texts).

