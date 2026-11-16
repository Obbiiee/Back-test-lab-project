import {useEffect} from 'react';
import {durationLabel} from './replay.js';
import {stamp} from './display.js';

// Announces a committed fill or exit. Values are the server's strings; the sign colour is
// presentation only. Auto-dismisses; the Journal and terminal remain the record.
export default function AlphaTradeToast({event,onDismiss}){
  useEffect(()=>{
    if(!event)return;
    const timer=setTimeout(onDismiss,9000);
    return()=>clearTimeout(timer);
  },[event,onDismiss]);
  if(!event)return null;
  const {order,kind}=event;
  const long=order.side==='LONG';
  if(kind==='FILL')return <div className="alpha-toast is-fill" role="status" aria-live="polite">
    <strong>{long?'Long':'Short'} filled</strong><span>@ {order.entryPrice} · {order.quantity} lots</span>
    <small>{order.entryTimeNs?stamp(order.entryTimeNs).replace('T',' ').replace(/\.\d+Z$/,' UTC'):''} · observed {long?'Ask':'Bid'} tick</small>
    <button type="button" aria-label="Dismiss trade message" onClick={onDismiss}>×</button>
  </div>;
  const net=Number(order.net),tone=net>0?'is-win':net<0?'is-loss':'is-flat';
  const held=durationLabel(order.durationNs);
  return <div className={`alpha-toast ${tone}`} role="status" aria-live="polite">
    <strong>{long?'Long':'Short'} closed · {order.exitReason??'exit'}</strong>
    <span className="alpha-toast-net">Net {order.net} USD</span>
    <small>{order.entryPrice} → {order.exitPrice}{held?` · held ${held}`:''}</small>
    <button type="button" aria-label="Dismiss trade message" onClick={onDismiss}>×</button>
  </div>;
}
