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
try{
  for(const account of config.accounts){
    const mobile=account.viewport==='mobile';
    const context=await browser.newContext({ignoreHTTPSErrors:true,
      viewport:mobile?{width:390,height:844}:{width:1280,height:900},isMobile:mobile,hasTouch:mobile});
    try{
      const page=await context.newPage();
      const errors=[];
      const jobs=[];
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
      assert.deepEqual(errors,[]);
      console.log(JSON.stringify({viewport:account.viewport,completed:true,revision:mobile?11:7,closedTrades:1,nativeCrashRecovered:!mobile}));
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}
