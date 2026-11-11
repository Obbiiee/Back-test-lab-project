// QA-only recovery for a duplicate Confirm request rejected before API
// admission. The same URL, bearer token, and command payload must be reused.
export async function retryExactConfirm({send, onResponse=()=>{}, sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms)),
  now=()=>performance.now(), random=Math.random, deadlineMs=30000, maxRetries=8}){
  const started=now();
  for(let attempt=0;attempt<=maxRetries;attempt++){
    const remaining=deadlineMs-(now()-started);
    if(remaining<=0)throw Object.assign(Error('EXACT_CONFIRM_RETRY_DEADLINE'),{code:'SERVICE_BUSY'});
    const began=performance.now();
    // send bounds its transport operation by the remaining request budget.
    // A rejected/ambiguous transport promise is deliberately not retried.
    const response=await send({timeoutMs:remaining});
    const body=await response.json();
    const status=response.status();
    const detail=typeof body?.detail==='string'&&/^[A-Z][A-Z0-9_]{2,80}$/.test(body.detail)?body.detail:null;
    onResponse({status,code:detail,durationMs:Math.max(0,performance.now()-began)});
    if(status===200)return {response,body};
    const preAdmissionBusy=(status===503&&detail==='SERVICE_BUSY')||
      (status===429&&detail==='RESEARCH_BUSY');
    if(!preAdmissionBusy||attempt===maxRetries)
      throw Object.assign(Error('EXACT_CONFIRM_RETRY_REFUSED'),{status,code:detail});
    const retryAfter=response.headers()['retry-after'];
    const seconds=retryAfter===undefined?0:Number(retryAfter);
    if(!Number.isFinite(seconds)||seconds<0||seconds>5)
      throw Object.assign(Error('EXACT_CONFIRM_RETRY_DELAY_REFUSED'),{status,code:detail});
    const serverDelay=Math.min(3000,seconds*1000);
    const backoff=Math.min(800,50*2**attempt);
    const delay=Math.max(serverDelay,backoff)+Math.floor(random()*25);
    if(now()-started+delay>=deadlineMs)
      throw Object.assign(Error('EXACT_CONFIRM_RETRY_DEADLINE'),{status,code:detail});
    await sleep(delay);
  }
  throw Error('EXACT_CONFIRM_RETRY_EXHAUSTED');
}
