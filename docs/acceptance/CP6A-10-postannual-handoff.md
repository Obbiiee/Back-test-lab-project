# CP6A-10 Post-Annual Persistent Handoff

## Installed behavior

The user-systemd timer polls the annual resume unit once per minute with a separate low-resource oneshot service. The timer is independent of SSH, the laptop, and interactive Codex. It only reads annual service state and evidence while the annual unit is active. A lock file prevents concurrent supervisors. Atomic status JSON, a human-readable status file, and fsynced logs are retained under the postannual evidence root.

The annual gate requires `systemd Result=success` **and** the annual resume handoff report plus annual replay report to pass explicit checks for all 56,208,511 groups, 366 days, canonical source ID and SHA-256, independent financial reconciliation, receipt ledger hash/count, event hash, cold recovery, idempotency, and unchanged `UNKNOWN`/`NOT_GRANTED` classifications. A service exit code alone cannot advance the state machine.

The tested state machine advances 10 → 50 → 100 sequentially only when each stage writes a report with passing source identity, session isolation, financial/event integrity, cold recovery, zero failed requests, measured CPU/RAM/database contention/storage/latency, and approved resource limits. Stage reports are revalidated on restart so state JSON alone cannot skip a stage. A measured unit-economics artifact is then built from annual and load reports, with no invented VPS bill and no profitability claim. The terminal state is `COMPLETE_PENDING_OWNER_REVIEW`.

## Current limitation

No tested RIKSORA multi-user shared-canonical-source load-stage executable exists in this checkout. The installed supervisor therefore omits `--load-runner`; after a genuinely verified annual PASS it will persist `STOPPED_NEEDS_OWNER` at the 10-user preflight and disarm its timer. It will not repurpose the existing 10-session in-process research probe, which does not test shared market-source behavior. The synthetic supervisor fixture uses temporary fake PASS reports and a mock stage runner only; it does not alter or certify the live annual Session.

Thus unattended annual detection and PASS verification are installed; actual 10/50/100 load execution and derived economics are not yet authorized for automatic launch until the required shared-source load runner is implemented and regression-tested.

## Synthetic verification

`tests.test_qa_postannual_supervisor` verifies: an active annual service waits without starting load; a failed annual service stops; a successful service without full annual PASS stops; synthetic complete PASS evidence triggers exactly 10 → 50 → 100; duplicate polling does not repeat completed stages; a failed load report prevents escalation; and the lock refuses a second supervisor.

The synthetic annual PASS fixtures exist only in temporary test directories and are not copied to the live annual evidence area.
