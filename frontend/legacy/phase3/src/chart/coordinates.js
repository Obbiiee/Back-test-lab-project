// Shared chart coordinates. No drawing or trading lifecycle dependencies.
export function timeAtLogical(candles, logical) {
  if (!candles.length || logical == null) return null;
  const index = Math.round(logical);
  const step = candles.intervalSeconds ?? (candles.length > 1 ? candles[1].time - candles[0].time : 1800);
  if (index < 0) return candles[0].time + index * step;
  if (index >= candles.length) return candles.at(-1).time + (index - candles.length + 1) * step;
  return candles[index].time;
}
export function logicalAtTime(candles, time) {
  if (!candles.length) return null;
  const step = candles.intervalSeconds ?? (candles.length > 1 ? candles[1].time - candles[0].time : 1800);
  if (time < candles[0].time) return (time - candles[0].time) / step;
  if (time > candles.at(-1).time) return candles.length - 1 + (time - candles.at(-1).time) / step;
  let left = 0, right = candles.length - 1;
  while (left < right) { const mid = Math.floor((left + right) / 2); if (candles[mid].time < time) left = mid + 1; else right = mid; }
  if (candles[left].time === time || !left) return left;
  return left - 1 + (time - candles[left - 1].time) / (candles[left].time - candles[left - 1].time);
}
