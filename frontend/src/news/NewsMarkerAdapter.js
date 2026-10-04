import { bucketTime } from '../market/candles.js';
// Official series primitive, never the trading marker plugin or a price scale.
export function hasCandleTime(candles, time) {
  let lo = 0, hi = candles.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (candles[mid].time < time) lo = mid + 1; else hi = mid; }
  return candles[lo]?.time === time;
}
export function markerGroups(events, candles, timeframe, hasMinute, cursor) {
  const groups = new Map();
  for (const event of events) {
    const time = event.fields.schedule?.value;
    if (!Number.isFinite(time) || time > cursor || !hasMinute(time)) continue;
    const stamp = bucketTime(time, timeframe);
    if (!hasCandleTime(candles, stamp)) continue;
    if (!groups.has(stamp)) groups.set(stamp, []);
    groups.get(stamp).push(event);
  }
  return [...groups].sort((a, b) => a[0] - b[0]).map(([time, items]) => ({ time, events: items }));
}
export class NewsMarkerAdapter {
  constructor() {
    this.groups = []; this.coordinates = [];
    this.view = { zOrder: () => 'top', renderer: () => ({ draw: target => target.useMediaCoordinateSpace(({ context }) => {
      context.save(); context.font = '11px sans-serif'; context.textAlign = 'center';
      for (const marker of this.coordinates) { context.fillStyle = '#d9a94f'; context.beginPath(); context.arc(marker.x, marker.y, 8, 0, 2 * Math.PI); context.fill(); context.fillStyle = '#10141b'; context.fillText(marker.events.length > 1 ? String(marker.events.length) : 'N', marker.x, marker.y + 4); }
      context.restore();
    }) }) };
  }
  attached({ chart, requestUpdate }) { this.chart = chart; this.requestUpdate = requestUpdate; }
  detached() { this.chart = null; this.requestUpdate = null; this.coordinates = []; }
  updateAllViews() {
    const height = this.chart?.paneSize(0).height ?? 0;
    const projected = this.groups.map(group => ({ ...group, x: this.chart?.timeScale().timeToCoordinate(group.time), y: Math.max(10, height - 18) })).filter(item => Number.isFinite(item.x)).sort((a, b) => a.x - b.x || a.time - b.time);
    this.coordinates = [];
    for (const item of projected) {
      const previous = this.coordinates.at(-1);
      if (previous && item.x - previous.x < 18) previous.events.push(...item.events);
      else this.coordinates.push({ ...item, events: [...item.events] });
    }
  }
  paneViews() { return [this.view]; }
  replace(groups) { this.groups = groups; this.updateAllViews(); this.requestUpdate?.(); }
  hit(x, y) { return this.coordinates.find(item => Math.abs(item.x - x) <= 10 && Math.abs(item.y - y) <= 10); }
}
