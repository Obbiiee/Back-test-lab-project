import { LineSeries, HistogramSeries } from 'lightweight-charts';

export class IndicatorSeriesAdapter {
  #chart = null;
  #series = new Map();
  attach(chart) { if (chart === this.#chart) return; this.detach(); this.#chart = chart; }
  sync(config, spec, points) {
    if (!this.#chart) return;
    let owned = this.#series.get(config.id);
    if (!owned) { owned = new Map(); this.#series.set(config.id, owned); }
    try {
      for (const output of spec.outputs) {
        let series = owned.get(output.key);
        if (!series) {
          series = this.#chart.addSeries(output.outputType === 'line' ? LineSeries : HistogramSeries,
            { ...output.options, priceLineVisible: false, lastValueVisible: false, visible: config.visible });
          owned.set(output.key, series);
        }
        series.applyOptions({ visible: config.visible });
        // Full replacement safely handles replay rewind, prepend and timeframe changes.
        series.setData(spec.output !== undefined ? points : points[output.key]);
      }
    } catch (error) {
      this.remove(config.id); // Remove every output, including successfully updated siblings.
      throw error;
    }
  }
  remove(id) {
    const owned = this.#series.get(id);
    if (!owned) return;
    for (const [key, series] of owned) { this.#chart.removeSeries(series); owned.delete(key); }
    this.#series.delete(id);
  }
  detach() { for (const id of this.#series.keys()) this.remove(id); this.#chart = null; }
}
