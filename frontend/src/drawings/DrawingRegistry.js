import { TREND_LINE } from './DrawingTypes.js';
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
  return new DrawingRegistry().register(TREND_LINE, { model: TrendLine, primitive: (model, bars, draft) => new TrendLinePrimitive(model, bars, draft) });
}
