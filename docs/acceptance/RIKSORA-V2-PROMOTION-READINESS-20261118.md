# Checkpoint V2 (`BTL-TICK-COMPACT-CHECKPOINT-1`) promotion readiness (2026-11-18)

Status: implementation register. **Nothing in production was changed.** Promotion needs the owner's explicit approval (AGENTS.md, Compact Checkpoint V2 addendum).

## 1. What V2 changes, what it does not
* Changes: how a Session's replay position is persisted and resumed (compact index-based checkpoint instead of an ever-growing advance log), which removes the `MAX_STEPS = 256` limit that stops a V1 Session after about 16,000 tick groups (measured in the Free/Pro audit: a Pro Session stops at 2020-02-10 04:50, 16,130 of 65,535 ticks, with `REFUSED_RECOVERY_LIMIT`).
* Does **not** change: reducer, fill rules, Bid/Ask handling, entitlement rules, immutable receipts, queue admission 16/2, TTL 60 s, deadline 30 s, worker count.
* Switch: one environment variable, `BTL_TICK_CHECKPOINT_FORMAT=compact-v2`, read by the API and forwarded to the native worker (`cloud/worker.py` whitelist). Default (unset) stays V1.

## 2. Deployment gates (all run on disposable PostgreSQL 17, synthetic data, 2026-11-18)
| Gate | Result | Evidence |
|---|---|---|
| V1 Session readable and continued under V2; lazy and non-destructive | **PASS** | `test_pro_long_sessions.Compat.test_v1_session_continued_under_v2_equals_a_v1_only_control`: a Session started under V1, continued under V2 after an operator restart, equals a V1-only control on cursor, balance, order statuses, journal rows, summary and event count |
| Old checkpoints | **PASS** | same test (V1 data is not rewritten); `test_compact_migration` (existing) |
| Worker restart mid Session | **PASS** | Pro tests: restart in the middle of a 3-month and a 12-month Session |
| SIGKILL during a V2 replay-run, cold recovery | **PASS** | `Compat.test_sigkill_during_a_v2_replay_run...`: 9 chunks committed, process killed, a cold worker finishes; equals the uninterrupted control; zero duplicate command ids |
| Retry / idempotency | **PASS on V1; PARTIAL on V2** | `test_replay_run` (14) runs with the production default checkpoint (V1), including same-job-id resubmission and conflicting body. On V2 the cold re-claim of the same job is proven by the SIGKILL test; same-job-id resubmission on V2 was not run separately |
| Jan→Dec, one Session | **PASS** | `YearJanDec`: 11 month boundaries, equals the uninterrupted control |
| Dec→Jan (year boundary), one Session | **PASS** | `YearBoundary` (2020-12 → 2021-01) |
| Orders at boundaries (PENDING limit and ACTIVE position) unchanged by a boundary | **PASS** | same tests, state compared immediately before and after each boundary |
| Financial parity vs reference | **PASS** | `leaf_diff` of the full fact set equals `[]`; only event-id fields that embed the Session identity are excluded |
| Free window rules still hold on V2 | **PASS** | `test_free_pro_months` (runs with V2). `test_window_guard`, `test_window_jump(_recovery)` use the fixture model with the default checkpoint (V1) and were not re-run on V2 |
| Browser gates (entitlement and extended journeys) | **PASS** | re-run on the latest build: entitlement journey 10 steps, extended journey 11 steps (PostgreSQL 17, synthetic, V1 default checkpoint in the gate's own stack) |
| 20-trader acceptance at 262,144 ticks | **PASS (earlier report)** | `RIKSORA-COMPACT-CHECKPOINT-V2-20261115.md` |
| Real data | **NOT RUN** | data rights UNKNOWN; synthetic only |

## 3. Resource evaluation (host-specific, synthetic, not a capacity claim)
| Run | Worker jobs | Worker CPU s | Worker wall s | Worker peak RSS | Note |
|---|---|---|---|---|---|
| 12-month Session, 16,384 ticks (`YearJanDec`, includes a control Session) | 30 | 33.95 | 43.76 | 220.7 MiB | 1 staged + 1 control |
| Dec→Jan, 4,096 ticks | 10 | 9.24 | 11.72 | 180.1 MiB | |
| 3-month Session, 65,535 ticks, staged + control (`test_free_pro_months`) | n/a | n/a | about 190 s wall in total | n/a | measured before telemetry was added |
Same 8,192-tick Session under V1 and under V2 (`Compat.test_report_v1_versus_v2_cost_of_the_same_session`, same host, run once):
| | Worker CPU s | Worker wall s | Peak RSS | DB growth | Checkpoint bytes |
|---|---|---|---|---|---|
| V1 | 9.11 | 11.54 | 180.1 MiB | 1,320 KiB | 390,738 |
| V2 | 8.41 | 10.69 | 180.1 MiB | 880 KiB | 255,490 |
V2 is not slower at a size where V1 still works (about 8% less CPU, one third less database growth); beyond about 16,000 tick groups only V2 works at all. One run each: indicative, not a benchmark.
Database growth per Session: earlier measurement 14.6 MB per 262,144-tick Session including checkpoints (V2 report). Memory is bounded by lazy row-group reads (the engine does not load all months). Storage and DB numbers for real data are NOT MEASURED.

## 4. Rollout, monitoring, rollback (for the owner to approve; not applied)
Rollout (each step only if the previous one is clean for the stated time):
1. **Staging profile** (the public application already uses `BTL_PRODUCT_PROFILE=staging`): add `BTL_TICK_CHECKPOINT_FORMAT=compact-v2` to `~/prod/app.env`, `systemctl --user restart riksora-api`. Existing V1 Sessions keep working; new Sessions use V2.
2. Run the owner's own test Session (several hundred thousand ticks is possible only with a larger synthetic fixture) and one cold restart (`systemctl --user restart riksora-api`) during a replay.
3. Observe 48 hours with the checks below; then keep.
Monitoring (all read-only):
* `journalctl --user -u riksora-api | grep research_job_failed` — expect zero `REFUSED_RECOVERY_LIMIT`, `REFUSED_STATE_VERSION`, `workerDeadline`.
* `SELECT state,count(*) FROM btl.research_jobs GROUP BY 1` — no growth of `RECONCILE_REQUIRED`/`FAILED`.
* `systemctl --user status riksora-api` memory peak against `MemoryMax=8G`; `pg_database_size` growth per Session (`btl.tick_checkpoints`).
Rollback: remove the variable, restart `riksora-api`. New Sessions use V1 again. Sessions created under V2 keep their format and stay readable by a V2-enabled process only; to read them after rollback, re-enable V2 (no data is deleted either way).
Rollback rehearsal (PASS, `Compat.test_rollback_to_v1_never_corrupts_a_v2_session`): a process with V2 disabled that meets an existing V2 Session **continued it** (outcome `CONTINUED`); after V2 was enabled again the Session finished identical to an uninterrupted control with zero duplicate command ids. So the variable governs the format used for new Sessions and no data is stranded by a rollback.

## 5. Readiness verdict
**READY for staged promotion on the synthetic evidence above, pending the owner's approval.** Not proven: real-data behaviour, a Session of several hundred thousand ticks on the public composition, and multi-instrument Sessions (see the multi-pair design note).

## 6. Open verification
* Rollback rehearsal: done (section 4). Not covered: a rollback while a replay-run is in flight on a V2 Session (SIGKILL on V2 is covered, rollback during it is not).
* Browser gates for this checkpoint: see the final report.
