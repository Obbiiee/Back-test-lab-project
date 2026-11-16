# CP6A-5 — Compact Storage Performance

**Status: PASS (isolated QA only).** The existing QA-v3 format stays enabled only through its explicit flag. No financial kernel, production path, durable schema, or authority contract changed.

## Finding and optimization

The CP6A-4 256-order profile showed repeated full delta-chain reconstruction during each apply was the dominant cost. One instrumented late apply took 12.630 s under cProfile; `_qa_reconstruct` ran twice and accounted for 11.049 s cumulative, with canonical normalization/serialization accounting for most of that reconstruction. Database row decoding and content hashing were each below 0.4 s cumulative. This identifies repeated reconstruction and its canonical state hashing as the dominant measured bottleneck; PostgreSQL I/O was not the cause.

The narrow optimization is a per-store LRU cache of at most four reconstructed QA-v3 states. It is keyed by workspace/session and usable only when the durable Session revision, state hash, and chain hash match. Every use still validates the state hash, controller snapshot, and immutable durable tip. Entries are written only after durable creation/commit. A fresh store, cache miss, mismatch, or cold resume reconstructs and verifies the complete durable chain; the cache is not the recovery authority. Legacy sessions do not enter this path.

## Identical 256-order comparison

The runner processed 256 created-and-cancelled orders (513 durable commands) on separate private PostgreSQL databases, using the same command bytes and actual observed execution controller/kernel. Each command result SHA-256 and final logical financial state matched exactly. The fixture intentionally had no fills; separate parity regressions exercised TP and SL fills.

| Measure | Legacy | QA-v3 optimized | Result |
|---|---:|---:|---|
| PostgreSQL database growth | 7,741,440 B | 3,858,432 B | **50.159% saved** |
| WAL bytes generated | 9,417,760 B | 3,908,776 B | lower in this run |
| Median apply | 286.724 ms | 266.899 ms | 0.931× legacy; gate ≤1.5× PASS |
| P95 apply | 506.517 ms | 491.259 ms | lower in this run |
| Cold resume / full reconstruction | — | 1.329 s | PASS |

Relative to the owner-provided CP6A-4 baseline (48.14% DB saving; about 1,010 ms QA-v3 median), this run measured 50.159% saving and 266.899 ms median apply. The profile checkpoint independently recorded the pre-optimization QA-v3 median at 989.521 ms and 48.363% saving; differences reflect run-to-run measurement variation. The cache does not make cold reconstruction faster: measured cold resume remained 1.329 s (CP6A-4 comparison run: 1.294 s).

## Correctness, recovery, and resource gates

- 256-order legacy and QA-v3: per-command result hashes, final logical state, source identity, receipts, ledger/event chain and independent delta reconstruction all PASS.
- Cold resume PASS. A process killed immediately after a committed command recovered and an identical retry returned the committed result without duplication.
- Missing, reordered, and corrupted delta probes were each rejected. The probes temporarily disabled the append-only trigger only inside a private QA transaction and rolled back to a savepoint; retained committed rows were unchanged.
- Separate real financial regressions: SHORT market entry followed by SL matched legacy exactly and passed cold resume; existing LONG STOP entry/TP, LIMIT cancellation, rollback, SIGKILL/retry, atomicity, idempotency, and independent verification regression passed.
- Full suite: 3/3 tests PASS in 309.833 s; test process exit code 0.
- CPU affinity: one core. Peak sampled cgroup RSS: 802,357,248 B (<1 GiB). QA artifacts: 86,228,992 B (<512 MiB). Free disk at completion: 54,011,887,616 B; the 30 GiB reserve remained intact. No protected archive, production DB, or canonical dataset was used or changed.

An initial attempt stopped at the corruption probe because the append-only trigger correctly blocked test mutation. The probe was adjusted to use a rolled-back fault injection in the isolated QA cluster, then the complete suite passed. This did not require weakening the durable-table policy.

## Reproduction and evidence

From the integration worktree root, use a new empty evidence directory:

```bash
BTL_QA_DELTA_V3_SCALE_ROOT=/home/riksora/riksora-qa-evidence/cp6a5-reproduction-20261031 \
PYTHONPATH=backend PYTHONDONTWRITEBYTECODE=1 \
/tmp/riksora-vps-candidate-venv/bin/python -B -m tests.qa_postgres_delta_v3_256
```

The private PostgreSQL cluster was stopped after the run. Evidence remains outside the repository at `/home/riksora/riksora-qa-evidence/`:

- Pre-optimization profile: `cp6a5-profile-20261031/evidence.json`, SHA-256 `9da765a0022a759d72b262b809aa81f59513fc9acc60abcabe483de67f531812`.
- Optimized 256-order evidence: `cp6a5-optimized-256b-20261031/evidence.json`, SHA-256 `8dda0781deb2bee27b3358f9ab9662cc51c95e08d04a9f6474c46d1a5b7b2f0c`.
- Test result: `cp6a5-optimized-256b-20261031/result.txt`, SHA-256 `7fb0be33309f223748cf2ceea110b35685c887e95e5bb5d3cd9a3e50c691ac77`.
- Financial regression result: `cp6a5-optimized-256b-20261031/small-financial-regression.json`, SHA-256 `2774ec57a2697ad5927b1e0119762dd957cc575d7c94a0a0e2b279dd77e178b1`.
- Machine-readable summary: [CP6A5 evidence JSON](CP6A5_COMPACT_STORAGE_PERFORMANCE_2026-10-31.json).

This passes the stated storage and latency gates for 256 orders. It does not authorize higher order counts, longer historical replay, or production use.
