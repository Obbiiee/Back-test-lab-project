import {useEffect,useRef,useState} from 'react';
import {api,id} from './client.js';
import {accountStorageKey} from './accountClient.js';
import {linkTo,navigate} from './productRoute.js';
import './miWorkspace.css';

const emptyPlan={side:'LONG',orderType:'MARKET',entry:'',quantity:'0.1',sl:'',tp:'',riskPercent:'1'};

function BidChart({rows,symbol}){
  const prices=rows.map(row=>Number(row.bid));
  if(!prices.length)return <p>Advance replay to reveal quotes.</p>;
  const low=Math.min(...prices),high=Math.max(...prices);
  const points=prices.map((value,index)=>[prices.length===1?240:20+index*440/(prices.length-1),
    low===high?72:130-(value-low)*110/(high-low)].join(',')).join(' ');
  return <figure><svg viewBox="0 0 480 150" role="img" aria-label={symbol+' revealed bid chart'}>
    <path d="M20 20V130H460" fill="none" stroke="currentColor" opacity=".35"/>
    {prices.length===1?<circle cx="240" cy="72" r="4" fill="currentColor"/>:<polyline points={points} fill="none" stroke="currentColor" strokeWidth="2"/>}
  </svg><figcaption>{symbol} bid · {rows.at(-1).bid}</figcaption></figure>;
}

function pairs(state){
  return state.profiles.map(profile=>profile.symbol);
}

export default function MIWorkspace({methods,sessionId}){
  const [catalog,setCatalog]=useState(null),[session,setSession]=useState(null);
  const [symbols,setSymbols]=useState([]),[methodIds,setMethodIds]=useState([]),[balance,setBalance]=useState('10000');
  const [pair,setPair]=useState(''),[plan,setPlan]=useState(emptyPlan),[review,setReview]=useState(null);
  const [target,setTarget]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const [journal,setJournal]=useState(null),[analytics,setAnalytics]=useState(null);
  const [journalPair,setJournalPair]=useState(''),[journalMethod,setJournalMethod]=useState('');
  const pendingKey=accountStorageKey('mi-pending:'+sessionId);
  const [resume,setResume]=useState(''),[pending,setPending]=useState(()=>{
    if(!sessionId)return null;
    try{
      const value=JSON.parse(sessionStorage.getItem(pendingKey));
      return value?.command?.sessionId===sessionId?value:null;
    }catch{return null;}
  });
  const [conditions,setConditions]=useState([]);
  const flight=useRef(false),createId=useRef(null);
  const state=session?.state?.sessionId===sessionId?session.state:null;
  const selected=state&&(Object.hasOwn(state.groups,pair)?pair:state.profiles[0].symbol);
  const quote=state?.groups[selected]?.events.at(-1);
  const path=sessionId?'/mi/sessions/'+encodeURIComponent(sessionId):null;
  const policy=state?.methods[state.activeMethodId];
  useEffect(()=>{
    const abort=new AbortController();
    api('/mi/catalog',undefined,{signal:abort.signal}).then(setCatalog).catch(error=>{if(!abort.signal.aborted)setNotice(error.message);});
    return ()=>abort.abort();
  },[]);
  useEffect(()=>{
    if(!path)return;
    const abort=new AbortController();
    api(path+(pair?'?instrument='+encodeURIComponent(pair):''),undefined,{signal:abort.signal})
      .then(value=>{setSession(value);if(!pair)setPair(value.state.profiles[0].symbol);})
      .catch(error=>{if(!abort.signal.aborted)setNotice(error.message);});
    return ()=>abort.abort();
  },[path,pair]);
  const run=async work=>{
    if(flight.current)return;
    flight.current=true;setBusy(true);setNotice('');
    try{await work();}catch(error){setNotice(error.message);}finally{flight.current=false;setBusy(false);}
  };
  const reload=async()=>setSession(await api(path+'?instrument='+encodeURIComponent(selected)));
  const send=async request=>{
    try{sessionStorage.setItem(pendingKey,JSON.stringify(request));}catch{/* Keep the current tab usable. */}
    try{await api(path+'/commands',request);}
    catch(error){
      if(error.code==='UNKNOWN')setPending(request);
      else{
        try{sessionStorage.removeItem(pendingKey);}catch{/* Storage may be disabled. */}
        setPending(null);
      }
      throw error;
    }
    try{sessionStorage.removeItem(pendingKey);}catch{/* Storage may be disabled. */}
    setPending(null);setReview(null);setJournal(null);setAnalytics(null);
    await reload();
  };
  const reconcile=()=>run(async()=>{
    const status=await api(path+'/command-status',pending);
    if(status.status==='UNKNOWN'){await send(pending);return;}
    try{sessionStorage.removeItem(pendingKey);}catch{/* Storage may be disabled. */}
    setPending(null);setReview(null);setJournal(null);setAnalytics(null);
    await reload();
    if(status.status==='NOT_COMMITTED')setNotice('The command was not committed. Review the current Session before retrying.');
  });
  const dispatch=(kind,payload,jump=false)=>run(()=>send({
    schemaVersion:1,artifact:'BTL-MI-QUEUE-REQUEST-1',jump,
    command:{schemaVersion:1,artifact:'BTL-TICK-EXECUTION-COMMAND-MI-1',sessionId,commandId:id('mi'),
      expectedRevision:state.revision,kind,payload}
  }));
  const toggle=(list,value)=>list.includes(value)?list.filter(item=>item!==value):[...list,value];

  if(!catalog)return <section className="mi-workspace"><h1>Multi-instrument QA</h1><p role="status">{notice||'Loading…'}</p><a {...linkTo({screen:'sessions'})}>All Sessions</a></section>;
  if(!sessionId)return <section className="mi-workspace"><a {...linkTo({screen:'sessions'})}>All Sessions</a><h1>Multi-instrument QA</h1><p>{catalog.label} · {catalog.startPeriod}</p>
    <form onSubmit={event=>{event.preventDefault();run(async()=>{
      createId.current??=id('mi-session');
      const value=await api('/mi/sessions',{schemaVersion:1,artifact:'BTL-MI-SESSION-CREATE-1',id:createId.current,
        instrumentIds:symbols,methodIds,activeMethodId:methodIds[0],initialBalance:balance});
      navigate({screen:'mi',session:value.state.sessionId});
    });}}>
      <fieldset><legend>Instruments</legend>{catalog.symbols.map(symbol=><label key={symbol}><input type="checkbox" checked={symbols.includes(symbol)} onChange={()=>setSymbols(toggle(symbols,symbol))}/>{symbol}</label>)}</fieldset>
      <fieldset><legend>Methods</legend>{methods.map(method=><label key={method.id}><input type="checkbox" checked={methodIds.includes(method.id)} onChange={()=>setMethodIds(toggle(methodIds,method.id))}/>{method.name}</label>)}</fieldset>
      {!methods.length&&<a {...linkTo({screen:'method-new'})}>Create a Method</a>}
      <label>Initial balance<input required value={balance} onChange={event=>setBalance(event.target.value)}/></label>
      <button disabled={busy||symbols.length<2||!methodIds.length}>Create MI Session</button>
    </form>
    <form onSubmit={event=>{event.preventDefault();navigate({screen:'mi',session:resume.trim()});}}><label>Session ID<input required value={resume} onChange={event=>setResume(event.target.value)}/></label><button>Resume MI Session</button></form>
    {notice&&<p role="alert">{notice}</p>}</section>;
  if(!state)return <section className="mi-workspace"><a {...linkTo({screen:'mi'})}>Multi-instrument Sessions</a><p role="status">{notice||'Opening Session…'}</p></section>;
  const blocked=busy||Boolean(pending);
  const change=(key,value)=>{setReview(null);setPlan({...plan,[key]:value});};
  const field=(key,label)=><label>{label}<input required value={plan[key]} onChange={event=>change(key,event.target.value)}/></label>;
  const visible=journal?.orders.filter(row=>(!journalPair||row.order.symbol===journalPair)&&(!journalMethod||row.order.methodId===journalMethod));
  return <section className="mi-workspace">
    <a {...linkTo({screen:'mi'})}>Multi-instrument Sessions</a> <a {...linkTo({screen:'account'})}>Account</a>
    <h1>Multi-instrument workspace</h1><p>{catalog.label} · <code>{sessionId}</code></p>
    {notice&&<p role="alert">{notice}</p>}
    {pending&&<button disabled={busy} onClick={reconcile}>Reconcile pending command</button>}
    <div className="mi-controls">
      <label>Active pair<select value={selected} disabled={blocked} onChange={event=>{setPair(event.target.value);setReview(null);}}>
        {pairs(state).map(symbol=><option key={symbol}>{symbol}</option>)}
      </select></label>
      <label>Active Method<select value={state.activeMethodId} disabled={blocked} onChange={event=>{setConditions([]);dispatch('SET_METHOD',{methodId:event.target.value});}}>
        {Object.keys(state.methods).map(key=><option key={key} value={key}>{methods.find(method=>method.id===key)?.name||key}</option>)}
      </select></label>
      <button disabled={busy} onClick={()=>run(reload)}>Reload Session</button>
    </div>
    <p>Balance {state.balance} USD · Equity {session.equity.complete?session.equity.equityUsd+' USD':'Unavailable'} · Revision {state.revision}</p>
    <BidChart rows={session.activeInstrument===selected?(session.chart||[]):[]} symbol={selected}/>
    <div className="mi-controls"><label>Replay target (ns UTC)<input inputMode="numeric" value={target} onChange={event=>setTarget(event.target.value)}/></label>
      <button disabled={blocked||!target} onClick={()=>dispatch('ADVANCE',{targetNs:target})}>Replay</button>
      <button disabled={blocked||!target} onClick={()=>dispatch('ADVANCE',{targetNs:target},true)}>Jump</button>
    </div>
    <h2>Order ticket</h2>
    <form onSubmit={event=>{event.preventDefault();setReview({...plan,symbol:selected,
      workflow:plan.orderType==='MARKET'?'QUICK':'PLANNED',entry:plan.orderType==='MARKET'?(plan.side==='LONG'?quote.ask:quote.bid):plan.entry,
      sl:plan.sl||null,tp:plan.tp||null,riskPercent:policy.riskPercent??plan.riskPercent,
      observations:policy.kind==='PROTOCOL'?policy.conditions.filter(key=>conditions.includes(key)).map(conditionId=>({conditionId,outcome:'PASS'})):[]});}}>
      <div className="mi-controls">
        <label>Side<select value={plan.side} onChange={event=>change('side',event.target.value)}><option>LONG</option><option>SHORT</option></select></label>
        <label>Order type<select value={plan.orderType} onChange={event=>change('orderType',event.target.value)}><option>MARKET</option><option>LIMIT</option><option>STOP</option></select></label>
        {field('quantity','Quantity')}
        {plan.orderType!=='MARKET'&&<>{field('entry','Entry')}{field('sl','Stop Loss')}{field('tp','Take Profit')}{field('riskPercent','Risk %')}</>}
      </div>
      {policy.kind==='PROTOCOL'&&<p>Protocol risk {policy.riskPercent}% · Target {policy.rr}R. The server checks exact size.</p>}
      {policy.checklistOn&&<fieldset><legend>Method checklist</legend>{policy.conditions.map(key=><label key={key}>
        <input type="checkbox" checked={conditions.includes(key)} onChange={()=>{setReview(null);setConditions(toggle(conditions,key));}}/>
        {methods.find(method=>method.id===policy.methodId)?.conditions.find(condition=>condition.id===key)?.label||key}
      </label>)}</fieldset>}
      <button disabled={!quote||blocked||(policy.kind==='PROTOCOL'&&plan.orderType==='MARKET')}>Review order</button>
    </form>
    {review&&<p>Review {review.symbol} {review.side} {review.orderType} · {review.quantity} lots at {review.entry}
      {' '}<button disabled={blocked} onClick={()=>dispatch('OPEN',review)}>Confirm order</button></p>}
    <h2>Positions and pending orders</h2>
    {Object.keys(state.orders).length===0?<p>No open or pending orders.</p>:<ul>{Object.entries(state.orders).map(([key,order])=><li key={key}>{order.symbol} · {order.status} · {order.remaining} lots {' '}
      <button disabled={blocked} onClick={()=>dispatch(order.status==='ACTIVE'?'CLOSE':'CANCEL',order.status==='ACTIVE'?{orderId:key,quantity:null}:{orderId:key})}>{order.status==='ACTIVE'?'Close':'Cancel'} {order.symbol}</button></li>)}</ul>}
    <button disabled={busy} onClick={()=>run(async()=>setJournal(await api(path+'/journal')))}>Journal</button>
    <button disabled={busy} onClick={()=>run(async()=>setAnalytics(await api(path+'/analytics')))}>Analytics</button>
    {journal&&<section><h2>Journal</h2><label>Pair filter<select value={journalPair} onChange={event=>setJournalPair(event.target.value)}><option value="">All</option>{pairs(state).map(symbol=><option key={symbol}>{symbol}</option>)}</select></label>
      <label>Method filter<select value={journalMethod} onChange={event=>setJournalMethod(event.target.value)}><option value="">All</option>{Object.keys(state.methods).map(key=><option key={key}>{key}</option>)}</select></label>
      {visible.length?<ul>{visible.map(row=><li key={row.orderId}>{row.order.symbol} · {row.order.methodId} · {row.order.status}</li>)}</ul>:<p>No records on this page.</p>}
      {journal.nextAfterSequence!==null&&<button disabled={busy} onClick={()=>run(async()=>setJournal(await api(path+'/journal?after='+journal.nextAfterSequence+'&revision='+journal.revision)))}>Next Journal page</button>}</section>}
    {analytics&&<section><h2>Analytics</h2><p>Closed trades {analytics.metrics.tradeCount} · Net {analytics.metrics.netCashChange} USD</p>
      <h3>By pair</h3><ul>{Object.entries(analytics.byPair).map(([key,value])=><li key={key}>{key} · {value.tradeCount} closed · {value.netCashChange} USD</li>)}</ul>
      <h3>By Method</h3><ul>{Object.entries(analytics.byMethod).map(([key,value])=><li key={key}>{key} · {value.tradeCount} closed · {value.netCashChange} USD</li>)}</ul></section>}
  </section>;
}
