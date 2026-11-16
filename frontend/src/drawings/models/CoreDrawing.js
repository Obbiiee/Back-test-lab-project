import { canonicalPoint, DRAWING_SPECS } from '../DrawingTypes.js';
import { normalizeOptions } from '../drawingStyle.js';
// A shared immutable schema; each registered type enforces its own anchor count.
// Optional keys (style options, name) are stored only when set, so records
// written before Issue #21 keep their exact canonical shape.
export function CoreDrawing(type, { id, points, options = {}, visible = true, locked = false, metadata = {}, text, name }) {
  if (typeof id !== 'string' || !id) throw new TypeError('Drawing requires an id');
  const spec = DRAWING_SPECS[type];
  const count = spec?.points;
  const anchorsOk = Array.isArray(points) && (typeof count === 'number' ? points.length === count
    : points.length >= count.min && points.length <= count.max);
  if (!spec || !anchorsOk) throw new TypeError('Invalid drawing anchor count');
  if (spec.text && (typeof text !== 'string' || !text.trim() || text.length > 2000)) throw new TypeError('Text requires 1–2000 characters');
  if (name !== undefined && (typeof name !== 'string' || name.length > 64)) throw new TypeError('Invalid drawing name');
  return Object.freeze({ id, type, ...(spec.text ? { text } : {}), ...(name ? { name } : {}), points: Object.freeze(points.map(canonicalPoint)),
    options: normalizeOptions(options),
    visible: Boolean(visible), locked: Boolean(locked),
    metadata: Object.freeze(typeof metadata.createdOnTimeframe === 'string' ? { createdOnTimeframe: metadata.createdOnTimeframe } : {}),
  });
}
