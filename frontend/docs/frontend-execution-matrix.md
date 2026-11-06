# Frontend execution matrix (founder instruction 2026-11-06)

Scope: frontend and presentation only. Codex owns API, auth, ledger, storage and market data. No deploy, no merge to `main`, no backend or dataset change, no CP6A-10 benchmark or VPS work.

Visual source: design canvas artifact `5AHxbsfoT3xdaxuMi4mJMb` (artboards DesignSystem, NewSession, Landing, Workspace, MobileTrading…), read directly on 2026-11-06. Workflow source: PR #20 `docs/RIKSORA_DESIGN_FREEZE_V1/`.

## PR state (checked against GitHub on 2026-11-06, not PR descriptions)

| PR | Branch @ head | Owner | Implemented + tested | Partial | Missing | Duplicated / conflicting | Blocked |
|---|---|---|---|---|---|---|---|
| #20 Integrated design | `design/riksora-integrated-freeze-v1-20261104` @ e81814a | founder/Codex docs | Docs 01–18 used as the workflow contract | — | — | — | Owner approval to merge (docs only, no frontend code) |
| #36 Terminal, drawings, indicators | `claude/terminal-drawings-indicators-v1` @ 47a823b | Claude | C-01…C-12 (47 drawings, 50 indicators, Draft→Review→Confirm UI, phone/tablet), C-13 header declutter | Phone REVIEW_EXACT / COMMIT_PENDING full sheet; Pick-from-chart mini-ticket | — | #38 is stacked on an older head of this branch | Codex finance/API sign-off; Jump 72h (Codex B07); cross-device drawing sync (B08) |
| #38 Terminal preview | `codex/issue-37-terminal-preview` @ e75454f | Codex | Standalone `/preview/terminal/` build with synthetic fixture | — | Desktop/mobile browser QA of the preview | Based on an older #36 head: its `CandleChart.jsx` diff reverts #36 English labels to Indonesian and adds `previewOnly`. #36 C-13 now ships `previewOnly`, so a rebase only needs the preview files | VPS administrator (sudo) to run the installer; owner review |
| #39 Product frontend | `claude/product-frontend-v1` (stacked on #36) | Claude | CP1 (shell, auth, My Methods, Method create/overview, Session analytics), CP2 (this checkpoint) | — | CP3 (Journal page, mobile review sheet), CP4 (landing coverage, Account/plan/help/status) | Old Sessions hub (`AlphaSessions.jsx`) replaced and removed | Backend gaps listed in `product-screen-inventory.md` |
| #40 Storage proposal | `docs/session-storage-efficiency-20261105` @ c75e286 | Codex | Docs only | — | — | Overlaps #20 ADR-009 (stated in the PR) | Owner + Codex approval. Frontend impact: none today; the Continue card and Session overview read `GET /sessions/{id}` only, so a compact persistence format must keep that DTO stable |

## Checkpoint order

1. #36 C-13 terminal declutter → merged into #39 (merge commit, no force-push).
2. #39 CP2: shared SearchableSelect, InstrumentPicker, MethodPicker; Sessions page; New Session wizard; Session overview; Data Catalog.
3. #39 CP3: Journal page with filters, mobile review sheet, replay breadcrumb.
4. #39 CP4: landing honesty pass, Account/plan/help/status.

## Shared components

| Component | File | Notes |
|---|---|---|
| SearchableSelect | `src/tickAlpha/AlphaSelect.jsx` | ARIA 1.2 combobox in a popover: type to filter (case-insensitive, label/description/keywords), ↑ ↓ Home End, Enter, Escape (focus returns), Tab, outside click, clear button, loading / empty / no-options / error states, bottom sheet at ≤760px |
| InstrumentPicker | same | Options come only from `catalog.profile`; never invents availability |
| MethodPicker | same | Methods from the catalog, Protocol risk/R:R in the description |
| Chart settings popover | `src/tickAlpha/AlphaChartSettings.jsx` | Fit, Grid, Crosshair, Volume (disabled: no source volume), Full screen |
| StatePanel / PageHead | `src/tickAlpha/AlphaShell.jsx` | loading, empty, filtered, error+retry, offline, unavailable |

## Backend dependencies (unchanged by this checkpoint)

Session list with cursor and counts; Method edit/archive; 16-instrument availability; entitlements/quota; Trash/Restore; cross-Session journal; Method analytics aggregation; Google OAuth; plan/billing. Until each route exists the UI says "not published yet" and shows no estimate.
