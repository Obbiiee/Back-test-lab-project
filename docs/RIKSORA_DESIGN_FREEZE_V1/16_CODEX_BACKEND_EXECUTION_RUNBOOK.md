# 16 — Codex Backend Turnkey Execution Runbook (linked to Claude Issue #21)

**Authoring status:** implementation specification and GitHub ticket handoff, not backend implementation. Owner wants concrete sequential work, minimum cost, no hidden redesign or worktree. **Codex** owns backend, market data, API/auth, persistence, analytics and verification. **Claude** owns frontend UI, drawing/indicator calculations and responsive app. Integration is defined in [17 — Cross-Team API](17_CLAUDE_CODEX_API_ACCEPTANCE_MATRIX.md). The overarching execution stages remain [08](08_STEP_BY_STEP_EXECUTION.md).

## Must-read authority, no silent rewrites

Before any code, verify actual current branch+remote SHA and read: [project plan](README.md), [user-authorized product behavior](../PRODUCT_DESIGN_BLUEPRINT.md), [frozen Method/Session](../TRADING_METHOD_SESSION_SPEC.md), [financial rules](../V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md), [market data standard](../MARKET_DATA_STANDARD.md), [alpha data/ops](../V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md), [one VPS benchmark gate](../SINGLE_VPS_STORAGE_BENCHMARK_GATE.md), [security architecture](../SECURITY_ARCHITECTURE.md), [AI engineering guardrails](../AI_ENGINEERING_GUARDRAILS.md), [operational phase](../../AI_CONTEXT/04_CURRENT_PHASE.md) and [Claude Issue #21](https://github.com/Obbiiee/Back-test-lab-project/issues/21).

Implementation on an **actual GitHub-backed branch**, normal single checkout or direct GitHub integration, **NO `git worktree`**, no forced resets/rebases or altering Codex/Claude in-progress directories. Separate `codex/Bxx-...` branches for bounded checkpoints. Commit, push to origin, open PR for each passing increment, link dependencies. Never push runtime to main unreviewed, upload licensed private ticks/keys, delete 2024/2015 QA snapshots, modify production, buy VPS/object storage, initiate payment or change canonical financial semantics without approved gate.

### Actual main-repo evidence (as inspected Nov 4)

- `backend/ticks/storage_v2.py` implements V2 SQLite/zlib content-addressed dataset, with **actual** `IndexedTickDataProvider.describe_v2/locate_v2/read_page_v2/read_evidence_v2` protocol. **No confirmed production Parquet reader**. `backend/ticks/timeline_v2.py` persists Session position/advancement lookup and reconstructs prefixes.
- `backend/execution/postgres.py` stores `tick_commands`, `tick_events`, `tick_checkpoints` with a full checkpoint each command; `backend/execution/research.py` owns frozen Method/Session and financial workflow; `backend/execution/historical.py` binds qualified Exness XAUUSDm subset. These are **preserve/benchmark/optimize**, not replace wholesale.
- `backend/cloud/{app,research,workspaces,queue}.py` owns FastAPI auth/workspaces/research/job routes and bounded queue. `backend/market_data/service.py` is a read-only source service but its access filter is explicitly **not** an authoritative Session cursor.
- Main operational pointer records **Alpha capacity gate FAILED** (20×/85% RAM + reference/HTTPS not passed). Older docs mention 2015 Exness **Aug 10–Dec 31 only**, not full 2015. VPS 2024 source and active QA job require fresh read-only audit. Public UI/login ≠ certified backtest.
- Some branch experiments (incl. `codex/cp6a10-postannual-handoff`, `codex/compact-writer-20261026`, `codex/columnar-storage-probe-20261024`) are **candidates** to audit; do not merge blindly or declare production.

## Fixed goals and exclusions

**Versioned stable law:** 16 exact target instruments, one primary instrument per Session, shared immutable data (no per-user tick copy), exact Bid/Ask/costs/causality, no lookahead, independent pending orders without OCO, fixed one-click 72 elapsed UTC hours Jump, Method Free Style/Protocol rules, server review → confirmation → receipt, append-only financial ledger, subscription accuracy parity, cross-device same Session. Open-source/professional chart calculations remain Claude's `frontend/` scope; backend stores chart objects + indicator configs and serves bounded authorized candle series. Do not implement all 50 chart indicator calculators in Python merely to satisfy Issue #21; that wastes CPU and duplicates implementations.

**Economic constraints:** initial single 6 vCPU / 16 GiB RAM / 200 GB SSD, shared object cache, source partitions requested on demand, PostgreSQL on same VPS, bounded worker/connection pool, no mandatory Redis/microservices/Kubernetes/second chart engine, no mandatory 2TB purchase. Source commercial-rights evidence, off-node backup and restore are independent release gates. Physical day vs month Parquet, PyArrow/DuckDB, ZSTD level and snapshot cadence selected by benchmark, never by untested intuition.

## Phased implementation — each is one reviewable PR, no hidden worktree

### B00 — repository + VPS inventory / destructive-action preflight (READ ONLY)

**Dependencies:** owner-approved design and safe access; no dependency on Claude code. **Files allowed:** QA reports `docs/qa/` or `reports/` only; no runtime writes; no dataset deletion. **Exact work:** inspect main/latest branch experiments, process/unit configuration, disk/CPU/RAM, 2015/2024 source+manifest+hash, SQLite canonical, 21GB/97GB candidate copies, database sizes including WAL/temp, 1/2/10 Session logs, source rights; classify PROD_SOURCE/QA_ARCHIVE/ROLLBACK/BACKUP/TEMP/UNKNOWN. Verify no ongoing year replay would be damaged. **Deliverable:** source passport, safe storage ledger, branch provenance, preserve/delete candidates (recommendation only). **PASS:** every claimed existing source identified by actual path/size/hash/coverage/owner; no uncertainty hidden. **STOP:** uncertain source hash, unsafe disk/quota or live replay conflict; do not buy/delete.

### B01 — domain/API inventory and frozen OpenAPI handoff (Codex + Claude contract review)

**Dependencies:** B00 actual repo checkout; [17 API matrix](17_CLAUDE_CODEX_API_ACCEPTANCE_MATRIX.md). **Files:** `backend/cloud/` tests and *generated actual* `docs/contracts/riksora-api-v1.openapi.yaml` (contract review before implementation). Extract actual FastAPI OpenAPI/route registration and map each U01–U16, DR tool CRUD and indicator settings control from Claude Issue #21 to `EXISTING / NEEDS_ADDITIVE_ENDPOINT / FUTURE`. Pin actor/workspace/Session permissions, pagination, cursor, async `202` job, idempotent command ID and machine errors. **PASS:** Claude can generate typed client and deterministic contract mocks without inventing endpoints; exact schema SHA and sample response/error fixtures verified, 401/403/404/409/422/429 tested. **STOP:** mismatch between frozen financial API and frontend desired payload; ADR instead of changing finance secretly.

### B02 — source registry, precise Instrument Profile and admission states

**Dependencies:** B00+B01. **Files:** `backend/market_data/`, `backend/ticks/`, narrow session/catal​og models/tests only. Create versioned passport `datasetId/version/feed/provider/instrument/profile/quality/rights/eligible UTC intervals`; target symbols `AUDUSD, EURGBP, NZDUSD, USDCHF, AUDJPY, CADJPY, EURUSD, GBPUSD, NZDJPY, USDCAD, CHFJPY, EURJPY, EURNZD, GBPJPY, USDJPY, XAUUSD`. Actual available/partially available/blocked/rights-blocked/planned distinct; **never mark all 16 available by registry alone**. Dataset immutable; Session pins source/contract/version; explicit no unauthorized catalog fallback. **PASS:** canonical hashes/order/UTC sidecars verified, qualified periods only selectable, provenance and license status exposed, arbitrary symbol/path injection rejected. **STOP:** source/data rights unknown for public serving; internal QA may remain source-scoped.

### B03 — REAL published-source Parquet/reader competition (no migration yet)

**Dependencies:** B00+B02 and safe scratch budget. **Files:** isolated `backend/ticks/` experiments + benchmarks/tests, reports. Benchmark current SQLite V2 against Parquet **per UTC day** vs **per month with row-group pruning** (ZSTD 1/3/6, 32k/64k/128k/256k rows), PyArrow and DuckDB direct bounded scan, source rights and exact integer prices. Use source-pinned 1h/day/72h/month/year windows incl. same-timestamp ties, gap, month boundary, busy/quiet periods; 3 repeated finalist trials with IO/cache notes. Record total disk incl. WAL/index/temp, cold/warm seek p50/p95 if sample size valid, CPU/RSS, request/read bytes, canonical event+evidence hash. **PASS:** zero canonical ordering/evidence mismatch, bounded memory, documented Pareto choice; or HOLD if none qualifies. **STOP:** any future leak/precision loss; never convert/drop production archives in this step.

### B04 — canonical Parquet storage adapter + bounded chart/historical candle API

**Dependencies:** B03 winner + B01 DTO. **Files:** `backend/ticks/`, `backend/market_data/`, `backend/cloud/` chart service, relevant tests. Adapt new selected physical storage behind **existing V2** provider `describe_v2/locate_v2/read_page_v2/read_evidence_v2`; no forked settlement/replay reducer, raw source unchanged. Add chart read path for `timeframe`, bounded `start/end/limit/pageToken`, candle OHLC, forming flag, price basis, source quality, actual volume availability, immutable feed/version and **authorized prefix restriction** tied to authenticated Session's committed cursor. Earlier calendar context may be separate **read-only** and explicitly flagged. Tier restrictions enforce tradable window but context may still be read-only by policy. **PASS:** existing V2 fixtures and qualified real-source 1-year parity, 9 current tf display, no future candle/indicator/source proof leaks, page cap and index behavior; same-time group/EOF handling exact. **STOP:** missing canonical sidecar evidence; never grant raw future tick streaming to browser. **Handoff to Claude:** `chart.CandlePage v1`, `MarketDataQuality`, `ChartReadOnlyContext` fixture SHA.

### B05 — compact Session command receipts, ledger and recovery

**Dependencies:** B01 + B04 provider parity. **Files:** `backend/execution/postgres.py`, `research.py`, `backend/ticks/timeline_v2.py`, versioned `backend/infrastructure/migrations/`, tests. Measure current write amplification in `tick_commands`, `tick_checkpoints`, `position_lookup`, WAL; design new append-only command identity+event+hash and **bounded compact current state + periodic indexed snapshot**. Maintain same-byte retry receipts and old-Session dual reader/versioned codec, no historical hash rewrite. Durable cursor/version/source pin, active orders and positions preserved; bounded suffix replay from checkpoint, not entire year at every restart. **PASS:** 0/100/500 trade cases + 1/2/5/10 Sessions storage growth; crash before/after commit and double submit exactly once; cold resume full-year after checkpoint canonical hash/finance equality; storage grows with user actions/evidence **not every raw tick**. **STOP:** old Session restore, ledger dedup or irreversible migration fails; no live delete/cutover without owner approval.

### B06 — complete instrument execution profiles, historical FX conversion (versioned extension)

**Dependencies:** B02, B04, B05 goldens. **Files:** profile version/financial adapter + `backend/execution/` narrow contract extension and tests. Freeze old Alpha **XAUUSD/USD** event semantics. For 16 target slots, implement exact tick/lot/contract size and timestamp-side bid/ask conversion to account USD using independently pinned historical FX conversion source, freshness, no post-event rate, gaps/tie uncertainty. Account USD currency only V1; one primary symbol per Session. User-facing unsupported conversion is REFUSED or UNRESOLVED, not today's rate. **PASS:** verified golden vectors USD-quoted, EURGBP, EURNZD, GBPJPY, USDJPY, CHFJPY, USDCHF, USDCAD, commissions, partial exits, risk/lot step and currency conversion; preserves old hashes. **STOP:** missing source/profile or changed old Alpha financial parity. No "all 16 real-feed ready" without admitted datasets.

### B07 — single chronological engine, next-event Jump 72h and background queue

**Dependencies:** B04+B05+B06 interfaces. **Files:** `backend/execution/controller.py`, `backend/cloud/{research,queue,worker}.py`, golden tests. Fixed one-button **72 elapsed UTC hours**; first eligible order activation/protective event, pending orders independent and no-event preserve them; no OCO/auto expiry. Controller alone may privately inspect future for an authorized Jump; engine/browser never see uncommitted future quote. Same normalized reducer/ledger as step-by-step replay. Queue admits 202 with jobID, scoped GET/cancel/429 and safe double-submission/recovery. **PASS:** exact event/ledger/state/ending cursor parity for normal vs Jump and restart (including no event, multi-pending, tie, gap, EOF), full real-source test and bounded API budget. **STOP:** any financial mismatch, uncertain quote treated as certain or double trade.

### B08 — **NEW CLAUDE DEPENDENCY: Drawing and indicator settings cross-device persistence**

**Dependencies:** B01 OpenAPI shape, verified authenticated Session ownership; can **run in parallel with B03–B07** after B01; no dependency on selected Parquet. **Files:** new `backend/cloud/chart_assets.py` or explicitly equivalent module, migrations `backend/infrastructure/migrations/01x_*.sql`, tests. **Do not store drawings in tick ledger or dataset**.

Persist per verified `workspaceId/sessionId`:
- `research_chart_objects`: `objectId`, `schemaVersion`, `type`, `anchors:[{timeNs,priceDecimal}]`, `style` (color, strokeWidthPx, strokePattern, opacity, fill, text Bold/Italic/font/size, Fib levels, label placement), `locked`, `visible`, `zOrder`, `revision`, `sourceVersionPin`, `deletedAt`.
- `research_indicator_instances`: `indicatorId`, `instanceId`, `calcVersion`, `inputs`, `outputsStyle[]` (color, width, visible, opacity, dash, fill), `paneId`, `paneOrder`, `scale`, `displayOrder`, `revision`, `deletedAt`.
- `research_layout_prefs` separate bounded per-account/device-class UI view state, not authoritative finance or source. **One row per object/instance, no giant per-tick Session snapshot.**
- Establish concrete quotas **200 drawing objects/Session, 16 displayed indicator instances baseline, 64 KiB per object (brush paths capped), 4 MiB total chart object payload/Session**, only adjustable after measured UX/storage proof; accept 100-drawing stress test. Style + anchor roundtrip exact, preserve original V1 shapes through backwards-compatible reader.
- Proposed API prefix `/api/v1/workspaces/{workspaceId}/research/sessions/{sessionId}/chart-objects`: **GET paginated, PUT /{objectId}, DELETE /{objectId}**; same for `/indicator-instances`; `/layout-preferences` GET/PUT under device class. `expectedRevision` + idempotent `mutationId` on writes; transaction conflict -> 409; 403 foreign workspace; 413 object/collection oversized; 422 impossible type/payload. Canonical decimal strings, UTC integer ns strings; versioned migration old local user drawings only after explicit authorized import. Batch operations limited; no loss in simultaneous laptop/HP edits.
- **PASS:** Claude issue #21 settings truly sync laptop↔HP↔PWA; stroke width 1→5, Bold false→true, point move -3 ticks, Fib level style, pane reorder after refresh on two clients, 409 conflict and safe recovery, third user 403, source pin different denied; zero tick dataset clones/finance mutation. **STOP:** lost object revisions, cross-tenant or rollback breakage.
- **Handoff:** OpenAPI `ChartObjectV1`, `IndicatorInstanceV1`, `LayoutPreferencesV1`, deterministic positive/negative fixtures, all status code docs, API SHA to Claude.

### B09 — Method/Session/Instrument Analytics, Journal and research evidence APIs

**Dependencies:** B05 ledger+data semantics, B01 contract; can build independently of B06 if aggregation refuses unsupported FX comparability. **Files:** `backend/execution/{analysis,journal,research}.py`, `backend/cloud/research.py`, tests. Session summary from committed ledger only: completed/trade count, win rate denominator, R, expectancy, PF, cash drawdown, unresolved, exclusions; Method summary groups by instrument/feed and eligible Session, no naive mixed-currency portfolio equity. Paginate trades and user journal/setup markers, pin source/trade/time and author; no invented counterfactual trade. **PASS:** zero trade, 1/500 trade, partial close, different Method Sessions, overlapping windows and missing FX evidence yield truthful null/refusal/unsupported metrics. **Handoff:** Session/Method Analytics and Journal DTOs with executable fixtures.

### B10 — Identity linking, Free entitlement, safe payment and account migration

**Dependencies:** B01 and stable actor/Session ownership. **Files:** `backend/identity/`, `backend/cloud/app.py`, entitlement/payment modules only after provider decided, migrations/tests. Email and Google login must not create duplicate user; **link with explicit verified proof**, do not merge by matching email alone. Workspace authorization and data export, logout all, token revocation, cross-tenant denial. Free = **one calendar-month tradable window per reset day**, **5 saved active Sessions**, **30d Trash**, open authorized position may resolve beyond window but no new unrelated entry, Free and Pro same financial truth. Payment webhook exactly-once in **test/sandbox** before merchant credential approval; no provider enablement/charging in this checkpoint. **PASS:** auth reset/link conflict, cross-account jobs/source/drawings, Free/Pro equivalence, quota boundary, expiry/open continuation, webhook duplicate/reversal and restore. **STOP:** account linkage loss or unauthorized tenant cross-read.

### B11 — one VPS capacity, read-only source and disaster-recovery certification

**Dependencies:** implemented reader/session/replay/client contract, B00 audited host; qualified real source and owner-approved test window. **Files:** QA harness/report + limited ops instrumentation; no production deploy. 6vCPU/16GiB/200GB measured host; 1 real user full-year, 0/100/500 actions, 1/2/5/10 independent Sessions pinned same immutable feed; 1 hot + many cold periods/symbols (label proxy if actual 16 missing). Measure CPU/whole-host RAM <=85%, usable disk <=80%, I/O, real p50/p95, queue, 2024 source integrity, restore from **off-node encrypted backup** to isolated environment, job stop/full disk/S3 outage. Existing 20x/10 Session and reference Alpha gate must **not** be waived. **PASS:** clear `KEEP_ONE_VPS / OPTIMIZE_FIRST / ADD_STORAGE / ADD_COMPUTE / HOLD` with bytes and contemporaneous service prices. Source provider license check separate. No auto-buy VPS, S3, 2TB, backups or hosting plan.

### B12 — integrated backend↔Claude UI E2E, release-candidate handoff

**Dependencies:** B01–B11 relevant gates, Claude Issue #21 UI checkpoints, per-source licensing and owner release approval. **Files:** narrowly scoped integration/browser tests, QA reports and release contract. Pin Codex backend API schema SHA and Claude typed-client version, run Method creation → qualified dataset Session → chart/drawing style persist → 50 indicator **frontend** value fixtures and actual candle API → order Review/Confirm → replay/Jump 72h → Journal/Analytics → reload on laptop/HP/PWA → account switching and Free quota. Test errors 401/403/409/422/429/503, stale timeout, no lookahead and crash. Complete final reference/capacity + real device + privacy/data rights/TLS before public Beta. **PASS:** backend signs finance/data; Claude signs UI; owner signs public production deploy/purchase. **STOP:** any unqualified data, missing rights, API mismatch, restore uncertainty or browser false fill.

## B00–B12 checkpoint dependency DAG

```text
B00 → B01 → B02 → B03 → B04 → B05 → B06 → B07 ─┐
       │                 │      │                │
       ├─────────────── B08 (chart objects/settings) ─┤ → B12 integration/release
       ├─────────────── B09 (journal/analytics) ─────┤
       └─────────────── B10 (identity/Free/payments) ┤
                                      B11 (host/source/DR) ┘
```

**Clarification:** arrows show *minimum API contract prerequisite* for B08/B09/B10, not permission to bypass their internal dependencies (B09 depends B05 ledger, B11 depends final optimized modules). Begin Claude layout/tool UX with **version-pinned B01 mock fixtures**, independently of backend storage. Do not wait for Parquet selection to start frontend shell/drawing UI. The final QA joins completed work.

## Standard agent checkpoint report (nonoptional)

```text
CHECKPOINT_ID / GITHUB_ISSUE:
OWNER: Codex | REVIEWER: Claude or Owner
BASE_SHA / HEAD_SHA / REMOTE_BRANCH / PR_URL:
CONTRACT_API_SHA / DATA_SOURCE_HASH / EXECUTION_PROFILE:
EXISTING_IMPLEMENTED vs NEW_CODE vs NOT_YET:
FILES_CHANGED_ALLOWLIST + WHY:
QA_TEST_COMMANDS (exact exit codes) + HASH_DIFF:
CANONICAL_FINANCE_PARITY / NO_LOOKAHEAD / CROSS_TENANT:
CPU_RAM_DISK / READ_AMP / P50_P95 (if performance task):
CLAUDE_UI_HANDOFF (fixture SHA + endpoint/status):
FAILURE_FIXTURE / STOP_REASON / PRESERVE LIST:
ROLLBACK / BACKWARD_COMPAT:
OWNER_GO_OR_HOLD:
```

**Rule:** do not mark a stage PASS on its design, mock, branch existence, historical report, or PR opened alone. Status `SPECIFIED`, `CODE_PUSHED`, `TESTED_FIXTURES`, `TESTED_PUBLISHED_SOURCE`, `HOST_CERTIFIED`, `RELEASE_ELIGIBLE` must be independently evidenced.
