// Local transport only. Financial values stay exact strings; no browser settlement.
const ROOT='http://127.0.0.1:5188/api/v1/tick-alpha';
import {accountTransport,isAccountPage} from './accountClient.js';
export function id(prefix){return `${prefix}:${crypto.randomUUID()}`;}
export function sourceContext(){
  if(accountTransport()||isAccountPage())return 'synthetic';
  return typeof window==='undefined'?null:new URL(window.location.href).searchParams.get('tick-alpha')==='local'?'synthetic':'historical';
}
export async function api(path,body,{signal}={}){
  const account=accountTransport();
  if(account){
    const replay=/\/sessions\/[^/]+\/commands$/.test(path)&&['ADVANCE','SEEK'].includes(body?.kind);
    const queued=replay||/\/sessions\/[^/]+\/(view|bootstrap)$/.test(path);
    const jobId=queued?crypto.randomUUID():undefined;
    const bounded=signal?AbortSignal.any([signal,AbortSignal.timeout(30000)]):AbortSignal.timeout(30000);
    const uncertainReplay=()=>Error('Replay outcome requires reconciliation. Reload committed Session evidence before retrying.');
    let value;
    try{value=await account.client.request(account.root+path,{method:body===undefined?'GET':'POST',body,signal:bounded,jobId});}
    catch(error){
      if(jobId)void account.client.request(account.root+'/jobs/'+jobId+'/cancel',{method:'POST'}).catch(()=>{});
      if(replay)throw uncertainReplay();
      throw error;
    }
    while(value?.jobId){
      if(value.jobId!==jobId)throw Error('Unexpected research job; no state was imported.');
      if(value.state==='SUCCEEDED'){value=value.result;break;}
      if(!['QUEUED','RUNNING'].includes(value.state))throw Error(replay
        ?'Replay outcome requires reconciliation. Reload committed Session evidence before retrying.'
        :'Research calculation did not complete. Financial state is unchanged.');
      try{
        await new Promise((resolve,reject)=>{
          if(bounded.aborted)return reject(bounded.reason);
          const abort=()=>{clearTimeout(timer);reject(bounded.reason);};
          const timer=setTimeout(()=>{bounded.removeEventListener('abort',abort);resolve();},1000);
          bounded.addEventListener('abort',abort,{once:true});
        });
        value=await account.client.request(account.root+'/jobs/'+jobId,{signal:bounded});
      }catch(error){
        // Best-effort stop: replay cancellation requires committed-state
        // reconciliation and never claims an earlier attempt did not commit.
        void account.client.request(account.root+'/jobs/'+jobId+'/cancel',{method:'POST'}).catch(()=>{});
        if(replay)throw uncertainReplay();
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
  if(!response.ok)throw new Error(value.detail||'Local service unavailable');
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
  return {schemaVersion:1,artifact:'BTL-TICK-EXECUTION-COMMAND-1',sessionId:view.metadata.id,
    commandId:id('command'),expectedRevision:view.state.revision,kind,payload};
}

// Reads only; an obsolete StrictMode mount must not start another workspace read.
export async function loadResearchContext(selected,{active=()=>true,timeframe='1m'}={}){
  const catalog=await api('/catalog');
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
    REFUSED_JOURNAL_LIMIT:'This Session exceeds the complete journal snapshot budget (32 canonical orders). No partial export or reset was made.',
    PROTOCOL_BLOCKED:'Protocol rules blocked this order. Check the checklist and locked entry/exit rules.',
    LOCAL_BUSY:'The local service is busy. Wait for the current request, then retry.',
    REFUSED_ANALYSIS_LIMIT:'Analysis exceeded its bounded event budget. No partial result is shown.',
  };
  return explanations[message]?`${explanations[message]} (${message})`:message;
}
