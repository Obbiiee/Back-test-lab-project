# RIKSORA — Compact Checkpoint V2 (QA only) — report 2026-11-15

Status: **PROTOTYPE, opt-in, QA-disposable.** Not promoted to the production path. Promotion and the frozen-contract deltas below need separate owner approval.
Environment: VPS riksora_vps1, branch `claude/dual-engine-v1-20261114`, cgroup 5 vCPU / 14 GiB, no swap, PostgreSQL 17 disposable cluster, synthetic financial-active ticks only (not commercial evidence, no data rights implied).
Financial reducer, fill rules, Bid/Ask, entitlement and immutable receipts: **unchanged**.

## 1. Format V1 vs V2

| | V1 (legacy) | V2 `BTL-TICK-COMPACT-CHECKPOINT-1` |
|---|---|---|
| Content | `{cursor, advanceTargets[]}` | constant-size: `eventsRevealed` (resume position), `advanceCount`, `advanceChainHash` (commitment to the schedule), `sourcePin` (manifest hash), last revealed group id |
| Step limit | `MAX_STEPS=256` (= 16,384 groups) | none from the checkpoint (limit was the schedule list) |
| Size growth | quadratic in total (every row carries the whole list) | constant, max 2,497 B per row |
| Resume | replays all targets, O(history); 1.94 s late at 4,096 ticks | starts at the manifest chunk holding the next event, validates it, proves position by rebuilding the last revealed group; 0.04 s early / 0.13 s late |
| Enablement | default | `BTL_TICK_CHECKPOINT_FORMAT=compact-v2` (opt-in, only for providers with `supports_index_resume`) |

**Recovery cost is bounded, not O(1):** `read_page(start_index)` scans the row-group index linearly, so cost grows with manifest/index size plus one chunk. It does not grow with revealed history.

## 2. Compatibility and migration (proven on disposable DB)
- V1 rows stay untouched and readable. A V1-restored timeline switches to V2 at its next accepted step (lazy migration) → mixed chain V1…V2; old rows are never deleted or rewritten.
- `tests/test_compact_migration.py` (2 tests, PASS): session with trades, partial exit, pending order and receipts migrated mid-life; result equal to an all-V1 control on normalised events, balance, orders, receipts. Second test forges the latest checkpoint row (wrong position) with triggers disabled: restore raises `ContractError` and writes nothing.
- `tests/test_compact_checkpoint.py`: equivalence with V1 acks, refusals (wrong source/hash, swapped manifest, wrong position, future position), size and cost checks, source admission.
- `tests/test_replay_run.py::DurableRunCompactCheckpoint`: durable queue + PostgreSQL + SIGKILL before/after commit, identical retry, Free-window bound, tenant separation, all with V2.

## 3. Tiered runs through API → durable queue → PostgreSQL → native worker (one Session each)
Control: V1 control exists only to 16,384; beyond that the control is a single-process chronological run in the same format (V1≡V2 equality is proven separately by the ack-equality and migration tests). `revisionEqual=False` is expected (different chunking of targets) and is not a financial difference.

| Ticks | Segments | Chunks | Run wall s | Worker CPU s | Peak RSS MB | Checkpoint max B | Checkpoint total | DB growth | WAL | Cold resume s* | Control equal / events equal |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2,048 | 2 | 33 | 4.1 | 0.6 | 135 | 2,497 | 70 KB | 0.69 MB | 0.23 MB | 2.7 | yes / yes |
| 16,384 | 3 | 257 | 25.0 | 6.0 | 209 | 2,497 | 498 KB | 2.0 MB | 1.4 MB | 13.4 | yes / yes |
| 65,536 | 7 | 1,025 | 71.4 | 22.6 | 216 | 2,497 | 1.97 MB | 5.4 MB | 5.3 MB | 13.4 | yes / yes |
| 131,072 | 13 | 2,049 | 148.9 | 47.6 | 219 | 2,497 | 3.93 MB | 8.4 MB | 10.9 MB | 14.8 | yes / yes |
| 262,144 | 28 | 4,097 | 337.3 | 110.5 | 222 | 2,497 | 7.87 MB | 14.6 MB | 22.0 MB | 13.6 | yes / yes |

*First segment after killing all worker processes (includes process start and about 2–3 s cold source load). Facts at every tier: balance 10000.7, 1 closed trade. V1 extrapolation at 262,144: about 300 MB of checkpoints (quadratic) and unreachable beyond 16,384 groups.

Findings fixed on the way (all in this checkpoint): the per-timeline O(dataset) source acceptance scan made 131k+ tiers fail with `create_session` EXPIRED; replaced by a once-per-source **offline acceptance record** (`BTL_SOURCE_ACCEPTANCE_DIR`, fail closed `REFUSED_SOURCE_NOT_ADMITTED` when set but missing; chunk hashes still verified on every read). Offline admission itself is O(N): 27.7 s at 65k, 127.7 s at 262k, run outside request deadlines.

## 4. Regression
170 touched-suite tests: 1 failure, `test_new_session_advances_journal_order_index_with_financial_events`. It fails identically at baseline `ab14259` (verified in a clean worktree), so it is not caused by V2. Cause: `f6ab2c3` intentionally moved the analytics projection to format 2 (exact-ratio totalR; head accepted 0/1/2 and upgraded on rewrite; `test_incremental_analytics` asserts format 2) but this test still expected 1. Expectation updated to 2 from that contract; 19 tests PASS.

## 5. Delta proposal (frozen-contract changes needed to promote V2 — NOT applied to production path)
1. New checkpoint artifact `BTL-TICK-COMPACT-CHECKPOINT-1` added beside the legacy one (additive; legacy unchanged and readable).
2. `TickTimeline` (frozen timeline module): index-mode row source, `compact_checkpoint`, `migrate_to_compact`, `resume_compact`.
3. `MonthlyParquetProvider.read_page(..., start_index=)` and `supports_index_resume`.
4. Accepted-source cache and offline acceptance record (+ admission step in deployment) replacing the per-request O(dataset) scan.
5. `replay_run` durable multi-segment run (`037_replay_run_queue.sql`) as the orchestration path; segment job ids are deterministic uuid5.
6. Make V2 the default format only after owner approval; decide whether an O(1) index (seekable row-group offsets) is wanted.
**Stop point:** none of the above is promoted; owner approval required.

## 6. Honest limits
- V2 is proven on synthetic financial-active data and one trade profile; not on real-market sources.
- Recovery is bounded (index scan), not O(1).
- Tier controls beyond 16,384 are same-format single-process, not V1.
- Cold resume of about 13 s in a fresh worker is dominated by process start and first segment budget; it is inside the 30 s deadline but not small.

## 7. 20-trader capacity run (SYNTHETIC, V2 opt-in, in-process API + real queue/native workers, PostgreSQL 17 disposable)
Budget: 5 vCPU / 14 GiB cgroup (owner addendum 2026-11-14), 4 workers, seed 20261115, normal-load schedule (20 staggered arrivals over 3,600 s), each trader one 262,144-tick financial-active Session via `replay-run`. Evidence: `docs/benchmarks/compact-v2-2026-11-15/normal_262144_run2.json`.

**Run 1 (invalid as capacity evidence, kept):** 7/20 completed. Root cause was harness-only: accounts were created before the window and bearer tokens live 1,800 s (`session_seconds`), so later traders got 401 / empty job bodies. Queue-wait also read a wrong key (all zeros). Both fixed (accounts provisioned at arrival, `waitMicroseconds`). The 2-trader smoke test is NOT the 20-trader result.

**Run 2 (valid):**
| Metric | Result |
|---|---|
| Completed traders | 20 / 20, 0 failures, 0 retries, jobs 210 SUCCEEDED |
| Wall (incl. queue drain) | 3,974 s (+ 625 s offline source admission, outside request deadlines) |
| Per-trader end-to-end | p50 419 s, p95 430 s, p99/max 441 s |
| Queue wait (200 first-claims) | p50 0.09 s, p95 0.24 s, p99 0.29 s, max 0.45 s |
| API latency p50/p95/p99 | submit 44/470/514 ms; poll 38/363/501 ms; summary 156/837/1060 ms; view 118/686/2132 ms |
| **Journal page / CSV export** | **p50 about 10.2 s, p95 10.9 s** (slow; read path at 262k-tick Sessions) |
| Worker CPU total / per trader | 6,482 core-s / 324 core-s; peak worker RSS 269 MB |
| Host | max CPU 61.7 %, p95 58.3 %, min MemAvailable 13.2 GiB, no swap; no gate tripped |
| PostgreSQL | DB +255 MB, WAL +464 MB, checkpoint rows 81,980 (max 2,497 B, total 157 MB), 60 events, 81,960 commands |
| Financial parity | all 20 traders identical (balance 10000.7, 1 closed trade CLOSED 1998.9 to 1999.6, net 0.7) |

**Limits of this result (do not over-read):**
- Arrivals about 3 min apart and about 7 min per run means only about 2 to 3 traders overlap at any time; peak concurrency of 20 was NOT exercised. The "burst of eight" schedule was NOT run. Fairness under contention was not measured separately.
- Synthetic ticks, one trade profile, in-process HTTP driver (no browser, no TLS/proxy), one host. Not a product/production capacity claim; needs production test.
- Journal/export about 10 s is a real latency defect to investigate before any SLO.
- 20-trader acceptance here uses the V2 opt-in path; V2 is not promoted.

**Verdict, commercial capacity gate (separate from Commercial V1):** PARTIAL / prototype. Proven (synthetic, this host): 20 traders each completing a 262,144-tick Session with equal financial results, no failures, wide resource headroom under the staggered normal schedule. NOT proven: simultaneous 20-trader load (burst), real-browser/TLS path, real data, Journal/export latency within an acceptable SLO. Gate therefore not PASS.

## 8. Journal / CSV export latency investigation (2026-11-15, display path only)
Finding (in-process cProfile, `docs/benchmarks/compact-v2-2026-11-15/journal_profile_*.json`): `journal_page`, `/journal` and the CSV export all call `FixtureTimelineCache.window` -> `MonthlyParquetProvider.read_revealed_window` for the display quote. Two causes: (a) every selected row group was fully split into timestamp groups (`make_group` validate + hash) although only the last 1..N groups can be returned; (b) the one-entry verified row-group cache was evicted by the alternating month-start pointer check (`first_time_for_month` reads the month's first row group), so each call re-read and re-validated two row groups.
Changes (display read only; execution, reducer, hashes and returned data unchanged): tail pruning in `read_revealed_window` (keeps `maximum_groups + 2` distinct timestamps) and a two-entry LRU for verified row groups (key still includes the pinned manifest hash). Tests: pruning equals the unpruned reference for 6 row-group sizes x 15 frontiers x 5 window sizes incl. groups straddling row groups; a mutation (pruning limit too small) makes it fail. Regression of 16 touched suites: PASS (EXIT 0).
Measured (idle host, one request, synthetic): cold page 3.3-3.4 s -> about 3.0 s at 16k; repeated reads in a warm process 3.4 s -> 0.02-0.27 s. At 65,536 ticks the cold read is still about 3.0 s, i.e. bounded and independent of tick count (about 16k rows are validated per cold request), but not small. The 10 s p50 seen in the 20-trader run was the same cold path on a CPU shared with replay workers.
Not fixed (needs owner decision, touches the row-group integrity path): avoid per-row canonical validation for display by verifying the row-group hash over raw bytes and converting only the needed rows, or persist the last quote with the committed revision. Status: IMPROVED, SLO still undefined.

## 9. Burst of 8 simultaneous traders (SYNTHETIC, V2 opt-in, 4 workers, 5 vCPU / 14 GiB cgroup)
Same harness and workload as section 7, `--burst`: 8 traders arrive within about 10 s (account creation is serialised by the 30/min auth limit, so effective arrival is a little wider), each runs one 262,144-tick Session. Evidence: `docs/benchmarks/compact-v2-2026-11-15/burst8_*`.

| Run | Result | Cause |
|---|---|---|
| 1 | 4/8, undiagnosed | harness did not record the failing response (KeyError on `state`/`balance`) |
| 2 | 6/8 | `GET /jobs/{id}` answered **503 SERVICE_BUSY** (+ `Retry-After: 1`); the harness treated it as fatal |
| 3 | **8/8**, 0 failures | harness retries SERVICE_BUSY up to 8 times, as the existing frontend does (`accountClient.js`, retryLimit 8) |

Run 3: end-to-end p50 749 s, p95 769 s, max 769 s (spread under 3 %, i.e. no starvation of any trader); queue wait p50 12.7 s, p95 13.1 s, p99 13.9 s, max 21.2 s (8 sessions contending for 4 workers; far below the 60 s TTL); jobs 250 SUCCEEDED; financial parity identical across all 8 (balance 10000.7, one closed trade); worker CPU 2,378 core-s, peak RSS 280 MB; host CPU max 84.8 % (p95 80.6 %), MemAvailable min 13.1 GiB, no swap, no gate tripped; DB +109 MB, WAL +185 MB, checkpoint max 2,497 B.
**Client recovery reported separately:** 5 SERVICE_BUSY retries (3 on job polls, 2 on summary reads). SERVICE_BUSY is the product's designed admission refusal (shared DB budget), so under an 8-trader burst some reads are refused once and succeed on retry; without client retry (run 2) 2 of 8 travellers failed.
**Journal page / CSV export under burst:** p50 15.8 s / 16.0 s, p95 18.1 s / 22.8 s (cold display read competing for CPU, section 8). This is the weakest measured path.
Limits: still synthetic ticks, one trade profile, in-process HTTP driver (no browser/TLS), one host; the 20-trader simultaneous cohort was NOT run (largest simultaneous cohort measured: 8).

## 10. Final verdict - commercial capacity gate (separate from Commercial V1)
**PARTIAL / prototype, not PASS.**
- Proven (synthetic, this host, V2 opt-in): one 262,144-tick Session through API, durable queue, PostgreSQL and native worker with financial parity; 20 staggered traders 20/20 with no failures; 8 simultaneous traders 8/8 (with bounded client retry on SERVICE_BUSY), queue wait about 13 s, resource headroom remains.
- Not proven: 20 simultaneous traders; real browser/TLS path; real market data; an accepted Journal/export latency (10-16 s under load, SLO undefined, owner decision); behaviour with the production-default V1 format (V2 is not promoted).
- Commercial V1 overall stays **BLOCKED** (data rights, 16-instrument profiles, payment sandbox, login, remote backup and CI keep their separate gates). No GO is claimed.
