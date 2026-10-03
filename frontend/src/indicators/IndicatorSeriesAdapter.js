import { LineSeries, HistogramSeries } from 'lightweight-charts';

export class IndicatorSeriesAdapter {
  #chart = null;
  #series = new Map();
  attach(chart) { if (chart === this.#chart) return; this.detach(); this.#chart = chart; }
  sync(config, spec, points) {
    if (!this.#chart) return;
    let series = this.#series.get(config.id);
    if (!series) {
      series = this.#chart.addSeries(spec.output === 'line' ? LineSeries : HistogramSeries,
        { priceLineVisible: false, lastValueVisible: false, visible: config.visible });
      this.#series.set(config.id, series);
    }
    series.applyOptions({ visible: config.visible });
    // Full replacement safely handles replay rewind, prepend and timeframe changes.
    series.setData(points);
  }
  remove(id) {
    const series = this.#series.get(id);
    if (series) { this.#series.delete(id); this.#chart.removeSeries(series); }
  }
  detach() { for (const id of this.#series.keys()) this.remove(id); this.#chart = null; }
}
