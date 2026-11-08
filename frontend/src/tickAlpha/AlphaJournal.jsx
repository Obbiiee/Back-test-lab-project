import {useEffect,useRef,useState} from 'react';
import {api,sessionPath,loadJournalPage,noticeText} from './client.js';

export default function AlphaJournal({view}){
  const [journal,setJournal]=useState(null),[error,setError]=useState(''),[saving,setSaving]=useState(false),[drafts,setDrafts]=useState({});
  const [loadingMore,setLoadingMore]=useState(false);
  const sessionId=view.metadata.id;
  const path=sessionPath(sessionId)+'/journal';
  const generation=useRef(0);
  useEffect(()=>{
    let active=true;
    const current=++generation.current;
    loadJournalPage(sessionId).then(value=>{if(active&&current===generation.current){setJournal(value);setError('');}},failure=>{if(active&&current===generation.current)setError(noticeText(failure.message));});
    return()=>{active=false;};
  },[path,sessionId,view.state.revision]);
  async function save(order,note){
    generation.current++;
    setSaving(true);setError('');
    try{
      const value=await api(path,{orderId:order.id,expectedNoteRevision:note?.noteRevision??0,text:drafts[order.id]?.text??note?.text??'',tags:(drafts[order.id]?.tags??(note?.tags??[]).join(', ')).split(',').map(value=>value.trim()).filter(Boolean)});
      setJournal(previous=>({...previous,notes:[...previous.notes.filter(item=>item.orderId!==order.id),value]}));
      setDrafts(previous=>{const next={...previous};delete next[order.id];return next;});
    }catch(failure){setError(noticeText(failure.message));}finally{setSaving(false);}
  }
  async function reloadJournal(){
    const current=++generation.current;
    setSaving(true);
    try{const value=await loadJournalPage(view.metadata.id);if(current===generation.current){setJournal(value);setError('');}}
    catch(failure){if(current===generation.current)setError(noticeText(failure.message));}
    finally{setSaving(false);}
  }
  async function loadMore(){
    if(!journal?.nextCursor||loadingMore)return;
    setLoadingMore(true);setError('');
    try{
      const page=await loadJournalPage(view.metadata.id,journal.nextCursor);
      setJournal(previous=>{
        if(!previous)return previous;
        const orders=new Map(previous.orders.map(order=>[order.id,order]));
        for(const order of page.orders)orders.set(order.id,order);
        const notes=new Map(previous.notes.map(note=>[note.orderId,note]));
        for(const note of page.notes)notes.set(note.orderId,note);
        return {...page,orders:[...orders.values()],notes:[...notes.values()]};
      });
    }catch(failure){setError(noticeText(failure.message));}
    finally{setLoadingMore(false);}
  }
  async function exportJournal(){
    setSaving(true);setError('');
    try{
      // Fetch a coherent committed snapshot; never mix browser drafts into financial rows.
      let page=await loadJournalPage(view.metadata.id),orders=new Map(page.orders.map(order=>[order.id,order])),notes=new Map(page.notes.map(note=>[note.orderId,note]));
      while(!page.complete){page=await loadJournalPage(view.metadata.id,page.nextCursor);for(const order of page.orders)orders.set(order.id,order);for(const note of page.notes)notes.set(note.orderId,note);}
      const value={...page,artifact:'BTL-TICK-JOURNAL-EXPORT-1',orders:[...orders.values()],notes:[...notes.values()]};
      const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));
      const link=document.createElement('a');link.href=url;link.download='backtest-journal.json';link.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(failure){setError(noticeText(failure.message));}finally{setSaving(false);}
  }
  return <div className="alpha-analysis alpha-journal"><h2>Research journal</h2><p>Private notes on canonical orders. Pending and unresolved intents are not completed trades. Notes never change fills or cash. Saved notes remain in the local product database.</p>
    {error&&<p role="alert">{error} Your draft is retained here. Reload the journal before resolving a conflicting edit.</p>}
    <button disabled={saving||!journal} onClick={exportJournal}>Export saved journal JSON</button>
    <button disabled={saving} onClick={reloadJournal}>Reload journal</button>
    {journal&&<p>Snapshot revision {journal.provenance.revision}. Financial authority: committed events only.</p>}
    {Object.keys(drafts).length>0&&<p>Unsaved drafts are excluded from export. Save before leaving this view.</p>}
    {!journal&&!error&&<p>Loading committed identities…</p>}
    {journal&&!journal.orders.length&&<p>No canonical orders yet. Review and confirm an intent before adding an order note.</p>}
    {journal?.orders.map(order=>{
      const note=journal.notes.find(item=>item.orderId===order.id),draft=drafts[order.id];
      return <article key={order.id}><h3>{order.side} · {order.status}</h3><code>{order.id}</code><p>Entry evidence: {order.entryFillRef??'No fill'} · Exit evidence: {order.exitFillRef??'No fill'}</p>
        <label>Research note<textarea aria-label={`Research note ${order.id}`} maxLength={4096} disabled={saving} value={draft?.text??note?.text??''} onChange={event=>setDrafts(previous=>({...previous,[order.id]:{text:event.target.value,tags:draft?.tags??(note?.tags??[]).join(', ')}}))}/></label>
        <label>Tags (up to 8, comma separated)<input aria-label={`Journal tags ${order.id}`} disabled={saving} value={draft?.tags??(note?.tags??[]).join(', ')} onChange={event=>setDrafts(previous=>({...previous,[order.id]:{text:draft?.text??note?.text??'',tags:event.target.value}}))}/></label>
        {draft&&note&&<details><summary>Compare latest saved note (revision {note.noteRevision})</summary><p style={{whiteSpace:'pre-wrap'}}>{note.text||'Empty saved note'}</p><p>Saved tags: {note.tags.join(', ')||'None'}</p></details>}
        <button disabled={saving||!draft} onClick={()=>save(order,note)}>Save note</button><small>{note?`Saved revision ${note.noteRevision}`:'No saved note'}</small>
      </article>;
    })}
    {journal&&!journal.complete&&<div><p>{journal.orders.length} of {journal.totalOrders} orders loaded.</p><button disabled={saving||loadingMore} onClick={loadMore}>{loadingMore?'Loading…':'Load more orders'}</button></div>}
  </div>;
}
