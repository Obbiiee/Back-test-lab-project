// Per-Session record of an unfinished replay target. A bounded backend ADVANCE can stop before its
// target and then only accepts the SAME target again, so the target is kept to let the user
// continue after cancel, error or reload. It is a navigation hint only: never balances, fills or
// outcomes, which always come from the server.
const valid=value=>Boolean(value)&&['ADVANCE','SEEK'].includes(value.kind)&&typeof value.target==='string'&&/^[0-9]{1,20}$/.test(value.target);
export function readPending(key){
  try{
    const raw=globalThis.localStorage.getItem(key);
    const value=raw?JSON.parse(raw):null;
    return valid(value)?{kind:value.kind,target:value.target}:null;
  }catch{return null;}
}
export function writePending(key,value){
  try{
    if(value===null)globalThis.localStorage.removeItem(key);
    else if(valid(value))globalThis.localStorage.setItem(key,JSON.stringify({kind:value.kind,target:value.target}));
  }catch{/* memory-only: Continue is then unavailable after reload */}
}
