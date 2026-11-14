// Audit 14 Nov 2026, scenarios 5 and 12, real local backend.
//   5   Free Style: a Quick order and a Planned order (stop + target) both confirm
//   12  every timeframe returns only candles at or before the replay cursor, before
//       and after stepping the replay; an indicator survives a timeframe change
// Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/orders-chart-qa.cjs <outDir>
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-orders-chart'; fs.mkdirSync(out, { recursive: true });
const base = process.env.QA_BASE || 'http://127.0.0.1:5196';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const tag = 'OC-' + Date.now().toString(36).slice(-5);
let passed = 0; const failed = [], errors = [], api = [];
const TFS = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', 'D'];
(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  let lastView = null;
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', async r => {
    if (!r.url().includes('127.0.0.1:5188')) return;
    const path = r.url().replace(/.*tick-alpha/, '');
    const row = { method: r.request().method(), path, status: r.status(), body: r.request().postData() };
    if (/\/view$/.test(path) && r.status() === 200) { try { const v = await r.json(); row.view = v; lastView = v; } catch { /* not json */ } }
    api.push(row);
  });
  const posts = re => api.filter(c => c.method === 'POST' && re.test(c.path));
  const run = async (label, fn) => {
    try { const note = await fn(); passed++; console.log('PASS', label, note || ''); }
    catch (e) { failed.push(label); console.log('FAIL', label, String(e.message).split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${label.replace(/[^a-z0-9]+/gi, '-').slice(0, 40)}.png` }); }
  };
  const name = `${tag} FREE`;
  await page.goto(base + '/?tick-alpha=local&screen=method-new'); await sleep(1200);
  await page.getByLabel('Method name').fill(name); await page.getByRole('button', { name: 'Save Method' }).click(); await sleep(1200);
  await page.goto(base + '/?tick-alpha=local&screen=session-new'); await sleep(1500);
  await page.locator('.rk-combo-trigger').first().click(); await page.keyboard.type(name); await sleep(200); await page.keyboard.press('Enter');
  for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByLabel('Session name').fill(`${name} S1`); await page.getByRole('button', { name: 'Continue' }).click();
  await page.getByRole('button', { name: 'Create Session' }).click();
  await page.waitForSelector('.candle-chart canvas'); await sleep(1500);

  const ask = async () => Number((await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').getAttribute('aria-label')).replace(/.*Ask /, ''));
  const confirmSheet = async () => {
    await page.waitForFunction(() => !document.querySelector('.alpha-review-primary')?.disabled, null, { timeout: 15000 });
    const before = posts(/\/confirm$/).length;
    await page.locator('.alpha-review-primary').click();
    for (let i = 0; i < 40 && posts(/\/confirm$/).length === before; i++) await sleep(150);
    await sleep(800);
    return posts(/\/confirm$/).at(-1);
  };
  const reviewClick = async () => {
    const before = posts(/\/reviews$/).length;
    await page.getByRole('button', { name: 'Review order' }).click();
    for (let i = 0; i < 40 && posts(/\/reviews$/).length === before; i++) await sleep(150);
    return posts(/\/reviews$/).at(-1);
  };

  await run('5 · Free Style Quick order: market, no stop or target, confirmed', async () => {
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click();
    await page.getByRole('heading', { name: 'Plan an order' }).waitFor();
    assert.equal(await page.getByRole('radio', { name: 'Quick' }).getAttribute('aria-checked'), 'true', 'Quick should be the default');
    const r = await reviewClick(); assert.equal(r.status, 200, 'review ' + r.status);
    const d = JSON.parse(r.body).draft;
    assert.equal(d.workflow, 'QUICK'); assert.equal(d.orderType, 'MARKET'); assert.ok(!d.sl && !d.tp, 'quick sent a stop or target');
    const c = await confirmSheet(); assert.equal(c.status, 200, 'confirm ' + c.status);
    return `${d.side} ${d.quantity ?? ''} lots`;
  });
  await run('5 · Free Style Planned order: limit with stop and target, confirmed', async () => {
    const a = await ask();
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click();
    await page.getByRole('heading', { name: 'Plan an order' }).waitFor();
    await page.getByRole('radio', { name: 'Plan · R:R' }).click();
    await page.getByLabel('Entry', { exact: true }).fill((a - 1).toFixed(2));
    await page.getByLabel('Stop Loss', { exact: true }).fill((a - 6).toFixed(2));
    await page.getByRole('button', { name: 'TP 2R' }).click();
    const r = await reviewClick(); assert.equal(r.status, 200, 'review ' + r.status);
    const d = JSON.parse(r.body).draft;
    assert.equal(d.workflow, 'PLANNED'); assert.ok(d.sl && d.tp, 'planned order lost its stop or target');
    const c = await confirmSheet(); assert.equal(c.status, 200, 'confirm ' + c.status);
    return `limit ${d.entry} sl ${d.sl} tp ${d.tp}`;
  });

  await run('12 · every timeframe: no candle after the cursor, before and after stepping', async () => {
    const sel = page.getByLabel('Chart timeframe');
    const check = (v, tf, when) => { const cursor = BigInt(v.state.throughNs); for (const c of v.chart.candles) assert.ok(BigInt(c.time) * 1000000000n <= cursor, `${tf} ${when}: candle ${c.time} is after the cursor`); return v.chart.candles.length; };
    let total = 0;
    for (const tf of TFS) {
      await sel.selectOption(tf); await sleep(1100);
      assert.equal(lastView.chart.timeframe, tf, 'view did not change timeframe to ' + tf);
      total += check(lastView, tf, 'before');
    }
    await sel.selectOption('1m'); await sleep(1000);
    for (let i = 0; i < 3; i++) { await page.getByRole('button', { name: 'Step ticks' }).click(); await sleep(900); }
    for (const tf of ['1m', '5m', '1h']) { await sel.selectOption(tf); await sleep(1000); total += check(lastView, tf, 'after stepping'); }
    return `${TFS.length} timeframes, ${total} candles checked`;
  });
  await run('12 · an indicator survives a timeframe change and stays after a reload', async () => {
    await page.getByRole('button', { name: 'Indicators', exact: true }).click(); await sleep(300);
    await page.getByRole('button', { name: 'Add SMA', exact: true }).click(); await sleep(400);
    await page.keyboard.press('Escape'); await sleep(300);
    await page.getByLabel('Chart timeframe').selectOption('5m'); await sleep(1100);
    const stored = () => page.evaluate(() => Object.keys(localStorage).filter(k => k.startsWith('backtest-indicators-v1:')).map(k => JSON.parse(localStorage.getItem(k)).instances.length));
    assert.ok((await stored()).some(n => n >= 1), 'indicator not stored');
    await page.reload(); await page.waitForSelector('.candle-chart canvas'); await sleep(1500);
    assert.ok((await stored()).some(n => n >= 1), 'indicator lost after reload');
  });
  await run('no page errors', async () => { assert.deepEqual(errors, []); });
  await browser.close();
  console.log(`\n${passed} passed, ${failed.length} failed`);
  if (failed.length) process.exit(1);
})();
