# RIKSORA — durable long-session engine: audit, implementation and measured limits (2026-11-15)

Status: **IMPLEMENTATION REGISTER, not an architecture authority.** SYNTHETIC / TEST ONLY measurements on riksora_vps1 (disposable PostgreSQL 17). Evidence: `~/bench/long/*.json` copies under `docs/benchmarks/long-session-2026-11-15/`.

## 1. Limits found in the code (Phase 2)
| Limit | Where | Nature |
|---|---|---|
| Native job deadline 30 s, queue TTL 60 s, lease 30 s / heartbeat 5 s, admission 16 global / 2 per user | `cloud/worker.py`, `cloud/queue.py` | safety/operational; unchanged |
| 64 timestamp groups per ADVANCE chunk | timeline reveal | frozen reveal bound; unchanged (each chunk is its own short durable commit, ~0.06 s hot) |
| **`MAX_STEPS = 256` persisted ADVANCE targets per Session** | `execution/contracts.py`, enforced in `execution/controller.py` for the non-indexed (fixture/synthetic Monthly) timeline | **technical limit, the real blocker**: the legacy checkpoint stores every accepted target (`advanceTargets`) and resume replays all of them. 256 x 64 = 16,384 groups per Session |
| Checkpoint growth | same | each commit stores a full checkpoint row; size grows linearly with steps, total quadratically (measured below) |
| Indexed timeline (compact `nextPosition` checkpoint, private session log, no `MAX_STEPS`) | `execution/historical.py` `IndexedTimelineCache` | exists for the local-archive/observed stack only |
| Provider archives without declared coverage | engine | orders end UNRESOLVED (no fill) by the frozen no-guessing rule; measured: indexed stack on a synthetic archive, 2,048 ticks, LIMIT stays UNRESOLVED, control equal |

## 2. Implemented (Phase 3, backward compatible, reducer untouched)
- `execution/replay_run.py`, queue operation `replay_run` (migration 037), route `POST .../sessions/{id}/replay-run`: one request, many short ADVANCE chunks per job under a wall-clock budget (default 12 s, env `BTL_REPLAY_RUN_BUDGET_S`, far below the 30 s deadline), command id derived from (runId, segment, start revision) so a chunk can be committed only once; the queue inserts the next segment as a deterministic job (`uuid5`) inside the same transaction that finalises the current one (a retry names the same follow-on); no long transaction; fair scheduling unchanged (replay_run is treated like replay_to).
- Tests `tests/test_replay_run.py` 7 PASS: chain of many short segments equals the chronological control (facts and one command per chunk), SIGKILL mid-segment with cold recovery (7 chunks committed, none lost or duplicated, equals control), resubmission of the same job id, foreign account refused, Free-window bound enforced (409 WINDOW_BOUNDARY), request validation.
- Found and fixed: `cloud/window_guard.py` built a fixture-provider application and returned 503 for any Free-window Session on a non-fixture source; it now reads state through the authorised runner.

## 3. Jump retry consistency (Phase 4) - DONE
A retried Jump whose command was already committed now returns the ORIGINAL outcome (EVENT_FOUND) built from the committed command, instead of a verdict on the resulting state (NO_ACTIVE_ORDERS). Financial state is never touched. `tests/test_window_jump_recovery.py` 7 PASS: SIGKILL before run, before commit, after commit, after run; a second job carrying the same request reconciled with a killed first one (same result, one command, parity with the control); retry by job id.

## 4. Tier acceptance (Phase 5), one Session through API, durable queue, native worker, canonical Monthly Parquet
| Ticks | Result | Segments / chunks | Run wall | Worker CPU / peak RSS | Checkpoint max / total | vs chronological control |
|---|---|---|---|---|---|---|
| 2,048 | PASS | 1 / 32 | 2.0 s | 1.5 s / 135 MB | 2.4 KB / 66 KB | equal facts and revision |
| 8,192 | PASS | 1 / 128 | 7.9 s | 6.2 s / 135 MB | 4.5 KB / 384 KB | equal |
| 15,872 | PASS | 2 / 248 | 15.5 s | 12.3 s / 204 MB | 7.2 KB / 1.07 MB | equal |
| 16,384 | **BLOCKED** | 256th step reached, chunk 257 refused `REFUSED_RECOVERY_LIMIT` (`fixtureSteps`) | - | - | - | - |
| 65,536 / 131,072 / 262,144 | NOT RUN (the previous tier failed; gate not lowered) | | | | | |
Per-chunk cost once hot is about 0.06 s (about 1,000 ticks/s); through the full API/queue path one chunk per job costs about 0.22 s, `replay_run` about 0.06 s per chunk. Checkpoint total grows quadratically: at the observed 1.07 MB for 248 steps, 4,096 steps would store roughly 300 MB per Session. Hot-state RSS grows with revealed groups (135 -> 204 MB). 20 traders x 262,144 ticks/hour needs 1,456 ticks/s; four hot workers give roughly 4,000 ticks/s, so compute would fit once the step limit and checkpoint growth are solved.
The 20-trader harness was NOT run (gate rule: a single 262,144-tick Session must PASS first).

## 5. What the blocker needs (OWNER APPROVAL REQUIRED: frozen checkpoint contract)
Proposal: give the synthetic Monthly (non-indexed) stack a compact checkpoint like the indexed stack's `BTL-TICK-SHARED-SOURCE-CHECKPOINT-2` (`cursor` + `nextPosition` + source pin + chain hash) with the revealed groups served from a private session log, so (a) resume is O(1) pages instead of replaying all targets, (b) checkpoint size is constant, (c) `MAX_STEPS` is no longer a function of session length. Backward compatibility: v1 checkpoints stay readable (the reader dispatches on artifact); a migration of an old Session writes a v2 checkpoint at its next commit, proven first on a disposable copy. Disk cost estimate: constant checkpoint (about 3 KB per commit as measured for the indexed stack) plus the session log (compressed groups, order of the archive size). A prototype would be built on the indexed timeline classes; it changes a frozen artifact schema, so it is not enabled here.
Interim alternative without a contract change: raise nothing; sessions longer than 16,384 timestamp groups remain unsupported on the synthetic Monthly stack.

## 6. Verdict for this directive
Checkpoint backward compatibility: not changed (no new checkpoint). Long-session completion: PASS up to 15,872 ticks, BLOCKED at 16,384 by `MAX_STEPS`. Jump recovery: DONE. Worker crash recovery: DONE for jump and replay_run. 20-trader capacity: NOT RUN. Commercial V1: BLOCKED.
