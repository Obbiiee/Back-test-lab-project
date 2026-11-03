# 11 — Desktop Trading Terminal: TradingView-like Functional Specification for Claude

**Design target:** professional chart-centric research workflow **inspired by familiar trading terminals**, not a pixel/brand clone of TradingView, FX Replay or third-party proprietary UI. Use existing React+Vite/Lightweight Charts, native RIKSORA design tokens, drawing registry/indicators/order semantics. **Claude owns UI implementation, not financial/dataset truth.** Every visible control must be functional, documented as coming in a later milestone, or absent—never an enabled fake button.

## 0. Audited existing code reality (2026-11-04 GitHub main)

Current drawing registry `frontend/src/drawings/DrawingTypes.js` has **nine** registered research drawing types: `trend-line`, `horizontal-line`, `vertical-line`, `rectangle`, `ray`, `fibonacci-retracement`, `arrow`, `text`, `measure`. AlphaWorkspace also exposes two planning objects `long-position`, `short-position` that are **not generic research drawings**.

Current `frontend/src/indicators/productionRegistry.js` plus overlay registry register **seven** indicators: SMA, EMA, Bollinger Bands, RSI, MACD, ATR, Stochastic. Current `frontend/src/tickAlpha/display.js` chart timeframes = `1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, D` (**nine**). Present AlphaWorkspace implements drawing group chooser, local indicator preferences, grid/fit, historical previous-month display, replay controls and chart owner; AlphaTerminal implements Open positions, Pending orders, Closed trades, Journal and Analysis panels. Current XAUUSD historical source is special; missing market volume must display "Volume unavailable", not invented bars.

Professional drawing engine target is [Drawing Engine Spec](../DRAWING_ENGINE_SPEC.md); indicator extension target is [Indicator Engine Spec](../INDICATOR_ENGINE_SPEC.md). Those are *future architecture targets*, not all implemented. All extensions require deterministic drawing/indicator tests. Preserve current chart source/time+price anchor and legacy user data compatibility.

## 1. Desktop spatial layout — concrete wireframes

### Wide desktop >=1440 CSS px, full research mode

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ RIKSORA  Methods > Method > Session [XAUUSD/EXNESS][version][quality]     Help       Avatar│ H=48
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ [Symbol+Source] [1m 3m 5m 15m 30m 1h 2h 4h D] [Indicators] [Chart] [Fit] [Snapshot*]       │ H=44
├──┬──────────────────────────────────────────────────────────────────────────────┬───────────┤
│  │  OHLC (revealed only)  Bid / Ask labels   Cursor UTC                           │  ORDER   │
│  │                                                                              │  Free/   │
│  │                                                                              │ Protocol │
│  │  MAIN LIGHTWEIGHT CHART / overlay indicators / drawing canvas                 │ Ticket   │
│  │  (dominant width, price axis at right, timeline bottom)                      │ Summary  │
│  │                                                                              │ Orders   │
│  │  selected object handles and temporary floating editing toolbar              │ Objects  │
│  │                                                                              │ Source   │
│  │                                                                              │          │
├──┴──────────────────────────────────────────────────────────────────────────────┴───────────┤
│ [Play/Pause] [Step] [Speed] [Jump next event · 72h] [Go to UTC] [cursor] [State / Saved rev] │ H=52
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ ⠿ [Open positions] [Pending orders] [Closed trades] [Journal] [Analysis] [Source details]     │ H=32
│ Active terminal tab: virtualized table / equity / notes + row actions; resizable             │ 180–360px
└──────────────────────────────────────────────────────────────────────────────────────────────┘
LEFT TOOL RAIL (44–48px) next to chart: Cursor/Select, Lines, Fib, Shapes, Text/Measure, Positions,
Magnet (only once implemented), Undo, Redo, Object Tree. Popovers anchor to rail and stay inside viewport.
```

**Width accounting:** left tools 44–52px, optional Objects 240–300px, right ticket/inspector 300–360px, remainder chart; collapse/hide inspector automatically before chart falls below **520px** useful width. Bottom terminal initial `~240px`, user drag range `collapsed 24px / 144px compact / up to 40% viewport expanded` where current existing resize contract permits. Drag six dots, keyboard Arrow adjusts, Home collapse, Enter restores. Persist *presentation preference only*, not financial state. App header/action menu focus and 200% zoom must work.

### Desktop 1024–1439

Header condenses auxiliary navigation into one menu; chart stays main, right order panel opens nonmodal over reserved width or is a drawer; Objects one panel at a time with Order/Journal. Terminal collapsible. Keep **chart above 520px wide** when feasible; do not allow right rail + Objects + order + terminal to squeeze candles into unreadable slit. At 1024 viewport, one right panel maximum and show context selector tabs.

## 2. Trading chart — precise view and rules

- Chart renders committed **revealed-only** OHLC candle prefix from `chart` API, default candles with rising/falling semantic colors. No front-end access to unrevealed tick/candle data; earlier historical context may be shown read-only when allowed by entitlement and causal policy, clearly distinguished from tradable replay.
- Candlestick **mid-price display** is separate from executed Bid/Ask evidence. Header shows instrument, feed/provider, selected timeframe and actual quote Bid/Ask only when known; data quality (ACTIVE, PARTIAL, UNRESOLVED, QA_BLOCKED) visible, no imaginary broker spread.
- Candle hover/crosshair shows UTC time, OHLC and change of **shown** candle; source-specific precision from manifest/profile. An incomplete forming candle is labeled; no repaint from future bars. No fabricated volume; Volume row says "Unavailable" unless qualified volume feed exists.
- Time axis scroll horizontally, mouse wheel zoom/pan using actual Lightweight Charts supported API, touch gestures differ per device. Crosshair toggle, grid toggle and Fit to revealed content; switching timeframe **does not advance market time** or modify orders/drawings. Preserve chart visible range unless explicit Fit or Session switch.
- Price axis and crosshair display exact tick size formatted by instrument; **chart floats are presentation only**. Entry/SL/TP input and server request use decimal-string canonical prices; never round financial inputs silently to JS float. No "market price now" from real-time public feed.
- Historical news markers permitted only with verified point-in-time news data; current News panel may explain "No historical news dataset", not show today's calendar as past.
- Chart source credit, settlement model, gap/equal-time ambiguity accessible from **Source** drawer. Layer order: candles/background → grid → indicators → drawings → planning objects/orders/levels → crosshair and selected edit handles. A selected drawing cannot obscure confirmation modal or cause accidental order.

## 3. Chart header and exact button actions

| Control | Click result | Detailed rule |
| --- | --- | --- |
| Symbol chip | source/pin detail; Session source cannot be altered in place | selecting new symbol → create **new Session** |
| Timeframe menu | switch among verified 9 values `1m 3m 5m 15m 30m 1h 2h 4h D` | hide unsupported (e.g. seconds/weekly until adapter) |
| Chart type | candle default; other types only after real renderer support | never invent data or alternate execution |
| Indicators | available seven, add/edit instance, reorder panes where supported | computed on revealed-only prefix |
| Fit | fit visible revealed bars | no SEEK; no reset |
| Grid/Crosshair | local display preference | keyboard + accessible label |
| Go to UTC | bounded date/time chooser and source warning | consult server rewind/fork rule; do not bypass |
| Save workspace layout | save pane/objects/indicator preferences by account+Session | no market/ledger copy |
| Source quality | show provider rights/timestamp limitations | never claim broker-grade certainty |
| Share/export chart | future screen only when screenshot export is actually supported and rights allow | no implicit tick/raw download |

### TradingView-like chart feature parity — scope decisions

**Core V1 required:** candle/timeframe, pan/zoom/crosshair/fit, revealed OHLC/UTC, precise price scale, drawing nine tools, two Position planning tools, seven indicators, Objects list, indicators pane, order draft/review/confirm, controlled replay/Jump, journal/analytics, Session restore. **Professional expansion** drawn from canonical drawing/indicator specs below: richer geometry, magnet and advanced indicator roster; those must not appear as live available controls until implemented/tested. No fake multi-chart sync, heatmap, order book, bid volume or Level-2 data.

## 4. Drawing rail — full exact catalog, create/edit/undo/persistence

### Currently registered (nine research drawings) — baseline preserve and finish

| ID | Tool | How user creates | Default behavior / handles |
| --- | --- | --- | --- |
| DR-01 | Trend Line | Lines → Trend Line → click/tap first time-price → click/tap second | infinite? **No**; finite segment between 2 anchors; handles at endpoints, style color/width/dash |
| DR-02 | Ray | Lines → Ray → first anchor → direction anchor | extend from start through second towards future on chart; no future **data**, only geometric line |
| DR-03 | Horizontal Line | Lines → Horizontal Line → click/tap price | price-anchored horizontal across visible chart; drag to another price, optional label |
| DR-04 | Vertical Line | Lines → Vertical Line → click/tap time | time-anchored full pane height |
| DR-05 | Rectangle | Shapes → Rectangle → opposite corners | two time-price anchors, move/resize handles, optional translucent fill |
| DR-06 | Arrow | Shapes → Arrow → start/end | line with arrowhead, style/label optional |
| DR-07 | Fibonacci Retracement | Fibonacci → Fib Retracement → 2 swing anchors | visible level labels/ratios (0/0.236/0.382/0.5/0.618/0.786/1) with reversible direction; editable levels, price scale, accuracy tested |
| DR-08 | Text | Annotations → Text → tap/click anchor → editor | multiline, size/color/alignment, save/cancel, safe XSS escaping |
| DR-09 | Measure | Measure → click start/end | display price difference, tick count, elapsed UTC/time bars where valid; *visual measurement*, not a trade |

Existing registry `DrawingTypes.js` is the source of truth for registered IDs. **Do not assume that every advanced gesture, style or editing affordance above is currently complete; test current implementation before adding UI.** Cursor/Select is a mode, not counted as a drawing; Long/Short are special planning objects, not generic drawings.

### Professional drawing catalog — architecture prepared, not falsely shipped

| Group | Planned tools from canonical spec | Required geometry/interactions |
| --- | --- | --- |
| Trend & structure | Extended Line, Horizontal Ray, Cross Line, Parallel Channel, Regression Trend | anchors + exact extension direction; channel width handles; regression window and causal historical bars only |
| Fibonacci | Fib Extension, Fib Channel | 3+ canonical anchors where required, user-configured levels; derived value labels anchored at observed times |
| Shapes | Rotated Rectangle, Ellipse/Circle, Polyline/Path, Brush, Highlighter | resize/rotate handles; point list; bounded gesture sampling; simplification not a tick artifact |
| Annotation | Anchored Text, Callout | connector/target anchor, editable text, focus and XSS safety |
| Measurement | Price Range, Date Range | exact price ticks/elapsed calendar differences (DST-safe UTC), visually available after two anchors |
| Trading | Long Position, Short Position | **Already a separate planning tool**; drag Entry/SL/TP, summary risk/RR/quantity, explicit Review/Confirm |

**Implementation policy:** professional entries become visible in selectable catalog **only after actual registry/render/serialization, hit testing and tests exist**. The catalog code can define a future schema/availability flag, but do not leave clickable no-op items. Claude should first finish reliable UX for nine existing research drawings and two position objects, then deliver professional groups in separate feature PRs coordinated with backend persistence.

### Drawing lifecycle / data ownership

1. Click group chevron opens list; click named tool sets `drawingMode` and closes list; active mode visually pressed; Escape cancels draft or exits tool; **no financial action**.
2. In Select mode click object → select, show handles and floating mini-toolbar `Edit Style`, `Copy`, `Lock`, `Hide`, `Delete` (only actions supported by saved-state adapter). Drag anchor snaps only when `Magnet` is explicitly enabled/implemented; otherwise preserve exact coordinate.
3. Keyboard Delete removes selected editable object after relevant confirmation/undo policy; Undo/Redo revert drawing edits only, **never a committed order**. Lock prevents drag/move/delete edits except Unlock; Hidden leaves persisted object in tree.
4. Object Tree contains Drawings, Indicators and **Position Plans** in distinct groups. Select from list highlights chart, visibility toggle affects rendering only, lock toggles editing only, Rename modifies UI metadata (not canonical source or trade ledger), Duplicate creates distinct object ID, Delete removes drawing/plan only. No deleting trading fills.
5. Drawing positions are `{time, price}` anchors with stable IDs, style and version; persist per authenticated workspace+Session+dataset version, preserve TIME+PRICE when changing timeframe or reloading. Server-side account association required before claiming cross-device sync; current local preference is *not* automatic cloud durability. Conflict on revision -> re-fetch/reconcile or prevent overwrite; never leak drawings across users.
6. Floating edit toolbar stays inside viewport; duplicate/copy preserves style but new ID; text XSS-safe; immutable financial ledger unrelated to drawing history. 100 drawing objects performance and hit-test regression per spec, no unbounded DOM redraw on each tick.

## 5. Position Planning objects vs live orders

**Long Position** and **Short Position** from rail open a Draft: first entry anchor, second stop anchor and target anchor, with handles aligned to Session tick scale; estimate risk/reward and lot derived from instrument/canonical estimate, **NOT financial authority**. When dragged, synchronize planner fields `Entry, SL, TP, RR, risk%, quantity` both directions. Changing SL under Protocol recalculates locked RR target and allowed size; Free Style permits discretionary supported planning. Planned object is not an executed trade.

Click object **Create Order / Review Order** → Order Ticket uses exact values → server Review shows pinned quote-side assumptions and approved risk/lot → explicit separate Confirm. A confirmed pending/open order gets immutable ID and becomes a trading overlay owned by backend; it is not a user-editable research drawing. Orders and drawings have distinct delete/undo rules. After submit, no optimistic simulated fill; entry triggers only with next eligible tick.

## 6. Indicators — exact existing catalog and interactions

**Existing seven** in `productionRegistry.js` / `overlayRegistry.js`:

| ID | Indicator | Default params / chart |
| --- | --- | --- |
| IN-01 | SMA | period 20 default, overlay price |
| IN-02 | EMA | period 20 default, overlay price |
| IN-03 | Bollinger Bands | period 20, std multiplier 2, upper/middle/lower overlay |
| IN-04 | RSI | period 14, separate [0..100] pane, reference 30/70 |
| IN-05 | MACD | fast 12, slow 26, signal 9, MACD/signal/histogram pane |
| IN-06 | ATR | period 14, separate pane |
| IN-07 | Stochastic | %K 14, %D 3, pane [0..100] with 20/80 |

**Flow:** Indicators → searchable dialog → choose a **registered** indicator → parameter form with validator/preview → **Add** → overlay or new pane → click indicator legend **gear** to edit period/style → toggle eye to hide → duplicate when supported → trash to remove; pane drag-resize/organize within supported renderer. Current Alpha limits **16 displayed indicator instances**; show count and honest limit (do not silently raise). Warmup/undefined values display gaps rather than fill made-up history. On first candle, indicator must not read future values; chart timeframe change recomputes only revealed bars. Store each indicator instance/config in scoped workspace preferences with version and account-safe sync when supported.

**Professional indicator future catalog** from [Indicator Engine Spec](../INDICATOR_ENGINE_SPEC.md): VWAP, Anchored VWAP, ADX, DMI, CCI, MFI, OBV, ROC, Momentum, Williams %R, Parabolic SAR, Donchian Channels, Keltner Channels, Ichimoku Cloud, Pivot Points. Each has separate math validation and volume-data requirements; **volume-dependent indicators blocked if volume unavailable** (VWAP, MFI, OBV etc). No external indicator scripting marketplace or custom code execution in V1 without sandbox/security review.

## 7. Order bar, ticket, review and financial lifecycle

### Right Order Panel / Ticket (Free Style)

Header `[LONG Buy / SHORT Sell]`, `[QUICK / PLANNED]`, `[MARKET / LIMIT / STOP]` restricted to supported domain. Top quote shows last revealed Bid/Ask with exact price scale, timestamp and feed. **Quick** order: side, quantity lots, market order, no SL/TP unless user clicks **Add Stop & Target** → switches Planned MARKET (when Free Style). **Planned**: entry, SL, TP, risk mode (percent or supported fixed amount), risk presets `0.5%, 1%, 2%, 3%` if existing, R:R shortcut `1R/1.5R/2R/3R` for Free Style, estimated loss/profit and cost/lot. Input all labeled with account/base/quote currency; decimal string exact; geometry validation. Each change invalidates old Review receipt.

**Protocol**: only Planned pending Limit/Stop, locked risk and RR/derived TP+lot, checklist ON all PASS or OFF actual observations; disable and server refuse forbidden Quick/Market/active manual exit. No auto-changing protocol locked values to satisfy edit.

**Step action:** click **Review Order** → pending spinner → server snapshot `Review ID, hash, Method, revision, exact quantity, side, entry/stop/TP, risk estimate, quality`; explicit **Confirm Order** commits intent; **Back to Edit** discards old review; **Cancel** commits nothing. If quote data unresolved, show refusal/uncertainty instead of fabricated fill. Submit idempotent, timeout triggers `Checking command` and GET receipt/Session, never silent resend.

**Trading overlay vs drawing:** pending line at trigger with status PENDING and cancel in terminal; open entry line + SL/TP with linked actual order state and backend-restricted amendment; closed trade history marker/lines readonly; click overlay opens order evidence card. Bid/Ask price labels and gap-through are visible; prevent misleading fill at unobserved stop.

### Terminal tabs

- **Open Positions:** symbol, side, entry, remaining lots, actual last revealed bid/ask mark, unrealized display estimate separate from settled cash, SL/TP, age, user-allowed management. Protocol locked controls labeled.
- **Pending Orders:** ID, side, type, trigger, lots, placed time, method/rule origin, cancel action; unfilled pending not counted as win/loss.
- **Closed Trades:** entry/exit timestamps/prices, side, quantity, commission/cost, realized cash and R where valid, reason SL/TP/manual, evidence refs, source quality; click → journal/details and chart evidence.
- **Journal:** canonical event timeline plus user notes, trade/order filter, optional setup markers. Cannot change fill or hash.
- **Analysis:** completed trades, valid win-rate denominator, expectancy, profit factor, drawdown and committed equity curve, warnings on missing R/FX, partial/unresolved, source quality.
- **Source/News:** source and known limitations; no point-in-time news feed means informational unavailable panel, not fake signals.

Terminal supports Collapse (24px), Compact (~144px), Expanded within bounds, Keyboard resize and saved presentation preference. Internal table scroll/virtualization, not full-page horizontal overflow.

## 8. Replay controls and keyboard shortcuts

`Play/Pause` toggles only controlled server Replay; `Step` advances bounded groups; `Speed` applies to UI requests as currently supported (main code offers 1/4/16 intervals per step; do not mislabel as broker speed). `Jump Next Event (72h)` uses one button; no duration picker. `Go to UTC` opens constrained time popover; committed financial rewind requires separate fork. Loading/queued states disable new mutating actions and expose Cancel Queue where safe. A user may continue chart pan/draw while replay paused.

Keyboard (desktop) proposal aligned with existing: `Space` Play/Pause; `Shift + →` Step. Ignore shortcuts in form/contentEditable, focused buttons, dialogs, screen-reader action, or browser OS shortcuts. `Esc` exit tool/close open menu; `Delete` remove selected editable drawing only; `Ctrl/Cmd+Z` undo drawing in focus (never backend trade), `Ctrl/Cmd+Shift+Z` redo drawing; `+`/`-` chart zoom only when canvas focused and not browser overriding. Don't register global action that places a trade without Review/Confirm.

## 9. Acceptance examples (Claude screenshots + real interaction)

`DESK-01` 1440px chart with visible header, left tools, right order and terminal, no overlap; 1024px panel auto-collapse without losing controls.
`DESK-02` create/edit/hide/lock/reload each of nine existing drawings; all selected handles persist TIME+PRICE on timeframe change; Undo cannot undo a confirmed order.
`DESK-03` Long Position drag→ticket precise values→server review→confirm; no fill until legitimate quote; Protocol forbids Quick.
`DESK-04` seven indicators add/edit/hide/remove/reload with no future values, missing volume disclosure; adding a 17th is refused.
`DESK-05` Jump 72h no trigger keeps pending; trigger/SL/TP event stops at correct first group with correct cash; normal replay exact result comparison by Codex.
`DESK-06` chart zoom/fit/timeframe switches do not alter cursor/cash/order, source panel reveals verified known limitations.
`DESK-07` modal focus, Escape, keyboard shortcuts, resizing terminal 24/144/expanded, 200% zoom and screen-reader table alternatives work.
`DESK-08` price input precision and cost labels match backend reviewed command, including unsupported source/refusal and timeout/reconciliation.
