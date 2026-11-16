import {useEffect,useRef,useState} from 'react';
import Icon from '../workspace/WorkspaceIcon.jsx';
import {replayTarget,seekTarget} from './display.js';
import {accountTransport} from './accountClient.js';
import {candleTarget,pendingTarget,playbackTarget,SPEEDS,timeframeLabel,utcLabel,widenScale,PLAY_INTERVAL_MS} from './replay.js';
import {emitLocal} from './measurement.js';
import AlphaReplayScrubber from './AlphaReplayScrubber.jsx';

// One replay control system. Every action is a forward ADVANCE/SEEK to a canonical UTC target (or the
// server's own jump-next-event); the backend reveals ticks and settles orders. The unfinished target is
// the server's (view.pendingReplayTargetNs), never the browser's. At most one request is in flight
// (the parent single-flights `onReplay`/`onJump`) and every timer/listener is released on cleanup.
const hostedObserved=view=>Boolean(accountTransport())&&view.metadata.artifact==='BTL-OBSERVED-RESEARCH-SESSION-1';

export default function AlphaReplayControls({view,timeframe,busy,pauseToken,onReplay,onJump,canJump,onNotice,onPan}){
  const [playToken,setPlayToken]=useState(null),[rate,setRate]=useState(2),[activity,setActivity]=useState(''),[progress,setProgress]=useState('');
  const abort=useRef(null),seekInput=useRef(null),inFlight=useRef(false);
  const latest=useRef({view,onReplay,timeframe,rate});
  useEffect(()=>{latest.current={view,onReplay,timeframe,rate};},[view,onReplay,timeframe,rate]);
  // Dialogs, timeframe changes and session switches pause playback: the parent bumps pauseToken.
  const playing=playToken===pauseToken,setPlaying=value=>setPlayToken(value?pauseToken:null);
  useEffect(()=>()=>{abort.current?.abort();},[]);
  const ended=view.state.ended,working=activity!=='';
  const pending=pendingTarget(view);
  const lock=busy||working||playing||ended||Boolean(pending);
  const tfLabel=timeframeLabel(timeframe);
  const nextCandle=candleTarget(view.state.throughNs,timeframe);

  // Forward to `target`, repeating the SAME target while the server reports it as unfinished.
  // Hosted observed Sessions use the server-side replay-to path (SEEK) in one bounded call.
  const advanceTo=async(target,{signal,onProgress}={})=>{
    let before=latest.current.view;
    for(let attempt=0;attempt<1000;attempt++){
      const result=await latest.current.onReplay(hostedObserved(before)?'SEEK':'ADVANCE',target);
      if(result===undefined||!result)return result;
      onProgress?.(result.view);
      if(result.reached||result.view.state.ended)return result;
      if(!result.revealed)return {...result,stalled:true};
      if(signal?.aborted)return {...result,cancelled:true};
      before=result.view;
    }
    return {view:before,reached:false,limit:true};
  };

  useEffect(()=>{
    if(!playing)return;
    let active=true,timer,scale=1n;
    const tick=async()=>{
      const current=latest.current,before=current.view;
      const unfinished=pendingTarget(before);
      const target=unfinished?unfinished.target:playbackTarget(before.state.throughNs,current.rate,scale);
      const result=await current.onReplay('ADVANCE',target);
      if(!active)return;
      if(result===undefined){timer=setTimeout(tick,PLAY_INTERVAL_MS);return;}
      if(!result||result.view.state.ended){setPlayToken(null);if(result?.view.state.ended)onNotice('End of the dataset reached. Replay stopped.');return;}
      scale=widenScale(scale,result.revealed,current.timeframe,current.rate);
      timer=setTimeout(tick,PLAY_INTERVAL_MS);
    };
    timer=setTimeout(tick,PLAY_INTERVAL_MS);
    return()=>{active=false;clearTimeout(timer);};
  // The loop reads fresh values through `latest`; only play/speed restart it.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[playing,rate]);

  const toggle=()=>{emitLocal(playing?'replay_paused':'replay_started');setPlaying(!playing);};
  const guarded=async(name,work)=>{
    if(working||inFlight.current)return;
    inFlight.current=true;
    const controller=new AbortController();abort.current=controller;
    setPlaying(false);setActivity(name);setProgress('');
    try{await work(controller);}finally{abort.current=null;inFlight.current=false;setActivity('');}
  };
  const busyNotice=result=>{if(result===undefined)onNotice('Another request is still running. Try again in a moment.');return result;};
  const showProgress=saved=>setProgress(`Revealed through ${utcLabel(saved.state.throughNs)}…`);
  const finish=(result,savedMessage)=>{
    if(result?.cancelled)onNotice(savedMessage);
    else if(result?.stalled)onNotice('No further quote was revealed toward this target. Replay paused; use Continue saved replay or try again.');
    else if(result?.limit)onNotice('The target needs more steps than one click allows. Committed progress is saved; use Continue saved replay.');
  };
  const stepTick=()=>guarded('step',async()=>{busyNotice(await latest.current.onReplay('ADVANCE',replayTarget(latest.current.view,1)));});
  const candle=()=>guarded('candle',async controller=>{
    const target=candleTarget(latest.current.view.state.throughNs,latest.current.timeframe);
    setProgress(`Revealing ticks to ${utcLabel(target)}…`);
    finish(busyNotice(await advanceTo(target,{signal:controller.signal,onProgress:showProgress})),'Cancelled. The replay cursor stays at the last committed position; use Continue saved replay to finish the same target.');
  });
  const resume=()=>guarded('continue',async controller=>{
    finish(busyNotice(await advanceTo(pending.target,{signal:controller.signal,onProgress:showProgress})),'Cancelled again. The saved target is kept.');
  });
  const jump=()=>guarded('jump',async controller=>{
    const found=busyNotice(await onJump({view:latest.current.view,cancelled:()=>controller.signal.aborted,
      onProgress:value=>setProgress(`Searching · ${utcLabel(value.throughNs)} · ${value.processedGroups} tick groups in this step`)}));
    if(controller.signal.aborted&&found?.status==='SEARCHING')onNotice('Search stopped after the current committed chunk. Session progress is saved; press Jump to Next Event to continue.');
  });
  const seekTo=target=>guarded('seek',async controller=>{
    finish(busyNotice(await advanceTo(target,{signal:controller.signal,onProgress:showProgress})),'Seek cancelled. The saved target is kept; use Continue saved replay to finish it.');
  });
  const seek=()=>{
    try{seekTo(seekTarget(seekInput.current.value));}catch(error){onNotice(error.message);}
  };

  // Space plays/pauses, Shift+→ steps one tick interval, N reveals the next candle. Ignored while
  // typing, inside dialogs or on interactive controls that own the key.
  const shortcut=useRef(null);
  useEffect(()=>{shortcut.current={playing,busy,ended,working,pending:Boolean(pending),toggle,stepTick,candle};});
  useEffect(()=>{
    const onKey=event=>{
      const target=event.target,state=shortcut.current;
      if(event.defaultPrevented||event.ctrlKey||event.metaKey||event.altKey||state.ended||state.working)return;
      if(target.closest?.('input,textarea,select,button,a,summary,[contenteditable="true"],[role=dialog]')||document.querySelector('[role=dialog]'))return;
      if(event.code==='Space'&&!event.shiftKey){if((state.busy||state.pending)&&!state.playing)return;event.preventDefault();state.toggle();}
      else if(event.key==='ArrowRight'&&event.shiftKey){if(state.busy||state.playing)return;event.preventDefault();state.stepTick();}
      else if(event.key==='n'&&!event.shiftKey){if(state.busy||state.playing||state.pending)return;event.preventDefault();state.candle();}
    };
    window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey);
  },[]);

  const forming=view.chart.candles.at(-1)?.incomplete;
  const scrubber=<AlphaReplayScrubber view={view} timeframe={timeframe} pending={pending} locked={lock} onPan={onPan} onSeek={seekTo}/>;
  return <>
  <div className="alpha-replay-strip" role="group" aria-label="Tick replay controls" data-activity={activity||undefined}>
    <button type="button" className="alpha-replay-play" aria-label={playing?'Pause replay':'Play replay'} disabled={working||(busy&&!playing)||ended||(Boolean(pending)&&!playing)} aria-pressed={playing} aria-keyshortcuts="Space" title="Play / Pause (Space)" onClick={toggle}><Icon name="play"/><span>{playing?'Pause':'Play'}</span></button>
    <button type="button" aria-label="Step ticks" disabled={lock} aria-keyshortcuts="Shift+ArrowRight" title="Step tick (Shift+→): reveals one replay interval of observed quotes" onClick={stepTick}>Step tick</button>
    <button type="button" aria-label={`Next ${tfLabel} candle`} disabled={lock} aria-keyshortcuts="N" title={`Next ${tfLabel} candle (N): reveals ticks up to ${utcLabel(nextCandle)} (UTC bucket end)`} onClick={candle}>Next {tfLabel}</button>
    {working&&activity==='jump'?<button type="button" className="alpha-replay-cancel" aria-label="Cancel search" onClick={()=>abort.current?.abort()}>Cancel</button>
      :<button type="button" aria-label="Jump to Next Event" disabled={lock||!canJump} title={canJump?'Process committed tick groups until the next trading event':'Add a pending or active order to search for its next event'} onClick={jump}>Next event</button>}
    {working&&activity!=='step'&&activity!=='jump'&&<button type="button" className="alpha-replay-cancel" onClick={()=>abort.current?.abort()}>Cancel</button>}
    {pending&&!working&&<button type="button" className="alpha-replay-continue" aria-label="Continue saved replay" disabled={busy||playing} title={`Finish the saved target ${utcLabel(pending.target)}`} onClick={resume}>Continue</button>}
    <label className="alpha-replay-speed" title="Playback rate: market seconds revealed per real second while playing (one request per 0.5 s)">Speed<select aria-label="Replay speed" disabled={working||busy&&!playing} value={rate} onChange={event=>setRate(Number(event.target.value))}>{SPEEDS.map(value=><option key={value} value={value}>{value}×</option>)}</select></label>
    <details className="alpha-seek" onToggle={event=>{if(event.currentTarget.open&&seekInput.current)seekInput.current.value=new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,19);}}><summary>Go to time</summary><div><label>Seek (UTC)<input ref={seekInput} aria-label="Seek UTC" type="datetime-local" step="1" disabled={lock} defaultValue={new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,19)}/></label><button type="button" disabled={lock} onClick={seek}>Seek replay</button><small>Forward only. Committed history cannot be rewound.</small></div></details>
    <div className="alpha-scrub-inline">{scrubber}</div>
    <span className="alpha-replay-time" role="status" aria-live="polite"><strong>{utcLabel(view.state.throughNs)}</strong> · {forming?`forming ${tfLabel}`:`${tfLabel} complete`}{pending&&!working?' · saved target pending':''}{working&&progress?` · ${progress}`:busy&&!working&&!playing?' · working…':playing?` · ${rate}× playing`:''}</span>
  </div>
  <div className="alpha-scrub-row">{scrubber}</div>
  </>;
}
