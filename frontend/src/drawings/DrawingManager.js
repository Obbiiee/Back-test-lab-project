import { TEXT } from './DrawingTypes.js';
import { createDrawingRegistry } from './DrawingRegistry.js';

// Drawing domain only: no React, trading, replay, indicators or storage imports.
export class DrawingManager {
  objects = new Map();
  primitives = new Map();
  listeners = new Set();
  series = null;
  bars = [];
  draft = null;
  selectedId = null;
  committed = [];
  commitListeners = new Set();
  historyFocus = null;
  setHistoryFocus(domain) { this.historyFocus = domain; }
  constructor(registry = createDrawingRegistry()) { this.registry = registry; }
  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  notify() { this.listeners.forEach(listener => listener(this.getAll(), Boolean(this.draft))); }
  subscribeCommitted(listener) { this.commitListeners.add(listener); return () => this.commitListeners.delete(listener); }
  // `coalesce` lets a burst of edits from one control (slider drag, colour
  // picker, held arrow key) become a single undo step.
  commit(coalesce = null) {
    const next = this.getAll();
    if (JSON.stringify(next) === JSON.stringify(this.committed)) return false;
    const previous = this.committed; this.committed = next;
    this.commitListeners.forEach(listener => listener(previous, next, coalesce));
    return true;
  }
  precision = 3;
  setPrecision(precision) {
    if (!Number.isInteger(precision) || precision < 0 || precision > 12 || precision === this.precision) return;
    this.precision = precision;
    for (const primitive of this.primitives.values()) primitive.setPrecision?.(precision);
    this.draft?.setPrecision?.(precision);
  }
  #replaceModel(id, model, coalesce) {
    this.objects.set(id, model); this.primitives.get(id).setModel(model);
    this.commit(coalesce); this.notify(); return model;
  }
  // Style/text options. Locked drawings refuse edits (unlock first).
  setOptions(id, patch, coalesce = null) {
    const previous = this.get(id);
    if (!previous || previous.locked) return null;
    const options = { ...previous.options };
    for (const [key, value] of Object.entries(patch)) { if (value === undefined) delete options[key]; else options[key] = value; }
    return this.#replaceModel(id, this.registry.get(previous.type).model({ ...previous, options }), coalesce);
  }
  rename(id, name) {
    const previous = this.get(id);
    if (!previous) return null;
    const rest = { ...previous }; delete rest.name;
    const trimmed = typeof name === 'string' ? name.trim().slice(0, 64) : '';
    return this.#replaceModel(id, this.registry.get(previous.type).model(trimmed ? { ...rest, name: trimmed } : rest), null);
  }
  // Exact coordinate edit from the Properties panel (keyboard / numeric input).
  setPoints(id, points, coalesce = null) {
    const previous = this.get(id);
    if (!previous || previous.locked) return null;
    return this.#replaceModel(id, this.registry.get(previous.type).model({ ...previous, points }), coalesce);
  }
  duplicate(id, newId, shift = point => point) {
    const previous = this.get(id);
    if (!previous) return null;
    return this.add({ ...previous, id: newId, locked: false, visible: true, points: previous.points.map(shift) });
  }
  // Layer order = insertion order. Primitives are re-attached in order so the
  // canvas paints (and hit testing resolves) the same stack.
  reorder(id, where) {
    const ids = [...this.objects.keys()], from = ids.indexOf(id);
    if (from < 0) return false;
    const to = where === 'front' ? ids.length - 1 : where === 'back' ? 0 : where === 'forward' ? Math.min(ids.length - 1, from + 1) : where === 'backward' ? Math.max(0, from - 1) : from;
    if (to === from) return false;
    ids.splice(from, 1); ids.splice(to, 0, id);
    const objects = new Map(ids.map(key => [key, this.objects.get(key)])), primitives = new Map(ids.map(key => [key, this.primitives.get(key)]));
    if (this.series) { for (const primitive of this.primitives.values()) this.series.detachPrimitive(primitive); }
    this.objects = objects; this.primitives = primitives;
    if (this.series) for (const primitive of primitives.values()) this.series.attachPrimitive(primitive);
    for (const [key, primitive] of primitives) primitive.setSelected(key === this.selectedId);
    this.commit(); this.notify(); return true;
  }
  add(input) {
    const definition = this.registry.get(input.type);
    const model = definition.model(input);
    if (this.objects.has(model.id)) throw new Error('Duplicate drawing id: ' + model.id);
    const primitive = definition.primitive(model, this.bars, false);
    primitive.precision = this.precision;
    if (this.series) this.series.attachPrimitive(primitive);
    this.objects.set(model.id, model); this.primitives.set(model.id, primitive);
    this.commit(); this.notify(); return model;
  }
  get(id) { return this.objects.get(id); }
  getAll() { return [...this.objects.values()]; }
  update(id, points, notify = true) {
    const previous = this.get(id);
    if (!previous) return null;
    if (previous.locked) return previous;
    const model = this.registry.get(previous.type).model({ ...previous, points });
    this.objects.set(id, model); this.primitives.get(id).setModel(model);
    if (notify) { this.commit(); this.notify(); }
    return model;
  }
  setText(id, text) {
    const previous = this.get(id);
    if (!previous || previous.type !== TEXT || previous.locked) return false;
    const model = this.registry.get(TEXT).model({ ...previous, text });
    this.objects.set(id, model); this.primitives.get(id).setModel(model);
    this.commit(); this.notify(); return true;
  }
  select(id) {
    const next = this.objects.get(id)?.visible ? id : null;
    if (next === this.selectedId) return;
    this.selectedId = next;
    for (const [key, primitive] of this.primitives) primitive.setSelected(key === next);
    this.notify();
  }
  remove(id) {
    if (!this.objects.has(id)) return false;
    if (this.selectedId === id) this.selectedId = null;
    if (this.series) this.series.detachPrimitive(this.primitives.get(id));
    this.objects.delete(id); this.primitives.delete(id); this.commit(); this.notify(); return true;
  }
  setProperties(id, properties) {
    const previous = this.get(id);
    if (!previous) return;
    const model = this.registry.get(previous.type).model({ ...previous,
      locked: properties.locked ?? previous.locked, visible: properties.visible ?? previous.visible });
    this.objects.set(id, model); this.primitives.get(id).setModel(model);
    if (!model.visible && this.selectedId === id) this.select(null);
    this.commit(); this.notify();
  }
  replaceAll(inputs) {
    const models = inputs.map(input => this.registry.get(input.type).model(input));
    if (new Set(models.map(model => model.id)).size !== models.length) throw new Error('Duplicate drawing ids');
    for (const primitive of this.primitives.values()) this.series?.detachPrimitive(primitive);
    this.objects.clear(); this.primitives.clear();
    for (const model of models) {
      const primitive = this.registry.get(model.type).primitive(model, this.bars, false);
      primitive.precision = this.precision;
      this.objects.set(model.id, model); this.primitives.set(model.id, primitive);
      this.series?.attachPrimitive(primitive);
    }
    if (!this.get(this.selectedId)?.visible) this.selectedId = null;
    for (const [id, primitive] of this.primitives) primitive.setSelected(id === this.selectedId);
    this.commit(); this.notify();
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
    this.draft.precision = this.precision;
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
