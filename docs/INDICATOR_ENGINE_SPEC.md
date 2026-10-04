# Backtest Lab — Indicator Engine 2.0 Specification

Status: architecture authority for future indicator work. This document does not authorize implementation.

## Principle
Indicator calculators are deterministic domain functions, separate from chart rendering. Chart, replay and research consumers must share compatible calculations rather than independently reproducing formulas.

## Definition contract
```text
IndicatorDefinition {
  id
  name
  category
  inputs[]
  outputs[]
  pane
  calculator
  warmup
  styles
  precision
}
```

Calculators consume time-bounded/revealed data only. No-look-ahead and warmup behavior require fixtures.

## Existing baseline
SMA, EMA, Bollinger Bands, Volume, RSI, MACD, ATR and Stochastic are the established v1 family and must remain regression-protected.

## Planned professional set
Add: VWAP, Anchored VWAP, ADX, DMI, CCI, MFI, OBV, ROC, Momentum, Williams %R, Parabolic SAR, Donchian Channels, Keltner Channels, Ichimoku Cloud, Pivot Points, Aroon and Choppiness Index, subject to phase authorization and data availability.

## UX contract
Plan add/configure/move/hide/duplicate/delete/persist, parameter editing, source selection, style controls, pane resize/reorder, price scale, reset defaults, search, favorites, templates, legend values and multiple instances. Undo/redo should integrate with workspace history where appropriate.

## Pane/rendering contract
Overlay indicators stay on the appropriate price pane; oscillator/secondary indicators own explicit panes. Renderer lifecycle, pane ownership and calculator state must not leak future data.

## Validation
Each calculator requires deterministic known-value fixtures, edge/warmup cases and truncation-invariance/no-look-ahead tests. Rendering tests do not substitute for calculator correctness.
