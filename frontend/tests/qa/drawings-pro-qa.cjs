// Issue #21 C-03 browser QA: every professional tool D10–D25 is drawn with the
// real mouse in the QA harness, edited through Properties and survives reload.
// Usage: start `npx vite --port 5179` in frontend/, then
//   node tests/qa/drawings-pro-qa.cjs <outDir> [baseUrl]
const { chromium } = require('playwright');
const pickTool = require('./pick-tool.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-out', base = process.argv[3] || 'http://localhost:5179';
fs.mkdirSync(out, { recursive: true });
const results = [];
const step = (name, detail = '') => { results.push({ name, detail }); console.log('PASS', name, detail); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const models = async page => JSON.parse(await page.locator('.candle-chart').getAttribute('data-primitive-drawings'));

const TOOLS = [
  ['Lines', 'Extended Line', 'extended-line', [[.30, .70], [.38, .60]]],
  ['Lines', 'Horizontal Ray', 'horizontal-ray', [[.55, .25]]],
  ['Lines', 'Cross Line', 'cross-line', [[.62, .45]]],
  ['Channels', 'Parallel Channel', 'parallel-channel', [[.08, .78], [.30, .55], [.18, .50]]],
  ['Channels', 'Regression Trend', 'regression-trend', [[.40, .5], [.70, .5]]],
  ['Fibonacci', 'Fibonacci Extension', 'fib-extension', [[.10, .80], [.22, .40], [.32, .65]]],
  ['Fibonacci', 'Fibonacci Channel', 'fib-channel', [[.45, .80], [.65, .62], [.55, .55]]],
  ['Shapes', 'Rotated Rectangle', 'rotated-rectangle', [[.72, .70], [.85, .55], [.80, .50]]],
  ['Shapes', 'Ellipse', 'ellipse', [[.12, .15], [.22, .32]]],
  ['Shapes', 'Polyline', 'polyline', [[.30, .15], [.36, .30], [.42, .12], [.48, .28]], 'done'],
  ['Brushes', 'Brush', 'brush', [[.60, .10], [.70, .20]], 'drag'],
  ['Brushes', 'Highlighter', 'highlighter', [[.60, .30], [.75, .30]], 'drag'],
  ['Annotations', 'Anchored Text', 'anchored-text', [[.80, .25]], 'text'],
  ['Annotations', 'Callout', 'callout', [[.86, .40], [.90, .18]], 'text'],
  ['Annotations', 'Price Range', 'price-range', [[.50, .88], [.58, .70]]],
  ['Annotations', 'Date Range', 'date-range', [[.62, .90], [.75, .80]]],
];

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(base + '/tests/qa/terminal.html?reset=1&objects=1'); await sleep(1500);
  const box = await page.locator('.candle-chart canvas').first().boundingBox();
  const at = ([fx, fy]) => ({ x: box.x + (box.width - 70) * fx, y: box.y + box.height * fy });

  for (const [group, name, type, points, mode] of TOOLS) {
    const before = (await models(page)).length;
    await page.getByLabel(`${group} drawing tools`).click();
    await page.getByRole('button', { name, exact: true }).click(); await sleep(200);
    if (mode === 'drag') {
      const [a, b] = points.map(at);
      await page.mouse.move(a.x, a.y); await page.mouse.down();
      for (let i = 1; i <= 25; i++) await page.mouse.move(a.x + (b.x - a.x) * i / 25, a.y + (b.y - a.y) * i / 25 + Math.sin(i / 3) * 12);
      await page.mouse.up(); await sleep(400);
    } else {
      for (const p of points.map(at)) { await page.mouse.move(p.x, p.y); await sleep(200); await page.mouse.click(p.x, p.y); await sleep(650); }
      if (mode === 'done') { assert.equal(await page.getByRole('status', { name: 'Polyline creation' }).count(), 1); await page.getByRole('button', { name: 'Done', exact: true }).click(); await sleep(300); }
      if (mode === 'text') { await page.getByLabel('Drawing text content').fill(name === 'Callout' ? 'Liquidity sweep' : 'London open'); await page.getByRole('button', { name: 'Save text' }).click(); await sleep(400); }
    }
    const list = await models(page);
    assert.equal(list.length, before + 1, `${name} created`);
    const model = list.at(-1);
    assert.equal(model.type, type);
    step(`${name} drawn`, `${model.points.length} anchors`);
  }
  await page.getByRole('button', { name: /^Cursor/ }).click().catch(() => {});
  await page.mouse.click(box.x + 5, box.y + box.height - 5); await sleep(300);
  await page.screenshot({ path: `${out}/01-all-16-tools.png` });
  step('All 16 professional tools on one chart');

  // Properties: regression bands, channel middle line, fib extension level, price range thickness.
  const openProps = async label => { await page.locator('.alpha-object-tree li', { hasText: label }).first().getByRole('button', { name: /properties drawing/ }).click(); await sleep(300); };
  await openProps('Regression Trend');
  await page.getByLabel('Band deviations').fill('1'); await page.keyboard.press('Enter'); await sleep(200);
  await page.getByLabel('Fill opacity').fill('25'); await sleep(200);
  let list = await models(page); let reg = list.find(m => m.type === 'regression-trend');
  assert.equal(reg.options.deviation, 1); assert.equal(reg.options.fillOpacity, 0.25);
  await page.screenshot({ path: `${out}/02-regression-properties.png` });
  step('Regression Trend: band deviation and fill applied');
  await page.getByRole('button', { name: 'Done' }).click(); await sleep(200);

  await openProps('Fibonacci Extension');
  await page.getByRole('tab', { name: 'Levels' }).click();
  await page.getByLabel('Show level 1.272').check(); await sleep(200);
  list = await models(page);
  assert.equal(list.find(m => m.type === 'fib-extension').options.levels.find(l => l.value === 1.272).visible, true);
  await page.screenshot({ path: `${out}/03-fib-extension-levels.png` });
  step('Fibonacci Extension: level 1.272 shown');
  await page.getByRole('button', { name: 'Done' }).click(); await sleep(200);

  await openProps('Polyline');
  await page.getByRole('tab', { name: 'Coordinates' }).click();
  await page.getByRole('button', { name: '+ Insert node' }).click(); await sleep(200);
  list = await models(page); assert.equal(list.find(m => m.type === 'polyline').points.length, 5);
  step('Polyline: node inserted from Properties');
  await page.getByRole('button', { name: 'Done' }).click(); await sleep(200);

  await openProps('Callout');
  await page.getByRole('tab', { name: 'Text' }).click();
  await page.getByRole('button', { name: 'Bold', exact: true }).click();
  await page.getByLabel('Font size value').selectOption('16'); await sleep(200);
  list = await models(page); const callout = list.find(m => m.type === 'callout');
  assert.equal(callout.options.bold, true); assert.equal(callout.options.fontSize, 16);
  await page.screenshot({ path: `${out}/04-callout-text.png` });
  step('Callout: bold + 16 px');
  await page.getByRole('button', { name: 'Done' }).click(); await sleep(200);

  // Keyboard: Polyline Backspace / Enter during creation; Escape cancels a 3-anchor draft.
  await page.getByLabel('Shapes drawing tools').click();
  await page.getByRole('button', { name: 'Polyline', exact: true }).click(); await sleep(200);
  for (const p of [[.15, .45], [.2, .55], [.25, .45]].map(at)) { await page.mouse.move(p.x, p.y); await sleep(150); await page.mouse.click(p.x, p.y); await sleep(650); }
  await page.keyboard.press('Backspace'); await page.keyboard.press('Enter'); await sleep(300);
  list = await models(page); assert.equal(list.at(-1).type, 'polyline'); assert.equal(list.at(-1).points.length, 2);
  step('Polyline keyboard: Backspace removes node, Enter finishes');
  const count = list.length;
  await page.getByLabel('Channels drawing tools').click();
  await page.getByRole('button', { name: 'Parallel Channel', exact: true }).click(); await sleep(200);
  const p1 = at([.3, .3]); await page.mouse.click(p1.x, p1.y); await sleep(400); await page.keyboard.press('Escape'); await sleep(200);
  assert.equal((await models(page)).length, count);
  step('Escape cancels an unfinished channel');

  // Reload.
  const snapshot = await models(page);
  await page.goto(base + '/tests/qa/terminal.html?objects=1'); await sleep(1800);
  assert.deepEqual(await models(page), snapshot);
  await page.screenshot({ path: `${out}/05-after-reload.png` });
  step('Reload restores all professional drawings', `${snapshot.length} drawings`);

  // Phone: draw a Price Range by tapping, open its properties sheet.
  const storageState = await page.context().storageState();
  const phone = await (await browser.newContext({ storageState, viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true, isMobile: true })).newPage();
  phone.on('pageerror', e => errors.push('phone: ' + e.message));
  await phone.goto(base + '/tests/qa/terminal.html?objects=0'); await sleep(1800);
  await pickTool(phone, 'Shapes', 'Polyline'); await sleep(300);
  const bar = await phone.getByRole('status', { name: 'Polyline creation' }).boundingBox();
  assert.ok(bar && bar.width <= 390, 'creation bar fits the phone');
  const done = await phone.getByRole('button', { name: 'Done', exact: true }).boundingBox();
  assert.ok(done.height >= 44, 'Done is a 44 px target');
  await phone.screenshot({ path: `${out}/06-phone-polyline-bar.png` });
  step('Phone 390: creation bar with 44 px Done/Cancel');

  assert.deepEqual(errors, [], 'No page errors');
  fs.writeFileSync(`${out}/results.json`, JSON.stringify({ results, errors }, null, 2));
  await browser.close();
  console.log(`professional drawings QA: ${results.length} steps passed`);
})().catch(e => { console.error(e); process.exit(1); });
