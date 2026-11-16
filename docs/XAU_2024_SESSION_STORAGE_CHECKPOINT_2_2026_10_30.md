# XAUUSD 2024 Session storage efficiency — Checkpoint 2

**Decision:** bounded prototype gates PASS; the 500 MB persistent-storage-per-user target is **NO-GO** on current evidence. Do not start a longer replay or annual acceptance from this checkpoint. Annual replay was not run.

This is an experiment report, not new architecture, financial, causal, or admission authority. Baseline branch was `codex/beta-integration-20261028` at `af0347a2054010d84335e91972848406b13d7c42`.

Private experiment evidence is retained at `/home/riksora/riksora-qa-evidence/session-storage-20261030/checkpoint2/`. Failed harness attempts and their reports remain preserved there.

## Scope and isolation

- Reused the existing XAUUSD 2024 one-hour QA prefix: 2,222 acknowledged groups, revision 36. Dense and range runs resumed identical new copies of its existing timeline log and used H1 read-only for source traversal.
- PostgreSQL raw and compressed trials each started from a separate filesystem clone of the stopped, exclusive QA cluster containing the same existing one-hour Session. They ran the same two existing observed-store tests with deterministic fixture identities. The database and worker were never shared with production or shared QA.
- Read-only clone comparison verified the existing XAU Session's 1 session, 37 checkpoints, 36 commands and 36 events byte-for-byte across both arms. Canonical payload/content hash comparison SHA-256: `3fc03b181dd4b6e2db71406c0428e86c8d8e05cf86ebf19526898a4b376bd831`.
- The compressed payload path was a process-local QA codec hook; it stores a tagged zlib payload while preserving the SHA-256 of the canonical logical bytes. It was not added to application code or the PostgreSQL schema. Existing rows remained raw and readable.
- H1 size, inode, mtime, mode and absence of WAL/SHM companions remained unchanged. The original QA cluster remained stopped. H2/H3 and production were not accessed or changed.

## TEMP lookup — dense baseline vs `range-v1`

The existing one-hour baseline has 2,222 groups and 36 replay acknowledgements. Its closed compressed timeline log is 208,896 B, or 94.016 B/group and 5,802.7 B/acknowledgement. The separate uncheckpointed live allocation measured earlier was 1,124,288 B (53,248 B main file + 1,038,272 B WAL + 32,768 B SHM); this is transient/operational allocation, not an extra closed-log estimate. The paired dense/range copies had the same persistent log size.

For the same one-hour PostgreSQL Session, existing mandatory rows are 37 checkpoints, 36 commands and 36 events. They use 209,448 B of tuple bytes (5,818 B/command, 94.261 B/group), 180,211 B of physical payload (5,006 B/command), and 524,288 B allocated across heap/TOAST and indexes. Indexes account for 81,920 B; heap/TOAST for 442,368 B. This gives 14,564 allocated B/command including page and index allocation. Exact MVCC dead-tuple bytes were not isolated from heap/TOAST and free-page allocation, so no separate MVCC bloat number is claimed. The prior QA WAL measurement was 790,628 B generated for the bounded gate and 16,777,216 B allocated to the exclusive cluster; WAL is shared/reusable cluster allocation, not per-user history.

| Measurement | Dense | Range prototype |
|---|---:|---:|
| Rebuildable lookup rows | 2,222 | 36 |
| TEMP allocation | 208,896 B (51 pages) | 36,864 B (9 pages) |
| Increment over 5-page empty baseline | 188,416 B | 16,384 B |
| 2,222-group TEMP reduction | — | **172,032 B / 82.35% total; 91.30% incremental** |
| Cold timeline reconstruction | 2.709 s | 2.686 s |
| Reveal batch latency, median | 0.2312 s | 0.0422 s |
| Reveal batch latency, p95 | 0.2594 s | 0.0554 s |
| Reveal batch latency, max | 0.2799 s | 0.0625 s |

Both representations read 2,222 groups in 35 batches. Checkpoints matched exactly; the full revealed stream hash matched (`caec2ffedfebc4f58d48a4b5dba235091d479a80636e91b8ceb2a1b99b49b9e2`). Resume replayed and checked the persisted acknowledgement chains. The authored 160-group test also compared advances, boundary reads, cold resume and refusal of an unrevealed index. No acknowledgement or canonical record was omitted.

These are warm-cache timings from a single VPS run, not browser latency or a cold operating-system cache test. The range index is TEMP/rebuildable; **persistent timeline bytes did not decrease**.

## PostgreSQL payload prototype

The paired PostgreSQL clones ran:

- `test_replay_to_uses_existing_durable_advances_and_recovers_idempotently`
- `test_before_commit_process_death_rolls_back_after_commit_death_retries_once`

Both tests passed on both raw and compressed trials. The crash was limited to each dedicated test worker. The checks cover retry/idempotency, rollback on death before commit, committed state after death, and retry after cold process exit. Ten new test rows (2 Sessions, 4 checkpoints, 2 commands, 2 events) had exact logical identity, content hash, length and canonical-payload SHA parity between clones.

| Measurement for the same 10 new rows | Raw | Compressed |
|---|---:|---:|
| Canonical logical payload | 27,429 B | 27,429 B |
| Stored payload bytes | 27,429 B | 11,620 B |
| Payload saving | — | **15,809 B / 57.64%** |
| Whole database after tests | 10,320,919 B | 10,288,151 B |
| Whole database difference | — | **32,768 B / 0.32%** |
| Whole cloned PostgreSQL cluster allocation | 42,921,984 B | 42,889,216 B |

Index allocation was unchanged. The 32 KiB database difference came from tuple/page allocation in `tick_sessions`; it is not a stable per-row storage factor. The clone already contained the existing one-hour XAU Session, which stayed byte-for-byte raw in both arms. Compression was only exercised for new authored test rows. This is a physical codec prototype, not a qualified application storage format.

## Annual arithmetic and 500 MB target

Using the same short-prefix row-count-as-group-count extrapolation as prior planning, the range TEMP increment is about **414,455,555 B (0.414 GB)** for 56,208,511 rows, versus the previous dense estimate of 4,766,238,888 B. The actual annual timestamp-group count was not measured, so this is not an annual bound.

Sparse TEMP reduces host transient storage; it does not reduce persistent per-user history. Prior short-prefix planning still puts the compressed annual timeline log at **4.519–5.284 GB per Session**, already about **9.0–10.6×** the 500,000,000 B target, before PostgreSQL history. The earlier **13.263 GB** PostgreSQL annual allocation estimate is also an unqualified extrapolation. The 57.64% payload saving from ten small rows cannot safely be applied to that estimate.

Therefore the current representation has not shown a viable path to 500 MB/user. A larger replay is not justified until a separately reviewed, lossless persistent-history encoding demonstrates the required reduction, verifies all logical records and recovery behavior, and fits the 30 GiB safety reserve. If that requires changing frozen acknowledgement or evidence semantics, stop for owner review first.

## Resource and safety result

- Successful paired experiment: 19.60 s wall, 19.15 s CPU, 198,225,920 B cgroup peak memory and 53,384 KiB process peak RSS.
- Exact raw/compressed parity rerun: 18.99 s wall, 18.62 s CPU, 198,369,280 B cgroup peak memory; independent read-only database parity check took 0.547 s.
- Every workload ran under 1 CPU-equivalent, 1 GiB memory, swap disabled, and a 900-second runtime cap. No cap was reached.
- Cumulative new QA artifacts including the evidence index: 347,107,328 B allocated, below the 536,870,912 B budget. Filesystem available at final check: 59,978,092,544 B, above the 32,212,254,720 B reserve. Exact file hashes and the final H1/source fingerprint check are in `final-evidence-index.json` under the private evidence root.
- PostgreSQL clones and workers stopped. Failed setup/reporting attempts were tooling errors (missing interpreter dependency, SQL placeholder escaping, test UUID construction, and a parity reporter import); they did not indicate data or engine parity failures and remain in the private evidence directory.

## Implementation and decision

The opt-in TEMP prototype is in `backend/ticks/timeline_v2.py` (`lookup_layout='range-v1'`); default remains dense. Its bounded regression is in `backend/tests/test_tick_storage_v2.py`. No persistent codec was integrated. No production, financial, causal, admission, or source contract changed.

Final focused regression: all **42** tests in `tests.test_tick_storage_v2` passed in 24.590 s (24.745 s wall, 23.376 s CPU, 54,324 KiB peak child RSS) under the agreed CPU, memory, swap and runtime limits. The two PostgreSQL idempotency/process-death tests passed on both arms, and the independent existing-XAU clone comparison passed.

**Checkpoint 2 result: PASS for the bounded efficiency and parity experiments. NO-GO for longer or annual replay and for claiming the 500 MB/user target.**
