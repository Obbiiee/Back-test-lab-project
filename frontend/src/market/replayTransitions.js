import { bucketTime } from './candles.js';

// Cursor algorithm preserves the existing bucket-end forward / bucket-start
// backward semantics, including the first backward click within a bucket.
export function advanceReplayIndex(bars, index, timeframe, direction = 1) {
  if (index < 0) return index;
  const bucket = bucketTime(bars[index].time, timeframe);
  let next = index;
  if (direction > 0) {
    while (next < bars.length - 1 && bucketTime(bars[next].time, timeframe) === bucket) next++;
    const nextBucket = bucketTime(bars[next].time, timeframe);
    while (next < bars.length - 1 && bucketTime(bars[next + 1].time, timeframe) === nextBucket) next++;
  } else {
    next = Math.max(0, next - 1);
    const previous = bucketTime(bars[next].time, timeframe);
    while (next > 0 && bucketTime(bars[next - 1].time, timeframe) === previous) next--;
  }
  return next;
}

// Revealed arrays are authoritative. Hints cannot authorize a changed historical prefix.
const fields = ['time', 'open', 'high', 'low', 'close', 'volume'];
export function sameCandle(a, b) {
  return !!a && !!b && fields.every(key => (key === 'volume' ? a[key] ?? 0 : a[key]) === (key === 'volume' ? b[key] ?? 0 : b[key]));
}
export function forwardChange(previous, next, hint) {
  if (hint?.kind !== 'forward' || !previous.length || next.length < previous.length) return null;
  // Only the previous latest bucket may change. All earlier values must match.
  for (let i = 0; i < previous.length - 1; i++) if (!sameCandle(previous[i], next[i])) return null;
  const from = previous.length - 1;
  if (previous[from].time !== next[from]?.time) return null;
  for (let i = from; i < next.length; i++) {
    if (!fields.slice(0, 5).every(key => Number.isFinite(next[i][key])) ||
        (i && next[i].time <= next[i - 1].time)) return null;
  }
  return { from: sameCandle(previous[from], next[from]) ? from + 1 : from, appendOnly: sameCandle(previous[from], next[from]) };
}
export function syncCandleSeries(series, previous, next, hint) {
  const change = forwardChange(previous, next, hint);
  if (change) {
    try { for (let i = change.from; i < next.length; i++) series.update(next[i]); return 'incremental'; }
    catch { /* Recover the complete authoritative dataset after any partial update. */ }
  }
  series.setData(next);
  return 'full';
}
