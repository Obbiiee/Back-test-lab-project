# XAUUSD 2024 Session persistence — Checkpoint 4

**Technical result: PASS for the bounded lossless codec experiment. Economic result: NO-GO for the 500 MB annual Session target.** This checkpoint does not change a financial, causal, admission, or acknowledgement contract and does not establish annual storage capacity.

Private evidence is retained at `/home/riksora/riksora-qa-evidence/session-storage-20261030/checkpoint4/`; `evidence-index.json` lists file hashes and physical allocated sizes. Failed harness attempts and their reports were preserved. No original evidence was overwritten.

## Scope and protection

- The validated XAUUSD QA Session covered **2,222 timestamp groups**, **36 advance commands**, and **72 timeline blocks**. Both arms replayed the same 36 stored target times against the same pinned dataset and source prefix.
- Baseline was the existing `zlib-1` physical timeline format. The experimental `delta-dict-zlib-1` adds a deterministic per-block string dictionary, delta-coded numeric position fields, and binary encoding for 32-byte hashes before zlib compression. The stored block key and all cursor/hash calculations still use the original canonical logical bytes.
- H1 was opened read-only. Its current `[size, mtimeNs, inode, permission mode]` matches the checkpoint 2 pre/post pin. The existing timeline source log SHA-256 also matches its checkpoint 2 pin. H2 and H3 were not accessed. Production was not accessed or changed.
- PostgreSQL retry and process-death tests ran on isolated filesystem clones of a stopped QA cluster. The baseline and candidate clones retained identical canonical row identities, hashes, lengths, and contents. Candidate workers inherited only the QA codec setting. Both QA clones are stopped and retained as private evidence.
- No annual replay, full source scan, cleanup, or canonical publication was run.

## Measurements

| Measure | Existing zlib baseline | Delta/dictionary candidate | Change |
|---|---:|---:|---:|
| Timeline SQLite allocated bytes after close | 208,896 B | 208,896 B | **0 B / 0%** |
| Sum of compressed block bodies | 145,400 B | 116,832 B | **−28,568 B / −19.65%** |
| Live WAL allocated bytes | 1,003,520 B | 1,003,520 B | equal; WAL absent after close |
| Live SHM allocated bytes | 32,768 B | 32,768 B | equal; SHM absent after close |
| TEMP database pages × 4,096 B | 192,512 B | 192,512 B | equal; rebuildable, not persistent |
| Median write latency, 36 advances | 30.66 ms | 31.61 ms | +3.1% |
| p95 write latency | 175.95 ms | 167.49 ms | −4.8% |
| Median read latency, 35 batches | 208.89 ms | 393.26 ms | +88.3% |
| p95 read latency | 238.13 ms | 419.71 ms | +76.3% |
| Process-cold logical resume | 2.366 s | 2.769 s | +17.0% |
| Worker CPU | 12.235 s | 18.975 s | +55.1% |
| Worker peak RSS | 43,188 KiB | 43,476 KiB | +288 KiB |

The SQLite file remained **51 pages** in both arms. The candidate saves bytes inside block payloads, but not a physical page at this sample size. The TEMP number is reported as page allocation (`PRAGMA temp.page_count × page_size`), not as a separately `stat()`-measured temp file. PostgreSQL's `tick_sessions`, `tick_checkpoints`, `tick_commands`, and `tick_events` relation sizes, stopped-cluster allocation (**43,024,384 B**), and allocated WAL (**16,777,216 B**) were equal between arms; PostgreSQL payload storage was unchanged by this timeline-only codec.

## Correctness and recovery evidence

- All **43** focused `tests.test_tick_storage_v2` tests passed, including the new comparison test. Both codecs produced the same final checkpoint, 36 advance result hashes, 72 canonical logical block bodies, and revealed-group SHA-256: `caec2ffedfebc4f58d48a4b5dba235091d479a80636e91b8ceb2a1b99b49b9e2`.
- Final cursor, `advanceLogHash`, `positionLogHash`, visible-prefix hash, revision and group count matched the existing QA checkpoint exactly. Cold reopen reconstructed the same checkpoint and revealed history; an unrevealed group remained refused.
- Existing PostgreSQL tests passed in both arms: `test_replay_to_uses_existing_durable_advances_and_recovers_idempotently` and `test_before_commit_process_death_rolls_back_after_commit_death_retries_once`. They cover same-command retry/idempotency, conflict/stale behavior, rollback when the worker exits before commit, and committed state plus one retry after worker exit following commit. Ten observed-QA rows had exact logical payload/hash parity across arms.
- Existing no-look-ahead regression passed as part of the focused timeline suite. No consumer/provider capability was added.
- First harness attempt completed timeline parity and baseline transaction tests but its reporter lacked the backend import path. A second attempt completed the 43 tests but stopped before candidate tests because its Unix socket path exceeded the OS limit. Both harness failures are retained. The final run used a short private socket and candidate tests passed; no engine parity failure occurred.

## Resource and economic decision

Each execution scope enforced **100% of one CPU**, **1,073,741,824 B memory maximum**, swap disabled, and a 900-second timeout. Across the three retained scopes, cumulative wall time was **66.35 s**, CPU usage **64.02 s**, and maximum memory peak **141,168,640 B**. The final cumulative new QA artifact allocation, including retained failed attempts and database clones, was **130,740,224 B**, below the **536,870,912 B** cap. Filesystem free space was **59,841,503,232 B**, leaving **27,629,248,512 B above the 30 GiB reserve**.

The actual annual timestamp-group count was not present in the trusted publication/recheck metadata inspected. It remains unknown; no tick-to-group approximation or annual storage extrapolation is made here. The 2,222-group sample cannot establish a 500 MB annual Session, much less a 500 MB aggregate quota across multiple Sessions for one user.

Checkpoint 2's non-annual projection put the existing compressed annual timeline at 4.519–5.284 GB before PostgreSQL, requiring roughly 88.9–90.5% further reduction in timeline storage to reach 500 MB by itself. Checkpoint 4 achieved **zero reduction in allocated SQLite bytes** and made read/resume slower. **Do not continue codec micro-optimization as the path to the economic target.** If the owner still requires 500 MB annual Sessions, the next decision is an explicit persistence-contract review: determine whether a compact block proof/checkpoint scheme may replace any per-group durable representation and what independent recovery proof must remain. No such contract change is approved by this report.

## Implementation and repository state

The optional codec and its focused regression are in `backend/ticks/timeline_v2.py` and `backend/tests/test_tick_storage_v2.py`. The default remains unchanged; the codec is not enabled by application configuration. No database migration or application storage policy changed. Annual timestamp-group count and annual economic feasibility remain unproven.

Final repository validation: the 43 focused timeline tests passed; `npm run test:repository`, `npm run test:ai-bundle`, `npm run ai:bundle`, and `npm run ai:bundle:verify` passed. No frontend test/build was applicable because the frontend was unchanged.
