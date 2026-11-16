// F08 PWA: worker registers only for production HTTPS; it caches the shell, never API/ledger data.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {registerShellWorker} from '../src/pwa.js';

const registered = [];
const nav = {serviceWorker: {register: (...args) => { registered.push(args); return Promise.resolve(); }}};
assert.equal(registerShellWorker({PROD: false}, {protocol: 'https:'}, nav), false, 'dev build never registers');
assert.equal(registerShellWorker({PROD: true}, {protocol: 'http:'}, nav), false, 'plain HTTP never registers');
assert.equal(registerShellWorker({PROD: true}, {protocol: 'https:'}, {}), false, 'browsers without workers are fine');
assert.equal(registerShellWorker({PROD: true}, {protocol: 'https:'}, nav), true);
assert.deepEqual(registered, [['/sw.js', {scope: '/'}]]);

const manifest = JSON.parse(fs.readFileSync(new URL('../public/manifest.webmanifest', import.meta.url)));
assert.equal(manifest.display, 'standalone');
assert.ok(manifest.icons.some(icon => icon.sizes === '512x512' && icon.purpose === 'maskable'));
for (const icon of manifest.icons) assert.ok(fs.existsSync(new URL('../public' + icon.src, import.meta.url)), icon.src);
assert.match(fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8'), /rel="manifest" href="\/manifest.webmanifest"/);

// Run the worker's fetch handler against representative requests.
const listeners = {};
const cachePuts = [];
const context = {
  self: {location: {origin: 'https://riksora.test'}, addEventListener: (type, fn) => { listeners[type] = fn; }, skipWaiting() {}, clients: {claim() {}}},
  caches: {match: async () => undefined, open: async () => ({put: (req) => cachePuts.push(req.url), addAll: async () => {}}), keys: async () => [], delete: async () => true},
  fetch: async () => ({ok: true, type: 'basic', clone() { return this; }}),
  URL,
};
vm.runInNewContext(fs.readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8'), context);
const intercepted = (url, {method = 'GET', mode = 'cors'} = {}) => {
  let responded = false;
  listeners.fetch({request: {url, method, mode}, respondWith: promise => { responded = true; return promise; }, waitUntil() {}});
  return responded;
};
assert.equal(intercepted('https://riksora.test/api/v1/auth/session'), false, 'auth API untouched');
assert.equal(intercepted('https://riksora.test/api/v1/sessions/abc/view'), false, 'session/ledger view untouched');
assert.equal(intercepted('http://127.0.0.1:5188/tick-alpha/sessions'), false, 'cross-origin API untouched');
assert.equal(intercepted('https://riksora.test/assets/index-abc.js', {method: 'POST'}), false, 'non-GET untouched');
assert.equal(intercepted('https://riksora.test/assets/index-abc.js'), true, 'hashed asset served from shell cache');
assert.equal(intercepted('https://riksora.test/?session=1', {mode: 'navigate'}), true, 'navigation is network-first with offline shell');
await new Promise(resolve => setTimeout(resolve, 10));
assert.ok(cachePuts.every(url => /\/assets\//.test(url)), 'only shell assets are written to the cache: ' + cachePuts.join(','));
console.log('F08 PWA tests passed');
