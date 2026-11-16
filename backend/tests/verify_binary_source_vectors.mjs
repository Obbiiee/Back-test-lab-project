import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const vectors=JSON.parse(readFileSync(new URL('./fixtures/binary_source_vectors.json',import.meta.url)));
for(const row of vectors.prices){
  const bytes=new ArrayBuffer(8),view=new DataView(bytes);
  view.setFloat64(0,Number(row.text));
  assert.equal(view.getBigUint64(0).toString(16).padStart(16,'0'),row.bits);
  const value=view.getFloat64(0);assert.equal(Number(row.text),value);
}
for(const row of vectors.timestamps){
  assert.equal((BigInt(row.ms)*1000000n).toString(),row.ns);
  assert.equal(new Date(Number(row.ms)).toISOString(),row.iso);
}
console.log('PASS independent Node binary64 bits and UTC-ms vectors: 6 prices / 4 timestamps.');
