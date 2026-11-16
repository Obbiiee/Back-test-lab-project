// Issue #21 C-02 mobile flow on a real touch device profile (390×844, touch):
// tap tool → tap anchors → tap select → finger-drag handle → bottom-sheet
// stepper; pinch never places anchors; finger brush; a plain tap never orders.
// Usage: start `npx vite --port 5179` in frontend/, then
//   node tests/qa/mobile-touch-qa.cjs <outDir> [baseUrl]
const { chromium } = require('playwright');
const pickTool = require('./pick-tool.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-out', base = process.argv[3] || 'http://localhost:5179';
fs.mkdirSync(out, { recursive: true });
const results = [];
const step = (name, detail = '') => { results.push({ name, detail }); console.log('PASS', name, detail); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(base + '/tests/qa/terminal.html?reset=1&objects=0'); await sleep(1500);
  const cdp = await ctx.newCDPSession(page);
  const touch = (type, pts) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: pts.map(([x, y], id) => ({ x, y, id })) });
  const models = async () => JSON.parse(await page.locator('.candle-chart').getAttribute('data-primitive-drawings'));
  const box = await page.locator('.candle-chart canvas').first().boundingBox();
  const at = (x, y) => [box.x + x, box.y + y];
  const dialogs = () => page.locator('[role=dialog]').count();

  // A plain tap on the chart in cursor mode creates nothing and opens no order flow.
  const dialogsBefore = await dialogs();
  await page.touchscreen.tap(...at(150, 150)); await sleep(500);
  assert.equal((await models()).length, 0); assert.equal(await dialogs(), dialogsBefore);
  step('Single tap in cursor mode: no drawing, no order dialog');

  // Tap-to-place: tap tool, tap A, tap B.
  await pickTool(page, 'Lines', 'Trend Line'); await sleep(300);
  await page.touchscreen.tap(...at(80, 200)); await sleep(700);
  assert.equal((await models()).length, 0, 'First tap is anchor A only');
  await page.touchscreen.tap(...at(220, 100)); await sleep(700);
  let list = await models(); assert.equal(list.length, 1);
  step('Tap tool, tap A, tap B creates the line');
  await page.screenshot({ path: `${out}/01-phone-tap-trend.png` });

  // Tap select, finger-drag handle B: the canonical price changes.
  await page.touchscreen.tap(...at(150, 150)); await sleep(500);
  const id = await page.locator('.candle-chart').getAttribute('data-primitive-selected');
  assert.equal(id, list[0].id, 'Tap selects the line');
  const before = list[0].points[1];
  await touch('touchStart', [at(220, 100)]);
  for (let i = 1; i <= 10; i++) { await touch('touchMove', [at(220, 100 + i * 6)]); await sleep(20); }
  await touch('touchEnd', []); await sleep(500);
  list = await models();
  assert.ok(list[0].points[1].price < before.price, 'Finger drag moved anchor B down');
  step('Finger drag on a handle edits the anchor', `${before.price.toFixed(3)} → ${list[0].points[1].price.toFixed(3)}`);

  // Bottom sheet stepper: one tap = exactly one tick.
  await page.getByRole('button', { name: 'Open drawing properties' }).tap(); await sleep(400);
  const sheet = await page.getByRole('dialog', { name: /properties/ }).boundingBox();
  assert.ok(sheet.width >= 388 && sheet.y > 200, 'Properties opens as a bottom sheet');
  await page.getByRole('tab', { name: 'Coordinates' }).tap();
  const priceBefore = (await models())[0].points[0].price;
  await page.getByRole('button', { name: 'Move Point A up 1 tick' }).tap(); await sleep(200);
  const priceAfter = (await models())[0].points[0].price;
  assert.equal(Number((priceAfter - priceBefore).toFixed(6)), 0.001);
  await page.screenshot({ path: `${out}/02-phone-sheet-stepper.png` });
  step('Bottom-sheet stepper moves exactly one tick', `${priceBefore} → ${priceAfter}`);
  await page.getByRole('button', { name: 'Done' }).tap(); await sleep(300);
  await page.touchscreen.tap(...at(30, 30)); await sleep(300);

  // Pinch while a tool is armed zooms the chart but places no anchor.
  await pickTool(page, 'Lines', 'Trend Line'); await sleep(300);
  const countBefore = (await models()).length;
  await touch('touchStart', [at(100, 150), at(200, 150)]);
  for (let i = 1; i < 8; i++) { await touch('touchMove', [at(100 - i * 5, 150), at(200 + i * 5, 150)]); await sleep(30); }
  await touch('touchEnd', []); await sleep(900);
  await page.touchscreen.tap(...at(120, 220)); await sleep(700);
  assert.equal((await models()).length, countBefore, 'One tap after a pinch is anchor A, not a finished line');
  await page.touchscreen.tap(...at(200, 120)); await sleep(700);
  assert.equal((await models()).length, countBefore + 1);
  step('Two-finger pinch places no anchor; the next two taps draw normally');

  // Finger brush.
  await pickTool(page, 'Brushes', 'Brush'); await sleep(300);
  await touch('touchStart', [at(60, 250)]);
  for (let i = 1; i <= 30; i++) { await touch('touchMove', [at(60 + i * 6, 250 + Math.sin(i / 4) * 20)]); await sleep(15); }
  await touch('touchEnd', []); await sleep(500);
  list = await models(); assert.equal(list.at(-1).type, 'brush'); assert.ok(list.at(-1).points.length > 5);
  await page.screenshot({ path: `${out}/03-phone-brush.png` });
  step('Finger brush stroke stored', `${list.at(-1).points.length} points`);

  assert.deepEqual(errors, [], 'No page errors');
  fs.writeFileSync(`${out}/results.json`, JSON.stringify({ results, errors }, null, 2));
  await browser.close();
  console.log(`mobile touch QA: ${results.length} steps passed`);
})().catch(e => { console.error(e); process.exit(1); });
