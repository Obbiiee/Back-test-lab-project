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

## Interpretation and limits

- These passes complete the sequential functional cohort sizes 1, 5, 10, 25, 50 and 100 when combined with the earlier results recorded in `AI_CONTEXT/04_CURRENT_PHASE.md`.
- They do not demonstrate 50 or 100 simultaneous users, worker scaling, queue capacity, latency percentiles, financial-result correctness for historical data, production readiness, or per-user infrastructure economics.
- No annual replay, benchmark, concurrency test, production mutation, or evidence cleanup was performed.
- Source rights remain `UNKNOWN`; historical execution eligibility remains `NOT_GRANTED`.
