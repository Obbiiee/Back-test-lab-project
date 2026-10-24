import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {confirmation,executionCommand,accessMessage,betaNotice,checkoutAddress,billingDuration,billingExpiry,methodFromForm,orderFromForm,createReplayLoop,startPeriods,periodLabel} from '../src/beta/betaWorkspace.js';
import {createBetaClient} from '../src/beta/betaClient.js';
const view={artifact:'BTL-RESEARCH-SESSION-VIEW-2',metadata:{id:'session:qa'},state:{revision:7,balance:'9007199254740993.03'}};
const payload={targetNs:'1577836800000000000'};
const command=executionCommand(view,'ADVANCE',payload);
assert.equal(command.artifact,'BTL-TICK-EXECUTION-COMMAND-2');assert.equal(command.expectedRevision,7);assert.deepEqual(command.payload,payload);
assert.notEqual(executionCommand(view,'ADVANCE',payload).commandId,command.commandId);
assert.throws(()=>executionCommand({...view,artifact:'BTL-RESEARCH-SESSION-VIEW-1'},'ADVANCE',payload));
assert.equal(view.state.balance,'9007199254740993.03');
const review={schemaVersion:1,artifact:'BTL-ORDER-REVIEW-2',id:'order:qa',estimate:{entry:'9007199254740993.00000001',quantity:'0.01',risk:null}};
const canonical='{"artifact":"BTL-ORDER-REVIEW-2","estimate":{"entry":"9007199254740993.00000001","quantity":"0.01","risk":null},"id":"order:qa","schemaVersion":1}';
assert.deepEqual(await confirmation(review),{reviewId:'order:qa',reviewHash:createHash('sha256').update(canonical).digest('hex')});
await assert.rejects(confirmation({...review,artifact:'BTL-ORDER-REVIEW-1'}));
assert.match(accessMessage({artifact:'BTL-SANDBOX-ACCESS-1',mode:'SANDBOX',fundsCollected:false,tier:'FREE',savedSessions:4,savedLimit:5,resetTimezone:'UTC'}),/FREE.*4\/5.*00:00 UTC/);
assert.throws(()=>accessMessage({artifact:'BTL-SANDBOX-ACCESS-1',mode:'LIVE',fundsCollected:true}));
assert.match(betaNotice({reconciliationRequired:true}),/uncertain.*Reload/);assert.match(betaNotice({code:'DAILY_WINDOW_LIMIT'}),/activated Session/);
assert.doesNotMatch(betaNotice({code:'password=private-token'}),/private-token/);
const calls=[];const c=createBetaClient({secure:()=>true,fetcher:async(path,options)=>{calls.push([path,options]);return new Response(JSON.stringify(path.endsWith('/login')?{access_token:'authored_opaque_fixture_token_12345',token_type:'bearer'}:{id:'11111111-1111-4111-8111-111111111111',is_active:true,is_verified:true}));}});
await assert.rejects(c.createWorkspace('Denied'),error=>error.code==='SIGN_IN_REQUIRED');assert.equal(calls.length,0);
await c.login('qa@example.com','authored fixture');await c.createWorkspace('Exact workspace');assert.equal(calls.at(-1)[0],'/api/v1/workspaces');assert.deepEqual(JSON.parse(calls.at(-1)[1].body),{name:'Exact workspace'});
console.log('PASS Beta UI contracts: engine isolation, exact review canonical hash, unique command identity, honest sandbox access and reconciliation messages.');

const fields=new Map(Object.entries({kind:'PROTOCOL',name:'Pinned rules',checklist:'ON',conditions:'Setup valid\nTrend valid',risk:'0.5',rr:'2'}));
const method=methodFromForm(fields,'method:pinned');assert.equal(method.kind,'PROTOCOL');assert.equal(method.conditions.length,2);assert.equal(method.checklistOn,true);
const forged=new Map(Object.entries({side:'LONG',workflow:'QUICK',orderType:'LIMIT',entry:'1.1',quantity:'99',tp:'999',sl:'1.09',risk:'99','condition:condition:0':'PASS'}));
const protocol=orderFromForm(forged,{method,quote:{ask:'1.2'}});assert.equal(protocol.workflow,'PLANNED');assert.equal(protocol.quantity,null);assert.equal(protocol.tp,null);assert.equal(protocol.riskPercent,null);assert.equal(protocol.observations[1].outcome,'NOT_ASSESSED');
const free=orderFromForm(forged,{method:{kind:'FREE_STYLE'},quote:{ask:'1.2'}});assert.equal(free.entry,'1.2');assert.equal(free.orderType,'MARKET');assert.deepEqual(free.observations,[]);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
let release,callsMade=0,stopped=0,queued=[];
const loop=createReplayLoop({step:()=>{callsMade++;return new Promise(resolve=>{release=resolve;});},onStop:()=>stopped++,schedule:fn=>{queued.push(fn);return fn;},cancel:fn=>{queued=queued.filter(x=>x!==fn);}});
assert.equal(loop.start(),true);assert.equal(loop.start(),false);assert.equal(callsMade,1);loop.stop();assert.equal(loop.start(),false,'in-flight command blocks restart');release(true);await settle();assert.equal(queued.length,0,'pause cannot schedule another command');
assert.equal(loop.start(),true);release(true);await settle();assert.equal(queued.length,1);const nextTick=queued.shift();nextTick();assert.equal(callsMade,3);release(false);await settle();assert.equal(queued.length,0);assert.equal(stopped,2);
console.log('PASS Protocol owns quantity/target/risk and checklist evidence; replay backpressure, pause-in-flight, restart and no-progress stop.');

assert.equal(checkoutAddress('https://app.sandbox.midtrans.com/snap/v4/redir/qa_1'),'https://app.sandbox.midtrans.com/snap/v4/redir/qa_1');
for(const value of ['javascript:alert(1)','https://evil.example/snap/v4/redir/a','https://app.sandbox.midtrans.com.evil.example/snap/v4/redir/a','https://user@app.sandbox.midtrans.com/snap/v4/redir/a','https://app.sandbox.midtrans.com/snap/v4/redir/a?token=b','http://app.sandbox.midtrans.com/snap/v4/redir/a'])assert.throws(()=>checkoutAddress(value));

assert.equal(billingDuration('86400'),'1 days');assert.equal(billingDuration('3600'),'1 hours');assert.equal(billingExpiry('0'),'1970-01-01 00:00:00 UTC');assert.equal(billingExpiry('bad'),'Unavailable');

assert.deepEqual(startPeriods({startPeriod:'2020-01'}),['2020-01']);
assert.deepEqual(startPeriods({startPeriod:'2020-01',periods:['2025-09','2024-11','2024-11','2024-13','bad',7]}),['2024-11','2025-09']);
assert.deepEqual(startPeriods({periods:[]}),[]);assert.deepEqual(startPeriods({startPeriod:'2020-1'}),[]);assert.deepEqual(startPeriods(undefined),[]);
assert.equal(periodLabel('2024-11'),'Nov 2024');
console.log('PASS New Session start months: only catalog-listed valid months, sorted and unique, synthetic fallback unchanged.');
