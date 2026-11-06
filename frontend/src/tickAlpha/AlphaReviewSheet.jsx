import {useEffect,useRef,useState} from 'react';
import {ReviewedIntent} from './AlphaOrderPresentation.jsx';
import {noticeText} from './client.js';

// Confirm step of Draft → server Review → Confirm (C-14). Phases:
//  REVIEW_EXACT    server-reviewed values; Confirm arms after a short delay so the
//                  tap that opened the review cannot land on Confirm.
//  COMMIT_PENDING  one confirm request in flight; every control and dismissal is
//                  locked, so a second confirm cannot be sent.
//  STALE / REFUSED the server did not place the order; nothing changed. Review again
//                  asks the server for fresh exact values (never reuses this review).
// The client computes nothing financial: R:R below is a display ratio of the three
// reviewed prices, labeled as such, and only when all three exist.
const ARM_MS=600;
const STALE=/STALE|REVISION|REVIEW_EXPIRED|REFUSED_REVIEW/;

const ratio=(entry,sl,tp)=>{
  if(![entry,sl,tp].every(value=>typeof value==='string'&&/^\d+(\.\d+)?$/.test(value)))return null;
  const [e,s,t]=[entry,sl,tp].map(Number);
  if(![e,s,t].every(Number.isFinite)||e===s)return null;
  const value=Math.abs(t-e)/Math.abs(e-s);
  return Number.isFinite(value)?value.toFixed(2):null;
};

export default function AlphaReviewSheet({review,view,busy,onConfirm,onCancel,onReviewAgain}){
  const payload=review.review.command.payload;
  const [phase,setPhase]=useState('REVIEW_EXACT');
  const [armed,setArmed]=useState(false);
  const [failure,setFailure]=useState(null);
  const sending=useRef(false);
  useEffect(()=>{const timer=setTimeout(()=>setArmed(true),ARM_MS);return()=>clearTimeout(timer);},[]);
  const confirm=async()=>{
    if(sending.current||!armed||phase!=='REVIEW_EXACT')return;
    sending.current=true;setPhase('COMMIT_PENDING');
    const result=await onConfirm();
    if(result&&result.ok)return; // parent closes the sheet with the saved Session
    sending.current=false;
    const code=result?.code||'';
    setFailure(code);setPhase(STALE.test(code)?'STALE':'REFUSED');
  };
  const pending=phase==='COMMIT_PENDING';
  const rr=ratio(payload.entry,payload.sl,payload.tp);
  const conditions=payload.observations??[];
  return <section className={`alpha-dialog alpha-review-sheet is-${phase.toLowerCase().replace('_','-')}`} aria-busy={pending||undefined}>
    <div className="alpha-review-sheet-head"><span className="alpha-review-step">Step 3 of 3 · Confirm</span><h2>Confirm reviewed order</h2></div>
    <div className="alpha-review-sheet-body">
      {(phase==='STALE'||phase==='REFUSED')&&<div className="alpha-review-refusal" role="alert">
        <strong>{phase==='STALE'?'This review is out of date':'The order was not placed'}</strong>
        <p>{phase==='STALE'?'The Session changed after this review. Review again to get fresh exact values. Nothing was placed.':`${noticeText(failure)||'The server refused the confirmation.'} Nothing was placed.`}</p>
      </div>}
      <ReviewedIntent payload={payload} methodName={view.method.name} riskBasis={review.review.riskBasis} researchRisk={review.review.researchRisk}/>
      {rr&&<p className="alpha-review-rr"><span>R:R from reviewed prices</span><strong>1 : {rr}</strong></p>}
      {view.method.kind==='PROTOCOL'&&<p className="alpha-review-protocol">Protocol rules apply: planned entry, risk and target come from the Method and cannot be changed here.</p>}
      {conditions.length>0&&<ul className="alpha-review-conditions" aria-label="Checklist">{conditions.map(o=><li key={o.conditionId}><span>{view.method.conditions.find(c=>c.id===o.conditionId)?.label??o.conditionId}</span><strong>{o.outcome.replaceAll('_',' ').toLowerCase()}</strong></li>)}</ul>}
      <p className="alpha-review-note">Fill uses the next eligible observed Bid/Ask. This confirmation is not an execution price.</p>
      {pending&&<p className="alpha-review-pending" role="status"><span className="alpha-review-spinner" aria-hidden="true"/>Saving the order… keep this open.</p>}
    </div>
    <div className="alpha-review-actions">
      {phase==='STALE'||phase==='REFUSED'
        ?<><button type="button" disabled={busy} onClick={onCancel}>Close</button><button type="button" className="alpha-review-primary" disabled={busy} onClick={onReviewAgain}>Review again</button></>
        :<><button type="button" disabled={pending||busy} onClick={onCancel}>Cancel confirmation</button>
          <button type="button" className="alpha-review-primary" disabled={pending||busy||!armed} onClick={confirm}>{pending?'Saving…':'Confirm order'}</button></>}
    </div>
  </section>;
}
