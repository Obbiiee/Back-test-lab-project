// Local transport only. Financial values stay exact strings; no browser settlement.
const ROOT='http://127.0.0.1:5188/api/v1/tick-alpha';
export function id(prefix){return `${prefix}:${crypto.randomUUID()}`;}
export async function api(path,body){
  const response=await fetch(ROOT+path,{method:body===undefined?'GET':'POST',cache:'no-store',
    credentials:'omit',headers:{'X-BTL-Local':'1',...(body===undefined?{}:{'Content-Type':'application/json'})},
    ...(body===undefined?{}:{body:JSON.stringify(body)})});
  const value=await response.json();
  if(!response.ok)throw new Error(value.detail||'Local service unavailable');
  if(value.schemaVersion!==1)throw new Error('Unsupported local response; no state was imported.');
  return value;
}
export function sessionPath(session){return `/sessions/${encodeURIComponent(session)}`;}
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
    REFUSED_REWIND_REQUIRES_FORK:'This Session already has financial history. Create a separate Session to replay an earlier time.',
    REFUSED_STALE_REVISION:'The saved Session changed. Reload it and review the action again.',
    PROTOCOL_BLOCKED:'Protocol rules blocked this order. Check the checklist and locked entry/exit rules.',
    LOCAL_BUSY:'The local service is busy. Wait for the current request, then retry.',
    REFUSED_ANALYSIS_LIMIT:'Analysis exceeded its bounded event budget. No partial result is shown.',
  };
  return explanations[message]?`${explanations[message]} (${message})`:message;
}
