import {lazy,Suspense,useEffect,useId,useRef,useState} from 'react';
import {createAccountClient,setAccountTransport,clearAccountTransport} from './accountClient.js';
import {readRoute,useRoute,navigate} from './productRoute.js';
import './tickAlpha.css';
import './alphaProduct.css';
import {RiksoraMark} from './AlphaBrand.jsx';
const Workspace=lazy(()=>import('./TickAlpha.jsx'));

// U02 account access (canvas AuthSignIn / AuthStates): one card per job instead of the
// old six-button switcher. Same /api/v1/auth routes; the bearer token stays in memory,
// so a refresh or a 401 signs the person out on purpose ("Signed out for safety").
const TITLES={signin:'Sign in',register:'Create account',verify:'Check your inbox',forgot:'Reset your password',reset:'Pick a new password'};
const MIN_PASSWORD=15;

function PasswordField({label,autoComplete,busy,value,onChange,invalid}){
  const [shown,setShown]=useState(false);
  const fieldId=useId();
  return <div className="rk-auth-field"><label htmlFor={fieldId}>{label}</label>
    <span className="rk-auth-password"><input id={fieldId} name="password" type={shown?'text':'password'} autoComplete={autoComplete} minLength={MIN_PASSWORD} maxLength={128} required disabled={busy}
      value={value} onChange={onChange} aria-invalid={invalid||undefined} placeholder={`At least ${MIN_PASSWORD} characters`}/>
      <button type="button" onClick={()=>setShown(v=>!v)} aria-pressed={shown} aria-label={shown?'Hide password':'Show password'} disabled={busy}>{shown?'Hide':'Show'}</button></span>
  </div>;
}

export default function AlphaAccount(){
  const [expired,setExpired]=useState(false);
  const [client]=useState(()=>createAccountClient({onExpired:()=>setExpired(true)}));
  const [mode,setMode]=useState('signin'),[user,setUser]=useState(null),[workspaces,setWorkspaces]=useState([]),[capabilities,setCapabilities]=useState(null),[identityProviders,setIdentityProviders]=useState([]);
  const [selected,setSelected]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[error,setError]=useState(''),[googleAvailable,setGoogleAvailable]=useState(false);
  const [email,setEmail]=useState(''),[password,setPassword]=useState('');
  const route=useRoute();
  // Deep link asked for before sign-in (e.g. a Session or Method); restored after a workspace is chosen.
  const intended=useRef(readRoute());
  const flight=useRef(false),live=useRef(true);
  useEffect(()=>{live.current=true;return()=>{live.current=false;clearAccountTransport();client.clear();};},[client]);
  // A 401 anywhere (account or research calls) drops back to sign-in with the safety card.
  const [seenExpired,setSeenExpired]=useState(false);
  if(expired&&!seenExpired){setSeenExpired(true);setUser(null);setSelected(null);setWorkspaces([]);setCapabilities(null);setMode('signin');}
  useEffect(()=>{if(expired)clearAccountTransport();},[expired]);

  async function action(operation){
    if(flight.current)return;
    flight.current=true;setBusy(true);setNotice('');setError('');
    try{await operation();}catch(failure){if(live.current){setError(failure.message);if(!client.hasSession()){clearAccountTransport();setSelected(null);setUser(null);setWorkspaces([]);}}}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  useEffect(()=>{
    if(window.location.protocol!=='https:')return;
    let active=true;
    const url=new URL(window.location.href),flow=url.searchParams.get('auth');
    async function load(){
      try{
        if(flow==='google'){
          const me=await client.completeGoogleLogin();
          const [list,providers]=await Promise.all([client.request('/api/v1/workspaces'),client.identityProviders()]);
          if(active){setGoogleAvailable(true);setUser(me);setWorkspaces(list);setIdentityProviders(providers);setNotice('Signed in with Google. Choose a workspace to continue.');}
          url.searchParams.delete('auth');url.searchParams.set('page','account');window.history.replaceState(null,'',url.pathname+url.search);
        }else if(flow==='google-linked'){
          const result=await client.completeGoogleLink();
          if(active){setGoogleAvailable(true);setNotice(result.userId?'Google is linked. Sign in with Google to continue.':'Google linking completed.');}
          url.searchParams.delete('auth');url.searchParams.set('page','account');window.history.replaceState(null,'',url.pathname+url.search);
        }else{
          const providers=await client.request('/api/v1/auth/providers',{authenticated:false});
          if(active)setGoogleAvailable(providers?.googleConfigured===true);
        }
      }catch(failure){
        if(active){
          // A consumed one-time handoff cannot be retried from a stale URL.
          // Drop any partially established in-memory bearer and let the user restart.
          if(flow==='google'||flow==='google-linked'){
            client.clear();clearAccountTransport();setUser(null);setSelected(null);setWorkspaces([]);setIdentityProviders([]);
            url.searchParams.delete('auth');url.searchParams.set('page','account');window.history.replaceState(null,'',url.pathname+url.search);
          }
          setError(failure.message);setNotice('');
        }
      }
    }
    void load();return()=>{active=false;};
  },[client]);
  function switchMode(next){setMode(next);setNotice('');setError('');setPassword('');}
  async function submit(event){
    event.preventDefault();
    const data=new FormData(event.currentTarget),token=data.get('token');
    const sentEmail=email.trim(),sentPassword=password;
    setPassword('');
    await action(async()=>{
      if(mode==='signin'){
        const me=await client.login(sentEmail,sentPassword);
        const [list,providers]=await Promise.all([client.request('/api/v1/workspaces'),client.identityProviders()]);
        if(live.current){setExpired(false);setSeenExpired(false);setUser(me);setWorkspaces(list);setIdentityProviders(providers);}
        return;
      }
      const routes={register:['register',{email:sentEmail,password:sentPassword}],verify:['verify',{token}],forgot:['forgot-password',{email:sentEmail}],reset:['reset-password',{token,password:sentPassword}]};
      const [path,body]=routes[mode];
      await client.request('/api/v1/auth/'+path,{method:'POST',body,authenticated:false});
      if(!live.current)return;
      if(mode==='register'){setMode('verify');setNotice('If this email can sign up, a verification code is on its way.');}
      else if(mode==='forgot'){setMode('reset');setNotice('If an account exists, a reset code is on its way.');}
      else{setMode('signin');setNotice(mode==='verify'?'Email verified. Sign in to start.':'Password saved. Sign in with the new password.');}
    });
  }
  async function resend(){await action(async()=>{await client.request('/api/v1/auth/request-verify-token',{method:'POST',body:{email:email.trim()},authenticated:false});if(live.current)setNotice('If eligible, a new code is on its way.');});}
  async function logout(all){
    await action(async()=>{
      try{
        await client.logout(all);
        if(live.current)setNotice(all?'Signed out on every device.':'Signed out.');
      }catch{
        if(live.current)setError('Signed out of this tab. The server did not confirm session revocation.');
      }finally{
        clearAccountTransport();
        if(live.current){
          setUser(null);setSelected(null);setWorkspaces([]);setCapabilities(null);setMode('signin');
        }
      }
    });
  }
  function open(workspace){
    void action(async()=>{
      const status=await client.request(`/api/v1/workspaces/${workspace.id}/capabilities`);
      clearAccountTransport();setAccountTransport(client,workspace.id);
      setCapabilities(status);setSelected(workspace);
      const target=intended.current;intended.current=null;
      navigate(target&&target.screen!=='account'?target:{screen:'methods'},{replace:true});
    });
  }
  const secure=window.location.protocol==='https:';

  if(user&&selected&&route.screen!=='account')return <Suspense fallback={<main className="rk-auth"><p className="rk-auth-loading">Loading workspace…</p></main>}><Workspace key={selected.id}/></Suspense>;

  const passwordShort=password.length>0&&password.length<MIN_PASSWORD;
  return <main className="rk-auth">
    <section className="rk-auth-hero">
      <a className="rk-auth-brand" href="/" aria-label="RIKSORA home"><RiksoraMark size={40}/><span>RIKSORA</span></a>
      <div><h1>{user?<>Your research,<br/><span>your rules.</span></>:<>Welcome back,<br/><span>trader.</span></>}</h1>
        <p>Your Methods, Sessions, journal and replay position stay saved on the server between visits.</p></div>
      <p className="rk-auth-small">Research tool. Results describe past data and are not a promise of future profit.</p>
    </section>
    <section className="rk-auth-panel">
      <div className="rk-auth-card" aria-live="polite">
        {!secure?<><h2>Use the secure address</h2><p>Accounts only work on the https:// address. The private local workspace is separate.</p><a className="rk-auth-btn rk-auth-primary" href="/">Open local workspace</a></>
        :user?<AccountPanel user={user} identityProviders={identityProviders} workspaces={workspaces} selected={selected} capabilities={capabilities} busy={busy} googleAvailable={googleAvailable} onLinkGoogle={password=>action(async()=>{const url=await client.startGoogleLink(password);window.location.assign(url);})} onOpen={open} onLogout={logout} onCreate={name=>action(async()=>{await client.request('/api/v1/workspaces',{method:'POST',body:{name}});const list=await client.request('/api/v1/workspaces');if(live.current)setWorkspaces(list);})} onBack={()=>navigate({screen:'methods'})}/>
        :<>
          {expired&&<div className="rk-auth-safety" role="status"><strong>Signed out for safety</strong><span>Your sign-in ended after a refresh or a while away. Your Sessions are saved.</span></div>}
          {['signin','register'].includes(mode)&&<div className="rk-auth-tabs" role="tablist" aria-label="Account">
            {[['signin','Sign in'],['register','Create account']].map(([key,text])=><button key={key} type="button" role="tab" aria-selected={mode===key} disabled={busy} onClick={()=>switchMode(key)}>{text}</button>)}
          </div>}
          {['verify','forgot','reset'].includes(mode)&&<h2>{TITLES[mode]}</h2>}
          {['signin','register'].includes(mode)&&<><button type="button" className="rk-auth-btn rk-auth-google" disabled={!googleAvailable||busy} aria-describedby="rk-google-note" onClick={()=>{window.location.assign('/api/v1/auth/google/start');}}><span aria-hidden="true">G</span>Continue with Google</button>
            <p id="rk-google-note" className="rk-auth-hint">{googleAvailable?'Use the Google account linked to your RIKSORA account.':'Google sign-in is not configured yet.'}</p>
            <div className="rk-auth-or" aria-hidden="true"><span/>or with email<span/></div></>}
          {mode==='verify'&&<p className="rk-auth-hint">Open the link in the email, or paste the code from it below.</p>}
          {mode==='forgot'&&<p className="rk-auth-hint">Enter your email. If the account exists, we send a reset code.</p>}
          <form key={mode} onSubmit={submit} className="rk-auth-form" noValidate={false}>
            {['signin','register','forgot'].includes(mode)&&<label className="rk-auth-field">Email<input name="email" type="email" autoComplete="email" maxLength={320} required disabled={busy} value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@example.com"/></label>}
            {['verify','reset'].includes(mode)&&<label className="rk-auth-field">{mode==='verify'?'Verification code':'Reset code'}<input name="token" type="password" autoComplete="one-time-code" maxLength={4096} required disabled={busy}/></label>}
            {['signin','register','reset'].includes(mode)&&<>
              {mode==='signin'&&<button type="button" className="rk-auth-link rk-auth-forgot" disabled={busy} onClick={()=>switchMode('forgot')}>Forgot password?</button>}
              <PasswordField label={mode==='reset'?'New password':'Password'} autoComplete={mode==='signin'?'current-password':'new-password'} busy={busy} value={password} onChange={e=>setPassword(e.target.value)} invalid={mode!=='signin'&&passwordShort}/>
              {mode!=='signin'&&<p className={`rk-auth-hint${passwordShort?' rk-auth-warn':''}`}>{passwordShort?`${MIN_PASSWORD-password.length} more characters to go (${MIN_PASSWORD} minimum).`:`${MIN_PASSWORD}+ characters. A short sentence works well.`}</p>}
            </>}
            {error&&<p className="rk-auth-error" role="alert">{error}</p>}
            {notice&&<p className="rk-auth-notice" role="status">{notice}</p>}
            <button type="submit" className="rk-auth-btn rk-auth-primary" disabled={busy}>{busy?'Working…':mode==='signin'?'Sign in':mode==='register'?'Create account':mode==='verify'?'Verify email':mode==='forgot'?'Send reset code':'Save password'}</button>
          </form>
          {mode==='verify'&&<button type="button" className="rk-auth-btn" disabled={busy||!email.trim()} onClick={resend}>Resend code</button>}
          {mode==='signin'&&<button type="button" className="rk-auth-link" disabled={busy} onClick={()=>switchMode('verify')}>Have a verification code?</button>}
          {['verify','forgot','reset'].includes(mode)&&<button type="button" className="rk-auth-link" disabled={busy} onClick={()=>switchMode('signin')}>Back to sign in</button>}
          <p className="rk-auth-small rk-auth-foot">For your safety you sign in again after closing or refreshing the tab.</p>
        </>}
      </div>
    </section>
  </main>;
}

function AccountPanel({user,identityProviders,workspaces,selected,capabilities,busy,googleAvailable,onLinkGoogle,onOpen,onLogout,onCreate,onBack}){
  const [linkPassword,setLinkPassword]=useState('');
  return <>
    <h2>{selected?'Account':'Choose a workspace'}</h2>
    <dl className="rk-auth-facts"><div><dt>Signed in as</dt><dd>{user.email}</dd></div><div><dt>Email</dt><dd>Verified</dd></div>{selected&&<div><dt>Workspace</dt><dd>{selected.name} · {selected.role==='OWNER'?'Owner':'Read access'}</dd></div>}<div><dt>Sign-in methods</dt><dd>{identityProviders.includes('EMAIL_PASSWORD')?'Email and password':''}{identityProviders.includes('EMAIL_PASSWORD')&&identityProviders.includes('GOOGLE')?' · ':''}{identityProviders.includes('GOOGLE')?'Google':''}</dd></div><div><dt>Plan</dt><dd>{capabilities?.entitlement?.status==='SANDBOX_ONLY'?'Sandbox entitlement only; no production access or funds collected.':'Not configured. No production plan or payment is available.'}</dd></div></dl>
    {googleAvailable&&identityProviders.includes('EMAIL_PASSWORD')&&!identityProviders.includes('GOOGLE')&&<form className="rk-auth-form rk-auth-inline" onSubmit={event=>{event.preventDefault();const password=linkPassword;setLinkPassword('');onLinkGoogle(password);}}>
      <label className="rk-auth-field">Confirm your password to link Google<input type="password" autoComplete="current-password" minLength={1} maxLength={128} required disabled={busy} value={linkPassword} onChange={event=>setLinkPassword(event.target.value)}/></label>
      <button className="rk-auth-btn" disabled={busy}>{busy?'Connecting…':'Link Google account'}</button>
      <p className="rk-auth-hint">Google is linked only after you confirm your password and finish Google sign-in. Matching email addresses alone never combine accounts.</p>
    </form>}
    {selected&&<button type="button" className="rk-auth-btn rk-auth-primary" onClick={onBack}>Back to My Methods</button>}
    <h3>{selected?'Switch workspace':'Your workspaces'}</h3>
    <p className="rk-auth-hint">Workspaces keep research separate. At most 50 are listed. Research here uses the synthetic test feed.</p>
    {workspaces.length?<ul className="rk-auth-list">{workspaces.map(w=><li key={w.id}><button type="button" className="rk-auth-btn" disabled={busy} aria-current={selected?.id===w.id||undefined} onClick={()=>onOpen(w)}><span>{w.name}</span><small>{w.role==='OWNER'?'Owner':'Read access'}</small></button></li>)}</ul>:<p className="rk-auth-hint">No workspace yet. Create one to start.</p>}
    <form className="rk-auth-form rk-auth-inline" onSubmit={event=>{event.preventDefault();const name=new FormData(event.currentTarget).get('name');event.currentTarget.reset();onCreate(name);}}>
      <label className="rk-auth-field">New workspace name<input name="name" maxLength={128} required disabled={busy}/></label><button className="rk-auth-btn" disabled={busy}>Create workspace</button>
    </form>
    <div className="rk-auth-row"><button type="button" className="rk-auth-btn" disabled={busy} onClick={()=>onLogout(false)}>Sign out</button><button type="button" className="rk-auth-btn" disabled={busy} onClick={()=>onLogout(true)}>Sign out on all devices</button></div>
  </>;
}
