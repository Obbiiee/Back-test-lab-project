// P1 Journal draft safety (founder remediation 2026-11-06) against the unchanged
// local API (synthetic source): unsaved drafts survive reload, leaving by the
// Session picker / sidebar / browser Back asks first, Cancel asks before
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

  await step('no page errors', async () => must(!errors.length, errors.join(' | ')));
  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
