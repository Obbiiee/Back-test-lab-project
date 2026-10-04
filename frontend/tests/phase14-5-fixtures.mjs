// Generated solely for tests. Dates/values are synthetic, never economic history.
export const iso = time => new Date(time * 1000).toISOString();
export const START = Date.parse('2024-06-03T12:00:00Z') / 1000;
export function sparsePilot(count) {
  const input = pilot(0), start = Date.parse('2016-10-03T00:00:00Z') / 1000, interval = Math.floor(10 * 365.25 * 86400 / count);
  input.occurrences = Array.from({ length: count }, (_, i) => {
    const time = start + i * interval;
    return { occurrenceId: `bench-${String(i).padStart(7, '0')}`, eventTypeId: 'test-CPI', referencePeriod: 'Synthetic', releaseStage: 'first', facts: { schedule: [fact(iso(time), time - 86400)] } };
  });
  return input;
}
export function fact(value, availableAt = START - 86400, extra = {}) {
  return { version: '1', value, availableAtUtc: availableAt === null ? null : iso(availableAt), evidence: availableAt === null ? null : 'Synthetic test evidence; not a real release', sourceTimestamp: '2024-06-03T00:00:00Z', sourceTimezone: 'UTC', precision: 'second', ...extra };
}
export function pilot(count = 6) {
  const categories = ['CPI', 'NFP', 'FOMC', 'PCE', 'GDP', 'CPI'];
  return { schemaVersion: 1, datasetId: 'synthetic-news-pilot', version: '1', provenance: { source: 'Backtest Lab synthetic fixtures — NOT real historical news', license: 'Project-owned synthetic test data', retrievedAt: '2026-10-04T00:00:00Z' }, coverage: [{ from: '2024-06-02T00:00:00Z', to: '2024-06-07T00:00:00Z', status: 'complete', currencies: ['*'], categories: ['*'], evidence: 'Complete for this synthetic fixture only' }], definitions: categories.slice(0, 5).map(category => ({ eventTypeId: `test-${category}`, sourceName: `${category} synthetic release`, variant: category === 'CPI' ? 'headline YoY' : category === 'GDP' ? 'advance' : category === 'FOMC' ? 'statement' : 'headline' })), occurrences: Array.from({ length: count }, (_, i) => {
    const release = START + (i + 1) * 1800, category = categories[i % categories.length];
    return { occurrenceId: `synthetic-${String(i).padStart(6, '0')}`, eventTypeId: `test-${category}`, referencePeriod: '2024-05 synthetic', releaseStage: category === 'GDP' ? 'advance' : category === 'FOMC' ? 'statement' : 'first', facts: {
      name: [fact(`${category} SYNTHETIC ${i + 1}`)], currency: [fact(i === 5 ? 'EUR' : 'USD')], category: [fact(category)], impact: [fact(i === 5 ? 'Medium' : 'High')], status: [fact('scheduled')], schedule: [fact(iso(release))], releaseTime: [fact(iso(release), release)], previous: [fact(1, START - 86400, { unit: '%', rawText: '1%' })], forecast: [fact(2, release - 900, { unit: '%', rawText: '2%' })], actual: [fact(3 + i, release, { unit: '%', rawText: `${3 + i}%` })]
    } };
  }) };
}
