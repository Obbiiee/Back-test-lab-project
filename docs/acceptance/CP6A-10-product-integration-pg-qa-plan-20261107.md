# CP6A-10 Product Integration — Isolated PostgreSQL QA Plan

Date: 2026-11-07
Status: PREPARED — NOT EXECUTED
Owner access to any second QA VPS: not requested or used.

## Required environment

- PostgreSQL 16. This matches the existing native QA harness and previously accepted CP6A-10 PostgreSQL test runs. The harness expects binaries at /usr/lib/postgresql/16/bin/{initdb,pg_ctl,pg_dump,pg_restore}.
- Ordinary unprivileged Linux account; the harness refuses root and does not use sudo or system PostgreSQL services.
- Python 3.12 with all 40 exact versions in backend/requirements.lock.
- Repository test dependencies include psycopg 3.3.6 plus the pinned FastAPI, httpx, AnyIO, and application dependencies. The PostgreSQL queue test creates its own isolated database inside the private test cluster.
- PostgreSQL must support local Unix sockets and an unused temporary socket path/port. The existing harness disables TCP listening, uses port 55439 on its private socket, UTF-8, SCRAM test credentials, shared_buffers=32MB, and max_connections=50.

The isolated Python environment created for this checkpoint is:

/tmp/riksora-product-v1-qa-venv-20261107

It uses Python 3.12.3. pip check passed, and comparison against the repository lock found all 40 entries at their exact pinned versions. Environment size at measurement was 322,751,033 bytes. It is not a production environment and is retained for this QA continuation.

## Synthetic fixture and resource budget

The canonical in-repository research fixture contains 2,048 authored synthetic tick events, delivered as 32 pages of 64. The canonical serialized events total 1,666,488 bytes (about 1.59 MiB). No historical dataset, Annual PASS artifact, source credential, or production evidence is used. The queue tests generate temporary Monthly Parquet from this fixture using TemporaryDirectory; the compressed Parquet byte size for this exact run has not been measured.

Prior references, not measurements of this candidate run:

- Existing CP6A-7 private PostgreSQL cluster allocation: about 76.1 MB.
- Existing 18-test queue suite on PostgreSQL 16: 104.567 seconds.

For planning only, reserve at most 1 GiB of incremental disk for the complete private cluster, temporary Parquet, and logs; this is a conservative operational budget, not a measured test result. Stop before the disk reserve falls below 30 GiB. Do not start unless the unchanged host gate is satisfied: at least 36 GiB free disk and 10 GiB MemAvailable, swap 0. If the run must preserve those gate figures throughout the test, preflight at ≥37 GiB free and ≥12 GiB MemAvailable to accommodate the planning budget.

Peak RAM for this exact combined suite is not measured. The private runner configures PostgreSQL shared buffers to 32 MB, but that does not bound total process memory. When later authorized and resource-eligible, place the runner and all descendants in one measured cgroup, plan a maximum 1 CPU and 2 GiB aggregate MemoryMax, and stop on OOM or if MemAvailable falls below the unchanged 10 GiB gate. If those limits cannot be enforced or measured, do not run the PostgreSQL gate. Expected total duration is below the runner's 900-second per-module timeout based on prior queue-suite timing, but the new combined suite duration remains NOT MEASURED.

## Tests covered by the prepared run

The isolated sequence is:

1. tests.test_research_queue_contract — legacy/observed dialect selection, wrong/unknown dialect refusal, and hash-verified persisted Session metadata helper.
2. tests.test_method_analytics_projection — aggregation/unit cases for wins, losses, breakeven, incompatible units, incomplete analytics, and event-budget refusal. This module is non-DB.
3. tests.test_cloud_research — migration checksum rerun, immutable Method versions, real concurrent CAS, Session pinning, exact retries, archive/restore, owner/member authorization, revocation, and committed-event analytics from three Sessions with synthetic win/loss/breakeven outcomes.
4. tests.test_research_queue — isolated PostgreSQL queue admission, persisted Session dialect enforcement, retry/idempotency, worker lifecycle, cancellation/reconciliation, process recovery, tenant authorization, and synthetic queue/replay journeys.

The database-backed analytics case creates only authored Session commands and quotes, then compares the API's committed-event analytics to each Session's independently projected committed trades. It does not insert fabricated ledger or receipt rows.

## Command to execute later on an authorized, eligible QA host

First create and verify a virtual environment against the repository lock:

    python3 -m venv /tmp/riksora-product-v1-qa-venv
    /tmp/riksora-product-v1-qa-venv/bin/python -m pip install -r backend/requirements.lock
    /tmp/riksora-product-v1-qa-venv/bin/python -m pip check

Confirm all resource gates and PostgreSQL 16 binaries before starting. Then, from the repository root, run the existing private harness and serial unittest modules:

    PYTHONPATH=backend /tmp/riksora-product-v1-qa-venv/bin/python - <<'PY'
    import subprocess
    import sys
    from deploy.vps.tests.run_private_pg import private_postgres

    modules = (
        "tests.test_research_queue_contract",
        "tests.test_method_analytics_projection",
        "tests.test_cloud_research",
        "tests.test_research_queue",
    )
    with private_postgres() as (repository, environment):
        for module in modules:
            subprocess.run(
                [sys.executable, "-B", "-m", "unittest", module, "-v"],
                cwd=repository, env=environment, check=True, timeout=900,
            )
    PY

The wrapper's private_postgres() creates a unique mode-0700 QA root, generates an ephemeral mode-0600 test password, uses a private Unix socket with TCP disabled, and supplies only its own ephemeral DSN to child tests. The queue suite creates a separate database inside that cluster. No external DSN is accepted.

## Cleanup and evidence

Do not run cleanup commands manually. On normal exit the existing context manager stops its own PostgreSQL server and removes only its own uniquely created temporary root. The test-owned TemporaryDirectory removes only its own generated Parquet fixture. Do not use --keep, rm, git clean, or a system PostgreSQL database for the acceptance run. If the runner is interrupted and leaves a cluster, preserve it and inspect its exact PID, path, and ownership before any recovery or cleanup.

The eventual acceptance report should record the exact host and PostgreSQL version, lock verification, start/end disk and MemAvailable, cgroup CPU/RAM peaks, private cluster allocated bytes, temporary Parquet bytes, test names/counts/durations, and cleanup result. A skipped test is not PASS.

## Current gate and next action

At the latest measured preflight on this working host: free disk was 36,131,262,464 bytes (33.65 GiB), MemAvailable was 4,707,896 kB (about 4.49 GiB), and swap was 0. Disk and RAM remain below the unchanged 36 GiB / 10 GiB requirements. Do not run the PostgreSQL sequence here.

The owner explicitly asked that the second QA VPS not be accessed or configured before authorization. It remains untouched. The safe next action is for the owner to authorize that host and provide an isolated account/path, after which its resource and binary preflight must be independently measured before running this plan.

Browser acceptance remains downstream of a fully passing PostgreSQL sequence. Account linking remains on its separate owner-decision HOLD.
