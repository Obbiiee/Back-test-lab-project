# RIKSORA: Bounded Session Storage / Recovery Efficiency Proposal (2026-11-05)

> **Status: DRAFT FOR OWNER + CODEX/CLAUDE REVIEW; docs-only, not implementation authorization.**
> This proposal supplements proposed ADR-009 in PR #20 and does not override AGENTS.md, frozen market/financial/evidence contracts, current operational authorization, or the canonical architecture blueprint. Do not treat this document as another independent source of truth. No migration, deletion, new runtime engine, benchmark, or production cutover is approved by this PR.

## 1. Observed baseline and reusable work

- Main `backend/ticks/storage_v2.py` stores immutable tick data via SQLite/zlib and the published V2 provider; `backend/ticks/timeline_v2.py` retains durable `timeline.sqlite` hash-bound advance/position blocks and a TEMP `position_lookup` table. Do **not** call the TEMP index durable, and do not infer one persisted row per tick without measuring block growth.
- Main `backend/execution/postgres.py` inserts a full `tick_checkpoints` snapshot after every accepted command; `tick_commands` stores a full result including a replay field; `tick_events` stores financial events. It supports idempotent same-command retries and historical fork points. These semantics must be preserved.
- Existing isolated `codex/cp6a10-postannual-handoff` CP6A-4/5 QA-v3 delta-chain experiments already achieved **50.159% less PostgreSQL database growth** on a 513-command / 256-order test (7,741,440 vs 3,858,432 bytes), with identical committed command hashes, idempotent retry, and measured cold reconstruction 1.329 s. These were **isolated QA**, not production certification; a full chain reconstruct and cache cost remain important.
- PR #20 already proposes shared immutable market data and **ADR-009** (immutable financial events, compact command receipt/current state, bounded recovery snapshots). Extend this work; do not create a competing architecture or rebuild the financial reducer.

## 2. Target design: shared tick data + compact recoverable user history

**Shared market data:** one immutable source/version for many Sessions, referenced by datasetId/version/manifest/rights/profile. Physical Parquet day vs month and PyArrow vs DuckDB remain measured candidates, not selected production authority. Do not copy tick history into each user's Session.

**Per-Session canonical durable truth (PostgreSQL):**

1. Immutable accepted command identity and hash, exact idempotent receipt and revision; financial order/fill/cancel/cash events with sequence and hash chain; Method, feed, dataset and execution profile pins.
2. A single atomically updated **current projection**: cursor, exact open orders/positions/balance, versioned visible-prefix anchor, ledger tip and current revision. This is fast-to-open state, not a replacement for canonical evidence.
3. **Versioned sparse deltas** and **periodic indexed recovery checkpoints** containing enough verified state to reconstruct a selected committed revision without replaying from Session genesis. Checkpoint frequency is a measured parameter; never assume a universal N-command cadence.
4. Command responses for the client may be reconstructed from a compact receipt **only if** the same-command retry still returns the exact committed public response or an explicitly versioned backward-compatible API form. Preserve legacy receipt format/reader during migration. Do not drop large replay payloads before proving exact reconstruction and bounded cost.
5. Drawings, user journal and research artifacts persist separately from transient chart cache. Derived candles/tick tiles are shared, recomputable and bounded; never per-user canonical price copies.

**Timeline / recovery:** evaluate the existing opt-in shared-source approach, but do not simply discard `positionLogHash` or `advanceLogHash` and re-scan the full history on every cold resume. Design an indexed provider seek from the pinned timestamp + ordinal, validated complete equal-time groups, and a versioned prefix/evidence commitment. If this cannot reproduce existing hashes/no-look-ahead, retain the existing timeline representation. Inactive positions and financial history must not be silently lost.

## 3. Failure semantics and compatibility requirements

- One PostgreSQL transaction atomically commits command dedup, accepted immutable events, ledger/current state, revision/cursor, and recovery anchor. Crash before commit leaves nothing; crash after commit plus identical retry returns one committed result, not a double fill.
- Preserve immutable historical revisions used by **fork-at-revision** and audit. A checkpoint may be retired only if each referenced historical state is recoverable and hash-valid; external references/active Sessions/pins and rollback evidence must be proven before cleanup.
- Dual-read legacy V1 and versioned compact formats. No rewriting immutable canonical bytes or changing source/financial hashes to make a new format pass.
- Recovery must verify source version/rights, prefix hash, event order, source ordinal/trust and tied timestamp group boundaries; fail closed on missing/corrupt evidence. Provider internals and future data never reach the browser/reducer.
- Working-set memory, spill, PostgreSQL WAL, backup retention and disk pressure count toward capacity. A tiny database with very slow chain reconstruction is **not** a win.

## 4. Measured acceptance plan — finite gates

**Gate A — read-only inventory:** record exact branch/commit, currently used runtime/DB schema, source/version receipts, per-Session timeline blocks and checkpoints, commands/result payload and existing QA-v3 experiment; review AGENTS, PR #20 and frozen contracts. No production mutation.

**Gate B — isolated parity prototype:** reuse CP6A-4/5 code and tests where applicable. Compare legacy vs compact on 0, 100 and 500 orders plus authored fill/SL/TP, fork, gap/UNRESOLVED, 72h Jump, idempotent retry, SIGKILL before/after commit, corruption and long cold-resume scenarios. Verify identical financial event hashes, result/receipt behavior, causal/revealed view and exact recovery.

**Gate C — bounded capacity:** on real structurally verified published source, compare no-trade replay and 100/1,000-trade workloads (only after smaller phases PASS). Report: PostgreSQL heap/index growth, cumulative WAL generated, timeline disk bytes per million tick groups, checkpoint/result bytes, wall and CPU times, RSS/cgroup peak, throughput, p50/p95/p99 apply/seek/restart, source/market clones count (must be zero), and long-prefix recovery amplification. Repeat under controlled cache conditions. Baseline against existing original, not a fabricated example like 5KB/trade.

**Gate D — guarded progression:** one-day gate first and then 7/30 days; year and 1→2→3→4→6-worker tests each require separate owner approval and current resource preflight. The 2026-11-05 reported host free space was 36.47 GiB with a 32 GiB minimum threshold and ~4.91 GiB MemAvailable; re-measure before any run. Preserve the stricter applicable Alpha gates (including host disk-utilization limit, memory and maximum checkpoint size). Do not buy hardware, delete evidence, or run heavy QA under this docs PR.

**Adoption rule:** select the Pareto candidate only if correctness, parity, recovery and resource limits hold. Roll back or hold if speedup comes from dropping required evidence. Migrate with additive versioned schema, dual reader, isolated restore rehearsal and owner-approved cutover.

## 5. Claude's 2026-11-05 technology audit — triage, not an acceptance vote

| Proposal | Review verdict for now | Reason / verification |
| --- | --- | --- |
| React + Vite + Lightweight Charts; FastAPI modular monolith; PostgreSQL; own exact financial reducer | **KEEP** | Existing implementation and contracts; no framework/engine rewrite. |
| PyArrow + Parquet compact market storage | **TEST / likely useful** | Measured format and one-day/cold/seek parity required. Day vs month; source provenance, exact bid/ask and equal-time events must survive. |
| DuckDB/Polars/NumPy | **OPTIONAL tools** | DuckDB tested previously only in an isolated columnar probe; reader vs execution engine is distinct. Do not add extra persistent DB or unbounded array cache. |
| Replace per-event identity with only file/row-group hashes; sort by time/ordinal; switch after a tiny parity test | **DO NOT ACCEPT AS WRITTEN** | May weaken V2 event identity, source order trust, causality, forensic evidence and rollback. Any new representation needs explicit contract-compatible identity and full staged proof. |
| Vectorized 72h Jump trigger scan | **RESEARCH candidate** | May help, but must match chronological reducer with pending/SL/TP, gaps, tied time, diagnostics and UNRESOLVED; no assumptions that all state changes are simple price crossings. |
| Compact receipts and periodic checkpoints | **ADOPT AS EXPERIMENT** | Existing QA-v3 has measured ~50% DB growth savings. Cold resume/fork/idempotency remain hard requirements; do not claim production-ready. |
| GitHub Actions CI, short current agent context, deploy recipe, consolidate HTTP entrypoints | **USEFUL, separate checkpoints** | Verify actual code/test/deployment dependency graph first. Do not move/delete existing authority documents or live routes in this task. |
| Public historical candle assets and market-data rights | **HIGH-PRIORITY OWNER/LEGAL REVIEW** | Main contains 964 files in frontend/public/market/decade (~278,635,671 bytes). Verify source and display/redistribution rights; any delete/history rewrite needs separate explicit authorization. |
| One VPS suffices for first paying users; 16×5 Parquet fits in 10–30 GB; December release | **ESTIMATES / NOT CERTIFIED** | Concurrency, full canonical schema, recovery footprint, real instrument densities, licensed data and launch gates are not proven. No storage/compute purchase claim. |

## 6. Review and ownership

1. Codex (backend) maps this proposal against PR #20 ADR-009, frozen contracts and the VPS actual source/state; Claude reviews UI/API compatibility. Publish explicit ACCEPT / NEEDS-CHANGE / REJECT with a specific evidence reference for every impact.
2. If owner approves, record the resulting decision **in the existing decision register/architecture authority** (not this document), then implement as small separately reviewed checkpoints. Keep a rollback reference and evidence receipts.
3. This change is **documentation only**; it does not change production, deployment, local QA files, Annual PASS, original market data, database schema, branches owned by another agent, or any running Codex session.

### References
- PR #20 proposed design: https://github.com/Obbiiee/Back-test-lab-project/pull/20
- Claude technology advisory (unmerged branch): https://github.com/Obbiiee/Back-test-lab-project/blob/docs/claude-audit-20261105/docs/CLAUDE_AUDIT_2026_11_05.md
- Isolated QA storage metrics: https://github.com/Obbiiee/Back-test-lab-project/blob/codex/cp6a10-postannual-handoff/docs/CP6A5_COMPACT_STORAGE_PERFORMANCE_2026-10-31.md
- Existing benchmark gate: https://github.com/Obbiiee/Back-test-lab-project/blob/main/docs/SINGLE_VPS_STORAGE_BENCHMARK_GATE.md
