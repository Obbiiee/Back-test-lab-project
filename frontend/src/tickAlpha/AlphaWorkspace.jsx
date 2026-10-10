import Icon from '../workspace/WorkspaceIcon.jsx';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import CandleChart from '../components/CandleChart.jsx';
import IndicatorControls from '../components/IndicatorControls.jsx';
import {productionRegistry} from '../indicators/productionRegistry.js';
import {DRAWING_SPECS} from '../drawings/DrawingTypes.js';
import {IndicatorPreferences} from '../workspacePreferences.js';
import {displayBars,TIMEFRAMES,replayTarget,seekTarget} from './display.js';

export default function AlphaWorkspace({view,timeframe,busy,pauseToken,onTimeframe,onReplay,onNotice,onPriceSelect,onPlanDrawing}){
  const workspaceKey=view.replayStepNs?`tick-historical:${view.state.datasetVersion}:${view.metadata.id}`:`tick-alpha:${view.metadata.id}`;
  const [savedIndicators]=useState(()=>{
    const store=new IndicatorPreferences(()=>globalThis.localStorage,workspaceKey,productionRegistry);
    return {store,instances:store.load()};
  });
  const [mode,setMode]=useState('none'),[instances,setInstances]=useState(savedIndicators.instances);
  const [preferences,setPreferences]=useState({showGrid:true,showCrosshair:true,showVolume:false});
  const [speed,setSpeed]=useState(4),[playToken,setPlayToken]=useState(null);
  const seekInput=useRef(null);
  const playing=playToken===pauseToken;
  const [chartCommand,setChartCommand]=useState(null);
  const latest=useRef({view,onReplay});
  useEffect(()=>{latest.current={view,onReplay};},[view,onReplay]);
  useEffect(()=>{
    if(!playing)return;
    let active=true,timer;
    const next=async()=>{
      const current=latest.current;
      const result=await current.onReplay('ADVANCE',replayTarget(current.view,speed));
      if(!active)return;
      if(!result){setPlayToken(null);return;}
      timer=setTimeout(next,500);
    };
    timer=setTimeout(next,500);
    return()=>{active=false;clearTimeout(timer);};
  },[playing,speed]);
  const bars=useMemo(()=>displayBars(view),[view]);
  const indicatorError=useCallback(error=>onNotice(error.message),[onNotice]);
  const changeInstances=value=>{
    if(value.length>16){onNotice('At most 16 indicators can be displayed.');return;}
    savedIndicators.store.save(value);
    setInstances(value);
  };
  const stopAndSeek=()=>{
    setPlayToken(null);
    try{onReplay('SEEK',seekTarget(seekInput.current.value));}catch(error){onNotice(error.message);}
  };
  return <section className="alpha-chart-workspace" aria-label="Tick replay workspace">
    <div className="alpha-chart-header">
      <label>Timeframe<select aria-label="Chart timeframe" disabled={busy||playing} value={timeframe} onChange={e=>onTimeframe(e.target.value)}>{TIMEFRAMES.map(tf=><option key={tf}>{tf}</option>)}</select></label>
      <IndicatorControls instances={instances} onChange={changeInstances} onOpen={()=>setPlayToken(null)}/>
      <button onClick={()=>setChartCommand({action:'fit',id:crypto.randomUUID()})}>Fit chart</button>
      <label><input type="checkbox" checked={preferences.showGrid} onChange={e=>setPreferences(p=>({...p,showGrid:e.target.checked}))}/>Grid</label>
      <span>Mid-price display · volume unavailable</span>
    </div>
    {savedIndicators.store.status&&<p className="alpha-chart-note" role="alert">{savedIndicators.store.status}</p>}
    <div className="alpha-chart-body">
      <nav className="alpha-drawing-tools" aria-label="Drawing tools">
        <button aria-pressed={mode==='none'} onClick={()=>{setPlayToken(null);setMode('none');}} aria-label="Cursor / Select" title="Cursor / Select"><Icon name="cursor"/></button>
        {Object.entries(DRAWING_SPECS).map(([type,spec])=><button key={type} aria-pressed={mode===type} onClick={()=>{setPlayToken(null);setMode(type);}} aria-label={spec.name} title={spec.name}><Icon name={({"trend-line":"trend","horizontal-line":"horizontal","vertical-line":"vertical",rectangle:"rectangle",arrow:"arrow",text:"text","fibonacci-retracement":"fib",measure:"ruler",ray:"ray"})[type]||"trend"}/></button>)}
        <button aria-pressed={mode==='long-position'} onClick={()=>{setPlayToken(null);setMode('long-position');}} aria-label="Long Position" title="Long Position"><Icon name="long"/></button>
        <button aria-pressed={mode==='short-position'} onClick={()=>{setPlayToken(null);setMode('short-position');}} aria-label="Short Position" title="Short Position"><Icon name="short"/></button>
      </nav>
      <div className="alpha-chart-host">
        <CandleChart candles={bars} transition={{kind:'forward'}} sessionId={`tick-alpha-${view.metadata.id}-${timeframe}`} viewportKey={`${view.metadata.id}:${timeframe}`}
          drawingWorkspace={workspaceKey} drawingStorageKey={view.replayStepNs?`backtest-${workspaceKey}`:`backtest-tick-alpha-planning:${encodeURIComponent(view.metadata.id)}`} volumeAvailable={false}
          tickEvidence={view.analysis} researchOnly
          drawingMode={mode} onDrawingModeChange={setMode} chartPreferences={preferences} onChartPreferencesChange={setPreferences}
          command={chartCommand} indicatorRegistry={productionRegistry} indicatorInstances={instances} onIndicatorError={indicatorError} onPriceSelect={onPriceSelect} onCreateOrder={onPlanDrawing}/>
      </div>
    </div>
    <div className="alpha-replay-controls" aria-label="Tick replay controls">
      <button disabled={busy&&!playing||view.state.ended} aria-pressed={playing} onClick={()=>setPlayToken(playing?null:pauseToken)}>{playing?'Pause replay':'Play replay'}</button>
      <button disabled={busy||playing||view.state.ended} onClick={()=>onReplay('ADVANCE',replayTarget(view,speed))}>Step ticks</button>
      <label>Replay speed<select aria-label="Replay speed" disabled={busy||playing} value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={1}>1 interval / step</option><option value={4}>4 intervals / step</option><option value={16}>16 intervals / step</option></select></label>
      <label>Seek (UTC)<input ref={seekInput} aria-label="Seek UTC" type="datetime-local" step="1" disabled={busy||playing} defaultValue={new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,19)}/></label>
      <button disabled={busy||playing} onClick={stopAndSeek}>Seek replay</button>
    </div>
    <p className="alpha-chart-note">Acknowledged cursor: {new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString()} · {view.chart.candles.length} revealed bars · latest bucket {view.chart.candles.at(-1)?.incomplete?'incomplete':'complete'}. Bid {view.quote?.bid??'unavailable'} / Ask {view.quote?.ask??'unavailable'}.</p>
    <p className="alpha-chart-note">Drawings and indicators are research aids; position drawings are planning estimates. Execution uses observed Bid/Ask ticks. {view.replayStepNs?'Historical candles use recorded row order for research display; order within a timestamp remains unverified. ':''}{view.chart.windowStartGroup!=='0'?'The bounded chart window may start inside a bucket. ':''}Committed financial history cannot be rewound; create a separate Session for another experiment.</p>
  </section>;
}
