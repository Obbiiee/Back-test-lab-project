# CP6A-4 — Compact QA Session Persistence

Status: **PASS for the six-command QA storage gate**. This is an experimental persistence format; it does not change production or the financial authority.

## Format

The opt-in QA-v3 Session keeps the full validated state available to the existing reducer and validators by reconstructing it from immutable PostgreSQL checkpoints. Revision zero stores the base state once. Each later `tick_checkpoints` row stores a versioned sparse state delta, its predecessor and state commitments, plus the validated controller checkpoint. `tick_sessions` stores only the current state/chain commitments and controller checkpoint. Version-3 command receipts store the state revision/hash, delta-chain commitment, command metadata and the existing event page; they do not repeat the full order map. The output returned to the caller is expanded to the existing full logical result shape.

The new receipt/checkpoint wire formats have their own versions and SHA-256 checks. Legacy v1 checkpoints and receipts continue through the original reader and validator; an opt-in reader was tested against a legacy Session. No financial arithmetic, event order, source identity, or production format changed.

## Same-workload result

Legacy and QA-v3 each ran the same six commands through the actual observed execution controller/kernel with the same three-quote authored QA fixture: ADVANCE, LONG STOP and LIMIT creation, two advances that trigger entry and TP, then cancellation of the unfilled LIMIT. The sixth QA-v3 command committed in a child process that was then SIGKILLed. Cold recovery and identical retry returned the committed result without duplication.

| Measurement | Legacy | QA-v3 |
| --- | ---: | ---: |
| Database size before workload | 9,264,151 B | 9,264,151 B |
| Database size after workload | 9,493,527 B | 9,411,607 B |
| PostgreSQL database growth | 229,376 B | 147,456 B |
| Allocated `pg_wal` after workload | 33,554,432 B | 33,554,432 B |
| Combined database + allocated WAL at end | 43,047,959 B | 42,966,039 B |
| Cumulative PostgreSQL tuple bytes written, including row metadata | 54,980 B | 41,506 B |
| Cumulative payload bytes written | 85,919 B | 40,897 B |
| WAL bytes generated (LSN delta) | 94,472 B | 76,232 B |
| Mean apply latency, first five commands | 42.097 ms | 47.933 ms |
| Cold inspect/reconstruction | 17.608 ms | 20.789 ms |

The six-command test reduced actual database growth by 81,920 bytes (35.71%), cumulative tuple writes by 13,474 bytes (24.51%), and payload writes by 45,022 bytes (52.40%). The WAL segment allocation was unchanged; measured WAL bytes written were 19.31% lower in this run. Mean apply latency was 13.9% slower and cold resume took 3.181 ms longer in this small sample. Receipt and checkpoint payload sizes are recorded per revision in the machine-readable evidence.

## Correctness and recovery

- Legacy and QA-v3 full financial states and command results match after every command; receipts and event rows were verified with format-specific hashes.
- Both paths produced six ledger events, an `ENTRY_FILL`, a TP `EXIT_FILL`, the same fill details, and final balance `10001`.
- Cold resume, all six idempotent receipt retries, and independent event sequence/predecessor/hash-chain verification passed.
- The post-commit SIGKILL and retry passed. A forced pre-commit exception left the six-command QA-v3 state, receipt count and checkpoint count unchanged.
- The exact recovery chain verifier rejected a missing delta, reordered deltas and a corrupted predecessor commitment.
- PostgreSQL observed-store regressions: 11/11 PASS. Kernel, finance and preserved CP6A SQLite-spike regressions: 31/31 PASS.

The candidate saves storage on this deliberately small workload. Cold reconstruction is 1.562 ms slower in the measured run; larger histories still need their own bounded scaling gate before any further persistence cutover.

## Reproduction and retained evidence

From the integration worktree root, use a new evidence directory for each run:

```bash
BTL_QA_DELTA_V3_ROOT=/home/riksora/riksora-qa-evidence/cp6a4-compact-rerun \
PYTHONPATH=backend PYTHONDONTWRITEBYTECODE=1 \
/tmp/riksora-vps-candidate-venv/bin/python -B -m tests.qa_postgres_delta_v3
```

The private PostgreSQL cluster was stopped after the accepted run and its evidence retained at `/home/riksora/riksora-qa-evidence/cp6a4-compact-accepted2/`. Machine-readable measurements: `evidence.json` (SHA-256 `574e7e4736ff1e5669251e9e1abbbd023214bae8accc3e79165e205f73f8b65a`); test summary: `result.txt` (11 tests, zero failures/errors).
