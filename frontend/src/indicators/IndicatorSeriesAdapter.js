import { LineSeries, HistogramSeries } from 'lightweight-charts';

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
      if (spec.placement === 'pane' && !pane) {
        this.#chart.applyOptions({ layout: { panes: { enableResize: true, separatorColor: '#2a2c30', separatorHoverColor: '#58616f' } } });
        pane = this.#chart.addPane(true);
        this.#panes.set(config.id, pane);
        pane.setStretchFactor(0.35);
      }
      for (const output of spec.outputs) {
        let series = owned.get(output.key);
        if (!series) {
          series = this.#chart.addSeries(output.outputType === 'line' ? LineSeries : HistogramSeries,
            { ...output.options, priceLineVisible: false, lastValueVisible: false, visible: config.visible,
              ...(spec.range ? { autoscaleInfoProvider: () => ({ priceRange: { minValue: spec.range[0], maxValue: spec.range[1] } }) } : {}) },
            pane ? pane.paneIndex() : 0);
          owned.set(output.key, series);
        }
        series.applyOptions({ visible: config.visible });
        // Full replacement safely handles replay rewind, prepend and timeframe changes.
        series.setData(spec.output !== undefined ? points : points[output.key]);
      }
      if (spec.references.length && !this.#references.has(config.id)) {
        const series = owned.values().next().value, lines = [];
        this.#references.set(config.id, { series, lines });
        for (const price of spec.references) lines.push(series.createPriceLine({ price, color: '#747b87', lineWidth: 1,
          lineStyle: 2, lineVisible: config.visible, axisLabelVisible: false }));
      }
      for (const line of this.#references.get(config.id)?.lines ?? []) line.applyOptions({ lineVisible: config.visible });
    } catch (error) {
      this.remove(config.id); // Remove every output, including successfully updated siblings.
      throw error;
    }
  }
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
