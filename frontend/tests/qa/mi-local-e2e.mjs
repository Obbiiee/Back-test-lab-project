import {createRequire} from 'node:module';
import {readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import assert from 'node:assert/strict';

const require=createRequire(new URL('../browser-tools/package.json',import.meta.url));
const {chromium}=require('playwright');
const config=JSON.parse(await readFile(join(process.env.MI_BROWSER_QA,'browser.json'),'utf-8'));
assert.equal(new URL(config.url).hostname,'127.0.0.1');
const browser=await chromium.launch({
  executablePath:process.env.MI_CHROMIUM,
  env:{...process.env,LD_LIBRARY_PATH:join(process.env.HOME,'tools/chromelibs/lib'),
       FONTCONFIG_FILE:join(process.env.HOME,'tools/fonts.conf')},
  args:['--no-sandbox'],
});
function latency(samples){
  const sorted=[...samples].sort((a,b)=>a-b);
  assert.ok(sorted.length>0);
  return {requests:sorted.length,...Object.fromEntries([50,95,99].map(percentile=>
    ['p'+percentile+'Ms',Math.round(sorted[Math.ceil(sorted.length*percentile/100)-1])]))};
}
try{
  for(const account of config.accounts){
    const mobile=account.viewport==='mobile';
    const context=await browser.newContext({ignoreHTTPSErrors:true,
      viewport:mobile?{width:390,height:844}:{width:1280,height:900},isMobile:mobile,hasTouch:mobile});
    try{
      const page=await context.newPage();
      const errors=[];
      const jobs=[];
      const interactive=[];
      const asyncJobs=[];
      context.on('requestfinished',request=>{
        const pathname=new URL(request.url()).pathname;
        const elapsed=request.timing().responseEnd;
        if(elapsed<0)return;
        if(/\/jobs\/[0-9a-f-]+$|\/mi\/sessions\/[^/]+\/commands$/.test(pathname))asyncJobs.push(elapsed);
        else if(pathname.includes('/mi/'))interactive.push(elapsed);
      });
      page.on('response',async response=>{
        if(response.ok()&&/\/jobs\/[0-9a-f-]+$/.test(response.url())){
          const job=await response.json().catch(()=>null);
          if(job)jobs.push(job);
        }
      });
      page.on('pageerror',error=>errors.push(error.message));
      const login=async (tab=page)=>{
        await tab.getByLabel('Email').fill(account.email);
        await tab.getByLabel('Password',{exact:true}).fill(account.password);
        await tab.getByRole('button',{name:'Sign in',exact:true}).click();
        await tab.getByRole('button',{name:/Isolated MI QA/}).click();
      };
      const revision=async (number,timeout=15000)=>page.getByText(new RegExp('Revision '+number+'$')).waitFor({timeout});
      const replay=async (target,number,label='Replay',timeout=15000)=>{
        await page.getByLabel('Replay target (ns UTC)').fill(target);
        await page.getByRole('button',{name:label,exact:true}).click();
        await revision(number,timeout);
      };
      await page.goto(config.url+'/?page=account&screen=sessions', {waitUntil:'domcontentloaded'});
      await login();
      await page.getByRole('link',{name:'Multi-instrument QA'}).click();
      await page.getByRole('heading',{name:'Multi-instrument QA'}).waitFor();
      await page.getByLabel('EURUSD',{exact:true}).check();
      await page.getByLabel('GBPUSD',{exact:true}).check();
      await page.getByLabel('Free style QA',{exact:true}).check();
      await page.getByLabel('Second method QA',{exact:true}).check();
      if(mobile)await page.getByLabel('Protocol QA',{exact:true}).check();
      await page.getByRole('button',{name:'Create MI Session'}).click();
      await revision(0);
      await replay('100',1);
      await page.getByRole('img',{name:'EURUSD revealed bid chart'}).waitFor();
      await page.getByRole('button',{name:'Review order'}).click();
      await page.getByRole('button',{name:'Confirm order'}).click();
      await revision(2);
      const method=page.getByLabel('Active Method');
      await method.selectOption({label:'Second method QA'});
      await revision(3);
      await page.getByLabel('Active pair').selectOption('GBPUSD');
      await page.getByRole('img',{name:'GBPUSD revealed bid chart'}).waitFor();
      await page.getByRole('button',{name:'Review order'}).click();
      await page.getByRole('button',{name:'Confirm order'}).click();
      await revision(4);
      await replay('150',5,'Jump');
      await page.getByLabel('Active pair').selectOption('EURUSD');
      await page.getByRole('img',{name:'EURUSD revealed bid chart'}).waitFor();
      await page.getByText(/GBPUSD · ACTIVE/).waitFor();
      await page.getByRole('button',{name:'Close EURUSD'}).click();
      await revision(6);
      if(!mobile)await writeFile(join(process.env.MI_BROWSER_QA,'crash-on-exit'),'armed');
      await replay('140',7,'Replay',55000);
      if(!mobile){
        const ids=JSON.parse(await readFile(join(process.env.MI_BROWSER_QA,'crash-proof.json'),'utf-8'));
        const recovered=jobs.find(job=>job.state==='SUCCEEDED'&&job.attempt===2&&job.result?.revision===7);
        assert.deepEqual(recovered?.result.events.filter(event=>event.kind==='EXIT_FILL').map(event=>event.eventId),ids);
      }
      if(mobile){
        await page.getByLabel('Active pair').selectOption('GBPUSD');
        await page.getByRole('img',{name:'GBPUSD revealed bid chart'}).waitFor();
        await page.getByLabel('Order type').selectOption('LIMIT');
        await page.getByLabel('Entry',{exact:true}).fill('1');
        await page.getByLabel('Stop Loss').fill('0.9');
        await page.getByLabel('Take Profit').fill('1.4');
        await page.getByRole('button',{name:'Review order'}).click();
        await page.getByRole('button',{name:'Confirm order'}).click();
        await revision(8);
        await page.route('**/mi/sessions/*/commands',route=>route.abort('connectionfailed'),{times:1});
        await page.getByRole('button',{name:'Cancel GBPUSD'}).click();
        await page.getByRole('button',{name:'Reconcile pending command'}).waitFor();
        await page.reload({waitUntil:'domcontentloaded'});
        await login();
        await revision(8);
        await page.getByRole('button',{name:'Reconcile pending command'}).click();
        await revision(9);
        await page.getByLabel('Active Method').selectOption({label:'Protocol QA'});
        await revision(10);
        await page.getByLabel('Active pair').selectOption('GBPUSD');
        await page.getByRole('img',{name:'GBPUSD revealed bid chart'}).waitFor();
        await page.getByLabel('Order type').selectOption('LIMIT');
        await page.getByLabel('Entry',{exact:true}).fill('1');
        await page.getByLabel('Stop Loss').fill('0.99');
        await page.getByLabel('Take Profit').fill('1.02');
        await page.getByLabel('Quantity').fill('0.09');
        await page.getByLabel('Setup valid').check();
        await page.getByRole('button',{name:'Review order'}).click();
        await page.getByRole('button',{name:'Confirm order'}).click();
        await revision(11);
        await page.getByRole('button',{name:'Cancel GBPUSD'}).waitFor();
        const tab=await context.newPage();
        await tab.goto(page.url(),{waitUntil:'domcontentloaded'});
        await login(tab);
        await tab.getByText(/Revision 11$/).waitFor({timeout:15000});
        await tab.getByRole('button',{name:'Cancel GBPUSD'}).waitFor();
        await tab.close();
      }
      await page.getByRole('button',{name:'Journal',exact:true}).click();
      await page.getByText(/EURUSD · method:.* · CLOSED/).waitFor();
      await page.getByRole('button',{name:'Analytics',exact:true}).click();
      await page.getByText(/Closed trades 1 · Net/).waitFor();
      const saved=page.url();
      await page.getByRole('link',{name:'Account',exact:true}).last().click();
      await page.getByRole('button',{name:'Sign out',exact:true}).click();
      await page.goto(saved,{waitUntil:'domcontentloaded'});
      await login();
      await revision(mobile?11:7);
      await page.getByRole('button',{name:'Close GBPUSD'}).waitFor();
      if(mobile){
        await replay(String(BigInt(config.boundaries.feb)+10n),12);
        await replay(String(BigInt(config.boundaries.dec)+10n),13);
        await replay(String(BigInt(config.boundaries.jan)+10n),14);
        await page.getByText(/GBPUSD · PENDING/).waitFor();
      }else{
        await replay(String(BigInt(config.boundaries.feb)-1n),8);
        await page.getByLabel('Replay target (ns UTC)').fill(String(BigInt(config.boundaries.feb)+10n));
        await page.getByRole('button',{name:'Replay',exact:true}).click();
        await page.getByRole('alert').filter({hasText:/Free window has ended/}).waitFor();
        await revision(8);
        await page.getByRole('button',{name:'Close GBPUSD'}).click();
        await revision(9);
        await replay(String(BigInt(config.boundaries.feb)+10n),10,'Jump');
        await page.getByText(/Market quotes outside your Free window are hidden/).waitFor();
        await page.getByRole('button',{name:'Analytics',exact:true}).click();
        await page.getByText(/Closed trades 2 · Net/).waitFor();
      }
      assert.deepEqual(errors,[]);
      console.log(JSON.stringify({viewport:account.viewport,completed:true,revision:mobile?14:10,closedTrades:mobile?1:2,nativeCrashRecovered:!mobile,
        windowCase:mobile?'PRO_DECEMBER_JANUARY':'FREE_BOUNDARY_AND_CLOSE',
        latency:{interactive:latency(interactive),asyncJobs:latency(asyncJobs)}}));
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}
