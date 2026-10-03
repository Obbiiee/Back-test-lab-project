import { performance } from 'node:perf_hooks';
import { syncCandleSeries } from '../src/market/replayTransitions.js';
import { IndicatorEngine } from '../src/indicators/IndicatorEngine.js';
import { productionRegistry } from '../src/indicators/productionRegistry.js';

const bars = Array.from({ length: 5100 }, (_, i) => ({ time: 1700000000 + i * 60, open: 2000 + i / 100, high: 2002 + i / 100, low: 1998 + i / 100, close: 2000 + i / 100 + Math.sin(i), volume: i % 100 }));
const adapter = { attach() {}, detach() {}, remove() {}, sync() {} };
const engine = new IndicatorEngine(productionRegistry, adapter);
for (const type of productionRegistry.types()) engine.create({ id: type, type });
let full = 0, incremental = 0, indicatorFull = 0;
// API-count instrumentation only: this does not pretend to measure browser rendering.
const series = { setData() { full++; }, update() { incremental++; } };
let previous = bars.slice(0, 5000); syncCandleSeries(series, [], previous);
const samples = [];
for (let end = 5001; end <= 5100; end++) {
  const next = bars.slice(0, end), start = performance.now();
  syncCandleSeries(series, previous, next, { kind: 'forward' }); engine.setCandles(next); indicatorFull += 7;
  samples.push(performance.now() - start); previous = next;
}
samples.sort((a, b) => a - b); const total = samples.reduce((a, b) => a + b, 0);
console.log(JSON.stringify({ history: 5000, steps: 100, indicators: 7, totalMs: +total.toFixed(2), averageStepMs: +(total / samples.length).toFixed(2), p95StepMs: +samples[Math.ceil(samples.length * .95) - 1].toFixed(2), chartFullReplacements: full, chartIncrementalUpdates: incremental, referenceChartFullReplacements: 101, indicatorFullRecomputes: indicatorFull, indicatorIncrementalCalculations: 0, note: 'CPU calculation + prefix validation; mock series API counts. No browser FPS or comparative wall-clock speedup claim; timing is non-gating.' }, null, 2));
engine.dispose();
