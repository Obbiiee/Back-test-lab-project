// P1 Journal draft safety (founder remediation 2026-11-06) against the unchanged
// local API (synthetic source): unsaved drafts survive reload, leaving by the
// Session picker / sidebar / Back / Forward / Open replay / Account link asks first
// (direct URL changes get the browser prompt), blocked or full tab storage is
// reported and never called kept, Cancel asks before
// discarding, and a save from an older revision is refused by the server
// (REFUSED_STALE_NOTE) and shown next to the newer saved note.
// Usage: PRODUCT_LOCAL=http://127.0.0.1:5196 node tests/qa/journal-drafts-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-journal-drafts'; fs.mkdirSync(out, { recursive: true });
const LOCAL = process.env.PRODUCT_LOCAL || 'http://127.0.0.1:5196';
const API = 'http://127.0.0.1:5188/api/v1/tick-alpha';
const HEADERS = { 'X-BTL-Local': '1', 'X-BTL-Source': 'synthetic', Origin: 'http://127.0.0.1:5196', 'Content-Type': 'application/json' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
let passed = 0; const fail = [];
const must = (ok, msg) => { if (!ok) throw Error(msg); };
const get = async path => (await fetch(API + path, { headers: HEADERS })).json();

(async () => {
  const catalog = await get('/catalog');
  const withOrders = [];
  for (const s of catalog.sessions.slice().reverse()) {
    const j = await get(`/sessions/${encodeURIComponent(s.id)}/journal`).catch(() => null);
    if (j?.orders?.length) withOrders.push({ session: s, journal: j });
    if (withOrders.length === 2) break;
  }
  must(withOrders.length === 2, 'need two Sessions with orders (run order-flow-qa first)');
  const [A, B] = withOrders;
  const journalUrl = id => `${LOCAL}/?tick-alpha=local&screen=journal&of=${encodeURIComponent(id)}`;

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
  const page = await ctx.newPage(); const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const step = async (name, fn) => { try { const n = await fn(); passed++; console.log('PASS', name, n || ''); } catch (e) { fail.push(name); console.log('FAIL', name, e.message.split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${name.replace(/[^a-z0-9]+/gi, '-').slice(0, 30)}.png` }); } };
  const firstCard = () => page.locator('.rk-journal-item').first();
  const openEditor = async () => { await firstCard().getByRole('button', { name: /Add note|Edit note/ }).click(); return firstCard().getByLabel('Research note'); };
  const dialog = () => page.getByRole('alertdialog', { name: 'Unsaved notes' });
  const marker = 'QA draft ' + Date.now().toString(36);

  await step('draft is flagged and survives a reload (tab storage only)', async () => {
    // Arrive at A through the in-app picker so browser Back has an in-app entry to go to.
    await page.goto(journalUrl(B.session.id)); await page.waitForSelector('.rk-journal-item', { timeout: 20000 });
    await page.locator('.rk-toolbar .rk-combo-trigger').first().click(); await page.keyboard.type(A.session.name); await page.keyboard.press('Enter');
    await page.waitForURL(u => u.toString().includes(encodeURIComponent(A.session.id))); await sleep(800); await page.waitForSelector('.rk-journal-item');
    const box = await openEditor(); await box.fill(marker);
    must(await page.getByText('1 unsaved note draft in this tab.').isVisible(), 'no dirty flag');
    await page.reload(); await page.waitForSelector('.rk-journal-item');
    must(await firstCard().getByLabel('Research note').inputValue() === marker, 'draft lost on reload');
    must(await page.getByText(/Unsaved draft restored/).isVisible(), 'restore notice missing');
    const stored = await page.evaluate(() => Object.keys(sessionStorage).filter(k => k.includes('riksora-note-draft')).length);
    const local = await page.evaluate(() => Object.keys(localStorage).filter(k => k.includes('riksora-note-draft')).length);
    must(stored >= 1 && local === 0, `stored ${stored} local ${local}`);
    await page.screenshot({ path: `${out}/journal-draft-restored-1280.png` });
  });

  await step('changing Session asks first; Escape keeps editing', async () => {
    const url = page.url();
    await page.locator('.rk-toolbar .rk-combo-trigger').first().click(); await page.keyboard.type(B.session.name); await page.keyboard.press('Enter');
    must(await dialog().isVisible(), 'no leave dialog');
    must(await page.getByRole('button', { name: 'Keep editing' }).evaluate(el => el === document.activeElement), 'focus not on Keep editing');
    await page.keyboard.press('Tab'); await page.keyboard.press('Tab');
    must(await page.getByRole('button', { name: 'Keep editing' }).evaluate(el => el === document.activeElement), 'focus escaped the dialog');
    await page.screenshot({ path: `${out}/journal-leave-dialog-1280.png` });
    await page.keyboard.press('Escape'); await sleep(100);
    must(!(await dialog().count()) && page.url() === url, 'navigated anyway');
    must(await firstCard().getByLabel('Research note').inputValue() === marker, 'draft changed');
  });

  await step('browser Back asks first and stays on the Journal', async () => {
    const url = page.url();
    await page.goBack(); await sleep(300);
    must(await dialog().isVisible(), 'no dialog on Back');
    must(page.url() === url, 'URL moved: ' + page.url());
    await page.getByRole('button', { name: 'Keep editing' }).click();
  });

  await step('sidebar link: Leave, keep drafts → navigates; returning restores the draft', async () => {
    await page.getByRole('link', { name: 'Sessions', exact: true }).first().click();
    must(await dialog().isVisible(), 'no dialog on sidebar link');
    await page.getByRole('button', { name: 'Leave, keep drafts' }).click(); await sleep(400);
    must(/screen=sessions/.test(page.url()), 'did not navigate: ' + page.url());
    await page.goto(journalUrl(A.session.id)); await page.waitForSelector('.rk-journal-item');
    must(await firstCard().getByLabel('Research note').inputValue() === marker, 'draft not restored after leaving');
  });

  // Every other way out of the Journal (founder P1 round 2): both answers each time.
  const backToA = async () => { await page.goto(journalUrl(A.session.id)); await page.waitForSelector('.rk-journal-item'); must(await firstCard().getByLabel('Research note').inputValue() === marker, 'draft not restored'); };
  await step('Open replay button: Keep editing stays without loading; Leave opens the replay', async () => {
    const url = page.url(); const views = [];
    const onReq = r => { if (r.url().endsWith('/view')) views.push(r.url()); }; page.on('request', onReq);
    await page.getByRole('button', { name: 'Open replay' }).first().click();
    must(await dialog().isVisible(), 'no dialog on Open replay');
    await page.getByRole('button', { name: 'Keep editing' }).click(); await sleep(300);
    must(page.url() === url && views.length === 0, `stayed? ${page.url()} views ${views.length}`);
    await page.getByRole('button', { name: 'Open replay' }).first().click();
    await page.getByRole('button', { name: 'Leave, keep drafts' }).click();
    await page.waitForSelector('.candle-chart canvas', { timeout: 20000 });
    must(/screen=replay/.test(page.url()) || /session=/.test(page.url()), 'replay not opened: ' + page.url());
    must(!(await dialog().count()), 'asked twice');
    page.off('request', onReq);
    await backToA();
  });
  await step('browser Forward asks first; Keep editing stays', async () => {
    await page.getByRole('link', { name: 'Help', exact: true }).first().click();
    await page.getByRole('button', { name: 'Leave, keep drafts' }).click(); await sleep(300);
    await page.goBack(); await page.waitForSelector('.rk-journal-item'); await sleep(300);
    const url = page.url();
    await page.goForward(); await sleep(300);
    must(await dialog().isVisible(), 'no dialog on Forward');
    must(page.url() === url, 'URL moved: ' + page.url());
    await page.getByRole('button', { name: 'Keep editing' }).click();
    must(await firstCard().getByLabel('Research note').inputValue() === marker, 'draft changed');
  });
  await step('Account link (loads another page): same dialog; Leave goes without a second browser prompt', async () => {
    const prompts = []; const onDialog = d => { prompts.push(d.type()); d.dismiss().catch(() => {}); }; page.on('dialog', onDialog);
    const url = page.url();
    await page.getByRole('link', { name: 'Account', exact: true }).first().click();
    must(await dialog().isVisible(), 'no dialog on Account');
    await page.getByRole('button', { name: 'Keep editing' }).click(); await sleep(300);
    must(page.url() === url, 'left on Keep editing');
    await page.getByRole('link', { name: 'Account', exact: true }).first().click();
    await page.getByRole('button', { name: 'Leave, keep drafts' }).click();
    await page.waitForURL(/page=account/, { timeout: 10000 });
    must(!prompts.length, 'browser prompt after Leave: ' + prompts);
    page.off('dialog', onDialog);
    await backToA();
  });
  await step('direct URL change: the browser asks before unloading; dismiss stays', async () => {
    const prompts = []; const onDialog = d => { prompts.push(d.type()); d.dismiss().catch(() => {}); }; page.on('dialog', onDialog);
    const url = page.url();
    await page.evaluate(() => { location.assign('/?tick-alpha=local&screen=help'); }).catch(() => {}); await sleep(800);
    page.off('dialog', onDialog);
    must(prompts.includes('beforeunload'), 'no beforeunload prompt: ' + prompts);
    must(page.url() === url, 'left: ' + page.url());
    must(await firstCard().getByLabel('Research note').inputValue() === marker, 'draft changed');
  });

  await step('Cancel asks before discarding; Discard clears the stored draft', async () => {
    await firstCard().getByRole('button', { name: 'Cancel' }).click();
    must(await page.getByRole('group', { name: 'Discard unsaved text?' }).isVisible(), 'no discard confirm');
    await page.getByRole('button', { name: 'Keep editing' }).click();
    must(await firstCard().getByLabel('Research note').inputValue() === marker, 'Keep editing lost text');
    await firstCard().getByRole('button', { name: 'Cancel' }).click(); await page.getByRole('button', { name: 'Discard', exact: true }).click(); await sleep(150);
    must(!(await firstCard().getByLabel('Research note').count()), 'editor still open');
    const stored = await page.evaluate(() => Object.keys(sessionStorage).filter(k => k.includes('riksora-note-draft')).length);
    must(stored === 0, 'draft still stored');
    must(!(await page.getByText(/unsaved note draft/).count()), 'dirty flag still shown');
  });

  await step('stale revision: server refuses, shows the newer note, Replace saves explicitly', async () => {
    const order = A.journal.orders[A.journal.orders.length - 1];
    const box = await openEditor(); const mine = 'Mine ' + marker; await box.fill(mine);
    const now = await get(`/sessions/${encodeURIComponent(A.session.id)}/journal`);
    const rev = now.notes.find(n => n.orderId === order.id)?.noteRevision ?? 0;
    const other = await fetch(`${API}/sessions/${encodeURIComponent(A.session.id)}/journal`, { method: 'POST', headers: HEADERS, body: JSON.stringify({ orderId: order.id, expectedNoteRevision: rev, text: 'Saved elsewhere ' + marker, tags: ['other'] }) });
    must(other.ok, 'setup save failed ' + other.status);
    await firstCard().getByRole('button', { name: 'Save note' }).click(); await sleep(1200);
    const alert = firstCard().getByRole('alert');
    must(await alert.filter({ hasText: /saved elsewhere \(revision/ }).isVisible(), 'no conflict panel');
    must(await alert.getByText('Saved elsewhere ' + marker).isVisible(), 'server version not shown');
    must(await firstCard().getByLabel('Research note').inputValue() === mine, 'my text lost');
    await page.screenshot({ path: `${out}/journal-conflict-1280.png` });
    await firstCard().getByRole('button', { name: 'Replace with my text' }).click(); await sleep(1200);
    const after = await get(`/sessions/${encodeURIComponent(A.session.id)}/journal`);
    const saved = after.notes.find(n => n.orderId === order.id);
    must(saved.text === mine && saved.noteRevision === rev + 2, `server has ${saved.text} rev ${saved.noteRevision}`);
    must(await firstCard().getByText(mine).isVisible(), 'saved note not shown');
    return `revision ${rev} → ${saved.noteRevision}`;
  });

  // Storage that does not keep the draft (founder P1 round 2): blocked and full.
  for (const [label, init] of [
    ['blocked', () => { Object.defineProperty(window, 'sessionStorage', { configurable: true, get() { throw new DOMException('blocked', 'SecurityError'); } }); }],
    ['full', () => { Storage.prototype.setItem = function () { throw new DOMException('full', 'QuotaExceededError'); }; }],
  ]) await step(`tab storage ${label}: warning shown; leaving says the text is lost`, async () => {
    const c2 = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }); const p2 = await c2.newPage(); const e2 = [];
    p2.on('pageerror', e => e2.push(e.message));
    await p2.addInitScript(init);
    try {
      await p2.goto(journalUrl(A.session.id)); await p2.waitForSelector('.rk-journal-item', { timeout: 20000 });
      const card = p2.locator('.rk-journal-item').first();
      await card.getByRole('button', { name: /Add note|Edit note/ }).click(); await card.getByLabel('Research note').fill('not kept ' + label);
      must(await card.locator('.rk-draft-lost').isVisible(), 'no warning');
      must(await p2.getByText(/1 not kept by this browser/).isVisible(), 'summary does not say not kept');
      await p2.screenshot({ path: `${out}/journal-storage-${label}-390.png` });
      await p2.getByRole('link', { name: 'Sessions', exact: true }).first().click();
      must(await p2.getByRole('alertdialog', { name: 'Unsaved notes' }).getByText(/could not be kept in this browser/).isVisible(), 'dialog claims drafts are kept');
      must(await p2.getByRole('button', { name: 'Leave and lose text' }).isVisible(), 'button still says keep drafts');
      must(!(await p2.getByRole('button', { name: 'Leave, keep drafts' }).count()), 'false keep-drafts button');
      await p2.getByRole('button', { name: 'Keep editing' }).click();
      must(await card.getByLabel('Research note').inputValue() === 'not kept ' + label, 'text lost on Keep editing');
      must(!e2.length, 'page errors: ' + e2.join(' | '));
    } finally { await c2.close(); }
  });

  await step('no page errors', async () => must(!errors.length, errors.join(' | ')));
  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
