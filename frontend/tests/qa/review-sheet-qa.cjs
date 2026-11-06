// C-14 QA against the REAL local backend (synthetic source): the confirm sheet
// (REVIEW_EXACT → COMMIT_PENDING, stale and refused states) and the Pick-from-chart
// mini ticket. Stale/refused confirmations are INJECTED in the browser (labeled
// below) because the synthetic fixture cannot be made to refuse on demand; every
// other request goes to the unchanged server.
// Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/review-sheet-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-review-sheet'; fs.mkdirSync(out, { recursive: true });
const base = process.env.QA_BASE || 'http://127.0.0.1:5196';
const API = 'http://127.0.0.1:5188/api/v1/tick-alpha';
const HEADERS = { 'X-BTL-Local': '1', 'X-BTL-Source': 'synthetic', Origin: 'http://127.0.0.1:5196' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
let passed = 0; const fail = [];
const must = (ok, msg) => { if (!ok) throw Error(msg); };
const get = async path => (await fetch(API + path, { headers: HEADERS })).json();

(async () => {
  const catalog = await get('/catalog');
  const fresh = [];
  for (const s of catalog.sessions.slice().reverse()) {
    const [j, v] = await Promise.all([get(`/sessions/${encodeURIComponent(s.id)}/journal`).catch(() => null), get(`/sessions/${encodeURIComponent(s.id)}`).catch(() => null)]);
    if (j && !j.orders.length && v?.state && !v.state.ended && !v.state.unresolved) fresh.push(s);
    if (fresh.length === 4) break;
  }
  must(fresh.length === 4, 'need 4 Sessions without orders (run order-flow-qa to create some)');
  const browser = await chromium.launch();
  const step = async (name, page, fn) => { try { const n = await fn(); passed++; console.log('PASS', name, n || ''); } catch (e) { fail.push(name); console.log('FAIL', name, e.message.split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${name.replace(/[^a-z0-9]+/gi, '-').slice(0, 30)}.png` }); } };
  const setup = async (opts, session) => {
    const ctx = await browser.newContext(opts); const page = await ctx.newPage(); const errors = []; const posts = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('request', r => { if (r.method() === 'POST' && r.url().includes('127.0.0.1:5188')) posts.push(r.url().replace(/.*tick-alpha/, '')); });
    await page.goto(`${base}/?tick-alpha=local&session=${encodeURIComponent(session.id)}`); await page.waitForSelector('.candle-chart canvas', { timeout: 20000 }); await sleep(1500);
    return { ctx, page, errors, posts };
  };
  const review = async page => {
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').click(); await page.locator('.alpha-ticket').waitFor();
    await page.getByRole('button', { name: 'Review order' }).click();
    await page.getByRole('heading', { name: 'Confirm reviewed order' }).waitFor({ timeout: 15000 });
  };
  const phone = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };

  { // A + B: phone geometry, arming delay, COMMIT_PENDING lock, single confirm.
    const { ctx, page, errors, posts } = await setup(phone, fresh[0]);
    await step('phone: review opens as a bottom sheet; Confirm arms after a short delay', page, async () => {
      await review(page);
      const confirmBtn = page.getByRole('button', { name: 'Confirm order' });
      must(await confirmBtn.isDisabled(), 'Confirm enabled immediately (tap-through risk)');
      await sleep(700); // let the 220 ms slide-up finish before measuring
      const box = await page.locator('.alpha-review-sheet').boundingBox();
      must(box.y + box.height >= 842 && box.y > 40 && Math.round(box.width) === 390, `sheet geometry ${JSON.stringify(box)}`);
      const actions = await page.locator('.alpha-review-actions').boundingBox();
      must(actions.y + actions.height <= 844, 'Confirm/Cancel row below the fold ' + JSON.stringify(actions));
      must(!(await page.locator('.alpha-review-rr').count()), 'R:R shown without a stop and target');
      for (const label of ['Entry intent', 'Stop Loss', 'Take Profit', 'Lots', 'Risk %']) must(await page.locator('.alpha-reviewed-values dt', { hasText: label }).count() === 1, 'missing ' + label);
      must(await confirmBtn.isEnabled(), 'Confirm never armed');
      await page.screenshot({ path: `${out}/review-exact-390.png` });
    });
    await step('phone: COMMIT_PENDING locks the sheet and sends exactly one confirm', page, async () => {
      await page.route(/\/confirm$/, async route => { await sleep(1500); await route.continue(); });
      const before = posts.filter(p => /\/confirm$/.test(p)).length;
      await page.getByRole('button', { name: 'Confirm order' }).tap();
      await page.getByRole('button', { name: 'Saving…' }).dispatchEvent('click').catch(() => {});
      await sleep(250);
      must(await page.getByText('Saving the order… keep this open.').isVisible(), 'no pending status');
      must(await page.getByRole('button', { name: 'Cancel confirmation' }).isDisabled(), 'Cancel enabled while pending');
      await page.keyboard.press('Escape'); await sleep(150);
      must(await page.locator('.alpha-review-sheet').isVisible(), 'Escape dismissed a pending confirm');
      await page.screenshot({ path: `${out}/commit-pending-390.png` });
      await page.locator('.alpha-review-sheet').waitFor({ state: 'detached', timeout: 15000 });
      const sent = posts.filter(p => /\/confirm$/.test(p)).length - before;
      must(sent === 1, 'confirm requests: ' + sent);
      must(/Order accepted and saved/.test(await page.locator('footer').innerText()), 'no accepted notice');
      return 'POST /confirm × 1';
    });
    must(!errors.length, errors.join('|')); await ctx.close();
  }

  { // C: stale (injected), then Review again against the real server.
    const { ctx, page, errors } = await setup(phone, fresh[1]);
    await step('stale review: sheet says out of date, Review again gets fresh values and confirms', page, async () => {
      await review(page); await sleep(700);
      let injected = false;
      await page.route(/\/confirm$/, route => { if (injected) return route.continue(); injected = true; return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'REFUSED_STALE_REVISION' }) }); });
      await page.getByRole('button', { name: 'Confirm order' }).tap(); await sleep(500);
      must(await page.getByRole('alert').filter({ hasText: 'This review is out of date' }).isVisible(), 'no stale state');
      must(await page.getByRole('button', { name: 'Confirm order' }).count() === 0, 'Confirm still offered on a stale review');
      await page.screenshot({ path: `${out}/review-stale-390.png` });
      await page.getByRole('button', { name: 'Review again' }).tap();
      await page.getByRole('heading', { name: 'Confirm reviewed order' }).waitFor(); await sleep(700);
      await page.getByRole('button', { name: 'Confirm order' }).tap();
      await page.locator('.alpha-review-sheet').waitFor({ state: 'detached', timeout: 15000 });
      return 'stale injected once, fresh review confirmed by the server';
    });
    must(!errors.length, errors.join('|')); await ctx.close();
  }

  { // D: refused (injected) on desktop.
    const { ctx, page, errors } = await setup({ viewport: { width: 1280, height: 860 } }, fresh[2]);
    await step('refused confirmation: "not placed" with the reason; Close leaves nothing changed', page, async () => {
      await review(page); await sleep(700);
      await page.route(/\/confirm$/, route => route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ detail: 'PROTOCOL_BLOCKED' }) }));
      await page.getByRole('button', { name: 'Confirm order' }).click(); await sleep(400);
      const alert = page.getByRole('alert').filter({ hasText: 'The order was not placed' });
      must(await alert.isVisible() && /Protocol rules blocked/.test(await alert.innerText()), 'no refusal reason');
      await page.screenshot({ path: `${out}/review-refused-1280.png` });
      await page.locator('.alpha-review-sheet').getByRole('button', { name: 'Close' }).click(); await sleep(200);
      must(!(await page.locator('.alpha-review-sheet').count()), 'sheet still open');
      const journal = await get(`/sessions/${encodeURIComponent(fresh[2].id)}/journal`);
      must(journal.orders.length === 0, 'an order exists after a refusal');
    });
    must(!errors.length, errors.join('|')); await ctx.close();
  }

  { // E + F: Pick-from-chart mini ticket.
    const { ctx, page, errors, posts } = await setup({ viewport: { width: 1280, height: 860 } }, fresh[3]);
    await step('pick from chart: grid price, focus, honest disabled fields, Escape returns focus', page, async () => {
      const pick = page.getByRole('button', { name: 'Pick order price' });
      await pick.click(); const c = await page.locator('.candle-chart canvas').first().boundingBox();
      await page.mouse.click(c.x + c.width * 0.6, c.y + c.height * 0.4); await sleep(300);
      const ticket = page.getByRole('dialog', { name: 'Use picked price' });
      must(await ticket.isVisible(), 'no mini ticket');
      const price = await ticket.locator('.alpha-pick-price').innerText();
      must(/^\d+(\.\d{1,3})?$/.test(price), 'price not on the 0.001 grid: ' + price);
      must(await page.evaluate(() => document.activeElement?.textContent) === 'Entry', 'focus not on the first action');
      must(await ticket.getByText(/switches this draft from Quick to Plan · R:R \(Limit\)/).isVisible(), 'Quick → Plan switch not disclosed');
      await page.screenshot({ path: `${out}/pick-ticket-1280.png` });
      await page.keyboard.press('Escape'); await sleep(150);
      must(!(await ticket.count()), 'Escape did not close');
      must(await pick.evaluate(el => el === document.activeElement), 'focus not returned to Pick order price');
      return 'picked ' + price;
    });
    await step('pick → Entry fills the draft (Plan · R:R, Limit) and opens the order panel; nothing is sent', page, async () => {
      const reviewsBefore = posts.filter(p => /\/(reviews|confirm)$/.test(p)).length;
      await page.getByRole('button', { name: 'Pick order price' }).click(); const c = await page.locator('.candle-chart canvas').first().boundingBox();
      await page.mouse.click(c.x + c.width * 0.5, c.y + c.height * 0.5); await sleep(300);
      const price = await page.locator('.alpha-pick-price').innerText();
      await page.getByRole('dialog', { name: 'Use picked price' }).getByRole('button', { name: 'Entry' }).click(); await page.locator('.alpha-ticket').waitFor();
      must(await page.locator('.alpha-ticket').getByLabel('Entry', { exact: true }).inputValue() === price, 'entry not filled');
      must(await page.locator('.alpha-ticket').getByRole('radio', { name: 'Limit' }).getAttribute('aria-checked') === 'true', 'order type not Limit');
      must(posts.filter(p => /\/(reviews|confirm)$/.test(p)).length === reviewsBefore, 'a pick sent a review/confirm');
      await page.screenshot({ path: `${out}/pick-applied-1280.png` });
    });
    must(!errors.length, errors.join('|')); await ctx.close();
  }
  {
    const { ctx, page, errors } = await setup(phone, fresh[3]);
    await step('phone: mini ticket fits 390 px with 44 px targets', page, async () => {
      await page.getByRole('button', { name: 'Pick order price' }).tap(); const c = await page.locator('.candle-chart canvas').first().boundingBox();
      await page.touchscreen.tap(c.x + c.width * 0.5, c.y + c.height * 0.45); await sleep(300);
      const box = await page.locator('.alpha-pick-ticket').boundingBox();
      must(box && box.x >= 0 && box.x + box.width <= 390, 'ticket overflows ' + JSON.stringify(box));
      const small = await page.locator('.alpha-pick-actions button').evaluateAll(els => els.filter(e => e.getBoundingClientRect().height < 44).length);
      must(small === 0, small + ' targets under 44px');
      await page.screenshot({ path: `${out}/pick-ticket-390.png` });
    });
    must(!errors.length, errors.join('|')); await ctx.close();
  }
  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
