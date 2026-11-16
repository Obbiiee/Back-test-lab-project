import {useEffect,useState} from 'react';
import {accountStorageKey} from './accountClient.js';
import {loadSessionWithMetadata,noticeText} from './client.js';

// A catalog page can omit a Session without making its direct URL invalid.
// Keep this lookup local to the screen and discard obsolete reads on navigation.
export function useSessionRead(sessionId,attempt,{analytics=false}={}){
  const [result,setResult]=useState(null);
  useEffect(()=>{
    if(!sessionId)return;
    const controller=new AbortController();
    const save=result=>{
      if(!controller.signal.aborted)setResult({sessionId,attempt,analytics,...result});
    };
    loadSessionWithMetadata(sessionId,{analytics,signal:controller.signal}).then(
      value=>save({status:'ready',value}),
      error=>save({status:'error',message:noticeText(error.message)}),
    );
    return()=>controller.abort();
  },[sessionId,attempt,analytics]);
  if(!sessionId)return {status:'idle'};
  if(result?.sessionId===sessionId&&result.attempt===attempt&&result.analytics===analytics)return result;
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

