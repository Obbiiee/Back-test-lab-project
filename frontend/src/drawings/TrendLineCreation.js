import { TREND_LINE, DRAWING_SPECS, TEXT } from './DrawingTypes.js';
import { pointFromPointer } from './timeCoordinates.js';

// Shared transient one/two-click creation workflow. Defaults preserve Trend Line callers.
export class TrendLineCreation {
  anchor = null;
  textPending = false;
  constructor(manager, chart, series, bars, timeframe, onComplete, type = TREND_LINE, onTextRequest = null) {
    Object.assign(this, { manager, chart, series, bars, timeframe, onComplete, type, onTextRequest });
  }
  input(points, id) {
    return { id, type: this.type, points, metadata: { createdOnTimeframe: this.timeframe } };
  }
  click = param => {
    const point = pointFromPointer(this.chart, this.series, param, this.bars);
    if (!point) return;
    if (this.type === TEXT) {
      if (!this.textPending) { this.textPending = true; this.onTextRequest?.(point); }
      return;
    }
    if (DRAWING_SPECS[this.type].points === 1) {
      const object = this.manager.add(this.input([point], crypto.randomUUID()));
      this.onComplete?.(object); return;
    }
    if (!this.anchor) {
      this.anchor = point;
      this.manager.startDraft(this.input([point, point], 'draft-' + this.type));
      return;
    }
    const object = this.manager.add(this.input([this.anchor, point], crypto.randomUUID()));
    this.cancel(); this.onComplete?.(object);
  };
  move = param => {
    if (!this.anchor) return;
    const point = pointFromPointer(this.chart, this.series, param, this.bars);
    if (point) this.manager.updateDraft(this.input([this.anchor, point], 'draft-' + this.type));
  };
  cancel() { this.textPending = false; this.anchor = null; this.manager.cancelDraft(); }
}
