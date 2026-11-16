import Icon from '../workspace/WorkspaceIcon.jsx';
import {useCallback,useEffect,useMemo,useState} from 'react';
import {capIndicators,PHONE_QUERY} from './indicatorCap.js';
import CandleChart from '../components/CandleChart.jsx';
import AlphaChartSettings from './AlphaChartSettings.jsx';
import IndicatorControls from '../components/IndicatorControls.jsx';
import {productionRegistry} from '../indicators/productionRegistry.js';
import {DRAWING_SPECS} from '../drawings/DrawingTypes.js';
import {IndicatorPreferences} from '../workspacePreferences.js';
import {displayBars,historyPage,TIMEFRAMES} from './display.js';
import AlphaReplayControls from './AlphaReplayControls.jsx';
import AlphaLegend from './AlphaLegend.jsx';
import {api,sessionPath} from './client.js';
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

export default function AlphaWorkspace({view,timeframe,busy,pauseToken,onPause,onTimeframe,onReplay,onJump,canJump=false,onNotice,onPriceSelect,onPlanDrawing,objectsOpen,onToggleObjects,lead=null,trail=null}){
  const workspaceKey=accountStorageKey(view.replayStepNs?`tick-historical:${view.state.datasetVersion}:${view.metadata.id}`:`tick-alpha:${view.metadata.id}`);
  const [savedIndicators]=useState(()=>{
    const store=new IndicatorPreferences(()=>globalThis.localStorage,workspaceKey,productionRegistry);
    return {store,instances:store.load()};
  });
  const [toolQuery,setToolQuery]=useState('');
  const [mode,setMode]=useState('none'),[instances,setInstances]=useState(savedIndicators.instances);
  // Phones draw at most PHONE_INDICATOR_CAP indicators; the rest are paused for display only.
  const [phone,setPhone]=useState(()=>Boolean(globalThis.matchMedia?.(PHONE_QUERY).matches));
  useEffect(()=>{const query=globalThis.matchMedia?.(PHONE_QUERY);if(!query)return undefined;const sync=()=>setPhone(query.matches);query.addEventListener('change',sync);return()=>query.removeEventListener('change',sync);},[]);
  const capped=useMemo(()=>capIndicators(instances,phone),[instances,phone]);
  const [preferences,setPreferences]=useState({showGrid:true,showCrosshair:true,showVolume:false});
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
  const openOrders=(view.analysis?.orders??[]).filter(order=>['PENDING','ACTIVE','UNRESOLVED'].includes(order.status));
  const bars=useMemo(()=>[...(past.key===historyKey?past.bars:[]),...displayBars(view)],[view,past,historyKey]);
  const indicatorError=useCallback(error=>onNotice(error.message),[onNotice]);
  const changeInstances=value=>{
    if(value.length>16){onNotice('At most 16 indicators can be displayed.');return;}
    savedIndicators.store.save(value);
    setInstances(value);
  };
  return <section className={`alpha-chart-workspace${fullscreen?' is-fullscreen':''}`} aria-label="Tick replay workspace">
    <div className="alpha-chart-header">
      {lead}
      <label>Timeframe<select aria-label="Chart timeframe" disabled={busy} value={timeframe} onChange={e=>{onPause();onTimeframe(e.target.value);}}>{TIMEFRAMES.map(tf=><option key={tf}>{tf}</option>)}</select></label>
      <IndicatorControls instances={instances} paused={capped.paused} onChange={changeInstances} onOpen={()=>onPause()}/>
      <button className="alpha-touch-only" aria-haspopup="dialog" aria-expanded={drawSheet!==null} onClick={()=>{onPause();setDrawSheet(DRAWING_GROUPS.find(([,types])=>types.includes(mode))?.[0]||'Lines');}}><Icon name="brush"/><span className="alpha-btn-label">Draw</span></button>
      {onToggleObjects&&<button className="alpha-touch-only" aria-expanded={objectsOpen} onClick={onToggleObjects} aria-label="Objects"><Icon name="layers"/><span className="alpha-btn-label">Objects</span></button>}
      <AlphaChartSettings preferences={preferences} onPreferences={setPreferences} onFit={()=>setChartCommand({action:'fit',id:crypto.randomUUID()})} volumeAvailable={false} fullscreen={fullscreen} onFullscreen={()=>setFullscreen(value=>!value)} onOpen={()=>onPause()}/>
      <span className="alpha-header-spacer" aria-hidden="true"/>
      {trail}
    </div>
    {savedIndicators.store.status&&<p className="alpha-chart-note" role="alert">{savedIndicators.store.status}</p>}
    {past.key===historyKey&&past.status&&<details className="alpha-display-details alpha-history-context"><summary>Earlier candle context</summary><div><p role="status">{past.status}</p><button onClick={()=>setHistoryRetry(value=>value+1)}>Retry earlier candles</button></div></details>}
    <div className="alpha-chart-body">
      <nav className="alpha-drawing-tools" aria-label="Drawing tools">
        <button aria-pressed={mode==='none'} onClick={()=>{onPause();setMode('none');}} aria-label="Cursor / Select" title="Cursor / Select"><Icon name="cursor"/></button>
        {DRAWING_GROUPS.map(([label,types,icon])=><details className="alpha-drawing-group" key={label} onKeyDown={event=>{if(event.key==='Escape'){event.currentTarget.open=false;event.currentTarget.querySelector('summary').focus();}}}><summary aria-label={`${label} drawing tools`} title={label}><Icon name={icon}/><span className="alpha-group-chevron">›</span></summary><div>{types.map(type=><button key={type} aria-pressed={mode===type} onClick={event=>{onPause();setMode(type);event.currentTarget.closest('details').open=false;}}>{toolName(type)}</button>)}</div></details>)}
      </nav>
      <div className="alpha-chart-host">
        {mode!=='none'&&<div className="alpha-mode-badge" role="status"><span>{POSITION_TYPES.has(mode)?'Plan':'Draw'}: {toolName(mode)}</span><button onClick={()=>setMode('none')}>Cancel</button></div>}
        <CandleChart candles={bars} transition={FORWARD_TRANSITION} sessionId={accountStorageKey(`tick-alpha-${view.metadata.id}-${timeframe}`)} viewportKey={accountStorageKey(`${view.metadata.id}:${timeframe}`)}
          drawingWorkspace={workspaceKey} drawingStorageKey={accountTransport()?`backtest-${workspaceKey}`:view.replayStepNs?`backtest-${workspaceKey}`:`backtest-tick-alpha-planning:${encodeURIComponent(view.metadata.id)}`} volumeAvailable={false} compactTools
          tickEvidence={view.analysis} researchOnly
          drawingMode={mode} onDrawingModeChange={setMode} chartPreferences={preferences} onChartPreferencesChange={setPreferences}
          command={chartCommand} onDrawingStateChange={setDrawingState} indicatorRegistry={productionRegistry} indicatorInstances={capped.rendered} onIndicatorError={indicatorError} onPriceSelect={onPriceSelect} onCreateOrder={onPlanDrawing} priceStep={view.state.profile?.tickSize}/>
        <AlphaLegend view={view}/>
      </div>
      {objectsOpen&&<aside className="alpha-object-panel" aria-label="Drawing objects"><div className="alpha-object-head"><h2>Object tree</h2>{onToggleObjects&&<button className="alpha-object-close" aria-label="Close object tree" onClick={onToggleObjects}>Close</button>}</div><p>Top layer first. Double-click a drawing on the chart to open its properties.</p><p className="alpha-local-only">Saved in this browser only: drawings and indicators are not synced to other devices or kept with the Session on the server.</p>{[['drawings','Drawings'],['plans','Position plans']].map(([group,title])=>{const count=drawingState.drawings.filter(item=>group==='plans'?POSITION_TYPES.has(item.type):!POSITION_TYPES.has(item.type)).length;return <section key={group} className="alpha-object-group" aria-label={title}><h3>{title} ({count})</h3>{!count&&<p>{group==='plans'?'No Long or Short plans.':'No drawings yet.'}</p>}<ol className="alpha-object-tree">{drawingState.drawings.map((item,index)=>({item,index})).filter(({item})=>group==='plans'?POSITION_TYPES.has(item.type):!POSITION_TYPES.has(item.type)).reverse().map(({item,index})=>{const run=action=>setChartCommand({action:`object:${action}:${item.id}`,id:crypto.randomUUID()});const label=item.name||toolName(item.type);return <li key={item.id} className={drawingState.selectedId===item.id?'is-selected':''}><button className="alpha-object-name" onClick={()=>run('select')}>{index+1}. {label}{item.hidden?' (hidden)':''}{item.locked?' (locked)':''}</button><div className="alpha-object-actions">{(item.native?['properties','hide','lock','forward','backward','duplicate','delete']:['edit','hide','lock','delete']).map(action=><button key={action} aria-label={`${action} drawing ${index+1}`} title={action} onClick={()=>run(action)}>{({properties:<Icon name="settings"/>,edit:<Icon name="settings"/>,hide:item.hidden?'Show':'Hide',lock:item.locked?'Unlock':'Lock',forward:'↑',backward:'↓',duplicate:'⧉',delete:<Icon name="trash"/>})[action]}</button>)}</div></li>;})}</ol></section>;})}<section className="alpha-object-group" aria-label="Indicators"><h3>Indicators ({instances.length})</h3>{!instances.length&&<p>No indicators.</p>}<ol className="alpha-object-tree">{instances.map((item,index)=><li key={item.id}><span className="alpha-object-name">{productionRegistry.get(item.type).name}{item.visible===false?' (hidden)':capped.paused.has(item.id)?' (paused on phone)':''}</span><div className="alpha-object-actions"><button aria-label={`${item.visible===false?'Show':'Hide'} indicator ${index+1}`} onClick={()=>changeInstances(instances.map(entry=>entry.id===item.id?{...entry,visible:entry.visible===false}:entry))}>{item.visible===false?'Show':'Hide'}</button><button aria-label={`Remove indicator ${index+1}`} title="Remove" onClick={()=>changeInstances(instances.filter(entry=>entry.id!==item.id))}><Icon name="trash"/></button></div></li>)}</ol></section><section className="alpha-object-group" aria-label="Orders"><h3>Orders ({openOrders.length}) · read-only</h3><p>Server records. Drawing Undo never changes them; manage them in the trading terminal.</p><ol className="alpha-object-tree">{openOrders.map(order=><li key={order.id}><span className="alpha-object-name">{order.side} · {order.status} · {order.status==='PENDING'?order.entry:order.entryPrice??order.entry}</span></li>)}</ol></section></aside>}
    </div>
    <AlphaReplayControls view={view} timeframe={timeframe} busy={busy} pauseToken={pauseToken} onReplay={onReplay} onJump={onJump} canJump={canJump} onNotice={onNotice} onPan={seconds=>setChartCommand({action:'goto:'+seconds,id:crypto.randomUUID()})}/>
    <div className="alpha-chart-disclosures"><details className="alpha-display-details alpha-replay-evidence"><summary>Replay time (UTC): {new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().replace("T"," ").replace(".000Z"," UTC")} · {view.chart.candles.at(-1)?.incomplete?"forming candle":"complete candle"} · details and limitations</summary><p className="alpha-chart-note">Acknowledged cursor: {new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString()} · {view.chart.candles.length} revealed bars · latest bucket {view.chart.candles.at(-1)?.incomplete?'incomplete':'complete'}. Bid {view.quote?.bid??'unavailable'} / Ask {view.quote?.ask??'unavailable'}.</p><p className="alpha-chart-note">Prices are mid-price; volume is unavailable for this source. Drawings and indicators are research aids; position drawings are planning estimates. Execution uses observed Bid/Ask ticks. {view.replayStepNs?'Historical candles use recorded row order for research display; order within a timestamp remains unverified. ':''}{view.chart.windowStartGroup!=='0'?'The bounded chart window may start inside a bucket. ':''}Committed financial history cannot be rewound; create a separate Session for another experiment.</p></details></div>
    {drawSheet!==null&&<div className="alpha-sheet-backdrop" onClick={event=>{if(event.target===event.currentTarget)setDrawSheet(null);}}><div className="alpha-draw-sheet" role="dialog" aria-modal="true" aria-label="Drawing tools" onKeyDown={event=>{if(event.key==='Escape')setDrawSheet(null);}}>
      <span className="alpha-sheet-handle" aria-hidden="true"/>
      <div className="alpha-sheet-head"><h2>Draw</h2><button aria-label="Close drawing tools" onClick={()=>setDrawSheet(null)}>Close</button></div>
      <label className="alpha-sheet-search"><span className="alpha-sr-only">Search drawing tools</span><input type="search" value={toolQuery} placeholder="Search all drawing tools" onChange={event=>setToolQuery(event.target.value)}/></label>
      {toolQuery.trim()?(()=>{const q=toolQuery.trim().toLowerCase();const found=DRAWING_GROUPS.flatMap(([,types])=>types).filter(type=>toolName(type).toLowerCase().includes(q));
        return <div className="alpha-sheet-tools" role="group" aria-label="Matching tools">{found.length?found.map(type=><button key={type} aria-pressed={mode===type} onClick={()=>{onPause();setMode(type);setDrawSheet(null);setToolQuery('');}}>{toolName(type)}</button>):<p className="alpha-sheet-empty" role="status">No drawing tool matches “{toolQuery.trim()}”.</p>}</div>;})()
      :<><div className="alpha-sheet-tabs" role="tablist" aria-label="Tool groups">{DRAWING_GROUPS.map(([label])=><button key={label} role="tab" aria-selected={drawSheet===label} onClick={()=>setDrawSheet(label)}>{label}</button>)}</div>
      <div className="alpha-sheet-tools" role="tabpanel" aria-label={`${drawSheet} tools`}><button aria-pressed={mode==='none'} onClick={()=>{setMode('none');setDrawSheet(null);}}><Icon name="cursor"/> Cursor</button>{DRAWING_GROUPS.find(([label])=>label===drawSheet)?.[1].map(type=><button key={type} aria-pressed={mode===type} onClick={()=>{onPause();setMode(type);setDrawSheet(null);}}>{toolName(type)}</button>)}</div></>}
      <p className="alpha-local-only">Drawings are saved in this browser only, not on other devices.</p>
    </div></div>}
  </section>;
}
