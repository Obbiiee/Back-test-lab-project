import {useEffect,useRef,useState} from 'react';
import {ReviewedIntent} from './AlphaOrderPresentation.jsx';
import {noticeText} from './client.js';
import {UNKNOWN_TEXT} from './confirmOutcome.js';

// Confirm step of Draft → server Review → Confirm (C-14). Phases:
//  REVIEW_EXACT    server-reviewed values; Confirm arms after a short delay so the
//                  tap that opened the review cannot land on Confirm.
//  COMMIT_PENDING  one confirm request in flight; every control and dismissal is
//                  locked, so a second confirm cannot be sent.
//  COMMITTED       saved, but the Session view could not refresh (the parent closes
//                  the sheet itself when the refresh works).
//  STALE / REFUSED a definitive server refusal: the order was not placed.
//  UNKNOWN         no definitive answer (lost response, timeout, 5xx). The sheet keeps
//                  this review, checks the saved Session read-only, and offers only
//                  Check again or Close: never a second confirm or a new review.
// Outcomes come from confirmOutcome.js. The client computes nothing financial: R:R
// below is a display ratio of the three reviewed prices, and only when all three exist.
const ARM_MS=600;

const ratio=(entry,sl,tp)=>{
  if(![entry,sl,tp].every(value=>typeof value==='string'&&/^\d+(\.\d+)?$/.test(value)))return null;
  const [e,s,t]=[entry,sl,tp].map(Number);
  if(![e,s,t].every(Number.isFinite)||e===s)return null;
  const value=Math.abs(t-e)/Math.abs(e-s);
  return Number.isFinite(value)?value.toFixed(2):null;
};

export default function AlphaReviewSheet({review,view,busy,onConfirm,onCheck,onReload,onCancel,onReviewAgain}){
  const payload=review.review.command.payload;
  const [phase,setPhase]=useState('REVIEW_EXACT');
  const [armed,setArmed]=useState(false);
  const [failure,setFailure]=useState(null);
  const [checking,setChecking]=useState(false);
  const sending=useRef(false);
  // Focus follows the phase: disabling the focused Confirm button would otherwise drop
  // focus to the page, so pending moves it to the sheet and an outcome to its main action.
  const sheet=useRef(null);
  useEffect(()=>{
    if(phase==='REVIEW_EXACT')return;
    const primary=sheet.current?.querySelector('.alpha-review-primary:not(:disabled)');
    (phase==='COMMIT_PENDING'||!primary?sheet.current:primary)?.focus();
  },[phase,checking]);
  useEffect(()=>{const timer=setTimeout(()=>setArmed(true),ARM_MS);return()=>clearTimeout(timer);},[]);
  const settle=result=>{
    if(result.outcome==='COMMITTED'){if(!result.refreshed)setPhase('COMMITTED');return;} // refreshed: parent closes
    setFailure(result.code||'');
    setPhase(result.outcome==='STALE'?'STALE':result.outcome==='REFUSED'?'REFUSED':result.outcome==='NOT_SENT'?'REVIEW_EXACT':'UNKNOWN');
    if(result.outcome==='NOT_SENT')sending.current=false;
  };
  const check=async identity=>{
    if(checking)return;
    setChecking(true);
    try{settle(await onCheck(identity));}finally{setChecking(false);}
  };
  const confirm=async()=>{
    if(sending.current||!armed||phase!=='REVIEW_EXACT')return;
    sending.current=true;setPhase('COMMIT_PENDING');
    const result=await onConfirm();
    settle(result);
    if(result.outcome==='UNKNOWN')await check(result.identity);
  };
  const pending=phase==='COMMIT_PENDING';
  const rr=ratio(payload.entry,payload.sl,payload.tp);
  const conditions=payload.observations??[];
  return <section ref={sheet} tabIndex={-1} className={`alpha-dialog alpha-review-sheet is-${phase.toLowerCase().replace('_','-')}`} aria-busy={pending||undefined}>
    <div className="alpha-review-sheet-head"><span className="alpha-review-step">Step 3 of 3 · Confirm</span><h2>Confirm reviewed order</h2></div>
    <div className="alpha-review-sheet-body">
      {(phase==='STALE'||phase==='REFUSED')&&<div className="alpha-review-refusal" role="alert">
        <strong>{phase==='STALE'?'This review is out of date':'The order was not placed'}</strong>
        <p>{phase==='STALE'?'The Session changed after this review, and the server refused it. Review again to get fresh exact values.'
          :failure==='RECONCILED_NOT_SAVED'?'The saved Session moved on without this confirmation, so it can no longer be applied.'
          :`The server refused this confirmation. ${noticeText(failure)}`}</p>
      </div>}
      {phase==='UNKNOWN'&&<div className="alpha-review-unknown" role="alert">
        <strong>Order status not verified</strong>
        <p>{checking?UNKNOWN_TEXT:'The saved Session does not show this order yet. It may still be saving. Check again; nothing is sent twice.'}</p>
      </div>}
      {phase==='COMMITTED'&&<div className="alpha-review-saved" role="status">
        <strong>Order saved</strong>
        <p>The server saved this order. The Session view could not refresh, so the chart and tables are out of date until you reload.</p>
      </div>}
      <ReviewedIntent payload={payload} methodName={view.method.name} riskBasis={review.review.riskBasis} researchRisk={review.review.researchRisk}/>
      {rr&&<p className="alpha-review-rr"><span>R:R from reviewed prices</span><strong>1 : {rr}</strong></p>}
      {view.method.kind==='PROTOCOL'&&<p className="alpha-review-protocol">Protocol rules apply: planned entry, risk and target come from the Method and cannot be changed here.</p>}
      {conditions.length>0&&<ul className="alpha-review-conditions" aria-label="Checklist">{conditions.map(o=><li key={o.conditionId}><span>{view.method.conditions.find(c=>c.id===o.conditionId)?.label??o.conditionId}</span><strong>{o.outcome.replaceAll('_',' ').toLowerCase()}</strong></li>)}</ul>}
      <p className="alpha-review-note">Fill uses the next eligible observed Bid/Ask. This confirmation is not an execution price.</p>
      {pending&&<p className="alpha-review-pending" role="status"><span className="alpha-review-spinner" aria-hidden="true"/>Saving the order… keep this open.</p>}
    </div>
    <div className="alpha-review-actions">
      {phase==='UNKNOWN'?<><button type="button" disabled={checking} onClick={onCancel}>Close</button><button type="button" className="alpha-review-primary" disabled={checking||busy} onClick={()=>check()}>{checking?'Checking…':'Check again'}</button></>
        :phase==='COMMITTED'?<><button type="button" disabled={busy} onClick={onCancel}>Close</button><button type="button" className="alpha-review-primary" disabled={busy} onClick={onReload}>Reload Session</button></>
        :phase==='STALE'||phase==='REFUSED'
        ?<><button type="button" disabled={busy} onClick={onCancel}>Close</button><button type="button" className="alpha-review-primary" disabled={busy} onClick={onReviewAgain}>Review again</button></>
        :<><button type="button" disabled={pending||busy} onClick={onCancel}>Cancel confirmation</button>
          <button type="button" className="alpha-review-primary" disabled={pending||busy||!armed} onClick={confirm}>{pending?'Saving…':'Confirm order'}</button></>}
    </div>
  </section>;
}
