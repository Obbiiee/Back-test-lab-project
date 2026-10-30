# Checkpoint 6 — PostgreSQL Session economics

**Technical PASS. Economic GO for the bounded compact-storage direction; NO-GO for claiming a 500 MB annual Session/user or production readiness.** One experimental representation was tested at four workload sizes. No authority, application persistence implementation, financial reducer, admission rule or production configuration changed. No annual replay or subsequent optimization was started.

Private evidence: `/home/riksora/riksora-qa-evidence/session-storage-20261030/checkpoint6/`, including `report.json`, `independent-final.json`, per-arm metrics, corruption/crash results, physical file inventories and the final evidence index. All new source is explicit-run QA code under `backend/tests/qa_pg_*6.py`; no application imports or enables it.

## Workload and isolation

Fresh isolated PostgreSQL databases compared current raw canonical payloads (including PostgreSQL's normal TOAST compression) with a versioned lossless DAG representation. Both arms used identical existing zlib SQLite timeline logs and the unchanged observed execution engine/store. Dataset generation reused the existing authored observed-tick QA fixture. H1/H2/H3 were not accessed; the stopped source QA cluster was copied, never started or mutated in place. The private QA server listened only on a private Unix socket and is stopped after the experiment.

Each eight-command cycle reveals a quote, submits a pending LONG LIMIT, executes it at ask 2299, exits at bid 2301 through TP, submits a pending LONG STOP, executes at ask 2302.1, exits at bid 2299.9 through SL, and issues a zero-reveal advance. Quantity is 0.01 lot (one underlying unit), commission zero. Independent expectations are +2 and -2.2 per cycle. These are actual existing-engine transitions on authored tick prices, **not broker outcomes or annual XAU market acceptance**. Source quality/rights remain the existing conditional QA classification.

Sizes 0/16/64/256 commands used one identical 160-tick source and exact command prefixes. At 256 commands, all 32 LIMIT and 32 STOP orders progressed through PENDING to fills and CLOSED. There were 32 TP exits and 32 SL exits, 256 receipts/events, 257 checkpoints, and final balance **9993.6**, from initial 10000. No second order engine was introduced.

## Experimental representation

Existing command receipt, event, checkpoint and mutable tip rows retain their identities and original canonical SHA-256. Their physical payload is a versioned root reference. Immutable PostgreSQL objects hold zlib-compressed, hash-addressed dictionary/list nodes; repeated profile/context, unchanged orders and identical state subtrees are reused across records. Decoding reconstructs the original full logical record, not an approximation or a receipt summary.

All object inserts and referencing receipt/event/checkpoint/tip writes happen in the existing SQL transaction. A QA-process-only pack/unpack/connection adapter supplies the object store; baseline code and logical validation are unchanged. No full receipt is counted a second time in the object model: referenced nodes are counted once by actual table/file allocation, with root-row/index overhead counted separately. No object garbage collection or evidence removal was implemented.

## Actual allocated bytes

PostgreSQL measurements include heap, TOAST, indexes, main/FSM/VM/init forks and relation segments, reconciled against `pg_total_relation_size` and actual filesystem `st_blocks × 512` after a QA CHECKPOINT. SQLite is also measured by actual allocated file blocks. Shared source data, database system catalogs and cluster WAL are reported separately from per-Session relations; they are not multiplied per user.

| Commands / events / checkpoints | Baseline SQLite + PostgreSQL | Compact SQLite + PostgreSQL | Saving |
|---|---:|---:|---:|
| 0 / 0 / 1 | 131,072 B | 196,608 B | **−50.00%** |
| 16 / 16 / 17 | 462,848 B | 348,160 B | **24.78%** |
| 64 / 64 / 65 | 1,294,336 B | 753,664 B | **41.77%** |
| 256 / 256 / 257 | **6,791,168 B** | **2,375,680 B** | **65.02%** |

The largest combined saving is **4,415,488 B**. Its identical SQLite contribution is 237,568 B per arm; PostgreSQL falls from 6,553,600 to 2,138,112 B. Therefore this is a reduction in physical persistent allocation, not only compressed payload length.

Empty Session-related PostgreSQL tables/indexes occupy 81,920 B in the baseline and 131,072 B with the object/format schema. After the initial Session seed, PostgreSQL occupies 114,688 and 180,224 B respectively, plus identical 16,384 B SQLite. These are database/schema fixed costs, normally amortized over multiple Sessions, not an assertion that production needs a database per user. Page granularity prevents claiming an exact break-even command count between the measured samples.

Largest-workload PostgreSQL breakdown:

| Component | Baseline allocated | Compact allocated |
|---|---:|---:|
| Immutable command receipts | 2,416,640 B | 180,224 B |
| Immutable checkpoints | 2,326,528 B | 114,688 B |
| Complete financial/other events | 491,520 B | 196,608 B |
| Mutable Session tip | 1,318,912 B | 32,768 B |
| Shared object table, including indexes/TOAST | — | 1,581,056 B |
| Format metadata | — | 32,768 B |

The object pool has 2,310 immutable nodes at 256 commands. Its bytes belong to the shared representation of all record kinds; allocating them independently to receipts and checkpoints would double-count them. The baseline's mutable tip allocation includes old tuple/TOAST versions, page slack and auxiliary files. Exact dead-tuple bytes were not isolated; statistics are estimates, not a measured bloat decomposition. Normal autovacuum remained enabled; one object-table autovacuum was observed. No manual VACUUM/cleanup policy was introduced to favor either arm.

Measured marginal growth separates fixed pages from scaling. Combined bytes per additional command are baseline/compact **17,322.67 / 8,448** for 16→64 and **28,629.33 / 8,448** for 64→256. For the latter interval, baseline command/checkpoint/event table growth is **10,496 B per command / 10,154.67 B per checkpoint / 1,706.67 B per event**; compact root tables use **469.33 / 256 / 554.67 B** respectively, plus shared-object growth of **6,314.67 B per additional command**, counted once. Mutable tip and SQLite growth account for the remaining difference. These workload-dependent slopes are not annual constants. Command/event/checkpoint counts co-vary in this fixture, so no independent combined multivariate coefficients are claimed.

## Performance and correctness

At 256 commands:

| Measure | Baseline | Compact |
|---|---:|---:|
| Write latency median / p95 | 155.21 / 270.02 ms | 195.16 / 341.17 ms |
| Read latency median / p95 | 52.48 / 96.73 ms | 119.82 / 182.18 ms |
| Logical cold resume | 0.600 s | 0.724 s |
| Worker CPU, including audit/measurement | 46.508 s | 56.772 s |
| Worker peak RSS | 89,916 KiB | 72,912 KiB |

The storage gain costs approximately **26% median write latency, 2.28× median read latency, 21% cold-resume time and 22% worker CPU** at this sample. Read samples are five page traversals (20 calls at the largest size); timings are descriptive, warm OS-cache measurements, not an SLA or an annual throughput result. Fresh worker processes isolate each arm's RSS. Cold resume loads durable state through the existing store and reconstructs the existing timeline; it does not bypass 42.17 recovery.

The main experiment ran for 220.29 s; final direct byte/adversarial verification added 3.89 s. Recorded cgroup CPU snapshots total 223.10 s and maximum aggregate memory peak was 293,130,240 B. Each scope enforced one CPU-equivalent, 1 GiB memory, zero swap and bounded timeouts. New QA artifacts, including the cloned cluster, all ten isolated databases, source fixture and logs, stayed below 512 MiB; the final evidence index records exact allocation and free space. The 30 GiB disk reserve was preserved, and the QA cluster is cleanly stopped. Repository gates and evidence closure are recorded separately.

PASS evidence:

- Independent decoder does not import the writer or use its caches. Node hashes, decompression bounds, canonical bytes, logical hashes and graph structure are verified.
- Direct byte comparisons at all four sizes match every original receipt, event, checkpoint and tip across arms, in addition to matching authenticated stream/state hashes.
- An independent authored numeric oracle verifies pending status, later eligible entry quotes, TP/SL prices, event chains, cash reconciliation, final closed orders and expected balances 10000 / 9999.6 / 9998.4 / 9993.6. SQL event histories exactly match the complete receipt event lists.
- Missing/reordered/duplicated history, missing/corrupt shared objects, substituted tip, trailing streams and inflation limits reject. Additional probes explicitly remove TP, SL and entry-fill events, omit receipts, reorder fills and substitute financial payloads; all reject. The initial tail-event removal probe is not misrepresented as removing a fill.
- Source-free retries return the original receipt; changed intent under the same command ID rejects.
- Dedicated workers are SIGKILLed before and after the SQL commit of an actual TP fill in both arms. Before commit, state and newly inserted codec objects roll back together. After commit, retry returns the original result without source access. All cases finish with one TP posting, balance 10002, exactly four commands and no duplicate events; independent cold audits pass.
- fsync, synchronous_commit and full_page_writes remained on. Worker process death is not a host-power-loss test.

## Decision and remaining limits

Technical PASS is limited to this isolated, single-writer experiment. **Economic GO applies to the compact physical representation direction:** the improvement is material and increases with the measured financial history size. It warrants an architecture decision about a versioned production storage design, not another automatic codec optimization.

**500 MB annual Session/user and production migration remain NO-GO.** Annual command/event/checkpoint distributions, multiple Sessions per user, sustained I/O and user concurrency were not measured. The current engine also caps retained orders at 128; this experiment uses 64 and does not change that financial limit. Do not extrapolate this trade-cycle slope into an unsupported annual trading workload.

Production review would need compatibility/versioning, tenant access controls for shared objects, bounded streaming verification, object-closure backup/restore, corruption blast-radius handling, concurrency and long-term retention decisions. One corrupt shared object may invalidate several logical records. The prototype verifier loads the bounded QA object set into memory, and the test connection adapter is not a concurrency-qualified application port. No existing authority was amended and no application decoder/migration was shipped. STOP after this checkpoint.
