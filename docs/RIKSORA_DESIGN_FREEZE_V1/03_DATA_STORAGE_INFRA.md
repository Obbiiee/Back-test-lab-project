# 03 — Market Data, Trader Storage, Cache, Infrastructure and Disaster Recovery

**Status:** proposed design, not a certified deployment or completed benchmark. Authority: [Market Data Standard](../MARKET_DATA_STANDARD.md), [Alpha data/ops contract](../V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md), [single-VPS benchmark gate](../SINGLE_VPS_STORAGE_BENCHMARK_GATE.md).

## Immutable shared dataset

Every qualified canonical market dataset is stored **once per instrument/provider/version** and referenced by many Sessions. Market values are not copied into each trader's storage or journal. No per-user dataset downloads, full-tick position logs, duplicate derived candles or persistent DuckDB tables.

Canonical data passport contains dataset ID, provider/feed/raw symbol, original hash, version/hash, UTC start/end and actual gaps, event count, timestamp resolution/ordering trust, Bid/Ask scale, source rights, execution-eligibility class, manifest/index hash and schema/reader version. Different versions are immutable and must coexist as long as referenced and rights permit. Source-data publication is not proof of commercial redistribution rights.

**Logical partition = instrument/feed/version/UTC day**, with no empty trading-day files and exact cross-day timestamp-group semantics. Benchmark finalists: one compressed Parquet file per UTC day **versus** monthly file(s) with time-prunable row groups. Default physical candidate Parquet ZSTD; measure level 1/3/6, row groups 32k/64k/128k/256k and fixed-point price encoding. PyArrow indexed partial reader baseline; DuckDB direct Parquet scan analytics/control. Choose one layout based on size, random seek, full replay, RAM and object-store request costs; NO change in canonical event hashes. No permanent simultaneous raw+SQLite+Parquet copies without auditable retention/rollback justification.

Parquet column contract: timestamp nanoseconds int64; exact integer/decimal Bid/Ask; source ordinal; trusted sequence only when verified; group/tie provenance, event identity and quality/diagnostic references; feed/contract version through immutable manifest. Preserve ambiguous equal-time rows, exact duplicates, invalid/gap evidence according to existing canonical contracts. Never coerce precision to float or silently sort untrustworthy events. A storage adapter reconstructs existing V2 canonical records byte/semantic-identically.

## Storage responsibility / lifecycle

| Data | Durable location | Writer | Retention |
| --- | --- | --- | --- |
| Canonical market tick / source proof | versioned immutable local SSD or licensed S3 | dataset publisher | pin while required by Session, source rights and disaster recovery |
| Index/manifest/quality | alongside dataset | offline validator | immutable, integrity checked |
| Method, Session, profile pin | PostgreSQL | application | user and audit policy |
| Accepted command, event, cash/position ledger | PostgreSQL | serialized transaction writer | immutable canonical proof |
| Author journal, drawings, setup marks | PostgreSQL or bounded versioned application blobs | application | user's durable research; restore tested |
| Current cursor and compact recovery snapshots | PostgreSQL | atomic Session writer | versioned; retain necessary recovery proofs |
| Shared derived candle / indicators | bounded cache | renderer/worker | recomputable by source/version |
| Work/spill files | bounded local scratch | worker | safe cleanup only on finished/aborted isolated job |
| Export ZIP | optional downloadable artifact | export job | time-limited, no default duplicated full history |
| Backup | separate failure domain | operator | explicit policy and tested restore |

**Audit targets:** main `backend/ticks/timeline_v2.py` per-session position/advance logs and `backend/execution/postgres.py` command results including replay content plus every-revision checkpoint; measure actual per-Session bytes per million ticks advanced, not merely raw dataset size. Replacement plan: compact command receipt, append-only trade/decision events, current cursor/checkpoint and periodic reconstructable snapshot. Preserve old revision hashes and idempotent receipts with schema migration rather than editing old records.

## Capacity on one VPS

Target **6 vCPU, 16 GiB RAM, 200 GB SSD** for one active user with full access to every **qualified** of sixteen instruments × five years through bounded reads. This does NOT imply all sources already exist or fit locally. Worker concurrency, memory, file handles, in-process cache and PostgreSQL pool are capped using measured host quotas. Initial Alpha reference gate remains **4 vCPU/8 GiB/80 GiB** with 20x / 10 Sessions; target host additionally receives one-user/long-year measurement. Existing resource ceilings: RAM <=85%, disk <=80% of usable provisioned disk, checkpoint <=2 MiB, cache <=20% RAM until tuned. The 16×5 catalog must NOT be kept fully in memory.

Hot: active day(s)/row groups plus bounded shared candle tiles. Warm: last-access periods, LRU bounded. Cold: infrequently used symbols/periods stay canonical in local volume or remote object store, retrieved on demand and then eligible for eviction. **Cold means access frequency, not loss of user access or a second obligatory physical copy**. Fixed cache key = dataset/version, profile, timeframe, UTC interval, derivation version, never only symbol or account. Per-user browser reveal uses only authorized prefix.

## Purchase decision table (nonnegotiable)

- KEEP ONE VPS while measured RAM/disk/latency and safety gates pass.
- OPTIMIZE FIRST if avoidable copies, per-tick user logs, expensive reconstruction, full-object download, unbounded caches, excessive small-file requests are detected.
- ADD STORAGE after a complete safe-capacity ledger shows canonical required data, retained source/backups, PostgreSQL, system, temp budget and safe headroom cannot fit under 80% utilized **after** dedup/compression/retention optimization; off-node backup can be required separately by disaster-recovery obligation.
- ADD CPU/RAM/SECOND VPS only after demonstrated real CPU/RAM/queue/network saturation on the actual host and failed bounded local remediation. Source disk size alone is not a second VPS trigger.
- HOLD with no purchase for unqualified source/rights, incomplete timing/OS cache provenance, mismatch, or missing cost evidence. A 2 TB object-storage target is a **capacity planning option** not a procurement approval.

S3 evaluation requires measured bytes/reads/GET or range requests, request and storage fees, download amplification, cache hit rate and p95 cold seek. Do not expose raw future ticks via CDN and do not depend on unbounded remote full-file download.

## Crash, backups and safe deletion

- Commit dedup receipt, accepted financial event, ledger/projection/cursor atomically; retry recovers exactly once. On server outage, UI reconciles by command and Session revision. Source corruption fails closed; no invented price.
- Cross-tenant access 0; no raw credentials in QA reports, repo, logs or browser. Source rights registry checks storage/derived/display/export/commercial and geographic permission separately.
- Configure off-node encrypted backup of durable PostgreSQL and required immutable dataset manifests/source proofs in permitted scope; retention policy follows existing Alpha contract (seven daily plus four weekly generations unless rights require shorter). Rehearse restore to an isolated environment, including matching dataset pins, events and Session state. Backups must not be confused with extra live market archives.
- Reference-count/manifest-pin old source versions and required trade evidence. GC may evict recomputable caches, bounded scratch and expired exports after verification. No deletion of live dataset, rollback versions, ledger, orphan audit evidence or old Sessions without owner approval and exact reachability/hash proof.
- Disk pressure is admission control: refuse new ingestion/heavy job before exhausting space; preserve replay/transaction integrity.

## Proof must be recorded, not asserted

Benchmark on **actually verified, structurally published** source; record the 2015 Exness historical report as baseline (8,698,581 rows; Aug 10–Dec 31; 554.8MB CSV vs 3.004GB canonical indexed SQLite store; 565 events/sec read-only day), not comparable Parquet evidence. Verify any 2024 VPS snapshot/hash rather than relying on chat. Three trials for finalists, independent golden/parity/long-year seek+resume/0-trade+500-trade Session growth/1 vs 10 Sessions/hot-cold partitions, plus full lifecycle recovery. Report exact p50/p95 where sample counts support. NO benchmark run or live VPS inspection is claimed here.
