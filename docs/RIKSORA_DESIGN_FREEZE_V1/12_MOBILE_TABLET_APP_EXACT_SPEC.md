# 12 — Mobile Web, Tablet and Installable App: Exact Touch Workflows

**Authoritative UI target:** same product routes, same server canonical order/finance, same source/Method/Session truth as [desktop terminal](11_TRADINGVIEW_LIKE_DESKTOP_TERMINAL.md). **Never shrink the desktop ticket into an unusable 320px panel or place order just from a gesture.** Implement one React+Vite component/domain model with responsive layouts and proper pointer/touch behavior.

## 1. Form factor matrix and hard layout choices

| CSS viewport | Shell/navigation | Replay workspace | Order planner | Analytics | QA |
| --- | --- | --- | --- | --- | --- |
| 320–374 narrow phone portrait | compact header + bottom nav 5 icons/labels where readable | chart takes safe visible height; one floating toolbar; drawer for tools | **full-screen accessible sheet**, no chart overlap | stacked KPI+charts/card list | 320/360 |
| 375–599 normal phone portrait | compact context chip; bottom nav | chart dominant, tabs below chart; layer/indicator/tool bottom sheets | bottom sheet with 60–95% viewport height | 2 compact KPIs per row where fits | 375/390 |
| 600–1023 tablet portrait | left compact nav rail | chart + selectable right drawer, terminal accordion | side drawer or bottom sheet | cards/2 columns | 768 |
| >=1024 tablet landscape/laptop | desktop workspace shell | chart-left, order-right, terminal below | docked side panel | desktop | 1024/1440 |
| phone landscape (height-limited) | minimal safe-area header, hiding bottom nav while in fullscreen chart only | **full-width chart + floating controls**; exit full-screen visible | full-height overlay/order sheet | separate routed screen | iOS/Android portrait/landscape |

Use viewport `100dvh` and safe-area insets where supported; no toolbar under iOS home bar/notch; soft keyboard cannot cover action buttons. Document horizontal scrolling only within intentionally scrollable tables and chart, never page-wide accidental overflow. Do not use mobile WebView absolute window size as trusted transaction scope.

### Phone portrait workspace wireframe (390 CSS px example)

```text
┌─────────────────────────────────┐
│ ‹ Session   XAUUSD   ⋯   status │  header 44–56px + safe top
├─────────────────────────────────┤
│ [1m ▼] [Indicators] [Draw ✎] [⛶]│  chart commands
│                                 │
│     CHART CANDLES               │  >40% usable screen target
│     crosshair, prices           │
│     overlays/drawing objects    │
│                                 │
│ [BID price]       [ASK price]   │  informational (not fill)
├─────────────────────────────────┤
│ [◀ Step] [▶ Play] [Jump 72h]    │  one-row replay actions
│ Cursor UTC · Saved rev N         │
├─────────────────────────────────┤
│ [Sell] [Buy] [Order]             │  opens ticket, never submit
├─────────────────────────────────┤
│ [Orders] [Positions] [Journal]  │  horizontal *local* tab scroll
│ panel card / tiny summary       │
├─────────────────────────────────┤
│ Methods Sessions Replay Analysis│
│ Account                         │  bottom nav with safe bottom
└─────────────────────────────────┘
```

**At 320px:** toolbar compresses to icons with accessible names and visible popup labels; chart space not sacrificed to nonexistent pro panels; order flow opens dedicated full-screen sheet. For a long tab list, horizontal scroll inside tab strip with scroll buttons and focus, no document overflow.

### Mobile fullscreen landscape chart

```text
┌────────────────────────────────────────────────────────────────────┐
│ ‹ exit  [symbol]  [tf]  [Draw] [Indicators]   [source] [clock UTC] │
├────────────────────────────────────────────────────────────────────┤
│ [floating drawing rail]   CHART (pan/zoom/touch handles)            │
│                                                                    │
│                         Bid/Ask readout                             │
├────────────────────────────────────────────────────────────────────┤
│ [Play] [Step] [Jump72h] [Pending n] [Order sheet] [Objects]        │
└────────────────────────────────────────────────────────────────────┘
```

Fullscreen chart is a UI layout toggle, not an unauthorized Screen Orientation lock; mobile browser behavior may vary. **Exit fullscreen** always visible; iOS browser without Fullscreen API uses an in-app full-viewport layout. Order sheet pauses replay before review.

## 2. One finger, two fingers and interactions — exact gesture arbitration

| Context / gesture | Result | Must NOT happen |
| --- | --- | --- |
| Chart SELECT/PAN, one-finger drag | pan chart horizontally (or chart library's selected scroll direction) | alter candle chronology or order |
| Chart SELECT/PAN, two-finger pinch | zoom time/price within chart support | browser-wide accidental document zoom only if safe accessible alternative exists |
| SELECT single tap on candle | reveal crosshair tooltip (OHLC, UTC, current source status) | issue buy/sell |
| SELECT long-press candle | pin movable crosshair until release/exit, accessible table alternative | create implicit entry |
| **DRAW mode** tap | start anchor with temporary preview and visible Cancel/Done | pan chart and place drawing simultaneously |
| DRAW mode drag | adjust current handle only with >=44px hit zone; context-specific pointer capture | shift unrelated orders or scroll whole page |
| DRAW mode second tap / Done | commit drawing object to Session's drawing store; toast saved/pending | server financial write |
| DRAW mode two-finger pinch | temporarily suspend creation and zoom; restore draft safely or explicit cancel | create phantom anchor |
| Position PLAN mode tap/drag | choose Entry/SL/TP anchors, then open exact numeric planner | auto-submit trade |
| Tap existing drawing | select + show big touch handles + bottom edit toolbar | select an overlapping filled order as editable drawing |
| Tap chart price axis | display crosshair/price chooser or only show readout per supported library | silently change SL/TP |
| Tap overlay order marker | open status/details; a pending Cancel requires confirmation | close position immediately |
| Bottom sheet swipe down | close only when not in COMMIT_PENDING; confirmation screens require explicit action | change server financial state |
| OS back gesture while modal | close/back to safe previous form if no accepted write | send duplicate confirmation |
| OS back while pending write | show reconciliation status; preserve command id | imply canceled transaction |
| Switch Session while DRAW draft | prompt discard draft or save through authorized drawing store | carry drawings to another user/session |

**Mode indicator** prominently says `Pan`, `Crosshair`, `Draw: Trend Line`, `Plan: Long`, etc. Only one exclusive chart interaction mode active. E.g. a user drawing a rectangle uses first tap start, second tap opposite corner; a user dragging a fib uses two taps and sees level handles. Use `pointerdown/pointermove/pointerup/pointercancel` with id/pointerType; guard against additional pointers; avoid `touch-action: none` on whole document. The chart host may use touch-action scope to prevent browser scroll while actively drawing, but body remains scrollable outside chart. Prevent long-press text selection on chart **only** in explicit drawing mode, not on text/notes.

## 3. Mobile drawing and indicators UI

**Tap Draw** → bottom sheet with tabs `Cursor`, `Lines`, `Shapes`, `Fibonacci`, `Annotations`, `Measure`, `Position Plan`. Show current nine registered research tools and separate Long/Short; professional tools only when genuinely implemented. Search and recent/favorites allowed as local preference; no decorative disabled collection. Selecting tool → close sheet → mode badge on chart → user places anchors → selected edit sheet `Style`, `Coordinates`, `Lock`, `Hide`, `Duplicate`, `Delete`. All numeric time/price anchors editable through accessible text fields for fingers/small charts, with precise decimal strings in conversion layer.

**Tap Indicators** → sheet with searchable **seven actual** options; selecting one opens parameter sheet with input validation, **Add** → chart pane, **Edit** → gear in pane legend, **Hide** → eye, **Remove** → trash. When pane is too tall on phone, provide tabs `Price chart` and `Indicator panes`; never calculate over future bars, never silently omit a user's saved indicator config. Extra extended indicators appear only after implementation and tests; volume-derived indicators refuse when volume missing.

**Tap Objects** → drawer or full-screen screen with hierarchical lists `Drawings (n)`, `Indicators (n)`, `Position plans (n)`, `Orders (read-only)`. Selecting object returns chart and focuses its handles; hidden object can still show in list; locking prevents edit; trading Order rows are controlled by backend not drawing Undo.

## 4. Mobile order sheet — distinct from desktop

### Sheet state `EDIT_DRAFT`

Header `New Order: XAUUSD`, close, immutable Method name/type, side selector `BUY / SELL`. Show quote-side label `Buy at Ask / Sell at Bid` with current **last revealed** timestamp and source. Workflow choices: Free Style `Quick` and `Planned`; Protocol only `Planned` and pending Limit/Stop. For Planned: order type `Market (Free Style only)`, `Limit`, `Stop`; fields Entry/SL/TP, RR, risk basis/value, quantity, estimated loss/gain/commission; Free Style risk presets if current interface supports; Protocol shows read-only locked RR/risk and derived TP/lot; required checklist ON/OFF with observed states and why blocked.

Numeric keyboard `inputMode=decimal`, no browser implicit float rounding, explicit units and input precision/validation. Tapping **Pick from chart** collapses sheet to minimal sticky mini-ticket, enters `PRICE_PICK` single-tap mode, selecting price returns to sheet with exact candidate and invalidates stale Review; cancel leaves prior value unchanged. Changing side or Method resets stale draft geometry only after explicit user acknowledgement when needed; never change entire Session source.

Primary sticky action at bottom **Review Order**, secondary **Discard Draft**; keyboard moves sticky actions above keyboard via safe-area/dynamic viewport and internal sheet scroll. Touch targets >=44x44.

### Sheet state `REVIEW_EXACT`

Dedicated review page, not tiny toast: show immutable Method, Session, order type, side, exact Entry/SL/TP, confirmed lot, estimated risk/return and fees, Bid/Ask evidence timestamp, execution uncertainty and data source. **Back to Edit** invalidates old review if values change. **Confirm Order** protected against double-tap; no optimistic fill. `PENDING` label means order accepted awaiting future eligible quote, not "trade profitable".

### Sheet state `COMMIT_PENDING / RECONCILE`

Spinner + text **Checking whether your order was recorded**; show read-only command/session revision. Disable second confirm and navigation that could generate new order; allow safe background/reopen reconciliation by command ID. `FAILED` result distinguishes server refusal vs network ambiguity; no blind retry. On accepted, toast "Order saved", jump to `Pending` or `Positions` based on actual backend status. For Protocol unauthorized Quick/Market, show real server refusal; not merely hidden button.

## 5. Replay on mobile and one-click Jump

`Play`, `Pause`, `Step`, `Jump Next Event · 72h`, UTC timestamp and source status always within one touch-accessible toolbar, or two rows on 320px with no hidden mutating action. Single Jump tap pauses play, queues bounded work; progress shows `searching eligible observed quotes` (never guessed % unless backend provides), can cancel queued job when permitted. On no event, show "72h elapsed, pending orders unchanged" and reveal eligible candle range; on event, open result card describing trigger/SL/TP; on EOF show last admitted timestamp. No date/window picker inside Jump. A separate **Go to time** action uses time dialog and visible restrictions on rewinding after committed trade.

Speed choices reflect actual server batching, not advertised playback accuracy. UI never continuously streams all ticks or reconstructs cash locally. On network interruption, pause local animation and inspect authoritative Session after reconnect.

## 6. Session, Journal, Analytics and quota on phone

- Methods hub: compact searchable cards, `Create Method` visible, last Session `Resume`; swipe on card never deletes.
- Method detail: top context → `Sessions | Analytics | Rules` accessible tabs; create Session uses staged wizard. Date calendar hides not-admitted intervals with explicit status; source detail follows from picker.
- Session Overview: current cursor UTC, Method and source/quality, summary counts, `Resume Replay` primary, `Journal`, `Analytics`, `Delete` under overflow + confirmation, no accidental swipe deletion.
- Journal: order/trade/observed skipped setup cards, filter chip, note editor with safe keyboard, annotated chart link only when data previously revealed; unsupported future AI result cannot appear as realized.
- Analytics: 2-column 390px tiles or 1-column 320px, horizontal equity curve with touch crosshair accessible via table, drawdown, trade list, scoped filters; "R unavailable" and reason shown without 0 substitutes. Method aggregated report shows per-instrument and sample-comparability warnings.
- Free quota: actual one monthly window per entitlement day, max 5 saved Sessions, 30d Trash, not inventing trades when window closes. Pro changes capacity only. Unsupported purchases not rendered as live checkout.

## 7. PWA and Capacitor Android/iOS wrappers

**PWA v1:** installable manifest and icon based on owned brand; secure HTTPS service worker caches versioned shell/public static assets and *only safe, non-sensitive* public data. Don't put bearer token, Session ledger, private candles, data source URL, command request, Google auth handoff or payment response in service-worker Cache Storage; private API requests use no-store/network-only. When offline: public/help shell may display cached, but replay and order buttons disabled with explanation, no local mutation queue. On app update, migrate UI preferences only; logged-in state rechecks account and server revision.

**Background/reopen:** store last safe navigation identity only according to privacy policy; app rehydrates latest Session from authenticated server, not local settled state; stop any client clock animation on suspend. A confirm pending during close must be reconciled by command ID, not re-fired on reopen.

**Native store packaging target:** Capacitor wraps same React built web assets. Deep links open validated same-origin route after verified login, no auth token in URL; system browser OAuth/PKCE and securely stored minimal credential under OS policy; back button/dialog navigation, status/nav bar safe-area, keyboard, file export/sheet share, no camera/location/notification permission by default. Native builds require separate Android/iOS signing, real device, store privacy, account/payment approval. No separate frontend business logic.

## 8. Device/orientation/input test matrix — obligatory

| ID | Device/viewport | Action path | PASS condition |
| --- | --- | --- | --- |
| MOB-01 | 320px phone portrait | first Method → Session → open replay | no horizontal page overflow, primary CTA reachable, no clipped keyboard |
| MOB-02 | 375px phone portrait | choose trend line, tap 2 anchors, edit both, undo/redo | exact source TIME+PRICE persisted; no chart pan conflict |
| MOB-03 | 390px phone portrait | Long Position 3 anchors → Planned ticket → review → confirm | no trade on drawing, numeric/chart sync, source review preserved |
| MOB-04 | 390px | Protocol checklist ON fail and OFF actual observations | server refusal correct, no Quick/Market manual bypass |
| MOB-05 | 768px tablet | tools/indicators/objects/order drawer overlap | only one blocking drawer, chart remains readable |
| MOB-06 | 1024px landscape tablet | docked right order, terminal resize, indicator pane | no overlaps, same Session state |
| MOB-07 | phone landscape | open fullscreen chart, pinch, exit, resume | safe-area, drawing handles, no pointer capture leaks |
| MOB-08 | Android Chrome PWA | install, foreground/background, offline/reconnect | offline writes refused, Session cursor rehydrated from server |
| MOB-09 | iOS Safari Add-to-Home-Screen | open deep link, keyboard quote input, update/relogin | no leaked token, no duplicate trade, status reachable |
| MOB-10 | any device | confirm with simulated network timeout, switch account, restore | reconciliation, tenant data cleared, exact ledger once |
| MOB-11 | phone | indicator add/edit, terminal/journal/analysis drilldown | chart source prefix preserved, accessible data table |
| MOB-12 | 320px with 200% text / reduced motion | navigate, open order sheet, review/confirm | labels and buttons remain accessible, no motion dependence |

**Implementation sequence:** shell navigation → Method/Session/catalog wizard → chart touch mode arbitration → drawing and indicators sheets → mobile order review/confirm → terminal/analytics → PWA install and native packaging. Claude commits UI/test only on own branch with actual device/browser evidence; no backend changes or invented API fields.
