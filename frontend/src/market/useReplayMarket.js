import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {aggregateCandles,bucketTime} from './candles';
import {advanceReplayIndex} from './replayTransitions.js';
import {decodeHistoryRows} from './history';
export default function useReplayMarket(timeframe){
  const [savedDate]=useState(()=>{try{return localStorage.getItem('backtest-replay-time-v1');}catch{return null;}});
  const [daily,setDaily]=useState([]),olderLoading=useRef(false);
  const [state,setState]=useState({bars:[],index:-1,loading:!!savedDate,error:'',kind:'reset',revision:0}),request=useRef(0),catalog=useRef(null),nextChunk=useRef(0),extending=useRef(false);
  const start=useCallback(async date=>{
    const token=++request.current;setState(current=>({...current,loading:true,error:''}));
    try{
      const base=import.meta.env.BASE_URL+'market/decade/';
      const response=await fetch(base+'manifest.json');if(!response.ok)throw new Error('Price data unavailable.');
      const manifest=await response.json();const time=Date.parse(date)/1000;
      if(!Number.isFinite(time)||time<manifest.first||time>manifest.last)throw new Error('Choose a date between October 2016 and September 25, 2026.');
      const files=manifest.frames['1m'];const index=files.findIndex(file=>file.last>=time);
      const chunks=files.slice(Math.max(0,index-1),Math.min(files.length,index+3));
      const bars=(await Promise.all(chunks.map(async file=>{const chunk=await fetch(base+file.path);if(!chunk.ok)throw new Error('Price data unavailable.');return decodeHistoryRows(await chunk.json(),'1m');}))).flat();
      const cursor=bars.findIndex(bar=>bar.time>=time);if(cursor<0)throw new Error('No candle at this date.');
      if(token===request.current){catalog.current=manifest;nextChunk.current=Math.min(files.length,index+3);extending.current=false;setState(current=>({bars,index:cursor,loading:false,error:'',kind:'start',revision:current.revision+1}));}
      return bars[cursor].time;
    }catch(error){if(token===request.current)setState(current=>({...current,loading:false,error:error.message}));throw error;}
  },[]);
  const step=useCallback((direction=1)=>setState(current=>{if(current.index<0)return current;const next=advanceReplayIndex(current.bars,current.index,timeframe,direction);return {...current,index:next,kind:direction>0?'forward':'rewind',revision:current.revision+1};}),[timeframe]);
  const stop=useCallback(()=>{request.current++;try{localStorage.removeItem('backtest-replay-time-v1');}catch{/* Storage may be unavailable. */}setState(current=>({bars:[],index:-1,loading:false,error:'',kind:'stop',revision:current.revision+1}));},[]);
  const loadOlder=useCallback(async()=>{
    if(olderLoading.current||state.index<0||!catalog.current)return;
    const files=catalog.current.frames['1m'],first=files.findIndex(file=>file.last>=state.bars[0].time);if(first<=0)return;
    olderLoading.current=true;const token=request.current;
    try{const response=await fetch(import.meta.env.BASE_URL+'market/decade/'+files[first-1].path);if(!response.ok)throw new Error('Price data unavailable.');const rows=decodeHistoryRows(await response.json(),'1m');if(token===request.current)setState(current=>({...current,bars:[...rows,...current.bars],index:current.index+rows.length,kind:'prepend',revision:current.revision+1}));}finally{olderLoading.current=false;}
  },[state.index,state.bars]);
  useEffect(()=>{if(!['D','W','M'].includes(timeframe)||daily.length)return;const request=new AbortController();fetch(import.meta.env.BASE_URL+'market/decade/all-D.json',{signal:request.signal}).then(response=>response.json()).then(rows=>setDaily(decodeHistoryRows(rows,'D'))).catch(()=>{});return()=>request.abort();},[timeframe,daily.length]);
  useEffect(()=>{if(savedDate)start(savedDate).catch(()=>{});},[savedDate,start]);
  useEffect(()=>{if(state.index<0)return;try{localStorage.setItem('backtest-replay-time-v1',new Date(state.bars[state.index].time*1000).toISOString());}catch{/* In-memory replay remains available. */}},[state.bars,state.index]);
  useEffect(()=>{
    if(state.index<0||state.bars.length-state.index>1000||extending.current)return;
    const chunk=catalog.current?.frames['1m'][nextChunk.current];if(!chunk)return;
    extending.current=true;const token=request.current;
    fetch(import.meta.env.BASE_URL+'market/decade/'+chunk.path).then(async response=>{if(!response.ok)throw new Error('Price data unavailable.');const bars=decodeHistoryRows(await response.json(),'1m');if(token!==request.current)return;nextChunk.current++;setState(current=>({...current,bars:[...current.bars,...bars],error:''}));}).catch(error=>{if(token===request.current)setState(current=>({...current,error:error.message}));}).finally(()=>{if(token===request.current)extending.current=false;});
  },[state.index,state.bars]);
  const raw=useMemo(()=>state.bars.slice(0,state.index+1),[state.bars,state.index]);
  const candles=useMemo(()=>aggregateCandles(['D','W','M'].includes(timeframe)&&raw.length?[...daily.filter(bar=>bar.time<bucketTime(raw[0].time,'D')),...raw]:raw,timeframe),[raw,timeframe,daily]);
  const transition=useMemo(()=>({kind:state.kind,revision:state.revision,timeframe}),[state.kind,state.revision,timeframe]);
  return {...state,transition,active:state.index>=0,raw,candles,start,step,stop,loadOlder,atEnd:state.index>=state.bars.length-1};
}
