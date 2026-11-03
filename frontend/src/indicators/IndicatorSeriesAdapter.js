import { LineSeries, HistogramSeries } from 'lightweight-charts';
import { LINE_STYLE_IDS, effectivePlacement } from './indicatorValidation.js';
import { colorWithOpacity, outputStyle } from './indicatorStyle.js';

export { colorWithOpacity, outputStyle };

export function seriesOptions(spec, config, output) {
  const style = outputStyle(spec, config, output);
  const options = { visible: style.visible, color: colorWithOpacity(style.color, style.opacity) };
  if (output.outputType === 'line') Object.assign(options, { lineWidth: style.lineWidth, lineStyle: LINE_STYLE_IDS[style.lineStyle] });
  if (output.options?.markers) Object.assign(options, { lineVisible: false, pointMarkersVisible: true, pointMarkersRadius: Math.max(1.5, style.lineWidth) });
  if (output.options?.lineType !== undefined) options.lineType = output.options.lineType;
  return options;
}
function histogramPoints(points, style) {
  if (!style.positiveColor && !style.negativeColor && style.opacity >= 1) return points;
  return points.map(point => {
    const color = point.value >= 0 ? (style.positiveColor ?? point.color ?? style.color) : (style.negativeColor ?? point.color ?? style.color);
    return { ...point, color: colorWithOpacity(color, style.opacity) };
  });
}

export class IndicatorSeriesAdapter {
  #chart = null;
  #series = new Map();
  #panes = new Map();
  #references = new Map();
  attach(chart) { if (chart === this.#chart) return; this.detach(); this.#chart = chart; }
  sync(config, spec, points) {
    if (!this.#chart) return;
    let owned = this.#series.get(config.id);
    if (!owned) { owned = new Map(); this.#series.set(config.id, owned); }
    try {
      let pane = this.#panes.get(config.id);
      const placement = effectivePlacement(spec, config);
      if (placement === 'pane' && !pane) {
        this.#chart.applyOptions({ layout: { panes: { enableResize: true, separatorColor: '#2a2c30', separatorHoverColor: '#58616f' } } });
        pane = this.#chart.addPane(true);
        this.#panes.set(config.id, pane);
        pane.setStretchFactor(config.paneHeight ?? 0.35);
      }
      if (pane && config.paneHeight !== undefined && pane.getStretchFactor?.() !== config.paneHeight) pane.setStretchFactor(config.paneHeight);
      for (const output of spec.outputs) {
        let series = owned.get(output.key);
        const options = seriesOptions(spec, config, output);
        if (!series) {
          series = this.#chart.addSeries(output.outputType === 'line' ? LineSeries : HistogramSeries,
            { color: output.options.color, lineWidth: output.options.lineWidth, priceLineVisible: false, lastValueVisible: false, ...options,
              ...(spec.range ? { autoscaleInfoProvider: () => ({ priceRange: { minValue: spec.range[0], maxValue: spec.range[1] } }) } : {}) },
            pane ? pane.paneIndex() : 0);
          owned.set(output.key, series);
        }
        series.applyOptions(options);
        // Full replacement safely handles replay rewind, prepend and timeframe changes.
        const data = spec.output !== undefined ? points : points[output.key];
        series.setData(output.outputType === 'histogram' ? histogramPoints(data, outputStyle(spec, config, output)) : data);
      }
      const references = config.references ?? spec.references;
      const current = this.#references.get(config.id);
      if (current && current.key !== references.join(',')) {
        for (const line of current.lines) current.series.removePriceLine(line);
        this.#references.delete(config.id);
      }
      if (references.length && !this.#references.has(config.id)) {
        const series = owned.values().next().value, lines = [];
        this.#references.set(config.id, { series, lines, key: references.join(',') });
        for (const price of references) lines.push(series.createPriceLine({ price, color: '#747b87', lineWidth: 1,
          lineStyle: 2, lineVisible: config.visible, axisLabelVisible: false }));
      }
      for (const line of this.#references.get(config.id)?.lines ?? []) line.applyOptions({ lineVisible: config.visible });
    } catch (error) {
      this.remove(config.id); // Remove every output, including successfully updated siblings.
      throw error;
    }
  }
  // Pane order follows instance order; overlays stay on the price pane.
  order(ids) {
    if (!this.#chart) return;
    const panes = ids.map(id => this.#panes.get(id)).filter(Boolean);
    panes.forEach((pane, index) => { if (pane.paneIndex() !== index + 1 && typeof pane.moveTo === "function") pane.moveTo(index + 1); });
  }
  paneIndex(id) { return this.#panes.get(id)?.paneIndex() ?? (this.#series.has(id) ? 0 : null); }
  remove(id) {
    const owned = this.#series.get(id);
    if (!owned) return;
    const references = this.#references.get(id);
    if (references) {
      for (const line of references.lines) references.series.removePriceLine(line);
      this.#references.delete(id);
    }
    for (const [key, series] of owned) { this.#chart.removeSeries(series); owned.delete(key); }
    const pane = this.#panes.get(id);
    if (pane) {
      // Pane handles derive the current index after any sibling removal/reindex.
      this.#chart.removePane(pane.paneIndex());
      this.#panes.delete(id);
    }
    this.#series.delete(id);
  }
  detach() { for (const id of this.#series.keys()) this.remove(id); this.#chart = null; }
}
