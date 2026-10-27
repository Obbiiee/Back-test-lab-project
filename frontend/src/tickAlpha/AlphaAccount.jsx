import {lazy,Suspense,useEffect,useRef,useState} from 'react';
import {createAccountClient,setAccountTransport,clearAccountTransport} from './accountClient.js';
import './tickAlpha.css';
import AlphaBrand from './AlphaBrand.jsx';
const Workspace=lazy(()=>import('./TickAlpha.jsx'));
const modes={login:'Sign in',register:'Create account',verify:'Verify email',resend:'Request verification',forgot:'Request recovery',reset:'Reset password'};

export default function AlphaAccount(){
  const [client]=useState(()=>createAccountClient());
  const [mode,setMode]=useState('login'),[user,setUser]=useState(null),[workspaces,setWorkspaces]=useState([]);
  const [selected,setSelected]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const flight=useRef(false),live=useRef(true);
  useEffect(()=>{live.current=true;return()=>{live.current=false;clearAccountTransport();client.clear();};},[client]);
  async function action(operation){
    if(flight.current)return;
    flight.current=true;setBusy(true);setNotice('');
    try{await operation();}catch(error){if(live.current){setNotice(error.message);if(!client.hasSession()){clearAccountTransport();setSelected(null);setUser(null);setWorkspaces([]);}}}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  async function submit(event){
    event.preventDefault();const form=event.currentTarget,data=new FormData(form);
    const email=data.get('email'),password=data.get('password'),token=data.get('token');
    form.reset();
    await action(async()=>{
      if(mode==='login'){
        const me=await client.login(email,password);
        const list=await client.request('/api/v1/workspaces');
        if(live.current){setUser(me);setWorkspaces(list);}
      }else{
        const routes={register:['register',{email,password}],verify:['verify',{token}],resend:['request-verify-token',{email}],forgot:['forgot-password',{email}],reset:['reset-password',{token,password}]};
        const [route,body]=routes[mode];
        await client.request('/api/v1/auth/'+route,{method:'POST',body,authenticated:false});
        if(live.current)setNotice(mode==='register'||mode==='resend'?'If eligible, verification instructions are sent to your email.':mode==='forgot'?'If eligible, recovery instructions are sent to your email.':'Request accepted. Sign in after completing verification or recovery.');
      }
    });
  }
  async function logout(all){await action(async()=>{try{await client.logout(all);}finally{clearAccountTransport();if(live.current){setUser(null);setSelected(null);setWorkspaces([]);}}});}
  function open(workspace){
    clearAccountTransport();setAccountTransport(client,workspace.id);
    const url=new URL(window.location.href);url.searchParams.delete('session');
    window.history.replaceState(null,'',url);setSelected(workspace);
  }
  const secure=window.location.protocol==='https:';
  return <main className="alpha-identity">
    <header className="alpha-identity-nav"><AlphaBrand href="?page=account"/><span>{user?'Verified account':'Account access'}</span></header>
    <section className={`alpha-identity-content${selected?' alpha-identity-workspace':''}`}><p className="alpha-eyebrow">RESEARCH / PRIVATE WORKSPACES</p>
      {!secure?<><h1>Account access requires HTTPS.</h1><p>Open the configured secure application address to sign in. The private local data service is separate.</p><a href="/">Open local workspace</a></>:!user?<>
        <h1>{modes[mode]}</h1><p>Use your verified account to access authorized workspaces. Tokens stay in memory; refreshing requires signing in again.</p>
        <form key={mode} onSubmit={submit}>
          {!['verify','reset'].includes(mode)&&<label>Email<input name="email" type="email" autoComplete="email" maxLength={320} required disabled={busy}/></label>}
          {['login','register','reset'].includes(mode)&&<label>Password<input name="password" type="password" autoComplete={mode==='login'?'current-password':'new-password'} minLength={15} maxLength={128} required disabled={busy}/></label>}
          {['verify','reset'].includes(mode)&&<label>{mode==='verify'?'Verification':'Recovery'} token<input name="token" type="password" autoComplete="off" maxLength={4096} required disabled={busy}/></label>}
          <button type="submit" disabled={busy}>{busy?'Working…':modes[mode]}</button>
        </form><nav aria-label="Account actions">{Object.entries(modes).filter(([key])=>key!==mode).map(([key,label])=><button key={key} disabled={busy} onClick={()=>{setMode(key);setNotice('');}}>{label}</button>)}</nav>
      </>:<>
        <div className="alpha-identity-actions"><span>{user.email}</span><button disabled={busy} onClick={()=>logout(false)}>Sign out</button><button disabled={busy} onClick={()=>logout(true)}>Sign out all sessions</button></div>
        {selected?<><button disabled={busy} onClick={()=>{clearAccountTransport();setSelected(null);}}>Back to workspaces</button><p>{selected.name} · {selected.role==='OWNER'?'Owner':'Read access; owner required for changes'}</p><Suspense fallback={<p>Loading workspace…</p>}><Workspace key={selected.id}/></Suspense></>:<>
          <h1>Your workspaces</h1><p>Available research sources are configured by the operator for each workspace. Source identity and limitations appear in the workspace. This list shows at most 50 authorized workspaces.</p>
          <ul>{workspaces.map(workspace=><li key={workspace.id}><button disabled={busy} onClick={()=>open(workspace)}>{workspace.name} · {workspace.role}</button></li>)}</ul>
          <form onSubmit={event=>{event.preventDefault();const name=new FormData(event.currentTarget).get('name');event.currentTarget.reset();action(async()=>{await client.request('/api/v1/workspaces',{method:'POST',body:{name}});const list=await client.request('/api/v1/workspaces');if(live.current)setWorkspaces(list);});}}><label>Workspace name<input name="name" maxLength={128} required disabled={busy}/></label><button disabled={busy}>Create workspace</button></form>
        </>}
      </>}
      <p role="status" aria-live="polite">{notice}</p>
    </section>
  </main>;
}
