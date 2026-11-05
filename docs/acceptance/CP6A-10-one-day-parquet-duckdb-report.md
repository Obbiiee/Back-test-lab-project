# CP6A-10 — one-day SQLite / Parquet / DuckDB benchmark

**PASS for this exact one-day QA gate. STOPPED pending owner review.** This is not annual format certification, production readiness, commercial data admission or concurrency acceptance. The previously accepted annual evidence remains unchanged.

## Workload and integrity

All five cases processed137,108 canonical XAUUSD timestamp groups for2024-01-02UTC using the same existing trading engine, fixed profile/schedule, Session/Workspace/Command identities in separate QA databases and batch256 shared-source mode. Each produced86 completed simulated trades,4 cancelled orders,777 events, ending balance9976.38 from10000 and gross P&L -23.62. Fee/slippage/latency assumptions remain NONE/NONE/ZERO. All172 entry/exit fills matched original source. Unknown coverage limitations remain explicit; no gap quotes were synthesized.

Canonical transcript, semantic financial-event, financial-state, full final-state, cold-resume-state, event-transcript and receipt-ledger hashes match across all five cases. Independent verification for every candidate traversed original canonical SQLite. Cold recovery and idempotent retry PASS. Complete hashes and per-stage metrics are in the adjacent evidence JSON.

## Results

Wall below includes fresh process/Session/PG initialization, mandatory source admission, replay, cold recovery, independent verification and normal PG shutdown. It excludes shared format construction and standalone read/seek probes, which are recorded separately. One financial run per candidate; timing differences are observations, not statistical speed claims.

| Case | Wall s | CPU s | End-to-end groups/s | Candidate peak RSS MiB | Warm seek p50/p95 ms |
|---|---:|---:|---:|---:|---:|
| SQLite/sqlite | 712.611 | 685.300 | 192.4 | 212.24 | 104.8/120.4 |
| PyArrow/single | 658.317 | 636.639 | 208.3 | 245.44 | 169.4/196.1 |
| PyArrow/daily | 663.299 | 643.212 | 206.7 | 246.37 | 187.2/209.3 |
| DuckDB/single | 651.463 | 629.293 | 210.5 | 260.62 | 263.9/301.1 |
| DuckDB/daily | 672.361 | 651.212 | 203.9 | 262.05 | 259.6/308.4 |

RSS is maximum observed per-candidate-process VmHWM, excluding common supervisor; cgroup accounting includes supervisor, all PG processes and filesystem cache. Sampled per-case cgroup peaks were approximately768.5MiB under MemoryHigh768MiB, MemoryMax1GiB, swap0 and aggregate CPUQuota100%. No OOM. Host early-stop reserve was32.5GiB; observed minimum free disk 35.998GiB. No concurrency or longer-range test was started.

Physical Single/Daily Parquet allocations were9,441,280/9,457,664bytes, including bounded next-day halo for correct source position/lookahead semantics. These two filesets were reused by Arrow and DuckDB, not copied per engine. Per-case retained QA roots were76.32–77.21MB versus the prior one-day76.66MB planning proxy. Original canonical archive22,926,401,536allocated bytes remains shared and protected; new Parquet outputs increase host storage while the source is retained.

## Interpretation and limits

- CPU utilization was96–97% of one core. Existing controller, PostgreSQL persistence and independent verification dominate total time; reducing raw read time alone does not predict the full application gain. Timing stages are nonexclusive where noted in each original report.
- DuckDB Single had the lowest observed full-run time, only about1% below Arrow Single, with higher candidate RSS. SQLite had lower measured warm random-seek latency than either Parquet adapter. The adapters validate/materialize bounded row groups; this cost and caching granularity matter more than query-only seek numbers.
- One day has one main daily partition plus a small halo. It does not demonstrate multi-day partition-pruning advantage or certify an optimal row-group size. No production layout winner is declared.
- Process-cold open, actual worker-process cold recovery and warm reads are measured. Device-cold performance is NOT certified; no global cache eviction was used.
- User cgroups do not delegate io controller. I/O is sampled from /proc for all cgroup processes; rapid exits may be undercounted. Host df growth includes unrelated host writes; filesystem block allocations are reported separately.
- Parquet supplies tick pages/seeks; canonical SQLite still supplies frozen publication/sidecar metadata, mandatory qualification and the independent financial oracle. This is not standalone production Direct Parquet authority.
- Source rights remain UNKNOWN; execution eligibility NOT_GRANTED; classification EXPERIMENTAL — UNVERIFIED SOURCE — SIMULATED EXECUTION.

## Retained failures and validation

An initial instrumentation preflight found missing io.stat before any Session creation; no infrastructure setting was changed. A first DuckDB launch later stopped at its last published progress revision86/group16,717 because PG environment reset removed the optional reader site-packages path. Its data, logs and checkpoint remain retained; that partial Session was not financially accepted. One launcher-only repair restored the path, with a regression that failed before and passed after the fix. A fresh bounded DuckDB-only retry produced the two successful results above; no successful SQL/Arrow gate or annual replay was rerun.

Validation:31 focused test executions PASS in the optional QA environment; independent Node6golden vectors x3PASS. Optional-reader tests explicitly skip when optional packages are absent from the ordinary application environment; actual benchmark services require and exercised the dependencies. No application dependency, engine/reducer, API, UI, production configuration or market source changes. Browser validation is exempt because only private QA tooling and reports changed. Repository/bundle/publication receipts are retained under the private validation directory.

## Projections and next gate

Actual format density projects Single/Daily data-only outputs to about0.048/0.048GiB for the observed7-day group count,0.196/0.196GiB for30days and3.605/3.611GiB for the accepted annual group count. These are not measured longer-range outputs and exclude PG/evidence/scratch/margins. Extra position-preserving columns make this estimate different from the earlier sparse screening prototype.

Group-based replay+verification projections, holding measured setup fixed, span about0.62–1.34hours for7days,2.43–5.38hours for30days and43.97–98.28hours forannual across reader/scenario choices. These are scenario arithmetic, not confidence intervals or resource acceptance. Annual high scenarios exceed72hours. The current one-day legacy workload cannot be naively repeated under4096cumulative orders; an accepted bounded schedule, archive/streaming recovery/verifier and fresh measured capacity plan remain mandatory.

Recommend a separately approved bounded reader-cache/pruning investigation or contiguous multi-day gate after fresh storage/RAM preflight. Do not infer6worker or100user capacity. STOP:7days,30days,annual and multiworker require new approval.

## Evidence

- [Machine-readable metrics and hashes](CP6A-10-one-day-parquet-duckdb-evidence.json).
- Private baseline/Arrow: `/home/riksora/riksora-qa-evidence/pqday-20261105/`.
- Private successful DuckDB/cohort report: `/home/riksora/riksora-qa-evidence/pqduck-20261105-r1/one-day-comparison.md`.
- Retained failed DuckDB attempt: `/home/riksora/riksora-qa-evidence/pqduck-20261105/`.
- Protected annual report SHA256: `cdc65e4c7fd7e65e85fac38726472c2ad92925c502afc2f08482a01b897fc831`.
