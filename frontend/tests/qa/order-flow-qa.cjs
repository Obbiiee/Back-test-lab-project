// C-09 integration QA against the REAL local backend (Codex's execution.local_api,
// unchanged) and the synthetic fixture source (`?tick-alpha=local`).
// Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/order-flow-qa.cjs <outDir>
// Covers: Long Position drawing → Create order → server review → confirm →
// future quotes → actual order; drawing undo never undoes a committed order;
// no-lookahead after step/seek; drawing + indicator persistence across reload.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-out';
const base = process.env.QA_BASE || 'http://127.0.0.1:5196';
fs.mkdirSync(out, { recursive: true });
const results = [], api = [], errors = [];
const step = (name, detail = '') => { results.push({ name, detail }); console.log('PASS', name, detail); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on('pageerror', e => errors.push(e.message));
  let lastView = null;
  page.on('response', async r => {
    if (!r.url().includes('127.0.0.1:5188')) return;
    api.push({ method: r.request().method(), path: r.url().replace(/.*tick-alpha/, ''), status: r.status() });
    if (r.status() >= 400) console.log('API refusal', r.url().replace(/.*tick-alpha/, ''), r.status(), (await r.text().catch(() => '')).slice(0, 300), '| request', (r.request().postData() || ''));
    if (r.status() === 200 && /\/(view|commands)$/.test(r.url())) { try { const json = await r.json(); const v = json.view ?? json; if (v?.chart?.candles && v?.state?.throughNs) lastView = v; } catch { /* non-JSON */ } }
  });
  const calls = re => api.filter(c => c.method === 'POST' && re.test(c.path));
  const dump = () => page.locator('footer').innerText();
  await page.goto(base + '/?tick-alpha=local'); await sleep(1500);

  // 1. Strategy + Sessions through the real UI.
  const tag = 'C09-' + Date.now().toString(36);
  await page.getByRole('button', { name: /^(Create a strategy|New strategy)$/ }).first().click();
  await page.locator('input[name=name]').fill(tag); await page.getByRole('button', { name: 'Save strategy' }).click(); await sleep(1200);
  const newSession = async name => {
    if (await page.locator('.candle-chart').count()) { await page.goto(base + '/?tick-alpha=local'); await sleep(1500); }
    await page.getByRole('button', { name: 'New Session' }).first().click();
    const methodOption = await page.locator('select[name=method] option', { hasText: tag }).getAttribute('value');
    await page.locator('select[name=method]').selectOption(methodOption);
    await page.locator('input[name=name]').fill(name); await page.getByRole('button', { name: 'Save Session' }).click();
    await page.waitForSelector('.candle-chart canvas'); await sleep(1500);
    assert.equal(calls(/^\/sessions$/).at(-1)?.status, 200);
  };
  const seek = async value => {
    if (!(await page.locator('.alpha-seek').evaluate(el => el.open))) await page.locator('.alpha-seek summary').click();
    await page.getByLabel('Seek UTC').fill(value);
    const beforeNs = lastView?.state.throughNs;
    const settled = page.waitForResponse(r => /\/commands$/.test(r.url()), { timeout: 15000 });
    await page.getByRole('button', { name: 'Seek replay' }).click();
    const response = await settled;
    // The app reloads the view after an accepted command; wait until it has been observed.
    for (let i = 0; response.status() === 200 && lastView?.state.throughNs === beforeNs && i < 50; i++) await sleep(200);
    await sleep(500);
    return response.status();
  };
  const ns = iso => BigInt(Date.parse(iso + ':00Z')) * 1000000n;
  const completed = (view, uptoNs) => view.chart.candles.filter(c => !c.incomplete && BigInt(c.time) * 1000000000n < uptoNs);
  const noLookahead = view => view.chart.candles.every(c => BigInt(c.time) * 1000000000n <= BigInt(view.state.throughNs));

  // 1a. Normal replay: one Session steps tick by tick to 01:00.
  await newSession(tag + ' normal');
  const target = '2020-01-01T01:00';
  await page.getByLabel('Replay speed').selectOption('16');
  for (let i = 0; i < 12 && (!lastView || BigInt(lastView.state.throughNs) < ns(target)); i++) { await page.getByRole('button', { name: 'Step ticks' }).click(); await sleep(900); }
  const normal = lastView;
  assert.ok(BigInt(normal.state.throughNs) >= ns(target), 'normal replay reached the target');
  assert.ok(noLookahead(normal), 'normal replay shows no candle after the cursor');

  // 1b. Jump: the trading Session seeks straight to 01:00.
  await newSession(tag + ' session');
  assert.equal(await seek(target), 200);
  const jump = lastView;
  assert.ok(BigInt(jump.state.throughNs) <= ns(target), 'jump cursor at or before the target');
  assert.ok(BigInt(jump.state.throughNs) > ns(target) - 60000000000n, 'jump actually reached the target minute');
  assert.ok(noLookahead(jump), 'jump shows no candle after the cursor');
  const a = completed(jump, BigInt(jump.state.throughNs)), b = completed(normal, BigInt(jump.state.throughNs));
  assert.ok(a.length > 10, 'jump revealed history');
  assert.deepEqual(a.map(c => [c.time, c.open, c.high, c.low, c.close]), b.slice(-a.length).map(c => [c.time, c.open, c.high, c.low, c.close]), 'jump and normal replay reveal identical completed candles');
  step('Jump vs normal replay: identical completed candles, none after the cursor', `${a.length} completed 1m candles compared up to ${new Date(Number(BigInt(jump.state.throughNs) / 1000000n)).toISOString()}`);
  await page.screenshot({ path: `${out}/01-session-after-jump.png` });

  const canvas = page.locator('.candle-chart canvas').first();
  const box = await canvas.boundingBox();
  const chartState = () => page.evaluate(() => { const el = document.querySelector('.candle-chart'); return { drawings: JSON.parse(el.getAttribute('data-primitive-drawings') || '[]').length }; });
  const objectCount = async () => {
    const toggle = page.getByRole('button', { name: 'Drawing objects' });
    if ((await toggle.getAttribute('aria-expanded')) !== 'true') await toggle.click();
    await sleep(200); return page.locator('.alpha-object-tree li').count();
  };
  const lastBarTime = () => page.locator('.alpha-display-details summary').first().textContent();

  // 2. Long Position planning drawing.
  await page.getByLabel('Positions drawing tools').click();
  await page.getByRole('button', { name: 'Long Position', exact: true }).click();
  await page.mouse.click(box.x + box.width * .7, box.y + box.height * .45); await sleep(600);
  const createOrder = page.getByRole('button', { name: 'Create order' });
  await createOrder.waitFor({ timeout: 5000 });
  assert.equal(calls(/\/reviews|\/confirm/).length, 0, 'Drawing alone sends no order command');
  step('Long Position drawn; nothing sent to the server', 'Create order offered, 0 review/confirm calls');
  await page.screenshot({ path: `${out}/02-long-position.png` });

  // 3. Create order → ticket prefilled with rounded levels.
  await createOrder.click(); await sleep(600);
  const ticket = page.locator('.alpha-ticket');
  await ticket.waitFor();
  const fields = await ticket.locator('input,select').evaluateAll(els => Object.fromEntries(els.map(e => [e.getAttribute('aria-label') || e.name, e.value])));
  fs.writeFileSync(`${out}/ticket-fields.json`, JSON.stringify(fields, null, 2));
  assert.ok(Object.values(fields).some(v => /^\d+(\.\d+)?$/.test(v)), 'ticket has numeric prefilled levels');
  assert.equal(calls(/\/reviews|\/confirm/).length, 0, 'Opening the ticket sends nothing');
  assert.equal(await ticket.getByRole('group', { name: 'Order direction' }).locator('[aria-pressed=true]').textContent().then(t => /Long/.test(t)), true, 'Long Position → Buy / Long');
  assert.ok(Number(fields['Stop Loss']) < Number(fields.Entry) && Number(fields['Take Profit']) > Number(fields.Entry), 'Long: SL below, TP above entry');
  step('Create order copies the planned levels into the ticket draft', JSON.stringify(fields).slice(0, 200));
  await page.screenshot({ path: `${out}/03-ticket-prefilled.png` });

  // 4a. Protocol refuses a forbidden order: Buy Limit above the Ask.
  const ask = Number(lastView.quote.ask);
  const setLevels = async (entry, sl, tp) => {
    for (const [label, value] of [['Entry', entry], ['Stop Loss', sl], ['Take Profit', tp]]) await ticket.getByLabel(label, { exact: true }).fill(value.toFixed(2));
  };
  await setLevels(ask + 2, ask + 1, ask + 3);
  await page.getByRole('button', { name: 'Review order' }).click(); await sleep(1200);
  assert.equal(calls(/\/reviews$/).at(-1)?.status, 409, 'server refuses Buy Limit above Ask');
  assert.equal(calls(/\/confirm$/).length, 0);
  assert.equal(await page.getByRole('heading', { name: 'Confirm reviewed order' }).count(), 0, 'no confirm step for a refused review');
  step('Server refuses a forbidden order (Buy Limit above Ask); nothing committed', `Ask ${ask}, refusal: ${(await dump()).slice(0, 80)}`);
  await page.screenshot({ path: `${out}/04a-review-refused.png` });

  // 4b. Valid market intent with protective levels → server review (no state change) → confirm.
  await ticket.getByLabel('Order type', { exact: true }).selectOption('MARKET'); await sleep(200);
  await setLevels(ask, ask - 1.5, ask + 1.5);
  await page.getByRole('button', { name: 'Review order' }).click(); await sleep(1200);
  const reviewCall = calls(/\/reviews$/).at(-1);
  if (reviewCall?.status !== 200) { await page.screenshot({ path: `${out}/04-review-refused.png` }); throw Error('Review refused: ' + (await dump())); }
  await page.getByRole('heading', { name: 'Confirm reviewed order' }).waitFor();
  assert.equal(calls(/\/confirm$/).length, 0);
  step('Server review returned; nothing committed before Confirm', `POST /reviews ${reviewCall.status}`);
  await page.screenshot({ path: `${out}/04-server-review.png` });
  await page.getByRole('button', { name: 'Confirm order' }).click(); await sleep(1500);
  const confirmCall = calls(/\/confirm$/).at(-1);
  assert.equal(confirmCall?.status, 200, 'confirm accepted');
  step('Confirm accepted by the server', `POST ${confirmCall.path} ${confirmCall.status}`);
  await page.screenshot({ path: `${out}/05-confirmed.png` });

  // 5. Future quotes → actual order lifecycle.
  const ordersText = async () => {
    const text = [];
    for (const tab of ['Open positions', 'Pending orders', 'Closed trades']) { await page.getByRole('tab', { name: tab }).or(page.getByRole('button', { name: tab, exact: true })).first().click().catch(() => {}); await sleep(200); text.push(tab + ': ' + (await page.locator('table').last().innerText().catch(() => '')).replace(/\s+/g, ' ').slice(0, 300)); }
    return text.join('\n');
  };
  const confirmedAt = BigInt(lastView.state.throughNs);
  const pendingText = await ordersText();
  assert.match(pendingText, /LONG PENDING/, 'confirmed intent waits for an eligible (future) tick; no fill at confirm time');
  const before = await lastBarTime();
  let lifecycle = pendingText;
  for (let i = 0; i < 20 && /LONG PENDING/.test(lifecycle); i++) { await page.getByRole('button', { name: 'Step ticks' }).click(); await sleep(900); lifecycle = await ordersText(); }
  assert.notEqual(before, await lastBarTime(), 'replay advanced');
  fs.writeFileSync(`${out}/orders-after-replay.txt`, pendingText + '\n---\n' + lifecycle);
  assert.doesNotMatch(lifecycle, /LONG PENDING/, 'order filled by a later quote');
  assert.match(lifecycle, /Open positions:.*LONG|Closed trades:.*LONG/, 'filled order shown as a position or closed trade');
  const filledThrough = BigInt(lastView.state.throughNs);
  assert.ok(filledThrough > confirmedAt, 'fill comes from a quote revealed after confirmation');
  step('Pending until a later quote; then filled by the server', `${new Date(Number(confirmedAt / 1000000n)).toISOString().slice(11, 19)} pending → ${new Date(Number(filledThrough / 1000000n)).toISOString().slice(11, 19)} filled`);
  await page.screenshot({ path: `${out}/06-order-after-quotes.png` });

  // 6. Undo the planning drawing: the committed order must stay.
  const drawingsBefore = await objectCount();
  assert.ok(drawingsBefore >= 1, 'Long Position listed in the object tree');
  await page.getByRole('button', { name: /Undo/ }).first().click(); await sleep(500);
  const drawingsAfter = await objectCount();
  assert.equal(drawingsAfter, drawingsBefore - 1, 'Undo removed the planning drawing');
  const lifecycleAfterUndo = await ordersText();
  assert.equal(lifecycleAfterUndo.replace(/\d{2}:\d{2}:\d{2}/g, ''), lifecycle.replace(/\d{2}:\d{2}:\d{2}/g, ''), 'Undo never undoes a committed order');
  assert.equal(calls(/cancel|close/i).length, 0);
  step('Drawing Undo removes the plan but leaves the committed order untouched', `objects ${drawingsBefore} → ${drawingsAfter}, orders unchanged, 0 cancel/close calls`);

  // 7. With an order on the books the server refuses Seek; the UI says so and nothing moves.
  const cursorBefore = lastView.state.throughNs;
  assert.equal(await seek('2020-01-01T03:00'), 409);
  assert.match(await dump(), /REFUSED_REWIND_REQUIRES_FORK/);
  assert.equal(lastView.state.throughNs, cursorBefore, 'cursor unchanged after refused seek');
  assert.ok(noLookahead(lastView));
  step('Seek after an order is refused by the server and shown to the user', (await dump()).slice(0, 120));
  await page.screenshot({ path: `${out}/07-seek-refused-with-order.png` });

  // 8. Persistence: a research drawing + an indicator survive reload.
  await page.getByLabel('Lines drawing tools').click();
  await page.getByRole('button', { name: 'Horizontal Line', exact: true }).click();
  await page.mouse.click(box.x + box.width * .5, box.y + box.height * .3); await sleep(400);
  await page.getByRole('button', { name: 'Indicators' }).first().click(); await sleep(400);
  const dialog = page.getByRole('dialog', { name: 'Overlay indicators' });
  await dialog.getByRole('button', { name: 'Add Simple Moving Average', exact: true }).or(dialog.getByRole('button', { name: /^Add SMA/ })).first().click(); await sleep(300);
  const saved = await page.evaluate(() => Object.keys(localStorage).filter(k => /backtest-(drawing-manager-v2|indicators-v1):/.test(k)).map(k => [k, JSON.parse(localStorage.getItem(k))]));
  await page.keyboard.press('Escape');
  const countBefore = await objectCount();
  await page.reload(); await page.waitForSelector('.candle-chart canvas'); await sleep(2000);
  const reopen = page.getByRole('button', { name: new RegExp(tag + ' session') });
  if (await reopen.count()) { await reopen.first().click(); await page.waitForSelector('.candle-chart canvas'); await sleep(1500); }
  const countAfter = await objectCount();
  assert.ok(countBefore >= 1 && countAfter === countBefore, `drawings persisted ${countBefore} → ${countAfter}`);
  assert.ok(saved.some(([k, v]) => k.includes('drawing-manager-v2') && v.version), 'versioned drawing document');
  const indicatorsAfter = await page.evaluate(() => { const k = Object.keys(localStorage).find(key => key.startsWith('backtest-indicators-v1:')); return k ? JSON.parse(localStorage.getItem(k)) : null; });
  assert.ok(indicatorsAfter?.version && indicatorsAfter.instances.length >= 1, 'versioned indicator settings persisted');
  const lifecycleAfterReload = await ordersText();
  assert.match(lifecycleAfterReload, /LONG|Long|Buy|BUY/, 'order still present after reload (server state)');
  step('Reload keeps versioned drawings/indicators and the server-side order', `${countAfter} drawings, ${indicatorsAfter.instances.length} indicator(s), keys: ${saved.map(([k]) => k.split(':')[0]).join(', ')}`);
  await page.screenshot({ path: `${out}/08-after-reload.png` });

  // 9. Phone (390×844, touch): Long Position → Create order → ticket usable on screen.
  const phone = await (await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })).newPage();
  phone.on('pageerror', e => errors.push('phone: ' + e.message));
  await phone.goto(base + '/?tick-alpha=local'); await sleep(1500);
  await phone.getByRole('button', { name: `Open ${tag} normal` }).tap();
  await phone.waitForSelector('.candle-chart canvas'); await sleep(1500);
  const pbox = await phone.locator('.candle-chart canvas').first().boundingBox();
  await phone.getByLabel('Positions drawing tools').tap();
  await phone.getByRole('button', { name: 'Long Position', exact: true }).tap();
  await phone.touchscreen.tap(pbox.x + pbox.width * .6, pbox.y + pbox.height * .5); await sleep(700);
  await phone.getByRole('button', { name: 'Create order' }).tap(); await sleep(700);
  const pticket = phone.locator('.alpha-ticket');
  await pticket.waitFor();
  const tb = await pticket.boundingBox();
  const poverflow = await phone.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(tb.x >= 0 && tb.x + tb.width <= 390 + 1, `ticket fits the phone width (${Math.round(tb.x)}…${Math.round(tb.x + tb.width)})`);
  assert.ok(poverflow <= 0, `no horizontal overflow (${poverflow}px)`);
  assert.ok(await phone.getByRole('button', { name: 'Review order' }).isVisible() || await phone.getByRole('button', { name: 'Review order' }).count(), 'Review reachable');
  assert.equal(calls(/\/reviews|\/confirm/).length, 3, 'phone flow sent no extra command (2 reviews + 1 confirm from the desktop run)');
  step('Phone 390×844: tap Long Position → Create order → ticket fits, nothing sent', `ticket ${Math.round(tb.width)}px wide`);
  await phone.screenshot({ path: `${out}/09-phone-ticket.png` });
  await phone.getByRole('button', { name: 'Close order panel' }).tap(); await sleep(400);
  await phone.getByLabel('Positions drawing tools').tap();
  await phone.getByRole('button', { name: 'Short Position', exact: true }).tap();
  await phone.touchscreen.tap(pbox.x + pbox.width * .4, pbox.y + pbox.height * .5); await sleep(700);
  await phone.getByRole('button', { name: 'Create order' }).tap(); await sleep(700);
  const sfields = await pticket.locator('input').evaluateAll(els => Object.fromEntries(els.map(e => [e.getAttribute('aria-label') || e.name, e.value])));
  assert.match(await pticket.getByRole('group', { name: 'Order direction' }).locator('[aria-pressed=true]').textContent(), /Short/, 'Short Position → Sell / Short');
  assert.ok(Number(sfields['Stop Loss']) > Number(sfields.Entry) && Number(sfields['Take Profit']) < Number(sfields.Entry), 'Short: SL above, TP below entry');
  assert.equal(calls(/\/reviews|\/confirm/).length, 3, 'Short planning sent nothing');
  step('Phone: Short Position → Create order → Sell / Short with SL above and TP below', `entry ${sfields.Entry} · SL ${sfields['Stop Loss']} · TP ${sfields['Take Profit']}`);
  await phone.screenshot({ path: `${out}/10-phone-short-ticket.png` });
  await phone.context().close();

  assert.deepEqual(errors, [], 'no page errors');
  fs.writeFileSync(`${out}/results.json`, JSON.stringify({ results, api: api.filter(c => c.method === 'POST'), errors }, null, 2));
  await browser.close();
  console.log(`order flow QA: ${results.length} steps passed`);
})().catch(async e => { console.error(e); console.error('API', JSON.stringify(api.slice(-8))); process.exit(1); });
