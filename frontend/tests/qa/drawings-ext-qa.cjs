// Issue #21 C-04 browser QA: all 22 extended tools drawn with the real mouse,
// tool-specific Properties edited, reload restores them.
// Usage: start `npx vite --port 5179` in frontend/, then
//   node tests/qa/drawings-ext-qa.cjs <outDir> [baseUrl]
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-out', base = process.argv[3] || 'http://localhost:5179';
fs.mkdirSync(out, { recursive: true });
const results = [];
const step = (name, detail = '') => { results.push({ name, detail }); console.log('PASS', name, detail); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const models = async page => JSON.parse(await page.locator('.candle-chart').getAttribute('data-primitive-drawings'));
const zig = (x0, n, dx = .05) => Array.from({ length: n }, (_, i) => [x0 + i * dx, i % 2 ? .35 : .55 - i * .01]);

const BATCHES = [
  ['01-pitchforks-gann', [
    ['Channels', 'Pitchfork', [[.05, .8], [.15, .45], [.22, .7]]],
    ['Channels', 'Schiff Pitchfork', [[.30, .8], [.40, .45], [.47, .7]]],
    ['Channels', 'Modified Schiff Pitchfork', [[.55, .8], [.65, .45], [.72, .7]]],
    ['Gann', 'Gann Fan', [[.05, .3], [.12, .2]]],
    ['Gann', 'Gann Box', [[.78, .2], [.95, .5]]],
  ]],
  ['02-fibonacci-extended', [
    ['Fibonacci', 'Fib Time Zone', [[.05, .9], [.08, .9]]],
    ['Fibonacci', 'Trend-Based Fib Time', [[.30, .85], [.36, .65], [.42, .8]]],
    ['Fibonacci', 'Fib Speed Resistance Fan', [[.10, .75], [.25, .35]]],
    ['Fibonacci', 'Fib Circles', [[.55, .3], [.65, .45]]],
    ['Fibonacci', 'Fib Speed Resistance Arcs', [[.70, .75], [.80, .55]]],
    ['Fibonacci', 'Fib Wedge', [[.30, .25], [.45, .12], [.45, .32]]],
  ]],
  ['03-patterns', [
    ['Patterns', 'ABCD Pattern', zig(.04, 4)],
    ['Patterns', 'XABCD Pattern', zig(.26, 5)],
    ['Patterns', 'Head and Shoulders', [[.55, .7], [.6, .5], [.65, .62], [.7, .35], [.75, .62], [.8, .5], [.85, .72]]],
    ['Patterns', 'Triangle Pattern', [[.05, .78], [.1, .95], [.2, .82], [.25, .92]]],
    ['Patterns', 'Elliott Impulse Wave', zig(.32, 6, .04).map(([x, y]) => [x, y + .35])],
    ['Patterns', 'Elliott Correction Wave', zig(.62, 4).map(([x, y]) => [x, y + .35])],
  ]],
  ['04-cycles-ranges-markers', [
    ['Lines', 'Cyclic Lines', [[.05, .5], [.12, .5]]],
    ['Annotations', 'Date and Price Range', [[.25, .7], [.4, .45]]],
    ['Annotations', 'Price Label', [[.5, .3]]],
    ['Annotations', 'Icon Marker', [[.6, .5]]],
    ['Annotations', 'Arrow Marker', [[.7, .6]]],
  ]],
];

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  const box0 = async () => page.locator('.candle-chart canvas').first().boundingBox();
  let all = [];
  for (const [shot, tools] of BATCHES) {
    await page.goto(base + '/tests/qa/terminal.html?reset=1&objects=0'); await sleep(1500);
    const box = await box0();
    const at = ([fx, fy]) => ({ x: box.x + (box.width - 70) * fx, y: box.y + box.height * fy });
    for (const [group, name, points] of tools) {
      const before = (await models(page)).length;
      await page.getByLabel(`${group} drawing tools`).click();
      await page.getByRole('button', { name, exact: true }).click(); await sleep(150);
      for (const p of points.map(at)) { await page.mouse.move(p.x, p.y); await sleep(120); await page.mouse.click(p.x, p.y); await sleep(620); }
      const list = await models(page);
      assert.equal(list.length, before + 1, `${name} created`);
      assert.equal(list.at(-1).points.length, points.length);
      step(`${name} drawn`, `${points.length} clicks`);
    }
    await page.mouse.click(box.x + 3, box.y + box.height - 3); await sleep(300);
    await page.screenshot({ path: `${out}/${shot}.png` });
    all = all.concat(await models(page));
  }
  // Properties on the last batch: Icon Marker glyph + size, Arrow direction, Cyclic repeats.
  await page.goto(base + '/tests/qa/terminal.html?objects=1'); await sleep(1600);
  const openProps = async label => { await page.locator('.alpha-object-tree li', { hasText: label }).first().getByRole('button', { name: /properties drawing/ }).click(); await sleep(300); };
  await openProps('Icon Marker');
  await page.getByRole('radiogroup', { name: 'Marker icon' }).getByRole('radio', { name: 'star' }).click();
  await page.getByLabel('Marker size').fill('32'); await sleep(200);
  let list = await models(page); let icon = list.find(m => m.type === 'icon-marker');
  assert.equal(icon.options.icon, 'star'); assert.equal(icon.options.markerSize, 32);
  await page.screenshot({ path: `${out}/05-icon-marker-properties.png` });
  step('Icon Marker: star, 32 px');
  await page.getByRole('button', { name: 'Done' }).click(); await sleep(200);
  await openProps('Arrow Marker');
  await page.getByRole('radiogroup', { name: 'Arrow direction' }).getByRole('radio', { name: /Down/ }).click(); await sleep(200);
  list = await models(page); assert.equal(list.find(m => m.type === 'arrow-marker').options.direction, 'down');
  step('Arrow Marker: direction down');
  await page.getByRole('button', { name: 'Done' }).click(); await sleep(200);
  await openProps('Cyclic Lines');
  await page.getByLabel('Cycle repeats').fill('6'); await page.keyboard.press('Enter'); await sleep(200);
  list = await models(page); assert.equal(list.find(m => m.type === 'cyclic-lines').options.repeats, 6);
  step('Cyclic Lines: 6 repeats');
  await page.getByRole('button', { name: 'Done' }).click(); await sleep(200);
  const snap = await models(page);
  await page.goto(base + '/tests/qa/terminal.html?objects=0'); await sleep(1600);
  assert.deepEqual(await models(page), snap);
  await page.screenshot({ path: `${out}/06-after-reload.png` });
  step('Reload restores the extended tools and their options', `${snap.length} drawings`);
  assert.equal(new Set(all.map(m => m.type)).size, 22);
  assert.deepEqual(errors, [], 'No page errors');
  fs.writeFileSync(`${out}/results.json`, JSON.stringify({ results, errors }, null, 2));
  await browser.close();
  console.log(`extended drawings QA: ${results.length} steps passed`);
})().catch(e => { console.error(e); process.exit(1); });
