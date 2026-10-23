import {useEffect,useRef,useState} from 'react';
import {betaNotice} from './betaWorkspace.js';
// Server timestamps carry an offset; show them in UTC to the minute.
const utcMinute=value=>{const date=new Date(value);return Number.isFinite(date.getTime())?date.toISOString().slice(0,16).replace('T',' ')+' UTC':value;};
export default function BetaSupport({client,onExpired}){
  const [data,setData]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
  const [title,setTitle]=useState(''),[message,setMessage]=useState(''),[pending,setPending]=useState(null),[uncertain,setUncertain]=useState(false);
  const live=useRef(true),flight=useRef(false);
  async function reload(){
    const value=await client.supportList();
    if(value?.schemaVersion!==1||!Array.isArray(value.items))throw Error('Unsupported support response');
    if(live.current)setData(value);return value;
  }
  async function run(fn){
    if(flight.current)return;flight.current=true;setBusy(true);setNotice('');
    try{await fn();}catch(error){if(live.current){setNotice(error.reconciliationRequired?'Response interrupted. Reload saved requests before retrying this same request.':error.code==='SUPPORT_LIMIT'?'You can send up to 10 support requests in 24 hours. Please wait before sending another.':betaNotice(error));if(error.reconciliationRequired)setUncertain(true);else setPending(null);if(!client.hasSession())onExpired();}}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  useEffect(()=>{live.current=true;let active=true;void Promise.resolve().then(()=>{if(active)return run(reload);});return()=>{active=false;live.current=false;};
  // This component remounts with the verified account.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[client]);
  function clearSaved(){if(live.current){setPending(null);setTitle('');setMessage('');setUncertain(false);}}
  return <section aria-label="Customer support" className="beta-support"><div className="beta-support-form"><h2 className="beta-visually-hidden">New request</h2>
    <form onSubmit={event=>{event.preventDefault();run(async()=>{
      if(!title.trim()||!message.trim()){setNotice('Enter a subject and describe the problem.');return;}
      const request=pending??{requestId:crypto.randomUUID(),title:title.trim(),message:message.trim()};setPending(request);
      await client.supportSubmit(request);clearSaved();
      try{await reload();}catch{if(live.current){setNotice('Request saved. Reload saved requests to refresh the list; do not send it again.');if(!client.hasSession())onExpired();}return;}
      if(live.current)setNotice('Request saved. Staff delivery may be pending until the next synchronization.');
    });}}><label>Subject<input name="supportTitle" value={title} onChange={e=>setTitle(e.target.value)} maxLength={160} required disabled={busy||!!pending}/></label>
      <label>Question or problem<textarea name="supportMessage" value={message} onChange={e=>setMessage(e.target.value)} maxLength={4000} required disabled={busy||!!pending}/></label>
      <p className="beta-warn"><span aria-hidden="true">!</span>Do not include passwords, card details or private keys.</p>
      <button disabled={busy||uncertain||!data}>{pending?'Retry same support request':'Send support request'}</button></form>
    <p role="status" aria-live="polite" className="beta-notice">{notice}</p></div>
    <div className="beta-support-list"><div className="beta-list-head"><h2>Your requests</h2>
      <button disabled={busy} onClick={()=>run(async()=>{const value=await reload();if(pending&&value.items.some(x=>x.requestId===pending.requestId))clearSaved();else if(live.current)setUncertain(false);})}>Reload saved support requests</button></div>
      {!data?<p className="beta-empty">{busy?'Loading saved requests…':'Saved requests are not loaded. Reload to try again.'}</p>
      :data.items.length?<ul>{data.items.map(row=><li key={row.id}><b>{row.title}</b><small><time dateTime={row.createdAt}>{utcMinute(row.createdAt)}</time> · saved</small></li>)}</ul>
      :<p className="beta-empty">No requests yet.</p>}
      {data?.truncated&&<p>Only the latest 50 requests are shown.</p>}
      <p className="beta-muted">Staff replies are not shown in the app yet.</p></div>
  </section>;
}
