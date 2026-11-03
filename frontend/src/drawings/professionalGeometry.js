// Pure geometry/statistics for the C-03 professional tools (Issue #21).
// Price/time math works on canonical anchors and revealed bars only; screen
// math works on transient CSS pixels and never mutates canonical anchors.
import { logicalForTimestamp } from './timeCoordinates.js';

// Least-squares fit of close over the revealed bars whose time lies between the
// two anchor times (inclusive). Bars after the last revealed bar do not exist in
// `bars`, so the fit can never read a future quote.
export function regressionFit(bars, timeA, timeB) {
  const from = Math.min(timeA, timeB), to = Math.max(timeA, timeB);
  let first = -1, last = -1;
  for (let i = 0; i < bars.length; i++) {
    if (bars[i].time < from) continue;
    if (bars[i].time > to) break;
    if (first < 0) first = i;
    last = i;
  }
  const n = first < 0 ? 0 : last - first + 1;
  if (n < 2) return null;
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (let k = 0; k < n; k++) { const y = bars[first + k].close; sx += k; sy += y; sxx += k * k; sxy += k * y; }
  const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx), intercept = (sy - slope * sx) / n;
  let sq = 0;
  for (let k = 0; k < n; k++) sq += (bars[first + k].close - (intercept + slope * k)) ** 2;
  const sd = Math.sqrt(sq / n);
  const priceAt = time => {
    const logical = logicalForTimestamp(bars, time);
    return logical == null ? null : intercept + slope * (logical - first);
  };
  return { first, last, count: n, slope, intercept, sd, priceAt };
}

// Unit normal of segment a→b (screen space) and signed distance of p from it.
export function normalOffset(a, b, p) {
  const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
  if (len < 1e-9) return { nx: 0, ny: 1, distance: p.y - a.y };
  const nx = -dy / len, ny = dx / len;
  return { nx, ny, distance: (p.x - a.x) * nx + (p.y - a.y) * ny };
}

// Vertical (price-axis) offset of p from the infinite line through a, b, in pixels.
export function verticalOffset(a, b, p) {
  if (Math.abs(b.x - a.x) < 1e-9) return p.y - a.y;
  return p.y - (a.y + (b.y - a.y) * (p.x - a.x) / (b.x - a.x));
}

export function formatDuration(seconds) {
  const s = Math.round(Math.abs(seconds)), d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
  return (seconds < 0 ? '−' : '') + [d ? d + 'd' : '', h ? h + 'h' : '', m || (!d && !h) ? m + 'm' : ''].filter(Boolean).join(' ');
}

// Revealed bars whose open time lies in [from, to].
export function barsBetween(bars, timeA, timeB) {
  const from = Math.min(timeA, timeB), to = Math.max(timeA, timeB);
  let count = 0;
  for (const bar of bars) { if (bar.time > to) break; if (bar.time >= from) count++; }
  return count;
}

export function priceRangeStats(a, b, tickSize) {
  const delta = b.price - a.price;
  const ticks = tickSize > 0 ? Math.round(delta / tickSize) : null;
  return { delta, ticks, percent: a.price === 0 ? null : delta / a.price * 100 };
}

// Douglas-free decimation for freehand strokes: drop points closer than
// `minDistance` px to the previous kept point and cap the total.
export function decimateStroke(points, minDistance, max) {
  const kept = [];
  for (const point of points) {
    const last = kept.at(-1);
    if (!last || Math.hypot(point.x - last.x, point.y - last.y) >= minDistance) kept.push(point);
    if (kept.length >= max) break;
  }
  return kept;
}
