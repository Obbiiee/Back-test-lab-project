// Local transport only. Financial values stay exact strings; no browser settlement.
const ROOT='http://127.0.0.1:5188/api/v1/tick-alpha';
import {accountTransport,isAccountPage} from './accountClient.js';
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
    const queued=replay||(/^\/sessions$/.test(path))||/\/sessions\/[^/]+\/(view|bootstrap|chart-history|replay-to)$/.test(path);
    const mutating=replay||path==='/sessions'||/\/replay-to$/.test(path);
    const jobId=queued?await durableJobId(account,path,body):undefined;
    const bounded=signal?AbortSignal.any([signal,AbortSignal.timeout(30000)]):AbortSignal.timeout(30000);
    const uncertain=()=>Object.assign(Error('UNKNOWN: durable operation outcome is not yet known. Reconcile its job or authoritative Session/receipt before retrying.'),{code:'UNKNOWN',jobId});
    let value;
    try{value=await account.client.request(account.root+path,{method:body===undefined?'GET':'POST',body,signal:bounded,jobId});}
    catch(error){
      const definitiveRefusal=[400,401,403,404,409,422,426,429].includes(error?.status);
      if(mutating&&!definitiveRefusal)throw uncertain();
      throw error;
    }
    if(queued&&['QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','EXPIRED','RECONCILE_REQUIRED'].includes(value?.state)&&!value?.jobId){
      if(mutating)throw uncertain();
      throw Error('Queued research response omitted its durable job identity.');
    }
    while(value?.jobId){
      if(value.jobId!==jobId)throw Error('Unexpected research job; no state was imported.');
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
    if(value?.schemaVersion!==1)throw Error('Unsupported workspace response; no state was imported.');
    return value;
  }
  if(isAccountPage())throw Error('Sign in to continue. No private local fallback was requested.');
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
