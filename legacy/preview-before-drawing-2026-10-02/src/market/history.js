import { aggregateCandles, bucketTime, TIMEFRAMES } from './candles.js';

export function parseHistDataCSV(csv) {
  const bars = new Map();
  for (const line of csv.trim().split(/\r?\n/)) {
    const [stamp, o, h, l, c] = line.split(';');
    const parts = /^(\d{4})(\d{2})(\d{2}) (\d{2})(\d{2})(\d{2})$/.exec(stamp);
    if (!parts) throw new Error('Invalid HistData M1 timestamp');
    // HistData uses fixed EST (UTC-5), without daylight-saving adjustments.
    const [, year, month, day, hour, minute, second] = parts.map(Number);
    const time = Date.UTC(year, month - 1, day, hour + 5, minute, second) / 1000;
    const bar = { time, open: Number(o), high: Number(h), low: Number(l), close: Number(c), volume: 0 };
    if (![time, bar.open, bar.high, bar.low, bar.close].every(Number.isFinite) || bar.low <= 0 || bar.low > Math.min(bar.open, bar.close) || bar.high < Math.max(bar.open, bar.close) || time % 60 !== 0) throw new Error('Invalid historical OHLC');
    bars.set(time, bar);
  }
  return [...bars.values()].sort((a, b) => a.time - b.time);
}

export function validateHistory(payload) {
  if (payload?.symbol !== 'XAUUSD' || !(payload.timeframe in TIMEFRAMES) || !Array.isArray(payload.candles) || !payload.candles.length) throw new Error('Riwayat XAU/USD tidak valid');
  let previous = -Infinity;
  for (const bar of payload.candles) {
    if (![bar.time, bar.open, bar.high, bar.low, bar.close].every(Number.isFinite) || bar.time <= previous || bar.time % 60 !== 0 || bar.low <= 0 || bar.low > Math.min(bar.open, bar.close) || bar.high < Math.max(bar.open, bar.close)) throw new Error('Candle historis tidak valid');
    previous = bar.time;
  }
  return payload;
}

export function decodeHistoryRows(rows, timeframe) {
  if (!Array.isArray(rows)) throw new Error('Invalid price data');
  const candles=rows.map(row=>({time:row[0],open:row[1],high:row[2],low:row[3],close:row[4],volume:0}));
  return validateHistory({symbol:'XAUUSD',timeframe,candles}).candles;
}

export function mergeHistory(history, live, timeframe) {
  const historical = aggregateCandles(history, timeframe), sampled = aggregateCandles(live, timeframe);
  const boundary = sampled.length ? bucketTime(sampled[0].time, timeframe) : null;
  // A whole aggregate candle belongs to one provider; never mix OHLC across feeds.
  const prior = boundary == null ? historical : historical.filter(bar => bar.time < boundary);
  const candles = [...prior, ...sampled];
  Object.defineProperty(candles, 'intervalSeconds', { value: sampled.intervalSeconds });
  return { candles, boundary, historicalCount: prior.length, liveCount: sampled.length,
    historicalEnd: prior.at(-1)?.time ?? null, liveStart: sampled[0]?.time ?? null };
}
