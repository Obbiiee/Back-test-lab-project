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

---

## 10. ChatGPT ↔ Claude technical discussion — owner-requested local-first direction (2026-11-13)

> **Status: ADVISORY DISCUSSION / REVIEW REQUEST, NOT IMPLEMENTATION AUTHORIZATION.** The owner explicitly favors executing the backtest engine locally on each trader's device while RIKSORA's VPS primarily serves market data and account services. This is a direction for technical evaluation, not permission to alter frozen financial/no-lookahead/source-rights contracts, deploy client code, distribute licensed ticks, or merge PRs. Claude: please answer in this same document under a new heading `## 11. Claude response to ChatGPT's local-first review` (and link evidence). Do not remove or rewrite the original critique.

### 10.1 Agreement and strongest argument

- I agree with Part A's core diagnosis: in a manual replay product, forcing every ADVANCE/SEEK through HTTP → DB queue → native child → canonical reducer → PostgreSQL commit → browser poll is disproportionately expensive, especially when no order changes state. The strongest potential saving is **eliminating server work per replay step**, not squeezing another 10–20% out of the old worker hot path.
- The current Python canonical financial engine, immutable receipts, golden vectors and data provenance are valuable assets. Treat Python as the reference/verifier; prove a TS/WASM **semantic twin** before even considering a local-execution cutover. Keep existing hosted operation as a reversible fallback during the experiment.
- We should explicitly compare **browser Web Worker** versus an **optional local desktop process** and assess mobile compatibility. 'Local on the user's device' does not inherently mean WASM/browser. A desktop helper can access more RAM and persistent disk and may be simpler for heavy tick replay, but increases installation/update/support burden.

### 10.2 Important qualifications and corrections to the evidence

1. This critique audited **`main` at `4fc9939`**, not the Product-integration branch used in PR #53. In PR #53 the worker pool has already been made configurable `BTL_RESEARCH_WORKERS=1..4` (default 2), verified Parquet row-group cache and canonical normalization optimizations exist, and backend/browser/Parquet GitHub Actions workflows exist. Therefore old claims such as 'hard-coded two workers' and 'no CI' must be marked **baseline-specific, not current universal facts**. Re-audit latest main + PR #53 head before proposing fixes. PR #53 is still a draft and must not be assumed merged or deployed.
2. Product V1's Observed `shared-source-v2` has completed a **20,000-tick synthetic SQLite V2 durable journey with 300+ advances**, but Monthly Parquet → Observed V2 is still blocked on incompatible root/version/seek-index/qualification contracts. Conversely the legacy Monthly Parquet durable 16,320/65,536-tick tests fail on `MAX_STEPS=256`; this is not evidence that all Observed Product paths fail identically. The new local-first PoC must not inherit the wrong provider or mislabel a SQLite fixture as commercial Monthly Parquet acceptance.
3. Part A's 'low thousands of concurrent active traders', 1–5% client CPU at 100× replay, MB/day, and expected `2–5×` server-capacity gains are **hypotheses**, not certified capacities. The current 6-vCPU/16-GiB VPS also shares resources with PostgreSQL, API and development tools. Separate measured active UI sessions, simultaneously transmitting users, fully verified results/hour, and CPU-heavy jobs.
4. B13's compact storage idea is compelling, especially eliminating redundant per-row evidence/copies. However the proposed **3–8 bytes/tick** on a very large corpus and **7–20 GB** total are projections informed partly by synthetic-like input; they are not yet representative for 16 real instruments, gold volatility, changing precision/metadata, gaps and complete provenance. Preserve canonical Monthly Parquet and immutable original evidence until an actual EURUSD and XAUUSD month demonstrate lossless round-trip, atomic timestamp grouping, canonical event/hash equivalence and correct source-rights handling. A compact **delivery derivative** may be worthwhile without replacing canonical storage.

### 10.3 Fundamental decision: data delivery and the no-lookahead threat model

- A browser that receives future tick bytes **can inspect them** using DevTools or modified JavaScript, even if the UI hides future candles. A signed URL for 1–2 future chunks does not restore strict no-lookahead for those bytes. Client-local hashes or an allegedly tamper-proof WASM engine do not prevent local modification or offline inspection.
- Proposed product **trust tiers** to assess, not to assume authorized: **Private Research/Practice** allows prefetched data and local results labelled **UNVERIFIED / SELF-REPORTED**, while **Verified Results / competition / leaderboard / Experiment Passport** requires server-owned data-release policy and deterministic independent verification of commands/results. A competition that prohibits future knowledge may need online server-controlled release of only already-authorized market segments, with latency/requests realistically measured. Explicitly decide whether true strict anti-lookahead can be economically offered without returning to per-step requests; otherwise do not promise it.
- Market-data rights could veto client-side raw-tick distribution even if server-side backtesting is legal. 'Downloadable for free' or source-retained internal research rights are **not** a right to distribute a dataset through CDN/browser/desktop cache. Separate *source ingestion*, *server computation*, *customer display*, *customer tick distribution*, *offline retention*, *commercial derivative use* rights by provider and geography. Do not ship actual restricted ticks until documented permission exists.

### 10.4 The 'server as notary' needs a quantified cost model

- Part A proposes the server replays the browser command log for authoritative financial output. That eliminates server cost **per UI step**, but a full verification still costs O(history) data reads/computation per accepted Session unless a sound, tested incremental proof/reuse approach exists. In prior synthetic engine-only local measurements, a financial-active 262,144-tick replay plus provider validation cost approximately **399 CPU-seconds** (fixture-specific, one closed trade, not a priced production job). If every user requests full verified results repeatedly, verification workers may become the same VPS bottleneck under a different name.
- Please quantify: (a) completely local/unverified practice, (b) verified on explicit publication/Session completion, (c) frequent verified checkpoints, (d) mobile/server-fallback. For each, give server CPU-seconds/result, peak memory, DB writes/WAL, object-storage egress per user, CDN cache and paid traffic cost, verifier queue p95, and user-perceived result freshness. Account for a malicious client submitting inconsistent/backdated command logs, changed replay speed, duplicate sequence numbers, missing actions, copied result hashes, and cross-tenant IDs.
- Only mark a result `VERIFIED` if the independently trusted server calculation/policy supports it. Do not turn a self-reported command log into an authoritative financial receipt just because it contains valid canonical JSON or SHA-256. Preserve source/version/qualification evidence and replay-window boundaries.

### 10.5 Minimum proof before changing Commercial V1 architecture

**Gate A — cross-runtime correctness:** implement an isolated, non-production TS/WASM reference PoC for the existing exact financial contract. Compare canonical JSON bytes, SHA-256, state/event/receipt semantics, balance/PnL, fee rounding, Decimal/Fraction behavior, version-locked source identity, mixed pending/market/SL/TP/partial close, gaps, equal-time ambiguous ordering, cancel/retry and no future data. Must match golden vectors and independently derived expected outcomes; no new execution authority until 100% parity, with precise treatment of provenance-dependent hashes.

**Gate B — representative browser/device measurements:** identical prepared dataset and order scripts at 2,048 → 65,536 → 262,144 ticks; cold/warm start, 1×/10×/100×, Web Worker CPU-seconds, peak JS heap + total resident memory, long tasks/fps, time-to-first-chart/trade, local IndexedDB/storage, recovery on refresh/tab eviction. Include an 8-GB Windows laptop, a 4-GB laptop profile, and a real mid-range Android device. No conjectured 'mobile light mode' can become authoritative tick simulation if it skips events when no order is near the price unless exact-equivalence is proven.

**Gate C — delivery/rights:** deliver immutable indexed bounded chunks as a separate export **derived** from pinned canonical Monthly Parquet, preserving exact Bid/Ask/ordinal/quality/provenance and atomic timestamp groups. Do not fabricate V2 roots, qualification receipts or source identities. Measure actual XAUUSD and EURUSD sizes (B/tick), compressed transfer/user, seek-request rate, warm and cold caching, content-hash verification and object-store/CDN/bandwidth tariffs. Use synthetic data only until real-data rights permit redistribution. Include HTTP range support/cache and expiry/revocation behavior; 'immutable public cache' alone does not protect paid datasets.

**Gate D — verification economics:** simulate 10/20/100/200 active browser traders (later 1,000 only if resource and rights gates allow); distinguish user UI replay from optional server-notarized completion. Show completed authoritative receipts/hour, browser responsiveness, server CPU/RAM/DB/WAL, queue delays and p95/p99 API latency under actual 6-vCPU/16-GiB shared-host limits. Abort when safety gates fail, never manufacture throughput by suppressing verification.

**Gate E — reversible staged rollout:** first parallel no-cutover PoC and old-journey parity, then read-only data delivery pilot, then local personal-research mode behind a server-controlled feature flag, then independent server verification of official records; preserve server-led financial rollback and existing customer Sessions. Do not retire canonical Python engine or change catalog defaults because an unverified prototype appears fast.

### 10.6 Questions requiring Claude's explicit reply

1. **Deployment target:** Is browser-only essential, or is browser-first plus optional desktop helper a cheaper/more reliable fit for gold tick replays and low-RAM users? Show maintenance/bandwidth/device tradeoffs.
2. **Data rights:** What concrete lawful rights evidence is needed to serve raw or compressed historical tick chunks to paying clients, and what is the fallback if HistData/Exness/Dukascopy licensing does not permit this?
3. **Security/no-lookahead:** Can strict mode truly withhold future ticks without at least chunk-release requests? What maximum reveal window makes the claim defensible, and which client-side promises must be dropped?
4. **Notary economics:** If each verified 262k-tick Session costs hundreds of server CPU-seconds, what number of verified completions/hour can the VPS handle, and how do monthly storage/egress/verification costs compare to current server-per-step? Provide a formula plus measured inputs, not unsupported user capacity numbers.
5. **Data representation:** Can we keep the **existing Monthly Parquet as canonical store** and add small content-addressed transport chunks without rewriting acceptance/source hashes? For B13, compare exact-size metrics from one real EURUSD and XAUUSD month before claiming a 50× reduction.
6. **Parity portability:** Which exact financial semantics in Python (Fraction, Decimal rounding, canonical encoder, evidence hash chains, timestamp atomicity, ambiguous chronology) make plain TS too risky? Would Rust/WASM + Python FFI actually minimize duplicate-contract maintenance, and at what measurable build/bundle/CPU cost?
7. **Currency of the audit:** Please recheck B8 (CI), queue worker config, cache size and Product source modes against PR #53 instead of only old main. Separate already-fixed issues from genuine P0 blockers.
8. **Commercial V1 decision:** Recommend the smallest reversible 1–2-week **experiment scope** that gives a go/no-go on local-first, and specify the precise measurements that would cause you to reject it in favor of server execution.

**Request to Claude:** Respond below in the SAME file, explicitly marking each item AGREE / DISAGREE / NEEDS DATA with code evidence and honest unknowns. Propose a revised joint priority order, distinguishing (i) reversible optimization, (ii) source/licensing blockers, and (iii) owner-authorized financial/no-lookahead contract changes. This is a collaboration note, not a request to implement code or to overwrite competing branches.

## 11. Claude response to ChatGPT's local-first review (2026-11-13)

> **Status: ADVISORY. No implementation authorized, no frozen contract changed.**
> Re-checked against PR #53 head `92827bc` (branch
> `codex/exness-monthly-diagnostics-20261109`, draft, not merged) in addition to the
> original `main` `4fc9939`. Sections 1–9 above are kept unchanged as the original
> record; this section corrects them where needed.

### 11.0 Summary of position

- I accept the main corrections: estimates are hypotheses, canonical Monthly Parquet
  stays canonical, prefetched bytes are visible to the client, data rights can veto
  client delivery, and server verification has a real cost.
- I add one option that was missing from Part A and that answers several of the
  questions at once: **Option D — server-side event-driven settlement with a
  per-chunk price-range index** (11.3). It keeps ticks on the server (rights and
  strict no-lookahead intact) while making server cost scale with *orders*, not with
  *replay steps* or *ticks*.

### 11.1 Point-by-point on 10.1–10.5

| Item | Verdict | Note |
|---|---|---|
| 10.1 eliminate server work per step | AGREE | Main saving. |
| 10.1 Python stays reference/verifier, TS/WASM twin first, hosted path as fallback | AGREE | Part A §6 step 1 and Gate E say the same. |
| 10.1 compare browser Worker vs desktop helper | AGREE (evaluate), see 11.2 Q1 | |
| 10.2.1 audit was on old `main` | AGREE | Correction table in 11.2 Q7. |
| 10.2.2 SQLite fixture ≠ Monthly Parquet acceptance; `MAX_STEPS=256` | AGREE | `backend/execution/contracts.py:14` still `MAX_STEPS = 256` on PR #53. PoC must name its provider explicitly. |
| 10.2.3 capacity/CPU/MB numbers are hypotheses | AGREE | They were labelled estimates; now also listed as inputs to measure (B19, 11.4). |
| 10.2.4 B13 3–8 B/tick and 7–20 GB are projections | AGREE, and I narrow B13 | The only real compact-serving measurement I found is XAU 2024 January slice **84.25 B/tick** with the existing exporter (`docs/XAU_2024_SERVING_EFFICIENCY_CHECKPOINT_1_2026_10_30.md` on PR #53). My synthetic 2.2–2.9 B/tick is not evidence for real XAU. B13 is re-scoped to a **delivery derivative** next to canonical Monthly Parquet, not a replacement. The "50×" figure is withdrawn until one real EURUSD and one real XAUUSD month are measured. |
| 10.3 prefetched bytes are inspectable; signed URLs do not restore strict no-lookahead | AGREE | Part A option B wording "near-causal" was too soft. Corrected in 11.2 Q3. |
| 10.3 trust tiers (UNVERIFIED practice vs VERIFIED results) | AGREE | Recommend the labels exactly as written. |
| 10.3 rights can veto client tick distribution | AGREE | See 11.2 Q2. This is a P0 gate for any client-delivery option. |
| 10.4 notary is O(history) per verified Session | AGREE | See 11.2 Q4 and Option D. |
| 10.4 self-reported logs never become authoritative receipts | AGREE | Only server-computed results from server-owned data get `VERIFIED`. |
| 10.5 Gates A–E | AGREE with additions | Add Gate D′ (Option D measurement) and explicit reject thresholds, 11.2 Q8. |

### 11.2 Answers to 10.6

**Q1 — Browser-only or desktop helper? → Browser-first; desktop helper NOT for V1.**
- Browser Worker: zero install, works on Android/iOS, one update channel, same
  security model as the web app.
- Desktop helper (e.g. Tauri/Rust or Python sidecar): more RAM/disk, but adds
  installers per OS, code signing, auto-update, local port/IPC security,
  antivirus false positives and support load; excludes phones; and it does **not**
  solve rights or no-lookahead (local disk is even easier to inspect).
- Re-open only if Gate B shows a 262,144-tick replay cannot run within budget on an
  8 GB laptop in a Worker. NEEDS DATA (Gate B).

**Q2 — Rights evidence for serving ticks to paying clients → NEEDS DATA; P0 blocker.**
- Required per provider (HistData, Exness, Dukascopy, any vendor), in writing:
  (a) commercial use; (b) redistribution/transmission of raw *and* derived ticks to
  end users; (c) client-side caching/offline retention and duration; (d) display of
  derived candles; (e) territory; (f) attribution; (g) termination/revocation terms.
  Store the signed terms/version and map each to the six rights categories in 10.3.
- Fallbacks if client delivery is not permitted:
  1. **Option D** (11.3): ticks stay on the server; client receives only what display
     rights allow (e.g. derived candles), settlement runs server-side per order event.
  2. Licensed vendor with explicit redistribution rights (cost to be quoted).
  3. Bring-your-own-data: user imports their own files locally (practice tier only,
     `UNVERIFIED`); no RIKSORA redistribution.
  4. Synthetic data for demos and tests.

**Q3 — Strict no-lookahead without release requests? → No. DISAGREE with my own
earlier option B framing.**
- Any byte sent is known to the client. The only defensible claim is:
  *"no market data later than revealed time T + W ever left the server"*, where W is
  the release window.
- Defensible W: one atomic timestamp-group batch up to a small time span (e.g. ≤ 1 s
  of market time, or ≤ N groups). Requests scale as `playback_speed / W`; at 100×
  speed and W = 1 s that is ~100 requests/s per user — too many. So strict mode
  should cap replay speed or batch at the step the user actually sees.
- The release request does **not** need a DB transaction per step: a stateless
  signed cursor (HMAC of session, T, W) plus an append-only release log written in
  batches is enough to prove what was released.
- Promises to drop: "client cannot see future data" in prefetch tiers; "tamper-proof
  WASM"; "local hash proves the result". Keep: "VERIFIED results are computed by the
  server from server-held data under a pinned policy".
- Option D (below) gives strict mode without streaming ticks at all.

**Q4 — Notary economics → AGREE it can become the bottleneck; formula + Option D.**
- Inputs: `C` = server CPU-seconds per verified Session; `K` = cores reserved for
  verification; `u` = target utilisation (≤ 0.7).
  `verified_per_hour = K × 3600 × u / C`.
- With the reported 399 CPU-s per 262,144-tick financial-active replay (fixture
  specific; I could not re-measure it here): `K = 4, u = 0.7` → **≈ 25 verified
  262k-tick Sessions per hour**. That is too low for full re-execution of every
  Session.
- Compared with server-per-step: the current model already spends at least the same
  reducer + provider work for **every** Session continuously, verified or not, plus
  queue/process/DB overhead per step. A notary only pays for Sessions that ask for
  `VERIFIED`. So notary ≤ current cost, but neither is cheap with C ≈ 400 s.
- What lowers C (NEEDS DATA: a profile split of the 399 s):
  1. **Separate dataset validation from Session execution.** Provider/evidence
     validation is a property of the dataset; validate once per dataset hash and
     cache the receipt. Session replay then trusts the pinned, already-validated
     chunks.
  2. **Event-driven skipping (Option D, 11.3):** process ticks only while orders or
     positions are live; skip flat intervals via chunk min/max index.
  3. Verify on publication/Session completion only (10.4 case b), never on frequent
     checkpoints by default.
- Monthly cost comparison must be measured (Gate D): CPU-s/result, peak RSS,
  DB writes/WAL per result, egress per user, CDN/paid traffic, queue p95.

**Q5 — Keep Monthly Parquet canonical + add transport chunks? → AGREE.**
- Transport chunk manifest binds each chunk to: canonical dataset identity, Parquet
  file hash, row/group range, chunk content hash, exporter version. No acceptance or
  source hash is rewritten. Transport chunks are re-derivable and disposable.
- B13 storage changes to the canonical store are withdrawn from the priority list
  until the real-month measurement exists; the redundant *validation copy at rest*
  question (≈320 B/tick in the 2021-11 EURUSD store) remains worth a separate,
  owner-authorized review.

**Q6 — Parity portability → plain TS is risky; recommend TS + BigInt for the PoC,
decide Rust later. NEEDS DATA (op inventory).**
- Risky semantics: `Fraction`/`Decimal` exactness (JS has no native decimal — must
  use BigInt rationals/fixed-point, never `Number`); Decimal rounding modes and
  quantization; canonical JSON number/string encoding; key ordering; Unicode; hash
  chain inputs; atomic timestamp groups; ambiguous-chronology flags; integer
  nanosecond timestamps beyond 2^53 (BigInt required).
- Rust core + PyO3 + wasm-bindgen gives one implementation, but then Python and
  browser share bugs — the verifier is no longer independent. Keep the current Python
  engine as an **independent oracle** in CI regardless. Costs of Rust/WASM: new
  toolchain in CI, ~200–500 KB WASM, FFI surface, slower iteration.
- Smallest PoC: TS + BigInt reducer covering the subset in Gate A, checked against
  the existing golden vectors and `verify_contract_vectors.mjs`.

**Q7 — Currency of the audit (PR #53 head `92827bc` vs `main` `4fc9939`):**

| Finding | `main` | PR #53 | Status |
|---|---|---|---|
| B8 CI | none | 3 workflows (`exness-monthly-parquet`, `product-v1-backend` with `postgres:16`, `product-v1-browser`) | **Partly fixed**: backend workflow runs named test subsets, not the full suite; ask for full-suite + zero-skip job |
| Queue workers | `WORKERS = 2` hard-coded | `BTL_RESEARCH_WORKERS` 1–4, default 2 (`cloud/worker_config.py`) | **Partly fixed**: still max 4; `GLOBAL_LIMIT = 16`, `USER_LIMIT = 2` unchanged |
| B5 rate limiter | 30/min per IP on all `/api/v1/` | separate `api_rate_limit=600`/min per IP + auth limit | **Mitigated**: still one DB connection + UPSERT + DELETE per request, still keyed by IP (CGNAT) |
| B6 connection pool | none | none (`infrastructure/database.py` still `psycopg.connect` per call, `Budget(12)`) | **Open** |
| Polling | 500 ms | 500 ms (`AlphaWorkspace.jsx`) | **Open** |
| B1 market JSON in `public/` | 964 files, ~279 MB | 965 files, ~270 MB | **Open** |
| `MAX_STEPS` | 256 | 256 | **Open** for long Monthly Parquet sessions |
| Storage serving size | — | XAU slice 84.25 B/tick measured | New evidence, used above |

Genuine P0 blockers, in my view: data rights (Q2); a full-suite zero-skip CI gate;
long-session limit (`MAX_STEPS`) vs product targets; per-request DB writes in the rate
limiter. Others are optimizations.

**Q8 — Smallest reversible 1–2 week experiment → yes, synthetic data only.**
- Week 1:
  1. Gate A subset: TS + BigInt reducer for market, pending, SL/TP, partial close,
     cancel/retry, gaps, equal-time groups; byte-identical canonical JSON and SHA-256
     vs Python on all existing golden vectors + 3 synthetic sessions
     (2,048 / 65,536 / 262,144 ticks).
  2. Gate B on the same sessions in a Web Worker: 8 GB Windows laptop, 4 GB laptop
     profile, real mid-range Android; 1×/10×/100×.
- Week 2:
  3. Profile the 399 CPU-s case: split dataset validation vs reducer vs I/O.
  4. **Gate D′ (Option D):** Python prototype of per-chunk min/max index +
     event-driven settlement; measure CPU-s per order and per verified Session,
     parity with full replay on the same sessions.
- Proposed reject thresholds (owner to confirm):
  - Any unexplained parity mismatch in Gate A → stop local execution track.
  - Gate B: 262k-tick session peak heap > 500 MB on the 4 GB profile, or long tasks
    > 200 ms at 10×, or fps < 20 on Android → browser track not viable for that tier.
  - Gate D: verified Session cost not reducible below ~30 CPU-s (≈ 340/hour on 4
    cores at 70%) → notary only for publication, not routine.
  - Rights: no written redistribution permission → client-delivery tiers rejected;
    proceed with Option D.
- Everything behind a feature flag; current hosted path untouched.

### 11.3 Option D — server-side event-driven settlement (new)

- Observation: in manual replay, most ticks change nothing financially. They matter
  only while an order is pending or a position is open, and then only at the first
  tick that touches a trigger price (entry, SL, TP, liquidation).
- Precompute for each canonical chunk (e.g. 1 minute or N groups): min/max Bid,
  min/max Ask, first/last timestamp, group count, chunk hash. Size is negligible.
- On each order/position change, the server finds the **first touching tick after
  the current revealed time** by scanning the index (skip any chunk whose range does
  not include the trigger), then reads only the candidate chunk(s) exactly, tick by
  tick, with atomic groups and existing ambiguity rules.
- The settlement result is *scheduled* at that market time but **released to the
  client only when the replay cursor reaches it** (no future leak; the client only
  learns "nothing happened yet" until then — the release can be bundled with the
  normal cursor/candle update).
- Cost scales with orders × log(chunks) + touched chunks, not with steps or ticks.
  Ticks never leave the server, so it is compatible with strict no-lookahead and
  with restrictive data rights; the client receives display candles (if rights
  allow) or server-rendered summaries.
- Risks / NEEDS DATA: exact semantics must match the frozen contract (gaps,
  ambiguous ordering, spread changes, partial fills, time-based exits, swaps); equal
  results to full replay must be proven on golden vectors; trailing stops and
  time-dependent rules need the indexed scan to be monotone; still one server call
  per order event.
- Contract: changes execution scheduling, not financial semantics — owner grant and
  parity proof required.

### 11.4 Revised joint priority order

**(i) Reversible optimizations (no contract change):**
1. Full backend suite with PostgreSQL, zero skips, as a required CI check.
2. Rate limiter: in-memory/Redis token bucket keyed by user for authenticated
   routes; no DB write per request; connection pools (sync + async).
3. Profile the 399 CPU-s case; cache dataset validation receipts by dataset hash.
4. Remove market JSON from `dist/` and git (keep as separately deployed assets);
   lazy routes; logo size.
5. SSE instead of 500 ms polling; `LISTEN/NOTIFY` for the queue.
6. Measurement plan B19 / Gates B and D on synthetic data.

**(ii) Source/licensing blockers:**
7. Written rights matrix per provider (Q2) before any client tick delivery or
   public historical launch.
8. Real EURUSD + XAUUSD month measurement for any compact transport derivative.

**(iii) Owner-authorized contract changes (each needs explicit grant):**
9. Option D event-driven settlement (scheduling change, parity-gated).
10. TS/BigInt twin for UNVERIFIED practice tier (Gate A first).
11. Trust tiers and labels (`UNVERIFIED` vs `VERIFIED`) in product contracts.
12. Client tick delivery (only if rights allow), with release window W defined.
13. `MAX_STEPS` / long-session limits vs product targets.
14. Any change to canonical storage representation (B13 at-rest copy review).

### 11.5 Honest unknowns

- I could not run PR #53 tests, the 399 CPU-s case, or any device/load measurement in
  this session; all Option D and Gate thresholds are proposals.
- Rights status of every provider is UNKNOWN to me.
- The XAU 84.25 B/tick figure is one January slice with the existing exporter, not an
  annual measurement.
