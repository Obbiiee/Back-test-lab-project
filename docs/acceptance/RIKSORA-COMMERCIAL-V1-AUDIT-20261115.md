# RIKSORA Commercial V1 — audit, requirement matrix and decisions (2026-11-15)

Status: **IMPLEMENTATION REGISTER / AUDIT REPORT, not an architecture authority.** Evidence was gathered by Claude on riksora_vps1 (branch `claude/dual-engine-v1-20261114`, last commit at the time of writing `babc556`). Labels: proven (test or measurement run, cited), prototype, hypothesis, needs production test. Nothing here uses synthetic or UNKNOWN-rights data as commercial evidence. No percentages of completion are given on purpose.

## A. Requirement matrix
| # | Requirement | Status | Evidence / gap |
|---|---|---|---|
| 1 | Google login | PARTIAL | `identity/google.py` + store, 12/12 tests with a stubbed provider; real keys absent (owner supplies later, never in chat) |
| 2 | Dashboard, Method, Session, Workspace, Replay, Trade, Jump, Journal | PARTIAL | Real-browser journey passes on synthetic ticks (10 traders clean, 15 via HTTP driver); real-data sessions through the product worker NOT implemented (see D1) |
| 3 | Chart history up to 5,000 candles | PARTIAL | Additive `BTL-CHART-HISTORY-PAGE-1` route + 8 tests; real catalog M1–H2 >5,000 candles in 6–120 ms in-process; D1 only ~1,615–1,865 candles (data limit, `historyExhausted` says so). Frontend does not use the route yet |
| 4 | Trade ledger Export CSV | DONE (CSV only) | `cloud/export_results.py`, 9 tests, real E2E equal to committed journal; frontend download wiring missing |
| 4b | Export PDF / JSON / multi-session | MISSING | needs owner decision on PDF dependency and scope |
| 5 | Planned Trade tool (Protocol Long/Short) | PROVEN (frontend unit level) | stitch-trading tests pass; not re-proven in real browser on real data |
| 6 | Statistics | PARTIAL | profit factor, expectancy, max drawdown, win rate, streak, R-multiple exist; UI labels the curve "Committed balance", not equity |
| 7 | Trading account simulation, 16 instruments | MISSING / OWNER DECISION | no margin, leverage, free margin, stop-out, swap in product execution; profiles exist only for XAUUSD (observed) and a synthetic fixture |
| 8 | Drawing tools / indicators | PROVEN (unit) | 88 drawing tools, indicator tests pass; chart-source integration unverified |
| 9 | Session lifecycle | PARTIAL | archive/trash/restore only in opt-in V2 sandbox; pause/downgrade absent |
| 10 | Free/Pro enforcement server side | MISSING in default path | windows exist only in `cloud/sandbox_access.py`, not enforced by default `/research/sessions`; capabilities show entitlement NOT_CONFIGURED |
| 11 | Midtrans Pro | PARTIAL (sandbox) | `cloud/midtrans.py` 16/16, `cloud/billing.py` 14/14 incl. cold backup restore; no renewal, invoice history, downgrade; no real keys, no production payment |
| 12 | Customer operations | MISSING | no account deletion/export, Terms/Privacy page, audit log, monitoring/alerting; off-box (R2) backup untested |
| 13 | Tenant isolation | PROVEN (route level) | foreign/unknown session answers identically for chart and export; 3 identity test failures reproduce on baseline `f941eba`, not regressions |
| 14 | Engine correctness on real data | PROVEN (scope-limited) | baseline = Claude v1 = Claude v2 on 18 real slices incl. tight scenarios (up to 256 fills) and one cross-month slice; independent OHLC oracle identical on EURUSD, USDJPY, XAUUSD; rights UNKNOWN = private QA only |
| 15 | Capacity | PROVEN (synthetic, this VPS, 2,048-tick fixture) | open model, 4 workers, 5 vCPU/14 GiB budget: 0.6 sessions/s all OK, 0.9/s degraded, knee between 0.6 and 0.9 sessions/s. The Commercial 262,144-tick x 20-trader hourly gate is NOT run |
| 16 | Data licensing | OWNER DECISION REQUIRED (postponed by owner) | rights UNKNOWN: no commercial claim |
| 17 | Release CI on final SHA | BLOCKED | branch is ahead of origin by ~30 commits; no GitHub credentials on the VPS |

## B. Six remaining product decisions (current state / problem / options / recommendation / consequence / approval)
1. **A. Trading account simulation** — State: no margin/leverage/swap. Problem: advertised "account" realism unsupported. Options: (a) V1 = cash PnL only, label it plainly; (b) add margin/leverage/stop-out per instrument. Recommendation: (a) for launch, (b) designed as a separate versioned artifact later. Consequence: (b) touches the frozen financial reducer, so needs explicit approval and a new golden set. Approval: owner.
2. **B. Drawing/indicators** — State: frontend-proven. Recommendation: ship, with chart source from the new paged route. Needs frontend wiring only; no contract change.
3. **C. Session lifecycle** — State: partial. Recommendation: promote archive/trash/restore from the V2 sandbox into default with a retention period; no pause. Consequence: retention policy (job retention already age-based, 900 s / 4,096 cap, W2). Approval: owner on retention days.
4. **D. Subscription/Midtrans** — Recommendation: fixed 30-day Pro period, no auto-renew in V1, invoice via Midtrans order record, refund = manual with entitlement revoke, downgrade at period end. Consequence: least billing code; needs sandbox keys (never in chat) before any real test. Approval: owner.
5. **E. Statistics/reporting** — Recommendation: keep committed-balance wording, add equity only after item 1(b). CSV now; JSON next (cheap, same ledger); PDF only on explicit approval of a dependency.
6. **F. Customer operations** — Recommendation: before any paid beta: Terms/Privacy, account deletion and data export, audit log of auth/billing events, metrics + alerting, off-box encrypted backups to R2 with a tested restore. Consequence: roughly the gating list in `RIKSORA-VPS-OPS-CHECKLIST-20261114.md`.

Free/Pro enforcement: recommended to move the V2 sandbox window check into the default session-creation path behind the same server-side entitlement lookup (no client trust). Not done, since it changes admission behaviour; needs owner approval.

## C. Implemented in this run (branch `claude/dual-engine-v1-20261114`)
- `dd0e4bd` W2: age-based finished-job retention (`backend/cloud/queue.py`; 26/26 queue tests); frontend idempotent resubmit on pruned job (`frontend/src/tickAlpha/client.js`, tests pass).
- `0abc724` W4b: `GET .../sessions/{id}/chart-bars` (`backend/cloud/chart_history.py`, route in `cloud/research.py`), 8 tests; prehistory verification (608 pair-months OK).
- `babc556` Export: `GET .../sessions/{id}/export?format=csv` (`backend/cloud/export_results.py`), 9 tests + real E2E; open-model W7 rerun with host metrics.
- Earlier: data verification (544 datasets, 1,331,417,302 ticks, all OK), oracle acceptance, W3 real parity, PITR backup drill, docs edits with SUPERSEDED markers.
Not run: `stitch-analytics` (needs `backend/venv` + msgspec), `market` suite (decade archive absent), CI on a remote SHA.

## D. Remaining blockers
1. Real-data sessions through the product worker: the Monthly path is hard-wired to a synthetic execution profile and rights class; needs the 16 instrument profiles (decision B1) and a gated private-QA rights class.
2. Frontend wiring: chart-bars paging and CSV download.
3. Free/Pro server-side enforcement, billing lifecycle, customer operations (decisions B3–B6).
4. GitHub credentials on the VPS (push/CI on final SHA), Google/Midtrans sandbox keys, R2 keys, root-only host checks (effective `PermitRootLogin`, firewall).
5. Commercial capacity gate (20 traders x 262,144-tick financial-active, two runs, burst of eight) not executed.
6. Data licensing.

## E. Final V1 readiness: **BLOCKED** for a paid launch
Blocked by D1, D3, D4, D5 and D6. Engine correctness on the real-data slices measured, the chart/export slices and the synthetic capacity knee are proven within the stated scope. Not ready to be called Commercial V1; any public statement stays limited to what is proven above.


## F. Update 2026-11-15 (after the owner approved the recommendations)
Implemented and tested after sections A–E were written (branch `claude/dual-engine-v1-20261114`):
| Item | Result | Evidence |
|---|---|---|
| Frontend CSV download (Journal) | DONE | `exportSessionCsv`, button in `AlphaJournal.jsx`, `tick-alpha.test.mjs` PASS, vite build OK (`cacad3b`) |
| Hosted chart uses `BTL-CHART-HISTORY-PAGE-1` (up to 5,000 earlier candles) | DONE at unit level; real-browser check NOT RUN | `chartHistoryBars`/`mergeHistoryBars`, tests PASS |
| Free/Pro server-side window admission | IMPLEMENTED, **opt-in** (`BTL_ENTITLEMENT_ENFORCE=1` + `BTL_ENTITLEMENT_RESET_TIMEZONE`), default OFF | `cloud/entitlements.py`, migration 033, `tests/test_entitlements.py` (Free one window/day, retry idempotent, tenant separation, PAID order makes Pro, REVERSED order removes Pro) |
| Session trash/restore (default path) | DONE | `cloud/session_lifecycle.py`, migration 034, 30-day restore, owner only, list hides trashed; `tests/test_session_lifecycle.py`; 22 research-session and 17 cloud-research regression tests pass |
| Audit trail | DONE (append-only) | migration 035, `cloud/audit.py`; export, trash/restore and refused window claims recorded |
| Billing model | Already matches the recommendation: fixed-duration plan, PAID order = Pro until expiry (no auto-renew), REVERSED/HOLD removes Pro, orders list = invoice history. Not new code; proven by the entitlement refund test (sandbox ledger only) |
| Cross-month real-data parity | PASS 6/6 (eventheavy, pending_tight, scalp_tight over 2024-01..02 and 2024-02..03; up to 203 fills; baseline = Claude v1 = Claude v2) | `~/bench/chain2/cross/` |

Limits stated honestly:
- Entitlement gate: the claim is per request body; a creation that fails inside the queue after admission keeps the claim (an idempotent retry with the same body is not charged twice). The spec's open-position boundary rule and viewable-context rule are not implemented. Gate is not enabled by default because launch configuration and the billing source (sandbox ledger) are owner/production decisions.
- Trash/restore: no permanent purge (needs owner erasure/retention decision because financial evidence tables are immutable by design).
- Still OWNER/credential bound: PDF export (dependency), account deletion/export policy, Terms/Privacy text, monitoring/alerting stack, R2 backup test, real-data sessions through the product worker (needs 16 instrument profiles and a gated private-QA rights class), Google/Midtrans sandbox keys, GitHub credentials, licensing.
Readiness stays **BLOCKED** for a paid launch.
