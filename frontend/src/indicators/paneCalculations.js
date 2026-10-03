import { ema } from './overlayCalculations.js';

// Wilder seeds use an arithmetic mean, then (previous * (N - 1) + current) / N.
export function rsi(candles, { period }) {
  if (candles.length <= period) return [];
  let gain = 0, loss = 0;
  for (let index = 1; index <= period; index++) {
    const delta = candles[index].close - candles[index - 1].close;
    gain += Math.max(0, delta); loss += Math.max(0, -delta);
  }
  gain /= period; loss /= period;
  const value = () => loss === 0 ? (gain === 0 ? 50 : 100) : 100 - 100 / (1 + gain / loss);
  const points = [{ time: candles[period].time, value: value() }];
  for (let index = period + 1; index < candles.length; index++) {
    const delta = candles[index].close - candles[index - 1].close;
    gain = (gain * (period - 1) + Math.max(0, delta)) / period;
    loss = (loss * (period - 1) + Math.max(0, -delta)) / period;
    points.push({ time: candles[index].time, value: value() });
  }
  return points;
}

export function macd(candles, { fastPeriod, slowPeriod, signalPeriod }) {
  const fast = ema(candles, { period: fastPeriod }), slow = ema(candles, { period: slowPeriod });
  const macdLine = slow.map((point, index) => ({ time: point.time, value: fast[index + slowPeriod - fastPeriod].value - point.value }));
  // Signal uses the same SMA-seeded EMA convention on valid MACD values.
  const signal = ema(macdLine.map(point => ({ time: point.time, close: point.value })), { period: signalPeriod });
  const histogram = signal.map((point, index) => {
    const value = macdLine[index + signalPeriod - 1].value - point.value;
    return { time: point.time, value, color: value >= 0 ? '#089981' : '#f23645' };
  });
  return { macd: macdLine, signal, histogram };
}

export function atr(candles, { period }) {
  const points = [];
  let value = 0;
  for (let index = 0; index < candles.length; index++) {
    const bar = candles[index], previous = candles[index - 1];
    const tr = previous ? Math.max(bar.high - bar.low, Math.abs(bar.high - previous.close), Math.abs(bar.low - previous.close)) : bar.high - bar.low;
    if (index < period) value += tr;
    if (index === period - 1) value /= period;
    if (index >= period) value = (value * (period - 1) + tr) / period;
    if (index >= period - 1) points.push({ time: bar.time, value });
  }
  return points;
}

export function stochastic(candles, { kPeriod, dPeriod }) {
  const k = [], d = [];
  let sum = 0;
  for (let index = kPeriod - 1; index < candles.length; index++) {
    let low = Infinity, high = -Infinity;
    for (let offset = index - kPeriod + 1; offset <= index; offset++) {
      low = Math.min(low, candles[offset].low); high = Math.max(high, candles[offset].high);
    }
    const value = high === low ? 50 : Math.max(0, Math.min(100, 100 * (candles[index].close - low) / (high - low)));
    k.push({ time: candles[index].time, value }); sum += value;
    if (k.length > dPeriod) sum -= k[k.length - dPeriod - 1].value;
    if (k.length >= dPeriod) d.push({ time: candles[index].time, value: Math.max(0, Math.min(100, sum / dPeriod)) });
  }
  return { k, d };
}
