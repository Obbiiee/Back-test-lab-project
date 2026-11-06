// C-14 viewport / orientation / reduced-motion sweep of the replay terminal against
// the REAL local backend (synthetic source). Per viewport: no horizontal overflow,
// chart visible, replay controls and order bar inside the viewport, and the confirm
// sheet's Confirm/Cancel row reachable without scrolling. Then an orientation change
// with the Pick-from-chart ticket open, and reduced motion. Review requests are sent
// (server review only); nothing is confirmed.
// Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/terminal-viewports-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-terminal-viewports'; fs.mkdirSync(out, { recursive: true });
const base = process.env.QA_BASE || 'http://127.0.0.1:5196';
const API = 'http://127.0.0.1:5188/api/v1/tick-alpha';
const HEADERS = { 'X-BTL-Local': '1', 'X-BTL-Source': 'synthetic', Origin: 'http://127.0.0.1:5196' };
const sleep = ms => new Promise(r => setTimeout(r, ms));
let passed = 0; const fail = [];
const must = (ok, msg) => { if (!ok) throw Error(msg); };
const VIEWPORTS = [[320, 640], [375, 667], [390, 844], [768, 1024], [1024, 768], [1280, 800], [1440, 900], [844, 390], [667, 375]];

(async () => {
  const catalog = await (await fetch(API + '/catalog', { headers: HEADERS })).json();
  let session = null;
  for (const s of catalog.sessions.slice().reverse()) {
    const v = await (await fetch(`${API}/sessions/${encodeURIComponent(s.id)}`, { headers: HEADERS })).json().catch(() => null);
    if (v?.state && !v.state.ended && !v.state.unresolved) { session = s; break; }
  }
  must(session, 'no open Session');
  const url = `${base}/?tick-alpha=local&session=${encodeURIComponent(session.id)}`;
  const browser = await chromium.launch();
  const step = async (name, fn) => { try { const n = await fn(); passed++; console.log('PASS', name, n || ''); } catch (e) { fail.push(name); console.log('FAIL', name, e.message.split('\n')[0]); } };
  const inside = (box, w, h) => box && box.x >= -1 && box.y >= -1 && box.x + box.width <= w + 1 && box.y + box.height <= h + 1;

  for (const [w, h] of VIEWPORTS) await step(`${w}×${h}: layout fits; confirm sheet actions reachable`, async () => {
    const touch = w < 900;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: touch && w < 700, hasTouch: touch });
    const page = await ctx.newPage(); const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(url); await page.waitForSelector('.candle-chart canvas', { timeout: 20000 }); await sleep(1500);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    must(over <= 0, 'overflow ' + over);
    const chart = await page.locator('.candle-chart canvas').first().boundingBox();
    must(chart && chart.width > 150 && chart.height > 100, 'chart ' + JSON.stringify(chart));
    must(inside(await page.locator('.alpha-replay-controls').boundingBox(), w, h), 'replay controls outside the viewport');
    const buy = page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]');
    await buy.scrollIntoViewIfNeeded(); await buy.click(); await page.locator('.alpha-ticket').waitFor();
    const review = page.getByRole('button', { name: 'Review order' }); await review.scrollIntoViewIfNeeded(); await review.click();
    await page.getByRole('heading', { name: 'Confirm reviewed order' }).waitFor({ timeout: 15000 }); await sleep(800);
    must(inside(await page.locator('.alpha-review-actions').boundingBox(), w, h), 'Confirm/Cancel row not reachable');
    if ([320, 390, 844, 1440].includes(w)) await page.screenshot({ path: `${out}/review-${w}x${h}.png` });
    await page.getByRole('button', { name: 'Cancel confirmation' }).click();
    must(!errors.length, errors.join('|')); await ctx.close();
  });

  await step('orientation change with the pick ticket open keeps it inside the viewport', async () => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const page = await ctx.newPage(); await page.goto(url); await page.waitForSelector('.candle-chart canvas'); await sleep(1500);
    await page.getByRole('button', { name: 'Pick order price' }).tap(); const c = await page.locator('.candle-chart canvas').first().boundingBox();
    await page.touchscreen.tap(c.x + c.width * .5, c.y + c.height * .4); await sleep(300);
    must(inside(await page.locator('.alpha-pick-ticket').boundingBox(), 390, 844), 'portrait');
    await page.setViewportSize({ width: 844, height: 390 }); await sleep(600);
    const box = await page.locator('.alpha-pick-ticket').boundingBox();
    must(inside(box, 844, 390), 'landscape ' + JSON.stringify(box));
    must(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth) <= 0, 'overflow after rotation');
    await page.screenshot({ path: `${out}/pick-after-rotation-844x390.png` });
    await ctx.close();
  });

  await step('phone Draw sheet: search across all 47 tools, empty state, local-only label', async () => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const page = await ctx.newPage(); await page.goto(url); await page.waitForSelector('.candle-chart canvas'); await sleep(1200);
    await page.getByRole('button', { name: 'Draw', exact: true }).tap();
    const sheet = page.getByRole('dialog', { name: 'Drawing tools' });
    must(await sheet.getByText('Drawings are saved in this browser only').isVisible(), 'no local-only label');
    await sheet.getByRole('searchbox', { name: 'Search drawing tools' }).fill('fib');
    const found = await sheet.getByRole('group', { name: 'Matching tools' }).getByRole('button').allInnerTexts();
    must(found.length >= 3 && found.every(t => /fib/i.test(t)), 'search results ' + found.join(', '));
    await page.screenshot({ path: `${out}/draw-search-390.png` });
    await sheet.getByRole('searchbox', { name: 'Search drawing tools' }).fill('zzz');
    must(await sheet.getByText('No drawing tool matches “zzz”.').isVisible(), 'no empty state');
    await sheet.getByRole('searchbox', { name: 'Search drawing tools' }).fill('fib');
    await sheet.getByRole('group', { name: 'Matching tools' }).getByRole('button').first().tap(); await sleep(200);
    must(!(await sheet.count()), 'choosing a tool did not close the sheet');
    await ctx.close();
    return found.length + ' Fibonacci tools';
  });

  await step('reduced motion: sheet, ticket and popovers do not animate', async () => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: 'reduce' });
    const page = await ctx.newPage(); await page.goto(url); await page.waitForSelector('.candle-chart canvas'); await sleep(1500);
    await page.getByRole('button', { name: 'Pick order price' }).tap(); const c = await page.locator('.candle-chart canvas').first().boundingBox();
    await page.touchscreen.tap(c.x + c.width * .5, c.y + c.height * .4); await sleep(200);
    const pick = await page.locator('.alpha-pick-ticket').evaluate(el => getComputedStyle(el).animationName);
    await page.getByRole('button', { name: 'Cancel' }).tap();
    await page.locator('.alpha-order-bar button[aria-label^="Buy at Ask"]').tap(); await page.locator('.alpha-ticket').waitFor();
    await page.getByRole('button', { name: 'Review order' }).tap(); await page.locator('.alpha-review-sheet').waitFor();
    const sheet = await page.locator('.alpha-review-sheet').evaluate(el => getComputedStyle(el).animationName);
    must(pick === 'none' && sheet === 'none', `animations: pick ${pick}, sheet ${sheet}`);
    await ctx.close();
  });

  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
