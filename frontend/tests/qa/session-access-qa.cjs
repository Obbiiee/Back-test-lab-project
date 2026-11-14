// Audit 14 Nov 2026, scenarios 8 and 13 against the REAL local backend.
//   13  a Session the workspace does not hold (another account's id looks the same
//       to the server: not found) shows a safe message and no data; the service going
//       away shows an offline state and Retry reconnects; a refresh keeps the Session
//   8   resume after a reload: same Method, pair, source and committed order; an
//       unconfirmed draft is NOT restored (it could be confirmed against stale prices)
// Account-mode isolation between two real users needs the HTTPS identity service and
// is not covered here.
// Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/session-access-qa.cjs <outDir>
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-access'; fs.mkdirSync(out, { recursive: true });
const base = process.env.QA_BASE || 'http://127.0.0.1:5196';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const tag = 'SA-' + Date.now().toString(36).slice(-5);
let passed = 0; const failed = [], errors = [], api = [];
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', async r => { if (r.url().includes('127.0.0.1:5188')) api.push({ method: r.request().method(), path: r.url().replace(/.*tick-alpha/, ''), status: r.status() }); });
  const run = async (label, fn) => {
    try { const note = await fn(); passed++; console.log('PASS', label, note || ''); }
    catch (e) { failed.push(label); console.log('FAIL', label, String(e.message).split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${label.replace(/[^a-z0-9]+/gi, '-').slice(0, 40)}.png` }); }
  };
  const text = () => page.locator('body').innerText();

  await run('13 · unknown Session id in the link: safe message, no chart, nothing changed', async () => {
    await page.goto(base + '/?tick-alpha=local&session=' + encodeURIComponent('session:not-mine-' + tag)); await sleep(2500);
    const t = await text();
    assert.match(t, /This Session could not be opened/);
    assert.match(t, /Nothing was changed/);
    assert.doesNotMatch(t, /Local service unavailable/, 'a refused Session must not read as a service outage');
    assert.equal(await page.locator('.candle-chart canvas').count(), 0, 'a chart was shown');
    await page.screenshot({ path: `${out}/session-unknown-link.png` });
  });
  await run('13 · unknown Session on the Session page: says it may belong to another workspace', async () => {
    await page.goto(base + '/?tick-alpha=local&screen=session&of=' + encodeURIComponent('session:not-mine-' + tag)); await sleep(2000);
    const t = await text();
    assert.match(t, /This Session is not in this workspace/);
    assert.match(t, /may belong to another/i);
    await page.screenshot({ path: `${out}/session-not-in-workspace.png` });
  });

  await run('13 · service goes away: offline state, then Retry reconnects', async () => {
    const c2 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p2 = await c2.newPage();
    await c2.route('http://127.0.0.1:5188/**', r => r.abort());
    await p2.goto(base + '/?tick-alpha=local'); await sleep(2500);
    const t = await p2.locator('body').innerText();
    assert.match(t, /Local service unavailable/);
    await p2.screenshot({ path: `${out}/service-offline.png` });
    await c2.unroute('http://127.0.0.1:5188/**');
    await p2.getByRole('button', { name: /Retry|Reconnect|Try again/i }).first().click(); await sleep(2500);
    const after = await p2.locator('body').innerText();
    assert.doesNotMatch(after, /Local service unavailable/);
    assert.match(after, /My Methods|Create your first Method/);
    await p2.screenshot({ path: `${out}/service-reconnected.png` });
    await c2.close();
  });

  // resume: a Free Style Session with one confirmed order
  const name = `${tag} FREE`;
  await page.goto(base + '/?tick-alpha=local&screen=method-new'); await sleep(1200);
  await page.getByLabel('Method name').fill(name); await page.getByRole('button', { name: 'Save Method' }).click(); await sleep(1200);
  await page.goto(base + '/?tick-alpha=local&screen=session-new'); await sleep(1500);
  await page.locator('.rk-combo-trigger').first().click(); await page.keyboard.type(name); await sleep(200); await page.keyboard.press('Enter');
  for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByLabel('Session name').fill(`${name} S1`); await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'Create Session' }).click();
  await page.waitForSelector('.candle-chart canvas'); await sleep(1500);
  const sessionUrl = () => page.url();

  await run('8 · confirm an order, then reload: same Method, pair, source and the committed order', async () => {
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click();
    await page.getByRole('heading', { name: 'Plan an order' }).waitFor();
    await page.getByRole('button', { name: 'Review order' }).click();
    await page.waitForFunction(() => !document.querySelector('.alpha-review-primary')?.disabled, null, { timeout: 15000 });
    await page.locator('.alpha-review-primary').click(); await sleep(1500);
    const before = await text();
    assert.match(before, new RegExp(name));
    const url = sessionUrl(); assert.match(url, /session=/);
    await page.reload(); await page.waitForSelector('.candle-chart canvas'); await sleep(1800);
    const after = await text();
    assert.match(after, new RegExp(name + ' S1'), 'Session name');
    assert.match(after, new RegExp(name + ' ·'), 'Method name in the header');
    assert.match(after, /XAUUSD/, 'pair');
    assert.ok(await page.getByRole('button', { name: /XAUUSD data source/ }).count(), 'source chip');
    await page.locator('.alpha-terminal-tabs button', { hasText: 'Pending orders' }).click();
    assert.ok(/Long|Buy/i.test(await page.locator('.alpha-terminal').innerText()), 'the committed order is missing after reload');
    await page.screenshot({ path: `${out}/resume-after-reload.png` });
  });
  await run('8 · an unconfirmed draft is not restored after a reload', async () => {
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click();
    await page.getByRole('heading', { name: 'Plan an order' }).waitFor();
    await page.getByRole('radio', { name: 'Plan · R:R' }).click();
    await page.getByLabel('Entry', { exact: true }).fill('1999.99');
    await page.reload(); await page.waitForSelector('.candle-chart canvas'); await sleep(1800);
    assert.equal(await page.getByRole('heading', { name: 'Plan an order' }).count(), 0, 'the ticket reopened by itself');
    assert.equal(await page.locator('.alpha-review-sheet').count(), 0, 'a review reopened by itself');
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click();
    await page.getByRole('heading', { name: 'Plan an order' }).waitFor();
    const entry = await page.getByLabel('Entry', { exact: true }).inputValue().catch(() => '');
    assert.notEqual(entry, '1999.99', 'the old draft entry came back');
  });

  await run('Sessions hub: cards, the last Session is marked and continues, Show more appears past 24', async () => {
    await page.goto(base + '/?tick-alpha=local&screen=sessions'); await sleep(1500);
    const cards = page.locator('ul[aria-label="Sessions"] > li');
    const n = await cards.count(); assert.ok(n >= 1 && n <= 24, 'cards ' + n);
    assert.ok(await page.getByRole('heading', { name: /Ready for the next round/ }).count(), 'hero should offer the last replay');
    assert.equal(await page.locator('.rk-session-card.is-last').count(), 1, 'last opened Session not marked');
    const total = Number((await page.locator('.rk-count').innerText()).match(/of (\d+)/)[1]);
    if (total > 24) { await page.getByRole('button', { name: /Show .* more/ }).click(); assert.ok(await cards.count() > n, 'Show more did nothing'); }
    await page.screenshot({ path: `${out}/sessions-hub.png` });
    await page.getByRole('button', { name: 'Continue replay' }).first().click();
    await page.waitForSelector('.candle-chart canvas', { timeout: 15000 });
    return `${n} cards of ${total}`;
  });
  await run('no page errors', async () => { assert.deepEqual(errors, []); });
  await browser.close();
  console.log(`\n${passed} passed, ${failed.length} failed`);
  if (failed.length) process.exit(1);
})();
