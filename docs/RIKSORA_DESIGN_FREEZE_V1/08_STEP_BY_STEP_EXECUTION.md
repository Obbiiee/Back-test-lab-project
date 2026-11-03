# 08 — Step-by-Step Engineering Project Plan for Codex + Claude

**State:** detailed execution sequence designed now; implementation, VPS benchmarks, migration and frontend coding not authorized merely by merging documentation. Each checkpoint begins only after previous dependency and specific owner authorization. Preserve current main, Alpha state and financial/data source evidence.

## Work organization: two parallel tracks, one integration gate

**Codex — Backend/Data:** domain contracts, versioned API, market data adapters, finance/goldens, DB/event store, verification, security, capacity.
**Claude — Frontend/UI:** design tokens, complete desktop/tablet/mobile routes, interaction/drawings, unified API client/mock, PWA/app shell, accessibility/browser QA.
**Integration reviewer:** verify contract hashes and real backend receipts match actual client; owner approves semantic/financial/rights/cost/deploy decisions.

Every stage has: `input_version/SHA`, scope allowlist, implementation or document, success/negative tests, resource metrics where relevant, rollback and signed report. Changes to the existing cash/quote semantics require an explicit Change Request, never a fix by loosening expected assertions.

## Phase 0 — Final design review and scope freeze (docs only)

**P0.1** Check existing authoritative source precedence against all package documents, user-approved 16 symbols/72h rules/Protocol. Detect contradictions and record exact line/ref rather than making an ad-hoc alternative. **Deliver:** reviewed integration map + frozen adapter boundaries; no product code.

**P0.2** Codex extracts real FastAPI routes/model types and a candidate versioned OpenAPI contract, with actual vs missing fields. Claude signs the screen-data requirement coverage and product route map. **Deliver:** API field inventory and schema change proposal; no deceptive mock-only acceptance.

**P0.3** Owner signs ADR register and explicit launch scope (all 16 remain target, only qualified data can be advertised). Check out a separate design PR; avoid modifying frozen TRADING_METHOD_SESSION_SPEC or phase authority just to match this package. **Gate:** conflicting semantics resolved with approved versioned ADR.

## Phase 1 — Factual evidence inventory / baseline (Codex; read-only)

**P1.1** Locate actual Git main+branch+worktree, process and VPS runtime, source data, published receipts, current production service and actual schemas; measure disk/ram/network permissions. Inspect Exness 2015 historical report and any 2024 published snapshot with SHA/coverage; distinguish raw, canonical, index, QA, backup and duplicate candidates. Preserve all originals. **Gate:** SOURCE_VERIFIED or STOP.

**P1.2** Measure existing read path and Session storage: full SQLite archive + WAL, timeline per Session, tick_commands payload/replay receipt, per-command checkpoints, DB tables, memory/RSS, reader seek, cold resume. **Deliver:** reproducible baseline JSON+summary; no destructive compaction.

**P1.3** Confirm QA copy/scratch quota and rights. No source in Git; do not run expensive tests while active replay would be endangered. **Gate:** disk under hard resource limit and provenance preserved.

## Phase 2 — Freeze executable domain API and goldens (Codex with Claude review)

**P2.1** Freeze `DatasetRegistry`, `IndexedTickProvider`, `ExecutionReducer`, `SessionRepository`, `ResearchProjection` ports at canonical semantics. Create schemas/fixtures for admitted vs blocked catalogs, Method/Protocol, Session/revision, review-confirm and errors/async job. **Tests:** strict JSON roundtrip/versioning/invalid price/unknown fields/migration compatibility.

**P2.2** Test Alpha finance and replay invariants without changing reducer; include quote-side, ties, uncertainty, Free/Protocol, idempotency/fork, 72h Jump chronology. **Gate:** reference canonical hashes fixed.

**P2.3** Publish signed source-backed OpenAPI with actual endpoint state; Claude generates typed client and mock, no dummy financial success. **Gate:** backend/client fixture parity.

## Phase 3 — Shared market storage competition (Codex; branch isolated)

**P3.1** Extract source-hash pinned contiguous periods from verified published real data (busy, quiet, ties, crossing month, gap, EOF), no fabricated canonical price rows.

**P3.2** Run physical candidates: existing SQLite CAS, Parquet day vs month row-group, ZSTD levels 1/3/6 and safe row-group sizes; exact integer price + group provenance + evidence sidecar. Run PyArrow and DuckDB direct read; no DuckDB full-table import. **Evidence:** size/index/metadata/scratch, I/O, RAM/CPU, seek/cold page, requests, hashes; 3 repeated trials for finalists.

**P3.3** Select one layout by predeclared correct+Pareto resource gates; optimize at most bounded focused pass and remeasure. **Gate:** no canonical/event/quality mutation; no per-Session copies. No promotion to production.

## Phase 4 — Versioned reader integration (Codex)

**P4.1** Implement adapter behind existing `IndexedTickDataProvider` port; preserve exact timeline/command reducer events and foreign source/pin rejection. **Scope:** `backend/ticks/` and narrow composition/tests only. Do not rewrite execution reducer or frontend.

**P4.2** Compare random seek, consecutive groups and tied timestamp cross-file boundaries, 72h interval, first/last event and full qualified source against SQLite reference. **Gate:** byte/semantic parity, bounded memory, no lookahead; source read-only.

**P4.3** Expose only revealed candle/timeframe pages, dataset quality+rights and source identity to API. **Gate:** UI cannot request uncommitted future quotes.

## Phase 5 — Session storage, checkpoints and recovery (Codex)

**P5.1** Measure and eliminate per-tick Session storage amplification without loss of dedup/event audit. Specify **new** snapshot/command receipt codec and references; keep original checkpoint/retry receipts valid. **Scope:** `backend/execution/`, migrations + tests under explicit owner approval.

**P5.2** Build versioned recovery checkpoints and indexed cursor. Crash before/after commit, repeated command, stale revision, reconstruct after long prefix and rare old Session. **Gate:** identical ledger and state hashes after cold restart, no duplicate finance, bounded disk and user storage growth.

**P5.3** Transparent compatibility migration/dual-reader for old Sessions; owner-approved cutover+rollback only after complete isolated restore/QA. No deleting existing logs, accepted dataset or user evidence until proven safe.

## Phase 6 — Multi-instrument real contract (Codex)

**P6.1** Add immutable 16-symbol registry and source profile ports (one primary instrument per Session). Preserve old XAUUSD profile byte semantics.

**P6.2** Add new versioned non-USD conversion and exact money/lot rules (JPY, CHF, CAD, GBP, NZD) with bid/ask, freshness, causal timing, missing feed refusal. **Gate:** unit/golden/model tests + provider source admission, no invented feed. Target slot ≠ admitted source.

**P6.3** Dataset admission for each legally qualified real feed, with source/quality/version/rights proofs. Same engine, no currency-specific browser calculations.

## Phase 7 — Canonical replay, Jump, async jobs and analytics (Codex)

**P7.1** Complete 72-hour one-click Jump on same reducer: no event means reveal entire span, unchanged pending; first event stops in canonical order; compare exact tick-by-tick replay and cold restart. **Gate:** 0 ledger/cursor mismatch.

**P7.2** Bounded queue, cancellation, immutable command idempotency and reconciled status; no browser synthetic settlement.

**P7.3** Read-only Session/Instrument/Method analytics and journal/opportunity marks; comparable R only, no merging independent account curves. **Gate:** overlapping/missing FX/unknown risk exclusion test.

## Phase 8 — Claude UI design and parallel implementation

**P8.1** Claude audits existing React/Vite/Lightweight Charts, visual assets and active routes; maps every screen U01–U16 against actual implementation and 320/375/390/768/1024/1440 responsive matrix. **Deliver:** wireframes/components/token diff without replacing approved logo.

**P8.2** In `claude/ui-shell-...` branch implement protected routes/auth, first Method, Method overview, catalog/Session setup with pinned typed mock API. **Gate:** unit/visual/a11y tests; no fake datasets or numbers.

**P8.3** Implement desktop+touch chart, Planned/Quick ticket, Protocol locked rules, review-confirm steps, 72h Jump progress, terminal/Journal, analytics. Distinct mobile order bottom sheet and fullscreen chart touch modes. **Gate:** click/tap/keyboard no accidental order, real refusal handling, no future candle reveal.

**P8.4** PWA manifest/service-worker safe scope, app install and background-online resume; no financial offline queue. **Gate:** tested mobile Safari/Android Chrome behavior, logout wipes cached private UI, update safe. Native-store wrapper is future gated.

## Phase 9 — Integration QA (both)

**P9.1** Codex publishes tested API SHA/real fixture IDs; Claude pins client to that schema, switches to real bounded backend. **Gate:** contract and tenant/identity/recovery integration pass.

**P9.2** End-to-end: login → first Method → valid Protocol/Free Style Session → chart/Planned/Quick → Review → Confirm → Jump → Journal/Stats → reload/restart → resume → Method aggregate. Test different account, Free daily/month, Trash/quota, error/timeout/429/unresolved. **Gate:** same canonical state on desktop/HP/PWA.

**P9.3** Real browser/devices capture with dimensions/orientation/keyboard/focus/drawing geometry. No production source or ledger mutation during QA.

## Phase 10 — Single-VPS certificate and procurement verdict (Codex)

**P10.1** Run exact [single-VPS gate](../SINGLE_VPS_STORAGE_BENCHMARK_GATE.md): final physical schema, 0/100/500 decisions, Session 1/2/5/10, actual published year if qualified, 1 hot + 15 cold instruments or truthful partition proxy; record CPU/RAM/SSD/IO/p95 and 3 finalist runs.

**P10.2** Test full restore/backup/rights, security, session-link/payload audit, failure/worker kill, payment sandbox idempotency, TLS and legitimate user journey on actual host. **Gate:** existing reference Alpha SLO not silently waived.

**P10.3** Deliver only one reasoned `KEEP_ONE_VPS` / `OPTIMIZE_FIRST` / `ADD_STORAGE` / `ADD_COMPUTE` / `HOLD` verdict, exact bytes/cost with provider pricing verified at decision time, and owner purchasing signoff. No purchase/release via agent assumption.

## Phase 11 — Release candidate and monitoring (both + owner)

Package pinned backend/frontend commits, migration rollback, OpenAPI/fixture hashes, backup restore receipt, catalog admission list, capacity limit, monitoring, legal/privacy/payment evidence and reproducible QA. Owner decides limited internal beta/public paid GO/HOLD based on actual coverage and rights, not on target date or a green UI screenshot.

## General task DoD and failure behavior

Each PR: single scope, base/head SHA, input pins, tests (full relevant repo/AI bundle/Node golden/Postgres/browser), negative scenarios, CPU/RSS/storage for performance, rollback and changelog. The PR may not change frozen financial behavior, dataset truth or Product/Method contract silently. If blocked, stop at the smallest safe boundary, retain exact evidence and submit one test-backed corrective plan; no uncontrolled rewrite.
