# Real-month engine QA on Compact Tick V2 (XAUUSD 2024-02), 2026-11-25

Status: **IMPLEMENTATION REGISTER / QA REPORT, not an architecture authority.** Private QA only. The data has rights class **UNKNOWN**: nothing here is commercial evidence, and **no tick, price or timestamp of the data is stored in this repository** (only counts and timings). Tool: `backend/tools/claude_exp/real_month_bench.py` (existing QA tools folder; no new engine, no new storage format, no permanent dataset copy; the temporary canonical stores used for the baseline were deleted afterwards).

Labels used below: **MEASURED** (actual run on this host), **HYPOTHESIS** (not measured), **NOT RUN**.

## 1. What was tested

| Item | Value |
|---|---|
| Data | One real month, XAUUSD 2024-02, Compact Tick V2 (`BTL-COMPACT-TICK-2`, `authoritative: false`, derived), 2,126,396 ticks, 7.79 MB, source recorded as Dukascopy, rights UNKNOWN |
| Reducer | The product's `execution/observed_kernel.apply`, unchanged. One financial reducer. |
| Baseline path | Temporary canonical store (`DukascopyCsvIngestion` -> `DatasetBuilder`) -> `IndexedTickTimeline` -> `observed_kernel.apply` (what the repo's QA baseline uses) |
| Direct path | `open_compact` on the real Compact V2 directory -> `AdmittedSource` -> `ClaudeSession` -> the same `observed_kernel` functions. `ClaudeSession` computes no fill or money amount itself; it only supplies the tick source and the event search (skipping is allowed only over spans proven to contain no event the reference loop would act on). |
| Strategy | Scripted trader of `tools/claude_exp/common.drive` (`mix=True`): market, limit, stop, manual close, cancel, with TP and SL; one live order at a time; 300 s step. Same strategy on both paths. |
| Profile | v1 = `CONDITIONAL_OBSERVED_TICK_SIMULATION` (old QA profile); **v2 = `HISTORICAL_TECHNICAL_TICK_SIMULATION_V2`** (the product's model for rights-UNKNOWN observed data; QA placeholder qualification digest, **no qualification is claimed**). Order archive (`QA_ORDER_RETENTION_V4`, the product rule "no 128 cumulative order cap") on where stated. |
| Host and budget | VPS1, 6 vCPU AMD EPYC, 15 GiB RAM, no swap. Each phase in its own process under `systemd-run --user --scope -p CPUQuota=100% -p MemoryMax=6G`, `nice -n 10`. One measurement at a time. OS guards (MemAvailable, swap, disk) in-process. Production was not touched; `riksora.com` answered 200 in 36-49 ms before and after. |

**Engine-only versus complete product.** Everything below is **engine-only** (in one Python process, no API, no queue, no PostgreSQL, no worker). A **complete product test of real data was NOT RUN**: the product worker refuses real data without pinned rights evidence, and the QA synthetic pin would mislabel real ticks. The product path was not changed to allow it.

## 2. Can the engine read Compact V2 directly? (item 1) - MEASURED: yes

| Step | Result |
|---|---|
| Open + manifest-hash pin | 0.002 s |
| SHA-256 of all files | 0.02 s |
| Deep verification (order, ordinals, groups, crossed) | 0.12 s |
| Decode all 2,126,396 ticks to arrays | 0.36 s (5.93 M ticks/s) |
| Whole phase | 0.50 s wall, 268 MB peak RSS (cgroup 240 MB), 7.8 MB read from the SSD (cold), 0 written |

No conversion and no second copy of the dataset are needed for this path.

## 3. Full-month run, direct path (items 2-3) - MEASURED

| Configuration | Run time | Ticks/s (run only) | Peak RSS | SSD write | Orders accepted | Fills | UNRESOLVED |
|---|---|---|---|---|---|---|---|
| v1, no archive | 6.15 s | 345,506 | 366 MB | 0.5 MB | 101 | 191 | **1** (`UNRESOLVED_OBSERVED_SILENCE`) |
| v2, no archive | 201.17 s | 10,570 | 364 MB | 1.0 MB | 128 | 230 | 0 |
| **v2 + archive** | **12.61 s** | **168,584** | **364 MB** | 8.0 MB | **1,412** | **2,391** | **0** |

Single core (99.8% of one CPU), cgroup memory peak 333 MB. SSD reads were 0 on repeat runs because the 7.8 MB file was in the page cache; the cold read is the 7.8 MB in section 2.

v2 + archive events: 1,412 ORDER_ACCEPTED, 1,196 ENTRY_FILL, 1,195 EXIT_FILL, 115 EXIT_REQUESTED, 216 ORDER_CANCELLED, 22 STALE_QUOTE, 2,638 DATA_GAP_LIMITATION; one order still ACTIVE at the end of the month; 2,450 exact groups and 2,123,946 skipped groups proven event-free, 7,361 jumps.

## 4. UNRESOLVED and REFUSED diagnosis (item 5) - MEASURED

1. **v1 UNRESOLVED.** Exactly one order ended `UNRESOLVED` with code `UNRESOLVED_OBSERVED_SILENCE`. Cause (code, `advance_through`): under the old model, a live order across a silence longer than `maxObservedSilenceNs` (60 s) is marked UNRESOLVED instead of guessing the missing period. After it, the scripted trader stops opening orders, which also explains why v1 produced only 101 orders. This is the conservative behaviour required by "insufficient evidence must stay explicit", not a defect.
2. **v2 has none.** The same gaps become `DATA_GAP_LIMITATION` (14 in the month for the first scripted run, 2,638 with 1,412 orders) and `STALE_QUOTE` (the stale quote basis is dropped); no order is unresolved and nothing is invented. This is the product's designed model for observed data of unknown completeness.
3. **The earlier "order became UNRESOLVED after the first fill" on real slices** (14 Nov report) is consistent with cause 1 (old model plus a silence). I did not re-run those slices, so for them this is **HYPOTHESIS**; for this month it is proven.
4. **202 s on "v2, no archive" is a harness artefact, not engine speed.** 5,360 events are `REFUSED_STATE_LIMIT` on `orders`: the hot state holds at most 128 orders, the trader opened exactly 128, then retried an `OPEN` every 5 minutes and each refused command costs about 35 ms (full state validation). With the archive on (the product rule), the same month takes 12.6 s.

## 5. Canonical baseline and parity (item 6) - MEASURED on windows, full month NOT RUN

| Window (first N ticks) | Canonical reducer | Direct path | Parity |
|---|---|---|---|
| 20,000 ticks, v1, no archive | 18.1 s (1,106 ticks/s), 88 MB | 0.14 s (146,891 ticks/s) | semantic events, balance, orders, UNRESOLVED, quote basis, cursor: **equal**; 23 fills |
| **300,000 ticks, v2 + archive** | **281.8 s (1,065 ticks/s)**, 102 MB RSS, 147 MB written | **1.11 s (271,342 ticks/s)** | semantic digest **identical** (`74527a5a...`, 527 events); balance, realized gross, orders, last-observed, next group, quote basis, unresolved: **equal**; 311 fills, 174 orders |
| Jump-driven trace replayed on the canonical reducer (300,000 ticks, v2 + archive) | 203.8 s | recorded run | **semantic events equal**; 1,037 trace steps, 107 orders, 210 fills |
| SEEK across 300,000 ticks, nothing live | 263.0 s | 0.0008 s | cursor, last-observed, through, quote basis (bid, ask, time), balance, orders, semantic events: **equal** |

The raw event lists differ only by the 1,156 (300k run) / 1,172 (SEEK) non-financial `REPLAY_ADVANCED` progress records the canonical timeline emits and the direct path does not. **A product integration of the direct path must reconcile that bookkeeping record (ledger and hash chain) first; that is an owner/contract decision, not made here.**

**Full-month canonical baseline: NOT RUN.** A first attempt was cut off when its session ended after seconds (no result). **HYPOTHESIS** from the measured rates (ingest 1,984 ticks/s, reducer 1,065 ticks/s): about 18 min ingest plus about 33 min reducer for 2.13 M ticks, one core. Month-scale parity therefore rests on the 300,000-tick windows plus the full-month direct runs, not on a month-long canonical run.

Canonical ingest cost that the direct path does not pay (300,000 ticks): 152.8 s, **2,050 MB written to the SSD**, 92 MB final store (13.8 MB CSV in).

## 6. Jump, SEEK, checkpoint and resume on the full month (item 4) - MEASURED, direct path, v2 + archive

| Test | Result |
|---|---|
| SEEK across the whole month, nothing live | 0.001 s; all 2,126,396 groups consumed |
| Jump-driven strategy (advance to `next_event_ns` while an order is live), market/limit/stop/close/cancel, TP/SL | 5.63 s (377,704 ticks/s); 1,473 advances, 827 commands, 737 orders, 1,417 fills, 1,036 jumps, 0 UNRESOLVED |
| Checkpoint and resume | JSON snapshot at the month midpoint (854 KB, 5,115 log records), recovered in 0.05 s; **final result identical to the uninterrupted run**; independent `verify_by_replay` of 10,095 records in 13.07 s: pass; final snapshot 1.67 MB |
| Pending, market, SL, TP | exercised by the strategy on every run above and checked against the canonical reducer on the windows in section 5 |

Checkpoint and resume were measured on the direct path only. The canonical (product) checkpoint, including SIGKILL recovery, is covered by the repository's PostgreSQL tests on synthetic data (13/13 on 2026-11-25), not on real data.

## 7. Where the time goes (item 7) - MEASURED (profile; proportions only)

`cProfile` of the canonical baseline on 20,000 real ticks (62.9 s profiled; profiler overhead makes absolute times about 3.5x slower than unprofiled):

| Component | Share |
|---|---|
| `contracts/canonical.py:_normalize` (canonical JSON normalisation), own time | 25.5% (10.5 M calls, about 527 per tick); 56% cumulative |
| `timeline_v2.advance_through` (read + verify groups and pages) | 66.6% cumulative |
| `storage_v2.read_page_v2` / `_check_position` / `_load` | 29.5% / 23.6% / 19.5% cumulative |
| `observed_kernel.apply` (the financial reducer) | 32.6% cumulative |

Reading: the slow part of the canonical path is **canonical JSON encoding and hash verification of every group** in Python, not the financial arithmetic. **No optimisation was made or proposed beyond this finding**; any change would have to keep the byte-identical canonical contracts.

## 8. What this does and does not establish

- **Proven (this host, engine-only, one real month, one pair, rights UNKNOWN, private QA):** the product reducer can be fed directly from Compact V2 with no conversion or dataset copy; on 300,000-tick windows it equals the canonical reducer (including Jump, SEEK, pending, market, SL, TP); the full month runs in about 13 s with 1,412 orders and 2,391 fills, 364 MB, one core; checkpoint and resume reproduce the uninterrupted result.
- **Prototype:** the direct path is QA tooling (`tools/claude_exp`), not wired to the product, the queue or PostgreSQL. Identity labels (`datasetId` and the like) were chosen by the harness, because the compact file does not carry the original `memberHash`.
- **Not proven / NOT RUN:** the complete product path with real data (worker, API, PostgreSQL, Journal, browser); a month-long canonical baseline; other months (the largest XAUUSD month in the folder has 9.4 M ticks, median 5.8 M); other pairs or instruments (the product has a XAUUSD profile only); more than one strategy or the real activity of a person; concurrency; rights, completeness and accuracy of the data.
- **Decisions for the owner, not taken:** making the v2 model the default for rights-UNKNOWN data (frozen financial contract); reconciling `REPLAY_ADVANCED` for the direct path; any source-admission or eligibility change that would let the website or the laptop stack use this data.

Commercial V1 stays BLOCKED.
