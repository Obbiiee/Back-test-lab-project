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

export default function BetaAccount(){
  const [client]=useState(()=>createBetaClient());
  const [user,setUser]=useState(null),[workspaces,setWorkspaces]=useState([]),[selected,setSelected]=useState(null);
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const [providers,setProviders]=useState(null),[expired,setExpired]=useState(false);
  const flight=useRef(false),live=useRef(true);
  useEffect(()=>{live.current=true;return()=>{live.current=false;client.clear();};},[client]);
  async function run(operation){
    if(flight.current)return;flight.current=true;setBusy(true);setNotice('');
    try{await operation();}catch(error){if(live.current){setNotice(betaNotice(error));if(!client.hasSession()){setExpired(error?.code==='SIGN_IN_REQUIRED');setUser(null);setSelected(null);setWorkspaces([]);}}}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  useEffect(()=>{
    let active=true;
    void Promise.resolve().then(async()=>{
      if(!active||location.protocol!=='https:')return;
      try{const value=await client.providers();if(active&&!client.hasSession())setProviders(value);}catch{if(active&&!client.hasSession())setProviders({googleConfigured:false});}
      if(!active||new URLSearchParams(location.search).get('auth')!=='google')return;
      // Consume the one-use cookie handoff once; never retain callback state in URLs.
      history.replaceState(null,'','/?page=beta');
      await run(async()=>{const me=await client.exchangeGoogle();const list=await client.workspaces();if(active){setUser(me);setWorkspaces(list);}});
    });
    return()=>{active=false;};
  // One verified identity client per mount; StrictMode's discarded setup is cancelled.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[client]);
  const secure=location.protocol==='https:';
  const signOut=()=>run(async()=>{try{await client.logout();}finally{if(live.current){setUser(null);setSelected(null);setWorkspaces([]);}}});
  const roleLabel=role=>role==='OWNER'?'Owner':'View only';
  return <main className={`alpha-identity beta-account${selected?' beta-account-workspace':''}`}>
    <header className="alpha-identity-nav beta-nav"><AlphaBrand href="/?page=home"/><span className="beta-nav-badge">Beta sandbox</span>
      {user?<div className="beta-userbar"><span>{user.email}</span><button disabled={busy} onClick={signOut}>Sign out</button></div>:<a href="/?page=account">Previous Sessions</a>}</header>
    <section className={`alpha-identity-content${selected?' alpha-identity-workspace':''}`}>
      {!secure?<div className="beta-card beta-card-center"><h1>Open the secure Beta address</h1><p>Verified account access requires HTTPS.</p></div>:!user?<BetaAuth client={client} providers={providers} expired={expired} onSignedIn={(me,list,configured)=>{setExpired(false);setNotice('');setUser(me);setWorkspaces(list);if(configured)setProviders(configured);}}/>:<>
        {selected?<><button className="beta-back" disabled={busy} onClick={()=>{client.selectWorkspace(selected.id);setSelected(null);}}>Back to workspaces</button>
          <Suspense fallback={<p role="status">Loading Beta workspace…</p>}><Workspace key={selected.id} client={client} workspace={selected} onExpired={()=>{client.clear();setExpired(true);setUser(null);setSelected(null);setWorkspaces([]);}}/></Suspense></>:<div className="beta-picker">
          {providers?.billingConfigured&&<BetaBilling key={user.id} client={client} onExpired={()=>{client.clear();setUser(null);setSelected(null);setWorkspaces([]);}}/>}
          <BetaSupport key={'support-'+user.id} client={client} onExpired={()=>{client.clear();setUser(null);setSelected(null);setWorkspaces([]);}}/>
          <h1>Where do you want to practise today?</h1><p>Beta Sessions are separate from your previous Sessions. Choose a workspace to practice.</p>
          <ul className="beta-workspace-list">{workspaces.map(ws=><li key={ws.id}><button disabled={busy} onClick={()=>{client.selectWorkspace(ws.id);setSelected(ws);}}>
            <span className="beta-ws-avatar" aria-hidden="true">{ws.name.trim().charAt(0).toUpperCase()||'W'}</span><strong>{ws.name}</strong><span className={`beta-role beta-role-${ws.role==='OWNER'?'owner':'viewer'}`}>{roleLabel(ws.role)}</span><span className="beta-open">Open</span></button></li>)}
            <li><form className="beta-ws-create" onSubmit={event=>{event.preventDefault();const name=new FormData(event.currentTarget).get('name');run(async()=>{
              await client.createWorkspace(name);const list=await client.workspaces();if(live.current)setWorkspaces(list);
            });}}><span className="beta-ws-plus" aria-hidden="true">+</span><label>Workspace name<input name="name" maxLength={128} required disabled={busy} placeholder="e.g. Gold scalping lab"/></label><button disabled={busy}>Create workspace</button></form></li></ul>
        </div>}
      </>}
      <p role="status" aria-live="polite" className="beta-notice">{notice}</p>
    </section>
  </main>;
}
