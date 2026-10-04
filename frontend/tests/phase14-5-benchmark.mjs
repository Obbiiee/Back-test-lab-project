import assert from 'node:assert/strict';
import { performance } from 'node:perf_hooks';
import { validateDataset } from '../src/news/eventValidation.js';
import { EventIndex } from '../src/news/eventIndex.js';
import { pilot, fact, iso, START } from './phase14-5-fixtures.mjs';
// Sparse, clearly synthetic ten-year series. No timing threshold asserted.
for (const count of [10000, 100000]) {
  const input = pilot(0), start = Date.parse('2016-10-03T00:00:00Z') / 1000, interval = Math.floor(10 * 365.25 * 86400 / count);
  input.occurrences = Array.from({ length: count }, (_, i) => ({ occurrenceId: `bench-${String(i).padStart(7, '0')}`, eventTypeId: 'test-CPI', referencePeriod: 'Synthetic', releaseStage: 'first', facts: { schedule: [fact(iso(start + i * interval))] } }));
  const memory = process.memoryUsage().heapUsed, begin = performance.now(), dataset = validateDataset(input), validated = performance.now(), index = new EventIndex(dataset), indexed = performance.now();
  const filters = { currency: 'All', impact: 'All', category: 'All' };
  index.range(start, start + 3600, START, filters); const ready = performance.now();
  let operations = 0; const times = [];
  for (let i = 0; i < 1000; i++) { const t = START + i * 60, before = performance.now(); index.range(t - 3600, t + 3600, t, filters, { limit: 100 }); times.push(performance.now() - before); operations += index.lastOperations; }
  const sorted = times.slice().sort((a, b) => a - b);
  // Operation count checks the actual range tree, not a mock timing budget.
  assert.ok(operations < count * 10, 'Cursor query must not scan entire event history.');
  console.log(JSON.stringify({ count, validateMs: +(validated - begin).toFixed(2), indexMs: +(indexed - validated).toFixed(2), initialViewMs: +(ready - indexed).toFixed(2), cursorMeanMs: +(times.reduce((a, b) => a + b, 0) / times.length).toFixed(4), cursorP95Ms: +sorted[950].toFixed(4), queryNodeVisits: operations, heapGrowthMiB: +((process.memoryUsage().heapUsed - memory) / 1048576).toFixed(2) }));
}
