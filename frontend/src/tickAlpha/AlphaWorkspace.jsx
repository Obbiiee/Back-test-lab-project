import Icon from '../workspace/WorkspaceIcon.jsx';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import CandleChart from '../components/CandleChart.jsx';
import IndicatorControls from '../components/IndicatorControls.jsx';
import {productionRegistry} from '../indicators/productionRegistry.js';
import {DRAWING_SPECS} from '../drawings/DrawingTypes.js';
import {IndicatorPreferences} from '../workspacePreferences.js';
import {displayBars,historyPage,TIMEFRAMES,replayTarget,seekTarget} from './display.js';
import {api,sessionPath} from './client.js';
import {emitLocal} from './measurement.js';
import {accountStorageKey,accountTransport} from './accountClient.js';
// Stable identity: a fresh object per render re-ran the candle/indicator sync on every UI change.
const FORWARD_TRANSITION=Object.freeze({kind:'forward'});
const DRAWING_GROUPS=[
  ['Lines',['trend-line','horizontal-line','vertical-line','ray','extended-line','horizontal-ray','cross-line','cyclic-lines'],'trend'],
  ['Channels',['parallel-channel','regression-trend','pitchfork','schiff-pitchfork','modified-schiff-pitchfork'],'layers'],
  ['Shapes',['rectangle','arrow','rotated-rectangle','ellipse','polyline'],'rectangle'],
  ['Fibonacci',['fibonacci-retracement','fib-extension','fib-channel','fib-time-zone','trend-fib-time','fib-fan','fib-circles','fib-arcs','fib-wedge'],'fib'],
  ['Gann',['gann-fan','gann-box'],'hex'],
  ['Patterns',['abcd-pattern','xabcd-pattern','head-shoulders','triangle-pattern','elliott-impulse','elliott-correction'],'pattern'],
  ['Brushes',['brush','highlighter'],'brush'],
  ['Annotations',['text','measure','anchored-text','callout','price-range','date-range','date-price-range','price-label','icon-marker','arrow-marker'],'text'],
  ['Positions',['long-position','short-position'],'long'],
];
const POSITION_TYPES=new Set(['long-position','short-position']);
const toolName=type=>DRAWING_SPECS[type]?.name||({'long-position':'Long Position','short-position':'Short Position'})[type]||type.replaceAll('-',' ');

export default function AlphaWorkspace({view,timeframe,busy,pauseToken,onTimeframe,onReplay,onNotice,onPriceSelect,onPlanDrawing,objectsOpen,onToggleObjects,lead=null,trail=null}){
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
  const [drawSheet,setDrawSheet]=useState(null),[fullscreen,setFullscreen]=useState(false);
  const [drawingState,setDrawingState]=useState({drawings:[],selectedId:null});
  const [past,setPast]=useState({key:'',bars:[],status:''}),[historyRetry,setHistoryRetry]=useState(0);
  const historyKey=`${view.metadata.id}:${timeframe}`;
  useEffect(()=>{
    const controller=new AbortController();
    const key=`${view.metadata.id}:${timeframe}`;
    if(!view.replayStepNs||accountTransport())return;
    const load=async()=>{
      const loaded=[];let offset=0;
      setPast({key,bars:[],status:'Loading the previous month of candle context…'});
      try{
        for(let requests=0;requests<2000;requests++){
          let page;
          try{page=await api(sessionPath(view.metadata.id)+'/chart-history',{timeframe,offset},{signal:AbortSignal.any([controller.signal,AbortSignal.timeout(30000)])});}
          catch(error){
            if(!controller.signal.aborted&&['LOCAL_BUSY','RATE_LIMITED'].includes(error.message)){
              await new Promise(resolve=>setTimeout(resolve,error.message==='RATE_LIMITED'?10000:2000));
              if(controller.signal.aborted)return;continue;
            }
            throw error;
          }
          const bars=historyPage(view,page,timeframe,offset);
          if(page.status==='BUILDING'){await new Promise(resolve=>setTimeout(resolve,500));if(controller.signal.aborted)return;continue;}
          if(bars.length&&loaded.length&&bars[0].time<=loaded.at(-1).time)throw Error('Overlapping past candle context');
          loaded.push(...bars);
          if(loaded.length>50000)throw Error('Past candle context exceeds the display limit');
          if(page.nextOffset===null){
            if(!controller.signal.aborted)setPast({key,bars:loaded,status:loaded.length?'Previous calendar month: recorded candles only; coverage remains unknown.':'No candles are available before this Session in the selected dataset.'});
            return;
          }
          offset=page.nextOffset;
        }
        throw Error('Past candle context did not finish within the work budget');
      }catch(error){if(!controller.signal.aborted)setPast({key,bars:[],status:`Earlier candles unavailable: ${error.message}. Retry earlier candles when the service is ready.`});}
    };
    void load();return()=>controller.abort();
  // Session/timeframe own this request; cursor changes must not restart it.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[view.metadata.id,timeframe,historyRetry]);
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
  // Replay shortcuts: Space plays/pauses, Shift+ArrowRight steps. Ignored while typing,
  // inside dialogs or when a control other than the chart has focus semantics of its own.
  const shortcut=useRef(null);
  shortcut.current={playing,busy,ended:view.state.ended,toggle:()=>{setPlayToken(playing?null:pauseToken);emitLocal(playing?'replay_paused':'replay_started');},step:()=>onReplay('ADVANCE',replayTarget(view,speed))};
  useEffect(()=>{
    const onKey=event=>{
      const target=event.target,state=shortcut.current;
      if(event.defaultPrevented||event.ctrlKey||event.metaKey||event.altKey||state.ended)return;
      if(target.closest?.('input,textarea,select,button,a,summary,[contenteditable="true"],[role=dialog]')||document.querySelector('[role=dialog]'))return;
      if(event.code==='Space'&&!event.shiftKey){if(state.busy&&!state.playing)return;event.preventDefault();state.toggle();}
      else if(event.key==='ArrowRight'&&event.shiftKey){if(state.busy||state.playing)return;event.preventDefault();state.step();}
    };
    window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey);
  },[]);
  const openOrders=(view.analysis?.orders??[]).filter(order=>['PENDING','ACTIVE','UNRESOLVED'].includes(order.status));
  const bars=useMemo(()=>[...(past.key===historyKey?past.bars:[]),...displayBars(view)],[view,past,historyKey]);
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
  return <section className={`alpha-chart-workspace${fullscreen?' is-fullscreen':''}`} aria-label="Tick replay workspace">
    <div className="alpha-chart-header">
      {lead}
      <label>Timeframe<select aria-label="Chart timeframe" disabled={busy||playing} value={timeframe} onChange={e=>onTimeframe(e.target.value)}>{TIMEFRAMES.map(tf=><option key={tf}>{tf}</option>)}</select></label>
      <IndicatorControls instances={instances} onChange={changeInstances} onOpen={()=>setPlayToken(null)}/>
      <button className="alpha-touch-only" aria-haspopup="dialog" aria-expanded={drawSheet!==null} onClick={()=>{setPlayToken(null);setDrawSheet(DRAWING_GROUPS.find(([,types])=>types.includes(mode))?.[0]||'Lines');}}><Icon name="brush"/> Draw</button>
      {onToggleObjects&&<button className="alpha-touch-only" aria-expanded={objectsOpen} onClick={onToggleObjects}><Icon name="layers"/> Objects</button>}
      <button className="alpha-touch-only alpha-fullscreen-toggle" aria-pressed={fullscreen} onClick={()=>setFullscreen(value=>!value)}><Icon name="expand"/> {fullscreen?'Exit full screen':'Full screen'}</button>
      <button onClick={()=>setChartCommand({action:'fit',id:crypto.randomUUID()})}>Fit chart</button>
      <label><input type="checkbox" checked={preferences.showGrid} onChange={e=>setPreferences(p=>({...p,showGrid:e.target.checked}))}/>Grid</label>
      <span className="alpha-header-spacer" aria-hidden="true"/>
      {trail}
    </div>
    {savedIndicators.store.status&&<p className="alpha-chart-note" role="alert">{savedIndicators.store.status}</p>}
    {past.key===historyKey&&past.status&&<details className="alpha-display-details alpha-history-context"><summary>Earlier candle context</summary><div><p role="status">{past.status}</p><button onClick={()=>setHistoryRetry(value=>value+1)}>Retry earlier candles</button></div></details>}
    <div className="alpha-chart-body">
      <nav className="alpha-drawing-tools" aria-label="Drawing tools">
        <button aria-pressed={mode==='none'} onClick={()=>{setPlayToken(null);setMode('none');}} aria-label="Cursor / Select" title="Cursor / Select"><Icon name="cursor"/></button>
        {DRAWING_GROUPS.map(([label,types,icon])=><details className="alpha-drawing-group" key={label} onKeyDown={event=>{if(event.key==='Escape'){event.currentTarget.open=false;event.currentTarget.querySelector('summary').focus();}}}><summary aria-label={`${label} drawing tools`} title={label}><Icon name={icon}/><span className="alpha-group-chevron">›</span></summary><div>{types.map(type=><button key={type} aria-pressed={mode===type} onClick={event=>{setPlayToken(null);setMode(type);event.currentTarget.closest('details').open=false;}}>{toolName(type)}</button>)}</div></details>)}
      </nav>
      <div className="alpha-chart-host">
        {mode!=='none'&&<div className="alpha-mode-badge" role="status"><span>{POSITION_TYPES.has(mode)?'Plan':'Draw'}: {toolName(mode)}</span><button onClick={()=>setMode('none')}>Cancel</button></div>}
        <CandleChart candles={bars} transition={FORWARD_TRANSITION} sessionId={accountStorageKey(`tick-alpha-${view.metadata.id}-${timeframe}`)} viewportKey={accountStorageKey(`${view.metadata.id}:${timeframe}`)}
          drawingWorkspace={workspaceKey} drawingStorageKey={accountTransport()?`backtest-${workspaceKey}`:view.replayStepNs?`backtest-${workspaceKey}`:`backtest-tick-alpha-planning:${encodeURIComponent(view.metadata.id)}`} volumeAvailable={false}
          tickEvidence={view.analysis} researchOnly
          drawingMode={mode} onDrawingModeChange={setMode} chartPreferences={preferences} onChartPreferencesChange={setPreferences}
          command={chartCommand} onDrawingStateChange={setDrawingState} indicatorRegistry={productionRegistry} indicatorInstances={instances} onIndicatorError={indicatorError} onPriceSelect={onPriceSelect} onCreateOrder={onPlanDrawing} priceStep={view.state.profile?.tickSize}/>
    <div className={`alpha-replay-controls ${floating?'is-floating':'is-docked'}`} style={floating?{translate:`${replayOffset.x}px ${replayOffset.y}px`}:undefined} aria-label="Tick replay controls">
      <button className="alpha-replay-grip" aria-label="Move replay controls" disabled={!floating} title="Drag or use arrow keys" onKeyDown={event=>{const delta={ArrowLeft:[-10,0],ArrowRight:[10,0],ArrowUp:[0,-10],ArrowDown:[0,10]}[event.key];if(delta){event.preventDefault();const rect=event.currentTarget.parentElement.getBoundingClientRect();setReplayOffset(current=>({x:current.x+Math.max(8-rect.left,Math.min(innerWidth-8-rect.right,delta[0])),y:current.y+Math.max(8-rect.top,Math.min(innerHeight-8-rect.bottom,delta[1]))}));}}} onPointerDown={event=>{if(event.button!==0)return;const target=event.currentTarget;let x=event.clientX,y=event.clientY;target.setPointerCapture(event.pointerId);target.onpointermove=next=>{const rect=target.parentElement.getBoundingClientRect();const dx=Math.max(8-rect.left,Math.min(innerWidth-rect.right-8,next.clientX-x));const dy=Math.max(8-rect.top,Math.min(innerHeight-rect.bottom-8,next.clientY-y));x=next.clientX;y=next.clientY;setReplayOffset(current=>({x:current.x+dx,y:current.y+dy}));};target.onpointerup=target.onpointercancel=()=>{target.onpointermove=null;target.onpointerup=null;target.onpointercancel=null;};}}>⠿</button>
      <button onClick={()=>{setFloating(!floating);setReplayOffset({x:0,y:0});}}>{floating?'Dock replay':'Float replay'}</button>
      <button disabled={busy&&!playing||view.state.ended} aria-pressed={playing} aria-keyshortcuts="Space" title="Space" onClick={()=>{setPlayToken(playing?null:pauseToken);emitLocal(playing?'replay_paused':'replay_started');}}>{playing?'Pause replay':'Play replay'}</button>
      <button disabled={busy||playing||view.state.ended} aria-keyshortcuts="Shift+ArrowRight" title={`Shift+→ · requests observed quotes through ${new Date(Number(BigInt(replayTarget(view,speed))/1000000n)).toISOString()}`} onClick={()=>onReplay('ADVANCE',replayTarget(view,speed))}>Step ticks</button>
      <span className="alpha-step-target">Next target: {new Date(Number(BigInt(replayTarget(view,speed))/1000000n)).toISOString().slice(11,19)} UTC</span>
      <label>Replay speed<select aria-label="Replay speed" disabled={busy||playing} value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value={1}>1 interval / step</option><option value={4}>4 intervals / step</option><option value={16}>16 intervals / step</option></select></label>
      <details className="alpha-seek" onToggle={event=>{if(event.currentTarget.open&&seekInput.current)seekInput.current.value=new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,19);}}><summary>Go to time</summary><div><label>Seek (UTC)<input ref={seekInput} aria-label="Seek UTC" type="datetime-local" step="1" disabled={busy||playing} defaultValue={new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,19)}/></label><button disabled={busy||playing} onClick={stopAndSeek}>Seek replay</button></div></details>
    </div>
      </div>
      {objectsOpen&&<aside className="alpha-object-panel" aria-label="Drawing objects"><div className="alpha-object-head"><h2>Object tree</h2>{onToggleObjects&&<button className="alpha-object-close" aria-label="Close object tree" onClick={onToggleObjects}>Close</button>}</div><p>Top layer first. Double-click a drawing on the chart to open its properties.</p>{[['drawings','Drawings'],['plans','Position plans']].map(([group,title])=>{const count=drawingState.drawings.filter(item=>group==='plans'?POSITION_TYPES.has(item.type):!POSITION_TYPES.has(item.type)).length;return <section key={group} className="alpha-object-group" aria-label={title}><h3>{title} ({count})</h3>{!count&&<p>{group==='plans'?'No Long or Short plans.':'No drawings yet.'}</p>}<ol className="alpha-object-tree">{drawingState.drawings.map((item,index)=>({item,index})).filter(({item})=>group==='plans'?POSITION_TYPES.has(item.type):!POSITION_TYPES.has(item.type)).reverse().map(({item,index})=>{const run=action=>setChartCommand({action:`object:${action}:${item.id}`,id:crypto.randomUUID()});const label=item.name||toolName(item.type);return <li key={item.id} className={drawingState.selectedId===item.id?'is-selected':''}><button className="alpha-object-name" onClick={()=>run('select')}>{index+1}. {label}{item.hidden?' (hidden)':''}{item.locked?' (locked)':''}</button><div className="alpha-object-actions">{(item.native?['properties','hide','lock','forward','backward','duplicate','delete']:['edit','hide','lock','delete']).map(action=><button key={action} aria-label={`${action} drawing ${index+1}`} title={action} onClick={()=>run(action)}>{({properties:<Icon name="settings"/>,edit:<Icon name="settings"/>,hide:item.hidden?'Show':'Hide',lock:item.locked?'Unlock':'Lock',forward:'↑',backward:'↓',duplicate:'⧉',delete:<Icon name="trash"/>})[action]}</button>)}</div></li>;})}</ol></section>;})}<section className="alpha-object-group" aria-label="Indicators"><h3>Indicators ({instances.length})</h3>{!instances.length&&<p>No indicators.</p>}<ol className="alpha-object-tree">{instances.map((item,index)=><li key={item.id}><span className="alpha-object-name">{productionRegistry.get(item.type).name}{item.visible===false?' (hidden)':''}</span><div className="alpha-object-actions"><button aria-label={`${item.visible===false?'Show':'Hide'} indicator ${index+1}`} onClick={()=>changeInstances(instances.map(entry=>entry.id===item.id?{...entry,visible:entry.visible===false}:entry))}>{item.visible===false?'Show':'Hide'}</button><button aria-label={`Remove indicator ${index+1}`} title="Remove" onClick={()=>changeInstances(instances.filter(entry=>entry.id!==item.id))}><Icon name="trash"/></button></div></li>)}</ol></section><section className="alpha-object-group" aria-label="Orders"><h3>Orders ({openOrders.length}) · read-only</h3><p>Server records. Drawing Undo never changes them; manage them in the trading terminal.</p><ol className="alpha-object-tree">{openOrders.map(order=><li key={order.id}><span className="alpha-object-name">{order.side} · {order.status} · {order.status==='PENDING'?order.entry:order.entryPrice??order.entry}</span></li>)}</ol></section></aside>}
    </div>
    <div className="alpha-chart-disclosures"><details className="alpha-display-details alpha-replay-evidence"><summary>Replay time (UTC): {new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().replace("T"," ").replace(".000Z"," UTC")} · {view.chart.candles.at(-1)?.incomplete?"forming candle":"complete candle"}</summary><p className="alpha-chart-note">Acknowledged cursor: {new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString()} · {view.chart.candles.length} revealed bars · latest bucket {view.chart.candles.at(-1)?.incomplete?'incomplete':'complete'}. Bid {view.quote?.bid??'unavailable'} / Ask {view.quote?.ask??'unavailable'}.</p></details>
    <details className="alpha-display-details"><summary>Chart and replay limitations</summary><p className="alpha-chart-note">Prices are mid-price; volume is unavailable for this source. Drawings and indicators are research aids; position drawings are planning estimates. Execution uses observed Bid/Ask ticks. {view.replayStepNs?'Historical candles use recorded row order for research display; order within a timestamp remains unverified. ':''}{view.chart.windowStartGroup!=='0'?'The bounded chart window may start inside a bucket. ':''}Committed financial history cannot be rewound; create a separate Session for another experiment.</p></details></div>
    {drawSheet!==null&&<div className="alpha-sheet-backdrop" onClick={event=>{if(event.target===event.currentTarget)setDrawSheet(null);}}><div className="alpha-draw-sheet" role="dialog" aria-modal="true" aria-label="Drawing tools" onKeyDown={event=>{if(event.key==='Escape')setDrawSheet(null);}}>
      <span className="alpha-sheet-handle" aria-hidden="true"/>
      <div className="alpha-sheet-head"><h2>Draw</h2><button aria-label="Close drawing tools" onClick={()=>setDrawSheet(null)}>Close</button></div>
      <div className="alpha-sheet-tabs" role="tablist" aria-label="Tool groups">{DRAWING_GROUPS.map(([label])=><button key={label} role="tab" aria-selected={drawSheet===label} onClick={()=>setDrawSheet(label)}>{label}</button>)}</div>
      <div className="alpha-sheet-tools" role="tabpanel" aria-label={`${drawSheet} tools`}><button aria-pressed={mode==='none'} onClick={()=>{setMode('none');setDrawSheet(null);}}><Icon name="cursor"/> Cursor</button>{DRAWING_GROUPS.find(([label])=>label===drawSheet)?.[1].map(type=><button key={type} aria-pressed={mode===type} onClick={()=>{setPlayToken(null);setMode(type);setDrawSheet(null);}}>{toolName(type)}</button>)}</div>
    </div></div>}
  </section>;
}
