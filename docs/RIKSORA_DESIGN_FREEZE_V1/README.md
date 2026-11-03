# RIKSORA — Integrated Product & Engineering Design V1.0

**Document state (2026-11-04):** proposed integrated *design freeze for owner review*, docs-only. NOT production implementation, approved release, fully qualified dataset, benchmark certificate, or authority for destructive changes. Owner direction: make design, interfaces, execution steps and Codex–Claude coordination complete **before coding**. No runtime, data, deployed environment, billing or provider configuration has been modified by this design package.

## One product, three form factors, one canonical backend

RIKSORA is a **Method-first, evidence-grounded trading research laboratory**. Primary progression: Sign in → Method → Session (one instrument, pinned feed/version/profile) → Replay → Plan/Review/Confirm orders → Journal → Session Analytics → Method/Instrument Analytics → Resume. Future AI comparison reads evidence and produces bounded test proposals; it never invents trading results.

- **Desktop/laptop:** React+Vite chart-first full workspace, keyboard/mouse.
- **Mobile browser:** same React app with deliberately touch-designed navigation, chart, order ticket and journals.
- **Installable application V1:** PWA based on the same app, manifest, safe service worker, correct online/auth/logout/resume behavior. Android/iOS **Capacitor native shell is the chosen later store-app delivery path**, with its own signing/store/compliance gates and no fork of financial logic; no app-store release is claimed now.
- **Backend:** FastAPI modular monolith + single canonical execution reducer + PostgreSQL immutable financial ledger; shared immutable market catalog behind versioned reader port; bounded worker/queues/cache; no mandatory Redis/Kubernetes/microservices/second VPS.
- **Market target:** EXACT 16 instruments × 5 years (80 instrument-years), not a claim of availability or rights. One active research user on target 6vCPU/16GiB/200GB VPS, subject to measured acceptance. CPU/storage upgrades **only** via evidence.

## Single-source authority and precedence

This package is an **integration/implementation handoff**, NOT a rival to or replacement for existing frozen owners. On any collision, STOP and refer to:

1. [Operational authorization/status](../../AI_CONTEXT/04_CURRENT_PHASE.md) and [workflow](../../AI_CONTEXT/06_WORKFLOW_RULES.md).
2. [Frozen Trading Method/Session/Protocol UX](../TRADING_METHOD_SESSION_SPEC.md) and [owner-approved product direction](../PRODUCT_DESIGN_BLUEPRINT.md).
3. [Execution/Financial/Evidence Contract](../V2_ALPHA_EXECUTION_FINANCIAL_CONTRACT.md), [Market Data Standard](../MARKET_DATA_STANDARD.md), [Data/Ops/Release Contract](../V2_ALPHA_DATA_OPS_RELEASE_CONTRACT.md), [Subscription Specification](../SUBSCRIPTION_ENTITLEMENT_SPEC.md).
4. [Architecture Blueprint](../PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md), [Engineering Master Plan](../ENGINEERING_MASTER_PLAN.md), [Single-VPS benchmark/procurement gate](../SINGLE_VPS_STORAGE_BENCHMARK_GATE.md), existing code and **current VPS evidence**.
5. This package resolves **integration gaps** and identifies extension contracts. Historical examples, prototypes and unmerged branch work are not production truth.

Old high-level blueprint references to a Next.js app are **superseded as an implementation suggestion by the observed React+Vite codebase**; no frontend-framework rewrite. Earlier notional API namespaces are not a promise that endpoints exist.

## Design deliverables / reading order

| File | Purpose | Owner |
| --- | --- | --- |
| [01_PRODUCT_UX_FLOWS.md](01_PRODUCT_UX_FLOWS.md) | full scope, route inventory, Method/Session journeys, refusal, billing, future research | Product + Claude |
| [02_BACKEND_ARCHITECTURE.md](02_BACKEND_ARCHITECTURE.md) | module responsibilities, stable ports, command state machine, FX conversion, correctness | Codex |
| [03_DATA_STORAGE_INFRA.md](03_DATA_STORAGE_INFRA.md) | immutable market data, daily Parquet candidate, per-trader storage, cache, DR, cost gate | Codex |
| [04_FRONTEND_RESPONSIVE_APP.md](04_FRONTEND_RESPONSIVE_APP.md) | UI components, design tokens, desktop/tablet/mobile/PWA/app behavior, a11y | Claude |
| [05_API_INTEGRATION_CONTRACT.md](05_API_INTEGRATION_CONTRACT.md) | actual vs planned API, DTO, errors, idempotency, async/reconciliation, mock parity | Codex + Claude |
| [06_AI_TEAM_COLLABORATION.md](06_AI_TEAM_COLLABORATION.md) | branch ownership, PR handoff, review, conflict management, operating rhythm | Both |
| [07_VERIFICATION_AND_UNKNOWNS.md](07_VERIFICATION_AND_UNKNOWNS.md) | executable acceptance matrix, finite known-unknown decisions, stop gates | QA + Codex |
| [08_STEP_BY_STEP_EXECUTION.md](08_STEP_BY_STEP_EXECUTION.md) | ordered implementation checkpoints, dependency/rollback/DoD | Codex + Claude |
| [09_ARCHITECTURE_DECISIONS.md](09_ARCHITECTURE_DECISIONS.md) | ADRs, frozen vs replaceable, migration/version/change control | Owner + reviewer |
| [10_FRONTEND_CLICK_BY_CLICK_JOURNEYS.md](10_FRONTEND_CLICK_BY_CLICK_JOURNEYS.md) | Click-by-click route/action and user flow navigation matrix | Claude |
| [11_TRADINGVIEW_LIKE_DESKTOP_TERMINAL.md](11_TRADINGVIEW_LIKE_DESKTOP_TERMINAL.md) | Chart-first laptop terminal, exact 9 drawings + 2 position planners, 7 indicators, trading ticket | Claude |
| [12_MOBILE_TABLET_APP_EXACT_SPEC.md](12_MOBILE_TABLET_APP_EXACT_SPEC.md) | 320–1024 mobile/tablet layouts, touch gestures, landscape, PWA and app lifecycle | Claude |
| [13_CLAUDE_SCREEN_WIREFRAMES_COMPONENTS.md](13_CLAUDE_SCREEN_WIREFRAMES_COMPONENTS.md) | Actual wireframes for all core screens and React component/route ownership | Claude |
| [14_DRAWING_INDICATOR_PROFESSIONAL_TOOL_CATALOG.md](14_DRAWING_INDICATOR_PROFESSIONAL_TOOL_CATALOG.md) | Complete 27-tool design target, 22-indicator design catalog, geometry, input and QA | Claude + Codex math validators |
| [15_CLAUDE_READY_TO_CODE_EXECUTION_RUNBOOK.md](15_CLAUDE_READY_TO_CODE_EXECUTION_RUNBOOK.md) | Scoped Claude frontend coding stages F00–F12, tests and API SHA handoff | Claude |
| [16_CODEX_BACKEND_EXECUTION_RUNBOOK.md](16_CODEX_BACKEND_EXECUTION_RUNBOOK.md) | Codex executable B00–B12, source/Parquet/Session/FX/API/capacity checkpoints; [backend Epic #22](https://github.com/Obbiiee/Back-test-lab-project/issues/22) | Codex |
| [17_CLAUDE_CODEX_API_ACCEPTANCE_MATRIX.md](17_CLAUDE_CODEX_API_ACCEPTANCE_MATRIX.md) | 19 real/proposed endpoint contracts; drawing/indicator/Session/replay contract and actual SHA handoff | Codex + Claude |
| [18_CURRENT_GITHUB_READINESS_20261104.md](18_CURRENT_GITHUB_READINESS_20261104.md) | Verified status vs unknown live VPS and next earliest execution gate | Owner + reviewer |

## Levels of freeze

- **FROZEN PRODUCT LAW:** Method/Session/Protocol semantics, two-stage review-confirm, 72h UTC Jump, no lookahead, no fake data, exact finance, immutable ledger, user isolation, identical truth across Free/Pro; existing authoritative contracts remain controlling.
- **FROZEN SYSTEM BOUNDARY (proposed V1):** one application API, backend financial authority, shared canonical market data, per-Session reference/event/checkpoint storage, versioned reader and DTOs, bounded cache, replay without per-user tick clones, React app for all surfaces.
- **BENCHMARK-SELECTED IMPLEMENTATION:** physical Parquet per-day versus monthly row-group, ZSTD level, PyArrow versus DuckDB read path, indexes/cache/worker budgets, remote vs local object location, checkpoint cadence. These choices MUST NOT alter frozen semantic ports.
- **OPEN EXTERNAL EVIDENCE:** actual published 2024 dataset/host inventory, rights, 16-source admission, price/lot/FX feed profiles, benchmark, distribution/payment/TLS capacities. These are verifiable **release and implementation acceptance gates**, not permission to redesign the product.
- **NOT FROZEN / future versions:** AI counterfactual analytics, multi-instrument portfolio clock, hosted app-store native distribution, broker execution equivalence.

## No surprise engineering rule

**No code first.** Before runtime changes, review this package against existing sources, close genuine contradictions with a human-approved ADR, then create small branch-scoped tickets. Each checkpoint has concrete input hashes, changed-file allowlist, contract tests, failure criteria, measured resource outputs, owner, reviewer and rollback. Approval of this docs PR **does not authorize production changes, purchases or migration**.

Readiness vocabulary: `DESIGNED`, `IMPLEMENTED`, `VERIFIED_ON_FIXTURE`, `VERIFIED_ON_PUBLISHED_SOURCE`, `CAPACITY_CERTIFIED`, `HOSTED_AND_LICENSED`. These are distinct facts; none is implicitly advanced.

**User acceptance:** the architecture is reviewable now; Code/QA execution still requires subsequent authorization. Keep the old and failed evidence, do not erase it to obtain a clean green dashboard.
