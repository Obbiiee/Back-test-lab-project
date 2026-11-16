import Icon from '../workspace/WorkspaceIcon.jsx';
import {useCallback,useEffect,useMemo,useState} from 'react';
import CandleChart from '../components/CandleChart.jsx';
import IndicatorControls from '../components/IndicatorControls.jsx';
import {productionRegistry} from '../indicators/productionRegistry.js';
import {DRAWING_SPECS} from '../drawings/DrawingTypes.js';
import {IndicatorPreferences} from '../workspacePreferences.js';
import {displayBars,historyPage,TIMEFRAMES} from './display.js';
import {timeframeLabel} from './replay.js';
import AlphaReplayControls from './AlphaReplayControls.jsx';
import {api,sessionPath} from './client.js';

import {accountStorageKey,accountTransport} from './accountClient.js';

export default function AlphaWorkspace({view,timeframe,busy,pauseToken,pending,onPause,onTimeframe,onAdvance,onNotice,onPriceSelect,onPlanDrawing,objectsOpen,drawRequest=null,focus=false,onFocus}){
  const workspaceKey=accountStorageKey(view.replayStepNs?`tick-historical:${view.state.datasetVersion}:${view.metadata.id}`:`tick-alpha:${view.metadata.id}`);
  const [savedIndicators]=useState(()=>{
    const store=new IndicatorPreferences(()=>globalThis.localStorage,workspaceKey,productionRegistry);
    return {store,instances:store.load()};
  });
  const [mode,setMode]=useState('none'),[instances,setInstances]=useState(savedIndicators.instances);
  // Phone layout keeps drawing tools behind the pencil button until asked for.
  const [toolsOpen,setToolsOpen]=useState(false),[seenDraw,setSeenDraw]=useState(drawRequest);
  if(drawRequest!==seenDraw){setSeenDraw(drawRequest);if(drawRequest){setMode(drawRequest.type);setToolsOpen(true);}}
  const [preferences,setPreferences]=useState({showGrid:true,showCrosshair:true,showVolume:false});
  const [chartCommand,setChartCommand]=useState(null),[follow,setFollow]=useState(true);
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
  const bars=useMemo(()=>[...(past.key===historyKey?past.bars:[]),...displayBars(view)],[view,past,historyKey]);
  const indicatorError=useCallback(error=>onNotice(error.message),[onNotice]);
  const changeInstances=value=>{
    if(value.length>16){onNotice('At most 16 indicators can be displayed.');return;}
    savedIndicators.store.save(value);
    setInstances(value);
  };
  const quickTimeframes=['1m','5m','15m','1h','4h','D'];
  const pickTimeframe=value=>{if(value!==timeframe){onPause();onTimeframe(value);}};
  const command=action=>setChartCommand({action,id:crypto.randomUUID()});
  return <section className="alpha-chart-workspace" aria-label="Tick replay workspace">
    <div className="alpha-chart-header" role="toolbar" aria-label="Chart toolbar">
      <div className="alpha-tf-buttons" role="group" aria-label="Chart timeframe">{(quickTimeframes.includes(timeframe)?quickTimeframes:[...quickTimeframes,timeframe]).map(tf=><button key={tf} type="button" aria-pressed={tf===timeframe} disabled={busy} onClick={()=>pickTimeframe(tf)}>{timeframeLabel(tf)}</button>)}</div>
      <select className="alpha-tf-select" aria-label="Chart timeframe" disabled={busy} value={timeframe} onChange={e=>pickTimeframe(e.target.value)}>{TIMEFRAMES.map(tf=><option key={tf} value={tf}>{timeframeLabel(tf)}</option>)}</select>
      <IndicatorControls instances={instances} onChange={changeInstances} onOpen={onPause}/>
      <button type="button" title="Fit all candles in view" onClick={()=>command('fit')}>Fit</button>
      <button type="button" title="Jump the view to the latest revealed candle" onClick={()=>command('latest')}>Latest</button>
      <label className="alpha-inline-check" title="Keep the newest candle in view while replay advances"><input type="checkbox" checked={follow} onChange={e=>setFollow(e.target.checked)}/>Follow</label>
      <label className="alpha-inline-check"><input type="checkbox" checked={preferences.showGrid} onChange={e=>setPreferences(p=>({...p,showGrid:e.target.checked}))}/>Grid</label>
      <details className="alpha-info-pop"><summary aria-label="Data provenance and chart limitations" title="Data provenance and limitations">i</summary><div role="note">
        <p><strong>{view.label??'Session'}</strong> · Mid-price display · volume unavailable · {view.chart.candles.length} revealed bars{view.chart.windowStartGroup!=='0'?' (bounded window may start inside a bucket)':''}.</p>
        <p>Bid {view.quote?.bid??'unavailable'} / Ask {view.quote?.ask??'unavailable'}. Execution uses observed Bid/Ask ticks; candles are display only. Drawings and indicators are research aids; position drawings are planning estimates. {view.replayStepNs?'Historical candles use recorded row order; order within a timestamp remains unverified. ':''}Committed financial history cannot be rewound; create a separate Session for another experiment.</p>
        {past.key===historyKey&&past.status&&<p role="status">{past.status} <button type="button" onClick={()=>setHistoryRetry(value=>value+1)}>Retry earlier candles</button></p>}
      </div></details>
      {onFocus&&<button type="button" className="alpha-focus-toggle" aria-pressed={focus} title={focus?'Exit focus (Esc)':'Focus: chart fills the screen'} onClick={()=>onFocus(!focus)}><Icon name="expand"/><span>{focus?'Exit focus':'Focus'}</span></button>}
    </div>
    {savedIndicators.store.status&&<p className="alpha-chart-note" role="alert">{savedIndicators.store.status}</p>}
    <div className={`alpha-chart-body${toolsOpen||mode!=='none'?' is-tools-open':''}`}>
      <button type="button" className="alpha-draw-toggle" aria-expanded={toolsOpen||mode!=='none'} aria-label={toolsOpen||mode!=='none'?'Hide drawing tools':'Show drawing tools'} onClick={()=>{if(toolsOpen||mode!=='none'){setMode('none');setToolsOpen(false);}else setToolsOpen(true);}}><Icon name={toolsOpen||mode!=='none'?'cursor':'brush'}/></button>
      <nav className="alpha-drawing-tools" aria-label="Drawing tools">
        <button aria-pressed={mode==='none'} onClick={()=>{onPause();setMode('none');}} aria-label="Cursor / Select" title="Cursor / Select"><Icon name="cursor"/></button>
        {[
          ['Lines',['trend-line','horizontal-line','vertical-line','ray'],'trend'],
          ['Shapes',['rectangle','arrow'],'rectangle'],
          ['Fibonacci',['fibonacci-retracement'],'fib'],
          ['Annotations',['text','measure'],'text'],
          ['Positions',['long-position','short-position'],'long'],
        ].map(([label,types,icon])=><details className="alpha-drawing-group" key={label} onKeyDown={event=>{if(event.key==='Escape'){event.currentTarget.open=false;event.currentTarget.querySelector('summary').focus();}}}><summary aria-label={`${label} drawing tools`} title={label}><Icon name={icon}/><span className="alpha-group-chevron">›</span></summary><div>{types.map(type=><button key={type} aria-pressed={mode===type} onClick={event=>{onPause();setMode(type);event.currentTarget.closest('details').open=false;}}>{DRAWING_SPECS[type]?.name||({'long-position':'Long Position','short-position':'Short Position'})[type]}</button>)}</div></details>)}
      </nav>
      <div className="alpha-chart-host">
        <CandleChart candles={bars} transition={{kind:'forward'}} sessionId={accountStorageKey(`tick-alpha-${view.metadata.id}-${timeframe}`)} viewportKey={accountStorageKey(`${view.metadata.id}:${timeframe}`)}
          drawingWorkspace={workspaceKey} drawingStorageKey={accountTransport()?`backtest-${workspaceKey}`:view.replayStepNs?`backtest-${workspaceKey}`:`backtest-tick-alpha-planning:${encodeURIComponent(view.metadata.id)}`} volumeAvailable={false}
          tickEvidence={view.analysis} researchOnly followLatest={follow}
          drawingMode={mode} onDrawingModeChange={setMode} chartPreferences={preferences} onChartPreferencesChange={setPreferences}
          command={chartCommand} onDrawingStateChange={setDrawingState} indicatorRegistry={productionRegistry} indicatorInstances={instances} onIndicatorError={indicatorError} onPriceSelect={onPriceSelect} onCreateOrder={onPlanDrawing}/>
      </div>
      {objectsOpen&&<aside className="alpha-object-panel" aria-label="Drawing objects"><h2>Drawing objects</h2><p>Select a drawing to edit its handles on the chart.</p>{!drawingState.drawings.length&&<p>No drawings yet.</p>}{drawingState.drawings.map((item,index)=><div key={item.id}><button onClick={()=>command(`object:select:${item.id}`)}>{index+1}. {item.type.replaceAll('-',' ')}</button>{['edit','hide','lock','delete'].map(action=><button key={action} aria-label={`${action} drawing ${index+1}`} onClick={()=>command(`object:${action}:${item.id}`)}>{action==='hide'&&item.hidden?'Show':action==='lock'&&item.locked?'Unlock':action}</button>)}</div>)}</aside>}
    </div>
    <AlphaReplayControls view={view} timeframe={timeframe} busy={busy} pauseToken={pauseToken} pending={pending} onAdvance={onAdvance} onNotice={onNotice}/>
  </section>;
}
