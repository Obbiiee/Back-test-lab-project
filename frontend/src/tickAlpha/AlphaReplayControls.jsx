import {useEffect,useRef,useState} from 'react';
import Icon from '../workspace/WorkspaceIcon.jsx';
import {replayTarget,seekTarget} from './display.js';
import {candleTarget,eventSignature,hasWatchedOrders,JUMP_MAX_CHUNKS,playbackTarget,SPEEDS,timeframeLabel,utcLabel,widenScale,PLAY_INTERVAL_MS} from './replay.js';
import {emitLocal} from './measurement.js';

// One replay control system. Every action is a backend ADVANCE/SEEK to a canonical UTC target;
// the backend reveals ticks and settles orders. At most one request is in flight (the parent
// single-flights `onAdvance`), and every timer/listener is released on cleanup.
export default function AlphaReplayControls({view,timeframe,busy,pauseToken,pending,onAdvance,onNotice}){
  const [playToken,setPlayToken]=useState(null),[rate,setRate]=useState(2),[activity,setActivity]=useState(''),[progress,setProgress]=useState('');
  const abort=useRef(null),seekInput=useRef(null),inFlight=useRef(false);
  const latest=useRef({view,onAdvance,timeframe,rate});
  useEffect(()=>{latest.current={view,onAdvance,timeframe,rate};},[view,onAdvance,timeframe,rate]);
  // Dialogs, timeframe changes and session switches pause playback: the parent bumps pauseToken.
  const playing=playToken===pauseToken,setPlaying=value=>setPlayToken(value?pauseToken:null);
  useEffect(()=>()=>{abort.current?.abort();},[]);
  const ended=view.state.ended,working=activity!=='';
  const nextCandle=candleTarget(view.state.throughNs,timeframe);
  const unresolvedTarget=pending&&BigInt(pending.target)>BigInt(view.state.throughNs)?pending:null;

  useEffect(()=>{
    if(!playing)return;
    let active=true,timer,scale=1n;
    const tick=async()=>{
      const current=latest.current;
      const before=current.view;
      const result=await current.onAdvance('ADVANCE',playbackTarget(before.state.throughNs,current.rate,scale),{});
      if(!active)return;
      if(result===undefined){timer=setTimeout(tick,PLAY_INTERVAL_MS);return;}
      if(!result||result.view.state.ended){setPlaying(false);if(result?.view.state.ended)onNotice('End of the dataset reached. Replay stopped.');return;}
      scale=widenScale(scale,result.view.state.nextGroupIndex!==before.state.nextGroupIndex,current.timeframe,current.rate);
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
  const stepTick=()=>guarded('step',async()=>{busyNotice(await onAdvance('ADVANCE',replayTarget(latest.current.view,1),{}));});
  const candle=()=>guarded('candle',async controller=>{
    const target=candleTarget(latest.current.view.state.throughNs,latest.current.timeframe);
    setProgress(`Revealing ticks to ${utcLabel(target)}…`);
    const result=busyNotice(await onAdvance('ADVANCE',target,{signal:controller.signal,onProgress:saved=>setProgress(`Revealed through ${utcLabel(saved.state.throughNs)}…`)}));
    if(result?.cancelled)onNotice('Cancelled. The replay cursor stays at the last committed position; use Continue to finish the same target.');
    else if(result&&!result.reached&&!result.view.state.ended)onNotice('The candle target was not reached; try Next candle again.');
  });
  const resume=()=>guarded('continue',async controller=>{
    const result=await onAdvance(unresolvedTarget.kind,unresolvedTarget.target,{signal:controller.signal,onProgress:saved=>setProgress(`Revealed through ${utcLabel(saved.state.throughNs)}…`)});
    if(result?.cancelled)onNotice('Cancelled again. The saved target is kept.');
  });
  const jump=()=>guarded('jump',async controller=>{
    let current=latest.current.view;const base=eventSignature(current);
    for(let index=0;index<JUMP_MAX_CHUNKS;index++){
      if(controller.signal.aborted){onNotice('Jump cancelled. Replay stays at the last committed cursor.');return;}
      const result=busyNotice(await onAdvance('ADVANCE',candleTarget(current.state.throughNs,latest.current.timeframe),{signal:controller.signal}));
      if(!result)return;
      if(result.cancelled){onNotice('Jump cancelled. Replay stays at the last committed cursor.');return;}
      current=result.view;setProgress(`${index+1} ${timeframeLabel(latest.current.timeframe)} candle(s) · ${utcLabel(current.state.throughNs)}`);
      if(eventSignature(current)!==base){onNotice('Trading event committed. Replay stopped at the end of that candle.');emitLocal('replay_advanced');return;}
      if(current.state.ended){onNotice('End of the dataset reached before any event.');return;}
    }
    onNotice('Jump limit reached with no event. Run Jump again to continue.');
  });
  const seek=()=>guarded('seek',async controller=>{
    let target;
    try{target=seekTarget(seekInput.current.value);}catch(error){onNotice(error.message);return;}
    const result=await onAdvance('SEEK',target,{signal:controller.signal,onProgress:saved=>setProgress(`Revealed through ${utcLabel(saved.state.throughNs)}…`)});
    if(result?.cancelled)onNotice('Seek cancelled. The saved target is kept; use Continue to finish it.');
  });

  // Space plays/pauses, Shift+→ steps one tick interval, N reveals the next candle. Ignored while
  // typing, inside dialogs or on interactive controls that own the key.
  const shortcut=useRef(null);
  useEffect(()=>{shortcut.current={playing,busy,ended,working,toggle,stepTick,candle};});
  useEffect(()=>{
    const onKey=event=>{
      const target=event.target,state=shortcut.current;
      if(event.defaultPrevented||event.ctrlKey||event.metaKey||event.altKey||state.ended||state.working)return;
      if(target.closest?.('input,textarea,select,button,a,summary,[contenteditable="true"],[role=dialog]')||document.querySelector('[role=dialog]'))return;
      if(event.code==='Space'&&!event.shiftKey){if(state.busy&&!state.playing)return;event.preventDefault();state.toggle();}
      else if(event.key==='ArrowRight'&&event.shiftKey){if(state.busy||state.playing)return;event.preventDefault();state.stepTick();}
      else if(event.key==='n'&&!event.shiftKey){if(state.busy||state.playing)return;event.preventDefault();state.candle();}
    };
    window.addEventListener('keydown',onKey);return()=>window.removeEventListener('keydown',onKey);
  },[]);

  const forming=view.chart.candles.at(-1)?.incomplete;
  const lock=busy||working||playing||ended;
  const tfLabel=timeframeLabel(timeframe);
  return <div className="alpha-replay-controls" role="group" aria-label="Tick replay controls" data-activity={activity||undefined}>
    <button type="button" className="alpha-replay-play" disabled={working||(busy&&!playing)||ended} aria-pressed={playing} aria-keyshortcuts="Space" title="Play / Pause (Space)" onClick={toggle}><Icon name="play"/><span>{playing?'Pause':'Play'}</span></button>
    <button type="button" disabled={lock} aria-keyshortcuts="Shift+ArrowRight" title={`Step tick (Shift+→): reveals one replay interval of observed quotes`} onClick={stepTick}>Step tick</button>
    <button type="button" disabled={lock} aria-keyshortcuts="N" title={`Next ${tfLabel} candle (N): reveals ticks up to ${utcLabel(nextCandle)} (UTC bucket end)`} onClick={candle}>Next {tfLabel}</button>
    <button type="button" disabled={lock||!hasWatchedOrders(view)} title={hasWatchedOrders(view)?'Advance candle by candle until a pending or open order changes. Stops at the end of the candle containing the event.':'Needs a pending or open order to wait for.'} onClick={jump}>Next event</button>
    {working&&activity!=='step'&&<button type="button" className="alpha-replay-cancel" onClick={()=>abort.current?.abort()}>Cancel</button>}
    {unresolvedTarget&&!working&&<button type="button" className="alpha-replay-continue" disabled={busy||playing} title={`Finish the saved ${unresolvedTarget.kind==='SEEK'?'seek':'advance'} to ${utcLabel(unresolvedTarget.target)}`} onClick={resume}>Continue saved</button>}
    <label className="alpha-replay-speed" title="Playback rate: market seconds revealed per real second while playing (one request per 0.5 s)">Speed<select aria-label="Replay speed" disabled={working||busy&&!playing} value={rate} onChange={event=>setRate(Number(event.target.value))}>{SPEEDS.map(value=><option key={value} value={value}>{value}×</option>)}</select></label>
    <details className="alpha-seek" onToggle={event=>{if(event.currentTarget.open&&seekInput.current)seekInput.current.value=new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,19);}}><summary>Go to time</summary><div><label>Seek (UTC)<input ref={seekInput} aria-label="Seek UTC" type="datetime-local" step="1" disabled={lock} defaultValue={new Date(Number(BigInt(view.state.throughNs)/1000000n)).toISOString().slice(0,19)}/></label><button type="button" disabled={lock} onClick={seek}>Seek replay</button><small>Forward only. Committed history cannot be rewound.</small></div></details>
    <span className="alpha-replay-time" role="status" aria-live="polite"><strong>{utcLabel(view.state.throughNs)}</strong> · {forming?`forming ${tfLabel}`:`${tfLabel} complete`}{working&&progress?` · ${progress}`:busy&&!working&&!playing?' · working…':playing?` · ${rate}× playing`:''}</span>
  </div>;
}
