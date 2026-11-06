// P1 SearchableSelect regression (founder remediation 2026-11-06): disabled options
// are never active after typing, keyboard Enter/Escape/Tab/Home/End, outside click,
// long labels, no-results, and the phone sheet (modal, focus kept inside, page scroll
// locked, backdrop and Close). Real component, mounted in the New Session wizard;
// /tick-alpha routes are answered by a LABELED browser fixture (not market data).
// Usage: PRODUCT_LOCAL=http://127.0.0.1:5196 node tests/qa/select-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-select'; fs.mkdirSync(out, { recursive: true });
const LOCAL = process.env.PRODUCT_LOCAL || 'http://127.0.0.1:5196';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let passed = 0; const fail = [];
const must = (ok, msg) => { if (!ok) throw Error(msg); };

const LONG = 'London open breakout with Asian range retest and a very long descriptive name that keeps going past any sane width';
const method = (id, name) => ({ artifact: 'BTL-LOCAL-METHOD-1', schemaVersion: 1, id, name, kind: 'FREE_STYLE', rr: null, riskPercent: null, checklistOn: false, conditions: [] });
const CATALOG = {
  artifact: 'BTL-LOCAL-CATALOG-1', schemaVersion: 1, label: 'QA FIXTURE / SELECT / NOT MARKET DATA', startPeriod: '2024-11', sessions: [],
  profile: { instrumentId: 'XAUUSD', feedInstrumentId: 'XAUUSDm', providerId: 'qa-fixture', feedId: 'qa-fixture', quoteCurrency: 'USD', tickSize: '0.001', minLot: '0.01', maxLot: '100', lotStep: '0.01', contractSize: '100', commissionModel: 'NONE' },
  methods: [method('method:qa-a', 'Alpha fixture'), method('method:qa-long', LONG)],
  availability: { schemaVersion: 1, instruments: [{ instrumentId: 'XAUUSD', status: 'AVAILABLE', periods: [
    { period: '2024-11', status: 'AVAILABLE' }, { period: '2024-12', status: 'GAP' }, { period: '2025-01', status: 'AVAILABLE' },
    { period: '2025-02', status: 'RIGHTS_BLOCKED' }, { period: '2025-03', status: 'EXPIRED' }] }] },
};

(async () => {
  const browser = await chromium.launch();
  const run = async (label, opts, fn) => {
    const ctx = await browser.newContext(opts);
    const page = await ctx.newPage(); const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/\/api\/v1\/tick-alpha\//, route => new URL(route.request().url()).pathname.endsWith('/catalog')
      ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(CATALOG) })
      : route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not in fixture"}' }));
    try {
      await page.goto(LOCAL + '/?tick-alpha=exness&screen=session-new'); await page.waitForSelector('.rk-wizard', { timeout: 15000 });
      const note = await fn(page);
      must(!errors.length, 'page errors: ' + errors.join(' | '));
      passed++; console.log('PASS', label, note || '');
    } catch (e) { fail.push(label); console.log('FAIL', label, e.message.split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${label.replace(/[^a-z0-9]+/gi, '-').slice(0, 30)}.png` }); }
    await ctx.close();
  };
  const activeText = page => page.evaluate(() => { const input = document.querySelector('.rk-combo-search input'); const id = input?.getAttribute('aria-activedescendant'); return id ? document.getElementById(id).textContent : null; });
  const toPeriod = async page => {
    await page.locator('.rk-combo-trigger').first().click(); await page.keyboard.type('Alpha'); await page.keyboard.press('Enter');
    await page.getByRole('button', { name: 'Continue' }).click(); await page.getByRole('button', { name: 'Continue' }).click(); await sleep(200);
  };
  const desktop = { viewport: { width: 1280, height: 800 } };

  await run('typing never leaves a disabled option active; Enter on disabled-only results does nothing', desktop, async page => {
    await toPeriod(page);
    await page.locator('.rk-combo-trigger').click(); await sleep(150);
    await page.keyboard.type('2024-12');
    must(await page.getByRole('option').count() === 1, 'filter');
    must(await activeText(page) === null, 'disabled option became active: ' + await activeText(page));
    await page.keyboard.press('Enter'); await sleep(100);
    must(await page.locator('.rk-combo-panel').isVisible(), 'Enter closed on a disabled-only list');
    await page.keyboard.press('Control+A'); await page.keyboard.type('2025');
    must((await activeText(page) || '').startsWith('January 2025'), 'first enabled not active: ' + await activeText(page));
    await page.keyboard.press('ArrowDown');
    must((await activeText(page) || '').startsWith('January 2025'), 'ArrowDown moved onto a disabled month');
    return 'active after "2025": January 2025';
  });

  await run('Home / End / Arrow skip disabled; Escape returns focus; Tab closes and moves on', desktop, async page => {
    await toPeriod(page);
    const trigger = page.locator('.rk-combo-trigger');
    await trigger.click(); await sleep(150);
    await page.keyboard.press('End'); must((await activeText(page) || '').startsWith('January 2025'), 'End landed on ' + await activeText(page));
    await page.keyboard.press('Home'); must((await activeText(page) || '').startsWith('November 2024'), 'Home');
    await page.keyboard.press('ArrowDown'); must((await activeText(page) || '').startsWith('January 2025'), 'ArrowDown did not skip the gap');
    await page.keyboard.press('ArrowDown'); must((await activeText(page) || '').startsWith('November 2024'), 'ArrowDown did not wrap past disabled tail');
    await page.keyboard.press('ArrowUp'); must((await activeText(page) || '').startsWith('January 2025'), 'ArrowUp wrap');
    const aria = await trigger.evaluate(el => ({ popup: el.getAttribute('aria-haspopup'), controls: el.getAttribute('aria-controls'), expanded: el.getAttribute('aria-expanded') }));
    const panel = page.locator('.rk-combo-panel');
    must(aria.popup === 'dialog' && aria.expanded === 'true' && aria.controls === await panel.getAttribute('id') && await panel.getAttribute('role') === 'dialog', 'trigger/panel ARIA mismatch ' + JSON.stringify(aria));
    must(await page.locator('.rk-combo-search input').getAttribute('aria-controls') === await page.getByRole('listbox').getAttribute('id'), 'combobox does not control the listbox');
    await page.keyboard.press('Escape'); await sleep(100);
    must(!(await page.locator('.rk-combo-panel').count()), 'Escape did not close');
    must(await trigger.evaluate(el => el === document.activeElement), 'focus not returned to trigger');
    must(await trigger.getAttribute('aria-expanded') === 'false' && await trigger.getAttribute('aria-controls') === null, 'closed trigger still claims a panel');
    await trigger.press('ArrowDown'); await sleep(100); must(await page.locator('.rk-combo-panel').isVisible(), 'ArrowDown on trigger did not open');
    await page.keyboard.press('Tab'); await sleep(100);
    must(!(await page.locator('.rk-combo-panel').count()), 'Tab did not close the desktop popover');
    await trigger.click(); await sleep(100); await page.mouse.click(1200, 760); await sleep(100);
    must(!(await page.locator('.rk-combo-panel').count()), 'outside click did not close');
  });

  await run('no results and long labels', { viewport: { width: 320, height: 640 } }, async page => {
    const trigger = page.locator('.rk-combo-trigger').first();
    await trigger.click(); await page.keyboard.type('zzzz-no-such');
    must(await page.getByText('Nothing matches your search.').isVisible(), 'no-results text');
    await page.keyboard.press('Control+A'); await page.keyboard.type('London'); await page.keyboard.press('Enter'); await sleep(150);
    const box = await trigger.boundingBox();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    must(overflow <= 0 && box.x + box.width <= 320, `long label overflows (page ${overflow}, trigger right ${box.x + box.width})`);
    await page.screenshot({ path: `${out}/select-long-label-320.png` });
  });

  await run('phone sheet: modal, focus kept inside, scroll locked, backdrop and Close', { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }, async page => {
    await toPeriod(page);
    const trigger = page.locator('.rk-combo-trigger');
    await trigger.tap(); await sleep(300);
    const panel = page.locator('.rk-combo-panel');
    must(await panel.getAttribute('aria-modal') === 'true', 'sheet not modal');
    must(await page.evaluate(() => document.body.style.overflow) === 'hidden', 'page scroll not locked');
    await page.screenshot({ path: `${out}/select-sheet-390.png` });
    const focused = () => page.evaluate(() => document.activeElement?.className || document.activeElement?.tagName);
    must((await focused()) === '' || await page.evaluate(() => document.activeElement?.getAttribute('role')) === 'combobox', 'search not focused');
    await page.keyboard.press('Tab'); must(/rk-combo-close/.test(await focused()), 'Tab left the sheet: ' + await focused());
    await page.keyboard.press('Tab'); must(await page.evaluate(() => document.activeElement?.getAttribute('role')) === 'combobox', 'Tab did not cycle back to search');
    await page.keyboard.press('Shift+Tab'); must(/rk-combo-close/.test(await focused()), 'Shift+Tab escaped');
    await page.getByRole('option', { name: /January 2025/ }).tap(); await sleep(200);
    must(await trigger.textContent().then(t => t.includes('January 2025')), 'tap did not choose');
    must(await page.evaluate(() => document.body.style.overflow) === '', 'scroll lock not restored');
    await trigger.tap(); await sleep(250);
    await page.getByRole('option', { name: /December 2024/ }).tap({ force: true }); await sleep(150);
    must(await panel.isVisible() && (await trigger.textContent()).includes('January 2025'), 'tap chose a disabled month');
    await page.touchscreen.tap(195, 60); await sleep(200);
    must(!(await page.locator('.rk-combo-panel').count()), 'backdrop tap did not close');
    must(await trigger.evaluate(el => el === document.activeElement), 'focus not returned after backdrop');
    await trigger.tap(); await sleep(250); await page.getByRole('button', { name: 'Close' }).tap(); await sleep(150);
    must(!(await page.locator('.rk-combo-panel').count()) && await page.evaluate(() => document.body.style.overflow) === '', 'Close button');
  });

  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
