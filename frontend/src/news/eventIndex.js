// Time index over schedule versions; future entries stay internal and cannot
// determine output eligibility. Consumers receive field-filtered projections.
import { NEWS_FIELDS } from './eventValidation.js';
import { TimeIndex } from './timeIndex.js';
export function upperBound(items, value, read = item => item) {
  let lo = 0, hi = items.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if (read(items[mid]) <= value) lo = mid + 1; else hi = mid; }
  return lo;
}
const selectedFact = (facts = [], time, retrospective) => retrospective ? facts.at(-1) : facts[upperBound(facts, time, fact => fact.availableAt ?? Infinity) - 1];
export function projectOccurrence(occurrence, time, retrospective = false) {
  if (!occurrence || !Number.isFinite(time)) return null;
  const fields = {}, hidden = [];
  for (const key of NEWS_FIELDS) {
    const fact = selectedFact(occurrence.facts[key], time, retrospective);
    if (fact) fields[key] = fact;
    else hidden.push(key);
  }
  const release = fields.releaseTime;
  if (!retrospective && (!release || release.precision === 'day' || !Number.isFinite(release.value) || release.value > time)) {
    delete fields.actual; if (!hidden.includes('actual')) hidden.push('actual');
    if (release) { delete fields.releaseTime; if (!hidden.includes('releaseTime')) hidden.push('releaseTime'); }
  }
  if (!fields.name && !fields.schedule) return null;
  return { occurrenceId: occurrence.occurrenceId, fields, hidden };
}
export const DEFAULT_FILTERS = Object.freeze({ currency: 'USD', impact: 'High', category: 'All' });
export function matchesFilters(event, filters = DEFAULT_FILTERS) {
  return ['currency', 'impact', 'category'].every(key => filters[key] === 'All' || (event.fields[key]?.value ?? 'Unknown') === filters[key]);
}
export class EventIndex {
  constructor(dataset) {
    this.dataset = dataset;
    this.occurrences = new Map(dataset.occurrences.map(item => [item.occurrenceId, item]));
    this.timeline = dataset.occurrences.flatMap(item => Object.values(item.facts).flatMap(facts => facts.filter(fact => fact.availableAt !== null).map(fact => ({ time: fact.availableAt, id: item.occurrenceId }))));
    // Actual eligibility also changes at proven release time, not only at fact availability.
    for (const item of dataset.occurrences) for (const fact of item.facts.releaseTime ?? []) if (fact.availableAt !== null && Number.isFinite(fact.value)) this.timeline.push({ time: Math.max(fact.availableAt, fact.value), id: item.occurrenceId });
    this.timeline.sort((a, b) => a.time - b.time);
    this.position = 0; this.time = -Infinity; this.active = new Map(); this.views = new Map(); this.retrospectiveViews = new Map();
    this.lastOperations = 0;
  }
  project(id, time, retrospective = false) { return projectOccurrence(this.occurrences.get(id), time, retrospective); }
  advance(time) {
    if (!Number.isFinite(time)) return;
    const next = upperBound(this.timeline, time, item => item.time), changed = new Set();
    for (let i = Math.min(next, this.position); i < Math.max(next, this.position); i++) changed.add(this.timeline[i].id);
    for (const id of changed) {
      const event = this.project(id, time);
      if (event) this.active.set(id, event); else this.active.delete(id);
      for (const { tree, filters } of this.views.values()) {
        tree.delete(id); tree.dateOnly.delete(id);
        if (this.eligible(event, filters)) tree.put(event);
        if (event?.fields.schedule?.precision === 'day' && event.fields.status?.value !== 'cancelled' && matchesFilters(event, filters)) tree.dateOnly.set(id, event);
      }
    }
    this.position = next; this.time = time;
  }
  eligible(event, filters) { return event && Number.isFinite(event.fields.schedule?.value) && event.fields.schedule.precision !== 'day' && event.fields.status?.value !== 'cancelled' && matchesFilters(event, filters); }
  view(time, filters, retrospective) {
    const key = JSON.stringify(['currency', 'impact', 'category'].map(field => filters[field]));
    if (!retrospective) this.advance(time);
    const views = retrospective ? this.retrospectiveViews : this.views;
    if (!views.has(key)) {
      const tree = new TimeIndex(), events = retrospective ? [...this.occurrences.values()].map(item => projectOccurrence(item, time, true)) : this.active.values();
      for (const event of events) {
        if (this.eligible(event, filters)) tree.put(event);
        if (event?.fields.schedule?.precision === 'day' && event.fields.status?.value !== 'cancelled' && matchesFilters(event, filters)) tree.dateOnly.set(event.occurrenceId, event);
      }
      // Bounded cache: at most eight filter views; evicted views are rebuilt only on filter changes.
      if (views.size >= 8) views.delete(views.keys().next().value);
      views.set(key, { tree, filters: { ...filters } });
    }
    return views.get(key).tree;
  }
  range(from, to, time, filters, { retrospective = false, limit = Infinity } = {}) {
    if (!Number.isFinite(time)) return [];
    const tree = this.view(time, filters, retrospective), result = tree.range(from, to, limit);
    this.lastOperations = tree.operations; return result;
  }
  navigate(time, direction, filters) {
    const tree = this.view(time, filters, false), target = tree.neighbor(time, direction);
    if (target === null) return null;
    return { time: target, events: tree.range(target, target + .001) };
  }
  dateOnly(time, filters, limit = 20, retrospective = false) {
    if (!Number.isFinite(time)) return [];
    const tree = this.view(time, filters, retrospective), events = [];
    for (const event of tree.dateOnly.values()) { events.push(event); if (events.length >= limit) break; }
    return events;
  }
  coverageAt(time, filters) {
    const rows = this.dataset.coverage.filter(item => item.from <= time && time < item.to && ['currencies', 'categories'].every(key => { const filter = filters[key === 'currencies' ? 'currency' : 'category']; return item[key].includes('*') || (filter !== 'All' && item[key].includes(filter)); }));
    return rows.some(item => item.status === 'complete') ? 'complete' : rows.some(item => item.status === 'partial') ? 'partial' : 'unknown';
  }
}
