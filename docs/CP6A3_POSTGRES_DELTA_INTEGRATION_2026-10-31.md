# CP6A-3 PostgreSQL Delta Integration

Status: **PASS for the bounded QA vertical slice**. This is not a storage-savings result and does not authorize production use.

The opt-in `qa_state_delta_v3` path writes a versioned base snapshot and one financial-state delta per committed command. Each delta is inserted inside `ObservedExecutionStore.commit`'s existing PostgreSQL transaction, alongside the unchanged command receipt, event rows, checkpoint, and Session tip. The delta table has a foreign key to its matching durable command receipt. Legacy format, validation, receipt hashes, checkpoint bytes, financial kernel, and default store behavior are unchanged. QA tables are only created when explicitly enabled.

The integration test runs six commands through the existing `ObservedExecutionController` and observed financial kernel, using the existing three-quote authored QA fixture: open a LONG STOP and distant LONG LIMIT, trigger entry and TP, then cancel the unfilled LIMIT. It produced two simulated fill events and positive realized gross. It compares the full resulting states, receipt bytes and hashes, event bytes and hashes between the legacy PostgreSQL store and opt-in delta store. A raw-row verifier independently rechecks receipt hashes, command identity, event IDs, sequence and predecessor hashes, and final ledger head.

Atomicity and recovery checks passed:

- An injected exception after the delta insert but before transaction exit rolls back the delta, financial event, command receipt, checkpoint and Session tip together; retry commits once.
- A dedicated child process is SIGKILLed after commit. Cold inspection reconstructs the same authoritative full state; identical command retry returns the committed receipt and does not duplicate the command.
- Mutating the committed delta payload is detected as `CORRUPT_RECORD` during cold inspection.
- Existing PostgreSQL observed-store regression suite: 11/11 passed. Kernel and finance regressions: 29/29 passed.

## Measurements

From the isolated PostgreSQL run (`cp6a3-postgres-delta-v3-verified`):

| Measurement | Result |
| --- | ---: |
| Commands / revisions | 6 |
| Ledger events / simulated fills | 6 / 2 |
| Full command-receipt payload bytes | 26,915 |
| QA delta payload bytes | 19,109 |
| QA base + delta relations allocated | 131,072 bytes |
| Private database size | 10,017,815 bytes |
| Legacy apply mean / median | 37.957 / 39.748 ms |
| Delta apply mean / median | 43.230 / 40.821 ms |

The paired sample is six commands and is only an overhead indicator: the opt-in path mean was 13.89% slower in this run. Full-state receipts and checkpoints remain, so delta bytes are additive and no overall storage reduction is claimed. This result supports atomic integration and parity only; do not remove or reduce existing persistence based on it.

## Reproduction

From the integration worktree root, with its QA venv:

```bash
BTL_QA_DELTA_V3_ROOT=/home/riksora/riksora-qa-evidence/cp6a3-postgres-delta-v3-rerun \
PYTHONPATH=backend PYTHONDONTWRITEBYTECODE=1 \
/tmp/riksora-vps-candidate-venv/bin/python -B -m tests.qa_postgres_delta_v3
```

The retained machine-readable evidence is at `/home/riksora/riksora-qa-evidence/cp6a3-postgres-delta-v3-verified/evidence.json` (SHA-256 `cf46cb8211242153dbc5e764a5769e55e24f68d92f593a3391b65fa5dbb95672`). The private QA PostgreSQL cluster was stopped after the run and its evidence directory retained.
