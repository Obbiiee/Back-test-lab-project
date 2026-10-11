import {useEffect,useRef,useState} from 'react';
import {KEY,QUESTIONS,readMeasurement,writeMeasurement,saveFeedback,measurementExport} from './measurement.js';
import {api} from './client.js';

const choiceLabel=value=>({'better-data':'Higher quality historical data','clearer-workflow':'Clearer research workflow',
  'under-5':'Under $5 / month','5-10':'$5–10 / month','10-20':'$10–20 / month','over-20':'Over $20 / month',
  skip:'Prefer not to say',very:'Very disappointed',somewhat:'Somewhat disappointed',not:'Not disappointed',unsure:'Unsure',
  '1':'1 — not useful','5':'5 — very useful'}[value]??value.charAt(0).toUpperCase()+value.slice(1));

export default function AlphaFeedback({onClose}){
  const [answers,setAnswers]=useState(Object.fromEntries(QUESTIONS.map(([key])=>[key,key==='price'?'skip':''])));
  const [notice,setNotice]=useState(''),[record,setRecord]=useState(()=>{try{return readMeasurement(window.localStorage);}catch{return null;}});
  const [responseId]=useState(()=>crypto.randomUUID());
  const [exporting,setExporting]=useState(false);
  const [download,setDownload]=useState(null);
  const exportController=useRef(null),generation=useRef(0);
  useEffect(()=>()=>{generation.current++;exportController.current?.abort();},[]);
  useEffect(()=>()=>{if(download)URL.revokeObjectURL(download.url);},[download]);
  function enable(){try{setRecord(writeMeasurement(window.localStorage,{...readMeasurement(window.localStorage),enabled:true}));setNotice('Optional observations enabled in this browser only.');}catch(e){setNotice(e.message);}}
  function submit(event){event.preventDefault();try{setRecord(saveFeedback(window.localStorage,answers,responseId));setNotice('Feedback saved locally. Thank you. No trading state changed.');}catch(e){setNotice(e.message);}}
  async function prepareExport(){if(exporting)return;setExporting(true);const current=++generation.current;try{
    const value=measurementExport(readMeasurement(window.localStorage));
    const controller=new AbortController();exportController.current=controller;
    const timeout=setTimeout(()=>controller.abort(),2000);
    try{value.operational=await api('/measurement/operational',undefined,{signal:controller.signal}).catch(()=>({status:'UNAVAILABLE'}));}finally{clearTimeout(timeout);}
    if(current!==generation.current)return;
    const json=JSON.stringify(value,null,2),url=URL.createObjectURL(new Blob([json],{type:'application/json'}));
    setDownload({json,url});setNotice('Export prepared. Download or review the JSON below.');
  }catch(e){if(current===generation.current)setNotice(e.message);}finally{if(current===generation.current)setExporting(false);}}
  function remove(){try{window.localStorage.removeItem(KEY);setRecord(readMeasurement(window.localStorage));setNotice('Optional observations and answers removed from this browser. Trading data is unchanged.');}catch(e){setNotice(e.message);}}
  return <section className="alpha-dialog"><div className="alpha-terminal-heading"><h2>Help improve the research workspace</h2><button onClick={onClose}>Not now</button></div>
    <p>Optional, private owner feedback. Stored in this browser for a 30-day observation window; no external collection, recording, credentials, strategy text or market files. Only you can read/export it here. Internal/QA use is excluded from public product metrics.</p>
    <p>Disabling or unavailable storage never affects orders. One response per observation window. Paying answers indicate interest, not a purchase.</p>
    {!record?<p role="alert">Existing optional data could not be read; it has been preserved.</p>:<>
      {!record.enabled&&<button onClick={enable}>Enable optional local measurement</button>}
      {record.responses.length>0&&<p>Your local feedback is already saved for this observation window. Export it below, or remove optional data to withdraw it.</p>}
      {record.enabled&&<form onSubmit={submit}>{QUESTIONS.map(([key,label,values])=><label key={key}>{label}<select required aria-label={label} value={answers[key]} onChange={e=>setAnswers(v=>({...v,[key]:e.target.value}))}><option value="" disabled>Choose an answer</option>{values.map(value=><option key={value} value={value}>{choiceLabel(value)}</option>)}</select></label>)}<button disabled={record.responses.length>0}>Save optional feedback</button></form>}
      <button disabled={exporting} onClick={prepareExport}>Export local observations and cost worksheet</button>
      {download&&<><a href={download.url} download="backtest-local-measurement.json">Download local measurement JSON</a><details><summary>Review export JSON</summary><textarea aria-label="Local measurement JSON" readOnly value={download.json}/></details></>}
      <button onClick={()=>{try{setRecord(writeMeasurement(window.localStorage,{...readMeasurement(window.localStorage),enabled:false}));setNotice('Optional collection disabled.');}catch(e){setNotice(e.message);}}}>Disable optional collection</button>
      <button onClick={remove}>Remove optional local data</button>
    </>}{notice&&<p role="status">{notice}</p>}
  </section>;
}
