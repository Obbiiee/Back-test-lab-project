# Claude critique — replay execution efficiency, capacity and full repository audit (2026-11-13)

Part A (sections 1–6): replay execution path and capacity.
Part B (section 8): whole-repository audit — data, frontend, backend/API, database,
security, testing/CI, deployment, low-end devices, documentation/process (B1–B12) and
resource efficiency: tick storage, RAM, CPU, PostgreSQL, disk/backup, bandwidth and a
measurement plan (B13–B19) — each with evidence, impact and proposed solution.
Section 9 gives the combined priority order.

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

Static source reading and repository documents, plus: `vite build` (output sizes
below), backend `unittest` (351 run, 82 skipped without PostgreSQL, OK) and
`frontend/tests/repository.test.mjs` (PASS). No load test, browser profiling or VPS
inspection. Capacity and size numbers are estimates unless stated as measured.

## 8. Part B — whole-repository audit

Each finding: **evidence → impact → solution**. "Contract" notes whether the solution
touches frozen authority (owner grant required) or is contract-neutral.

### B1. Market data stored as JSON inside git and shipped inside the frontend build (HIGH)

- Evidence: `frontend/public/market/decade/` holds 964 tracked files, ~279 MB
  (measured). Per month there are 8 pre-aggregated timeframes (1m, 3m, 5m, 15m, 30m,
  1h, 2h, 4h) as text arrays `[[time,o,h,l,c],…]`. The 1m files alone are ~167 MB; the
  other 7 timeframes add ~111 MB (40%) of data derivable from 1m. `vite build` copies
  `public/` into `dist/`, measured **273 MB dist** — every deploy ships the dataset.
  `.git` is already 72 MB and grows with every data refresh.
- Measured on `2024-10-1m.json` (31,731 bars): JSON 1.5 MB → gzip 380 KB →
  delta-encoded int32 columns + deflate **210 KB** (≈7× smaller than raw, ≈1.8×
  smaller than gzip JSON, also much faster to decode than `JSON.parse`).
- Impact: slow clones/CI/deploys, wasted VPS disk and bandwidth, slow parsing on weak
  phones, data versioning mixed with code versioning.
- Solution:
  1. Move market data out of git into an immutable, content-addressed store
     (object storage or a VPS directory behind Caddy/CDN with
     `Cache-Control: public, max-age=31536000, immutable`). Git keeps only a manifest
     (file → hash → size → source/provenance).
  2. Columnar binary format: delta-encoded int timestamps and fixed-point prices
     (respecting source precision per Market Data Standard), compressed with
     brotli/zstd; decode into typed arrays in a Web Worker.
  3. Store only 1m (plus optionally 1h/D for fast overview); derive other timeframes
     client-side — aggregation of 1m is trivial CPU. Candles remain display-only, so
     this does not touch execution authority.
  4. Exclude market data from `dist/` (build only code/assets).
- Contract: neutral for display candles; tick evidence formats stay as frozen.

### B2. Three execution engines coexist (HIGH, maintenance/correctness)

- Evidence: (1) `frontend/src/trading/simulator.js` + `useTrading.js` +
  `AccountPersistence.js` (candle-based, localStorage account); (2) legacy
  `backend/api/main.py` (FastAPI v0.4) → `services/replay_service.py` →
  `backend/engine/{replay,trading}` (candle-based); (3) `backend/execution` tick engine
  (current authority direction). `main.jsx` still eagerly imports the legacy
  `FigmaWorkspace` for `?legacy=local`.
- Impact: triple maintenance, risk that results silently differ between paths, larger
  bundle, confusion for agents about which engine is authoritative.
- Solution: declare `backend/execution` (and its future TS/WASM twin from Part A) the
  only financial engine. Freeze the other two as read-only rollback, then retire:
  remove the legacy FastAPI app and `backend/engine` once no test/fixture depends on
  them; keep `simulator.js` only if the owner wants a no-account "quick practice"
  mode, labelled non-authoritative.
- Contract: retirement needs owner grant (protected systems list).

### B3. Frontend bundle and loading (MEDIUM)

- Evidence (measured `vite build`): main `index` chunk 358.6 KB (112.8 KB gzip),
  `RiskRewardGeometry` 182.9 KB (59.6 KB gzip), `index.css` 117 KB, and
  `src/assets/riksora-mark.png` **1.23 MB**. `main.jsx` statically imports
  `FigmaWorkspace`, `PrototypeEntry`, `TickReviewEntry`, `TickAlphaEntry`,
  `AlphaAccount` — every route pays for all of them.
- Solution: `React.lazy` per route (legacy, prototype, tick review, account); convert
  the logo to SVG or WebP/AVIF at display size (expected tens of KB); split
  RiskReward geometry from the default path if not needed on first paint; purge
  unused CSS from legacy workspaces. Expected: first-load JS roughly halved and
  ~1.2 MB less image on every cold visit.
- Contract: neutral.

### B4. Per-transition full recomputation in chart/indicators (MEDIUM, low-end devices)

- Evidence: `AI_CONTEXT/02_ARCHITECTURE.md` — IndicatorEngine "retains full
  recomputation/setData for every transition"; replay settlement prefix validation
  "remains linear".
- Impact: per-step cost grows with history length; noticeable on weak phones and long
  sessions.
- Solution: incremental indicator state (SMA/EMA/RSI/ATR/MACD/Stochastic/Bollinger
  keep rolling state; update only the latest bucket via `series.update`), with the
  existing reference calculators as golden tests (full recompute must equal
  incremental result). Replace linear prefix validation with a rolling hash
  checkpoint of the revealed prefix. Full `setData` stays as the fallback for seek,
  timeframe change and errors.
- Contract: neutral if equality tests are kept.

### B5. API rate limiter: one DB write per request, keyed per IP (HIGH, availability)

- Evidence: `identity/boundary.py::_attempt` runs on **every** `/api/v1/` request:
  opens a new `psycopg.AsyncConnection` (`identity/store.py::connection`, no pool),
  UPSERTs `btl.auth_rate_limits`, and DELETEs old buckets; default limit
  `rate_limit=30` per minute per client IP (`cloud/app.py`).
- Impact: (a) every API call costs an extra connection + 2 write statements;
  (b) a single replaying user polling every 500 ms already exceeds 30/min
  (`AlphaWorkspace.jsx` contains a `RATE_LIMITED` 10 s back-off path); (c) Indonesian
  mobile carriers use CGNAT — many users share one public IP and would rate-limit each
  other.
- Solution: in-memory token bucket per process (or Redis if multiple processes) keyed
  by authenticated user id for authenticated routes, by IP only for anonymous/auth
  routes; keep the strict per-account login/reset limits (they are correct). Separate
  limits per route class (auth vs. data vs. commands). Remove the DELETE from the hot
  path (periodic cleanup). Use a shared `psycopg_pool.AsyncConnectionPool`.
- Contract: security boundary change — owner/security review, but no financial change.

### B6. Database connections and growth (MEDIUM)

- Evidence: sync `infrastructure/database.py::connect` and async
  `identity/store.py::connection` both open a fresh connection per call, guarded by
  `DATABASE = Budget(12)`. Session auth uses FastAPI Users `DatabaseStrategy` (token
  lookup per request). `tick_events` / `tick_checkpoints` (migration 005) receive rows
  per replay step.
- Solution: one sync and one async pool sized to cores; consider PgBouncer if several
  processes. With the Part A notary model, per-step rows disappear; otherwise add
  retention/compaction (keep events, prune superseded checkpoints) and time/session
  partitioning before beta growth. Add `EXPLAIN` checks for the queue polling query.
- Contract: checkpoint retention touches frozen evidence — owner grant.

### B7. Single process server (MEDIUM)

- Evidence: `cloud/serve.py` starts one `uvicorn.Server` (one event loop, one
  process); heavy work goes through threads/child slots.
- Solution: run N processes (e.g. `uvicorn --workers` or gunicorn with uvicorn
  workers, N ≈ cores) behind Caddy; move queue workers to a separate systemd service so
  API latency is isolated from heavy jobs. Requires the in-process caches and
  rate-limit state to be either per-process-safe or externalized (B5).
- Contract: neutral.

### B8. No CI; PostgreSQL tests skipped by default (HIGH, quality)

- Evidence: no `.github/workflows/`. Backend run: 351 tests, **82 skipped** without a
  database. Frontend has ~40 separate `test:*` scripts plus `test:regression`.
- Impact: PRs (including agent PRs) merge without an automatic gate; the most
  important persistence/financial tests only run when someone has PostgreSQL locally.
- Solution: GitHub Actions workflow: Node + Python + `postgres:16` service; run
  backend unittest (0 skips required), `test:regression`, `test:repository`, lint,
  build, golden vectors (`verify_contract_vectors.mjs`). Make it a required check on
  `main`. Cache npm/pip. This also gives Codex/Claude objective pass/fail instead of
  self-reported evidence.
- Contract: neutral.

### B9. Deployment not reproducible from the repository (HIGH, operations)

- Evidence: no deploy/systemd/Caddy/backup scripts tracked. `docs/AI_HANDOFF.md`
  (2026-10-24) records: deployed API commit not an ancestor of main, API and static UI
  from different lineages, backup directory unreadable without sudo, rollback
  unverified → NO-GO.
- Solution: track `deploy/` (Caddyfile, systemd units, env template without secrets,
  backup + restore scripts); build immutable release artifacts in CI tagged with the
  commit; deploy = upload artifact + switch symlink + health check, rollback = switch
  symlink back; nightly `pg_dump` with off-host copy and a monthly restore test into a
  separate database. Market data deployed separately (B1).
- Contract: neutral (infrastructure), owner approval for the VPS.

### B10. Low-end laptops/phones (MEDIUM, product reach)

- Expected to run on ~3–4 GB RAM phones and 4 GB laptops if: engine in a Web Worker;
  typed arrays; keep only hours–1 day of ticks around the cursor; cap rendered bars
  (~2,000–5,000) with lazy history; throttle redraw to 20–30 fps on mobile and never
  redraw per tick; limit simultaneous indicators/drawings in a mobile preset; lower max
  replay speed on mobile. 2 GB devices are at risk of tab eviction.
- Optional "light mode": play M1 candles for display and switch to tick resolution
  only when an order is near price; authoritative results still come from server tick
  re-execution, so precision of official results is unchanged.
- Needs measurement on real devices (Chrome DevTools performance + memory panel,
  WebPageTest on a mid-range Android profile).

### B11. Smaller items (LOW)

- `market/useGoldMarket.js` calls `https://api.gold-api.com/price/XAU` directly from
  the browser: third-party availability/terms dependency; proxy and cache it
  server-side or label it non-authoritative.
- Drawings and several preferences persist only in `localStorage`
  (`drawings/useDrawingTools.js`, `tickAlpha/*`): paid users lose them across devices
  and browsers. Sync per Session through the API (small JSON, debounced).
- `legacy/` (root, 39 files) and `frontend/legacy/phase3/` (50 files) are fixtures;
  keep, but move under `tests/fixtures/legacy` to make the boundary obvious.
- API responses are all `Cache-Control: no-store` (correct for account data); ensure
  any future static/market endpoint is excluded so CDN caching works.

### B12. Documentation and process overhead (HIGH for agent efficiency)

- Evidence: 134 files under `docs/`; `docs/` + `AI_CONTEXT/` ≈ **4.8 MB** of text.
  `AI_CONTEXT/04_CURRENT_PHASE.md` is 33 KB of stacked "Latest human grant"
  paragraphs; `03_PHASE_HISTORY.md` 78 KB; `07_TEST_COMMANDS.md` 47 KB;
  `docs/AI_HANDOFF.md` 1,646 lines.
- Impact: each agent session spends a large share of its context reading history,
  which raises cost, slows work and increases the chance of contradictory
  interpretation (several grants supersede each other in prose).
- Solution (keeps all history, changes only what is read first):
  1. `04_CURRENT_PHASE.md` ≤ ~3 KB: the JSON pointer + the single active grant + open
     blockers. Move older grants verbatim to `docs/archive/grants-2026.md`.
  2. `AI_HANDOFF.md`: keep the last 5–10 entries; archive the rest by month.
  3. `07_TEST_COMMANDS.md`: replace prose with one `npm run test:all` /
     `make test` entry point (also used by CI, B8).
  4. `00_START_HERE.md` lists the minimal reading set per task type
     (frontend/UI, backend, data, ops) so agents do not load everything.
  5. Keep the `repository.test.mjs` authority checks, updated for the archive paths.
- Contract: touches the AI-context authority structure — owner grant; no product
  contract change.

### B13. Tick storage footprint — the largest efficiency problem (CRITICAL)

- Evidence (Codex measurements recorded in `docs/AI_HANDOFF.md`, 2026-10-23/24):
  - One accepted EURUSD month, 1,496,361 ticks: validation store **479,637,504 B
    (≈320 B/tick)** + serving replica **124,080,128 B (≈83 B/tick)**.
  - Parquet PoC: 14,888,706 B per 100,000 ticks (**≈149 B/tick**) because each row
    keeps exact Bid/Ask strings, source/event IDs, textual ordinal, full canonical
    bytes, a per-row SHA-256 and the original raw record bytes.
  - Linear forecast for the audited 2,451,954,017 rows: ≈786 GB validation,
    ≈989 GB validation+serving (also ≈545 GB with the normalized layout) versus
    ≈150–163 GB free. Eight-symbol 11-month beta alone: ≈104–121 GB new copies,
    ≈242 GB with a local backup → NO-GO.
  - Meanwhile the **entire retained raw HistData root is ≈15.2 GB** (15,209,961,033 B),
    i.e. the source itself is ≈6 B/tick. Derived stores are ≈50–65× larger than the
    evidence they are derived from.
- Root cause: integrity and provenance are stored **per row, redundantly, in every
  copy** (canonical bytes + raw bytes + digest + string IDs), and validation and
  serving are separate full copies.
- Solution (keeps exact precision, provenance and verifiability):
  1. **Raw source archive = the evidence.** Keep the original GZIP files immutable,
     pinned by SHA-256 (already done). They are the only copy that must be preserved
     byte-for-byte.
  2. **Deterministic derivation instead of stored canonical bytes.** Canonical ticks
     are a pure function of (raw file hash, parser version, admission policy
     version). Store that recipe plus the result hash; anyone can re-derive and
     re-verify. Per-row canonical bytes and per-row raw bytes need not be stored.
  3. **Integrity per chunk, not per row.** Hash each chunk (e.g. one hour or one
     timestamp-group range) and build a Merkle tree per month/dataset; the root hash
     is pinned in the registry/Passport. Tampering with any tick changes the root.
     Proofs for a single tick are a few hashes (log₂ n), not 32 B per row.
  4. **One compact serving format.** Columnar chunk: `int64` ns timestamp as
     delta/zigzag varint, Bid and Ask as fixed-point integers at the **source
     precision** (store the scale per chunk, so no rounding and no float error),
     Ask stored as spread from Bid, optional source ordinal as delta; compressed
     with zstd (or brotli for web delivery). Equal-time groups remain atomic because
     chunks split only at group boundaries.
  5. **No separate validation copy at rest.** Validation runs at admission time and
     outputs a report + hashes; it does not need its own permanent full copy. If a
     queryable index is required, keep a small per-chunk index (time range, row
     count, hash, byte offset), not per-row rows.
- Expected size: synthetic EURUSD-like stream (70,000 ticks, ms timestamps,
  integer pip deltas) measured **≈2.2–2.9 B/tick** with delta + deflate/xz; real data
  has more entropy, so plan for **≈3–8 B/tick**. Full 2.45 B-row corpus ≈ **7–20 GB**
  instead of ≈786–989 GB; eight-symbol beta year ≈ 1–3 GB. This must be confirmed by
  a real-data PoC (one EURUSD + one XAUUSD month) with exact canonical-hash parity
  against the current store.
- Contract: changes storage/evidence representation (Market Data Standard, 42.17/42.19
  storage contract) — **owner grant required**. Execution semantics, Bid/Ask
  exactness, ordering trust flags and no-look-ahead are unchanged.

### B14. Server RAM budget for 6 vCPU / 16 GB (HIGH)

- Evidence: internal probe 10 sessions → sampled host RAM 85–95%
  (`04_CURRENT_PHASE.md`); Parquet/DuckDB full scan VmHWM 415 MB, Arrow-only
  154 MB, SQLite reader ≈47 MB per process (handoff measurements); per-job native
  child processes (`cloud/worker.py`); per-process timeline cache
  (`execution/workspace.py`, 4 entries).
- Impact: memory grows with sessions × processes × caches; a heavy scan job can
  push the host into swap and stall the API.
- Solution — explicit budget, enforced by systemd `MemoryMax=` per service:

  | Component | Budget | Notes |
  |---|---|---|
  | OS + Caddy + page cache floor | 2 GB | page cache benefits chunk serving |
  | PostgreSQL | 4 GB | `shared_buffers=2GB`, `effective_cache_size=6GB` |
  | API processes (4–6) | 3 GB | ≈300–500 MB each, no market data in-process |
  | Queue / verification workers (3) | 4.5 GB | `MemoryMax=1.5G` each; DuckDB `memory_limit` + streaming reads |
  | Reserve | 2.5 GB | no swap thrash; alert at 80% |

  - Stream chunks instead of loading months; cap per-request result size (already
    8 MB — keep it).
  - Bound caches by bytes, not entry count; one shared chunk cache (OS page cache or
    a single process) instead of per-session copies.
  - With the Part A notary model, per-session server RAM ≈ 0 during replay.
- Contract: neutral.

### B15. CPU budget (MEDIUM)

- Evidence: per-step replay work on the server (Part A); conversion 47.7 s CPU per
  100k EURUSD ticks in the Parquet PoC (≈2,100 ticks/s single thread) — ingestion of
  2.45 B rows at that rate ≈ 13 CPU-days; single uvicorn process (B7).
- Solution:
  - Ingestion: vectorized parsing (PyArrow CSV reader / Polars) instead of per-row
    Python; process months in parallel with `nice` and CPU affinity off the API cores;
    target ≥ 500k–1M ticks/s per core (to be measured).
  - Reserve cores: e.g. 2 vCPU for API + PostgreSQL, 4 vCPU for workers via
    systemd `CPUQuota=`/`AllowedCPUs=`; ingestion only off-peak.
  - Verification re-execution (Part A) is linear in ticks of the session window;
    measure ticks/s of the reducer and set per-user job quotas.
- Contract: neutral.

### B16. PostgreSQL tuning and write amplification (MEDIUM)

- Evidence: no PostgreSQL configuration is tracked in the repository; hot-path writes
  per API request (B5) and per replay step (Part A); queue table polled every 0.25 s
  per worker (`cloud/queue.py` lifespan loop) with `FOR UPDATE SKIP LOCKED`.
- Solution:
  - Track a reviewed `postgresql.conf` fragment in `deploy/` (B9):
    `shared_buffers=2GB`, `effective_cache_size=6GB`, `work_mem=16MB`,
    `maintenance_work_mem=512MB`, `max_connections=50` (pools in front),
    `wal_compression=on`, `checkpoint_timeout=15min`, `max_wal_size=4GB`,
    SSD: `random_page_cost=1.1`.
  - Aggressive autovacuum on hot tables (`research_jobs`, `auth_rate_limits`,
    `tick_*`): lower `autovacuum_vacuum_scale_factor` per table.
  - Replace 0.25 s queue polling with `LISTEN/NOTIFY` (wake on insert) plus a slow
    fallback poll.
  - Remove per-request rate-limit writes (B5) and per-step checkpoint writes
    (Part A / B6) — these dominate WAL volume.
  - Enable `pg_stat_statements` to find the top queries before tuning further.
- Contract: neutral.

### B17. Disk I/O, backup and retention (HIGH)

- Evidence: backup of new stores would need ≈242 GB (B13); handoff notes
  `riksora-beta-backup` exists but contents/off-host copy unverified; local
  file-copy drill is explicitly not disaster recovery.
- Solution:
  - After B13, the whole market corpus is small enough (≈7–20 GB) to back up
    off-host cheaply (object storage, e.g. Backblaze B2 / Cloudflare R2 / Wasabi);
    raw GZIP archives backed up once (immutable, verify by hash).
  - PostgreSQL: nightly `pg_dump -Fc` (or `pgBackRest` with WAL archiving for
    point-in-time recovery), encrypted, off-host, 7 daily / 4 weekly / 6 monthly
    retention; monthly automated restore test into a scratch database.
  - Separate volumes/directories for OS, PostgreSQL, market data, backups; alert at
    75% disk.
  - Retention: delete scratch/experiment copies after their report is pinned
    (owner-approved policy); never auto-delete evidence.
- Contract: deletion policies require owner grant.

### B18. Network bandwidth (MEDIUM)

- Estimate (to be measured): compact ticks ≈ 0.2–0.6 MB per symbol-day; a
  user replaying ~100 symbol-days per month ≈ 20–60 MB; 1,000 active users ≈
  20–60 GB/month of chunk traffic, plus app assets. Current JSON candles are
  ≈1.5 MB/month per timeframe file and re-downloaded without content addressing.
- Solution: content-addressed immutable URLs + CDN (Cloudflare free tier is enough
  at this scale) so most traffic never reaches the VPS; brotli for text assets;
  HTTP caching headers on static chunks; per-user download quotas for abuse.
- Contract: neutral (respect data-rights gates before any public distribution —
  HistData hosted/public rights are still UNKNOWN per handoff).

### B19. Measurement plan (so the numbers above become evidence)

Estimates in this review must be replaced by measurements before decisions:

1. **Storage PoC (B13):** one EURUSD and one XAUUSD month → compact chunk format;
   report B/tick, encode/decode ticks/s, canonical-hash parity with the current
   store, Merkle root reproducibility.
2. **Server load test:** k6 or Locust against a staging VPS with the real
   API: 10 / 50 / 200 / 1,000 simulated users; record p95 latency, CPU per core,
   RSS per process, PostgreSQL TPS/WAL MB/s, error rate. Run before and after
   B5/B6/B7 and Part A option C.
3. **Client profile (B10):** Chrome DevTools performance + memory on a 3–4 GB
   Android phone and a 4 GB laptop: heap MB, long tasks, fps at 1×/10×/100× replay.
4. **Bandwidth:** bytes per session from the load test and real beta logs.
5. Record all results in the proper authority document (system blueprint), not
   only in the handoff.

## 9. Combined priority order

| # | Item | Impact | Effort | Contract |
|---|---|---|---|---|
| 1 | B8 CI with PostgreSQL, required check | quality gate for everything else | low | neutral |
| 2 | B13 compact tick storage PoC (chunk hashes, fixed-point, zstd) | ≈786–989 GB → ≈7–20 GB forecast; unblocks data NO-GO | medium | owner grant |
| 3 | B5 rate limiter + connection pools (B6) | removes a real availability bug | low–medium | security review |
| 4 | B19 measurement plan (load test, storage PoC, client profile) | turns estimates into evidence | low–medium | neutral |
| 5 | B1 market data out of git/dist, binary + derive TFs | −270 MB deploy, faster load | medium | neutral (display) |
| 6 | B9 + B17 reproducible deploy, off-host backup, restore tests | removes NO-GO blocker | medium | neutral / retention needs grant |
| 7 | B14 + B16 RAM budget, systemd limits, PostgreSQL config | stability under load | low | neutral |
| 8 | Part A step 1: engine parity TS/WASM + golden vectors | unlocks Part A | medium–high | owner grant |
| 9 | Part A low-risk optimizations (option C list) | 2–5× replay capacity | medium | neutral |
| 10 | B3 lazy routes + logo | faster first load | low | neutral |
| 11 | B4 incremental indicators | low-end devices | medium | neutral with tests |
| 12 | B12 documentation slimming | agent cost/clarity | low | owner grant |
| 13 | B2 single engine / retire legacy | maintenance | medium | owner grant |
| 14 | B15 vectorized ingestion, CPU reservation | faster imports | medium | neutral |
| 15 | Part A full notary architecture (options A/B) | thousands of users | high | owner grant |
| 16 | B7, B10, B11, B18 | scale/reach polish | varies | neutral |
