import {useEffect,useMemo,useState} from 'react';
import Icon from '../workspace/WorkspaceIcon.jsx';
import {api,sessionPath,sourceContext} from './client.js';
import {money,kindLabel,utc,lastSession} from './productData.js';
import {linkTo} from './productRoute.js';
import {StatePanel,PageHead} from './AlphaShell.jsx';
import {MethodPicker} from './AlphaSelect.jsx';

// CP2 pages: Sessions list (U07 entry), Session overview (U08) and Data Catalog
// (U06). Everything shown comes from the catalog or GET /sessions/{id}; what the
// service does not publish (counts per Session, other instruments, trash) is
// stated as unavailable instead of being estimated.

const PAGE_SIZE=24;
const monthName=period=>{const [year,month]=String(period).split('-').map(Number);return year&&month?new Date(Date.UTC(year,month-1,1)).toLocaleString('en',{month:'long',year:'numeric',timeZone:'UTC'}):String(period);};

// Playful Sessions hub (canvas 08): a hero that continues the last replay, then one
// card per Session. Only values the catalog publishes are shown; progress, balance
// now and results are not on the catalog, so the card links to Analytics instead.
function SessionCard({session,catalog,onOpen,last}){
  const method=catalog.methods.find(m=>m.id===session.methodId);
  const instrument=catalog.profile.instrumentId;
  return <li><article className={`rk-session-card${last?' is-last':''}`}>
    <div className="rk-session-head"><span className="rk-avatar" aria-hidden="true">{instrument.slice(0,2)}</span><div><h2><a {...linkTo({screen:'session',of:session.id})}>{session.name}</a></h2><p>{instrument} · {method?.name||'Method unavailable'}</p></div></div>
    <div className="rk-session-facts"><span><small>Start</small><b className="rk-num">{monthName(session.startPeriod)}</b></span><span><small>Starting balance</small><b className="rk-num">{money(session.initialBalance)}</b></span></div>
    <div className="rk-session-tags">{method&&<span className={`rk-tag rk-tag-${method.kind==='PROTOCOL'?'protocol':'free'}`}>{kindLabel(method.kind)}</span>}{last&&<span className="rk-tag rk-tag-last">Last opened</span>}</div>
    <div className="rk-session-actions"><button type="button" className="rk-btn rk-btn-primary" onClick={()=>onOpen(session.id)} aria-label={`Open replay for ${session.name}`}>{last?'Continue replay':'Open replay'}</button><a className="rk-btn rk-btn-quiet" {...linkTo({screen:'analytics',of:session.id})} aria-label={`Analytics for ${session.name}`}>Analytics</a></div>
  </article></li>;
}

function SessionsHero({catalog,onOpen}){
  const last=catalog.sessions.find(s=>s.id===lastSession());
  return <section className="rk-hub-hero" aria-label="Continue">
    <div><h2>{last?'Ready for the next round?':'Ready for your first round?'}</h2>
      <p>{last?<>Your last replay was <b>{last.name}</b>. Pick up where you left it.</>:'Press New Session, pick a Method and a month, then Play. Your orders and notes are saved per Session.'}</p>
      {last&&<div className="rk-hub-actions"><button type="button" className="rk-btn rk-btn-light" onClick={()=>onOpen(last.id)}>Continue replay</button></div>}</div>
    <dl className="rk-hub-stats"><div><dt>Sessions</dt><dd className="rk-num">{catalog.sessions.length}</dd></div><div><dt>Methods</dt><dd className="rk-num">{catalog.methods.length}</dd></div></dl>
  </section>;
}

export function SessionsPage({catalog,onOpen}){
  const [shown,setShown]=useState(PAGE_SIZE);
  const [query,setQuery]=useState('');
  const [methodId,setMethodId]=useState(null);
  const [sort,setSort]=useState('newest');
  const rows=useMemo(()=>{
    const q=query.trim().toLowerCase();
    const methodName=id=>catalog.methods.find(m=>m.id===id)?.name||'';
    const list=catalog.sessions.filter(s=>(!methodId||s.methodId===methodId)&&(!q||s.name.toLowerCase().includes(q)||methodName(s.methodId).toLowerCase().includes(q)));
    const ordered=sort==='name'?list.slice().sort((a,b)=>a.name.localeCompare(b.name)):list.slice().reverse();
    // The Session you opened last always comes first, so Continue is never below the fold.
    const last=lastSession();
    return sort==='newest'&&last&&ordered.some(item=>item.id===last)?[ordered.find(item=>item.id===last),...ordered.filter(item=>item.id!==last)]:ordered;
  },[catalog,query,methodId,sort]);
  const newSession=<a className="rk-btn rk-btn-primary" {...linkTo({screen:'session-new',method:methodId||undefined})}><Icon name="plus" size={18}/><span>New Session</span></a>;
  if(!catalog.sessions.length)return <><PageHead eyebrow="Research" title="Sessions" lead="A Session replays one Method on one instrument from a start month, with its own balance and journal." actions={newSession}/>
    <StatePanel kind="empty" title="No Sessions yet" action={catalog.methods.length?newSession:<a className="rk-btn rk-btn-primary" {...linkTo({screen:'method-new'})}>Create your first Method</a>}><p>{catalog.methods.length?'Pick a Method and press Play. Your replay time, orders and journal are saved per Session.':'Write a Method first; every Session replays one Method.'}</p></StatePanel></>;
  return <><PageHead eyebrow="Research" title="Sessions" lead="Open one to continue where you left off." actions={newSession}/>
    <SessionsHero catalog={catalog} onOpen={onOpen}/>
    <div className="rk-toolbar">
      <label className="rk-search"><span className="alpha-sr-only">Search Sessions</span><Icon name="search" size={18}/><input type="search" value={query} onChange={event=>{setQuery(event.target.value);setShown(PAGE_SIZE);}} placeholder="Search Sessions or Methods"/></label>
      <div className="rk-toolbar-combo"><MethodPicker methods={catalog.methods} value={methodId} onChange={setMethodId} label="Method" placeholder="All Methods" clearable/></div>
      <label className="rk-select">Sort<select value={sort} onChange={event=>setSort(event.target.value)}><option value="newest">Newest first</option><option value="name">Name A–Z</option></select></label>
      <span className="rk-count" role="status">{rows.length} of {catalog.sessions.length}</span>
    </div>
    {rows.length?<><ul className="rk-session-grid" aria-label="Sessions">{rows.slice(0,shown).map(row=><SessionCard key={row.id} session={row} catalog={catalog} onOpen={onOpen} last={row.id===lastSession()}/>)}</ul>
      {rows.length>shown&&<div className="rk-more"><button type="button" className="rk-btn" onClick={()=>setShown(count=>count+PAGE_SIZE)}>Show {Math.min(PAGE_SIZE,rows.length-shown)} more of {rows.length-shown} remaining</button></div>}</>
      :<StatePanel kind="filtered" title="No Session matches" action={<button type="button" className="rk-btn" onClick={()=>{setQuery('');setMethodId(null);}}>Clear filters</button>}><p>Try another name or show all Methods.</p></StatePanel>}
  </>;
}

export function SessionOverview({catalog,route,onOpen}){
  const sessionId=route.analyticsSession;
  const session=catalog.sessions.find(s=>s.id===sessionId)||null;
  const [attempt,setAttempt]=useState(0);
  const [result,setResult]=useState({key:null});
  const key=`${sessionId}:${attempt}`;
  useEffect(()=>{
    if(!session)return undefined;
    let live=true;
    api(sessionPath(session.id)).then(value=>{if(live)setResult({key,status:'ready',value});},error=>{if(live)setResult({key,status:'error',message:error.message});});
    return()=>{live=false;};
  },[session,key]);
  if(!session)return <><PageHead back={{label:'Sessions',to:{screen:'sessions'}}} title="Session unavailable"/>
    <StatePanel kind="unavailable" title="This Session is not in this workspace" action={<a className="rk-btn" {...linkTo({screen:'sessions'})}>All Sessions</a>}><p>It may belong to another workspace or the link is incomplete.</p></StatePanel></>;
  const method=catalog.methods.find(m=>m.id===session.methodId);
  const state=result.key===key?result:{status:'loading'};
  const saved=state.status==='ready'?state.value.state:null;
  return <><PageHead back={method?{label:method.name,to:{screen:'method',method:method.id}}:{label:'Sessions',to:{screen:'sessions'}}} eyebrow="Session" title={session.name}
      actions={<><button type="button" className="rk-btn rk-btn-primary" onClick={()=>onOpen(session.id)}><Icon name="candles" size={18}/><span>Resume replay</span></button><a className="rk-btn" {...linkTo({screen:'analytics',method:session.methodId,of:session.id})}>Analytics</a></>}/>
    <div className="rk-grid-2">
      <section className="rk-card" aria-labelledby="rk-so-saved"><h2 id="rk-so-saved">Saved state</h2>
        {state.status==='loading'?<p className="rk-note" role="status"><span className="rk-spinner" aria-hidden="true"/> Loading the saved state…</p>
          :state.status==='error'?<div role="alert"><p className="rk-note">The saved state could not load. {state.message}</p><button type="button" className="rk-btn" onClick={()=>setAttempt(n=>n+1)}>Retry</button></div>
          :<dl className="rk-facts">
            <div><dt>Replay time</dt><dd className="rk-num">{utc(saved.throughNs)}</dd></div>
            <div><dt>Committed balance</dt><dd className="rk-num">{money(saved.balance)}</dd></div>
            <div><dt>Saved revision</dt><dd className="rk-num">{saved.revision}</dd></div>
            <div><dt>Evidence</dt><dd>{saved.unresolved?'Unresolved: waiting for later quotes':saved.ended?'Replay reached the end of data':'Ready'}</dd></div>
          </dl>}
      </section>
      <section className="rk-card" aria-labelledby="rk-so-setup"><h2 id="rk-so-setup">Setup</h2>
        <dl className="rk-facts">
          <div><dt>Method</dt><dd>{method?<a {...linkTo({screen:'method',method:method.id})}>{method.name}</a>:'Unavailable'} · {kindLabel(method?.kind)}</dd></div>
          <div><dt>Instrument</dt><dd className="rk-num">{catalog.profile.instrumentId}</dd></div>
          <div><dt>Start month</dt><dd className="rk-num">{session.startPeriod}</dd></div>
          <div><dt>Starting balance</dt><dd className="rk-num">{money(session.initialBalance)}</dd></div>
          <div><dt>Source</dt><dd>{sourceContext()==='historical'?'Historical quotes':'Synthetic test feed'} · {catalog.label}</dd></div>
        </dl>
      </section>
    </div>
    <details className="rk-card rk-disclosure"><summary>What is not shown here yet</summary>
      <p className="rk-note">Order counts, Trash and Restore need server routes that are not published yet. The trading terminal shows this Session’s positions, pending orders, journal and analysis.</p></details>
  </>;
}

export function CatalogPage({catalog,onSource}){
  const [query,setQuery]=useState('');
  const p=catalog.profile;
  const historical=sourceContext()==='historical';
  const instruments=[{id:p.instrumentId,feed:p.feedInstrumentId,provider:p.providerId}];
  const shown=instruments.filter(item=>!query.trim()||[item.id,item.feed,item.provider].some(text=>text.toLowerCase().includes(query.trim().toLowerCase())));
  return <><PageHead eyebrow="Data" title="Data Catalog" lead="Instruments this workspace can replay, as confirmed by the service."/>
    <div className="rk-toolbar">
      <label className="rk-search"><span className="alpha-sr-only">Search instruments</span><Icon name="search" size={18}/><input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search instruments"/></label>
      <span className="rk-count" role="status">{shown.length} of {instruments.length} confirmed</span>
    </div>
    {shown.length?<ul className="rk-catalog" aria-label="Confirmed instruments">{shown.map(item=><li key={item.id} className="rk-card rk-catalog-item">
      <div className="rk-catalog-main"><span className="rk-avatar" aria-hidden="true">{item.id.slice(0,2)}</span>
        <div><h2>{item.id}</h2><p className="rk-note">{historical?'Historical Bid/Ask quotes':'Synthetic test feed'} · earliest start {catalog.startPeriod}</p></div>
        <span className="rk-tag rk-tag-free">{historical?'Available':'Test only'}</span></div>
      <details className="rk-disclosure"><summary>Contract and source details</summary>
        <dl className="rk-facts"><div><dt>Provider / feed</dt><dd>{p.providerId} / {p.feedId}</dd></div><div><dt>Quote currency</dt><dd>{p.quoteCurrency}</dd></div><div><dt>Tick size</dt><dd className="rk-num">{p.tickSize}</dd></div><div><dt>Lots</dt><dd className="rk-num">{p.minLot}–{p.maxLot} step {p.lotStep}</dd></div><div><dt>Contract size</dt><dd className="rk-num">{p.contractSize}</dd></div><div><dt>Commission</dt><dd>{p.commissionModel}</dd></div></dl>
        <button type="button" className="rk-btn" onClick={onSource}>Source limitations</button></details>
    </li>)}</ul>:<StatePanel kind="filtered" title="No confirmed instrument matches" action={<button type="button" className="rk-btn" onClick={()=>setQuery('')}>Clear search</button>}><p>Only instruments the service confirms are listed.</p></StatePanel>}
    <p className="rk-main-note">Other instruments are not listed until the service publishes their availability. Nothing here is marked available without server confirmation.</p>
  </>;
}
