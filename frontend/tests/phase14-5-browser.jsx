// Synthetic fixture. Production never imports these controls or instrumentation.
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import useReplayMarket from '../src/market/useReplayMarket.js';
import useTrading from '../src/trading/useTrading.js';
import useNews from '../src/news/useNews.js';
import NewsPanel from '../src/news/NewsPanel.jsx';
import { NewsRepository } from '../src/news/eventRepository.js';
import CandleChart from '../src/components/CandleChart.jsx';
import { productionRegistry } from '../src/indicators/productionRegistry.js';
import { NewsMarkerAdapter, markerGroups } from '../src/news/NewsMarkerAdapter.js';
import { validateDataset } from '../src/news/eventValidation.js';
import { EventIndex } from '../src/news/eventIndex.js';
import { pilot, sparsePilot, START } from './phase14-5-fixtures.mjs';
import '../src/FxWorkspace.css';
const errors=[];
window.addEventListener('error',event=>errors.push(event.message));
window.addEventListener('unhandledrejection',event=>errors.push(String(event.reason)));
const instances=new Set(), attach=NewsMarkerAdapter.prototype.attached;
NewsMarkerAdapter.prototype.attached=function(input){instances.add(this);return attach.call(this,input);};
export default function Harness(){
 const [frame,setFrame]=useState('15m'),[command,setCommand]=useState(null),[report,setReport]=useState(''),[open,setOpen]=useState(true),[height,setHeight]=useState(400),[mounted,setMounted]=useState(true);
 const replay=useReplayMarket(frame),trading=useTrading(replay.raw,replay.active,replay.transition);
 const news=useNews({replay,trading,timeframe:frame,setPlaying:()=>{},chartCommand:setCommand,openPanel:setOpen});
 const start=async()=>{const time=await replay.start('2024-06-03T12:00:00Z');trading.reset(time);};
 const storage=async()=>{
  const repository=new NewsRepository(indexedDB,'backtest-news-isolated-browser-test');
  const a=JSON.stringify(pilot()),b=pilot();b.version='2';
  await repository.replace(a);await repository.replace(JSON.stringify(b));
  const conflicting=structuredClone(b);conflicting.provenance.source='Different source';
  let conflictRejected=false;try{await repository.replace(JSON.stringify(conflicting));}catch{conflictRejected=true;}
  if(!conflictRejected)throw Error('Reused version was overwritten');
  const reloaded=await repository.load();if(reloaded.record.dataset.version!=='2')throw Error('Reload failed');
  const db=await repository.open();
  await new Promise((resolve,reject)=>{const tx=db.transaction('datasets','readwrite');tx.objectStore('datasets').put({schemaVersion:1,raw:JSON.stringify(b),hash:'CORRUPT',sourceHash:'CORRUPT'},JSON.stringify([b.datasetId,b.version]));tx.oncomplete=resolve;tx.onerror=reject;});db.close();
  let rejected=false;try{await repository.load();}catch{rejected=true;}if(!rejected)throw Error('Corruption accepted');
  const restored=await repository.restorePrevious();if(restored.dataset.version!=='1')throw Error('Restore failed');
  setReport(JSON.stringify({storage:'PASS: real IndexedDB replace, reload, corruption rejection, backup restore',errors}));
 };
 const benchmark=async()=>{
  const results=[], filters={currency:'All',impact:'All',category:'All'};
  for(const count of [10000,100000]){
   const input=sparsePilot(count), begin=performance.now(), dataset=validateDataset(input), validated=performance.now(), index=new EventIndex(dataset), indexed=performance.now();
   index.range(START-86400,START,START,filters);const ready=performance.now();let operations=0;
   for(let i=0;i<1000;i++){const t=START+i*60;index.range(t-3600,t+3600,t,filters,{limit:100});operations+=index.lastOperations;}
   const queried=performance.now(), events=index.range(replay.candles.at(-100)?.time??START-86400,START+86400,news.cursor,filters,{limit:500});
   const primitive=[...instances].find(item=>item.chart), previous=primitive?.groups;
   if(primitive)primitive.replace(markerGroups(events,replay.candles,frame,news.chart.hasMinute,news.cursor));
   await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
   const painted=performance.now();if(primitive)primitive.replace(previous);
   results.push({count,validateMs:validated-begin,indexMs:indexed-validated,initialViewMs:ready-indexed,queriesAndAvailability1000Ms:queried-ready,nodeVisits:operations,projectionAndTwoFramesMs:painted-queried,visibleEventCount:events.length});
  }
  setReport(JSON.stringify({browserBenchmark:results,note:'Sparse synthetic ten-year schedule series; observed durations, no CI timing threshold or FPS claim.',errors},null,2));
 };
 return <><div style={{display:'flex',gap:8,flexWrap:'wrap',padding:8}}>
  <button onClick={start}>Start synthetic date replay</button><button onClick={()=>news.replace(JSON.stringify(pilot()))}>Import synthetic pilot</button>
  <button onClick={()=>{const next=pilot();next.version='2';news.replace(JSON.stringify(next));}}>Import version 2</button><button onClick={()=>news.replace('{broken')}>Invalid import</button>
  <button onClick={storage}>Run isolated IndexedDB checks</button><button onClick={()=>{news.cancel();replay.step();}}>Manual step</button>
  <button onClick={benchmark}>Benchmark 10k and 100k</button>
  <button onClick={()=>setFrame(frame==='15m'?'1h':'15m')}>Timeframe</button><button onClick={()=>replay.loadOlder()}>Prepend</button>
  <button onClick={()=>setHeight(height===400?300:400)}>Resize chart</button><button onClick={()=>setMounted(!mounted)}>Remount chart</button>
  <button onClick={()=>setCommand({action:'fit',id:performance.now()})}>Fit chart</button>
  <button onClick={()=>{const chart=[...instances].find(item=>item.chart)?.chart;chart?.timeScale().setVisibleLogicalRange({from:10,to:80});}}>Pan and zoom</button>
  <button onClick={()=>setReport(JSON.stringify({cursor:news.cursor,lastTime:trading.account.lastTime,revision:replay.transition.revision,navigation:news.navigation,account:trading.account,preferences:news.preferences,hash:news.record?.hash,markers:[...instances].map(item=>({attached:!!item.chart,groups:item.groups.length,coordinates:item.coordinates})),errors},null,2))}>Snapshot</button>
 </div><div style={{height,position:'relative',marginRight:460}}>{mounted&&<CandleChart candles={replay.candles} transition={replay.transition} sessionId={'XAUUSD-replay-'+frame} viewportKey={frame} onLoadOlder={replay.loadOlder} positions={trading.account.positions} orders={trading.account.orders} simulatedTrades={trading.account.trades} drawingMode="none" chartPreferences={{showVolume:true,showCrosshair:true,showGrid:true}} indicatorRegistry={productionRegistry} news={news.chart} command={command}/>}</div>
 {open&&<NewsPanel news={news} onClose={()=>setOpen(false)}/>}<pre id="evidence" style={{maxHeight:500,overflow:'auto',marginRight:460}}>{report}</pre></>;
}
const root=import.meta.hot?.data.root??createRoot(document.getElementById('root'));if(import.meta.hot)import.meta.hot.data.root=root;
root.render(<StrictMode><Harness/></StrictMode>);
