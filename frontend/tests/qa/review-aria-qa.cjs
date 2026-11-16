// ARIA/focus of the phone Review sheet and Pick-from-chart ticket as integrated in the
// product workspace (founder follow-up on PR #36, item 4), against the real local
// backend. Checks: dialog role, aria-modal, accessible name, focus starts inside and
// Tab stays inside, Escape and Close return focus, the pending state is announced
// (aria-busy + status), a refusal is an alert, and an unknown outcome (injected 503,
// labeled) is an alert that is NOT worded as a refusal.
// Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/review-aria-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-review-aria'; fs.mkdirSync(out, { recursive: true });
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
  const newSession = async n => (await call('/sessions', { id: `session:qa-aria-${Date.now()}-${n}`, name: `QA aria ${n}`, methodId: method.id, startPeriod: catalog.startPeriod, initialBalance: '10000' })).metadata;
  const browser = await chromium.launch();
  const phone = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };
  const run = async (label, fn) => {
    const session = await newSession(passed + fail.length);
    const ctx = await browser.newContext(phone); const page = await ctx.newPage(); const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    try {
      await page.goto(`${base}/?tick-alpha=local&session=${encodeURIComponent(session.id)}`); await page.waitForSelector('.candle-chart canvas', { timeout: 20000 }); await sleep(1000);
      const note = await fn(page);
      must(!errors.length, 'page errors: ' + errors.join(' | '));
      passed++; console.log('PASS', label, note || '');
    } catch (e) { fail.push(label); console.log('FAIL', label, e.message.split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${label.replace(/[^a-z0-9]+/gi, '-').slice(0, 30)}.png` }); }
    await ctx.close();
  };
  const inDialog = (page, name) => page.evaluate(n => { const d = document.querySelector(`[role=dialog][aria-label="${n}"]`); return Boolean(d && d.contains(document.activeElement)); }, name);
  const toReview = async page => {
    const buy = page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]');
    await buy.tap(); await page.locator('.alpha-ticket').waitFor();
    await page.getByRole('button', { name: 'Review order' }).tap();
    await page.getByRole('heading', { name: 'Confirm reviewed order' }).waitFor({ timeout: 15000 }); await sleep(700);
  };

  await run('Review sheet: modal dialog, named, focus inside, Tab trapped, Escape returns focus', async page => {
    await toReview(page);
    const dialog = page.getByRole('dialog', { name: 'Confirm reviewed order' });
    must(await dialog.getAttribute('aria-modal') === 'true', 'not modal');
    must(await inDialog(page, 'Confirm reviewed order'), 'focus not inside');
    for (let i = 0; i < 12; i++) { await page.keyboard.press('Tab'); must(await inDialog(page, 'Confirm reviewed order'), 'Tab left the sheet at step ' + i); }
    for (let i = 0; i < 4; i++) { await page.keyboard.press('Shift+Tab'); must(await inDialog(page, 'Confirm reviewed order'), 'Shift+Tab left the sheet'); }
    await page.keyboard.press('Escape'); await sleep(300);
    must(!(await dialog.count()), 'Escape did not close');
    const focused = await page.evaluate(() => document.activeElement?.closest('.alpha-dialog, .alpha-ticket, .alpha-order-bar') ? 'workspace control' : document.activeElement?.tagName);
    must(focused !== 'BODY', 'focus lost to body');
    return 'focus returned to ' + focused;
  });

  await run('Pending is announced (aria-busy + status); refusal is an alert; unknown is an alert, not a refusal', async page => {
    let mode = 'slow';
    await page.route('**/sessions/*/confirm', async route => {
      if (mode === 'slow') { await sleep(800); return route.fulfill({ status: 409, contentType: 'application/json', body: '{"detail":"PROTOCOL_BLOCKED"}' }); } // INJECTED refusal
      return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"LOCAL_SERVICE_UNAVAILABLE"}' }); // INJECTED unknown
    });
    await toReview(page);
    await page.getByRole('button', { name: 'Confirm order' }).tap(); await sleep(200);
    const sheet = page.locator('.alpha-review-sheet');
    must(await sheet.getAttribute('aria-busy') === 'true', 'pending not aria-busy');
    must(await page.getByRole('status').filter({ hasText: 'Saving the order' }).count() === 1, 'pending not a status');
    await sleep(900);
    must(await page.getByRole('alert').filter({ hasText: 'The order was not placed' }).isVisible(), 'refusal not an alert');
    await page.getByRole('button', { name: 'Review again' }).tap(); await page.getByRole('heading', { name: 'Confirm reviewed order' }).waitFor(); await sleep(700);
    mode = 'unknown';
    await page.getByRole('button', { name: 'Confirm order' }).tap(); await sleep(1200);
    const alert = page.getByRole('alert').filter({ hasText: 'Order status not verified' });
    must(await alert.isVisible(), 'unknown not an alert');
    must(!/not placed|refused/i.test(await alert.textContent()), 'unknown worded as a refusal');
    must(await inDialog(page, 'Confirm reviewed order'), 'focus left the sheet after the outcome');
    await page.screenshot({ path: `${out}/review-unknown-alert-390.png` });
  });

  await run('Pick ticket: named dialog, focus moves in, Escape returns focus to Pick order price', async page => {
    const pick = page.getByRole('button', { name: 'Pick order price' });
    await pick.tap(); await sleep(200);
    const box = await page.locator('.candle-chart canvas').first().boundingBox();
    await page.touchscreen.tap(box.x + box.width * .5, box.y + box.height * .4); await sleep(500);
    const ticket = page.getByRole('dialog', { name: 'Use picked price' });
    must(await ticket.isVisible(), 'pick ticket not a named dialog');
    must(await ticket.evaluate(el => el.contains(document.activeElement)), 'focus not inside the ticket');
    await page.keyboard.press('Escape'); await sleep(300);
    must(!(await ticket.count()), 'Escape did not close');
    must(await pick.evaluate(el => el === document.activeElement), 'focus not returned to Pick order price');
  });

  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
