import { projectGeometry } from '../projectGeometry.js';
import { RECTANGLE, HORIZONTAL_LINE, VERTICAL_LINE, FIBONACCI, ARROW, TEXT, MEASURE, RAY } from '../DrawingTypes.js';
import { fibonacciLevels, arrowHead, measurementLines, labelBounds } from '../advancedGeometry.js';
import {rayEnd} from '../rayGeometry.js';

// One official Series Primitive lifecycle, retained under its compatible Phase 5 name.
class TrendLinePaneRenderer {
  constructor(view) { this.view = view; }
  draw(target) {
    const { projected, source } = this.view;
    const { model } = source;
    if (!model.visible || projected.length < (model.type === TEXT ? 1 : 2) || projected.some(p => p == null)) return;
    target.useMediaCoordinateSpace(({ context }) => {
      context.save();
      try {
        context.strokeStyle = model.options.color;
        context.lineWidth = model.options.lineWidth + (source.selected ? 1 : 0);
        context.lineCap = 'round';
        context.setLineDash(source.draft ? [5, 4] : []);
        const [a,b] = projected;
        const segment = (from,to) => { context.moveTo(from.x,from.y); context.lineTo(to.x,to.y); };
        const label = (anchor,lines,background=true) => {
          const bounds = labelBounds(anchor,lines);
          context.setLineDash([]); context.font='12px monospace'; context.textBaseline='top';
          if(background) { context.fillStyle='#10141be8'; context.fillRect(bounds.x,bounds.y,bounds.width,bounds.height); }
          context.fillStyle=model.options.color;
          lines.forEach((line,index)=>context.fillText(line,bounds.x+6,bounds.y+4+index*16));
          if(source.selected && model.type===TEXT) context.strokeRect(bounds.x,bounds.y,bounds.width,bounds.height);
        };
        if (model.type === TEXT) label(a,model.text.split('\n'));
        else {
          context.beginPath();
          if (model.type === RECTANGLE) {
            context.moveTo(a.x,a.y); context.lineTo(projected[2].x,projected[2].y);
            context.lineTo(b.x,b.y); context.lineTo(projected[3].x,projected[3].y); context.closePath();
          } else {
            segment(a,model.type===RAY?rayEnd(a,b,source.chart.timeScale().width(),source.chart.paneSize().height):b);
            if(model.type===ARROW) for(const wing of arrowHead(a,b)) segment(b,wing);
            if(model.type===MEASURE) { segment(a,{x:b.x,y:a.y}); segment({x:b.x,y:a.y},b); }
          }
          context.stroke();
          if(model.type===FIBONACCI) {
            for(const level of fibonacciLevels(model.points)) {
              const y=source.series.priceToCoordinate(level.price);
              if(!Number.isFinite(y)) continue;
              context.beginPath();segment({x:a.x,y},{x:b.x,y});context.stroke();
              label({x:Math.max(a.x,b.x),y},[level.ratio+' · '+level.price.toFixed(3)],false);
              context.setLineDash(source.draft?[5,4]:[]);
            }
          }
          if(model.type===MEASURE) label({x:(a.x+b.x)/2,y:(a.y+b.y)/2},measurementLines(model.points,source.bars));
        }
        if (source.selected && !source.draft) {
          context.setLineDash([]); context.lineWidth = 1.5; context.fillStyle = '#10141b';
          const handles = [HORIZONTAL_LINE, VERTICAL_LINE].includes(model.type) ? [] : projected;
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
