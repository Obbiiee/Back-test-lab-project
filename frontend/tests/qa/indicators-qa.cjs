// Issue #21 C-05/C-06 browser QA for the indicator studio in the QA harness.
// Usage: start `npx vite --port 5179` in frontend/, then
//   node tests/qa/indicators-qa.cjs <outDir> [baseUrl]
// Assertions read the persisted instance configs (what the chart engine renders).
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-out', base = process.argv[3] || 'http://localhost:5179';
fs.mkdirSync(out, { recursive: true });
const results = [];
const step = (name, detail = '') => { results.push({ name, detail }); console.log('PASS', name, detail); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const stored = page => page.evaluate(() => {
  const key = Object.keys(localStorage).find(k => k.startsWith('backtest-indicators-v1:'));
  return key ? JSON.parse(localStorage.getItem(key)).instances : [];
});

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(base + '/tests/qa/terminal.html?reset=1&objects=0'); await sleep(1500);
  const shot = (name, p = page) => p.screenshot({ path: `${out}/${name}.png` });
  const dialog = () => page.getByRole('dialog', { name: 'Overlay indicators' });

  // Catalog: categories, search, volume entries shown as unavailable.
  await page.getByRole('button', { name: 'Indicators' }).click(); await sleep(300);
  // C-15: a Popular row is open; category groups start collapsed with a count.
  const popular = await dialog().getByRole('group', { name: 'Popular' }).getByRole('button', { name: /^Add / }).count();
  assert.equal(popular, 8, 'Popular row');
  assert.equal(await dialog().getByRole('button', { name: /^Add / }).count(), 8, 'groups start collapsed');
  for (const summary of await dialog().locator('details.ind-fold > summary').all()) await summary.click();
  const addButtons = await dialog().locator('details.ind-fold').getByRole('button', { name: /^Add / }).count();
  assert.equal(addButtons, 50, 'All 50 registered indicators are offered');
  const blocked = await dialog().locator('button.ind-blocked').count();
  assert.ok(blocked >= 10, 'Volume indicators listed as unavailable');
  assert.ok(await dialog().locator('button.ind-blocked').first().isDisabled());
  await shot('01-catalog');
  step('Catalog lists 50 indicators by category; volume tools disabled', `${blocked} unavailable (quote-only data)`);
  await page.getByRole('searchbox', { name: 'Search indicators' }).fill('super');
  assert.equal(await dialog().getByRole('button', { name: /^Add / }).count(), 1);
  await dialog().getByRole('button', { name: 'Add Supertrend' }).click(); await sleep(300);
  await page.getByRole('searchbox', { name: 'Search indicators' }).fill('');
  await dialog().getByRole('button', { name: 'Add RSI', exact: true }).click(); await sleep(200);
  await dialog().getByRole('button', { name: 'Add MACD', exact: true }).click(); await sleep(200);
  await dialog().getByRole('button', { name: 'Add Ichimoku Cloud' }).click(); await sleep(400);
  let list = await stored(page);
  assert.deepEqual(list.map(i => i.type), ['SUPERTREND', 'RSI', 'MACD', 'ICHIMOKU']);
  step('Search + add', list.map(i => i.type).join(', '));

  // Inputs: change MACD fast period.
  await dialog().getByRole('button', { name: 'Edit indicator 3' }).click(); await sleep(200);
  await page.getByLabel('Indicator fast period').fill('8');
  await page.getByRole('button', { name: 'Apply parameters' }).click(); await sleep(300);
  list = await stored(page); assert.equal(list[2].parameters.fastPeriod, 8);
  step('Inputs: MACD fast period 12 → 8 applied');

  // Style: thickness, dashed, colour, opacity, histogram colours.
  await page.getByRole('tab', { name: 'Style' }).click(); await sleep(200);
  await page.getByRole('radiogroup', { name: 'MACD thickness' }).getByRole('radio', { name: '4 px' }).click();
  await page.getByRole('radiogroup', { name: 'MACD line style' }).getByRole('radio', { name: 'dashed' }).click();
  await page.getByLabel('MACD color').fill('#ff9800');
  await page.getByLabel('Signal opacity').fill('50');
  await page.getByLabel('Histogram positive color').fill('#00e676');
  await sleep(400);
  list = await stored(page);
  assert.deepEqual(list[2].style.macd, { lineWidth: 4, lineStyle: 'dashed', color: '#ff9800' });
  assert.equal(list[2].style.signal.opacity, 0.5); assert.equal(list[2].style.histogram.positiveColor, '#00e676');
  await shot('02-style-macd');
  step('Style: width 4, dashed, colour, opacity 50 %, histogram rising colour', JSON.stringify(list[2].style));

  // Placement: move MACD pane above RSI, pane height, reference lines.
  await page.getByRole('tab', { name: 'Placement' }).click(); await sleep(200);
  await page.getByRole('button', { name: 'Move pane up', exact: true }).click(); await sleep(300);
  list = await stored(page); assert.deepEqual(list.map(i => i.type), ['SUPERTREND', 'MACD', 'RSI', 'ICHIMOKU']);
  await page.getByLabel('Pane height').fill('60'); await sleep(300);
  list = await stored(page); assert.equal(list[1].paneHeight, 0.6);
  await shot('03-placement-macd-up');
  step('Placement: MACD pane moved above RSI, height 60 %');

  // Overlay → own pane for Supertrend.
  await dialog().getByRole('button', { name: 'Edit indicator 1' }).click(); await sleep(200);
  await page.getByRole('tab', { name: 'Placement' }).click();
  await page.getByRole('radiogroup', { name: 'Placement' }).getByRole('radio', { name: 'Own pane' }).click(); await sleep(300);
  list = await stored(page); assert.equal(list[0].placement, 'pane');
  await page.getByRole('radiogroup', { name: 'Placement' }).getByRole('radio', { name: 'Overlay on price' }).click(); await sleep(300);
  list = await stored(page); assert.equal(list[0].placement, undefined);
  step('Placement: Supertrend overlay → own pane → overlay');

  // Hide + duplicate.
  await dialog().getByRole('button', { name: 'Hide indicator 4' }).click();
  await dialog().getByRole('button', { name: 'Duplicate indicator 3' }).click(); await sleep(300);
  list = await stored(page); assert.equal(list.length, 5); assert.equal(list[4].visible, false); assert.equal(list[3].type, 'RSI');
  step('Hide and duplicate', list.map(i => i.type + (i.visible ? '' : '(hidden)')).join(', '));
  await page.getByRole('button', { name: 'Close indicators' }).click(); await sleep(600);
  await shot('04-chart-with-panes');

  // Reload: identical configs, chart rebuilt.
  const before = await stored(page);
  await page.goto(base + '/tests/qa/terminal.html?objects=0'); await sleep(1800);
  assert.deepEqual(await stored(page), before);
  await page.getByRole('button', { name: 'Indicators', exact: true }).click(); await sleep(300);
  assert.equal(await dialog().locator('.indicator-instance').count(), 5);
  await shot('05-after-reload');
  step('Reload keeps parameters, style, pane order, height and visibility');
  await page.getByRole('button', { name: 'Close indicators' }).click();

  // Tablet + phone layouts.
  const storageState = await page.context().storageState();
  for (const [name, viewport, mobile] of [['tablet-768', { width: 768, height: 1024 }, false], ['phone-390', { width: 390, height: 844 }, true]]) {
    const p = await (await browser.newContext({ storageState, viewport, deviceScaleFactor: 1, hasTouch: mobile, isMobile: mobile })).newPage();
    p.on('pageerror', e => errors.push(name + ': ' + e.message));
    await p.goto(base + '/tests/qa/terminal.html?objects=0'); await sleep(1800);
    await p.getByRole('button', { name: 'Indicators', exact: true }).click(); await sleep(300);
    await p.getByRole('dialog', { name: 'Overlay indicators' }).getByRole('button', { name: 'Edit indicator 2' }).click(); await sleep(200);
    await p.getByRole('tab', { name: 'Style' }).click(); await sleep(200);
    const box = await p.getByRole('dialog', { name: 'Overlay indicators' }).boundingBox();
    assert.ok(box.width <= viewport.width + 1, `${name}: dialog fits width`);
    const scroll = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(scroll <= 0, `${name}: no horizontal page scroll`);
    if (mobile) {
      const small = await p.locator('.ind-seg button').evaluateAll(els => els.filter(e => e.getBoundingClientRect().height < 44).length);
      assert.equal(small, 0, 'phone: segment buttons are 44 px targets');
    }
    await shot('06-' + name, p);
    step(`${name}: settings usable`, `dialog ${Math.round(box.width)}×${Math.round(box.height)}`);
  }

  assert.deepEqual(errors, [], 'No page errors');
  fs.writeFileSync(`${out}/results.json`, JSON.stringify({ results, errors }, null, 2));
  await browser.close();
  console.log(`indicators QA: ${results.length} steps passed`);
})().catch(e => { console.error(e); process.exit(1); });
