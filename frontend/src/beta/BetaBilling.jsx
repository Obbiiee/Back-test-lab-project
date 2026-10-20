import {useEffect,useRef,useState} from 'react';
import {betaNotice,checkoutAddress,billingDuration,billingExpiry} from './betaWorkspace.js';

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
  return <section aria-label="Sandbox payments"><h2>Plan and payments</h2><p>Sandbox only. No real funds are collected.</p>
    <button disabled={busy} onClick={()=>run(async()=>{await reload();setUncertain(false);})}>Reload saved payments</button>
    {data&&<><p>Current access: <strong>{data.access.tier}</strong> · reset {data.access.resetTimezone}</p><p>Sandbox offer: IDR {data.plan.amountIdr} · {billingDuration(data.plan.durationSeconds)}.</p>
    <button disabled={busy||uncertain||pending||data.orders.truncated||data.access.tier==='PRO'} onClick={()=>run(async()=>{
      const requestId=crypto.randomUUID();setUncertain(true);
      const result=await client.billingCheckout(requestId);
      const address=checkoutAddress(result.redirectUrl);
      if(live.current){setRedirect(address);setUncertain(false);}await reload();
    })}>Start sandbox checkout</button>
    {pending&&<p>A payment is still open. Check its saved status before starting another checkout.</p>}
    {redirect&&<p><a href={redirect} target="_blank" rel="noopener noreferrer">Open secure Midtrans sandbox checkout</a></p>}
    <ul>{data.orders.orders.map(order=><li key={order.orderId}><strong>{order.phase}</strong> · IDR {order.amountIdr} · {order.orderId}
      {order.expiresAt&&<span> · access expires: {billingExpiry(order.expiresAt)}</span>}
      {order.phase==='CREATED'&&<button disabled={busy} onClick={()=>run(async()=>{setUncertain(true);const result=await client.billingResume(order.orderId);const address=checkoutAddress(result.redirectUrl);if(live.current){setRedirect(address);setUncertain(false);}await reload();})}>Resume unsubmitted checkout</button>}
      <button disabled={busy} onClick={()=>run(async()=>{await client.billingReconcile(order.orderId);await reload();setUncertain(false);setRedirect(null);})}>Check payment status</button></li>)}</ul>
    {data.orders.truncated&&<p>Only 50 saved payments are shown. New checkout is disabled; contact support to review remaining payments.</p>}</>}
    <p role="status" aria-live="polite">{notice}</p></section>;
}
