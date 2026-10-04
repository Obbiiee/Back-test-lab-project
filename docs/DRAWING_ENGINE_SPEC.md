# Backtest Lab — Professional Drawing Engine Specification

Status: architecture authority for future drawing work. This document does not authorize implementation.

## Goal
One shared drawing engine should provide professional interaction semantics. Individual tools define geometry/behavior; they must not reimplement selection, persistence, magnet, history and common interaction independently.

## Canonical object
```text
id
type
points[]
style{}
visible
locked
selected
groupId?
zIndex
createdAt
updatedAt
metadata{}
```
Anchors store market coordinates (time + price, with optional OHLC attachment), not screen pixels.

## Shared subsystems
Anchor Engine; coordinate conversion; hit testing; hover/selection; multi-selection; drag/transform; Magnet; style; visibility; lock; z-order; grouping; serialization; clipboard/duplicate; undo/redo; context menu; events; persistence; Object Tree synchronization.

## Magnet
Modes: OFF / WEAK / STRONG. Targets: Open / High / Low / Close where applicable.
WEAK snaps within a defined interaction radius. STRONG snaps to the nearest eligible OHLC target on the intended candle. Temporary keyboard modifiers may alter snapping where UX validation approves.

## Interaction contract
Professional tools should support as applicable: precise anchors, drag/edit handles, hover/select state, lock/unlock, hide/show, duplicate, delete, undo/redo, styling, persistence, z-order, grouping, keyboard Delete/Escape, context menu, and stability through zoom/pan/timeframe/replay.

## Planned professional tool set
Trend/structure: Trend Line, Ray, Extended Line, Horizontal Line, Horizontal Ray, Vertical Line, Cross Line, Parallel Channel, Regression Trend.

Fibonacci: Fib Retracement, Fib Extension, Fib Channel.

Geometry: Rectangle, Rotated Rectangle, Circle/Ellipse, Polyline/Path, Brush, Highlighter.

Annotation: Text, Anchored Text, Callout.

Measurement/trading: Price Range, Date Range, Long Position, Short Position.

The exact implementation order remains phase-authorized work.

## Position tools
Long/Short Position are special: visually they use drawing infrastructure, but planned-trade behavior turns them into Trade Planner + Risk Calculator + Order Creator. Geometry may represent Entry/SL/TP and preview RR/risk/size; PLACE ORDER emits a canonical order request. Drawing state itself is not account/execution state.

## Object Tree
Plan hierarchical Drawings + Indicators with rename, hide, lock, delete, reorder, group/ungroup and group-level visibility/lock. Selection must synchronize both directions between chart and tree.

## Performance
Future hardening should benchmark representative 100-drawing workloads together with large candle sets, indicators and multi-chart layouts. Correct interaction and deterministic persistence take precedence over decorative complexity.
