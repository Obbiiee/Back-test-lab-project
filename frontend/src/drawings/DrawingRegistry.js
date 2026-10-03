import { TREND_LINE, HORIZONTAL_LINE, VERTICAL_LINE, RECTANGLE, ADVANCED_DRAWINGS } from './DrawingTypes.js';
import { CoreDrawing } from './models/CoreDrawing.js';
import { TrendLine } from './models/TrendLine.js';
import { TrendLinePrimitive } from './primitives/TrendLinePrimitive.js';

export class DrawingRegistry {
  entries = new Map();
  register(type, definition) {
    if (this.entries.has(type)) throw new Error('Drawing type already registered: ' + type);
    if (typeof definition?.model !== 'function' || typeof definition?.primitive !== 'function') throw new TypeError('Invalid drawing definition');
    this.entries.set(type, definition);
    return this;
  }
  get(type) {
    if (!this.entries.has(type)) throw new Error('Unknown drawing type: ' + type);
    return this.entries.get(type);
  }
}
export function createDrawingRegistry() {
  const primitive = (model, bars, draft) => new TrendLinePrimitive(model, bars, draft);
  const registry = new DrawingRegistry().register(TREND_LINE, { model: TrendLine, primitive });
  for (const type of [HORIZONTAL_LINE, VERTICAL_LINE, RECTANGLE, ...Object.keys(ADVANCED_DRAWINGS)]) registry.register(type, { model: input => CoreDrawing(type, input), primitive });
  return registry;
}
