import { canonicalPoint, TREND_LINE } from '../DrawingTypes.js';

export function TrendLine({ id, points, options = {}, visible = true, locked = false, metadata = {} }) {
  if (typeof id !== 'string' || !id) throw new TypeError('Drawing requires an id');
  if (!Array.isArray(points) || points.length !== 2) throw new TypeError('Trend Line requires exactly two anchors');
  const width = options.lineWidth ?? 2;
  if (!Number.isFinite(width) || width < 1 || width > 10) throw new TypeError('Invalid line width');
  return Object.freeze({
    id, type: TREND_LINE, points: Object.freeze(points.map(canonicalPoint)),
    options: Object.freeze({ color: typeof options.color === 'string' ? options.color : '#58a6ff', lineWidth: width }),
    visible: Boolean(visible), locked: Boolean(locked),
    metadata: Object.freeze(typeof metadata.createdOnTimeframe === 'string' ? { createdOnTimeframe: metadata.createdOnTimeframe } : {}),
  });
}
