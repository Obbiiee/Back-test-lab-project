import {accountStorageKey} from './accountClient.js';

export const money=value=>{if(value===null||value===undefined)return 'Unavailable';const text=String(value),neg=text.startsWith('-'),[whole,fraction]=text.replace(/^-/,'').split('.');return (neg?'-':'')+'$'+whole.replace(/\B(?=(\d{3})+(?!\d))/g,',')+(fraction?'.'+fraction:'');};
export const kindLabel=kind=>kind==='PROTOCOL'?'Protocol':'Free Style';
export const utc=ns=>ns?new Date(Number(BigInt(ns)/1000000n)).toISOString().slice(0,16).replace('T',' ')+' UTC':'—';

// Device-local convenience only: which Session this browser opened last. It is never
// used for money, fills or replay position; those always come from the server.
const LAST_KEY='riksora-last-session';
export function rememberSession(sessionId){try{globalThis.localStorage?.setItem(accountStorageKey(LAST_KEY),sessionId);}catch{/* storage may be blocked */}}
export function lastSession(){try{return globalThis.localStorage?.getItem(accountStorageKey(LAST_KEY))||null;}catch{return null;}}

