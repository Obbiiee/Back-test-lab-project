export const TREND_LINE = 'trend-line';

export function canonicalPoint(point) {
  if (!point || !Number.isFinite(point.time) || !Number.isFinite(point.price)) {
    throw new TypeError('Drawing anchors require numeric time and price');
  }
  return Object.freeze({ time: point.time, price: point.price });
}
