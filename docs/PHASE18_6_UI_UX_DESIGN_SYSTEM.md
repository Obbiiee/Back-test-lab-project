# Phase 18.6 — UI/UX audit and design-system specification

Date: 2026-10-04. Starting checkpoint `8e8d840b7bba79fd474f72d2069adc4b138e2232`, local/origin/actual GitHub main equal, 0/0. One owner-approved local typo in the 18.5 report was restored to HEAD; content hashes match and baseline is clean. This is the single focused Phase 18.6 UI audit/design specification, subordinate to existing [roadmap](ROADMAP.md), [workflow](../AI_CONTEXT/06_WORKFLOW_RULES.md) and [Method/Session authority](TRADING_METHOD_SESSION_SPEC.md). It does not authorize 18.7–19 or change v1 acceptance.

## Audit method and scope

Actual existing preview at 5197 was inspected without mutating its trading data. An isolated development origin 5198 was used for reproducible UI inspection, pointer/keyboard and responsive checks; production-build verification uses a separate QA origin. Source owners: FigmaWorkspace.jsx, FigmaWorkspace.css/FxWorkspace.css, PositionsPanel, OrderTicket, Journal, NewsPanel, IndicatorControls, WorkspaceModal/usePopupFocus and usePanelResize. [Phase 18.5 architecture audit](PHASE18_5_ARCHITECTURE_REFERENCE_AUDIT.md) boundaries are retained; [Phase 15](PHASE15_FIGMA_UI.md) describes historical UI, not current minimum height. The owner's typography, chooser and terminal complaints are requirements; no attached screenshot image was available in this request, so browser captures are the reproducible visual evidence.

## Current UI inventory

| Surface | Observed current implementation/state | Owner and direction |
| --- | --- | --- |
| Global/header | Symbol, interval, indicators, New Layout, two Risk/Reward history buttons, export/fullscreen; several disabled placeholders; brand/layout text | FigmaWorkspace; separate global product entry from chart tools in future IA; do not implement absent routes |
| Chart header/timeframes | XAUUSD, timeframe, OHLC and unavailable Volume; interval chooser and separate replay-timeframe shortcut | Single existing timeframe state; use consistent number formatting; never imply future data |
| Indicators | Modal catalog of seven types, empty state, add/edit/Apply/visibility/removal | IndicatorControls; keep IndicatorEngine/pane lifecycle; runtime-only configuration clearly disclosed |
| Left toolbar | Cursor, drawing and Risk/Reward groups; magnet/lock/hide/delete/keep apply to legacy Risk/Reward; chooser expander is narrow and hover-dependent | FigmaWorkspace presentation; improve scope labels, keep domain ownership |
| Tool chooser/favorites | Lines/Shapes/Research + separate Long/Short; repeated category icon for every row before correction; help/star actions | Existing toolGroups/TOOL_MODES; same dispatch and favorites storage retained |
| Chart | Official dark chart/native scales, pan/zoom/crosshair, drawings, positions and news primitives | CandleChart and domain adapters; primary spatial resource, no redesign of geometry |
| Right toolbar | Order, Object tree, Journal, News, account info | Chart/context actions, not global navigation; Object tree currently Risk/Reward only |
| Order | Centered nonmodal popup; side/type/size/entry/exits/tags/strategy/risk preview, explicit submit/discard; chart price picking must remain available | OrderTicket; no new Quick/Planned or Protocol workflow in this phase |
| Object Tree | Empty explanation explicitly excludes canonical chart drawings; legacy list supports select/edit/hide/lock/delete | Existing compatibility bridge; future unified presentation must preserve distinct stores/histories |
| Journal | Trades/Calendar/search, empty or canonical exit-record detail/notes | Journal/useTrading; present evidence, not a new account store |
| News | Import, previous recovery, Strict/Retrospective, availability/coverage, windows/filters/navigation; no-dataset state | News domain; research context must not imply known absence outside coverage |
| Terminal | Open/Pending/Closed/Analysis tabs, scrollable rows, pagination, six-dot divider | PositionsPanel; true collapsed state now hides all content except grip |
| Analysis | Account-derived realized metrics, reconciliation, balance curve, exports, partial/completed distinction | BacktestAnalysis; maintain labels, do not rename realized balance as floating equity |
| Bottom controls | Buy/Sell/quantity, replay/date/speed/step/timeframe/Go to, balance and terminal visibility | Existing callbacks unchanged; visual groups need distinct ownership |
| Dialogs/menus/settings | Date/edit/indicator modal focus loop; Order/News nonmodal Escape/return; Risk/Reward properties and chart export; no general account Settings page | WorkspaceModal/usePopupFocus; avoid nested dialogs without composition contract |
| Empty/loading | Chart lazy loading seen on cold open; empty rows/Analysis/Journal/Object Tree/News all inspected | Distinguish no data from unavailable capability; no fictitious onboarding |
| Error/warning | Existing role-alert ticket errors, persistence warnings and render recovery; malformed-storage QA needed for fresh browser evidence | Existing Phase 16 owners; token presentation must not suppress message/data protection |
| Focus/narrow | Focus rings, modal Shift-Tab wrap and Escape return observed; narrow rails retain Order/News/Indicators/account; terminal table/tabs scroll | Desktop research product; no mobile feature parity claim |

## Reproducible problem register

| ID / priority | Reproduction and evidence | Resolution / boundary |
| --- | --- | --- |
| U1 HIGH | Default → focus divider → Home or drag down: old value stops at 95; tabs/table/pagination consume chart space | Implemented UI-only collapse to 24 with content hidden, focusable grip; restore using drag/ArrowUp/Enter/Space/End |
| U2 HIGH | Open chooser; Risk/Reward Long and Short share ruler/category icon, all drawing rows share active group icon | Implemented per-tool existing SVG vocabulary, larger help/favorite controls, planning heading/hint, differentiated selection/favorite styling |
| U3 MEDIUM | Computed/source fonts: 12px overall but 7–11px labels/calendar/table with normal line-height; glyphs mixed with SVG/emoji | Coherent scale below; bounded chooser/terminal adoption now, remaining surfaces specified for incremental adoption |
| U4 MEDIUM | Left magnet/lock/eye history buttons appear general while canonical drawing controls are separate | Scope-specific tooltips/labels and conceptual group separation required; no store/history merge now |
| U5 MEDIUM | Open Object tree: only Risk/Reward records present, eight canonical types absent | Specification must identify scope; comprehensive object management is future integration, not a fake capability |
| U6 MEDIUM | At 390/320 widths replay/trading/table/pagination compete; tab labels overflow available chart width | Keep two explicit bottom rows and local scrolling; pagination now stays on one line in its own scroll area; no global overflow |
| U7 MEDIUM | Dialog-local focus traps have no central stacking/inert owner; Order must permit chart picking | Modal/nonmodal rules below; no nested-modal framework or workflow rewrite |
| U8 LOW | No imported news/replay anchor shows epoch-based window with Unavailable label; dense explanatory copy | Later copy/presentation refinement must say no anchor/data, without altering strict availability or coverage calculations |
| U9 LOW | New Layout is chart command, not a cloud layout manager; disabled header placeholders dominate scarce space | Scope-specific wording/inventory; do not invent global routes or change command semantics now |
| U11 MEDIUM | QA legacy Closed Positions row with missing commission renders $NaN, while Analysis flags incomplete identity/size | Specify unavailable marker instead of numeric-looking NaN; defer scoped presentation correction, do not invent commission or repair historical financial evidence |
| U10 MEDIUM | Small 12px-wide expander/Unicode controls; native title alone has limited focus/touch discoverability | Future target/tooltip normalization; chooser help/star and divider improved now; no full accessibility certification |

## Visual identity and information architecture

Backtest Lab: professional research laboratory, quantitative analysis and trading workstation. Use deliberate density, clear hierarchy, restrained geometry and functional color. No casino/neon/glass effects, decorative gradients or proprietary assets. Dark chart stays dark; structural workspace uses medium blue-gray neutrals; deep research can use lighter neutral data surfaces. Light surface tokens are defined, not newly implemented pages.

Proposed sitemap (specification only):

```text
Public: Home → Product/Features → Pricing → Login/Register/Recovery
Application:
  Dashboard → New Backtest / Previous Sessions
    First Method creation when no Method exists → Session creation
    Previous Session → Session Overview → Continue → Backtest Workspace
  Backtest Workspace (primary chart + contextual panels + terminal)
  Research (deep cross-session evidence; advanced labs only when available)
  Strategies (Method management when implemented)
  Reports (durable outputs when implemented)
  Account/avatar → Profile / Settings / Subscription-Billing
Deferred: Team / Community / AI Research Assistant
```

No new routes, auth, billing or Method/Session runtime are implemented. Dashboard remains a lightweight launcher; Overview inspects evidence; Workspace continues research. Provisional labels are not implementation authorization. Session inherits Method; Protocol execution rules come only from the Method authority, not this visual spec.

| Presentation | Content | Canonical owner / responsive behavior |
| --- | --- | --- |
| Page | Dashboard, Session Overview, Research, Strategies, Reports, account/public collections | Future shared domain identity; wide modest product navigation, compact labeled menu; narrow single navigation drawer when implemented |
| Workspace panel/tab | Object Tree, indicators/drawings, current orders/positions, compact Journal, News, Analysis, Protocol summary | Existing domain owner; one visible contextual panel preferred on narrow; no duplicate state |
| Popover/menu | Timeframe, tool chooser, presets, concise context/help | Existing chart/selection state; anchored and viewport-constrained, Escape and opener return |
| Nonmodal popup | Current Order, News, chart-linked planning controls | Keep chart accessible; no background inert/trapping; meaningful label and close |
| Modal | Short confirmation, replay date, parameter editing and guarded destructive decisions | Focus entry/Tab containment/Escape/return; do not silently stack |
| Global status | Account/data provenance/storage/replay state | Compact status readout; full details on demand; never duplicate financial calculations |

## Typography, spacing, sizing and surfaces

Executable token foundation is [designTokens.css](../frontend/src/workspace/designTokens.css). These tokens own new presentation corrections; old rules are not blindly replaced. Inter remains the existing family, with explicit system fallbacks; no additional font dependency. Use quantitative tabular lining numerals in aligned values; monospace is optional for provenance/time/code, not every label. Use sentence case for actions, concise section labels, stable decimal precision according to existing formatters.

| Role | Size / weight / line-height | Application |
| --- | --- | --- |
| Metadata | 11 / 400–500 / 1.45 | Secondary chart/feed/status, never critical buttons |
| Dense UI/data | 12 / 400–500 / 1.45 | Tables, tabs, chooser items, compact inputs |
| Body/form | 13 / 400 / 1.45–1.5 | Descriptions, field values and forms |
| Section title | 16 / 600 / 1.3 | Panel/modal headings |
| Page/result title | 22 / 600 / 1.25 | Future Overview/Research title; not workspace clutter |

Keep weights 400/500/600. Avoid tiny 7–9px meaningful data or arbitrary letter spacing; .04em reserved for compact category labels. Column headings 500, values 400; right-align comparable numeric columns in later presentation normalization without changing data ordering. Existing financial precision/units remain authoritative.

Spacing rhythm 4/8/12/16/24; compact related actions 4, row/internal spacing 8, panel padding 12–16, section separation 24. Desktop standard controls 32 high, comfortable/narrow actions 40; table row target 32–36 with horizontal scroll instead of dropping fields. Icon buttons standard 32 hit area with 18 glyph, 24-unit SVG viewbox and consistent 1.6 stroke; 20 glyph only for primary rails. Aim minimum 24×24 for actionable targets, prefer 40 on touch; resizing is 24 high and full width. Rails keep existing 52/49 desktop and 44 narrow; no new permanent nav column.

| Token role | Value | Purpose |
| --- | --- | --- |
| Chart | #08090b | Price/analytical canvas; existing engine surface unchanged |
| Workspace | #151b24 | Terminal structural surface |
| Secondary | #202936 | Chooser/context surface |
| Elevated | #293445 | Hover/menu layer |
| Research light / ink | #f1f4f8 / #243145 | Future deep reading/data context, not a forced light chart |
| Primary / secondary text | #e9eef5 / #bac5d5 | Readable hierarchy |
| Accent / selected | #8ab8ff / #304967 | Focus and current selection, not P&L branding |
| Success / warning / error | #68d6bd / #f0c674 / #ff9aa5 | Status plus text/icon; existing trading semantics/colors unchanged |
| Border / radius | #435268 / 4px | Restrained structure; essential focus uses accent, not subtle separator alone |

One menu shadow for transient elevation; chart/terminal use structural borders. No rounded-card grid redesign. Text pairs require ≥4.5:1 for normal text; larger eligible text ≥3:1. Essential focus/nontext affordances need distinct contrast. [W3C contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) and [target guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) inform targets; these documents are not certification. Check actual rendered inherited colors, not token names alone.

## Icon, component and state system

Reuse repository SVG Icon vocabulary for bounded chooser fixes; no installed icon-library dependency justified. Long/Short planning symbols have direction; line axes/rectangle/arrow/text/Fibonacci/measure get corresponding glyphs. Native/Unicode star remains a favorite affordance with explicit accessible name; unify remaining glyph/emoji controls only in a later scoped presentation task. Tooltips: descriptive action and scope, appear on hover/focus, no dependency on tooltip alone; locked/disabled reason discoverable through adjacent explanation where needed.

| Primitive | Already present | Specification / missing normalization |
| --- | --- | --- |
| Button/IconButton | Native buttons and Icon | Shared 32/40 sizing, accessible name, selected/disabled/focus |
| Input/Select | Existing ticket/settings/filter forms | Stable labels and units, token borders, validation message association; no risk-engine changes |
| Tabs/Table | Terminal/Journal/Analysis | Named selection, local scroll, consistent numbers; semantic tab keyboard behavior needs a focused future review |
| Menu/ToolPicker | toolGroups + existing toolbar/chooser | Registry-backed available catalog, distinct main/help/star actions, Escape return; future roving keys/search only if authorized |
| Tooltip/Popover | Native title, interval/Go to | Focus-discoverable explanation, anchored bounds, no accidental execution |
| Modal/Panel | WorkspaceModal and Order/News/Journal | Explicit modality; use existing lifecycle, central stacking policy before nested portals |
| Divider/ResizeHandle | usePanelResize/PositionsPanel | Three states and keyboard/drag lifecycle implemented |
| EmptyState/Badge/Status | Domain-specific messages | Concise status + optional next action; don't suggest unavailable features |
| ToolbarGroup | Existing header/rails/bottom | Group by chart/replay/trading/context ownership; no second command owner |

States: NORMAL readable surface; HOVER elevated neutral; ACTIVE transient press; SELECTED persistent tint + aria-pressed/current; FOCUSED 2px accent outline; DISABLED native semantics plus reason, no click; LOCKED icon/text distinct from selected; WARNING/ERROR status with message and recovery; SUCCESS meaningful acknowledgment; PROTOCOL-RESTRICTED future locked/reason indicator backed by domain refusal, not merely CSS. Never let TRACK_VIOLATION styling override prohibited execution. Do not simulate future enforcement in v1.

## Tool chooser specification

Keep canonical eight drawings separate from planning tools and cursor presentation. Intended categories: Cursor; Lines; Geometry; Annotations; Fibonacci; Measurement; Position Planning. Current implemented Lines/Shapes/Research groups remain recognized; richer grouping is specified without exposing unsupported tools. No Ray/additional tool promised by UI. Row order must be stable, names match registry, correct per-tool glyph, help and favorite distinct; active tool styling applies only to main row action, star state must not mimic selected tool. Show favorite placement consistently without merging Risk/Reward and drawing undo domains. Contextual help explains supported anchor/interaction, not proprietary shortcuts.

Risk/Reward chooser now says Position Planning with a review-in-Order hint. Long/Short are previews; selecting or drawing never auto-submits. The order workflow redesign belongs to 18.7/18.8. Keyboard Tab reaches existing controls; Escape closes and restores opener. Full arrow-key submenu navigation and catalog search are deferred, not falsely implemented. Future chooser adapters consume existing registry/dispatch rather than rewriting DrawingManager/models.

## Terminal/resizer and lower workspace contract

State: COLLAPSED = 24px grip only; COMPACT = 144px content with scrolling; EXPANDED >144 bounded by viewport. Drag below midpoint 84 snaps collapsed, above snaps at least compact. Chart reclaims terminal height through its existing ResizeObserver. At desktop 1280×720, observed collapsed terminal 24/chart 600; max terminal 392/chart 232. Content hidden remains mounted, so UI tab/page state and canonical account persist. No height storage added: existing preferences architecture has no terminal preference owner, so runtime-only height avoids a silent schema change.

Pointer left-button drag cleans move/up/cancel/blur listeners; no click toggling, so accidental click does not collapse. Keyboard ArrowUp/Down changes 10px, Shift 50px; ArrowUp from collapsed restores compact, ArrowDown from compact collapses, Home collapses, End maximizes, Enter/Space toggles and restores prior usable height. Grip retains focus and aria min/max/current plus state text; pointer drag focuses grip. Existing hide/show button restores usable content height from either fully hidden or collapsed state, with aria-expanded/label reflecting content visibility. The [W3C splitter pattern](https://www.w3.org/WAI/ARIA/apg/patterns/windowsplitter/) informs focus/keyboard semantics; a full assistive-tech conformance audit is not claimed.

Bottom hierarchy: chart range/log/auto stays chart-adjacent; trading side/quantity/Order stays in trading group; date/speed/play/step/timeframe belongs to replay group; account/status on trailing edge; terminal tabs/table/pagination belong inside terminal. Collapse never hides Buy/Sell, replay or account. Chart tools do not become global navigation. Keep separate historical range shortcut vs replay date explicit to avoid accidental reset assumptions.

## Responsive and focus rules

Wide ≥1051: current rails/header/terminal, chart dominant; optional metadata stays compact. Compact 721–1050: remove optional placeholders/long layout label before primary controls; keep context actions, local table scrolling. Narrow ≤720: existing 44px rails and two-row 88px bottom group; primary Order/News/Indicators/account stay reachable; one context panel preferred; chart remains primary, no mobile parity claim. At 320/390 tables/pagination may scroll locally, never force document horizontal overflow. Very short windows may require full terminal collapse; don't invent a useful expanded table height below available chart budget.

Focus: labels for icon-only actions; explicit opener restoration; Tab order follows visible groups, hidden terminal content removed from accessibility tree; no selected-state inference solely by color. Escape cancels/closes most-local UI before global drawing keys; modal Tab contained, nonmodal Order/News must not trap/inert chart picking. Nested-modal manager and portal/inert policy are deferred to a specifically authorized implementation. Preserve warnings/error text and Escape cancellation; never move finance requests into generic UI primitives.

## Implementation boundaries and next phase

Implemented only UI: terminal state/bounds/restore plus hidden-content wrapper; scoped token stylesheet; per-tool chooser glyphs/planning hint/Escape return; terminal/chooser typography/surfaces and narrow pagination. No drawing geometry/history/storage, financial formulas/order lifecycle, replay/settlement, indicators, market data, news availability or account schema changes. No new dependencies, cloud/routes/auth/subscription/community, trading workflow/prototype/specification freeze.

Next separately authorized 18.7 should specify Method/Session/plan/request/evidence boundaries, instrument/risk units, explicit confirmation and refusal journeys using this visual foundation. Do not implement 18.7 now. Deferred: global page routes, complete token migration, full icon/tooltip library, all-drawing object tree, menu roving keys, modal composition framework, persistence migration and new trading workflows.

## Evidence and validation record

Disposable browser captures live under ignored frontend/tests/artifacts/ (phase18-6-before-chooser.png and phase18-6-collapsed.png initially; final production captures recorded after validation). They are supplementary, not canonical fixtures. Reproduce with default workspace → chooser or focus separator → Home/ArrowUp/End → drag both directions; inspect 1280×720, 390×844 and 320×700. Observed modal Shift-Tab wraps to Start replay, Escape returns; chooser Escape returns to expander; Order/News/Journal/Indicators/Object Tree and all terminal empty states inspected. Chart cold-loading state seen. Fresh full registered regression, lint, production build and distribution audit PASS. Phase18.6 tests cover four viewport bounds, collapsed/compact/expanded, Home/End/Arrow/Shift/Enter/Space and invalid-height fallback; token contrast tests PASS for chooser, terminal, selected and future light-text pairs. Production origin 5199 passed collapsed/restore preserving selected Analysis and its $12 legacy evidence; chart drawing placement/resize; Order/News access at 320×700; 700×720 expanded terminal 364/chart 220 with no document overflow; earlier 390×844 development inspection also had no overflow. Corrupt account/favorites bytes remained preserved through existing QA UI. Production console errors/warnings: none. Captures: phase18-6-built-chooser.png and phase18-6-built-narrow.png. No full accessibility/device certification claimed. Repo/bundle and documentation controls are refreshed after final context updates.

## Checkpoint change inventory

Final production recheck: Home collapsed to 24px; Show positions restored 150px and aria-expanded=true; Hide removed the terminal; Show restored visible content again. Fresh production console remained free of warnings/errors. User-facing capture: phase18-6-final-preview.png on isolated development origin 5198.

Existing files extended: AI_CONTEXT/01_PROJECT_STATE.md, 02_ARCHITECTURE.md, 03_PHASE_HISTORY.md, 04_CURRENT_PHASE.md, 07_TEST_COMMANDS.md; docs/ROADMAP.md and DOCUMENT_MAP.md; frontend/src/FigmaWorkspace.jsx, trading/PositionsPanel.jsx, workspace/usePanelResize.js; frontend/package.json (test command only), scripts/ai-bundle.config.json (reviewed context/source/test allowlist). New files: this focused specification, frontend/src/workspace/designTokens.css and frontend/tests/phase18-6.test.mjs. No files deleted; dependency sets/lock, datasets, protected engines/history/storage and historical evidence unchanged. Diff checks confirmed terminal financial projection and table action markup identical; only presentation wrapper/props changed.
