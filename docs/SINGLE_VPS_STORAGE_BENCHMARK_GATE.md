# RIKSORA — Single-VPS Shared Market Data: Benchmark, Storage and Upgrade Gate

> **Status:** Owner-requested evidence-first Codex execution brief / benchmark acceptance plan, 2026-11-04. This file is a **work order and test plan, not a benchmark result or production change authorization**. It does not supersede [Method/Session](TRADING_METHOD_SESSION_SPEC.md), [Market Data Standard](MARKET_DATA_STANDARD.md), [Execution Financial Contract](V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md), [Alpha Data/Ops Contract](V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md), [Architecture Blueprint](PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md), [Engineering Plan](ENGINEERING_MASTER_PLAN.md), [Current Phase](../AI_CONTEXT/04_CURRENT_PHASE.md) or [Test Commands](../AI_CONTEXT/07_TEST_COMMANDS.md). Do not bypass their gates. Any destructive migration, public cutover, unbudgeted network purchase or production-data deletion requires separate explicit owner approval.

## 0. Owner goal / non-negotiables

- **One VPS target:** 6 vCPU, 15–16 GB RAM, 200 GB SSD/NVMe, with **one active trader able to access every qualified period across the owner-approved 16 instruments × 5 years**. This means accessing one time slice at a time, **not** storing 80 instrument-years in memory, or implying all feeds/licensing/coverage have already been qualified.
- **One immutable versioned market dataset, shared by any number of eligible Sessions.** A user completing a one-year backtest must not generate a per-user copy of tick history, a per-user per-tick price log or redundant OHLC per-user. Session stores **Method reference, dataset/version/feed/profile pins, replay cursor, orders/financial events, immutable decisions, compact recoverable checkpoint, drawing/journal and derived statistics**.
- **Single VPS before a second VPS.** Add compute only after repeated measured saturation under safe accepted workload and after proving a local architecture/algorithm fix is not sufficient. Add object storage only if **measured durable dataset + justified replicas/backups + headroom** will not fit the safe local capacity (or if durable off-node backup is required). A planned 2 TB target is not a purchase justification.
- **Parquet is a candidate, not an acceptance shortcut.** Preserve exact precision, ordered/equal-time event grouping, canonical identity/hash/provenance/evidence, gap/rights flags, and the existing execution reducer; do not trade correctness for compression.
- **Never interpret structural publication as rights/precision/completeness certification.** No provider sample may be relabeled or redistributed just because it passes a benchmark.
- **No OCO, no auto-cancellation of untriggered pending orders.** Jump-to-Next-Event stays one button, fixed 72 elapsed UTC hours, and is semantically identical to chronological replay.

### Exactly sixteen target symbols (founder-approved)

`AUDUSD, EURGBP, NZDUSD, USDCHF, AUDJPY, CADJPY, EURUSD, GBPUSD, NZDJPY, USDCAD, CHFJPY, EURJPY, EURNZD, GBPJPY, USDJPY, XAUUSD`.

## 1. What is actually proven already (do not replace with synthetic claims)

**Observed private Exness XAUUSDm 2015 evidence** in the preserved [V22-C/V22-D report](https://github.com/Obbiiee/Back-test-lab-project/blob/codex/cp6a10-postannual-handoff/docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md): `554,761,330` raw CSV bytes, `8,698,581` source quotes, covered **2015-08-10 to 2015-12-31** (not full 2015), `3,004,055,552` bytes for the indexed SQLite content-addressed canonical dataset store (including indexes/metadata), `3,034,378,240` bytes with benchmark logs. That is **5.41× CSV size**, with richer canonical evidence than the source CSV, not a like-for-like compressed-column comparison. One-day bounded replay observed `87,859` events / `48,131` groups in `155.394987` seconds (**565.39 events/s**), **execution=false**. Thirty-minute actual-source cold Session resumes took about **1.98–4.46 seconds**, not evidence of one-year cold resume. Source coverage, rights, equal-time ordering and precision limitations remain explicit.

**Main repo (inspected 2026-11-04):**
- `backend/ticks/storage_v2.py` is a bounded indexed **SQLite/zlib content-addressed** dataset store, not a production Parquet market reader; includes identity indexes and private caches. `backend/ticks/benchmark_v2.py` is an actual CSV/SQLite ingestion/access benchmark CLI, not a Parquet AB harness.
- `backend/execution/research.py` and `backend/execution/postgres.py` pin `datasetId/datasetVersion` per Session and store financial ledger/revisions; they **do not clone the original market dataset** per Session.
- `backend/ticks/timeline_v2.py` presently persists **per-Session position log and advance log** in `timeline.sqlite`; `backend/execution/postgres.py` INSERTs a snapshot into `btl.tick_checkpoints` for **every command**. This may grow substantially during long replay. `backend/execution/historical.py` currently assumes **Exness XAUUSDm**, so multi-feed catalogue is not proven on the main historical runtime.
- In the isolated `codex/cp6a10-postannual-handoff` branch, opt-in `shared-source-v1` removes the Session position log, but `__reconstruct` replays the durable advance chain from the Session start on cold resume. **Less disk can mean more CPU**; do not select this mode before measuring both. The main ResearchApplication still constructs IndexedTimelineCache without selecting that opt-in mode.
- Branches such as `codex/columnar-storage-probe-20261024`, `codex/compact-writer-20261026`, and `codex/cp6a10-postannual-handoff` are audit inputs, **not proof their designs are merged, production-active or faster**.
- The user also references an annual 2024 dataset and published/verified serving snapshots on the VPS. **Neither current VPS disk inventory nor exact 2024 published-archive identity, measured size, rights, hashes, or performance is observable from this GitHub-only audit.** Codex must verify on the VPS before choosing or testing any source. Do not assume older historical doc numbers describe the active 2024 host.

Technical reference docs: [Arrow filtering/row-group skipping](https://arrow.apache.org/docs/python/parquet/parquet.html); [DuckDB remote Parquet I/O / EXPLAIN ANALYZE](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads); [DuckDB memory/spill guidance](https://duckdb.org/docs/current/guides/performance/my_workload_is_slow); [NautilusTrader Parquet catalog](https://nautilustrader.io/docs/latest/concepts/data/), [streaming BacktestNode chunk_size](https://nautilustrader.io/docs/latest/concepts/backtesting/apis-and-runs/). These are **patterns and tunable candidates**, not RIKSORA benchmark receipts; never import a whole external engine merely to read Parquet.

## 2. Mandatory safety / source-publication preflight

**First actions on Codex's actual machine/VPS are read-only**:
1. Record current UTC timestamp, git branch/commit/status, CPU model and quota, memory/swap, filesystem/mount disk usage, process list and current PostgreSQL size. Inventory source file(s), canonical published dataset(s), every snapshot/archive, WAL, cache and QA-output directory by *exact path and measured bytes*. Record the authorization, owner and intended meaning of each location; never assume three similar 21-GB files are byte-identical.
2. Identify **which dataset is truly structurally PUBLISHED** by reading the existing publication receipt/manifest/datasetVersion/source SHA/checksum/rights classification; verify the receipt and source/serving artifact identity without modifying publication state. The **2015 full supplied file is structurally published** in historical evidence; the **2024 VPS snapshot is only eligible if the current machine independently proves it**. Record coverage start/end and completeness status as distinct fields.
3. Confirm `root`, source, any previous known-good rollback archive, and user Session stores are protected. Hash the immutable dataset and log stable file metadata before/after tests; no in-place compaction, WAL checkpoint/mutation on live read-only snapshots, rename, deletion, chmod, re-ingestion or provider payment. Respect licenses/rights. Avoid unsafe full-disk scans during active replay; schedule or throttle with actual system capacity.
4. Verify **real free SSD capacity** and set a strict bounded scratch quota *before* creating derivatives. If a full-format candidate cannot be safely written without crossing the existing <=80% disk gate, first test slices; **do not buy storage just to run a benchmark**. Use a separate isolated QA directory and database; no production credentials in report/Git.
5. Make a versioned **dataset passport**: instrument, provider/raw symbol, datasetId, datasetVersion, immutable hashes, number of events, start/end UTC, timestamp precision, bid/ask units, quote-side fidelity, equal-time sequencing, gap/diagnostic evidence, contract/tick/lot profile and rights class. Missing/UNKNOWN remain UNKNOWN.
6. If no published dataset can be authenticated **STOP with SOURCE_NOT_VERIFIED**, preserving everything. Synthetic cases may support tests but cannot replace the promised real-data benchmark.

## 3. Benchmark candidates — prove before choosing

All read paths must implement the **existing IndexedTickDataProvider/controller boundary** or a versioned adapter with exact equivalence; retain golden wire/event hashes, not an alternate financial calculator.

| Candidate | Physical storage | Read path | Why test |
| --- | --- | --- | --- |
| A — baseline | existing published canonical SQLite/zlib V2 | existing DiskTickProvider/IndexedTickTimeline | Actual correctness baseline, size, read/seek, memory, write amplification |
| B — compact experiments | only existing isolated compact/log/shared-source opt-ins after review | existing provider/execution reducer | Measure disk saving vs resume/CPU tradeoff |
| C — columnar | immutable Parquet with exact fixed-point integer Bid/Ask/timestamp/ordinal, sufficient evidence/sidecars | bounded PyArrow Dataset/ParquetFile reader + adapter | Candidate fast selective read and smaller bytes |
| D — analytical reference | **same Parquet files**, no materialized extra DuckDB database | DuckDB `read_parquet` range query / profiling | Compare query/read amplification, not market fill engine |

**No second canonical market store per user**. Sidecar metadata/manifest/evidence may be shared per dataset/version, but **must remain independently integrity-verified**. No converting event precision to float, dropping duplicates/ties/quality flags, silently sorting untrusted same-time records or reconstructing unsupported broker execution semantics.

### Stage B0: representative original data before full conversion

Use only **contiguous windows extracted from a truly published original dataset**, provenance-bound to its immutable hash: busiest observed day, ordinary day, quiet day, weekend/session closure, many equal-time quotes, known gap/diagnostic window, random month-end and near dataset edges. Include >1 month if the published source permits; never synthesize prices and call them published data. State the actual source span.

Sweep on those windows:
- `Parquet ZSTD` levels 1, 3 and 6, plus one fast codec baseline such as Snappy.
- Row groups 32K / 64K / 128K / 256K, preserving row-group `ts_ns` min/max and source-order semantics.
- Compare **year-partition vs month-partition** only where the observed source actually spans multiple months. Small-file overhead, number of objects, range amplification and cold seek count matter. Do not assume one Parquet file/year wins.
- Column schema: `ts_ns int64`; Bid/Ask as exact price-scale integer or equally exact decimal; `source_ordinal`/trusted-sequence; quality/diagnostic references; feed/source identity and version in immutable registry, with event-local fields sufficient for exact reconstruction. Compression must not erase required evidence.

After 3 deterministic runs of each viable candidate (record order/thermal state; ABBA when comparing CPU), eliminate variants that violate correctness/safety. **Advance only the Pareto finalists** to the full published dataset where safe. Stop if scratch disk budget would be exceeded.

### Stage B1: verified replay / API / reader performance

For baseline and finalists, test on identical pinned source/version/profile and fixed replay commands, cold-ish new-process + warm repetitions (do not claim OS-cold cache unless actually controlled and safe):

1. Random seek: near dataset start/middle/end; 1 hour, 1 day, 72 hours, 1 month bounded scan; interval crossing month/file boundary; EOF; equal-time/tie crossing.
2. Jump-to-Next-Event, exactly 72h UTC: **no event**, first pending activation, first active SL/TP, multiple independent pending orders, overlapping order conditions, market closure, missing/ambiguous evidence, dataset EOF. Compare **one-click canonical event/ledger state and cursor** against normal exact-tick chronological reference. No OCO or pending expiry.
3. One full **published year only if it is actually published and safe**; if only Aug–Dec 2015 is qualified, benchmark that exact span and label it **PARTIAL_YEAR**, not YEAR_PASS. 2024 if published must have its own immutable version and year-scoped report.
4. **0 orders vs authored 100 and 500 orders**: the 100/500 order experiment may use **isolated, explicitly SYNTHETIC test commands**, while the market read path uses actual published ticks; do not fabricate real-data fills if the provider evidence forces UNRESOLVED.
5. Repeat for 1, 2, 5, 10 independent QA Sessions referencing **one dataset version** to measure per-Session storage delta; record shared-data duplication count. These are load probes, not justification for production concurrency until the actual host is certified.
6. Kill/restart the **isolated worker/QA DB** after committed checkpoints and compare exact canonical hashes, pending orders, balance, replay cursor, event counts and idempotent retry. Benchmark *long-history cold resume* separately; the existing historical 30-minute resumes do not qualify a 1-year claim.
7. For **rarely used instruments**, after actual data exists: simulate 1 frequently used instrument and 15 cold instruments, access cold instrument/month randomly and return to the hot one. If only one real instrument is published, run this exact test on different months/versioned partitions **as a proxy**, label `COLD_PARTITION_PROXY`, never 16-real-pair certification.
8. Test bounded in-process cache sizes, evictions and cache-miss latency. **No per-user canonical candle/tick duplication;** derived M1/other timeframes cached once per source/version/timeframe where justified. Precompute/keep only access patterns that beat on-demand generation or were measured cheap. Never cache unrestricted future market data in browser.
9. Evaluate object storage only by **measured what-if / sanctioned free-safe remote test**. For an actual S3 candidate profile requests, bytes transferred, range-read inefficiency, first-byte latency, egress/transaction fees, cold object retrieval and local hot-cache hit ratio. No paid purchase or moving/publishing source data without separate owner approval.

## 4. Report schema and repeatability

Every run has a durable local **non-public JSON/CSV report** with:
`run_id, timestamp_utc, host_spec, cpu_limit, ram, disk_free_before_after, source_id/hash/version/span/event_count/rights, exact git_sha, package_versions, storage_layout, codec, row_group, partition_size, engine_version/profile_hash, workload_id, repetition, cold_cache_claim, published_not_synthetic, wall_ns, cpu_ns, peak_rss_bytes, process_and_host_ram, swap_bytes, disk_read_bytes, disk_write_bytes, network_in_out_bytes, s3_request_count, dataset_bytes, index_bytes, metadata_bytes, session_log_bytes_delta, postgres_db_wal_bytes_delta, temp_bytes_peak, checkpoint_count, first_response_latency_ms, seek/jump/resume_p50_p95_p99, ticks_per_s, user_actions, canonical_result_hash, parity_pass, unresolved_status, errors`.

- Record ordinary OS page cache separately from measured Python/SQLite/Parquet cache. Produce a stable manifest of candidate contents. Never present source/raw counts or vendor performance estimates as host measurements.
- Store reports in ignored QA directory, with a sanitized Markdown executive summary + hash/aggregate measurements in repo only where rights and security permit. No source rows/quotes/customer ids/credentials/dataset URLs in Git.
- Run **at least three controlled repetitions per finalist**, compare one independent baseline after every optimized run (ABBA where practical), include failed runs, report median and p95/p99 only where sample size supports those statistics; for small samples disclose min/max/raw values, don't manufacture p99.
- Stop at a defined iteration budget: baseline → candidate → measurement → one focused optimization → repeat → audit. If still failing, **HOLD** with evidence and next bounded experiment. No unlimited loops, production disruption or optimistic result selection.
- A "faster" result with different canonical event/financial hash, future leakage, missing diagnostics or incorrect grouping is a **FAIL** regardless of disk savings.

## 5. Resource, correctness and UX gates (no invented PASS)

**Hard correctness (all compulsory, zero tolerances):**
- 0 market-data canonical identity/hash discrepancies; 0 missing/misordered event/group, no changed Bid/Ask precision or rights/quality interpretation.
- 0 changed accepted financial ledger/state hash on same deterministic input; no unexplained quote, cash, position, Protocol or pending mismatches, no look-ahead.
- No generated **per-user tick archive** and no permanent **per-user per-tick reveal/position materialization**. Market file physical copies must be enumerated, justified as *temporary QA* or *required recovery*, and removed only after evidence + owner-approved safety.
- Recoverable checkpoints are cryptographically pinned, exact-replay safe, idempotent and retained according to the immutable financial record policy. A bounded **checkpoint snapshot strategy** may be proposed, but must not silently prune audit events or break restore/provenance.

**Resource gates (existing Alpha contract still controls):**
- Peak node RAM **<=85%** of reference node under applicable certified workload, **disk utilized <=80%**, bounded worker/job/cache/file handles, no OOM/swap thrash, 0 duplicate/lost financial events.
- Preserve [Alpha p95 seek/ack targets and 20× ten-session reference gate](V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md) for that workload. **One-user full-year and long-history resume require new measured acceptance**; the existing ten-session synthetic probe, short cold resume or partial historical source are not substitutes.
- For single-VPS MVP, objective is availability of the full *qualified* 16×5 catalog via bounded working-set reads, **not** all data in 16 GB memory. Measure p50/p95 from enough samples, not one selected screenshot.
- Report **storage per million actual tick events**, **per-Session metadata/event/checkpoint growth per million revealed tick events**, and **cold-resume latency vs revealed-prefix length** (30min, day, month, actual year if published). The Session storage growth should follow *user actions and bounded recovery artifacts*, **not market tick count**. Constant factors and any unavoidable replay-prefix work must be disclosed.
- No added permanent data copy solely for DuckDB. `CREATE TABLE AS read_parquet` or saved analytical tables would materialize another full store; require a separately justified use case. Spill/temp files are strictly quota-bound.

## 6. Capacity and purchase gate: KEEP / OPTIMIZE / ADD STORAGE / ADD COMPUTE

**KEEP 1 VPS** when benchmarked single-trader reads, jumps, session recovery, source quality and budgets pass, peak RAM/disk remain within gate, and qualified catalog fits active safe storage plus the proven data growth and backups. Unused instrument data can be cold: **do not pin all 16 instruments in SSD cache**.

**OPTIMIZE WITHOUT PURCHASE** if any candidate data path writes redundant tick/position logs, repeatedly reconstructs all history from Session start, uses unbounded cache, downloads full remote Parquet to open one month, duplicates candles by user, or permanently stores full CSV + canonical SQLite + Parquet versions without an approved retention reason. Measure before/after, preserve rollback/reference hash.

**ADD STORAGE only if** a reproducible storage accounting report proves:
- Immutable admitted market catalogs plus mandatory rights-compliant retained originals/backups, PostgreSQL, system files, peak QA/import scratch and a safe working-set cache **cannot fit under 80% of usable SSD**, **after** eliminating unwarranted copies and tuning physical layout; **OR** an off-node durable backup/recovery requirement is unmet (independent of dataset size).
- Compare **local disk expansion vs object storage** by actual monthly dollars including storage, requests, retrieval, transfer, egress, backup/retention and latency, under realistic hot/cold access. Buy only measured required capacity plus controlled headroom, **not 2 TB by default**.
- If object storage wins: immutable canonical Parquet there, LRU/size-capped SSD hot cache locally, row-group/range reads, bounded S3 requests. Cold pair available on demand, not permanently resident. Do not claim access without dataset rights.

**ADD VPS / COMPUTE only if** the same **actual target host** repeatedly misses hard latency, throughput, RAM or queue/SLO goals **after** indexed/bounded reading, cache, resource limits, producer/consumer decoupling and profiling prove no high-value single-node remediation remains. Document exact bottleneck (CPU, RAM, I/O, DB, workers, network), load (concurrent sessions, requests, duration), p95/p99, cost and expected/observed effect. Dataset size itself is not a CPU-upgrade trigger.

**INCONCLUSIVE / HOLD** if data versions/rights are missing, year coverage isn't published, OS-cache condition is unproven, result hashes mismatch, host hardware/throttling changed, too few replicates, or production safety cannot be guaranteed. Never convert absence of evidence into procurement authorization.

## 7. Concrete bounded Codex execution plan (execute sequentially, report each gate)

**C0 — inventory only**: inspect repo main/branches, operational phase and actual VPS published dataset. Produce exact source + disk map, immutable evidence pins, host envelope. STOP if SOURCE_NOT_VERIFIED or safety budget fails. No code changes.

**C1 — baseline**: run existing `backend/ticks/benchmark_v2.py` only in an audited read-only/isolated mode compatible with published version; audit CLI implementation before invoking. Capture storage/endpoints/long-history replay/cold resume/Session growth. Do not re-ingest the whole source merely to obtain a baseline, never mutate the accepted published store.

**C2 — candidate bake-off**: build an **isolated experimental Parquet reader/writer** respecting the existing dataset provider interface and original precise canonical evidence, then test named windows/variants; support streaming on one VPS under scratch quota. Preserve current engine/financial reducer. Test both PyArrow and DuckDB as **readers**; never call DuckDB the execution engine.

**C3 — full qualified source**: compare finalists on **the exact immutable published source** (2015 complete-supplied Aug–Dec, 2024 only if verified as published on host). Record full bytes, read/seek/day/72h, end-to-end 0-order replay where quality permits, integrity parity, cleanup/scoped user state.

**C4 — session overhead and cold restart**: 0/100/500 action trials (synthetic financial commands clearly labeled), 1/2/5/10 Sessions, same dataset pins, long-prefix cold resume, durable recovery and per-user disk/WAL growth. Profile/rework session position/advance log and checkpoint compaction **only if** tests prove problem; no deleting required provenance.

**C5 — hot/cold catalog**: cold partition/proxy and real rare instrument if published, LRU eviction, no pinned all-pair RAM or per-user tick cache; test network/S3 costs without billing. Verify no unexpected full-object download.

**C6 — repeated independent audit**: rerun goldens, exact hash comparisons, code review, full relevant backend/frontend/DB/browser gates, quota/OOM/disk pressure, restore, original published source hash and working-tree preservation; repeat finalists three times and report both failures and success. Do not lower acceptance or alter frozen contract to make a candidate pass.

**C7 — procurement verdict**: one-page `KEEP_1_VPS`, `OPTIMIZE_FIRST`, `ADD_STORAGE`, `ADD_COMPUTE` or `HOLD` with measured alternatives, effect sizes, actual costs where available, release blockers, exact missing dataset symbols, and owner approval requested only if purchase/deployment is truly necessary. No purchase, deletion or production cutover.

**Definition of Done:** all **C0–C7** complete with reproducible local/private receipts, dataset hash pins, benchmark comparisons, complete safety/financial parity and an honest recommendation. If a gate is blocked, deliver precise evidence and the smallest safe next authorized task; **do not fabricate completion**. Commit benchmark harness/test changes only to a reviewed isolated branch and follow normal repo/AI bundle/QA/PR gates. Do not merge or deploy automatically.

## 8. Codex kickoff instruction

> Read `docs/SINGLE_VPS_STORAGE_BENCHMARK_GATE.md` and its referenced canonical specs first. This is an **evidence-first measurement task**, not a right to change production. Work through C0–C7 in order against the **actually structurally published, independently verified dataset** on your authorized host, not synthetic substitutes or unverified 2024 copies. Prove no per-user tick cloning and bounded RAM/disk; compare existing SQLite V2, isolated compact/shared-source branch candidates, PyArrow Parquet and DuckDB direct Parquet without rewriting the financial engine. For any proposed optimization produce hash-identical tests, actual disk/CPU/latency results, cold restart and uncommon/cold-partition access results, and keep complete failure history. Re-run controlled benchmarks. Produce the one-page purchase/upgrade decision and STOP for owner approval before purchases, deletion, production migration or public data use.
