import { canonicalPoint, DRAWING_SPECS, TEXT } from '../DrawingTypes.js';
// A shared immutable schema; each registered type enforces its own anchor count.
export function CoreDrawing(type, { id, points, options = {}, visible = true, locked = false, metadata = {}, text }) {
  if (typeof id !== 'string' || !id) throw new TypeError('Drawing requires an id');
  const spec = DRAWING_SPECS[type];
  if (!spec || !Array.isArray(points) || points.length !== spec.points) throw new TypeError('Invalid drawing anchor count');
  const width = options.lineWidth ?? 2;
  if (!Number.isFinite(width) || width < 1 || width > 10) throw new TypeError('Invalid line width');
  if (type === TEXT && (typeof text !== 'string' || !text.trim() || text.length > 2000)) throw new TypeError('Text requires 1–2000 characters');
  return Object.freeze({ id, type, ...(type === TEXT ? { text } : {}), points: Object.freeze(points.map(canonicalPoint)),
    options: Object.freeze({ color: typeof options.color === 'string' ? options.color : '#58a6ff', lineWidth: width }),
    visible: Boolean(visible), locked: Boolean(locked),
    metadata: Object.freeze(typeof metadata.createdOnTimeframe === 'string' ? { createdOnTimeframe: metadata.createdOnTimeframe } : {}),
  });
}
