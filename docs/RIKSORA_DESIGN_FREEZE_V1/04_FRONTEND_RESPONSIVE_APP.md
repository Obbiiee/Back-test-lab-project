# 04 — Frontend Design, Responsive Workflows and Installable App

**Claude owns this UI design and React code. Codex owns authoritative APIs and finance.** The current frontend is React + Vite + Lightweight Charts, NOT the old hypothetical Next.js layout. No new framework, no duplicate financial simulator, no frontend-generated fills.

## Platform decision

- **Desktop/laptop V1:** same React application; chart-first research terminal, keyboard/precision mouse interaction and dockable panels.
- **Tablet/mobile web V1:** same route/DTO/component model, separate responsive compositions and TOUCH interaction, not a scaled-down desktop.
- **App V1:** installable **PWA** using same deployed origin, manifest, icons and shell cache. Core replay, trade confirmation and financial write **online only**; no offline authoritative order queue. Android Chrome and iOS Safari Add to Home Screen tested separately. App background/resume must fetch server Session, not advance an invisible local financial clock.
- **Later store app:** optional Capacitor-style native shell wrapping the same web app, decided only when app-store/deep platform requirements are evidenced; separate release/signing/privacy/store QA. Do not promise Play Store/App Store submission from PWA alone.

## Brand and design tokens — inherit already approved design

**Do not regenerate the metallic R brand asset.** Approved brand colors: midnight navy `#06162E`, electric blue `#0965FF`, ice white `#F5F8FC`, silver `#C8D1DE`, amber `#FFC83D` (warning/evidence accent only), muted gray `#64748B`. Preserve existing self-hosted font assets and design work. Light informational/research home, dark/navy chart workspace, accessible contrast; tabular numeric prices, 14px body baseline, 12px secondary minimum where safe, restrained radii, motion reduced by preference. Define semantic tokens `surface/page/card/chart`, `text/main/muted`, `action/primary/disabled`, `evidence/warn/unresolved`, `finance/positive/negative`, `border/focus`. No color-only financial status; accessible label accompanies every color.

Layout tokens as design proposals for visual tests, not fixed assumptions about hardware: compact phone 320–389 CSS px; normal phone 390–599; tablet 600–1023; desktop >=1024; wide >=1440. Touch target **minimum 44x44 CSS px** on mobile; desktop precision controls remain keyboard accessible. Support pointer, touch, keyboard, screen readers and 200% zoom. 320px must have no document horizontal overflow; chart axes may locally pan/scroll without hiding order state. Respect safe-area insets on notched phones, dynamic viewport height, orientation and keyboard overlays.

## Route to component map

| Route/surface | Desktop hierarchy | Tablet | Mobile/PWA |
| --- | --- | --- | --- |
| Auth, verify, reset | centered form + information | centered | full-height step form + clear error |
| Methods hub | searchable grid/table; last Session | two columns | single cards; primary Create Method |
| Method Create | left form / right rule summary | stacked | wizard-like sections; sticky Save; Protocol checklist |
| Method Overview | Sessions table + Analytics + rules | stacked | Sessions list first; analytics tabs |
| Dataset Catalog | searchable matrix with coverage/status | cards | searchable list; eligibility badges + source drilldown |
| Session Setup | Method pin, symbol, time, profile | step panel | explicit staged selection, no hidden defaults |
| Replay | center chart; top controls; order right; Objects/indicators side; terminal bottom | chart with collapsible right and bottom panels | chart primary; one-row replay; bottom navigation; order in sheet; fullscreen landscape chart |
| Order Ticket | anchored side panel or dialog, chart geometry in sync | overlay panel | full-height bottom sheet with Price/RR/Risk keyboard; Review separate step |
| Journal/History | filterable accessible table, chart/trade link | table/card hybrid | chronological cards, expandable evidence |
| Session Analytics | 2–4 KPI grid + curves + table/filters | two-column | KPI carousel/grid + stacked graphs, drilldown |
| Method Analytics | instrument comparison, Session source filters | stacked | instrument selector + cards, disclosure |
| Account, Billing, Trash | settings panels / status | stacked | single-column, destructive confirmation |

**Do not conflate Free subscription vs Free Style Method.** Show source coverage and quote uncertainty beside chart and reviews. Official available catalog states: AVAILABLE, PARTIAL, QA_BLOCKED, RIGHTS_BLOCKED, PLANNED.

## Desktop workspace detail

Primary chart 60–75% available width depending user-resized side panel; compact top bar with active Method, Session, symbol/feed/version, timeframe and source-quality pill. Left/side: Drawing tools (eight preserved types), Indicators, Objects; main chart retains Lightweight Charts 5 integration; right Order Planner uses synchronized Entry/SL/TP geometry and server-readable draft preview; bottom six-dot collapsible terminal tabs **Orders, Positions, History, Journal, Analytics** with known implemented/available tab inventory not imaginary placeholders. Browser must preserve focus, resize, popup arbitration and TIME/PRICE anchor fidelity when changing timeframe.

Replay toolbar: Play/Pause, Step, speed only if already supported, Jump to Next Event fixed 72h UTC; disabled during unresolved write/queued job. Keyboard Space and Shift+ArrowRight ignored when typing or modal open. No Jump duration selector or OCO toggle.

## Mobile trading UX detail

- Bottom navigation: **Methods, Sessions, Replay, Analysis, Account**; Dataset Catalog accessible from Session Setup and menu. Sticky replay header displays symbol/time/source; no duplicate nested scroll traps.
- Chart fullscreen is allowed on portrait/landscape, with floating touch-safe toolbar; the visible chart must never overlap numeric inputs or OS safe area. Pan/zoom pinch and drawing drag have mutually exclusive interaction modes; explicit `Select`, `Draw`, `Trade Plan` tools and clear Exit mode. Tap-to-place anchors with numeric precision fallback; no hover-only SL/TP.
- Buy/Sell buttons **open a ticket only**. Order sheet exposes side, type, precise Entry/SL/TP, lot/risk, costs, Method restrictions, and mandatory Review; **Confirm in a separate explicit confirmation step**. Keyboard opening shrinks/scrolls sheet, never overwrites price with implicit round; cancel never submits. Payment-upgrade sheet cannot obscure unresolved financial confirmation.
- Large pending order card has status and a deliberate Cancel pending action; show position state, exact fill side, uncertainty, source version and undo prohibition. The app explains that rewinding past a committed trade requires Session fork.
- Chart can show only revealed candles; Session may resume after network loss. When status is `COMMIT_PENDING`, disable duplicate submission, poll the server-scoped job/command, then show committed or reconciled refusal. No optimistic fake fill.

## Component library & visual states to design before code

Foundation: tokens, typography, numeric/price fields, date+timezone selector, icon scale, spacing/grid, elevation, focus, text/error style. Controls: Button, Field, FormLabel, Select, Search, EmptyState, Warning, Modal, Drawer/BottomSheet, Tabs, Toast/InlineError, LoadingSkeleton, SourceStatus, ConfirmReview, QuoteBadge, OrderPreview, LedgerRow, TradeStatus, DatasetCoverageCard, SessionCard, ChartToolbar, DrawingToolbar, InstrumentFilter, ChartEvidencePopover. Each must specify disabled/loading/pending/error/stale/refused/unresolved/success/partial states and keyboard/touch behaviors. No inert decorative "trade" action.

## UX acceptance requirements

- Screens at **320, 375, 390, 768, 1024, 1440** CSS px and Android/iOS portrait/landscape; no unintended overflow, clipped modal, bad focus or hidden submit. 44px targets and explicit drag/tap scenarios; test drawing touch hit targets with a real browser/device where possible.
- Source/Session navigation, opening old deep link, refresh/back/forward/logout and account switch preserve or clear the right state without cross-user carryover. Google and email cannot accidentally create two same-owner accounts; explicit secure linking flow must work before shipping.
- Desktop full chart/order/replay/terminal; mobile touch planned+quick (subject to Method), safe keyboard, pending, single-button 72h Jump, Session/Method charts; PWA install, update, offline information shell but no offline financial trade, background resume, service worker cache version/clear on logout.
- WCAG 2.2 AA target, reduced motion, screen-reader labels, live authoritative result notice; verify no fake gain/quote/win statistics. Chart inaccessible visual information has tabular/text alternatives. Show USD/account currency and quote side.
- Performance: avoid rendering entire tick streams in browser; window/paginate trades, virtualize long lists, bounded candle tiles, lazy-load heavy analytics. No heavy remote fonts or duplicate chart engines.
- Validate on mocked exact OpenAPI contract and actual backend integration. Regression, type/schema checks, production build, repository/bundle/security tests, visual responsive snapshots, keyboard/touch/browser smoke and full Method→trade→resume journey before claiming complete.

## Ownership and handoff

Claude pushes `frontend/` code + UI-specific tests and artifacts to `claude/ui-v1-...` branch. Codex pushes backend/API schema and canonical fixtures to `codex/backend-v1-...` branch. Cross-boundary changes require coordinated PR and canonical contract review. Neither may merge the other's branch or change frozen finance/Market Data/Method/Session product rules silently. Every Claude UI PR lists exact backend DTO version, endpoints consumed, 320/375/768/1440 browser evidence, A11y checklist, mobile/desktop/PWA checks and no backend or source-data mutation.
