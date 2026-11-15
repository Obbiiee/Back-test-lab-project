import {createInterface} from 'node:readline';
import {pathToFileURL} from 'node:url';
import {resolve,join} from 'node:path';
import {readFileSync,realpathSync,statSync,appendFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const ROOT=resolve(new URL('../../',import.meta.url).pathname);
const TOOLS=resolve(process.env.RIKSORA_BROWSER_TOOLS||join(ROOT,'frontend/tests/browser-tools'));
const input=createInterface({input:process.stdin})[Symbol.asyncIterator]();
const read=async()=>JSON.parse((await input.next()).value);
const config=await read();
if(!Number.isSafeInteger(config.startDelayMs??0)||(config.startDelayMs??0)<0||(config.startDelayMs??0)>240000)
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
const browserEndpoint=process.env.RIKSORA_BROWSER_WS;
let browser;
if(browserEndpoint){
  let endpoint;
  try{endpoint=new URL(browserEndpoint);}catch{throw Error('LOCAL_BROWSER_HOST_REQUIRED');}
  if(endpoint.protocol!=='ws:'||endpoint.hostname!=='127.0.0.1'||endpoint.port===''||endpoint.username||endpoint.password)
    throw Error('LOCAL_BROWSER_HOST_REQUIRED');
  browser=await chromium.connect(browserEndpoint);
}else browser=await chromium.launch({headless:true,chromiumSandbox:process.env.RIKSORA_QA_NO_SANDBOX!=='1',args:process.env.RIKSORA_QA_E2E_COVERAGE==='1'?['--host-resolver-rules=MAP riksora-landing.test 127.0.0.1']:[]});
const context=await browser.newContext({ignoreHTTPSErrors:true,serviceWorkers:'block',viewport:{width:1440,height:1000}});
const page=await context.newPage();page.setDefaultTimeout(20000);
const errors=[];page.on('pageerror',error=>errors.push(error.message));
const consoleErrors=[];page.on('console',message=>{
  if(message.type()!=='error'||consoleErrors.length>=16)return;
  consoleErrors.push(message.text().split('\n',1)[0].slice(0,300));
});
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
const recordFile=process.env.RIKSORA_QA_RECORD_API||null;const recordSeq=new WeakMap();let recordCounter=0;
page.on('request',request=>{
  const requestUrl=new URL(request.url());
  if(recordFile&&requestUrl.origin===configOrigin&&requestUrl.pathname.startsWith('/api/v1/'))recordSeq.set(request,recordCounter++);
  if(requestUrl.origin===configOrigin&&requestUrl.pathname.startsWith('/api/v1/')){
    const key=apiRequestKey(request),started=apiStarts.get(key)??[];
    started.push(performance.now());apiStarts.set(key,started);
  }
});
page.on('response',response=>{
  const url=new URL(response.url());if(url.origin!==configOrigin) return;
  const pathname=safePath(url.pathname);
  if(pathname.startsWith('/api/v1/'))apiResponseCount++;
  if(recordFile&&recordSeq.has(response.request())){
    // QA-only opt-in: private record of one synthetic trader's API traffic, used to replay the same journey over HTTP.
    const req=response.request(),seq=recordSeq.get(req);
    response.text().catch(()=>'').then(text=>appendFileSync(recordFile,JSON.stringify({seq,method:req.method(),path:url.pathname+url.search,
      job:req.headers()['x-btl-job']??null,contentType:req.headers()['content-type']??null,body:req.postData()??null,status:response.status(),response:text})+'\n'));
  }
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
    // Exports (text/csv, application/pdf) are not JSON; they still count as API responses and must be traced like any other.
    const parsed=(response.status()===204||!/json/i.test(response.headers()['content-type']??'')?Promise.resolve(null):response.json()).then(body=>{
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
      const jumpStatus=body?.result?.status??body?.status;
      row.jumpStatus=['EVENT_FOUND','SEARCHING','NO_EVENT_UNTIL_SESSION_END','NO_ACTIVE_ORDERS'].includes(jumpStatus)?jumpStatus:null;
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
  // This harness runs Playwright assertions outside the test runner. A failed
  // `expect(...).toBeVisible()` can mask the actual timeout with an internal
  // matcher error, so use the equivalent locator wait to preserve diagnostics.
  await page.getByRole('tab',{name:'Sign in',exact:true}).waitFor({state:'visible',timeout:30000});step('login_screen');
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
  if(process.env.RIKSORA_QA_E2E_COVERAGE==='1'||process.env.RIKSORA_QA_E2E_ENTITLEMENT==='1'){
    const fsp=await import('node:fs/promises');
    const shot=async name=>page.screenshot({path:join(evidence,name+'.png')});
    const mainNav=label=>page.getByRole('navigation',{name:'Main'}).getByRole('link',{name:label,exact:true});
    const seen={ws:null,sid:null};
    page.on('request',r=>{const m=/\/workspaces\/([0-9a-f-]{36})\/research\/sessions\/([^/?]+)/.exec(r.url());if(m){seen.ws=m[1];const d=decodeURIComponent(m[2]);if(d.startsWith('session:'))seen.sid=d;}});
    const guarded=fn=>async(...args)=>{try{return await fn(...args);}catch(error){await page.screenshot({path:join(evidence,'cov-failure-'+Date.now()+'.png')}).catch(()=>{});await fsp.writeFile(join(evidence,'cov-failure.txt'),String(error)+'\n'+await page.locator('body').innerText().catch(()=>'')).catch(()=>{});throw error;}};
    const newMethod=guarded(async(name,{protocol=false,condition='Trend aligned',checklist=false}={})=>{
      phase='cov_method_'+name;
      const first=page.getByRole('link',{name:'Create your first Method'});
      if(await first.count())await first.click();else{await mainNav('My Methods').click();await page.getByRole('link',{name:/New Method/}).first().click();}
      await page.getByLabel('Method name').fill(name);
      if(protocol){
        await page.getByRole('radio',{name:'Protocol',exact:true}).click();
        await page.getByRole('textbox',{name:'Condition 1',exact:true}).fill(condition);
        const sw=page.getByRole('checkbox',{name:/Checklist enforcement/});
        if(checklist!==await sw.isChecked())await sw.click({force:true});
      }
      await page.getByRole('button',{name:'Save Method',exact:true}).click();
      await expect(page.getByRole('heading',{name})).toBeVisible();
    });
    const newSession=guarded(async(methodName,sessionName)=>{
      phase='cov_session_'+sessionName;
      await page.getByRole('button',{name:'New Session',exact:true}).or(page.getByRole('link',{name:/New Session/})).first().click();
      await page.locator('.rk-wizard .rk-combo button.rk-combo-trigger').click();
      await page.getByRole('option',{name:new RegExp(methodName)}).click();
      for(let i=0;i<3;i++)await page.getByRole('button',{name:'Continue',exact:true}).click();
      await page.getByLabel('Session name').fill(sessionName);
      await page.getByRole('button',{name:'Continue',exact:true}).click();
      await page.getByRole('button',{name:'Create Session',exact:true}).click();
      await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible({timeout:95000});
      await expect(page.getByRole('button',{name:'Step ticks',exact:true})).toBeEnabled({timeout:60000});
    });
    const terminal=()=>page.getByRole('region',{name:'Trading and Analysis'});
    const revision=async()=>Number(await terminal().getAttribute('data-revision'));
    const stepOnce=async()=>{const before=await revision();const b=page.getByRole('button',{name:'Step ticks',exact:true});await b.click();await expect.poll(revision,{timeout:95000}).toBeGreaterThanOrEqual(before);await expect(b).toBeEnabled({timeout:95000});};
    if(process.env.RIKSORA_QA_E2E_COVERAGE==='1'){
    // ---- Landing (hosted home on a non-local host name), in its own context so the session under test is untouched
    phase='cov_landing';
    {
      const landingContext=await browser.newContext({ignoreHTTPSErrors:true,serviceWorkers:'block',viewport:{width:1280,height:900}});
      await landingContext.route('**/*',route=>new URL(route.request().url()).hostname==='riksora-landing.test'?route.continue():route.abort());
      const landing=await landingContext.newPage();
      await landing.goto(`https://riksora-landing.test:${url.port}/`);
      await landing.waitForLoadState('domcontentloaded');
      await landing.waitForTimeout(1500);
      await landing.screenshot({path:join(evidence,'landing.png')});
      const text=await landing.locator('body').innerText();
      await fsp.writeFile(join(evidence,'landing.txt'),text.slice(0,4000));
      expect(text.toLowerCase()).toContain('riksora');
      await landingContext.close();
    }
    step('cov_landing');
    await newMethod('Cov Free Style');
    await newMethod('Cov Protocol',{protocol:true,condition:'Trend aligned'});
    step('cov_methods');
    await newSession('Cov Free Style','Cov FS session');
    step('cov_session_free_style');
    // ---- nine timeframes: every one must load without error and keep the replay time
    phase='cov_timeframes';
    const select=page.getByLabel('Chart timeframe');
    const tfs=await select.locator('option').allTextContents();
    expect(tfs).toEqual(['1m','3m','5m','15m','30m','1h','2h','4h','D']);
    const timeBefore=await page.getByText(/Replay time \(UTC\)/).first().innerText();
    for(const tf of tfs){
      await select.selectOption(tf);
      await expect(select).toHaveValue(tf);
      await expect(select).toBeEnabled({timeout:95000});
      await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible();
    }
    expect(await page.getByText(/Replay time \(UTC\)/).first().innerText()).toBe(timeBefore);
    await select.selectOption('1m');await expect(select).toBeEnabled({timeout:95000});
    await shot('cov-timeframes');
    step('cov_nine_timeframes');
    // ---- indicators and drawing on the real chart
    phase='cov_indicators';
    await page.getByRole('button',{name:'Indicators',exact:false}).first().click();
    await page.getByLabel('Search indicators').fill('moving average');
    const addButtons=page.locator('.ind-group button:not([disabled])').filter({hasText:/moving average/i});
    await addButtons.first().click();
    await expect(page.getByRole('group',{name:/instance 1$/})).toBeVisible({timeout:30000});
    await shot('cov-indicator');
    await page.keyboard.press('Escape');
    step('cov_indicators');
    phase='cov_drawing';
    const tools=page.getByRole('navigation',{name:'Drawing tools'});
    await tools.locator('summary').first().click();
    await shot('cov-drawing-menu');
    const trend=page.getByRole('button',{name:/^Trend Line/i}).first();
    await trend.click();
    const canvasBox=await page.locator('.alpha-chart-workspace canvas').first().boundingBox();
    await page.mouse.move(canvasBox.x+canvasBox.width*0.30,canvasBox.y+canvasBox.height*0.55,{steps:5});
    await page.mouse.click(canvasBox.x+canvasBox.width*0.30,canvasBox.y+canvasBox.height*0.55);
    await page.waitForTimeout(600);
    await page.mouse.move(canvasBox.x+canvasBox.width*0.50,canvasBox.y+canvasBox.height*0.40,{steps:8});
    await page.mouse.click(canvasBox.x+canvasBox.width*0.50,canvasBox.y+canvasBox.height*0.40);
    await page.waitForTimeout(800);
    await page.getByRole('button',{name:'Drawing objects'}).click();
    await expect(page.getByRole('complementary',{name:'Drawing objects'})).toBeVisible();
    await expect(page.getByText('DRAWINGS (1)')).toBeVisible({timeout:20000});
    await shot('cov-drawing');
    step('cov_drawing');
    // ---- orders: helper
    const quote=async side=>Number(/([0-9.]+)$/.exec(await page.getByRole('button',{name:side==='LONG'?/Buy at Ask/:/Sell at Bid/}).getAttribute('aria-label'))[1]);
    const placeOrder=async({side,planned=false,type='MARKET',entry=null,sl=null,tp=null,pass=false})=>{
      const b=page.getByRole('button',{name:side==='LONG'?/Buy at Ask/:/Sell at Bid/});
      await b.click();
      const ticket=page.getByRole('dialog',{name:'Plan an order'});
      if(planned){
        await ticket.getByRole('radio',{name:'Plan · R:R'}).click().catch(()=>{});
        if(type!=='MARKET')await ticket.getByRole('radio',{name:type==='LIMIT'?'Limit':'Stop',exact:true}).click();
        if(entry!==null)await ticket.getByLabel('Entry').fill(String(entry));
        if(sl!==null)await ticket.getByLabel('Stop Loss').fill(String(sl));
        if(tp!==null)await ticket.locator('input[aria-label="Take Profit"]').fill(String(tp));
      }
      if(pass)for(const r of await ticket.getByRole('radio',{name:'Pass'}).all())await r.click().catch(()=>{});
      const reviewed=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/reviews'),{timeout:95000});
      await ticket.getByRole('button',{name:'Review order',exact:true}).click();
      const reviewStatus=(await reviewed).status();
      const review=page.locator('[role="dialog"][aria-label="Confirm reviewed order"]');
      await expect(review.getByRole('heading',{name:'Confirm reviewed order'})).toBeVisible({timeout:60000});
      await expect(review.getByRole('button',{name:'Confirm order',exact:true})).toBeEnabled();
      const confirmed=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/confirm'),{timeout:95000});
      await review.getByRole('button',{name:'Confirm order',exact:true}).click();
      const response=await confirmed;
      expect(reviewStatus).toBe(200);expect(response.status()).toBe(200);
      const receipt=await response.json();expect(receipt.durable).toBe(true);
      const dlg=page.getByRole('dialog',{name:'Confirm reviewed order'});
      if(await dlg.isVisible()){
        const reload=dlg.getByRole('button',{name:'Reload Session',exact:true});
        const r=await Promise.race([reload.waitFor({state:'visible',timeout:95000}).then(()=>'reload'),dlg.waitFor({state:'hidden',timeout:95000}).then(()=>'ok')]);
        if(r==='reload'){await reload.click();await expect(dlg).not.toBeVisible({timeout:95000});}
      }
      return receipt;
    };
    const rows=async tab=>{await terminal().getByRole('button',{name:tab,exact:true}).click();return terminal().getByRole('table',{name:tab}).locator('tr[data-order-id]');};
    const balance=async()=>(await terminal().locator('.alpha-account strong').first().innerText()).replace('$','');
    const jump=page.getByRole('button',{name:'Jump to Next Event',exact:true});
    // Jump to Next Event; false when nothing is live (the button is then disabled by design). Waits for the workspace to be idle first.
    const jumpOnce=async()=>{
      await expect(page.getByRole('button',{name:'Step ticks',exact:true})).toBeEnabled({timeout:95000});
      await page.waitForTimeout(400);
      if(!(await jump.isEnabled()))return false;
      const before=await revision();await jump.click();
      await expect.poll(revision,{timeout:95000}).toBeGreaterThan(before);
      await expect(page.getByRole('button',{name:'Step ticks',exact:true})).toBeEnabled({timeout:95000});
      return true;
    };
    // ---- Free Style Quick: market sell at Bid, filled by the next quote
    phase='cov_fs_quick';
    const quickReceipt=await placeOrder({side:'SHORT'});
    expect(quickReceipt.artifact).toBe('BTL-TICK-EXECUTION-RESULT-1');
    await stepOnce();
    await expect(await rows('Open positions')).toHaveCount(1,{timeout:60000});
    await shot('cov-fs-quick');
    step('cov_free_style_quick');
    // ---- Free Style Planned: pending LIMIT below the market, then Jump to Next Event until it fills and stops out
    phase='cov_fs_planned_limit';
    const ask0=await quote('LONG');
    const limitEntry=(ask0-3).toFixed(2),limitSl=(ask0-3.5).toFixed(2),limitTp=(ask0-1).toFixed(2);
    await placeOrder({side:'LONG',planned:true,type:'LIMIT',entry:limitEntry,sl:limitSl,tp:limitTp});
    await expect(await rows('Pending orders')).toHaveCount(1,{timeout:60000});
    await shot('cov-fs-pending-limit');
    step('cov_free_style_planned_limit');
    phase='cov_jump_resolution';
    for(let i=0;i<60;i++){
      if(await (await rows('Pending orders')).count()===0&&await (await rows('Closed trades')).count()>=1)break;
      if(!(await jumpOnce()))break;
    }
    await expect(await rows('Pending orders')).toHaveCount(0,{timeout:60000});
    await expect(await rows('Closed trades')).toHaveCount(1,{timeout:60000});
    const closedRow=(await rows('Closed trades')).first();
    expect(await closedRow.innerText()).toMatch(/LONG/);
    await shot('cov-fs-limit-resolved');
    step('cov_jump_resolution');
    // manual close of the quick short (Free Style only), executed by the next quote
    phase='cov_fs_manual_close';
    const openRows=await rows('Open positions');
    await expect(openRows).toHaveCount(1,{timeout:60000});
    await openRows.first().getByRole('button',{name:'Close position',exact:true}).click();
    await page.getByRole('button',{name:'Confirm action',exact:true}).click();
    await expect(page.getByRole('dialog',{name:'Confirm position action'})).toBeHidden({timeout:95000});
    await stepOnce();
    await expect(await rows('Closed trades')).toHaveCount(2,{timeout:95000});
    step('cov_free_style_manual_close');
    // ---- Journal, Statistics and Export must agree with each other and with the balance shown
    phase='cov_statistics';
    const balanceNow=Number(await balance());
    await terminal().getByRole('button',{name:'Analysis',exact:true}).click();
    const analysisText=await terminal().locator('.alpha-analysis:not(.alpha-journal)').innerText();
    expect(analysisText).toMatch(/Completed trades\s*2/);
    await shot('cov-statistics');
    await terminal().getByRole('button',{name:'Journal',exact:true}).click();
    await expect(terminal().locator('.alpha-journal article')).toHaveCount(2,{timeout:60000});
    step('cov_journal_statistics');
    phase='cov_export';
    const [dlCsv]=await Promise.all([page.waitForEvent('download',{timeout:60000}),page.getByRole('button',{name:'Export committed trades CSV'}).click()]);
    await dlCsv.saveAs(join(evidence,'cov-trades.csv'));
    const csvLines=(await fsp.readFile(join(evidence,'cov-trades.csv'),'utf8')).trim().split('\r\n').map(l=>l.split(','));
    expect(csvLines.length).toBe(3);
    const ci=name=>csvLines[0].indexOf(name);
    const netSum=csvLines.slice(1).reduce((sum,row)=>sum+Number(row[ci('net')]),0);
    expect(Math.abs(balanceNow-10000-netSum)).toBeLessThan(1e-6);
    expect(csvLines.slice(1).every(row=>row[ci('status')]==='CLOSED')).toBe(true);
    expect(csvLines.slice(1).map(row=>row[ci('side')]).sort()).toEqual(['LONG','SHORT']);
    const [dlPdf]=await Promise.all([page.waitForEvent('download',{timeout:60000}),page.getByRole('button',{name:'Export PDF report'}).click()]);
    await dlPdf.saveAs(join(evidence,'cov-report.pdf'));
    expect((await fsp.readFile(join(evidence,'cov-report.pdf'))).subarray(0,5).toString()).toBe('%PDF-');
    await fsp.writeFile(join(evidence,'cov-expect.json'),JSON.stringify({balance:String(balanceNow),netSum:String(netSum),trades:2}));
    step('cov_export');
    // ---- Protocol: pending LIMIT and STOP, cancel one, Jump to the locked exit, no manual close
    phase='cov_protocol';
    await page.getByRole('link',{name:/^Back to /}).click();
    await newSession('Cov Protocol','Cov Protocol session');
    const placeProtocol=async({side,type,entry,sl})=>{
      const b=page.getByRole('button',{name:side==='LONG'?/Buy at Ask/:/Sell at Bid/});
      await b.click();
      const ticket=page.getByRole('dialog',{name:'Plan an order'});
      await ticket.getByRole('radio',{name:type==='LIMIT'?'Limit':'Stop',exact:true}).click();
      await ticket.getByLabel('Entry').fill(String(entry));await ticket.getByLabel('Stop Loss').fill(String(sl));
      await expect(ticket.getByText(/locked RR/)).toBeVisible();
      const reviewed=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/reviews'),{timeout:95000});
      await ticket.getByRole('button',{name:'Review order',exact:true}).click();
      expect((await reviewed).status()).toBe(200);
      const review=page.locator('[role="dialog"][aria-label="Confirm reviewed order"]');
      await expect(review.getByRole('button',{name:'Confirm order',exact:true})).toBeEnabled({timeout:60000});
      const confirmed=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.endsWith('/confirm'),{timeout:95000});
      await review.getByRole('button',{name:'Confirm order',exact:true}).click();
      expect((await confirmed).status()).toBe(200);
      const dlg=page.getByRole('dialog',{name:'Confirm reviewed order'});
      if(await dlg.isVisible()){
        const reload=dlg.getByRole('button',{name:'Reload Session',exact:true});
        const r=await Promise.race([reload.waitFor({state:'visible',timeout:95000}).then(()=>'reload'),dlg.waitFor({state:'hidden',timeout:95000}).then(()=>'ok')]);
        if(r==='reload'){await reload.click();await expect(dlg).not.toBeVisible({timeout:95000});}
      }
    };
    const pAsk=await quote('LONG'),pBid=await quote('SHORT');
    await placeProtocol({side:'LONG',type:'LIMIT',entry:(pAsk-0.5).toFixed(2),sl:(pAsk-1.0).toFixed(2)});
    await placeProtocol({side:'SHORT',type:'STOP',entry:(pBid-2).toFixed(2),sl:(pBid-1).toFixed(2)});
    await expect(await rows('Pending orders')).toHaveCount(2,{timeout:60000});
    await shot('cov-protocol-pending');
    step('cov_protocol_pending_limit_stop');
    phase='cov_protocol_cancel';
    await (await rows('Pending orders')).last().getByRole('button',{name:'Cancel pending',exact:true}).click();
    await page.getByRole('button',{name:'Confirm action',exact:true}).click();
    await expect(page.getByRole('dialog',{name:'Confirm position action'})).toBeHidden({timeout:95000});
    await expect(await rows('Pending orders')).toHaveCount(1,{timeout:60000});
    step('cov_protocol_cancel');
    phase='cov_protocol_jump';
    for(let i=0;i<60;i++){
      if(await (await rows('Open positions')).count()>=1){
        const closeButton=(await rows('Open positions')).first().getByRole('button',{name:'Close position',exact:true});
        await expect(closeButton).toBeDisabled();                         // Protocol: no manual close
      }
      if(!(await jumpOnce()))break;
    }
    await expect(await rows('Closed trades')).toHaveCount(1,{timeout:60000});
    await shot('cov-protocol-resolved');
    step('cov_protocol_jump_locked_exit');
    // ---- Position planner tool (Long Position) from the drawing menu
    phase='cov_position_planner';
    await page.locator('details.alpha-drawing-group').filter({hasText:/Long Position/}).locator('summary').click();
    await page.getByRole('button',{name:/Long Position/i}).first().click();
    const box2=await page.locator('.alpha-chart-workspace canvas').first().boundingBox();
    await page.mouse.click(box2.x+box2.width*0.45,box2.y+box2.height*0.5);
    await page.waitForTimeout(800);
    if(!(await page.getByRole('complementary',{name:'Drawing objects'}).isVisible()))await page.getByRole('button',{name:'Drawing objects'}).click();
    await shot('cov-position-planner');
    await expect(page.getByText(/position plans \(1\)/i)).toBeVisible({timeout:20000});
    step('cov_position_planner');
    // ---- IDOR: a second real account with a valid token attacks the first account's workspace and Session by id
    phase='cov_idor';
    {
      const base=url.origin;
      const post=(path,token,data)=>context.request.post(base+path,{headers:token?{Authorization:'Bearer '+token}:{},data,maxRedirects:0,failOnStatusCode:false});
      const get=(path,token)=>context.request.get(base+path,{headers:token?{Authorization:'Bearer '+token}:{},maxRedirects:0,failOnStatusCode:false});
      let regs=await post('/api/v1/auth/register',null,{email:config.email2,password:config.password});
      expect(regs.status()).toBe(201);
      process.stdout.write(JSON.stringify({need:'verification',email:config.email2})+'\n');
      const token2=(await read()).token;
      expect((await post('/api/v1/auth/verify',null,{token:token2})).status()).toBe(200);
      const login=await context.request.post(base+'/api/v1/auth/login',{form:{username:config.email2,password:config.password},failOnStatusCode:false});
      expect(login.status()).toBe(200);
      const tokenB=(await login.json()).access_token;
      const wsB=(await (await post('/api/v1/workspaces',tokenB,{name:'Attacker workspace'})).json()).id;
      const A=`/api/v1/workspaces/${seen.ws}/research`,sid=encodeURIComponent(seen.sid),B=`/api/v1/workspaces/${wsB}/research`;
      const attacks=[
        ['GET',`/api/v1/workspaces/${seen.ws}`],['GET',`/api/v1/workspaces/${seen.ws}/capabilities`],['GET',`${A}/sessions`],['GET',`${A}/sessions?trashed=true`],
        ['GET',`${A}/sessions/${sid}`],['GET',`${A}/sessions/${sid}/journal/pages`],['GET',`${A}/sessions/${sid}/export?format=csv`],['GET',`${A}/sessions/${sid}/export?format=pdf`],
        ['GET',`${A}/sessions/${sid}/chart-bars?timeframe=1m`],['GET',`${A}/sessions/${sid}/analytics/pages`],['GET',`${A}/methods`],['GET',`${A}/entitlements`],
        ['POST',`${A}/sessions/${sid}/trash`],['POST',`${A}/sessions/${sid}/restore`],['POST',`${A}/sessions/${sid}/commands`],
        ['GET',`${B}/sessions/${sid}`],['GET',`${B}/sessions/${sid}/export?format=csv`],['GET',`${B}/sessions/${sid}/journal/pages`],['POST',`${B}/sessions/${sid}/trash`],
      ];
      const outcome=[];
      for(const [method,path] of attacks){
        const response=method==='GET'?await get(path,tokenB):await post(path,tokenB,{});
        const body=await response.text();
        outcome.push({method,path:path.replace(/[0-9a-f-]{36}/g,'{id}').replace(/session%3A[^/?]+/,'{sid}'),status:response.status()});
        expect([401,403,404,422]).toContain(response.status());
        expect(body).not.toContain('Cov Protocol session');expect(body).not.toContain('Cov FS session');expect(body).not.toContain('order:');
      }
      const anonymous=await get(`${A}/sessions/${sid}/export?format=csv`,null);expect(anonymous.status()).toBe(401);
      // the victim's data is unchanged after the attacks
      await terminal().getByRole('button',{name:'Closed trades',exact:true}).click();
      await expect(terminal().getByRole('table',{name:'Closed trades'}).locator('tr[data-order-id]')).toHaveCount(1);
      await fsp.writeFile(join(evidence,'cov-idor.json'),JSON.stringify({attacks:outcome,anonymousExport:401},null,1));
    }
    step('cov_idor');
    }
    if(process.env.RIKSORA_QA_E2E_ENTITLEMENT==='1')try{
      const hook=async(need,extra={})=>{process.stdout.write(JSON.stringify({need,...extra})+'\n');return await read();};
      const nextMonthText=()=>{const n=new Date();return new Date(Date.UTC(n.getUTCFullYear(),n.getUTCMonth()+1,1)).toLocaleString('en',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC',timeZoneName:'short'});};
      const tryCreate=async(methodName,name)=>{
        await page.getByRole('button',{name:'New Session',exact:true}).or(page.getByRole('link',{name:/New Session/})).first().click();
        await page.locator('.rk-wizard .rk-combo button.rk-combo-trigger').click();
        await page.getByRole('option',{name:new RegExp(methodName)}).click();
        for(let i=0;i<3;i++)await page.getByRole('button',{name:'Continue',exact:true}).click();
        await page.getByLabel('Session name').fill(name);
        await page.getByRole('button',{name:'Continue',exact:true}).click();
        await page.getByRole('button',{name:'Create Session',exact:true}).click();
        const created=page.getByRole('region',{name:'Tick replay workspace'});
        const alert=page.getByRole('alert').first();
        const outcome=await Promise.race([created.waitFor({state:'visible',timeout:95000}).then(()=> 'created'),alert.waitFor({state:'visible',timeout:95000}).then(()=> 'refused')]);
        if(outcome==='created')return {outcome};
        return {outcome,text:await page.locator('body').innerText()};
      };
      expect((await hook('qa_enforced')).enforced).toBe(true);step('ent_enforced');
      await newMethod('Ent Free Style');
      await newSession('Ent Free Style','Ent session 1');
      step('ent_first_session');
      await page.getByRole('link',{name:/^Back to /}).click();
      const refused=await tryCreate('Ent Free Style','Ent session 2');
      expect(refused.outcome).toBe('refused');
      expect(refused.text).toContain('one new Session per calendar month (UTC)');
      expect(refused.text).toContain(nextMonthText());
      await shot('ent-refused');
      step('ent_second_refused');
      phase='ent_logout';
      // logout / login: the same state and the same refusal; the first Session is still there
      await page.keyboard.press('Escape');
      await mainNav('Sessions').click();
      await page.getByRole('navigation',{name:'Account and help'}).getByRole('link',{name:'Account',exact:true}).click();
      await page.getByRole('button',{name:'Sign out',exact:true}).click();
      await expect(page.getByRole('tab',{name:'Sign in',exact:true})).toBeVisible();
      await page.getByLabel('Email',{exact:true}).fill(config.email);await page.getByLabel('Password',{exact:true}).fill(config.password);
      await page.getByRole('button',{name:'Sign in',exact:true}).click();
      await page.getByRole('button',{name:/Synthetic browser acceptance/}).click();
      await mainNav('Sessions').click();
      await expect(page.getByRole('link',{name:'Ent session 1'}).first()).toBeVisible({timeout:60000});
      await expect(page.getByRole('link',{name:'Ent session 2'})).toHaveCount(0);
      const again=await tryCreate('Ent Free Style','Ent session 2');
      expect(again.outcome).toBe('refused');expect(again.text).toContain(nextMonthText());
      step('ent_logout_login_consistent');
      phase='ent_pro';
      // Pro (a PAID, unexpired order on the server) unlocks a second Session immediately
      expect((await hook('qa_grant_pro',{email:config.email})).ok).toBe(true);
      await mainNav('Sessions').click();
      const pro=await tryCreate('Ent Free Style','Ent session 2');
      expect(pro.outcome).toBe('created');
      step('ent_pro_unlocks');
      phase='ent_refund';
      // refund: Pro is revoked at once, the earlier Sessions and their ledgers stay
      expect((await hook('qa_reverse_pro',{email:config.email})).ok).toBe(true);
      await page.getByRole('link',{name:/^Back to /}).click();
      const third=await tryCreate('Ent Free Style','Ent session 3');
      expect(third.outcome).toBe('refused');expect(third.text).toContain('one new Session per calendar month (UTC)');
      await page.keyboard.press('Escape');
      await mainNav('Sessions').click();
      await expect(page.getByRole('link',{name:'Ent session 1'}).first()).toBeVisible();
      await expect(page.getByRole('link',{name:'Ent session 2'}).first()).toBeVisible();
      await page.getByRole('button',{name:/Continue replay|Open replay/}).first().click();
      await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible({timeout:95000});
      step('ent_refund_downgrade');
      phase='ent_utc';
      // UTC turnover: earlier periods stop counting, a new Session is allowed again (and takes one token)
      expect((await hook('qa_turn_utc',{email:config.email})).ok).toBe(true);
      await page.getByRole('link',{name:/^Back to /}).click();
      const reset=await tryCreate('Ent Free Style','Ent session 3');
      expect(reset.outcome).toBe('created');
      await page.getByRole('link',{name:/^Back to /}).click();
      const afterReset=await tryCreate('Ent Free Style','Ent session 4');
      expect(afterReset.outcome).toBe('refused');
      step('ent_utc_turnover');
      phase='ent_idor';
      // IDOR on the quota: a second account cannot reserve or consume anything in the first account's workspace
      const base=url.origin;
      const post=(path,token,data)=>context.request.post(base+path,{headers:token?{Authorization:'Bearer '+token}:{},data,maxRedirects:0,failOnStatusCode:false});
      expect((await post('/api/v1/auth/register',null,{email:config.email2,password:config.password})).status()).toBe(201);
      process.stdout.write(JSON.stringify({need:'verification',email:config.email2})+'\n');
      expect((await post('/api/v1/auth/verify',null,{token:(await read()).token})).status()).toBe(200);
      const login2=await context.request.post(base+'/api/v1/auth/login',{form:{username:config.email2,password:config.password},failOnStatusCode:false});
      const tokenB=(await login2.json()).access_token;
      const before=(await hook('qa_claims',{email:config.email})).active;
      const attempt=await post(`/api/v1/workspaces/${seen.ws}/research/sessions`,tokenB,{id:'session:attack',name:'attack',methodId:'method:x',initialBalance:'10000',startPeriod:'2020-01'});
      expect([401,403,404,422]).toContain(attempt.status());
      expect((await attempt.text())).not.toContain('SESSION_MONTH_LIMIT');
      expect((await hook('qa_claims',{email:config.email})).active).toBe(before);
      expect((await hook('qa_claims',{email:config.email2})).active).toBe(0);
      const ent2=await context.request.get(`${base}/api/v1/workspaces/${seen.ws}/research/entitlements`,{headers:{Authorization:'Bearer '+tokenB},failOnStatusCode:false});
      expect([403,404]).toContain(ent2.status());
      step('ent_idor_no_claims');
    }catch(error){await page.screenshot({path:join(evidence,'ent-failure.png')}).catch(()=>{});await fsp.writeFile(join(evidence,'ent-failure.txt'),String(error)+'\n'+await page.locator('body').innerText().catch(()=>'')).catch(()=>{});throw error;}
    process.stdout.write(JSON.stringify({complete:true,browserVersion:browser.version(),transientBusyCount:0,apiResponseCount,pageErrorCount:errors.length,failedRequests:requestFailures.length,steps:completedSteps})+'\n');
    await context.close();await browser.close();process.exit(0);
  }
  phase='method_create';await page.getByRole('link',{name:'Create your first Method'}).click();
  await page.getByLabel('Method name').fill('Synthetic browser method');
  await page.getByRole('button',{name:'Save Method',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Synthetic browser method'})).toBeVisible();step('method');
  phase='session_wizard_open';await page.getByRole('button',{name:'New Session',exact:true}).or(page.getByRole('link',{name:/New Session/})).first().click();
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
  await ticket.getByRole('button',{name:'Add stop & target',exact:true}).click();
  const entry=Number(await ticket.getByLabel('Entry').inputValue());
  expect(Number.isFinite(entry)).toBeTruthy();
  // Keep the stop/target close to the current synthetic quote so the real tick
  // engine reaches a committed exit boundary in this bounded browser journey.
  await ticket.getByLabel('Stop Loss').fill((entry-1.00).toFixed(2));
  await ticket.locator('input[aria-label="Take Profit"]').fill((entry+2.00).toFixed(2));
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
    onResponse:row=>{
      const event={method:'POST',path:retryPath,status:row.status,code:row.code,
        rows:null,journalPage:null,state:null,durationMs:row.durationMs};
      apiResponseCount++;apiTrace.push(event);
      process.stdout.write(JSON.stringify({apiEvent:event})+'\n');
    },
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
  phase='jump_to_entry_event';
  const beforeEntryRevision=Number(await terminal.getAttribute('data-revision'));
  expect(Number.isSafeInteger(beforeEntryRevision)).toBeTruthy();
  const jumpButton=page.getByRole('button',{name:'Jump to Next Event',exact:true});
  await expect(jumpButton).toBeEnabled({timeout:95000});
  await jumpButton.click({timeout:95000});
  await expect.poll(async()=>Number(await terminal.getAttribute('data-revision')),{timeout:95000}).toBeGreaterThan(beforeEntryRevision);
  await expect(jumpButton).toBeEnabled({timeout:95000});
  phase='jump_to_exit_event';
  const beforeExitRevision=Number(await terminal.getAttribute('data-revision'));
  expect(Number.isSafeInteger(beforeExitRevision)).toBeTruthy();
  await jumpButton.click({timeout:95000});
  await expect.poll(async()=>Number(await terminal.getAttribute('data-revision')),{timeout:95000}).toBeGreaterThan(beforeExitRevision);
  phase='trade_close_closed_trades_tab';
  await terminal.getByRole('button',{name:'Closed trades',exact:true}).click();
  phase='trade_close_committed_row';
  await expect(terminal.getByRole('table',{name:'Closed trades'}).locator('tr[data-order-id]')).toHaveCount(1,{timeout:95000});
  await expect(page.locator('.alpha-balance-pill')).not.toHaveAttribute('aria-label','Saved balance 10000 USD');step('jump_entry_exit_journal_analytics');
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
  const busyResponses=apiTrace.filter(entry=>(entry.status===429&&['RESEARCH_BUSY','QUEUE_CAPACITY'].includes(entry.code))||
    (entry.status===503&&entry.code==='SERVICE_BUSY'));
  const unrecoveredBusy=busyResponses.filter(entry=>{
    const index=apiTrace.indexOf(entry);
    return !apiTrace.slice(index+1).some(next=>next.method===entry.method&&next.path===entry.path&&next.status>=200&&next.status<400);
  });
  expect(apiTrace.filter(entry=>(entry.status===429&&!['RESEARCH_BUSY','QUEUE_CAPACITY'].includes(entry.code))||
    (entry.status===503&&entry.code!=='SERVICE_BUSY')||entry.status>=500&&entry.status!==503)).toEqual([]);
  expect(unrecoveredBusy).toEqual([]);
  expect(apiTrace.filter(entry=>entry.jumpStatus==='EVENT_FOUND').length).toBeGreaterThanOrEqual(2);
  const committedJournal=apiTrace.filter(entry=>entry.path.endsWith('/journal/pages')&&entry.status===200).at(-1);
  expect(committedJournal?.journalPage?.firstOrderStatuses).toEqual(['CLOSED']);
  expect(errors).toEqual([]);step('logout_login_resume');
  if(process.env.RIKSORA_QA_E2E_EXTRA==='1'){
    const fsp=await import('node:fs/promises');
    // Exports: the downloaded files must carry the committed numbers, not just exist.
    phase='export_csv';
    await resumedTerminal.getByRole('button',{name:'Journal',exact:true}).click();
    const csvButton=page.getByRole('button',{name:'Export committed trades CSV'});
    await expect(csvButton).toBeEnabled({timeout:95000});
    const [csvDownload]=await Promise.all([page.waitForEvent('download',{timeout:60000}),csvButton.click()]);
    await csvDownload.saveAs(join(evidence,'trades.csv'));
    const csvRows=(await fsp.readFile(join(evidence,'trades.csv'),'utf8')).trim().split('\r\n').map(line=>line.split(','));
    expect(csvRows[0].slice(0,5)).toEqual(['sessionId','datasetId','datasetVersion','ledgerRevision','orderId']);
    expect(csvRows.length).toBe(2);
    const col=name=>csvRows[1][csvRows[0].indexOf(name)];
    expect(col('status')).toBe('CLOSED');expect(Number(col('entryPrice'))).toBeGreaterThan(0);expect(Number(col('exitPrice'))).toBeGreaterThan(0);
    const pill=await page.locator('.alpha-balance-pill').getAttribute('aria-label');
    const shown=Number(/Saved balance ([-0-9.]+)/.exec(pill)?.[1]);
    expect(Math.abs(shown-10000-Number(col('netCashChange')))).toBeLessThan(1e-6);   // exported net cash change equals the balance the UI shows
    step('export_csv_ledger');
    phase='export_pdf';
    const [pdfDownload]=await Promise.all([page.waitForEvent('download',{timeout:60000}),page.getByRole('button',{name:'Export PDF report'}).click()]);
    await pdfDownload.saveAs(join(evidence,'report.pdf'));
    const pdfBytes=await fsp.readFile(join(evidence,'report.pdf'));
    expect(pdfBytes.subarray(0,5).toString()).toBe('%PDF-');expect(pdfBytes.length).toBeGreaterThan(1500);
    await fsp.writeFile(join(evidence,'report.expect.json'),JSON.stringify({netCashChange:col('netCashChange'),balance:String(shown)}));
    step('export_pdf_report');
    // Trash and Restore through the product UI; the Session must disappear, come back, and keep its committed ledger.
    phase='trash_restore';
    await page.getByRole('link',{name:'Back to Synthetic browser method',exact:true}).click();
    await page.getByRole('navigation',{name:'Main'}).getByRole('link',{name:'Sessions',exact:true}).click();
    await page.getByRole('link',{name:'Synthetic browser session'}).first().click();
    await page.getByRole('button',{name:'Move to Trash',exact:true}).click();
    await expect(page.getByText('No Sessions yet')).toBeVisible({timeout:60000});
    await page.getByText('Trash',{exact:true}).click();
    await page.getByRole('button',{name:/Restore Synthetic browser session/}).click();
    await expect(page.getByRole('link',{name:'Synthetic browser session'}).first()).toBeVisible({timeout:60000});
    step('trash_restore');
    // Mobile viewport: no horizontal page scroll on the main screens and the replay workspace still opens.
    phase='mobile_viewport';
    await page.setViewportSize({width:390,height:844});
    // On a phone the main navigation is the bottom tab bar (Methods, Sessions, Replay, Analysis, Account).
    for(const screen of ['Methods','Sessions','Analysis']){
      await page.getByRole('link',{name:screen,exact:true}).last().click();
      await page.waitForTimeout(800);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
    }
    await page.getByRole('link',{name:'Sessions',exact:true}).last().click();
    await page.getByRole('button',{name:/Continue replay|Open replay/}).first().click();
    await expect(page.getByRole('region',{name:'Tick replay workspace'})).toBeVisible({timeout:95000});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
    await fsp.copyFile(join(evidence,'trades.csv'),join(evidence,'trades.final.csv')).catch(()=>{});
    await page.screenshot({path:join(evidence,'mobile-replay.png'),fullPage:false});
    step('mobile_viewport');
  }
  process.stdout.write(JSON.stringify({complete:true,browserVersion:browser.version(),
    transientBusyCount:busyResponses.length,apiResponseCount,pageErrorCount:errors.length,
    failedRequests:requestFailures.length,
    steps:completedSteps})+'\n');
}catch(error){
  const failureMessage=String(error?.message||error).split('\n')[0]
    .replace(/\b[0-9a-f]{8}-[0-9a-f-]{27,}\b/gi,'{id}')
    .replace(/\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b/g,'{email}')
    .slice(0,300);
  process.stderr.write(`QA_ORIGINAL_FAILURE phase=${phase} type=${error?.name||'Error'} message=${failureMessage}\n`);
  // Report the original failure before any best-effort browser inspection. In
  // cohort mode the parent must preserve this cause even if the browser is
  // already disconnecting and screenshot/DOM diagnostics cannot complete.
  process.stdout.write(JSON.stringify({failurePhase:phase,failureType:error?.name||'Error',screenState:[],consoleErrors,
    pageErrorCount:errors.length,browserDiagnostics:{routeScreen:null,journalLists:0,journalRows:0,journalError:'UNAVAILABLE'},
    browserFailureMessage:failureMessage,
    requestFailures})+'\n');
  await Promise.allSettled(apiBodyReads);
  await Promise.race([page.screenshot({path:join(evidence,'failure.png'),fullPage:true}),
    new Promise(resolve=>setTimeout(resolve,1500))]);
  const body=await Promise.race([page.locator('body').innerText({timeout:1000}).catch(()=>''),
    new Promise(resolve=>setTimeout(()=>resolve(''),1100))]);
  await import('node:fs/promises').then(fs=>fs.writeFile(join(evidence,'failure.txt'),String(error)+'\n'+body));
  throw error;
}finally{await context.close();await browser.close();}
