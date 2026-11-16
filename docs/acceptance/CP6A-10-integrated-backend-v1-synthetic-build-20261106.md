# RIKSORA Backend V1 — Synthetic Integration Build Review

Date: 2026-11-06  
Branch: `codex/integrated-backend-v1-20261106`  
Code verification commit: `5bf91f7` (`test: exercise monthly parquet through API worker lifecycle`)  
Evidence/report branch tip before this document: `475707f`

## Executive result

**SYNTHETIC_BACKEND_BUILD: PASS.** The core backend components are connected and have light correctness regressions. A real FastAPI lifespan worker consumed Session creation and replay work against a server-pinned, temporary synthetic Monthly Parquet source and completed the authenticated Review → Confirm → durable receipt → Journal → summary → metering path. Queue idempotency and worker cleanup were also verified.

This is an engineering build checkpoint, not production, source-rights, historical-data, concurrency-capacity, commercial, or final performance acceptance. Heavy replay, benchmark, profiling, concurrency, and economics work remains deferred to final acceptance.

## Component matrix

| Component | Build status | Evidence and limits |
| --- | --- | --- |
| Immutable Monthly Parquet, versioned manifest, canonical identity and bounded range reads | PASS for synthetic QA | `backend/tests/test_monthly_parquet.py`; 9/9 current tests. Manifest/source/row-group hash refusal, immutable publication, stable event identity/order and `TickTimeline` page parity. No historical source admission. |
| Proof-gated Arrow/NumPy scanner | PASS for correctness | `backend/tests/test_next_event_scanner.py`; 7/7 current tests. Candidate selection matches chronological fallback and all authored financial goldens. It remains a hint; deterministic reducer stays authoritative. Performance benefit was not measured. |
| PostgreSQL queue, fairness, lease/heartbeat, bounded one-worker service lifecycle, recovery and idempotency | PASS for synthetic functional behavior | `backend/tests/test_research_queue.py`; 18/18 on temporary PostgreSQL 16, including actual API lifespan processing, two-tenant shared-source integration, cancellation/fencing, process-death recovery and durable receipt recovery. `backend/tests/test_worker_deadline.py`; 17/17. Not a multiworker/capacity result or reboot-supervision proof. |
| Compact/recoverable Session storage and read models | PASS for authored QA | `backend/tests/test_compact_storage.py` and `backend/tests/test_tick_journal.py` are included in a combined 38/38 PostgreSQL run. Cold recovery, hash/state parity, idempotency and revision-pinned Journal pagination passed. No production storage-format selection or physical savings claim. |
| Hosted auth, authorization and Session isolation | PASS for fixture-backed flows | Password registration/verification/login and isolated workspace/Session flows pass in the 50/100 synthetic cohort journeys. Google OIDC state/PKCE/subject isolation tests use signed fixtures and mocked provider traffic; live Google credentials and SMTP were not exercised. |
| Metering | PASS for bounded instrumentation behavior | Per-job worker CPU/wall/RSS/I/O, first-claim queue wait, database/WAL snapshots and logical per-Session storage reports have regression coverage. Per-Session physical bytes and per-job WAL remain explicitly unavailable; logical storage values are not physical allocation. |
| Virtual trader generator and sequential journeys | PASS for functional workflow | Deterministic isolated cohorts for 1, 5, 10, 25, 50 and 100 users. The 50-user journey took 204.514 s; 100-user journey 408.715 s. These are sequential request journeys, not concurrent load or user-capacity measurements. See [cohort evidence](CP6A-10-virtual-trader-functional-cohorts-20261106.md). |
| End-to-end synthetic service pipeline | PASS | `QueueTests.test_api_lifespan_worker_executes_pinned_monthly_parquet_pipeline`; 1/1, 22.345 s on a temporary PostgreSQL 16 cluster. Session creation and ADVANCE were queued over the actual API lifespan worker; Confirm retry returned identical bytes; durable receipt, Journal, summary and storage meter were checked. Cluster stopped and removed. |

The 21-test unit group `test_monthly_parquet`, `test_next_event_scanner`, and `test_virtual_traders` also passed 21/21 in 0.921 s. The combined PostgreSQL group `test_compact_storage`, `test_tick_journal`, `test_session_storage_metrics`, `test_google_identity`, and `test_p0_local_integration` passed 38/38 in 21.094 s on a separate temporary PostgreSQL 16 cluster.

## Preserved authority and restrictions

- The deterministic execution reducer, receipt authority, canonical event identity, source order, and financial contracts were not changed by this integration checkpoint.
- Only generated synthetic source data was used by the new integrated API-lifespan path.
- Historical source rights remain `UNKNOWN`; historical execution eligibility remains `NOT_GRANTED`. No public/historical source is exposed through this QA configuration.
- CP6A-10 Annual PASS and CP6A-8 evidence remain protected. PR #41 evidence and its separate branch were not modified or merged by this checkpoint.
- No production service, database, worker configuration, or deployment was changed.

## Deferred final-acceptance gates

1. Validate source rights/provenance and obtain an authorized historical source before any historical-data product path.
2. Run the approved integrated performance and resource acceptance on an eligible, resource-qualified environment; measure scanner benefit rather than infer it.
3. Test concurrent worker scaling and queue latency only under a separate final-acceptance resource gate.
4. Complete long-window resource/economic measurements; retain `NOT_MEASURED` where PostgreSQL/WAL or per-Session physical attribution is unavailable.
5. Verify any live hosted identity provider/SMTP configuration and production recovery separately, without changing production in this build checkpoint.

## Status

`BUILD_PASS_PENDING_FINAL_ACCEPTANCE`  
Heavy benchmark/load, historical rights, live provider, production deployment and commercial-readiness claims remain out of scope and unpassed.
