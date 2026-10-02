import { projectTimestamp } from '../timeCoordinates.js';

// Original application implementation of the official 5.2.1 ISeriesPrimitive
// lifecycle/view/renderer interfaces; references are recorded in the Phase 5 report.
class TrendLinePaneRenderer {
  constructor(view) { this.view = view; }
  draw(target) {
    const { projected, source } = this.view;
    if (!source.model.visible || projected.length !== 2 || projected.some(p => p == null)) return;
    target.useMediaCoordinateSpace(({ context }) => {
      context.save();
      try {
        context.strokeStyle = source.model.options.color;
        context.lineWidth = source.model.options.lineWidth;
        context.lineCap = 'round';
        context.setLineDash(source.draft ? [5, 4] : []);
        context.beginPath();
        context.moveTo(projected[0].x, projected[0].y);
        context.lineTo(projected[1].x, projected[1].y);
        context.stroke();
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
    this.projected = !chart || !series ? [] : model.points.map(point => {
      const x = projectTimestamp(chart.timeScale(), bars, point.time);
      const y = series.priceToCoordinate(point.price);
      return x == null || y == null || !Number.isFinite(x + y) ? null : { x, y };
    });
  }
}

export class TrendLinePrimitive {
  chart = null;
  series = null;
  requestUpdate = null;
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
  setTimePoints(bars) { this.bars = bars; this.requestUpdate?.(); }
  // No autoscaleInfo: annotations do not change the market's price-scale range.
}
