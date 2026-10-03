// Test-only reference and instrumentation: never imported by the production entrypoint.
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CandleChart from '../src/components/CandleChart.jsx';
import { IndicatorRegistry } from '../src/indicators/IndicatorRegistry.js';
import { IndicatorSeriesAdapter } from '../src/indicators/IndicatorSeriesAdapter.js';
import useReplayMarket from '../src/market/useReplayMarket.js';
import '../src/FigmaWorkspace.css';
import '../src/FxWorkspace.css';

const evidence = { active: 0, points: [], syncs: 0, removes: 0, inputCount: 0, inputLast: null };
const sync = IndicatorSeriesAdapter.prototype.sync, remove = IndicatorSeriesAdapter.prototype.remove;
const known = new WeakMap();
IndicatorSeriesAdapter.prototype.sync = function(config, spec, points) {
  sync.call(this,config,spec,points);
  const ids=known.get(this)??new Set(); if(!ids.has(config.id)){ids.add(config.id);evidence.active++;}known.set(this,ids);
  evidence.points=points; evidence.visible=config.visible; evidence.syncs++;
};
IndicatorSeriesAdapter.prototype.remove=function(id){const ids=known.get(this);if(ids?.delete(id)){evidence.active--;evidence.removes++;}remove.call(this,id);};
const registry=new IndicatorRegistry().register({type:'TEST_LINE',output:'line',warmup:1,parameters:{},calculate:bars=>{
  evidence.inputCount=bars.length;evidence.inputLast=bars.at(-1)?.time??null;
  return bars.map(bar=>({time:bar.time,value:bar.close,color:'#ffcc00'}));
}});
const reference=[{id:'reference',type:'TEST_LINE'}];
export default function Harness(){
  const [timeframe,setTimeframe]=useState('15m'),[instances,setInstances]=useState(reference),[mounted,setMounted]=useState(true);
  const [mode,setMode]=useState('none'),[preferences,setPreferences]=useState({showVolume:true,showCrosshair:true});
  const [report,setReport]=useState(''),[command,setCommand]=useState(null);
  const [testVolume,setTestVolume]=useState(false);
  const replay=useReplayMarket(timeframe);
  return <><div style={{display:'flex',flexWrap:'wrap',gap:8,padding:8}}>
    <button onClick={()=>replay.start('2024-06-03T12:00:00Z')}>Start replay</button>
    <button onClick={()=>replay.step()}>Reveal next</button><button onClick={()=>replay.step(-1)}>Rewind</button>
    <button onClick={()=>setTimeframe(value=>value==='15m'?'1h':'15m')}>Timeframe</button>
    <button onClick={()=>replay.loadOlder()}>Prepend history</button>
    <button onClick={()=>setInstances([{...reference[0],visible:false}])}>Disable</button>
    <button onClick={()=>setInstances(reference)}>Enable</button><button onClick={()=>setInstances([])}>Remove</button>
    <button onClick={()=>setMounted(value=>!value)}>Mount toggle</button>
    <button onClick={()=>setPreferences(value=>({...value,showVolume:!value.showVolume}))}>Volume</button>
    <button onClick={()=>setTestVolume(value=>!value)}>Fixture volume data</button>
    <button onClick={()=>setCommand({action:'fit',id:Date.now()})}>Fit</button>
    <button onClick={()=>setReport(JSON.stringify({...evidence,points:{count:evidence.points.length,first:evidence.points[0],last:evidence.points.at(-1)},count:replay.candles.length,last:replay.candles.at(-1)?.time,timeframe,mounted,error:replay.error,storage:localStorage.getItem('backtest-drawing-manager-v1:main%3AXAUUSD')},null,2))}>Snapshot</button>
    {['none','trend-line','horizontal-line','vertical-line','rectangle','fibonacci-retracement','arrow','text','measure','long-position','short-position'].map(tool=><button key={tool} onClick={()=>setMode(tool)}>{tool}</button>)}
  </div><div style={{height:600,position:'relative'}}>{mounted&&<CandleChart candles={testVolume?replay.candles.map((bar,index)=>({...bar,volume:10+index%50})):replay.candles} sessionId={'XAUUSD-replay-'+timeframe} viewportKey={timeframe}
    indicatorRegistry={registry} indicatorInstances={instances} drawingMode={mode} onDrawingModeChange={setMode} chartPreferences={preferences} onChartPreferencesChange={setPreferences}
    command={command} onCreateOrder={()=>setReport('Order ticket trigger received')} />}</div><pre id="evidence" style={{maxHeight:250,overflow:'auto'}}>{report}</pre></>;
}
const root = import.meta.hot?.data.root ?? createRoot(document.getElementById('root'));
if (import.meta.hot) import.meta.hot.data.root = root;
root.render(<StrictMode><Harness/></StrictMode>);
