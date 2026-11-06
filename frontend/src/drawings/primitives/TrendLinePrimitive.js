import { projectGeometry } from '../projectGeometry.js';
import { HORIZONTAL_LINE, VERTICAL_LINE, DRAWING_SPECS } from '../DrawingTypes.js';
import { drawingShapes } from '../drawingShapes.js';
import { dashFor, fontFor } from '../drawingStyle.js';

export function drawingEnv(source) {
  return {
    width: source.chart?.timeScale().width?.() ?? 0,
    height: source.chart?.paneSize?.().height ?? 0,
    priceToY: price => source.series?.priceToCoordinate(price),
    bars: source.bars, precision: source.precision ?? 3, tickSize: source.tickSize ?? 0.001,
  };
}
export function minimumAnchors(type) {
  const points = DRAWING_SPECS[type]?.points;
  return typeof points === 'number' ? Math.min(points, 2) : points?.min ?? 2;
}

// One official Series Primitive lifecycle, retained under its compatible Phase 5 name.
// Rendering is driven by drawingShapes() so style options apply uniformly.
class TrendLinePaneRenderer {
  constructor(view) { this.view = view; }
  draw(target) {
    const { projected, source } = this.view;
    const { model } = source;
    if (!model.visible || projected.length < minimumAnchors(model.type) || projected.some(p => p == null)) return;
    target.useMediaCoordinateSpace(({ context }) => {
      context.save();
      try {
        const { shapes, style } = drawingShapes(model, projected, drawingEnv(source));
        const width = style.lineWidth + (source.selected ? 1 : 0);
        const dash = source.draft ? [5, 4] : dashFor(style.lineStyle, style.lineWidth);
        context.globalAlpha = style.opacity;
        context.lineCap = 'round'; context.lineJoin = 'round';
        for (const shape of shapes) {
          if (shape.kind === 'text') { this.text(context, shape, source.selected); continue; }
          context.strokeStyle = shape.color ?? style.color;
          context.lineWidth = shape.width ?? width;
          context.setLineDash(shape.dash ?? dash);
          context.beginPath();
          if (shape.kind === 'lines') {
            for (const [from, to] of shape.segments) { context.moveTo(from.x, from.y); context.lineTo(to.x, to.y); }
          } else if (shape.kind === 'polygon' || shape.kind === 'path') {
            shape.points.forEach((point, index) => index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y));
            if (shape.kind === 'polygon') context.closePath();
          } else if (shape.kind === 'ellipse') {
            context.ellipse(shape.center.x, shape.center.y, Math.max(0, shape.rx), Math.max(0, shape.ry), shape.rotation ?? 0, 0, Math.PI * 2);
          } else if (shape.kind === 'arc') {
            context.arc(shape.center.x, shape.center.y, Math.max(0, shape.radius), shape.start, shape.end, shape.anticlockwise ?? false);
          }
          if (shape.fill) { context.fillStyle = shape.fill; context.fill(); }
          if (shape.stroke !== false) context.stroke();
        }
        if (source.selected && !source.draft) {
          context.setLineDash([]); context.lineWidth = 1.5; context.fillStyle = '#10141b'; context.strokeStyle = style.color; context.globalAlpha = 1;
          const handles = [HORIZONTAL_LINE, VERTICAL_LINE].includes(model.type) || DRAWING_SPECS[model.type]?.freehand ? [] : projected;
          for (const point of handles) {
            context.beginPath(); context.arc(point.x, point.y, 5, 0, Math.PI * 2);
            context.fill(); context.stroke();
          }
        }
      } finally { context.restore(); }
    });
  }
  text(context, shape, selected) {
    const { bounds, style, lines } = shape;
    context.setLineDash([]); context.font = fontFor(style); context.textBaseline = 'top';
    if (style.background && style.background !== 'none') { context.fillStyle = style.background; context.fillRect(bounds.x, bounds.y, bounds.width, bounds.height); }
    context.fillStyle = style.color;
    lines.forEach((line, index) => context.fillText(line, bounds.x + 6, bounds.y + 4 + index * bounds.lineHeight));
    if (style.frame && (selected || style.border)) { context.lineWidth = 1; context.strokeStyle = style.color; context.strokeRect(bounds.x, bounds.y, bounds.width, bounds.height); }
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
  precision = 3;
  tickSize = 0.001;
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
  setPrecision(precision) { this.precision = precision; this.requestUpdate?.(); }
  // No autoscaleInfo: annotations do not change the market's price-scale range.
}
