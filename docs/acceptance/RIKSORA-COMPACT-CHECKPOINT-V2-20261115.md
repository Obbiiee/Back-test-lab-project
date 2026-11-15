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
