# RIKSORA V1 — frozen-architecture integration register

**Recorded:** 2026-11-08
**Authority:** [Product System Architecture Blueprint — owner freeze](../PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md#owner-decision--riksora-product-v1-architecture-freeze-2026-11-08).
**Scope:** Candidate Product V1 branch only. No automatic deployment, migration, deletion, data-rights promotion or re-run of the annual benchmark.
**Baseline examined:** PR #44 \`codex/product-integration-v1-20261106\` at \`4bc3defe6ff552b5ef3790b7d439732bd1f73d09\`.

This register tracks the gap between the **agreed target** and **verified code**. It is not a competing architecture source, a claim that every task is complete, or permission to bypass protected financial/no-look-ahead contracts. Each item below is a product implementation task, **not a request for a new exploratory benchmark**.

## Executive status

- **ALIGNED BASE:** React/Vite/Lightweight Charts; Python/FastAPI; PostgreSQL financial events/receipts/checkpoints; versioned immutable source contracts; durable queue leases/fencing; workspace scoping; deterministic financial reducer.
- **PARTIAL AND NEEDS INTEGRATION:** shared-source-v2 (committed candidate, not general production-wired); compact-v1 (opt-in); monthly Parquet (PyArrow adapter, synthetic gate); bounded journal/method pages; Method versions; replay recovery.
- **NOT YET PRODUCT-READY:** commercial historical monthly Parquet/object storage provider, customer-facing shared-source default, normal-session closed order archive, periodic compact recovery bases, persistent incremental trade analytics and removal of hard lifetime/list ceilings, final worker QoS/cost policy, Google/email linking, historical source rights and final deployment acceptance.

## Implementation slices with definitions of done

### A. Shared historical market-data route — P0
**Existing code:** \`backend/market_data/monthly_parquet.py\`; \`backend/cloud/research.py\`; \`backend/execution/observed_catalog.py\`; \`backend/execution/observed_admission.py\`; \`backend/execution/observed_source.py\`; \`backend/tests/qa_duckdb_day_provider.py\`.

**Gap:** \`MonthlyParquetProvider\` already reads immutable row groups through PyArrow, but \`_synthetic_monthly_provider\` is explicitly QA-only. The observed customer path still resolves the local original \`archive.sqlite\` and operator qualification. DuckDB is only a QA reader candidate in the inspected baseline. Source-use rights for historical commercial execution remain UNKNOWN / NOT_GRANTED.

**Deliverable:** server-owned instrument/source/coverage/version catalog mapping eligible instruments to shared immutable monthly Parquet in S3-compatible storage; bounded ranged reads/caching, correct identical-time tick ordering/ordinal, clear Bid/Ask and source quality; use PyArrow for execution streaming and DuckDB only for suitable bulk queries, without redundant passes; no user-by-user dataset copies. Independent publication/admission proof and source pin must remain enforced without repeated whole-archive rehash on every warm worker. No rights bypass.

**Done when:** a versioned, authorized source goes through actual Method → Session → replay → order → committed result via the Parquet provider; restart reproduces the same result and a second user reuses the same source without a new full dataset copy. Commercial source remains unavailable until rights verified.

### B. Replay, progress and causal recovery — P0
**Existing code:** \`backend/ticks/timeline_v2.py\`; \`backend/execution/historical.py\`; \`backend/execution/observed_catalog.py\`; \`backend/execution/observed_research.py\`; \`backend/cloud/research.py\`.

**Gap:** \`shared-source-v2\` direct indexed checkpoints are now implemented and no longer create group position/advance logs, with a 16 MiB per-timeline cache; however \`ObservedCatalog.resolve\` constructs \`AdmittedObservedSource\` without a mode override, and its default is \`session-log-v2\`. QA v2 enablement is not a production feature. \`replay_to\` still persists many small ADVANCE commands/checkpoints. Cold recovery and no-rewind/no-look-ahead must be correct simultaneously.

**Deliverable:** versioned, opt-in-to-new-customer-Sessions **production** route using \`shared-source-v2\` with no QA flag; bounded checkpoint, durable monotonic revealed frontier before user-visible reveal, exact source ordinal/timestamp group, atomic finance/cursor commit; compact replaceable no-trade progress (target ~30 wall-clock seconds between checkpoints) but no replay to a previously seen trading opportunity after crash. Avoid one immutable no-financial-event record per tiny advance. Old Session formats continue to read through original validators.

**Done when:** no per-group position/advance log or per-user source duplicate is produced by newly created replay Sessions, the user cannot trade behind a previously revealed frontier, and resumed state/receipt/order outcome match their authoritative commit.

### C. User, trade and Session persistence — P0
**Existing code:** \`backend/execution/observed_postgres.py\`; \`backend/execution/postgres.py\`; \`backend/execution/observed_kernel.py\`; \`backend/execution/observed_order_archive_v1.py\`; \`backend/execution/observed_state_delta_v3.py\`; \`backend/execution/session_storage_metrics.py\`.

**Gap:** default Session storage is \`snapshot-v1\`; \`compact-v1\` is gated to new Sessions. Normal observed Session has **128 cumulative lifetime orders**; terminal archive is QA-only. Cold compact reconstruction scans deltas since genesis.

**Deliverable:** production-versioned compact storage for new Sessions, compatible legacy read, append-only financial event truth, active order hot-state only, versioned committed closed-order archive/read model, indexed paginated history and periodic verified compact recovery base to bound reconstruction. Keep exact idempotent retry and immutable record semantics, protect financial history and money.

**Done when:** a long-lived Session is not blocked after 128 lifetime completed orders, previous fills still reconcile, cold recovery reads a bounded tail rather than all revisions, and physical per-trade/Session disk accounting can detect growth including indexes/TOAST/WAL separately.

### D. Analytical projections, journal and catalog scaling — P1 before public V1
**Existing code:** \`backend/execution/observed_analysis.py\`; \`backend/execution/observed_research.py\`; \`backend/execution/product_read_model.py\`; \`backend/execution/product_method_lifecycle.py\`; \`frontend/src/tickAlpha/client.js\`.

**Gap:** event folding in memory can rebuild long histories, observed \`_complete_statistics\` assembles all trade pages, Method analytics has 4,096-event limit for the candidate, catalog versions consume a 128-record lifetime budget, and hosted frontend refuses >128 loaded records even though some server pages exist. The journal full route remains bounded; cursor pages exist.

**Deliverable:** revision-pinned incremental persistent Session/Method aggregates, bounded equity samples, keyset page for trade/journal/Method/Session without hard 128 lifetime rows or full collection in browser memory. Preserve compatibility/unit restrictions when pooling results; never compute settlement from chart candles.

**Done when:** one newly committed trade updates derived statistics without replaying the entire previous ledger for every page request, stable page navigation works past 128 historical Methods/Sessions/orders, and aggregates can be rebuilt/verified against events.

### E. Worker fairness, quotas and predictable costs — P1 before public V1
**Existing code:** \`backend/cloud/queue.py\`; \`backend/cloud/worker.py\`; \`backend/cloud/research.py\`.

**Gap:** current global queue=16, per-user queue=2, worker slots=1, job deadline=30s and queued TTL=60s; initial one-day heavy replay consumed about one core, but no integrated concurrence/cost entitlement exists. Durable queue correctness is implemented.

**Deliverable:** keep PostgreSQL queue; separate interactive short work vs resumable heavy job service levels, per-actor fairness and server-side quotas; bounded memory, CPU, result size, queue age and storage retention; reliable job reconciliation before pruning operational rows. No Redis/Kafka/Kubernetes. Split long replay work into bounded resumable units; avoid promises of N heavy users without measurement.

**Done when:** client can pause/cancel/resume, uncertainty and timeout do not duplicate financial commands, one slow research job cannot starve every short interaction indefinitely, and the system exposes measured time/CPU/RSS/disk metrics for final acceptance.

### F. Auth, product UI, source rights and operations — P0 for account correctness, P1 for launch
**Existing code:** \`frontend/src/tickAlpha/*\`; \`frontend/src/trading/useTrading.js\`; \`backend/identity/google_store.py\`; \`backend/cloud/app.py\`; \`deploy/vps/compose.yaml\`; \`docs/SECURITY_ARCHITECTURE.md\`.

**Gap:** integrated product UI exists, but account-linking contract is not implemented, Google conflict does not auto-link; browser journey not fully verified. A legacy browser-local simulator persists in the repo and must not be another authoritative hosted financial engine. Object storage, off-host backup restore, quotas, commercial rights and real provider config require integration.

**Deliverable:** hosted frontend uses backend as the only financial authority; safe explicit Google/password account linking tied to existing \`users.id\`, no merge solely by matching email; source rights and entitlement fail-closed; one real authorized-session journey through chart, Method, order, receipt, journal and analytics; version-pinned deployment on isolated staging and controlled production approval; server quota/retention/backup restore drill.

**Done when:** an actual hosted browser account round-trip preserves the same user/workspace/trades, no duplicate financial authority is active, source/entitlement gates are enforced, and recovery from off-host backup is tested without touching production data.

## Mandatory evidence / no speculative benchmarks while building

**During implementation:** only syntax, lint/build, targeted unit/integration and transaction/no-look-ahead regressions necessary for the changed slice; use dedicated safe QA resources. No unapproved annual replay or broad load tests, no production/Annual PASS artifact deletion. Do not stall all product coding because a historical oversized annual QA gate cannot fit on a small host; document its actual scope as a **release gate** to run after integration, without claiming it passed.

**After integrated end-to-end Product V1:** one approved final acceptance plan with source license/rights, provider equivalence, financial parity, crash-at-commit + no double fill, no-look-ahead across crash, full-year user-attributed persistent disk and per-trade physical allocation, PG WAL/index/TOAST, shared source bytes, worker CPU/RSS, mixed interactive/heavy concurrency, queue health, security/tenant isolation, browser + mobile, off-host restore, cost/usage accounting and deployment rollback. Optimize only measured bottlenecks.

**No invented target pass:** ~16 KiB/trade, >32 KiB/trade review and <=10 MiB no-trade annual progress remain target budgets pending measured physical data. CPU ~1 core/heavy job is *observed in one existing gate*, not a concurrency guarantee.

## Safe merge / owner decision

Merge this freeze into the Product V1 integration branch only after comparing against current Codex/Claude changes and resolving actual conflicts without discarding either party's work. This register grants no authority to run destructive cleanup, change protected evidence, deploy, or bypass source licensing. The single source of architecture authority remains the existing Product System Architecture Blueprint.
