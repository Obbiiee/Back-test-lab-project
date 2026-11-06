# CP6A-10 Virtual Trader Functional Cohorts — 2026-11-06

## Scope

Sequential synthetic functional journeys for the existing 50-user and 100-user cohort sizes. These are not concurrent load, throughput, or capacity tests. No historical dataset was read, and no financial/source-rights classification was changed.

## Environment

- Host: `VM-a3efa1db-4da0-49f3-80e9-3fa49c06ed62` (KVM VPS)
- Repository branch and source revision: `codex/integrated-backend-v1-20261106` at `707471d0fc735cdc054c9ad590373dd80bed93ca`
- Runner: `backend/tests/run_virtual_trader_cohort.py`
- QA database: runner-owned temporary PostgreSQL 16 cluster; stopped and removed after each run
- Execution mode: `SEQUENTIAL_FUNCTIONAL_JOURNEY`
- Worker concurrency: `NOT_EXERCISED`
- Capacity status: `NOT_MEASURED`

## Resource preflight

Immediately before the 50-user run, `/proc/meminfo` reported 4,837,716 KiB `MemAvailable`; swap was disabled; `/tmp` had 36,917,608,448 bytes free. The 100-user run began after the 50-user QA cluster had been removed. Its fresh preflight reported 4,838,016 KiB `MemAvailable`, swap disabled, and the same 36,917,608,448 bytes free. No other virtual-trader runner, pytest process, or matching temporary PostgreSQL QA cluster was active at those checks.

These are host snapshots, not per-test peak memory or I/O measurements. This checkpoint does not qualify benchmark preflight or concurrency capacity.

## Results

| Cohort | Result | Test body duration | Run ID | Cluster cleanup |
| ---: | --- | ---: | --- | --- |
| 50 | PASS | 204.514 s | `44cf03c7-cd4b-4afe-aed0-ad3a046a0a3e` | `EXCLUSIVE_QA_STOPPED; OWN_FIXTURES_REMOVED` |
| 100 | PASS | 408.715 s | `417a953b-edea-425b-b887-95fcb677e9b0` | `EXCLUSIVE_QA_STOPPED; OWN_FIXTURES_REMOVED` |

Both runs executed `test_virtual_traders_complete_isolated_authenticated_journey`. The test provisions synthetic accounts, isolated workspaces and Sessions, performs Review → Confirm → duplicate Confirm → durable receipt lookup → Journal and storage-meter checks, then tests tenant isolation. Cohorts larger than five use the test's bounded ring-sampled foreign-Session checks; every trader receives an own-Session read and each sampled cross-tenant Session and storage-meter read is refused.

The runner output classified both results as `BTL-VIRTUAL-TRADER-FUNCTIONAL-COHORT-RESULT-1`, `status=PASS`, `executionMode=SEQUENTIAL_FUNCTIONAL_JOURNEY`, `workerConcurrency=NOT_EXERCISED`, and `capacityStatus=NOT_MEASURED`.

## API-lifespan worker regression

The previous Monthly Parquet integration test drove `queue.work_one()` directly. To verify the product service lifecycle, `backend/tests/test_research_queue.py` now also submits one synthetic read job through the authenticated API while its real FastAPI lifespan is active. The test waits for the background one-worker pump to complete the durable job, resubmits the exact job ID and payload and checks the identical result, then verifies the native child process was reaped when the lifespan closed.

- `QueueTests.test_api_lifespan_worker_consumes_and_deduplicates_durable_job`: 1/1 PASS, 5.064 s, isolated temporary PostgreSQL 16 cluster stopped and removed.
- `tests.test_worker_deadline`: 17/17 PASS, 4.788 s.

This verifies the synthetic in-process API worker lifecycle and bounded child cleanup. It does not prove service supervision across VPS reboot, live deployment behavior, or production queue capacity.

## Shared Monthly Parquet through API lifespan

`QueueTests.test_api_lifespan_worker_executes_pinned_monthly_parquet_pipeline` now exercises the complete synthetic shared-source path with the actual FastAPI lifespan worker, rather than manually calling the queue pump. The test pins a temporary immutable Monthly Parquet manifest in server-side QA configuration, queues Session creation and an ADVANCE through authenticated API routes, and verifies Review → Confirm → durable receipt lookup → Journal → summary → storage meter. It resubmits Session creation with the exact same job ID and payload and receives the identical durable result.

- Result: 1/1 PASS, 22.345 s.
- PostgreSQL: temporary exclusive PostgreSQL 16 cluster stopped and removed after the run.
- Source: generated synthetic fixture only; no historical or externally licensed source.
- Worker count: one lifespan worker; no concurrent load or capacity test.
- Compact storage: enabled by server-pinned `BTL_TICK_SESSION_STORAGE_FORMAT=compact-v1` for this QA-created Session only.

The full `tests.test_research_queue` PostgreSQL suite was then rerun on its own temporary PostgreSQL 16 cluster and passed 18/18 in 104.567 s. This includes worker lease/heartbeat and cancellation, actor fairness, bounded admission, process-death recovery, replay receipt idempotency, both two-tenant and actual-lifespan Monthly Parquet journeys, and the new source-pinned lifespan journey. The cluster was stopped and removed. `tests.test_worker_deadline` separately passed 17/17 in 4.788 s.

The following PostgreSQL-backed component regressions then passed together, 38/38 in 21.094 s on a separate temporary PostgreSQL 16 cluster: compact/recovery storage, canonical Journal cursor pagination, bounded per-Session storage metering, Google identity and workspace authorization fixtures, and the P0 availability/receipt-confirm integration. The Google OIDC tests use signed/authored fixtures and mocked provider traffic; they do not prove live Google credentials, SMTP delivery, or hosted-provider operations. The cluster was stopped and removed.

This demonstrates a connected synthetic service path. It does not prove historical source eligibility, source rights, production deployment, VPS reboot recovery, or concurrency capacity.

## Interpretation and limits

- These passes complete the sequential functional cohort sizes 1, 5, 10, 25, 50 and 100 when combined with the earlier results recorded in `AI_CONTEXT/04_CURRENT_PHASE.md`.
- They do not demonstrate 50 or 100 simultaneous users, worker scaling, queue capacity, latency percentiles, financial-result correctness for historical data, production readiness, or per-user infrastructure economics.
- No annual replay, benchmark, concurrency test, production mutation, or evidence cleanup was performed.
- Source rights remain `UNKNOWN`; historical execution eligibility remains `NOT_GRANTED`.
