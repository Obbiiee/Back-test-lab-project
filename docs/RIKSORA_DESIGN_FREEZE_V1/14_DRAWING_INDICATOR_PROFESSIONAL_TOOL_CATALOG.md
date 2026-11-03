# 14 — Professional Drawing and Indicator Catalogue: Geometry, Interaction and Test Oracle

**For Claude UI implementation and Codex/source-value compatibility.** The RIKSORA design targets professional terminal drawing workflows without copying TradingView artwork/layout. [Existing Drawing Engine Spec](../DRAWING_ENGINE_SPEC.md) and [Indicator Engine Spec](../INDICATOR_ENGINE_SPEC.md) remain canonical design owners. Do not mislabel target professional extras as presently implemented.

## 1. Tool taxonomy and availability policy

**Current main audited:** nine research drawing types (`trend-line, horizontal-line, vertical-line, rectangle, ray, fibonacci-retracement, arrow, text, measure`) and two special planning objects (`long-position, short-position`); **seven existing registered indicators** (SMA, EMA, Bollinger Bands, RSI, MACD, ATR, Stochastic). Future tool catalog expands in scoped PRs only after rendering, source-version persistence, keyboard/touch hit testing, math and regression evidence.

**Shared toolbar groups**:
- Select / Crosshair / Pan — modes, no persisted drawings.
- **Lines:** Trend Line, Ray, Extended Line, Horizontal Line, Horizontal Ray, Vertical Line, Cross Line, Parallel Channel, Regression Trend.
- **Fibonacci:** Fib Retracement, Fib Extension, Fib Channel.
- **Shapes:** Rectangle, Rotated Rectangle, Circle/Ellipse, Polyline/Path, Brush, Highlighter, Arrow.
- **Annotations:** Text, Anchored Text, Callout.
- **Measure:** Measure (current two-point generic), Price Range, Date Range.
- **Position Planning:** Long Position, Short Position (special draft/order workflow; not generic drawing).
- **Object controls:** visibility, lock, duplicate, delete, styles, property dialog, undo/redo, presets, object hierarchy.

**Numeric creation terminology:** `T` = timestamp from chart time axis; `P` = display/chart price coordinate. A source-price anchor is `{T,P}` using canonical stored time/decimal precision, not a pixel snapshot. Never create geometry that requires nonrevealed candle values; projecting a *line* to the right is not displaying future market data.

## 2. Existing nine research drawing creation contract — preserve baseline

| ID | Tool | Points | Create flow | Edit / result |
| --- | --- | --- | --- | --- |
| D01 | Trend Line | 2× (T,P) | select → chart click A → click B → Finish | endpoints + segment move; color/width/dash |
| D02 | Ray | 2× (T,P) | A start → B direction | extends from A in B direction; draggable handles |
| D03 | Horizontal Line | one P | click price → Done | across chart; price label, drag vertical |
| D04 | Vertical Line | one T | click time → Done | across chart pane; drag horizontal |
| D05 | Rectangle | opposite (T,P) | A → B | fill opacity, resize/translate; click inside selects |
| D06 | Arrow | two points | click tail → head | endpoints, arrowhead at second, line style |
| D07 | Fib Retracement | two swing points | click swing A → B | base swing, level lines/labels, reverse direction and user levels |
| D08 | Text | one (T,P) | tap anchor → editor → Save | text XSS-escaped, font/size/align/style, lock |
| D09 | Measure | two points | A → B | measured price change/tick count/time difference; never an execution order |

**Current code may have incomplete specific UX above:** implement/test against `DrawingTypes.js` and `CandleChart.jsx` rather than assuming every property currently persists. Keep existing IDs and saved objects readable.

## 3. Professional extensions from frozen drawing architecture (16 additional types)

| ID | Tool | User creation sequence | Editable geometry + displayed semantics |
| --- | --- | --- | --- |
| D10 | Extended Line | tap A then B | infinite geometric line both directions; no unobserved price history |
| D11 | Horizontal Ray | tap anchor price/time | ray from anchor into future time; right extension is visual only |
| D12 | Cross Line | tap intersection (T,P) | independent horiz + vertical arms, two-axis labels |
| D13 | Parallel Channel | tap A, B primary trend; tap C channel width | draggable three anchors; parallel channel boundaries, bounded filled band |
| D14 | Regression Trend | select visible historical start/end times | linear fit from **already revealed** eligible close values, finite window, intercept/bands with specified method; no future candles |
| D15 | Fib Extension | tap A, B swing; C retrace | projected levels relative to A→B from C; level multipliers editable; provenance and time anchors |
| D16 | Fib Channel | tap A, B channel baseline; C width | parallel displacement, user fib-level bands; geometry-only extensions |
| D17 | Rotated Rectangle | tap A, B baseline then C height/angle | 3 anchor/rotation handles; local geometric transform, no mutation of prices |
| D18 | Circle/Ellipse | tap center and radius/diagonal; editable | two axes/time-price extents with correct chart scaling; changes in zoom do not alter stored anchors |
| D19 | Polyline/Path | tap successive anchors → double-click or Done | add/remove nodes, move segment, max nodes quota, style |
| D20 | Brush | choose Brush → drag stroke → release | bounded pointer-sampled path in chart coordinates, smoothing optional but no raw tick creation, Undo whole stroke |
| D21 | Highlighter | choose → drag | wide translucent stroke, non-interactive on orders, bounded path and alpha |
| D22 | Anchored Text | tap (T,P) then enter content | stays chart-anchored, moves with time/price, multiline, no XSS |
| D23 | Callout | choose target (T,P), then label offset | pointer connector + movable text label, readable on phone |
| D24 | Price Range | tap A/B prices | exact price delta, tick count, percent where defined; not trade P&L |
| D25 | Date Range | tap start/end times | elapsed UTC time, optional visible-bar count separately; no false market-open assumption |

**Special planning objects** (separately owned in trading domain):
- **P01 Long Position:** first Entry, SL on loss side, TP on profit side; drag handles + numeric entry, shaded risk/reward boxes, derived RR/size/risk, Method pinned, button "Review Order" (never auto-trade).
- **P02 Short Position:** mirror geometry of Long. Free Style can use supported Quick separately, Protocol cannot use market/Quick and locks RR/risk. After server commit, actual Order/Position overlays have separate immutable IDs and rules.

Total planned catalog **27 rendered tool types** = 9 existing research + 16 new professional research + 2 position planning, subject to implemented availability and test gates. Count does not imply current UI includes all 27. Choose proper distinct icons and accessible names, not one generic repeated icon for every tool.

## 4. Common interaction contract all drawings must satisfy

**Creation:** click tool; `mode=TOOL_ARMED`, mouse/touch tap anchors with preview; `ESC` cancel, `Done` finalizes multi-point, `Shift` constraints only when defined. No double click interpreted as both extra point + Finish. Chart time-price conversion is explicit and resistant to timeframe switching, resizing, zoom, 320px device safe areas and panning.

**Selection:** one object selected at a time initially; click direct geometry or accessible Object Tree; click empty chart deselects; when overlapping, show small chooser/list near pointer (not silently select an order). Selected object displays draggable high-contrast handles and floating edit toolbar. Avoid intercepting pointer event for chart crosshair when not actually hit.

**Movement:** when unlocked, drag body to move all anchors, drag handle to modify one anchor; prevent impossible negative/NaN numeric values, cap text/path bytes/points; show preview and commit on release as a single drawing Undo step. Screen pixels are not persisted.

**Styles:** color (approved accessible palette+custom hex when safe), line thickness 1/2/3/4 px, solid/dashed/dotted when supported, fill alpha 0–100%, text size/font, level toggles for Fibonacci and channel. Preset defaults per tool are deterministic and restored when reopening; style changes do not trigger backend finance.

**Object Tree:** type icons; rename (user label), hide/show, lock/unlock, duplicate, z-order where renderer supports, delete with Undo for drawing only, group/ungroup only after object manager supports it; refuse action with meaningful explanation rather than silently fail. Hierarchy separates Research Drawings, Indicators, Position Drafts and actual server Orders. Hiding an actual position marker is visual, not canceling financial position.

**Persistence:** key by verified workspace, Session, data/profile version and drawing schema version; server-sync/versioned if supported, local-only cache clearly labeled. Stored anchors must preserve exact timestamps and string prices; no per-timeframe copy of drawings. Stable IDs and migration from existing object shapes; no reassigning a historical trade ID. Account switch clears private cache. Undo/Redo/duplicate cannot alter ledger.

**Mobile:** choose tool from bottom sheet, large handles and explicit `Edit coordinates` sheet, one interaction mode active, second finger pinch temporarily suspends tool, long press shows context only after canceling drag; frame/scroll safe. Numeric precision fallback is mandatory for placing SL/TP on small screen.

**Test oracle per tool:** create → select → edit every anchor → change timeframe → chart zoom/pan → hide/show → lock/unlock → duplicate → delete → Undo/Redo → reload → account switch; expected same time/price and text, no XSS and no accidental order.

## 5. Indicator category and calculation-integrity handoff

### Existing seven — must preserve exact registered parameters

- **SMA:** close-source moving average, period default 20, overlay, user color/width.
- **EMA:** period 20, overlay.
- **Bollinger Bands:** period 20, multiplier 2, 3 overlay lines, no future candles.
- **RSI:** period 14, oscillator pane 0..100, threshold 30/70.
- **MACD:** fast12/slow26/signal9, macd+signal+histogram pane.
- **ATR:** period14, true range pane.
- **Stochastic:** %K14/%D3, pane 0..100, threshold 20/80.
- Registry is the math authority; UI is only presentation and validated parameter input. Current chart supports at most **16 simultaneous indicator instances** until backend/client capacity test changes it.

### Planned fifteen professional indicators — UI specifications, math requires golden tests

| ID | Indicator | Default user input proposal | Pane / evidence requirement |
| --- | --- | --- | --- |
| I08 | VWAP | daily session reset / verified calendar | price overlay; **requires legitimate volume**, not tick-count pretending traded volume |
| I09 | Anchored VWAP | tap historical anchor time | overlay, source volume required, no anchor beyond cursor |
| I10 | ADX | period14 | pane trend strength, directional math tested |
| I11 | DMI | period14 | pane +DI/-DI and ADX where specified |
| I12 | CCI | period20 | oscillator pane |
| I13 | MFI | period14 | oscillator pane, **volume required** |
| I14 | OBV | price+volume | pane, **volume required** |
| I15 | ROC | period12 | pane percent change |
| I16 | Momentum | period10 | pane price delta |
| I17 | Williams %R | period14 | pane negative reference scale |
| I18 | Parabolic SAR | step0.02, max0.2 | price overlay dots, causal iterative calc |
| I19 | Donchian Channels | period20 | price overlay prior-range bands, decide current-bar inclusion in verified calc |
| I20 | Keltner Channels | EMA20, ATR10, multiplier2 | overlay three lines |
| I21 | Ichimoku Cloud | conversion9, base26, spanB52 | overlay with visual forward displacement; **never use future market data** |
| I22 | Pivot Points | prior completed period selection | overlay, calendar and period provenance required |

**Status:** target input defaults are design proposals. No indicator becomes an enabled UI choice until independent numeric test vectors (including no-lookahead, warmup, flat data, timestamp boundary, output ranges), renderer and persistence pass. Volume-dependent choices remain **unavailable on XAUUSD feeds with no qualified volume**; display exact reason. Advanced indicators use no arbitrary user-entered JS/script execution in V1.

## 6. Indicator picker and pane contract

Click **Indicators** → modal/search `Available` (actual registered), `Favorites`, `On chart`, with name/short description/placement. Click indicator → parameter form with typed period, source and style; **Add** creates one instance and default overlay/pane. In chart legend, click name selects, gear edits parameters, eye hides temporarily, clone duplicates if allowed, trash deletes only indicator. Nested pane can resize/reorder within supported chart engine; one shared source/version/cursor, no independent future prices. Chart loads only bounded revealed candles and context, indicators use same precision display and honest warmup `—` not zero.

Use source/status messages: `CAN_ADD`, `INVALID_PARAMETER`, `UNAVAILABLE_VOLUME`, `CAPACITY_16_REACHED`, `DATA_QUALITY_BLOCKED`, `REPLAY_PREFIX_ONLY`; UI should not claim not-implemented indicators work. Persist versioned config scoped to Session and validate all results against reference calculator before production.
