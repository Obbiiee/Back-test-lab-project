import {useEffect,useMemo,useState} from 'react';
import {api,sessionPath,noticeText} from './client.js';
import {money,utc,lastSession} from './productData.js';
import {linkTo,navigate} from './productRoute.js';
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

function NoteEditor({order,note,path,onSaved}){
  const [open,setOpen]=useState(false);
  const [text,setText]=useState(note?.text??'');
  const [tags,setTags]=useState((note?.tags??[]).join(', '));
  const [state,setState]=useState({saving:false,error:null});
  const save=async event=>{
    event.preventDefault();setState({saving:true,error:null});
    try{
      const value=await api(path,{orderId:order.id,expectedNoteRevision:note?.noteRevision??0,text,tags:tags.split(',').map(item=>item.trim()).filter(Boolean)});
      onSaved(value);setOpen(false);setState({saving:false,error:null});
    }catch(failure){setState({saving:false,error:noticeText(failure.message)});}
  };
  if(!open)return <div className="rk-note-view">
    {note?.text?<p className="rk-note-text">{note.text}</p>:<p className="rk-note">No note yet.</p>}
    {note?.tags?.length>0&&<ul className="rk-tag-list" aria-label="Tags">{note.tags.map(tag=><li key={tag}>{tag}</li>)}</ul>}
    <button type="button" className="rk-btn rk-btn-small" onClick={()=>{setText(note?.text??'');setTags((note?.tags??[]).join(', '));setOpen(true);}}>{note?'Edit note':'Add note'}</button>
  </div>;
  return <form className="rk-form rk-note-form" onSubmit={save}>
    <label>Research note<textarea value={text} maxLength={4096} rows={4} onChange={event=>setText(event.target.value)} disabled={state.saving}/></label>
    <label>Tags<input value={tags} onChange={event=>setTags(event.target.value)} placeholder="breakout, london" disabled={state.saving}/><small>Up to 8, separated by commas.</small></label>
    {state.error&&<p className="rk-form-error" role="alert">{state.error} Your text is kept here.</p>}
    <div className="rk-form-actions"><button className="rk-btn rk-btn-primary" disabled={state.saving}>{state.saving?'Saving…':'Save note'}</button><button type="button" className="rk-btn rk-btn-quiet" disabled={state.saving} onClick={()=>setOpen(false)}>Cancel</button></div>
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
  const key=`${sessionId}:${attempt}`;
  const path=session?sessionPath(session.id)+'/journal':null;
  useEffect(()=>{
    if(!path)return undefined;
    let live=true;
    api(path).then(value=>{if(live)setResult({key,status:'ready',value});},failure=>{if(live)setResult({key,status:'error',message:noticeText(failure.message)});});
    return()=>{live=false;};
  },[path,key]);
  const state=result.key===key?result:{status:'loading'};
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
  return <><PageHead eyebrow="Research" title="Journal" lead="Committed orders of one Session with your notes. Notes never change fills or cash."
      actions={session&&<button type="button" className="rk-btn" onClick={()=>onOpen(session.id)}>Open replay</button>}/>
    <div className="rk-toolbar">{picker}</div>
    {!catalog.sessions.length?<StatePanel kind="empty" title="Nothing journaled yet" action={<a className="rk-btn rk-btn-primary" {...linkTo({screen:'session-new'})}>New Session</a>}><p>Journals start when you confirm the first order in a Session.</p></StatePanel>
      :!session?<StatePanel kind="empty" title={sessionId?'This Session is not in this workspace':'Choose a Session'}><p>{sessionId?'Pick one from the list above.':'A journal across all Sessions needs a server list that is not published yet, so pick one Session.'}</p></StatePanel>
      :state.status==='loading'?<StatePanel kind="loading" title="Loading the journal…"/>
      :state.status==='error'?<StatePanel kind="error" title="The journal could not load" action={<button type="button" className="rk-btn" onClick={()=>setAttempt(n=>n+1)}>Retry</button>}><p>{state.message}</p></StatePanel>
      :!journal.orders.length?<StatePanel kind="empty" title="No orders yet" action={<button type="button" className="rk-btn rk-btn-primary" onClick={()=>onOpen(session.id)}>Open replay</button>}><p>Review and confirm an order in replay; it appears here with room for a note.</p></StatePanel>
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
            <NoteEditor key={`${order.id}:${note?.noteRevision??0}`} order={order} note={note} path={path} onSaved={savedNote}/>
          </li>;})}</ol>
          :<StatePanel kind="filtered" title="No order matches" action={<button type="button" className="rk-btn" onClick={()=>{setSide('ALL');setStatus(null);setQuery('');}}>Clear filters</button>}><p>Try another side, status or search.</p></StatePanel>}
        <p className="rk-main-note">Snapshot revision {journal.provenance.revision}. Financial values come from committed events only.</p>
      </>}
  </>;
}
