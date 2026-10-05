// Independent standard-library reference for the reviewed BTL-CJSON-1 fixtures.
// No import of Python implementation, frontend, execution or persistence code.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

function decimalText(text) {
  const m = text.match(/^(-?)(\d+)(?:\.(\d+))?(?:e([+-]?\d+))?$/i);
  assert(m);
  const digits = m[2] + (m[3] || '');
  if (/^0+$/.test(digits)) return '0';
  const point = m[2].length + Number(m[4] || 0);
  let result = point <= 0 ? '0.' + '0'.repeat(-point) + digits
    : point >= digits.length ? digits + '0'.repeat(point - digits.length)
      : digits.slice(0, point) + '.' + digits.slice(point);
  result = result.replace(/^0+(?=\d)/, '');
  if (result.includes('.')) result = result.replace(/0+$/, '').replace(/\.$/, '');
  return m[1] + result;
}
function codePointOrder(a, b) {
  const x = Array.from(a, c => c.codePointAt(0)), y = Array.from(b, c => c.codePointAt(0));
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i];
  return x.length - y.length;
}
function normalize(value) {
  if (Array.isArray(value)) return value.map(normalize);
  if (value && typeof value === 'object') {
    if (Object.keys(value).join() === '$decimal') return decimalText(value.$decimal);
    if (Object.keys(value).join() === '$timestamp') {
      const fraction = value.$timestamp.match(/\.(\d{1,6})(?:Z|[+-]\d\d:\d\d)$/)?.[1] || '';
      return new Date(value.$timestamp).toISOString().replace(/\.\d{3}Z$/, '.' + fraction.padEnd(6, '0') + 'Z');
    }
    return Object.fromEntries(Object.keys(value).sort(codePointOrder).map(key => [key, normalize(value[key])]));
  }
  return value;
}
const vectors = JSON.parse(readFileSync(new URL('./fixtures/contract_hash_vectors.json', import.meta.url), 'utf8'));
function serialize(value) {
  if (Array.isArray(value)) return '[' + value.map(serialize).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort(codePointOrder)
    .map(key => JSON.stringify(key) + ':' + serialize(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
for (let run = 0; run < 3; run++) for (const vector of vectors) {
  const bytes = serialize(normalize(vector.input));
  assert.equal(bytes, vector.canonical, vector.name);
  assert.equal(createHash('sha256').update(bytes, 'utf8').digest('hex'), vector.sha256, vector.name);
}
console.log(`PASS independent Node reference: ${vectors.length} golden vectors, 3 repeated runs.`);
