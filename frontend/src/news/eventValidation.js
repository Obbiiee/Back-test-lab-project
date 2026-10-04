// Provider-neutral trust boundary. No browser, trading or market state.
export class NewsDataError extends Error {
  constructor(path, message) { super(`${path}: ${message}`); this.name = 'NewsDataError'; }
}
const fail = (path, message) => { throw new NewsDataError(path, message); };
const text = (value, path) => { if (typeof value !== 'string' || !value.trim() || value.length > 2048) fail(path, 'Expected nonempty string (max 2048 characters).'); return value; };
const array = (value, path) => { if (!Array.isArray(value)) fail(path, 'Expected array.'); return value; };
const object = (value, path) => { if (!value || typeof value !== 'object' || Array.isArray(value)) fail(path, 'Expected object.'); return value; };
const orderText = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const formatters = new Map();
function formatterFor(zone, path) {
  if (formatters.has(zone)) return formatters.get(zone);
  let formatter;
  try { formatter = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }); }
  catch { fail(path, 'Unsupported source timezone.'); }
  if (formatters.size >= 32) formatters.delete(formatters.keys().next().value);
  formatters.set(zone, formatter); return formatter;
}
export function endOfSourceDay(value, zone, path = 'availability') {
  if (!/^\d{4}-\d\d-\d\d$/.test(value)) fail(path, 'Expected source-local YYYY-MM-DD.');
  const midnight = utcTimestamp(value + 'T00:00:00Z', path);
  const next = new Date((midnight + 86400) * 1000).toISOString().slice(0, 10);
  const formatter = formatterFor(zone, path);
  // Try every legal offset, including quarter-hour offsets, and require a unique
  // source-local midnight. DST midnight folds/gaps are explicitly rejected.
  const base = midnight + 86400, matches = [];
  for (let minutes = -14 * 60; minutes <= 14 * 60; minutes += 15) {
    const candidate = base + minutes * 60;
    const p = Object.fromEntries(formatter.formatToParts(new Date(candidate * 1000)).map(item => [item.type, item.value]));
    if (`${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}` === next + 'T00:00:00') matches.push(candidate);
  }
  if (matches.length !== 1) fail(path, 'Ambiguous, missing or unsupported source-local midnight; supply explicit availability offset.');
  return matches[0];
}
export function utcTimestamp(value, path = 'timestamp', zone) {
  text(value, path);
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?(?:Z|[+-]\d\d:\d\d)$/.test(value)) fail(path, 'Explicit UTC offset and seconds required.');
  const time = Date.parse(value), local = Date.parse(value.slice(0, 19) + 'Z');
  if (!Number.isFinite(time) || !Number.isFinite(local) || new Date(local).toISOString().slice(0, 19) !== value.slice(0, 19)) fail(path, 'Invalid calendar date/time.');
  if (zone) {
    if (zone === 'UTC') { if (new Date(time).toISOString().slice(0, 19) !== value.slice(0, 19)) fail(path, 'UTC source contradicts offset.'); }
    else {
      const p = Object.fromEntries(formatterFor(zone, path).formatToParts(new Date(time)).map(item => [item.type, item.value]));
      if (`${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}` !== value.slice(0, 19)) fail(path, 'Source timezone contradicts offset.');
    }
  }
  return time / 1000;
}
export const NEWS_FIELDS = Object.freeze(['schedule', 'releaseTime', 'status', 'name', 'currency', 'category', 'impact', 'previous', 'forecast', 'actual']);
export function canonicalString(value) {
  if (Array.isArray(value)) return '[' + value.map(canonicalString).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonicalString(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
export async function contentHash(value) {
  const bytes = new TextEncoder().encode(typeof value === 'string' ? value : canonicalString(value));
  const hash = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}
const freeze = value => { if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
export function validateDataset(input) {
  const d = object(input, 'dataset');
  if (d.schemaVersion !== 1) fail('schemaVersion', 'Only version 1 is supported; existing data will be preserved.');
  const datasetId = text(d.datasetId, 'datasetId'), version = text(d.version, 'version');
  const provenance = object(d.provenance, 'provenance');
  for (const key of ['source', 'license', 'retrievedAt']) text(provenance[key], 'provenance.' + key);
  utcTimestamp(provenance.retrievedAt, 'provenance.retrievedAt');
  if (array(d.definitions, 'definitions').length > 10000 || array(d.coverage, 'coverage').length > 10000) fail('dataset', 'Maximum 10000 definitions and coverage intervals.');
  const definitions = d.definitions.map((definition, i) => {
    const path = `definitions[${i}]`; object(definition, path);
    return { eventTypeId: text(definition.eventTypeId, path + '.eventTypeId'), sourceName: text(definition.sourceName, path + '.sourceName'), variant: text(definition.variant, path + '.variant') };
  }).sort((a, b) => orderText(a.eventTypeId, b.eventTypeId));
  const types = new Set(definitions.map(item => item.eventTypeId));
  if (types.size !== definitions.length) fail('definitions', 'Duplicate eventTypeId.');
  const coverage = array(d.coverage, 'coverage').map((item, i) => {
    const path = `coverage[${i}]`; object(item, path);
    const from = utcTimestamp(item.from, path + '.from'), to = utcTimestamp(item.to, path + '.to');
    if (from >= to || !['complete', 'partial', 'unknown'].includes(item.status)) fail(path, 'Invalid interval or coverage status.');
    const scope = key => { const values = array(item[key], path + '.' + key); if (!values.length || values.length > 1000) fail(path, 'Coverage scope requires 1–1000 values.'); return [...new Set(values.map((v, j) => text(v, `${path}.${key}[${j}]`)))].sort(); };
    return { from, to, status: item.status, currencies: scope('currencies'), categories: scope('categories'), evidence: text(item.evidence, path + '.evidence') };
  }).sort((a, b) => a.from - b.from || a.to - b.to);
  if (array(d.occurrences, 'occurrences').length > 100000) fail('occurrences', 'Maximum 100000 occurrences per dataset.');
  let totalFacts = 0;
  const occurrences = d.occurrences.map((occurrence, i) => {
    const path = `occurrences[${i}]`; object(occurrence, path);
    const id = text(occurrence.occurrenceId, path + '.occurrenceId'), type = text(occurrence.eventTypeId, path + '.eventTypeId');
    if (!types.has(type)) fail(path, 'Unknown eventTypeId.');
    object(occurrence.facts, path + '.facts');
    const facts = {};
    for (const key of Object.keys(occurrence.facts)) {
      if (!NEWS_FIELDS.includes(key)) fail(path + '.facts.' + key, 'Unknown field.');
      const versions = new Set();
      facts[key] = array(occurrence.facts[key], path + '.facts.' + key).map((fact, j) => {
        if (++totalFacts > 1000000) fail(path, 'Maximum 1000000 field versions per dataset.');
        const at = `${path}.facts.${key}[${j}]`; object(fact, at);
        const factVersion = text(fact.version, at + '.version');
        if (versions.has(factVersion)) fail(at, 'Duplicate fact version.'); versions.add(factVersion);
        if (!['second', 'millisecond', 'day'].includes(fact.precision)) fail(at, 'Precision required.');
        if (j > 999) fail(at, 'Maximum 1000 versions per field.');
        const sourceTimezone = text(fact.sourceTimezone, at + '.sourceTimezone');
        const sourceTimestamp = text(fact.sourceTimestamp, at + '.sourceTimestamp');
        let value = fact.value;
        if (value !== null) {
          if (['schedule', 'releaseTime'].includes(key)) {
            if (fact.precision === 'day') { if (!/^\d{4}-\d\d-\d\d$/.test(value)) fail(at, 'Date-only value expected.'); utcTimestamp(value + 'T00:00:00Z', at); }
            else value = utcTimestamp(value, at + '.value', sourceTimezone);
          } else if (['actual', 'previous', 'forecast'].includes(key)) {
            if (typeof value !== 'number' || !Number.isFinite(value)) fail(at, 'Finite numeric value required.');
            text(fact.unit, at + '.unit'); text(fact.rawText, at + '.rawText');
          } else {
            text(value, at + '.value');
            if (key === 'currency' && !/^[A-Z]{3}$/.test(value)) fail(at, 'Currency must use three uppercase letters.');
            if (key === 'impact' && !['High', 'Medium', 'Low', 'Unknown'].includes(value)) fail(at, 'Unsupported impact.');
            if (key === 'status' && !['scheduled', 'released', 'cancelled', 'tentative'].includes(value)) fail(at, 'Unsupported status.');
          }
        }
        const availabilityPrecision = fact.availabilityPrecision ?? 'second';
        if (!['second', 'millisecond', 'day'].includes(availabilityPrecision)) fail(at, 'Invalid availability precision.');
        const availableAt = fact.availableAtUtc == null ? null : availabilityPrecision === 'day' ? endOfSourceDay(fact.availableAtUtc, sourceTimezone, at + '.availableAtUtc') : utcTimestamp(fact.availableAtUtc, at + '.availableAtUtc');
        if (availableAt !== null) text(fact.evidence, at + '.evidence');
        for (const field of ['evidence', 'unit', 'rawText', 'referencePeriod']) if (fact[field] != null) text(fact[field], at + '.' + field);
        if (fact.precision !== 'day') utcTimestamp(sourceTimestamp, at + '.sourceTimestamp', sourceTimezone);
        else endOfSourceDay(sourceTimestamp, sourceTimezone, at + '.sourceTimestamp');
        return { version: factVersion, value, availableAt, evidence: fact.evidence ?? null, sourceTimestamp, sourceTimezone, precision: fact.precision, availabilityPrecision, unit: fact.unit ?? null, rawText: fact.rawText ?? null, referencePeriod: fact.referencePeriod ?? null };
      }).sort((a, b) => (a.availableAt ?? Infinity) - (b.availableAt ?? Infinity) || orderText(a.version, b.version));
      for (let j = 1; j < facts[key].length; j++) if (facts[key][j].availableAt !== null && facts[key][j].availableAt === facts[key][j - 1].availableAt) fail(path, 'Ambiguous simultaneous field versions.');
    }
    return { occurrenceId: id, eventTypeId: type, referencePeriod: text(occurrence.referencePeriod, path + '.referencePeriod'), releaseStage: text(occurrence.releaseStage, path + '.releaseStage'), facts };
  }).sort((a, b) => orderText(a.occurrenceId, b.occurrenceId));
  if (new Set(occurrences.map(item => item.occurrenceId)).size !== occurrences.length) fail('occurrences', 'Duplicate occurrenceId.');
  return freeze({ schemaVersion: 1, datasetId, version, provenance: { source: provenance.source, license: provenance.license, retrievedAt: provenance.retrievedAt }, coverage, definitions, occurrences });
}
export async function importDataset(raw) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > 64 * 1024 * 1024) fail('file', 'Expected JSON text up to 64 MiB.');
  let input; try { input = JSON.parse(raw.replace(/^\uFEFF/, '')); } catch { fail('file', 'Invalid JSON.'); }
  const dataset = validateDataset(input);
  return { dataset, hash: await contentHash(dataset), sourceHash: await contentHash(raw) };
}
