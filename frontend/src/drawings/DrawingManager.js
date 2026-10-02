import { createDrawingRegistry } from './DrawingRegistry.js';

// Drawing domain only: no React, trading, replay, indicators or storage imports.
export class DrawingManager {
  objects = new Map();
  primitives = new Map();
  listeners = new Set();
  series = null;
  bars = [];
  draft = null;
  constructor(registry = createDrawingRegistry()) { this.registry = registry; }
  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  notify() { this.listeners.forEach(listener => listener(this.getAll(), Boolean(this.draft))); }
  add(input) {
    const definition = this.registry.get(input.type);
    const model = definition.model(input);
    if (this.objects.has(model.id)) throw new Error('Duplicate drawing id: ' + model.id);
    const primitive = definition.primitive(model, this.bars, false);
    if (this.series) this.series.attachPrimitive(primitive);
    this.objects.set(model.id, model); this.primitives.set(model.id, primitive);
    this.notify(); return model;
  }
  get(id) { return this.objects.get(id); }
  getAll() { return [...this.objects.values()]; }
  remove(id) {
    if (!this.objects.has(id)) return false;
    if (this.series) this.series.detachPrimitive(this.primitives.get(id));
    this.objects.delete(id); this.primitives.delete(id); this.notify(); return true;
  }
  clear() { this.cancelDraft(); for (const id of this.objects.keys()) this.remove(id); }
  attach(series) {
    if (this.series === series) return;
    this.detach(); this.series = series;
    for (const primitive of this.primitives.values()) series.attachPrimitive(primitive);
  }
  detach() {
    this.cancelDraft();
    if (this.series) for (const primitive of this.primitives.values()) this.series.detachPrimitive(primitive);
    this.series = null;
  }
  setTimePoints(bars) {
    this.bars = bars;
    for (const primitive of this.primitives.values()) primitive.setTimePoints(bars);
    this.draft?.setTimePoints(bars);
  }
  startDraft(input) {
    this.cancelDraft();
    const definition = this.registry.get(input.type);
    this.draft = definition.primitive(definition.model(input), this.bars, true);
    if (this.series) this.series.attachPrimitive(this.draft);
    this.notify();
  }
  updateDraft(input) {
    if (this.draft) this.draft.setModel(this.registry.get(input.type).model(input));
  }
  cancelDraft() {
    if (!this.draft) return;
    if (this.series) this.series.detachPrimitive(this.draft);
    this.draft = null; this.notify();
  }
}
