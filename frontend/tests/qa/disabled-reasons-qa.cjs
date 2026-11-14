// Audit 14 Nov 2026, scenario 14: a disabled primary action always says why, in text
// next to it (and via aria-describedby), and the reason disappears when it is fixed.
// Real local backend. Run: backend on 127.0.0.1:5188 + `npx vite --port 5196`, then
//   node tests/qa/disabled-reasons-qa.cjs <outDir>
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-disabled'; fs.mkdirSync(out, { recursive: true });
const base = process.env.QA_BASE || 'http://127.0.0.1:5196';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let passed = 0; const failed = [], errors = [];
(async () => {
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  page.on('pageerror', e => errors.push(e.message));
  const run = async (label, fn) => {
    try { await fn(); passed++; console.log('PASS', label); }
    catch (e) { failed.push(label); console.log('FAIL', label, String(e.message).split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${label.replace(/[^a-z0-9]+/gi, '-').slice(0, 40)}.png` }); }
  };
  const describedBy = async button => { const id = await button.getAttribute('aria-describedby'); return id ? (await page.locator('#' + id).innerText()).trim() : ''; };

  await run('Save Method: disabled with its reason, reason goes away once named', async () => {
    await page.goto(base + '/?tick-alpha=local&screen=method-new'); await sleep(1200);
    const save = page.getByRole('button', { name: 'Save Method' });
    assert.ok(await save.isDisabled());
    assert.equal(await describedBy(save), 'Name the Method to save it.');
    await page.screenshot({ path: `${out}/save-method-reason.png` });
    await page.getByLabel('Method name').fill('Reason check');
    assert.ok(await save.isEnabled());
    assert.equal(await page.locator('#rk-method-why').count(), 0, 'reason still shown');
  });
  await run('Protocol without a condition: says a condition is needed', async () => {
    await page.getByRole('radio', { name: 'Protocol' }).click();
    const save = page.getByRole('button', { name: 'Save Method' });
    assert.ok(await save.isDisabled());
    assert.equal(await describedBy(save), 'Add at least one condition to save a Protocol.');
    await page.getByLabel('Condition 1', { exact: true }).fill('Trend aligned');
    assert.ok(await save.isEnabled());
  });
  await run('New Session: Continue says what is missing and later steps explain why they are locked', async () => {
    await page.goto(base + '/?tick-alpha=local&screen=session-new'); await sleep(1500);
    const next = page.getByRole('button', { name: 'Continue' });
    assert.ok(await next.isDisabled());
    assert.equal(await describedBy(next), 'Choose a Method to continue.');
    assert.equal(await page.getByRole('button', { name: 'Instrument', exact: true }).getAttribute('title'), 'Finish the earlier steps first.');
    await page.screenshot({ path: `${out}/wizard-continue-reason.png` });
  });
  await run('no page errors', async () => { assert.deepEqual(errors, []); });
  await browser.close();
  console.log(`\n${passed} passed, ${failed.length} failed`);
  if (failed.length) process.exit(1);
})();
