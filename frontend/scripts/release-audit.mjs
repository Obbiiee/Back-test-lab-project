// Local distribution gate, separate from domain tests and browser acceptance.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('..', import.meta.url));
const read = name => readFileSync(path.join(root, name), 'utf8');
const pkg = JSON.parse(read('package.json')), lock = JSON.parse(read('package-lock.json'));
assert.equal(pkg.version, '1.0.0'); assert.equal(lock.version, pkg.version); assert.equal(lock.packages[''].version, pkg.version);
assert.equal(JSON.parse(read('node_modules/lightweight-charts/package.json')).version, '5.2.1');
assert.ok(read('dist/index.html').includes('type="module"'), 'Production build is required.');
const notices = readdirSync(path.join(root, 'public/licenses'));
assert.ok(notices.includes('NOTICE.txt') && notices.length >= 7);
for (const name of notices) assert.equal(read('dist/licenses/' + name), read('public/licenses/' + name), 'Distribution must retain notice: ' + name);
for (const name of ['lightweight-charts', 'react', 'react-dom', 'scheduler']) assert.equal(read('public/licenses/' + name + '-LICENSE.txt').replace(/\r\n/g,'\n'), read('node_modules/' + name + '/LICENSE').replace(/\r\n/g,'\n'), 'Installed license must remain unchanged.');
assert.ok(read('dist/licenses/NOTICE.txt').includes('TradingView'));
assert.ok(read('dist/licenses/NOTICE.txt').includes('72290d3165682ec7bd28f96af7f9354184982dda'));
assert.ok(read('dist/licenses/lightweight-charts-drawing-ray-LICENSE.txt').includes('Copyright (c) 2026 deepentropy'));
for (const name of readdirSync(path.join(root, 'dist/assets'))) {
  if (!/\.js$/.test(name)) continue;
  const content = read('dist/assets/' + name);
  assert.ok(!content.includes('PHASE16-CORRUPT-PRESERVE') && !content.includes('Seed incomplete legacy account'), 'QA seed code must never enter production.');
}
assert.ok(statSync(path.join(root,'dist/market/decade/manifest.json')).isFile(), 'Historical replay catalog must ship.');
console.log('PASS local v1.0 package/lock identity, installed chart, production build/history catalog, preserved distribution licenses and excluded QA seeds.');
