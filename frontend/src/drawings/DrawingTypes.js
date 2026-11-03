export const TREND_LINE = 'trend-line';
export const HORIZONTAL_LINE = 'horizontal-line';
export const VERTICAL_LINE = 'vertical-line';
export const RECTANGLE = 'rectangle';
export const CORE_DRAWINGS = Object.freeze({
  [TREND_LINE]: { name: 'Trend Line', points: 2 },
  [HORIZONTAL_LINE]: { name: 'Horizontal Line', points: 1 },
  [VERTICAL_LINE]: { name: 'Vertical Line', points: 1 },
  [RECTANGLE]: { name: 'Rectangle', points: 2 },
});

export const FIBONACCI = 'fibonacci-retracement';
export const ARROW = 'arrow';
export const TEXT = 'text';
export const MEASURE = 'measure';
export const RAY = 'ray';
export const ADVANCED_DRAWINGS = Object.freeze({
  [RAY]: { name: 'Ray', points: 2 },
  [FIBONACCI]: { name: 'Fibonacci Retracement', points: 2 },
  [ARROW]: { name: 'Arrow', points: 2 },
  [TEXT]: { name: 'Text', points: 1, text: true },
  [MEASURE]: { name: 'Measure', points: 2 },
});

// Issue #21 C-03: professional tools D10–D25. `points` is a fixed count or
// {min,max}. `nodes` = click-per-node path finished with Done/Enter/double-click;
// `freehand` = pointer-drag stroke (bounded). `defaults` are written into the
// record on creation so the stored drawing is self-describing.
export const EXTENDED_LINE = 'extended-line';
export const HORIZONTAL_RAY = 'horizontal-ray';
export const CROSS_LINE = 'cross-line';
export const PARALLEL_CHANNEL = 'parallel-channel';
export const REGRESSION_TREND = 'regression-trend';
export const FIB_EXTENSION = 'fib-extension';
export const FIB_CHANNEL = 'fib-channel';
export const ROTATED_RECTANGLE = 'rotated-rectangle';
export const ELLIPSE = 'ellipse';
export const POLYLINE = 'polyline';
export const BRUSH = 'brush';
export const HIGHLIGHTER = 'highlighter';
export const ANCHORED_TEXT = 'anchored-text';
export const CALLOUT = 'callout';
export const PRICE_RANGE = 'price-range';
export const DATE_RANGE = 'date-range';
export const FREEHAND_MAX_POINTS = 512;
export const POLYLINE_MAX_NODES = 64;
export const PROFESSIONAL_DRAWINGS = Object.freeze({
  [EXTENDED_LINE]: { name: 'Extended Line', points: 2 },
  [HORIZONTAL_RAY]: { name: 'Horizontal Ray', points: 1 },
  [CROSS_LINE]: { name: 'Cross Line', points: 1 },
  [PARALLEL_CHANNEL]: { name: 'Parallel Channel', points: 3 },
  [REGRESSION_TREND]: { name: 'Regression Trend', points: 2 },
  [FIB_EXTENSION]: { name: 'Fibonacci Extension', points: 3 },
  [FIB_CHANNEL]: { name: 'Fibonacci Channel', points: 3 },
  [ROTATED_RECTANGLE]: { name: 'Rotated Rectangle', points: 3 },
  [ELLIPSE]: { name: 'Ellipse', points: 2 },
  [POLYLINE]: { name: 'Polyline', points: { min: 2, max: POLYLINE_MAX_NODES }, nodes: true },
  [BRUSH]: { name: 'Brush', points: { min: 2, max: FREEHAND_MAX_POINTS }, freehand: true },
  [HIGHLIGHTER]: { name: 'Highlighter', points: { min: 2, max: FREEHAND_MAX_POINTS }, freehand: true, defaults: { color: '#ffd23f', lineWidth: 10, opacity: 0.35 } },
  [ANCHORED_TEXT]: { name: 'Anchored Text', points: 1, text: true, defaults: { labelPosition: 'top', textAlign: 'center', bold: true } },
  [CALLOUT]: { name: 'Callout', points: 2, text: true, defaults: { textBorder: true } },
  [PRICE_RANGE]: { name: 'Price Range', points: 2, defaults: { fillOpacity: 0.15 } },
  [DATE_RANGE]: { name: 'Date Range', points: 2, defaults: { fillOpacity: 0.15 } },
});
export const DRAWING_SPECS = Object.freeze({ ...CORE_DRAWINGS, ...ADVANCED_DRAWINGS, ...PROFESSIONAL_DRAWINGS });

export function canonicalPoint(point) {
  if (!point || !Number.isFinite(point.time) || !Number.isFinite(point.price)) {
    throw new TypeError('Drawing anchors require numeric time and price');
  }
  return Object.freeze({ time: point.time, price: point.price });
}
