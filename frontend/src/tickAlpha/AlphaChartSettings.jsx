import {useEffect,useId,useRef,useState} from 'react';
import Icon from '../workspace/WorkspaceIcon.jsx';

// One "Chart settings" popover replaces the always-visible Fit chart button, Grid
// checkbox, disabled Volume button and the phone Full screen button (progressive
// disclosure). Nothing here touches orders or financial state; it only changes
// local chart presentation preferences.
export default function AlphaChartSettings({preferences,onPreferences,onFit,volumeAvailable=false,fullscreen,onFullscreen,onOpen}){
  const [open,setOpen]=useState(false);
  const panelId=useId();
  const wrap=useRef(null),trigger=useRef(null);
  useEffect(()=>{
    if(!open)return undefined;
    const outside=event=>{if(wrap.current&&!wrap.current.contains(event.target))setOpen(false);};
    document.addEventListener('pointerdown',outside);
    return()=>document.removeEventListener('pointerdown',outside);
  },[open]);
  const close=()=>{setOpen(false);trigger.current?.focus();};
  const toggle=key=>onPreferences(value=>({...value,[key]:!value[key]}));
  return <div className="alpha-chart-settings" ref={wrap} onKeyDown={event=>{if(event.key==='Escape'&&open){event.stopPropagation();close();}}}>
    <button ref={trigger} type="button" className="alpha-chart-settings-trigger" aria-haspopup="dialog" aria-expanded={open} aria-controls={open?panelId:undefined} title="Chart settings"
      onClick={()=>{if(!open)onOpen?.();setOpen(value=>!value);}}><Icon name="settings"/><span>Chart</span></button>
    {open&&<div className="alpha-chart-settings-panel" id={panelId} role="dialog" aria-label="Chart settings">
      <button type="button" className="alpha-settings-row" onClick={()=>{onFit();close();}}><Icon name="expand"/><span>Fit chart to data</span></button>
      <label className="alpha-settings-switch"><span>Grid lines</span><input type="checkbox" role="switch" checked={Boolean(preferences.showGrid)} onChange={()=>toggle('showGrid')}/></label>
      <label className="alpha-settings-switch"><span>Crosshair</span><input type="checkbox" role="switch" checked={Boolean(preferences.showCrosshair)} onChange={()=>toggle('showCrosshair')}/></label>
      <label className="alpha-settings-switch" title={volumeAvailable?undefined:'This source has no exchange volume; tick count is not volume.'}><span>Volume{volumeAvailable?'':<small>Not available for this source</small>}</span><input type="checkbox" role="switch" disabled={!volumeAvailable} checked={Boolean(volumeAvailable&&preferences.showVolume)} onChange={()=>toggle('showVolume')}/></label>
      {onFullscreen&&<button type="button" className="alpha-settings-row alpha-touch-only" aria-pressed={fullscreen} onClick={()=>{onFullscreen();close();}}><Icon name="expand"/><span>{fullscreen?'Exit full screen':'Full screen chart'}</span></button>}
    </div>}
  </div>;
}
