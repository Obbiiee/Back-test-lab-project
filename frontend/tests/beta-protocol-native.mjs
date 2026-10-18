// Private QA stdin/stdout protocol only. Never run against a user database.
import assert from 'node:assert/strict';
import {createInterface} from 'node:readline';
import {confirmation,methodFromForm,orderFromForm,executionCommand} from '../src/beta/betaWorkspace.js';
import {createBetaClient} from '../integration/betaClient.js';
const lines=createInterface({input:process.stdin})[Symbol.asyncIterator]();
const next=async()=>JSON.parse((await lines.next()).value);
const config=await next();
const c=createBetaClient({secure:()=>true,fetcher:async(path,options)=>{
  process.stdout.write(JSON.stringify({path,options})+'\n');const response=await next();
  return new Response(response.status===204?null:response.body,{status:response.status,headers:{'content-type':'application/json'}});
}});

await c.login(config.email,config.password);c.selectWorkspace(config.workspace);
const method=methodFromForm(new Map(Object.entries({name:'Protocol UI native',kind:'PROTOCOL',checklist:'ON',conditions:'Setup valid',risk:'1',rr:'2'})),config.method.id);
await c.createMethod(method);const sid='session:protocol-ui';
await c.createSession({id:sid,name:'Protocol native',methodId:method.id,initialBalance:'10000',startPeriod:'2020-01',symbol:'EURUSD'});await c.activate(sid);
let view=await c.inspect(sid);
async function command(kind,payload){await c.command(sid,executionCommand(view,kind,payload));view=await c.inspect(sid);}
await command('ADVANCE',{targetNs:config.start});
const fields=new Map(Object.entries({side:'LONG',workflow:'QUICK',orderType:'STOP',entry:'1.1001',sl:'1.0991',quantity:'99',tp:'999'}));
await assert.rejects(c.review(sid,{id:'order:unassessed',expectedRevision:view.state.revision,payload:orderFromForm(fields,view)}));
fields.set('condition:'+method.conditions[0].id,'PASS');
const review=await c.review(sid,{id:'order:protocol',expectedRevision:view.state.revision,payload:orderFromForm(fields,view)});
assert.equal(review.command.payload.quantity,'1');assert.equal(review.command.payload.tp,'1.1021');assert.equal(review.command.payload.riskPercent,'1');
await c.confirm(sid,await confirmation(review));view=await c.inspect(sid);
await command('CANCEL',{orderId:review.id});assert.equal(view.state.orders[review.id].status,'CANCELLED');
const active=await c.review(sid,{id:'order:protocol-active',expectedRevision:view.state.revision,payload:orderFromForm(fields,view)});
await c.confirm(sid,await confirmation(active));view=await c.inspect(sid);
await command('ADVANCE',{targetNs:config.last});assert.equal(view.state.orders[active.id].status,'ACTIVE');
const before=view.state;
await assert.rejects(c.command(sid,executionCommand(view,'CLOSE',{orderId:active.id,quantity:null})));
assert.deepEqual((await c.inspect(sid)).state,before,'Protocol cannot manually close or mutate evidence after refusal');
await c.logout();process.stdout.write(JSON.stringify({complete:true})+'\n');process.exit(0);
