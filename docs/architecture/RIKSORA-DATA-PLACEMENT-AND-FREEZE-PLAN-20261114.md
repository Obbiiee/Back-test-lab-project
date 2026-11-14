# RIKSORA — Owner decision: market data on VPS SSD, R2 for user data only; gap audit and freeze plan

Date: 2026-11-14
Status: **OWNER DECISION (data placement) + REVIEW CANDIDATE (freeze plan). Not a competing authority:** this is a delta linked from the sole authoritative `PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md`. Frozen financial and no-look-ahead rules, AGENTS.md and the current owner authorization remain controlling.
Evidence base: `docs/benchmarks/CLAUDE_VPS_MEASUREMENTS_2026-11-14.md` (sections A-J), `docs/DUAL_ENGINE_FINAL_DECISION_20261114.md`, public-repository research summarized below. All load numbers are SYNTHETIC; real EURUSD ticks (rights UNKNOWN) were used only for private QA.

## 1. Decision (owner, 2026-11-14)
| Data | Where | Why |
|---|---|---|
| Canonical ordered Bid/Ask ticks (authoritative), derived compact tick (v2) | **VPS local SSD** | Financial evidence and fast reads; no third-party copy of licensed market data |
| OHLC, nine timeframes M1/M3/M5/M15/M30/H1/H2/H4/D1, including long history | **VPS local SSD** (immutable objects, manifest per instrument/source/basis/month) | Low latency, no per-request object-store cost, no market-data redistribution to a cloud |
| User data: Session archives/receipts export, Journal/Analytics exports, user uploads, encrypted database backups | **Cloudflare R2** | Durable off-box copy of data the VPS must not lose |
| Session, Method, orders, receipts, Journal, Analytics (hot) | PostgreSQL on the VPS | Unchanged |

This **supersedes** the 2026-11-13 decision that placed the nine OHLC timeframes in private R2 (`RIKSORA-HYBRID-NINE-TF-R2-OWNER-DECISION-20261113.md`). Everything else in that document (causal chart rules, 5,000-candle active window per timeframe, 512 first page, 500-1,000 older pages, tick authority, no browser aggregation) is unchanged. It also reverses the earlier "cold archival to R2 proposed" only in scope: R2 stays the target for **user** data archives.

Sizing on the 200 GB VPS (measured): compact v2 ticks about 2.6 B/tick (real EURUSD: 14.0 MB vs 77.0 MB for v1, 5.5x), 16 pairs x 34 months about 3.5-3.9 GB; OHLC about 1.1 MB per instrument-month, about 0.6 GB; 34 EURUSD months of v1 (817 MB) are already on the VPS and verified. Plenty of headroom; the disk gate (>= 30 GB free) stays.

Coverage reality (from the owner's laptop, replaces the stale 2021-2025 numbers of the 2026-11-13 record): ticks 2024-01 through 2026-10, 16 pairs (544 instrument-months); before 2024 only M1 BID OHLC exists (OHLC-only prehistory; importer not yet written; basis BID, display only). Rights for all real data: UNKNOWN (private QA only).

## 2. What other open-source projects show we lack
Method: generic public searches only (no project/owner details sent). These are search summaries, NOT verified against primary sources; each item needs a primary-source check before it becomes a contract.
| # | Observation from public projects | Our state | Gap / action | Priority |
|---|---|---|---|---|
| 1 | NautilusTrader keeps a Parquet **catalog** (canonical directories, query by instrument and ns range, ascending timestamps, instrument definitions stored separately) ([docs](https://nautilustrader.io/docs/latest/concepts/data/catalog/)) | One manifest per pair-month; the chart service pins one source hash per Session, so history across months/datasets is not found | Instrument definitions (precision, tick size, session calendar, price basis) as a first-class record; one catalog per instrument chaining months/datasets; query by instrument + range | P0 |
| 2 | Event-driven engines make look-ahead structurally impossible: strategies receive only data up to the cursor; one project reproduces another platform trade-for-trade as a comparator ([replay-lab](https://github.com/gregkitz/replay-lab), [GlowBack](https://www.mintlify.com/LatencyTDH/GlowBack/concepts/event-driven-simulation)) | Cursor-bound server and no-lookahead tests exist; our independent oracle covers OHLC only | An **independent financial reference** (golden vectors from a second implementation/external engine) for fills, SL/TP, fees, pending orders; the first real-data parity produced only 3 events (order UNRESOLVED), so activity-level parity is unproven | P1 (P0 before adopting the Claude jump engine) |
| 3 | Time-series databases build OHLC with first/max/min/last and chained materialized views (1s to 5s to 1m) ([QuestDB](https://questdb.com/docs/cookbook/sql/finance/ohlc/)) | Our own streaming engine, byte-deterministic, oracle-verified, 0.3 s per month | Not adopted: an extra database service costs RAM/CPU on a 6 vCPU host and would add a second authority for bars. Revisit only if live (non-batch) bars become a requirement | Considered, deferred |
| 4 | Charting library demo loads older bars on scroll via the visible-range subscription; known pitfalls: prepending needs a full `setData` and the viewport can jump ([lightweight-charts](https://tradingview.github.io/lightweight-charts/tutorials/demos/infinite-history), [issue discussion](https://www.github.com/tradingview/lightweight-charts/discussions/1341)) | Frontend still uses the frozen previous-month 512-bar context; no 5,000-candle paging | Implement prepend with preserved visible range, 500-1,000 page size, 5,000 cap with defined eviction side; tests for jumps | P1 (after contract approval) |
| 5 | Postgres queue guidance: SKIP LOCKED protects only the claim; use renewable leases and idempotent handlers; keep a **deliberate retention** (hot table plus archive), watch WAL and bloat ([overview](https://artur.bearblog.dev/background-jobs-without-redis-postgres-skip-locked-in-production/), [consequences](https://techcommunity.microsoft.com/blog/adforpostgresql/potential-consequences-of-using-postgres-as-a-job-queue/4514332)) | Leases, heartbeat and idempotent commands exist; retention is **count-based** (15 finished jobs globally), proven to delete results before their owner polls (`poll:404`); WAL growth not measured | Age-based retention (keep finished jobs longer than the longest poll plus TTL), archive outside the hot table, measure WAL; or frontend recovery | P0 (needs owner approval: frozen limit) |
| 6 | Delta plus bit-packing before zstd is the effective tick codec; reported ratios vary widely and vendor claims are unverified ([example](https://dev.to/parth_khare_84da5090de191/how-we-compressed-635-gb-of-financial-tick-data-to-55-gb-56dm)) | Compact v2 uses exactly this (5.5x on real EURUSD, lossless) | No action; keep claims to our own measurements | None |

Gaps from the VPS/repo audit that no public project was needed for: (a) **backups and restore drill** (database plus user data to R2) have never been exercised; (b) **observability** (queue depth, per-route p95/p99, PostgreSQL WAL, per-process CPU) exists only inside the QA harness; (c) **admission by resource** (CPU/queue depth) is absent; at 100 simultaneous traders the real frontend would show errors because it retries busy refusals only 8 times; (d) **data-rights evidence process** for any real data before commercial use; (e) firewall status and secrets handling on the VPS are unverified; (f) concurrent agent/owner sessions on the same VPS need a coordination rule (one measurement at a time).

## 3. Freeze plan
Principle: freeze only what is proven; everything else stays a gated review candidate. No runtime code or frozen contract is changed by this document.

### F0 — FREEZE NOW (decision and proven formats; documentation only)
1. Data placement of section 1 (market data on VPS SSD, R2 for user data only).
2. Derived compact tick `BTL-COMPACT-TICK-2` as a hash-pinned, lossless, non-authoritative accelerator (proof: 9 edge tests, tick-by-tick equality with v1 on 5.35 M real ticks, independent decode, tamper detection). The canonical Monthly Parquet stays the only execution authority.
3. OHLC object layout and rules `claude-ohlc-1`: MID per tick, exact integer scale, UTC bucket boundaries, immutable deterministic objects, oracle as the shared acceptance judge.
4. Chart causality rule: only completed buckets with end <= cursor T leave the trusted boundary; the forming bar uses revealed ticks only.
5. Worker pool: 4 workers (maximum), configured only through `BTL_RESEARCH_WORKERS` so queue loops, native slots and exchange threads match (a mismatched pool raised `Native worker slots unavailable` and left jobs RUNNING).

### F1 — FREEZE AFTER ITS GATE (needs owner approval and tests)
| Item | Gate to pass | Owner decision needed |
|---|---|---|
| Chart API: 512 first page, 500-1,000 older pages, 5,000 cap per timeframe incl. D1 | no-lookahead at cursors in M1/M5/H1/D1, tenant isolation with product identity, cross-month catalog, SSD object cache, paging tests, load test | change of `BTL-PAST-CHART-CONTEXT-1` |
| Cross-month instrument catalog and instrument definitions | verify against 34 months of EURUSD plus a second pair | none beyond this plan |
| Queue retention | age-based policy, no `poll:404` at 50+ traders, WAL measured | change of the retention limit (or accept frontend-only recovery) |
| Frontend busy retry and pruned-job recovery | real-browser cohort at 50 and 100 with default limits | none if recovery is idempotent by command id |
| OHLC-only prehistory importer (M1 BID) | basis label BID, seam rules, oracle on aggregation, rights note | format from the owner's laptop |

### F2 — NOT FROZEN (review candidates)
Claude jump engine for settlement (needs activity-level parity and the real-data UNRESOLVED diagnosis), event-driven settlement, sparse checkpoints, R2 user-data archive design, multi-process API, any time-series database, real R2 credentials and cost test.

### Acceptance checklist before declaring the V1 data architecture frozen
1. 34 months EURUSD plus at least one more pair verified and published as OHLC on the VPS; oracle equality on a sampled set of real months.
2. Full-month real replay Session through the product worker with measured RSS/CPU per worker (sets the RAM budget).
3. Chart path with product identity: 9 timeframes x >= 5,000 candles, p95 first page < 0.5 s measured on the SSD store, no-lookahead tests green.
4. Queue retention and frontend recovery: 100-trader burst with default client limits, zero user-visible errors, WAL measured.
5. Backup and restore drill executed once; observability dashboard (queue depth, p95/p99, WAL, CPU per role).
6. Rights evidence recorded per dataset before any commercial use.

## 4. Documents edited because of this decision (history preserved, tagged SUPERSEDED 2026-11-14)
`PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md` (banner), `architecture/RIKSORA-HYBRID-NINE-TF-R2-OWNER-DECISION-20261113.md` (R2-for-OHLC statements), `acceptance/RIKSORA-COMMERCIAL-V1-TARGETS.md` (override note), `DOCUMENT_MAP.md`, `acceptance/RIKSORA-V1-FREEZE-INTEGRATION-REGISTER-20261108.md` (new P0 items) and `AI_CONTEXT/04_CURRENT_PHASE.md` (dated checkpoint).
