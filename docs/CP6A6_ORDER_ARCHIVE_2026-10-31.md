# CP6A-6B — Complete Archive Integration

**Status: PASS for the isolated QA archive architecture and 1,024-order structural acceptance.** This is authored QA storage-stress evidence, not a market-data trading benchmark or production approval.

## PostgreSQL environment recovered

The original test failure used the system `python3`, which did not have `psycopg`. The established `/tmp/riksora-vps-candidate-venv/bin/python` has the required package. The shell did not have `BTL_TEST_DATABASE_URL`; the existing `deploy/vps/tests/run_private_pg.py::private_postgres` helper creates a new PostgreSQL 16 Unix-socket-only cluster and private DSN. The cluster was freshly created for each independent bounded integration/regression run; the scale run used its retained private QA cluster across stopped/restarted stages. No production DSN was supplied or used.

## Integration and regression results

The PostgreSQL integration PASS covers a real kernel STOP order entry and TP exit, parity with the legacy reducer's events and balances, atomic commit/rollback, SIGKILL after commit and identical retry, cold recovery, and independent archive/event/receipt verification. Missing, reordered, and corrupted archive rows are rejected. A second real kernel flow archives `EXPIRED` pending and `UNRESOLVED` open-order outcomes and cold-recovers them. The active order 129 refusal is separately verified without state mutation.

The focused regression command passed **28 tests**:

```text
private_postgres + /tmp/riksora-vps-candidate-venv/bin/python -B -m unittest \
  tests.test_observed_kernel tests.test_observed_order_archive_v1 \
  tests.test_observed_postgres.ObservedPostgresTests.test_qa_order_archive_v1_integrates_kernel_postgres_recovery_and_ledger -v
```

## Staged PostgreSQL scale results

Each stage resumed the same isolated database/session. The fixture repeatedly opened and cancelled authored QA orders. It therefore verifies archive growth, durable history, recovery, and event/receipt chains; it does **not** demonstrate thousands of executed fills. A separate bounded financial integration test verifies the filled STOP→TP lifecycle against the legacy implementation.

| Cumulative terminal orders | Hot state bytes / canonical nodes | Archive rows / allocated tuple bytes | DB bytes | Median / p95 cancel apply | Cold resume | Elapsed / CPU | Peak sampled RSS | QA artifacts | Disk free |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 128 | 2,578 / 81 | 128 / 139,741 | 11,262,999 | 48.9 / 57.0 ms | 0.59 s | 18.3 / 11.9 s | 777,908,224 B | 47,751,168 B | 51,498,975,232 B |
| 512 | 2,580 / 81 | 512 / 559,466 | 16,645,143 | 48.9 / 58.6 ms | 2.28 s | 56.7 / 35.0 s | 777,883,648 B | 75,427,840 B | 51,470,966,784 B |
| 800 | 2,580 / 81 | 800 / 874,538 | 20,691,991 | 47.2 / 56.8 ms | 3.67 s | 52.4 / 36.2 s | 778,010,624 B | 79,495,168 B | 51,466,842,112 B |
| 1,024 | 2,581 / 81 | 1,024 / 1,119,618 | 23,845,911 | 47.7 / 55.4 ms | 4.42 s | 77.0 / 60.2 s | 777,105,408 B | 83,927,040 B | 51,462,234,112 B |

All stages passed within the 1 GiB RSS cap, 512 MiB allocated-artifact cap, 3,600-second per-stage cap, and 30 GiB free-disk reserve. The active-order cap remains 128; active order 129 was rejected without a persisted command. At 1,024 cumulative orders the hot financial state remained 81 canonical nodes, and all 1,024 terminal order records remained queryable and independently verifiable.

Raw stage reports: [128](CP6A6B_ORDER_ARCHIVE_SCALE_128_2026-10-31.json), [512](CP6A6B_ORDER_ARCHIVE_SCALE_512_2026-10-31.json), [800](CP6A6B_ORDER_ARCHIVE_SCALE_800_2026-10-31.json), [1,024](CP6A6B_ORDER_ARCHIVE_SCALE_1024_2026-10-31.json). Consolidated evidence is in [CP6A6B_ORDER_ARCHIVE_2026-10-31.json](CP6A6B_ORDER_ARCHIVE_2026-10-31.json). Raw private PG workspaces remain under `/tmp/riksora-cp6a6b-scale-20261031-r2`; the first aborted runner attempt is preserved separately under `/tmp/riksora-cp6a6b-scale-20261031` and is excluded from acceptance.

## Scope and limits

- QA-only state format `BTL-OBSERVED-EXECUTION-STATE-QA-ORDER-ARCHIVE-1`; QA archive table enabled only by explicit isolated configuration.
- Legacy QA-v3 read behavior and production paths were unchanged.
- H1/H2/H3, production databases, and canonical market data were not accessed or modified.
- The scale fixture had zero fills and zero financial P&L events. Do not interpret it as evidence for 2,000 actual completed trades, one-week/year performance, or production readiness.
- The monthly replay runner and all pre-existing local changes remain preserved.

No source dataset or market archive was committed. The accepted commit hash and push verification are reported in the completion message.
