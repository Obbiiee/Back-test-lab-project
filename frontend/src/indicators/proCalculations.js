// Issue #21 C-06 professional price indicators. Pure, deterministic and
// causal: the value at bar i uses bars 0..i only (displacements only move a
// plotted point to a later revealed bar, never read a future quote).
// Conventions are pinned here and documented in docs/terminal-indicators.md;
// changing one requires a new indicator version, not a silent edit.
//
// EMA convention matches the existing registry: seeded with the SMA of the
// first N values, then alpha = 2 / (N + 1). Wilder/RMA: SMA seed, then
// (prev * (N - 1) + x) / N.

const NaNs = n => new Array(n).fill(NaN);
export const closes = candles => candles.map(bar => bar.close);
export const hl2 = candles => candles.map(bar => (bar.high + bar.low) / 2);
export const hlc3 = candles => candles.map(bar => (bar.high + bar.low + bar.close) / 3);
const ohlc4 = candles => candles.map(bar => (bar.open + bar.high + bar.low + bar.close) / 4);
export const SOURCES = Object.freeze({ close: closes, open: c => c.map(b => b.open), high: c => c.map(b => b.high), low: c => c.map(b => b.low), hl2, hlc3, ohlc4 });
export const sourceRule = (fallback = 'close') => ({ default: fallback, label: 'Source', options: Object.keys(SOURCES), validate: value => Object.hasOwn(SOURCES, value) });
const source = (candles, name = 'close') => SOURCES[name](candles);

// Converts an index-aligned array to chart points, skipping warmup NaNs.
export function toPoints(candles, values, color) {
  const points = [];
  for (let i = 0; i < values.length; i++) if (Number.isFinite(values[i])) points.push(color ? { time: candles[i].time, value: values[i], color: color(i, values[i]) } : { time: candles[i].time, value: values[i] });
  return points;
}
// Index of the first finite value at or after `from`.
function firstFinite(values, from = 0) { for (let i = from; i < values.length; i++) if (Number.isFinite(values[i])) return i; return -1; }

export function smaArr(values, n) {
  const out = NaNs(values.length); let sum = 0, count = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (!Number.isFinite(v)) { sum = 0; count = 0; continue; }
    sum += v; count++;
    if (count > n) sum -= values[i - n];
    if (count >= n) out[i] = sum / n;
  }
  return out;
}
export function emaArr(values, n) {
  const out = NaNs(values.length), start = firstFinite(values);
  if (start < 0 || values.length - start < n) return out;
  let value = 0;
  for (let i = start; i < start + n; i++) value += values[i];
  value /= n; out[start + n - 1] = value;
  const alpha = 2 / (n + 1);
  for (let i = start + n; i < values.length; i++) { value = values[i] * alpha + value * (1 - alpha); out[i] = value; }
  return out;
}
export function rmaArr(values, n) {
  const out = NaNs(values.length), start = firstFinite(values);
  if (start < 0 || values.length - start < n) return out;
  let value = 0;
  for (let i = start; i < start + n; i++) value += values[i];
  value /= n; out[start + n - 1] = value;
  for (let i = start + n; i < values.length; i++) { value = (value * (n - 1) + values[i]) / n; out[i] = value; }
  return out;
}
export function wmaArr(values, n) {
  const out = NaNs(values.length), denominator = n * (n + 1) / 2;
  for (let i = n - 1; i < values.length; i++) {
    let sum = 0, ok = true;
    for (let k = 0; k < n; k++) { const v = values[i - n + 1 + k]; if (!Number.isFinite(v)) { ok = false; break; } sum += v * (k + 1); }
    if (ok) out[i] = sum / denominator;
  }
  return out;
}
export function trueRange(candles) {
  return candles.map((bar, i) => i === 0 ? bar.high - bar.low : Math.max(bar.high - bar.low, Math.abs(bar.high - candles[i - 1].close), Math.abs(bar.low - candles[i - 1].close)));
}
export const atrArr = (candles, n) => rmaArr(trueRange(candles), n);
function highest(values, n, i) { let m = -Infinity; for (let k = i - n + 1; k <= i; k++) m = Math.max(m, values[k]); return m; }
function lowest(values, n, i) { let m = Infinity; for (let k = i - n + 1; k <= i; k++) m = Math.min(m, values[k]); return m; }
function stdevArr(values, n) {
  const mean = smaArr(values, n), out = NaNs(values.length);
  for (let i = n - 1; i < values.length; i++) {
    if (!Number.isFinite(mean[i])) continue;
    let sq = 0; for (let k = i - n + 1; k <= i; k++) sq += (values[k] - mean[i]) ** 2;
    out[i] = Math.sqrt(sq / n);
  }
  return out;
}
// Least-squares line over the last n values; returns the fitted value at the
// window end plus slope/intercept for channel use.
function linreg(values, n, i) {
  let sx = 0, sy = 0, sxy = 0, sxx = 0;
  for (let k = 0; k < n; k++) { const y = values[i - n + 1 + k]; sx += k; sy += y; sxy += k * y; sxx += k * k; }
  const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx || 1), intercept = (sy - slope * sx) / n;
  return { value: intercept + slope * (n - 1), slope, intercept };
}
function linregArr(values, n) {
  const out = NaNs(values.length);
  for (let i = n - 1; i < values.length; i++) {
    let ok = true; for (let k = i - n + 1; k <= i; k++) if (!Number.isFinite(values[k])) { ok = false; break; }
    if (ok) out[i] = linreg(values, n, i).value;
  }
  return out;
}
const shift = (values, bars) => values.map((_, i) => i - bars >= 0 && i - bars < values.length ? values[i - bars] : NaN);

// ---- Moving averages --------------------------------------------------------
export const wma = (c, { period, source: s }) => toPoints(c, wmaArr(source(c, s), period));
export const rma = (c, { period, source: s }) => toPoints(c, rmaArr(source(c, s), period));
export function hma(c, { period, source: s }) {
  const x = source(c, s), half = wmaArr(x, Math.max(1, Math.floor(period / 2))), full = wmaArr(x, period);
  return toPoints(c, wmaArr(half.map((v, i) => 2 * v - full[i]), Math.max(1, Math.round(Math.sqrt(period)))));
}
export function dema(c, { period, source: s }) {
  const e1 = emaArr(source(c, s), period), e2 = emaArr(e1, period);
  return toPoints(c, e1.map((v, i) => 2 * v - e2[i]));
}
export function tema(c, { period, source: s }) {
  const e1 = emaArr(source(c, s), period), e2 = emaArr(e1, period), e3 = emaArr(e2, period);
  return toPoints(c, e1.map((v, i) => 3 * v - 3 * e2[i] + e3[i]));
}
export function zlema(c, { period, source: s }) {
  const x = source(c, s), lag = Math.floor((period - 1) / 2);
  return toPoints(c, emaArr(x.map((v, i) => i >= lag ? 2 * v - x[i - lag] : NaN), period));
}
// KAMA (Kaufman): seed = close at bar N-1, as in bukosabino/ta.
export function kama(c, { period, fast, slow }) {
  const x = closes(c), out = NaNs(x.length);
  if (x.length < period) return [];
  const fastSc = 2 / (fast + 1), slowSc = 2 / (slow + 1);
  out[period - 1] = x[period - 1];
  for (let i = period; i < x.length; i++) {
    let volatility = 0; for (let k = i - period + 1; k <= i; k++) volatility += Math.abs(x[k] - x[k - 1]);
    const er = volatility === 0 ? 0 : Math.abs(x[i] - x[i - period]) / volatility;
    const sc = (er * (fastSc - slowSc) + slowSc) ** 2;
    out[i] = out[i - 1] + sc * (x[i] - out[i - 1]);
  }
  return toPoints(c, out);
}
export const linearRegression = (c, { period, source: s }) => toPoints(c, linregArr(source(c, s), period));
export const standardDeviation = (c, { period, source: s }) => toPoints(c, stdevArr(source(c, s), period));
export function maRibbon(c, params) {
  const x = closes(c), result = {};
  for (let k = 1; k <= 6; k++) {
    const period = params['period' + k];
    result['ma' + k] = period > 0 ? toPoints(c, (params.kind === 'SMA' ? smaArr : emaArr)(x, period)) : [];
  }
  return result;
}

// ---- Bands, channels, trend --------------------------------------------------
// Supertrend (pinned to the common Pine definition): bands hl2 ± m·ATR(Wilder),
// final bands ratchet, first valid bar starts in a downtrend (upper band).
export function supertrend(c, { atrPeriod, multiplier }) {
  const atr = atrArr(c, atrPeriod), mid = hl2(c), out = [];
  let upper = NaN, lower = NaN, up = false;
  for (let i = 0; i < c.length; i++) {
    if (!Number.isFinite(atr[i])) continue;
    const basicUpper = mid[i] + multiplier * atr[i], basicLower = mid[i] - multiplier * atr[i];
    const first = !Number.isFinite(upper), prevClose = c[i - 1]?.close;
    const finalUpper = first || basicUpper < upper || prevClose > upper ? basicUpper : upper;
    const finalLower = first || basicLower > lower || prevClose < lower ? basicLower : lower;
    if (first) up = false;
    else if (up) up = c[i].close >= finalLower;
    else up = c[i].close > finalUpper;
    upper = finalUpper; lower = finalLower;
    out.push({ time: c[i].time, value: up ? lower : upper, color: up ? '#089981' : '#f23645' });
  }
  return { trend: out };
}
export function keltner(c, { period, atrPeriod, multiplier }) {
  const middle = emaArr(closes(c), period), atr = atrArr(c, atrPeriod);
  return { middle: toPoints(c, middle), upper: toPoints(c, middle.map((m, i) => m + multiplier * atr[i])), lower: toPoints(c, middle.map((m, i) => m - multiplier * atr[i])) };
}
export function donchian(c, { period }) {
  const highs = c.map(b => b.high), lows = c.map(b => b.low), up = NaNs(c.length), down = NaNs(c.length);
  for (let i = period - 1; i < c.length; i++) { up[i] = highest(highs, period, i); down[i] = lowest(lows, period, i); }
  return { upper: toPoints(c, up), lower: toPoints(c, down), basis: toPoints(c, up.map((u, i) => (u + down[i]) / 2)) };
}
// Wilder Parabolic SAR. Starts on bar 1 with direction from bar0→bar1 close.
export function parabolicSar(c, { start, increment, maximum }) {
  if (c.length < 2) return [];
  let long = c[1].close >= c[0].close, af = start, ep = long ? Math.max(c[0].high, c[1].high) : Math.min(c[0].low, c[1].low);
  let sar = long ? Math.min(c[0].low, c[1].low) : Math.max(c[0].high, c[1].high);
  const points = [{ time: c[1].time, value: sar }];
  for (let i = 2; i < c.length; i++) {
    let next = sar + af * (ep - sar);
    if (long) {
      next = Math.min(next, c[i - 1].low, c[i - 2].low);
      if (c[i].low < next) { long = false; next = ep; ep = c[i].low; af = start; }
      else if (c[i].high > ep) { ep = c[i].high; af = Math.min(maximum, af + increment); }
    } else {
      next = Math.max(next, c[i - 1].high, c[i - 2].high);
      if (c[i].high > next) { long = true; next = ep; ep = c[i].high; af = start; }
      else if (c[i].low < ep) { ep = c[i].low; af = Math.min(maximum, af + increment); }
    }
    sar = next; points.push({ time: c[i].time, value: sar });
  }
  return points;
}
export function ichimoku(c, { conversion, base, spanB, displacement }) {
  const highs = c.map(b => b.high), lows = c.map(b => b.low);
  const mid = n => c.map((_, i) => i >= n - 1 ? (highest(highs, n, i) + lowest(lows, n, i)) / 2 : NaN);
  const tenkan = mid(conversion), kijun = mid(base), b = mid(spanB);
  const a = tenkan.map((t, i) => (t + kijun[i]) / 2);
  // Leading spans are plotted `displacement` bars later on revealed bars only;
  // lagging span plots today's close `displacement` bars back.
  const lagging = c.map((_, i) => i + displacement < c.length ? c[i + displacement].close : NaN);
  return { conversion: toPoints(c, tenkan), base: toPoints(c, kijun), spanA: toPoints(c, shift(a, displacement)), spanB: toPoints(c, shift(b, displacement)), lagging: toPoints(c, lagging) };
}
const UTC_DAY = 86400;
// Prior completed UTC day. A day is complete once a bar from a later day is revealed.
function completedDays(c) {
  const days = []; let current = null;
  for (let i = 0; i < c.length; i++) {
    const day = Math.floor(c[i].time / UTC_DAY);
    if (!current || current.day !== day) { if (current) days.push(current); current = { day, high: c[i].high, low: c[i].low, close: c[i].close, first: i }; }
    else { current.high = Math.max(current.high, c[i].high); current.low = Math.min(current.low, c[i].low); current.close = c[i].close; }
  }
  return { days, current };
}
export const PIVOT_METHODS = ['classic', 'fibonacci', 'camarilla'];
export function pivotLevels(method, { high: h, low: l, close: cl }) {
  const p = (h + l + cl) / 3, r = h - l;
  if (method === 'fibonacci') return { p, r1: p + .382 * r, r2: p + .618 * r, r3: p + r, s1: p - .382 * r, s2: p - .618 * r, s3: p - r };
  if (method === 'camarilla') return { p, r1: cl + r * 1.1 / 12, r2: cl + r * 1.1 / 6, r3: cl + r * 1.1 / 4, s1: cl - r * 1.1 / 12, s2: cl - r * 1.1 / 6, s3: cl - r * 1.1 / 4 };
  return { p, r1: 2 * p - l, r2: p + r, r3: h + 2 * (p - l), s1: 2 * p - h, s2: p - r, s3: l - 2 * (h - p) };
}
export function pivotPoints(c, { method }) {
  const keys = ['p', 'r1', 'r2', 'r3', 's1', 's2', 's3'], result = Object.fromEntries(keys.map(key => [key, []]));
  const { days } = completedDays(c), byDay = new Map(days.map((day, index) => [day.day, index]));
  for (let i = 0; i < c.length; i++) {
    const day = Math.floor(c[i].time / UTC_DAY), index = byDay.has(day) ? byDay.get(day) : days.length;
    const prior = days[index - 1];
    if (!prior) continue;
    const levels = pivotLevels(method, prior);
    for (const key of keys) result[key].push({ time: c[i].time, value: levels[key] });
  }
  return result;
}
// Fractal at bar i needs `right` later bars, so it appears only once confirmed.
export function williamsFractals(c, { left, right }) {
  const up = [], down = [];
  for (let i = left; i + right < c.length; i++) {
    let isUp = true, isDown = true;
    for (let k = i - left; k <= i + right; k++) {
      if (k === i) continue;
      if (c[k].high >= c[i].high) isUp = false;
      if (c[k].low <= c[i].low) isDown = false;
    }
    if (isUp) up.push({ time: c[i].time, value: c[i].high });
    if (isDown) down.push({ time: c[i].time, value: c[i].low });
  }
  return { up, down };
}
export function alligator(c, { jaw, teeth, lips, jawShift, teethShift, lipsShift }) {
  const m = hl2(c);
  return { jaw: toPoints(c, shift(rmaArr(m, jaw), jawShift)), teeth: toPoints(c, shift(rmaArr(m, teeth), teethShift)), lips: toPoints(c, shift(rmaArr(m, lips), lipsShift)) };
}
// Confirmed-pivot ZigZag: a swing point is fixed only after price reverses by
// `deviation` percent and at least `depth` bars separate it from the previous
// pivot. Confirmed pivots never move. The unfinished last leg (previous pivot
// → current extreme) is a separate "provisional" output because it can move.
export function zigzag(c, { depth, deviation }) {
  if (c.length < 2) return { confirmed: [], provisional: [] };
  const up = 1 + deviation / 100, down = 1 - deviation / 100, pivots = [];
  let trend = 0, hi = { i: 0, price: c[0].high }, lo = { i: 0, price: c[0].low }, extreme = null;
  for (let i = 1; i < c.length; i++) {
    const { high, low } = c[i];
    if (trend === 0) {
      if (high > hi.price) hi = { i, price: high };
      if (low < lo.price) lo = { i, price: low };
      if (hi.i > lo.i && hi.price >= lo.price * up) { pivots.push(lo); trend = 1; extreme = hi; }
      else if (lo.i > hi.i && lo.price <= hi.price * down) { pivots.push(hi); trend = -1; extreme = lo; }
      continue;
    }
    const last = pivots.at(-1);
    if (trend === 1) {
      if (high > extreme.price) extreme = { i, price: high };
      else if (low <= extreme.price * down && extreme.i - last.i >= depth) { pivots.push(extreme); trend = -1; extreme = { i, price: low }; }
    } else {
      if (low < extreme.price) extreme = { i, price: low };
      else if (high >= extreme.price * up && extreme.i - last.i >= depth) { pivots.push(extreme); trend = 1; extreme = { i, price: high }; }
    }
  }
  const confirmed = pivots.map(p => ({ time: c[p.i].time, value: p.price }));
  const last = pivots.at(-1);
  const provisional = last && extreme && extreme.i > last.i ? [{ time: c[last.i].time, value: last.price }, { time: c[extreme.i].time, value: extreme.price }] : [];
  return { confirmed, provisional };
}

// ---- Momentum & oscillators -------------------------------------------------
function rsiArr(values, n) {
  const out = NaNs(values.length);
  if (values.length <= n) return out;
  let gain = 0, loss = 0;
  for (let i = 1; i <= n; i++) { const d = values[i] - values[i - 1]; gain += Math.max(0, d); loss += Math.max(0, -d); }
  gain /= n; loss /= n;
  const value = () => loss === 0 ? (gain === 0 ? 50 : 100) : 100 - 100 / (1 + gain / loss);
  out[n] = value();
  for (let i = n + 1; i < values.length; i++) { const d = values[i] - values[i - 1]; gain = (gain * (n - 1) + Math.max(0, d)) / n; loss = (loss * (n - 1) + Math.max(0, -d)) / n; out[i] = value(); }
  return out;
}
export function stochRsi(c, { rsiPeriod, stochPeriod, kSmoothing, dSmoothing }) {
  const r = rsiArr(closes(c), rsiPeriod), raw = NaNs(c.length);
  for (let i = 0; i < c.length; i++) {
    if (i < rsiPeriod + stochPeriod - 1) continue;
    const hi = highest(r, stochPeriod, i), lo = lowest(r, stochPeriod, i);
    raw[i] = hi === lo ? 50 : 100 * (r[i] - lo) / (hi - lo);
  }
  const k = smaArr(raw, kSmoothing), d = smaArr(k, dSmoothing);
  return { k: toPoints(c, k), d: toPoints(c, d) };
}
// Wilder DMI/ADX: smoothed sums (first = sum of N), ADX = RMA of DX.
function dmiArrays(c, n) {
  const len = c.length, plus = NaNs(len), minus = NaNs(len), adx = NaNs(len);
  if (len <= n) return { plus, minus, adx };
  const tr = trueRange(c); let sTr = 0, sPlus = 0, sMinus = 0;
  const dx = NaNs(len);
  for (let i = 1; i < len; i++) {
    const up = c[i].high - c[i - 1].high, down = c[i - 1].low - c[i].low;
    const pdm = up > down && up > 0 ? up : 0, mdm = down > up && down > 0 ? down : 0;
    if (i <= n) { sTr += tr[i]; sPlus += pdm; sMinus += mdm; if (i < n) continue; }
    else { sTr = sTr - sTr / n + tr[i]; sPlus = sPlus - sPlus / n + pdm; sMinus = sMinus - sMinus / n + mdm; }
    plus[i] = sTr === 0 ? 0 : 100 * sPlus / sTr; minus[i] = sTr === 0 ? 0 : 100 * sMinus / sTr;
    const sum = plus[i] + minus[i]; dx[i] = sum === 0 ? 0 : 100 * Math.abs(plus[i] - minus[i]) / sum;
  }
  return { plus, minus, adx: rmaArr(dx, n) };
}
export const adx = (c, { period }) => toPoints(c, dmiArrays(c, period).adx);
export function dmi(c, { period }) { const r = dmiArrays(c, period); return { plus: toPoints(c, r.plus), minus: toPoints(c, r.minus) }; }
export function cci(c, { period }) {
  const tp = hlc3(c), mean = smaArr(tp, period), out = NaNs(c.length);
  for (let i = period - 1; i < c.length; i++) {
    let dev = 0; for (let k = i - period + 1; k <= i; k++) dev += Math.abs(tp[k] - mean[i]);
    dev /= period; out[i] = dev === 0 ? 0 : (tp[i] - mean[i]) / (0.015 * dev);
  }
  return toPoints(c, out);
}
export function roc(c, { period, source: s }) { const x = source(c, s); return toPoints(c, x.map((v, i) => i >= period && x[i - period] !== 0 ? 100 * (v - x[i - period]) / x[i - period] : NaN)); }
export function momentum(c, { period, source: s }) { const x = source(c, s); return toPoints(c, x.map((v, i) => i >= period ? v - x[i - period] : NaN)); }
export function williamsR(c, { period }) {
  const highs = c.map(b => b.high), lows = c.map(b => b.low);
  return toPoints(c, c.map((bar, i) => { if (i < period - 1) return NaN; const hh = highest(highs, period, i), ll = lowest(lows, period, i); return hh === ll ? -50 : -100 * (hh - bar.close) / (hh - ll); }));
}
export function awesome(c, { fast, slow }) {
  const m = hl2(c), f = smaArr(m, fast), s = smaArr(m, slow), ao = f.map((v, i) => v - s[i]);
  return toPoints(c, ao, i => i > 0 && Number.isFinite(ao[i - 1]) && ao[i] < ao[i - 1] ? '#f23645' : '#089981');
}
export function trix(c, { period }) {
  const e3 = emaArr(emaArr(emaArr(closes(c), period), period), period);
  return toPoints(c, e3.map((v, i) => i > 0 && Number.isFinite(e3[i - 1]) && e3[i - 1] !== 0 ? 100 * (v - e3[i - 1]) / e3[i - 1] : NaN));
}
export function ultimate(c, { fast, medium, slow }) {
  const bp = c.map((b, i) => b.close - Math.min(b.low, i ? c[i - 1].close : b.low));
  const tr = c.map((b, i) => Math.max(b.high, i ? c[i - 1].close : b.high) - Math.min(b.low, i ? c[i - 1].close : b.low));
  const avg = (n, i) => { let a = 0, t = 0; for (let k = i - n + 1; k <= i; k++) { a += bp[k]; t += tr[k]; } return t === 0 ? 0 : a / t; };
  return toPoints(c, c.map((_, i) => i < slow ? NaN : 100 * (4 * avg(fast, i) + 2 * avg(medium, i) + avg(slow, i)) / 7));
}
export function aroon(c, { period }) {
  const up = NaNs(c.length), down = NaNs(c.length);
  for (let i = period; i < c.length; i++) {
    let hi = i - period, lo = i - period;
    for (let k = i - period; k <= i; k++) { if (c[k].high >= c[hi].high) hi = k; if (c[k].low <= c[lo].low) lo = k; }
    up[i] = 100 * (period - (i - hi)) / period; down[i] = 100 * (period - (i - lo)) / period;
  }
  return { up: toPoints(c, up), down: toPoints(c, down) };
}
export function cmo(c, { period }) {
  const x = closes(c);
  return toPoints(c, x.map((_, i) => {
    if (i < period) return NaN;
    let up = 0, down = 0; for (let k = i - period + 1; k <= i; k++) { const d = x[k] - x[k - 1]; if (d > 0) up += d; else down -= d; }
    return up + down === 0 ? 0 : 100 * (up - down) / (up + down);
  }));
}
// Causal (non-centred) DPO: close[i − (N/2 + 1)] − SMA(N)[i]. The centred
// textbook form would read future bars and is not offered.
export function dpo(c, { period }) {
  const x = closes(c), ma = smaArr(x, period), back = Math.floor(period / 2) + 1;
  return toPoints(c, x.map((_, i) => i >= back && Number.isFinite(ma[i]) ? x[i - back] - ma[i] : NaN));
}
export function tsi(c, { long, short, signal }) {
  const x = closes(c), m = x.map((v, i) => i ? v - x[i - 1] : NaN);
  const num = emaArr(emaArr(m, long), short), den = emaArr(emaArr(m.map(Math.abs), long), short);
  const t = num.map((v, i) => den[i] === 0 ? 0 : 100 * v / den[i]);
  return { tsi: toPoints(c, t), signal: toPoints(c, emaArr(t, signal)) };
}
export function vortex(c, { period }) {
  const tr = trueRange(c), plus = NaNs(c.length), minus = NaNs(c.length);
  for (let i = period; i < c.length; i++) {
    let vp = 0, vm = 0, t = 0;
    for (let k = i - period + 1; k <= i; k++) { vp += Math.abs(c[k].high - c[k - 1].low); vm += Math.abs(c[k].low - c[k - 1].high); t += tr[k]; }
    plus[i] = t === 0 ? 0 : vp / t; minus[i] = t === 0 ? 0 : vm / t;
  }
  return { plus: toPoints(c, plus), minus: toPoints(c, minus) };
}
// Ehlers Fisher Transform on hl2 (0.33/0.67 smoothing, clamp ±0.999).
export function fisher(c, { period }) {
  const m = hl2(c), fish = NaNs(c.length), trigger = NaNs(c.length);
  let value = 0, previous = 0;
  for (let i = period - 1; i < c.length; i++) {
    const hi = highest(m, period, i), lo = lowest(m, period, i);
    value = .66 * ((hi === lo ? .5 : (m[i] - lo) / (hi - lo)) - .5) + .67 * value;
    value = Math.max(-.999, Math.min(.999, value));
    const f = .5 * Math.log((1 + value) / (1 - value)) + .5 * previous;
    trigger[i] = previous; fish[i] = f; previous = f;
  }
  return { fisher: toPoints(c, fish), trigger: toPoints(c, trigger.map((v, i) => i > period - 1 ? v : NaN)) };
}
export function elderRay(c, { period }) {
  const e = emaArr(closes(c), period);
  return { bull: toPoints(c, c.map((b, i) => b.high - e[i]), (i, v) => v >= 0 ? '#089981' : '#f2364588'), bear: toPoints(c, c.map((b, i) => b.low - e[i]), (i, v) => v <= 0 ? '#f23645' : '#08998188') };
}
export function balanceOfPower(c, { smoothing }) {
  const raw = c.map(b => b.high === b.low ? 0 : (b.close - b.open) / (b.high - b.low));
  return toPoints(c, smoothing > 1 ? smaArr(raw, smoothing) : raw);
}
export function ppo(c, { fastPeriod, slowPeriod, signalPeriod }) {
  const x = closes(c), f = emaArr(x, fastPeriod), s = emaArr(x, slowPeriod);
  const line = f.map((v, i) => s[i] === 0 ? NaN : 100 * (v - s[i]) / s[i]), sig = emaArr(line, signalPeriod);
  const hist = line.map((v, i) => v - sig[i]);
  return { ppo: toPoints(c, line), signal: toPoints(c, sig), histogram: toPoints(c, hist, (i, v) => v >= 0 ? '#089981' : '#f23645') };
}
export function chandelier(c, { period, multiplier }) {
  const atr = atrArr(c, period), highs = c.map(b => b.high), lows = c.map(b => b.low), long = NaNs(c.length), short = NaNs(c.length);
  for (let i = period - 1; i < c.length; i++) if (Number.isFinite(atr[i])) { long[i] = highest(highs, period, i) - multiplier * atr[i]; short[i] = lowest(lows, period, i) + multiplier * atr[i]; }
  return { long: toPoints(c, long), short: toPoints(c, short) };
}
// Squeeze Momentum, LazyBear variant (pinned): BB(N, bbMult) vs KC(N, kcMult)
// using SMA basis and SMA of true range; momentum = linreg(close − mean(mean(HH, LL), SMA)).
export function squeeze(c, { period, bbMultiplier, kcMultiplier }) {
  const x = closes(c), basis = smaArr(x, period), dev = stdevArr(x, period), range = smaArr(trueRange(c), period);
  const highs = c.map(b => b.high), lows = c.map(b => b.low);
  const delta = x.map((v, i) => i >= period - 1 && Number.isFinite(basis[i]) ? v - ((highest(highs, period, i) + lowest(lows, period, i)) / 2 + basis[i]) / 2 : NaN);
  const mom = linregArr(delta, period);
  const momentumPoints = toPoints(c, mom, i => {
    const rising = i > 0 && Number.isFinite(mom[i - 1]) && mom[i] > mom[i - 1];
    return mom[i] >= 0 ? (rising ? '#26a69a' : '#b2dfdb') : (rising ? '#ffcdd2' : '#f23645');
  });
  const state = toPoints(c, basis.map((b, i) => Number.isFinite(b) && Number.isFinite(range[i]) ? 0 : NaN), i => {
    const on = basis[i] - bbMultiplier * dev[i] > basis[i] - kcMultiplier * range[i] && basis[i] + bbMultiplier * dev[i] < basis[i] + kcMultiplier * range[i];
    return on ? '#f8fafc' : '#64748b';
  });
  return { momentum: momentumPoints, squeeze: state };
}
export function regressionChannel(c, { period, deviations }) {
  const x = closes(c), mid = NaNs(c.length), up = NaNs(c.length), down = NaNs(c.length);
  for (let i = period - 1; i < c.length; i++) {
    const fit = linreg(x, period, i);
    let sq = 0; for (let k = 0; k < period; k++) sq += (x[i - period + 1 + k] - (fit.intercept + fit.slope * k)) ** 2;
    const sd = Math.sqrt(sq / period);
    mid[i] = fit.value; up[i] = fit.value + deviations * sd; down[i] = fit.value - deviations * sd;
  }
  return { basis: toPoints(c, mid), upper: toPoints(c, up), lower: toPoints(c, down) };
}
export function averageDailyRange(c, { period }) {
  const { days } = completedDays(c), out = [];
  const byDay = new Map(days.map((day, index) => [day.day, index]));
  for (let i = 0; i < c.length; i++) {
    const day = Math.floor(c[i].time / UTC_DAY), index = byDay.has(day) ? byDay.get(day) : days.length;
    if (index < period) continue;
    let sum = 0; for (let k = index - period; k < index; k++) sum += days[k].high - days[k].low;
    out.push({ time: c[i].time, value: sum / period });
  }
  return out;
}
export function natr(c, { period }) { const a = atrArr(c, period); return toPoints(c, a.map((v, i) => c[i].close === 0 ? NaN : 100 * v / c[i].close)); }
