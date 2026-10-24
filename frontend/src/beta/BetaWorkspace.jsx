import {useEffect,useMemo,useRef,useState} from 'react';
import CandleChart from '../components/CandleChart.jsx';
import IndicatorControls from '../components/IndicatorControls.jsx';
import {IndicatorPreferences} from '../workspacePreferences.js';
import {DRAWING_SPECS} from '../drawings/DrawingTypes.js';
import {productionRegistry} from '../indicators/productionRegistry.js';
import WorkspaceModal from '../workspace/WorkspaceModal.jsx';
import {BetaNewSession,BetaSessionsHub,BetaTrash,BetaWindowCard} from './BetaNewSession.jsx';
import {displayBars,stamp,TIMEFRAMES} from '../tickAlpha/display.js';
import {ratioLabel} from '../tickAlpha/annotations.js';
import {accessMessage,betaNotice,confirmation,executionCommand,newId,orderFromForm,createReplayLoop,chartPriceFormat} from './betaWorkspace.js';

// Server order status in plain words; a confirmed order is accepted, not filled, until a tick fills it.
const POSITION_GROUPS=[['ACTIVE','Open positions'],['PENDING','Pending orders'],['DONE','Closed positions']];
const groupOf=o=>o.status==='ACTIVE'||o.status==='PENDING'?o.status:'DONE';
const STATUS={ACTIVE:'Open',CLOSED:'Closed',CANCELLED:'Cancelled',EXPIRED:'Expired, no quote',UNRESOLVED:'Unresolved'};
const statusLabel=o=>o.status==='PENDING'?(o.orderType==='MARKET'?'Accepted, waiting for next tick':'Waiting for entry price'):(STATUS[o.status]??o.status)+(o.exitRequest?' · exit requested':'');
// Sign only; the exact decimal string from the server is never recomputed.
const signed=value=>typeof value==='string'&&!value.startsWith('-')&&!/^0(\.0+)?$/.test(value)?'+'+value:value;
const REVIEW_LABELS={entry:'Entry',quantity:'Lots',riskPercent:'Risk %',sl:'Stop loss',tp:'Take profit',orderType:'Order type',side:'Direction'};

export default function BetaWorkspace({client,workspace,onExpired,onAccess,onPlans}){
  const [catalog,setCatalog]=useState(null),[access,setAccess]=useState(null),[view,setView]=useState(null);
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[blocked,setBlocked]=useState(false);
  const [review,setReview]=useState(null),[action,setAction]=useState(null),[journal,setJournal]=useState(null);
  const [creating,setCreating]=useState(false),[windowPrompt,setWindowPrompt]=useState(false),[timeframe,setTimeframe]=useState('1m'),[speed,setSpeed]=useState(1),[playing,setPlaying]=useState(false);
  const [problem,setProblem]=useState(null),[offline,setOffline]=useState(()=>globalThis.navigator?.onLine===false),[sheet,setSheet]=useState(false),sheetButton=useRef(null),[moment,setMoment]=useState(''),[quickLots,setQuickLots]=useState('0.01'),[tab,setTab]=useState('Positions'),[positionsView,setPositionsView]=useState('ACTIVE'),[drawing,setDrawing]=useState('none'),[workflow,setWorkflow]=useState('QUICK');
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
    if(live.current){onAccess?.(nextAccess);setCatalog(nextCatalog);setAccess(nextAccess);setView(nextView);setJournal(nextJournal);}
    return nextView;
  }
  async function run(operation,{reconcile=false}={}){
    if(flight.current||blocked&&!reconcile)return;flight.current=true;setBusy(true);setNotice('');setProblem(null);
    try{const result=await operation();if(live.current&&reconcile){setBlocked(false);setReview(null);setAction(null);}return result??true;}
    catch(error){if(live.current){setNotice(betaNotice(error));setProblem(error.reconciliationRequired?'UNCERTAIN':error.code);setReview(null);setAction(null);if(error.reconciliationRequired)setBlocked(true);if(!client.hasSession())onExpired();}return false;}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  useEffect(()=>{
    const down=()=>setOffline(true),up=()=>setOffline(false);
    addEventListener('offline',down);addEventListener('online',up);
    return()=>{removeEventListener('offline',down);removeEventListener('online',up);};
  },[]);
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
  const priceFormat=useMemo(()=>view?chartPriceFormat(view.state.profile):undefined,[view]);
  const writeDisabled=busy||blocked||offline||playing||!owner;
  const tradingDisabled=writeDisabled||view?.savedState!=='SAVED'||view?.state.ended||view?.state.unresolved;
  const stats=view?.analysis,orders=Object.entries(view?.state.orders??{});
  async function mutate(operation){await operation();await reload();}
  // Every order, panel or quick strip, goes to server review first; confirm is a separate step.
  function requestReview(fields,focus){
    returnFocus.current=focus;setMoment('');
    run(async()=>{
      const result=await client.review(view.metadata.id,{id:newId('order'),expectedRevision:view.state.revision,payload:orderFromForm(fields,view)});
      const request=await confirmation(result);if(live.current)setReview({value:result,request});
    });
  }
  async function step(){
    const window=await client.activate(view.metadata.id);
    const current=BigInt(view.state.throughNs),start=BigInt(window.startNs);
    const targetNs=String(current<start?start:current+BigInt(speed)*BigInt(view.replayStepNs));
    await client.command(view.metadata.id,executionCommand(view,'ADVANCE',{targetNs}));const saved=await reload();
    // Announce only status changes the server committed during this step.
    const before=view.state.orders,after=Object.entries(saved.state.orders);
    // Canvas 13/18 wording; every value is the server's committed string.
    const side=o=>o.side==='LONG'?'Buy':'Sell',lines=[];let next=null;
    for(const [id,o] of after){
      const was=before[id];if(!was)continue;
      if(was.status==='PENDING'&&o.status==='ACTIVE'){lines.push(`You’re in! ${side(o)} ${o.quantity} at ${o.entryPrice}.`);next='ACTIVE';}
      else if(was.status==='ACTIVE'&&o.status==='ACTIVE'&&was.remaining!==o.remaining){lines.push(`Partial exit filled · ${o.remaining} lots still open.`);next='ACTIVE';}
      else if(was.status==='ACTIVE'&&o.status==='CLOSED'){lines.push(`Position closed · realized ${signed(o.grossPosted)} USD before commission.`);next??='DONE';}
      else if(['ACTIVE','PENDING'].includes(was.status)&&o.status==='UNRESOLVED'){lines.push('A trade has no final result: ticks are missing, so it stays unresolved instead of being guessed.');next??='DONE';}
    }
    if(live.current&&lines.length){setMoment(lines.join(' '));setPositionsView(next);}
    return saved.state.nextGroupIndex!==view.state.nextGroupIndex;
  }
  return <section className="beta-workspace tick-alpha" aria-label="Beta workspace">
    <header><h1>{workspace.name}</h1><span className="alpha-badge">Synthetic sandbox</span>
      <button disabled={busy} onClick={()=>{replay.stop();run(()=>reload(),{reconcile:true});}}>Reload saved evidence</button></header>
    <SystemState kind={blocked?'UNCERTAIN':offline?'OFFLINE':problem} busy={busy}
      onReload={()=>{replay.stop();run(()=>reload(),{reconcile:true});}}
      onRetry={()=>run(()=>reload())} onHub={()=>{setMoment('');run(()=>reload(null));}} onPlans={onPlans}
      onFreeSlot={()=>document.getElementById('beta-sessions-title')?.scrollIntoView({block:'start'})}/>
    <p role="status" aria-live="polite">{CARD_STATES.has(blocked?'UNCERTAIN':offline?'OFFLINE':problem)?'':notice||(busy?'Loading saved evidence…':'')}</p>
    {view&&moment&&<p className="beta-moment" role="status" aria-live="polite">{moment}</p>}
    {!owner&&<p>Read access. Ask the workspace owner to create or change Sessions.</p>}
    {!catalog?(busy?<div className="beta-skeleton" aria-hidden="true"><span/><span/><span/></div>:<p>Connect to the enabled Beta sandbox. No fallback feed is used.</p>):!view?<>
      {!creating&&catalog.sessions.filter(s=>catalog.savedStates[s.id]==='SAVED').length>0?<>
        <BetaSessionsHub sessions={catalog.sessions.filter(s=>catalog.savedStates[s.id]==='SAVED')} methods={catalog.methods} access={access}
          busy={busy||blocked} writeDisabled={writeDisabled} onOpen={s=>run(()=>reload(s.id))} onTrash={s=>run(()=>mutate(()=>client.trash(s.id)))} onNew={()=>setCreating(true)}/>
        {catalog.sessions.filter(s=>catalog.savedStates[s.id]==='TRASHED').length>0&&<div className="beta-hub-trash"><BetaTrash sessions={catalog.sessions.filter(s=>catalog.savedStates[s.id]==='TRASHED')} disabled={writeDisabled} onRestore={s=>run(()=>mutate(()=>client.restore(s.id)))}/></div>}
      </>:<div className="beta-hub">
        <div className="beta-hub-main"><BetaNewSession catalog={catalog} access={access} disabled={writeDisabled} run={run} client={client} reload={reload}
          onCreated={()=>setCreating(false)} onCancel={catalog.sessions.filter(s=>catalog.savedStates[s.id]==='SAVED').length?()=>setCreating(false):null}/></div>
        <aside className="beta-hub-side"><BetaWindowCard access={access}/>
          <BetaTrash sessions={catalog.sessions.filter(s=>catalog.savedStates[s.id]==='TRASHED')} disabled={writeDisabled} onRestore={s=>run(()=>mutate(()=>client.restore(s.id)))}/></aside>
      </div>}
      <p className="beta-demo-note"><span aria-hidden="true"/>Beta practice data is a short demo per pair, not a full historical month yet. No real funds are collected.</p>
      {!catalog.sessions.length&&<p>Pick a pair, a starting balance and a strategy to create your first Session. Free accounts can trade.</p>}
    </>:<>
      <div className="beta-session-heading"><button disabled={busy||blocked||playing} onClick={()=>{setMoment('');run(()=>reload(null));}}>All Beta Sessions</button><h2>{view.metadata.name} · {view.metadata.symbol}</h2><span className="beta-kind">{view.method.name} · {view.method.kind==='PROTOCOL'?'Protocol':'Free Style'}</span><strong>Saved balance ${view.state.balance}</strong></div>
      <p>{view.label}. Earlier two-year candle history is unavailable in these demos.</p>
      <div className="beta-chartbar" role="group" aria-label="Chart">
        <label>Timeframe<select aria-label="Beta timeframe" disabled={busy||playing} value={timeframe} onChange={e=>{const tf=e.target.value;run(async()=>{await reload(view.metadata.id,tf);setTimeframe(tf);setReview(null);});}}>{TIMEFRAMES.map(tf=><option key={tf}>{tf}</option>)}</select></label>
        <label>Drawing<select value={drawing} onChange={e=>setDrawing(e.target.value)}><option value="none">Cursor</option>{Object.entries(DRAWING_SPECS).map(([type,spec])=><option key={type} value={type}>{spec.name}</option>)}</select></label>
        <span className="beta-chartbar-quote">Bid <b>{view.quote?.bid??'—'}</b> · Ask <b>{view.quote?.ask??'—'}</b></span></div>
      <div className="beta-trade"><div className="beta-chart-col"><SavedBetaChart key={view.metadata.id} preferenceKey={`beta:${client.subject()}:${workspace.id}:${view.metadata.id}`} candles={bars} priceFormat={priceFormat} transition={{kind:'forward'}} researchOnly volumeAvailable={false}
        sessionId={`beta:${client.subject()}:${workspace.id}:${view.metadata.id}`} drawingWorkspace={`beta:${client.subject()}:${workspace.id}:${view.metadata.id}`} drawingStorageKey={`beta-drawings:${client.subject()}:${workspace.id}:${view.metadata.id}`}
        drawingMode={drawing} onDrawingModeChange={setDrawing} chartPreferences={chartPreferences} onChartPreferencesChange={setChartPreferences} indicatorRegistry={productionRegistry}/>
        <div className="beta-replay" role="group" aria-label="Replay">
          <button className="beta-replay-activate" disabled={tradingDisabled} onClick={event=>{returnFocus.current=event.currentTarget;if(access?.tier==='FREE'&&access.freeActivationAvailable)setWindowPrompt(true);else run(()=>mutate(()=>client.activate(view.metadata.id)));}}>Activate trading window</button>
          <button className="beta-replay-play" disabled={playing?false:tradingDisabled} aria-pressed={playing} onClick={()=>{if(playing)replay.stop();else if(replay.start())setPlaying(true);}}>{playing?'Pause replay':'Play replay'}</button>
          <button disabled={tradingDisabled} onClick={()=>run(step)}>Step replay</button>
          <label>Replay speed<select value={speed} disabled={busy||playing} onChange={e=>setSpeed(Number(e.target.value))}>{[1,4,16].map(n=><option key={n} value={n}>{n} intervals / step</option>)}</select></label>
          <span className="beta-replay-time"><small>Replay time</small>{stamp(view.state.throughNs)}</span>
        </div>
        <button type="button" ref={sheetButton} className="beta-sheet-open" aria-expanded={sheet} aria-controls="beta-order-sheet" onClick={()=>setSheet(true)}>Order panel<small>{view.method.kind==='PROTOCOL'?'Protocol · Plan':'Market or Plan'}</small></button>
        {view.method.kind==='FREE_STYLE'&&<div className="beta-quick" role="group" aria-label="Quick market order">
          <button type="button" className="beta-quick-sell" aria-label={`Sell at Bid ${view.quote?.bid??""}`} disabled={tradingDisabled||!view.quote||!quickLots.trim()} onClick={event=>requestReview(new Map([['side','SHORT'],['workflow','QUICK'],['quantity',quickLots.trim()]]),event.currentTarget)}>Sell<small>{view.quote?.bid??'—'}</small></button>
          <label>Lots<input value={quickLots} onChange={e=>setQuickLots(e.target.value)} inputMode="decimal" disabled={tradingDisabled}/></label>
          <button type="button" className="beta-quick-buy" aria-label={`Buy at Ask ${view.quote?.ask??""}`} disabled={tradingDisabled||!view.quote||!quickLots.trim()} onClick={event=>requestReview(new Map([['side','LONG'],['workflow','QUICK'],['quantity',quickLots.trim()]]),event.currentTarget)}>Buy<small>{view.quote?.ask??'—'}</small></button>
          <span>Market order · server review opens next, no stop or target</span>
        </div>}</div>
      {sheet&&<div className="beta-sheet-backdrop" aria-hidden="true" onClick={()=>{setSheet(false);sheetButton.current?.focus();}}/>}
      {/* On phones (canvas 20) the panel is a bottom sheet; on desktop it is always the right-hand panel. */}
      <form id="beta-order-sheet" className={`beta-order-form${sheet?' beta-sheet-is-open':''}`} onKeyDown={event=>{if(event.key==='Escape'&&sheet){setSheet(false);sheetButton.current?.focus();}}} onSubmit={event=>{event.preventDefault();const back=sheet?sheetButton.current:event.currentTarget.querySelector('button:not([type])');setSheet(false);requestReview(new FormData(event.currentTarget),back);}}><div className="beta-sheet-head"><h2>New order</h2><button type="button" className="beta-sheet-close" aria-label="Close order panel" onClick={()=>{setSheet(false);sheetButton.current?.focus();}}>×</button></div><p className="beta-muted">Review never fills an order. Buys fill at Ask, sells at Bid on the next eligible tick.</p>
        <fieldset className="beta-side" disabled={tradingDisabled}><legend>Direction</legend><label className="beta-side-sell"><input type="radio" name="side" value="SHORT"/><span>Sell<small>Bid {view.quote?.bid??'—'}</small></span></label><label className="beta-side-buy"><input type="radio" name="side" value="LONG" defaultChecked/><span>Buy<small>Ask {view.quote?.ask??'—'}</small></span></label></fieldset>
        <label>Workflow<select name="workflow" disabled={tradingDisabled||view.method.kind==='PROTOCOL'} value={view.method.kind==='PROTOCOL'?'PLANNED':workflow} onChange={e=>setWorkflow(e.target.value)}><option value="QUICK">Market</option><option value="PLANNED">Planned</option></select></label>
        {(view.method.kind==='PROTOCOL'||workflow==='PLANNED')&&<><label>Planned order type<select name="orderType" disabled={tradingDisabled}><option>LIMIT</option><option>STOP</option></select></label>
        <label>Planned entry<input name="entry" inputMode="decimal" required disabled={tradingDisabled}/></label></>}
        <label>Lots<input name="quantity" defaultValue={view.method.kind==='PROTOCOL'?'':'0.01'} placeholder={view.method.kind==='PROTOCOL'?'Calculated by server':undefined} inputMode="decimal" required disabled={tradingDisabled||view.method.kind==='PROTOCOL'}/></label>
        <label>Stop loss<input name="sl" inputMode="decimal" disabled={tradingDisabled}/></label><label>Take profit<input name="tp" inputMode="decimal" disabled={tradingDisabled||view.method.kind==='PROTOCOL'}/></label>
        {view.method.kind==='PROTOCOL'&&<><p>Protocol risk {view.method.riskPercent}% · R:R {view.method.rr}. The server owns quantity and target; manual exits are locked.</p>{view.method.conditions.map(c=><label key={c.id}>{c.label}<select name={'condition:'+c.id} disabled={tradingDisabled}><option value="NOT_ASSESSED">Not assessed</option><option value="PASS">Pass</option><option value="FAIL">Fail</option></select></label>)}</>}<button disabled={tradingDisabled||!view.quote}>Review order</button>
      </form></div>
      {!view.chart&&<p>Chart display unavailable. Committed evidence remains saved.</p>}
      <nav className="beta-tabs" aria-label="Session views">{['Positions','Statistics','Journal','Evidence'].map(t=><button key={t} aria-pressed={tab===t} onClick={()=>setTab(t)}>{t}</button>)}</nav>
      {tab==='Positions'&&<section className="beta-positions" aria-label="Positions">
        <div className="beta-subtabs" role="group" aria-label="Order groups">{POSITION_GROUPS.map(([key,label])=><button key={key} type="button" aria-pressed={positionsView===key} onClick={()=>setPositionsView(key)}>{label} <span>{orders.filter(([,o])=>groupOf(o)===key).length}</span></button>)}</div>
        <div className="alpha-table-scroll"><table><caption>{POSITION_GROUPS.find(([key])=>key===positionsView)[1]} · committed by the server</caption><thead><tr><th>Order</th><th>Direction</th><th>Status</th><th>Lots</th><th>Entry</th><th>Stop loss</th><th>Take profit</th><th>Realized gross USD</th><th>Action</th></tr></thead><tbody>{orders.filter(([,o])=>groupOf(o)===positionsView).map(([id,o])=><tr key={id}><td>{id.slice(-8)}</td><td><span className={`beta-side-pill beta-side-pill-${o.side==='LONG'?'buy':'sell'}`}>{o.side==='LONG'?'Buy':'Sell'}</span></td><td>{statusLabel(o)}</td><td>{o.status==='ACTIVE'&&o.remaining!==o.quantity?`${o.remaining} of ${o.quantity} open`:o.quantity}</td><td>{o.entryPrice?<>Filled {o.entryPrice}</>:o.orderType==='MARKET'?'Market, next tick':`${o.orderType==='LIMIT'?'Limit':'Stop'} ${o.entry}`}</td><td>{o.sl??'—'}</td><td>{o.tp??'—'}</td><td>{o.entryPrice?signed(o.grossPosted):'—'}</td><td>{['PENDING','ACTIVE'].includes(o.status)&&<button disabled={tradingDisabled||!!o.exitRequest||(o.status==='ACTIVE'&&view.method.kind!=='FREE_STYLE')} onClick={event=>{returnFocus.current=event.currentTarget;setAction(executionCommand(view,o.status==='PENDING'?'CANCEL':'CLOSE',{orderId:id,...(o.status==='ACTIVE'?{quantity:null}:{})}));}}>{o.status==='PENDING'?'Cancel pending':'Close position'}</button>}{o.status==='ACTIVE'&&view.method.kind==='FREE_STYLE'&&<form onSubmit={event=>{event.preventDefault();const quantity=new FormData(event.currentTarget).get('partial');returnFocus.current=event.currentTarget.querySelector('button');setAction(executionCommand(view,'CLOSE',{orderId:id,quantity}));}}><label>Partial lots<input name="partial" aria-label={'Partial lots '+id.slice(-8)} required inputMode="decimal" disabled={tradingDisabled||!!o.exitRequest}/></label><button disabled={tradingDisabled||!!o.exitRequest}>Review partial close</button></form>}</td></tr>)}</tbody></table>
        {!orders.some(([,o])=>groupOf(o)===positionsView)&&<p className="beta-empty-row">{orders.length?'Nothing here right now.':'No orders yet. Activate trading, step the replay, then review an order.'}</p>}</div>
        <p className="beta-muted">Open positions show no unrealized value: the server does not provide it, and it is not estimated here. Realized gross is before commission.</p></section>}
      {tab==='Statistics'&&<StatisticsPanel stats={stats}/>}
      {tab==='Journal'&&<JournalPanel orders={orders} journal={journal} completed={stats?.status==='COMPLETE'?stats.completed:[]} disabled={writeDisabled} onSave={(orderId,note,text,tags)=>run(()=>mutate(()=>client.editJournal(view.metadata.id,{orderId,expectedNoteRevision:note?.noteRevision??0,text,tags})))}/>}
      {tab==='Evidence'&&<section className="beta-evidence"><h2>Source evidence</h2><p>{view.label}</p><dl>{Object.entries(stats?.provenance??{}).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl></section>}
    </>}
    {review&&<WorkspaceModal label="Review Beta order" returnFocusRef={returnFocus} onClose={()=>{if(!busy)setReview(null);}}><section className="alpha-dialog beta-dialog"><h2>Review exact order</h2><p>{review.value.command.payload.side} · {review.value.command.payload.orderType} · {view.metadata.symbol}</p><dl className="beta-review-values">{Object.entries(review.value.estimate).filter(([k])=>k!=='risk').map(([key,value])=><div key={key}><dt>{REVIEW_LABELS[key]??key}</dt><dd>{value??'None'}</dd></div>)}</dl>{review.value.estimate.risk&&<p>Planned loss USD {ratioLabel(review.value.estimate.risk.plannedRequestedLossUsdExact)} · budget USD {review.value.estimate.risk.budgetUsd}{review.value.estimate.risk.exceedsBudget?' · Requested size exceeds the budget.':''}</p>}<p>Actual entry requires the next eligible tick. Spread and conversion use server evidence.</p><button disabled={busy||blocked} onClick={()=>run(async()=>{await client.confirm(view.metadata.id,review.request);setReview(null);await reload();if(live.current){setMoment('Order accepted — filling on the next tick…');setTab('Positions');setPositionsView('PENDING');}})}>Confirm order</button><button disabled={busy} onClick={()=>setReview(null)}>Back</button></section></WorkspaceModal>}
    {windowPrompt&&view&&<WorkspaceModal label="Start today’s replay window" returnFocusRef={returnFocus} onClose={()=>{if(!busy)setWindowPrompt(false);}}><section className="alpha-dialog beta-dialog beta-dialog-window"><span className="beta-kicker">BEFORE THE FIRST TRADE</span><h2>Start today’s replay window?</h2><p>Free includes one window a day. Once started, this Session stays tradable. Next free window: 00:00 {access.resetTimezone}.</p><button disabled={busy||blocked} onClick={()=>run(async()=>{await client.activate(view.metadata.id);setWindowPrompt(false);await reload();}).then(ok=>{if(ok&&live.current&&replay.start())setPlaying(true);})}>Start window &amp; play</button><button disabled={busy} onClick={()=>setWindowPrompt(false)}>Just look around</button></section></WorkspaceModal>}
    {action&&<WorkspaceModal label="Confirm position action" returnFocusRef={returnFocus} onClose={()=>{if(!busy)setAction(null);}}><section className="alpha-dialog beta-dialog"><h2>{action.kind==='CLOSE'?'Request position exit':'Cancel pending order'}</h2><p>Order {action.payload.orderId} · quantity {action.payload.quantity??'all remaining'}. An exit request needs the next eligible liquidation-side tick.</p><button disabled={busy||blocked} onClick={()=>run(async()=>{await client.command(view.metadata.id,action);setAction(null);await reload();if(live.current)setMoment(action.kind==='CLOSE'?'Exit requested · waiting for the next tick.':'Pending order cancelled.');})}>Confirm {action.kind==='CLOSE'?'exit':'cancellation'}</button><button disabled={busy} onClick={()=>setAction(null)}>Back</button></section></WorkspaceModal>}
  </section>;
}


// Canvas 15. Every number is the server's committed value; the line only places
// points on screen. Open positions are excluded, so this is a balance line, not equity.
function StatisticsPanel({stats}){
  if(stats?.status!=='COMPLETE')return <section className="beta-stats-empty"><h2>Statistics</h2><p>Statistics unavailable: {stats?.reason??'no complete projection yet'}. Nothing partial is shown as complete.</p></section>;
  const m=stats.metrics,a=stats.account;
  const tiles=[
    ['Net result, closed trades (USD)',signed(m.realizedNetCompleted),'hero'],
    ['Balance (USD)',a.balance,''],
    ['Win rate',m.winRate?`${ratioLabel(m.winRate,{percent:true})} · ${m.wins} W / ${m.losses} L`:`${m.wins} W / ${m.losses} L`,''],
    ['Profit factor',ratioLabel(m.profitFactor),''],
    ['Expectancy (USD)',ratioLabel(m.expectancy),''],
    ['Average R',m.averageR?`${ratioLabel(m.averageR)} · ${m.rEligible} of ${m.tradeCount}`:'Unavailable',''],
    ['Max drawdown',`${m.maxDrawdown} USD · ${ratioLabel(m.maxDrawdownRate,{percent:true})}`,''],
    ['Trades · unresolved',`${m.tradeCount} · ${m.unresolved}`,m.unresolved?'warn':'']];
  const more=[['Average win (USD)',ratioLabel(m.averageWin)],['Average loss (USD)',ratioLabel(m.averageLoss)],['Best win streak',m.maxWinStreak],['Worst loss streak',m.maxLossStreak],['Commission (USD)',a.commission],['Average hold',duration(m.averageDurationNs)]];
  return <section className="beta-stats" aria-labelledby="beta-stats-h">
    <div className="beta-stats-head"><h2 id="beta-stats-h">Statistics</h2><span>Closed positions only · open P&amp;L excluded · unresolved trades counted apart, never guessed</span></div>
    <dl className="beta-kpis">{tiles.map(([label,value,tone])=><div key={label} className={tone?'beta-kpi-'+tone:undefined}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <BalanceLine stats={stats}/>
    <dl className="beta-kpis beta-kpis-small">{more.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    {stats.completed.length>0&&<div className="alpha-table-scroll"><table className="beta-trades"><caption>Closed trades · committed by the server</caption><thead><tr><th>#</th><th>Order</th><th>Net USD</th><th>R</th><th>Held</th></tr></thead>
      <tbody>{stats.completed.map((c,i)=><tr key={c.id}><td>{i+1}</td><td>{c.id.slice(-8)}</td><td className={sign(c.net)}>{signed(c.net)}</td><td>{c.rMultiple?ratioLabel(c.rMultiple):'—'}</td><td>{duration(c.durationNs)}</td></tr>)}</tbody></table></div>}
  </section>;
}

function BalanceLine({stats}){
  const points=stats.balanceCurve,start=stats.account.initialBalance;
  if(!points.length)return <div className="beta-line-empty">No committed cash postings yet. The balance line starts with the first fill.</div>;
  // Geometry only: Number() places points; labels always show the exact strings.
  const values=[start,...points.map(p=>p.balance)],nums=values.map(Number);
  const lo=Math.min(...nums),hi=Math.max(...nums),span=hi-lo||1,W=720,H=180;
  const xy=nums.map((v,i)=>`${(i/(nums.length-1||1)*W).toFixed(1)},${(H-(v-lo)/span*H).toFixed(1)}`).join(' ');
  const low=values[nums.indexOf(lo)],high=values[nums.indexOf(hi)],end=values.at(-1);
  return <figure className="beta-line" aria-label={`Committed balance line from ${start} to ${end} USD, low ${low}, high ${high}`}>
    <svg viewBox={`-4 -8 ${W+8} ${H+16}`} preserveAspectRatio="none" aria-hidden="true"><polyline points={xy} fill="none" stroke="#1378f5" strokeWidth="3" vectorEffect="non-scaling-stroke" strokeLinejoin="round"/></svg>
    <figcaption><span>Start <b>{start}</b></span><span>Low <b>{low}</b></span><span>High <b>{high}</b></span><span>Now <b>{end}</b></span>
      <small>Committed balance line (USD, cash postings{stats.curveWindowStart>0?`, last ${points.length}`:''}). Not an equity curve: open positions are not marked to market.</small></figcaption>
  </figure>;
}

// Canvas 14. Tags follow the server contract: at most 8, 1–32 characters, unique.
function JournalPanel({orders,journal,completed,disabled,onSave}){
  const [filter,setFilter]=useState('ALL'),[picked,setPicked]=useState(null);
  const result=new Map(completed.map(c=>[c.id,c])),notes=new Map((journal?.notes??[]).map(n=>[n.orderId,n]));
  const rows=orders.filter(([id,o])=>{const net=result.get(id)?.net;
    return filter==='ALL'||filter==='BUY'&&o.side==='LONG'||filter==='SELL'&&o.side==='SHORT'||filter==='WIN'&&net&&sign(net)==='pos'||filter==='LOSS'&&net&&sign(net)==='neg'||filter==='NOTES'&&notes.get(id)?.text;});
  const current=orders.find(([id])=>id===picked);
  if(!orders.length)return <section className="beta-journal-empty"><h2>Journal</h2><p>No trades yet. Press Play in this Session and place your first order; it lands here automatically.</p></section>;
  return <section className="beta-journal" aria-labelledby="beta-journal-h">
    <div className="beta-stats-head"><h2 id="beta-journal-h">Journal</h2><span>Every confirmed order in this Session, with your notes</span></div>
    <div className="beta-subtabs" role="group" aria-label="Journal filter">{[['ALL','All trades'],['BUY','Buy'],['SELL','Sell'],['WIN','Winners'],['LOSS','Losers'],['NOTES','With notes']].map(([k,l])=><button key={k} type="button" aria-pressed={filter===k} onClick={()=>setFilter(k)}>{l}</button>)}</div>
    <div className="beta-journal-grid">
      <div className="alpha-table-scroll"><table className="beta-trades"><caption>Orders · {rows.length} shown</caption><thead><tr><th>Order</th><th>Side</th><th>Lots</th><th>Entry</th><th>Status</th><th>Net USD</th><th>R</th><th>Tags</th><th>Note</th></tr></thead>
        <tbody>{rows.map(([id,o])=>{const r=result.get(id),n=notes.get(id);return <tr key={id} className={picked===id?'beta-row-picked':undefined}>
          <td><button type="button" className="beta-row-open" onClick={()=>setPicked(id)} aria-label={'Open journal for '+id.slice(-8)}>{id.slice(-8)}</button></td>
          <td><span className={`beta-side-pill beta-side-pill-${o.side==='LONG'?'buy':'sell'}`}>{o.side==='LONG'?'Buy':'Sell'}</span></td><td>{o.quantity}</td><td>{o.entryPrice??'—'}</td><td>{o.status}</td>
          <td className={r?sign(r.net):undefined}>{r?signed(r.net):'—'}</td><td>{r?.rMultiple?ratioLabel(r.rMultiple):'—'}</td>
          <td>{n?.tags?.length?n.tags.map(t=><span key={t} className="beta-tag">#{t}</span>):'—'}</td><td>{n?.text?'✓':'—'}</td></tr>;})}</tbody></table>
        {!rows.length&&<p className="beta-empty-row">No orders match this filter.</p>}</div>
      {current?<JournalEditor key={`${current[0]}:${notes.get(current[0])?.noteRevision??0}`} id={current[0]} order={current[1]} result={result.get(current[0])} note={notes.get(current[0])} disabled={disabled} onSave={onSave} onClose={()=>setPicked(null)}/>
        :<aside className="beta-journal-hint">Pick an order to write a note and tags. Rating is planned; the server does not store it yet.</aside>}
    </div>
  </section>;
}

function JournalEditor({id,order,result,note,disabled,onSave,onClose}){
  const [text,setText]=useState(note?.text??''),[tagText,setTagText]=useState((note?.tags??[]).join(', '));
  const tags=tagText.split(',').map(t=>t.trim()).filter(Boolean);
  const problem=tags.length>8?'Use at most 8 tags.':tags.some(t=>t.length>32)?'Each tag is at most 32 characters.':new Set(tags).size!==tags.length?'Remove duplicate tags.':text.length>4000?'Notes are at most 4000 characters.':'';
  return <aside className="beta-journal-editor" aria-labelledby="beta-je-h">
    <div className="beta-je-head"><span className="beta-kicker">TRADE · {id.slice(-8)}</span><button type="button" className="beta-je-close" onClick={onClose} aria-label="Close journal entry">×</button></div>
    <h3 id="beta-je-h">{order.side==='LONG'?'Buy':'Sell'} {order.quantity} lots{result?` · ${signed(result.net)} USD`:''}</h3>
    <dl className="beta-je-facts"><div><dt>Entry</dt><dd>{order.entryPrice??'Not filled'}</dd></div><div><dt>Stop loss</dt><dd>{order.sl??'—'}</dd></div><div><dt>Take profit</dt><dd>{order.tp??'—'}</dd></div><div><dt>R</dt><dd>{result?.rMultiple?ratioLabel(result.rMultiple):'—'}</dd></div></dl>
    <form onSubmit={event=>{event.preventDefault();if(!problem)onSave(id,note,text,tags);}}>
      <label>Tags, comma separated<input value={tagText} onChange={e=>setTagText(e.target.value)} placeholder="breakout, london" disabled={disabled} aria-invalid={!!problem&&tags.length>0}/></label>
      <label>Note<textarea value={text} onChange={e=>setText(e.target.value)} maxLength={4000} disabled={disabled} placeholder="What did you see? Did you follow your plan?"/></label>
      {problem&&<small className="beta-field-error">{problem}</small>}
      <button disabled={disabled||!!problem}>Save note</button>
    </form>
  </aside>;
}

const sign=value=>typeof value==='string'&&value.startsWith('-')?'neg':/^0(\.0+)?$/.test(String(value))?'zero':'pos';
function duration(value){
  if(value===null||value===undefined)return '—';
  const ns=typeof value==='object'?BigInt(value.numerator)/BigInt(value.denominator):BigInt(value);
  const s=Number(ns/1000000000n),h=Math.floor(s/3600),m=Math.floor(s%3600/60);
  return h?`${h}h ${m}m`:m?`${m}m ${s%60}s`:`${s}s`;
}


// Canvas 24 system and limit states. Every card offers a way back; saved Sessions are never at risk.
const CARD_STATES=new Set(['UNCERTAIN','OFFLINE','SERVICE_UNAVAILABLE','SERVICE_BUSY','SAVED_SESSION_LIMIT','DAILY_WINDOW_LIMIT']);
function SystemState({kind,busy,onReload,onRetry,onHub,onPlans,onFreeSlot}){
  if(!CARD_STATES.has(kind))return null;
  const cards={
    UNCERTAIN:['warn','We couldn’t confirm that change','The request outcome is uncertain. Reload saved evidence before sending anything else, so nothing is placed twice.',[['Reload saved evidence',onReload]]],
    OFFLINE:['dark','Connection lost','You are offline. Replay paused and nothing new was sent. Reconnect, then reload saved evidence before trading again.',[['Try again',onRetry]]],
    SERVICE_UNAVAILABLE:['dark','The service is unavailable','Nothing new was sent. Your Sessions and journal are saved. Try again in a moment.',[['Try again',onRetry]]],
    SERVICE_BUSY:['dark','The service is busy','Too many requests at once. Wait a moment, then try again.',[['Try again',onRetry]]],
    SAVED_SESSION_LIMIT:['light','Your Free Sessions are full','Move a Session you’re done with to Trash, or go Pro for more room.',[['Choose a Session to Trash',onFreeSlot],onPlans&&['See plans',onPlans]]],
    DAILY_WINDOW_LIMIT:['light','You’ve used today’s replay window','Keep trading in Sessions you started earlier, or come back after 00:00 UTC.',[['My started Sessions',onHub],onPlans&&['See plans',onPlans]]]};
  const [tone,title,text,actions]=cards[kind];
  return <section className={'beta-system beta-system-'+tone} role="alert">
    <div><h2>{title}</h2><p>{text}</p></div>
    <div className="beta-system-actions">{actions.filter(Boolean).map(([label,fn])=><button key={label} type="button" disabled={busy} onClick={fn}>{label}</button>)}</div>
  </section>;
}

// Reuse the existing chart/indicator owners with identity-and-Session scoped preferences.
function SavedBetaChart({preferenceKey,...props}){
  const [saved]=useState(()=>{const store=new IndicatorPreferences(()=>globalThis.localStorage,preferenceKey,productionRegistry);return {store,instances:store.load()};});
  const [instances,setInstances]=useState(saved.instances),[status,setStatus]=useState(saved.store.status);
  return <><div className="beta-indicator-tools"><IndicatorControls instances={instances} onChange={next=>{try{saved.store.normalize(next);}catch{setStatus('Use at most 16 valid indicator instances. Your previous configuration is unchanged.');return;}saved.store.save(next);setInstances(next);setStatus(saved.store.status);}}/><small>Indicators use revealed bars only. Insufficient history remains warmup.</small>{status&&<p role="status">{status}</p>}</div>
    <div className="beta-chart"><CandleChart {...props} indicatorInstances={instances} onIndicatorError={()=>setStatus('Indicator configuration unavailable. Other saved evidence is unchanged.')}/></div></>;
}
