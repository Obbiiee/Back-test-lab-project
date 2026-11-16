# CP6A-10 Annual Worker Launch and Recovery

**Status:** launcher and schedule regressions PASS; annual resume attempt 3 is authorized from the verified checkpoint.

## Root cause

The failed cold-resume call in `backend/tests/qa_historical_day_v2.py` passed the complete worker payload in the environment variable `BTL_HISTORICAL_DAY_V2_WORKER`. Reconstructing that payload from the preserved annual `replay-config.json` measured 8,784 decision targets and a 281,706-byte environment value. The subprocess argument vector was 85 bytes and the total environment was 286,141 bytes, below `SC_ARG_MAX` of 2,097,152 bytes. Linux's per-string limit was 131,072 bytes. Passing the measured payload to a bounded `/bin/true` launch reproduced `OSError: [Errno 7] E2BIG`.

## Fix

The parent now writes structured worker state to `year/cold-resume-worker.json` with mode `0600`, a 4 MiB maximum, atomic no-overwrite creation, and a SHA-256 digest. The child receives only the file path and digest in its environment. It checks path containment, ownership, permissions, size, payload shape, and digest before reading state. Annual resume validates the existing replay configuration and Session checkpoint, starts the preserved cleanly shut down PostgreSQL cluster without initialization or migration, verifies the durable receipt ledger and checkpoint chain, retries the known opening command idempotently, and confirms that event and fill counts do not change before continuing the same Session.

Financial semantics, market source identity, annual decision schedule, cumulative order limit, rights classification, and execution eligibility are unchanged.

The first guarded resume attempt stopped before creating the worker payload because the added retry assertion compared the opening command response's embedded snapshot revision (`1`) with the annual Session revision (`548`). A direct repeat against the existing database proved both retry responses identical, the Session revision unchanged, the event/fill counts unchanged, and the receipt/checkpoint chains valid. The guard now compares the Session revision and event/fill counts for mutation, while identical retry receipts establish idempotency. No annual progress or finance state was changed by the failed attempt. Resume attempt evidence is isolated under `annual-resume-attempt-2/`.

Resume attempt 2 passed the checkpoint identity, hash chain, receipt ledger, and idempotent retry checks, then stopped while assembling the worker payload because the optional partial-probe state was only initialized on fresh runs. The Session remained at revision 548/group 137708. The state is now initialized for both fresh and resumed runs, and each resume writes checkpoint verification to a per-attempt file so prior evidence remains intact.

## Validation

- Launcher regression: **2/2 PASS**, including exact bounded `E2BIG` reproduction and successful child startup with an 8,784-target file payload; altered payload digest is rejected.
- Annual schedule regression: **3/3 PASS**.
- PostgreSQL, financial-kernel, recovery, and delta-v3 scale regressions: **60/60 PASS** under 1 CPU, 1 GiB RAM, zero swap, and single-core affinity. The scale report confirms cold resume, exact retry, post-commit SIGKILL recovery, independent delta reconstruction, receipt and event-chain verification, and rejection of missing, reordered, and corrupted deltas.
- Existing annual checkpoint reopened and independently verified without advancing or changing it: **PASS**. Revision 548, group index 137708, 548 command receipts and 549 checkpoints; 557 events, 7 entry fills and 7 exit fills before and after the idempotent retry. State event hash and checkpoint chain hash were verified.
- The first two resume attempts stopped before the worker could advance any annual data. Both reports/logs and attempt 2's checkpoint verification are preserved. Corrected launcher, retry, and payload gates pass; the third run will use the persistent annual-resume systemd service.
- Existing week and month reports and annual resource preflight remain **PASS**. The annual replay itself is still incomplete and is not yet a PASS.

## Evidence

- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resume-regressions/targeted-postgres-finance-recovery.log`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resume-regressions/targeted-postgres-finance-recovery-fix2.log`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resume-regressions/resume-checkpoint-diagnostic-attempt1.json`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/year/resume-checkpoint-verification-attempt-2.json`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resume-regressions/delta-v3-scale-report.json`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resume-regressions/resume-checkpoint-preflight.json`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/annual-resource-preflight.json`
- `/home/riksora/riksora-qa-evidence/cp6a10-shared-source-stages-20261101/stage-runner-report.json` (original stop record retained)

Source rights remain **UNKNOWN** and execution eligibility remains **NOT_GRANTED**. No production system or canonical source was modified.
