import {useEffect,useRef,useState} from 'react';
import {betaNotice,checkoutAddress,billingDuration,billingExpiry} from './betaWorkspace.js';

// Saved provider phases in plain words; unknown phases show the server value as is.
// Wording from canvas 17 "Payment states".
const PHASES={CREATED:['Checkout not finished','open'],CHECKOUT_STARTED:['Checkout not finished','open'],PENDING:['Waiting for Midtrans','open'],HOLD:['Under review','open'],
  PAID:['Paid','paid'],FAILED:['Payment didn’t go through','failed'],REVERSED:['Payment reversed','failed']};

export function Meter({label,value,max,suffix=''}){
  const pct=max>0?Math.min(100,Math.round(value*100/max)):0;
  return <div className="beta-meter"><div><span>{label}</span><span className="beta-mono">{value} / {max}{suffix}</span></div>
    <div role="meter" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}><i style={{width:Math.max(pct,3)+'%'}}/></div></div>;
}

export default function BetaBilling({client,onExpired}){
  const [data,setData]=useState(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[redirect,setRedirect]=useState(null),[uncertain,setUncertain]=useState(false);
  const live=useRef(true),flight=useRef(false);
  async function reload(){
    const [plan,orders]=await Promise.all([client.billingPlan(),client.billingOrders()]);
    const access=await client.billingAccess();
    if(plan.mode!=='SANDBOX'||orders.mode!=='SANDBOX'||access.mode!=='SANDBOX'||plan.fundsCollected!==false||orders.fundsCollected!==false||access.fundsCollected!==false||!Array.isArray(orders.orders)||!['FREE','PRO'].includes(access.tier))throw Error('Unsupported billing response');
    if(live.current)setData({plan,orders,access});
    return orders;
  }
  async function run(fn){
    if(flight.current)return;flight.current=true;setBusy(true);setNotice('');
    try{await fn();}catch(error){if(live.current){setNotice(error.reconciliationRequired?'Payment response was interrupted. Reload saved payments; do not start another checkout.':betaNotice(error));if(error.reconciliationRequired)setUncertain(true);if(!client.hasSession())onExpired();}}
    finally{flight.current=false;if(live.current)setBusy(false);}
  }
  useEffect(()=>{live.current=true;let active=true;void Promise.resolve().then(()=>{if(active)return run(reload);});return()=>{active=false;live.current=false;};
  // Account-scoped component remounts on identity changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[client]);
  const pending=data?.orders.orders.some(o=>['CREATED','CHECKOUT_STARTED','PENDING','HOLD'].includes(o.phase));
  return <section aria-label="Sandbox payments" className="beta-billing">
    <div className="beta-sandbox-banner"><strong>Sandbox</strong><span>Test payments only. No real funds are collected and nothing here is a live offer.</span></div>
    {!data&&!notice&&<p role="status" className="beta-loading">Loading your plan…</p>}
    {data&&<div className="beta-plan-grid">
      <section className={'beta-plan-current beta-plan-'+data.access.tier.toLowerCase()} aria-labelledby="beta-usage-h">
        <div className="beta-usage-head"><h2 id="beta-usage-h">Today on {data.access.tier==='PRO'?'Pro':'Free'}</h2><span>Resets 00:00 {data.access.resetTimezone}</span></div>
        <Meter label="Saved Sessions" value={data.access.savedSessions} max={data.access.savedLimit}/>
        {data.access.tier==='FREE'&&<Meter label="Replay window today" value={data.access.freeActivationAvailable?0:1} max={1} suffix=" used"/>}
        <p>Deleted Sessions stay in Trash for 30 days.</p></section>
      <div className="beta-plan-offer">
        <span className="beta-kicker">PRO · SANDBOX TEST PLAN</span>
        <strong className="beta-mono">IDR {data.plan.amountIdr}</strong><p>{billingDuration(data.plan.durationSeconds)} of Pro sandbox access. Amount set by the server; owner prices are still drafts and are not offered here.</p>
        <button className="beta-plan-buy" disabled={busy||uncertain||pending||data.orders.truncated||data.access.tier==='PRO'} onClick={()=>run(async()=>{
          const requestId=crypto.randomUUID();setUncertain(true);
          const result=await client.billingCheckout(requestId);
          const address=checkoutAddress(result.redirectUrl);
          if(live.current){setRedirect(address);setUncertain(false);}await reload();
        })}>Start sandbox checkout</button>
        {data.access.tier==='PRO'&&<p>You already have Pro sandbox access.</p>}
        {pending&&<p>A payment is still open. Check its saved status before starting another checkout.</p>}
        <p className="beta-plan-handoff">Payment opens in Midtrans. Pro starts only after our server confirms the payment, not when the tab closes.</p>
        {redirect&&<a className="beta-plan-redirect" href={redirect} target="_blank" rel="noopener noreferrer">Open secure Midtrans sandbox checkout</a>}
      </div></div>}
    <p role="status" aria-live="polite" className="beta-notice">{notice}</p>
    <div className="beta-list-head"><h2>Order history</h2><button disabled={busy} onClick={()=>run(async()=>{await reload();setUncertain(false);})}>Reload saved payments</button></div>
    {data&&(data.orders.orders.length?<ul className="beta-orders">{data.orders.orders.map(order=><li key={order.orderId}>
      <span className={'beta-phase beta-phase-'+(PHASES[order.phase]?.[1]??'open')}>{PHASES[order.phase]?.[0]??order.phase}</span>
      <span className="beta-order-main"><b className="beta-mono">IDR {order.amountIdr}</b><small className="beta-mono">{order.orderId}</small>
        {order.expiresAt&&<small>Access expires {billingExpiry(order.expiresAt)}</small>}</span>
      <span className="beta-order-actions">
        {order.phase==='CREATED'&&<button disabled={busy} onClick={()=>run(async()=>{setUncertain(true);const result=await client.billingResume(order.orderId);const address=checkoutAddress(result.redirectUrl);if(live.current){setRedirect(address);setUncertain(false);}await reload();})}>Resume unsubmitted checkout</button>}
        <button disabled={busy} onClick={()=>run(async()=>{await client.billingReconcile(order.orderId);await reload();setUncertain(false);setRedirect(null);})}>Check payment status</button></span></li>)}</ul>
      :<p className="beta-empty">No saved payments yet.</p>)}
    {data?.orders.truncated&&<p>Only 50 saved payments are shown. New checkout is disabled; contact support to review remaining payments.</p>}
  </section>;
}
