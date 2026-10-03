import { projectGeometry } from '../projectGeometry.js';
import { RECTANGLE, HORIZONTAL_LINE, VERTICAL_LINE } from '../DrawingTypes.js';

// Original application implementation of the official 5.2.1 ISeriesPrimitive
// lifecycle/view/renderer interfaces; references are recorded in the Phase 5 report.
class TrendLinePaneRenderer {
  constructor(view) { this.view = view; }
  draw(target) {
    const { projected, source } = this.view;
    if (!source.model.visible || projected.length < 2 || projected.some(p => p == null)) return;
    target.useMediaCoordinateSpace(({ context }) => {
      context.save();
      try {
        context.strokeStyle = source.model.options.color;
        context.lineWidth = source.model.options.lineWidth + (source.selected ? 1 : 0);
        context.lineCap = 'round';
        context.setLineDash(source.draft ? [5, 4] : []);
        context.beginPath();
        context.moveTo(projected[0].x, projected[0].y);
        if (source.model.type === RECTANGLE) {
          context.lineTo(projected[2].x, projected[2].y);
          context.lineTo(projected[1].x, projected[1].y);
          context.lineTo(projected[3].x, projected[3].y);
          context.closePath();
        } else context.lineTo(projected[1].x, projected[1].y);
        context.stroke();
        if (source.selected && !source.draft) {
          context.setLineDash([]); context.lineWidth = 1.5;
          context.fillStyle = '#10141b';
          const handles = [HORIZONTAL_LINE, VERTICAL_LINE].includes(source.model.type) ? [] : projected;
          for (const point of handles) {
            context.beginPath(); context.arc(point.x, point.y, 5, 0, Math.PI * 2);
            context.fill(); context.stroke();
          }
        }
      } finally { context.restore(); }
    });
  }
}

class TrendLinePaneView {
  projected = [];
  constructor(source) { this.source = source; this.paneRenderer = new TrendLinePaneRenderer(this); }
  zOrder() { return 'top'; }
  renderer() { return this.paneRenderer; }
  update() {
    const { chart, series, model, bars } = this.source;
    this.projected = projectGeometry(model, chart, series, bars);
  }
}

export class TrendLinePrimitive {
  chart = null;
  series = null;
  requestUpdate = null;
  selected = false;
  constructor(model, bars = [], draft = false) {
    this.model = model; this.bars = bars; this.draft = draft;
    this.views = [new TrendLinePaneView(this)];
  }
  attached({ chart, series, requestUpdate }) {
    this.chart = chart; this.series = series; this.requestUpdate = requestUpdate;
    this.updateAllViews(); requestUpdate();
  }
  detached() {
    this.chart = null; this.series = null; this.requestUpdate = null;
    this.views.forEach(view => { view.projected = []; });
  }
  paneViews() { return this.views; }
  updateAllViews() { this.views.forEach(view => view.update()); }
  setModel(model) { this.model = model; this.requestUpdate?.(); }
  setSelected(selected) { this.selected = selected; this.requestUpdate?.(); }
  setTimePoints(bars) { this.bars = bars; this.requestUpdate?.(); }
  // No autoscaleInfo: annotations do not change the market's price-scale range.
}
