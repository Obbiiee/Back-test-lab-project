# RIKSORA V1 — frozen-architecture integration register

## Owner checkpoint — V1 integration, browser stability and authority recovery (2026-11-10)

### Jump to Next Event — local synthetic implementation evidence (2026-11-11)

The frontend control and durable API/worker path now search bounded committed tick chunks through the canonical reducer and pinned provider, stopping on the earliest committed financial boundary while preserving order state at Session end. Golden parity includes pending fills, protection exits, equal-time ties, and the final unrevealed group at the current timestamp. Durable PostgreSQL tests cover retry, receipt recovery after worker death, and monthly-Parquet source execution. Two independent browser cohorts completed 10/10 full Jump → receipt → Journal/Analytics → logout/login/resume journeys on isolated PostgreSQL with the authored 2,048-tick fixture. Detailed measurements, test results, and private evidence paths are recorded in the newest `AI_CONTEXT/04_CURRENT_PHASE.md` checkpoint.

The 10-user cohorts are not a latency/capacity PASS: observed API p95/p99 are 4.47/15.54 s and 4.62/16.48 s, above the previously recorded provisional interactive targets of 2/5 s. Admission and in-handler Review/Journal work both contribute, but SQL/lock/commit decomposition is unavailable. No normal-replay-versus-Jump speedup, long-history Parquet performance, or >10-user capacity claim is made; those measurements remain pending. No external market data is included.

This register remains the implementation-gap tracker only. Agent permissions are defined in root `AGENTS.md`; technical architecture and frozen contracts remain in the Product System Architecture Blueprint; current authorization and status remain in `AI_CONTEXT/04_CURRENT_PHASE.md`. No second architecture or permission authority is introduced here.

Remote branch reconciliation: related remote branch `codex/exness-monthly-prep-remote-20261109` advanced to `be3cfc6` from common ancestor `273f8b0`. Its GitHub Actions run `42678982007` recorded ten sequential real-browser journeys PASS and `42678981688` recorded the pinned Parquet suite PASS. This historical evidence belongs to that remote source tree and is not inherited as validation for the merged candidate below; both the hidden-Journal-tab fix and local concurrent-acceptance implementation must be tested together.

### Default-auth concurrent acceptance and provisional latency targets (2026-11-11)

Two independent local Chromium cohorts each completed 10/10 full synthetic browser journeys with 10 closed trades, receipt, CLOSED Journal/Analytics, logout/login and Session resume. Evidence is retained privately at `frontend/tests/artifacts/riksora-private-browser-2g7bbfzy/report.json` and `frontend/tests/artifacts/riksora-private-browser-m3zfzycm/report.json`. The runtime used the actual product API, two configured workers, disposable PostgreSQL 16 and fixture `synthetic:local-alpha-v1` (2,048 authored ticks). API p95 was 8.68s in both runs and p99 18.85/20.42s. Explicit overload refusals recovered (6 and 10); queue terminal failures and auth rate limits were zero. Local KVM only, no VPS inference.

Before the cache experiment, provisional 10-trader engineering targets were recorded in current-phase: interactive API p95 ≤2s/p99 ≤5s; async submission/status p95 ≤500ms/p99 ≤1.5s. These are candidate targets, not frozen acceptance contracts. Server-Timing shows review and Journal tails include substantial direct-admission waits and operation time; probe RTT does not split SQL, locks, transaction commit, or serialization. The compact-state LRU's old capacity of four vs ten interleaved Sessions is now tested as a bounded optimization hypothesis; post-change evidence is required before attributing root cause. Existing queue 60s TTL/worker 30s deadline remain unchanged.

### Post-cache 10-trader retest and bounded local economics (2026-11-11)

With `_COMPACT_CACHE_MAX=16`, two additional independent runs (`ldhgoiwp`, `q_ghp70r`) completed 10/10 full journeys and closed 10/10 trades. API p50/p95/p99: 87/6,289/17,953 ms and 78/7,043/15,477 ms; compared with preceding runs, p95 improved 18.7–27.5%, p99 4.7–24.2%. This supports the cache-eviction hypothesis but does not isolate it as the sole root cause. The provisional 2s/5s interactive p95/p99 target remains unmet. Review and Journal remain the slow routes; aggregate timing cannot distinguish SQL, lock, commit, and serialization. No cohort above ten or longer synthetic replay has passed; 20/50/100 remains pending.

Both retests used the actual product UI/API, two workers, isolated PostgreSQL16, and the 2,048-tick repository fixture. cgroup peak 3.04–3.07 GB; minimum MemAvailable 13.30–13.34 GB; free disk ~193.24 GB; swap and CPU throttling zero. Service CPU was 243–285 s, PostgreSQL CPU 5.02–5.17 s, browser generator CPU 113–114 s per ten-user run. Database growth 2.09–2.26 MB per cohort. This implies ~24–29 service CPU-seconds and ~209–226 KB DB growth per short test journey, not a valid 128-trade annual or customer-cost estimate; per-trade and customer overhead were not separated.

### Local synthetic Product acceptance continuation — measured (2026-11-10)

| Local slice | Status/evidence | Limits |
| --- | --- | --- |
| Browser user journey | **PASS** on the current working tree based on `8faa9db8fb644819a212363f62d750d4930c57d1`; Chromium 156 / Playwright 1.64.1, 101.57 s; login → workspace → Method → Session/chart/replay → review/confirm/exact retry → tick close → committed Journal/Analytics → logout/login/resume. Fresh PostgreSQL 16.15; cleanup true. | Password verification uses the in-memory test delivery sink. No real SMTP, Google OAuth, TLS-host trust, or persistent server after the gate exits. Synthetic software behavior only. |
| Synthetic data provenance | **PASS**; report pins dataset ID/version, canonical tick hash, Parquet manifest hash and bytes. 2,048 authored Bid/Ask rows; temporary Parquet 202,132 bytes. | Not market history, source-rights evidence or historical-price validation. |
| PostgreSQL financial/recovery | **PASS targeted**; exact concurrent confirm retry, immutable order archive/keyset, compact cold reconstruction, worker death before/after commit, empty-target backup restore with identical receipt/state. | Full backend discovery and actual PostgreSQL daemon stop/start were not run; this is targeted service/worker/restore recovery, not a capacity or backup-operations certification. |
| Auth, tenant scope, pages | **PASS targeted**; foreign-account refusal, owner/member/revocation, bounded Method/Session/Journal pages, 129 Method versions on signed cursor pages, compatibility detail remains latest 128. Removed ignored Method-detail pagination parameters from the API route. | Does not certify Google identity linking or external account providers. |
| Synthetic user cohort | **PASS sequential functional runs** for 5 and 10 users: 38.31 s and 68.74 s wall time; max RSS 198,400 and 197,532 KiB; about 97% CPU. | Not simultaneous users, not worker concurrency, not measured capacity. No max-user count inferred. |
| Frontend targeted/build | **PASS** targeted period, product pages and TickAlpha; ESLint; production build in browser gate; independent 6 golden vectors × 3. | Full registered frontend regression is **NOT PASS on final code**. The run previously stopped on a stale assertion; corrected test passes targeted, but full suite was not repeated because its `test:market` reads bundled non-synthetic OHLC history. |

The current final browser run initially required a rootless fontconfig environment variable; after using the supplied private font configuration the real browser/API/DB journey passed. Two other observed failures were stale test inputs/contracts, not product failures: a timeline target before the fixture's first timestamp, and Method version paging through the compatibility detail route. Those regressions now exercise the canonical timeline start and the existing signed-cursor `/versions` endpoint. Detailed commands, evidence identifiers and limitations are in the current-phase entry and test runbook. This checkpoint does **not** close external rights, live Google/SMTP, concurrent capacity, full-suite, historical accuracy, staging or production release gates.

The owner authorized the existing PR #50/#51 product integration path, the recovery of the phase file from its last readable Git parent, a UTF-8 authority regression, and sequential ten-run browser stability CI on disposable backend/PostgreSQL infrastructure. The phase file is restored from the valid parent of first-corrupt commit `e38a0592bafee1e005e5777b9e4f3c89f5b59b3d`, with the latest owner checkpoint prepended; earlier phase history remains intact.

Browser investigation found two independent test/runtime issues. The Analytics metric sat below the fold in the bounded terminal scroller; the browser test now scrolls it into view before checking the label and committed value. A subsequent run returned HTTP 429 on concurrent Journal/research reads. Source inspection showed the inactive Journal tab remained mounted, and its fetch effect replayed on Session revision changes while the user navigated elsewhere. The component now retains note drafts but only fetches while its tab is active. The E2E checks that no API 429 occurred and the latest Journal result is `CLOSED`. GitHub Actions run `42678982007` completed the full journey 10 consecutive times with separate temporary PostgreSQL and real backend/browser: **10/10 PASS**, cleanup true on all reports. The earlier `42677281620` and `42677950361` failures remain historical evidence; the latter showed 429s at method-version and Journal page routes. No timeout increase or sleep was used to mask these failures.

PR #51 adds the resumable synthetic-tested pipeline atop PR #50's integration tree and reuses the frozen Monthly Parquet V2 writer/reader and server-side source catalog. A bounded PostgreSQL worker journey already exercises pinned Monthly Parquet through order confirmation, replay, durable receipt, Journal and summary. No real Exness partitions have been acquired (`0/544`); provider rights and capacity remain unverified, so historical acquisition and commercial eligibility stay blocked.

Tested PR #51 code head `be3cfc6c5220e38afd11f3bdd64c188fcfb61cc5` is based on PR #50; its tested GitHub PR merge tree is `d5f71f09b9a7361abd06ac1d01e9e801f6eafde1`. Browser CI `42678982007`: **PASS, 10/10** on that merge tree; setup, authority guard, frontend lint and focused regression tests pass. Parquet CI `42678981688`: **PASS** with pinned PyArrow dependencies and the synthetic Exness/monthly-Parquet regression set. Local focused browser gate suite: 6 passed, 1 skipped because Node is unavailable locally; Python compilation and `git diff --check` pass. The authority-document CI guard also passes. This checkpoint itself is documentation-only and records test evidence for the unchanged code tree above. Full backend catch-all tests, broader migration/recovery matrix, and a separate production build/regression sweep were not run. PR #50/#51 remain open drafts and unmerged.

Private staging manifests exist, but root `AGENTS.md` prohibits SSH/VPS/deployment in this repository-only checkpoint; server access was not attempted, and no active URL or staging smoke test is verified. Dataset status remains `0/544`; provider rights and disk capacity are unverified. Synthetic tests do not establish market-history accuracy, licensing, capacity, or production readiness. This branch is not a deployed Owner UAT environment.

**Recorded:** 2026-11-10. **Baseline:** PR #50 `d8f5e12843fd84a7f23524b91c307b63a9b84138`; PR #51 code head tested `be3cfc6c5220e38afd11f3bdd64c188fcfb61cc5` (tested PR merge tree `d5f71f09b9a7361abd06ac1d01e9e801f6eafde1`).

## Owner-authorized browser/staging checkpoint (2026-11-09)

Added a version-pinned Playwright 1.64.1 browser acceptance lane on Ubuntu 24.04. It installs Chromium and its OS libraries using Playwright's official `install --with-deps` command, builds the checked-out frontend, starts the existing disposable Unix-socket PostgreSQL16 harness, starts the real HTTPS backend with a restricted runtime role, and drives the current account/Method/Session/replay/order/receipt/Journal/Analytics/logout/resume UI. The browser has same-origin-only egress; no authored API response mocks are installed. Synthetic verification delivery is supplied by the existing in-memory test delivery adapter. Browser evidence remains on the isolated runner and is not uploaded as a public workflow artifact.

Added `deploy/vps/compose.staging.yaml`, `Caddyfile.staging`, and `.env.staging.example`. The dedicated Compose overlay uses a separate PostgreSQL volume and requires Caddy Basic Auth before any app/API route. At the time this historical checkpoint was recorded, deployment was **NOT TESTED / BLOCKED**: the configured SSH alias `sorabit` did not resolve, and no VPS identity/connection was verified. No staging URL exists. The former statement that the phase file was intentionally preserved as binary is superseded by the newer owner recovery checkpoint above; it records the earlier handling and is not current permission.

Browser workflow execution and final-HEAD browser evidence are **PENDING CI** because this local environment has no Node/npm, Docker, PostgreSQL16 tools or project Python dependencies. Local browser E2E is therefore NOT TESTED at this checkpoint; do not infer PASS from the earlier API functional journey. Synthetic acceptance does not certify historical-source accuracy, licensing, capacity or production.

**Recorded:** 2026-11-08
**Authority:** [Product System Architecture Blueprint — owner freeze](../PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#owner-decision--riksora-product-v1-architecture-freeze-2026-11-08).
**Scope:** Candidate Product V1 branch only. No automatic deployment, migration, deletion, data-rights promotion or re-run of the annual benchmark.
**Baseline examined:** PR #44 `codex/product-integration-v1-20261106` at `4bc3defe6ff552b5ef3790b7d439732bd1f73d09`.

This register tracks the gap between the **agreed target** and **verified code**. It is not a competing architecture source, a claim that every task is complete, or permission to bypass protected financial/no-look-ahead contracts. Each item below is a product implementation task, **not a request for a new exploratory benchmark**.

## ACTIVE execution pointer — repo-only Product V1 (2026-11-08)

### PR #48 / PR #44 reconciliation checkpoint (2026-11-08)

**Follow-up backend regression fixes:** Reproduced then fixed Product Session creation selecting legacy genesis (`REFUSED_POLICY`), catalog format reads indexing tuple rows as dictionaries, and the full-projection compatibility path losing earlier order details after 64 completed rows. The first analytics page is now checked against the requested revision before loading later pages. Five focused application tests plus eight finance/golden tests pass; SQL is mocked in the application tests. This does not make the full projection lifetime-bounded or prove native PostgreSQL/hosted acceptance.

**Product progress/recovery compatibility follow-up:** `read_progress`, receipt lookup, replaceable replay progress, periodic compact-base cold reconstruction and the store's product archive-tip check now carry the Product order-retention policy. Cold replay previously validated Product state as legacy and failed closed; the archive tip guard also mistakenly received the wrapper instead of its `state`. Eight targeted progress/application tests pass, including product genesis, progress round-trip, retry identity, financial-mutation refusal, cold archive tip and analytics page revision. PostgreSQL statements remain mocked in this suite; embedded migration SQL remains separate evidence.

Live GitHub heads examined: #44 `32c75e7c3518f09f9ad3a3e122cd0a388a1954cd`, #48 `5c4e8d47913ddf6a5fbebb88aadd01f102987148`. Compared recursive trees and pinned source, not stale local tracking refs. GitHub comparison is divergent (25 commits on #48, 46 on #44); its file list is relative to the merge base, so it is not a complete direct tree comparison.

Reconciled the **migration file set only**, on P0-1: retained all original 023–025 filenames/bytes from #48 and added #44's eight original 023–030 files. The runner keys `public.btl_migrations` by full filename and LF-normalized SHA256, not the numeric prefix. Renaming or editing an applied migration causes `MIGRATION_DRIFT`. The pinned Git blob manifest is `backend/tests/fixtures/migration_reconciliation_heads.json`; the regression checks every published migration against it. No migration was renumbered, existing ledger rewritten, account linked, or production database accessed. Actual deployed migration history remains UNKNOWN; the two published histories are tested upgrade fixtures, not evidence of a deployed ledger.

The progress-consolidation migration replaces `guard_tick_session`; both histories retain its dependency on `observed_replay_progress` and its restricted-role legacy behavior. #44's terminal archive (`btl.tick_terminal_orders`) and #48's (`btl.tick_terminal_order_archive_v1`) are separate tables with different wire artifacts. They are retained independently; this checkpoint does not convert archive evidence or dispatch one artifact through the other implementation.

**Archive/replay integration contract matrix (source-verified on the current #49 tree):**

| Field/behavior | PR #44 integration archive | PR #48 native Product archive | Candidate handling |
| --- | --- | --- | --- |
| Session state identity | `BTL-OBSERVED-EXECUTION-STATE-ARCHIVE-1` | `BTL-OBSERVED-EXECUTION-STATE-PRODUCT-ORDER-ARCHIVE-1` | Dispatch by persisted artifact; no state rewrite |
| Archive artifact / schema | `BTL-OBSERVED-TERMINAL-ORDER-ARCHIVE-1`, schema 1 | `BTL-TERMINAL-ORDER-ARCHIVE-1`, schema 1 | Keep distinct codec, genesis and summary hashes |
| Record fields | `schemaVersion, artifact, sessionId, sequence, finalizedRevision, orderId, previousHash, order, orderHash, recordHash` | Same names/shapes | Same field set does not make the wire identity or hashes interchangeable |
| Summary fields | `schemaVersion, artifact, count, grossPosted, headHash`; integration summary artifact | Same fields; native Product summary artifact | Validate exact summary artifact and chain head per codec |
| PostgreSQL table | `btl.tick_terminal_orders`; adds required `terminal_status` column, scoped sequence PK and scoped order uniqueness | `btl.tick_terminal_order_archive_v1`; no `terminal_status` column, scoped sequence PK and scoped order uniqueness | Route reads/writes from state artifact; retain both migrations and table schemas. Fixed the combined writer to supply `terminal_status` only for the #44 table. |
| Write/recovery | Append record and compact summary with the Session checkpoint/receipt transaction; recovery verifies archive records against persisted integration summary | Same transaction boundary using native Product archive codec; cold-read verifies archive tip/chain | Require atomicity and verification in the selected artifact family; do not copy rows across tables |
| Receipt format | Not determined by archive family. The compact-v1 store encodes `BTL-OBSERVED-EXECUTION-RESULT-COMPACT-1` (`formatVersion=1`); snapshot-v1 stores the full `BTL-OBSERVED-EXECUTION-RESULT-1` | Same receipt formats, selected by persisted state-storage format | Decode only the receipt format selected by state storage; retries bind command ID/hash and recorded state/chain; no receipt promotion or fabricated committed result |
| Replaceable replay | `compact-progress-v1` row is a PR #48 addition, anchored to immutable base/checkpoint revision and hash; exact latest retry is retained separately from financial receipts | Same PR #48 behavior | Keep replay progress replaceable and monotonic; financial receipt remains immutable and authoritative |
| Migrations | Original `024_tick_terminal_order_archive.sql` | Original `025_product_terminal_order_archive.sql`, plus progress migration files with independent full filenames | Migration ledger keys full filename + normalized hash; never renumber/edit an applied file |

Regression coverage checks both record schemas, proves each archive verifier rejects the other archive's record, and checks the writer emits the exact selected table columns. The #44 archive writer previously omitted its required `terminal_status`, which would fail that archive insert; this checkpoint fixes the column mapping. These tests do not prove PostgreSQL transaction behavior or the hosted end-to-end journey.

Remaining #48 deltas absent/different in #44 source:

| Slice | Reconciliation disposition |
| --- | --- |
| `observed_replay_progress.py`, migrations 023/024, progress receipt/retry + Review/Confirm dispatch in observed store/research/cloud/client | Missing on #44; retain #48, needs composition with #44 runtime and transaction tests |
| `observed_state_delta_v3.py`, `observed_postgres.py` compact progress deltas and inline recovery bases | Different from #44's separate recovery-base table and chain contract; do not replace #44 wholesale |
| `ticks/timeline_v2.py` interrupted-target resume, genesis/group bounds, read-only probe close | Missing on #44; scoped recovery changes eligible for later transplant with their regressions |
| `cloud/queue.py` fresh replay-to aging versus cross-actor interactive jobs | Missing on #44; preserve FIFO and fair-turn behavior when composing |
| Hosted `AppEntry`/`entryRoute`, fresh read IDs, uncertain sign-out, observed receipt/client checks | #48 deltas require comparison with Claude presentation; no frontend presentation copied in this checkpoint |
| Product archive policy/state, revision-pinned order/analytics response pages and client loaders | Parallel #48 implementation, not a replacement for #44's newer Journal/Analytics. Response pagination does not bound full-history folding |

#44's `journal_order_index`, `incremental_analytics`, coverage markers, compact recovery bases, Monthly catalog/Parquet, worker routing, identity and Claude frontend remain untouched on GitHub. **The branches are not yet runtime-reconciled or merge-ready.** Importing migrations does not import those implementations.

Validation: all 33 migration files and original Git blob identities passed embedded PostgreSQL for fresh → union, #44 → union, and #48 → union, including retained nonempty archive/recovery payloads, migration retry/drift refusal, least-privilege legacy update, progress receipt commit/rollback, and immutable-table truncation refusal. Thirteen pure/kernel financial/archive tests passed, including 240 terminal orders and financial goldens. Native psycopg/PostgreSQL integration is NOT RUN successfully: no native test DSN; disposable PGlite socket failed with `ECONNRESET`. Direct embedded SQL is narrower evidence. Native opt-in regression remains in `test_migration_reconciliation.py`.

**Use the CURRENT state of the code, not the age of a test report.** This is the existing Product V1 implementation register, not an architecture replacement. Agent permissions are in root AGENTS.md and active phase is the newest AI_CONTEXT/04_CURRENT_PHASE.md entry. **No VPS, SSH, deployment, historical replay, data ingestion, storage/performance/load/concurrency benchmark or big evidence generation during coding.** A new owner approval is required for those actions.

### Deterministic next-work queue (check actual code before claiming complete)

**Rule:** Work on the earliest *ready, unimplemented* task in the list below. If its dependency is missing, complete that dependency first. A synthetic vertical slice is valid for coding; it is **not** commercial/historical acceptance. Implement source and bounded tests, not another plan.

| Sequence | Work item | Baseline condition at PR #44 (4bc3defe) | Coding-only definition of done |
| --- | --- | --- | --- |
| **P0-1** | Single customer vertical slice and server as financial truth | Synthetic API → worker → Parquet → receipt → Journal exists; frontend/client and hosted journey are partial | One integrated frontend-to-API synthetic Method → Session → replay → review/confirm → durable receipt → journal → analytics → logout/resume path; no local browser financial settlement in hosted mode; scoped synthetic regression + frontend build |
| **P0-2** | Remove 128 cumulative Session order cap safely (issue #47) | 128 cumulative default; QA-only 512/1024/4096 and archive proof-of-concept | Versioned active-only hot state + atomic append-only production terminal archive, indexed history, legacy readers; 129/240+ synthetic completed orders with financial/crash/idempotency checks; no unlimited in-memory order map |
| **P0-3** | Shared-source V2 progress and compact recovery | v2 direct-index logic exists, not customer default; no-trade progress and compact cold reconstruction still costly | Code-wired new-Session versioned v2 source-index route; monotonic revealed high-water and financial/cursor crash parity; compact state with periodic verified recovery base; legacy formats untouched |
| **P0-4** | Monthly Parquet + source catalog without historical rights bypass | Synthetic QA provider exists; historical observed catalog still uses original archive | Versioned shared-source catalog/manifest + bounded PyArrow streaming and S3-compatible configuration using generated synthetic data; no per-user tick copy; rights UNKNOWN remains fail-closed |
| **P0-5** | Scalable journal, Method/Session pages and analytics | Hard 128/4096 and historical fold limits remain in parts of app/client | Indexed keyset pages + revision-pinned incremental trade/Method/session projections and bounded browser state; financial parity from committed events |
| **P0-6** | Identity, workflow modes and UX completion | Google/password conflict linking not yet an explicit safe workflow; chart/product UI partial | Explicit account linking, Free Style/Protocol/Planned/Quick flows, source/entitlement guards; bounded synthetic E2E and no duplicate account/financial authority |
| **P1-7** | Worker QoS and repo deployment recipes | One-worker queue works for synthetic QA; economics and runtime unverified | Bounded interactive/heavy QoS, idempotent resumable work and scoped telemetry; version-pinned scripts/docs to rebuild a *fresh* VPS later; do not execute scripts on any VPS |
| **RELEASE GATE** | Historical, crash-recovery, resource economics, concurrency, backup restore, browser hosted, commercial source rights | **NOT VERIFIED** for product; older annual evidence belongs to historical QA | Produce one finite final acceptance plan for owner approval **after** Product V1 feature integration; do not run it automatically |

**Ordering is dependency-aware:** P0-2 or P0-3 may be taken before P0-1 if necessary to make the integrated vertical slice safe, but give the owner a concrete code reason and return to P0-1. Treat these as one continuous Product V1 build, not separate QA campaigns. Do not claim a task DONE merely because a QA-only prototype or freeze document exists.

**Each "audit repo" response must return:** baseline branch/SHA and PR state, source-evidenced DONE/PARTIAL/TODO table, one next ready P0 task with code paths, tests not run, and explicit VPS/rights/hosted blockers. **Each "lanjut/kerjakan" response must also include a code diff/commit/PR and scoped synthetic test result, unless a concrete blocker prevents safe edits.** Update this same register and the top current-phase entry after a real milestone; no parallel status spreadsheets/roadmaps.

### P0-1 checkpoint — hosted entry isolation (PARTIAL)

The public entry now mounts the existing RIKSORA landing, with account sign-in as its workspace link. Explicit loopback routes retain the local workspace, legacy simulator, review and prototype. Hosted route selection never mounts those entries, even when a local selector is supplied. The signed-in workspace continues to use the existing account transport and server financial authority. The public landing identifies the preview and leaves source availability to the selected workspace.

Verified on the integration candidate: route and account transport regression, Local Tick Review, prototype isolation, confirm/receipt outcome, product pagination, repository boundaries, changed-file ESLint, production build, rendered landing CTA/source disclosure and independent Node golden vectors. Full authenticated browser → worker → receipt → Journal/analytics → logout/resume remains pending a small isolated synthetic integration check. Commercial-source acceptance, live provider verification, deployment and capacity acceptance were outside this checkpoint.

### P0-1 checkpoint — observed replay receipt persistence (PARTIAL)

The scoped implementation now routes observed `command_result` lookups, reconciles exact retries against replaceable replay-progress receipts, validates progress-format review/confirm input, and checks the observed result artifact in the frontend receipt path. The nine pre-existing implementation changes were reviewed as P0-1 work, tested and published to PR #48 (`c27e8a001075130ed26dfffc59b917b247f2120e`; local commit `d0dc78ef67e74bffeb42607b9c8c295628282257`). Focused frontend receipt/TickAlpha tests, lint/build, Python compilation, observed-finance goldens (6/6) and execution goldens (2/2) passed. Native PostgreSQL worker/receipt integration remains NOT RUN because the test dependencies and isolated test database are unavailable. The authenticated hosted browser → API/worker/PostgreSQL → Journal/analytics → logout/resume path remains open.

### P0-1 checkpoint — current Session reads and sign-out (PARTIAL)

Hosted view, bootstrap and chart-history reads now use a fresh queue identity per request. The queue retains completed results by ID, so a reused read ID could restore an old committed revision after replay or sign-in. A single read still polls its original job; mutation retries retain their deterministic ID and unexpected results remain explicitly uncertain. Hosted transport refuses local fallback, and sign-out only confirms server revocation after a successful server response.

A bounded client fixture that retains completed results by job ID verified revision 3 before sign-out and revision 4 after sign-in. The same suite verified stable mutation retries, local fallback refusal, and removal of the tab token when the logout response is lost. Full authenticated browser and isolated PostgreSQL worker verification remain open.

### P0-3 checkpoint — direct replay recovery integrity (PARTIAL)

Shared-source-v2 cold resume now refuses an altered genesis cursor and verifies that the revealed group count is consistent with the source ordinal bounds and the last revealed group is inside the Session interval. This preserves empty progress and atomic timestamp groups without rebuilding the historical prefix. The existing legacy replay-log reader now closes its read-only format probe deterministically.

Focused validation: 31 tests passed for shared-source recovery, legacy replay-log compatibility, tick storage and sidecar contracts, and financial goldens. Independent Node golden vectors also passed. The regression reproduced acceptance of a corrupted genesis before the fix. PostgreSQL frontier persistence, periodic compact recovery bases, replaceable no-trade progress, and production source selection remain open. The next replay integration must use an eligible shared source and must not enable the legacy QA-only observed admission mode as a customer default.

### P0-3 checkpoint — interrupted advance and monotonic commit (PARTIAL)

A shared-source-v2 checkpoint can resume an interrupted bounded advance directly at the next atomic timestamp group. Recovery verifies the remaining target against the pinned source. At the observed store write boundary, under the existing Session lock, the proposed checkpoint cannot rewind the committed time/group frontier, change its source pin, skip its pending target, or move the frontier during a non-replay command.

33 focused synthetic tests passed, including parity between uninterrupted and resumed advancement, refusal of invalid continuation targets and refusal of a rewind before any write through a mocked database boundary. PostgreSQL transaction integration, replaceable non-financial progress, periodic recovery bases and eligible production source selection remain open.

### P0-3 checkpoint — periodic compact recovery bases (PARTIAL)

The observed compact-v1 writer records a versioned recovery base every 64 revisions in the same immutable checkpoint row and transaction as the existing delta. The reader uses scoped indexed lookups to bind the base state and controller to its delta hash and predecessor, then validates at most 63 later deltas when a base is present. Older compact checkpoints fall back to the genesis reader. Receipt and checkpoint chain hashes retain their existing definitions.

17 focused tests passed, including a mocked database test proving the selected tail range and corruption refusal. Six independent Node golden vectors passed. Live PostgreSQL integration, maximum-size base acceptance, replaceable non-financial progress and production shared-source selection remain open.

### P0-1/P0-3 checkpoint — hosted forward jump and continuation (PARTIAL)

Hosted observed Sessions use the existing bounded replay-to worker for forward UTC jumps. The authenticated view returns only the user's pending requested target, and the browser resumes that target with Step or Play before requesting a new one. The client verifies the result's Session, request identity, revision and frontier before rendering it. Server retries are bound to the original target and starting revision through the first immutable advance command hash.

10 focused backend tests, frontend transport and receipt tests, repository checks, lint, build and six independent golden vectors passed. This covers synthetic controller and mocked transport/storage cases. Live PostgreSQL worker and interactive browser acceptance remain open. Replaceable non-financial progress still requires a new persistence contract rather than discarding existing immutable advances.

### P0-3 checkpoint — replaceable replay frontier schema (PARTIAL)

Migration 023 adds one replaceable progress row per scoped Session, anchored to an immutable checkpoint revision and content hash. The database refuses backward time, backward group index, stale revisions, a different workspace's checkpoint, and row removal. The table is additive and has no hosted runtime grants or writers in this checkpoint.

All 23 migrations executed in a disposable embedded PostgreSQL engine. Synthetic SQL assertions verified a single row across updates, refusal cases and no new immutable command receipt. The isolated native PostgreSQL regression is authored and was skipped locally because no test database was configured. Next, wire versioned progress writes and reads under the existing Session lock, with immutable financial commits consuming the exact revealed frontier and legacy Session reads preserved.

### P0-3 checkpoint — verified progress reader and writer (PARTIAL)

The new internal progress adapter locks the scoped Session before replacement, checks the expected revision, verifies the pinned shared-source checkpoint, and stores only replay fields over the verified immutable base. The reader rechecks the persisted hash, base revision, scoped row and frontier. The writer refuses active or pending orders, changed financial state, and any event other than the reducer's exact replay bookkeeping event. No hosted caller selects the new adapter yet.

17 focused synthetic tests and six independent Node golden vectors passed. The progress round-trip used real authored tick frames and a mocked database boundary. Next, add versioned hosted routing and make a financial commit atomically consume or consolidate the effective frontier, including durable command retries. The native PostgreSQL/browser gate remains open.

### P0-3 checkpoint — atomic progress consolidation contract (PARTIAL)

Migration 024 permits a skipped immutable revision only when the scoped progress row proves the exact intervening logical frontier and the replacement checkpoint and command receipt exist in the same transaction. An after-update trigger consumes that row atomically. Sessions without a progress row still advance one immutable revision at a time. The explicitly opted-in compact delta codec represents the consolidation with the previous immutable and consumed progress revisions, preserving the existing delta format for other Sessions.

All 24 migrations ran in a disposable embedded PostgreSQL engine. SQL assertions passed for rollback, successful consumption, rejection of an unbacked jump or stale anchor, and a legacy update by a role with no direct progress-table access. 13 focused backend tests and six independent golden vectors passed. The native PostgreSQL regression was skipped without a test DSN. The hosted observed store still needs version selection, sparse checkpoint reads/writes, and end-to-end receipt reconciliation before enabling replaceable progress.

### P0-3 checkpoint — latest replaceable receipt (PARTIAL)

The internal progress row now retains the latest advance command ID and canonical input hash. Exact retry returns the same bounded result with no additional write or financial event. Reusing the ID with changed input is refused. The result is recoverable while its progress row is current. The hosted store still does not select the adapter, and this does not replace immutable financial receipts.

### P1-7 checkpoint — priority across queued actor heads (PARTIAL)

The claim query lets another actor's interactive job pass a fresh multi-chunk replay-to job. Replay-to returns to ordinary actor rotation after five seconds of queue age. Per-actor FIFO and the worker lease are retained. Embedded PostgreSQL ran the actual claim SQL and proved both selection orders on three generated jobs. No throughput or wait-time guarantee is inferred. Native worker, durable unresolved-receipt retention and operational acceptance remain open.

## Executive status

- **ALIGNED BASE:** React/Vite/Lightweight Charts; Python/FastAPI; PostgreSQL financial events/receipts/checkpoints; versioned immutable source contracts; durable queue leases/fencing; workspace scoping; deterministic financial reducer.
- **PARTIAL AND NEEDS INTEGRATION:** shared-source-v2 (committed candidate, not general production-wired); compact-v1 (opt-in); monthly Parquet (PyArrow adapter, synthetic gate); bounded journal/method pages; Method versions; replay recovery.
- **NOT YET PRODUCT-READY:** commercial historical monthly Parquet/object storage provider, customer-facing shared-source default, normal-session closed order archive, periodic compact recovery bases, persistent incremental trade analytics and removal of hard lifetime/list ceilings, final worker QoS/cost policy, Google/email linking, historical source rights and final deployment acceptance.

## Implementation slices with definitions of done

### A. Shared historical market-data route — P0
**Existing code:** `backend/market_data/monthly_parquet.py`; `backend/cloud/research.py`; `backend/execution/observed_catalog.py`; `backend/execution/observed_admission.py`; `backend/execution/observed_source.py`; `backend/tests/qa_duckdb_day_provider.py`.

**Gap:** `MonthlyParquetProvider` already reads immutable row groups through PyArrow, but `_synthetic_monthly_provider` is explicitly QA-only. The observed customer path still resolves the local original `archive.sqlite` and operator qualification. DuckDB is only a QA reader candidate in the inspected baseline. Source-use rights for historical commercial execution remain UNKNOWN / NOT_GRANTED.

**Deliverable:** server-owned instrument/source/coverage/version catalog mapping eligible instruments to shared immutable monthly Parquet in S3-compatible storage; bounded ranged reads/caching, correct identical-time tick ordering/ordinal, clear Bid/Ask and source quality; use PyArrow for execution streaming and DuckDB only for suitable bulk queries, without redundant passes; no user-by-user dataset copies. Independent publication/admission proof and source pin must remain enforced without repeated whole-archive rehash on every warm worker. No rights bypass.

**Done when:** a versioned, authorized source goes through actual Method → Session → replay → order → committed result via the Parquet provider; restart reproduces the same result and a second user reuses the same source without a new full dataset copy. Commercial source remains unavailable until rights verified.

### B. Replay, progress and causal recovery — P0
**Existing code:** `backend/ticks/timeline_v2.py`; `backend/execution/historical.py`; `backend/execution/observed_catalog.py`; `backend/execution/observed_research.py`; `backend/cloud/research.py`.

**Gap:** `shared-source-v2` direct indexed checkpoints are now implemented and no longer create group position/advance logs, with a 16 MiB per-timeline cache; however `ObservedCatalog.resolve` constructs `AdmittedObservedSource` without a mode override, and its default is `session-log-v2`. QA v2 enablement is not a production feature. `replay_to` still persists many small ADVANCE commands/checkpoints. Cold recovery and no-rewind/no-look-ahead must be correct simultaneously.

**Deliverable:** versioned, opt-in-to-new-customer-Sessions **production** route using `shared-source-v2` with no QA flag; bounded checkpoint, durable monotonic revealed frontier before user-visible reveal, exact source ordinal/timestamp group, atomic finance/cursor commit; compact replaceable no-trade progress (target ~30 wall-clock seconds between checkpoints) but no replay to a previously seen trading opportunity after crash. Avoid one immutable no-financial-event record per tiny advance. Old Session formats continue to read through original validators.

**Done when:** no per-group position/advance log or per-user source duplicate is produced by newly created replay Sessions, the user cannot trade behind a previously revealed frontier, and resumed state/receipt/order outcome match their authoritative commit.

### C. User, trade and Session persistence — P0
**Existing code:** `backend/execution/observed_postgres.py`; `backend/execution/postgres.py`; `backend/execution/observed_kernel.py`; `backend/execution/observed_order_archive_v1.py`; `backend/execution/observed_state_delta_v3.py`; `backend/execution/session_storage_metrics.py`.

**Gap:** new observed hosted Sessions now select `compact-v1` Product archive mode; persisted Session artifacts select legacy versus Product validators on later requests and catalog reads. The immutable migration and bounded archive page are code-complete but have NOT been verified against PostgreSQL/worker runtime. Cold compact reconstruction and analytics still need bounded verified projections.

**Deliverable:** production-versioned compact storage for new Sessions, compatible legacy read, append-only financial event truth, active order hot-state only, versioned committed closed-order archive/read model, indexed paginated history and periodic verified compact recovery base to bound reconstruction. Keep exact idempotent retry and immutable record semantics, protect financial history and money.

**Done when:** a long-lived Session is not blocked after 128 lifetime completed orders, previous fills still reconcile, cold recovery reads a bounded tail rather than all revisions, and physical per-trade/Session disk accounting can detect growth including indexes/TOAST/WAL separately.

**Latest checkpoint (PARTIAL, 2026-11-08):** `8715e11` / PR #48 commits `1f2b818`, `0d8729e`, and `8b3e964` add Product-only unlimited cumulative retention with a bounded active set, an immutable indexed terminal-order table, revision-pinned sequence pages, persisted-version legacy/Product dispatch, and revision-pinned analytics response pages. New hosted observed Sessions select compact-v1 Product state; legacy validators remain selected for older artifacts. Pure archive checks cover 4,097 records and reject tampering; finance/execution goldens and frontend page/lint/build checks pass. Analytics response rows are bounded, but the fold still retains per-order lifetime history in process memory and Journal still gathers all rows. PostgreSQL migration, mixed-format catalog/session runtime tests are NOT RUN. Next: persistent incremental aggregates, keyset Journal, and native PostgreSQL lifecycle/recovery regressions. Register revision `6ede87a` was published; the oversized current-phase document could not be written through the GitHub connector and remains local.

### D. Analytical projections, journal and catalog scaling — P1 before public V1
**Existing code:** `backend/execution/observed_analysis.py`; `backend/execution/observed_research.py`; `backend/execution/product_read_model.py`; `backend/execution/product_method_lifecycle.py`; `frontend/src/tickAlpha/client.js`.

**Gap:** event folding in memory can rebuild long histories, observed `_complete_statistics` assembles all trade pages, Method analytics has 4,096-event limit for the candidate, catalog versions consume a 128-record lifetime budget, and hosted frontend refuses >128 loaded records even though some server pages exist. The journal full route remains bounded; cursor pages exist.

**Deliverable:** revision-pinned incremental persistent Session/Method aggregates, bounded equity samples, keyset page for trade/journal/Method/Session without hard 128 lifetime rows or full collection in browser memory. Preserve compatibility/unit restrictions when pooling results; never compute settlement from chart candles.

**Done when:** one newly committed trade updates derived statistics without replaying the entire previous ledger for every page request, stable page navigation works past 128 historical Methods/Sessions/orders, and aggregates can be rebuilt/verified against events.

### E. Worker fairness, quotas and predictable costs — P1 before public V1
**Existing code:** `backend/cloud/queue.py`; `backend/cloud/worker.py`; `backend/cloud/research.py`.

**Gap:** current global queue=16, per-user queue=2, worker slots=1, job deadline=30s and queued TTL=60s; initial one-day heavy replay consumed about one core, but no integrated concurrence/cost entitlement exists. Durable queue correctness is implemented.

**Deliverable:** keep PostgreSQL queue; separate interactive short work vs resumable heavy job service levels, per-actor fairness and server-side quotas; bounded memory, CPU, result size, queue age and storage retention; reliable job reconciliation before pruning operational rows. No Redis/Kafka/Kubernetes. Split long replay work into bounded resumable units; avoid promises of N heavy users without measurement.

**Done when:** client can pause/cancel/resume, uncertainty and timeout do not duplicate financial commands, one slow research job cannot starve every short interaction indefinitely, and the system exposes measured time/CPU/RSS/disk metrics for final acceptance.

### F. Auth, product UI, source rights and operations — P0 for account correctness, P1 for launch
**Existing code:** `frontend/src/tickAlpha/*`; `frontend/src/trading/useTrading.js`; `backend/identity/google_store.py`; `backend/cloud/app.py`; `deploy/vps/compose.yaml`; `docs/SECURITY_ARCHITECTURE.md`.

**Gap:** integrated product UI exists, but account-linking contract is not implemented, Google conflict does not auto-link; browser journey not fully verified. A legacy browser-local simulator persists in the repo and must not be another authoritative hosted financial engine. Object storage, off-host backup restore, quotas, commercial rights and real provider config require integration.

**Deliverable:** hosted frontend uses backend as the only financial authority; safe explicit Google/password account linking tied to existing `users.id`, no merge solely by matching email; source rights and entitlement fail-closed; one real authorized-session journey through chart, Method, order, receipt, journal and analytics; version-pinned deployment on isolated staging and controlled production approval; server quota/retention/backup restore drill.

**Done when:** an actual hosted browser account round-trip preserves the same user/workspace/trades, no duplicate financial authority is active, source/entitlement gates are enforced, and recovery from off-host backup is tested without touching production data.

## Mandatory evidence / no speculative benchmarks while building

**During implementation:** only syntax, lint/build, targeted unit/integration and transaction/no-look-ahead regressions necessary for the changed slice; use dedicated safe QA resources. No unapproved annual replay or broad load tests, no production/Annual PASS artifact deletion. Do not stall all product coding because a historical oversized annual QA gate cannot fit on a small host; document its actual scope as a **release gate** to run after integration, without claiming it passed.

**After integrated end-to-end Product V1:** one approved final acceptance plan with source license/rights, provider equivalence, financial parity, crash-at-commit + no double fill, no-look-ahead across crash, full-year user-attributed persistent disk and per-trade physical allocation, PG WAL/index/TOAST, shared source bytes, worker CPU/RSS, mixed interactive/heavy concurrency, queue health, security/tenant isolation, browser + mobile, off-host restore, cost/usage accounting and deployment rollback. Optimize only measured bottlenecks.

**No invented target pass:** ~16 KiB/trade, >32 KiB/trade review and <=10 MiB no-trade annual progress remain target budgets pending measured physical data. CPU ~1 core/heavy job is *observed in one existing gate*, not a concurrency guarantee.

## Safe merge / owner decision

Merge this freeze into the Product V1 integration branch only after comparing against current Codex/Claude changes and resolving actual conflicts without discarding either party's work. This register grants no authority to run destructive cleanup, change protected evidence, deploy, or bypass source licensing. The single source of architecture authority remains the existing Product System Architecture Blueprint.


### GitHub follow-up — bounded Method Analytics and catalog compatibility (2026-11-09)

**Partial, focused synthetic evidence:** PR #48 now uses 32-Session keyset batches to pool verified per-Session analytics projections without the former 128-Session route refusal. The accumulator has a versioned exact-rational snapshot/restore contract and can replace a Session contribution without growing state, but it is not yet stored or updated transactionally by the database runtime. Observed catalog compatibility returns a bounded 128-row prefix with explicit truncation and next keys instead of refusing larger workspaces. Focused local aggregate, keyset, Journal/Analytics, catalog-window and financial-golden regressions: 45/45 PASS; Python compilation and diff check PASS. PostgreSQL route/lifecycle tests remain NOT RUN because this environment lacks `psycopg` and `BTL_TEST_DATABASE_URL`. Next: durable Method rollup schema/writes and rebuild path, followed by PostgreSQL compatibility acceptance. This does not certify PR #44/#48 integration or hosted completion.


### P0-5 follow-up — durable bounded Method Analytics rollup (2026-11-09)

Added additive migration 032 with a versioned exact-rational Method rollup. Existing Methods are marked `REBUILD_REQUIRED` and lazily rebuilt from revision-verified Session projections; new Methods start with an empty rollup. Observed Session creation and committed Session metric replacements update the rollup in the same database transaction. Legacy/local Session creation invalidates the rollup so the next read rebuilds it. The snapshot is hash-checked and bounded to 256 KiB; aggregate detail remains capped at 128 Sessions.

Validation on the coding checkout: focused synthetic Method/Journal/Analytics/financial suite 47/47 PASS; Python compilation and `git diff --check` PASS. Embedded PGlite migration/reconciliation PASS for fresh, PR #44, and PR #48 histories (35 migrations each), including backfill of one existing Method/Session. Native PostgreSQL acceptance is NOT RUN because `psycopg` and `BTL_TEST_DATABASE_URL` are unavailable. Rollup runtime transaction acceptance against PostgreSQL remains pending; this does not complete the end-to-end hosted Product V1 path. Local commit: `7b3a544`.


Publication verification for the Method rollup milestone: all source, migration, and regression files were published to PR #48 through the GitHub Contents API. File readback confirmed the durable-store wiring and migration backfill assertions. The API commits were `6d5d7d0`, `0f57d3c`, `b9aa7ce`, `48120c3`, `16c7289`, `264cb05`, `2b49b38`, `0e2b00c`, `cb2e3aa`, and `211fea8`; PR #48 was open/draft at `211fea824c8903205a6309cf413a016d6f1d3b08` before the next slice. PR #44 remained unchanged at `32c75e7c3518f09f9ad3a3e122cd0a388a1954cd`. No CI status checks were attached to the published documentation commit.

### P0-5 follow-up — legacy Method Analytics keyset aggregation (2026-11-09)

The local/Product Method Analytics path now reads Session IDs in keyset batches of 32 rather than refusing at 129. It verifies each Session through the existing runtime, reduces one Session's completed trade rows immediately into exact rational totals, and retains only the accumulator's bounded 128-row detail window. Method-wide event-count rejection and concatenation of every Session's completed rows are removed; an individually incomplete/over-limit Session is explicitly listed as excluded. No cross-Session streak or balance is introduced.

Validation on the coding checkout: 46 focused synthetic aggregate, keyset, Journal/Analytics, store, and financial-golden tests PASS; five tests that import backend runtime modules used dependency stubs for unavailable `psycopg`/`numpy` imports and did not open a database. Python compilation and `git diff --check` PASS. PostgreSQL acceptance remains NOT RUN. Local commit: `957f9d7`; GitHub API commits for this slice are `bbf9752`, `a670c33`, and `c2db5a2`. This removes the Method-wide 128 Session and 4,096-event budget caps but still excludes individual Session analytics that cannot complete the bounded legacy event fold.


Publication verification for legacy Method Analytics: the method accumulator, keyset read path and 130-Session regression were published to PR #48 and read back from `codex/product-v1-p0-1`. GitHub API commits: `bbf9752395df22e9032acdef09d2be086ec24e72`, `a670c33bcb95170acab7e854960058e9d8752b28`, and `c2db5a2fc71f912c8bdbb6a9d6873c85e3be19ba`. Verified PR #48 HEAD before this register update: `54f8bd570bf0f117ab371dd17d38c2bbb904608f`; PR #44 remains `32c75e7c3518f09f9ad3a3e122cd0a388a1954cd`. Both PRs remain open drafts; no merge or production action was taken.


### P0-4 follow-up — bounded Monthly Parquet row-group reader (2026-11-09)

The immutable Parquet reader now consumes each requested row group through PyArrow `iter_batches()` with an 8,192-row batch bound, while verifying the complete canonical row-group hash, source order/provenance, timestamp order, and global-index endpoints. It preallocates only the two bounded typed index arrays and avoids materializing a full Arrow Table. A regression forbids `read_row_group()` and forces multiple two-row batches over synthetic data.

Python compilation and `git diff --check` PASS. The Monthly Parquet regression is NOT RUN because this checkout's Python 3.13 lacks `pyarrow` (and `numpy`); no test pass is claimed. GitHub API published the reader and regression to PR #48 as commits `f9563d21086cef61b7dd15159b78aed8d7332004` and `525fceec9806f77bd054ee91865d30ec51c4b7a4`. Remote readback verified the test and bounded batch implementation. PR #48 HEAD before this register update: `525fceec9806f77bd054ee91865d30ec51c4b7a4`; PR #44 remains unchanged. S3 integration and full API/queue/worker acceptance remain NOT RUN.

### P0-E follow-up — one-pass exact committed metrics (2026-11-09)

The PR #48 candidate had retained the pre-optimization `metrics()` implementation from PR #44's older base. It allocated separate lists for net, wins, losses, R values, and durations. Ported only the existing PR #44 one-pass exact accumulator into `backend/execution/analysis.py`; added a regression proving single-pass iterator consumption and parity for exact rational metrics. No formulas, output fields, financial state, or analytics authority changed.

Validation: Python compilation and `git diff --check` PASS. Local direct execution was BLOCKED because `psycopg`, `numpy`, and `pyarrow` are absent. An isolated AST comparison against the PR #48 prior implementation passed empty, mixed win/loss/breakeven, R/duration, and one-pass iterator cases. GitHub Actions passed the 53-test analytics/financial/application suite including `AnalysisGoldenTests`. Native PostgreSQL was not available locally; hosted journey remains NOT RUN. This is a bounded P0-E code contribution, not end-to-end acceptance.

The derived work branch inherits a non-text/binary `AI_CONTEXT/04_CURRENT_PHASE.md` blob from PR #48 (48,058 bytes); do not overwrite it or infer operational status from it. The text status on PR #44 is a different older candidate state, so it was not substituted. Reconcile this context owner during an explicit reviewed PR #44/#48 integration checkpoint.

CI follow-up: first run exposed a malformed legacy-test docstring preventing suite import; after repairing it, the suite ran 53 tests and exposed a stale mocked SQL boundary in synthetic Session creation. That boundary now mocks the separately covered Method rollup helper. The next run passed all 53 analytics/financial/application tests. PostgreSQL integration then exposed a restricted-role grant defect and two harness issues: missing `BTL_QA_CLUSTER_ROOT` in a WAL/footprint benchmark, and a killed-worker subprocess resolving `tests` from the repository root. The role grants and subprocess working directory are now fixed. CI selects bounded persistence/recovery tests explicitly and omits only the WAL/footprint benchmark; capacity remains a separate gate and is NOT RUN. The isolated upgrade test remains skipped until a disposable migration harness is available. Migration rejection log entries are expected assertions, not failures.

### P0-1/P0-5 follow-up — restricted runtime projection grants (2026-11-09)

The isolated PostgreSQL run showed that `grant_execution_runtime()` omitted the bounded Journal and analytics read-model tables added after the original runtime grant. The runtime now receives SELECT/INSERT/UPDATE on Journal heads and projections, INSERT only on the append-only Journal order-event index, and SELECT/UPDATE on Session/Method analytics projections plus the Session method link. It still receives no update/delete rights on immutable tick evidence or Journal order events. The existing `test_restricted_runtime_commits_but_cannot_modify_evidence` passed against isolated PostgreSQL after this change. This is a storage permission correction, not a change to financial or analytics authority.

### P0-3/P0-F follow-up — isolated recovery CI scope (2026-11-09)

Fixed the synthetic killed-worker recovery test to launch from `backend/`, so its child process resolves the same `tests` package as the parent. Backend CI now explicitly runs bounded persistence, idempotency, restricted-role, archive-recovery and migration-runner cases while excluding the WAL/footprint benchmark, which requires a private PostgreSQL cluster root. The latest GitHub Actions run passed 53 analytics/financial/application tests and 19 PostgreSQL recovery/migration-runner tests; one upgrade-history integration test was skipped because it requires a fresh disposable migration harness database. The WAL/footprint measurement stays outside routine CI and is not claimed complete; capacity remains a separate gate.

### P0-1/P0-C follow-up — archive writer and authenticated API journey (2026-11-09)

The #44 integration archive table requires `terminal_status`; #48's native Product archive table does not. The shared writer now selects insert columns from the persisted Session artifact, retaining each format/table and its codec. A native PostgreSQL regression writes a cancelled order to the #44 table, checks the exact artifact/status, reconstructs the Session and retries the command with the original receipt. The explicit Google demo runtime also now has least-purpose table grants for immutable Method versions and their mutable family head, which Method creation needs; a real restricted-role journey reproduced the prior 503 and passes after the grants.

Added an authenticated single-instrument authored-synthetic API journey to backend CI: login, workspace, Method, Session, replay, review/confirm, exact retry, close, committed analytics, Journal, logout, new app/login, and persisted resume. It uses a separate disposable PostgreSQL database. Focused Postgres recovery/migration selection ran 20 cases (one migration test self-skipped without its opt-in DSN); the new #44 archive case and one-instrument journey separately PASS. Frontend lint and production build PASS; targeted frontend regressions PASS. Browser-runner E2E and real-source/provider acceptance remain NOT TESTED. The existing 16-instrument synthetic test is not part of routine CI. PR #44/#48 runtime reconciliation remains PARTIAL: only their archive writer/table distinction is covered here; broader worker, queue and frontend integration is not certified.

### PR #44/#48/#49 integration candidate — repository checkpoint (2026-11-09)

A safe candidate branch, `codex/riksora-v1-integration-20261109`, was created from the verified PR #49 head and merged with PR #44 while preserving the #49 branch's frozen Product contracts and binary current-phase blob. The PR #48 implementation is already the parent of #49. Both archive codecs and their separate PostgreSQL tables remain selected from the persisted Session artifact; the terminal-order compatibility route reads through the selected archive reader. The local tick API now exposes revision-pinned order-history and committed analytics pages expected by the frontend. Monthly-source identity remains pinned through resume/chart operations, and Method version history now uses the signed revision-pinned cursor endpoint.

Merge regressions fixed during this checkpoint: worker environment composition now validates and forwards monthly catalog/S3 settings while retaining source-root sanitization; compatibility with the earlier recovery-base revision argument is verified; archive retention defaults are selected only when the versioned archive mode is explicit; and the Session summary uses the committed projection head, with a legacy event fallback. Monthly Parquet lookup tests retain bounded row-group reads. Added a synthetic order-history adapter regression.

CI on the integration candidate final code SHA `00da9fdb189d22ea8175f7907d10a5e09b7fcf20` passed: 55 backend Method Analytics/financial contract tests; 20 selected PostgreSQL migration, receipt, archive, idempotency, recovery and permissions tests (1 opt-in migration test skipped); and the isolated authenticated one-instrument API journey (1 test). The journey exercises login, workspace, Method, Session, replay, review/confirm, idempotent retry, close, committed analytics, Journal, logout, fresh login and persisted resume. The rerun also covered the regression fixing committed analytics when terminal orders are absent from active hot state, lifetime event histories beyond the former 4096-event cutoff, the persisted-artifact archive codec return contract, and the durable analytics projection artifact export. The GitHub workflow is `Product V1 backend contracts`, run 13, completed successfully. Local frontend targeted tests, ESLint and Vite production build passed on the integration tree before these backend-only fixes; Python compilation and `git diff --check` passed on the fixes. Browser E2E remains NOT TESTED: local Chromium cannot launch because the host lacks `libnspr4.so`; the API journey is not a browser test. No staging deployment or production action was attempted.

This is a backend/API and frontend-build integration candidate, not yet a browser-verified Release Candidate or an Owner-UAT-ready website. PR #44/#48/#49 code is present in one draft PR, but the full frontend-driven chart/replay/order interface has not been proven end-to-end in a browser. The archive codecs and PostgreSQL routes remain version-dispatched, not converted. Staging needs an explicitly verified staging host and credentials; none were available in this repository-only session. Source rights, real historical-data validation, capacity certification and public deployment remain separate gates. `AI_CONTEXT/04_CURRENT_PHASE.md` is preserved byte-for-byte because the PR #48/#49 version is a binary blob; no speculative replacement was made.
