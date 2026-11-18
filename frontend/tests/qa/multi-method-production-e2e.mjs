// QA only: drives the public site with an injected synthetic bearer token (see deploy/site/v2_smoke.py for the account provisioning pattern). Not part of the build.
import {createRequire} from 'node:module'; import fs from 'node:fs';
const require = createRequire('/home/developer/projects/Back-test-lab-project/frontend/tests/browser-tools/');
const {chromium} = require('playwright'); const home = process.env.HOME;
const st = JSON.parse(fs.readFileSync(process.env.SC + '/mm.state', 'utf8'));
const browser = await chromium.launch({executablePath: `${home}/projects/Back-test-lab-project/frontend/tests/browser-tools/browsers/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell`,
  args:['--no-sandbox','--host-resolver-rules=MAP riksora.com 127.0.0.1'], env:{...process.env, LD_LIBRARY_PATH:`${home}/tools/chromelibs/lib`, FONTCONFIG_FILE:`${home}/tools/fonts.conf`}});
const dev = process.env.DEV || 'desktop'; const vp = dev === 'mobile' ? {width:390,height:844} : {width:1280,height:900};
const ctx = await browser.newContext({viewport: vp}); const page = await ctx.newPage(); const errs = [], bad = []; let createBody = null, switchBody = null;
page.on('pageerror', e => errs.push(String(e).slice(0,140))); page.on('console', m => { if (m.type()==='error') errs.push(m.text().slice(0,140)); });
page.on('response', r => { if (r.url().includes('/api/') && r.status() >= 400) bad.push(r.status()+' '+new URL(r.url()).pathname.slice(-40)); });
page.on('request', r => { const u = r.url(); if (r.method()==='POST' && /\/research\/sessions$/.test(u)) createBody = r.postData(); if (r.method()==='POST' && /\/commands$/.test(u) && /SET_METHOD/.test(r.postData()||'')) switchBody = r.postData(); });
await page.route('**/api/v1/auth/google/exchange', r => r.fulfill({status:200, contentType:'application/json', body: JSON.stringify({schemaVersion:1, access_token: st.tok, token_type:'bearer'})}));
const out = {dev, steps: []}; const ok = (n, v, d='') => { out.steps.push({n, ok: !!v, d: String(d).slice(0,120)}); if (!v) throw new Error('STEP FAILED: ' + n + ' ' + d); };
try {
  await page.goto('https://riksora.com/?page=account&auth=google', {waitUntil:'domcontentloaded'}); await page.waitForTimeout(5000);
  await page.getByRole('button', {name: /MM browser/}).first().click(); await page.waitForTimeout(3500);
  ok('workspace opened', await page.getByRole('heading', {name:'My Methods'}).isVisible());
  await page.getByRole('button', {name:'New Session', exact:true}).or(page.getByRole('link', {name:/New Session/})).first().click(); await page.waitForTimeout(1500);
  if (!(await page.locator('.rk-wizard').count())) { await page.getByRole('button', {name:'New Session', exact:true}).or(page.getByRole('link', {name:/New Session/})).first().click(); await page.waitForTimeout(1500); }
  const trig = page.locator('.rk-wizard .rk-combo button.rk-combo-trigger'); await trig.waitFor({state:'visible', timeout:15000}); await trig.click(); await page.getByRole('option', {name:/Free style/}).click(); await page.waitForTimeout(500);
  ok('wizard offers other Methods', await page.getByText('Also allow switching to (optional)').isVisible());
  await page.getByLabel(/Protocol 1R:2R/).check();
  for (let i=0;i<3;i++) await page.getByRole('button', {name:'Continue', exact:true}).click();
  await page.getByLabel('Session name').fill('MM browser session'); await page.getByRole('button', {name:'Continue', exact:true}).click();
  await page.getByRole('button', {name:'Create Session', exact:true}).click();
  await page.getByRole('region', {name:'Tick replay workspace'}).waitFor({state:'visible', timeout:60000});
  const body = JSON.parse(createBody||'{}');
  ok('create request carries the Method set', Array.isArray(body.methodIds) && body.methodIds.length===2 && body.methodIds.includes(st.a) && body.methodIds.includes(st.b) && body.methodId===st.a, JSON.stringify(body.methodIds));
  const sel = page.getByLabel('Active Method'); await sel.waitFor({state:'visible', timeout:15000});
  ok('Active Method selector shows Free style', (await sel.inputValue())===st.a);
  await page.screenshot({path:`mm-${dev}-1-created.png`});
  await sel.selectOption(st.b); await page.waitForTimeout(4000);
  ok('switch request sent', switchBody && JSON.parse(switchBody).payload.methodId===st.b);
  ok('selector now shows Protocol', (await sel.inputValue())===st.b);
  ok('notice explains the switch', await page.getByText(/Now trading with Protocol/).first().isVisible().catch(()=>false));
  await page.screenshot({path:`mm-${dev}-2-switched.png`});
  await sel.selectOption(st.a); await page.waitForTimeout(3000); ok('switch back', (await sel.inputValue())===st.a);
  ok('no page errors', errs.length===0, errs.join(' | ')); ok('no failed API calls', bad.length===0, bad.join(' | '));
  out.pass = true;
} catch (e) { out.pass = false; out.error = String(e).slice(0,300); out.errs = errs; out.bad = bad; await page.screenshot({path:`mm-${dev}-fail.png`}).catch(()=>{}); }
await browser.close(); console.log(JSON.stringify(out));
