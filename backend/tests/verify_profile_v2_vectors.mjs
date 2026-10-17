// Independent stdlib canonical bytes/hash reference; no production imports.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const file = new URL('./fixtures/execution_profiles_v2.json', import.meta.url);
const fixture = JSON.parse(readFileSync(file, 'utf8'));
function bytes(v) {
  if(Array.isArray(v)) return '[' + v.map(bytes).join(',') + ']';
  if(v && typeof v === 'object') return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + bytes(v[k])).join(',') + '}';
  return JSON.stringify(v);
}
for(const vector of fixture.vectors) {
  assert.equal(bytes(vector.input), vector.canonical, vector.name);
  assert.equal(createHash('sha256').update(vector.canonical, 'utf8').digest('hex'), vector.sha256, vector.name);
}
assert.equal(fixture.vectors.length,16);
console.log('PASS independent Node reference: 16 authored v2 profile canonical bytes/hashes.');
