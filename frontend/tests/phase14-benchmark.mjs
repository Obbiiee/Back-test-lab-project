import { performance } from 'node:perf_hooks';
import { syncCandleSeries } from '../src/market/replayTransitions.js';
import { IndicatorEngine } from '../src/indicators/IndicatorEngine.js';
import { productionRegistry } from '../src/indicators/productionRegistry.js';
import { analyzeAccount } from '../src/trading/backtestAnalysis.js';
const bars=Array.from({length:5100},(_,i)=>({time:1700000000+i*60,open:2000+i/100,high:2002+i/100,low:1998+i/100,close:2000+i/100+Math.sin(i),volume:i%100}));
const trades=Array.from({length:500},(_,i)=>({id:'exit-'+i,positionId:'position-'+i,side:'Buy',size:1,initialSize:1,entry:2000,exit:2000+(i%3-1),entryTime:1690000000+i*120,exitTime:1690000060+i*120,pnl:100*(i%3-1)}));
const initial={initialBalance:100000,balance:100000+trades.reduce((sum,row)=>sum+row.pnl,0),positions:[],trades};
function run(open) {
  const engine=new IndicatorEngine(productionRegistry,{attach(){},detach(){},remove(){},sync(){}});
  for(const type of productionRegistry.types())engine.create({id:type,type});
  let full=0,updates=0,calculations=0,analysis=null,previousInputs=null;
  const series={setData(){full++;},update(){updates++;}};
  let previous=bars.slice(0,5000);syncCandleSeries(series,[],previous);
  const mountStart=performance.now();
  const project=account=>{const inputs=[account.trades,account.positions,account.initialBalance,account.balance];if(open&&(!previousInputs||inputs.some((value,i)=>value!==previousInputs[i]))){analysis=analyzeAccount(account);calculations++;previousInputs=inputs;}};
  project(initial);const initialProjectionMs=performance.now()-mountStart,samples=[];let projectionChecksMs=0;
  for(let end=5001;end<=5100;end++){
    const next=bars.slice(0,end),start=performance.now();
    syncCandleSeries(series,previous,next,{kind:'forward'});engine.setCandles(next);
    const projectionStart=performance.now();project({...initial,lastTime:next.at(-1).time});projectionChecksMs+=performance.now()-projectionStart; // Same four dependencies as PositionsPanel useMemo.
    samples.push(performance.now()-start);previous=next;
  }
  const total=samples.reduce((sum,value)=>sum+value,0);samples.sort((a,b)=>a-b);engine.dispose();
  return {panel:open?'open':'closed',totalMs:+total.toFixed(2),meanMs:+(total/100).toFixed(2),p95Ms:+samples[94].toFixed(2),initialProjectionMs:+initialProjectionMs.toFixed(2),projectionChecksMs:+projectionChecksMs.toFixed(3),analysisCalculations:calculations,completed:analysis?.summary.completed??null,chartFull:full,chartUpdates:updates,indicatorCalculations:700};
}
// Alternating order helps distinguish run-order/JIT noise from analytics overhead.
const results=[run(false),run(true),run(true),run(false)];
console.log(JSON.stringify({history:5000,indicators:7,steps:100,exitRecords:500,results,note:'Non-gating CPU benchmark with mock chart APIs. Dependency-cache model matches panel useMemo; actual React calculation counts are checked separately in browser. No FPS/20× throughput claim.'},null,2));
