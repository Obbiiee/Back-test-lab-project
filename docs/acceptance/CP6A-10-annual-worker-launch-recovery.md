# CP6A-10 Annual Worker Launch and Recovery

**Status:** worker-launch fix and checkpoint recovery validated; annual replay is ready to resume but has not yet restarted.

## Root cause

The failed cold-resume call in `backend/tests/qa_historical_day_v2.py` passed the complete worker payload in the environment variable `BTL_HISTORICAL_DAY_V2_WORKER`. Reconstructing that payload from the preserved annual `replay-config.json` measured 8,784 decision targets and a 281,706-byte environment value. The subprocess argument vector was 85 bytes and the total environment was 286,141 bytes, below `SC_ARG_MAX` of 2,097,152 bytes. Linux's per-string limit was 131,072 bytes. Passing the measured payload to a bounded `/bin/true` launch reproduced `OSError: [Errno 7] E2BIG`.

## Fix

The parent now writes structured worker state to `year/cold-resume-worker.json` with mode `0600`, a 4 MiB maximum, atomic no-overwrite creation, and a SHA-256 digest. The child receives only the file path and digest in its environment. It checks path containment, ownership, permissions, size, payload shape, and digest before reading state. Annual resume validates the existing replay configuration and Session checkpoint, starts the preserved cleanly shut down PostgreSQL cluster without initialization or migration, verifies the durable receipt ledger and checkpoint chain, retries the known opening command idempotently, and confirms that event and fill counts do not change before continuing the same Session.

Financial semantics, market source identity, annual decision schedule, cumulative order limit, rights classification, and execution eligibility are unchanged.

## Validation

- Launcher regression: **2/2 PASS**, including exact bounded `E2BIG` reproduction and successful child startup with an 8,784-target file payload; altered payload digest is rejected.
- Annual schedule regression: **3/3 PASS**.
- PostgreSQL, financial-kernel, recovery, and delta-v3 scale regressions: **60/60 PASS** under 1 CPU, 1 GiB RAM, zero swap, and single-core affinity. The scale report confirms cold resume, exact retry, post-commit SIGKILL recovery, independent delta reconstruction, receipt and event-chain verification, and rejection of missing, reordered, and corrupted deltas.
- Existing annual checkpoint reopened and independently verified without advancing or changing it: **PASS**. Revision 548, group index 137708, 548 command receipts and 549 checkpoints; 557 events, 7 entry fills and 7 exit fills before and after the idempotent retry. State event hash and checkpoint chain hash were verified.
- Existing week and month reports and annual resource preflight remain **PASS**. The annual replay itself is still incomplete and is not yet a PASS.

## Evidence

- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resume-regressions/targeted-postgres-finance-recovery.log`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resume-regressions/delta-v3-scale-report.json`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resume-regressions/resume-checkpoint-preflight.json`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resource-preflight.json`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/stage-runner-report.json` (original stop record retained)

Source rights remain **UNKNOWN** and execution eligibility remains **NOT_GRANTED**. No production system or canonical source was modified.
