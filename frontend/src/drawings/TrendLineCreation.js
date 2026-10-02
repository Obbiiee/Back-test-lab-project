import { TREND_LINE } from './DrawingTypes.js';
import { pointFromPointer } from './timeCoordinates.js';

// Transient two-click workflow, not an editing/selection engine.
export class TrendLineCreation {
  anchor = null;
  constructor(manager, chart, series, bars, timeframe, onComplete) {
    Object.assign(this, { manager, chart, series, bars, timeframe, onComplete });
  }
  input(points, id) {
    return { id, type: TREND_LINE, points, metadata: { createdOnTimeframe: this.timeframe } };
  }
  click = param => {
    const point = pointFromPointer(this.chart, this.series, param, this.bars);
    if (!point) return;
    if (!this.anchor) {
      this.anchor = point;
      this.manager.startDraft(this.input([point, point], 'draft-trend-line'));
      return;
    }
    const object = this.manager.add(this.input([this.anchor, point], crypto.randomUUID()));
    this.cancel(); this.onComplete?.(object);
  };
  move = param => {
    if (!this.anchor) return;
    const point = pointFromPointer(this.chart, this.series, param, this.bars);
    if (point) this.manager.updateDraft(this.input([this.anchor, point], 'draft-trend-line'));
  };
  cancel() { this.anchor = null; this.manager.cancelDraft(); }
}
