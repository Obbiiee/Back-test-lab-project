import {useEffect,useMemo,useRef,useState} from 'react';
import {api,sessionPath,sourceContext} from './client.js';

// Hub cards request committed read-only summaries only near the viewport. The
// bounded queue avoids a fan-out across every saved Session and never advances replay.
const money=(value,currency='USD')=>{const [whole,fraction]=String(value).split('.');return (currency==='USD'?'$':`${currency} `)+whole.replace(/\B(?=(\d{3})+(?!\d))/g,',')+(fraction?'.'+fraction:'');};
const kindLabel=kind=>kind==='PROTOCOL'?'Protocol':'Free Style';
const exactDecimal=value=>typeof value==='string'&&/^-?\d+(?:\.\d+)?$/.test(value);
const SUMMARY_ARTIFACTS=new Set(['BTL-SESSION-SUMMARY-1','BTL-OBSERVED-SESSION-SUMMARY-1']);
const SUMMARY_LIMIT=2;
let activeSummaryReads=0;
const summaryQueue=[];

function drainSummaryQueue(){
  while(activeSummaryReads<SUMMARY_LIMIT&&summaryQueue.length){
    const task=summaryQueue.shift();
    if(task.cancelled||task.signal?.aborted)continue;
    activeSummaryReads++;
    api(sessionPath(task.sessionId)+'/summary',undefined,{signal:task.signal})
      .then(task.resolve,task.reject)
      .finally(()=>{task.signal?.removeEventListener('abort',task.abort);activeSummaryReads--;drainSummaryQueue();});
  }
}

function queuedSummary(sessionId,signal){
  return new Promise((resolve,reject)=>{
    const task={sessionId,signal,resolve,reject,cancelled:false};
    task.abort=()=>{
      task.cancelled=true;
      const queued=summaryQueue.indexOf(task);if(queued>=0)summaryQueue.splice(queued,1);
      signal?.removeEventListener('abort',task.abort);
      reject(signal.reason??Error('Request cancelled'));
    };
    if(signal?.aborted){task.abort();return;}
    signal?.addEventListener('abort',task.abort,{once:true});
    summaryQueue.push(task);drainSummaryQueue();
  });
}

function replayTime(value){
  if(value===null||value===undefined)return 'Not started';
  try{
    const milliseconds=Number(BigInt(value)/1000000n);
    if(!Number.isSafeInteger(milliseconds))return 'Unavailable';
    return new Intl.DateTimeFormat('en-US',{timeZone:'UTC',dateStyle:'medium',timeStyle:'short'}).format(milliseconds)+' UTC';
  }catch{return 'Unavailable';}
}

function signedMoney(value,currency){
  const negative=String(value).startsWith('-'),absolute=negative?String(value).slice(1):String(value);
  return `${negative?'−':'+'}${money(absolute,currency)}`;
}

function SessionSummary({session}){
  const target=useRef(null);
  const [visible,setVisible]=useState(()=>typeof IntersectionObserver==='undefined'),[attempt,setAttempt]=useState(0),[state,setState]=useState({status:'WAITING'});
  useEffect(()=>{
    if(!target.current||visible||typeof IntersectionObserver==='undefined')return;
    const observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting)){setVisible(true);observer.disconnect();}},{rootMargin:'240px'});
    observer.observe(target.current);return()=>observer.disconnect();
  },[visible]);
  useEffect(()=>{
    if(!visible)return;
    const controller=new AbortController();
    queuedSummary(session.id,controller.signal).then(summary=>{
      if(!SUMMARY_ARTIFACTS.has(summary?.artifact)||summary.sessionId!==session.id||!exactDecimal(summary.balance)||!exactDecimal(summary.netCashChange)||typeof summary.accountCurrency!=='string'||!/^[A-Z]{3}$/.test(summary.accountCurrency)||!Number.isSafeInteger(summary.completedTrades)||summary.completedTrades<0||typeof summary.unresolved!=='boolean'||typeof summary.ended!=='boolean'||(summary.throughNs!==null&&typeof summary.throughNs!=='string'))throw Error('Unsupported Session summary');
      setState({status:'READY',summary});
    }).catch(error=>{if(!controller.signal.aborted)setState({status:'ERROR',message:error.message});});
    return()=>controller.abort();
  },[session.id,visible,attempt]);
  const summary=state.summary;
  const status=visible&&state.status==='WAITING'?'LOADING':state.status;
  return <div className="alpha-hub-summary" ref={target} aria-label={`Saved results for ${session.name}`} aria-live="polite">
    {status==='WAITING'&&<p>Session results load when this card is nearby.</p>}
    {status==='LOADING'&&<p>Loading saved results…</p>}
    {status==='ERROR'&&<div><p role="status">Saved results are temporarily unavailable.</p><button type="button" onClick={()=>{setState({status:'LOADING'});setAttempt(value=>value+1);}}>Retry results</button></div>}
    {summary&&<>
      <dl>
        <div><dt>Current balance</dt><dd>{money(summary.balance,summary.accountCurrency)}</dd></div>
        <div><dt>Net cash change</dt><dd>{signedMoney(summary.netCashChange,summary.accountCurrency)}</dd></div>
        <div><dt>Closed trades</dt><dd>{summary.completedTrades}</dd></div>
        <div><dt>Replay position</dt><dd>{replayTime(summary.throughNs)}</dd></div>
      </dl>
      <p className="alpha-hub-summary-state">{summary.ended?'Session ended':summary.unresolved?'Evidence unresolved':'Saved replay state'} · committed values</p>
    </>}
  </div>;
}

export default function AlphaSessions({catalog,busy,onOpen,onCreate,onSource}){
  const [query,setQuery]=useState(''),[strategy,setStrategy]=useState('');
  const methods=useMemo(()=>new Map(catalog.methods.map(m=>[m.id,m])),[catalog.methods]);
  const visible=useMemo(()=>{
    const text=query.trim().toLowerCase();
    return catalog.sessions
      .filter(s=>(!strategy||s.methodId===strategy)&&(!text||s.name.toLowerCase().includes(text)||(methods.get(s.methodId)?.name||'').toLowerCase().includes(text)))
      .sort((a,b)=>a.name.localeCompare(b.name));
  },[catalog.sessions,query,strategy,methods]);
  const hasMethods=catalog.methods.length>0,hasSessions=catalog.sessions.length>0;
  const sourceFor=session=>session.model==='CONDITIONAL_OBSERVED_TICK_SIMULATION'
    ?(catalog.datasets?.find(dataset=>dataset.key===session.datasetKey)?.label??'Observed XAUUSD ticks')
    :sourceContext()==='historical'?'Exness XAUUSD':'Synthetic fixture';
  const steps=[['Create a strategy','Write the rules you want to test.',hasMethods],['Create a Session','Pick a start month and starting balance.',hasSessions],['Replay and trade','Reveal history one step at a time and place orders.',false],['Review the evidence','Check the journal and Analysis for each Session.',false]];
  return <section className="alpha-hub" aria-labelledby="alpha-hub-title">
    <div className="alpha-hub-head">
      <div><h1 id="alpha-hub-title">Your next practice starts here.</h1><p>Each Session keeps its own replay position, orders and evidence. Open one to continue where you left off.</p></div>
      <div className="alpha-hub-actions">
        <button className="alpha-primary-action" disabled={busy} onClick={event=>onCreate(hasMethods?'session':'method',event)}>{hasMethods?'New Session':'Create a strategy'}</button>
        {hasMethods&&<button disabled={busy} onClick={event=>onCreate('method',event)}>New strategy</button>}
        <button onClick={onSource}>Data source</button>
      </div>
    </div>
    {!hasSessions&&<ol className="alpha-hub-steps" aria-label="Getting started">{steps.map(([title,text,done],index)=><li key={title} className={done?'done':''}><span aria-hidden="true">{done?'✓':index+1}</span><div><strong>{title}</strong><p>{text}</p></div>{done&&<span className="alpha-visually-hidden">Done</span>}</li>)}</ol>}
    {hasSessions&&<div className="alpha-hub-filters" role="search">
      <label>Search<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Session or strategy name"/></label>
      <label>Strategy<select value={strategy} onChange={e=>setStrategy(e.target.value)}><option value="">All strategies</option>{catalog.methods.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
      <span aria-live="polite">{visible.length} of {catalog.sessions.length} Sessions</span>
    </div>}
    {hasSessions&&(visible.length?<ul className="alpha-hub-grid" aria-label="Saved Sessions">{visible.map(session=>{const method=methods.get(session.methodId);return <li key={session.id}>
      <article className="alpha-hub-card">
        <header><h2>{session.name}</h2><span className="alpha-hub-tag">{kindLabel(method?.kind)}</span></header>
        <dl>
          <div><dt>Instrument</dt><dd>XAUUSD</dd></div>
          <div><dt>Starting balance</dt><dd>{money(session.initialBalance)}</dd></div>
          <div><dt>Start month</dt><dd>{session.period??session.startPeriod}</dd></div>
          <div><dt>Strategy</dt><dd>{method?.name||'Unavailable'}</dd></div>
        </dl>
        <SessionSummary session={session}/>
        <footer><span>{sourceFor(session)}</span><button className="alpha-primary-action" disabled={busy} onClick={()=>onOpen(session.id)} aria-label={`Open ${session.name}`}>Open</button></footer>
      </article></li>;})}</ul>:<p className="alpha-hub-none">No Session matches this search.</p>)}
    {hasMethods&&<section className="alpha-hub-strategies" aria-labelledby="alpha-hub-strategies"><h2 id="alpha-hub-strategies">Strategies</h2><ul>{catalog.methods.map(m=><li key={m.id}><strong>{m.name}</strong><span>{kindLabel(m.kind)}{m.kind==='PROTOCOL'&&m.riskPercent?` · risk ${m.riskPercent}%`:''}{m.kind==='PROTOCOL'&&m.rr?` · R:R ${m.rr}`:''}</span><span>{catalog.sessions.filter(s=>s.methodId===m.id).length} Sessions</span></li>)}</ul></section>}
  </section>;
}
