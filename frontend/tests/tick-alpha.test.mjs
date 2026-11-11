import {entryRoute} from '../src/entryRoute.js';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {api,command,replayObservedTo,sessionPath,loadResearchContext,noticeText,sourceContext,pagePath} from '../src/tickAlpha/client.js';
import {syncTickAnnotations,ratioLabel} from '../src/tickAlpha/annotations.js';
import {displayBars,historyPage,replayTarget,seekTarget} from '../src/tickAlpha/display.js';
import {KEY,RETENTION,readMeasurement,writeMeasurement,eventTo,saveFeedback,measurementExport,QUESTIONS} from '../src/tickAlpha/measurement.js';
import {createAccountClient,setAccountTransport,clearAccountTransport,accountStorageKey} from '../src/tickAlpha/accountClient.js';

// HTTPS-only account transport never persists tokens or falls back to local data.
const accountCalls=[];
const accountFetch=async(path,options)=>{
  accountCalls.push([path,options]);
  return {ok:true,status:200,json:async()=>path.endsWith('/login')?{access_token:'QA-MEMORY-TOKEN',token_type:'bearer'}:path.endsWith('/me')?{id:'22222222-2222-4222-8222-222222222222',is_verified:true,is_active:true}: {schemaVersion:1,label:'SYNTHETIC / TEST ONLY'}};
};
const account=createAccountClient({fetcher:accountFetch,secure:()=>true});
await account.login('qa@example.com','Test fixture passphrase only');
assert.equal(accountCalls[0][1].credentials,'omit');
assert.equal(accountCalls[0][1].headers.Authorization,undefined);
assert.equal(accountCalls[1][1].headers.Authorization,'Bearer QA-MEMORY-TOKEN');
assert.equal(JSON.stringify(account).includes('QA-MEMORY-TOKEN'),false);
setAccountTransport(account,'11111111-1111-4111-8111-111111111111');
const tenantKey=accountStorageKey('same-session-id');
setAccountTransport(account,'33333333-3333-4333-8333-333333333333');
assert.notEqual(accountStorageKey('same-session-id'),tenantKey);
setAccountTransport(account,'11111111-1111-4111-8111-111111111111');
assert.equal(sourceContext(),'synthetic');
await api('/catalog');
assert.equal(accountCalls.at(-1)[0],'/api/v1/workspaces/11111111-1111-4111-8111-111111111111/research/catalog');
assert.equal(accountCalls.at(-1)[1].headers['X-BTL-Source'],undefined);
const transientReadCalls=[];
let transientMutationCalls=0;
const transientReadAccount=createAccountClient({secure:()=>true,fetcher:async(path,options)=>{
  if(path.endsWith('/login'))return {ok:true,status:200,json:async()=>({access_token:'RETRY-TOKEN',token_type:'bearer'})};
  if(path.endsWith('/me'))return {ok:true,status:200,json:async()=>({id:'22222222-2222-4222-8222-222222222222',is_verified:true,is_active:true})};
  if(path.endsWith('/catalog')){
    transientReadCalls.push(path);
    if(transientReadCalls.length<3)return {ok:false,status:transientReadCalls.length===1?429:503,
      json:async()=>({detail:transientReadCalls.length===1?'RESEARCH_BUSY':'SERVICE_BUSY'})};
    return {ok:true,status:200,json:async()=>({schemaVersion:1,label:'Recovered bounded read'})};
  }
  if(path.endsWith('/methods')){
    transientMutationCalls++;
    if(transientMutationCalls===1)return {ok:false,status:429,json:async()=>({detail:'RESEARCH_BUSY'})};
    return {ok:true,status:200,json:async()=>({schemaVersion:1,label:'Method accepted once'})};
  }
  if(path.endsWith('/sessions')){
    return {ok:false,status:429,json:async()=>({detail:'QUEUE_CAPACITY'})};
  }
  return {ok:true,status:200,json:async()=>({schemaVersion:1})};
}});
await transientReadAccount.login('qa@example.com','Test fixture passphrase only');
setAccountTransport(transientReadAccount,'11111111-1111-4111-8111-111111111111');
assert.equal((await api('/catalog')).label,'Recovered bounded read');
assert.equal(transientReadCalls.length,3,'explicit read-only research contention retries with bounded backoff');
assert.equal((await api('/methods',{name:'One explicit no-op retry'})).label,'Method accepted once');
assert.equal(transientMutationCalls,2,'a pre-admission RESEARCH_BUSY refusal may be retried before any operation executes');
let extendedBusyCalls=0;
const extendedBusyClient=createAccountClient({secure:()=>true,fetcher:async(path)=>{
  if(path.endsWith('/login'))return {ok:true,status:200,json:async()=>({access_token:'BUSY-TOKEN',token_type:'bearer'})};
  if(path.endsWith('/me'))return {ok:true,status:200,json:async()=>({id:'22222222-2222-4222-8222-222222222222',is_verified:true,is_active:true})};
  extendedBusyCalls++;
  if(extendedBusyCalls<=6)return {ok:false,status:503,headers:{get:name=>name==='Retry-After'?'0':null},json:async()=>({detail:'SERVICE_BUSY'})};
  return {ok:true,status:200,json:async()=>({schemaVersion:1,label:'Recovered after admission pressure'})};
}});
await extendedBusyClient.login('qa@example.com','Test fixture passphrase only');
assert.equal((await extendedBusyClient.request('/api/v1/workspaces/11111111-1111-4111-8111-111111111111/research/catalog')).label,
  'Recovered after admission pressure');
assert.equal(extendedBusyCalls,7,'bounded SERVICE_BUSY retries can outlast a short admission-pressure burst');
let retryAfterCalls=0;
const retryAfterClient=createAccountClient({secure:()=>true,fetcher:async(path)=>{
  if(path.endsWith('/login'))return {ok:true,status:200,json:async()=>({access_token:'RETRY-AFTER-TOKEN',token_type:'bearer'})};
  if(path.endsWith('/me'))return {ok:true,status:200,json:async()=>({id:'22222222-2222-4222-8222-222222222222',is_verified:true,is_active:true})};
  retryAfterCalls++;
  if(retryAfterCalls===1)return {ok:false,status:503,headers:{get:name=>name==='Retry-After'?'0.1':null},json:async()=>({detail:'SERVICE_BUSY'})};
  return {ok:true,status:200,json:async()=>({schemaVersion:1,label:'Retry-After honored'})};
}});
await retryAfterClient.login('qa@example.com','Test fixture passphrase only');
const retryAfterStart=performance.now();
assert.equal((await retryAfterClient.request('/api/v1/workspaces/11111111-1111-4111-8111-111111111111/research/catalog')).label,
  'Retry-After honored');
assert.ok(performance.now()-retryAfterStart>=90,'explicit Retry-After is a minimum delay before a safe retry');
let queueRefusalCalls=0;
const queueRefusalAccount=createAccountClient({secure:()=>true,fetcher:async(path)=>{
  if(path.endsWith('/login'))return {ok:true,status:200,json:async()=>({access_token:'QUEUE-TOKEN',token_type:'bearer'})};
  if(path.endsWith('/me'))return {ok:true,status:200,json:async()=>({id:'22222222-2222-4222-8222-222222222222',is_verified:true,is_active:true})};
  if(path.endsWith('/sessions')){queueRefusalCalls++;return {ok:false,status:429,json:async()=>({detail:'QUEUE_CAPACITY'})};}
  return {ok:true,status:200,json:async()=>({schemaVersion:1})};
}});
await queueRefusalAccount.login('qa@example.com','Test fixture passphrase only');
setAccountTransport(queueRefusalAccount,'11111111-1111-4111-8111-111111111111');
await assert.rejects(()=>api('/sessions',{name:'Queue refusal is not retried'}),error=>error.status===429);
assert.equal(queueRefusalCalls,1,'queue capacity refusal does not resubmit a durable command');
setAccountTransport(account,'11111111-1111-4111-8111-111111111111');
const queuedCalls=[];
let queuedId;
const queuedAccount={subject:()=> '22222222-2222-4222-8222-222222222222',request:async(path,options={})=>{
  queuedCalls.push([path,options]);
  if(path.endsWith('/view')){queuedId=options.jobId;return {schemaVersion:1,jobId:queuedId,state:'QUEUED',result:null};}
  return {schemaVersion:1,jobId:queuedId,state:'SUCCEEDED',result:{schemaVersion:1,label:'Bounded queued read'}};
}};
setAccountTransport(queuedAccount,'11111111-1111-4111-8111-111111111111');
const queuedResult=await api('/sessions/session:queue/view',{timeframe:'1m'});
assert.equal(queuedResult.label,'Bounded queued read');
assert.equal(queuedCalls.length,2);
assert.match(queuedId,/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
const pollDelays=[];let pendingPolls=0;let pendingJobId;
setAccountTransport({subject:queuedAccount.subject,request:async(path,options={})=>{
  if(path.endsWith('/view')){pendingJobId=options.jobId;return {schemaVersion:1,jobId:pendingJobId,state:'QUEUED',result:null};}
  pendingPolls++;
  return pendingPolls<4?{schemaVersion:1,jobId:pendingJobId,state:'RUNNING',result:null}:
    {schemaVersion:1,jobId:pendingJobId,state:'SUCCEEDED',result:{schemaVersion:1,label:'Backoff poll complete'}};
}},'11111111-1111-4111-8111-111111111111');
const nativeSetTimeout=globalThis.setTimeout;
globalThis.setTimeout=(callback,delay,...args)=>{pollDelays.push(delay);queueMicrotask(()=>callback(...args));return pollDelays.length;};
let backoffResult;
try{backoffResult=await api('/sessions/session:poll/view',{timeframe:'1m'});}
finally{globalThis.setTimeout=nativeSetTimeout;}
assert.equal(backoffResult.label,'Backoff poll complete');
assert.equal(pendingPolls,4);
assert.ok(pollDelays.length===4&&pollDelays[0]>=1000&&pollDelays.every((delay,index)=>
  delay<=3250&&(index===0||delay>pollDelays[index-1])), 'queued status polls back off with bounded jitter');
const readRetryIds=[];
setAccountTransport({subject:queuedAccount.subject,request:async(_path,options={})=>{readRetryIds.push(options.jobId);return {schemaVersion:1,label:'done'};}},'11111111-1111-4111-8111-111111111111');
await api('/sessions/session:queue/view',{timeframe:'1m'});
assert.notEqual(readRetryIds[0],queuedId,'a new view read cannot reuse a completed queue result');
assert.ok(queuedCalls[1][0].endsWith('/jobs/'+queuedId),'Poll stable read identity; never resend the command');
const additionalQueued=[];
setAccountTransport({subject:queuedAccount.subject,request:async(path,options={})=>{
  additionalQueued.push([path,options]);
  return path.endsWith('/chart-history')||path.endsWith('/replay-to')
    ?{schemaVersion:1,jobId:options.jobId,state:'SUCCEEDED',result:{schemaVersion:1,artifact:'BTL-SYNTHETIC-RESULT-1'}}
    :{schemaVersion:1,jobId:options.jobId,state:'SUCCEEDED',result:{schemaVersion:1,metadata:{id:'session:created'}}};
}},'11111111-1111-4111-8111-111111111111');
assert.equal((await api('/sessions/session:queued/chart-history',{timeframe:'1m',offset:0})).artifact,'BTL-SYNTHETIC-RESULT-1');
assert.equal((await api('/sessions/session:queued/replay-to',{requestId:'request:stable'})).artifact,'BTL-SYNTHETIC-RESULT-1');
assert.ok(additionalQueued.every(([,options])=>options.jobId),'chart-history and replay-to use durable queue IDs');
const observedJump={metadata:{id:'session:jump',artifact:'BTL-OBSERVED-RESEARCH-SESSION-1'},state:{revision:3,throughNs:'100'}};
const jumpRequests=[];
setAccountTransport({subject:queuedAccount.subject,request:async(_path,{body,jobId})=>{
  jumpRequests.push([body.requestId,jobId]);
  const view={metadata:{id:body.sessionId},state:{throughNs:'150',revision:4}};
  return {schemaVersion:1,artifact:'BTL-OBSERVED-REPLAY-TO-RESULT-1',requestId:body.requestId,
    sessionId:body.sessionId,targetNs:body.targetNs,throughNs:'150',targetReached:false,view};
}},'11111111-1111-4111-8111-111111111111');
await assert.rejects(()=>replayObservedTo(observedJump,'99','1m'),/after the saved replay/);
await assert.rejects(()=>replayObservedTo({...observedJump,pendingReplayTargetNs:'175'},'200','1m'),/Continue the saved replay/);
assert.equal((await replayObservedTo(observedJump,'200','1m')).targetReached,false);
await replayObservedTo(observedJump,'200','1m');
assert.equal(jumpRequests.length,2);
assert.deepEqual(jumpRequests[0],jumpRequests[1],'retry keeps both request and queue identities');

const mismatched={subject:queuedAccount.subject,request:async()=>({schemaVersion:1,jobId:'foreign',state:'SUCCEEDED',result:{schemaVersion:1}})};
setAccountTransport(mismatched,'11111111-1111-4111-8111-111111111111');
await assert.rejects(()=>api('/sessions/session:queue/view',{timeframe:'1m'}),/Unexpected research job/);
await assert.rejects(()=>api('/sessions',{id:'session:uncertain'}),error=>error.code==='UNKNOWN'&&!!error.jobId);
let replayJob;
const replayCalls=[];
const reconciliation={subject:queuedAccount.subject,request:async(path,options={})=>{
  replayCalls.push([path,options]);
  if(path.endsWith('/commands')){replayJob=options.jobId;return {schemaVersion:1,jobId:replayJob,state:'QUEUED',result:null};}
  return {schemaVersion:1,jobId:replayJob,state:'RECONCILE_REQUIRED',result:null};
}};
setAccountTransport(reconciliation,'11111111-1111-4111-8111-111111111111');
const replayBody={kind:'ADVANCE',commandId:'command:retained'};
await assert.rejects(()=>api('/sessions/session:queue/commands',replayBody),error=>
  error.code==='UNKNOWN'&&error.jobId===replayJob);
assert.equal(replayCalls.length,2,'Uncertain replay polls its existing job; never silently resubmits a financial command');
assert.equal(replayCalls[0][1].body,replayBody,'Preserve canonical financial command identity');
const lostReplayCalls=[];
let lostId;
setAccountTransport({subject:queuedAccount.subject,request:async(path,options={})=>{
  lostReplayCalls.push([path,options]);
  lostId=options.jobId;
  throw new DOMException('Response lost after possible commit','TimeoutError');
}},'11111111-1111-4111-8111-111111111111');
await assert.rejects(()=>api('/sessions/session:queue/commands',replayBody),error=>error.code==='UNKNOWN'&&error.jobId===lostId);
assert.equal(lostReplayCalls.filter(([path])=>path.endsWith('/commands')).length,1);
assert.equal(lostReplayCalls.some(([path])=>path.endsWith('/cancel')),false,'do not cancel an uncertain financial mutation');
const retried=[];
setAccountTransport({subject:queuedAccount.subject,request:async(path,options={})=>{
  retried.push([path,options]);
  return path.endsWith('/commands')?{schemaVersion:1,jobId:options.jobId,state:'SUCCEEDED',result:{schemaVersion:1,revision:8}}:{schemaVersion:1};
}},'11111111-1111-4111-8111-111111111111');
await api('/sessions/session:queue/commands',replayBody);
assert.equal(retried[0][1].jobId,lostId,'retry reuses the durable financial job ID');
const createCalls=[];
setAccountTransport({subject:queuedAccount.subject,request:async(path,options={})=>{
  createCalls.push([path,options]);
  return {schemaVersion:1,jobId:options.jobId,state:'SUCCEEDED',result:{schemaVersion:1,metadata:{id:'session:new'}}};
}},'11111111-1111-4111-8111-111111111111');
await api('/sessions',{id:'session:new',name:'Synthetic'});
assert.ok(createCalls[0][1].jobId,'POST /sessions is submitted with a durable job identity');
setAccountTransport({subject:queuedAccount.subject,request:async()=>{throw Object.assign(Error('definitive stale request'),{status:409});}},
  '11111111-1111-4111-8111-111111111111');
await assert.rejects(()=>api('/sessions',{id:'session:stale',name:'Synthetic'}),error=>error.status===409&&error.code!=='UNKNOWN');
setAccountTransport({subject:queuedAccount.subject,request:async()=>({schemaVersion:1,state:'QUEUED'})},
  '11111111-1111-4111-8111-111111111111');
await assert.rejects(()=>api('/sessions',{id:'session:missing-job',name:'Synthetic'}),error=>error.code==='UNKNOWN');
const cancelUncertainty=[];
let cancelJob;
setAccountTransport({subject:queuedAccount.subject,request:async(path,options={})=>{
  cancelUncertainty.push([path,options]);
  if(path.endsWith('/commands')){cancelJob=options.jobId;return {schemaVersion:1,jobId:cancelJob,state:'QUEUED',result:null};}
  return {schemaVersion:1,jobId:cancelJob,state:'RECONCILE_REQUIRED',cancellation:'RECONCILE_REQUIRED',result:null};
}},'11111111-1111-4111-8111-111111111111');
await assert.rejects(()=>api('/sessions/session:queue/commands',replayBody),error=>error.code==='UNKNOWN');
assert.equal(cancelUncertainty.length,2,'cancellation race remains an explicit unknown until reconciliation');
const pollTimeout=[];
let timeoutJob;
setAccountTransport({subject:queuedAccount.subject,request:async(path,options={})=>{
  pollTimeout.push([path,options]);
  if(path.endsWith('/commands')){timeoutJob=options.jobId;return {schemaVersion:1,jobId:timeoutJob,state:'QUEUED',result:null};}
  throw new DOMException('poll response timed out','TimeoutError');
}},'11111111-1111-4111-8111-111111111111');
await assert.rejects(()=>api('/sessions/session:queue/commands',replayBody),error=>error.code==='UNKNOWN'&&error.jobId===timeoutJob);
assert.equal(pollTimeout.length,2,'poll timeout preserves the durable job for later reconciliation');
setAccountTransport(account,'11111111-1111-4111-8111-111111111111');
await account.logout(true);
await assert.rejects(()=>api('/catalog'),/Sign in/);
clearAccountTransport();
assert.equal(accountStorageKey('same-session-id'),'same-session-id');
// Match the server queue's retained result semantics across sign-out/sign-in.
const retainedViews=new Map();
let committedRevision=3;
const resumeClient=createAccountClient({secure:()=>true,fetcher:async(path,options)=>{
  if(!path.endsWith('/view'))return accountFetch(path,options);
  const jobId=options.headers['X-BTL-Job'];
  assert.ok(jobId);
  if(!retainedViews.has(jobId))retainedViews.set(jobId,{schemaVersion:1,state:{revision:committedRevision}});
  return {ok:true,status:200,json:async()=>retainedViews.get(jobId)};
}});
const resumeWorkspace='11111111-1111-4111-8111-111111111111';
const loadResume=()=>api('/sessions/session:saved/view',{timeframe:'1m'});
await resumeClient.login('qa@example.com','Test fixture passphrase only');
setAccountTransport(resumeClient,resumeWorkspace);
assert.equal((await loadResume()).state.revision,3);
await resumeClient.logout();
clearAccountTransport();
committedRevision=4;
await resumeClient.login('qa@example.com','Test fixture passphrase only');
setAccountTransport(resumeClient,resumeWorkspace);
assert.equal((await loadResume()).state.revision,4,'resume must load a newly committed server revision');
assert.equal(retainedViews.size,2);
clearAccountTransport();

const failedLogout=createAccountClient({secure:()=>true,fetcher:async(path,options)=>{
  if(path.endsWith('/logout-all'))throw new DOMException('Response lost','TimeoutError');
  return accountFetch(path,options);
}});
await failedLogout.login('qa@example.com','Test fixture passphrase only');
await assert.rejects(()=>failedLogout.logout(true),{name:'TimeoutError'});
assert.equal(failedLogout.hasSession(),false);
assert.equal(failedLogout.subject(),null);
const beforeAccountWindow=globalThis.window;
globalThis.window={location:{href:'https://localhost:5197/?page=account'}};
await assert.rejects(()=>api('/catalog'),/No private local fallback/);
assert.equal(pagePath('home'),'/?page=account');
window.location.href='https://research.example/?tick-alpha=local';
await assert.rejects(()=>api('/catalog'),/No private local fallback/);
if(beforeAccountWindow===undefined)delete globalThis.window;else globalThis.window=beforeAccountWindow;
const insecure=createAccountClient({fetcher:()=>{throw Error('Must not fetch');},secure:()=>false});
await assert.rejects(()=>insecure.login('qa@example.com','password'),/HTTPS/);
const refused=createAccountClient({fetcher:async()=>({ok:false,status:400,json:()=>{throw Error('SECRET');}}),secure:()=>true});
await assert.rejects(()=>refused.login('qa@example.com','SECRET'),error=>!error.message.includes('SECRET'));
let safeBusyCalls=0;
const safeBusy=createAccountClient({secure:()=>true,fetcher:async()=>{
  safeBusyCalls++;
  return {ok:false,status:503,json:async()=>({detail:'SERVICE_BUSY',secret:'must not escape'})};
}});
await assert.rejects(()=>safeBusy.request('/api/v1/auth/providers',{authenticated:false}),error=>
  error.status===503&&error.code==='SERVICE_BUSY'&&!error.message.includes('secret'));
assert.equal(safeBusyCalls,9,'only eight bounded retries follow the original SERVICE_BUSY refusal');
let resolveLogin;
const obsolete=createAccountClient({fetcher:()=>new Promise(resolve=>{resolveLogin=resolve;}),secure:()=>true});
const obsoleteLogin=obsolete.login('qa@example.com','password');
obsolete.clear();resolveLogin({ok:true,status:200,json:async()=>({access_token:'STALE',token_type:'bearer'})});
await assert.rejects(()=>obsoleteLogin,/discarded/);
assert.equal(obsolete.hasSession(),false);
let resolveDecoded;
const decoding=createAccountClient({secure:()=>true,fetcher:async()=>({ok:true,status:200,json:()=>new Promise(resolve=>{resolveDecoded=resolve;})})});
const decodingLogin=decoding.login('qa@example.com','password');
await Promise.resolve();await Promise.resolve();
decoding.clear();resolveDecoded({access_token:'STALE-DECODED',token_type:'bearer'});
await assert.rejects(()=>decodingLogin,/discarded/);
assert.equal(decoding.hasSession(),false,'Logout during response decoding may not restore a token');
const callerAbort=new AbortController();
const canceled=createAccountClient({secure:()=>true,fetcher:async(_path,options)=>{assert.equal(options.signal.aborted,true);throw Error('canceled');}});
callerAbort.abort();
await assert.rejects(()=>canceled.request('/api/v1/auth/verify',{authenticated:false,signal:callerAbort.signal}),/canceled/);
const operationDeadline=new AbortController();let forwardedDeadline;
const inheritedDeadline=createAccountClient({secure:()=>true,fetcher:async(_path,options)=>{
  forwardedDeadline=options.signal;
  return {ok:true,status:200,json:async()=>({schemaVersion:1})};
}});
await inheritedDeadline.request('/api/v1/workspaces/11111111-1111-4111-8111-111111111111/research/journal/pages',
  {authenticated:false,signal:operationDeadline.signal});
assert.equal(forwardedDeadline,operationDeadline.signal,
  'research transport must honor the caller’s bounded job deadline without imposing a shorter nested timeout');
console.log('PASS account transport: HTTPS-only, memory-only token, strict verified identity, scoped preferences, logout/no local fallback, safe refusals and obsolete-login cancellation.');

const localData=new Map(),localStore={getItem:key=>localData.get(key)??null,setItem:(key,value)=>localData.set(key,value)};
const observedNow=Date.UTC(2026,9,11),disabledMeasurement=readMeasurement(localStore,observedNow);
assert.equal(eventTo(localStore,{id:'event:1',name:'workspace_opened'},observedNow),false);
assert.equal(localData.size,0,'Disabled collection cannot write');
writeMeasurement(localStore,{...disabledMeasurement,enabled:true},observedNow);
for(let i=0;i<256;i++)assert.equal(eventTo(localStore,{id:`event:${i}`,name:'workspace_opened'},observedNow),true);
assert.equal(eventTo(localStore,{id:'event:0',name:'workspace_opened'},observedNow),true);
assert.equal(readMeasurement(localStore,observedNow).events.length,256);
assert.equal(eventTo(localStore,{id:'event:overflow',name:'analysis_opened'},observedNow),false);
assert.equal(readMeasurement(localStore,observedNow).dropped,1);
const privateBefore=localData.get(KEY);
assert.equal(eventTo(localStore,{id:'event:private',name:'workspace_opened',token:'SECRET'},observedNow),false);
assert.equal(localData.get(KEY),privateBefore);
const answers=Object.fromEntries(QUESTIONS.map(([key,,values])=>[key,values[0]]));
saveFeedback(localStore,answers,'response:1',observedNow);
saveFeedback(localStore,answers,'response:1',observedNow);
assert.equal(readMeasurement(localStore,observedNow).responses.length,1);
assert.throws(()=>saveFeedback(localStore,answers,'response:2',observedNow),/One response/);
assert.throws(()=>saveFeedback(localStore,{...answers,pay:'SECRET'},'response:1',observedNow),/differs/);
const report=measurementExport(readMeasurement(localStore,observedNow),observedNow);
assert.equal(report.externalCohortSize,0);assert.equal(report.excludedFromPublicMetrics,true);
assert.equal(report.costWorksheet.marginalUserCost,null);assert.match(report.definitions.abandonment,/UNKNOWN/);
assert.equal(readMeasurement(localStore,observedNow+RETENTION+1).responses.length,0);
for(const hostile of ['{','x'.repeat(32769),JSON.stringify({...disabledMeasurement,schemaVersion:2})]){
  localData.set(KEY,hostile);assert.equal(eventTo(localStore,{id:'event:new',name:'analysis_opened'},observedNow),false);
  assert.equal(localData.get(KEY),hostile,'Unknown/corrupt data must remain byte-identical');
}
assert.equal(eventTo({getItem(){throw Error('Denied');}},{id:'event:denied',name:'analysis_opened'},observedNow),false);
const quotaStore={getItem:()=>JSON.stringify({...disabledMeasurement,enabled:true}),setItem(){throw Error('Quota');}};
assert.equal(eventTo(quotaStore,{id:'event:quota',name:'analysis_opened'},observedNow),false);
console.log('PASS optional internal measurement: disabled/no-op, typed privacy, idempotent/bounded events, separate feedback/retry/retention, honest cost unknowns and corrupt/denied/quota preservation.');

globalThis.window={location:{href:'http://127.0.0.1:5173/'}};
const calls=[];
globalThis.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({schemaVersion:1,reviewHash:'pinned'})};};
const exact='0.123456789012345678';
await api('/reviews',{draft:{quantity:exact},expectedRevision:7});
assert.equal(JSON.parse(calls[0].options.body).draft.quantity,exact);
assert.equal(calls[0].options.credentials,'omit');
assert.equal(calls[0].options.cache,'no-store');
assert.equal(calls[0].options.headers['X-BTL-Local'],'1');
await api('/catalog');
assert.equal(calls[1].options.method,'GET');assert.ok(!Object.hasOwn(calls[1].options,'body'));
const optionalReadController=new AbortController();
await api('/measurement/operational',undefined,{signal:optionalReadController.signal});
assert.equal(calls[2].options.signal,optionalReadController.signal,'Optional observation timeout must abort the actual request');
assert.equal(sessionPath('session:α'),'/sessions/session%3A%CE%B1');
const localView={metadata:{id:'session:one',artifact:'BTL-LOCAL-SESSION-1'},state:{revision:7}};
const observedView={metadata:{id:'session:observed',artifact:'BTL-OBSERVED-RESEARCH-SESSION-1'},state:{revision:7}};
const raw=command(localView,'ADVANCE',{targetNs:'1577838600000000000'});
assert.equal(raw.artifact,'BTL-TICK-EXECUTION-COMMAND-1');
assert.equal(command(observedView,'ADVANCE',{targetNs:'1577838600000000000'}).artifact,'BTL-OBSERVED-EXECUTION-COMMAND-1');
assert.throws(()=>command(observedView,'SEEK',{targetNs:'1577838600000000000'}),/do not support SEEK/);
assert.throws(()=>command({metadata:{id:'ambiguous'}},'ADVANCE',{}),/ambiguous Session model/);
assert.equal(raw.expectedRevision,7);assert.equal(raw.payload.targetNs,'1577838600000000000');
assert.notEqual(raw.commandId,command(localView,'ADVANCE',raw.payload).commandId);
globalThis.fetch=async()=>({ok:false,json:async()=>({detail:'REFUSED_STALE_REVISION'})});
await assert.rejects(()=>api('/reviews',{}),/REFUSED_STALE_REVISION/);
globalThis.fetch=async()=>({ok:true,json:async()=>({schemaVersion:2})});
await assert.rejects(()=>api('/catalog'),/Unsupported local response/);
const ui=readFileSync(new URL('../src/tickAlpha/TickAlpha.jsx',import.meta.url),'utf8');
for(const prohibited of ['useTrading','prototypeModel','localStorage','simulate trigger','manage('])assert.ok(!ui.includes(prohibited),'Alpha must not adopt a second financial truth: '+prohibited);
assert.ok(ui.includes('review.reviewHash')&&ui.includes("+'/confirm'"));
assert.ok(ui.includes('flight.current')&&ui.includes('loadWorkspace(view.metadata.id)'));
assert.equal(entryRoute({hostname:'localhost',search:'?tick-alpha=local'}),'workspace');
assert.equal(entryRoute({hostname:'127.0.0.1',search:'?legacy=local'}),'legacy');
assert.equal(entryRoute({hostname:'[::1]',search:'?tick-alpha=exness'}),'workspace');
for(const search of ['', '?legacy=local', '?tick-alpha=local', '?tick-alpha=exness',
  '?tick-review=local', '?trading-ux=prototype']){
  assert.equal(entryRoute({hostname:'research.example',search}),'hosted-home',search);
}
assert.equal(entryRoute({hostname:'research.example',
  search:'?page=account&session=saved&legacy=local'}),'account');
console.log('PASS tick-alpha transport exact strings, explicit revision/command identity, local-only opt-in and durable-review UI boundary.');

const view={state:{throughNs:'1577838600000000000'},chart:{timeframe:'1m',priceBasis:'EXACT_REVEALED_MID_DISPLAY_ONLY',volumeAvailable:false,candles:[
  {time:1577838540,open:'2000.015',high:'2001.015',low:'1999.015',close:'2000.515',event_count:4,incomplete:false,partialWindow:false},
]}};
const bars=displayBars(view);
assert.equal(bars[0].open,2000.015);assert.ok(!Object.hasOwn(bars[0],'volume'));
assert.deepEqual(Object.keys(bars[0]),['time','open','high','low','close']);
assert.equal(view.chart.candles[0].open,'2000.015');
assert.equal(replayTarget(view,4),'1577838660000000000');
const resumedView={...view,pendingReplayTargetNs:'1577838700000000000'};
for(const steps of [1,4,16])assert.equal(replayTarget(resumedView,steps),resumedView.pendingReplayTargetNs);
for(const pending of ['1577838600000000000','-1','1.5',1577838700000000000]){
  assert.throws(()=>replayTarget({...view,pendingReplayTargetNs:pending},1),/Invalid pending replay target/);
}
assert.equal(seekTarget('2020-01-01T00:30'),'1577838600000000000');
assert.equal(seekTarget('2020-02-29T12:34:56'),'1582979696000000000');
assert.equal(seekTarget('2000-02-29T00:00'),'951782400000000000');
for(const invalid of ['2025-02-30T12:00','2015-04-31T00:00','1900-02-29T00:00','2015-12-01T24:00','2015-13-01T00:00','2015-12-01T00:60','2015-12-01T00:00:60']){
  assert.throws(()=>seekTarget(invalid),/valid UTC/,'Invalid calendar/time must never silently normalize: '+invalid);
}
assert.throws(()=>replayTarget(view,1000));assert.throws(()=>seekTarget('2020-01-01T00:30Z'));
const future=structuredClone(view);future.chart.candles[0].time=1577838660;
assert.throws(()=>displayBars(future),/Unrevealed/);
const bad=structuredClone(view);bad.chart.candles[0].open=2000.015;
assert.throws(()=>displayBars(bad),/display price/);
const volume=structuredClone(view);volume.chart.volumeAvailable=true;
assert.throws(()=>displayBars(volume),/Invalid revealed/);
console.log('PASS revealed-only display projection, no fabricated volume, immutable exact wire prices and exact tick/UTC targets.');

const chartLines=[],removed=[],chartMarkers=[];
const series={createPriceLine:line=>{chartLines.push(line);return line;},removePriceLine:line=>removed.push(line)};
const projection={status:'COMPLETE',annotations:[{eventId:'fill:exact',timeNs:'1577838540000000000',price:'2000.02',side:'LONG',kind:'ENTRY_FILL',chronologyLimited:false}],orders:[{status:'ACTIVE',side:'LONG',entryPrice:'2000.02',entry:'2000',sl:'1998',tp:'2004'}]};
const priceLines=syncTickAnnotations({series,markerPlugin:{setMarkers:markers=>chartMarkers.push(...markers)},candles:bars,evidence:projection});
assert.equal(chartMarkers[0].id,'fill:exact');assert.equal(chartMarkers[0].time,1577838540);
assert.equal(chartMarkers[0].text,'Entry @ 2000.02');assert.equal(priceLines[0].price,2000.02);
assert.notEqual(priceLines[0].price,bars[0].open,'Fill annotation retains actual Ask, not candle mid');
assert.equal(projection.annotations[0].price,'2000.02');
syncTickAnnotations({series,markerPlugin:{setMarkers:markers=>assert.deepEqual(markers,[])},priceLines,candles:bars,evidence:{status:'UNAVAILABLE'}});
assert.equal(removed.length,3);
assert.equal(ratioLabel({numerator:'3',denominator:'7'},{percent:true}),'42.86%');
assert.equal(ratioLabel({numerator:'-45',denominator:'7'}),'-6.43');
assert.equal(ratioLabel(null),'Unavailable');assert.throws(()=>ratioLabel({numerator:'1',denominator:'0'}));
console.log('PASS actual fill identity/price chart annotation, unavailable-history clearing and exact rational display rounding.');

// An obsolete bootstrap must not spend a workspace worker slot or load a Session.
const bootstrapCalls=[];
globalThis.fetch=async(url,options)=>{bootstrapCalls.push({url,options});return {ok:true,json:async()=>({schemaVersion:1,methods:[],sessions:[]})};};
assert.equal(await loadResearchContext('session:obsolete',{active:()=>false}),null);
assert.equal(bootstrapCalls.length,1);
assert.equal(bootstrapCalls[0].options.method,'GET');
bootstrapCalls.length=0;
const reopened=await loadResearchContext('session:saved',{timeframe:'5m'});
assert.equal(bootstrapCalls.length,2);assert.ok(bootstrapCalls[1].url.endsWith('/sessions/session%3Asaved/view'));
assert.deepEqual(JSON.parse(bootstrapCalls[1].options.body),{timeframe:'5m'});
assert.ok(reopened.catalog&&reopened.view);
assert.ok(noticeText('REFUSED_REWIND_REQUIRES_FORK').includes('Create a separate Session'));
assert.ok(noticeText('REFUSED_REWIND_REQUIRES_FORK').includes('REFUSED_REWIND_REQUIRES_FORK'));
assert.equal(noticeText('UNKNOWN_BOUNDARY'),'UNKNOWN_BOUNDARY');
console.log('PASS obsolete-bootstrap cancellation, saved-session reconnect and honest refusal guidance without command mutation.');

const routed=[];
globalThis.fetch=async(url,options)=>{routed.push({url,options});return {ok:true,json:async()=>({schemaVersion:1})};};
globalThis.window={location:{href:'http://127.0.0.1:5173/'}};
assert.equal(pagePath('home'),'/?page=home');
window.location.href='http://127.0.0.1:5173/?session=session%3Asaved&tick-alpha=local&page=home';
assert.equal(pagePath(),'/?session=session%3Asaved&tick-alpha=local');
assert.equal(pagePath('home'),'/?session=session%3Asaved&tick-alpha=local&page=home');
assert.throws(()=>pagePath('https://evil.example/'));
window.location.href='http://127.0.0.1:5173/';
await api('/catalog');
assert.equal(routed.at(-1).options.headers['X-BTL-Source'],'historical');
assert.equal(sourceContext(),'historical');
await api('/sessions',{id:'session:month',name:'Late month',methodId:'method:test',initialBalance:'10000',startPeriod:'2015-11'});
assert.equal(JSON.parse(routed.at(-1).options.body).startPeriod,'2015-11');
assert.ok(!routed.at(-1).url.includes('?'),'Local API query guard remains intact');
globalThis.window.location.href='http://127.0.0.1:5173/?tick-alpha=local';
await api('/catalog');
assert.equal(routed.at(-1).options.headers['X-BTL-Source'],'synthetic');
assert.equal(sourceContext(),'synthetic');
delete globalThis.window;
assert.equal(sourceContext(),null);
assert.ok(noticeText('REFUSED_HISTORICAL_PERIOD').includes('no fallback feed'));
const observed={state:{throughNs:'1439166600000000000'},replayStepNs:'1000000000'};
assert.equal(replayTarget(observed,4),'1439166604000000000');
for(const invalid of ['0','-1','1000000000000',1,true,'1e9'])assert.throws(()=>replayTarget({...observed,replayStepNs:invalid},1));
// The Start month field moved from the old Create Session dialog into the New Session wizard.
const wizard=readFileSync(new URL('../src/tickAlpha/AlphaSessionWizard.jsx',import.meta.url),'utf8');
assert.ok(wizard.includes('name="startPeriod"')&&wizard.includes('Start month (UTC)'));
assert.ok(ui.includes("api('/sessions',{id:creationId.current"),'Session creation still sends the existing POST /sessions payload');
assert.ok(ui.includes("dialog==='ticket'"));
assert.ok(!ui.includes('synthetic feed · January 2020 fixture'));
console.log('PASS explicit historical/synthetic isolation, source period, bounded exact replay interval and one popup ticket.');
const historyView={metadata:{startPeriod:'2015-09'},state:{datasetId:'test:history',datasetVersion:'test:v1',throughNs:'1441067400000000000'}};
const pastPage={schemaVersion:1,artifact:'BTL-PAST-CHART-CONTEXT-1',datasetId:'test:history',datasetVersion:'test:v1',startTime:1438387200,endTime:1441065600,timeframe:'1m',priceBasis:'EXACT_REVEALED_MID_DISPLAY_ONLY',volumeAvailable:false,coverage:'UNKNOWN',executionAuthority:false,status:'READY',candles:[{time:1439164800,open:'1.001',high:'1.003',low:'1.001',close:'1.002'}],nextOffset:null};
assert.equal(historyPage(historyView,pastPage,'1m',0)[0].open,1.001);
for(const change of [{datasetId:'foreign'},{datasetVersion:'foreign'},{executionAuthority:true},{coverage:'COMPLETE'},{endTime:1441065660},{nextOffset:256},{endOfDataset:true},{status:'BUILDING'},{candles:[{...pastPage.candles[0],time:1441065600}]},{candles:[{...pastPage.candles[0],time:1439164801}]}])assert.throws(()=>historyPage(historyView,{...pastPage,...change},'1m',0));
assert.deepEqual(historyPage(historyView,{...pastPage,candles:[],status:'BUILDING'},'1m',0),[]);
console.log('PASS past OHLC context identity, exact price display, Session boundary, timeframe alignment, bounded pagination and future metadata refusal.');
