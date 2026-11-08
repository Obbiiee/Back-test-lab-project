import { TREND_LINE } from '../DrawingTypes.js';
import { CoreDrawing } from './CoreDrawing.js';

export function TrendLine(input) {
  if (!Array.isArray(input?.points) || input.points.length !== 2) {
    if (typeof input?.id !== 'string' || !input.id) throw new TypeError('Drawing requires an id');
    throw new TypeError('Trend Line requires exactly two anchors');
  }
  return CoreDrawing(TREND_LINE, input);
}
