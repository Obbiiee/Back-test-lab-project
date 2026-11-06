// P0 confirm outcome QA (founder remediation round 2, 2026-11-06) against the REAL
// local backend (synthetic source). Each case gets its own new Session created
// through the unchanged API. Faults are INJECTED in the browser with page.route
// (labeled per case); the server itself is never modified.
//   a  POST /confirm 200, then the Session refresh fails        → saved, never "not placed"
//   b  the server commits, the response is lost                 → unknown, then reconciled as saved
//   c  genuine 409 from the server (tampered reviewHash)        → refused, server has no order
//   d  503 before the server                                    → unknown; banner + order lock
//   e  double tap on Confirm while the POST is slow             → exactly one POST
//   f  Back and reload while the confirm is pending             → held / no false claim, one POST
//   g  reconciliation finds the order committed, or the Session moved on without it
// Every case asserts no "not placed" text appeared unless the server refused, and
// counts /confirm POSTs.
// Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/confirm-outcome-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-confirm-outcome'; fs.mkdirSync(out, { recursive: true });
const base = process.env.QA_BASE || 'http://127.0.0.1:5196';
const API = 'http://127.0.0.1:5188/api/v1/tick-alpha';
const HEADERS = { 'X-BTL-Local': '1', 'X-BTL-Source': 'synthetic', Origin: 'http://127.0.0.1:5196' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
let passed = 0; const fail = [];
const must = (ok, msg) => { if (!ok) throw Error(msg); };
const call = async (path, body) => {
  const r = await fetch(API + path, body === undefined ? { headers: HEADERS } : { method: 'POST', headers: { ...HEADERS, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const v = await r.json(); if (!r.ok) throw Error(`${path} ${r.status} ${v.detail}`); return v;
};
const FALSE_CLAIM = /not placed|Nothing was placed|was not saved/i;

(async () => {
  const catalog = await call('/catalog');
  const method = catalog.methods.find(m => m.kind === 'FREE_STYLE' && !m.checklistOn);
  must(method, 'need a Free Style Method without checklist in the local catalog');
  let n = 0;
  const newSession = async () => (await call('/sessions', { id: `session:qa-outcome-${Date.now()}-${n++}`, name: `QA confirm outcome ${n}`, methodId: method.id, startPeriod: catalog.startPeriod, initialBalance: '10000' })).metadata;
  const saved = id => call(`/sessions/${encodeURIComponent(id)}`);
  const browser = await chromium.launch();

  const scenario = async (name, viewport, fn) => {
    const session = await newSession();
    const ctx = await browser.newContext(viewport); const page = await ctx.newPage(); const errors = []; const confirms = []; let reviewBody = null;
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => {
      if (r.method() !== 'POST' || !r.url().includes('127.0.0.1:5188')) return;
      if (r.url().endsWith('/confirm')) confirms.push(r.postDataJSON());
      if (r.url().endsWith('/reviews')) reviewBody = r.postDataJSON();
    });
    await page.addInitScript(() => {
      window.__claims = [];
      new MutationObserver(() => { const t = document.body?.innerText || ''; for (const m of t.match(/[^\n]*(not placed|Nothing was placed|was not saved)[^\n]*/gi) || []) if (!window.__claims.includes(m)) window.__claims.push(m); })
        .observe(document, { subtree: true, childList: true, characterData: true });
    });
    const open = async () => { await page.goto(`${base}/?tick-alpha=local&session=${encodeURIComponent(session.id)}`); await page.waitForSelector('.candle-chart canvas', { timeout: 20000 }); await sleep(1200); };
    await open();
    const ctxObj = { page, session, confirms, review: () => reviewBody, open, claims: () => page.evaluate(() => window.__claims) };
    try {
      const note = await fn(ctxObj);
      must(!errors.length, 'page errors: ' + errors.join(' | '));
      passed++; console.log('PASS', name, note || '');
    } catch (e) { fail.push(name); console.log('FAIL', name, e.message.split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${name.replace(/[^a-z0-9]+/gi, '-').slice(0, 30)}.png` }); }
    await ctx.close();
  };
  const toReview = async page => {
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click(); await page.locator('.alpha-ticket').waitFor();
    await page.getByRole('button', { name: 'Review order' }).click();
    await page.getByRole('heading', { name: 'Confirm reviewed order' }).waitFor({ timeout: 15000 });
    await sleep(700); // arming delay
  };
  const orderOf = async (session, review) => {
    const s = await saved(session.id); return { has: Object.keys(s.state.orders).length, revision: s.state.revision };
  };
  const desktop = { viewport: { width: 1280, height: 860 } };
  const phone = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };

  await scenario('a: POST 200 then refresh fails → "Order saved" with Reload, never "not placed"', phone, async ({ page, session, confirms, claims }) => {
    let committed = false;
    await page.route('**/sessions/*/confirm', async route => { const r = await route.fetch(); committed = r.ok(); await route.fulfill({ response: r }); });
    await page.route('**/sessions/*/view', route => committed ? route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"LOCAL_SERVICE_UNAVAILABLE"}' }) : route.continue()); // INJECTED refresh failure
    await toReview(page);
    await page.getByRole('button', { name: 'Confirm order' }).tap(); await sleep(1200);
    must(await page.getByText('Order saved', { exact: true }).isVisible(), 'saved state missing');
    must(await page.getByRole('button', { name: 'Reload Session' }).isVisible(), 'no Reload');
    must(!(await page.getByRole('button', { name: /Confirm order|Review again/ }).count()), 'offers another confirm/review after a commit');
    await page.screenshot({ path: `${out}/a-saved-refresh-failed-390.png` });
    must((await orderOf(session)).has === 1, 'server has no order');
    await page.unroute('**/sessions/*/view');
    await page.getByRole('button', { name: 'Reload Session' }).tap(); await sleep(1500);
    must(!(await page.locator('.alpha-review-sheet').count()), 'sheet still open after reload');
    must(confirms.length === 1, 'confirm POSTs ' + confirms.length);
    const c = await claims(); must(!c.length, 'false claim: ' + c);
    return 'server orders 1, confirm POSTs 1';
  });

  await scenario('b: server commits, response lost → unknown, then read-only check finds it saved', desktop, async ({ page, session, confirms, claims }) => {
    const gets = [];
    page.on('request', r => { if (r.method() === 'GET' && /\/sessions\/[^/]+$/.test(r.url())) gets.push(r.url()); });
    await page.route('**/sessions/*/confirm', async route => { await route.fetch(); await route.abort('failed'); }); // INJECTED: commit reaches the server, response dropped
    await toReview(page);
    await page.getByRole('button', { name: 'Confirm order' }).click(); await sleep(1800);
    must(!(await page.locator('.alpha-review-sheet').count()), 'sheet did not close after reconciling as saved');
    must(await page.getByText('Order accepted and saved').isVisible(), 'saved notice missing');
    must(gets.length >= 1, 'no read-only Session check');
    must(confirms.length === 1, 'confirm POSTs ' + confirms.length);
    must((await orderOf(session)).has === 1, 'server order count');
    const c = await claims(); must(!c.length, 'false claim: ' + c);
    return `GET checks ${gets.length}, confirm POSTs 1`;
  });

  await scenario('c: genuine 409 from the server → refused, server has no order', desktop, async ({ page, session, confirms }) => {
    let status = 0;
    await page.route('**/sessions/*/confirm', async route => { // tampered hash, sent to the real server
      const body = route.request().postDataJSON(); body.reviewHash = 'f'.repeat(64);
      const r = await route.fetch({ postData: JSON.stringify(body) }); status = r.status(); await route.fulfill({ response: r });
    });
    await toReview(page);
    await page.getByRole('button', { name: 'Confirm order' }).click(); await sleep(1000);
    must(status === 409, 'server status ' + status);
    must(await page.getByText('The order was not placed').isVisible(), 'refusal missing');
    must(await page.getByText(/REFUSED_IDEMPOTENCY_CONFLICT/).isVisible(), 'server code missing');
    must(await page.getByRole('button', { name: 'Review again' }).isVisible(), 'no Review again');
    await page.screenshot({ path: `${out}/c-refused-409-1280.png` });
    must((await orderOf(session)).has === 0, 'server has an order');
    must(confirms.length === 1, 'confirm POSTs ' + confirms.length);
    return 'server 409 REFUSED_IDEMPOTENCY_CONFLICT';
  });

  await scenario('d + g(committed): 503 → unknown, no resubmit offered, orders locked; later saved → Check again settles it', phone, async ({ page, session, confirms, review, claims }) => {
    await page.route('**/sessions/*/confirm', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"LOCAL_SERVICE_UNAVAILABLE"}' })); // INJECTED, never reaches the server
    await toReview(page);
    await page.getByRole('button', { name: 'Confirm order' }).tap(); await sleep(1200);
    must(await page.getByText('Order status not verified').isVisible(), 'unknown state missing');
    must(await page.locator('.alpha-review-unknown').getByText(/does not show this order yet/).isVisible(), 'check result missing');
    must(!(await page.getByRole('button', { name: /Confirm order|Review again/ }).count()), 'unsafe resubmission offered');
    await page.screenshot({ path: `${out}/d-unknown-390.png` });
    await page.locator('.alpha-review-actions').getByRole('button', { name: 'Close' }).tap(); await sleep(300);
    must(await page.locator('.alpha-unverified').isVisible(), 'workspace banner missing');
    must(await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').isDisabled(), 'new orders not locked');
    await page.screenshot({ path: `${out}/d-banner-390.png` });
    // The original confirmation is applied out of band (as a delayed server would).
    const sent = confirms[0]; await call(`/sessions/${encodeURIComponent(session.id)}/confirm`, sent);
    await page.locator('.alpha-unverified').getByRole('button', { name: 'Check again' }).tap(); await sleep(1500);
    must(!(await page.locator('.alpha-unverified').count()), 'banner did not clear');
    must(await page.getByText('Order accepted and saved').isVisible(), 'saved notice missing');
    must(await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').isEnabled(), 'orders still locked');
    must(confirms.length === 1, 'browser confirm POSTs ' + confirms.length);
    must(review() !== null, 'review body not seen');
    const c = await claims(); must(!c.length, 'false claim: ' + c);
    return 'browser confirm POSTs 1; settled by GET';
  });

  await scenario('g(refused): unknown, then the Session moves on without it → "not saved" only after the read', desktop, async ({ page, session, review }) => {
    await page.route('**/sessions/*/confirm', route => route.abort('timedout')); // INJECTED transport timeout
    await toReview(page);
    await page.getByRole('button', { name: 'Confirm order' }).click(); await sleep(1200);
    must(await page.getByText('Order status not verified').isVisible(), 'unknown state missing');
    must(!(await page.getByText(FALSE_CLAIM).count()), 'claimed not placed before reading');
    // Another review on the same revision is confirmed out of band: revision moves on.
    const other = await call('/reviews', { ...review(), requestId: `order:qa-other-${Date.now()}` });
    await call(`/sessions/${encodeURIComponent(session.id)}/confirm`, { reviewId: other.review.command.commandId, reviewHash: other.reviewHash });
    await page.getByRole('button', { name: 'Check again' }).click(); await sleep(1200);
    must(await page.getByText('The order was not placed').isVisible(), 'reconciled refusal missing');
    must(await page.getByText(/moved on without this confirmation/).isVisible(), 'reason missing');
    must(await page.getByRole('button', { name: 'Review again' }).isVisible(), 'Review again not offered after settling');
    await page.screenshot({ path: `${out}/g-reconciled-refused-1280.png` });
    const s = await saved(session.id);
    must(Object.keys(s.state.orders).length === 1 && Object.hasOwn(s.state.orders, other.review.command.commandId), 'server orders unexpected');
  });

  await scenario('e: double tap while the POST is slow → one POST, pending lock', phone, async ({ page, session, confirms }) => {
    await page.route('**/sessions/*/confirm', async route => { await sleep(1200); await route.continue(); }); // INJECTED latency
    await toReview(page);
    const btn = page.getByRole('button', { name: 'Confirm order' });
    await btn.tap(); await page.locator('.alpha-review-sheet button.alpha-review-primary').tap({ force: true }).catch(() => {});
    await page.locator('.alpha-review-sheet button.alpha-review-primary').dispatchEvent('click').catch(() => {});
    await page.keyboard.press('Escape');
    must(await page.locator('.alpha-review-sheet').isVisible(), 'Escape closed a pending sheet');
    await sleep(2200);
    must(confirms.length === 1, 'confirm POSTs ' + confirms.length);
    must((await orderOf(session)).has === 1, 'server order count');
    return 'confirm POSTs 1';
  });

  await scenario('f: Back while pending is held; reload while pending makes no false claim and no second POST', desktop, async ({ page, session, confirms, open, claims }) => {
    // In-app history entry to go Back to: the entry below this Session is another screen.
    await page.evaluate(() => { const here = location.href; history.replaceState(null, '', '/?tick-alpha=local&screen=sessions'); history.pushState(null, '', here); });
    let release; const held = new Promise(r => { release = r; });
    await page.route('**/sessions/*/confirm', async route => { const r = await route.fetch(); await held; await route.fulfill({ response: r }).catch(() => {}); }); // INJECTED: response held
    await toReview(page);
    const url = page.url();
    await page.getByRole('button', { name: 'Confirm order' }).click(); await sleep(400);
    await page.goBack().catch(() => {}); await sleep(500);
    must(page.url() === url, 'Back left the page during a pending confirm: ' + page.url());
    must(await page.getByText('Saving the order').isVisible(), 'pending state lost after Back');
    release(); await sleep(1500);
    must(await page.getByText('Order accepted and saved').isVisible(), 'did not finish after Back was held');
    must((await orderOf(session)).has === 1, 'server order count after Back');
    // Second order: reload while pending.
    let release2; const held2 = new Promise(r => { release2 = r; });
    await page.unroute('**/sessions/*/confirm');
    await page.route('**/sessions/*/confirm', async route => { const r = await route.fetch(); await held2; await route.fulfill({ response: r }).catch(() => {}); });
    await toReview(page);
    await page.getByRole('button', { name: 'Confirm order' }).click(); await sleep(400);
    await page.reload(); release2(); await page.waitForSelector('.candle-chart canvas', { timeout: 20000 }); await sleep(1200);
    must(confirms.length === 2, 'confirm POSTs ' + confirms.length);
    must((await orderOf(session)).has === 2, 'server order count after reload');
    must(!(await page.locator('.alpha-review-sheet').count()), 'a review reopened by itself after reload');
    const c = await claims(); must(!c.length, 'false claim: ' + c);
    return 'Back held; reload sent nothing again';
  });

  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
