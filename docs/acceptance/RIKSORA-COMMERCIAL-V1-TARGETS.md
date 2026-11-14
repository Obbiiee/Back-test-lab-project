# RIKSORA Commercial V1 — Capacity Target & Definition of Done

> Owner target baseline: 2026-11-13. Status: TARGET APPROVED FOR PLANNING; **NOT ACCEPTED / NOT LAUNCH-READY**.
>
> This is a finite *release acceptance specification*, not a second roadmap, permission to alter frozen contracts, permission to use real market data, or authorization for deployment, charging, merge, or VPS access.
> The long-term plan remains [ROADMAP.md](../ROADMAP.md); operational authorization remains [AI_CONTEXT/04_CURRENT_PHASE.md](../../AI_CONTEXT/04_CURRENT_PHASE.md), safety rules remain [AGENTS.md](../../AGENTS.md), and implementation evidence belongs to the existing [V1 Integration Register](RIKSORA-V1-FREEZE-INTEGRATION-REGISTER-20261108.md).

> **LATEST OWNER ARCHITECTURE OVERRIDE — 2026-11-13:** [Hybrid tick-on-VPS + nine precomputed OHLC timeframes on private Cloudflare R2](../architecture/RIKSORA-HYBRID-NINE-TF-R2-OWNER-DECISION-20261113.md) supersedes conflicting **architecture/transport/cache** proposals below, including local-first browser financial execution, runtime browser M1→D1 candle aggregation, and the historical exception for D1's **active 5,000-bar chart cache**. The latest policy is **5,000 active chart candles for every selected timeframe including D1**, but unrestricted qualified archive pagination for all timeframes; initial ≤512-bar and older 500–1,000-bar pages remain. The existing financial acceptance, data-rights, safety, and true-date-range-count gates remain intact. This linked architecture is **NOT YET IMPLEMENTED / ACCEPTED**, and the most recent locally reported BID M1 sidecar is a partial foundation, not a nine-timeframe R2 product pipeline. See linked decision for the MID/BID display compatibility requirement and protection of unpublished local commits.

## OWNER PRODUCT CONTRACT — 2026-11-15: Commercial V1 end-to-end website, Free/Pro, and Claude engine integration

> **Status: NEW OWNER PRODUCT TARGET / IMPLEMENTATION SPECIFICATION; NOT A CLAIM OF DONE, LIVE INTEGRATION, QUALIFIED MARKET DATA, OR PAYMENT READINESS.** This section records the owner's latest requested Commercial V1 *user-facing product contract*; its explicit product/entitlement decisions override older inconsistent quota and journey wording (for example the 2026-10-23 draft's five Free saved Sessions and older unspecified Free/Pro limits). Existing frozen money/provenance/source-rights/security contracts remain protective authorities. Architecture/transport follows the [2026-11-13 hybrid owner decision](../architecture/RIKSORA-HYBRID-NINE-TF-R2-OWNER-DECISION-20261113.md). Deployment/merge/paid launch still require separate operational authorization and evidence.
>
> **One-line V1 promise:** a new trader can visit RIKSORA, log in with Google, create Free Style or Protocol Method, create a Session, analyze historical price charts, run correct tick-based simulation (normal/fast/Jump), confirm trades, inspect persistent Journal/Statistics, logout and resume; upgrade through an actually verified Midtrans transaction; and run unrestricted *qualified* history according to Pro entitlements. Every user is private from every other user.
>
> **Priority:** reach a usable, demonstrably correct *product* first, not merely a fast local engine benchmark. Do not replace the hosted application with the single-user Claude experiment server or lose existing working UI, Method/Session, PostgreSQL, receipts, Journal, or analytics.

### A. Product information architecture and complete user journeys

Required public surfaces: **Landing**, Features/How it works, Pricing (Free vs Pro), Login/Registration, FAQ/Support, basic legal/data-quality disclosures. Public pages should be accessible on mobile, lightweight, fast, and consistent with the existing RIKSORA design identity.

Required private surfaces: **Onboarding → Methods → Sessions/Dashboard → Backtest Workspace → Journal → Statistics**, plus Account/Billing/Support. Main workspace must be chart-first; pair search, method and Session identity, source/version/time, replay controls, drawing tools, indicators, Long/Short planning, order review, Open/Pending/Closed positions and results must be discoverable without overwhelming the chart. Reuse existing correct components before redesigning.

**New user (happy path):**
1. Visitor opens RIKSORA → chooses **Continue with Google**.
2. Owned Google OAuth/OIDC credentials and registered HTTPS callback complete a real authorization-code/PKCE/state/nonce transaction. Backend validates issuer/audience/signature/expiry, uses stable provider subject, and establishes a revocable first-party authenticated session; do not silently merge accounts on matching email, persist Google tokens in frontend URLs, or treat mocks as a completed login.
3. New account receives **Free** server-side entitlement. Existing authenticated user goes to Dashboard. Unconfigured Google OAuth must fail clearly, not expose fake successful login.
4. First use creates a Trading Method of type **FREE_STYLE** or **PROTOCOL** (see below).
5. User creates a named Session by choosing Method, one qualified pair, starting balance, source identity and eligible historical start/range. Session inherits Method type; no redundant Method type picker; timeframe is changeable later.
6. Backtest Workspace opens; user analyzes chart, replays, places eligible orders, reviews/confirms, reads Journal/Statistics, and can leave and later continue without losing committed evidence.
7. Upgrade path: Pricing → Pro checkout → verified Midtrans payment status/webhook → internal billing ledger → Pro entitlement → same account and preserved research data. Account shows actual subscription period and transaction status.

**Terminology/integrity:** one Method can own multiple Sessions; each Session binds **exactly one pair, one Method, one immutable feed/source identity and one chronological financial account**. Pro 'all pairs' means every qualified catalog pair may be selected across unlimited separate Sessions; **not** simultaneous mixed-pair execution in one Session. A Pro Session can traverse **all qualified tick history for its one selected pair as a continuous user experience**, even if backend data/jobs are partitioned internally by month/day. Historical OHLC context is never financial execution authority.

### B. Free versus Pro — explicit commercial entitlement matrix

| Policy | FREE (Rp0) | PRO |
| --- | --- | --- |
| Google login and private account | Yes | Yes |
| Trading Method types | Free Style and Protocol | Free Style and Protocol |
| Methods quota | **1 usable Trading Method per account** | **No product-count quota** |
| Pair trading eligibility | **1 chosen pair per account** during Free entitlement; enforce server-side against Method/Session/API | All **qualified** available pairs (intended 16-symbol catalog) |
| Trading-history entitlement | At most **12 consecutive calendar months of qualified tick history** per Free Session, confined to its eligible/pinned window | **Entire qualified available tick range** for that Session's chosen pair, chronological and continuous |
| Session creation | **1 new Session per UTC calendar month** per Free account; creation tokens do not accumulate | **No product-count quota**; unlimited Sessions |
| Replay time allowance | **1 historical calendar-day replay window per UTC day**, reset at 00:00 UTC; unused allowance expires and **never rolls over** | **No daily replay allowance restriction** |
| Free Style / Protocol, chart, Jump, fast replay, planning, basic Journal and Statistics | Available within valid entitlement and method constraints | Available |
| Additional research/statistical modules | Basic reliable statistics; advanced research may be gated according to implemented capabilities | Extended actually implemented features; do not advertise missing Monte Carlo/AI as already live |
| Compute resources | Fair bounded queue and abuse protection | Fair bounded queue and abuse protection; **unlimited Sessions does not mean unlimited simultaneous CPU jobs** |

**Free allowance exact behavior target:** A UTC day is determined by server clock, not device time. One replay allowance grants a single chosen **historical trading-calendar day** on that real UTC date. The allowance is consumed by the first successful replay activity/activation, not by opening a dashboard or merely examining already-eligible historical chart context. Pause, reconnect, logout/login and resume must not spend another allowance for the *same active daily historical window*. Once exhausted, **block further replay advancement outside the eligible window**, surface next reset, preserve pending orders, position state and every prior receipt, and allow read-only access consistent with entitlement. Never force-close a position, silently move the cursor, or fabricate a trade at midnight. No stockpiling; changing browser clock, deleting/recreating Session, simultaneous tabs, changed IDs or raw API requests cannot multiply allowance. Treat these detailed accounting choices as implementation interpretation of the owner's explicit '1 hari, tidak bisa dikumpulkan' target and expose them clearly in UX.

**Free one-Method/one-pair/one-year implementation:** Separate durable account-level eligibility/usage records from Session rows; deleting/archive/recreating resources cannot bypass quotas. If a customer later changes selected pair or 12-month historical window, that requires a defined server-side entitlement transition, not an implicit loophole. Old historically committed research must remain preserved. A Session continues past a calendar-month quota boundary without resetting balance or consuming an extra *Session-creation* token; chronology and the replay-day allowance still apply.

**Downgrade/expiry:** Pro → Free may prevent new replay, out-of-policy Session creation or Method creation, but **must not delete, rewrite, reset or cross-link** Pro evidence, Session, receipts or Journal. Continue read-only review of previously owned evidence subject to the documented retention/security contract, show upgrade CTA, and resume existing eligible work after re-upgrade. A cancelled payment/chargeback/refund must be reconciled without losing historical financial integrity.

**Pricing:** Prior workflow contains Rp139.000/month and Rp1.668.000/year as owner-draft prices. Store prices, billing periods, tax and discounts **on the server as configurable catalog entries**; they are **not final approved commercial prices** and must not be hardcoded into the frontend. Obtain explicit owner sign-off before any live charging. Only Free and Pro are product tiers in V1.

### C. Google authentication, Midtrans billing and tenant security

**Google:** real sign-in with owner-controlled Google OAuth credentials, exact registered redirect, secure HttpOnly/SameSite cookies as appropriate, CSRF defense, revocable login/session lifecycle, logout-all, account disabled handling, stable provider subject mapping, safe account linking and recovery. Reuse [security architecture](../SECURITY_ARCHITECTURE.md) and existing authenticated account model. Pass Google credential-less offline fixtures separately from browser/OAuth acceptance with a real configured provider; never mark the latter PASS without a successful real exchange.

**Midtrans:** Pricing → create server-priced invoice/order → official Midtrans checkout/Snap workflow in sandbox → payment notification verification (signature/merchant credentials/status) → idempotent durable billing ledger → server-side entitlement activation → account payment history and Pro expiry. Handle pending/failed/expired/duplicate/replayed/out-of-order notifications, browser redirect without payment, retry, cancellation and applicable refund/chargeback reconciliation. Do not activate Pro based on client-supplied status/redirect or expose payment secrets in browser. Sandbox end-to-end tests and production merchant readiness are separate gates. Frontend should show truthful pending/paid/failed state and not assume that payment completion is instant.

**Tenant isolation (P0):** authenticated user A must not read, modify, execute, export, subscribe to, or infer user B's Methods, Sessions, Orders, Trades, Journal, Statistics, exports, billing, object storage, worker jobs, progress streams, cached Session data or admin-only details by changing IDs, using API directly or through concurrent requests. Enforce ownership at backend/service/database/query/storage boundaries, not merely hiding buttons. Treat all user research private by default. Test cross-tenant IDOR, horizontal and vertical authorization, subscription events, cache poisoning, job queue ownership, object storage URLs, account linking and token revocation. Operations/admin requires separate, audited authorization. Retain least privilege, HTTPS, rate limiting, secrets separation, backups and restore drills.

### D. Free Style versus Protocol — non-negotiable behavior

A Trading Method owns exactly one **type**, FREE_STYLE or PROTOCOL; a Session inherits it. Both are available under **both Free and Pro subscriptions**; do not confuse the Free Style type with Free entitlement.

**Free Style:**
- **Quick Execution:** user selects Buy/Sell and permitted size → review/explicit confirm as required by canonical order contract → market order fills only at next eligible historical tick using correct side of Bid/Ask. Supported discretionary manual/partial close remains possible; no mandated checklist.
- **Planned Execution:** Long/Short Position Tool or Plan ticket chooses Entry/SL/TP, side, risk/size and appropriate Market/Limit/Stop type where supported; freely adjustable RR within execution constraints → review and confirm → pending/fill/SL/TP/exit driven by authoritative tick stream. Chart drawing is not execution; it must produce a properly validated canonical Order Request.

**Protocol:**
- Create named, immutable evidence-bearing method with **locked risk per trade, locked RR and ≥1 user-defined checklist condition**. Checklist enforcement ON requires **all** recorded conditions PASS; OFF records truthful state and still preserves checklist definition/evidence rather than inventing PASS.
- Workspace must **show the actual Planned Trade / Long-Short position planner** in Protocol Mode. Do **not** hide or remove the planner. Disable **Quick market Buy/Sell**, direct market entries and unsupported manual discretionary exits; only **Planned pending LIMIT/STOP** entry is eligible.
- Moving Entry or SL recomputes TP by locked RR, and permitted lot size by locked risk / contract, price precision, currency conversion and execution assumptions. Do not permit TP/risk bypass by direct API calls.
- User opens immutable order review → explicit confirm → backend revalidates method, checklist, pending price, risk and RR → immutable canonical evidence → engine fills/exits via permitted SL/TP or explicitly preplanned terminal rules. Fixed-RR Protocol does not allow arbitrary manual close after trigger.
- Material Method rule changes after evidence exist require **a new Method**, not silent historical mutation. Old results remain attached to the old immutable Method.
- Include frontend tests for presence of Protocol planner and backend tests for forged Quick entry, RR/risk violations, checklist ON/OFF, pending activation, manual-close denial and rule provenance.

### E. Chart, timeframes, OHLC, tick execution and replay

**Exactly nine V1 timeframes:** M1, M3, M5, M15, M30, H1, H2, H4, D1. Do not expose W1/MN1 or unsupported fallbacks. Consistent with the most recent 2026-11-13 owner architecture override, **every selected timeframe, including D1, has an active rolling chart-history cache ceiling of 5,000 qualified bars**. This is **not** a cap on the complete underlying archive; qualified earlier bars remain reachable via bounded backward pagination/jumps. Actual visible candles depend on chart width/zoom and actual data. A small ≤512-candle initial request is a transport optimization; pages of ~500–1,000 are examples, not fabricated historical limits. Preserve source-gaps/holiday calendars and true counts.

**Authoritative market-data architecture:** verified/immutable ordered Bid/Ask ticks and fast financial worker on VPS; precomputed/indexed source-pinned nine-timeframe OHLC sidecars in **private Cloudflare R2** according to the linked 2026-11-13 decision, served to authorized browser through bounded/paged delivery. Do not silently replace the private R2 hybrid architecture with eager all-history download or client-side financial execution. Maintain BID/MID compatibility/source disclosure as specified in that decision. Actual R2 provider credentials/object availability require separate validation, not a hardcoded successful assumption.

**Data targets (not inventory or rights proof):** intended 16 pairs AUDUSD, EURGBP, NZDUSD, USDCHF, AUDJPY, CADJPY, EURUSD, GBPUSD, NZDJPY, USDCAD, CHFJPY, EURJPY, EURNZD, GBPJPY, USDJPY, XAUUSD; 2023-01 through 2025-10 tick trading target (544 instrument-months); 2021-01 through 2022-12 qualified OHLC-only prehistory (384 instrument-months). Actual eligible periods must use qualified source/version/hash/coverage/rights. Prehistory OHLC is **analysis-only** and never financial fill authority. If data are not qualified, show accurate unavailable/partial coverage and don't label Beta commercial-ready.

**Causal display:** Historical completed bars are safe only up to the simulated cursor; current forming candle is generated/updated from **already processed ticks**. Future full H/L/C must not leak during replay even when a future-derived sidecar exists server-side. Higher-timeframe bars are generated correctly rather than retimestamping M1. Preserve drawings' time/price anchors, indicators (with separate bounded warm-up), active chart state and financial state through timeframe changes; no chart operation may mutate financial hashes. Browser does not need full multi-year tick downloads.

**Replay controls:** Play, Pause, Step, variable speed (UX targets 1x/2x/5x/10x/20x/Fast; exact scheduling can be benchmark-tuned), progress, safe cancel, and **Jump to Next Event**. Jump must stop at the *next legally eligible financial event* (e.g. pending entry trigger/SL/TP/terminal), preserve other pending orders and exact event ordering, and return a durable reviewed/committed result. Normal, fast and Jump must be financially identical on identical state/input/action sequence. No future-data exposure, no double fills, no silent drop, no uncommitted 'success'. If no next event is available, surface truthful result.

**Claude performance engine integration:** compact tick access, event-index skips, fast deterministic continuation/recovery are promising candidates, not evidence the hosted product uses them. Retain authoritative Python financial contract, exact money/profile, source manifest, order execution, receipts, Journal and Statistics. Address quoteBasis/policy/profile/source commitments in cheap recovery, fail closed on tampering, avoid loading all historical tick arrays per active trader, bound caches per worker, support real PG/durable queue and source qualifications. Report head-to-head same-workload/scenario/hardware accuracy and CPU/RSS, not scanner-only throughput; preserve cold restart, gap, crossing, chronology and unsupported FX conversions.

### F. Journal, analytics, persistence, user controls

- Persist Method, Session, position/order states, immutable receipt, financial state hashes, chart/drawing/indicator preferences, notes/tags and user-owned research history across refresh/logout/login/worker crash.
- Journal records pair, Method, Session, time, planned and actual Entry/Exit, SL/TP, size, cost/spread assumptions, risk, RR, gross/net PnL, R-multiple, fill/receipt identity and Protocol checklist/exit reason.
- Basic Statistics: trade count, closed count, win rate, average win/loss, realized balance curve, drawdown with clearly specified definition, expectancy, profit factor where defined, streaks, R distribution and breakdown by Method/Session/pair/period. Unavailable/insufficient measures must be clearly labelled; do not invent values or label realized balance as floating equity.
- Exports must contain correct provenance and be restricted to owner. Session cannot silently reset balance on month boundary or Pro renewal; archival/retention must not erase immutable evidence.
- Dashboard: Methods, Sessions, Continue, entitlement/allowance state, results summary, upgrade; Account: Google/password identities as legitimately linked, active tier/expiry, invoice/status history, logout/all-devices; support/help and honest loading/reconnect/error states.
- Mobile-width navigation must preserve essential actions, though desktop is primary high-density chart experience.

### G. V1 Acceptance / Definition of Done (all evidence-based)

**Product/identity/monetization**
1. Actual configured Google sign-in completes and returns the correct private account; first-time onboarding and subsequent login both tested; password/login compatibility retained when applicable.
2. Free registration, exactly 1 Method, 1 selected pair, 1 Session created per UTC month, max 12-month tick range and 1 non-accumulating daily historical replay-day allowance are enforced by backend + concurrent/API abuse tests.
3. Midtrans **Sandbox** end-to-end payment and verified webhook activate Pro once and exactly once; pending/invalid webhook cannot grant entitlement; real merchant launch remains separate.
4. Pro can create more than one Method/Session, choose every **qualified** catalog symbol, and continue a single pair Session across every available qualified historical month without a monthly UX wall. No invisible product quota, but legitimate resource safety remains.
5. Expiry/downgrade/upgrade preserve old Session/evidence, allow legal review/resumption and enforce current tier accurately.

**Workspace/execution/evidence**
6. All 9 timeframes correctly display causal candles; 5,000 active bars per timeframe, historical paging, precomputed sidecars, correct forming candle, drawings, indicators and source provenance are browser-verified (desktop and mobile-width).
7. Free Style Quick+Planned execute exactly per canonical Bid/Ask tick and yield deterministic immutable receipts; Protocol planner is **visible** and Protocol pending-only/locked risk/RR/checklist/manual-exit restrictions hold through the backend.
8. Play/Pause/Step/multiple speeds/Jump correctly work with pending orders, SL/TP, gaps and resume; financial parity is proven across speed modes, chunking and worker restarts.
9. Journal and Statistics reconcile to canonical receipts, with Method/Session/pair aggregation, persisted notes and proper unsupported/unavailable states.
10. Logout/login/refresh/cancel/retry/worker crash/cold recovery never lose or duplicate committed financial results.

**Security/data/operations**
11. Two or more independent accounts cannot read/change other tenants' any resource/API/job/stream/export, including direct forged IDs and storage access; tenant isolation and account revocation tests PASS.
12. Each advertised symbol/range has qualified/licensed coverage provenance. Synthetic tests are distinct from commercial data, unavailable months are honestly labelled; actual rights gate PASS before customer sales.
13. Real server integration, migrations, bounded worker resources, queue fairness, resource admission, p95/p99/API/RSS/CPU/storage measurements and 20-trader target-VPS acceptance meet the pre-existing detailed gates in this same document. Do not infer 20 simultaneous CPU-heavy jobs from 20 active users.
14. Repeatable regression CI and real-browser E2E PASS on final release candidate SHA; historical benchmark results are never substituted for current tests. Production credentials, deployment, pricing launch, paid admission, merges and protected data changes require explicit respective authorization.

**Claude execution handoff:** First audit repository implementation and report a requirement-to-code **DONE / PARTIAL / MISSING / BLOCKED** matrix, with paths and tested evidence, prioritizing Google auth, Midtrans billing, tenant isolation, Free/Pro quotas, Protocol planner, continuous Pro tick history, nine-TF chart sidecars, fast Replay/Jump, Journal/Statistics and recovery. Reuse and integrate; don't duplicate product architecture. Then implement in safe bounded slices with regression and actual E2E proof. Do not claim feature completeness from documentation, mocked services, prototype screenshots or single-run engine benchmarks. Report unchanged protected files, exact branch/commit SHA, tests and still-blocked external credentials/data. **No production deployment, live payment, changes to protected production datasets, force push, or unapproved frozen financial contract changes by this document alone.**


## 1. Exact product promise

RIKSORA Commercial V1 is a hosted, authenticated, multi-tenant tick-level *historical simulation/backtesting* product: Method → Session → chart/replay → reviewed/confirmed planned order or supported quick execution → deterministic tick execution → immutable receipt → Journal/Analytics → logout/login/resume. Simulated fills are not live/broker fills, and uncertain tick chronology, missing coverage, unsupported conversion, or source qualification must be surfaced explicitly.

Do **not** advertise real-time brokerage, live execution, automated profitability, complete market realism, or validated market accuracy from synthetic QA evidence.

### Minimum supported SKU

- One instrument per Session; preserve existing canonical financial/provenance/no-lookahead contracts and supported trading modes.
- Intended launch catalog: 16 named instruments (AUDUSD, EURGBP, NZDUSD, USDCHF, AUDJPY, CADJPY, EURUSD, GBPUSD, NZDJPY, USDCAD, CHFJPY, EURJPY, EURNZD, GBPJPY, USDJPY, XAUUSD), with planned Jan 2023–Oct 2025 historical coverage (34 months × 16 = 544 instrument-months). Every advertised instrument-month requires verified qualified source, immutable manifest/hash, actual usable coverage, correct instrument precision and **documented commercial use/display/retention rights**; missing months must be disclosed or excluded. The historical catalog is a *target*, not a current inventory or rights assertion.
- If all 544 instrument-months cannot be qualified, the owner must explicitly approve a narrower and accurately described paid-Beta SKU **before** sales; no silent substitution with synthetic data.

### Historical OHLC coverage matrix — owner V1 target 2026-11-13

**Explicit launch dataset target, in addition to the 34-month tick catalog:**

| Historical period (UTC/calendar) | Data class | Scope for 16 target instruments | Permitted role |
| --- | --- | --- | --- |
| **2021-01 through 2022-12** (24 months) | Qualified historical **M1 OHLC**, or a source with equivalent verified M1 resolution/aggregation; no extra pre-2023 tick storage required | **384 OHLC instrument-months** (16 × 24) | Read-only chart context, drawings, technical indicators and causal warm-up, **never** execution settlement |
| **2023-01 through 2025-10** (34 months) | Qualified ordered Bid/Ask tick market data, with versioned derived OHLC sidecars for chart | **544 tick instrument-months** (16 × 34), with derived candle availability | Tick alone governs historical simulation/execution; OHLC serves chart/indicators |

The intended combined temporal coverage runs from **January 2021 through October 2025** for each advertised instrument, while the **trading-eligible tick range remains January 2023 through October 2025**. The 384 OHLC-months are **additional historical coverage**, not 384 additional tick-months; derived chart candles in the tick period should reuse qualified source data rather than requiring duplicate raw tick copies. These counts describe the proposed *full* 16-instrument SKU, **not** inventory already acquired or licensed.

**Why prehistory is necessary:** For a Session starting at the first available tick date in January 2023, read-only analysis must be able to reach at least January 2021. For a Session starting later in 2023–2025, the preceding two calendar years can span both the older OHLC-only region and the qualified OHLC derived from the tick catalog. Before 2023, OHLC **must not** trigger entries, SL, TP, exits or any simulated financial settlement.

**Storage/compute policy:** Prepare monthly partitioned, immutable, indexed, bounded-access historical OHLC (M1 as the prehistory base for the supported M1/M3/M5/M15/M30/H1/H2/H4/D timeframes); use deterministic aggregation with documented timestamps, price side/basis, timezone/session calendar, missing periods, and versioned source manifest/checksums. A provider's OHLC is not silently rebranded as tick-derived data; if chart and tick feeds differ, disclose that distinction and preserve provenance. Cache verified derived higher-timeframe bars/indicator inputs where justified; avoid full raw tick scans merely to display earlier chart context. No client should download all historical candles at Session open.

**Rights/quality:** Historical OHLC must have independently verified accuracy/coverage and commercial processing/display/retention rights. Explicitly mark weekends, holidays, source gaps and genuine missing bars; do not fabricate uninterrupted candles or claim 24 months means every minute traded. Synthetic fixtures can validate the pipeline but **cannot** satisfy a real-historical-data commercial source-rights gate.

**Mandatory V1 acceptance:**
1. Maintain a per-instrument and per-calendar-month coverage matrix for all 16 target symbols and both data classes: source/provider, license evidence, data version, hash/manifest, actual time bounds, completeness/gaps, timezone, price basis, and qualification result. Record separate totals: **384/384 prehistory OHLC months** and **544/544 trading tick months** as full-SKU acceptance targets; report partial counts honestly.
2. On the earliest possible tick Session start (January 2023), a Free user and a Pro user can access at least **two prior calendar years of qualified read-only OHLC** through bounded backward pagination; on later starts (e.g., January 2025), the same two-year span correctly crosses the OHLC-only/derived-candle boundary. No order can execute on OHLC-only prehistory.
3. M1 OHLC aggregates deterministically and correctly into supported M3/M5/M15/M30/H1/H2/H4/D bars with stable draw anchors and no future high/low/close leakage. **Adopt MT5-style separation of full time-frame-specific history vs bounded on-device chart cache:** initial no-local-history request may seed **up to 512 recently closed bars per selected timeframe**, with subsequent bounded backward pages (e.g. 500–1,000), while the count for a selected date range reflects **all qualified observed bars of that timeframe**, never the seed/page limit. Initial indicator warm-up budget remains up to **1,000 bars of the indicator's input timeframe** (with readiness-aware extensions), per section 3A.
4. Timeframe switches and scroll across the **2022-12 / 2023-01** boundary preserve chronology, source/version/price-side provenance, causal clipping, drawing anchors, and all committed trading financial hashes. Distinguish cross-provider visual discontinuities rather than silently altering historical prices.
5. Benchmark on intended VPS with concurrent trader viewport loads, timeframes, warm-up and pagination; measure request latency, CPU, RSS, storage bytes and object-read costs against the Commercial V1 SLOs.
6. Until **both** full-SKU matrices are actually qualified and lawful, mark **DATA COVERAGE: NOT VERIFIED / BLOCKED**. A smaller launch catalog or historical date range needs explicit owner-approved SKU change and accurate customer disclosure before limited sales. No automated purchasing, downloading or publishing third-party market data is authorized by this specification.

## 2. Capacity target: one VPS, clear meaning of 'trader'

Deployment profile under test: 6 vCPU / 16 GiB RAM single VPS, with API, PostgreSQL and workers co-resident as proposed (verify actual topology). Codex/development processes may share the host; never assume six exclusive worker CPUs. `BTL_RESEARCH_WORKERS` now configures the bounded queue/native pool from 1 through 4, with default 2. The four-slot setting is configurable but remains a **target configuration**, not capacity acceptance evidence.

**V1 GO capacity target: 20 simultaneously active, independently authenticated traders, with a planned ratio of five active traders per each of four workers.**

Definitions (do not conflate):
- An **active trader** has a live authenticated product Session and performs UI/API work, potentially with a backtest submitted or queued. A trader is not a CPU core, and a 'five traders/worker' ratio does **not** mean five heavy backtests concurrently inside one worker.
- A **worker** executes no more than one admitted CPU-heavy native job at a time unless a separate correct and benchmarked design proves otherwise.
- **Heavy concurrent jobs** under the four-worker profile: up to four running at once, with bounded queued jobs. Admission, per-user limits, fairness, TTL, job deadline and lease recovery must be compatible with measured full-job/chunk duration and must never silently drop financial work.
- Capacity must be measured on the actual target VPS, not inferred from a local KVM, a single synthetic throughput number, or a sequential browser test.

**Normal-load acceptance workload:**
- 20 independent identities and Sessions, 60-minute coordinated real-browser/API test, external/separate load generator if feasible.
- Across the hour, each of 20 traders submits **one 262,144-tick financial-active backtest** (20 complete histories/hour in aggregate), staggered with a documented seeded arrival schedule. Each includes at least one true entry and exit via the canonical engine, committed receipt, Journal and Analytics, not a scanner-only job. No more than four heavy jobs should execute concurrently.
- During those jobs, all 20 keep using a representative mix of chart navigation, Method/Session, review/confirm, Journal/Analytics, polling, and save/resume; record operation mix and request rate.
- Repeat the full normal-load profile twice in independently reset runs with identical seed/configuration. A separate burst test submits eight financial-active jobs close together; queued jobs must remain visible, eventually finish or explicitly fail/reconcile, never disappear.
- Add a lower-cost 2,048-tick functional 20-browser journey to isolate UI/identity defects from heavy-engine throughput; this *alone* cannot pass the commercial-capacity gate.
- Test 1, 2, 3, and 4-worker profiles with a worker ceiling of one effective vCPU each. Choose the final worker count based on throughput, latency, database pressure and spare system resources. Four workers is the target, not a mandate to overcommit.

### Performance acceptance SLOs (candidate engineering contract, must be measured)

At the **20-trader normal workload**, in **both** independent runs:
- Interactive authenticated API endpoints (non-heavy requests) p95 <= 2.0 s and p99 <= 5.0 s.
- Async submit/status endpoints p95 <= 0.5 s and p99 <= 1.5 s; the response may be 'queued' with a durable ID.
- Each 262,144-tick *full financial-active history* job reaches durable terminal completion with p95 end-to-end <= 15 minutes, and normal-load queue wait p95 <= 5 minutes. Measure from submission, and report p50/p95/p99 of queue, execution, and full journey separately. If the current chunk/deadline model makes this impossible, record FAIL/BLOCKED; do not redefine 'full job' as a 30-second chunk.
- Burst-of-eight jobs: all receive durable accepted/explicitly refused outcomes, no hidden timeouts; any accepted jobs reach terminal state and are recoverable. Report waiting time rather than masking queue pressure.
- No unexplained 5xx, silent dropped jobs, duplicate financial results, or missing terminal status. Intentional bounded 429/SERVICE_BUSY is acceptable only if correctly surfaced and retry/recovery tested, with counts disclosed.
- No service OOM, swap-driven degradation, unsafe disk decline or safety-gate override; capture CPU, cgroup memory, per-worker RSS, PostgreSQL pressure, storage delta, queue depth, CPU throttling and **effective** affinity/quota/exclusivity. Retain the stricter applicable existing host runbook gates.

A launch capacity statement is allowed only as: "Passed 20 simultaneous active traders under the documented workload on the specified VPS", never "20 simultaneous full-history CPU jobs", "20 users forever", or "20 users for any dataset".

## 3. Correctness and reliability gates — zero-tolerance

**PASS only if all relevant evidence is reproducible:**
- Frozen canonical tick order/bid/ask, exact arithmetic, spread/cost/PnL, entry/SL/TP, partial close, no-lookahead, identical-time ambiguity, chronology/gap and uncertainty handling remain correct. SHA-256/canonical bytes, event head, state, immutable receipt, Journal and Analytics parity match current golden fixtures.
- Include at least one pending-order entry and SL/TP terminal fill in representative long workload; add separate mixed-order/stress fixtures so a single completed trade is not misrepresented as realistic activity.
- Two independent test cohorts complete 20/20 required product journeys (login, create/open Session, replay, entry/exit, receipt, Journal, Analytics, logout/login/resume), with tenant isolation.
- Cancellation, stale revision, idempotent retries, worker death before/after commit, lease recovery, queue FIFO/fairness, restart and cold resume all pass with **zero** duplicate committed financial receipts, lost committed results, cross-tenant access or unreconciled job.
- Regression/CI on the *final remote release-candidate SHA* succeeds: backend directed and broad relevant suites, actual browser E2E, Parquet/source/serializer, PostgreSQL migrations, finance golden, lint/build, and resource tests. A PASS on a parent SHA is insufficient.

## 3A. Timeframe-aware chart prehistory, indicator warm-up and causal paging (Commercial V1)

**This refines, and does NOT replace**, the prior owner-approved [Market Data Standard — Human-selected Beta chart prehistory (2026-10-19)](../MARKET_DATA_STANDARD.md#human-selected-beta-chart-prehistory--2026-10-19): **at least two calendar years of qualified, read-only OHLC prehistory before the Session trading start must be accessible to both Free and Pro** for each advertised eligible instrument, subject to actual verified coverage and honest gaps. A fixed initial display count is not a substitute for two calendar years of eligible historical availability. Tick execution authority remains independent from chart OHLC.

### User-visible behavior and defaults — MT5-inspired data with TradingView Basic-style chart limit (Owner decision 2026-11-13)

**Latest owner decision overrides the earlier MT5 chart-cache recommendation:** follow a **TradingView Basic-style normal chart policy**: **M1/M3/M5/M15/M30/H1/H2/H4 → maximum 5,000 historical candles loaded/retained per selected chart timeframe at a time; D1 → entire qualified available historical date range remains accessible with no 5,000-candle history cap.** Maximum chart timeframe remains **D1** (no W1/MN1). This applies to the **regular analysis chart** as well as its historical context; it does not truncate canonical tick data, permanently erase dataset history, or determine trading outcomes. Earlier references to MT5-specific minimum configurable 5,000 and unlimited intraday chart cache are superseded. The initial ≤512-bar request remains a transport optimization, not a hard limit, and the chart actually *visible on screen* still depends on width/zoom. D1 may use bounded paging and memory eviction without restricting the underlying full qualified daily history; don't render all daily candles at once. For intraday, the rolling 5,000-bar client window may move when scrolling/jumping across qualified history, but **never exceed 5,000 concurrently loaded historical chart candles for the active timeframe**. Keep historical catalog counts separate from current chart window counts. No future bars or unclosed-candle final OHLC may leak into replay. Do not misrepresent this as a commitment to every TradingView plan feature or license.

**Retained technical reference: MetaTrader 5 historical chart construction.** Official docs: [Chart construction/history loading](https://www.metatrader5.com/en/terminal/help/charts_analysis/charts), [Max. bars in chart settings](https://www.metatrader5.com/en/terminal/help/startworking/settings), [M1-based timeframes](https://www.metatrader5.com/en/terminal/help/trading_advanced/price_data). This is a product **behavioral target**, not a claim of byte-for-byte MT5 compatibility, a promise of all MT5 21 timeframes in V1, or authorization to copy MT5 proprietary code.

1. **Separate three quantities:** (a) total *qualified historical candle count* in the date window and selected timeframe, (b) **client chart cache cap** (`Max bars in chart`), and (c) currently **visible screen bars**, which vary by zoom/viewport. None may be substituted for another. An initial HTTP page of 512 rows does not mean the dataset has 512 candles. The total is computed from real available aggregates, retaining gaps and trading-calendar/session rules, not from a fixed row cap or simplistic calendar arithmetic.
2. **Canonical data model:** retain immutable validated ordered Bid/Ask **tick** as execution authority; derive persistent, indexed, version-pinned **M1 OHLC** sidecars once per permitted dataset, with explicit price side/source, tick-to-M1 aggregation calendar and gaps. Generate/cache higher-timeframe bars deterministically from qualified M1, as in MT5 chart semantics. This does **not** mean the chart OHLC can execute trades; a future sourced from tick remains the sole financial input. If 2021–2022 has qualified OHLC-only prehistory, preserve its distinct feed/version and chart-only classification.
3. **Initial chart history:** where no locally cached chart data exists, request **up to the most recent 512 causally completed bars of the selected timeframe** preceding the selected backtest cursor, analogous to MT5's latest-512 bootstrap behavior. This is only an **initial transport seed**, not a fixed chart viewport, total historical count, or cap. Render the appropriate number of bars for actual screen width and zoom. If less history is eligible, report truthful insufficiency.
4. **Chart-history window:** cap the active **intraday** (M1/M3/M5/M15/M30/H1/H2/H4) chart-history cache at **5,000 eligible candles of the selected timeframe**; do not present a user setting to raise this cap in Commercial V1. For **D1**, qualified daily history is accessible without this 5,000-candle historical cap, using bounded paging and memory-aware client caching. A user moving to older intraday history may receive a new rolling window while older bars are evicted; it must not imply the underlying source dataset has only 5,000 bars. Indicator history and warm-up can use a separately bounded, provenance-pinned calculation cache, not falsely inflate chart-history counts. Do not promise full years of D1 bars all rendered simultaneously.
5. **Backward navigation:** when the trader scrolls left, automatically fetch earlier eligible bars in bounded, independently validated pages (implementation example: **500–1,000 bars/request**), preserving source calendar, no duplicates, source gaps, version and price side. Continue as long as qualified data and permission allow; respect a memory budget by evicting offscreen chart cache, not by making older history inaccessible. Support explicit historical time jumps without preloading the entire time span.
6. **Timeframe changes:** for the **same fixed historical cursor/date range**, compute the correct number and exact OHLC of **that timeframe**, not 500 or 512 for every timeframe and not a retimestamped fixed M1 sample. Fetch enough underlying qualified M1 context for aggregation. On M5 → H1 → D → M5, preserve replay cursor, drawings' time/price anchors, user-selected date range, orders, journal and financial hashes. Version and calendar remain pinned.
7. **Indicator warm-up:** independent of visible screen bars, initial budget up to **1,000 verified bars of each indicator's input timeframe**, expandable when needed and permitted. No silent fake history, no incorrect claim of convergence; show `INSUFFICIENT_HISTORY` or warming-up when relevant. The chosen `Max bars in chart` and bounded cache need explicit indicator read-access semantics.
8. **No-lookahead under local-first Option A:** chart and indicators reveal only completed historical bars up to the simulated replay cursor, plus an optional current forming bar constructed from *already replayed* tick prefix; never publish the future H/L/C of an unfinished candle in normal UI. Download prefetch on the trader's device is allowed for personal research, but strict technical prevention of local future-data inspection is **not** promised. Past OHLC context can inform research but never settle historical trades.
9. **Supported V1 timeframe gate — OWNER DECISION (2026-11-13): maximum selectable chart timeframe is D1 (Daily), inclusive.** Target V1 choices are exactly `M1/M3/M5/M15/M30/H1/H2/H4/D1` (verify final implementation/feature flags). **Do not expose W1 (Weekly), MN1 (Monthly), or higher timeframes in the Commercial V1 chart/replay UI/API**, even if lower-level helpers or legacy chart code can aggregate them. Reject unsupported higher timeframes clearly; never silently coerce them to D1. All permitted timeframes use actual source-observed candle counts for the selected historical window, independent of the 512-bar initial download and client chart cache limit. The user's 'maximum bar D1' decision concerns the **largest timeframe**, not the maximum historical candle count. MT5 itself has more timeframes; copying all 21 is NOT the V1 target. Adding W1/MN1 requires a later explicit owner decision and validation.

### Architecture proposal — OHLC Parquet sidecars and browser delivery (2026-11-13, NOT IMPLEMENTED)

**Problem:** the existing `backend/market_data/monthly_parquet.py` is an immutable, source-pinned **tick** Parquet implementation; `frontend/src/market/candles.js` can aggregate candles and `backend/market_data/context_archive.py` can read qualified reference OHLC, but these do **not** together establish a production-grade, source-pinned **Tick → OHLC M1 → timeframe sidecar → browser chart transport** pipeline. Do not claim this integration already exists or that all 16×58 months are licensed/available.

**Proposed low-cost reuse-first architecture (subject to tests, legal rights and final source coverage):**

1. **Keep existing validated Monthly Parquet tick canonical unchanged**: UTC timestamp with source ordering, exact Bid/Ask, instrument, source/manifest version, quality flags. Tick remains execution authority. Reuse ingestion and immutable monthly manifest as upstream input; do not invent a second parallel canonical tick format.
2. **Build versioned OHLC M1 derivative *once*, offline/incrementally, per instrument and month** by streaming ordered validated tick groups (memory bounded). Pin price basis (e.g. Bid), market-session calendar/timezone, bucketing rules, aggregation code version, source dataset version/hash, input range, first/last observed timestamp, gaps, row count, and output SHA-256. Preserve exact price scale (integer or decimal; do not silently use binary float for auditable reference prices); do not invent volume from missing quote volume or invent bars during market closure. When source changes, invalidate only affected derived partitions and indexes. For 2021–2022 OHLC-only prehistory, use separately qualified OHLC source with explicit source identity, **not** a false 'tick-derived' label.
3. **Store M1 OHLC in compact, immutable indexed monthly Parquet partitions** on VPS/object storage. Higher permitted timeframes (`M3/M5/M15/M30/H1/H2/H4/D1`) are deterministic derived bars from qualified M1, with **optional pre-materialized, separately version-pinned indexed Parquet sidecars** for high-demand or high-latency frames. Consider at least a D1 materialized/indexed layer for long-horizon navigation; choose which other frames to materialize only after latency/storage benchmarks. Derived candle files are **cache/rebuildable materialized views**, not a second price truth. Timeframe changes must not scan every historical raw tick on demand.
4. **Do not require browsers to read entire raw monthly Parquet objects** just to show 512 or 5,000 candles. Provide a bounded time-range/timeframe chart endpoint or immutable compact HTTP-delivery chunks with indexes, integrity checks, compression/ETags and cache-control, generated from indexed Parquet sidecars. JSON with exact wire price tokens is a reasonable V1 transport baseline; Arrow IPC/binary packed arrays may be benchmarked later, never assumed required. Build authorization and revocation checks before issuing protected data chunks; user-facing browser delivery of provider-derived history requires explicit commercial display/**client-delivery** permissions. Requesting S3 data does not itself establish such permission.
5. **Browser policy (latest owner choice):** seed up to 512 eligible closed bars on initial cold chart load; intraday `M1…H4` chart history holds **at most 5,000 selected-timeframe bars** at a time in a rolling window; `D1` can navigate all qualified available daily history through bounded pages, without a 5,000-history ceiling. Total catalog bar count over a requested period remains separate from cache/visible bar count. This chart cache does **not** bound the immutable tick dataset or replay engine's active tick stream.
6. **No-lookahead:** at replay cursor T, present closed candle aggregates only when the full candle completes by T; current forming candle, if shown, must be computed from the revealed tick prefix. Timeframe charts, indicator inputs and prehistory must not reveal future OHLC values. Browser local-first prefetch is not a promise of tamper-proof hidden future data. Tick fill decisions use only the tick reducer.
7. **Required acceptance:** (i) canonical tick → M1 and M1 → every supported TF exact OHLC/time-bucket parity against reference fixtures; (ii) single tick partition reprocessing is idempotent with identical hashes; (iii) gaps, session closings, source changes, price side and month/year boundaries; (iv) November 2024 count-per-timeframe, correct 512 seed, ≤5,000 intraday rolling cache, D1 pagination; (v) Android low-memory chart and server bandwidth tests; (vi) all 16 instruments' coverage/rights inventory and correct `NOT VERIFIED` on incomplete months; (vii) controlled chart source never becoming trade execution evidence.
8. **Cost/complexity guardrail:** start with canonical tick Parquet + M1 OHLC Parquet and an indexed D1 view; benchmark caching additional timeframes before generating 9 permanently materialized sidecar copies per month. No re-download of tick history just to recompute a chart timeframe; no cold full-history scan for a 512-candle chart request. Avoid storing multiple unversioned conflicting OHLC truths.

**Status:** PROPOSED ARCHITECTURE ONLY. Needs code implementation, fixture/real-data acceptance, browser profiling and source-rights clearance before Commercial V1 GO. This subsection must not be mistaken for evidence of an already-functioning production transport.

### Owner concrete scenario — November 2024, true timeframe-dependent candle counts (corrected 2026-11-13)

**Mandatory example:** a trader selects **XAUUSD** and a period such as **2024-11-01 00:00 UTC through 2024-12-01 00:00 UTC**, or starts replay at an instant inside November 2024. RIKSORA must enumerate valid observed M1 history and aggregate into the selected timeframe over the authorized **actual time range**. The **total count differs per timeframe**. It is *not* 500/512 bars for all timeframes.

For orientation only, the following are **mathematical maxima assuming a complete, gapless 24-hours-a-day, 7-days-a-week feed during the whole 30-day November 2024**; they are **NOT expected actual forex/gold bar counts**:

| Timeframe | Hypothetical full 30-day count | Actual RIKSORA count |
| --- | ---: | --- |
| M1 | 43,200 | Count qualified observed M1 minutes in the selected interval |
| M5 | 8,640 | Count eligible M5 buckets with real observed constituent data |
| M15 | 2,880 | Count eligible M15 buckets |
| H1 | 720 | Count eligible H1 buckets |
| H4 | 180 | Count eligible H4 buckets |
| D1 | 30 | Count eligible daily session bars |

Forex/gold trade on instrument- and source-specific schedules, **not 24/7**. Weekends, holidays, market-session start/end, genuine missing observations, data quality and candle construction policy change counts. Explicitly distinguish incomplete coverage from intentional trading closures. Do not invent a candle for a period with no eligible observations, and do not merge separate sources to force round-number counts.

**Acceptance tests required (synthetic fixtures for code correctness; separately rights-qualified real feed for commercial GO):**

1. Count M1/M5/M15/H1/H4/D1 eligible bars over **exactly November 2024**, using a deterministic source-calendar-aware independent reference enumerator; assert **actual counts and timestamp-bucket OHLC** by timeframe rather than assuming all timeframes return an equal fixed page size. Also test M3/M30/H2 where supported. Compare 24/7 fixture theoretical maxima separately from FX weekday/weekend fixtures with market close, session holidays and deliberate missing ticks.
2. At a replay cursor (e.g. 2024-11-15 13:07 UTC), assert that **only preceding fully completed bars** and optionally the valid partial 13:07 bar appear; no higher-timeframe final H/L/C from any future suffix. When a whole date range is requested for **catalog/history inspection**, allow full qualified counts only within its permitted scope; when in replay, reveal/chart clip by cursor. These are distinct APIs/views.
3. Empty local history fetches an **initial ≤512-bar seed** for the selected timeframe when available; scrolling backwards beyond that seed loads more verified bars as a rolling cache window. For intraday M1–H4, enforce **≤5,000 simultaneously retained historical chart candles per active timeframe**, evicting older offscreen candles as new ones are loaded; D1 exposes **all qualified daily history through bounded pagination** without a 5,000-bar history truncation. Distinguish catalog total, active chart-window length, and screen-visible bars. Test correct cap, date-window counts, D1 beyond 5,000 when dataset supports it, eviction, backward paging and old-cursor revisit without losing financial state.
4. Switching M1 → M5 → H1 → D1 → M1 preserves replay cursor, chart time-price drawing anchors, Session and finance state; first/last bar and actual total-available counts are correct for the identical selected date window. Validate indicator warm-up independently and report **insufficient qualified history**, not made-up bars.
5. Ensure the pre-2023 OHLC-only history and 2023–2025 tick-derived OHLC are source-version pinned, never silently mixed across feeds, and tick-only trade execution remains intact. For any actual dataset not fully qualified/rights-cleared, report **NOT VERIFIED / BLOCKED** rather than a fabricated successful acceptance.
6. Measure on low-RAM browser/Android devices: initial ≤512-bar bootstrap speed, bounded 500–1,000-bar pages, **intraday active chart history capped at 5,000 bars**, D1 long-history pagination with bounded client memory, indicator memory, and long-history scroll without VPS full-history scans. Preserve 5,000 intraday cap unless owner explicitly changes SKU policy.

**Implementation status:** OWNER TARGET UPDATED TO TRADINGVIEW BASIC-STYLE INTRADAY CHART CAP + UNRESTRICTED QUALIFIED D1 HISTORY, RETAINING MT5-INSPIRED DATA AGGREGATION; **NOT YET IMPLEMENTED / ACCEPTED**. This supersedes the earlier mistaken interpretation that *500 bars are the whole historical candle count*; previous '500 latest visible bars' wording is replaced by **optional 512-bar initial transfer seed**, chart-cache cap, and separate total eligible timeframe history. No third-party market-data download, licensing change, deployment, production dataset modification, or live cutover is authorized by recording this requirement.

### Specific acceptance tests — all mandatory for chart-history GO

- Empty-cache bootstrap retrieves at most **512 latest eligible closed bars** of the active timeframe (or fewer if actual coverage is shorter), and **does not define the total**. Independently assert **total eligible candle counts per timeframe over a pinned date range** and exact first/last bar, bucket chronology, source-side OHLC and missing periods. Test the honest <512 insufficient-history case.
- Deterministic fixtures for **M1, M5, H1 and D**, plus compatibility of all supported timeframe choices. For **identical November 2024 date bounds**, actual timeframe-dependent catalog counts and bar content must differ appropriately; no fixed 500/512 count. Test session/day boundaries, weekends, market gaps, year boundary and DST/timezone policies where relevant.
- Indicator warm-up requests up to 1,000 verified bars in indicator input timeframe independently of 500 displayed; test EMA200-style longer convergence, insufficient data/partially formed bars, optional additional history, and multi-timeframe indicators if supported. Indicator availability must never silently turn into an execution signal before its causal readiness.
- Paginate left 500–1,000 bars per bounded request after an optional ≤512-bar initial fetch; no duplicates/missing IDs across adjacent pages, stable ordering/cursors, no cross-dataset cache contamination, and reproducible candle aggregation. `Max bars in chart` is fixed at **5,000 for intraday chart cache** in V1, while D1 historical access has no 5,000-bar truncation; neither caps the canonical data catalog.
- Switch M5 → H1 → M5 and verify correct candle count, indicator values, drawing anchors, Session time/revision, no-lookahead and immutable financial state/receipts.
- Simulate a replay cursor in the middle of an H1 candle: neither a cached closed H1 candle's future high/low/close nor any provider/index future-suffix capability may leak into chart/indicator/analysis.
- **Two-year qualified OHLC accessibility** is a separate gating test per advertised supported instrument, for Free and Pro, not satisfied solely by a successful 500-candle first page. Explicit PARTIAL/BLOCKED if qualified prehistory or commercial display rights are unavailable.
- During the capacity test (server-led baseline or Option A local-first pilot as separately approved), measure concurrent initial ≤512-bar seed, 1,000-bar indicator warm-up, ≤5,000 intraday chart cache, D1 paged history, page-back and timeframe switching on API p95/p99, client/server RAM, object-store egress and CPU; do not count a trivial blank or cached fixture as full production acceptance.

**Implementation state (2026-11-13): TARGET RECORDED; NOT TESTED as Commercial V1 acceptance.** No code or protected dataset is changed by this specification.

## 4. Data, security, operations and paid-product gates

**Market data:** Each live advertised dataset has legally verified commercial processing/display and retention rights, immutable hashes, bounded loading, authentic coverage/quality and provenance; any missing/incomplete/ambiguous data is not silently treated as verified. Synthetic data remains visibly TEST ONLY and cannot substantiate commercial historical accuracy.

**Security:** HTTPS, authenticated user/workspace ownership and tenant isolation, rate limits, secret handling, safe Session boundaries, no raw card storage, audit logs, relevant abuse tests and sensitive-data protections. Independently test a user cannot access another user's Session, trades, dataset entitlements or receipts.

**Persistence/operations:** Restartable workers and correct long-job lease/deadline behavior, monitored queue depth/CPU/RAM/disk/latency, alerting on failed/stuck jobs and storage pressure, restore test from fresh backup, evidence of recovery objective (initial target RPO <=24h and RTO <=4h; revise only through explicit owner decision and disclosure). No production cutover without reviewed rollback steps.

**Billing:** Real entitlement enforcement by server, quota/reset consistency, provider-signed webhook verification, replay/idempotency, failure/cancellation/refund policy, and end-to-end sandbox checkout tests. A permitted low-value live charge/refund test on approved merchant configuration is required before collecting live customer payments. Price, currency, provider fees, tax/compliance, terms and privacy copy require owner approval. Never test real charges without explicit authorization.

**Product UX:** Desktop plus a defined mobile viewport complete critical flow; recoverable status for queued/rejected/failed jobs, truthful progress, explicit data limitations, no unexplained browser dead end.

**Economics:** Capture measured cost drivers (CPU-seconds per full job, memory, DB growth per Session/trade/job, object-storage/egress, payment fees, VPS charges); produce reproducible margin and break-even sensitivity scenarios for active users. Target initial commercially viable gross margin >=60% under the chosen paid tier and measured usage profile, subject to owner approval of pricing and real tariffs. If costs are unknown, this gate remains NOT VERIFIED; do not invent a per-customer cost. Existing approximately Rp300k/month VPS *planning budget* is not an independently verified total infrastructure price.

## 5. Final release decision

All gates must have explicit PASS / FAIL / BLOCKED / NOT TESTED with immutable evidence URL/path, exact commit SHA, host specs, source/dataset hashes, configuration, date, measured percentiles, sample counts and named owner approval.

**GO for limited paid Beta** requires:
1. Correctness/recovery/tenant security: PASS.
2. Data rights and specifically advertised catalog: PASS (or owner-approved explicitly narrower SKU).
3. 20-trader two-run capacity and SLOs on the real target VPS: PASS.
4. Backup/restore, monitoring and operational rollback: PASS.
5. Billing/entitlement and approved customer/legal terms: PASS.
6. Real economics and acceptable margin: PASS.
7. Final remote-SHA CI/E2E, owner review and explicit production/deployment/payment authorization: PASS.

Any missing critical item is **HOLD**, not a fractional 'percent complete' or permission to sell. Failed tests cannot be bypassed by lowering security, financial or resource gates. A narrower launch SKU or capacity claim requires explicit owner scope amendment; it must not inherit the full V1 claim.

## 6. Acceptance sequencing

A. Baseline and one-worker financial-active CPU/RAM/DB/queue measurements on representative prepared Monthly Parquet; isolate benchmark generator/storage-conversion time.

B. Harden configurable two-to-four worker pool without changing financial semantics; profile one-worker cohorts and control queue/lease/job deadline behavior, preserving existing limits until reviewed.

C. Controlled 5 → 10 → 15 → 20 real-browser trader cohorts; stop and report on safety, integrity or SLO failures. Test four-worker 20-user full profile twice plus burst. Do not extrapolate five active traders/worker as an observed fact before step C.

D. Finish data licensing/coverage, billing, security, backup, mobile/desktop acceptance and pricing validation; publish evidence in existing integration register/current phase, not a competing tracker.

E. Freeze release candidate, verify all final-SHA CI and gates, and obtain separate owner GO before any external launch.

### Current baseline, not acceptance

- Repository worker pool accepts `BTL_RESEARCH_WORKERS=1..4` (default 2); configuration wiring has unit coverage. Actual multi-worker capacity and four-slot resource safety remain unproven.
- Local synthetic real-browser ten-trader cohort has passed functional journeys, but older interactive p95/p99 exceeded candidate targets. A local 20-user cohort was blocked by host resource gate.
- 524,288-tick synthetic financial-active engine replay passed in local KVM with one closed trade, not an end-to-end long durable worker on target VPS.
- No 20-user / four-worker real-VPS capacity PASS, complete rights-qualified launch catalog, live billing evidence or verified Commercial V1 unit economics exists in this checkpoint.

### Local worker-capacity checkpoint (2026-11-12, continued)

This checkpoint is local Linux KVM synthetic software evidence only. It does not satisfy product browser, VPS, historical-data, or Commercial V1 capacity acceptance.

- Worker pool wiring: `BTL_RESEARCH_WORKERS=1..4`, default `2`; bounded queue worker count, native child slots, and exchange executor use the same parsed count. Invalid values fail closed. Configuration tests: 4/4 PASS. Real 2–4 worker load and resource safety: NOT TESTED.
- Authenticated API → PostgreSQL 16.15 durable queue/native child → canonical Monthly Parquet → financial reducer → durable receipt → CLOSED Journal → Analytics: PASS for 2,048 synthetic ticks. One identity/session, 34 queue jobs (create, quote setup, 32 bounded advances), one trade, ENTRY_FILL + EXIT_FILL, balance `10000.7`. Repeat confirm returned the same result. The harness invokes `queue.work_one` serially; the configured pool default was 2, and concurrent service-worker lifecycle/one-worker pool throughput was not tested.
- Fixture: `riksora-synthetic-financial-monthly-v1`, seed `20261112`, label `SYNTHETIC / TEST ONLY`; dataset version `d12c77000573eb1acce8e56b0297b6f3909cce2d066f44e246c450a61ca57d86`; source-member SHA-256 `1c8bb56a4a211129ce59ddffb5fb1e94bcf4b343f9cf276c6d9d3ad5ba8cf37f`; Parquet manifest SHA-256 `3629f511796ed1a7cb22c094afd053d984237063c45f8a269f449c2fa5ed57f`.
- Three initial 2,048-tick repeats plus a post-merge-commit verification now exist; they are not an optimization before/after. Runs 1–3 are detailed in the integration register. The fourth unbound run measured journey 11.958 s, worker CPU/wall 3.207/3.959 s, queue wait p50/p95/p99 11.103/15.504/15.570 ms over 34 jobs, child peak RSS 184,410,112 B, DB growth 876,544 B. All four used the same synthetic identity/hash and produced one CLOSED trade with identical retry-confirm behavior. One affinity-limited run pinned the API/test process and native child, not PostgreSQL; CPU 5 was not exclusive. These tiny-fixture repetitions do not establish heavy-job throughput or optimization ROI. `/proc` reported zero process `read_bytes`; physical disk I/O is not established. Endpoint-latency decomposition and browser-visible time: NOT TESTED.
- A serial durable-queue attempt at 65,536 ticks failed after 167.659 s with `REFUSED_RECOVERY_LIMIT` (`fixtureSteps`); a 16,320-tick probe also failed with that code after 109.060 s. The legacy fixture controller contract is `MAX_STEPS=256`, and `TickTimeline` stores each accepted advance target in its checkpoint. Splitting API work into durable queue jobs does not reset this same Session checkpoint. No limit was changed. Durable full-history completion at 65,536/131,072/262,144 ticks: BLOCKED by the frozen Session checkpoint budget; the 65,536 and 16,320 outcomes are FAIL for those attempted test runs, not data corruption or a successful full replay.
- Test harness now snapshots queue/worker metrics as each job completes because operational `research_jobs` retention is capped at 32. The retention policy was not changed. Focused regression: worker-pool config, queue contract, worker deadline, and synthetic financial fixture **37/37 PASS**. Real 2,048-tick journey **1/1 PASS**. The two larger attempts above **FAIL** at the step guard.
- Browser/UI journey, chart page/timeframe/warm-up, mixed multi-order workload, multi-trader 1/2/3/5 cohorts, actual 1–4 worker scaling, 262,144 full durable history, and actual target VPS: NOT TESTED or BLOCKED as stated. Qualified two-year chart prehistory remains BLOCKED on qualified source rights/coverage.

### Performance ROI decisions — local engine evidence only

These are engineering disposition decisions, **not durable-worker capacity claims**. Existing before/after figures are single measurements from earlier synthetic engine-only runs; the requested three-run same-workload confirmation is still required before attributing Commercial V1 capacity gains.

| Candidate | Decision | Measured CPU saved per synthetic 65,536-tick engine pass | Worker-capacity implication |
|---|---|---:|---|
| Verified one-row-group Parquet cache / avoid repeated decode and hash validation | RETEST | About 256.35 CPU-s versus the earlier uncached run (473.24 → 216.89 CPU-s including setup+replay; single run per side) | Theoretical 2.18× CPU-bound engine throughput only; durable queue/worker benefit is unmeasured. Keep the implementation pending repeated ROI/parity confirmation. |
| Canonical accumulator, msgspec-after-normalization, and timeline hot-path optimization (combined; effects cannot be separated honestly) | RETEST | About 120.10 CPU-s versus the cached pre-optimization run (216.89 → 96.79 CPU-s including setup+replay; single run per side) | Theoretical 2.24× CPU-bound engine throughput only; not a worker-capacity multiplier. Exact canonical byte/hash golden tests pass. |
| Provider page-copy reduction (8,192-tick profiled diagnostic) | RETEST | 7.443 CPU-s in one profiled run (70.285 → 62.842 CPU-s; about 10.6%) | Below the 15–20% end-to-end promotion bar and profiler-instrumented; durable-worker capacity saved is unknown, so no capacity credit. |
| Jump preview/replay reuse as a compute optimization | REJECT for CPU-capacity claims; retain the user-facing Jump feature | On the measured 1,024-tick A/B, Jump used about 1.45 more CPU-s (2.809 vs 1.359) and was 2.07× slower by wall time | At that sample it would reduce compute-limited throughput to about 0.48× normal replay; no CPU saving is shown. A new algorithm requires causal parity and a new benchmark. |
| Rust/PyO3 hot-loop replacement | REJECT for production adoption; no prototype justified yet | 0 CPU-s measured/saved | No capacity impact established. Reconsider only after a profile isolates a suitable hot loop and an isolated candidate demonstrates roughly 2× end-to-end gain or a major memory reduction with full parity/recovery. |

No candidate currently qualifies for Commercial V1 capacity credit: the promising Python/Arrow savings lack three-run repetition and a durable-worker comparison, while the durable 65,536-tick path is blocked by the existing 256-step Session checkpoint limit. No Rust/native dependency is added.

**DoD status on 2026-11-13: NOT DONE / HOLD.** The next engineering blocker is a reviewed, backward-compatible durable timeline checkpoint compaction/continuation design that can represent long Sessions without relaxing financial, causal, or recovery guarantees. That changes frozen checkpoint/recovery behavior and needs Owner authorization before implementation.
