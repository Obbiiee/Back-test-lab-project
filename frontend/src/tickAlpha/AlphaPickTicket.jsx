import {useEffect,useRef} from 'react';
import {pickedPrice} from './planningIntent.js';

// Pick-from-chart mini ticket (C-14). A tap or click on the chart with "Pick order
// price" active proposes one price; the person chooses which planning field it
// fills. It only edits the draft: nothing is reviewed or sent from here, and the
// next step is still the order panel → server Review → Confirm.
export default function AlphaPickTicket({price,tickSize,plan,protocol,onApply,onCancel}){
  const ref=useRef(null);
  const value=pickedPrice(price,tickSize);
  const planned=protocol||plan.workflow==='PLANNED';
  // Quick drafts are Market-only with no stop/target, so using a price moves the
  // draft to Plan · R:R (Limit), exactly as the Workflow switch in the order panel does.
  const toPlan=!planned;
  const base=toPlan?{workflow:'PLANNED',orderType:'LIMIT'}:{};
  const marketEntry=planned&&!protocol&&plan.orderType==='MARKET';
  const fields=[
    {key:'entry',label:'Entry',patch:{...base,...(marketEntry?{orderType:'LIMIT'}:{}),entry:value}},
    {key:'sl',label:'Stop loss',patch:{...base,sl:value}},
    {key:'tp',label:'Take profit',patch:{...base,tp:value},reason:protocol?'Protocol sets the target from the Method R:R.':null},
  ];
  const note=toPlan?'Using a price switches this draft from Quick to Plan · R:R (Limit). Quantity then follows the risk rule.'
    :marketEntry?'Entry switches this draft from Market to Limit.':null;
  useEffect(()=>{ref.current?.querySelector('button:not(:disabled)')?.focus();},[price]);
  return <div ref={ref} className="alpha-pick-ticket" role="dialog" aria-label="Use picked price" aria-describedby="alpha-pick-help"
    onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();onCancel();}}}>
    <div className="alpha-pick-head"><span>Picked price</span><strong className="alpha-pick-price">{value??'Unavailable'}</strong></div>
    <p id="alpha-pick-help" className="alpha-pick-help">{value?'Use it for one field of the draft. Nothing is sent until you review and confirm.':'This price cannot be placed on the Session price grid. Enter it in the order panel instead.'}</p>
    <div className="alpha-pick-actions" role="group" aria-label="Use as">
      {fields.map(field=><button key={field.key} type="button" disabled={!value||Boolean(field.reason)} onClick={()=>onApply(field.key,field.patch)}>{field.label}</button>)}
      <button type="button" className="alpha-pick-cancel" onClick={onCancel}>Cancel</button>
    </div>
    {value&&(note||fields.some(field=>field.reason))&&<ul className="alpha-pick-reasons">{note&&<li>{note}</li>}{fields.filter(field=>field.reason).map(field=><li key={field.key}><strong>{field.label}:</strong> {field.reason}</li>)}</ul>}
  </div>;
}
