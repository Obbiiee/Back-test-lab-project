# XAUUSD order-retention CP4 — 2026-10-31

## Decision

**PASS for the isolated QA extension; NO-GO for production or unbounded sessions.** One three-day, continuous XAUUSD Session used the explicit QA retention policy and retained 134 accepted orders, including 130 completed trades and four cancellations. Independent source traversal, financial reconciliation, cold resume, and crash/retry checks passed. The existing 128 active-order limit remains in force. The version 1/default cumulative limit and production behavior remain unchanged.

This is a bounded extension: cumulative history is kept in full up to 512 orders; order 513 remains refused. It does not introduce pruning or claim unbounded lifetime storage. The experimental source disclosure remains `EXPERIMENTAL — UNVERIFIED SOURCE — SIMULATED EXECUTION`; source rights remain UNKNOWN and financial execution eligibility remains NOT_GRANTED.

## Cause and contract boundary

- `backend/execution/observed_kernel.py:23,65-92,270-284` defines `MAX_ORDERS=128` and applies it to the entire `state.orders` map. That map contains PENDING/ACTIVE orders and terminal CLOSED/CANCELLED records, so completed history consumed the same limit as live exposure. `OPEN` refused order 129 with `REFUSED_STATE_LIMIT`.
- This was an intentional bounded-state rule, not truncation of the durable event or command ledger. PostgreSQL independently kept immutable commands, results, checkpoints, and the complete event chain.
- The financial contract retains the 128-order and 256-event-per-transition safety limits (`docs/V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md:339`). The analysis projection also describes the 128-order session bound (`:359`). Those authorities were not changed. The extension is only for an explicitly pinned isolated QA policy. Before any product/production use, the financial and analysis contract owners must revise the applicable bounds and review the 512 cap and projection pagination.
- The separate timeline position log is block-addressed, not capped at 128 total records: `backend/ticks/timeline_v2.py:446,499-506` validates/appends position-log blocks of up to 128 records and writes additional blocks as needed. This concerns source-position lookup evidence, not orders, financial events, or command receipts.

## Versioned extension

`QA_ORDER_RETENTION_V2` is an exact, hash-pinned configuration (`BTL-QA-ORDER-RETENTION-2`, `scope=ISOLATED_QA_ONLY`): maximum 512 cumulative order records and maximum 128 PENDING/ACTIVE records. The default (`None`) still resolves to 128 cumulative and 128 active. Store and controller require the same policy; validators apply it on prepare, commit, retry, inspect, and cold resume. Unknown/mutated policy values refuse. The existing financial reducer and execution rules did not change.

Terminal history stays in the full state and in ORDER_ACCEPTED/terminal events. Nothing is silently dropped. This bounds retained order state at 512 for this experiment; event/receipt history remains append-only and independently checked.

## Bounded persistence and recovery fixture

The authored, non-market-data fixture crossed each threshold in one Session. At each threshold a fresh worker cold-resumed, independently walked and hashed the full event chain, checked all accepted/cancelled IDs against state, killed a worker with SIGKILL after a durable cancel commit, retried the exact command, and cold-resumed again. The 128-live-order fixture separately proved that order 129 is rejected with the state and command ledger unchanged.

| Cumulative orders | State payload | Session commands/events | Whole QA database* | Cold resume | Post-crash exact retry |
|---:|---:|---:|---:|---:|---|
| 129 | 58,725 B | 262 / 262 | 12,958,743 B | 0.830 s | PASS |
| 256 | 113,335 B | 519 / 519 | 16,530,455 B | 1.639 s | PASS |
| 512 | 223,419 B | 1,034 / 1,034 | 24,345,623 B | 3.693 s | PASS |

*The PostgreSQL database measurements are cumulative database sizes at successive checkpoints in the same isolated cluster, including schema/fixed overhead and earlier fixture state. They are not isolated per-session sizes. From 129→256 orders, database allocation increased 3,571,712 B for 127 more orders and 257 more command/event rows; from 256→512, it increased 7,815,168 B for 256 more orders and 515 more rows. At 512 orders, `tick_commands` occupied 6,332,416 B, `tick_events` 1,892,352 B and `tick_checkpoints` 6,004,736 B, including their relation pages as separately recorded in the JSON report. The state payload grew 58,725→223,419 B (about 3.8× for 4× the orders); cold resume grew 0.830→3.693 s (about 4.4×). These are measurements across bounded points, not evidence for larger limits.

Across the open/cancel fixture, median pair latency was 0.908 s (p95 1.621 s; 509 samples). Fixture runtime was 548.562 s and CPU 512.459 s. Peak measured RAM was 796,016,640 B (<1 GiB); peak artifacts were 75,567,104 B; free disk remained 56,710,500,352 B (>30 GiB). The PostgreSQL relation sizes and full measurements are in the retained `report.json`.

## Continuous historical Session

The actual run processed Jan 2–4 UTC as three continuous days in one Session, using Batch-256 and the pinned hourly decision schedule. It crossed the threshold without reducing trade frequency:

- 424,030 observed ticks/timestamp groups; first quote `2024-01-02T00:00:00.130Z`; last quote `2024-01-04T23:59:58.583Z`.
- 5 unknown-coverage gap records (4 source-observed intervals); no synthetic quotes were introduced. The source rights are UNKNOWN.
- 1,829 durable commands; 134 accepted orders (67 LIMIT, 67 STOP), 130 CLOSED and 4 CANCELLED. Financial outcomes: 130 entries, 130 exits, 100 SL and 30 TP; ending balance 9,962.23 from 10,000, realized gross −37.77.
- Cold resume occurred after day one at revision 90 and continued the same Session through revision 1,829. Exact retry/idempotency passed.
- Independent verifier traversed all 424,030 source groups and independently matched 260 fills (130 entries, 130 exits), source ordering, event-chain head, balance 9,962.23 and gross −37.770000.
- Replay elapsed 1,353.217 s; full end-to-end QA 1,694.674 s; independent full verification 206.470 s; cold-resume phase 59.172 s. Peak RAM 777,965,568 B (<1 GiB); peak QA artifacts 427,184,128 B (<512 MiB); ending free disk 56,284,946,432 B (>30 GiB). PostgreSQL DB 79,043,607 B; total QA artifacts 424,308,736 B.

All prior artifacts and protected H1/H2/H3 were left untouched. Production was unchanged. The detailed machine-readable reports remain at:

- `/home/riksora/riksora-qa-evidence/cp4-order-retention-v2-20261031-r3/report.json`
- `/home/riksora/riksora-qa-evidence/rb256-3day-20261031/report.json`

## Reproduction

From the integration worktree, set a **new empty** artifact root for each run:

```bash
PYTHONPATH=backend PYTHONDONTWRITEBYTECODE=1 \
  BTL_QA_ORDER_RETENTION_ROOT=/home/riksora/riksora-qa-evidence/cp4-order-retention-v2-<new-id> \
  /tmp/riksora-vps-candidate-venv/bin/python -B -m tests.qa_order_retention_v2

BTL_HISTORICAL_QA_ROOT=/home/riksora/riksora-qa-evidence/rb256-3day-<new-id> \
BTL_HISTORICAL_QA_RUN_ID=rb256-3day-<new-id> \
BTL_QA_HISTORICAL_BATCH_GROUPS=256 BTL_QA_HISTORICAL_DAYS=3 \
PYTHONPATH=backend PYTHONDONTWRITEBYTECODE=1 \
  /tmp/riksora-vps-candidate-venv/bin/python -B -m tests.qa_historical_day_v2
```

The existing roots intentionally refuse overwrite. A rerun requires a separate fresh root and the same isolated resource/disk gates.

## Gates and next milestone

The changed observed execution/kernel/storage and QA modules passed 61 targeted regression tests after the default/v2 policy assertion was added. The private PostgreSQL acceptance fixture passed at 129/256/512, including crash recovery and independent event-history verification. The 3-day historical QA report is PASS.

**GO:** proceed to a separate one-week readiness checkpoint after reviewing the complete three-day artifacts and the analysis projection's remaining 128-order limitation. The present historical runner's 512 MiB artifact ceiling is nearly consumed by three days (427,184,128 B peak), so a seven-day run is **NO-GO under the current artifact budget**; planning should reserve a separately approved isolated evidence budget above 1 GiB, then repeat disk/RAM preflight. That size is a cautious planning estimate, not measured seven-day growth. **NO-GO:** annual replay, product/production enablement, increasing the 512-order cap, or claiming unbounded retention. No full week/year was run here.
