// Audit 14 Nov 2026, scenarios 2, 3, 4, 6, 7 and 10, against the REAL local backend
// (execution.local_api, unchanged) with the synthetic fixture source. Nothing is mocked.
//   2  Protocol locked R:R: moving the stop changes the reviewed target and lots
//   3  checklist ON: FAIL / NOT_ASSESSED refused, all PASS accepted and confirmed
//   4  checklist OFF: not blocked, and the observations are still sent and kept
//   6  Free Style -> Protocol -> Free Style: no order state leaks between Sessions
//   7  an edited or refused draft never leaves an old review that can be confirmed
//   10 terminal collapsed -> the phone Analysis button opens the Analysis content
// Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/protocol-rules-qa.cjs <outDir>
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-protocol'; fs.mkdirSync(out, { recursive: true });
const base = process.env.QA_BASE || 'http://127.0.0.1:5196';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const tag = 'PR-' + Date.now().toString(36).slice(-5);
let passed = 0; const failed = [], api = [], errors = [];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', async r => {
    if (!r.url().includes('127.0.0.1:5188')) return;
    const path = r.url().replace(/.*tick-alpha/, '');
    const row = { method: r.request().method(), path, status: r.status(), body: r.request().postData() };
    if (/\/reviews$/.test(path) && r.status() === 200) row.json = await r.json().catch(() => null);
    api.push(row);
  });
  const posts = re => api.filter(c => c.method === 'POST' && re.test(c.path));
  const run = async (label, fn) => {
    try { const note = await fn(); passed++; console.log('PASS', label, note || ''); }
    catch (e) { failed.push(label); console.log('FAIL', label, String(e.message).split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${label.replace(/[^a-z0-9]+/gi, '-').slice(0, 40)}.png` }); }
  };

  const newMethod = async (name, { protocol, checklist = true }) => {
    await page.goto(base + '/?tick-alpha=local&screen=method-new'); await sleep(1200);
    if (!(await page.getByLabel('Method name').count())) {
      await page.goto(base + '/?tick-alpha=local'); await sleep(1200);
      await page.getByRole('link', { name: /^(New Method|Create your first Method)$/ }).first().click(); await sleep(400);
    }
    await page.getByLabel('Method name').fill(name);
    if (protocol) {
      await page.getByRole('radio', { name: 'Protocol' }).click();
      await page.getByLabel('Condition 1', { exact: true }).fill('Trend aligned');
      await page.getByRole('button', { name: '+ Add condition' }).click();
      await page.getByLabel('Condition 2', { exact: true }).fill('Retest held');
      const box = page.getByRole('checkbox', { name: /Checklist enforcement/ });
      if ((await box.isChecked()) !== checklist) await box.setChecked(checklist, { force: true });
    }
    await page.getByRole('button', { name: 'Save Method' }).click(); await sleep(1200);
  };
  const newSession = async (methodName, name) => {
    await page.goto(base + '/?tick-alpha=local&screen=session-new'); await sleep(1500);
    await page.locator('.rk-combo-trigger').first().click(); await page.keyboard.type(methodName); await sleep(200); await page.keyboard.press('Enter');
    for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Continue' }).click();
    await page.getByLabel('Session name').fill(name); await page.getByRole('button', { name: 'Continue' }).click();
    await page.getByRole('button', { name: 'Create Session' }).click();
    await page.waitForSelector('.candle-chart canvas'); await sleep(1500);
  };
  const askBid = async () => {
    const buy = await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').getAttribute('aria-label');
    return Number(buy.replace(/.*Ask /, ''));
  };
  const openTicket = async () => {
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click();
    await page.getByRole('heading', { name: 'Plan an order' }).waitFor();
  };
  const ensureTicket = async () => { if (!(await page.getByRole('heading', { name: 'Plan an order' }).count())) await openTicket(); };
  const closeTicket = async () => { await page.getByRole('button', { name: 'Close order panel' }).click(); await sleep(300); };
  const setPrices = async (entry, sl) => {
    await page.getByLabel('Entry', { exact: true }).fill(String(entry));
    await page.getByLabel('Stop Loss', { exact: true }).fill(String(sl));
  };
  const setChecks = async outcomes => {
    for (const [label, value] of Object.entries(outcomes)) await page.getByLabel(label, { exact: true }).selectOption(value);
  };
  const review = async () => {
    const before = posts(/\/reviews$/).length;
    await page.getByRole('button', { name: 'Review order' }).click();
    for (let i = 0; i < 40 && posts(/\/reviews$/).length === before; i++) await sleep(150);
    await sleep(500);
    return posts(/\/reviews$/).at(-1);
  };
  const sheetText = async () => (await page.locator('.alpha-review-sheet').count()) ? page.locator('.alpha-review-sheet').innerText() : '';
  const reviewedNumber = (text, label) => { const m = text.match(new RegExp(label + '[^0-9\\-]*([0-9]+(?:\\.[0-9]+)?)', 'i')); return m ? Number(m[1]) : null; };

  const proOn = `${tag} ON`, proOff = `${tag} OFF`, free = `${tag} FREE`;
  await newMethod(proOn, { protocol: true, checklist: true });
  await newMethod(proOff, { protocol: true, checklist: false });
  await newMethod(free, { protocol: false });

  // ---- Protocol, checklist ON
  await newSession(proOn, `${proOn} S1`);
  const ask = await askBid();

  await run('2 · Protocol: moving the stop changes the reviewed target and lots (R:R stays locked)', async () => {
    await openTicket();
    await setChecks({ 'Trend aligned': 'PASS', 'Retest held': 'PASS' });
    await setPrices((ask - 1).toFixed(2), (ask - 6).toFixed(2));
    const first = await review();
    assert.equal(first.status, 200, 'review status ' + first.status);
    const a = await sheetText(); await page.screenshot({ path: `${out}/protocol-review-stop5.png` });
    await page.getByRole('button', { name: 'Cancel confirmation' }).click(); await sleep(400);
    await ensureTicket();
    await setPrices((ask - 1).toFixed(2), (ask - 11).toFixed(2));
    const second = await review();
    assert.equal(second.status, 200, 'review 2 status ' + second.status);
    const b = await sheetText(); await page.screenshot({ path: `${out}/protocol-review-stop10.png` });
    const pa = JSON.parse(first.body), pb = JSON.parse(second.body);
    const ra = (await page.evaluate(() => 0), a), rb = b;
    assert.notEqual(pa.requestId, pb.requestId, 'a new review is created, not reused');
    const rrA = a.match(/1 : ([0-9.]+)/)?.[1], rrB = b.match(/1 : ([0-9.]+)/)?.[1];
    assert.equal(rrA, rrB, `R:R changed ${rrA} -> ${rrB}`);
    assert.notEqual(a, b, 'moving the stop changed nothing in the reviewed values');
    const field = (t, name) => Number(t.match(new RegExp(name + '\\s+([0-9.]+)'))?.[1]);
    const [tpA, tpB, lotsA, lotsB] = [field(a, 'Take Profit'), field(b, 'Take Profit'), field(a, 'Lots'), field(b, 'Lots')];
    assert.ok(tpB > tpA, `target did not move with the stop (${tpA} -> ${tpB})`);
    assert.ok(lotsB < lotsA, `lots did not shrink for a wider stop (${lotsA} -> ${lotsB})`);
    return `R:R 1 : ${rrA}; stop 5 → TP ${tpA}, lots ${lotsA}; stop 10 → TP ${tpB}, lots ${lotsB}`;
  });

  await run('3a · checklist ON: NOT_ASSESSED is refused and nothing is saved', async () => {
    await page.getByRole('button', { name: 'Cancel confirmation' }).click().catch(() => {}); await sleep(300);
    await ensureTicket();
    await setChecks({ 'Trend aligned': 'PASS', 'Retest held': 'NOT_ASSESSED' });
    const r = await review();
    assert.ok(r.status >= 400 || !(await page.locator('.alpha-review-sheet').count()), 'review was created with an unassessed condition');
    const n = (await page.locator('.alpha-ticket-notice').innerText().catch(() => '')) || '';
    assert.equal(await page.locator('.alpha-review-sheet').count(), 0, 'sheet opened');
    assert.equal(posts(/\/confirm$/).filter(c => /PLACE|ORDER/i.test(c.body || '')).length, 0, 'an order command was sent');
    assert.equal(await page.locator('.alpha-check-unmet').count(), 1, 'the unmet condition is not marked');
    await page.screenshot({ path: `${out}/checklist-on-not-assessed.png` });
    return `HTTP ${r.status} · ${n.slice(0, 90)}`;
  });
  await run('3b · checklist ON: FAIL is refused', async () => {
    await setChecks({ 'Trend aligned': 'PASS', 'Retest held': 'FAIL' });
    const r = await review();
    assert.equal(await page.locator('.alpha-review-sheet').count(), 0, 'sheet opened for a FAIL');
    assert.equal(await page.locator('.alpha-check-unmet').count(), 1, 'the failed condition is not marked');
    await page.screenshot({ path: `${out}/checklist-on-fail.png` });
    return `HTTP ${r.status} · ${((await page.locator('.alpha-ticket-notice').innerText().catch(() => '')) || '').slice(0, 90)}`;
  });
  await run('3c · checklist ON: all PASS is accepted and confirmed', async () => {
    await setChecks({ 'Trend aligned': 'PASS', 'Retest held': 'PASS' });
    const r = await review(); assert.equal(r.status, 200, 'review ' + r.status);
    await page.waitForFunction(() => !document.querySelector('.alpha-review-primary')?.disabled, null, { timeout: 5000 });
    const before = posts(/\/confirm$/).length;
    await page.locator('.alpha-review-primary').click();
    for (let i = 0; i < 40 && posts(/\/confirm$/).length === before; i++) await sleep(150);
    await sleep(800);
    assert.equal(posts(/\/confirm$/).at(-1)?.status, 200, 'confirm status');
    assert.equal(await page.locator('.alpha-review-sheet').count(), 0, 'sheet should close after a saved order');
    await page.screenshot({ path: `${out}/checklist-on-pass-confirmed.png` });
  });

  // ---- Protocol, checklist OFF
  await newSession(proOff, `${proOff} S1`);
  await run('4 · checklist OFF: not blocked, observations still sent and shown in the review', async () => {
    const a = await askBid();
    await openTicket();
    assert.ok(await page.getByText(/not enforced/).count(), 'OFF caption missing');
    await setChecks({ 'Trend aligned': 'FAIL', 'Retest held': 'NOT_ASSESSED' });
    await setPrices((a - 1).toFixed(2), (a - 6).toFixed(2));
    const r = await review(); assert.equal(r.status, 200, 'review ' + r.status);
    const body = JSON.parse(r.body);
    const obs = body.draft?.observations ?? [];
    assert.equal(obs.length, 2, 'observations missing from the request');
    assert.deepEqual(obs.map(o => o.outcome).sort(), ['FAIL', 'NOT_ASSESSED']);
    const text = await sheetText();
    assert.match(text, /fail/i); assert.match(text, /not assessed/i);
    await page.screenshot({ path: `${out}/checklist-off-recorded.png` });
    await page.waitForFunction(() => !document.querySelector('.alpha-review-primary')?.disabled, null, { timeout: 5000 });
    const before = posts(/\/confirm$/).length;
    await page.locator('.alpha-review-primary').click();
    for (let i = 0; i < 40 && posts(/\/confirm$/).length === before; i++) await sleep(150);
    await sleep(800);
    assert.equal(posts(/\/confirm$/).at(-1)?.status, 200, 'confirm status');
    return 'fail + not assessed accepted';
  });

  // ---- 7: edited draft never leaves an old confirmable review
  await newSession(free, `${free} S1`);
  await run('7 · editing after Review leaves no old review to confirm; the new review carries the new values', async () => {
    const a = await askBid();
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click();
    await page.getByRole('heading', { name: 'Plan an order' }).waitFor();
    await page.getByRole('radio', { name: 'Plan · R:R' }).click();
    await setPrices((a - 1).toFixed(2), (a - 6).toFixed(2));
    await page.getByLabel('Take Profit', { exact: true }).fill((a + 8).toFixed(2));
    const first = await review(); assert.equal(first.status, 200);
    await page.getByRole('button', { name: 'Cancel confirmation' }).click(); await sleep(400);
    await ensureTicket();
    await page.getByLabel('Entry', { exact: true }).fill((a - 2).toFixed(2));
    assert.equal(await page.locator('.alpha-review-sheet').count(), 0, 'old sheet survived an edit');
    const second = await review(); assert.equal(second.status, 200);
    const d1 = JSON.parse(first.body).draft, d2 = JSON.parse(second.body).draft;
    assert.notEqual(d1.entry, d2.entry, 'second review did not use the edited entry');
    await page.waitForFunction(() => !document.querySelector('.alpha-review-primary')?.disabled, null, { timeout: 5000 });
    const before = posts(/\/confirm$/).length;
    await page.locator('.alpha-review-primary').click();
    for (let i = 0; i < 40 && posts(/\/confirm$/).length === before; i++) await sleep(150);
    await sleep(600);
    const sent = JSON.parse(posts(/\/confirm$/).at(-1).body);
    assert.equal(sent.reviewId, second.json.review.command.commandId, 'confirmed a different review than the one on screen');
    assert.notEqual(sent.reviewId, first.json.review.command.commandId, 'confirmed the old review');
    return `entry ${d1.entry} -> ${d2.entry}; the confirmed command used the new one`;
  });

  // ---- 6: Free Style -> Protocol -> Free Style
  await run('6 · Free Style → Protocol → Free Style: no draft or checklist state carries over', async () => {
    await page.goto(base + '/?tick-alpha=local'); await sleep(800);
    await newSession(free, `${free} S2`);
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click();
    await page.getByRole('heading', { name: 'Plan an order' }).waitFor();
    assert.ok(await page.getByRole('radio', { name: 'Plan · R:R' }).count(), 'free style ticket has the Quick / Plan tabs');
    assert.equal(await page.getByText(/Checklist · enforcement/).count(), 0, 'checklist shown for Free Style');
    await closeTicket();
    await newSession(proOn, `${proOn} S2`);
    await openTicket();
    assert.ok(await page.getByText(/Checklist · enforcement ON/).count(), 'protocol checklist missing');
    assert.equal(await page.getByLabel('Trend aligned', { exact: true }).inputValue(), 'NOT_ASSESSED', 'previous checklist answers leaked');
    await setChecks({ 'Trend aligned': 'PASS', 'Retest held': 'PASS' });
    await setPrices('1.00', '0.50');
    await closeTicket();
    await newSession(free, `${free} S3`);
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click();
    await page.getByRole('heading', { name: 'Plan an order' }).waitFor();
    assert.equal(await page.getByText(/Checklist · enforcement/).count(), 0, 'checklist leaked into Free Style');
    assert.ok(await page.getByRole('radio', { name: 'Plan · R:R' }).count(), 'Quick/Plan tabs missing');
    const entry = await page.getByLabel('Entry', { exact: true }).inputValue().catch(() => '');
    assert.notEqual(entry, '1.00', 'old entry leaked');
    const a = await askBid();
    const r = await review();
    const body = JSON.parse(r.body);
    assert.deepEqual(body.draft.observations ?? [], [], 'observations from a Protocol Session were sent');
    await page.getByRole('button', { name: 'Cancel confirmation' }).click(); await sleep(300);
    return `Free Style review sent no observations (HTTP ${r.status})`;
  });

  // ---- 10: collapsed terminal + Analysis
  await run('10 · terminal collapsed → the Analysis button opens the Analysis content', async () => {
    await page.setViewportSize({ width: 390, height: 844 }); await sleep(600);
    const sec = page.locator('.alpha-terminal');
    await sec.scrollIntoViewIfNeeded().catch(() => {});
    await page.locator('.alpha-terminal-resize').focus();
    await page.keyboard.press('Home'); await sleep(300);
    assert.equal(await sec.getAttribute('data-terminal-state'), 'COLLAPSED', 'terminal did not collapse');
    try { await page.locator('.alpha-bottom-nav button', { hasText: 'Analysis' }).click({ timeout: 5000 }); } catch (e) { console.log(e.message.split('\n').slice(0, 12).join('\n')); throw e; }
    await sleep(1800);
    await page.screenshot({ path: `${out}/terminal-collapsed-analysis.png` });
    const state = await sec.getAttribute('data-terminal-state');
    assert.notEqual(state, 'COLLAPSED', 'terminal is still collapsed after pressing Analysis');
    assert.ok(await page.locator('.alpha-terminal-content > .alpha-analysis').isVisible(), 'Analysis content is not visible');
  });

  await run('no page errors', async () => { assert.deepEqual(errors, []); });
  await browser.close();
  console.log(`\n${passed} passed, ${failed.length} failed`);
  if (failed.length) process.exit(1);
})();
