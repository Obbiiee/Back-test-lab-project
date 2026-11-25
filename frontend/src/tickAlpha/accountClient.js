import {clearShellCache} from '../pwa.js';
// Existing same-origin HTTPS identity. Bearer tokens live only in this closure.
// Server refusals of the Free plan limits and the Free window boundary: say what is limited and when it resets (all times UTC).
const RESET_FORMAT={year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC',timeZoneName:'short'};
export function entitlementRefusal(body){
  const code=body?.detail;
  const at=typeof body?.resetsAt==='string'&&!Number.isNaN(Date.parse(body.resetsAt))?new Date(body.resetsAt).toLocaleString('en',RESET_FORMAT):null;
  const messages={
    SESSION_DAY_LIMIT:`Free plan: one new Session per day (UTC), each using one month of data. Pro has no limit.${at?` Your next Session is available from ${at}.`:''} Existing Sessions stay open.`,
    WINDOW_DAY_LIMIT:`Free plan: one newly opened historical month per day (UTC).${at?` Another month can be opened from ${at}.`:''} Continuing a month you already opened is free.`,
    ACTIVATION_IN_PROGRESS:'Another Session is still being created. Wait a moment and check your Sessions before trying again.',
    WINDOW_ENDED:'This Free window has ended: new orders cannot be opened. Open positions can still be resolved. Pro has no one-month window limit.',
    WINDOW_BOUNDARY:'This step would cross the end of your Free window. Step to the last tick of the window instead. Pro has no one-month window limit.',
    WINDOW_ENDED_CONTINUATION_ONLY:'This Free window has ended. Replay cannot continue past it. Cancel and End remain available, open positions stay open, and results stay visible. Pro has no one-month window limit.',
    WINDOW_CLOSE_REFUSED:'Close is not available after the end of this Free window: the position stays open and replay cannot continue. Cancel pending orders or End the Session. A new month needs a new Free Session.',
    CHART_CONTEXT_PRO_ONLY:'Candles from before this month are part of Pro. Your Free Session shows the month you opened.',
    PENDING_AT_WINDOW_END:'A pending order is still waiting at the end of your Free window. Cancel it. Replay cannot continue past the window.',
    WINDOW_COMPLETED:'This Free window has ended: replay cannot continue past it. Results and statistics stay visible; open positions stay open until you close them.',
    TRASH_EXPIRED:'The 30-day restore window for this Session has passed.',
    REFUSED_DATASET_VERSION:'This Session was created on an earlier version of the market data and cannot be replayed on the current one. Its Journal and results stay as they were. Create a new Session to keep testing.',
  };
  return messages[code]?{code,message:messages[code]}:null;
}
export function createAccountClient({fetcher=fetch,secure=()=>window.location.protocol==='https:',onExpired=()=>{}}={}){
  let token=null,subject=null,generation=0;
  const waitRetry=(milliseconds,signal)=>{
    if(signal.aborted)return Promise.reject(signal.reason);
    return new Promise((resolve,reject)=>{
      const onAbort=()=>{clearTimeout(timer);reject(signal.reason);};
      const timer=setTimeout(()=>{signal.removeEventListener('abort',onAbort);resolve();},milliseconds);
      signal.addEventListener('abort',onAbort,{once:true});
    });
  };
  async function request(path,{method='GET',body,form=false,authenticated=true,signal,jobId,as='json'}={}){
    if(!secure())throw Error('Account access requires HTTPS. The private local workspace remains separate.');
    if(!/^\/api\/v1\/(auth|workspaces)(\/|$)/.test(path))throw Error('Unsupported account route');
    if(authenticated&&!token)throw Error('Sign in to continue.');
    const current=generation;
    // Product research callers pass the already-bounded durable-operation
    // deadline (queue TTL + worker budget + observation margin). Applying a
    // second, shorter 30 s timer here caused an admitted read to be aborted
    // while it safely waited through explicit RESEARCH_BUSY backpressure.
    const boundedSignal=signal??AbortSignal.timeout(30000);
    let response,rejected,retries=0;
    while(true){
      response=await fetcher(path,{method,cache:'no-store',credentials:'omit',signal:boundedSignal,
        headers:{...(authenticated?{Authorization:`Bearer ${token}`} : {}),...(jobId?{'X-BTL-Job':jobId}:{}),...(body===undefined?{}:{'Content-Type':form?'application/x-www-form-urlencoded':'application/json'})},
        ...(body===undefined?{}:{body:form?new URLSearchParams(body).toString():JSON.stringify(body)})});
      if(current!==generation)throw Error('Account changed; this response was discarded.');
      if(response.ok)break;
      rejected=await Promise.resolve().then(()=>response.json()).catch(()=>null);
      const code=['RESEARCH_BUSY','QUEUE_CAPACITY','SERVICE_BUSY'].includes(rejected?.detail)?rejected.detail:undefined;
      // These codes are emitted before request work is accepted: the outer
      // API budget rejects before routing, research admission rejects before
      // execution, and queue.submit checks capacity before inserting a job.
      // Retrying those explicit no-op refusals is safe with the same job ID;
      // ambiguous transport failures are never retried here.
      // Queue capacity is a definitive pre-insert refusal (queue.submit checks
      // the same X-BTL-Job before admission). Keep that ID stable while a slot
      // frees; never apply this retry to transport errors or stale revisions.
      const retryLimit=code==='QUEUE_CAPACITY'?45:8;
      if(['RESEARCH_BUSY','SERVICE_BUSY','QUEUE_CAPACITY'].includes(code)&&retries<retryLimit){
        // These responses are explicit pre-admission refusals. Honor the
        // server's bounded Retry-After hint so a committed command's read-only
        // refresh can recover after a busy cohort without replaying a write.
        const retryAfter=Number(response.headers?.get?.('Retry-After'));
        const serverDelay=Number.isFinite(retryAfter)?Math.min(3000,Math.max(0,retryAfter*1000)):0;
        const delay=Math.max(serverDelay,Math.min(800,50*2**retries))+Math.floor(Math.random()*25);
        retries++;
        await waitRetry(delay,boundedSignal);
        if(current!==generation)throw Error('Account changed; this response was discarded.');
        continue;
      }
      if(response.status===401){const had=token!==null;token=null;subject=null;generation++;if(had&&authenticated)onExpired();}
      // Never surface rejected payloads/passwords/tokens or raw server errors.
      const entitlement=response.status===409?entitlementRefusal(rejected):null;
      if(entitlement)throw Object.assign(Error(entitlement.message),{status:409,code:entitlement.code});
      throw Object.assign(Error(({400:'The request was refused. Check your details and verification.',401:'Sign in again.',403:'This action is not permitted.',404:'This workspace or record is unavailable.',409:'The saved record changed. Reload before retrying.',422:'Check the supplied fields.',426:'Account access requires HTTPS.',429:'The service is busy. Wait and retry.'})[response.status]||'Account service unavailable.'),{status:response.status,...(code?{code}:{})});
    }
    const value=response.status===204?null:as==='text'?await response.text():as==='blob'?await response.blob():await response.json();
    if(current!==generation)throw Error('Account changed; this response was discarded.');
    return value;
  }
  return {
    request,
    async completeGoogleLogin(){
      const response=await fetcher('/api/v1/auth/google/exchange',{method:'POST',cache:'no-store',credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-BTL-Google-Exchange':'1'},body:'{}'});
      if(!response.ok)throw Error('Google sign-in could not be completed. Start again.');
      const result=await response.json();
      // The backend returns the standard bearer login body (no schemaVersion), the same shape the password login accepts below.
      if(typeof result?.access_token!=='string'||result.token_type!=='bearer')
        throw Error('Unsupported Google sign-in response.');
      token=result.access_token;generation++;
      const me=await request('/api/v1/auth/me');
      if(!validUuid(me?.id)||me.is_verified!==true||me.is_active!==true){token=null;throw Error('Verified account required.');}
      subject=me.id;return me;
    },
    async startGoogleLink(password){
      if(!token)throw Error('Sign in again before connecting Google.');
      const response=await fetcher('/api/v1/auth/google/link/start',{method:'POST',cache:'no-store',credentials:'same-origin',
        headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json','X-BTL-Google-Link':'1'},body:JSON.stringify({password})});
      if(!response.ok)throw Error(({401:'Sign in again.',403:'Password confirmation failed or Google linking is unavailable.',429:'The service is busy. Wait and retry.'})[response.status]||'Could not start Google linking.');
      const result=await response.json();
      if(result?.schemaVersion!==1||typeof result.authorizationUrl!=='string'||!result.authorizationUrl.startsWith('https://accounts.google.com/'))
        throw Error('Unsupported Google linking response.');
      return result.authorizationUrl;
    },
    async completeGoogleLink(){
      const response=await fetcher('/api/v1/auth/google/exchange',{method:'POST',cache:'no-store',credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-BTL-Google-Exchange':'1'},body:'{}'});
      if(!response.ok)throw Error('Google linking could not be completed. Start again.');
      const result=await response.json();
      if(result?.schemaVersion!==1||result.linked!==true||!validUuid(result.userId))throw Error('Unsupported Google linking response.');
      return result;
    },
    async login(email,password){
      token=null;subject=null;generation++;
      const result=await request('/api/v1/auth/login',{method:'POST',body:{username:email,password},form:true,authenticated:false});
      if(typeof result?.access_token!=='string'||result.token_type!=='bearer')throw Error('Unsupported account response.');
      token=result.access_token;
      const me=await request('/api/v1/auth/me');
      if(!validUuid(me?.id)||me.is_verified!==true||me.is_active!==true){token=null;throw Error('Verified account required.');}
      subject=me.id;return me;
    },
    async logout(all=false){try{await request(all?'/api/v1/auth/logout-all':'/api/v1/auth/logout',{method:'POST'});}finally{token=null;subject=null;generation++;clearShellCache();}},
    async identityProviders(){
      const value=await request('/api/v1/auth/identities');
      if(value?.schemaVersion!==1||!Array.isArray(value.providers)||value.providers.some(item=>!['EMAIL_PASSWORD','GOOGLE'].includes(item)))
        throw Error('Unsupported account identity response.');
      return value.providers;
    },
    clear(){token=null;subject=null;generation++;},
    hasSession(){return token!==null;},
    subject(){return subject;},
  };
}

let research=null;
const validUuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
export function setAccountTransport(client,workspaceId,features={}){
  if(!validUuid(workspaceId)||!validUuid(client.subject()))throw Error('Verified workspace required');
  research={client,root:`/api/v1/workspaces/${workspaceId}/research`,storageScope:`account:${workspaceId}:${client.subject()}`,features:{chartHistory:features.chartHistory===true}};
}
export function clearAccountTransport(){research=null;}
export function accountTransport(){return research;}
export function accountStorageKey(key){return research?`${research.storageScope}:${key}`:key;}
export function isAccountPage(){return typeof window!=='undefined'&&new URL(window.location.href).searchParams.get('page')==='account';}
