# Checkpoint 5 — verified range QA prototype

**Technical GO for this bounded proof of equivalence. Economic NO-GO for a 500 MB annual Session claim. Production/contract cutover remains NO-GO.** Authorities 42.17/42.19 and application persistence were not changed. The implementation is confined to explicit-run `backend/tests/qa_range_*5.py` modules, which are not imported by the application.

Private evidence: `/home/riksora/riksora-qa-evidence/session-storage-20261030/checkpoint5/`. All original evidence, H1/H2/H3 and production remain preserved. H1 was opened read-only; H2/H3 were not accessed. No annual replay or source scan was performed.

## Workload and representation

Both arms used the same existing 2,222-group XAUUSD prefix and unchanged timeline/observed financial engine. The original 36 ADVANCE intents were reconstructed from the stored acknowledgement schedule and their command hashes checked against PostgreSQL. All 36 resulting receipt payloads matched the original bytes. One identical zero-reveal ADVANCE control was added to both arms, giving **37 durable commands/receipts, 37 events, 38 checkpoints, and still 2,222 groups**. This workload has no entry/exit fills; financial-event completeness here covers all events actually generated, not a new trade-scenario qualification.

Baseline uses existing zlib timeline logs and unchanged PostgreSQL receipt/event/checkpoint storage. The prototype stores one binding plus 37 compressed range envelopes. Each envelope binds command ID/hash, exact target, before/after cursor hashes, group bounds, first source position, legacy log tips, previous range hash and an ordered, length-framed SHA-256 commitment to the original logical position records. Empty ranges are retained. Full receipts remain stored exactly once in PostgreSQL; range envelopes contain command references, not duplicate receipt bodies.

The unchanged engine still writes V2 logs into **rebuildable QA scratch**. The prototype's independent verifier rebuilds legacy log/cursor hashes from source and the complete schedule into separate scratch. This is an experimental alternative durable representation, not an authorized removal of logs required by 42.17. All scratch is retained as QA evidence and included in the artifact budget, although excluded from the proposed per-Session persistent representation comparison.

## Cross-store protocol

1. Commit the immutable range prepare to SQLite WAL with `synchronous=FULL` before SQL commit.
2. In the **same PostgreSQL transaction** as the existing financial state, command receipt, events and checkpoint, insert the range hash reference with a foreign key to the command. The existing store/reducer remains unchanged; a test-process-only connection adapter adds this reference before transaction exit.
3. Publish the SQLite head after PostgreSQL commits. PostgreSQL references determine visibility; the SQLite head is rebuildable acceleration.
4. On recovery, verify every SQL-referenced prepare and the complete chain. Ignore and retain unreferenced prepares. A SQL reference to absent/corrupt preparation fails closed. A committed SQL reference with an unpublished SQLite head is reconciled from SQL. Retried committed commands return the original receipt before source work.

The QA PostgreSQL clone used fsync, synchronous_commit and full_page_writes set to `on`. Tests kill only dedicated experimental workers, not PostgreSQL or a production service. Power-loss/storage-device durability is not certified by these worker-kill tests.

## Independent verification and adversarial gates

`qa_range_verifier5.py` does not import the writer. It verifies stored hashes, sequence, command bindings, continuity and SQL references; traverses immutable source pages to derive complete timestamp groups and positions separately; recomputes commitments; and replays the complete schedule through a fresh existing timeline and the unchanged financial reducer. It trusts no writer-generated index/cache. The resulting legacy log tips, cursor chain, state and events must match.

PASS gates:

- All original 36 receipts exact; all 37 baseline/prototype receipts exact, including zero-reveal.
- Source group stream SHA-256 equals the prior accepted value `caec2ffedfebc4f58d48a4b5dba235091d479a80636e91b8ceb2a1b99b49b9e2`.
- Missing/duplicate/corrupt prepared records, missing/duplicate/reordered commits, and substituted dataset binding reject.
- A malicious writer's internally consistent rewritten hash chain around a false source commitment rejects through independent source verification.
- Unreferenced future tail is excluded. Public reads beyond the committed prefix refuse. Consumer exposes no provider/index/checkpoint/EOF capability.
- Removing future rows in a QA provider projection leaves the first/last committed consumer windows unchanged, including the complete final timestamp group.
- SIGKILL after durable prepare, inside SQL before commit, after SQL commit, and after finalization: all four recover correctly and retain exactly one command after retries. Conflicting retries reject. These controlled crashes occur on the first 64-group advance; they are not year-scale crash probes.
- Four subsequent independent source-based cold verifications of those recovered histories pass.
- Independent direct SQL checks verify contiguous commands/events/checkpoints, payload hashes/canonical bytes, exact receipt-to-event completeness, checkpoint-to-receipt state, immutable tip equality and baseline/prototype parity. Main Session counts are 37 commands, 37 events and 38 checkpoints; all crash scopes also reconcile.

## Physical storage and performance

Measured after the main workload and before adding the separate crash-test scopes:

| Measure | Existing zlib baseline | Range prototype |
|---|---:|---:|
| Timeline/range SQLite logical file length | 208,896 B | 57,344 B |
| Actual SQLite allocated bytes (`st_blocks × 512`) | 212,992 B | 61,440 B |
| Existing PostgreSQL Session relations including indexes/TOAST | 712,704 B | 712,704 B |
| Additional SQL range-reference relation including index | 0 B | 65,536 B |
| **Total proposed persistent Session allocation** | **925,696 B** | **839,680 B** |
| Write latency median / p95 | 1.439 / 2.654 s | 1.461 / 2.535 s |
| Read latency median / p95 (35 bounded reads) | 0.210 / 0.228 s | 0.142 / 0.242 s |
| Logical cold reconstruction | 2.562 s | 3.630 s |
| Main arm CPU | 65.063 s | 62.481 s |
| Main worker peak RSS | 63,600 KiB | 63,900 KiB |

Timeline allocation decreases **151,552 B / 71.15%**. After accounting for unchanged full receipts/checkpoints/events and the SQL reference relation, the actual combined saving is **86,016 B / 9.29%**. ADVANCE receipts are counted once; reference/index metadata is additional physical overhead, not another receipt estimate. Filesystem allocation differs from file length and is intentionally reported separately.

PostgreSQL page accounting was independently cross-checked against actual filesystem `st_blocks` for every main, TOAST, index and auxiliary-fork file. Fresh isolated SQL projections used the same 37 validated receipt/event/checkpoint records through the existing store commit path, followed by an isolated QA CHECKPOINT to flush files. All projected receipt bytes matched, file sizes reconciled with PostgreSQL totals, and actual allocated bytes confirmed the totals above. This storage check did not replay additional market history.

The prototype had 569,344 B of engine scratch and 208,896 B of verifier scratch at its measurement point. These are rebuildable but retained QA artifacts; they do consume host disk. PostgreSQL WAL is cluster operational storage, not included in Session relation bytes; final allocation is recorded separately in the evidence closure. SQLite live WAL/SHM and TEMP peaks were not continuously sampled, so no peak-I/O or WAL-amplification claim is made.

Write latency includes cold reconstruction on each command in both arms; it is not browser/API acknowledgement latency with a warm application cache. Reconstruction timings use fresh controller objects and warm OS page cache, not a flushed disk cache. This is one sequential pair with a harness retry, not an ABBA performance benchmark. Prototype reads deliberately derive from source rather than rely on writer indexes; no scalable random-read complexity claim follows.

The first prototype attempt stopped on a missing schema version in the experimental canonical envelope. Its partial report and completed baseline were preserved. The QA envelope/hash calls were corrected and only the unfinished prototype continued. The engine and original workload were not changed to pass.

Recorded experiment stages, including that failed setup, consumed 147.54 s wall and 145.37 s sampled cgroup CPU; repository gates are recorded separately. Maximum cgroup memory peak was 170,196,992 B. Every experiment scope enforced CPU quota 100000/100000, 1 GiB RAM and zero swap, with bounded timeouts; aggregate execution remained below 15 minutes. Final cluster WAL occupies 33,554,432 allocated bytes independently of Session relation accounting. New QA artifacts were about 101.4 MB before the final evidence index, below 512 MiB; the index records the exact final allocation. Free disk at closure was 59,736,215,552 B, above the 32,212,254,720 B reserve. The isolated PostgreSQL clone is cleanly stopped. No peak disk-I/O measurement was claimed.

## Contract and economic limits

42.17 requires durable per-group position records, exact log/checkpoint shapes, verified membership and full-prefix reconstruction. 42.19 preserves these fields. Range envelopes and SQL reference authority are therefore **not an approved production substitute**. This experiment proves reconstruction equivalence for the bounded input, not permission to change those requirements.

Other gaps: the transaction adapter is single-worker QA instrumentation, not a concurrency-qualified application port; no concurrent-writer/host-power-loss test was run; the verifier still replays the full prefix; the QA harness retains a bounded in-memory command/receipt list; order/fill workloads and large histories remain untested. Whole-history rollback requires a separately trusted tip/anchor and is not solved by a hash chain alone.

Annual growth must be modeled as range/schedule bytes plus **one** durable command/receipt representation, complete event bytes, checkpoints, references and physical overhead. There is no persistent per-group record in the proposed range destination, but source traversal and reconstruction still scale with revealed groups. Actual annual timestamp-group/acknowledgement/event counts and physical allocation curves were not established.

**Economic NO-GO:** 500 MB per annual Session is unproven, and 500 MB across multiple Sessions per user is stricter. A 9.29% saving on this small allocation sample does not authorize a longer run. The unchanged receipt/checkpoint representation dominates remaining storage. Any proposal to compress/reconstruct those logical records or change checkpoint retention requires another explicit contract review. No automatic optimization, longer replay, contract amendment, migration or production change follows this checkpoint.
