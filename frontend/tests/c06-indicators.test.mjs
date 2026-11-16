// Issue #21 C-06: the professional indicator catalog against an independent
// Python/pandas reference (tests/fixtures/c06_reference.py → c06-golden.json),
// plus causality, degenerate-input and registry contract checks for all 50 types.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { productionRegistry } from '../src/indicators/productionRegistry.js';

const { bars, golden } = JSON.parse(readFileSync(new URL('./fixtures/c06-golden.json', import.meta.url), 'utf8'));
const defaults = type => Object.fromEntries(Object.entries(productionRegistry.get(type).parameters).map(([k, r]) => [k, r.default]));
const run = (type, candles, params = defaults(type)) => productionRegistry.get(type).calculate(candles, params);
const asOutputs = (type, result) => Array.isArray(result) ? { [productionRegistry.get(type).outputs[0].key]: result } : result;
const TOL = 1e-8;
const failures = [];

function compare(type, key, actual, expected) {
  const exp = new Map(expected.map(([t, v]) => [t, v]));
  const act = new Map(actual.map(p => [p.time, p.value]));
  if (act.size !== exp.size) { failures.push(`${type}.${key}: ${act.size} points, reference ${exp.size}`); return; }
  pointsCompared += exp.size;
  for (const [t, v] of exp) {
    const a = act.get(t);
    if (a === undefined) { failures.push(`${type}.${key}: missing t=${t}`); return; }
    if (Math.abs(a - v) > TOL * Math.max(1, Math.abs(v))) { failures.push(`${type}.${key} @${t}: ${a} vs ${v}`); return; }
  }
}

let compared = 0, pointsCompared = 0;
for (const [type, ref] of Object.entries(golden)) {
  const outputs = asOutputs(type, run(type, bars));
  const refOutputs = Array.isArray(ref) ? { [productionRegistry.get(type).outputs[0].key]: ref } : ref;
  for (const [key, expected] of Object.entries(refOutputs)) { compare(type, key, outputs[key] ?? [], expected); compared++; }
}
assert.deepEqual(failures, [], `Golden mismatches:\n${failures.join('\n')}`);
assert.ok(compared >= 75, `compared ${compared} outputs`);

// Registry contract: 50 types, every one with category, version and description.
const types = productionRegistry.types();
assert.equal(types.length, 50);
for (const type of types) {
  const spec = productionRegistry.get(type);
  if (!['SMA','EMA','BOLLINGER_BANDS','RSI','MACD','ATR','STOCHASTIC'].includes(type)) {
    assert.ok(spec.category && spec.version === 1 && spec.description, `${type} metadata`);
  }
}

// Causality: no output point may change when later bars are appended.
// ZigZag's provisional leg is by definition repainting and is excluded.
const REPAINT = { ZIGZAG: ['provisional'] };
for (const type of types) {
  const full = asOutputs(type, run(type, bars));
  for (const cut of [60, 150, 250]) {
    const part = asOutputs(type, run(type, bars.slice(0, cut)));
    for (const [key, points] of Object.entries(part)) {
      if (REPAINT[type]?.includes(key)) continue;
      const index = new Map(full[key].map(p => [p.time, p.value]));
      for (const p of points) {
        assert.ok(p.time <= bars[cut - 1].time, `${type}.${key} emits a point after the last revealed bar`);
        const later = index.get(p.time);
        assert.ok(later !== undefined && Math.abs(later - p.value) <= 1e-9 * Math.max(1, Math.abs(later)), `${type}.${key} repaints t=${p.time} at cut ${cut}`);
      }
    }
  }
}

// Degenerate input: empty, one bar, short and totally flat series never throw or emit non-finite values.
const flat = Array.from({ length: 120 }, (_, i) => ({ time: 1736121600 + i * 3600, open: 5, high: 5, low: 5, close: 5 }));
for (const type of types) {
  for (const candles of [[], bars.slice(0, 1), bars.slice(0, 5), flat]) {
    const out = asOutputs(type, run(type, candles));
    for (const [key, points] of Object.entries(out)) {
      assert.ok(Array.isArray(points), `${type}.${key} array`);
      for (const p of points) assert.ok(Number.isFinite(p.value) && Number.isFinite(p.time), `${type}.${key} non-finite on ${candles.length} bars`);
      for (let i = 1; i < points.length; i++) assert.ok(points[i].time > points[i - 1].time, `${type}.${key} times ascending`);
    }
  }
}

// ZigZag: confirmed pivots alternate high/low and only use revealed bars.
const zz = run('ZIGZAG', bars, { depth: 12, deviation: 0.5 });
assert.ok(zz.confirmed.length >= 3, 'zigzag found pivots');
for (let i = 2; i < zz.confirmed.length; i++) {
  const a = zz.confirmed[i - 1].value - zz.confirmed[i - 2].value, b = zz.confirmed[i].value - zz.confirmed[i - 1].value;
  assert.ok(a * b < 0, 'zigzag pivots alternate high/low');
}

console.log(`c06 indicators: ${compared} outputs (${pointsCompared} points) match the reference, ${types.length} types causal and safe on degenerate input`);
