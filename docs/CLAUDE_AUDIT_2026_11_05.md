# External audit for Codex: architecture, technology cost and reusable open source (2026-11-05)

> **Status:** advisory input requested by the owner, written by Claude after reading `main` @ `8ba3489`.
> This file is **not** a new architecture authority and authorizes nothing by itself. For every item the owner accepts, Codex records the decision in the existing owners (`V2_ALPHA_DECISION_REGISTER.md`, `PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md`, `AI_CONTEXT/04_CURRENT_PHASE.md`) and then implements it as a normal checkpoint.
> Numbers marked **measured** come from this repo's own evidence. Numbers marked **estimate** are back-of-envelope figures to be confirmed by the benchmark, not acceptance results.

## 0. Summary for Codex

The correctness design (tick-native execution, no look-ahead, explicit UNRESOLVED, exact Decimal ledger, PostgreSQL CAS) is sound and should be kept. The weak points are **cost and throughput of the tick data path**, **process overhead**, and **launch blockers that are not engineering at all** (data rights, payments, deployment). With a December 2026 launch target there are about four weeks left, so the order of work matters more than any single design choice.

Top five actions, in order:

1. **Replace the per-event canonical-JSON + SHA-256 tick store with immutable Parquet** (exact fixed-point integers), and hash per file/row group instead of per event. (§2.1)
2. **Implement Jump-to-Next-Event as a vectorized trigger search**, then run the existing exact reducer only on the triggering timestamp group. (§2.2)
3. **Get the market-data license decision from the owner this week**; without it nothing can be sold in December regardless of code. (§4.1)
4. **Add CI, a single deployable backend app and a deploy recipe**; none exist on `main`. (§3.3–3.5)
5. **Shrink the agent context**: the two main authority/mailbox files total ~880 KB, which no agent can read in full in one session. (§3.1)

## 1. What should be kept as is

- React 19 + Vite + TradingView Lightweight Charts 5 (Apache-2.0): the cheapest and fastest-loading chart option. Keep the TradingView attribution.
- Python backend with an exact Decimal financial reducer in `backend/execution/engine.py` (~277 lines). It is small and auditable; do not replace it with an external engine.
- PostgreSQL as the system of record for Methods, Sessions, commands, events and checkpoints.
- One VPS (6 vCPU / 16 GB / 200 GB) for launch. Once the data path in §2 is fixed, this is enough for the first paying users. Do not buy a second VPS or 2 TB of storage.
- The invariants in `AGENTS.md` (no OHLC settlement, atomic timestamp groups, causal RevealedView).

## 2. Technology: what is inefficient, and the fix

### 2.1 Tick storage is ~5.4× larger than the raw CSV and cannot hold the 16×5 catalog

**Measured** (`SINGLE_VPS_STORAGE_BENCHMARK_GATE.md` §1, Exness XAUUSDm 2015-08-10 → 2015-12-31):

| Quantity | Value |
| --- | --- |
| Source quotes | 8,698,581 |
| Raw CSV | 554,761,330 B → **~64 B/quote** |
| Canonical SQLite/zlib V2 store | 3,004,055,552 B → **~345 B/quote** |

Cause, visible in `backend/ticks/storage_v2.py`: every event is serialized as sorted-key JSON, hashed with SHA-256 (`:181`, `:388`), stored in an `identities` table row (`:212`), and packed into zlib(level 1) JSON chunk objects (`:70-74`). In practice per-event identity costs more than the price data itself.

**Estimate for the approved target** (16 instruments × 5 years). The XAU sample gives ~22 M quotes/year (8.7 M over ~143 days). Using it as a proxy, 16 × 5 × 22 M ≈ **1.8 B quotes**:

| Layout | B/quote | 16×5 total | Fits 200 GB SSD under the 80% gate? |
| --- | --- | --- | --- |
| Current V2 (SQLite/zlib JSON) | ~345 (measured) | **~600 GB** | **No** |
| Raw CSV | ~64 (measured) | ~115 GB | Barely, with no room for anything else |
| Parquet ZSTD, int64 `ts_ns` + int32/int64 fixed-point bid/ask + ordinal | ~5–15 (estimate) | **~10–30 GB** | Yes, with a large margin |

**Recommendation (decide now; benchmark only to tune):**

- Physical format: one Parquet file per `instrument / year / month`, ZSTD level 3, row groups of about 128K rows, sorted by `(ts_ns, source_ordinal)`. Columns: `ts_ns:int64`, `bid:int64`, `ask:int64` (price × 10^scale, scale stored in the manifest), `source_ordinal:int64`, `flags:uint16` (quality/diagnostic bits), and `bid_size`/`ask_size` only where the source has them.
- Integrity: SHA-256 **per file**, plus row-group min/max `ts_ns` in an immutable dataset manifest (`datasetId`, `datasetVersion`, provider, rights class, hashes, coverage). Event identity is `(datasetVersion, file, row)`, derived rather than stored. This keeps provenance and tamper detection without a per-event hash table.
- Keep existing `DiskTickProvider`/`IndexedTickDataProvider` as the interface. Write one `ParquetTickProvider` adapter and prove equivalence against V2 with the existing golden vectors on the 2015 dataset (same canonical event/ledger hashes). This is the only benchmark needed before switching.
- Read path: PyArrow `ParquetFile.iter_batches` with row-group skipping by `ts_ns`. DuckDB/Polars are optional for analytics; they read the same files, so no second copy exists.
- Retire V2 SQLite for new datasets after parity. Keep the 2015 V2 store only as a rollback reference until the owner approves deletion.
- Session state stays in PostgreSQL. Do **not** persist a per-Session position log (`timeline_v2.py` `position_lookup` / advance log). The cursor is `(datasetVersion, ts_ns, ordinal)` and can be re-sought in O(log n) using the row-group index, so long-history cold resume no longer means replaying from Session start.

### 2.2 Replay throughput makes the approved one-click 72h Jump unusable

**Measured:** one-day bounded replay took 87,859 events / 155.4 s ≈ **565 events/s** with `execution=false`.

**Estimate from that rate:** a 72h Jump covers roughly three trading days (~260K events), so **about 7–8 minutes per click**. A full year of one instrument is ~22 M events, or **about 11 hours**. That is not a viable product UX.

Fix, which stays exactly equivalent to chronological replay given the owner's own rules (no OCO, no pending expiry, so account state can only change on a price trigger):

1. Load the window `[cursor, cursor + 72h]` as Arrow/NumPy int64 arrays (milliseconds for a few hundred thousand rows).
2. For each pending order or active SL/TP, compute its first crossing index vectorized (`bid <= x` / `ask >= y` on the correct side) and take the minimum over all orders.
3. If there is no trigger, move the cursor to the window end (or EOF / source boundary) and commit one checkpoint.
4. If there is a trigger, feed only that **atomic timestamp group** to the existing exact Decimal reducer, commit, recompute the trigger set (it changes after a fill), and repeat from that point.
5. Unresolved/ambiguous evidence rules apply unchanged inside step 4. Ties within a timestamp group still go through the reducer, never through the vectorized scan.

Golden test: for N random windows, the Jump result (events, ledger hash, cursor) must equal plain tick-by-tick replay. The same technique gives fast "play at 20×" since the chart only needs revealed bars and not per-tick Python objects.

Hot path rule: no `json.dumps`, `Decimal()` construction, SHA-256 or SQL `INSERT` per tick. Use integers until a trigger hits, then convert to Decimal only for the ledger.

### 2.3 Redundant pre-aggregated candles in the public Git repo

`frontend/public/market/decade/` holds 964 JSON files (~271 MB on disk) of the same M1 data pre-aggregated into 11 timeframes, all committed to Git. This:

- bloats every clone and the deploy;
- duplicates data that can be derived from M1 (or from ticks) on demand and cached once per `datasetVersion/timeframe`;
- **redistributes HistData-derived prices from a public GitHub repo**, while the repo's own provider research (`PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` §42.5) states HistData redistribution rights are not established. See §4.2.

Fix: move candles behind the backend (derived from the canonical dataset, gzip/brotli JSON or Arrow IPC over HTTP), remove the folder from the tracked tree, and make the repository private or purge it from history (owner decision, since rewriting history is destructive).

### 2.4 Per-command full checkpoint snapshots

`backend/execution/postgres.py` inserts a full `tick_checkpoints` row on every command. This is fine at launch scale. Later, keep the last K snapshots plus every Nth one, because the event log is the source of truth and is never pruned. Low priority.

## 3. Architecture and process

### 3.1 Documentation volume is larger than the code and blocks AI agents

| Item | Size |
| --- | --- |
| `docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` | 474 KB (229 headings) |
| `docs/AI_HANDOFF.md` | 407 KB |
| All `docs/*.md` + `AI_CONTEXT/*` | ~19,300 lines |
| Backend production Python | ~9,600 lines |
| Frontend `src` (code) | ~7,000 lines |

Together the two big files are roughly 200K+ tokens. No Codex/ChatGPT/Claude session can hold them alongside code, so agents read fragments of their "source of truth", re-verify old gates, and produce more documentation. That costs subscription/API tokens and calendar time on every task.

Recommendation:

- Freeze `PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` as historical (`docs/archive/`). Replace it with **one current architecture file ≤ 15 KB** describing what runs today, plus `docs/adr/NNN-title.md` (one page per decision: context, decision, consequences).
- Rotate `AI_HANDOFF.md`: keep only the latest open request and the latest report (≤ 10 KB), and move the rest to `docs/archive/handoff-YYYY-MM.md`.
- Replace repeated "this does not authorize / not certified / remains separate" boilerplate with one sentence in `AGENTS.md`. Every paragraph currently restates it.
- Add a short `CLAUDE.md` containing `@AGENTS.md` so Claude Code loads the same rules automatically.
- Target: an agent can load all *current* authority in under ~30K tokens.

### 3.2 Gate-heavy process for decisions that arithmetic already settles

`SINGLE_VPS_STORAGE_BENCHMARK_GATE.md` C0–C7 is a multi-week research program (codec × row-group × partition sweeps, ABBA runs, cold-partition proxies) whose answer is already clear from the numbers in §2.1. Decide, build the one adapter, prove parity with goldens, measure the result, then tune. Correctness gates (golden hashes, no look-ahead) stay strict. Exploratory sweeps become optional.

### 3.3 No CI on `main`

There is no `.github/workflows`. GitHub Actions is free for public repos and cheap for private ones. Add one workflow on every PR: `python -m unittest discover -s backend/tests`, a PostgreSQL service container for the DB tests, and `npm ci && npm run lint && npm run build && npm run test:regression` in `frontend/`. This replaces most manual "record gate evidence" documents.

### 3.4 Thirty-four remote branches with unmerged work

Branches like `codex/cp6a10-postannual-handoff`, `codex/compact-writer-20261026` and `claude/*` hold work that the docs explicitly call "not merged". Use trunk-based flow: short-lived branches, PR + CI, merge or delete within days. List each branch with a one-line merge/delete decision for the owner.

### 3.5 Five HTTP entry points and no deploy recipe

`backend/api/main.py`, `backend/cloud/app.py`, `backend/cloud/serve.py`, `backend/market_data/serve.py` and `backend/execution/local_api.py` each start their own server. For launch: **one FastAPI app** with routers (auth, workspace, sessions/replay, market data) over the existing modules, which matches the modular monolith already chosen. Add a deploy recipe to the repo: Caddy (automatic HTTPS) → uvicorn under systemd (or one `docker compose` file), PostgreSQL local, plus a `.env.example`. Delete the legacy `backend/api` + `backend/engine` candle prototype once nothing imports it.

### 3.6 Too many frontend modes for a product

`/`, `/?legacy=local`, `/?tick-alpha=local`, `/?trading-ux=prototype`, FigmaWorkspace and the root `legacy/` snapshots all remain. For launch, ship one route tree and delete the rest (Git history preserves them). Rename `test:phaseN` scripts to feature names (`test:drawings`, `test:replay` ...) so the suite describes behavior, not project history.

### 3.7 Security and hygiene

- The public repo contains the VPS public IP, hostname/paths and DNS layout (`docs/AI_HANDOFF.md` ~line 727). These are not credentials, but make the repo private or scrub them before launch.
- `fastapi-users` is officially in **maintenance mode** (security fixes only). Keeping it for launch is acceptable since it already works. Do not build new auth features on it. Revisit after launch.
- Add off-site backups: nightly `pg_dump`/pgBackRest plus a dataset-manifest copy to an S3-compatible bucket. Cloudflare R2 has no egress fees; Backblaze B2 is also cheap. Market Parquet files only need re-uploading when a new `datasetVersion` is published.

## 4. Launch blockers that are not code

### 4.1 Market-data rights for 16 instruments (biggest risk)

The repo's provider research already shows that HistData, Dukascopy and TrueFX terms are personal/internal only, and that SaaS display/redistribution needs a separate agreement. December revenue therefore depends on one of these:

1. **Commercial license** from a tick vendor covering 16 symbols × 5 years with display rights to end users (Dukascopy business agreement, Tick Data LLC, or an LSEG/Refinitiv reseller). Ask for the quote this week.
2. **Broker partnership** (e.g. the Exness source already used, or Darwinex) granting historical data use in exchange for referral/IB placement.
3. **Bring-your-own-data at launch:** the user imports their own CSV (the importer exists). RIKSORA ships no prices, so rights stay with the user. This is the fastest legal path to a December launch and can coexist with options 1 and 2 later.

Codex cannot resolve this. Surface it to the owner as a blocking decision, and build the BYOD import path in the Parquet format from §2.1 so all three options share one pipeline.

### 4.2 Data already published

Decide with the owner whether the HistData-derived `frontend/public/market/decade/` data must be removed from the public repo (and history). See §2.3.

### 4.3 Payments and entitlements are not designed

There is no payment, plan or entitlement model on `main`. Minimal design: `plans`, `subscriptions` and `entitlements(instrument set, date range)` tables in PostgreSQL, and a webhook endpoint. For an Indonesian business use Xendit or Midtrans. For global card sales without handling VAT yourself, use a merchant of record (Paddle or Lemon Squeezy).

## 5. Open-source projects: what to reuse and how

Checked on 2026-11-05 via the GitHub API (stars / license / last push).

| Project | License | Activity | Use for RIKSORA | Verdict |
| --- | --- | --- | --- | --- |
| [apache/arrow](https://github.com/apache/arrow) (PyArrow) + Parquet | Apache-2.0 | active | Tick storage format and reader (§2.1) | **ADOPT now** |
| [pola-rs/polars](https://github.com/pola-rs/polars) | MIT, 40K★ | active | Vectorized trigger search, candle aggregation, statistics | **ADOPT** (or NumPy only) |
| [duckdb/duckdb](https://github.com/duckdb/duckdb) | MIT, 43K★ | active | Ad-hoc analytics/QA over the same Parquet files; no extra copy | ADOPT for tooling only |
| [nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | LGPL-3.0, 31K★ | active (pushed 2026-11-04) | Copy the *design* of its `ParquetDataCatalog` QuoteTick schema (fixed-point int prices, `ts_event`/`ts_init`) and streaming chunked backtests. Using it as an unmodified server-side library dependency is LGPL-compatible for SaaS. | REFERENCE; do not replace own reducer |
| [nkaz001/hftbacktest](https://github.com/nkaz001/hftbacktest) | MIT, 5K★ | slower (pushed 2025-12) | Reference for fast tick loops over structured NumPy arrays | REFERENCE |
| [Leo4815162342/dukascopy-node](https://github.com/Leo4815162342/dukascopy-node) | MIT, ~950★ | active | Download all 16 instruments for **development/QA only** until a license exists | ADOPT as dev tool |
| [tradingview/lightweight-charts](https://github.com/tradingview/lightweight-charts) | Apache-2.0, 18K★ | active | Already used | KEEP |
| [difurious/lightweight-charts-line-tools](https://github.com/difurious/lightweight-charts-line-tools) | Apache-2.0, small | 2025-12 | Reference for more drawing tools (channels, pitchfork) if the catalog grows | REFERENCE, low priority |
| [klinecharts/KLineChart](https://github.com/klinecharts/KLineChart) | Apache-2.0, 4.3K★ | active | Built-in drawings/indicators alternative | Do not switch now (switching cost > benefit) |
| [TA-Lib/ta-lib-python](https://github.com/TA-Lib/ta-lib-python) | BSD-2, 12K★ | active | Server-side indicators for statistics/AI features | OPTIONAL |
| [better-auth/better-auth](https://github.com/better-auth/better-auth) | MIT, 31K★ | active | Only if auth ever moves to a Node layer | Not now |
| [kernc/backtesting.py](https://github.com/kernc/backtesting.py) | **AGPL-3.0** | active | — | **AVOID** (AGPL obligations for a SaaS) |
| [polakowo/vectorbt](https://github.com/polakowo/vectorbt) | Apache-2.0 + Commons Clause | active | — | **AVOID** for commercial use |
| pocketbase/pocketbase | MIT | **archived** | — | AVOID |

Not recommended: QuestDB, TimescaleDB or ClickHouse for historical ticks. The data is immutable and read by time range, so Parquet files on local SSD are cheaper and simpler to operate than another database server.

## 6. Suggested four-week order to December

| Week | Work |
| --- | --- |
| 1 | Owner decides on data rights (§4.1) and public repo (§2.3/§3.7). CI (§3.3). `ParquetTickProvider` + converter + parity goldens on 2015 XAU (§2.1). |
| 2 | Vectorized Jump + golden equivalence (§2.2). Single FastAPI app + Caddy/systemd deploy + off-site backup (§3.5, §3.7). Ingest dev data for the 16 symbols (dukascopy-node, dev-only). |
| 3 | Payments/entitlements (§4.3). BYOD import into Parquet. Remove legacy modes (§3.6). Documentation diet (§3.1). |
| 4 | Load test one VPS with realistic Sessions, fix the measured bottleneck, release candidate, launch checklist. |

## 7. Instruction for Codex

1. Read this file, `AGENTS.md` and `AI_CONTEXT/04_CURRENT_PHASE.md`.
2. Report back to the owner, in the handoff mailbox, a one-line **ACCEPT / REJECT / NEEDS-OWNER** verdict for each of §2.1, §2.2, §2.3, §3.1–3.7 and §4.1–4.3, with the reason if you disagree. Cite code or measurements, not process.
3. Do not start implementation until the owner confirms the verdict list. Then record accepted items as ADRs/decision-register entries and execute in the §6 order.
