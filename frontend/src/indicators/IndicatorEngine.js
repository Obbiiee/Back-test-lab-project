import { defaultIndicatorRegistry } from './IndicatorRegistry.js';
import { instanceConfig, revealedInput, normalizedIndicatorOutput, emptyIndicatorOutput } from './indicatorValidation.js';
import { IndicatorSeriesAdapter } from './IndicatorSeriesAdapter.js';

export class IndicatorEngine {
  #registry;
  #adapter;
  #instances = new Map();
  #outputs = new Map();
  #errors = new Map();
  #candles = Object.freeze([]);
  #disposed = false;
  constructor(registry = defaultIndicatorRegistry, adapter = new IndicatorSeriesAdapter()) { this.#registry = registry; this.#adapter = adapter; }
  #active() { if (this.#disposed) throw Error('Indicator engine disposed'); }
  #run(config) {
    try {
      const spec = this.#registry.get(config.type);
      const points = normalizedIndicatorOutput(spec, this.#candles.length < spec.warmup ? emptyIndicatorOutput(spec) : spec.calculate(this.#candles, config.parameters), this.#candles);
      this.#adapter.sync(config, spec, points);
      this.#outputs.set(config.id, points); this.#errors.delete(config.id);
    } catch (error) {
      this.#outputs.set(config.id, emptyIndicatorOutput(this.#registry.get(config.type))); this.#errors.set(config.id, String(error?.message ?? error));
      // Never leave stale output after a failed calculation/adapter update.
      try { this.#adapter.remove(config.id); } catch { /* retain original instance error */ }
    }
  }
  create(value) {
    this.#active(); const config = instanceConfig(this.#registry, value);
    if (this.#instances.has(config.id)) throw Error('Duplicate indicator ID');
    this.#instances.set(config.id, config); this.#run(config); return config;
  }
  update(id, patch) {
    this.#active(); const current = this.#instances.get(id);
    if (!current || !patch || Object.keys(patch).some(key => !['parameters', 'visible'].includes(key))) throw Error('Invalid instance update');
    const config = instanceConfig(this.#registry, { ...current, ...patch });
    this.#instances.set(id, config); this.#run(config); return config;
  }
  replaceInstances(values) {
    this.#active(); if (!Array.isArray(values)) throw Error('Invalid instances');
    const configs = values.map(value => instanceConfig(this.#registry, value));
    if (new Set(configs.map(config => config.id)).size !== configs.length) throw Error('Duplicate indicator ID');
    for (const id of this.#instances.keys()) if (!configs.some(config => config.id === id)) this.remove(id);
    for (const config of configs) {
      const previous = this.#instances.get(config.id);
      if (previous && previous.type !== config.type) this.#adapter.remove(config.id);
      this.#instances.set(config.id, config); this.#run(config);
    }
  }
  setCandles(candles) {
    this.#active(); const input = revealedInput(candles); this.#candles = input;
    for (const config of this.#instances.values()) this.#run(config);
  }
  attach(chart) { this.#active(); this.#adapter.attach(chart); for (const config of this.#instances.values()) this.#run(config); }
  detach() { this.#adapter.detach(); }
  remove(id) { this.#active(); this.#adapter.remove(id); this.#instances.delete(id); this.#outputs.delete(id); this.#errors.delete(id); }
  snapshot() { return Object.freeze([...this.#instances.values()]); }
  output(id) { return this.#outputs.get(id) ?? Object.freeze([]); }
  errors() { return Object.freeze(Object.fromEntries(this.#errors)); }
  dispose() { this.detach(); this.#instances.clear(); this.#outputs.clear(); this.#errors.clear(); this.#candles = Object.freeze([]); this.#disposed = true; }
}
