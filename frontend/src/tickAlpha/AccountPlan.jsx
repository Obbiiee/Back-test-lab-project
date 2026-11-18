import {useEffect,useState} from 'react';
import {isPaymentRedirect,planOffer,planSummary} from './accountPlan.js';

// Plan panel: shows Free/Pro, quota use and the Pro offer (price in Rupiah, one period per payment, no auto-renewal). The server decides everything;
// this component only displays it and opens the hosted payment page returned by the server.
export default function AccountPlan({client,workspace,billingConfigured}){
  const [status,setStatus]=useState(null),[offer,setOffer]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const workspaceId=workspace?.id;
  useEffect(()=>{
    if(!workspaceId)return undefined;
    let live=true;
    (async()=>{
      try{const value=await client.request(`/api/v1/workspaces/${workspaceId}/research/entitlements`);if(live)setStatus(planSummary(value));}catch{if(live)setStatus({known:false});}
      if(billingConfigured){try{const value=await client.request('/api/v1/billing/sandbox/plan');if(live)setOffer(planOffer(value));}catch{if(live)setOffer(null);}}
    })();
    return()=>{live=false;};
  },[client,workspaceId,billingConfigured]);
  async function buy(){
    if(busy)return;
    setBusy(true);setError('');
    try{
      const result=await client.request('/api/v1/billing/sandbox/checkout',{method:'POST',body:{requestId:crypto.randomUUID().replaceAll('-','')}});
      if(!isPaymentRedirect(result?.redirectUrl)){setError('The payment page address was not recognised, so nothing was opened. Please contact support.');return;}
      window.location.assign(result.redirectUrl);
    }catch(failure){setError(failure.message||'Payment could not be started.');}
    finally{setBusy(false);}
  }
  if(!workspace)return null;
  const quota=item=>item.limit===null?'no limit':`${item.used??'?'} of ${item.limit} used`;
  return <section className="rk-auth-plan" aria-labelledby="rk-plan-h">
    <h3 id="rk-plan-h">Plan</h3>
    {status?.known?<>
      <p>You are on <strong>{status.pro?'Pro':'Free'}</strong>.</p>
      {status.pro
        ?<p className="rk-auth-hint">Pro has no quota on new Sessions or newly activated historical months.</p>
        :<ul className="rk-auth-hint">
          <li>New Sessions today (UTC): {quota(status.sessions)}.</li>
          <li>New historical months today (UTC): {quota(status.windows)}.</li>
          <li>Continuing a Session or re-using an activated month uses no quota. Quotas reset at 00:00 UTC (07:00 WIB).</li>
        </ul>}
    </>:<p className="rk-auth-hint">Your plan could not be loaded right now.</p>}
    {status?.known&&!status.pro&&offer&&<>
      <p><strong>Pro: {offer.price}</strong> for {offer.days} days. One period per payment; it does not renew automatically.</p>
      {offer.testMode&&<p className="rk-auth-hint">Test mode: no money is collected.</p>}
      <button type="button" className="rk-auth-btn rk-auth-primary" disabled={busy} onClick={buy}>{busy?'Opening payment…':'Buy Pro'}</button>
      <p className="rk-auth-hint">Payments are processed by Midtrans. RIKSORA does not store your card details.</p>
    </>}
    {error&&<p role="alert" className="rk-auth-error">{error}</p>}
  </section>;
}
