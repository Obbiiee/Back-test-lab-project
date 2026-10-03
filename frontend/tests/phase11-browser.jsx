// Actual chart/UI/replay with test-only observation of official owned series.
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import CandleChart from '../src/components/CandleChart.jsx';
import IndicatorControls from '../src/components/IndicatorControls.jsx';
import { overlayRegistry } from '../src/indicators/overlayRegistry.js';
import { IndicatorSeriesAdapter } from '../src/indicators/IndicatorSeriesAdapter.js';
import useReplayMarket from '../src/market/useReplayMarket.js';
import '../src/FigmaWorkspace.css';
import '../src/FxWorkspace.css';

const live=new Map(),observed=new WeakSet();let context=null,syncs=0;
const attach=IndicatorSeriesAdapter.prototype.attach,sync=IndicatorSeriesAdapter.prototype.sync;
IndicatorSeriesAdapter.prototype.attach=function(chart){
  if(chart&&!observed.has(chart)){
    observed.add(chart);const add=chart.addSeries.bind(chart),remove=chart.removeSeries.bind(chart);
    chart.addSeries=(definition,options)=>{
      const series=add(definition,options);
      if(context){const output=context.spec.outputs[context.index++];const record={id:context.config.id,type:context.config.type,key:output.key,visible:options.visible,points:[]};live.set(series,record);
        const set=series.setData.bind(series),apply=series.applyOptions.bind(series);
        series.setData=points=>{set(points);record.points=points;};series.applyOptions=options=>{apply(options);if(options.visible!==undefined)record.visible=options.visible;};}
      return series;
    };
    chart.removeSeries=series=>{remove(series);live.delete(series);};
  }
  attach.call(this,chart);
};
IndicatorSeriesAdapter.prototype.sync=function(config,spec,points){context={config,spec,index:0};try{sync.call(this,config,spec,points);syncs++;}finally{context=null;}};
export default function Harness(){
  const [timeframe,setTimeframe]=useState('15m'),[instances,setInstances]=useState([]),[mounted,setMounted]=useState(true),[report,setReport]=useState('');
  const [mode,setMode]=useState('none'),[preferences,setPreferences]=useState({showVolume:true,showCrosshair:true,showGrid:true}),[testVolume,setTestVolume]=useState(false);
  const replay=useReplayMarket(timeframe);
  function snapshot(){setReport(JSON.stringify({count:replay.candles.length,last:replay.candles.at(-1)?.time,first:replay.candles[0]?.time,timeframe,mounted,syncs,configs:instances,
    series:[...live.values()].map(record=>({...record,points:{count:record.points.length,first:record.points[0],last:record.points.at(-1)}})),drawingJSON:localStorage.getItem('backtest-drawing-manager-v1:main%3AXAUUSD')},null,2));}
  return <><div style={{display:'flex',flexWrap:'wrap',gap:8,padding:8}}>
    <IndicatorControls instances={instances} onChange={setInstances}/>
    <button onClick={()=>replay.start('2024-06-03T12:00:00Z')}>Start replay</button><button onClick={()=>replay.step()}>Reveal next</button><button onClick={()=>replay.step(-1)}>Rewind</button>
    <button onClick={()=>setTimeframe(value=>value==='15m'?'1h':'15m')}>Timeframe</button><button onClick={()=>replay.loadOlder()}>Prepend history</button>
    <button onClick={()=>setMounted(value=>!value)}>Mount toggle</button><button onClick={()=>setPreferences(value=>({...value,showVolume:!value.showVolume}))}>Volume</button>
    <button onClick={()=>setTestVolume(value=>!value)}>Fixture volume data</button><button onClick={snapshot}>Snapshot</button>
    {['none','trend-line','horizontal-line','vertical-line','rectangle','fibonacci-retracement','arrow','text','measure','long-position','short-position'].map(tool=><button key={tool} onClick={()=>setMode(tool)}>{tool}</button>)}
  </div><div style={{height:550,position:'relative'}}>{mounted&&<CandleChart candles={testVolume?replay.candles.map((bar,index)=>({...bar,volume:10+index%50})):replay.candles}
    sessionId={'XAUUSD-replay-'+timeframe} viewportKey={timeframe} indicatorRegistry={overlayRegistry} indicatorInstances={instances}
    drawingMode={mode} onDrawingModeChange={setMode} chartPreferences={preferences} onChartPreferencesChange={setPreferences}
    onCreateOrder={()=>setReport('Order ticket trigger received')} />}</div><pre id="evidence" style={{maxHeight:250,overflow:'auto'}}>{report}</pre></>;
}
const root=import.meta.hot?.data.root??createRoot(document.getElementById('root'));if(import.meta.hot)import.meta.hot.data.root=root;
root.render(<StrictMode><Harness/></StrictMode>);
