import assert from 'node:assert/strict';
import {createBetaClient,BetaRequestError} from '../integration/betaClient.js';
const user='11111111-1111-4111-8111-111111111111',workspace='22222222-2222-4222-8222-222222222222',other='33333333-3333-4333-8333-333333333333';
const token='authored_opaque_fixture_token_12345';
const me={id:user,is_active:true,is_verified:true,email:'fixture@example.com'};
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'content-type':'application/json'}});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
function harness(){
  const calls=[];let handler=async path=>path.endsWith('/login')||path.endsWith('/exchange')?json({access_token:token,token_type:'bearer'}):path.endsWith('/me')?json(me):json({schemaVersion:1});
  const client=createBetaClient({secure:()=>true,fetcher:async(path,options)=>{calls.push([path,options]);return handler(path,options);}});
  return {client,calls,set:fn=>{handler=fn;}};
}
async function signed(){const h=harness();await h.client.login('fixture@example.com','private password');h.client.selectWorkspace(workspace);return h;}
const isCode=(code,reconcile=false)=>error=>error instanceof BetaRequestError&&error.code===code&&error.reconciliationRequired===reconcile;
{
  let calls=0;const c=createBetaClient({secure:()=>false,fetcher:()=>{calls++;}});
  await assert.rejects(c.login('a','b'),isCode('HTTPS_REQUIRED'));assert.throws(()=>c.googleStart(),isCode('HTTPS_REQUIRED'));
  await assert.rejects(c.providers(),isCode('HTTPS_REQUIRED'));assert.equal(calls,0);
  const h=harness();await assert.rejects(h.client.catalog(),isCode('SIGN_IN_REQUIRED'));
  assert.throws(()=>h.client.selectWorkspace(workspace),isCode('SIGN_IN_REQUIRED'));assert.equal(h.calls.length,0);
}
{
  const h=await signed();assert.equal(h.client.subject(),user);assert.equal(h.client.hasSession(),true);
  const [login,identity]=h.calls;assert.equal(login[0],'/api/v1/auth/login');assert.equal(login[1].credentials,'omit');assert.equal(login[1].headers.Authorization,undefined);
  assert.equal(new URLSearchParams(login[1].body).get('password'),'private password');assert.equal(identity[1].headers.Authorization,'Bearer '+token);
  h.set(async()=>json({schemaVersion:2,balance:'9007199254740993.00000001',r:{numerator:'3',denominator:'100'}}));
  const result=await h.client.inspect('session:one');assert.equal(result.balance,'9007199254740993.00000001');assert.deepEqual(result.r,{numerator:'3',denominator:'100'});
  assert.equal(h.calls.at(-1)[0],`/api/v1/workspaces/${workspace}/research-v2/sessions/session%3Aone`);
  const count=h.calls.length;await assert.rejects(h.client.createSession(),isCode('INVALID_REQUEST'));await assert.rejects(h.client.command('one',[]),isCode('INVALID_REQUEST'));assert.equal(h.calls.length,count);
  const intent={id:'review:one',expectedRevision:7,payload:{quantity:'0.01',price:'1.10002'}};
  await h.client.review('session:one',intent);assert.deepEqual(JSON.parse(h.calls.at(-1)[1].body),intent);
  await h.client.confirm('session:one',{reviewId:'review:one',reviewHash:'exact-hash'});assert.ok(h.calls.at(-1)[0].endsWith('/confirm'));
  for(const op of ['activate','trash','restore']){await h.client[op]('session:one');assert.equal(h.calls.at(-1)[1].body,'{}');}
  for(const bad of ['../foreign','a/b','a?source=real','%2f','.', 'x'.repeat(129)])await assert.rejects(async()=>h.client.inspect(bad),/Invalid Session identity/);
  assert.throws(()=>h.client.selectWorkspace('../foreign'),isCode('INVALID_WORKSPACE'));
  assert.ok(h.calls.every(([path,opt])=>path.startsWith('/api/v1/')&&!path.includes('?')&&opt.cache==='no-store'&&opt.redirect==='error'));
}
{
  const h=harness();assert.equal(h.client.googleStart(),'/api/v1/auth/google/start');await h.client.providers();assert.equal(h.calls[0][1].headers.Authorization,undefined);
  await h.client.exchangeGoogle();const exchange=h.calls.find(([p])=>p.endsWith('/exchange'))[1];assert.equal(exchange.credentials,'same-origin');assert.equal(exchange.headers['X-BTL-Google-Exchange'],'1');assert.equal(exchange.headers.Authorization,undefined);assert.equal(exchange.body,'{}');
  assert.equal(h.calls.at(-1)[1].credentials,'omit');assert.equal(h.client.subject(),user);
  await h.client.logout(true);assert.ok(h.calls.at(-1)[0].endsWith('/logout-all'));assert.equal(h.client.hasSession(),false);assert.equal(h.client.subject(),null);
}
{
  const h=await signed();h.set(async()=>json({detail:'private-password-and-token'},409));await assert.rejects(h.client.activate('one'),isCode('RELOAD_REQUIRED'));
  h.set(async()=>json({detail:'DAILY_WINDOW_LIMIT'},409));await assert.rejects(h.client.activate('one'),isCode('DAILY_WINDOW_LIMIT'));
  h.set(async()=>{throw Error('secret network details');});const before=h.calls.length;
  await assert.rejects(h.client.confirm('one',{reviewId:'r',reviewHash:'h'}),isCode('SERVICE_UNAVAILABLE',true));assert.equal(h.calls.length,before+1,'never auto-retry an uncertain write');
  await assert.rejects(h.client.inspect('one'),isCode('SERVICE_UNAVAILABLE'));
  h.set(async()=>json({detail:'SERVICE_UNAVAILABLE'},503));await assert.rejects(h.client.command('one',{kind:'ADVANCE'}),isCode('SERVICE_UNAVAILABLE',true));
  h.set(async()=>json({schemaVersion:999}));await assert.rejects(h.client.confirm('one',{}),isCode('UNSUPPORTED_RESPONSE',true));
  h.set(async()=>json({detail:'never show raw error'},401));await assert.rejects(h.client.catalog(),isCode('SIGN_IN_REQUIRED'));assert.equal(h.client.hasSession(),false);
}
{
  const h=await signed(),pending=deferred();h.set(()=>pending.promise);const read=h.client.inspect('one');h.client.selectWorkspace(other);pending.resolve(json({schemaVersion:2,state:{balance:'foreign'}}));await assert.rejects(read,isCode('ACCOUNT_CHANGED'));
  h.set(async()=>json({schemaVersion:1}));await h.client.catalog();assert.ok(h.calls.at(-1)[0].includes(other));
}
{
  const h=harness(),old=deferred();h.set(path=>path.endsWith('/login')?old.promise:Promise.resolve(json(me)));
  const obsolete=h.client.login('old@example.com','old');
  h.set(async path=>path.endsWith('/login')?json({access_token:token,token_type:'bearer'}):json(me));await h.client.login('new@example.com','new');
  old.resolve(json({access_token:'obsolete_fixture_token_value',token_type:'bearer'}));await assert.rejects(obsolete,isCode('ACCOUNT_CHANGED'));assert.equal(h.client.hasSession(),true);assert.equal(h.client.subject(),user);
}
{
  const h=harness();h.set(async path=>path.endsWith('/login')?json({access_token:token,token_type:'bearer'}):json({...me,is_verified:false}));await assert.rejects(h.client.login('a','b'),isCode('VERIFIED_ACCOUNT_REQUIRED'));assert.equal(h.client.hasSession(),false);
  const good=await signed();good.set(async()=>new Response('{malformed'));await assert.rejects(good.client.command('one',{}),isCode('SERVICE_UNAVAILABLE',true));
  good.set(async()=>new Response(' '.repeat(8388609)));await assert.rejects(good.client.catalog(),isCode('SERVICE_UNAVAILABLE'));
  const paused=deferred();good.set(async()=>new Response(new ReadableStream({async start(controller){await paused.promise;controller.enqueue(new TextEncoder().encode('{"schemaVersion":2}'));controller.close();}})));
  const read=good.client.catalog();good.client.clear();paused.resolve();await assert.rejects(read,isCode('ACCOUNT_CHANGED'));
}
console.log('PASS Beta transport: exact v2 requests, Google cookie exchange, HTTPS, scoped identity, stale-response refusal, bounded responses, quota errors and uncertain-write reconciliation without retry.');

{
 const h=await signed();h.set(async()=>json({schemaVersion:1,artifact:'BTL-RESEARCH-SESSION-VIEW-2'}));
 await h.client.inspect('session:one',{timeframe:'1h'});assert.ok(h.calls.at(-1)[0].endsWith('/view'));assert.deepEqual(JSON.parse(h.calls.at(-1)[1].body),{timeframe:'1h'});
 h.set(async()=>{throw Error('network');});await assert.rejects(h.client.inspect('session:one',{timeframe:'D'}),isCode('SERVICE_UNAVAILABLE'));
}

{
 const h=await signed();h.set(async()=>json({schemaVersion:1,mode:'SANDBOX'}));
 for(const method of ['billingPlan','billingOrders','billingAccess'])await h.client[method]();
 await h.client.billingCheckout('11111111-1111-4111-8111-111111111111');
 assert.deepEqual(JSON.parse(h.calls.at(-1)[1].body),{requestId:'11111111-1111-4111-8111-111111111111'});
 assert.equal(h.calls.at(-1)[0],'/api/v1/billing/sandbox/checkout');
 await h.client.billingResume('btl-sbx-'+'a'.repeat(32));assert.equal(h.calls.at(-1)[1].body,'{}');
 h.set(async()=>{throw Error('lost response');});await assert.rejects(h.client.billingCheckout('11111111-1111-4111-8111-111111111111'),isCode('SERVICE_UNAVAILABLE',true));
 const count=h.calls.length;await assert.rejects(h.client.billingCheckout('../bad'),isCode('INVALID_REQUEST'));assert.equal(h.calls.length,count);
 h.client.clear();await assert.rejects(h.client.billingOrders(),isCode('SIGN_IN_REQUIRED'));
}
