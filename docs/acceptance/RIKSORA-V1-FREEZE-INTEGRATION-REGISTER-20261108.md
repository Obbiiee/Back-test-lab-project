# RIKSORA V1 — frozen-architecture integration register

**Recorded:** 2026-11-08
**Authority:** [Product System Architecture Blueprint — owner freeze](../PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#owner-decision--riksora-product-v1-architecture-freeze-2026-11-08).
**Scope:** Candidate Product V1 branch only. No automatic deployment, migration, deletion, data-rights promotion or re-run of the annual benchmark.
**Baseline examined:** PR #44 `codex/product-integration-v1-20261106` at `4bc3defe6ff552b5ef3790b7d439732bd1f73d09`.

This register tracks the gap between the **agreed target** and **verified code**. It is not a competing architecture source, a claim that every task is complete, or permission to bypass protected financial/no-look-ahead contracts. Each item below is a product implementation task, **not a request for a new exploratory benchmark**.

## ACTIVE execution pointer — repo-only Product V1 (2026-11-08)

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

**Gap:** default Session storage is `snapshot-v1`; `compact-v1` is gated to new Sessions. Normal observed Session has **128 cumulative lifetime orders**; terminal archive is QA-only. Cold compact reconstruction scans deltas since genesis.

**Deliverable:** production-versioned compact storage for new Sessions, compatible legacy read, append-only financial event truth, active order hot-state only, versioned committed closed-order archive/read model, indexed paginated history and periodic verified compact recovery base to bound reconstruction. Keep exact idempotent retry and immutable record semantics, protect financial history and money.

**Done when:** a long-lived Session is not blocked after 128 lifetime completed orders, previous fills still reconcile, cold recovery reads a bounded tail rather than all revisions, and physical per-trade/Session disk accounting can detect growth including indexes/TOAST/WAL separately.

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
