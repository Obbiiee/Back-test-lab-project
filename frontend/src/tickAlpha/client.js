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
