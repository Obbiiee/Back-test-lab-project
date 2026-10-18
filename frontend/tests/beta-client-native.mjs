// Private QA stdin/stdout protocol only. Never run against a user database.
import assert from 'node:assert/strict';
import {createInterface} from 'node:readline';
import {confirmation} from '../src/beta/betaWorkspace.js';
import {createBetaClient} from '../integration/betaClient.js';
const lines=createInterface({input:process.stdin})[Symbol.asyncIterator]();
const next=async()=>JSON.parse((await lines.next()).value);
const config=await next();
const c=createBetaClient({secure:()=>true,fetcher:async(path,options)=>{
  process.stdout.write(JSON.stringify({path,options})+'\n');const response=await next();
  return new Response(response.status===204?null:response.body,{status:response.status,headers:{'content-type':'application/json'}});
}});
assert.equal((await c.providers()).googleConfigured,false);
await c.login(config.email,config.password);c.selectWorkspace(config.workspace);
await c.createMethod(config.method);
const sid='session:node-native';await c.createSession({id:sid,name:'Node adapter QA',methodId:config.method.id,initialBalance:'10000',startPeriod:'2020-01',symbol:'EURUSD'});
const catalog=await c.catalog();assert.equal(catalog.instruments.length,16);
assert.equal((await c.inspect(sid)).state.revision,0);await c.activate(sid);
let revision=0;const command=async(kind,payload)=>{
 const result=await c.command(sid,{schemaVersion:1,artifact:'BTL-TICK-EXECUTION-COMMAND-2',sessionId:sid,commandId:'node:'+revision,expectedRevision:revision,kind,payload});revision=result.state.revision;return result;
};
await command('ADVANCE',{targetNs:config.start});
const review=await c.review(sid,{id:'order:node',expectedRevision:revision,payload:config.opening});
assert.equal(review.command.payload.entry,'1.10002');
const request=await confirmation(review);
const receipt=await c.confirm(sid,request);revision=receipt.state.revision;
await command('ADVANCE',{targetNs:config.next});await command('CLOSE',{orderId:review.id,quantity:null});await command('ADVANCE',{targetNs:config.last});
const stats=await c.statistics(sid);assert.equal(stats.account.balance,'10000.03');assert.deepEqual(stats.metrics.totalR,{numerator:'3',denominator:'100'});
assert.deepEqual(await c.confirm(sid,request),receipt);assert.equal((await c.inspect(sid)).state.revision,revision);
// All chart resolutions are read-only and keep the same durable financial state.
const original=await c.inspect(sid);
for(const timeframe of ['1m','3m','5m','15m','30m','1h','2h','4h','D']){
 const framed=await c.inspect(sid,{timeframe});assert.equal(framed.chart.timeframe,timeframe);assert.deepEqual(framed.state,original.state);
}
// Two exits remain one completed position, with exact posted cash.
const second=await c.review(sid,{id:'order:partial',expectedRevision:revision,payload:{...config.opening,quantity:'0.02'}});
const secondReceipt=await c.confirm(sid,await confirmation(second));revision=secondReceipt.state.revision;
const later=n=>String(BigInt(config.start)+BigInt(n)*15000000000n);
await command('ADVANCE',{targetNs:later(3)});await command('CLOSE',{orderId:second.id,quantity:'0.01'});await command('ADVANCE',{targetNs:later(4)});
assert.equal((await c.statistics(sid)).metrics.tradeCount,1,'partial exit is not a completed position');
assert.equal((await c.inspect(sid)).state.orders[second.id].remaining,'0.01');
await command('CLOSE',{orderId:second.id,quantity:null});await command('ADVANCE',{targetNs:later(5)});
const partialStats=await c.statistics(sid);assert.equal(partialStats.account.balance,'10000.14');assert.equal(partialStats.metrics.tradeCount,2);
assert.equal(partialStats.completed.find(p=>p.id===second.id).net,'0.11');
await c.editJournal(sid,{orderId:review.id,expectedNoteRevision:0,text:'Actual Node/ASGI receipt',tags:['qa']});assert.equal((await c.journal(sid)).notes.length,1);
const access=await c.access();assert.equal(access.mode,'SANDBOX');assert.equal(access.fundsCollected,false);
await c.trash(sid);assert.equal((await c.inspect(sid)).savedState,'TRASHED');await c.restore(sid);assert.equal((await c.inspect(sid)).savedState,'SAVED');
await c.logout();assert.equal(c.hasSession(),false);
process.stdout.write(JSON.stringify({complete:true})+'\n');process.exit(0);
