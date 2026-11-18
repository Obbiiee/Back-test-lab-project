# RIKSORA Free/Pro rules: audit, tests and findings (2026-11-18)

Starting point: commit `539a936` (Free = 1 new Session per UTC day, each Session uses 1 month of data; Pro unlimited). Everything below was run on the real stack
(API, durable PostgreSQL queue, native worker, canonical Monthly Parquet) on disposable PostgreSQL 17 clusters, with the synthetic dataset
(`synthetic:financial-active-v1`, 65,536 ticks, one per minute from 2020-01-30 to 2020-03-15, so it crosses Jan→Feb and Feb→Mar). Nothing here uses market data.
Labels: **PROVEN** (test evidence below), **LIMITATION** (measured, product cannot do it today), **OWNER DECISION**, **NOT TESTABLE** (fixture cannot express it).

## 1. Findings, by severity

| # | Severity | Finding | Status |
|---|---|---|---|
| F1 | **Critical for the Pro contract** | The production configuration uses the V1 checkpoint (`MAX_STEPS = 256`). A Pro Session crosses the Jan→Feb boundary correctly but **stops at 2020-02-10 04:50 UTC (about 16,130 of 65,535 ticks)** with `REFUSED_RECOVERY_LIMIT` / `fixtureSteps`. One Session from January to December is therefore **not possible in production today**. With checkpoint V2 (QA opt-in) the same Session runs through all three months. | **LIMITATION; OWNER DECISION** (promotion of V2 to the production path needs separate owner approval, see §5) |
| F2 | Medium | Past-chart context before the Session start (`BTL-PAST-CHART-CONTEXT-1`, and `chart-bars` when a chart registry is configured) shows already-recorded candles of the previous period to Free users. They are derived, cursor-bound display data, not new Sessions or revealed ticks, and the public application has no chart registry configured, but a Free user does see data older than the activated month. | **OWNER DECISION** (accept by design, or clip Free to the activated month) |
| F3 | Medium | "Change pair and method inside a Session": a Session has one dataset/instrument and one Method fixed at creation (command kinds are only OPEN, ADVANCE, SEEK, CANCEL, CLOSE, END); the synthetic catalog also has a single instrument. The contract item cannot be tested and is not implemented as stated. | **NOT IMPLEMENTED / NOT TESTABLE; OWNER DECISION** |
| F4 | Low | `entitlement_claims` migration comment still says "SESSION period = YYYY-MM"; the column is free text and now holds `YYYY-MM-DD` for SESSION. Migration text left unchanged on purpose (checksum). Documented here. | Documented |
| F5 | Low | Pro/Free window refusal messages did not tell a Free user that Pro has no one-month window. Added (`accountClient.js`). I deliberately did **not** write "Pro continues across months" because of F1. | Fixed |
| F6 | Info | A pre-existing test helper (`TestClient` without a lifespan) cannot be used for concurrency: it creates one event loop per request while the app's limiters belong to the first loop, and 8 parallel requests hang. Concurrency is tested through a real uvicorn loop (as in production). Not a product bug. | Test-method note |

No quota bypass was found. Server-side enforcement covers every advancing route (`replay-run`, `replay-to`, `commands` ADVANCE/SEEK, `jump-next-event`, `confirm`/OPEN),
and the claim ledger is keyed by account, not by token, tab or IP.

## 2. Contract conformance

| Contract item | Result | Evidence |
|---|---|---|
| Free: max 1 new Session per UTC day | **PASS** | `test_entitlements`, `test_free_second_session_same_utc_day_is_refused_and_old_session_stays_readable`, production check (409 `SESSION_DAY_LIMIT`, reset 2026-11-19 00:00 UTC) |
| Free: after UTC reset a new Session is allowed | **PASS** | `test_window_quota_is_one_new_month_per_utc_day_and_reuse_is_free` (day turnover by backdating), browser journey `ent_utc_turnover` |
| Free: 1 newly activated month per UTC day; second new month refused | **PASS** | same test (`WINDOW_DAY_LIMIT`) |
| Free: an already activated month consumes no window quota (but does consume the daily Session token) | **PASS** | same test |
| Free: old Sessions, Journal, Analytics stay readable after the quota is used | **PASS** | `test_free_second_session...` (Session, summary, journal, analytics pages, list: 200; quota unchanged) |
| Free: cannot reveal data beyond the activated month through the API | **PASS** | `test_free_session_stops_at_the_end_of_its_month_without_touching_orders` (`replay-run` and `commands` ADVANCE refused 409; orders and cursor unchanged); `test_window_guard`, `test_window_jump` |
| Free: pending order at the window end is not closed, cancelled or rewritten | **PASS** | `test_window_guard`, `test_window_jump`, `test_window_jump_recovery` (SIGKILL), new Free test |
| Free: open ACTIVE position (no PENDING order) at the window end is not settled by Jump | **FAIL / OWNER DECISION** (correction 2026-11-18) | Current behaviour: with ACTIVE only, Jump is an unbounded continuation (`execution/research.py`, `jump_next_event`), so a TP/SL can settle beyond the window. Tests pin this (`test_window_jump`, two-position case). Not changed; see the owner decision in the final report. The earlier PASS wording was wrong. |
| Free: no bypass by parallel tabs, refresh, logout/login, simultaneous requests | **PASS** | `test_free_parallel_requests_and_second_tab_cannot_open_two_sessions` (8 parallel "tabs" over a real uvicorn loop, distinct client addresses: exactly 1 accepted, claims = 1 SESSION + 1 WINDOW); `test_parallel_requests_cannot_activate_twice`; browser journey `ent_logout_login_consistent` |
| Free: reset at 00.00 UTC = 07.00 WIB | **PASS** | UTC period keys; frontend/Terms text |
| Free: change pair and method inside a Session | **NOT TESTABLE** | F3 |
| Pro: many new Sessions | **PASS** | `test_pro_admits_many_sessions_and_records_them` (4 Sessions, limits `null`), `test_entitlements` |
| Pro: one Session through at least three months without reset (QA, checkpoint V2) | **PASS** | `test_pro_one_session_runs_through_three_months_with_parity_and_restart`: Jan 30 → Mar 15 in one Session |
| Pro: pending order and open position unchanged at each month boundary | **PASS** | same test: order statuses and cash balance equal immediately before and after Feb 1 and Mar 1 |
| Pro: continuous run equals an uninterrupted reference (no tick lost, duplicated or executed twice) | **PASS** | same test: staged run with a worker restart after the Feb boundary equals a single uninterrupted run on cursor, balance, order statuses, journal rows (entry/exit price and time, PnL), summary and event count. Only event-id fields (`entryFillRef`, `exitFillRef`) differ, because they embed the Session identity |
| Pro: one Session Jan–Dec in production | **LIMITATION** | F1 |
| Pro expired/reversed mid-Session | **PASS** | `test_pro_expiry_mid_session_keeps_the_history_and_falls_back_to_free_rules`: history, orders, balance unchanged and readable; advance beyond the window refused (`WINDOW_ENDED_CONTINUATION_ONLY`); after renewal the same Session continues to March |
| Dec→Jan year boundary | **PASS** (synthetic, correction 2026-11-18) | Arithmetic PASS: `YearBoundaryArithmetic`. Replay PASS: `YearBoundary.test_one_pro_session_runs_from_december_into_january_with_parity` (one Pro Session crosses Dec→Jan, 1 boundary, 10 jobs, parity OK; evidence `/tmp/riksora-qa-20261118/yearb.log`). Earlier "NOT RUN" was out of date. |
| Checkpoint, resume, restart worker | **PASS** | worker restart inside the Pro test; `test_window_jump_recovery` (7 SIGKILL cases); `test_replay_run` (14) |
| UI desktop and mobile | **PASS** (synthetic) | browser gates below |

## 3. Tests run (PASS/FAIL/SKIP)

Backend, disposable PostgreSQL 17, `BTL_TEST_DATABASE_URL`, one run at a time:

| Suite | Result |
|---|---|
| `tests.test_entitlements` | 9 / 9 PASS |
| `tests.test_window_guard` | 5 / 5 PASS |
| `tests.test_window_jump` | 6 / 6 PASS |
| `tests.test_window_jump_recovery` (SIGKILL) | 7 / 7 PASS |
| `tests.test_replay_run` | 14 / 14 PASS |
| `tests.test_commercial_grants` | 1 / 1 PASS |
| `tests.test_free_pro_months` (new, checkpoint V2) | 7 / 7 PASS (6 database tests, about 5 min in total, 3 min 12 s for the long Pro run; plus 1 year-boundary arithmetic test) |
| same Pro test with the production default (V1) | **FAIL by design of V1**: stops at 2020-02-10 04:50 (F1) |

Frontend: site content, account plan, tick-alpha (10 PASS blocks), eslint clean, production build.
Browser gates (real Chromium headless shell, own disposable cluster, synthetic ticks):
* entitlement journey (`RIKSORA_QA_E2E_ENTITLEMENT=1`, enforcement ON): PASS, 10 steps (enforced, first Session, second refused `SESSION_DAY_LIMIT`, logout/login consistent, Pro unlocks, refund downgrade, UTC turnover, IDOR no claims).
* extended journey (`RIKSORA_QA_E2E_EXTRA=1`): PASS, 11 steps (login, Method, replay, order receipt, Jump, journal and analytics, logout/login resume, CSV, PDF, Trash/Restore, mobile viewport).
Note: this host has PostgreSQL 17 only. The gate wants "PostgreSQL 16 tools"; it was run with `BTL_QA_PG_BIN/BTL_QA_PG_SHAREDIR` pointing to the 17 build. So these are PostgreSQL 17 results.

Not run: Dec→Jan replay (a multi-year fixture does not exist), the capacity ladder (no hot path changed; the quota layer touches one text column), a multi-instrument or multi-Method Session (F3).

## 4. Performance
The quota change replaces one text key (`YYYY-MM` → `YYYY-MM-DD`); same table, same partial unique index, same queries. No capacity re-measurement was made. Measured on the new tests:
a 65,535-tick Pro Session over three months through the durable worker with checkpoint V2 took roughly 95 s wall (about 690 ticks/s including queue, checkpoint and test overhead; the isolated
engine replay measured earlier at 262,144 ticks per 110 s is faster). Memory: the engine reads monthly partitions lazily (row-group clipping); the test did not load months in advance.

## 5. Proposal delta for owner approval: promote `BTL-TICK-COMPACT-CHECKPOINT-1` (V2) to the public application
* **What:** set `BTL_TICK_CHECKPOINT_FORMAT=compact-v2` in `~/prod/app.env` (and the worker environment is already forwarded by `cloud/worker.py`). V1 Sessions stay readable (lazy, non-destructive migration).
* **Why:** F1. Without it a Pro Session cannot cover more than about 16,000 tick groups, which for real tick data is a small part of one month.
* **Evidence already held:** V2 parity and recovery reports (`RIKSORA-COMPACT-CHECKPOINT-V2-20261115.md`), the Pro three-month test above, 20-trader acceptance at 262,144 ticks.
* **Not changed by this:** reducer, fill rules, Bid/Ask, entitlement, receipts, queue 16/2, TTL 60 s, deadline 30 s, worker count.
* **Rollback:** remove the line and restart `riksora-api`; new Sessions use V1 again, V2 Sessions created meanwhile keep their format.
* **Decision needed:** yes/no. It is **not** applied.

## 6. Residual risks and blocked items
* F1 (V2 promotion), F2 (past-chart clipping for Free), F3 (pair/method switching) need owner decisions.
* Dec→Jan boundary is covered by arithmetic tests only, not by a replay.
* Terms section 4 changed on 2026-11-18 after the 2026-11-17 approval; the approval date was not touched and re-approval by the owner is still pending.
* Commercial V1 stays BLOCKED (data rights UNKNOWN, no real-data acceptance, billing single-plan and sandbox).

## 7. Status
**PARTIAL.** Free contract: PASS except pair/method switching (not implemented). Pro: unlimited Sessions PASS; cross-month continuity PASS on QA with V2 and boundary parity; **not available in production until V2 is promoted (BLOCKED on owner approval)**.
