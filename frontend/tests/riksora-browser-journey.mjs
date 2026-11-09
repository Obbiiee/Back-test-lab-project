import {createInterface} from 'node:readline';
import {pathToFileURL} from 'node:url';
import {resolve,join} from 'node:path';
import {readFileSync,realpathSync,statSync} from 'node:fs';

const ROOT=resolve(new URL('../../',import.meta.url).pathname);
const TOOLS=resolve(process.env.RIKSORA_BROWSER_TOOLS||join(ROOT,'frontend/tests/browser-tools'));
const input=createInterface({input:process.stdin})[Symbol.asyncIterator]();
const read=async()=>JSON.parse((await input.next()).value);
const config=await read();
const url=new URL(config.url);
const configOrigin=url.origin;
if(url.protocol!=='https:'||url.hostname!=='127.0.0.1'||Number(url.port)<1024||url.username||url.password||url.pathname!=='/'||url.search!=='?page=account'||url.hash||!/^[a-f0-9]{64}$/.test(config.nonce))throw Error('EXCLUSIVE_QA_TARGET_REQUIRED');
if(process.argv.includes('--check-config')){process.stdout.write('QA_TARGET_SYNTAX_ACCEPTED\n');process.exit(0);}
const expected=realpathSync(join(ROOT,'frontend/tests/artifacts'));
const evidence=realpathSync(config.evidence);
if(!evidence.startsWith(expected+'/')||(statSync(evidence).mode&0o777)!==0o700||statSync(evidence).uid!==process.getuid())throw Error('PRIVATE_QA_ARTIFACTS_REQUIRED');
for(const pkg of ['playwright','@playwright/test'])if(JSON.parse(readFileSync(join(TOOLS,'node_modules',pkg,'package.json'),'utf8')).version!=='1.64.1')throw Error('PINNED_PLAYWRIGHT_REQUIRED');
const {chromium}=await import(pathToFileURL(join(TOOLS,'node_modules/playwright/index.mjs')));
const {expect}=await import(pathToFileURL(join(TOOLS,'node_modules/@playwright/test/index.mjs')));
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({ignoreHTTPSErrors:true,serviceWorkers:'block',viewport:{width:1440,height:1000}});
const page=await context.newPage();page.setDefaultTimeout(20000);
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const apiTrace=[];page.on('response',async response=>{
  const url=new URL(response.url());if(url.origin!==configOrigin) return;
  const pathname=url.pathname.split('/').map(part=>part.startsWith('session:')||/^[a-f0-9-]{24,}$/i.test(part)?'{id}':part).join('/');
  const body=await response.json().catch(()=>null),detail=body?.detail;
  if(pathname.startsWith('/api/v1/')&&apiTrace.length<128){
    const jobCode=body?.result?.detail??body?.result?.error??body?.detail;
    apiTrace.push({method:response.request().method(),path:pathname,status:response.status(),
      code:typeof jobCode==='string'&&/^[A-Z][A-Z0-9_]{2,80}$/.test(jobCode)?jobCode:null,
      rows:pathname.endsWith('/journal/pages')&&Array.isArray(body?.orders)?body.orders.length:null,
      journalPage:pathname.endsWith('/journal/pages')?{
        artifact:body?.artifact==='BTL-TICK-JOURNAL-PAGE-1'?'BTL-TICK-JOURNAL-PAGE-1':'OTHER',
        schemaVersion:Number.isSafeInteger(body?.schemaVersion)?body.schemaVersion:null,
        hasNotes:Array.isArray(body?.notes),hasTotalOrders:Number.isSafeInteger(body?.totalOrders),
        hasComplete:typeof body?.complete==='boolean',
        paginationValid:body?.complete===true||typeof body?.nextCursor==='string'&&body.nextCursor.length>0,
      }:null,
      state:['QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED'].includes(body?.state)?body.state:null});
  }
});
const step=name=>process.stdout.write(JSON.stringify({step:name})+'\n');
let phase='proof';
try{
  const proof=await context.request.get(new URL('/__qa/browser-proof/'+config.nonce,url).href,{maxRedirects:0});
  expect(proof.status()).toBe(200);expect(await proof.json()).toEqual({purpose:'RIKSORA_EXCLUSIVE_SYNTHETIC_QA',nonce:config.nonce});
  // Product API calls pass through to the local real backend unchanged. All other
  // network origins are refused; there is no route.fulfill with authored API data.
  await context.route('**/*',route=>new URL(route.request().url()).origin===url.origin?route.continue():route.abort());
  phase='login_page';await page.goto(config.url);
  await expect(page.getByRole('tab',{name:'Sign in',exact:true})).toBeVisible();step('login_screen');
  phase='account_registration';await page.getByRole('tab',{name:'Create account',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).fill(config.email);
  await page.getByLabel('Password',{exact:true}).fill(config.password);
  await page.getByRole('button',{name:'Create account',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Check your inbox'})).toBeVisible();
  process.stdout.write(JSON.stringify({need:'verification',email:config.email})+'\n');
  phase='email_verification';await page.getByLabel('Verification code').fill((await read()).token);
  await page.getByRole('button',{name:'Verify email',exact:true}).click();
  await expect(page.getByText('Email verified. Sign in to start.')).toBeVisible();
  phase='password_login';await page.getByRole('tab',{name:'Sign in',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).fill(config.email);await page.getByLabel('Password',{exact:true}).fill(config.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await expect(page.getByLabel('New workspace name')).toBeVisible();
  phase='workspace_create';await page.getByLabel('New workspace name').fill('Synthetic browser acceptance');
  await page.getByRole('button',{name:'Create workspace',exact:true}).click();
  await page.getByRole('button',{name:/Synthetic browser acceptance/}).click();
  await expect(page.getByRole('heading',{name:'My Methods'})).toBeVisible();step('login_workspace');
  phase='method_create';await page.getByRole('link',{name:'Create your first Method'}).click();
  await page.getByLabel('Method name').fill('Synthetic browser method');
  await page.getByRole('button',{name:'Save Method',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Synthetic browser method'})).toBeVisible();step('method');
  phase='session_wizard_open';await page.getByRole('button',{name:'New Session',exact:true}).first().click();
  phase='session_method_select';await page.locator('.rk-wizard .rk-combo button.rk-combo-trigger').click();
  await page.getByRole('option',{name:/Synthetic browser method/}).click();
  phase='session_instrument_continue';await page.getByRole('button',{name:'Continue',exact:true}).click();
  phase='session_period_continue';await page.getByRole('button',{name:'Continue',exact:true}).click();
  phase='session_capital';await page.getByRole('button',{name:'Continue',exact:true}).click();
  await page.getByLabel('Session name').fill('Synthetic browser session');
  phase='session_review';
  await page.getByRole('button',{name:'Continue',exact:true}).click();
  phase='session_submit';
  await page.getByRole('button',{name:'Create Session',exact:true}).click();
  phase='session_wait';
  await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible({timeout:60000});step('session_replay');
  phase='replay';await expect(page.getByRole('button',{name:'Step ticks',exact:true})).toBeEnabled();
  const stepButton=page.getByRole('button',{name:'Step ticks',exact:true});
  await stepButton.click();await expect(stepButton).toBeEnabled();
  phase='order_review';await page.getByRole('button',{name:/Buy at Ask/}).click();
  const ticket=page.getByRole('dialog',{name:'Plan an order'});
  await ticket.getByLabel('Quantity (lots)').fill('0.01');
  await ticket.getByRole('button',{name:'Review order',exact:true}).click();
  const review=page.getByRole('dialog',{name:'Confirm reviewed order'});
  await expect(review.getByRole('heading',{name:'Confirm reviewed order'})).toBeVisible();
  phase='order_review_wait_for_arm';
  await expect(review.getByRole('button',{name:'Confirm order',exact:true})).toBeEnabled();
  const confirmRequest=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname.endsWith('/confirm'));
  const confirmResponse=page.waitForResponse(response=>response.request().method()==='POST'&&new URL(response.url()).pathname.endsWith('/confirm'));
  await review.getByRole('button',{name:'Confirm order',exact:true}).click();
  const request=await confirmRequest;const response=await confirmResponse;
  expect(response.status()).toBe(200);
  const receipt=await response.json();
  expect(receipt.durable).toBe(true);
  // This gate deliberately boots the local synthetic executor. Its committed
  // receipt is the local Tick contract; observed-source receipts are tested by
  // the PostgreSQL contract suite and must not be conflated here.
  expect(receipt.artifact).toBe('BTL-TICK-EXECUTION-RESULT-1');
  expect(typeof receipt.commandId).toBe('string');
  expect(receipt.commandHash).toMatch(/^[a-f0-9]{64}$/);
  expect(receipt.state?.sessionId).toBe(decodeURIComponent(new URL(request.url()).pathname.split('/').at(-2)));
  const authorization=await request.headerValue('authorization');
  expect(authorization).toBeTruthy();
  const retry=await context.request.post(request.url(),{headers:{Authorization:authorization,'Content-Type':'application/json'},data:request.postDataJSON(),maxRedirects:0});
  expect(retry.status()).toBe(200);expect(await retry.json()).toEqual(receipt);
  await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible();
  step('order_receipt');
  const terminal=page.getByRole('region',{name:'Trading and Analysis'});
  phase='trade_close_advance_to_open_positions';
  const beforeEntryRevision=Number(await terminal.getAttribute('data-revision'));
  expect(Number.isSafeInteger(beforeEntryRevision)).toBeTruthy();
  await stepButton.click();
  await expect(terminal).toHaveAttribute('data-revision',String(beforeEntryRevision+1));
  phase='trade_close_open_positions_tab';
  await terminal.getByRole('button',{name:'Open positions',exact:true}).click();
  phase='trade_close_open_positions_table';
  await expect(terminal.getByRole('table',{name:'Open positions'})).toBeVisible();
  phase='trade_close_find_open_position';
  const row=terminal.locator('tr[data-order-id]').first();
  await expect(row).toBeVisible();
  phase='trade_close_open_confirmation';
  await row.getByRole('button',{name:'Close position',exact:true}).click();
  phase='trade_close_commit_confirmation';
  const closeDialog=page.getByRole('dialog',{name:'Confirm position action'});
  await closeDialog.getByRole('button',{name:'Confirm action',exact:true}).click();
  await expect(closeDialog).toBeHidden();
  phase='trade_close_advance_after_commit';
  const beforeExitRevision=Number(await terminal.getAttribute('data-revision'));
  expect(Number.isSafeInteger(beforeExitRevision)).toBeTruthy();
  await stepButton.click();
  await expect(terminal).toHaveAttribute('data-revision',String(beforeExitRevision+1));
  phase='trade_close_closed_trades_tab';
  await terminal.getByRole('button',{name:'Closed trades',exact:true}).click();
  phase='trade_close_committed_row';
  await expect(terminal.getByRole('table',{name:'Closed trades'}).locator('tr[data-order-id]')).toHaveCount(1);step('committed_trade_journal_analytics');
  phase='journal_analytics';await terminal.getByRole('button',{name:'Journal',exact:true}).click();
  await expect(terminal.getByText('No saved note',{exact:true})).toBeVisible();
  await terminal.getByRole('button',{name:'Analysis',exact:true}).click();
  await expect(terminal.getByRole('heading',{name:'Committed position Analysis'})).toBeVisible();
  phase='workspace_method_back';await page.getByRole('link',{name:'Back to Synthetic browser method',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Synthetic browser method',exact:true})).toBeVisible();
  phase='global_journal_navigation';await page.getByRole('navigation',{name:'Main'}).getByRole('link',{name:'Journal',exact:true}).click();
  await page.waitForURL(current=>current.searchParams.get('screen')==='journal');
  phase='global_journal_select_session';await page.locator('.rk-toolbar-combo-wide .rk-combo-trigger').click();
  await expect(page.getByRole('dialog',{name:'Session'})).toBeVisible();
  await page.getByRole('option',{name:/Synthetic browser session/}).click();
  await page.waitForURL(current=>current.searchParams.get('of')===receipt.state.sessionId);
  phase='global_journal_content';
  const journal=page.locator('.rk-journal');
  await expect(journal).toHaveAttribute('aria-label','Orders in Synthetic browser session');
  const journalRows=journal.locator('li');
  phase='global_journal_wait_for_committed_order';await expect(journalRows).toHaveCount(1);
  const journalRowCount=await journalRows.count();
  phase=`global_journal_order_count_${journalRowCount}`;
  expect(journalRowCount).toBe(1);
  phase='global_sessions_navigation';await page.getByRole('navigation',{name:'Main'}).getByRole('link',{name:'Sessions',exact:true}).click();
  phase='global_sessions_heading';await expect(page.getByRole('heading',{name:'Sessions',exact:true})).toBeVisible();
  phase='global_analytics_link';
  await page.getByRole('link',{name:'Analytics for Synthetic browser session',exact:true}).click();
  await page.waitForURL(current=>current.searchParams.get('screen')==='analytics');
  phase='global_analytics_heading';await expect(page.locator('.rk-page-title h1')).toHaveText('Research analytics');
  phase='global_analytics_session';await expect(page.locator('.rk-scope dd').filter({hasText:'Synthetic browser session'})).toHaveCount(1);
  phase='logout_resume';await page.getByRole('navigation',{name:'Account and help'}).getByRole('link',{name:'Account',exact:true}).click();
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.getByRole('tab',{name:'Sign in',exact:true})).toBeVisible();
  await page.getByLabel('Email',{exact:true}).fill(config.email);await page.getByLabel('Password',{exact:true}).fill(config.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('button',{name:/Synthetic browser acceptance/}).click();
  await expect(page.getByRole('heading',{name:'My Methods'})).toBeVisible();
  await page.getByRole('button',{name:'Resume replay',exact:true}).click();
  await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible();
  const resumedTerminal=page.getByRole('region',{name:'Trading and Analysis'});
  await resumedTerminal.getByRole('button',{name:'Closed trades',exact:true}).click();
  await expect(resumedTerminal.getByRole('table',{name:'Closed trades'}).locator('tr[data-order-id]')).toHaveCount(1);
  expect(errors).toEqual([]);step('logout_login_resume');
  process.stdout.write(JSON.stringify({complete:true,browserVersion:browser.version()})+'\n');
}catch(error){
  await new Promise(resolve=>setTimeout(resolve,0));
  const panelTitles=await page.locator('.rk-state h1,.rk-state h2').allTextContents().catch(()=>[]);
  const panelKinds=new Map([['No orders yet','NO_ORDERS'],['No order matches','FILTERED_EMPTY'],
    ['The journal could not load','JOURNAL_ERROR'],['Loading the journal…','JOURNAL_LOADING'],
    ['Choose a Session','CHOOSE_SESSION'],['This Session is not in this workspace','SESSION_MISSING'],
    ['Analytics could not load','ANALYTICS_ERROR'],['Loading committed analytics…','ANALYTICS_LOADING'],
    ['Analytics unavailable for this Session','ANALYTICS_UNAVAILABLE']]);
  const screenState=panelTitles.map(title=>panelKinds.get(title)).filter(Boolean).slice(0,8);
  const browserDiagnostics=await page.evaluate(()=>{
    const error=document.querySelector('.rk-state-error .rk-state-body')?.textContent||'';
    const journalError=error.includes('Unsupported Journal page')?'JOURNAL_SCHEMA':
      error.includes('Journal pagination did not advance')?'JOURNAL_CURSOR':
      error.includes('Unsupported workspace response')?'WORKSPACE_SCHEMA':
      error.includes('REFUSED')||error.includes('CORRUPT_RECORD')?'BACKEND_REFUSAL':
      document.querySelector('.rk-state-error')?'OTHER':'NONE';
    return {routeScreen:new URL(location.href).searchParams.get('screen'),
      journalLists:document.querySelectorAll('.rk-journal').length,
      journalRows:document.querySelectorAll('.rk-journal li').length,journalError};
  }).catch(()=>({routeScreen:null,journalLists:0,journalRows:0,journalError:'UNAVAILABLE'}));
  process.stdout.write(JSON.stringify({failurePhase:phase,failureType:error?.name||'Error',screenState,
    pageErrorCount:errors.length,browserDiagnostics,apiTrace})+'\n');
  await page.screenshot({path:join(evidence,'failure.png'),fullPage:true}).catch(()=>{});
  const body=await page.locator('body').innerText().catch(()=> '');
  await import('node:fs/promises').then(fs=>fs.writeFile(join(evidence,'failure.txt'),String(error)+'\n'+body));
  throw error;
}finally{await context.close();await browser.close();}
