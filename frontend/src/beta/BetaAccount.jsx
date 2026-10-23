import {lazy,Suspense,useEffect,useRef,useState} from 'react';
import BetaBilling from './BetaBilling.jsx';
import BetaSupport from './BetaSupport.jsx';
import {createBetaClient} from './betaClient.js';
import {betaNotice} from './betaWorkspace.js';
import BetaAuth from './BetaAuth.jsx';
import AlphaBrand from '../tickAlpha/AlphaBrand.jsx';
import '../tickAlpha/tickAlpha.css';
import './beta.css';
const Workspace=lazy(()=>import('./BetaWorkspace.jsx'));
const GOOGLE_NOTICE={GOOGLE_LOGIN_FAILED:'Google sign-in didn’t finish. The link expired or was opened twice. Try again, or sign in with email.',
  GOOGLE_STATE_REFUSED:'Google sign-in didn’t finish. The link expired or was opened twice. Try again, or sign in with email.',
  GOOGLE_BUSY:'Google sign-in is busy. Wait a moment and try again.'};

// Canvas 06/08 avatar menu: a disclosure of plain buttons; Escape or an outside click closes it.
function AccountMenu({user,busy,onAccount,onSupport,onSignOut,onSignOutAll}){
  const [open,setOpen]=useState(false),wrap=useRef(null),toggle=useRef(null);
  useEffect(()=>{
    if(!open)return;
    const outside=event=>{if(!wrap.current?.contains(event.target))setOpen(false);};
    document.addEventListener('pointerdown',outside);return()=>document.removeEventListener('pointerdown',outside);
  },[open]);
  const pick=action=>()=>{setOpen(false);action();};
  return <div className="beta-menu" ref={wrap} onKeyDown={event=>{if(event.key==='Escape'&&open){setOpen(false);toggle.current?.focus();}}}>
    <button ref={toggle} type="button" className="beta-avatar" aria-label="Account menu" aria-expanded={open} aria-controls="beta-account-menu" onClick={()=>setOpen(o=>!o)}>{user.email.charAt(0).toUpperCase()}</button>
    {open&&<div id="beta-account-menu" className="beta-menu-panel">
      <div className="beta-menu-who"><strong>{user.email}</strong><span>verified</span></div>
      <button type="button" disabled={busy} onClick={pick(onAccount)}>Account &amp; plan</button>
      <button type="button" disabled={busy} onClick={pick(onSupport)}>Support</button>
      <button type="button" disabled={busy} onClick={pick(onSignOut)}>Sign out</button>
      <button type="button" disabled={busy} className="beta-menu-danger" onClick={pick(onSignOutAll)}>Sign out on all devices</button>
    </div>}
  </div>;
}

export default function BetaAccount({googleOnly=false,entryPath='/?page=beta'}={}){
  const [client]=useState(()=>createBetaClient());
  const [user,setUser]=useState(null),[workspaces,setWorkspaces]=useState([]),[selected,setSelected]=useState(null);
  const [workspaceSection,setWorkspaceSection]=useState('sessions');
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[uncertain,setUncertain]=useState(false),[loaded,setLoaded]=useState(false);
  const [googleFinishing,setGoogleFinishing]=useState(()=>new URLSearchParams(location.search).get('auth')==='google'),[providers,setProviders]=useState(null),[expired,setExpired]=useState(false),[area,setArea]=useState('workspaces'),[tier,setTier]=useState(null);
  const flight=useRef(false),live=useRef(true);
  useEffect(()=>{live.current=true;return()=>{live.current=false;client.clear();};},[client]);
  async function run(operation){
    if(flight.current)return;flight.current=true;setBusy(true);setNotice('');
    try{await operation();}catch(error){if(live.current){setNotice(googleOnly ? betaNotice(error) : (GOOGLE_NOTICE[error?.code]??betaNotice(error)));if(error.reconciliationRequired)setUncertain(true);if(!client.hasSession()){setExpired(error?.code==='SIGN_IN_REQUIRED');setUser(null);setSelected(null);setWorkspaces([]);}}}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  useEffect(()=>{
    let active=true;
    void Promise.resolve().then(async()=>{
      if(!active||location.protocol!=='https:')return;
      try{const value=await client.providers();if(active&&!client.hasSession())setProviders(value);}catch{if(active&&!client.hasSession())setProviders({googleConfigured:false});}
      if(!active||new URLSearchParams(location.search).get('auth')!=='google')return;
      // Consume the one-use cookie handoff once; never retain callback state in URLs.
      history.replaceState(null,'',entryPath);
      await run(async()=>{try{const me=await client.exchangeGoogle();const list=await client.workspaces();if(active){setUser(me);setWorkspaces(list);setLoaded(true);}}finally{if(active)setGoogleFinishing(false);}});
    });
    return()=>{active=false;};
  // One verified identity client per mount; StrictMode's discarded setup is cancelled.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[client]);
  const secure=location.protocol==='https:';
  const signOut=(all=false)=>run(async()=>{try{await client.logout(all);}finally{if(live.current){setUser(null);setSelected(null);setWorkspaces([]);setArea('workspaces');setTier(null);}}});
  const expire=()=>{client.clear();setExpired(true);setUser(null);setSelected(null);setWorkspaces([]);setArea('workspaces');setTier(null);};
  // Re-selecting the current workspace bumps the client generation, cancelling its in-flight requests.
  const go=next=>{if(selected)client.selectWorkspace(selected.id);setSelected(null);setNotice('');setArea(next);};
  const roleLabel=role=>role==='OWNER'?'Owner':'View only';
  return <main className={`alpha-identity beta-account${selected?' beta-account-workspace':''}`}>
    <header className="alpha-identity-nav beta-nav"><AlphaBrand href="/"/><span className="beta-nav-badge">Practice preview</span>
      {user&&selected&&<nav className="beta-mainnav" aria-label="Main">{['Sessions','Strategies','Journal','Statistics'].map(label=><button key={label} type="button" aria-current={workspaceSection===label.toLowerCase()?'page':undefined} onClick={()=>setWorkspaceSection(label.toLowerCase())}>{label}</button>)}</nav>}
      {user?<div className="beta-userbar">{tier&&<span className="beta-tier">{tier}</span>}
        <a href="/login/?view=features">Explore features</a><AccountMenu user={user} busy={busy} onAccount={()=>go('account')} onSupport={()=>go('support')} onSignOut={()=>signOut()} onSignOutAll={()=>signOut(true)}/></div>
      :<nav aria-label="Public"><a href="/">Home</a> · <a href="/login/?view=features">Explore features</a></nav>}</header>
    <section className={`alpha-identity-content${selected?' alpha-identity-workspace':''}`}>
      {!secure?<div className="beta-card beta-card-center"><h1>Open the secure Beta address</h1><p>Verified account access requires HTTPS.</p></div>:!user&&googleFinishing?<div className="beta-card beta-card-center" role="status"><h1>Finishing Google sign-in…</h1><p>This takes a second. Don’t close the tab.</p></div>:!user&&googleOnly?<div className="beta-auth"><div className="beta-auth-hero"><p className="beta-auth-title">Welcome back, <span>trader.</span></p><p>Your practice Sessions, journal and results stay saved in your workspace.</p><ul><li>16 synthetic demo pairs</li><li>Not five years of market history</li></ul></div><div className="beta-card beta-auth-card"><h1>Sign in to RIKSORA</h1><p>Use your Google account to continue.</p>{providers?.googleConfigured?<a className="beta-google" href={client.googleStart()}>Continue with Google</a>:<p role="status">{providers ? 'Google sign-in unavailable. Try again later.' : 'Checking sign-in availability…'}</p>}<p className="beta-muted">Email registration and payments are unavailable in this staging.</p></div></div>:!user?<BetaAuth client={client} providers={providers} expired={expired} onSignedIn={(me,list,configured)=>{setExpired(false);setNotice('');setUser(me);setWorkspaces(list);setLoaded(true);setArea('workspaces');setTier(null);if(configured)setProviders(configured);}}/>:<>
        {selected?<><button className="beta-back" disabled={busy} onClick={()=>go('workspaces')}>Back to workspaces</button>
          <Suspense fallback={<p role="status">Loading Beta workspace…</p>}>{googleOnly && providers?.demoConfigured !== true ? <p>Practice replay is unavailable in this environment.</p> : <Workspace key={selected.id} client={client} workspace={selected} section={workspaceSection} onSection={setWorkspaceSection} onExpired={expire} onPlans={()=>go('account')} onAccess={access=>setTier(access.tier)}/> }</Suspense></>
        :area==='account'?<div className="beta-picker beta-area">
          <div className="beta-area-head"><h1>Account &amp; plan</h1><p>Your profile, today’s usage and your plan in one place.</p></div>
          <section className="beta-profile" aria-labelledby="beta-profile-h"><h2 id="beta-profile-h">Profile</h2>
            <div className="beta-profile-who"><span aria-hidden="true">{user.email.charAt(0).toUpperCase()}</span><strong>{user.email}</strong><small>verified</small></div>
            <button type="button" className="beta-signout" disabled={busy} onClick={()=>signOut()}>Sign out</button></section>
          {!googleOnly&&providers?.billingConfigured?<BetaBilling key={user.id} client={client} onExpired={expire}/>
            :<section className="beta-plan-off" aria-label="Plan"><h2>Checkout is not set up here</h2><p>This environment has no sandbox checkout configured, so no plan can be bought from this page. Your plan and limits come from the server: open a workspace to see your saved Sessions and today’s replay window.</p></section>}
        </div>
        :area==='support'?<div className="beta-picker beta-area">
          <div className="beta-area-head"><h1>How can we help?</h1><p>Account help and test feedback.</p></div>
          {googleOnly ? <p>Support submission is not enabled in this staging. Report test problems to the operator who invited you.</p> : <BetaSupport key={'support-'+user.id} client={client} onExpired={expire}/>}
        </div>
        :<div className="beta-picker">
          <h1>Where do you want<br/>to practise today?</h1><p>A workspace holds its own strategies and Sessions. Your saved Sessions remain available after signing in again.</p>
          <button disabled={busy} onClick={()=>run(async()=>{const list=await client.workspaces();setWorkspaces(list);setLoaded(true);setUncertain(false);})}>Refresh workspaces</button>
          <ul className="beta-workspace-list">{workspaces.map(ws=><li key={ws.id}><button disabled={busy} onClick={()=>{client.selectWorkspace(ws.id);setWorkspaceSection('sessions');setSelected(ws);}}>
            <span className="beta-ws-avatar" aria-hidden="true">{ws.name.trim().charAt(0).toUpperCase()||'W'}</span><strong>{ws.name}</strong><span className={`beta-role beta-role-${ws.role==='OWNER'?'owner':'viewer'}`}>{roleLabel(ws.role)}</span><span className="beta-open">Open</span></button></li>)}
            <li><form className="beta-ws-create" onSubmit={event=>{event.preventDefault();const name=String(new FormData(event.currentTarget).get('name')||'').trim();if(!name||uncertain||!loaded||busy)return;setUncertain(true);run(async()=>{
              await client.createWorkspace(name);const list=await client.workspaces();if(live.current){setWorkspaces(list);setLoaded(true);setUncertain(false);}
            });}}><span className="beta-ws-plus" aria-hidden="true">+</span><label>Workspace name<input name="name" maxLength={128} required disabled={busy||uncertain||!loaded} placeholder="e.g. Gold scalping lab"/></label><button disabled={busy||uncertain||!loaded}>Create workspace</button></form></li></ul>
          <p className="beta-demo-note"><span aria-hidden="true"/>Beta practice data is a short demo per pair, not a full historical month yet.</p>
        </div>}
      </>}
      <p role="status" aria-live="polite" className="beta-notice">{notice}</p>
      <p className="beta-demo-note">Short synthetic practice only. Real-data backtest, payments and five-year coverage are not enabled. Reloading requires signing in again; saved work stays on the server.</p>
    </section>
  </main>;
}
