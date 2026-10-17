// Private QA stdin/stdout protocol only. Never run against a user database.
import assert from 'node:assert/strict';
import {createInterface} from 'node:readline';
import {createHash} from 'node:crypto';
import {createBetaClient} from '../integration/betaClient.js';
const lines=createInterface({input:process.stdin})[Symbol.asyncIterator]();
const next=async()=>JSON.parse((await lines.next()).value);
const config=await next();
const c=createBetaClient({secure:()=>true,fetcher:async(path,options)=>{
  process.stdout.write(JSON.stringify({path,options})+'\n');const response=await next();
  return new Response(response.status===204?null:response.body,{status:response.status,headers:{'content-type':'application/json'}});
}});
const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v!==null&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
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
const request={reviewId:review.id,reviewHash:createHash('sha256').update(canonical(review)).digest('hex')};
const receipt=await c.confirm(sid,request);revision=receipt.state.revision;
await command('ADVANCE',{targetNs:config.next});await command('CLOSE',{orderId:review.id,quantity:null});await command('ADVANCE',{targetNs:config.last});
const stats=await c.statistics(sid);assert.equal(stats.account.balance,'10000.03');assert.deepEqual(stats.metrics.totalR,{numerator:'3',denominator:'100'});
assert.deepEqual(await c.confirm(sid,request),receipt);assert.equal((await c.inspect(sid)).state.revision,revision);
await c.editJournal(sid,{orderId:review.id,expectedNoteRevision:0,text:'Actual Node/ASGI receipt',tags:['qa']});assert.equal((await c.journal(sid)).notes.length,1);
const access=await c.access();assert.equal(access.mode,'SANDBOX');assert.equal(access.fundsCollected,false);
await c.trash(sid);assert.equal((await c.inspect(sid)).savedState,'TRASHED');await c.restore(sid);assert.equal((await c.inspect(sid)).savedState,'SAVED');
await c.logout();assert.equal(c.hasSession(),false);
process.stdout.write(JSON.stringify({complete:true})+'\n');process.exit(0);
