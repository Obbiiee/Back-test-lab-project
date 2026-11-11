import {createInterface} from 'node:readline';
import {pathToFileURL} from 'node:url';
import {resolve,join} from 'node:path';
import {readFileSync,realpathSync,statSync} from 'node:fs';
import {createHash} from 'node:crypto';

const ROOT=resolve(new URL('../../',import.meta.url).pathname);
const TOOLS=resolve(process.env.RIKSORA_BROWSER_TOOLS||join(ROOT,'frontend/tests/browser-tools'));
const input=createInterface({input:process.stdin})[Symbol.asyncIterator]();
const read=async()=>JSON.parse((await input.next()).value);
const config=await read();
if(!Number.isSafeInteger(config.startDelayMs??0)||(config.startDelayMs??0)<0||(config.startDelayMs??0)>180000)
  throw Error('COHORT_START_DELAY_INVALID');
const url=new URL(config.url);
const configOrigin=url.origin;
if(url.protocol!=='https:'||url.hostname!=='127.0.0.1'||Number(url.port)<1024||url.username||url.password||url.pathname!=='/'||url.search!=='?page=account'||url.hash||!/^[a-f0-9]{64}$/.test(config.nonce))throw Error('EXCLUSIVE_QA_TARGET_REQUIRED');
if(process.argv.includes('--check-config')){process.stdout.write('QA_TARGET_SYNTAX_ACCEPTED\n');process.exit(0);}
const expected=realpathSync(join(ROOT,'frontend/tests/artifacts'));
const evidence=realpathSync(config.evidence);
if(!evidence.startsWith(expected+'/')||(statSync(evidence).mode&0o777)!==0o700||statSync(evidence).uid!==process.getuid())throw Error('PRIVATE_QA_ARTIFACTS_REQUIRED');
for(const pkg of ['playwright','@playwright/test'])if(JSON.parse(readFileSync(join(TOOLS,'node_modules',pkg,'package.json'),'utf8')).version!=='1.64.1')throw Error('PINNED_PLAYWRIGHT_REQUIRED');
const {chromium}=await import(pathToFileURL(join(TOOLS,'node_modules/playwright/index.mjs')));
const {expect:baseExpect}=await import(pathToFileURL(join(TOOLS,'node_modules/@playwright/test/index.mjs')));
const {retryExactConfirm}=await import(pathToFileURL(join(TOOLS,'retry-exact-confirm.mjs')));
const digestIdentity=value=>createHash('sha256').update(value).digest('hex').slice(0,20);
// Matches the frontend's bounded product operation deadline so an explicit
// pre-admission busy response can be retried without the harness truncating it.
const API_REQUEST_DEADLINE_MS=95000;
const safePath=pathname=>pathname.split('/').map(part=>{
  let decoded=part;try{decoded=decodeURIComponent(part);}catch{}
  return /^[A-Za-z][A-Za-z0-9_-]*:[a-f0-9-]{24,}$/i.test(decoded)||
    /^[a-f0-9-]{24,}$/i.test(decoded)?'{id}':part;
}).join('/');
// Product API requests have a documented 30 s bound. Playwright's independent
// 5 s assertion default was shorter and falsely failed while a bounded read
// was recovering from the explicit RESEARCH_BUSY backpressure response.
const expect=baseExpect.configure({timeout:30000});
if(config.startDelayMs)await new Promise(resolve=>setTimeout(resolve,config.startDelayMs));
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({ignoreHTTPSErrors:true,serviceWorkers:'block',viewport:{width:1440,height:1000}});
const page=await context.newPage();page.setDefaultTimeout(20000);
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const requestFailures=[];page.on('requestfailed',request=>{
  const url=new URL(request.url());if(url.origin!==configOrigin)return;
  const pathname=url.pathname.split('/').map(part=>part.startsWith('session:')||/^[a-f0-9-]{24,}$/i.test(part)?'{id}':part).join('/');
  const rawFailure=request.failure()?.errorText||'';
  const failure=/^net::ERR_[A-Z_]+$/.test(rawFailure)?rawFailure:'NETWORK_ERROR';
  if(pathname.startsWith('/api/v1/')&&requestFailures.length<32)
    requestFailures.push({method:request.method(),path:pathname,error:failure});
});
const apiBodyReads=[];const apiTrace=[];const apiStarts=new Map();let apiResponseCount=0;
const apiRequestKey=request=>`${request.method()}\n${request.url()}`;
page.on('request',request=>{
  const requestUrl=new URL(request.url());
  if(requestUrl.origin===configOrigin&&requestUrl.pathname.startsWith('/api/v1/')){
    const key=apiRequestKey(request),started=apiStarts.get(key)??[];
    started.push(performance.now());apiStarts.set(key,started);
  }
});
page.on('response',response=>{
  const url=new URL(response.url());if(url.origin!==configOrigin) return;
  const pathname=safePath(url.pathname);
  if(pathname.startsWith('/api/v1/'))apiResponseCount++;
  if(pathname.startsWith('/api/v1/')&&apiTrace.length<512){
    const requestTiming=response.request().timing();
    const started=apiStarts.get(apiRequestKey(response.request()))??[];
    const requestStarted=started.shift();
    if(!started.length)apiStarts.delete(apiRequestKey(response.request()));
    const requestDuration=Number.isFinite(requestTiming.responseEnd)&&requestTiming.responseEnd>0?
      requestTiming.responseEnd:requestStarted===undefined?0:Math.max(0,performance.now()-requestStarted);
    const row={method:response.request().method(),path:pathname,status:response.status(),code:null,
      rows:null,journalPage:null,state:null,
      atUnixMs:Date.now(),durationMs:Math.max(0,requestDuration)};
    apiTrace.push(row);
    const parsed=(response.status()===204?Promise.resolve(null):response.json()).then(body=>{
      row.serverTiming=response.headers()['server-timing']??null;
      const jobCode=body?.result?.detail??body?.result?.error??body?.detail;
      row.code=typeof jobCode==='string'&&/^[A-Z][A-Z0-9_]{2,80}$/.test(jobCode)?jobCode:null;
      row.rows=pathname.endsWith('/journal/pages')&&Array.isArray(body?.orders)?body.orders.length:null;
      row.journalPage=pathname.endsWith('/journal/pages')?{
        artifact:body?.artifact==='BTL-TICK-JOURNAL-PAGE-1'?'BTL-TICK-JOURNAL-PAGE-1':'OTHER',
        schemaVersion:Number.isSafeInteger(body?.schemaVersion)?body.schemaVersion:null,
        hasNotes:Array.isArray(body?.notes),hasTotalOrders:Number.isSafeInteger(body?.totalOrders),
        hasComplete:typeof body?.complete==='boolean',
        complete:typeof body?.complete==='boolean'?body.complete:null,
        totalOrders:Number.isSafeInteger(body?.totalOrders)?body.totalOrders:null,
        noteCount:Array.isArray(body?.notes)?body.notes.length:null,
        firstOrderStatuses:Array.isArray(body?.orders)?body.orders.slice(0,4).map(order=>
          ['ACTIVE','PENDING','UNRESOLVED','CLOSED','EXPIRED'].includes(order?.status)?order.status:'OTHER'):null,
        paginationValid:body?.complete===true||typeof body?.nextCursor==='string'&&body.nextCursor.length>0,
      }:null;
      row.state=['QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','RECONCILE_REQUIRED'].includes(body?.state)?body.state:null;
      const jobId=typeof body?.jobId==='string'?body.jobId:typeof body?.result?.jobId==='string'?body.result.jobId:
        pathname.endsWith('/jobs/{id}')?decodeURIComponent(url.pathname.split('/').at(-1)):null;
      if(typeof jobId==='string'&&/^[a-f0-9-]{36}$/i.test(jobId))row.jobDigest=digestIdentity(jobId);
      const sessionSegment=url.pathname.split('/').find(part=>{
        try{return decodeURIComponent(part).startsWith('session:');}catch{return false;}
      });
      if(sessionSegment)row.sessionDigest=digestIdentity(decodeURIComponent(sessionSegment));
      if(pathname.endsWith('/jobs/{id}')){
        const value=body?.result,state=value?.state,analysis=value?.analysis;
        if(state&&Number.isSafeInteger(state.revision)){
          const active=state.orders&&typeof state.orders==='object'?Object.values(state.orders):[];
          const projected=Array.isArray(analysis?.orders)?analysis.orders:[];
          row.sessionEvidence={revision:state.revision,balance:typeof state.balance==='string'?state.balance:null,
            nextGroupIndex:Number.isSafeInteger(state.nextGroupIndex)?state.nextGroupIndex:null,
            ended:typeof state.ended==='boolean'?state.ended:null,
            unresolved:typeof state.unresolved==='boolean'?state.unresolved:null,
            throughNs:typeof state.throughNs==='string'?state.throughNs:null,
            activeOrders:active.slice(0,32).map(order=>({status:order?.status,exitRequested:order?.exitRequested===true})),
            projectedOrderStatuses:projected.slice(0,32).map(order=>order?.status),
            tradeCount:Number.isSafeInteger(analysis?.metrics?.tradeCount)?analysis.metrics.tradeCount:null};
        }
      }
      process.stdout.write(JSON.stringify({apiEvent:row})+'\n');
    });
    apiBodyReads.push(parsed.catch(()=>{}));
  }
});
const completedSteps=[];
const step=name=>{completedSteps.push(name);process.stdout.write(JSON.stringify({step:name,atUnixMs:Date.now()})+'\n');};
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
  if(config.cohortBarrier){
    phase='cohort_barrier';process.stdout.write(JSON.stringify({need:'cohort_start'})+'\n');
    const release=await read();if(release?.start!==true||!Number.isSafeInteger(release.delayMs??0)||
      (release.delayMs??0)<0||(release.delayMs??0)>30000)throw Error('COHORT_START_REFUSED');
    if(release.delayMs)await new Promise(resolve=>setTimeout(resolve,release.delayMs));
  }
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
  await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible({timeout:95000});step('session_replay');
  phase='replay';await expect(page.getByRole('button',{name:'Step ticks',exact:true})).toBeEnabled({timeout:60000});
  const stepButton=page.getByRole('button',{name:'Step ticks',exact:true});
  await stepButton.click();await expect(stepButton).toBeEnabled({timeout:95000});
  phase='order_review';await page.getByRole('button',{name:/Buy at Ask/}).click();
  const ticket=page.getByRole('dialog',{name:'Plan an order'});
  await ticket.getByLabel('Quantity (lots)').fill('0.01');
  const reviewResponse=page.waitForResponse(response=>response.request().method()==='POST'&&
    new URL(response.url()).pathname.endsWith('/reviews')&&response.status()===200,
    {timeout:API_REQUEST_DEADLINE_MS});
  await ticket.getByRole('button',{name:'Review order',exact:true}).click();
  const review=page.locator('[role="dialog"][aria-label="Confirm reviewed order"]');
  expect((await reviewResponse).status()).toBe(200);
  await expect(review.getByRole('heading',{name:'Confirm reviewed order'})).toBeVisible({timeout:60000});
  phase='order_review_wait_for_arm';
  await expect(review.getByRole('button',{name:'Confirm order',exact:true})).toBeEnabled();
  const confirmRequest=page.waitForRequest(request=>request.method()==='POST'&&new URL(request.url()).pathname.endsWith('/confirm'));
  const confirmResponse=page.waitForResponse(response=>response.request().method()==='POST'&&
    new URL(response.url()).pathname.endsWith('/confirm')&&response.status()===200,
    {timeout:API_REQUEST_DEADLINE_MS});
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
  const retryPayload=request.postDataJSON();
  const retryPath=new URL(request.url()).pathname.split('/').map(part=>part.startsWith('session:')||/^[a-f0-9-]{24,}$/i.test(part)?'{id}':part).join('/');
  const retry=await retryExactConfirm({
    send:({timeoutMs})=>context.request.post(request.url(),{headers:{Authorization:authorization,'Content-Type':'application/json'},
      data:retryPayload,maxRedirects:0,timeout:timeoutMs}),
    onResponse:row=>{apiResponseCount++;apiTrace.push({method:'POST',path:retryPath,status:row.status,code:row.code,
      rows:null,journalPage:null,state:null,durationMs:row.durationMs});},
  });
  expect(retry.body).toEqual(receipt);
  const reviewDialog=page.getByRole('dialog',{name:'Confirm reviewed order'});
  if(await reviewDialog.isVisible()){
    // A committed receipt with a failed workspace refresh is explicitly shown
    // as COMMITTED and offers Reload Session. Exercise that durable recovery
    // path instead of interacting through the modal or assuming stale state.
    const reload=reviewDialog.getByRole('button',{name:'Reload Session',exact:true});
    const resolution=await Promise.race([
      reload.waitFor({state:'visible',timeout:95000}).then(()=> 'reload'),
      reviewDialog.waitFor({state:'hidden',timeout:95000}).then(()=> 'refreshed'),
    ]);
    if(resolution==='reload'){
      await reload.click({timeout:95000});
      await expect(reviewDialog).not.toBeVisible({timeout:95000});
    }
  }
  await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible();
  await expect(stepButton).toBeEnabled({timeout:95000});
  step('order_receipt');
  const terminal=page.getByRole('region',{name:'Trading and Analysis'});
  phase='trade_close_advance_to_open_positions';
  const beforeEntryRevision=Number(await terminal.getAttribute('data-revision'));
  expect(Number.isSafeInteger(beforeEntryRevision)).toBeTruthy();
  await expect(stepButton).toBeEnabled({timeout:95000});
  await stepButton.click({timeout:95000});
  await expect(terminal).toHaveAttribute('data-revision',String(beforeEntryRevision+1),{timeout:95000});
  await expect(stepButton).toBeEnabled({timeout:95000});
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
  // A close commits before the next replay step; the single worker may still
  // have earlier traders' jobs ahead of this Session. Bound this wait by the
  // repository's 60 s queue TTL instead of Playwright's 20 s locator default.
  await expect(stepButton).toBeEnabled({timeout:95000});
  await stepButton.click({timeout:60000});
  await expect(terminal).toHaveAttribute('data-revision',String(beforeExitRevision+1));
  await expect(stepButton).toBeEnabled({timeout:95000});
  phase='trade_close_closed_trades_tab';
  await terminal.getByRole('button',{name:'Closed trades',exact:true}).click();
  phase='trade_close_committed_row';
  await expect(terminal.getByRole('table',{name:'Closed trades'}).locator('tr[data-order-id]')).toHaveCount(1,{timeout:95000});
  await expect(page.getByLabel('Saved balance 9999.7 USD')).toBeVisible();step('committed_trade_journal_analytics');
  phase='journal_analytics_workspace_note';
  const journalResponse=page.waitForResponse(response=>response.request().method()==='GET'&&
    new URL(response.url()).pathname.endsWith('/journal/pages')&&response.status()===200,{timeout:95000});
  await terminal.getByRole('button',{name:'Journal',exact:true}).click();
  expect((await journalResponse).status()).toBe(200);
  const sessionJournal=terminal.locator('.alpha-journal');
  await expect(sessionJournal.getByRole('heading',{name:'Research journal'})).toBeVisible();
  const journalOrder=sessionJournal.locator('article');
  await expect(journalOrder).toHaveCount(1,{timeout:60000});
  await expect(journalOrder.getByRole('heading',{name:'LONG · CLOSED'})).toBeVisible();
  await expect(journalOrder.locator('small')).toHaveText('No saved note');
  phase='journal_analytics_workspace_tab';
  await terminal.getByRole('button',{name:'Analysis',exact:true}).click();
  phase='journal_analytics_workspace_heading';
  await expect(terminal.getByRole('heading',{name:'Committed position Analysis'})).toBeVisible();
  phase='journal_analytics_trade_count_label';
  const completedLabel=terminal.locator('.alpha-analysis dt').filter({hasText:/^Completed trades$/});
  // The chart precedes the definition list inside a bounded scroll panel. Bring
  // the committed metric into the panel viewport before asserting visibility.
  await completedLabel.scrollIntoViewIfNeeded();
  await expect(completedLabel).toHaveText('Completed trades');
  phase='journal_analytics_trade_count_value';
  const completedMetric=terminal.locator('.alpha-analysis dl div').filter({hasText:'Completed trades'});
  await expect(completedMetric.locator('dd')).toHaveText('1');
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
  phase='global_analytics_session';await expect(page.locator('.rk-scope dd').filter({hasText:'Synthetic browser session'})).toHaveCount(1,{timeout:60000});
  phase='logout_resume';await page.getByRole('navigation',{name:'Account and help'}).getByRole('link',{name:'Account',exact:true}).click();
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.getByRole('tab',{name:'Sign in',exact:true})).toBeVisible();
  await page.getByLabel('Email',{exact:true}).fill(config.email);await page.getByLabel('Password',{exact:true}).fill(config.password);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('button',{name:/Synthetic browser acceptance/}).click();
  await expect(page.getByRole('heading',{name:'My Methods'})).toBeVisible();
  await page.getByRole('button',{name:'Resume replay',exact:true}).click();
  await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible({timeout:95000});
  const resumedTerminal=page.getByRole('region',{name:'Trading and Analysis'});
  await resumedTerminal.getByRole('button',{name:'Closed trades',exact:true}).click();
  await expect(resumedTerminal.getByRole('table',{name:'Closed trades'}).locator('tr[data-order-id]')).toHaveCount(1,{timeout:95000});
  await Promise.allSettled(apiBodyReads);
  const busyResponses=apiTrace.filter(entry=>(entry.status===429&&entry.code==='RESEARCH_BUSY')||
    (entry.status===503&&entry.code==='SERVICE_BUSY'));
  const unrecoveredBusy=busyResponses.filter(entry=>{
    const index=apiTrace.indexOf(entry);
    return !apiTrace.slice(index+1).some(next=>next.method===entry.method&&next.path===entry.path&&next.status>=200&&next.status<400);
  });
  expect(apiTrace.filter(entry=>(entry.status===429&&entry.code!=='RESEARCH_BUSY')||
    (entry.status===503&&entry.code!=='SERVICE_BUSY')||entry.status>=500&&entry.status!==503)).toEqual([]);
  expect(unrecoveredBusy).toEqual([]);
  const committedJournal=apiTrace.filter(entry=>entry.path.endsWith('/journal/pages')&&entry.status===200).at(-1);
  expect(committedJournal?.journalPage?.firstOrderStatuses).toEqual(['CLOSED']);
  expect(errors).toEqual([]);step('logout_login_resume');
  process.stdout.write(JSON.stringify({complete:true,browserVersion:browser.version(),
    transientBusyCount:busyResponses.length,
    apiResponseCount,pageErrorCount:errors.length,failedRequests:requestFailures.length,
    steps:completedSteps})+'\n');
}catch(error){
  await Promise.allSettled(apiBodyReads);
  await new Promise(resolve=>setTimeout(resolve,0));
  if(phase==='trade_close_committed_row')
    await page.getByRole('region',{name:'Trading and Analysis'}).getByRole('button',{name:'Open positions',exact:true}).click().catch(()=>{});
  const panelTitles=await page.locator('.rk-state h1,.rk-state h2').allTextContents().catch(()=>[]);
  const panelKinds=new Map([['No orders yet','NO_ORDERS'],['No order matches','FILTERED_EMPTY'],
    ['The journal could not load','JOURNAL_ERROR'],['Loading the journal…','JOURNAL_LOADING'],
    ['Choose a Session','CHOOSE_SESSION'],['This Session is not in this workspace','SESSION_MISSING'],
    ['Analytics could not load','ANALYTICS_ERROR'],['Loading committed analytics…','ANALYTICS_LOADING'],
    ['Analytics unavailable for this Session','ANALYTICS_UNAVAILABLE']]);
  const screenState=panelTitles.map(title=>panelKinds.get(title)).filter(Boolean).slice(0,8);
  const browserDiagnostics=await page.evaluate(()=>{
    const error=document.querySelector('.rk-state-error .rk-state-body')?.textContent||'';
    const safeError=error.replace(/\b[0-9a-f]{8}-[0-9a-f-]{27,}\b/gi,'{id}')
      .replace(/\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b/g,'{email}')
      .replace(/\s+/g,' ').trim().slice(0,180);
    const journalError=error.includes('Unsupported Journal page')?'JOURNAL_SCHEMA':
      error.includes('Journal pagination did not advance')?'JOURNAL_CURSOR':
      error.includes('Unsupported workspace response')?'WORKSPACE_SCHEMA':
      error.includes('REFUSED')||error.includes('CORRUPT_RECORD')?'BACKEND_REFUSAL':
      document.querySelector('.rk-state-error')?'OTHER':'NONE';
    const terminal=document.querySelector('[aria-label="Trading and Analysis"]');
    const openTable=terminal?.querySelector('table[aria-label="Open positions"]');
    const openRows=Array.from(openTable?.querySelectorAll('tr[data-order-id]')||[]).slice(0,4).map(row=>{
      const cells=Array.from(row.querySelectorAll('td'));
      const rawStatus=cells[2]?.textContent?.trim()||'';
      const status=['ACTIVE','PENDING','UNRESOLVED'].find(value=>rawStatus.startsWith(value))||'OTHER';
      return {status,exitRequested:rawStatus.includes('exit requested'),
        side:['LONG','SHORT'].includes(cells[1]?.textContent?.trim())?cells[1].textContent.trim():'OTHER'};
    });
    return {routeScreen:new URL(location.href).searchParams.get('screen'),
      journalLists:document.querySelectorAll('.rk-journal').length,
      journalRows:document.querySelectorAll('.rk-journal li').length,journalError,
      sanitizedError:safeError,terminalRevision:Number.isSafeInteger(Number(terminal?.getAttribute('data-revision')))?
        Number(terminal.getAttribute('data-revision')):null,openTableVisible:Boolean(openTable),openRows};
  }).catch(()=>({routeScreen:null,journalLists:0,journalRows:0,journalError:'UNAVAILABLE'}));
  const failureMessage=String(error?.message||error).split('\n')[0]
    .replace(/\b[0-9a-f]{8}-[0-9a-f-]{27,}\b/gi,'{id}')
    .replace(/\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b/g,'{email}')
    .slice(0,300);
  process.stdout.write(JSON.stringify({failurePhase:phase,failureType:error?.name||'Error',screenState,
    pageErrorCount:errors.length,browserDiagnostics,browserFailureMessage:failureMessage,
    apiTrace:apiTrace.slice(-64),requestFailures})+'\n');
  await page.screenshot({path:join(evidence,'failure.png'),fullPage:true}).catch(()=>{});
  const body=await page.locator('body').innerText().catch(()=> '');
  await import('node:fs/promises').then(fs=>fs.writeFile(join(evidence,'failure.txt'),String(error)+'\n'+body));
  throw error;
}finally{await context.close();await browser.close();}
