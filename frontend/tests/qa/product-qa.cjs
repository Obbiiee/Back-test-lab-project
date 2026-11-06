// CP1 product QA: account sign-in → My Methods → Method → Session → replay draft/review/
// cancel/confirm → journal → analytics → sign out / sign in / resume, plus expired sign-in,
// deep links, back/forward and phone/tablet layouts.
// Account routes are mocked in the browser (no real identity service in this container);
// research routes are forwarded to the unchanged local API so money/fills stay server-side.
// Usage: PRODUCT_HTTPS=https://127.0.0.1:5443 PRODUCT_LOCAL=http://127.0.0.1:5196 node tests/qa/product-qa.cjs <outDir>
const { chromium } = require('playwright');
const fs = require('node:fs');
const out = process.argv[2] || 'qa-product'; fs.mkdirSync(out, { recursive: true });
const HTTPS = process.env.PRODUCT_HTTPS || 'https://127.0.0.1:5443';
const LOCAL = process.env.PRODUCT_LOCAL || 'http://127.0.0.1:5196';
const API = 'http://127.0.0.1:5188/api/v1/tick-alpha';
const WS = '7d1f6c3e-2a4b-4c5d-8e9f-0a1b2c3d4e5f', USER = '1c2d3e4f-5a6b-4c7d-8e9f-a0b1c2d3e4f5';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let passed = 0; const fail = [];
async function step(name, fn) { try { const note = await fn(); passed++; console.log('PASS', name, note || ''); } catch (e) { fail.push(name); console.log('FAIL', name, e.message.split('\n')[0]); if (global.__failShot) await global.__failShot(name).catch(() => {}); } }
const must = (ok, msg) => { if (!ok) throw Error(msg); };

function mockAccount(page, state) {
  return page.route(/\/api\/v1\/(auth|workspaces)(\/|$|\?)/, async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname, method = req.method();
    const json = (status, body) => route.fulfill({ status, contentType: 'application/json', body: body === undefined ? '' : JSON.stringify(body) });
    if (path === '/api/v1/auth/login') { state.logins++; return json(200, { access_token: 'qa-token-' + state.logins, token_type: 'bearer' }); }
    if (path === '/api/v1/auth/me') return json(200, { id: USER, email: 'qa@example.com', is_verified: true, is_active: true });
    if (/\/auth\/(logout|logout-all)$/.test(path)) return route.fulfill({ status: 204, body: '' });
    if (/\/auth\/(register|verify|request-verify-token|forgot-password|reset-password)$/.test(path)) return json(202, {});
    if (path === '/api/v1/workspaces' && method === 'GET') return json(200, [{ id: WS, name: 'QA workspace', role: 'OWNER' }]);
    const research = path.match(new RegExp(`^/api/v1/workspaces/${WS}/research(/.*)$`));
    if (!research) return json(404, { detail: 'not mocked' });
    if (state.expireNext) { state.expireNext = false; return json(401, { detail: 'expired' }); }
    const sub = research[1];
    const headers = { 'X-BTL-Local': '1', 'X-BTL-Source': 'synthetic', Origin: 'http://127.0.0.1:5196', 'Content-Type': 'application/json' };
    if (sub === '/catalog') {
      const base = await (await fetch(API + '/catalog', { headers })).json();
      return json(200, { ...base, methods: state.methods, sessions: state.sessions });
    }
    if (sub === '/methods' && method === 'POST') { const body = req.postDataJSON(); const r = await fetch(API + '/methods', { method: 'POST', headers, body: JSON.stringify(body) }); const v = await r.json(); if (r.ok) state.methods.push(body); return json(r.status, v); }
    const r = await fetch(API + sub, { method, headers, body: method === 'GET' ? undefined : req.postData() });
    const v = await r.json();
    if (sub === '/sessions' && method === 'POST' && r.ok) state.sessions.push(v.metadata);
    return json(r.status, v);
  });
}

(async () => {
  const browser = await chromium.launch();
  const state = { methods: [], sessions: [], logins: 0, expireNext: false };
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: true });
  const page = await ctx.newPage(); const errors = [];
  page.on('pageerror', e => errors.push(e.message)); page.on('console', m => { if (m.type() === 'error' && !/401|404|Failed to load resource/.test(m.text())) errors.push(m.text()); });
  await mockAccount(page, state);
  const shot = name => page.screenshot({ path: `${out}/${name}.png` });
  global.__failShot = async name => { console.log('  at', page.url()); await page.screenshot({ path: `${out}/FAIL-${name.slice(0, 24).replace(/[^a-z0-9]+/gi, '-')}.png` }); };
  const signIn = async () => {
    await page.getByLabel('Email').fill('qa@example.com');
    await page.getByLabel('Password', { exact: true }).fill('correct horse battery staple');
    await page.locator('form').getByRole('button', { name: 'Sign in' }).click();
    await page.getByRole('button', { name: /QA workspace/ }).click();
    await page.waitForSelector('.rk-shell, .candle-chart'); await sleep(800);
  };

  await step('Sign-in card: tabs, Google unavailable, password reveal, safety note', async () => {
    await page.goto(HTTPS + '/?page=account&screen=method&method=method:deep-link'); await sleep(1500);
    await shot('01-sign-in');
    must(await page.getByRole('tab', { name: 'Sign in' }).getAttribute('aria-selected') === 'true', 'sign-in tab not selected');
    must(await page.getByRole('button', { name: 'Continue with Google' }).isDisabled(), 'Google must be disabled');
    await page.getByLabel('Password', { exact: true }).fill('abc');
    await page.getByRole('button', { name: 'Show password' }).click();
    must(await page.getByLabel('Password', { exact: true }).getAttribute('type') === 'text', 'reveal failed');
    await page.getByRole('button', { name: 'Hide password' }).click();
  });
  await step('Register → check inbox → verify returns to sign in (generic messages)', async () => {
    await page.getByRole('tab', { name: 'Create account' }).click();
    await page.getByLabel('Email').fill('new@example.com');
    await page.getByLabel('Password', { exact: true }).fill('short');
    must(await page.getByText(/more characters to go/).isVisible(), 'length hint missing');
    await shot('02-register');
    await page.getByLabel('Password', { exact: true }).fill('a long enough passphrase');
    await page.locator('form').getByRole('button', { name: 'Create account' }).click(); await sleep(400);
    must(await page.getByRole('heading', { name: 'Check your inbox' }).isVisible(), 'verify card missing');
    must(await page.getByText('If this email can sign up').isVisible(), 'generic notice missing');
    await shot('03-verify');
    await page.getByLabel('Verification code').fill('token-123');
    await page.getByRole('button', { name: 'Verify email' }).click(); await sleep(400);
    must(await page.getByText('Email verified. Sign in to start.').isVisible(), 'verified notice missing');
  });
  await step('Forgot → reset → back to sign in', async () => {
    await page.getByRole('button', { name: 'Forgot password?' }).click();
    await page.getByLabel('Email').fill('qa@example.com');
    await page.getByRole('button', { name: 'Send reset code' }).click(); await sleep(300);
    must(await page.getByRole('heading', { name: 'Pick a new password' }).isVisible(), 'reset card missing');
    await page.getByLabel('Reset code').fill('reset-1'); await page.getByLabel('New password').fill('another long passphrase');
    await page.getByRole('button', { name: 'Save password' }).click(); await sleep(300);
    must(await page.getByText('Password saved').isVisible(), 'reset notice missing');
  });
  await step('First user: sign in → workspace → deep link to missing Method shows unavailable', async () => {
    await signIn();
    must(await page.getByRole('heading', { name: 'This Method is not in this workspace' }).isVisible(), 'deep-link unavailable state missing');
    await shot('04-deeplink-unavailable');
    await page.getByRole('link', { name: 'Back to My Methods' }).click(); await sleep(500);
    must(await page.getByRole('heading', { name: 'Create your first Method' }).isVisible(), 'first-use card missing');
    await shot('05-first-use');
  });
  const methodName = 'QA breakout ' + Date.now().toString(36).slice(-4);
  await step('Create Protocol Method → lands on Method overview with empty Sessions', async () => {
    await page.getByRole('link', { name: 'Create your first Method' }).click(); await sleep(400);
    await page.getByLabel('Method name').fill(methodName);
    await page.getByRole('radio', { name: 'Protocol' }).click();
    await page.getByLabel('Condition 1', { exact: true }).fill('Price broke the Asian range');
    await page.getByRole('button', { name: '+ Add condition' }).click();
    await page.getByLabel('Condition 2', { exact: true }).fill('Retest held on 5m');
    await shot('06-method-new');
    await page.getByRole('button', { name: 'Save Method' }).click(); await sleep(1200);
    must(await page.getByRole('heading', { name: methodName }).isVisible(), 'overview heading missing');
    must(await page.getByRole('heading', { name: 'No Sessions yet' }).isVisible(), 'empty sessions state missing');
    await page.getByRole('navigation', { name: 'Method sections' }).getByRole('link', { name: 'Rules' }).click(); await sleep(300);
    must(await page.getByText('Retest held on 5m').isVisible(), 'rules list missing');
    await page.getByRole('navigation', { name: 'Method sections' }).getByRole('link', { name: 'Analytics' }).click(); await sleep(300);
    must(await page.getByRole('heading', { name: 'Method analytics is not published yet' }).isVisible(), 'honest method analytics state missing');
    await shot('07-method-analytics');
  });
  const sessionName = methodName + ' S1';
  await step('New Session from Method → replay opens with Method breadcrumb', async () => {
    await page.getByRole('button', { name: 'New Session' }).first().click(); await sleep(400);
    // Wizard: the Method is preselected from the Method overview.
    must(await page.getByRole('heading', { name: 'Set up a replay' }).isVisible(), 'wizard did not open');
    must((await page.locator('.rk-combo-trigger').first().innerText()).includes(methodName), 'Method not preselected');
    for (let i = 0; i < 3; i++) { await page.getByRole('button', { name: 'Continue' }).click(); await sleep(200); }
    await page.getByLabel('Session name').fill(sessionName);
    await page.getByRole('button', { name: 'Continue' }).click(); await sleep(200);
    must(await page.getByRole('heading', { name: 'Review' }).isVisible() || await page.getByText('Review', { exact: true }).first().isVisible(), 'review step missing');
    await shot('05b-wizard-review');
    await page.getByRole('button', { name: 'Create Session' }).click();
    await page.waitForSelector('.candle-chart canvas', { timeout: 20000 }); await sleep(1200);
    must(new URL(page.url()).searchParams.get('session'), 'session missing from URL');
    must(await page.getByRole('link', { name: `Back to ${methodName}` }).isVisible(), 'breadcrumb back link missing');
    await shot('08-replay');
  });
  await step('Draft → server review → cancel; then draft → review → confirm', async () => {
    await page.getByRole('button', { name: /^Buy at Ask/ }).click(); await sleep(500);
    const ticket = page.locator('.alpha-ticket');
    for (const c of await ticket.getByRole('combobox').all()) await c.selectOption('PASS').catch(() => {});
    await ticket.getByLabel('Entry', { exact: true }).fill('1999.0'); await ticket.getByLabel('Stop Loss', { exact: true }).fill('1997.0');
    await ticket.getByRole('button', { name: /^Review/ }).click(); await sleep(1500);
    must(await page.getByRole('heading', { name: 'Confirm reviewed order' }).isVisible(), 'server review missing');
    await page.getByRole('button', { name: 'Cancel confirmation' }).click(); await sleep(400);
    await page.getByRole('button', { name: /^Buy at Ask/ }).click(); await sleep(500);
    for (const c of await ticket.getByRole('combobox').all()) await c.selectOption('PASS').catch(() => {});
    await ticket.getByLabel('Entry', { exact: true }).fill('1999.0'); await ticket.getByLabel('Stop Loss', { exact: true }).fill('1997.0');
    await ticket.getByRole('button', { name: /^Review/ }).click(); await sleep(1500);
    await page.getByRole('button', { name: 'Confirm order' }).click(); await sleep(2000);
    const footer = await page.locator('footer').innerText();
    must(!/refused|error/i.test(footer), 'confirm refused: ' + footer);
    return footer.slice(0, 90);
  });
  await step('Journal opens from the Session; refresh requires sign-in', async () => {
    await page.getByRole('button', { name: 'Open journal panel' }).click(); await sleep(600);
    must(await page.getByRole('dialog', { name: 'Research journal' }).isVisible(), 'journal dialog missing');
    await shot('08b-journal');
    await page.keyboard.press('Escape'); await sleep(300);
    await page.goto(page.url()); // reload signs out on purpose (token in memory)
    await sleep(1200);
    must(await page.getByRole('tab', { name: 'Sign in' }).isVisible(), 'refresh should require sign-in');
    return 'refresh requires sign-in (token kept in memory only)';
  });
  await step('Returning user: sign in → deep link back to the Session (replay)', async () => {
    await signIn(); await page.getByRole('link', { name: `Back to ${methodName}` }).waitFor({ timeout: 20000 }); await sleep(800);
    must(await page.getByRole('link', { name: `Back to ${methodName}` }).isVisible(), 'did not return to Session');
  });
  await step('My Methods shows Continue research for the last opened Session', async () => {
    await page.getByRole('link', { name: `Back to ${methodName}` }).click(); await sleep(600);
    await page.locator('.rk-sidebar').getByRole('link', { name: 'My Methods', exact: true }).click(); await sleep(1200);
    must(await page.getByRole('heading', { name: sessionName }).isVisible(), 'continue card missing');
    await shot('09-my-methods-returning');
  });
  await step('Session analytics page shows scope + primary row from committed data', async () => {
    await page.locator('.rk-sidebar').getByRole('link', { name: 'Analytics' }).click(); await sleep(500);
    await page.locator('.rk-toolbar select').nth(1).selectOption({ label: sessionName }); await sleep(2500);
    must(await page.getByText('Realized net (USD)').isVisible(), 'primary row missing');
    await shot('10-session-analytics');
  });
  await step('Back/forward keeps routes; Account panel; expired sign-in shows safety card', async () => {
    await page.goBack(); await sleep(400); await page.goForward(); await sleep(600);
    must(new URL(page.url()).searchParams.get('screen') === 'analytics', 'forward lost route');
    await page.locator('.rk-sidebar').getByRole('link', { name: 'Account' }).click(); await sleep(600);
    must(await page.getByRole('heading', { name: 'Account' }).isVisible(), 'account panel missing');
    await shot('11-account');
    await page.getByRole('button', { name: 'Back to My Methods' }).click(); await sleep(1000);
    state.expireNext = true;
    // The next authenticated request answers 401: the app must drop the token and show the safety card.
    // My Methods re-reads the last Session (one GET) for the Continue card, so the 401 lands there.
    await page.locator('.rk-sidebar').getByRole('link', { name: 'Sessions' }).click(); await sleep(400);
    if (!(await page.getByText('Signed out for safety').isVisible())) { await page.locator('.rk-sidebar').getByRole('link', { name: 'My Methods', exact: true }).click(); }
    await page.getByText('Signed out for safety').waitFor({ timeout: 8000 });
    must(await page.getByText('Signed out for safety').isVisible(), 'safety card missing');
    await shot('12-expired');
  });
  await step('Sign out on all devices returns to sign-in', async () => {
    await signIn(); await page.locator('.rk-sidebar').getByRole('link', { name: 'Account' }).click(); await sleep(500);
    await page.getByRole('button', { name: 'Sign out on all devices' }).click(); await sleep(500);
    must(await page.getByText('Signed out on every device.').isVisible(), 'sign-out notice missing');
  });
  // Local workspace (no account): deep links and phone/tablet layouts.
  for (const [name, viewport] of [['1280', { width: 1280, height: 800 }], ['1024', { width: 1024, height: 768 }], ['768', { width: 768, height: 1024 }], ['390', { width: 390, height: 844 }], ['375', { width: 375, height: 812 }], ['320', { width: 320, height: 640 }], ['844x390', { width: 844, height: 390 }]]) {
    await step(`Local ${name}: My Methods + Method overview without horizontal overflow`, async () => {
      const c = await browser.newContext({ viewport }); const p = await c.newPage();
      await p.goto(LOCAL + '/?tick-alpha=local'); await sleep(1800);
      const over = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      await p.screenshot({ path: `${out}/local-${name}-methods.png` });
      await p.locator('.rk-method-card h2 a').first().click(); await sleep(700);
      const over2 = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      await p.screenshot({ path: `${out}/local-${name}-method.png` });
      await c.close(); must(over <= 0 && over2 <= 0, `overflow ${over}/${over2}px`);
    });
  }
  await step('Local: replay tab without a Session explains first; old ?session= link still opens replay', async () => {
    const c = await browser.newContext({ viewport: { width: 390, height: 844 } }); const p = await c.newPage();
    await p.goto(LOCAL + '/?tick-alpha=local'); await sleep(1500);
    await p.locator('.rk-tabbar').getByRole('link', { name: 'Replay' }).click(); await sleep(500);
    must(await p.getByRole('heading', { name: 'Replay needs a Session' }).isVisible(), 'replay explainer missing');
    await p.screenshot({ path: `${out}/local-390-replay-explainer.png` });
    const sid = await p.locator('.rk-table tbody tr th a').first().getAttribute('href');
    // Row names open the Session overview; the old ?session=<id> replay link must keep working.
    const id = new URL(LOCAL + sid).searchParams.get('of'); must(id, 'row link should open the Session overview');
    await p.goto(LOCAL + '/?tick-alpha=local&session=' + encodeURIComponent(id)); await p.waitForSelector('.candle-chart canvas', { timeout: 20000 });
    await c.close();
  });
  await step('Local CP2: Sessions search + Method combobox (keyboard), filtered-empty, overview, catalog search', async () => {
    const c = await browser.newContext({ viewport: { width: 1280, height: 800 } }); const p = await c.newPage();
    await p.goto(LOCAL + '/?tick-alpha=local&screen=sessions'); await sleep(1500);
    const trigger = p.locator('.rk-combo-trigger').first();
    await trigger.focus(); await p.keyboard.press('ArrowDown'); await sleep(150);
    must(await p.getByRole('listbox').isVisible(), 'ArrowDown opens the listbox');
    must(await p.getByRole('combobox', { name: /Search Method/ }).evaluate(el => el === document.activeElement), 'search input focused');
    await p.keyboard.press('Escape'); await sleep(120);
    must(!(await p.getByRole('listbox').isVisible()) && await trigger.evaluate(el => el === document.activeElement), 'Escape closes and returns focus');
    await trigger.click(); await p.keyboard.type('zzzz-no-method'); await sleep(120);
    must(await p.getByText('Nothing matches your search.').isVisible(), 'empty search state');
    await p.keyboard.press('Escape');
    await p.getByPlaceholder('Search Sessions or Methods').fill('zzzz-none'); await sleep(150);
    must(await p.getByRole('heading', { name: 'No Session matches' }).isVisible(), 'filtered-empty state');
    await p.getByRole('button', { name: 'Clear filters' }).click(); await sleep(150);
    await p.locator('.rk-table tbody th a').first().click(); await sleep(1500);
    must(await p.getByRole('heading', { name: 'Saved state' }).isVisible() && await p.getByText('Saved revision').isVisible(), 'Session overview shows saved state');
    await p.screenshot({ path: `${out}/local-1280-session-overview.png` });
    await p.goto(LOCAL + '/?tick-alpha=local&screen=catalog'); await sleep(1200);
    await p.getByPlaceholder('Search instruments').fill('eurusd'); await sleep(150);
    must(await p.getByRole('heading', { name: 'No confirmed instrument matches' }).isVisible(), 'catalog never invents instruments');
    await p.getByPlaceholder('Search instruments').fill('xau'); await sleep(150);
    must(await p.getByRole('heading', { name: 'XAUUSD' }).isVisible(), 'server instrument listed');
    await p.screenshot({ path: `${out}/local-1280-catalog.png` });
    await p.goto(LOCAL + '/?tick-alpha=local&screen=session-new'); await sleep(1200);
    must(await p.getByRole('button', { name: 'Continue' }).isDisabled(), 'Continue disabled until a Method is chosen');
    await c.close();
  });
  console.log(`product QA: ${passed} passed, ${fail.length} failed${fail.length ? ' → ' + fail.join(' | ') : ''}`);
  if (errors.length) console.log('page errors:', errors.slice(0, 5));
  await browser.close();
  process.exit(fail.length || errors.length ? 1 : 0);
})();
