import {useEffect,useMemo,useRef,useState} from 'react';
import Icon from '../workspace/WorkspaceIcon.jsx';
import {api,id,sessionPath,sourceContext} from './client.js';
import {money,kindLabel,utc,lastSession} from './productData.js';
import {linkTo,navigate,METHOD_TABS} from './productRoute.js';
import {StatePanel,PageHead} from './AlphaShell.jsx';
import Segmented from './AlphaSegmented.jsx';
import AlphaEquityChart from './AlphaEquityChart.jsx';
import {ratioLabel} from './annotations.js';

// Product pages (U03 My Methods, U04 Method create, U05 Method overview, U12/U13
// analytics layout). They read only the existing catalog and per-Session DTOs; any
// value the backend does not publish is shown as unavailable, never estimated.
function sourceLine(catalog){
  const p=catalog.profile;
  return `${p.instrumentId} · ${sourceContext()==='historical'?'historical quotes':'synthetic test feed'} · ${p.providerId}/${p.feedId}`;
}

function SessionRow({session,catalog,onOpen}){
  return <tr>
    <th scope="row"><a {...linkTo({screen:'session',of:session.id})}>{session.name}</a></th>
    <td>{catalog.profile.instrumentId}</td><td className="rk-num">{session.startPeriod}</td><td className="rk-num">{money(session.initialBalance)}</td>
    <td className="rk-row-actions"><button type="button" className="rk-btn rk-btn-small" onClick={()=>onOpen(session.id)} aria-label={`Open replay for ${session.name}`}>Open replay</button><a className="rk-btn rk-btn-small rk-btn-quiet" {...linkTo({screen:'analytics',of:session.id})} aria-label={`Analytics for ${session.name}`}>Analytics</a></td>
  </tr>;
}

export function SessionTable({sessions,catalog,onOpen,caption}){
  return <div className="rk-table-scroll" tabIndex={0} role="region" aria-label={`${caption}, scrolls sideways`}><table className="rk-table">
    <caption className="alpha-sr-only">{caption}</caption>
    <thead><tr><th scope="col">Session</th><th scope="col">Instrument</th><th scope="col">Start month</th><th scope="col">Starting balance</th><th scope="col"><span className="alpha-sr-only">Actions</span></th></tr></thead>
    <tbody>{sessions.map(s=><SessionRow key={s.id} session={s} catalog={catalog} onOpen={onOpen}/>)}</tbody>
  </table></div>;
}

function ContinueCard({catalog,onOpen}){
  const remembered=lastSession();
  const session=catalog.sessions.find(s=>s.id===remembered);
  const [state,setState]=useState({status:session?'loading':'none'});
  useEffect(()=>{
    if(!session)return;
    let live=true;
    api(sessionPath(session.id)).then(value=>{if(live)setState({status:'ready',value});},()=>{if(live)setState({status:'error'});});
    return()=>{live=false;};
  },[session]);
  if(!session)return null;
  const method=catalog.methods.find(m=>m.id===session.methodId);
  return <section className="rk-continue" aria-labelledby="rk-continue-h">
    <div><p className="rk-eyebrow">Continue research · last opened on this device</p><h2 id="rk-continue-h">{session.name}</h2>
      <dl className="rk-facts">
        <div><dt>Method</dt><dd>{method?.name||'Unavailable'}</dd></div>
        <div><dt>Instrument</dt><dd>{catalog.profile.instrumentId}</dd></div>
        <div><dt>Replay time</dt><dd className="rk-num">{state.status==='ready'?utc(state.value.state.throughNs):state.status==='loading'?'Loading…':'Unavailable'}</dd></div>
        <div><dt>Saved revision</dt><dd className="rk-num">{state.status==='ready'?state.value.state.revision:'—'}</dd></div>
      </dl>
    </div>
    <button type="button" className="rk-btn rk-btn-primary" onClick={()=>onOpen(session.id)}>Resume replay</button>
  </section>;
}

export function MyMethods({catalog,onOpen}){
  const [query,setQuery]=useState(''),[type,setType]=useState('ALL'),[sort,setSort]=useState('name');
  const counts=useMemo(()=>{const map=new Map();for(const s of catalog.sessions)map.set(s.methodId,(map.get(s.methodId)||0)+1);return map;},[catalog.sessions]);
  const visible=useMemo(()=>{
    const text=query.trim().toLowerCase();
    return catalog.methods.filter(m=>(type==='ALL'||m.kind===type)&&(!text||m.name.toLowerCase().includes(text)))
      .sort((a,b)=>sort==='sessions'?(counts.get(b.id)||0)-(counts.get(a.id)||0)||a.name.localeCompare(b.name):a.name.localeCompare(b.name));
  },[catalog.methods,query,type,sort,counts]);
  const newMethod=<a className="rk-btn rk-btn-primary" {...linkTo({screen:'method-new'})}><Icon name="plus" size={18}/><span>New Method</span></a>;
  if(!catalog.methods.length)return <>
    <PageHead eyebrow="Dashboard" title="My Methods" lead="A Method is the set of rules you want to test. Every Session replays one Method on real-time-ordered history."/>
    <section className="rk-first-use" aria-labelledby="rk-first-h">
      <h2 id="rk-first-h">Create your first Method</h2>
      <p>Write the idea down before you replay, so the result tests the idea and not hindsight.</p>
      <div className="rk-type-explain">
        <div><h3>Free Style</h3><p>Quick market orders or planned entries with your own stop and target per order.</p></div>
        <div><h3>Protocol</h3><p>Locked reward:risk and risk per trade, an optional checklist, and planned Limit/Stop entries only.</p></div>
      </div>
      <a className="rk-btn rk-btn-primary rk-btn-large" {...linkTo({screen:'method-new'})}>Create your first Method</a>
    </section>
  </>;
  return <>
    <PageHead eyebrow="Dashboard" title="My Methods" lead="Open a Method to see its Sessions, rules and analytics." actions={newMethod}/>
    <ContinueCard catalog={catalog} onOpen={onOpen}/>
    <dl className="rk-summary" aria-label="Research summary">
      <div><dt>Methods</dt><dd className="rk-num">{catalog.methods.length}</dd></div>
      <div><dt>Sessions</dt><dd className="rk-num">{catalog.sessions.length}</dd></div>
      <div><dt>Data</dt><dd>{catalog.label}</dd></div>
    </dl>
    <div className="rk-toolbar" role="search">
      <label className="rk-search"><Icon name="search" size={18}/><span className="alpha-sr-only">Search Methods</span><input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search Methods"/></label>
      <Segmented className="rk-filter" label="Method type" value={type} onChange={setType} options={[['ALL','All'],['FREE_STYLE','Free Style'],['PROTOCOL','Protocol']]}/>
      <label className="rk-select">Sort<select value={sort} onChange={e=>setSort(e.target.value)}><option value="name">Name A–Z</option><option value="sessions">Most Sessions</option></select></label>
      <span className="rk-count" aria-live="polite">{visible.length} of {catalog.methods.length}</span>
    </div>
    {visible.length?<ul className="rk-method-grid" aria-label="Methods">{visible.map(m=>{const n=counts.get(m.id)||0;const resume=catalog.sessions.find(s=>s.id===lastSession()&&s.methodId===m.id);return <li key={m.id}><article className="rk-method-card">
      <div className="rk-method-head"><span className="rk-avatar" aria-hidden="true">{m.name.charAt(0).toUpperCase()}</span><div><h2><a {...linkTo({screen:'method',method:m.id})}>{m.name}</a></h2><p>{n} {n===1?'Session':'Sessions'}{n?` · ${catalog.profile.instrumentId}`:''}</p></div><span className={`rk-tag rk-tag-${m.kind==='PROTOCOL'?'protocol':'free'}`}>{kindLabel(m.kind)}</span></div>
      <p className="rk-method-rules">{m.kind==='PROTOCOL'?`Risk ${m.riskPercent}% · R:R ${m.rr} · checklist ${m.checklistOn?'on':'off'} · ${m.conditions.length} ${m.conditions.length===1?'condition':'conditions'}`:'Quick or planned orders; stop and target chosen per order.'}</p>
      <div className="rk-method-foot"><a className="rk-btn" {...linkTo({screen:'method',method:m.id})}>Open</a>{resume?<button type="button" className="rk-btn rk-btn-quiet" onClick={()=>onOpen(resume.id)}>Resume</button>:!n?<a className="rk-btn rk-btn-quiet" {...linkTo({screen:'method',method:m.id,tab:'sessions'})}>New Session</a>:null}</div>
    </article></li>;})}</ul>:<StatePanel kind="filtered" title="No Method matches" action={<button type="button" className="rk-btn" onClick={()=>{setQuery('');setType('ALL');}}>Clear search</button>}><p>Your Methods are still saved. Clear the search or filter to see them.</p></StatePanel>}
    {catalog.sessions.length>0&&<section className="rk-section" aria-labelledby="rk-sessions-h"><div className="rk-section-head"><h2 id="rk-sessions-h">Sessions</h2><a {...linkTo({screen:'sessions'})}>All Sessions</a></div>
      <SessionTable sessions={catalog.sessions.slice(-5).reverse()} catalog={catalog} onOpen={onOpen} caption="Latest saved Sessions"/></section>}
  </>;
}

const RISK=['0.5','1','2'],RR=['1.5','2','3'];
export function MethodNew({catalog,onSaved}){
  const [kind,setKind]=useState('FREE_STYLE'),[name,setName]=useState(''),[risk,setRisk]=useState('1'),[rr,setRr]=useState('2');
  const [checklist,setChecklist]=useState(true),[conditions,setConditions]=useState(['']);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const creation=useRef(id('method'));
  const protocol=kind==='PROTOCOL';
  const filled=conditions.map(c=>c.trim()).filter(Boolean);
  async function save(event){
    event.preventDefault();if(busy)return;
    setBusy(true);setError('');
    try{
      const value={schemaVersion:1,artifact:'BTL-LOCAL-METHOD-1',id:creation.current,name:name.trim(),kind,
        checklistOn:protocol&&checklist,conditions:protocol?filled.map((label,i)=>({id:`condition:${i}`,label})):[],
        riskPercent:protocol?risk:null,rr:protocol?rr:null};
      await api('/methods',value);
      await onSaved(value.id);
    }catch(failure){setError(failure.message);setBusy(false);}
  }
  return <>
    <PageHead back={{label:'My Methods',to:{screen:'methods'}}} eyebrow="New Method" title="Write the rules first" lead="The type is chosen once. Sessions created from this Method inherit it."/>
    <div className="rk-editor">
      <form className="rk-card rk-form" onSubmit={save} aria-describedby={error?'rk-method-error':undefined}>
        <label>Method name<input value={name} onChange={e=>setName(e.target.value)} required maxLength={128} disabled={busy} autoComplete="off"/></label>
        <fieldset><legend>Type</legend><Segmented className="rk-type" label="Method type" value={kind} onChange={setKind} disabled={busy} options={[['FREE_STYLE','Free Style'],['PROTOCOL','Protocol']]}/></fieldset>
        {protocol&&<>
          <div className="rk-form-row">
            <fieldset><legend>Risk per trade (%)</legend><div className="rk-chips" role="group" aria-label="Risk presets">{RISK.map(v=><button type="button" key={v} aria-pressed={risk===v} disabled={busy} onClick={()=>setRisk(v)}>{v}%</button>)}</div><input aria-label="Risk per trade (%)" inputMode="decimal" value={risk} onChange={e=>setRisk(e.target.value)} required disabled={busy}/></fieldset>
            <fieldset><legend>Reward : risk</legend><div className="rk-chips" role="group" aria-label="Reward to risk presets">{RR.map(v=><button type="button" key={v} aria-pressed={rr===v} disabled={busy} onClick={()=>setRr(v)}>{v}</button>)}</div><input aria-label="Reward to risk" inputMode="decimal" value={rr} onChange={e=>setRr(e.target.value)} required disabled={busy}/></fieldset>
          </div>
          <label className="rk-switch"><input type="checkbox" checked={checklist} onChange={e=>setChecklist(e.target.checked)} disabled={busy}/><span aria-hidden="true"/>Checklist enforcement {checklist?'on':'off'}</label>
          <fieldset><legend>Conditions to check before every order</legend>
            <ol className="rk-conditions">{conditions.map((c,i)=><li key={i}><span className="rk-num" aria-hidden="true">{i+1}</span><input aria-label={`Condition ${i+1}`} value={c} maxLength={512} disabled={busy} onChange={e=>setConditions(list=>list.map((x,j)=>j===i?e.target.value:x))}/><button type="button" aria-label={`Remove condition ${i+1}`} disabled={busy||conditions.length===1} onClick={()=>setConditions(list=>list.filter((_,j)=>j!==i))}>×</button></li>)}</ol>
            <button type="button" className="rk-btn rk-btn-dashed" disabled={busy||conditions.length>=20} onClick={()=>setConditions(list=>[...list,''])}>+ Add condition</button>
          </fieldset>
        </>}
        {error&&<p id="rk-method-error" className="rk-error" role="alert">{error}</p>}
        <div className="rk-form-actions"><button className="rk-btn rk-btn-primary" disabled={busy||!name.trim()||(protocol&&!filled.length)}>{busy?'Saving…':'Save Method'}</button><a className="rk-btn rk-btn-quiet" {...linkTo({screen:'methods'})}>Cancel</a></div>
      </form>
      <aside className="rk-card rk-card-navy rk-howto" aria-labelledby="rk-howto-h">
        <h2 id="rk-howto-h">How this Method trades</h2>
        {protocol?<ol>
          <li>{checklist?`You assess all ${filled.length||'the'} conditions before an order can be reviewed.`:'Conditions are recorded but do not block orders.'}</li>
          <li>The server sizes lots from {risk||'—'}% of the saved balance and your stop.</li>
          <li>Target is set at {rr||'—'}R. Planned Limit or Stop entries only; no manual or partial close.</li>
        </ol>:<ol><li>Quick sends a market order without a stop or target.</li><li>Planned orders take your entry, stop and target, with an estimate before review.</li><li>Every order goes Draft → server Review → Confirm.</li></ol>}
        <p className="rk-note">Rules are fixed after saving; editing a Method is not available yet. Data for new Sessions: {sourceLine(catalog)}.</p>
      </aside>
    </div>
  </>;
}

export function MethodOverview({catalog,route,onOpen,onNewSession}){
  const method=catalog.methods.find(m=>m.id===route.method);
  const sessions=useMemo(()=>catalog.sessions.filter(s=>s.methodId===route.method),[catalog.sessions,route.method]);
  if(!method)return <><PageHead back={{label:'My Methods',to:{screen:'methods'}}} title="Method unavailable"/><StatePanel kind="unavailable" title="This Method is not in this workspace" action={<a className="rk-btn" {...linkTo({screen:'methods'})}>Back to My Methods</a>}><p>It may belong to another workspace or account. Nothing was changed.</p></StatePanel></>;
  const tab=route.tab;
  const newSession=<button type="button" className="rk-btn rk-btn-primary" onClick={event=>onNewSession(method.id,event)}><Icon name="plus" size={18}/><span>New Session</span></button>;
  const labels={overview:'Overview',sessions:`Sessions (${sessions.length})`,analytics:'Analytics',rules:'Rules'};
  return <>
    <PageHead back={{label:'My Methods',to:{screen:'methods'}}} eyebrow={kindLabel(method.kind)} title={method.name} actions={newSession}/>
    <nav className="rk-tabs" aria-label="Method sections">{METHOD_TABS.map(key=><a key={key} aria-current={tab===key?'page':undefined} {...linkTo({screen:'method',method:method.id,tab:key})}>{labels[key]}</a>)}</nav>
    {tab==='overview'&&<div className="rk-grid-2">
      <section className="rk-card" aria-labelledby="rk-ov-h"><h2 id="rk-ov-h">At a glance</h2><dl className="rk-facts">
        <div><dt>Type</dt><dd>{kindLabel(method.kind)}</dd></div>
        <div><dt>Sessions</dt><dd className="rk-num">{sessions.length}</dd></div>
        <div><dt>Data</dt><dd>{sourceLine(catalog)}</dd></div>
        <div><dt>Rules</dt><dd>{method.kind==='PROTOCOL'?`Risk ${method.riskPercent}% · R:R ${method.rr} · checklist ${method.checklistOn?'on':'off'}`:'Chosen per order'}</dd></div>
      </dl><p className="rk-note">A written hypothesis and last-used time are not recorded by the service yet.</p></section>
      <section className="rk-card" aria-labelledby="rk-ov-s"><div className="rk-section-head"><h2 id="rk-ov-s">Sessions</h2>{sessions.length>0&&<a {...linkTo({screen:'method',method:method.id,tab:'sessions'})}>See all</a>}</div>
        {sessions.length?<ul className="rk-mini-list">{sessions.slice(-3).reverse().map(s=><li key={s.id}><span><strong>{s.name}</strong><small>{catalog.profile.instrumentId} · from {s.startPeriod} · {money(s.initialBalance)}</small></span><button type="button" className="rk-btn rk-btn-small" onClick={()=>onOpen(s.id)} aria-label={`Open replay for ${s.name}`}>Open</button></li>)}</ul>
          :<StatePanel kind="empty" title="No Sessions yet" action={newSession}><p>A Session replays this Method on one instrument from a start month, with its own balance and journal.</p></StatePanel>}
      </section>
    </div>}
    {tab==='sessions'&&(sessions.length?<SessionTable sessions={sessions} catalog={catalog} onOpen={onOpen} caption={`Sessions of ${method.name}`}/>:<StatePanel kind="empty" title="No Sessions yet" action={newSession}><p>Create a Session to start replaying this Method.</p></StatePanel>)}
    {tab==='analytics'&&<MethodAnalytics method={method} sessions={sessions}/>}
    {tab==='rules'&&<section className="rk-card" aria-labelledby="rk-rules-h"><h2 id="rk-rules-h">Rules</h2>
      <dl className="rk-facts"><div><dt>Type</dt><dd>{kindLabel(method.kind)}</dd></div>{method.kind==='PROTOCOL'&&<><div><dt>Locked risk per trade</dt><dd className="rk-num">{method.riskPercent}%</dd></div><div><dt>Locked reward : risk</dt><dd className="rk-num">{method.rr}</dd></div><div><dt>Checklist enforcement</dt><dd>{method.checklistOn?'On: orders need every condition assessed':'Off: conditions are recorded only'}</dd></div></>}</dl>
      {method.kind==='PROTOCOL'&&<><h3>Conditions</h3><ol className="rk-rule-list">{method.conditions.map(c=><li key={c.id}>{c.label}</li>)}</ol></>}
      <details className="rk-provenance"><summary>Provenance</summary><dl className="rk-facts"><div><dt>Method id</dt><dd><code>{method.id}</code></dd></div>{sessions[0]&&<div><dt>Rule hash (pinned by Sessions)</dt><dd><code>{sessions[0].methodHash}</code></dd></div>}</dl></details>
      <p className="rk-note">Rules stay fixed after saving so earlier evidence keeps its meaning. Editing and archiving are not available yet.</p>
    </section>}
  </>;
}

function MethodAnalytics({method,sessions}){
  return <div className="rk-stack">
    <StatePanel kind="unavailable" title="Method analytics is not published yet"><p>Combining Sessions needs a server calculation (pooled completed positions, expectancy in R, profit factor on compatible units, and which Sessions were included or excluded). RIKSORA does not average win rates or stitch independent balances in the browser.</p></StatePanel>
    {sessions.length>0&&<section className="rk-card" aria-labelledby="rk-ma-h"><h2 id="rk-ma-h">Analytics per Session</h2><p className="rk-note">Each Session has its own committed analytics.</p>
      <ul className="rk-mini-list">{sessions.map(s=><li key={s.id}><span><strong>{s.name}</strong><small>from {s.startPeriod} · {money(s.initialBalance)} starting balance</small></span><a className="rk-btn rk-btn-small" {...linkTo({screen:'analytics',method:method.id,of:s.id})} aria-label={`Analytics for ${s.name}`}>Session analytics</a></li>)}</ul></section>}
  </div>;
}

export function Analytics({catalog,route}){
  const methodId=route.method||catalog.sessions.find(s=>s.id===route.analyticsSession)?.methodId||'';
  const sessions=catalog.sessions.filter(s=>!methodId||s.methodId===methodId);
  const sessionId=route.analyticsSession;
  const session=catalog.sessions.find(s=>s.id===sessionId);
  const [result,setResult]=useState({key:null});
  const [attempt,setAttempt]=useState(0);
  const key=session?`${session.id}:${attempt}`:null;
  useEffect(()=>{
    if(!key)return;
    let live=true;
    api(sessionPath(key.slice(0,key.lastIndexOf(':')))+'/view',{timeframe:'1m'}).then(view=>{if(live)setResult({key,status:'ready',view});},error=>{if(live)setResult({key,status:'error',message:error.message});});
    return()=>{live=false;};
  },[key]);
  const state=result.key===key?result:{status:'loading'};
  const pick=next=>navigate({screen:'analytics',...next});
  return <>
    <PageHead eyebrow="Analytics" title="Research analytics" lead="Pick a Method and a Session. Statistics come from committed positions only."/>
    <div className="rk-toolbar" role="group" aria-label="Analytics scope">
      <label className="rk-select">Method<select value={methodId} onChange={e=>pick({method:e.target.value||undefined})}><option value="">All Methods</option>{catalog.methods.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
      <label className="rk-select">Session<select value={session?.id||''} onChange={e=>pick({method:methodId||undefined,of:e.target.value||undefined})}><option value="">Choose a Session</option>{sessions.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      {methodId&&<a className="rk-btn rk-btn-quiet" {...linkTo({screen:'method',method:methodId,tab:'analytics'})}>Method analytics</a>}
    </div>
    {!catalog.sessions.length?<StatePanel kind="empty" title="No Sessions to analyse" action={<a className="rk-btn" {...linkTo({screen:'methods'})}>Go to My Methods</a>}><p>Analytics appear after you create a Session and close at least one position.</p></StatePanel>
      :!session?<StatePanel kind="empty" title={sessionId?'This Session is not in this workspace':'Choose a Session'}><p>{sessionId?'It may belong to another workspace. Pick one from the list.':'Session analytics show one Session at a time, so independent balances are never mixed.'}</p></StatePanel>
      :state.status==='loading'?<StatePanel kind="loading" title="Loading committed analytics…"/>
      :state.status==='error'?<StatePanel kind="error" title="Analytics could not load" action={<button type="button" className="rk-btn" onClick={()=>setAttempt(n=>n+1)}>Retry</button>}><p>{state.message} Nothing was changed.</p></StatePanel>
      :<SessionAnalytics view={state.view} catalog={catalog}/>}
  </>;
}

function SessionAnalytics({view,catalog}){
  const analysis=view.analysis;
  if(!analysis||analysis.status!=='COMPLETE')return <StatePanel kind="unavailable" title="Analytics unavailable for this Session"><p>{analysis?.reason??'The service has no compatible analysis for this Session.'} No partial history is shown as a complete result.</p></StatePanel>;
  const {metrics,account}=analysis;
  const scope=[['Session',view.metadata.name],['Method',`${view.method.name} · ${kindLabel(view.method.kind)}`],['Instrument',catalog.profile.instrumentId],['Range',`${view.metadata.startPeriod} → ${utc(view.state.throughNs)}`],['Completed positions',String(metrics.tradeCount)],['Unresolved / expired',`${metrics.unresolved} / ${metrics.expired}`]];
  const secondary=[['Wins / losses / breakeven',`${metrics.wins} / ${metrics.losses} / ${metrics.breakeven}`],['Average win (USD)',ratioLabel(metrics.averageWin)],['Average loss (USD)',ratioLabel(metrics.averageLoss)],['Longest win / loss streak',`${metrics.maxWinStreak} / ${metrics.maxLossStreak}`],['Mean R',`${ratioLabel(metrics.averageR)} · ${metrics.rEligible} eligible / ${metrics.rExcluded} excluded`],['Commission (USD)',account.commission],['Starting balance',money(view.state.initialBalance)],['Committed balance now',money(account.balance)]];
  return <div className="rk-stack">
    <dl className="rk-scope" aria-label="Scope">{scope.map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
    <dl className="rk-metrics" aria-label="Primary results">
      <div><dt>Realized net (USD)</dt><dd className="rk-num">{money(account.netCashChange)}</dd></div>
      <div><dt>Win rate</dt><dd className="rk-num">{ratioLabel(metrics.winRate,{percent:true})}</dd><dd className="rk-sub">of {metrics.tradeCount} completed</dd></div>
      <div><dt>Expectancy (USD)</dt><dd className="rk-num">{ratioLabel(metrics.expectancy)}</dd></div>
      <div><dt>Profit factor</dt><dd className="rk-num">{ratioLabel(metrics.profitFactor)}</dd></div>
      <div><dt>Max cash drawdown</dt><dd className="rk-num">{money(metrics.maxDrawdown)}</dd><dd className="rk-sub">{ratioLabel(metrics.maxDrawdownRate,{percent:true})}</dd></div>
    </dl>
    <section className="rk-card rk-card-navy rk-equity"><AlphaEquityChart view={view}/>
      <details><summary>Balance path as a table</summary><div className="rk-table-scroll" tabIndex={0} role="region" aria-label="Committed balance postings, scrolls sideways"><table className="rk-table"><thead><tr><th scope="col">Time (UTC)</th><th scope="col">Committed balance</th></tr></thead><tbody>{analysis.equity.map(row=><tr key={row.eventId}><td className="rk-num">{utc(row.timeNs)}</td><td className="rk-num">{money(row.balance)}</td></tr>)}</tbody></table></div></details>
    </section>
    <dl className="rk-facts rk-card" aria-label="More results">{secondary.map(([k,v])=><div key={k}><dt>{k}</dt><dd className="rk-num">{v}</dd></div>)}</dl>
    <p className="rk-note">Only completed positions enter the denominators; partial exits stay inside their original position. Indicative unrealized equity is not part of these results. Unavailable means the value is undefined for this sample, not zero.</p>
  </div>;
}

export function Placeholder({screen,catalog,onOpen,onSource,onFeedback}){
  if(screen==='account')return <><PageHead eyebrow="Account" title="Account" lead="This is the private local workspace, so there is no account here. Signing in, workspaces and plans live on the secure account page."/>
    <StatePanel kind="unavailable" title="No account in local mode" action={<a className="rk-btn rk-btn-primary" href="/?page=account">Open account page</a>}><p>The account page needs the https:// address. Local Sessions stay on this computer.</p></StatePanel></>;
  if(screen==='replay')return <><PageHead eyebrow="Replay" title="Replay needs a Session" lead="Pick a Session to continue from its saved replay time, or open a Method to start a new one."/>
    {catalog.sessions.length?<SessionTable sessions={catalog.sessions.slice().reverse()} catalog={catalog} onOpen={onOpen} caption="Sessions you can replay"/>:<StatePanel kind="empty" title="No Sessions yet" action={<a className="rk-btn" {...linkTo({screen:'methods'})}>Go to My Methods</a>}><p>Create a Method, then a Session inside it.</p></StatePanel>}</>;
  if(screen==='journal')return <><PageHead eyebrow="Journal" title="Journal" lead="Each Session keeps its own journal next to the chart. A journal across Sessions needs a server list that is not published yet."/>
    {catalog.sessions.length?<SessionTable sessions={catalog.sessions.slice().reverse()} catalog={catalog} onOpen={onOpen} caption="Sessions with a journal"/>:<StatePanel kind="empty" title="Nothing journaled yet"><p>Journals start when you create a Session.</p></StatePanel>}</>;
  return <><PageHead eyebrow="Help" title="Help" lead="Short answers about how RIKSORA research works."/>
    <div className="rk-grid-2">
      <section className="rk-card"><h2>How replay works</h2><p>History is revealed step by step from the Session’s saved time. Orders fill on later observed Bid/Ask quotes only, never on prices that were not yet visible.</p></section>
      <section className="rk-card"><h2>Draft, review, confirm</h2><p>Buy or Sell opens a draft. The server reviews exact values, and nothing is placed until you confirm. Drawing a position is a planning tool, not a trade.</p></section>
      <section className="rk-card"><h2>Data limitations</h2><p>Each Session pins one source and version. Missing or refused months are never filled with another feed.</p><button type="button" className="rk-btn" onClick={onSource}>Source details</button></section>
      <section className="rk-card"><h2>Report a problem</h2><p>Send optional research feedback. Do not include passwords or tokens.</p><button type="button" className="rk-btn" onClick={onFeedback}>Open feedback</button></section>
    </div></>;
}
