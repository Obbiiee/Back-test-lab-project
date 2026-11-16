import {useRef,useState} from 'react';
import {scrubFraction,scrubKind,scrubRange,scrubStep,scrubTarget,utcLabel} from './replay.js';

// Replay position scrubber over the Session's calendar month.
//  - Left of the cursor = revealed history: moving there only pans the chart (no Session change).
//  - Right of the cursor = future time: selecting it only proposes a target; nothing is revealed
//    until the user confirms, and then only through the official forward SEEK (single-flight,
//    pending-target aware). Future candles are never drawn here.
export default function AlphaReplayScrubber({view,timeframe,pending,locked,onPan,onSeek}){
  const range=scrubRange(view);
  const track=useRef(null),frame=useRef(0);
  const [preview,setPreview]=useState(null),[draft,setDraft]=useState(null);
  if(!range)return null;
  const through=view.state.throughNs;
  const cursor=scrubFraction(through,range);
  const percent=value=>`${(value*100).toFixed(3)}%`;
  const pan=target=>{cancelAnimationFrame(frame.current);frame.current=requestAnimationFrame(()=>onPan(Number(BigInt(target)/1000000000n)));};
  const targetAt=clientX=>{
    const box=track.current.getBoundingClientRect();
    return scrubTarget(box.width>0?(clientX-box.left)/box.width:0,range);
  };
  const propose=target=>{
    setPreview(target);
    if(scrubKind(target,through)==='REVEALED'){setDraft(null);pan(target);}
  };
  const finish=target=>{
    setPreview(null);
    if(scrubKind(target,through)==='FUTURE'&&!locked&&!view.state.ended)setDraft(target);
  };
  const down=event=>{
    if(event.button!==undefined&&event.button!==0)return;
    event.preventDefault();track.current.focus({preventScroll:true});
    track.current.setPointerCapture(event.pointerId);
    propose(targetAt(event.clientX));
  };
  const move=event=>{if(track.current.hasPointerCapture(event.pointerId))propose(targetAt(event.clientX));};
  const up=event=>{
    if(!track.current.hasPointerCapture(event.pointerId))return;
    track.current.releasePointerCapture(event.pointerId);
    finish(targetAt(event.clientX));
  };
  const key=event=>{
    const base=draft??preview??through;
    if(event.key==='ArrowLeft'||event.key==='ArrowRight'){
      event.preventDefault();
      const next=scrubStep(base,timeframe,event.key==='ArrowLeft'?-1:1,range);
      if(scrubKind(next,through)==='REVEALED'){setDraft(null);setPreview(null);pan(next);}
      else if(!locked&&!view.state.ended)setDraft(next);
    }else if(event.key==='Home'){event.preventDefault();setDraft(null);pan(range.startNs);}
    else if(event.key==='End'){event.preventDefault();setDraft(null);pan(through);}
    else if(event.key==='Enter'&&draft){event.preventDefault();confirm();}
    else if(event.key==='Escape'&&(draft||preview)){event.stopPropagation();setDraft(null);setPreview(null);}
  };
  const confirm=()=>{const target=draft;setDraft(null);if(target)onSeek(target);};
  const ghost=draft??preview;
  const pendingStart=pending&&BigInt(pending.target)>BigInt(through)?scrubFraction(through,range):null;
  const label=`${utcLabel(through)} · ${Math.round(cursor*100)}% of ${view.metadata.startPeriod} revealed${pending?' · unfinished target saved':''}`;
  return <div className="alpha-scrub" role="group" aria-label="Replay position">
    <div ref={track} className="alpha-scrub-track" role="slider" tabIndex={0} aria-label="Replay position in this month"
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(cursor*100)} aria-valuetext={label}
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={()=>{setPreview(null);}} onKeyDown={key}>
      <span className="alpha-scrub-revealed" style={{width:percent(cursor)}}/>
      {pendingStart!==null&&<span className="alpha-scrub-pending" title="Unfinished replay target" style={{left:percent(pendingStart),width:percent(Math.max(0,scrubFraction(pending.target,range)-pendingStart))}}/>}
      <span className="alpha-scrub-thumb" style={{left:percent(cursor)}}/>
      {ghost&&<span className={`alpha-scrub-ghost ${scrubKind(ghost,through)==='FUTURE'?'is-future':''}`} style={{left:percent(scrubFraction(ghost,range))}}>
        <em>{utcLabel(ghost).slice(5,16)}{scrubKind(ghost,through)==='FUTURE'?' · future':''}</em></span>}
    </div>
    {draft&&<div className="alpha-scrub-confirm" role="group" aria-label="Confirm forward replay">
      <span>Go to <strong>{utcLabel(draft)}</strong></span>
      <button type="button" className="alpha-scrub-go" onClick={confirm}>Go</button>
      <button type="button" aria-label="Cancel forward replay" onClick={()=>setDraft(null)}>×</button>
    </div>}
  </div>;
}
