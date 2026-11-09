// Financial values stay exact strings across hosted and loopback transports.
const ROOT='http://127.0.0.1:5188/api/v1/tick-alpha';
import {accountTransport,isAccountPage} from './accountClient.js';
import {isLocalReview} from '../tickReview/LocalOrigin.js';
export function id(prefix){return `${prefix}:${crypto.randomUUID()}`;}
function stableValue(value){
  if(Array.isArray(value))return value.map(stableValue);
  if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,stableValue(value[key])]));
  return value;
}
async function durableJobId(account,path,body){
  // A retry of the same operation must address the same durable queue record,
  // including after a lost HTTP response or a page reload.
  const identity=`${account.storageScope}\n${path}\n${JSON.stringify(stableValue(body??null))}`;
  const digest=new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(identity)));
  const bytes=digest.slice(0,16);bytes[6]=(bytes[6]&0x0f)|0x50;bytes[8]=(bytes[8]&0x3f)|0x80;
  const hex=[...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export function sourceContext(){
  if(accountTransport()||isAccountPage())return 'synthetic';
  return typeof window==='undefined'?null:new URL(window.location.href).searchParams.get('tick-alpha')==='local'?'synthetic':'historical';
}
export async function api(path,body,{signal}={}){
  const account=accountTransport();
  if(account){
    const replay=/\/sessions\/[^/]+\/commands$/.test(path)&&['ADVANCE','SEEK'].includes(body?.kind);
    const mutating=replay||(path==='/sessions'&&body!==undefined)||/\/replay-to$/.test(path);
    const queuedRead=/\/sessions\/[^/]+\/(view|bootstrap|chart-history)$/.test(path);
    // The queue reuses completed results by job ID. A new read must see the
    // current committed revision; only retries of a mutation reuse its ID.
    const jobId=mutating?await durableJobId(account,path,body):queuedRead?crypto.randomUUID():undefined;
    const bounded=signal?AbortSignal.any([signal,AbortSignal.timeout(30000)]):AbortSignal.timeout(30000);
    const uncertain=()=>Object.assign(Error('UNKNOWN: durable operation outcome is not yet known. Reconcile its job or authoritative Session/receipt before retrying.'),{code:'UNKNOWN',jobId});
    let value;
    try{value=await account.client.request(account.root+path,{method:body===undefined?'GET':'POST',body,signal:bounded,jobId});}
    catch(error){
      const definitiveRefusal=[400,401,403,404,409,422,426,429].includes(error?.status);
      if(mutating&&!definitiveRefusal)throw uncertain();
      throw error;
    }
    if(jobId&&['QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','EXPIRED','RECONCILE_REQUIRED'].includes(value?.state)&&!value?.jobId){
      if(mutating)throw uncertain();
      throw Error('Queued research response omitted its durable job identity.');
    }
    while(value?.jobId){
      if(value.jobId!==jobId){
        if(mutating)throw uncertain();
        throw Error('Unexpected research job; no state was imported.');
      }
      if(value.state==='SUCCEEDED'){value=value.result;break;}
      if(!['QUEUED','RUNNING'].includes(value.state)){
        if(mutating)throw uncertain();
        throw Object.assign(Error(`Research job ended in ${value.state}.`),{code:value.state,jobId});
      }
      try{
        await new Promise((resolve,reject)=>{
          if(bounded.aborted)return reject(bounded.reason);
          const abort=()=>{clearTimeout(timer);reject(bounded.reason);};
          const timer=setTimeout(()=>{bounded.removeEventListener('abort',abort);resolve();},1000);
          bounded.addEventListener('abort',abort,{once:true});
        });
        value=await account.client.request(account.root+'/jobs/'+jobId,{signal:bounded});
      }catch(error){
        // Mutations are never cancelled on a transport timeout: cancellation
        // races the commit and can only leave an UNKNOWN outcome.
        if(mutating)throw uncertain();
        throw error;
      }
    }
    if(value?.schemaVersion!==1){
      if(mutating)throw uncertain();
      throw Error('Unsupported workspace response; no state was imported.');
    }
    return value;
  }
  if(isAccountPage()||typeof window==='undefined'||!isLocalReview(new URL(window.location.href).hostname)){
    throw Error('Sign in to continue. No private local fallback was requested.');
  }
  const source=sourceContext();
  const response=await fetch(ROOT+path,{method:body===undefined?'GET':'POST',cache:'no-store',
    credentials:'omit',headers:{'X-BTL-Local':'1',...(source?{'X-BTL-Source':source}:{}),...(body===undefined?{}:{'Content-Type':'application/json'})},
    ...(body===undefined?{}:{body:JSON.stringify(body)}),signal:signal??AbortSignal.timeout(30000)});
  const value=await response.json();
  // `status` lets callers tell a definitive refusal from an unknown outcome (confirmOutcome.js).
  if(!response.ok)throw Object.assign(new Error(value.detail||'Local service unavailable'),{status:response.status});
  if(value.schemaVersion!==1)throw new Error('Unsupported local response; no state was imported.');
  return value;
}
export function sessionPath(session){return `/sessions/${encodeURIComponent(session)}`;}
export function orderHistoryPagePath(sessionId,{limit=64,afterSequence=null,revision=null}={}){
  if(typeof sessionId!=='string'||!sessionId||!Number.isInteger(limit)||limit<1||limit>256)
    throw Error('Invalid order history page request.');
  if(afterSequence!==null&&(!Number.isSafeInteger(afterSequence)||afterSequence<0))
    throw Error('Invalid order history cursor.');
  if(revision!==null&&(!Number.isSafeInteger(revision)||revision<0))
    throw Error('Invalid order history revision.');
  const query=new URLSearchParams({limit:String(limit)});
  if(afterSequence!==null)query.set('after_sequence',String(afterSequence));
  if(revision!==null)query.set('revision',String(revision));
  return `${sessionPath(sessionId)}/orders/pages?${query}`;
}
export function validateOrderHistoryPage(page,sessionId,{limit=64,afterSequence=null,revision=null}={}){
  if(!page||page.artifact!=='BTL-ORDER-HISTORY-PAGE-1'||page.sessionId!==sessionId||
     !Number.isSafeInteger(page.revision)||page.revision<0||!Number.isSafeInteger(page.total)||page.total<0||
     !Array.isArray(page.records)||page.records.length>limit||typeof page.complete!=='boolean')
    throw Error('Unsupported or incomplete order history page.');
  if(revision!==null&&page.revision!==revision)throw Error('Order history revision changed; reload from the first page.');
  let prior=afterSequence===null?-1:afterSequence;
  for(const record of page.records){
    if(!record||typeof record.orderId!=='string'||!record.order||typeof record.order!=='object'||
       !Number.isSafeInteger(record.sequence)||record.sequence<=prior||
       !Number.isSafeInteger(record.finalizedRevision)||record.finalizedRevision<1||
       typeof record.recordHash!=='string'||!/^[a-f0-9]{64}$/.test(record.recordHash))
      throw Error('Invalid order history record.');
    prior=record.sequence;
  }
  const cursor=page.nextCursor;
  if(cursor!==null&&(!cursor||cursor.revision!==page.revision||!Number.isSafeInteger(cursor.afterSequence)||
     cursor.afterSequence!==prior||page.records.length===0))throw Error('Invalid order history cursor response.');
  if(page.complete!==(cursor===null))throw Error('Inconsistent order history completion state.');
  return page;
}
export async function loadOrderHistoryPage(sessionId,options={}){
  if(!accountTransport())throw Error('Historical order pages require an authenticated workspace.');
  const path=orderHistoryPagePath(sessionId,options);
  const page=await api(path,undefined,{signal:options.signal});
  return validateOrderHistoryPage(page,sessionId,options);
}
export function analyticsPagePath(sessionId,{limit=32,offset=0,revision=null}={}){
  if(typeof sessionId!=='string'||!sessionId||!Number.isInteger(limit)||limit<1||limit>64||
     !Number.isSafeInteger(offset)||offset<0)
    throw Error('Invalid analytics page request.');
  if(revision!==null&&(!Number.isSafeInteger(revision)||revision<0))
    throw Error('Invalid analytics revision.');
  const query=new URLSearchParams({limit:String(limit),offset:String(offset)});
  if(revision!==null)query.set('revision',String(revision));
  return `${sessionPath(sessionId)}/analytics/pages?${query}`;
}
export function validateAnalyticsPage(page,sessionId,{limit=32,offset=0,revision=null}={}){
  if(!page||page.artifact!=='BTL-OBSERVED-ANALYTICS-PAGE-1'||page.sessionId!==sessionId||
     !Number.isSafeInteger(page.revision)||page.revision<0||!Array.isArray(page.completed)||
     page.completed.length>limit||!['BUILDING','COMPLETE'].includes(page.status))
    throw Error('Unsupported or invalid analytics page.');
  if(page.completed.some(row=>!row||typeof row.id!=='string'||row.status!=='CLOSED'))
    throw Error('Invalid analytics trade row.');
  if(revision!==null&&page.revision!==revision)
    throw Error('Analytics revision changed; reload from the first page.');
  if(page.status==='BUILDING'){
    if(page.completed.length!==0||!Number.isSafeInteger(page.processedEvents)||
       !Number.isSafeInteger(page.totalEvents)||page.processedEvents<0||
       page.processedEvents>page.totalEvents||page.nextTradeOffset!==null)
      throw Error('Invalid analytics build progress.');
    return page;
  }
  if(!page.metrics||typeof page.metrics!=='object'||!page.account||typeof page.account!=='object'||
     !page.provenance||typeof page.provenance!=='object'||
     (page.nextTradeOffset!==null&&(!Number.isSafeInteger(page.nextTradeOffset)||
       page.nextTradeOffset<offset+page.completed.length)))
    throw Error('Invalid complete analytics page.');
  return page;
}
export async function loadAnalyticsPage(sessionId,options={}){
  if(!accountTransport())throw Error('Analytics pages require an authenticated workspace.');
  const path=analyticsPagePath(sessionId,options);
  const page=await api(path,undefined,{signal:options.signal});
  return validateAnalyticsPage(page,sessionId,options);
}
export function pagePath(page=null){
  if(page!==null&&page!=='home')throw Error('Unsupported workspace page');
  const url=new URL(typeof window==='undefined'?'http://localhost/':window.location.href);
  if(isAccountPage()){url.searchParams.delete('session');return url.pathname+'?page=account';}
  url.searchParams.delete('page');
  if(page)url.searchParams.set('page',page);
  return url.pathname+url.search;
}
// Testing hub: same entry and source, no selected Session (account page keeps its own route).
export function sessionsPath(){
  const url=new URL(typeof window==='undefined'?'http://localhost/':window.location.href);
  url.searchParams.delete('session');url.searchParams.delete('page');
  if(isAccountPage())url.searchParams.set('page','account');
  return url.pathname+url.search;
}
export function selectSessionUrl(session){
  const url=new URL(window.location.href);
  url.searchParams.set('session',session);
  window.history.replaceState(null,'',url);
}
export async function replayObservedTo(view,targetNs,timeframe){
  const account=accountTransport();
  if(!account||view.metadata.artifact!=='BTL-OBSERVED-RESEARCH-SESSION-1')throw Error('Forward jump requires a hosted observed Session.');
  if(typeof targetNs!=='string'||!/^(0|[1-9][0-9]{0,19})$/.test(targetNs)||
    BigInt(targetNs)<=BigInt(view.state.throughNs))throw Error('Choose a time after the saved replay position.');
  if(view.pendingReplayTargetNs!=null&&view.pendingReplayTargetNs!==targetNs){
    throw Error('Continue the saved replay target before choosing another time.');
  }
  const sessionId=view.metadata.id;
  const path=sessionPath(sessionId)+'/replay-to';
  const request={schemaVersion:1,artifact:'BTL-OBSERVED-REPLAY-TO-1',sessionId,expectedRevision:view.state.revision,targetNs,timeframe};
  const requestId=(await durableJobId(account,path,request)).replaceAll('-','');
  if(accountTransport()!==account)throw Error('Account changed before replay could start.');
  const result=await api(path,{...request,requestId});
  if(accountTransport()!==account||result.artifact!=='BTL-OBSERVED-REPLAY-TO-RESULT-1'||result.requestId!==requestId||
    result.sessionId!==sessionId||result.targetNs!==targetNs||result.view?.metadata?.id!==sessionId||
    result.view?.state?.throughNs!==result.throughNs||!Number.isSafeInteger(result.view?.state?.revision)||
    result.view.state.revision<request.expectedRevision||typeof result.throughNs!=='string'||
    !/^(0|[1-9][0-9]{0,19})$/.test(result.throughNs)||BigInt(result.throughNs)<BigInt(view.state.throughNs)||
    BigInt(result.throughNs)>BigInt(targetNs)||result.targetReached!==(result.throughNs===targetNs)){
    throw Error('Replay result could not be verified. Reopen the saved Session before continuing.');
  }
  return result;
}

export function command(view,kind,payload){
  const artifact=view?.metadata?.artifact;
  const dialect=artifact==='BTL-LOCAL-SESSION-1'?'BTL-TICK-EXECUTION-COMMAND-1':
    artifact==='BTL-OBSERVED-RESEARCH-SESSION-1'?'BTL-OBSERVED-EXECUTION-COMMAND-1':null;
  if(!dialect)throw Error('Unsupported or ambiguous Session model. Reload the authoritative Session metadata.');
  if(dialect==='BTL-OBSERVED-EXECUTION-COMMAND-1'&&kind==='SEEK')
    throw Error('Observed Sessions do not support SEEK commands.');
  return {schemaVersion:1,artifact:dialect,sessionId:view.metadata.id,
    commandId:id('command'),expectedRevision:view.state.revision,kind,payload};
}

async function productPage(path,artifact,after=null,project=value=>value){
  const query=new URLSearchParams({limit:'50'});if(after)query.set('after',after);
  const page=await api(`${path}${path.includes('?')?'&':'?'}${query}`);
  if(page.artifact!==artifact||!Array.isArray(page.items)||typeof page.complete!=='boolean')
    throw Error('Unsupported workspace page; no state was imported.');
  if(!page.complete&&(typeof page.nextCursor!=='string'||page.nextCursor===after))
    throw Error('Workspace pagination did not advance.');
  return {...page,items:page.items.map(project)};
}

export async function loadProductCatalog(){
  const catalog=await api('/catalog');
  if(accountTransport()){
    const [families,sessions]=await Promise.all([
      productPage('/method-families?includeArchived=true','BTL-METHOD-FAMILY-PAGE-1'),
      productPage('/sessions','BTL-SESSION-PAGE-1',null,item=>({
        ...item.metadata,revision:item.revision,
        financialCountsStatus:item.financialCountsStatus,
      })),
    ]);
    const methodFamilies=families.items.map(family=>({...family,versions:[{
      version:family.latestVersion,methodId:family.latestMethodId,method:family.current,
    }]}));
    const methods=methodFamilies.map(family=>({
      ...family.current,methodFamilyId:family.familyId,methodVersion:family.latestVersion,
      methodFamilyRevision:family.revision,methodArchived:family.archived,methodLatest:true,
    }));
    return {...catalog,methods,methodFamilies,sessions:sessions.items,
      productPagination:{methods:{cursor:families.nextCursor,complete:families.complete},
        sessions:{cursor:sessions.nextCursor,complete:sessions.complete}}};
  }
  return catalog;
}

export async function loadMoreProductCatalog(catalog,kind){
  if(!accountTransport()||!catalog?.productPagination?.[kind])
    throw Error('Workspace pagination is unavailable. Reload the workspace.');
  const state=catalog.productPagination[kind];
  if(state.complete||typeof state.cursor!=='string')return catalog;
  if(kind==='methods'){
    const page=await productPage('/method-families?includeArchived=true','BTL-METHOD-FAMILY-PAGE-1',state.cursor);
    const families=page.items.map(family=>({...family,versions:[{
      version:family.latestVersion,methodId:family.latestMethodId,method:family.current,
    }]}));
    const methods=families.map(family=>({...family.current,methodFamilyId:family.familyId,
      methodVersion:family.latestVersion,methodFamilyRevision:family.revision,
      methodArchived:family.archived,methodLatest:true}));
    return {...catalog,methods:[...catalog.methods,...methods],
      methodFamilies:[...catalog.methodFamilies,...families],
      productPagination:{...catalog.productPagination,methods:{cursor:page.nextCursor,complete:page.complete}}};
  }
  if(kind==='sessions'){
    const page=await productPage('/sessions','BTL-SESSION-PAGE-1',state.cursor,item=>({
      ...item.metadata,revision:item.revision,financialCountsStatus:item.financialCountsStatus,
    }));
    return {...catalog,sessions:[...catalog.sessions,...page.items],
      productPagination:{...catalog.productPagination,sessions:{cursor:page.nextCursor,complete:page.complete}}};
  }
  throw Error('Unknown workspace page.');
}

export async function loadJournalPage(sessionId,cursor=null){
  if(typeof sessionId!=='string'||!sessionId)throw Error('Journal Session is unavailable.');
  const query=new URLSearchParams({limit:'32'});if(cursor)query.set('cursor',cursor);
  const page=await api(`${sessionPath(sessionId)}/journal/pages?${query}`);
  if(page.artifact!=='BTL-TICK-JOURNAL-PAGE-1'||!Array.isArray(page.orders)||!Array.isArray(page.notes)||
      !Number.isSafeInteger(page.totalOrders)||typeof page.complete!=='boolean')
    throw Error('Unsupported Journal page; no state was imported.');
  if(!page.complete&&(typeof page.nextCursor!=='string'||page.nextCursor===cursor))
    throw Error('Journal pagination did not advance.');
  return page;
}

export async function createMethodVersion(family,method){
  if(!accountTransport())throw Error('Method versioning requires an authenticated workspace.');
  if(!family||typeof family.familyId!=='string'||!Number.isSafeInteger(family.revision))
    throw Error('Method family revision is unavailable. Reload before creating a version.');
  return api(`/method-families/${encodeURIComponent(family.familyId)}/versions`,
    {expectedRevision:family.revision,method});
}

export async function loadMethodVersionPage(familyId,cursor=null){
  if(typeof familyId!=='string'||!familyId)throw Error('Method family is unavailable.');
  const query=new URLSearchParams({limit:'25'});if(cursor)query.set('cursor',cursor);
  const page=await api(`/method-families/${encodeURIComponent(familyId)}/versions?${query}`);
  if(page.artifact!=='BTL-METHOD-VERSION-PAGE-1'||page.familyId!==familyId||
      !Number.isSafeInteger(page.revision)||!Array.isArray(page.versions)||typeof page.complete!=='boolean')
    throw Error('Unsupported Method version page; no state was imported.');
  if(!page.complete&&(typeof page.nextCursor!=='string'||page.nextCursor===cursor))
    throw Error('Method version pagination did not advance.');
  return page;
}

export async function loadMethodFamily(familyId){
  if(typeof familyId!=='string'||!familyId)throw Error('Method family is unavailable.');
  const [detail,page]=await Promise.all([
    api(`/method-families/${encodeURIComponent(familyId)}`),loadMethodVersionPage(familyId),
  ]);
  if(detail.artifact!=='BTL-METHOD-FAMILY-1'||detail.family?.familyId!==familyId)
    throw Error('Unsupported Method family; no state was imported.');
  return {...detail.family,versions:page.versions,nextVersionCursor:page.nextCursor,revision:page.revision};
}

export async function setMethodArchived(family,archived){
  if(!accountTransport())throw Error('Method lifecycle requires an authenticated workspace.');
  if(!family||typeof family.familyId!=='string'||!Number.isSafeInteger(family.revision))
    throw Error('Method family revision is unavailable. Reload before changing lifecycle.');
  return api(`/method-families/${encodeURIComponent(family.familyId)}/lifecycle`,
    {expectedRevision:family.revision,archived});
}

export async function loadResearchContext(selected,{active=()=>true,timeframe='1m'}={}){
  const catalog=await loadProductCatalog();
  if(!active())return null;
  const view=selected?await api(sessionPath(selected)+'/view',{timeframe}):null;
  return active()?{catalog,view}:null;
}

export function noticeText(message){
  const explanations={
    REFUSED_HISTORICAL_PERIOD:'Choose a month with observations in the configured source year. Unavailable months have no fallback feed.',
    REFUSED_REWIND_REQUIRES_FORK:'This Session already has financial history. Create a separate Session to replay an earlier time.',
    REFUSED_STALE_REVISION:'The saved Session changed. Reload it and review the action again.',
    REFUSED_STALE_NOTE:'Another edit changed this note. Reload the journal, compare with your retained draft, then explicitly save again.',
    PROTOCOL_BLOCKED:'Protocol rules blocked this order. Check the checklist and locked entry/exit rules.',
    LOCAL_BUSY:'The local service is busy. Wait for the current request, then retry.',
  };
  return explanations[message]?`${explanations[message]} (${message})`:message;
}
