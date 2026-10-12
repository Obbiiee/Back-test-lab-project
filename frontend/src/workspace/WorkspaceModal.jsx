import usePopupFocus from './usePopupFocus.js';
import {useState} from 'react';
export default function WorkspaceModal({ label, onClose, children, returnFocusRef, movable=false }) {
  const ref = usePopupFocus(onClose, true, returnFocusRef);
  const [floating,setFloating]=useState(false),[offset,setOffset]=useState({x:0,y:0});
  const move=event=>{
    if(!floating||event.button!==0)return;
    const target=event.currentTarget;
    const point={x:event.clientX,y:event.clientY};
    target.setPointerCapture(event.pointerId);
    target.onpointermove=next=>{
      const panel=target.parentElement.parentElement.getBoundingClientRect();
      const dx=Math.max(8-panel.left,Math.min(innerWidth-8-panel.right,next.clientX-point.x));
      const dy=Math.max(8-panel.top,Math.min(innerHeight-48-panel.top,next.clientY-point.y));
      point.x=next.clientX;point.y=next.clientY;
      setOffset(current=>({x:current.x+dx,y:current.y+dy}));
    };
    target.onpointerup=target.onpointercancel=()=>{target.onpointermove=null;target.onpointerup=null;target.onpointercancel=null;};
  };
  return <div ref={ref} className={`dialog-backdrop${movable?' alpha-movable-modal':''}`} role="dialog" aria-modal="true" aria-label={label}>{movable?<div className={`alpha-panel-surface ${floating?'is-floating':'is-docked'}`} style={floating?{transform:`translate(${offset.x}px, ${offset.y}px)`}:undefined}><div className="alpha-panel-handle"><button type="button" aria-label={`Move ${label}`} disabled={!floating} onPointerDown={move} onKeyDown={event=>{const delta={ArrowLeft:[-10,0],ArrowRight:[10,0],ArrowUp:[0,-10],ArrowDown:[0,10]}[event.key];if(delta){event.preventDefault();const rect=event.currentTarget.parentElement.parentElement.getBoundingClientRect();setOffset(current=>({x:current.x+Math.max(8-rect.left,Math.min(innerWidth-8-rect.right,delta[0])),y:current.y+Math.max(8-rect.top,Math.min(innerHeight-48-rect.top,delta[1]))}));}}} title="Drag or use arrow keys">⠿</button><span>{label}</span><button type="button" onClick={()=>{setFloating(!floating);setOffset({x:0,y:0});}}>{floating?'Dock panel':'Float panel'}</button></div>{children}</div>:children}</div>;
}
