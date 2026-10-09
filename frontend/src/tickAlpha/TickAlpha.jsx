import {useEffect,useRef,useState} from 'react';
import WorkspaceModal from '../workspace/WorkspaceModal.jsx';
import {api,id,sessionPath,selectSessionUrl,loadResearchContext,noticeText} from './client.js';
import {command} from './client.js';
import AlphaWorkspace from './AlphaWorkspace.jsx';
import AlphaTerminal from './AlphaTerminal.jsx';
import './tickAlpha.css';

const initialPlan=()=>({side:'LONG',orderType:'MARKET',workflow:'QUICK',entry:'2000',sl:'1998',tp:'2004',
  quantity:'0.1',riskPercent:'1',observations:[]});

export default function TickAlpha(){
  const [catalog,setCatalog]=useState(null),[view,setView]=useState(null),[busy,setBusy]=useState(false);
  const [notice,setNotice]=useState(''),[dialog,setDialog]=useState(null),[review,setReview]=useState(null);
  const [kind,setKind]=useState('FREE_STYLE'),[plan,setPlan]=useState(initialPlan),[planRevision,setPlanRevision]=useState(0);
  const flight=useRef(false),returnFocus=useRef(null);
  const [connecting,setConnecting]=useState(true);
  const creationId=useRef(null);
  const [timeframe,setTimeframe]=useState('1m'),[pauseToken,setPauseToken]=useState(0);
  const [orderAction,setOrderAction]=useState(null);
  const loadWorkspace=(session,tf=timeframe)=>api(sessionPath(session)+'/view',{timeframe:tf});
  useEffect(()=>{
    let mounted=true;
    (async()=>{try{
      const selected=new URL(window.location.href).searchParams.get('session');
      const result=await loadResearchContext(selected,{active:()=>mounted});
      if(result){setCatalog(result.catalog);setView(result.view);}
    }catch(error){if(mounted)setNotice(error.message);}finally{if(mounted)setConnecting(false);}})();
    return ()=>{mounted=false;};
  },[]);
  const run=async action=>{
    if(flight.current)return;
    flight.current=true;setBusy(true);setNotice('');
    try{return await action()??true;}catch(error){setNotice(error.message);return false;}finally{flight.current=false;setBusy(false);}
  };
  const reopen=async session=>{
    setPauseToken(n=>n+1);
    const saved=await loadWorkspace(session);setView(saved);selectSessionUrl(session);setReview(null);setDialog(null);setOrderAction(null);
    setPlan(initialPlan());setPlanRevision(0);
    setNotice('Session reopened from its committed local state.');
  };
  const edit=patch=>{setPlan(p=>({...p,...patch}));setPlanRevision(r=>r+1);setReview(null);};
  const protocol=view?.method.kind==='PROTOCOL';
  const planned=protocol||plan.workflow==='PLANNED';
  const openReview=event=>{returnFocus.current=event.currentTarget;return run(async()=>{
    setPauseToken(n=>n+1);
    const draft={...plan,workflow:planned?'PLANNED':'QUICK',orderType:protocol&&plan.orderType==='MARKET'?'LIMIT':plan.orderType,
      ...(protocol?{tp:null,riskPercent:null,quantity:null}:{}),
      ...(!protocol&&planned?{quantity:null}:{}),
      ...(!planned?{sl:null,tp:null}:{}),
      observations:protocol?view.method.conditions.map(c=>({conditionId:c.id,outcome:plan.observations.find(o=>o.conditionId===c.id)?.outcome||'NOT_ASSESSED'})):[]};
    const request=await api('/reviews',{sessionId:view.metadata.id,requestId:id('order'),expectedRevision:view.state.revision,
      planId:planned?id('plan'):null,planRevision:planned?planRevision:null,draft});
    setReview(request);setDialog('review');
  });};
  const confirm=()=>run(async()=>{
    await api(sessionPath(view.metadata.id)+'/confirm',{reviewId:review.review.command.commandId,reviewHash:review.reviewHash});
    setView(await loadWorkspace(view.metadata.id));setDialog(null);setReview(null);
    setNotice('Order accepted and saved locally. A fill requires the next eligible tick.');
  });
  const createMethod=event=>{
    event.preventDefault();const fields=new FormData(event.currentTarget);
    run(async()=>{
      const value={schemaVersion:1,artifact:'BTL-LOCAL-METHOD-1',id:creationId.current,name:fields.get('name'),kind,
        checklistOn:kind==='PROTOCOL'&&fields.get('checklist')==='ON',
        conditions:kind==='PROTOCOL'?String(fields.get('conditions')).split('\n').filter(s=>s.trim()).map((s,i)=>({id:`condition:${i}`,label:s.trim()})):[],
        riskPercent:kind==='PROTOCOL'?fields.get('risk'):null,rr:kind==='PROTOCOL'?fields.get('rr'):null};
      await api('/methods',value);setCatalog(await api('/catalog'));setDialog(null);
      setNotice('Immutable Method saved. Create a Session to use it.');
    });
  };
  const requestAction=(order,kind,quantity=null)=>{
    returnFocus.current=document.activeElement;setNotice('');
    const payload={orderId:order.id,...(kind==='CLOSE'?{quantity}:{})};
    setPauseToken(n=>n+1);setOrderAction({order,kind,quantity,command:command(view,kind,payload)});setDialog('action');
  };
  const confirmAction=()=>run(async()=>{
    await api(sessionPath(view.metadata.id)+'/commands',orderAction.command);
    setView(await loadWorkspace(view.metadata.id));setDialog(null);setOrderAction(null);
    setNotice(orderAction.kind==='CANCEL'?'Pending order cancellation committed.':'Exit requested. Actual closure needs the next eligible liquidation-side tick.');
  });
  const createSession=event=>{
    event.preventDefault();const fields=new FormData(event.currentTarget);
    run(async()=>{
      const saved=await api('/sessions',{id:creationId.current,name:fields.get('name'),methodId:fields.get('method'),
        initialBalance:fields.get('balance'),startPeriod:'2020-01'});
      const workspace=await loadWorkspace(saved.metadata.id);
      setCatalog(await api('/catalog'));setView(workspace);selectSessionUrl(saved.metadata.id);setDialog(null);setPlan(initialPlan());setPlanRevision(0);
      setNotice('Session created. The initial chart prefix is warmup; orders use subsequent ticks.');
    });
  };
  return <main className="tick-alpha">
    <header><div><strong>Backtest Lab</strong><span className="alpha-badge">Local tick alpha · Synthetic fixture</span></div><a href="/">Open local v1</a></header>
    <section className="alpha-context" aria-label="Method and Session">
      <button disabled={busy||!catalog} onClick={event=>{returnFocus.current=event.currentTarget;setNotice('');setPauseToken(n=>n+1);creationId.current=id('method');setKind('FREE_STYLE');setDialog('method');}}>Create Method</button>
      <button disabled={busy||!catalog?.methods.length} onClick={event=>{returnFocus.current=event.currentTarget;setNotice('');setPauseToken(n=>n+1);creationId.current=id('session');setDialog('session');}}>Create Session</button>
      <label>Reopen Session<select aria-label="Reopen Session" disabled={busy||!catalog} value={view?.metadata.id||''} onChange={e=>{if(e.target.value)run(()=>reopen(e.target.value));}}>
        <option value="">Choose saved Session</option>{catalog?.sessions.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      {view&&<><span>{view.method.name} · {view.method.kind==='PROTOCOL'?'Protocol':'Free Style'}</span><button disabled={busy} onClick={()=>run(()=>reopen(view.metadata.id))}>Reload saved Session</button></>}
    </section>
    {!catalog?<section className="alpha-empty"><h1>Local tick service</h1><p>Start the local alpha service and database to create or reopen a Session.</p><p>{connecting?'Connecting to the saved local workspace…':'Your local service is unavailable. Start it, then retry the connection.'}</p><button disabled={busy||connecting} onClick={()=>run(async()=>{
        setConnecting(true);try{const result=await loadResearchContext(new URL(window.location.href).searchParams.get('session'),{timeframe});setCatalog(result.catalog);setView(result.view);}finally{setConnecting(false);}
      })}>Retry connection</button></section>:!view?<section className="alpha-empty"><h1>Start a research Session</h1><p>Create a Method, then a Session. Your Method rules and balance are saved locally.</p><p>This alpha uses an authored XAUUSD/USD fixture, not historical market prices.</p></section>:<>
      <section className="alpha-session"><h1>{view.metadata.name}</h1><p>XAUUSD · USD · authored January 2020 fixture · {view.method.name}</p><p>Saved balance <strong>${view.state.balance}</strong> · {view.state.unresolved?'Unresolved evidence':'Ready'} · revision {view.state.revision}</p></section>
      <div className="alpha-workspace"><AlphaWorkspace key={view.metadata.id} view={view} timeframe={timeframe} busy={busy} pauseToken={pauseToken} onNotice={setNotice}
        onTimeframe={tf=>run(async()=>{const saved=await loadWorkspace(view.metadata.id,tf);setView(saved);setTimeframe(tf);})}
        onReplay={(kind,targetNs)=>run(async()=>{
          await api(sessionPath(view.metadata.id)+'/commands',command(view,kind,{targetNs}));
          const saved=await loadWorkspace(view.metadata.id);setView(saved);
          if(kind==='ADVANCE'&&saved.state.nextGroupIndex===view.state.nextGroupIndex){setNotice('No additional quote was revealed at this requested boundary. Replay paused.');return false;}
          return true;
        })} onPriceSelect={price=>edit({entry:String(price)})}/>
      <aside className="alpha-ticket"><h2>Plan an order</h2><p className="alpha-ticket-guide">1. Set the intent · 2. Review exact values · 3. Confirm · 4. Reveal the next tick</p>
        <label>Workflow<select aria-label="Workflow" disabled={busy||protocol} value={planned?'PLANNED':'QUICK'} onChange={e=>edit({workflow:e.target.value,orderType:e.target.value==='QUICK'?'MARKET':'LIMIT'})}><option value="QUICK">Quick</option><option value="PLANNED">Planned</option></select></label>
        <label>Direction<select disabled={busy} value={plan.side} onChange={e=>edit({side:e.target.value})}><option value="LONG">Buy / Long</option><option value="SHORT">Sell / Short</option></select></label>
        <label>Order type<select aria-label="Order type" disabled={busy||!planned} value={protocol&&plan.orderType==='MARKET'?'LIMIT':plan.orderType} onChange={e=>edit({orderType:e.target.value})}>{!protocol&&<option value="MARKET">Market</option>}<option value="LIMIT">Limit</option><option value="STOP">Stop</option></select></label>
        {planned?<><label>Entry<input aria-label="Entry" inputMode="decimal" value={plan.entry} disabled={busy} onChange={e=>edit({entry:e.target.value})}/></label><label>Stop Loss<input aria-label="Stop Loss" inputMode="decimal" value={plan.sl} disabled={busy} onChange={e=>edit({sl:e.target.value})}/></label>{protocol?<p>Target and quantity derive from locked RR {view.method.rr} and risk {view.method.riskPercent}%.</p>:<><label>Take Profit<input aria-label="Take Profit" inputMode="decimal" value={plan.tp} disabled={busy} onChange={e=>edit({tp:e.target.value})}/></label><label>Risk %<input inputMode="decimal" value={plan.riskPercent} disabled={busy} onChange={e=>edit({riskPercent:e.target.value})}/></label></>}</>:<label>Quantity (lots)<input aria-label="Quantity (lots)" inputMode="decimal" value={plan.quantity} disabled={busy} onChange={e=>edit({quantity:e.target.value})}/></label>}
        {protocol&&<fieldset><legend>Checklist · enforcement {view.method.checklistOn?'ON':'OFF'}</legend>{view.method.conditions.map(c=><label key={c.id}>{c.label}<select aria-label={c.label} disabled={busy} value={plan.observations.find(o=>o.conditionId===c.id)?.outcome||'NOT_ASSESSED'} onChange={e=>edit({observations:[...plan.observations.filter(o=>o.conditionId!==c.id),{conditionId:c.id,outcome:e.target.value}]})}><option value="NOT_ASSESSED">Not assessed</option><option value="PASS">Pass</option><option value="FAIL">Fail</option></select></label>)}</fieldset>}
        <button disabled={busy||view.state.unresolved} onClick={openReview}>Review order</button><p>Quote-based simulation; no broker fill, margin, liquidity or slippage claim. Default fixture commission is zero.</p>
      </aside></div>
      <AlphaTerminal key={view.metadata.id} view={view} busy={busy} onAction={requestAction}/>
    </>}
    <footer role="status" aria-live="polite">{noticeText(notice)||'Synthetic / test only. Local state is durable; historical-data precision acceptance remains separate.'}</footer>
    {dialog==='action'&&orderAction&&<WorkspaceModal returnFocusRef={returnFocus} label="Confirm position action" onClose={()=>{if(!busy){setDialog(null);setOrderAction(null);}}}><section className="alpha-dialog"><h2>{orderAction.kind==='CANCEL'?'Cancel pending order':orderAction.quantity===null?'Request full close':'Request partial close'}</h2><p>{orderAction.order.side} · {orderAction.order.id}</p><p>{orderAction.kind==='CLOSE'?`Quantity: ${orderAction.quantity??orderAction.order.remaining} lots. A request does not settle the trade; the next eligible observed Bid/Ask determines its exit.`:'This cancels an unfilled intent; it does not close a position.'}</p>{notice&&<p role="alert">{noticeText(notice)}</p>}<button disabled={busy} onClick={()=>{setDialog(null);setOrderAction(null);}}>Keep current order</button><button disabled={busy} onClick={confirmAction}>Confirm action</button></section></WorkspaceModal>}
    {dialog==='method'&&<WorkspaceModal returnFocusRef={returnFocus} label="Create Trading Method" onClose={()=>{if(!busy)setDialog(null);}}><form className="alpha-dialog" onSubmit={createMethod}><h2>Create Trading Method</h2><label>Name<input name="name" required maxLength={128}/></label><label>Type<select name="kind" value={kind} onChange={e=>setKind(e.target.value)}><option value="FREE_STYLE">Free Style</option><option value="PROTOCOL">Protocol</option></select></label>{kind==='PROTOCOL'&&<><label>Locked risk %<input name="risk" defaultValue="1" inputMode="decimal" required/></label><label>Locked RR<input name="rr" defaultValue="2" inputMode="decimal" required/></label><label>Conditions (one per line)<textarea name="conditions" required maxLength={4096}/></label><label>Checklist enforcement<select name="checklist"><option>ON</option><option>OFF</option></select></label></>}<p>Changing rules later requires a new Method.</p>{notice&&<p role="alert">{noticeText(notice)}</p>}<button type="button" disabled={busy} onClick={()=>setDialog(null)}>Cancel</button><button disabled={busy}>Save Method</button></form></WorkspaceModal>}
    {dialog==='session'&&<WorkspaceModal returnFocusRef={returnFocus} label="Create Session" onClose={()=>{if(!busy)setDialog(null);}}><form className="alpha-dialog" onSubmit={createSession}><h2>Create Session</h2><label>Name<input name="name" required maxLength={128}/></label><label>Method<select name="method">{catalog.methods.map(m=><option key={m.id} value={m.id}>{m.name} · {m.kind}</option>)}</select></label><label>Starting balance (USD)<input name="balance" defaultValue="10000" inputMode="decimal" required/></label><p>XAUUSD/USD · synthetic feed · January 2020 fixture. The Session inherits its Method type and immutable rules.</p>{notice&&<p role="alert">{noticeText(notice)}</p>}<button type="button" disabled={busy} onClick={()=>setDialog(null)}>Cancel</button><button disabled={busy}>Save Session</button></form></WorkspaceModal>}
    {dialog==='review'&&review&&<WorkspaceModal returnFocusRef={returnFocus} label="Confirm reviewed order" onClose={()=>{if(!busy){setDialog(null);setReview(null);}}}><section className="alpha-dialog"><h2>Confirm reviewed order</h2><p>{view.method.name} · {review.review.command.payload.side} {review.review.command.payload.orderType}</p><dl>{['entry','sl','tp','quantity','riskPercent'].map(k=><div key={k}><dt>{({entry:'Entry',sl:'Stop Loss',tp:'Take Profit',quantity:'Lots',riskPercent:'Risk %'})[k]}</dt><dd>{review.review.command.payload[k]??'None'}</dd></div>)}</dl><p>Risk basis ${review.review.riskBasis}. Exact values checked by the server; fill uses the next eligible observed Bid/Ask.</p>{review.review.command.payload.observations.map(o=><p key={o.conditionId}>{view.method.conditions.find(c=>c.id===o.conditionId)?.label}: {o.outcome}</p>)}{notice&&<p role="alert">{noticeText(notice)}</p>}<button disabled={busy} onClick={()=>{setReview(null);setDialog(null);setOrderAction(null);}}>Cancel confirmation</button><button disabled={busy} onClick={confirm}>Confirm order</button></section></WorkspaceModal>}
  </main>;
}
