import Icon from '../workspace/WorkspaceIcon.jsx';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import CandleChart from '../components/CandleChart.jsx';
import IndicatorControls from '../components/IndicatorControls.jsx';
import {productionRegistry} from '../indicators/productionRegistry.js';
import {DRAWING_SPECS} from '../drawings/DrawingTypes.js';
import {IndicatorPreferences} from '../workspacePreferences.js';
import {displayBars,TIMEFRAMES,replayTarget,seekTarget} from './display.js';
import {emitLocal} from './measurement.js';
import {accountStorageKey,accountTransport} from './accountClient.js';

export default function AlphaWorkspace({view,timeframe,busy,pauseToken,onTimeframe,onReplay,onNotice,onPriceSelect,onPlanDrawing,objectsOpen}){
  const workspaceKey=accountStorageKey(view.replayStepNs?`tick-historical:${view.state.datasetVersion}:${view.metadata.id}`:`tick-alpha:${view.metadata.id}`);
  const [savedIndicators]=useState(()=>{
    const store=new IndicatorPreferences(()=>globalThis.localStorage,workspaceKey,productionRegistry);
    return {store,instances:store.load()};
  });
  const [mode,setMode]=useState('none'),[instances,setInstances]=useState(savedIndicators.instances);
  const [preferences,setPreferences]=useState({showGrid:true,showCrosshair:true,showVolume:false});
  const [speed,setSpeed]=useState(4),[playToken,setPlayToken]=useState(null);
  const seekInput=useRef(null);
  const [floating,setFloating]=useState(false),[replayOffset,setReplayOffset]=useState({x:0,y:0});
  const playing=playToken===pauseToken;
  const [chartCommand,setChartCommand]=useState(null);
  const [drawingState,setDrawingState]=useState({drawings:[],selectedId:null});
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
        {[
          ['Lines',['trend-line','horizontal-line','vertical-line','ray'],'trend'],
          ['Shapes',['rectangle','arrow'],'rectangle'],
          ['Fibonacci',['fibonacci-retracement'],'fib'],
          ['Annotations',['text','measure'],'text'],
          ['Positions',['long-position','short-position'],'long'],
        ].map(([label,types,icon])=><details className="alpha-drawing-group" key={label} onKeyDown={event=>{if(event.key==='Escape'){event.currentTarget.open=false;event.currentTarget.querySelector('summary').focus();}}}><summary aria-label={`${label} drawing tools`} title={label}><Icon name={icon}/><span className="alpha-group-chevron">›</span></summary><div>{types.map(type=><button key={type} aria-pressed={mode===type} onClick={event=>{setPlayToken(null);setMode(type);event.currentTarget.closest('details').open=false;}}>{DRAWING_SPECS[type]?.name||({'long-position':'Long Position','short-position':'Short Position'})[type]}</button>)}</div></details>)}
      </nav>
      <div className="alpha-chart-host">
        <CandleChart candles={bars} transition={{kind:'forward'}} sessionId={accountStorageKey(`tick-alpha-${view.metadata.id}-${timeframe}`)} viewportKey={accountStorageKey(`${view.metadata.id}:${timeframe}`)}
          drawingWorkspace={workspaceKey} drawingStorageKey={accountTransport()?`backtest-${workspaceKey}`:view.replayStepNs?`backtest-${workspaceKey}`:`backtest-tick-alpha-planning:${encodeURIComponent(view.metadata.id)}`} volumeAvailable={false}
          tickEvidence={view.analysis} researchOnly
          drawingMode={mode} onDrawingModeChange={setMode} chartPreferences={preferences} onChartPreferencesChange={setPreferences}
          command={chartCommand} onDrawingStateChange={setDrawingState} indicatorRegistry={productionRegistry} indicatorInstances={instances} onIndicatorError={indicatorError} onPriceSelect={onPriceSelect} onCreateOrder={onPlanDrawing}/>
      </div>
      {objectsOpen&&<aside className="alpha-object-panel" aria-label="Position drawing objects"><h2>Position drawings</h2><p>Other chart drawings keep their on-chart editing controls.</p>{!drawingState.drawings.length&&<p>No position drawings yet.</p>}{drawingState.drawings.map((item,index)=><div key={item.id}><button onClick={()=>setChartCommand({action:`object:select:${item.id}`,id:crypto.randomUUID()})}>{index+1}. {item.type.replaceAll('-',' ')}</button>{['edit','hide','lock','delete'].map(action=><button key={action} aria-label={`${action} drawing ${index+1}`} onClick={()=>setChartCommand({action:`object:${action}:${item.id}`,id:crypto.randomUUID()})}>{action==='hide'&&item.hidden?'Show':action==='lock'&&item.locked?'Unlock':action}</button>)}</div>)}</aside>}
    </div>
    <div className={`alpha-replay-controls ${floating?'is-floating':'is-docked'}`} style={floating?{translate:`${replayOffset.x}px ${replayOffset.y}px`}:undefined} aria-label="Tick replay controls">
      <button className="alpha-replay-grip" aria-label="Move replay controls" disabled={!floating} title="Drag or use arrow keys" onKeyDown={event=>{const delta={ArrowLeft:[-10,0],ArrowRight:[10,0],ArrowUp:[0,-10],ArrowDown:[0,10]}[event.key];if(delta){event.preventDefault();const rect=event.currentTarget.parentElement.getBoundingClientRect();setReplayOffset(current=>({x:current.x+Math.max(8-rect.left,Math.min(innerWidth-8-rect.right,delta[0])),y:current.y+Math.max(8-rect.top,Math.min(innerHeight-8-rect.bottom,delta[1]))}));}}} onPointerDown={event=>{if(event.button!==0)return;const target=event.currentTarget;let x=event.clientX,y=event.clientY;target.setPointerCapture(event.pointerId);target.onpointermove=next=>{const rect=target.parentElement.getBoundingClientRect();const dx=Math.max(8-rect.left,Math.min(innerWidth-rect.right-8,next.clientX-x));const dy=Math.max(8-rect.top,Math.min(innerHeight-rect.bottom-8,next.clientY-y));x=next.clientX;y=next.clientY;setReplayOffset(current=>({x:current.x+dx,y:current.y+dy}));};target.onpointerup=target.onpointercancel=()=>{target.onpointermove=null;target.onpointerup=null;target.onpointercancel=null;};}}>⠿</button>
      <button onClick={()=>{setFloating(!floating);setReplayOffset({x:0,y:0});}}>{floating?'Dock replay':'Float replay'}</button>
      <button disabled={busy&&!playing||view.state.ended} aria-pressed={playing} onClick={()=>{setPlayToken(playing?null:pauseToken);emitLocal(playing?'replay_paused':'replay_started');}}>{playing?'Pause replay':'Play replay'}</button>
      <button disabled={busy||playing||view.state.ended} title={`Requests observed quotes through ${new Date(Number(BigInt(replayTarget(view,speed))/1000000n)).toISOString()}`} onClick={()=>onReplay('ADVANCE',replayTarget(view,speed))}>Step ticks</button>
      <span className="alpha-step-target">Next target: {new Date(Number(BigInt(replayTarget(view,speed))/1000000n)).toISOString().slice(11,19)} UTC</span>
      <label>Replay speed<select aria-label="Replay speed" disabled={busy||playing} value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={1}>1 interval / step</option><option value={4}>4 intervals / step</option><option value={16}>16 intervals / step</option></select></label>
      <details className="alpha-seek" onToggle={event=>{if(event.currentTarget.open&&seekInput.current)seekInput.current.value=new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,19);}}><summary>Go to time</summary><div><label>Seek (UTC)<input ref={seekInput} aria-label="Seek UTC" type="datetime-local" step="1" disabled={busy||playing} defaultValue={new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,19)}/></label><button disabled={busy||playing} onClick={stopAndSeek}>Seek replay</button></div></details>
    </div>
    <div className="alpha-chart-disclosures"><details className="alpha-display-details alpha-replay-evidence"><summary>Replay time (UTC): {new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().replace("T"," ").replace(".000Z"," UTC")} · {view.chart.candles.at(-1)?.incomplete?"forming candle":"complete candle"}</summary><p className="alpha-chart-note">Acknowledged cursor: {new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString()} · {view.chart.candles.length} revealed bars · latest bucket {view.chart.candles.at(-1)?.incomplete?'incomplete':'complete'}. Bid {view.quote?.bid??'unavailable'} / Ask {view.quote?.ask??'unavailable'}.</p></details>
    <details className="alpha-display-details"><summary>Chart and replay limitations</summary><p className="alpha-chart-note">Drawings and indicators are research aids; position drawings are planning estimates. Execution uses observed Bid/Ask ticks. {view.replayStepNs?'Historical candles use recorded row order for research display; order within a timestamp remains unverified. ':''}{view.chart.windowStartGroup!=='0'?'The bounded chart window may start inside a bucket. ':''}Committed financial history cannot be rewound; create a separate Session for another experiment.</p></details></div>
  </section>;
}
