// CP4 QA (founder remediation 2026-11-06): Help with service status, local Account
// and landing "What works today" state AVAILABLE / NOT PUBLISHED / NOT LIVE honestly,
// fit every viewport, and never claim Google sign-in, plans or extra instruments.
// Runs against the unchanged local API (synthetic source).
// Usage: PRODUCT_LOCAL=http://127.0.0.1:5196 node tests/qa/cp4-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-cp4'; fs.mkdirSync(out, { recursive: true });
const LOCAL = process.env.PRODUCT_LOCAL || 'http://127.0.0.1:5196';
let passed = 0; const fail = [];
const must = (ok, msg) => { if (!ok) throw Error(msg); };
const VIEWPORTS = [[1440, 900], [1280, 800], [1024, 768], [768, 1024], [390, 844], [375, 667], [320, 640], [844, 390]];
const BANNED = /16 pairs|16 instruments|Google sign-in is available|Pro plan|\$\d+\s*\/\s*mo|testimonial/i;

(async () => {
  const browser = await chromium.launch();
  const step = async (name, fn) => { try { const n = await fn(); passed++; console.log('PASS', name, n || ''); } catch (e) { fail.push(name); console.log('FAIL', name, e.message.split('\n')[0]); } };
  const open = async (url, [w, h]) => { const page = await browser.newPage({ viewport: { width: w, height: h } }); const errors = []; page.on('pageerror', e => errors.push(e.message)); await page.goto(url); await page.waitForSelector('h1', { timeout: 20000 }); await page.waitForTimeout(600); return { page, errors }; };

  await step('Help: getting started, service status and honest capability list', async () => {
    const { page, errors } = await open(LOCAL + '/?tick-alpha=local&screen=help', [1440, 900]);
    must(await page.getByRole('heading', { name: 'Getting started' }).isVisible(), 'no getting started');
    must(await page.getByText('Connected').isVisible(), 'service not shown connected');
    const list = page.getByRole('list', { name: 'What works today' });
    const text = await list.innerText();
    must(/Available\s+Replay with Draft/.test(text), 'replay not available');
    must(/Not published yet\s+List of start months/.test(text), 'months must be not published (no availability DTO)');
    must(/Not live\s+Google sign-in/.test(text) && /Not live\s+Plans and billing/.test(text), 'google/plans');
    must(!BANNED.test(await page.locator('body').innerText()), 'banned claim');
    await page.getByRole('link', { name: 'New Session' }).click(); await page.waitForTimeout(400);
    must(/screen=session-new/.test(page.url()), 'getting-started link');
    must(!errors.length, errors.join('|')); await page.close();
  });

  await step('Local Account: workspace facts from the catalog, online account not faked', async () => {
    const { page, errors } = await open(LOCAL + '/?tick-alpha=local&screen=account', [1280, 800]);
    must(await page.getByText('Private local workspace').first().isVisible(), 'workspace');
    must(await page.getByText('Not used here').isVisible(), 'sign-in');
    const items = await page.getByRole('list', { name: 'What works today' }).getByRole('listitem').count();
    must(items === 2, 'account list should hold Google + plans only, got ' + items);
    must(!BANNED.test(await page.locator('body').innerText()), 'banned claim');
    must(!errors.length, errors.join('|')); await page.close();
  });

  await step('Landing: "What works today" lists only shipped items as Available', async () => {
    const { page, errors } = await open(LOCAL + '/?tick-alpha=local&page=home', [1440, 900]);
    const section = page.locator('#today');
    const avail = await section.locator('.alpha-home-today-cols > div').filter({ has: page.getByRole('heading', { name: 'Available' }) }).locator('li').allInnerTexts();
    const notYet = await section.locator('.alpha-home-today-cols > div').filter({ has: page.getByRole('heading', { name: 'Not yet' }) }).locator('li').allInnerTexts();
    must(avail.length === 3 && notYet.length === 7, `available ${avail.length}, not yet ${notYet.length}`);
    must(notYet.some(t => /Google sign-in/.test(t)) && notYet.some(t => /Plans and billing/.test(t)), 'google/plans not listed as not yet');
    must(await page.getByText('Pick a start month, press Play').isVisible(), 'hero copy');
    must(!BANNED.test(await page.locator('body').innerText()), 'banned claim');
    await section.scrollIntoViewIfNeeded(); await page.screenshot({ path: `${out}/landing-today-1440.png` });
    must(!errors.length, errors.join('|')); await page.close();
  });

  await step('Viewport sweep: Help, Account, Landing at 8 sizes without horizontal overflow', async () => {
    const bad = [];
    for (const [name, url] of [['help', '/?tick-alpha=local&screen=help'], ['account', '/?tick-alpha=local&screen=account'], ['landing', '/?tick-alpha=local&page=home']])
      for (const vp of VIEWPORTS) {
        const { page, errors } = await open(LOCAL + url, vp);
        const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
        if (over > 0 || errors.length) bad.push(`${name} ${vp.join('x')} overflow ${over} errors ${errors.length}`);
        if (['1440x900', '390x844', '320x640'].includes(vp.join('x'))) await page.screenshot({ path: `${out}/${name}-${vp.join('x')}.png`, fullPage: name !== 'landing' });
        await page.close();
      }
    must(!bad.length, bad.join('; '));
    return '24 page × viewport checks';
  });

  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
