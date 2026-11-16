import {useEffect,useState} from 'react';
import {accountStorageKey} from './accountClient.js';
import {loadMethodFamilyRecord,loadMethodRecord,loadSessionWithMetadata,noticeText} from './client.js';

// A catalog page can omit a Session without making its direct URL invalid.
// Keep this lookup local to the screen and discard obsolete reads on navigation.
export function useSessionRead(sessionId,attempt,{analytics=false}={}){
  return useProductRecord(sessionId,attempt,loadSessionWithMetadata,analytics);
}

export function useMethodRead(methodId,attempt){
  return useProductRecord(methodId,attempt,loadMethodRecord);
}

export function useMethodFamilyRead(familyId,attempt){
  return useProductRecord(familyId,attempt,loadMethodFamilyRecord);
}

function useProductRecord(id,attempt,load,analytics=false){
  const [result,setResult]=useState(null);
  useEffect(()=>{
    if(!id)return;
    const controller=new AbortController();
    const save=result=>{
      if(!controller.signal.aborted)setResult({id,attempt,analytics,...result});
    };
    load(id,{analytics,signal:controller.signal}).then(
      value=>save({status:'ready',value}),
      error=>save({status:'error',message:noticeText(error.message)}),
    );
    return()=>controller.abort();
  },[id,attempt,load,analytics]);
  if(!id)return {status:'idle'};
  if(result?.id===id&&result.attempt===attempt&&result.analytics===analytics)return result;
  return {status:'loading'};
}

export const money=value=>{if(value===null||value===undefined)return 'Unavailable';const text=String(value),neg=text.startsWith('-'),[whole,fraction]=text.replace(/^-/,'').split('.');return (neg?'-':'')+'$'+whole.replace(/\B(?=(\d{3})+(?!\d))/g,',')+(fraction?'.'+fraction:'');};
export const kindLabel=kind=>kind==='PROTOCOL'?'Protocol':'Free Style';
export const utc=ns=>ns?new Date(Number(BigInt(ns)/1000000n)).toISOString().slice(0,16).replace('T',' ')+' UTC':'—';

// Device-local convenience only: which Session this browser opened last. It is never
// used for money, fills or replay position; those always come from the server.
const LAST_KEY='riksora-last-session';
export function rememberSession(sessionId){try{globalThis.localStorage?.setItem(accountStorageKey(LAST_KEY),sessionId);}catch{/* storage may be blocked */}}
export function lastSession(){try{return globalThis.localStorage?.getItem(accountStorageKey(LAST_KEY))||null;}catch{return null;}}

