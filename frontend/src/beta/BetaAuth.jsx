import {useEffect,useId,useRef,useState} from 'react';
import {betaNotice} from './betaWorkspace.js';

// Signed-out account flows (design: Claude canvas "12 · Sign in" and "13 · Account flows").
// One card, one job. Copy never reveals whether an email has an account.
const MIN_PASSWORD=15;
const messages={
  LOGIN_BAD_CREDENTIALS:'That email and password don’t match. Try again or reset your password.',
  LOGIN_USER_NOT_VERIFIED:'Please verify your email first. We can send a new link.',
  VERIFIED_ACCOUNT_REQUIRED:'Please verify your email first. We can send a new link.',
  REGISTER_INVALID_PASSWORD:'Pick a longer password: at least 15 characters. A short sentence works great.',
  RESET_PASSWORD_INVALID_PASSWORD:'Pick a longer password: at least 15 characters. A short sentence works great.',
  VERIFY_USER_BAD_TOKEN:'That code didn’t work or has expired. Request a new one.',
  RESET_PASSWORD_BAD_TOKEN:'That reset code didn’t work or has expired. Request a new one.',
  SERVICE_BUSY:'Too many attempts. Wait a minute and try again.',
};
const explain=error=>messages[error?.code]??betaNotice(error);

function Password({label,autoComplete,busy,onLength}){
  const [shown,setShown]=useState(false),id=useId();
  return <div className="beta-field"><label htmlFor={id}>{label}</label><span className="beta-password">
    <input id={id} name="password" type={shown?'text':'password'} autoComplete={autoComplete} minLength={MIN_PASSWORD} maxLength={128} required disabled={busy}
      placeholder={`At least ${MIN_PASSWORD} characters`} onChange={onLength?event=>onLength(event.target.value.length):undefined}/>
    <button type="button" className="beta-password-toggle" aria-pressed={shown} aria-label={shown?'Hide password':'Show password'} onClick={()=>setShown(v=>!v)}>{shown?'Hide':'Show'}</button>
  </span></div>;
}
function Strength({length}){
  const left=Math.max(0,MIN_PASSWORD-length),bars=length===0?0:left>0?1:length>=24?3:2;
  return <div className="beta-strength" aria-live="polite">
    <span aria-hidden="true">{[1,2,3].map(n=><i key={n} className={n<=bars?'on':''}/>)}</span>
    <small className={left>0&&length>0?'beta-strength-short':''}>{length===0?`${MIN_PASSWORD}+ characters · a short sentence works great`:left>0?`${left} more character${left===1?'':'s'} to go (${MIN_PASSWORD} minimum)`:'✓ Long enough'}</small>
  </div>;
}

export default function BetaAuth({client,providers,expired,onSignedIn}){
  // Email links may carry the one-use code in the fragment (never sent to servers or logs); consume once.
  const [link]=useState(()=>{
    const hash=new URLSearchParams(location.hash.slice(1)),found={verify:hash.get('verify'),reset:hash.get('reset')};
    return found;
  });
  const [view,setView]=useState(link.reset?'reset':'signin'),[email,setEmail]=useState(''),[resetToken,setResetToken]=useState(link.reset??'');
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[length,setLength]=useState(0),[cooldown,setCooldown]=useState(0);
  const flight=useRef(false),live=useRef(true);
  useEffect(()=>{live.current=true;return()=>{live.current=false;};},[]);
  useEffect(()=>{if(cooldown<=0)return;const t=setTimeout(()=>setCooldown(c=>c-1),1000);return()=>clearTimeout(t);},[cooldown]);
  async function run(operation){
    if(flight.current)return;flight.current=true;setBusy(true);setNotice('');
    try{await operation();}catch(error){if(live.current)setNotice(explain(error));}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  const go=next=>{setView(next);setNotice('');setLength(0);};
  useEffect(()=>{
    let active=true;
    if(link.verify||link.reset)history.replaceState(null,'',location.pathname+location.search);
    if(link.verify)void Promise.resolve().then(()=>{if(active)return run(async()=>{await client.verify(link.verify);if(active&&live.current)setView('verified');});});
    return()=>{active=false;};
  // Runs once per mount; the client and link are stable for the page.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[]);
  const resend=()=>run(async()=>{await client.requestVerification(email);if(live.current)setCooldown(60);});
  const tabs=<div className="beta-tabs-auth" role="tablist" aria-label="Account">
    <button type="button" role="tab" disabled={busy} aria-selected={view==='signin'} onClick={()=>go('signin')}>Sign in</button>
    <button type="button" role="tab" disabled={busy} aria-selected={view==='register'} onClick={()=>go('register')}>Create account</button></div>;
  const status=<p role="status" aria-live="polite" className="beta-notice">{notice}</p>;
  const emailField=<label>Email<input name="email" type="email" autoComplete="email" maxLength={320} required disabled={busy} defaultValue={email} placeholder="you@example.com"/></label>;
  let card;
  if(view==='signin')card=<>{tabs}
    {expired&&<div className="beta-info"><strong>Signed out for safety</strong><span>Your sign-in ended after a refresh or a while away. Your Sessions are saved.</span></div>}
    <h1>Sign in to Beta</h1>
    {providers?.googleConfigured?<><a className="beta-google" href={client.googleStart()}><span aria-hidden="true">G</span>Continue with Google</a><p className="beta-divider"><span>or with email</span></p></>:<p className="beta-muted">Google sign-in turns on once it is set up.</p>}
    <form onSubmit={event=>{event.preventDefault();const f=new FormData(event.currentTarget);const address=String(f.get('email'));setEmail(address);run(async()=>{
      try{const me=await client.login(address,f.get('password'));const [list,configured]=await Promise.all([client.workspaces(),client.providers()]);if(live.current)onSignedIn(me,list,configured);}
      catch(error){if(['LOGIN_USER_NOT_VERIFIED','VERIFIED_ACCOUNT_REQUIRED'].includes(error.code)&&live.current){setView('check');}throw error;}
    });}}>{emailField}
      <div className="beta-field-head"><span/><button type="button" className="beta-link" disabled={busy} onClick={()=>go('forgot')}>Forgot password?</button></div>
      <Password label="Password" autoComplete="current-password" busy={busy}/>
      {status}
      <button className="beta-primary" disabled={busy}>{busy?'Signing in…':'Sign in'}</button>
    </form>
    <p className="beta-muted">For your safety you sign in again after closing or refreshing the tab.</p></>;
  else if(view==='register')card=<>{tabs}
    <h1>Start practising free</h1>
    <form onSubmit={event=>{event.preventDefault();const f=new FormData(event.currentTarget);const address=String(f.get('email'));setEmail(address);run(async()=>{
      try{await client.register(address,f.get('password'));}catch(error){if(error.code!=='REGISTER_USER_ALREADY_EXISTS')throw error;}
      if(live.current){setView('check');setCooldown(60);}
    });}}>{emailField}
      <Password label="Password" autoComplete="new-password" busy={busy} onLength={setLength}/>
      <Strength length={length}/>
      {status}
      <button className="beta-primary" disabled={busy||length<MIN_PASSWORD}>{busy?'Creating…':'Create account'}</button>
    </form>
    <p className="beta-muted">Free includes 5 saved Sessions and one replay window a day. No card needed.</p></>;
  else if(view==='check')card=<div className="beta-center">
    <div className="beta-envelope" aria-hidden="true"><span/><span/><span/></div>
    <h1>Check your inbox</h1>
    <p>If <b>{email||'your email'}</b> can sign up, a verification code is on its way. Enter it below to finish.</p>
    <form onSubmit={event=>{event.preventDefault();const code=String(new FormData(event.currentTarget).get('token')).trim();run(async()=>{await client.verify(code);if(live.current)setView('verified');});}}>
      <label>Verification code<input name="token" autoComplete="one-time-code" maxLength={4096} required disabled={busy}/></label>
      {status}
      <button className="beta-primary" disabled={busy}>{busy?'Checking…':'Verify email'}</button>
    </form>
    <button type="button" className="beta-secondary" disabled={busy||cooldown>0||!email} onClick={resend}>{cooldown>0?`Resend in 0:${String(cooldown).padStart(2,'0')}`:'Resend code'}</button>
    <button type="button" className="beta-link" disabled={busy} onClick={()=>go('register')}>Use a different email</button></div>;
  else if(view==='verified')card=<div className="beta-center beta-celebrate">
    <span className="beta-check" aria-hidden="true"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5 9-10"/></svg></span>
    <h1>You’re in!</h1>
    <p>Your Free account is ready: 5 saved Sessions and one replay window a day.</p>
    <button type="button" className="beta-primary beta-dark" onClick={()=>go('signin')}>Sign in to start</button></div>;
  else if(view==='forgot')card=<>
    <h1>Happens to everyone</h1>
    <p>Enter your email and we’ll send a reset code if the account exists.</p>
    <form onSubmit={event=>{event.preventDefault();const address=String(new FormData(event.currentTarget).get('email'));setEmail(address);run(async()=>{await client.forgotPassword(address);if(live.current){setView('forgotSent');setCooldown(60);}});}}>
      {emailField}{status}<button className="beta-primary" disabled={busy}>{busy?'Sending…':'Send reset code'}</button></form>
    <button type="button" className="beta-link" disabled={busy} onClick={()=>go('signin')}>Back to sign in</button></>;
  else if(view==='forgotSent'||view==='reset')card=<>
    <h1>Pick a new password</h1>
    <p>{view==='reset'?'Opened from your email link.':<>If <b>{email}</b> has an account, a reset code is on its way. Enter it with your new password.</>}</p>
    <form onSubmit={event=>{event.preventDefault();const f=new FormData(event.currentTarget);const code=view==='reset'?resetToken:String(f.get('token')).trim();run(async()=>{await client.resetPassword(code,f.get('password'));if(live.current){setResetToken('');setView('resetDone');}});}}>
      {view!=='reset'&&<label>Reset code<input name="token" autoComplete="one-time-code" maxLength={4096} required disabled={busy}/></label>}
      <Password label="New password" autoComplete="new-password" busy={busy} onLength={setLength}/>
      <Strength length={length}/>{status}
      <button className="beta-primary" disabled={busy||length<MIN_PASSWORD}>{busy?'Saving…':'Save password'}</button></form>
    <button type="button" className="beta-link" disabled={busy||cooldown>0||!email} onClick={()=>run(async()=>{await client.forgotPassword(email);if(live.current)setCooldown(60);})}>{cooldown>0?`New code in 0:${String(cooldown).padStart(2,'0')}`:'Send a new code'}</button></>;
  else card=<div className="beta-center beta-celebrate">
    <span className="beta-check" aria-hidden="true"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 12l5 5 9-10"/></svg></span>
    <h1>Password saved</h1><p>Sign in with your new password.</p>
    <button type="button" className="beta-primary beta-dark" onClick={()=>go('signin')}>Sign in</button></div>;

  return <div className="beta-auth">
    <div className="beta-auth-hero" aria-hidden="true">
      <p className="beta-auth-title">{view==='register'?<>Start practising, <span>one Session</span> at a time.</>:<>Welcome back, <span>trader.</span></>}</p>
      <p>{view==='register'?'Practise with clearly labelled data, review your orders, and learn from every saved Session.':'Your Sessions, journal and replay position are waiting where you left them.'}</p>
      <ul><li>Practice data is labelled before you start</li><li>Free plan · trade from day one</li></ul></div>
    <div key={view} className={`beta-card beta-auth-card${['verified','resetDone'].includes(view)?' beta-card-yellow':''}`}>{card}</div>
  </div>;
}
