import {useMemo,useState} from 'react';
import {sourceContext} from './client.js';

// Testing hub shown when no Session is open. Reads only the existing catalog
// (Session metadata and strategies); it never fetches per-Session financial state,
// so opening the hub adds no replay work. Balances shown are starting balances.
const money=value=>{const [whole,fraction]=String(value).split('.');return '$'+whole.replace(/\B(?=(\d{3})+(?!\d))/g,',')+(fraction?'.'+fraction:'');};
const kindLabel=kind=>kind==='PROTOCOL'?'Protocol':'Free Style';

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
  const source=sourceContext()==='historical'?'Exness XAUUSD':'Synthetic fixture';
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
          <div><dt>Start month</dt><dd>{session.startPeriod}</dd></div>
          <div><dt>Strategy</dt><dd>{method?.name||'Unavailable'}</dd></div>
        </dl>
        <footer><span>{source}</span><button className="alpha-primary-action" disabled={busy} onClick={()=>onOpen(session.id)} aria-label={`Open ${session.name}`}>Open</button></footer>
      </article></li>;})}</ul>:<p className="alpha-hub-none">No Session matches this search.</p>)}
    {hasMethods&&<section className="alpha-hub-strategies" aria-labelledby="alpha-hub-strategies"><h2 id="alpha-hub-strategies">Strategies</h2><ul>{catalog.methods.map(m=><li key={m.id}><strong>{m.name}</strong><span>{kindLabel(m.kind)}{m.kind==='PROTOCOL'&&m.riskPercent?` · risk ${m.riskPercent}%`:''}{m.kind==='PROTOCOL'&&m.rr?` · R:R ${m.rr}`:''}</span><span>{catalog.sessions.filter(s=>s.methodId===m.id).length} Sessions</span></li>)}</ul></section>}
  </section>;
}
