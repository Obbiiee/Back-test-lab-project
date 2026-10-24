import {useState} from 'react';
import {methodFromForm,newId,periodLabel,startPeriods} from './betaWorkspace.js';

// Canvas 09 "New Session, daily window, Trash". Presentation only: every value
// shown comes from catalog/access; creation uses the existing createSession route.
const BALANCES=['10000','50000','100000'];
const AVATAR={XAU:['Au','gold'],USD:['$','blue'],EUR:['€','blue-strong'],GBP:['£','coral'],AUD:['A$','ice'],NZD:['N$','ice'],CAD:['C$','coral'],CHF:['Fr','coral'],JPY:['¥','ice']};
const avatar=symbol=>AVATAR[symbol.slice(0,3)]??[symbol.slice(0,2),'navy'];
// Group digits of a decimal string without converting it to a float.
function usd(value){
  const [whole,fraction]=String(value).split('.');
  const grouped=whole.replace(/\B(?=(\d{3})+(?!\d))/g,',');
  return '$'+grouped+(fraction?'.'+fraction:'');
}
const shortUsd=value=>Number(value)%1000===0&&Number(value)>=1000?'$'+Number(value)/1000+'K':usd(value);
const validBalance=value=>/^\d{1,9}(\.\d{1,2})?$/.test(value)&&Number(value)>0;

export function BetaNewSession({catalog,access,disabled,onCreated,onCancel,run,client,reload}){
  // Gold first (the product's home market), then the server's order.
  const instruments=[...catalog.instruments].sort((a,b)=>(b.symbol==='XAUUSD')-(a.symbol==='XAUUSD'));
  const [symbol,setSymbol]=useState(instruments[0]?.symbol??'');
  const instrument=instruments.find(i=>i.symbol===symbol);
  const periods=startPeriods(instrument);
  const [periodChoice,setPeriodChoice]=useState('');
  const period=periods.includes(periodChoice)?periodChoice:periods[0]??'';
  const historical=instruments.some(i=>Array.isArray(i.periods));
  const [preset,setPreset]=useState('10000'),[custom,setCustom]=useState('');
  const [methodId,setMethodId]=useState(catalog.methods[0]?.id??'');
  const [name,setName]=useState(''),[named,setNamed]=useState(false);
  const [strategyOpen,setStrategyOpen]=useState(!catalog.methods.length),[methodKind,setMethodKind]=useState('FREE_STYLE');
  const balance=preset==='CUSTOM'?custom.trim():preset;
  const method=catalog.methods.find(m=>m.id===methodId);
  const sessionName=named?name:`${symbol} ${method?.name??'Session'}`.slice(0,128);
  const free=access?Math.max(0,access.savedLimit-access.savedSessions):null;
  const full=free===0;
  const ready=!!symbol&&!!period&&!!method&&validBalance(balance)&&sessionName.trim().length>0&&!full;
  const filled=[!!symbol,validBalance(balance),!!method],current=filled.indexOf(false);
  function create(event){
    event.preventDefault();if(!ready||disabled)return;
    run(async()=>{const saved=await client.createSession({id:newId('session'),name:sessionName.trim(),methodId,symbol,startPeriod:period,initialBalance:balance});await reload(saved.id);onCreated?.();});
  }
  function saveStrategy(event){
    event.preventDefault();const f=new FormData(event.currentTarget),id=newId('method');
    run(async()=>{await client.createMethod(methodFromForm(f,id));await reload(null);setMethodId(id);setStrategyOpen(false);});
  }
  return <section className="beta-new" aria-labelledby="beta-new-title">
    <div className="beta-new-head">
      <h2 id="beta-new-title">New Session</h2>
      <ol aria-label="Steps" className="beta-steps">{['Pair','Start','Strategy'].map((label,i)=><li key={label} aria-current={current===i?'step':undefined} className={filled[i]?'done':''}>{i+1} {label}{filled[i]&&<span className="beta-visually-hidden"> (done)</span>}</li>)}</ol>
    </div>

    <fieldset className="beta-pairs" disabled={disabled}>
      <legend>What do you want to trade?</legend>
      <div className="beta-pair-grid">{instruments.map(i=>{const [mark,tone]=avatar(i.symbol);return <label key={i.symbol} className="beta-pair">
        <input type="radio" name="beta-pair" value={i.symbol} checked={symbol===i.symbol} onChange={()=>setSymbol(i.symbol)}/>
        <span><i aria-hidden="true" className={'beta-pair-mark beta-tone-'+tone}>{mark}</i><span><b>{i.symbol}</b><small>{i.dataLabel??'Demo data'}</small></span></span>
      </label>;})}</div>
      <p className="beta-new-note">{historical?'Only months that passed our data checks can be picked. Results are historical replays, not broker fills.':'Every pair here is a short synthetic demo, not a historical month.'}</p>
    </fieldset>

    {periods.length>1&&<label className="beta-period">Start month (UTC)
      <select value={period} disabled={disabled} onChange={e=>setPeriodChoice(e.target.value)}>{periods.map(p=><option key={p} value={p}>{periodLabel(p)}</option>)}</select>
    </label>}

    <div className="beta-new-row">
      <fieldset className="beta-chips" disabled={disabled}>
        <legend>Starting balance</legend>
        <div>{BALANCES.map(b=><label key={b}><input type="radio" name="beta-balance" checked={preset===b} onChange={()=>setPreset(b)}/><span className="beta-mono">{shortUsd(b)}</span></label>)}
          <label><input type="radio" name="beta-balance" checked={preset==='CUSTOM'} onChange={()=>setPreset('CUSTOM')}/><span>Custom</span></label></div>
        {preset==='CUSTOM'&&<label className="beta-custom">Custom balance (USD)<input inputMode="decimal" value={custom} onChange={e=>setCustom(e.target.value)} placeholder="25000" aria-invalid={custom!==''&&!validBalance(custom.trim())}/></label>}
        {preset==='CUSTOM'&&custom!==''&&!validBalance(custom.trim())&&<small className="beta-field-error">Use a positive amount with up to 2 decimals.</small>}
      </fieldset>
      <fieldset className="beta-chips" disabled={disabled}>
        <legend>Strategy</legend>
        <div>{catalog.methods.map(m=><label key={m.id}><input type="radio" name="beta-method" checked={methodId===m.id} onChange={()=>setMethodId(m.id)}/><span>{m.name}</span></label>)}
          <button type="button" className="beta-chip-add" aria-expanded={strategyOpen} onClick={()=>setStrategyOpen(o=>!o)}>+ New strategy</button></div>
      </fieldset>
    </div>

    {strategyOpen&&<form className="beta-strategy-form" onSubmit={saveStrategy} aria-label="New strategy">
      <label>Strategy name<input name="name" maxLength={128} required disabled={disabled}/></label>
      <label>Strategy type<select name="kind" value={methodKind} disabled={disabled} onChange={e=>setMethodKind(e.target.value)}><option value="FREE_STYLE">Free Style</option><option value="PROTOCOL">Protocol</option></select></label>
      {methodKind==='PROTOCOL'&&<><label>Risk percent<input name="risk" defaultValue="1" required disabled={disabled}/></label><label>Reward / risk<input name="rr" defaultValue="2" required disabled={disabled}/></label><label>Checklist<select name="checklist" disabled={disabled}><option>ON</option><option>OFF</option></select></label><label className="beta-wide">Conditions, one per line<textarea name="conditions" required maxLength={4000} disabled={disabled}/></label></>}
      <div className="beta-wide beta-actions"><button disabled={disabled}>Save strategy</button>{catalog.methods.length>0&&<button type="button" className="beta-ghost" disabled={disabled} onClick={()=>setStrategyOpen(false)}>Close</button>}</div>
    </form>}

    <form className="beta-new-summary" onSubmit={create}>
      <label className="beta-name">Session name<input value={sessionName} maxLength={128} required disabled={disabled} onChange={e=>{setNamed(true);setName(e.target.value);}}/></label>
      <span className="beta-summary-text"><b>{symbol}{periods.length>1&&period?' · '+periodLabel(period):''} · {validBalance(balance)?usd(balance):'—'} · {method?.name??'Pick a strategy'}</b>
        <span>{access?full?`All ${access.savedLimit} saved Sessions are in use. Move one to Trash to make room.`:`Uses 1 of your ${access.savedLimit} saved Sessions (${free-1} left after this)`:'Checking your saved Sessions…'}</span></span>
      {onCancel&&<button type="button" className="beta-ghost" disabled={disabled} onClick={onCancel}>Cancel</button>}
      <button className="beta-create" disabled={disabled||!ready}>Create Session</button>
    </form>
  </section>;
}

export function BetaWindowCard({access}){
  if(!access||access.tier!=='FREE')return null;
  if(access.freeActivationAvailable)return <section className="beta-window" aria-labelledby="beta-window-title">
    <span className="beta-kicker">BEFORE THE FIRST TRADE</span>
    <h2 id="beta-window-title">Today’s replay window is ready</h2>
    <p>Free includes one window a day. Starting a Session’s replay uses it; once started, that Session stays tradable. Next free window: 00:00 {access.resetTimezone}.</p>
  </section>;
  return <section className="beta-window-used" aria-labelledby="beta-window-used-title">
    <h2 id="beta-window-used-title">Window already used today</h2>
    <p>Keep trading in Sessions you started earlier, or come back after 00:00 {access.resetTimezone}.</p>
  </section>;
}

// Canvas 08 Sessions hub. Cards show only catalog metadata (name, pair, strategy,
// starting balance). Current balance, P&L, replay progress, "Continue replay" and the
// In progress/Ended filter need per-Session summary fields the catalog does not expose.
export function BetaSessionsHub({sessions,methods,access,busy,writeDisabled,onOpen,onTrash,onNew}){
  const methodById=new Map(methods.map(m=>[m.id,m]));
  const left=access?Math.max(0,access.savedLimit-access.savedSessions):null;
  const plan=access?.tier==='PRO'?'Pro':'Free';
  return <>
    <section className="beta-hero" aria-labelledby="beta-hero-h">
      <span aria-hidden="true" className="beta-hero-dot beta-hero-dot-1"/><span aria-hidden="true" className="beta-hero-dot beta-hero-dot-2"/><span aria-hidden="true" className="beta-hero-dot beta-hero-dot-3"/>
      <div className="beta-hero-copy"><h2 id="beta-hero-h">Welcome back.<br/>Ready for the next round?</h2>
        <p>Open a Session to pick up where its replay stopped.</p>
        <div><button type="button" className="beta-hero-new" disabled={writeDisabled||left===0} onClick={onNew}>+ New Session</button></div></div>
      {access&&<ul className="beta-hero-stats">
        <li><span>Sessions</span><strong className="beta-mono">{access.savedSessions}<small> / {access.savedLimit}</small></strong></li>
        {access.tier==='FREE'&&<li><span>Today’s window</span><strong className={access.freeActivationAvailable?'beta-ready':''}>{access.freeActivationAvailable?'Ready':'Used'}</strong></li>}
      </ul>}
    </section>
    <section className="beta-sessions" aria-labelledby="beta-sessions-title">
      <h2 id="beta-sessions-title">Your Sessions</h2>
      <ul className="beta-session-cards" aria-label="Saved Sessions">{sessions.map(s=>{
        const [mark,tone]=avatar(s.symbol),method=methodById.get(s.methodId);
        return <li key={s.id}><article>
          <header><i aria-hidden="true" className={'beta-pair-mark beta-tone-'+tone}>{mark}</i>
            <span><h3>{s.name}</h3><small>{s.symbol} · {method?method.name:'Strategy unavailable'}</small></span></header>
          <div className="beta-card-balance"><strong className="beta-mono">{usd(s.initialBalance)}</strong><span>Starting balance · demo data</span></div>
          <p className="beta-card-status">{method?.kind==='PROTOCOL'?'Protocol strategy':'Free Style strategy'} · balance and replay position show inside</p>
          <div className="beta-card-actions">
            <button className="beta-card-open" disabled={busy} onClick={()=>onOpen(s)} aria-label={'Open '+s.name}>Open</button>
            <button className="beta-card-trash" disabled={writeDisabled} onClick={()=>onTrash(s)} aria-label={'Move '+s.name+' to Trash'}>Trash</button>
          </div>
        </article></li>;})}
        <li><button type="button" className="beta-card-new" disabled={writeDisabled||left===0} onClick={onNew}>
          <span aria-hidden="true">+</span>New Session
          {access&&<small>{left===0?`All ${access.savedLimit} slots used · move one to Trash`:`${left} slot${left===1?'':'s'} left on ${plan}`}</small>}</button></li>
      </ul>
    </section>
  </>;
}

export function BetaTrash({sessions,disabled,onRestore}){
  return <section className="beta-trash" aria-labelledby="beta-trash-title">
    <div className="beta-trash-head"><h2 id="beta-trash-title">Trash</h2><span>Kept for 30 days</span></div>
    {sessions.length?<ul>{sessions.map(s=>{const [mark,tone]=avatar(s.symbol);return <li key={s.id}>
      <i aria-hidden="true" className={'beta-pair-mark beta-tone-'+tone}>{mark}</i>
      <span><b>{s.name}</b><small>{s.symbol} · in Trash</small></span>
      <button type="button" disabled={disabled} onClick={()=>onRestore(s)} aria-label={'Restore '+s.name}>Restore</button>
    </li>;})}</ul>:<p>Nothing in Trash.</p>}
    <p className="beta-trash-note">Restore puts the Session back exactly as you left it.</p>
  </section>;
}
