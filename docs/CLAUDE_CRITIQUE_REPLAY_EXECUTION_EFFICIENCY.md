# Claude critique — replay execution efficiency and capacity (2026-11-13)

> **Status: ADVISORY REVIEW ONLY. Not architecture authority.**
> This document records an external review requested by the owner. It does not
> authorize implementation, change frozen contracts, or supersede
> `PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md`, `MARKET_DATA_STANDARD.md` or
> `AI_CONTEXT/04_CURRENT_PHASE.md`. Any adoption requires an explicit owner grant
> and must be recorded in the proper authority documents.

Reviewed baseline: `main` at `4fc9939` (shallow clone, 2026-11-13).
Owner question: *"With a 6 vCPU / 16 GB VPS and the most efficient design that stays
precise, how many concurrent traders can we serve? Is the current repo already the
most efficient design?"*

## 1. Verdict

The current design is **precision- and safety-first, not efficiency-first**. It is
server-authoritative per replay step. With the current hard limits it serves on the
order of **tens of concurrent replay sessions**, not hundreds or thousands, on a
6 vCPU / 16 GB host.

The strongest assets in the repository — a deterministic financial reducer,
canonical hashing, golden vectors (`backend/tests/fixtures/tick_execution_v1.json`,
`contract_hash_vectors.json`) and a JS vector verifier
(`backend/tests/verify_contract_vectors.mjs`) — are exactly what is needed to move to
a far cheaper architecture **without losing precision**.

## 2. Evidence (what makes each replay step expensive)

Each `ADVANCE`/`SEEK` takes this path:

1. Browser sends an HTTP request (`frontend/src/tickAlpha/client.js`).
2. `cloud/research.py` rewrites `apply` + `ADVANCE|SEEK` into the `replay` operation and
   inserts a row into `btl.research_jobs` (`cloud/queue.py::submit`, migration `009`).
3. A lifespan worker claims it with `FOR UPDATE SKIP LOCKED` plus an advisory lock
   (`cloud/queue.py::work_one`).
4. The work is executed through a native child process exchange (`cloud/worker.py`,
   `_Slot`, `pooled_invoke`, 30 s deadline).
5. The controller resumes the timeline from the checkpoint
   (`execution/controller.py`: `TickTimeline.resume(...)` or the 4-entry
   `execution/workspace.py` cache), runs the reducer and commits through a PostgreSQL
   transaction.
6. The browser polls job status (`AlphaWorkspace.jsx`, 500 ms timers).

So a single "next tick" costs several DB connections, at least one write transaction,
a process exchange and a poll round-trip.

Hard-coded ceilings found:

| Location | Value | Effect |
|---|---|---|
| `cloud/queue.py` | `WORKERS = 2` | at most 2 replay steps execute at once for the whole server |
| `cloud/queue.py` | `GLOBAL_LIMIT = 16`, `USER_LIMIT = 2` | 17th queued step server-wide → `429 QUEUE_CAPACITY` |
| `cloud/worker.py` | 2 native slots, `MAX_JOBS = 32` | process-level serialization |
| `cloud/research.py` | `Semaphore(2)` / `CapacityLimiter(2)` | request admission |
| `infrastructure/resources.py` | `DATABASE = Budget(12)`, `ApiAdmission(limit=8)` | DB/API concurrency caps |
| `infrastructure/database.py` | new `psycopg.connect` per call | no connection pool |

Repository's own measurement (`AI_CONTEXT/04_CURRENT_PHASE.md`): the ten-session probe
reached 14.6×–20.7× with sampled host RAM 85–95% and status
`CAPACITY_GATE_FAILED_FINAL_ACCEPTANCE_BLOCKED`. Ten sessions already approach the
limit (Windows laptop, not a reference host — a 6 vCPU VPS may be 2–3× better, still
tens).

## 3. How comparable open-source projects place execution

Audited 2026-11-13 (shallow clones, source inspected):

| Project | Execution location | Notes |
|---|---|---|
| William-Trader/zhuk-replay-studio | **Browser** (`src/orders.ts`, `model.ts`) | Order **action log** (`place`/`cancel`/`protect` with `seq`) → deterministic re-derivation of account state. Closest to the recommended pattern. |
| jezztify/backtesting-app | **Browser** (`TradingPanel.tsx`, tick playback) | Node backend only fetches Dukascopy data. README warns very large tick sets stress the browser. |
| cagriKarakulak/binance-tick-replay | **Browser** | Python only downloads/prepares data. |
| Jaxmy/ReplayLab | Server (FastAPI + NautilusTrader), every step is an API call | **Single user, Windows, bound to 127.0.0.1** — per-step cost is irrelevant there. |
| rjav1/momentum-strategy-studio | Server | Automated backtester; frontend only animates results. |
| Quod-Financial/quantreplay | Server (C++ matching engine, FIX) | Algo/bot testing, different problem. |
| Hallupa/SimpleTradingSimulator | Desktop (C#) | Local install. |

Pattern: server-per-step execution appears only in single-user local tools or algo
simulators. Multi-user web replay tools run the step loop client-side. (FX Replay and
Forex Tester Online are closed source; only their browser-only delivery is observable.)

## 4. Recommended target ("efficient but still precise")

Principle: **the server must not do work per replay step.** It serves data, records
commands, and produces the authoritative result by deterministic re-execution.

1. **Engine parity in the browser.** Port the financial reducer (`execution/engine.py`
   and the frozen financial contract) to TypeScript, or a single Rust core compiled to
   WASM + Python bindings. Run the same golden vectors in both runtimes; require
   byte-identical canonical hashes. No cutover until parity is 100%.
2. **Static, immutable, content-addressed data chunks.** Export V2 storage
   (`ticks/storage_v2.py` is already immutable/hierarchical) into compressed binary
   chunks (per hour/day), served by Nginx/Caddy + CDN with long cache, bypassing Python.
3. **Server as notary.** Browser submits a batched **command log** (orders, cancels,
   SL/TP changes, with tick-time references) on each order or every few seconds — one
   INSERT, no computation. A verification worker replays the log with the Python engine
   over the same canonical data at session end / on demand. Server results are the only
   source for statistics, Experiment Passport, leaderboards. Mismatch → session flagged.
4. **Backend cleanup.** Remove the per-step job queue path for ADVANCE/SEEK, the
   per-job native process exchange and 500 ms polling. Use `psycopg_pool`, one API
   worker per core, configurable (not hard-coded) limits, queue reserved for heavy jobs
   (verification, Monte Carlo, optimization; ~3–4 workers), SSE for notifications.

Expected on 6 vCPU / 16 GB: CPU near idle during replay, a few DB writes per minute
per user, bandwidth (CDN-offloaded) becomes the bottleneck → realistic capacity in the
**low thousands of concurrent active traders**. Estimate only; must be load-tested.

Client cost estimate (XAUUSD, to be measured, e.g. by adapting `ticks/benchmark_v2.py`):
<1–5% CPU at 100× replay; one day of ticks ≈ 3–7 MB in typed arrays (objects would be
5–10× larger); download ≈ 0.5–2 MB/day of ticks compressed; engine bundle 50–200 KB JS
or 200–500 KB WASM. Run the engine in a Web Worker and throttle chart redraws to
30–60 fps.

## 5. Conflict with frozen contracts — owner decision required

Section 4 **conflicts with the current No-look-ahead invariant** (AGENTS.md; frozen
42.17/42.19): the consumer/RevealedView must never receive future ticks. Shipping
chunks ahead of the cursor to the browser gives the client future data. Options for
the owner, not for an agent to choose:

- **A. Personal/practice mode:** accept client prefetch; authority remains the
  server re-execution of the command log, and the server rejects commands that
  reference ticks not yet revealed at their claimed time. Look-ahead only harms the
  user's own practice.
- **B. Strict mode (competition/leaderboard/Passport):** a cheap stateless release
  endpoint issues short-lived signed URLs for at most 1–2 chunks beyond the cursor;
  no DB transaction per step. Preserves near-causal release at much lower cost than
  today.
- **C. Keep the current strict per-step model** and only apply the low-risk
  optimizations below (target ~100–300 concurrent, unverified).

Low-risk optimizations compatible with current contracts (no frozen-contract change):
connection pooling; keep the timeline in-process instead of a child process per job;
batch ADVANCE (one per playback second instead of per tick group); persist checkpoints
on order events / every N steps instead of every step; replace polling with SSE;
workers = cores; make limits configuration.

## 6. Suggested checkpoint sequence (if the owner authorizes)

1. Parity spike: TS/WASM reducer + cross-runtime golden vectors (no UI change).
2. Chunk export + static serving (read-only, no execution change).
3. Command-log endpoint + server verification worker.
4. UI uses local engine behind an explicit mode flag; current path stays as rollback.
5. Remove the old per-step path only after load test and parity evidence.

Step 1 is the gate: if parity is not exact, stop.

## 7. Limits of this review

Static source reading and repository documents only. No tests, benchmarks or load
tests were run by Claude. Capacity numbers are estimates, not certification.
