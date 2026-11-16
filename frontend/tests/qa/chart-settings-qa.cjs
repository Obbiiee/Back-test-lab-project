// Chart settings popover: keyboard, outside click, switches, phone header fit.
// Needs the local API (5188) and Vite on 5196. Usage: node tests/qa/chart-settings-qa.cjs [outDir]
const { chromium } = require('playwright');
const assert = require('assert');
const out = process.argv[2] || 'qa-chart-settings'; require('fs').mkdirSync(out, { recursive: true });
const base = process.env.LOCAL || 'http://127.0.0.1:5196';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let steps = 0; const step = name => { steps++; console.log('PASS', name); };
(async () => {
  const browser = await chromium.launch(); const errors = [];
  for (const [label, viewport] of [['laptop', { width: 1440, height: 900 }], ['phone', { width: 390, height: 844 }], ['small', { width: 320, height: 640 }]]) {
    const page = await (await browser.newContext({ viewport, hasTouch: label !== 'laptop' })).newPage();
    page.on('pageerror', e => errors.push(label + ': ' + e.message));
    await page.goto(base + '/?tick-alpha=local'); await sleep(1500);
    const open = page.locator('button[aria-label^="Open"]').first();
    await open.click(); await page.waitForSelector('.candle-chart canvas'); await sleep(1200);
    const trigger = page.getByRole('button', { name: 'Chart' });
    assert.equal(await page.getByRole('button', { name: 'Fit chart' }).count(), 0, 'Fit chart is no longer a permanent header button');
    await trigger.click(); await sleep(250);
    const panel = page.getByRole('dialog', { name: 'Chart settings' });
    assert.ok(await panel.isVisible(), 'popover opens');
    const grid = panel.getByRole('switch', { name: 'Grid lines' });
    const before = await grid.isChecked(); await grid.click(); assert.notEqual(await grid.isChecked(), before, 'grid switch toggles'); await grid.click();
    assert.ok(await panel.getByRole('switch', { name: /Volume/ }).isDisabled(), 'volume stays disabled: source has no volume');
    await page.screenshot({ path: `${out}/${label}-settings.png` });
    await page.keyboard.press('Escape'); await sleep(150);
    assert.ok(!(await panel.isVisible()), 'Escape closes');
    assert.ok(await trigger.evaluate(el => el === document.activeElement), 'focus returns to the trigger');
    await trigger.click(); await sleep(150); await page.mouse.click(5, viewport.height / 2); await sleep(150);
    assert.ok(!(await panel.isVisible()), 'outside click closes');
    const overflow = await page.evaluate(() => { const h = document.querySelector('.alpha-chart-header'); return [h.scrollWidth - h.clientWidth, document.documentElement.scrollWidth - document.documentElement.clientWidth]; });
    assert.deepEqual(overflow, [0, 0], `header and page fit at ${viewport.width}px`);
    step(`${label}: Chart settings popover (open, switch, Escape + focus return, outside click), no header overflow`);
  }
  await browser.close();
  assert.deepEqual(errors, []);
  console.log(`chart settings QA: ${steps} steps passed`);
})().catch(e => { console.error(e); process.exit(1); });
