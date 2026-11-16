// Issue #21 browser QA driver for the QA harness (tests/qa/terminal.html).
// Usage: start `npx vite --port 5179` in frontend/, then
//   node tests/qa/terminal-qa.cjs <outDir> [baseUrl]
// Every step asserts the canonical drawing model exposed on the chart element
// (data-primitive-drawings) and saves a screenshot as evidence.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-out', base = process.argv[3] || 'http://localhost:5179';
fs.mkdirSync(out, { recursive: true });
const results = [];
const step = (name, detail = '') => { results.push({ name, detail }); console.log('PASS', name, detail); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function models(page) { return JSON.parse(await page.locator('.candle-chart').getAttribute('data-primitive-drawings')); }
async function draw(page, group, tool, points) {
  await page.getByLabel(`${group} drawing tools`).click();
  await page.getByRole('button', { name: tool, exact: true }).click();
  for (const p of points) { await page.mouse.move(p.x, p.y); await sleep(250); await page.mouse.click(p.x, p.y); await sleep(650); }
}

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(base + '/tests/qa/terminal.html?reset=1'); await sleep(1500);
  const box = await page.locator('.candle-chart').boundingBox();
  const at = (fx, fy) => ({ x: box.x + box.width * fx, y: box.y + box.height * fy });
  const shot = name => page.screenshot({ path: `${out}/${name}.png` });

  // Trend line → select → properties.
  const a = at(.25, .78), b = at(.7, .3);
  await draw(page, 'Lines', 'Trend Line', [a, b]);
  let list = await models(page); assert.equal(list.length, 1); const trendId = list[0].id;
  const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  await page.mouse.click(mid.x, mid.y); await sleep(400);
  assert.equal(await page.locator('.candle-chart').getAttribute('data-primitive-selected'), trendId);
  await page.mouse.dblclick(mid.x, mid.y); await sleep(400);
  assert.equal(await page.getByRole('dialog', { name: /properties/ }).count(), 1);
  step('Double-click opens Properties');

  // Style: width 5, dashed, coral, opacity 60%.
  await page.getByRole('radiogroup', { name: 'Line thickness' }).getByRole('radio', { name: '5 px' }).click();
  await page.getByRole('radiogroup', { name: 'Line style' }).getByRole('radio', { name: 'dashed' }).click();
  await page.getByRole('button', { name: 'Line color #ff6b6b' }).click();
  await page.getByLabel('Opacity').fill('60');
  list = await models(page);
  assert.deepEqual(list[0].options, { color: '#ff6b6b', lineWidth: 5, lineStyle: 'dashed', opacity: .6 });
  await shot('01-trend-style-width5-dashed');
  step('Style width 1→5, dashed, colour, opacity written to model', JSON.stringify(list[0].options));

  // Coordinates: Point B down 3 ticks = exactly −0.003.
  await page.getByRole('tab', { name: 'Coordinates' }).click();
  const before = (await models(page))[0].points[1].price;
  for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Move Point B down 1 tick' }).click();
  const after = (await models(page))[0].points[1].price;
  assert.equal(Number((before - after).toFixed(6)), 0.003);
  const timeBefore = (await models(page))[0].points[0].time;
  await page.getByRole('button', { name: 'Move Point A right 1 bar' }).click();
  assert.equal((await models(page))[0].points[0].time - timeBefore, 900, 'One 15m bar = 900 s');
  // Exact numeric price entry.
  const priceField = page.getByRole('textbox', { name: 'Point A price', exact: true });
  await priceField.fill('2612.345'); await priceField.press('Enter');
  assert.equal((await models(page))[0].points[0].price, 2612.345);
  await priceField.focus(); await priceField.press('ArrowUp'); await priceField.press('Shift+ArrowUp');
  assert.equal((await models(page))[0].points[0].price, 2612.356, 'ArrowUp = 1 tick, Shift+ArrowUp = 10 ticks');
  await shot('02-coordinates-tick-bar-steps');
  step('Coordinates: down 3 ticks = 0.003, right 1 bar = 900 s, exact price, keyboard ticks', `${before} → ${after}`);

  // Extend right on the Style tab.
  await page.getByRole('tab', { name: 'Style' }).click();
  await page.getByLabel('Right', { exact: true }).check();
  assert.equal((await models(page))[0].options.extendRight, true);
  await page.getByRole('button', { name: 'Done' }).click();
  step('Extend right toggles geometry');

  // Text with bold + size.
  await page.getByLabel('Annotations drawing tools').click();
  await page.getByRole('button', { name: 'Text', exact: true }).click();
  const tp = at(.42, .3); await page.mouse.move(tp.x, tp.y); await sleep(250); await page.mouse.click(tp.x, tp.y); await sleep(500);
  await page.getByLabel('Drawing text content').fill('Asia session high');
  await page.getByRole('button', { name: 'Save text' }).click(); await sleep(400);
  list = await models(page); const text = list.find(m => m.type === 'text');
  await page.locator('.alpha-object-tree li', { hasText: 'Text' }).getByRole('button', { name: /properties drawing/ }).click(); await sleep(300);
  await page.getByRole('tab', { name: 'Text' }).click();
  await page.getByRole('button', { name: 'Bold', exact: true }).click();
  await page.getByLabel('Font size value').selectOption('20');
  await page.getByRole('radiogroup', { name: 'Text alignment' }).getByRole('radio', { name: 'center' }).click();
  list = await models(page);
  const styled = list.find(m => m.id === text.id);
  assert.equal(styled.options.bold, true); assert.equal(styled.options.fontSize, 20); assert.equal(styled.options.textAlign, 'center');
  await shot('03-text-bold-size-align');
  step('Text: Bold → font-weight 700, size 20, centre', JSON.stringify(styled.options));

  // Rectangle overlapping, then layer order.
  await page.getByRole('button', { name: 'Close drawing properties' }).click();
  await draw(page, 'Shapes', 'Rectangle', [at(.36, .35), at(.62, .62)]);
  list = await models(page); const rect = list.at(-1);
  await page.locator('.alpha-object-tree li', { hasText: 'Rectangle' }).getByRole('button', { name: /properties drawing/ }).click(); await sleep(300);
  await page.getByLabel('Fill opacity').fill('35');
  await page.getByRole('tab', { name: 'Object' }).click();
  await page.getByRole('button', { name: 'Send to back' }).click();
  list = await models(page);
  assert.equal(list[0].id, rect.id, 'Rectangle moved to bottom layer');
  await shot('04-layer-send-to-back');
  await page.getByRole('button', { name: 'Bring to front' }).click();
  assert.equal((await models(page)).at(-1).id, rect.id);
  step('Layer: send to back / bring to front reorders paint stack', (await models(page)).map(m => m.type).join(' < '));
  await page.getByRole('button', { name: 'Done' }).click();

  // Fibonacci: hide 0.236, show 1.618 with a colour.
  await draw(page, 'Fibonacci', 'Fibonacci Retracement', [at(.15, .2), at(.3, .7)]);
  list = await models(page); const fib = list.at(-1);
  await page.locator('.alpha-object-tree li', { hasText: 'Fibonacci' }).getByRole('button', { name: /properties drawing/ }).click(); await sleep(300);
  await page.getByRole('tab', { name: 'Levels' }).click();
  await page.getByLabel('Show level 0.236').uncheck();
  await page.getByLabel('Show level 1.618').check();
  list = await models(page);
  const levels = list.find(m => m.id === fib.id).options.levels;
  assert.equal(levels.find(l => l.value === .236).visible, false); assert.equal(levels.find(l => l.value === 1.618).visible, true);
  await shot('05-fib-levels');
  step('Fib levels: per-row show/hide');
  await page.getByRole('button', { name: 'Done' }).click();

  // Reload: everything survives.
  const snapshot = await models(page);
  await page.goto(base + '/tests/qa/terminal.html'); await sleep(1800);
  assert.deepEqual(await models(page), snapshot, 'Reload restores identical canonical models');
  await shot('06-after-reload');
  step('Reload retains styles, anchors, text, levels and layer order', `${snapshot.length} drawings`);

  // Phone 390 px: bottom sheet with 44px targets.
  const storageState = await page.context().storageState();
  const phone = await (await browser.newContext({ storageState, viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, hasTouch: true, isMobile: true })).newPage();
  phone.on('pageerror', e => errors.push('phone: ' + e.message));
  await phone.goto(base + '/tests/qa/terminal.html?objects=1'); await sleep(1800);
  await phone.locator('.alpha-object-tree li').first().getByRole('button', { name: /properties drawing/ }).click(); await sleep(400);
  const sheet = await phone.getByRole('dialog', { name: /properties/ }).boundingBox();
  assert.ok(sheet.width >= 388 && sheet.y + sheet.height >= 843, 'Bottom sheet spans width and sits at bottom');
  await phone.screenshot({ path: `${out}/07-phone-390-bottom-sheet.png` });
  const small = await phone.evaluate(() => [...document.querySelectorAll('.drawing-properties button:not(.dp-swatch)')].filter(b => b.offsetParent && b.getBoundingClientRect().height < 43).map(b => (b.getAttribute('aria-label') || b.textContent) + ':' + Math.round(b.getBoundingClientRect().height)));
  assert.deepEqual(small, [], 'All sheet buttons ≥ 44px');
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  assert.ok(overflow <= 0, 'No horizontal overflow at 390');
  await phone.screenshot({ path: `${out}/07-phone-390-bottom-sheet.png` });
  step('Phone 390: bottom sheet, 44px targets, no horizontal overflow');

  const tablet = await (await browser.newContext({ storageState, viewport: { width: 768, height: 1024 }, hasTouch: true })).newPage();
  await tablet.goto(base + '/tests/qa/terminal.html'); await sleep(1800);
  await tablet.locator('.alpha-object-tree li').first().getByRole('button', { name: /properties drawing/ }).click(); await sleep(400);
  await tablet.screenshot({ path: `${out}/08-tablet-768.png` });
  step('Tablet 768 renders');

  assert.deepEqual(errors, [], 'No page errors');
  fs.writeFileSync(`${out}/results.json`, JSON.stringify({ results, errors }, null, 2));
  console.log(`PASS terminal QA: ${results.length} steps, 0 page errors`);
  await browser.close();
})().catch(error => { console.error('FAIL', error); process.exit(1); });
