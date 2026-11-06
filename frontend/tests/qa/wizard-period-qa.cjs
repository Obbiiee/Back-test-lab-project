// P0 period QA (founder remediation 2026-11-06): the New Session wizard in the
// historical context never derives months from a range. All /tick-alpha routes are
// answered by a LABELED browser fixture (no server, no market data); the fixture only
// shapes the catalog `availability` DTO proposed in docs/codex-api-requests.md REQ-01
// and POST /sessions refusals, so this proves UI behaviour, not backend support.
// Usage: PRODUCT_LOCAL=http://127.0.0.1:5196 node tests/qa/wizard-period-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-wizard-period'; fs.mkdirSync(out, { recursive: true });
const LOCAL = process.env.PRODUCT_LOCAL || 'http://127.0.0.1:5196';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let passed = 0; const fail = [];
const must = (ok, msg) => { if (!ok) throw Error(msg); };

const METHOD = { artifact: 'BTL-LOCAL-METHOD-1', schemaVersion: 1, id: 'method:qa-period', name: 'QA period fixture', kind: 'FREE_STYLE', rr: null, riskPercent: null, checklistOn: false, conditions: [] };
const PROFILE = { instrumentId: 'XAUUSD', feedInstrumentId: 'XAUUSDm', providerId: 'qa-fixture', feedId: 'qa-fixture', quoteCurrency: 'USD', tickSize: '0.001', minLot: '0.01', maxLot: '100', lotStep: '0.01', contractSize: '100', commissionModel: 'NONE' };
const catalogFor = availability => ({ artifact: 'BTL-LOCAL-CATALOG-1', schemaVersion: 1, label: 'QA FIXTURE / PERIOD AVAILABILITY / NOT MARKET DATA', startPeriod: '2024-11', profile: PROFILE, methods: [METHOD], sessions: [], ...(availability ? { availability } : {}) });
const PUBLISHED = { schemaVersion: 1, instruments: [{ instrumentId: 'XAUUSD', status: 'AVAILABLE', periods: [
  { period: '2024-11', status: 'AVAILABLE' }, { period: '2024-12', status: 'GAP' }, { period: '2025-01', status: 'AVAILABLE' },
  { period: '2025-02', status: 'RIGHTS_BLOCKED' }, { period: '2025-03', status: 'EXPIRED', reason: 'Retired for new Sessions' }] }] };
const NONE_AVAILABLE = { schemaVersion: 1, instruments: [{ instrumentId: 'XAUUSD', status: 'QA_BLOCKED', periods: [{ period: '2024-11', status: 'AVAILABLE' }] }] };

(async () => {
  const browser = await chromium.launch();
  const run = async (label, { availability, refuse, viewport = { width: 1440, height: 900 } }, fn) => {
    const ctx = await browser.newContext({ viewport });
    const page = await ctx.newPage(); const errors = []; const posts = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route(/\/api\/v1\/tick-alpha\//, async route => {
      const req = route.request(), path = new URL(req.url()).pathname;
      const json = (status, body) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (path.endsWith('/catalog')) return json(200, catalogFor(availability));
      if (path.endsWith('/sessions') && req.method() === 'POST') { posts.push(req.postDataJSON()); return json(refuse.status, { detail: refuse.code }); }
      return json(404, { detail: 'not in fixture' });
    });
    try {
      await page.goto(LOCAL + '/?tick-alpha=exness&screen=session-new'); await page.waitForSelector('.rk-wizard', { timeout: 15000 });
      await page.locator('.rk-combo-trigger').first().click(); await page.keyboard.type('QA period'); await page.keyboard.press('Enter');
      await page.getByRole('button', { name: 'Continue' }).click(); await page.getByRole('button', { name: 'Continue' }).click();
      await sleep(250);
      const note = await fn(page, posts);
      must(!errors.length, 'page errors: ' + errors.join(' | '));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
      must(overflow <= 0, 'horizontal overflow ' + overflow);
      passed++; console.log('PASS', label, note || '');
    } catch (e) { fail.push(label); console.log('FAIL', label, e.message.split('\n')[0]); await page.screenshot({ path: `${out}/FAIL-${label.replace(/[^a-z0-9]+/gi, '-').slice(0, 30)}.png` }); }
    await ctx.close();
  };
  const cont = page => page.getByRole('button', { name: 'Continue' });

  await run('unpublished: earliest month stated, later and cross-year months go to the server', { refuse: { status: 422, code: 'REFUSED_HISTORICAL_PERIOD' } }, async (page, posts) => {
    must(await page.getByRole('button', { name: /Earliest observed · November 2024/ }).getAttribute('aria-pressed') === 'true', 'earliest not default');
    must(await cont(page).isEnabled(), 'earliest month should be allowed');
    await page.screenshot({ path: `${out}/period-unpublished-earliest-1440.png` });
    await page.getByRole('button', { name: 'Another month' }).click();
    const month = page.getByLabel('Start month (UTC)');
    must(await month.getAttribute('max') === null, 'a max month is still guessed');
    await month.fill('2024-10'); must(!(await cont(page).isEnabled()), 'month before earliest accepted');
    must(await page.getByText('Choose November 2024 or a later month.').isVisible(), 'no inline reason');
    await month.fill('2025-03'); must(await cont(page).isEnabled(), 'cross-year month blocked by a guess');
    must(await page.getByText(/checked when you press Create/).isVisible(), 'server-check disclosure missing');
    await page.screenshot({ path: `${out}/period-unpublished-other-1440.png` });
    await cont(page).click(); await page.getByLabel('Session name').fill('QA period'); await cont(page).click();
    must(await page.getByText('checked by the server when you create').isVisible(), 'review lacks server-check note');
    must(await page.getByText('pinned from this workspace’s server profile').isVisible(), 'review lacks instrument provenance');
    await page.screenshot({ path: `${out}/period-review-1440.png` });
    await page.getByRole('button', { name: 'Create Session' }).click(); await sleep(400);
    must(posts.length === 1, 'POST count ' + posts.length);
    must(JSON.stringify(Object.keys(posts[0]).sort()) === JSON.stringify(['id', 'initialBalance', 'methodId', 'name', 'startPeriod']), 'payload keys changed: ' + Object.keys(posts[0]));
    must(posts[0].startPeriod === '2025-03', 'sent ' + posts[0].startPeriod);
    must(await page.getByRole('group', { name: 'Which period?' }).isVisible().catch(() => false) || await page.getByText('Which period?').isVisible(), 'refusal did not return to the Period step');
    must(await page.getByRole('alert').filter({ hasText: 'REFUSED_HISTORICAL_PERIOD' }).isVisible(), 'refusal reason not shown');
    must(await page.getByRole('alert').filter({ hasText: 'nothing was created' }).isVisible(), 'no nothing-created note');
    await page.screenshot({ path: `${out}/period-refused-1440.png` });
    return 'payload ' + JSON.stringify(posts[0]);
  });

  await run('409 conflict stays on Review and keeps choices', { refuse: { status: 409, code: 'REFUSED_STALE_REVISION' } }, async (page, posts) => {
    await cont(page).click(); await page.getByLabel('Session name').fill('QA conflict'); await cont(page).click();
    await page.getByRole('button', { name: 'Create Session' }).click(); await sleep(400);
    must(posts.length === 1 && posts[0].startPeriod === '2024-11', 'earliest not sent');
    must(await page.getByText('Review', { exact: true }).isVisible(), 'left Review');
    must(await page.getByRole('alert').filter({ hasText: /Nothing was created; your choices are kept/ }).isVisible(), 'conflict message missing');
    await page.getByRole('button', { name: 'Create Session' }).click(); await sleep(400);
    must(posts.length === 2 && posts[1].id === posts[0].id, 'retry must reuse the creation id');
    return 'retry reused ' + posts[0].id;
  });

  await run('published DTO: only listed AVAILABLE months, gaps/rights/expiry disabled with reasons', { availability: PUBLISHED, refuse: { status: 422, code: 'X' } }, async page => {
    must(await page.locator('.rk-combo-trigger').filter({ hasText: 'November 2024' }).isVisible(), 'default not first available');
    await page.locator('.rk-combo-trigger').filter({ hasText: 'November 2024' }).click(); await sleep(200);
    const opts = page.getByRole('option');
    must(await opts.count() === 5, 'options ' + await opts.count());
    must(await page.getByRole('option', { name: /December 2024/ }).getAttribute('aria-disabled') === 'true', 'gap selectable');
    must(await page.getByRole('option', { name: /No observations in this month/ }).isVisible(), 'gap reason missing');
    must(await page.getByRole('option', { name: /Data rights do not cover/ }).isVisible(), 'rights reason missing');
    must(await page.getByRole('option', { name: /Retired for new Sessions/ }).isVisible(), 'expiry reason missing');
    await page.screenshot({ path: `${out}/period-published-open-1440.png` });
    await page.keyboard.type('december'); await page.keyboard.press('Enter'); await sleep(150);
    must(await page.getByRole('option').count() === 1, 'filter failed');
    await page.keyboard.press('Escape'); await sleep(150);
    must(await page.locator('.rk-combo-trigger').filter({ hasText: 'November 2024' }).isVisible(), 'Enter selected a disabled month');
    await page.locator('.rk-combo-trigger').filter({ hasText: 'November 2024' }).click(); await page.keyboard.type('2025-01'); await page.keyboard.press('Enter'); await sleep(150);
    must(await page.locator('.rk-combo-trigger').filter({ hasText: 'January 2025' }).isVisible(), 'could not pick an available month across the year boundary');
    must(await cont(page).isEnabled(), 'Continue disabled for an available month');
  });

  await run('published DTO with no available month blocks honestly', { availability: NONE_AVAILABLE, refuse: { status: 422, code: 'X' } }, async page => {
    must(await page.getByText('No month is available for XAUUSD').isVisible(), 'no blocked state');
    must(!(await cont(page).isEnabled()), 'Continue enabled with no month');
    await page.screenshot({ path: `${out}/period-none-available-1440.png` });
  });

  await run('PARTIAL instrument with AVAILABLE months stays closed and says why (pinned REQ-01)', { availability: { schemaVersion: 1, instruments: [{ instrumentId: 'XAUUSD', status: 'PARTIAL', periods: [{ period: '2024-11', status: 'AVAILABLE' }, { period: '2025-01', status: 'AVAILABLE' }] }] }, refuse: { status: 422, code: 'X' } }, async page => {
    must(await page.getByText('No month is available for XAUUSD').isVisible(), 'PARTIAL opened months');
    must(await page.getByText(/Coverage for this instrument is partial/).isVisible(), 'instrument reason missing');
    must(!(await cont(page).isEnabled()), 'Continue enabled');
    await page.screenshot({ path: `${out}/period-partial-1440.png` });
  });

  for (const vp of [{ width: 390, height: 844 }, { width: 320, height: 640 }])
    await run(`phone ${vp.width}: period step fits`, { viewport: vp, refuse: { status: 422, code: 'X' } }, async page => {
      await page.getByRole('button', { name: 'Another month' }).click();
      await page.screenshot({ path: `${out}/period-unpublished-${vp.width}.png`, fullPage: true });
    });

  await browser.close();
  console.log(`\n${passed} passed, ${fail.length} failed`); if (fail.length) process.exit(1);
})();
