// P1 (founder round 2): the workspace names the instrument from the Session's pinned
// server profile, never a hardcoded XAUUSD, and fails closed when the profile does
// not state one. Real local backend (synthetic source); the /view response's
// `state.profile.instrumentId` is REWRITTEN in the browser (labeled fixture) to prove
// the label follows the profile. The POST /reviews payload must stay unchanged.
// Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/session-instrument-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-session-instrument'; fs.mkdirSync(out, { recursive: true });
const base = process.env.QA_BASE || 'http://127.0.0.1:5196';
const API = 'http://127.0.0.1:5188/api/v1/tick-alpha';
const HEADERS = { 'X-BTL-Local': '1', 'X-BTL-Source': 'synthetic', Origin: 'http://127.0.0.1:5196', 'Content-Type': 'application/json' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
let passed = 0; const fail = [];
const must = (ok, msg) => { if (!ok) throw Error(msg); };
const call = async (path, body) => { const r = await fetch(API + path, body === undefined ? { headers: HEADERS } : { method: 'POST', headers: HEADERS, body: JSON.stringify(body) }); const v = await r.json(); if (!r.ok) throw Error(`${path} ${r.status} ${v.detail}`); return v; };

(async () => {
  const catalog = await call('/catalog');
  const method = catalog.methods.find(m => m.kind === 'FREE_STYLE' && !m.checklistOn);
  const session = (await call('/sessions', { id: `session:qa-instrument-${Date.now()}`, name: 'QA instrument label', methodId: method.id, startPeriod: catalog.startPeriod, initialBalance: '10000' })).metadata;
  const browser = await chromium.launch();
  const run = async (label, viewport, rewrite, fn) => {
    const ctx = await browser.newContext(viewport); const page = await ctx.newPage(); const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    if (rewrite) await page.route('**/sessions/*/view', async route => { // INJECTED: profile rewritten, labeled fixture
      const r = await route.fetch(); const v = await r.json(); rewrite(v.state.profile); v.label = 'QA FIXTURE / PROFILE REWRITE / ' + v.label;
      await route.fulfill({ response: r, body: JSON.stringify(v) });
    });
    try {
      await page.goto(`${base}/?tick-alpha=local&session=${encodeURIComponent(session.id)}`); await page.waitForSelector('.candle-chart canvas', { timeout: 20000 }); await sleep(1000);
      const note = await fn(page);
      must(!errors.length, 'page errors: ' + errors.join(' | '));
      passed++; console.log('PASS', label, note || '');
    } catch (e) { fail.push(label); console.log('FAIL', label, e.message.split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${label.replace(/[^a-z0-9]+/gi, '-').slice(0, 30)}.png` }); }
    await ctx.close();
  };
  const phone = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };

  await run('real profile: XAUUSD comes from the Session; review payload keys unchanged', { viewport: { width: 1280, height: 860 } }, null, async page => {
    must(await page.getByRole('button', { name: 'XAUUSD data source' }).isVisible(), 'chip');
    const body = page.waitForRequest(r => r.url().endsWith('/reviews') && r.method() === 'POST');
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click(); await page.getByRole('button', { name: 'Review order' }).click();
    const keys = Object.keys((await body).postDataJSON()).sort().join(',');
    must(keys === 'draft,expectedRevision,planId,planRevision,requestId,sessionId', 'payload keys ' + keys);
    return keys;
  });

  await run('profile says EURUSD: header, chip, aria label, phone title and source details follow it', phone, p => { p.instrumentId = 'EURUSD'; }, async page => {
    must(await page.locator('.alpha-symbol-chip').getAttribute('aria-label') === 'EURUSD data source', 'chip aria'); // chip is hidden at phone width
    must(await page.locator('.alpha-ws-phone-title strong').textContent() === 'EURUSD · 1m', 'phone title');
    must(!(await page.locator('body').innerText()).includes('XAUUSD'), 'XAUUSD still shown somewhere');
    await page.screenshot({ path: `${out}/instrument-eurusd-390.png` });
    await page.locator('.alpha-session button[aria-label="Data source"]').evaluate(el => el.click()); await sleep(300);
    must(await page.getByText(/EURUSD · USD · feed symbol SYNTHETIC_INSTRUMENT/).isVisible(), 'source details');
  });

  await run('profile without an instrument: fails closed, orders locked', phone, p => { delete p.instrumentId; }, async page => {
    must(await page.locator('.alpha-symbol-chip').getAttribute('aria-label') === 'Instrument not stated data source', 'fallback label');
    must(await page.locator('.alpha-ws-phone-title strong').textContent() === 'Instrument not stated · 1m', 'phone title');
    must(await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').isDisabled(), 'Buy enabled');
    must(await page.locator('.alpha-order-bar button[aria-label^="Sell at Bid"]').isDisabled(), 'Sell enabled');
    must(!(await page.locator('body').innerText()).includes('XAUUSD'), 'XAUUSD invented');
    await page.screenshot({ path: `${out}/instrument-missing-390.png` });
  });

  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
