import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {api,sessionPath,noticeText} from './client.js';
import {money,utc,lastSession} from './productData.js';
import {linkTo,navigate,setLeaveGuard} from './productRoute.js';
import {readDraft,writeDraft,clearDraft,isDirty,tagList,tagText} from './noteDrafts.js';
import {StatePanel,PageHead} from './AlphaShell.jsx';
import {SearchableSelect} from './AlphaSelect.jsx';
import Segmented from './AlphaSegmented.jsx';
import Icon from '../workspace/WorkspaceIcon.jsx';

// Journal page (U11, CP3): one Session at a time, because a journal across
// Sessions needs a server list that is not published yet. Rows are the
// committed orders from GET /sessions/{id}/journal; notes are research
// annotations and never change fills or cash. Unknown values stay "—".
const SIDES=[['ALL','All'],['LONG','Long'],['SHORT','Short']];
const dash=value=>value===null||value===undefined||value===''?'—':value;

// Note editor with draft safety (founder remediation 2026-11-06 P1): the draft
// is kept in this tab's sessionStorage until saved or discarded, Cancel asks
// before throwing text away, and a save made from an older revision is refused
// by the server and shown side by side with the newer saved note.
function NoteEditor({order,note,sessionId,path,onSaved,onDirty,onReload}){
  const [draft,setDraft]=useState(()=>readDraft(sessionId,order.id));
  const [restored]=useState(()=>Boolean(readDraft(sessionId,order.id)));
  const [state,setState]=useState({saving:false,error:null,conflict:false,confirmDiscard:false,stored:true});
  const dirty=isDirty(draft,note);
  // Reports 'kept' (in tab storage) or 'lost' (storage blocked/full) while dirty.
  const report=dirty?(state.stored?'kept':'lost'):false;
  useEffect(()=>{onDirty(order.id,report);},[order.id,report,onDirty]);
  useEffect(()=>()=>onDirty(order.id,false),[order.id,onDirty]);
  const update=next=>{const value={...draft,...next};setDraft(value);setState(previous=>({...previous,stored:writeDraft(sessionId,order.id,value),confirmDiscard:false}));};
  const start=()=>{const value={text:note?.text??'',tags:tagText(note?.tags),baseRevision:note?.noteRevision??0};setDraft(value);const stored=writeDraft(sessionId,order.id,value);setState(previous=>({...previous,stored,error:null,conflict:false}));};
  const discard=()=>{clearDraft(sessionId,order.id);setDraft(null);setState({saving:false,error:null,conflict:false,confirmDiscard:false,stored:true});};
  const save=async(event,baseRevision=draft.baseRevision)=>{
    event?.preventDefault();
    setState(previous=>({...previous,saving:true,error:null,confirmDiscard:false}));
    try{
      const value=await api(path,{orderId:order.id,expectedNoteRevision:baseRevision,text:draft.text,tags:tagList(draft.tags)});
      clearDraft(sessionId,order.id);setDraft(null);onSaved(value);
      setState({saving:false,error:null,conflict:false,confirmDiscard:false,stored:true});
    }catch(failure){
      const conflict=failure.message==='REFUSED_STALE_NOTE';
      setState(previous=>({...previous,saving:false,conflict,error:conflict?null:noticeText(failure.message)}));
      if(conflict)onReload();
    }
  };
  if(!draft)return <div className="rk-note-view">
    {note?.text?<p className="rk-note-text">{note.text}</p>:<p className="rk-note">No note yet.</p>}
    {note?.tags?.length>0&&<ul className="rk-tag-list" aria-label="Tags">{note.tags.map(tag=><li key={tag}>{tag}</li>)}</ul>}
    <button type="button" className="rk-btn rk-btn-small" onClick={start}>{note?'Edit note':'Add note'}</button>
  </div>;
  const newer=state.conflict&&(note?.noteRevision??0)!==draft.baseRevision;
  return <form className="rk-form rk-note-form" onSubmit={save} aria-label={`Note for ${order.side==='LONG'?'long':'short'} order ${utc(order.entryTimeNs)}`}>
    {restored&&!state.conflict&&<p className="rk-note rk-draft-flag" role="status">Unsaved draft restored. It is kept in this browser tab only until you save or discard it.</p>}
    {state.conflict&&<div className="rk-conflict" role="alert">
      <strong>{newer?`This note was saved elsewhere (revision ${note?.noteRevision??0}).`:'The note changed on the server.'}</strong>
      <p>Your text below is kept. Compare, then choose which version stays.</p>
      {newer&&<blockquote className="rk-conflict-server"><span>Saved version</span>{note?.text?<p>{note.text}</p>:<p className="rk-note">Empty note</p>}{note?.tags?.length>0&&<small>Tags: {note.tags.join(', ')}</small>}</blockquote>}
      <div className="rk-form-actions">
        <button type="button" className="rk-btn rk-btn-primary" disabled={state.saving||!newer} onClick={()=>{update({baseRevision:note?.noteRevision??0});save(null,note?.noteRevision??0);}}>Replace with my text</button>
        <button type="button" className="rk-btn" disabled={state.saving} onClick={discard}>Keep saved version</button>
      </div>
    </div>}
    <label>Research note<textarea value={draft.text} maxLength={4096} rows={4} onChange={event=>update({text:event.target.value})} disabled={state.saving}/></label>
    <label>Tags<input value={draft.tags} onChange={event=>update({tags:event.target.value})} placeholder="breakout, london" disabled={state.saving}/><small>Up to 8, separated by commas.</small></label>
    {!state.stored&&<p className="rk-note rk-draft-lost" role="alert">This browser could not keep the draft (tab storage is blocked or full). Save the note, or the text is lost if you leave or reload this page.</p>}
    {state.error&&<p className="rk-form-error" role="alert">{state.error} Your text is kept here.</p>}
    {state.confirmDiscard?<div className="rk-form-actions" role="group" aria-label="Discard unsaved text?">
        <span className="rk-note">Discard the unsaved text?</span>
        <button type="button" className="rk-btn rk-btn-danger" onClick={discard}>Discard</button>
        <button type="button" className="rk-btn" onClick={()=>setState(previous=>({...previous,confirmDiscard:false}))}>Keep editing</button></div>
      :<div className="rk-form-actions"><button className="rk-btn rk-btn-primary" disabled={state.saving||state.conflict||!dirty}>{state.saving?'Saving…':'Save note'}</button>
        <button type="button" className="rk-btn rk-btn-quiet" disabled={state.saving} onClick={()=>dirty?setState(previous=>({...previous,confirmDiscard:true})):discard()}>Cancel</button></div>}
  </form>;
}

export default function AlphaJournalPage({catalog,route,onOpen}){
  const sessionId=route.analyticsSession||(catalog.sessions.some(s=>s.id===lastSession())?lastSession():null);
  const session=catalog.sessions.find(s=>s.id===sessionId)||null;
  const [attempt,setAttempt]=useState(0);
  const [result,setResult]=useState({key:null});
  const [side,setSide]=useState('ALL');
  const [status,setStatus]=useState(null);
  const [query,setQuery]=useState('');
  const [dirty,setDirty]=useState(()=>new Map()); // orderId → 'kept' | 'lost'
  const [leaving,setLeaving]=useState(null);
  const stay=useRef(null),allow=useRef(false);
  // Open replay loads the Session before it changes the route, so ask before starting it.
  const leaveThen=action=>{if(dirty.size&&!allow.current)setLeaving(()=>action);else action();};
  const onDirty=useCallback((orderId,value)=>setDirty(previous=>{
    if((previous.get(orderId)??false)===value)return previous;
    const next=new Map(previous);if(value)next.set(orderId,value);else next.delete(orderId);return next;
  }),[]);
  const lost=[...dirty.values()].filter(value=>value==='lost').length;
  // Leaving with unsaved drafts (Session picker, sidebar, Back) asks first; closing the tab warns.
  useEffect(()=>{
    if(!dirty.size)return undefined;
    // `allow` is set once the person chose Leave, so the move it starts (which may
    // navigate again, or load another document) is not asked about twice.
    allow.current=false;
    const release=setLeaveGuard(proceed=>{if(allow.current)return true;setLeaving(()=>proceed);return false;});
    const unload=event=>{if(allow.current)return;event.preventDefault();event.returnValue='';};
    globalThis.addEventListener('beforeunload',unload);
    return()=>{release();globalThis.removeEventListener('beforeunload',unload);};
  },[dirty.size]);
  useEffect(()=>{if(leaving)stay.current?.focus();},[leaving]);
  const key=`${sessionId}:${attempt}`;
  const path=session?sessionPath(session.id)+'/journal':null;
  useEffect(()=>{
    if(!path)return undefined;
    let live=true;
    api(path).then(value=>{if(live)setResult({key,status:'ready',value});},failure=>{if(live)setResult({key,status:'error',message:noticeText(failure.message)});});
    return()=>{live=false;};
  },[path,key]);
  // A reload after a stale-note refusal keeps the page (and open editors) mounted.
  const state=result.key===key?result:result.key?.startsWith(`${sessionId}:`)&&result.status==='ready'?result:{status:'loading'};
  const journal=state.status==='ready'?state.value:null;
  const statuses=useMemo(()=>[...new Set((journal?.orders??[]).map(order=>order.status))].sort(),[journal]);
  const rows=useMemo(()=>{
    if(!journal)return [];
    const q=query.trim().toLowerCase();
    return journal.orders.filter(order=>{
      if(side!=='ALL'&&order.side!==side)return false;
      if(status&&order.status!==status)return false;
      if(!q)return true;
      const note=journal.notes.find(item=>item.orderId===order.id);
      return [note?.text,...(note?.tags??[]),order.orderType,order.status].filter(Boolean).some(text=>text.toLowerCase().includes(q));
    }).slice().reverse();
  },[journal,side,status,query]);
  const sessionOptions=catalog.sessions.slice().reverse().map(s=>({value:s.id,label:s.name,description:catalog.methods.find(m=>m.id===s.methodId)?.name}));
  const picker=<div className="rk-toolbar-combo rk-toolbar-combo-wide"><SearchableSelect label="Session" placeholder="Search or select Session" searchPlaceholder="Search Sessions…" options={sessionOptions} value={session?.id??null}
    onChange={value=>navigate({screen:'journal',of:value||undefined})} noOptionsText="No Sessions yet."/></div>;
  const savedNote=value=>setResult(previous=>({...previous,value:{...previous.value,notes:[...previous.value.notes.filter(item=>item.orderId!==value.orderId),value]}}));
  const leaveDialog=leaving&&<div className="rk-leave" role="alertdialog" aria-modal="true" aria-labelledby="rk-leave-title" aria-describedby="rk-leave-text"
    onKeyDown={event=>{
      if(event.key==='Escape'){event.preventDefault();setLeaving(null);}
      else if(event.key==='Tab'){const buttons=[...event.currentTarget.querySelectorAll('button')];const at=buttons.indexOf(document.activeElement);event.preventDefault();buttons[(at+(event.shiftKey?-1:1)+buttons.length)%buttons.length]?.focus();}
    }}>
    <div className="rk-card rk-leave-card"><h2 id="rk-leave-title">Unsaved notes</h2>
      <p id="rk-leave-text">{dirty.size===1?'One order has':`${dirty.size} orders have`} unsaved note text. {lost?`${lost===dirty.size?(lost===1?'It':'They'):`${lost} of them`} could not be kept in this browser, so leaving loses that text.`:'Drafts stay in this browser tab until you save or discard them.'} Notes never change fills or cash.</p>
      <div className="rk-form-actions"><button ref={stay} type="button" className="rk-btn rk-btn-primary" onClick={()=>setLeaving(null)}>Keep editing</button>
        <button type="button" className="rk-btn" onClick={()=>{const proceed=leaving;setLeaving(null);allow.current=true;proceed();}}>{lost?'Leave and lose text':'Leave, keep drafts'}</button></div></div></div>;
  return <>{leaveDialog}<PageHead eyebrow="Research" title="Journal" lead="Committed orders of one Session with your notes. Notes never change fills or cash."
      actions={session&&<button type="button" className="rk-btn" onClick={()=>leaveThen(()=>onOpen(session.id))}>Open replay</button>}/>
    <div className="rk-toolbar">{picker}</div>
    {!catalog.sessions.length?<StatePanel kind="empty" title="Nothing journaled yet" action={<a className="rk-btn rk-btn-primary" {...linkTo({screen:'session-new'})}>New Session</a>}><p>Journals start when you confirm the first order in a Session.</p></StatePanel>
      :!session?<StatePanel kind="empty" title={sessionId?'This Session is not in this workspace':'Choose a Session'}><p>{sessionId?'Pick one from the list above.':'A journal across all Sessions needs a server list that is not published yet, so pick one Session.'}</p></StatePanel>
      :state.status==='loading'?<StatePanel kind="loading" title="Loading the journal…"/>
      :state.status==='error'?<StatePanel kind="error" title="The journal could not load" action={<button type="button" className="rk-btn" onClick={()=>setAttempt(n=>n+1)}>Retry</button>}><p>{state.message}</p></StatePanel>
      :!journal.orders.length?<StatePanel kind="empty" title="No orders yet" action={<button type="button" className="rk-btn rk-btn-primary" onClick={()=>leaveThen(()=>onOpen(session.id))}>Open replay</button>}><p>Review and confirm an order in replay; it appears here with room for a note.</p></StatePanel>
      :<>
        <div className="rk-toolbar">
          <Segmented label="Side" options={SIDES} value={side} onChange={setSide}/>
          <div className="rk-toolbar-combo"><SearchableSelect label="Status" placeholder="All statuses" options={statuses.map(value=>({value,label:value.charAt(0)+value.slice(1).toLowerCase().replaceAll('_',' ')}))} value={status} onChange={setStatus} clearable/></div>
          <label className="rk-search"><span className="alpha-sr-only">Search notes and tags</span><Icon name="search" size={18}/><input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Search notes and tags"/></label>
          <span className="rk-count" role="status">{rows.length} of {journal.orders.length} orders</span>
        </div>
        {rows.length?<ol className="rk-journal" aria-label={`Orders in ${session.name}`}>{rows.map(order=>{
          const note=journal.notes.find(item=>item.orderId===order.id);
          return <li key={order.id} className="rk-card rk-journal-item">
            <div className="rk-journal-head"><span className={`rk-side rk-side-${order.side==='LONG'?'buy':'sell'}`}>{order.side==='LONG'?'Long':'Short'}</span><strong>{order.orderType.charAt(0)+order.orderType.slice(1).toLowerCase()}</strong><span className="rk-tag">{order.status.toLowerCase().replaceAll('_',' ')}</span><span className="rk-num rk-journal-time">{utc(order.entryTimeNs)}</span></div>
            <dl className="rk-facts rk-journal-facts">
              <div><dt>Entry</dt><dd className="rk-num">{dash(order.entryPrice??order.entry)}</dd></div>
              <div><dt>Lots</dt><dd className="rk-num">{dash(order.quantity)}</dd></div>
              <div><dt>SL / TP</dt><dd className="rk-num">{dash(order.sl)} / {dash(order.tp)}</dd></div>
              <div><dt>Net cash change</dt><dd className="rk-num">{money(order.netCashChange)}</dd></div>
              <div><dt>R multiple</dt><dd className="rk-num" title={order.rMultiple===null?order.rReason:undefined}>{order.rMultiple===null?'—':order.rMultiple}</dd></div>
            </dl>
            <NoteEditor key={order.id} order={order} note={note} sessionId={session.id} path={path} onSaved={savedNote} onDirty={onDirty} onReload={()=>setAttempt(n=>n+1)}/>
          </li>;})}</ol>
          :<StatePanel kind="filtered" title="No order matches" action={<button type="button" className="rk-btn" onClick={()=>{setSide('ALL');setStatus(null);setQuery('');}}>Clear filters</button>}><p>Try another side, status or search.</p></StatePanel>}
        {dirty.size>0&&<p className="rk-note rk-draft-flag" role="status">{dirty.size===1?'1 unsaved note draft':`${dirty.size} unsaved note drafts`} in this tab{lost?`; ${lost} not kept by this browser`:''}.</p>}
        <p className="rk-main-note">Snapshot revision {journal.provenance.revision}. Financial values come from committed events only.</p>
      </>}
  </>;
}
