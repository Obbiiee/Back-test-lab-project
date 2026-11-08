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

// Rendered series window (PR #36 memory gate). Indicators are still CALCULATED on the
// whole revealed prefix by IndicatorEngine; only what is handed to the chart is
// bounded to the visible time range plus a margin. Calculation history, warmup,
// confirmed fractals and repaint labels are therefore unchanged: a windowed series
// shows exactly the same values as the full series for every bar it contains, and
// it never contains a bar the full series does not (nothing past the last revealed bar).
// Most of the heap at 45k candles is the chart's own per-point storage (about 21 MB
// per output line), which this bounds. Series up to WINDOW_FROM_POINTS are handed over
// whole: at 5k candles a re-slice costs more frame time than the memory it saves.
export const WINDOW_FROM_POINTS = 12000;
export const WINDOW_MIN_POINTS = 4000; // smallest slice handed to the chart
const MARGIN_SPANS = 1;     // extra visible spans kept on each side
const GUARD_SPANS = 0.25;   // re-slice when the view comes this close to a window edge

const timeOf = point => point.time;
function lowerBound(data, time) { let lo = 0, hi = data.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (timeOf(data[mid]) < time) lo = mid + 1; else hi = mid; } return lo; }
function upperBound(data, time) { let lo = 0, hi = data.length; while (lo < hi) { const mid = (lo + hi) >> 1; if (timeOf(data[mid]) <= time) lo = mid + 1; else hi = mid; } return lo; }

// Points of `data` inside [from, to], widened to at least WINDOW_MIN_POINTS around it.
export function windowSlice(data, bounds) {
  if (!bounds || data.length <= WINDOW_FROM_POINTS || typeof timeOf(data[0]) !== 'number') return data;
  let lo = lowerBound(data, bounds.from), hi = upperBound(data, bounds.to);
  const missing = WINDOW_MIN_POINTS - (hi - lo);
  if (missing > 0) { lo = Math.max(0, lo - Math.ceil(missing / 2)); hi = Math.min(data.length, lo + WINDOW_MIN_POINTS); lo = Math.max(0, hi - WINDOW_MIN_POINTS); }
  return lo === 0 && hi === data.length ? data : data.slice(lo, hi);
}

export class IndicatorSeriesAdapter {
  #chart = null;
  #series = new Map();
  #panes = new Map();
  #references = new Map();
  #full = new Map();      // series -> complete prepared points (shared with the engine output)
  #bounds = null;         // {from, to} in chart time, or null = latest WINDOW_MIN_POINTS
  #frame = 0;
  #onRange = () => {
    if (this.#frame) return;
    const schedule = globalThis.requestAnimationFrame ?? (callback => setTimeout(callback, 16));
    let ran = false;
    const id = schedule(() => { ran = true; this.#frame = 0; this.#refresh(); });
    if (!ran) this.#frame = id; // a synchronous scheduler already ran it
  };
  attach(chart) {
    if (chart === this.#chart) return;
    this.detach(); this.#chart = chart;
    chart.timeScale?.().subscribeVisibleTimeRangeChange?.(this.#onRange);
  }
  #visible() {
    const range = this.#chart?.timeScale?.().getVisibleRange?.();
    return range && typeof range.from === 'number' && typeof range.to === 'number' ? range : null;
  }
  #nextWindow() {
    const visible = this.#visible();
    if (!visible) return null;
    const span = Math.max(1, visible.to - visible.from);
    return { from: visible.from - span * MARGIN_SPANS, to: visible.to + span * MARGIN_SPANS, guard: span * GUARD_SPANS, visible };
  }
  #longest() { let best = null; for (const data of this.#full.values()) if (!best || data.length > best.length) best = data; return best; }
  // The bounds actually held by the chart, read from the longest series' slice (the
  // minimum-size widening makes them wider than the request). An open edge means the
  // slice reaches the first/last point, so moving towards it never needs a re-slice.
  #coverFor(next) {
    const reference = this.#longest();
    const slice = next ? windowSlice(reference, next) : reference.slice(-WINDOW_MIN_POINTS);
    return { from: slice[0] === reference[0] ? -Infinity : timeOf(slice[0]), to: slice.at(-1) === reference.at(-1) ? Infinity : timeOf(slice.at(-1)), points: slice.length };
  }
  #needsRefresh(next) {
    const cover = this.#bounds;
    if (!cover) return true;
    const { visible, guard } = next;
    if (visible.from < cover.from + guard || visible.to > cover.to - guard) return true;
    // Zoomed far in after a wide view: shrink again so memory comes back.
    const reference = this.#longest();
    const wanted = Math.max(WINDOW_MIN_POINTS, upperBound(reference, next.to) - lowerBound(reference, next.from));
    return cover.points > wanted * 3;
  }
  #refresh() {
    if (!this.#chart || !(this.#longest()?.length > WINDOW_FROM_POINTS)) return;
    const next = this.#nextWindow();
    if (!next || !this.#needsRefresh(next)) return;
    this.#bounds = { ...this.#coverFor(next), reference: this.#longest() };
    for (const [series, data] of this.#full) if (data.length > WINDOW_FROM_POINTS) series.setData(windowSlice(data, this.#bounds));
  }
  #render(series, data) {
    this.#full.set(series, data);
    if (data.length <= WINDOW_FROM_POINTS || !this.#chart.timeScale) { series.setData(data); return; }
    if (!this.#bounds || this.#bounds.reference !== this.#longest()) this.#bounds = { ...this.#coverFor(this.#nextWindow()), reference: this.#longest() };
    series.setData(windowSlice(data, this.#bounds));
  }
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
        this.#render(series, output.outputType === 'histogram' ? histogramPoints(data, outputStyle(spec, config, output)) : data);
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
    for (const [key, series] of owned) { this.#chart.removeSeries(series); this.#full.delete(series); owned.delete(key); }
    const pane = this.#panes.get(id);
    if (pane) {
      // Pane handles derive the current index after any sibling removal/reindex.
      this.#chart.removePane(pane.paneIndex());
      this.#panes.delete(id);
    }
    this.#series.delete(id);
  }
  detach() {
    for (const id of this.#series.keys()) this.remove(id);
    this.#chart?.timeScale?.().unsubscribeVisibleTimeRangeChange?.(this.#onRange);
    if (this.#frame) (globalThis.cancelAnimationFrame ?? clearTimeout)(this.#frame);
    this.#frame = 0; this.#bounds = null; this.#chart = null;
  }
}
