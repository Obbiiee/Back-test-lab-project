// Exact, keyboard-addressable coordinate edits for drawings (Issue #21 C-01).
// Prices move on the Session tick grid with decimal-safe rounding; times move
// by whole bars of the currently displayed timeframe. Nothing here touches
// market data, orders or the financial ledger.
import { logicalAtTime, timeAtLogical } from '../chart/coordinates.js';

export function decimalsOf(step) {
  const text = String(step);
  if (/e-/i.test(text)) return Number(text.split(/e-/i)[1]);
  return text.split('.')[1]?.length ?? 0;
}

export function roundToStep(value, step) {
  if (!Number.isFinite(value) || !Number.isFinite(step) || step <= 0) return value;
  const places = Math.min(12, decimalsOf(step));
  return Number((Math.round(value / step) * step).toFixed(places));
}

// Adds an exact number of ticks: 2300.120 + 3 × 0.001 = 2300.123, never 2300.12300000004.
export function stepPrice(price, ticks, tickSize) {
  if (!Number.isFinite(price) || !Number.isInteger(ticks) || !(tickSize > 0)) throw new RangeError('Invalid price step');
  const places = Math.min(12, Math.max(decimalsOf(tickSize), decimalsOf(price)));
  return Number((price + ticks * tickSize).toFixed(places));
}

// Moves a timestamp by N displayed bars. Inside the series it lands on actual
// bar times (fractional anchors keep their fraction); outside it uses the bar
// interval. Times past the last revealed bar are drawing space only and reveal
// no market data.
export function stepBars(time, bars, count) {
  if (!Number.isFinite(time) || !Number.isInteger(count)) throw new RangeError('Invalid bar step');
  if (!bars?.length) return time;
  const logical = logicalAtTime(bars, time);
  if (logical == null) return time;
  const target = logical + count;
  const whole = Math.round(target);
  if (Math.abs(target - whole) < 1e-9) return timeAtLogical(bars, whole);
  const left = Math.floor(target), weight = target - left;
  const a = timeAtLogical(bars, left), b = timeAtLogical(bars, left + 1);
  return a + (b - a) * weight;
}

export function movePoints(points, { index = null, ticks = 0, bars: count = 0, tickSize, candles }) {
  return points.map((point, i) => {
    if (index != null && i !== index) return point;
    return {
      time: count ? stepBars(point.time, candles, count) : point.time,
      price: ticks ? stepPrice(point.price, ticks, tickSize) : point.price,
    };
  });
}

export function parseUtc(value) {
  if (typeof value !== 'string' || !value) return null;
  const normalized = value.length === 16 ? value + ':00' : value;
  const time = Date.parse(normalized.endsWith('Z') ? normalized : normalized + 'Z') / 1000;
  return Number.isFinite(time) ? time : null;
}
export function formatUtc(time) {
  if (!Number.isFinite(time)) return '';
  return new Date(Math.round(time) * 1000).toISOString().slice(0, 19);
}
export function formatPrice(price, tickSize) {
  return Number.isFinite(price) ? price.toFixed(Math.min(12, Math.max(decimalsOf(tickSize), 0))) : '';
}
