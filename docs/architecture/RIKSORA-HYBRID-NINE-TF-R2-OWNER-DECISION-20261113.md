# RIKSORA — Owner architecture decision: VPS tick execution + nine precomputed OHLC timeframes in private Cloudflare R2

Date: 2026-11-13
Status: **OWNER-SELECTED TARGET ARCHITECTURE; NOT IMPLEMENTED / NOT COMMERCIALLY ACCEPTED**
Source of current technical evidence: PR #53 and owner-provided unpublished local Codex checkpoint (local commits `7b79f52d...`, `0f5b01e0...`; 42 local commits ahead of remote `58b3cb9e...`). This document does not claim to inspect or publish those local commits.

## 0. Precedence and scope

This latest owner decision **supersedes** earlier proposals for:
- mandatory client-side/local-first financial execution and shipping full yearly tick data to browsers;
- deriving M3/M5/.../D1 from M1 **in the browser on each timeframe switch**;
- leaving D1 outside the 5,000-candle **active chart cache** limit;
- keeping the active OHLC archive on the VPS instead of Cloudflare R2.

It does **not** change financial authority, tick contract, Session/recovery semantics, source rights, production, data acquisition, or paid-beta acceptance. Earlier Commercial V1 acceptance targets remain in effect except where this decision explicitly changes chart architecture/UI caching. Preserve the complete **unpublished Git commit history** and do not force-push, reset, or overwrite local Codex work.

## 1. Two data classes, one financial engine

| Role | Store and execution location | Actual behavior |
| --- | --- | --- |
| Canonical ordered Bid/Ask Tick Monthly Parquet, immutable manifest, Observed V2 metadata sidecar index | **Local SSD of RIKSORA VPS** | **Only** financial execution evidence; no second canonical tick copy; immutable source identity and coverage |
| Precomputed, independently accessible OHLC for **M1, M3, M5, M15, M30, H1, H2, H4, D1** | **Private Cloudflare R2**, with per-instrument/month/timeframe/version manifests | Chart history and indicator input; generated **offline only once per validated source version** and incrementally republished when source changes |
| Trader browser | HTTP chart pages and UI | Request **the already-generated timeframe selected**, display candles, indicator analysis, drawings and order controls; **no M1→D1 aggregation on timeframe change**; no full-year tick download during normal backtest |
| Python tick-precise canonical reducer + durable PostgreSQL queue/worker | VPS | Advance real replay cursor, pending orders, fills, SL/TP, fees, canonical receipts, active-candle update; server-authoritative V1 |
| Session, Method, order events, receipts, Journal, Analytics | PostgreSQL VPS | Durable, tenant-isolated, idempotent records |

Do not substitute a faster OHLC-only fill simulator for tick authority. Do not automatically keep a dedicated CPU worker running while someone reads static OHLC or draws on a paused chart. Idle Session does not require ongoing tick computations.

## 2. Precompute all nine timeframes, not browser aggregation

Implement an offline source- and version-pinned processing path:

`Verified canonical tick (SSD VPS) → qualified M1 chart bars → offline nine-timeframe materialization → immutable manifest/hash → private Cloudflare R2 → authenticated bounded chart delivery`

Source periods are separate:
- **2021-01 through 2022-12**: 24 months × 16 instruments = **384 instrument-months** of qualified **OHLC-only prehistory**, used for chart and indicator warm-up only. It is not execution tick evidence; it requires its own source/version/rights/price basis.
- **2023-01 through 2025-10**: 34 months × 16 instruments = **544 instrument-months** of qualified canonical ordered Bid/Ask **tick** for trading. Generate independent nine-timeframe chart derivatives from the tick feed.
These are **coverage targets**, not existing complete inventories or commercial rights.

For each selected instrument/month/timeframe, publish immutable, compressed chart artifacts with source provider/feed identity, source pin/hash, aggregation code version, price basis, trading-calendar/UTC bucket rules, gap/partial flags, actual first/last bar times and counts, artifact hash, and qualification/rights state. Cross-month higher-timeframe boundaries must be exact. Do not infer traded volume from quote counts or fabricate closed-market candles. An archive may contain more than 5,000 candles per timeframe.

The latest unpublished local Codex report says the **BID M1** streaming ZSTD Parquet sidecar generator passes directed synthetic tests, with partial chart integration and a base 256-event tick transport. **Reuse** it; do not rewrite the successful validator/streaming/manifest machinery. But PR #53's existing chart `backend/execution/workspace.py::display_candles` and `backend/execution/historical.py::chart_history` use **MID = (Bid+Ask)/2** for display, while BID is settlement-side quote data. A BID-derived M1 sidecar cannot silently replace a MID-labeled chart. Implement a deliberate **versioned display-price-basis compatibility strategy** (default: match the current MID chart by generating MID-derived display OHLC directly from both Bid and Ask), with fixtures proving boundary continuity; preserve the BID M1 sidecar where useful, without pretending BID and MID are equal. The nine published display timeframe products should share one explicitly selected basis within a Session. Existing pre-2023 OHLC-only providers may have independent basis; pin and disclose discontinuities instead of falsely splicing.

## 3. Exactly 5,000 candles PER SELECTED timeframe

The owner means **5,000 historical OHLC candles for the active chart-window of each selected timeframe, including D1**, not 5,000 raw ticks, 5,000 bars for the entire data archive, or 5,000 bars accumulated across all nine timeframes.

- Eligible V1 chart choices: `M1/M3/M5/M15/M30/H1/H2/H4/D1` (nine), no W1/MN1.
- M1: up to **5,000 M1** bars resident when M1 selected.
- M5: up to **5,000 M5** bars resident when M5 selected.
- H1: up to **5,000 H1** bars resident when H1 selected.
- D1: up to **5,000 D1** bars resident when D1 selected; older D1 history remains available through bounded paging if total exceeds 5,000.
- On first visit, fetch **up to 512 already-precomputed eligible completed bars** of the selected timeframe, not all 5,000.
- On scroll/seek, fetch **500–1,000 already-precomputed bars/page** and use rolling cache eviction at 5,000 for the active timeframe. The underlying archive never truncates; no browser M1 aggregation and no default caching of 9 × 5,000 simultaneously.
- Distinguish total catalog bars for a date range, 5,000-bar in-memory cap, 512-bar initial request, and viewport-rendered bars. Each timeframe has its own actual count based on source-observed sessions/gaps.
- Indicator warm-up uses a separately bounded causal cache (initial guideline up to 1,000 bars of input timeframe), not made-up history.

## 4. Causal chart rendering with precomputed future OHLC

Even though all future OHLC candles exist on private R2, a backtest at server-controlled cursor `T` may receive only **fully completed candle buckets whose close <= T**, plus an **in-progress candle constructed solely from tick groups already revealed on the VPS**. Never send the future final high/low/close of the active M5/H1/D1 bar. Do not generate unscoped signed R2 URLs whose cached contents could expose unapproved future full-bar data. Prefer an authenticated, entitlement-checked, Session-cursor-clipped API/edge gateway which returns bounded pages, with source-version pinning, ETags/cache discipline and no R2 credentials exposed. Historical catalog inspection outside a Session is a distinct, permissioned scope from in-Session replay visibility.

**No-lookahead tests:** cursor in the middle of M1, M5, H1, and D1; first/last partial candle at source edge, week/weekend gaps, 2022–2023 boundary, cursor restart and timeframe switch; indicators must see only eligible bars. Security is server-side authorization/cursor enforcement, not just browser hiding.

## 5. Actual code status and changed priorities

**Already reported by local Codex (unpublished, synthetic-directed only):** streaming BID M1 Parquet sidecar; bounded V2 tick delivery primitive with per-page hash; time-bounded higher-TF frontend aggregation/display; 23/23 relevant backend tests plus frontend tests/lint/build; no authenticated chart API or product E2E. Treat these as **reported local results**, not independently audited remote HEAD PASS.

**Remote PR #53 status:** Monthly Parquet → observed financial execution, Python reducer, durable PostgreSQL queue, workspaces and chart helpers exist; its OHLC architecture subsection still records an unimplemented proposal. No nine-timeframe private-R2 production path is demonstrated by the remote SHA.

**Revised implementation order:**
1. **Git safety**: preserve 42 unpublished local commits; reconcile/push authentic ancestry safely, without force-push/squash/API snapshot. Do not cherry-pick this document onto a stale base without reviewing conflicts.
2. **Promote existing BID M1 implementation** as a reusable offline generator; establish explicit MID/BID display compatibility using exact-source fixtures. Generate **all nine** monthly OHLC materializations **offline**, not in browser. Test timezone/session/gaps/month-boundary/hash and idempotent publish.
3. **Cloudflare R2 private publishing**: use bucket credentials in trusted workers only; immutable path/version, manifest, integrity verification, bounded object access, retry/recovery and rights gates. No production upload of real market data without rights.
4. **Authenticated chart history**: dataset entitlement, Session cursor and price-basis pins, exact selected-timeframe paging, 512 initial bars, 500–1,000 older bars, 5,000 active chart cache including D1. Rewire `AlphaWorkspace` and retire old tick-scanning historical page hot path after compatibility QA. Keep all nine-frame storage outside the Vite `frontend/public` bundle; never remove public files before a verified consumer migration/backup and source-rights audit.
5. **Server-authoritative replay UX**: keep existing Python canonical reducer; send only durable cursor/receipt/financial events plus bounded active-candle updates built from revealed ticks. Optimize per-step queue/polling and timeline checkpoint recovery with explicit reviewed contract approval; retain fallback and golden financial hashes.
6. **Commercial and economics gates**: synthetic full product browser E2E (source→R2 fixture→chart→replay→Journal→resume), protected access/tenant isolation and no-lookahead, VPS CPU/latency/RAM/database growth plus R2 stored bytes/Class A/B operations, then qualified licensed historical feed acceptance. No blanket 20-user or one-year capacity claim without actual load tests.

**Deprioritized for now:** mandatory browser financial-engine TS/WASM port and downloading large tick histories to clients. Do **not** remove the local Codex tick-page transport primitive: preserve it for private QA, specialized later workflows or possible fallback, but **do not wire it as the normal backtest data plane** in this owner-selected hybrid.

## 6. Gate status and safety

- **Specification:** OWNER DECIDED; **implementation NOT DONE**.
- **Dataset:** 384 qualified OHLC-only instrument-months plus 544 qualified tick instrument-months: **NOT VERIFIED / RIGHTS BLOCKED**.
- **Private R2, all nine precomputed frames and browser paging:** **NOT IMPLEMENTED/ACCEPTED**.
- **Local BID M1 sidecar:** **reported implemented/tested locally**, not yet visible on the PR #53 remote final SHA.
- **Financial correctness:** current frozen Python reducer and hash evidence retained; new chart system cannot become financial authority.
- **Commercial release, billing, third-party market-data usage, deployment and storage migration:** **NOT AUTHORIZED** by this document.

This is an architecture decision and implementation specification only. It may be discussed in a draft PR; merging with active product/local branches requires ancestry/conflict review and owner safety gates.
