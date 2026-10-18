import {useEffect,useMemo,useRef,useState} from 'react';
import CandleChart from '../components/CandleChart.jsx';
import {productionRegistry} from '../indicators/productionRegistry.js';
import WorkspaceModal from '../workspace/WorkspaceModal.jsx';
import {displayBars,stamp,TIMEFRAMES} from '../tickAlpha/display.js';
import {ratioLabel} from '../tickAlpha/annotations.js';
import {accessMessage,betaNotice,confirmation,executionCommand,newId,methodFromForm,orderFromForm,createReplayLoop} from './betaWorkspace.js';

export default function BetaWorkspace({client,workspace,onExpired}){
  const [catalog,setCatalog]=useState(null),[access,setAccess]=useState(null),[view,setView]=useState(null);
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[blocked,setBlocked]=useState(false);
  const [review,setReview]=useState(null),[action,setAction]=useState(null),[journal,setJournal]=useState(null);
  const [methodKind,setMethodKind]=useState('FREE_STYLE'),[timeframe,setTimeframe]=useState('1m'),[speed,setSpeed]=useState(1),[playing,setPlaying]=useState(false);
  const [tab,setTab]=useState('Positions'),[drawing,setDrawing]=useState('none');
  const [chartPreferences,setChartPreferences]=useState({showGrid:true,showCrosshair:true,showVolume:false});
  const flight=useRef(false),live=useRef(true),returnFocus=useRef(null);
  const latest=useRef(null);
  const [replay]=useState(()=>createReplayLoop({step:()=>latest.current(),onStop:()=>{if(live.current)setPlaying(false);}}));
  useEffect(()=>{latest.current=()=>run(step);});
  useEffect(()=>()=>replay.stop(),[replay]);
  const owner=workspace.role==='OWNER';
  async function reload(id=view?.metadata.id,tf=timeframe){
    const [nextCatalog,nextAccess]=await Promise.all([client.catalog(),client.access()]);
    const [nextView,nextJournal]=id?await Promise.all([client.inspect(id,{timeframe:tf}),client.journal(id)]):[null,null];
    accessMessage(nextAccess);
    if(live.current){setCatalog(nextCatalog);setAccess(nextAccess);setView(nextView);setJournal(nextJournal);}
    return nextView;
  }
  async function run(operation,{reconcile=false}={}){
    if(flight.current||blocked&&!reconcile)return;flight.current=true;setBusy(true);setNotice('');
    try{const result=await operation();if(live.current&&reconcile){setBlocked(false);setReview(null);setAction(null);}return result??true;}
    catch(error){if(live.current){setNotice(betaNotice(error));setReview(null);setAction(null);if(error.reconciliationRequired)setBlocked(true);if(!client.hasSession())onExpired();}return false;}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  useEffect(()=>{
    live.current=true;let active=true;
    // Defer network admission until setup settles; StrictMode's discarded setup
    // must not consume both server request slots before the live setup starts.
    void Promise.resolve().then(()=>{if(active)return run(()=>reload(null));});
    return()=>{active=false;live.current=false;};
  // This workspace owns its client scope and is remounted when scope changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[]);
  const bars=useMemo(()=>view?.chart?displayBars(view):[],[view]);
  const writeDisabled=busy||blocked||playing||!owner;
  const tradingDisabled=writeDisabled||view?.savedState!=='SAVED'||view?.state.ended||view?.state.unresolved;
  const stats=view?.analysis,orders=Object.entries(view?.state.orders??{});
  async function mutate(operation){await operation();await reload();}
  async function step(){
    const window=await client.activate(view.metadata.id);
    const current=BigInt(view.state.throughNs),start=BigInt(window.startNs);
    const targetNs=String(current<start?start:current+BigInt(speed)*BigInt(view.replayStepNs));
    await client.command(view.metadata.id,executionCommand(view,'ADVANCE',{targetNs}));const saved=await reload();return saved.state.nextGroupIndex!==view.state.nextGroupIndex;
  }
  return <section className="beta-workspace tick-alpha" aria-label="Beta workspace">
    <header><h1>{workspace.name}</h1><span className="alpha-badge">Synthetic sandbox</span>
      <button disabled={busy} onClick={()=>{replay.stop();run(()=>reload(),{reconcile:true});}}>Reload saved evidence</button></header>
    {access&&<section className="beta-access" aria-label="Plan and usage"><strong>{accessMessage(access)}</strong>
      <p>{access.tier==='FREE'?(access.freeActivationAvailable?'One monthly window activation available today.':'Today’s activation used. Previously activated Sessions remain tradable.'):'Pro sandbox access is granted by the server.'}</p>
      <p>No funds collected. Checkout is not enabled. Demos contain only a short authored sequence, not one month of historical data.</p></section>}
    <p role="status" aria-live="polite">{notice||(busy?'Loading saved evidence…':blocked?'Reload saved evidence to reconcile the last request.':'')}</p>
    {!owner&&<p>Read access. Ask the workspace owner to create or change Sessions.</p>}
    {!catalog?<p>Connect to the enabled Beta sandbox. No fallback feed is used.</p>:!view?<>
      <div className="beta-create-grid"><form onSubmit={event=>{event.preventDefault();const f=new FormData(event.currentTarget);run(async()=>{
        await client.createMethod(methodFromForm(f,newId('method')));await reload(null);
      });}}><h2>Create a strategy</h2><label>Strategy type<select name="kind" value={methodKind} disabled={writeDisabled} onChange={e=>setMethodKind(e.target.value)}><option value="FREE_STYLE">Free Style</option><option value="PROTOCOL">Protocol</option></select></label>{methodKind==='PROTOCOL'&&<><label>Risk percent<input name="risk" defaultValue="1" required disabled={writeDisabled}/></label><label>Reward / risk<input name="rr" defaultValue="2" required disabled={writeDisabled}/></label><label>Checklist<select name="checklist" disabled={writeDisabled}><option>ON</option><option>OFF</option></select></label><label>Conditions, one per line<textarea name="conditions" required maxLength={4000} disabled={writeDisabled}/></label></>}<label>Strategy name<input name="name" maxLength={128} required disabled={writeDisabled}/></label><button disabled={writeDisabled}>Save strategy</button></form>
      <form onSubmit={event=>{event.preventDefault();const f=new FormData(event.currentTarget);run(async()=>{
        const symbol=f.get('symbol'),instrument=catalog.instruments.find(i=>i.symbol===symbol);
        const saved=await client.createSession({id:newId('session'),name:f.get('name'),methodId:f.get('method'),symbol,startPeriod:instrument.startPeriod,initialBalance:f.get('balance')});await reload(saved.id);
      });}}><h2>Start a Session</h2><label>Session name<input name="name" maxLength={128} required disabled={writeDisabled}/></label>
        <label>Pair<select name="symbol" disabled={writeDisabled}>{catalog.instruments.map(i=><option key={i.symbol}>{i.symbol}</option>)}</select></label>
        <label>Strategy<select name="method" required disabled={writeDisabled}>{catalog.methods.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <label>Starting balance (USD)<input name="balance" inputMode="decimal" defaultValue="10000" required disabled={writeDisabled}/></label>
        <button disabled={writeDisabled||!catalog.methods.length||access?.savedSessions>=access?.savedLimit}>Create Session</button></form></div>
      <h2>Saved Sessions</h2><ul className="beta-session-list">{catalog.sessions.filter(s=>catalog.savedStates[s.id]==='SAVED').map(s=><li key={s.id}><div><strong>{s.name}</strong><span>{s.symbol} · {s.startPeriod}</span></div><button disabled={busy||blocked} onClick={()=>run(()=>reload(s.id))}>Open {s.name}</button><button disabled={writeDisabled} onClick={()=>run(()=>mutate(()=>client.trash(s.id)))}>Move {s.name} to Trash</button></li>)}</ul>
      {!catalog.sessions.length&&<p>Create a strategy, then a Session to begin. Free accounts can trade.</p>}
      <details><summary>Trash · restore within 30 days</summary><ul className="beta-session-list">{catalog.sessions.filter(s=>catalog.savedStates[s.id]==='TRASHED').map(s=><li key={s.id}><span>{s.name} · {s.symbol}</span><button disabled={writeDisabled} onClick={()=>run(()=>mutate(()=>client.restore(s.id)))}>Restore {s.name}</button></li>)}</ul></details>
    </>:<>
      <div className="beta-session-heading"><button disabled={busy||blocked||playing} onClick={()=>run(()=>reload(null))}>All Beta Sessions</button><h2>{view.metadata.name} · {view.metadata.symbol}</h2><strong>Saved balance ${view.state.balance}</strong></div>
      <p>{view.label}. Earlier two-year candle history is unavailable in these demos.</p>
      <div className="beta-toolbar" role="group" aria-label="Chart and replay"><button disabled={tradingDisabled} onClick={()=>run(()=>mutate(()=>client.activate(view.metadata.id)))}>Activate trading window</button>
        <label>Timeframe<select aria-label="Beta timeframe" disabled={busy||playing} value={timeframe} onChange={e=>{const tf=e.target.value;run(async()=>{await reload(view.metadata.id,tf);setTimeframe(tf);setReview(null);});}}>{TIMEFRAMES.map(tf=><option key={tf}>{tf}</option>)}</select></label><label>Replay speed<select value={speed} disabled={busy||playing} onChange={e=>setSpeed(Number(e.target.value))}>{[1,4,16].map(n=><option key={n} value={n}>{n} intervals / step</option>)}</select></label><button disabled={playing?false:tradingDisabled} aria-pressed={playing} onClick={()=>{if(playing)replay.stop();else if(replay.start())setPlaying(true);}}>{playing?'Pause replay':'Play replay'}</button><button disabled={tradingDisabled} onClick={()=>run(step)}>Step replay</button><span>{stamp(view.state.throughNs)}</span>
        <label>Drawing<select value={drawing} onChange={e=>setDrawing(e.target.value)}><option value="none">Cursor</option><option value="trend-line">Trend line</option><option value="horizontal-line">Horizontal line</option><option value="rectangle">Rectangle</option><option value="fibonacci-retracement">Fibonacci</option><option value="text">Text</option></select></label></div>
      <div className="beta-chart"><CandleChart candles={bars} transition={{kind:'forward'}} researchOnly volumeAvailable={false}
        sessionId={`beta:${client.subject()}:${workspace.id}:${view.metadata.id}`} drawingWorkspace={`beta:${client.subject()}:${workspace.id}:${view.metadata.id}`} drawingStorageKey={`beta-drawings:${client.subject()}:${workspace.id}:${view.metadata.id}`}
        drawingMode={drawing} onDrawingModeChange={setDrawing} chartPreferences={chartPreferences} onChartPreferencesChange={setChartPreferences} indicatorRegistry={productionRegistry}/></div>
      {!view.chart&&<p>Chart display unavailable. Committed evidence remains saved.</p>}
      <form className="beta-order-form" onSubmit={event=>{event.preventDefault();const f=new FormData(event.currentTarget);returnFocus.current=event.currentTarget.querySelector('button');run(async()=>{
        const result=await client.review(view.metadata.id,{id:newId('order'),expectedRevision:view.state.revision,payload:orderFromForm(f,view)});
        const request=await confirmation(result);if(live.current)setReview({value:result,request});
      });}}><h2>Plan an order</h2><p>Buy at Ask {view.quote?.ask??'unavailable'} · Sell at Bid {view.quote?.bid??'unavailable'}. Review never fills an order.</p>
        <label>Direction<select name="side" disabled={tradingDisabled}><option value="LONG">Buy</option><option value="SHORT">Sell</option></select></label>
        <label>Workflow<select name="workflow" disabled={tradingDisabled||view.method.kind==='PROTOCOL'} value={view.method.kind==='PROTOCOL'?'PLANNED':undefined}><option value="QUICK">Market</option><option value="PLANNED">Planned</option></select></label>
        <label>Planned order type<select name="orderType" disabled={tradingDisabled}><option>LIMIT</option><option>STOP</option></select></label>
        <label>Planned entry<input name="entry" inputMode="decimal" disabled={tradingDisabled}/></label>
        <label>Lots<input name="quantity" defaultValue={view.method.kind==='PROTOCOL'?'':'0.01'} placeholder={view.method.kind==='PROTOCOL'?'Calculated by server':undefined} inputMode="decimal" required disabled={tradingDisabled||view.method.kind==='PROTOCOL'}/></label>
        <label>Stop loss<input name="sl" inputMode="decimal" disabled={tradingDisabled}/></label><label>Take profit<input name="tp" inputMode="decimal" disabled={tradingDisabled||view.method.kind==='PROTOCOL'}/></label>
        {view.method.kind==='PROTOCOL'&&<><p>Protocol risk {view.method.riskPercent}% · R:R {view.method.rr}. The server owns quantity and target; manual exits are locked.</p>{view.method.conditions.map(c=><label key={c.id}>{c.label}<select name={'condition:'+c.id} disabled={tradingDisabled}><option value="NOT_ASSESSED">Not assessed</option><option value="PASS">Pass</option><option value="FAIL">Fail</option></select></label>)}</>}<button disabled={tradingDisabled||!view.quote}>Review order</button>
      </form>
      <nav className="beta-tabs" aria-label="Session views">{['Positions','Analysis','Journal','Evidence'].map(t=><button key={t} aria-pressed={tab===t} onClick={()=>setTab(t)}>{t}</button>)}</nav>
      {tab==='Positions'&&<div className="alpha-table-scroll"><table><caption>Committed orders</caption><thead><tr><th>Order</th><th>Direction</th><th>Status</th><th>Lots remaining</th><th>Entry</th><th>Action</th></tr></thead><tbody>{orders.map(([id,o])=><tr key={id}><td>{id.slice(-8)}</td><td>{o.side}</td><td>{o.status}{o.exitRequest?' · exit requested':''}</td><td>{o.remaining}</td><td>{o.entryPrice??o.entry}</td><td>{['PENDING','ACTIVE'].includes(o.status)&&<button disabled={tradingDisabled||!!o.exitRequest||(o.status==='ACTIVE'&&view.method.kind!=='FREE_STYLE')} onClick={event=>{returnFocus.current=event.currentTarget;setAction(executionCommand(view,o.status==='PENDING'?'CANCEL':'CLOSE',{orderId:id,...(o.status==='ACTIVE'?{quantity:null}:{})}));}}>{o.status==='PENDING'?'Cancel pending':'Close position'}</button>}{o.status==='ACTIVE'&&view.method.kind==='FREE_STYLE'&&<form onSubmit={event=>{event.preventDefault();const quantity=new FormData(event.currentTarget).get('partial');returnFocus.current=event.currentTarget.querySelector('button');setAction(executionCommand(view,'CLOSE',{orderId:id,quantity}));}}><label>Partial lots<input name="partial" aria-label={'Partial lots '+id.slice(-8)} required inputMode="decimal" disabled={tradingDisabled||!!o.exitRequest}/></label><button disabled={tradingDisabled||!!o.exitRequest}>Review partial close</button></form>}</td></tr>)}</tbody></table>{!orders.length&&<p>No orders. Activate trading, step replay, then review an order.</p>}</div>}
      {tab==='Analysis'&&(stats?.status==='COMPLETE'?<section className="beta-analysis"><h2>Committed results</h2><dl>{[
        ['Balance (USD)',stats.account.balance],['Net cash change (USD)',stats.account.netCashChange],['Commission (USD)',stats.account.commission],
        ['Completed trades',stats.metrics.tradeCount],['Win rate',ratioLabel(stats.metrics.winRate,{percent:true})],['Profit factor',ratioLabel(stats.metrics.profitFactor)],
        ['Expectancy (USD)',ratioLabel(stats.metrics.expectancy)],['Max drawdown (USD)',stats.metrics.maxDrawdown],['Max drawdown %',ratioLabel(stats.metrics.maxDrawdownRate,{percent:true})],['Mean R',ratioLabel(stats.metrics.averageR)],['Unresolved',stats.metrics.unresolved],
      ].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><p>Completed positions only. Partial exits stay in their original position. Open unrealized value is excluded.</p><div className="alpha-table-scroll"><table><caption>Committed balance path · starts at posting {stats.curveWindowStart}</caption><thead><tr><th>UTC</th><th>Balance USD</th></tr></thead><tbody>{stats.balanceCurve.map(p=><tr key={p.eventId}><td>{stamp(p.timeNs)}</td><td>{p.balance}</td></tr>)}</tbody></table></div></section>:<p>Analysis unavailable: {stats?.reason??'No complete projection'}. No partial result is presented as complete.</p>)}
      {tab==='Journal'&&<section><h2>Research journal</h2>{orders.map(([id])=>{const note=journal?.notes.find(n=>n.orderId===id);return <form key={`${id}:${note?.noteRevision??0}`} onSubmit={event=>{event.preventDefault();const text=new FormData(event.currentTarget).get('text');run(()=>mutate(()=>client.editJournal(view.metadata.id,{orderId:id,expectedNoteRevision:note?.noteRevision??0,text,tags:note?.tags??[]})));}}><label>Note for {id.slice(-8)}<textarea name="text" defaultValue={note?.text??''} maxLength={2000} disabled={writeDisabled}/></label><button disabled={writeDisabled}>Save note</button></form>;})}{!orders.length&&<p>Your order notes will appear here after confirmation.</p>}</section>}
      {tab==='Evidence'&&<section className="beta-evidence"><h2>Source evidence</h2><p>{view.label}</p><dl>{Object.entries(stats?.provenance??{}).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl></section>}
    </>}
    {review&&<WorkspaceModal label="Review Beta order" returnFocusRef={returnFocus} onClose={()=>{if(!busy)setReview(null);}}><section className="alpha-dialog"><h2>Review exact order</h2><p>{review.value.command.payload.side} · {review.value.command.payload.orderType} · {view.metadata.symbol}</p><dl>{Object.entries(review.value.estimate).filter(([k])=>k!=='risk').map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value??'None'}</dd></div>)}</dl>{review.value.estimate.risk&&<p>Planned loss USD {ratioLabel(review.value.estimate.risk.plannedRequestedLossUsdExact)} · budget USD {review.value.estimate.risk.budgetUsd}{review.value.estimate.risk.exceedsBudget?' · Requested size exceeds the budget.':''}</p>}<p>Actual entry requires the next eligible tick. Spread and conversion use server evidence.</p><button disabled={busy||blocked} onClick={()=>run(async()=>{await client.confirm(view.metadata.id,review.request);setReview(null);await reload();})}>Confirm order</button><button disabled={busy} onClick={()=>setReview(null)}>Back</button></section></WorkspaceModal>}
    {action&&<WorkspaceModal label="Confirm position action" returnFocusRef={returnFocus} onClose={()=>{if(!busy)setAction(null);}}><section className="alpha-dialog"><h2>{action.kind==='CLOSE'?'Request position exit':'Cancel pending order'}</h2><p>Order {action.payload.orderId} · quantity {action.payload.quantity??'all remaining'}. An exit request needs the next eligible liquidation-side tick.</p><button disabled={busy||blocked} onClick={()=>run(async()=>{await client.command(view.metadata.id,action);setAction(null);await reload();})}>Confirm {action.kind==='CLOSE'?'exit':'cancellation'}</button><button disabled={busy} onClick={()=>setAction(null)}>Back</button></section></WorkspaceModal>}
  </section>;
}
