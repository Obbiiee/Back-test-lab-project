// App glue for numeric UTC timestamps absent from the chart's current data.
// Exact points use timeToCoordinate. Missing points interpolate between actual
// chart coordinates of bracketing times (with fractional logical weights);
// neither this projection nor timeframe changes mutate canonical timestamps.
export function logicalForTimestamp(bars, time) {
  if (!bars.length || !Number.isFinite(time)) return null;
  let low = 0, high = bars.length;
  while (low < high) {
    const mid = (low + high) >>> 1;
    if (bars[mid].time < time) low = mid + 1; else high = mid;
  }
  if (bars[low]?.time === time) return low;
  if (bars.length < 2) return null;
  const left = Math.max(0, Math.min(bars.length - 2, low - 1));
  const span = bars[left + 1].time - bars[left].time;
  return span > 0 ? left + (time - bars[left].time) / span : null;
}

export function projectTimestamp(scale, bars, time) {
  if (!bars.length) return null;
  const exact = scale.timeToCoordinate(time);
  if (exact != null) return exact;
  const logical = logicalForTimestamp(bars, time);
  if (logical == null || bars.length < 2) return null;
  const left = Math.max(0, Math.min(bars.length - 2, Math.floor(logical)));
  // Use actual chart coordinates of the bracketing timestamps, rather than
  // assuming this series' array indices equal the chart's global time indices.
  const x1 = scale.timeToCoordinate(bars[left].time);
  const x2 = scale.timeToCoordinate(bars[left + 1].time);
  return x1 == null || x2 == null ? null : x1 + (logical - left) * (x2 - x1);
}

export function pointFromPointer(chart, series, param, bars) {
  if (!param.point) return null;
  const scale = chart.timeScale();
  let time = param.time ?? scale.coordinateToTime(param.point.x);
  if (time == null && bars.length > 1) {
    const logical = scale.coordinateToLogical(param.point.x);
    if (logical == null) return null;
    const index = Math.max(0, Math.min(bars.length - 2, Math.floor(logical)));
    time = bars[index].time + (logical - index) * (bars[index + 1].time - bars[index].time);
  }
  const price = series.coordinateToPrice(param.point.y);
  return Number.isFinite(time) && Number.isFinite(price) ? { time, price } : null;
}
