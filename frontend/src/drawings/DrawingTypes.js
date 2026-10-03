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

export function canonicalPoint(point) {
  if (!point || !Number.isFinite(point.time) || !Number.isFinite(point.price)) {
    throw new TypeError('Drawing anchors require numeric time and price');
  }
  return Object.freeze({ time: point.time, price: point.price });
}
