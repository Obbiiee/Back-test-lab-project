import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { addQuote, aggregateCandles, parseQuote } from './candles';
import { decodeHistoryRows, mergeHistory, validateHistory } from './history.js';
const KEY='backtest-xau-goldapi-sampled-1m-v1';
function readCache(){try{const value=JSON.parse(localStorage.getItem(KEY)||'[]');return Array.isArray(value)?value.filter(bar=>[bar.time,bar.open,bar.high,bar.low,bar.close].every(Number.isFinite)).slice(-30000):[];}catch{return [];}}
const base=import.meta.env.BASE_URL+'market/';
export default function useGoldMarket(timeframe, enabled) {
  const [bars,setBars]=useState(readCache),[status,setStatus]=useState('Connecting'),[updatedAt,setUpdatedAt]=useState(null);
  const [catalog,setCatalog]=useState(null),[history,setHistory]=useState({timeframe:null,candles:[],loaded:[]});
  const chunks=useRef(new Map()),generation=useRef(0),loading=useRef(false);
  useEffect(()=>{
    if(!enabled)return;
    const request=new AbortController();
    async function read(){
      try{
        const response=await fetch(base+'decade/manifest.json',{signal:request.signal});
        if(!response.ok)throw new Error('Manifest not ready');
        const manifest=await response.json();
        if(manifest.symbol!=='XAUUSD'||!manifest.frames)throw new Error('Invalid catalog');
        if(!request.signal.aborted)setCatalog(manifest);
      }catch{
        if(request.signal.aborted)return;
        // Preserve the existing archive until the larger dataset is published.
        try{const response=await fetch(base+'xauusd-history.json',{signal:request.signal});if(!response.ok)throw new Error('History unavailable');const value=validateHistory(await response.json());if(!request.signal.aborted)setCatalog({fallback:value});}catch{/* A live feed remains usable when the archive is unavailable. */}
      }
    }
    read();return()=>request.abort();
  },[enabled]);
  const loadChunks=useCallback(async(selected,token)=>{
    const rows=await Promise.all(selected.map(async chunk=>{
      const key=chunk.path;
      if(!chunks.current.has(key)){
        const response=await fetch(base+'decade/'+key);
        if(!response.ok)throw new Error('Price data unavailable');
        chunks.current.set(key,decodeHistoryRows(await response.json(),timeframe));
      }
      return chunks.current.get(key);
    }));
    if(token!==generation.current)return;
    setHistory({timeframe,candles:aggregateCandles(rows.flat(),timeframe),loaded:selected});
  },[timeframe]);
  useEffect(()=>{
    const token=++generation.current;loading.current=false;
    if(!catalog||!enabled)return;
    async function initialize(){
      if(catalog.fallback){setHistory({timeframe,candles:aggregateCandles(catalog.fallback.candles,timeframe),loaded:[]});return;}
      const files=catalog.frames[timeframe]??[];
      // Intraday history is loaded in chunks as the user pans left.
      const count={'1m':2,'3m':3,'5m':4,'15m':6,'30m':12,'1h':18,'2h':24,'4h':36}[timeframe]??files.length;
      try{await loadChunks(files.slice(-count),token);}catch{/* Keep the live chart when a historical chunk fails. */}
    }
    initialize();return()=>{generation.current=token+1;};
  },[catalog,enabled,timeframe,loadChunks]);
  const loadOlder=useCallback(async()=>{
    if(loading.current||!catalog?.frames||history.timeframe!==timeframe||!history.loaded.length)return;
    const files=catalog.frames[timeframe],first=files.findIndex(chunk=>chunk.path===history.loaded[0].path);
    if(first<=0)return;
    loading.current=true;const token=generation.current;
    try{await loadChunks([files[first-1],...history.loaded],token);}finally{if(token===generation.current)loading.current=false;}
  },[catalog,history,timeframe,loadChunks]);
  useEffect(()=>{
    if(!enabled)return;
    let disposed=false,timer,request;
    async function poll(){
      request=new AbortController();const timeout=setTimeout(()=>request.abort(),12000);
      try{
        const response=await fetch('https://api.gold-api.com/price/XAU',{signal:request.signal});
        if(!response.ok)throw new Error('HTTP '+response.status);
        const quote=parseQuote(await response.json());if(disposed)return;
        setBars(current=>addQuote(current,quote));setUpdatedAt(quote.time);
        setStatus(Date.now()/1000-quote.time>120?'stale':'connected');
      }catch{if(!disposed)setStatus('disconnected');}
      finally{clearTimeout(timeout);if(!disposed)timer=setTimeout(poll,30000);}
    }
    poll();return()=>{disposed=true;clearTimeout(timer);request?.abort();};
  },[enabled]);
  useEffect(()=>{try{localStorage.setItem(KEY,JSON.stringify(bars));}catch{/* Storage full: in-memory feed continues. */}},[bars]);
  const merged=useMemo(()=>mergeHistory(history.timeframe===timeframe?history.candles:[],bars,timeframe),[history,bars,timeframe]);
  return {...merged,status,updatedAt,loadOlder,liveBars:bars};
}
