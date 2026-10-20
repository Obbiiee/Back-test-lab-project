import {useEffect,useRef,useState} from 'react';
import {betaNotice} from './betaWorkspace.js';
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
  return <section aria-label="Customer support"><h2>Support</h2><p>Ask about your account or report a problem. Do not include passwords, card details, or private keys.</p>
    <button disabled={busy} onClick={()=>run(async()=>{const value=await reload();if(pending&&value.items.some(x=>x.requestId===pending.requestId))clearSaved();else if(live.current)setUncertain(false);})}>Reload saved support requests</button>
    <form onSubmit={event=>{event.preventDefault();run(async()=>{
      if(!title.trim()||!message.trim()){setNotice('Enter a subject and describe the problem.');return;}
      const request=pending??{requestId:crypto.randomUUID(),title:title.trim(),message:message.trim()};setPending(request);
      await client.supportSubmit(request);clearSaved();
      try{await reload();}catch{if(live.current){setNotice('Request saved. Reload saved requests to refresh the list; do not send it again.');if(!client.hasSession())onExpired();}return;}
      if(live.current)setNotice('Request saved. Staff delivery may be pending until the next synchronization.');
    });}}><label>Subject<input name="supportTitle" value={title} onChange={e=>setTitle(e.target.value)} maxLength={160} required disabled={busy||!!pending}/></label>
      <label>Question or problem<textarea name="supportMessage" value={message} onChange={e=>setMessage(e.target.value)} maxLength={4000} required disabled={busy||!!pending}/></label>
      <button disabled={busy||uncertain||!data}>{pending?'Retry same support request':'Send support request'}</button></form>
    <p role="status" aria-live="polite">{notice}</p>
    {data&&<><ul>{data.items.map(row=><li key={row.id}>{row.title} · {row.createdAt} · saved by the application</li>)}</ul>{data.truncated&&<p>Only the latest 50 requests are shown.</p>}</>}
  </section>;
}
