# RIKSORA — Owner architecture decision: VPS tick execution + nine precomputed OHLC timeframes in private Cloudflare R2

Date: 2026-11-13
Status: **OWNER-SELECTED TARGET ARCHITECTURE; NOT IMPLEMENTED / NOT COMMERCIALLY ACCEPTED**
Source of current technical evidence: PR #53 and owner-provided unpublished local Codex checkpoint (local commits `7b79f52d...`, `0f5b01e0...`; 44 local commits ahead of remote (most recent locally reported HEAD e099e344; unverified against unpublished source) `58b3cb9e...`). This document does not claim to inspect or publish those local commits.

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

**Additional local checkpoint reported by Codex, not yet published:** incremental EMA with full fallback, incremental candle/volume series updates, bundle size report and CI guardrails; targeted tests/lint PASS. Initial JS 69,541 B gzip, total JS 304,804 B gzip, CSS 44,079 B gzip, non-market assets 1,907,220 B; 965 legacy market assets retained. Local HEAD e099e3443582d2ecdb1321f74738e5ca50688c23, reportedly 44 commits ahead of remote. These do not establish real-device frame-time or any speed improvement over the prior baseline.

**Remote PR #53 status:** Monthly Parquet → observed financial execution, Python reducer, durable PostgreSQL queue, workspaces and chart helpers exist; its OHLC architecture subsection still records an unimplemented proposal. No nine-timeframe private-R2 production path is demonstrated by the remote SHA.

**Revised implementation order:**
1. **Git safety**: preserve all 44 reportedly unpublished local commits; reconcile/push authentic ancestry safely, without force-push/squash/API snapshot. Do not cherry-pick this document onto a stale base without reviewing conflicts.
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

---

## 7. Integrated architecture vNext — efficiency plan and review scope (2026-11-13)

**Scope and authority:** This is the owner-selected target architecture *delta* linked from the sole authoritative PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md, not a competing authority. Decided: nine precomputed OHLC timeframe products stored on private R2; canonical Tick evidence and Python execution on VPS SSD; chart cache cap 5,000 *per selected timeframe, including D1*, with unlimited underlying qualified history by bounded paging. Everything about new reader representation, batching, sparse checkpoints and event-index settlement below is a **candidate subject to Claude challenge, CodeX proof and explicit owner approval for frozen changes**. Neither this design nor PR #55 constitutes release/deployment, commercial data rights, or an override of AGENTS.md, current phase, frozen 42.17/42.19 or existing financial goldens.

### 7.1 Logical layers and data placement

| Layer | Location | Responsibility | Does NOT do |
| --- | --- | --- | --- |
| Browser React/Vite, Lightweight Charts | Trader device | Chart, drawings, technical indicators, replay UX; render the *selected* precomputed TF | Execute authoritative fills, reconstruct a year's tick data, aggregate M1 into D1 on each switch |
| R2 private | Cloudflare R2 | Immutable nine-timeframe chart objects per symbol/period/source-version, source manifest and hashes | Expose future bars to untrusted replay clients or store financial Session authority |
| Chart authorization/delivery | VPS API or secure edge gate (compare measured economics) | Entitlement + Session/revision/cursor checks, bounded chart pages, authorized cache | Issue unbounded whole-month URLs revealing future H/L/C |
| Source and execution index | Local VPS SSD | Ordered Bid/Ask Tick Monthly Parquet or future independently verified physical equivalent, V2 seek plus optional time/min/max price index | Treat OHLC as a trading fill source |
| Financial execution and worker | VPS Python + bounded durable queue | Exact reducer, pending/market/SL/TP, revision, verified event and receipt | Permanent dedicated CPU for an idle user |
| PostgreSQL | VPS | Identity, Method, Session, append-only commands/events, receipts, state recovery, terminal archive, Journal/Analytics | Store full raw tick dataset separately for each trader |

**Operational goal:** static chart browsing and timeframe switching do not enter the heavy financial queue. Execution runs only while admitted bounded work exists. Cache a finite number of hot states per worker, not one process per logged-in trader.

### 7.2 Dataset and chart pipeline

1. Qualify rights, source identity, input hash, feed precision, time ordering/ambiguity, UTC calendar, gaps, quality and replay eligibility. Pre-2023 OHLC-only prehistory remains read-only; tick-enabled 2023–2025 may support settlement only when source-qualified. Planned 384 OHLC-only instrument-months and 544 Tick instrument-months remain **unverified targets**.
2. Reuse the locally reported streaming **BID M1** ZSTD writer and existing validation/manifest tooling; match the existing **MID = (Bid+Ask)/2** display contract or explicitly version and test a different price basis. Do not relabel BID bars as MID, nor hide provider-feed discontinuities.
3. Offline, once per source/version, materialize **M1, M3, M5, M15, M30, H1, H2, H4, D1** as independently addressable, compressed and immutable objects. All bars have pinned aggregation version, source rights, price basis, timezone/calendar, first/last time, actual counts, gaps/partial-edge flags and hash. Handle UTC month and D1 bucket boundaries without synthetic gaps.
4. Publish to **private R2 only when authorized**. Use path/version manifests and idempotent publication; chart users request the selected TF directly, not browser M1→D1 computation.
5. Deliver at most **512 eligible completed bars** on first load; later pages **500–1,000**, rolling chart cache **at most 5,000 for the selected TF including D1**. Qualified archive remains available beyond that cache, including all qualified D1 through pagination. Indicator warm-up uses a separately bounded causal buffer.
6. For Session at replay cursor T, only fully completed buckets with end <= T may leave the trusted boundary. Construct the forming candle solely from **revealed tick prefix**. In particular, raw R2 object URLs, object range headers, unrestricted indexes, cached CDN objects and error messages must not leak future full H/L/C, future gaps or EOF. Test server/edge responses and another tenant, not just UI clipping.
7. Do not delete the ~965 legacy public market assets or claim a build-size speed gain before dependency audit, staged replacement and rollback. If the chart gateway proxies every R2 byte via VPS, it can still incur VPS egress; compare bounded secure edge delivery against a simple VPS proxy with measured access, bandwidth and R2 operation costs.

### 7.3 Frontend optimization

**Locally reported done but not remote-verified:** incremental EMA with full fallback, shared incremental candle/volume updates, bundle-size measurements and CI guardrails. Reuse these, do not rewrite them.

**Next candidate changes:** remove unused market assets from build only after safe chart cutover; optimize ~1.2 MB logo; inspect initial JS bundle before adding lazy loading (some entry components already lazy); incremental other indicators if full-versus-incremental output equality passes; chart update and drawing anchor stability; coalesce network/re-render on playback; React profiling on desktop and a 3–4 GB Android.

**Important correction:** AlphaWorkspace's 500 ms delay follows each ADVANCE call; it is a playback loop, not automatically the same as 500 ms job-status polling.

Measure initial compressed bundle, LCP/TBT, main-thread long tasks, heap/RSS, fps at 1×/10×/100×, request count and candle/indicator equality. CI guardrails are not proof that real mobile performance improved.

### 7.4 Queue, API and worker optimization

**Current remote facts:** queue already uses PostgreSQL FOR UPDATE SKIP LOCKED; GLOBAL_LIMIT=16, USER_LIMIT=2, WORKERS configurable 1–4/default 2, durable lease/TTL and idempotent jobs. Do not recreate SKIP LOCKED or raise limits to hide bad latency.

- Instrument HTTP/admission → queue wait → worker startup or state resume → Arrow read/reducer → PostgreSQL commit → response; separate system time from user-visible latency.
- Use **bounded batched cursor advances** when allowed, rather than a durable DB transaction for every chart animation frame. Consider LISTEN/NOTIFY wake-ups plus SSE for state changes and reconnect; preserve durable queue, fairness, retry/reconciliation, cancellation and tenant isolation.
- Current identity rate limiter writes to PostgreSQL per protected request and uses IP budgets (special handling for auth). Measure cost and threat model before moving to user-aware in-memory limits; never remove the login/credential-abuse safety boundary. Likewise, profile DB connection setup before introducing bounded sync/async/native-worker pools with correct lifecycle.
- Test **warm process per worker with a memory-bounded per-Session cache**, TTL/eviction and restart fallback, not one permanent process per user. Preserve one heavy CPU job per worker and leave RAM/CPU for API/PostgreSQL. Decide 2/3/4 workers only from actual 6-vCPU/16-GiB VPS measures.
- Session long-run remains blocked by MAX_STEPS=256 and REFUSED_RECOVERY_LIMIT on prior long durable paths. Propose versioned checkpoint compaction/continuation; **do not simply raise MAX_STEPS** or fabricate extra Session identities. Requires explicit owner approval for frozen recovery-contract changes.

### 7.5 Tick Engine: compare, do not prejudge the final format

**Owner choice pending local Claude integrit​y tests.** A past local report compared ~82 s for per-event-validating reader with ~1.3 s for compact read on 150,103 ticks; the two paths did different work. 1,897 SMA trade equality does **not** establish full financial parity.

| Candidate | Advantage | Main gate |
| --- | --- | --- |
| A — existing 18-column Monthly Parquet | Baseline, source/provenance/quality representation intact | High Python conversion and revalidation overhead |
| B — same source + projected Arrow reader + bounded verified cache | Reversible; no new canonical file to store | Correct cache invalidation and exceptional-tick behavior |
| C — five-column or similar exact compact execution view + independently versioned identity/quality/provenance proofs | Potential speed and storage benefit | Exact event reconstruction, full reducer/hash/recovery parity and independent verification |
| D — replace canonical on-disk layout | Potential long-run simplicity | New versioned contract, backward compatibility and migration |

Keep A as fallback while testing B/C. Promote a compact design **if** the independent verifier proves source/event identity, exact Bid/Ask/ordinal, quality flags, spread, gaps, crossed quotes, equal-timestamp group ambiguity, pending/SL/TP, fills, partial close, balance, receipts, cold restart and repeat hashes **byte-for-byte**. Fixed-point integer comparisons are permissible only when source scale conversion is lossless; exact financial money arithmetic must remain identical.

**Verify-once candidate:** receipt keyed by source manifest hash, byte-level Parquet file and covered row-group hashes, verifier/policy version and immutable file identity. No trusting file paths alone; define corruption/mutation/revocation behavior. The existing per-row proofs remain available for independent forensic audit unless a separately authorized versioned migration replaces them.

**Manifest limits:** the reported 16,384 canonical node / 4,096 array/chunk constraints are a genuine area to audit, but don't globally raise normalization and all payload size limits using a temporary five-line patch. Compare segmented/versioned manifest with bounded independent verification and resource gates.

### 7.6 Indexed Jump to Next Event — Option D proof obligation

Candidate derived index per safe chunk: first/last time and atomic group, row range/count, min/max Bid and Ask, version/hash and ambiguity metadata. On pending order or position changes, test whether a complete chunk **can be proven incapable** of any financial state transition; skip only proven-safe chunks. Read candidate chunks in exact chronological atomic-group order through the existing reducer.

Events include pending fills, SL/TP, stop-out, relevant time/trailing exits and manual commands; an alert or next candle-close is not a financial fill. Manual scalpers without automatic triggers still need exact bounded cursor lookup and UI playback.

**Risk:** a simple min/max range can miss time-based logic, trailing movement, margin/equity triggers, partial order interactions and ambiguous same-time events. If the proof doesn't cover a particular rule, exact-scan fallback is compulsory. Indexed scanning may be speculative server-side, but never send future event times/final prices to the browser before the authenticated revealed cursor advances.

Previously recorded small-sample Jump used ~2.809 versus 1.359 CPU-s for baseline; the new indexed method is **not yet proven faster**. Measure eliminated blocks, CPU per Jump/full replay, memory, p95 click-to-event, exact state/event/receipt parity and restart equivalence. First implement as isolated experiment behind a feature flag; activation changes frozen settlement scheduling and needs owner approval.

### 7.7 Trade/Session data storage

Logical target: Session and dataset pin + append-only idempotent command log + immutable exact financial events/receipt + indexed active/terminal orders + bounded recoverable checkpoints + Journal/Analytics projections. Do not duplicate raw market tick data for each Session.

Claude cited prior PostgreSQL fixture: ~18.4 MB for 512 commands versus ~4.76 MB compact candidate; verify same workload and scope before claiming ~74% universally. Examine repeating full-state receipts/checkpoints, optional additive deltas, indexes/WAL and per-command payload growth. Compare dedup, compression, binary hash storage, sparse checkpoint plus canonical deltas and structural checkpoints for fills/closes.

**Do not delete or mutate currently immutable receipts/checkpoints.** Versioned snapshot/delta model and cold archival to R2 are **proposed** only and require explicit approval plus independent hash-chain, SIGKILL-before/after-commit, recovery, tenant separation, Journal/Analytics and retention tests. Recovery time and DB/WAL storage must be counted, not merely row payload bytes.

### 7.8 Capacity, economics and implementation gates

Target hardware is a **6 vCPU / 16 GiB** VPS with API, DB and worker co-location to be verified. A 10-trader tiny-fixture browser PASS is not a 20-trader throughput or price guarantee. Benchmark **three workload classes** independently: (1) chart-only multi-timeframe navigation/mobile, (2) manual scalping with many click events/no SL/TP, (3) swing trading with sparse orders and Jump. Record input hash/workload, CPU-s, wall latency p95/p99, FPS, memory, PostgreSQL rows/WAL/backup growth, bytes/tick, R2 storage/Class A/B requests/egress and VPS egress. Never extrapolate 63× end-to-end financial performance from read microbenchmarks or call hundreds of simultaneous traders proven.

| Gate | Scope | Proof to advance |
| --- | --- | --- |
| G0 | Preserve local Codex HEAD e099e344 and its 44 unpublished commits; read PR #53/#54/#55 | No force-push, overwrite, reset, snapshot flattening, or unstated merge |
| G1 | Frontend checkpoint integration and CPU/queue/DB baseline | Same-SHA metrics, tests and honest NOT RUN labels |
| G2 | Nine-versioned-TF offline generator + safe private-R2 fixture + chart API | 512 seed, 500–1,000 pages, 5k per TF including D1, no-lookahead, source/tenant boundary, offline hash |
| G3 | Compare A/B/C readers, verify-once proof and bounded cache | Full financial parity, independent evidence, version invalidation, real-host gate only with authorization |
| G4 | Batching, possible pool/NOTIFY/SSE and warm bounded workers | Idempotency, restart, CPU and latency before/after, rollback |
| G5 | Indexed Jump, long-session checkpoint design and sparse-state candidate | Explicit owner frozen-contract approval, exact parity and crash recovery |
| G6 | Actual commercial release readiness | Source rights and 384/544 coverage (or narrower owner-approved SKU), licensed display, real VPS load, billing/restore/security/economics and separate launch GO |

**Status:** G0 local source not yet published; frontend incremental checkpoint reported local only; G2–G6 not accepted. Source rights and Cloudflare credentials remain external gates, not permission to use/download real data. This document does not authorize any deployment, VPS access, new data admission, financial contract edit or production migration.

## 8. CLAUDE REQUEST — adversarial architectural review

**Review against the actual PR #53 code and Claude PR #54 audit; challenge this proposal, do not rubber-stamp it.** Return AGREE / DISAGREE / NEEDS DATA for each subsystem, with file-path evidence, economic assumptions, counterexamples and a better alternative where one exists. Do not treat unpublished e099e344 code as remotely inspected.

1. Does a private-R2 nine-TF architecture *actually* lower full infrastructure cost versus M1-only plus edge/server aggregation, counting object operations, storage, cache leakage and multi-tenant authorization? What is break-even at 16 instruments and 58 months?
2. Design an authenticated, replay-cursor-clipped chart gateway that cannot leak future complete OHLC via URLs, ranges, caching, metadata or unauthorized tenant access. Can it scale without proxying all bytes through VPS?
3. How should MID display and BID M1 source be reconciled? Show exact M1/H1/D1 edge, gap, DST/calendar and source-provider discontinuity tests.
4. Does the 5,000-bar cache **per selected TF including D1** remain efficient on 3–4 GB Android with multiple indicators, drawings and chart-library copies? What numerical memory/fps threshold is defensible?
5. Between projected existing 18-column, independently audited 5-column derivative, and canonical physical-format replacement: which is most efficient and least risky after **full** financial parity, not SMA alone?
6. Can verify-once receipts survive mutation, partial corruption, tampered cache, verifier version change, backup/restore and restarted workers? Show the minimum sufficient per-event evidence.
7. Is manifest segmentation better than raising all canonical limits? Give counterexamples and streaming validator requirements.
8. What does profiling actually show is the biggest bottleneck: Arrow-to-Python conversion, per-event validation, reducer serialization, queue/DB writes, or native child startup? Propose smallest **same-scope** test to isolate it.
9. Should queue optimization prioritize batching, native warm cache, rate-limit write removal, pools or NOTIFY/SSE, and which are already implemented (SKIP LOCKED, configurable 1–4 workers)?
10. Find a counterexample where Option D min/max chunk skipping misses an earlier SL/TP, stop-out, trailing/time exit or ambiguity. How can a proof-backed fallback preserve chronological first-event semantics and no-lookahead?
11. How do sparse checkpoints and delta receipts affect immutable hashes, database WAL, storage per command, restore time and the MAX_STEPS=256 long-Session blocker? Provide a versioned migration, not a limit raise.
12. Is the final 6-vCPU/16-GiB capacity and storage budget realistic for actual licensed 16×34 months and two-year prehistory? State which numbers are measured and which are hypotheses.
13. Identify conflicts with frozen 42.17/42.19, AGENTS.md, Commercial V1 target, existing source policies, historical authorization, and the new locally reported checkpoint. Classify owner-grant requirements.
14. Give **three concrete failure scenarios**, **one counterproposal architecture** if superior, and **the single most valuable next reversible code PR**. Include before/after metrics and reject thresholds.

**Required answer:** summary verdict; component-by-component AGREE/DISAGREE/NEEDS DATA table; precise counterexamples; better alternative where justified; prioritized reversible gates with objective PASS/FAIL; unknown rights/host risks; explicit owner decisions. Respond in PR #55 discussion or in the existing Claude critique document PR #54, linking this architecture. **Critique only; no runtime edits or frozen-contract changes**.
