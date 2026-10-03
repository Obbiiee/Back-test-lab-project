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
export const ADVANCED_DRAWINGS = Object.freeze({
  [FIBONACCI]: { name: 'Fibonacci Retracement', points: 2 },
  [ARROW]: { name: 'Arrow', points: 2 },
  [TEXT]: { name: 'Text', points: 1 },
  [MEASURE]: { name: 'Measure', points: 2 },
});
export const DRAWING_SPECS = Object.freeze({ ...CORE_DRAWINGS, ...ADVANCED_DRAWINGS });

export function canonicalPoint(point) {
  if (!point || !Number.isFinite(point.time) || !Number.isFinite(point.price)) {
    throw new TypeError('Drawing anchors require numeric time and price');
  }
  return Object.freeze({ time: point.time, price: point.price });
}
