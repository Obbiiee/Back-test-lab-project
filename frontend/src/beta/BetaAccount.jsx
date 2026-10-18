import {lazy,Suspense,useEffect,useRef,useState} from 'react';
import {createBetaClient} from './betaClient.js';
import {betaNotice} from './betaWorkspace.js';
import AlphaBrand from '../tickAlpha/AlphaBrand.jsx';
import '../tickAlpha/tickAlpha.css';
import './beta.css';
const Workspace=lazy(()=>import('./BetaWorkspace.jsx'));

export default function BetaAccount(){
  const [client]=useState(()=>createBetaClient());
  const [user,setUser]=useState(null),[workspaces,setWorkspaces]=useState([]),[selected,setSelected]=useState(null);
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const flight=useRef(false),live=useRef(true);
  useEffect(()=>{live.current=true;return()=>{live.current=false;client.clear();};},[client]);
  async function run(operation){
    if(flight.current)return;flight.current=true;setBusy(true);setNotice('');
    try{await operation();}catch(error){if(live.current){setNotice(betaNotice(error));if(!client.hasSession()){setUser(null);setSelected(null);setWorkspaces([]);}}}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  const secure=location.protocol==='https:';
  return <main className="alpha-identity beta-account">
    <header className="alpha-identity-nav"><AlphaBrand href="/?page=home"/><span>Beta sandbox</span><a href="/?page=account">Previous Sessions</a></header>
    <section className={`alpha-identity-content${selected?' alpha-identity-workspace':''}`}>
      {!secure?<><h1>Open the secure Beta address</h1><p>Verified account access requires HTTPS.</p></>:!user?<>
        <p className="alpha-eyebrow">16 PAIRS · SYNTHETIC PRACTICE</p><h1>Sign in to Beta</h1>
        <p>Free includes trading. This sandbox uses short synthetic demos; no real payment or historical month is included.</p>
        <form onSubmit={event=>{event.preventDefault();const fields=new FormData(event.currentTarget);event.currentTarget.reset();run(async()=>{
          const me=await client.login(fields.get('email'),fields.get('password'));const list=await client.workspaces();
          if(live.current){setUser(me);setWorkspaces(list);}
        });}}><label>Email<input name="email" type="email" autoComplete="email" maxLength={320} required disabled={busy}/></label>
          <label>Password<input name="password" type="password" autoComplete="current-password" minLength={15} maxLength={128} required disabled={busy}/></label>
          <button disabled={busy}>{busy?'Signing in…':'Sign in'}</button>
        </form><p><a href="/?page=account">Create or verify an account, or recover access</a></p>
      </>:<>
        <div className="alpha-identity-actions"><span>{user.email}</span><button disabled={busy} onClick={()=>run(async()=>{
          try{await client.logout();}finally{if(live.current){setUser(null);setSelected(null);setWorkspaces([]);}}
        })}>Sign out</button></div>
        {selected?<><button disabled={busy} onClick={()=>{client.selectWorkspace(selected.id);setSelected(null);}}>Back to workspaces</button>
          <Suspense fallback={<p role="status">Loading Beta workspace…</p>}><Workspace key={selected.id} client={client} workspace={selected} onExpired={()=>{client.clear();setUser(null);setSelected(null);setWorkspaces([]);}}/></Suspense></>:<>
          <h1>Your workspaces</h1><p>Beta Sessions are separate from your previous Sessions. Choose a workspace to practice.</p>
          <ul className="beta-workspace-list">{workspaces.map(ws=><li key={ws.id}><button disabled={busy} onClick={()=>{client.selectWorkspace(ws.id);setSelected(ws);}}>{ws.name} · {ws.role}</button></li>)}</ul>
          <form onSubmit={event=>{event.preventDefault();const name=new FormData(event.currentTarget).get('name');run(async()=>{
            await client.createWorkspace(name);const list=await client.workspaces();if(live.current)setWorkspaces(list);
          });}}><label>Workspace name<input name="name" maxLength={128} required disabled={busy}/></label><button disabled={busy}>Create workspace</button></form>
        </>}
      </>}
      <p role="status" aria-live="polite">{notice}</p>
    </section>
  </main>;
}
