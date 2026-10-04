import { canonicalString } from './eventValidation.js';
export const DEFAULT_WINDOW = Object.freeze({ version: 1, A: 3600, B: 0, C: 60, D: 3600 });
export function validateWindow(config) {
  if (!config || config.version !== 1 || !['A', 'B', 'C', 'D'].every(key => Number.isFinite(config[key]) && config[key] >= 0) || config.A < config.B || config.D < config.C || config.A <= 0 || config.D <= 0 || Math.max(config.A, config.D) > 31 * 86400) throw new Error('Invalid research window; use nonnegative seconds, A ≥ B, D ≥ C, positive outer bounds (max 31 days).');
  return { version: 1, A: config.A, B: config.B, C: config.C, D: config.D };
}
export function classifyWindow(delta, config) {
  if (delta >= -config.A && delta < -config.B) return 'Pre';
  if (delta >= -config.B && delta < config.C) return 'During';
  if (delta >= config.C && delta < config.D) return 'Post';
  return null;
}
export function contextAt(index, tradeTime, cursor, filters, window, retrospective = false) {
  if (!index || !Number.isFinite(tradeTime) || !Number.isFinite(cursor) || tradeTime > cursor) return { status: 'unknown', matches: [], nearest: null };
  const config = validateWindow(window), asOf = Math.min(tradeTime, cursor);
  const matches = index.range(tradeTime - config.D, tradeTime + config.A + .001, asOf, filters, { retrospective }).map(event => ({ ...event, delta: tradeTime - event.fields.schedule.value, window: classifyWindow(tradeTime - event.fields.schedule.value, config) })).filter(event => event.window);
  const nearest = matches.slice().sort((a, b) => Math.abs(a.delta) - Math.abs(b.delta) || a.fields.schedule.value - b.fields.schedule.value || (a.occurrenceId < b.occurrenceId ? -1 : 1))[0] ?? null;
  return { status: index.coverageAt(tradeTime, filters), matches, nearest, windowIdentity: canonicalString(config), mode: retrospective ? 'Retrospective' : 'Strict as-of trade time' };
}
