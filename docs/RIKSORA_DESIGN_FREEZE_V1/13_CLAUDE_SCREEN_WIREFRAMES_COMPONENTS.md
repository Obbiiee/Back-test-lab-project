# 13 — Claude Screen Wireframes, Component Architecture, Microcopy, State Ownership

**Goal:** Claude can translate each route/screen into implementation without asking the founder where a button belongs. All screens correspond to [U01–U16](01_PRODUCT_UX_FLOWS.md), click behavior [10](10_FRONTEND_CLICK_BY_CLICK_JOURNEYS.md), desktop terminal [11](11_TRADINGVIEW_LIKE_DESKTOP_TERMINAL.md), and mobile/app [12](12_MOBILE_TABLET_APP_EXACT_SPEC.md).

**Boundary:** these are functional wireframes, not claim of pixel-approved final screenshots. Existing RIKSORA logo/colors apply; preserve the chart engine and server state. Actual backend DTOs must be generated from current OpenAPI rather than invented by Claude. Empty/blocked states must be real before displaying controls.

## 1. Desktop non-terminal screens — layout, entry, exit

### U01 Landing (public; 1440)

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ RIKSORA      How It Works     Features      Data Coverage      Help   Sign in│
├─────────────────────────────────────────────────────────────────────────────┤
│ H1: Don't Trust the Claim. Test It.         [Chart/Research concept preview]│
│ Method → Replay → Evidence                                               │
│ [Start researching]  [View available data]                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3 steps to test an idea                 Real data limitations explained     │
│ Research not guaranteed profitability   Pricing if verified, source status │
├─────────────────────────────────────────────────────────────────────────────┤
│ FAQ / Source limitations / Terms / Privacy / Contact / Copyright           │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Click rules:** primary CTA → Auth if anonymous; if authenticated Methods. Data Coverage → public version/quality summary (not fake 16x5). Feature cards link to anchored explanation, not unavailable fake demo. Marketing metrics cannot be invented. Mobile stacks hero text then CTA then visual; main CTA visible without horizontal scroll. Reuse existing `AlphaHome.jsx` and approved metallic-R asset.

### U02 Auth/login/verify

```text
[Brand] [Sign in to RIKSORA]
[Continue with Google]
──────── or ────────
[Email address________________]
[Password_____________________][show]
[Sign in]
[Forgot password]  [Create account]
[Verify email / linking conflict / network state]
```

Form submit loading, field and server error, enter-to-submit. Password reveal is local UI only. Google account conflict → explicit account-linking verification, never merge by email. Mobile safe keyboard and full-width controls. Existing `AlphaAccount.jsx` may be reused but no claim Google flow is fully deployed.

### U03 Methods Hub / Dashboard

```text
Header  Methods [active]   Sessions  Catalog    User
H1: My Trading Methods       [ + New Method ]
Search Method...    Filter: All | Free Style | Protocol   Sort: Recently used
[ Method Breakout | Protocol | 3 Sessions | Last 2024-05 | Open | Resume ]
[ Method Price Action | Free Style | 1 Session  | Open | Resume ]
Below: Last sessions (date/status)  |  Quality/status notices
```

**No Methods:** single large `Create Your First Method` card and simple explanation Free Style vs Protocol; never default-create a fake Method. **Card click title** → U05 Method Overview; **Resume** → U08 Session Overview; **New Method** → U04. Mobile single card list; at 320 choose search and actions below rather than cramped 3-column header. Server-paged results, no all-history requests. Existing `AlphaSessions.jsx` hub provides reusable visual/cards, but old "Strategy" labels become Method only when contract conversion is verified.

### U04 Create Method (Free Style / Protocol)

```text
‹ Methods                H1 New Trading Method        [Rules help]
[Name input] [Free Style card] [Protocol card]
[Description/Hypothesis textarea]
IF FREE STYLE: info Quick+Planned, order-specific RR/risk
IF PROTOCOL:
  [Locked RR ___] [Risk basis selector] [Locked risk value ___]
  [Checklist enforcement  ON / OFF]
  Condition 1 [rule text____] [remove]   [+ Add condition]
[Review Method Summary]  [Cancel]  [Save Method]
```

Method type set only at creation; switching type in unsaved draft must warn if it drops Protocol fields; after saving evidence-bearing Protocol locked. **Save** posts new Method once → U05. **Review summary** no financial/session mutation. Client checks required fields but server authority independently validates; invalid checklist ≥1 refusal is inline. Mobile vertical wizard with 2 sections `Basic` / `Rules`; back preserves draft but not unverified server write.

### U05 Method Overview and U13 Analytics

```text
‹ Methods   [Method name] [FREE_STYLE/PROTOCOL] [Rules/Source provenance]
[Sessions active] [Analytics] [Method Rules]
[ + New Session ]       [Archive Method...] 
Sessions table: Name | Symbol | Coverage | Cursor UTC | Pending/Open/Closed | Resume
Analytics tab: Scope: All eligible / Instrument / period | sample warnings
   [Completed N] [Win rate] [Expectancy R] [Profit factor]
   [Trade distributions] [By instrument bars] [Session comparison table]
   [Trade / Session evidence links]
Rules tab: Method type, locked rule hash, checklist / assumptions / history
```

**Click Session name** → U08; **Resume** → U09 only after Session overview rule where appropriate; **Instrument filter** refreshes metrics from server/verified ledger, not by averaging Session win rates; **Archive** protects evidence. Mobile tabs with horizontal local scroll, detail views stack.

### U06 Catalog / U07 New Session

```text
U06: [Search symbol __ ]  [All / Available / Partial / Blocked / Planned]
[AUDUSD | PLANNED / coverage N/A | View details]
[EURUSD | AVAILABLE only if evidence | version/feed/rights | Select]
[... exact 16 target symbols, none invented or reordered]
Click Detail → coverage UTC, Bid/Ask, source, quality, rights & profile

U07: H1 New Backtest Session
[Trading Method: Breakout   Readonly rules summary]
[Session name __]
[Symbol ▾] → Catalog chooser (only eligible allows Select)
[Source/version ▾ eligible pinned entries] [Data-quality details]
[Start period/date UTC eligible picker] [Initial USD balance __]
[Free remaining allowance/slots if relevant]
[Cancel] [Create Session]
```

Never show all 16 selectable just because registry exists. On symbol change, invalidate source+period and refresh qualified list. On create success → U08 Session Overview; no auto-filled trades/candles beyond source. Mobile step screens `Method → Symbol → Eligible period → Balance & confirm` with explicit Back/Next; use stable draft state and summary.

### U08 Session Overview / U11 Journal / U12 Session Analytics

```text
‹ Method > [Session name]       XAUUSD [source/quality] [saved rev 15]
[Resume Replay] [Analytics] [Journal]  [More: Fork/Trash]
[Current virtual time UTC] [Admitted period] [Free window if relevant]
[Pending n] [Open n] [Closed n] [Unresolved n] [Realized Net]
[Replay timeline by segment] [Last activity]
History preview [Trade rows / evidence] [Source limitations]

U11 Journal: [Filter Session/Method/type]  [Search note] [Add note]
[UTC | order event | fill? | authored note | dataset source] → Detail
[Mark setup / Skipped setup] only from revealed-time chart context.
Notes edit with version conflict; never edit trade fills.

U12 Analytics: [Session] [Instrument within Method] [Method]
[N trades] [N wins/loss] [Win rate] [Avg R if valid] [Profit factor] [MDD]
[Equity curve + accessible table] [Drawdown curve] [Trades table]
[Coverage warning] [Unresolved n] [Exclude reasons]
```

**Resume** fetches current server cursor, not local playback position. **Go to trade** opens exact evidence and chart context allowed by replay contract; if historical financial rewind forbidden, open read-only evidence viewport, not mutate Session. **Delete** goes to Trash after confirmation and 30-day policy. Mobile analysis uses stacked cards and touch tooltips/accessible tables, no combined independent portfolio equity.

### U14 Account/Billing/Trash and U15 Support

```text
Account: [Verified email / linked providers] [Account security] [Sign out all]
         [Workspace memberships] [Data privacy/export] [Subscription]
Billing: [Current plan] [Usage: active Sessions / Free daily segment]
         [Reset time with timezone] [Upgrade (only active checkout)]
Trash:   [Session cards, deleted date, expiry in 30d] [Restore] [Permanent delete: gated]
Support: [Help topics] [Data quality FAQs] [Report issue] [Service status]
```

Read-only account billing screens must present real backend state; if no production payment provider then show unavailable state rather than accepting fake credit cards. Account linking requires proof and explicit conflict flow. On phone every card is single-column, no nested horizontal form scroll.

## 2. Claude React component tree and ownership

```text
<AppShell>
  <AuthBoundary><VerifiedWorkspaceScope>
    <RouteOutlet>
      <PublicHome/>
      <AuthPage/> <MethodHub/> <MethodEditor/>
      <MethodOverview>
        <MethodSessions/> <MethodAnalytics/> <MethodRules/>
      </MethodOverview>
      <InstrumentCatalog/> <SessionWizard/> <SessionOverview/>
      <ReplayPage>
        <ResearchHeader/><DataQualityBadge/>
        <DesktopTerminalLayout | MobileReplayLayout>
          <ChartToolbar/><DrawingToolPicker/><CandleChart/>
          <IndicatorPicker/><ObjectsPanel/><PositionPlanner/>
          <ReplayControls/><OrderTicket/><OrderReview/>
          <TradingTerminalTabs/>
        </DesktopTerminalLayout>
      </ReplayPage>
      <JournalPage/><SessionAnalytics/><AccountSettings/><Billing/><Trash/><Support/>
    </RouteOutlet>
    <GlobalNotice/><CommandReconciliationBoundary/>
  </VerifiedWorkspaceScope></AuthBoundary>
</AppShell>
```

**Component principle:** responsive *compositions*, not duplicate business logic. One canonical `OrderTicket`, `OrderReview`, `PositionPlannerModel`, `CandleChart`, `IndicatorPicker`, `SessionDataClient` are shared. Only layout wrapper/panel placement differs desktop/tablet/mobile. Do not fork numeric risk/settlement logic by device.

### Specific existing source files to reuse, avoid rewriting

| Existing implementation | Reuse/extend for |
| --- | --- |
| `frontend/src/main.jsx`, `tickAlpha/TickAlphaEntry.jsx` | safe router/deep-link compatibility; no default route break |
| `tickAlpha/AlphaHome.jsx`, `AlphaBrand.jsx` | public home, approved logo, hero and brand |
| `tickAlpha/AlphaAccount.jsx`, `accountClient.js` | auth, workspace scoped client, identity |
| `tickAlpha/AlphaSessions.jsx` | Methods/Sessions hub card patterns |
| `tickAlpha/TickAlpha.jsx` | existing review/confirm hooks and Session lifecycle; extract responsibly |
| `tickAlpha/AlphaWorkspace.jsx` | chart header, indicator/drawing picker, replay controls |
| `components/CandleChart.jsx` | official Lightweight Charts, price/time anchor and drawing lifecycle |
| `drawings/DrawingTypes.js`, `DrawingRegistry.js` | actual nine drawing types; no invented custom renderer |
| `indicators/productionRegistry.js` | actual seven registered indicators |
| `tickAlpha/AlphaTerminal.jsx`, `AlphaJournal.jsx`, `AlphaEquityChart.jsx` | orders/positions/history/journal and valid analysis |
| `tickAlpha/AlphaOrderPresentation.jsx`, `AlphaTicketEstimate.jsx` | exact ticket presentation/review evidence |
| `workspace/WorkspaceModal.jsx`, `usePopupFocus.js`, `usePanelResize.js` | accessible dialogs/focus and six-dot terminal resize |
| `tickAlpha/riksoraBrand.css`, `workspace/designTokens.css` | approved tokens, contrast, reduced motion |

**Do not introduce** new chart engine, form framework, global state framework, Next.js, server financial calculations or live price provider merely for layout. Add small route/view components scoped to `frontend/src/` with tests. If backend API missing, render truthful blocked state or use a canonical version-pinned mock only in QA/demo, NEVER in production.

## 3. Frontend data/state taxonomy

| Store/state | Owner | Persistence | Rules |
| --- | --- | --- | --- |
| Verified actor/workspace/token | auth boundary | token in secure ephemeral client as supported | wipe private caches/logout, stale response ignored |
| Method/Session/dataset/profile pins | backend DTO | PostgreSQL source of truth | no mutable browser override |
| Orders/fills/cash/ledger/cursor | backend | authoritative DB, command receipt/revision | UI read-only projection; no simulated fill |
| Draft planned order geometry | frontend form + chart draft | ephemeral until reviewed | safe to cancel, invalidates review on edits |
| Selected drawing/active tool/pan | chart UI | local ephemeral | does not mutate finance |
| Saved drawings/indicator preferences | scoped workspace/Session store when available | versioned, cross-device only when server-backed | local storage is not canonical research truth |
| UI panel widths/open state/timeframe | frontend preferences | local bounded preference cache | no effect on replay cursor or accounting |
| Active async job/command ID | backend receipt + bounded client | reconcile on reconnect | timeout != failure; no duplicate submit |
| Derived stat tiles/candles | server projection / bounded viewport cache | recomputable | no future leak or fake denominators |

### Error loading/resilience exact behavior

- `AUTH_REQUIRED`: redirect auth; preserve only public route, not private data payload.
- `CATALOG_PARTIAL`: available items selectable, blocked items reveal limitation, no fake feed.
- `SESSION_LOADING`: skeleton, no enabled trading controls.
- `COMMIT_PENDING`: disable double-submit; inspect command+job; show status notice with ID short and exact timestamp if known.
- `SESSION_STALE`: fetch authoritative Session and invalidate old review; re-enter user consent.
- `UNRESOLVED_EXECUTION`: show cause and evidence link; disable affected finance until allowed fork.
- `SERVER_UNAVAILABLE`: readable saved state last seen clearly labeled stale; **no active order controls**.
- `SOURCE_RIGHTS_BLOCKED`: no chart/trade of prohibited dataset; show plain explanation and legal source status.

## 4. Responsive component tokens and usability

Same brand tokens as [04 responsive app](04_FRONTEND_RESPONSIVE_APP.md); 320/375/390/768/1024/1440 breakpoints; minimum 44px touch target on mobile, desktop terminal controls 32px if accessible keyboard. At phone font >=14px meaningful, 12px labels where validated; avoid eliding prices without detail. For mobile numeric keyboard use `inputMode=decimal` and explicit currency. Source/version tags collapse to accessible icon/text popover, never hidden entirely. Use semantic field labels, aria-describedby for errors, portal modal stacking, focus return, no keyboard trap on unmounted modal, reduced-motion and table fallback for charts.

## 5. Visual acceptance screenshots (not supplied, generated by Claude after implementation)

Capture full screen + focused screenshots for U01–U14 at 1440, 1024, 768, 390 and 320; mobile landscape fullscreen U09; selected chart drawings; Protocol blocked checklist; review and committed order; pending/closed trades; Journal/Analytics with real QA fixture; offline PWA; account quota/Trash. Attach screenshots and interaction trace, source IDs and backend contract SHA to Claude PR. A screenshot alone is NOT order, canonical, mobile device, accessibility or storage certification.
