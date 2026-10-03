import { canonicalPoint, CORE_DRAWINGS } from '../DrawingTypes.js';
// A shared immutable schema; each registered type enforces its own anchor count.
export function CoreDrawing(type, { id, points, options = {}, visible = true, locked = false, metadata = {} }) {
  if (typeof id !== 'string' || !id) throw new TypeError('Drawing requires an id');
  const spec = CORE_DRAWINGS[type];
  if (!spec || !Array.isArray(points) || points.length !== spec.points) throw new TypeError('Invalid drawing anchor count');
  const width = options.lineWidth ?? 2;
  if (!Number.isFinite(width) || width < 1 || width > 10) throw new TypeError('Invalid line width');
  return Object.freeze({ id, type, points: Object.freeze(points.map(canonicalPoint)),
    options: Object.freeze({ color: typeof options.color === 'string' ? options.color : '#58a6ff', lineWidth: width }),
    visible: Boolean(visible), locked: Boolean(locked),
    metadata: Object.freeze(typeof metadata.createdOnTimeframe === 'string' ? { createdOnTimeframe: metadata.createdOnTimeframe } : {}),
  });
}
