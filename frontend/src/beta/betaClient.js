// Verified Beta transport. Backend receipts remain the financial authority.
const uuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const segment=value=>{
  if(typeof value!=='string'||value.length<1||value.length>128||!/^[-A-Za-z0-9_:]+$/.test(value))throw Error('Invalid Session identity.');
  return encodeURIComponent(value);
};
const refusals=new Set(['DAILY_WINDOW_LIMIT','SAVED_SESSION_LIMIT','WINDOW_ACTIVATION_REQUIRED','SESSION_TRASHED','TRASH_EXPIRED','OUTSIDE_TRADABLE_WINDOW','WINDOW_CONTINUATION_UNAVAILABLE','GOOGLE_LOGIN_FAILED','GOOGLE_STATE_REFUSED','GOOGLE_BUSY','PROTOCOL_BLOCKED','CHECKOUT_ALREADY_STARTED','STALE_PAYMENT_OBSERVATION','BILLING_BUSY']);
export class BetaRequestError extends Error{
  constructor(code,{status=0,reconcile=false}={}){super(code);this.name='BetaRequestError';this.code=code;this.status=status;this.reconciliationRequired=reconcile;}
}
export function createBetaClient({fetcher=fetch,secure=()=>globalThis.location?.protocol==='https:'}={}){
  let token=null,subject=null,workspace=null,generation=0;
  const clear=()=>{token=null;subject=null;workspace=null;generation++;};
  const current=epoch=>{if(epoch!==generation)throw new BetaRequestError('ACCOUNT_CHANGED');};
  async function send(path,{body,form=false,cookies=false,auth=token,epoch=generation,signal,mutation=false}={}){
    if(!secure())throw new BetaRequestError('HTTPS_REQUIRED');
    current(epoch);
    let response,value;
    try{
      response=await fetcher(path,{method:body===undefined?'GET':'POST',cache:'no-store',redirect:'error',credentials:cookies?'same-origin':'omit',
        signal:signal?AbortSignal.any([signal,AbortSignal.timeout(30000)]):AbortSignal.timeout(30000),
        headers:{...(auth?{Authorization:`Bearer ${auth}`} : {}),...(cookies?{'X-BTL-Google-Exchange':'1'}:{}),
          ...(body===undefined?{}:{'Content-Type':form?'application/x-www-form-urlencoded':'application/json'})},
        ...(body===undefined?{}:{body:form?new URLSearchParams(body).toString():JSON.stringify(body)})});
      current(epoch);
      if(response.status!==204){
        // Bound decoded response bytes, including chunked/no Content-Length replies.
        const reader=response.body.getReader(),parts=[];let size=0;
        try{while(true){const part=await reader.read();current(epoch);if(part.done)break;size+=part.value.byteLength;if(size>8388608)throw Error('response limit');parts.push(part.value);}}
        finally{await reader.cancel().catch(()=>{});}
        const bytes=new Uint8Array(size);let offset=0;for(const part of parts){bytes.set(part,offset);offset+=part.byteLength;}
        value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
      }else value=null;
      current(epoch);
    }catch(error){
      current(epoch);
      if(error instanceof BetaRequestError)throw error;
      throw new BetaRequestError('SERVICE_UNAVAILABLE',{reconcile:mutation});
    }
    if(!response.ok){
      if(response.status===401)clear();
      throw new BetaRequestError(refusals.has(value?.detail)?value.detail:({401:'SIGN_IN_REQUIRED',403:'NOT_PERMITTED',404:'UNAVAILABLE',409:'RELOAD_REQUIRED',422:'INVALID_REQUEST',429:'SERVICE_BUSY'})[response.status]||'SERVICE_UNAVAILABLE',
        {status:response.status,reconcile:mutation&&response.status>=500});
    }
    return value;
  }
  async function authenticate(path,options){
    clear();const epoch=generation;
    try{
      const result=await send(path,{...options,auth:null,epoch});current(epoch);
      if(result?.token_type!=='bearer'||typeof result.access_token!=='string'||!/^[-A-Za-z0-9_]{16,4096}$/.test(result.access_token))throw new BetaRequestError('INVALID_IDENTITY_RESPONSE');
      token=result.access_token;
      const me=await send('/api/v1/auth/me',{epoch});current(epoch);
      if(!uuid(me?.id)||me.is_active!==true||me.is_verified!==true)throw new BetaRequestError('VERIFIED_ACCOUNT_REQUIRED');
      subject=me.id;return me;
    }catch(error){if(epoch===generation)clear();throw error;}
  }
  const scope=()=>{
    if(!token||!subject)throw new BetaRequestError('SIGN_IN_REQUIRED');
    if(!workspace)throw new BetaRequestError('WORKSPACE_REQUIRED');
    return `/api/v1/workspaces/${workspace}/research-v2`;
  };
  async function research(path,body,options={},mutation=body!==undefined){
    const value=await send(scope()+path,{body,signal:options.signal,mutation});
    if(![1,2].includes(value?.schemaVersion))throw new BetaRequestError('UNSUPPORTED_RESPONSE',{reconcile:mutation});
    return value; // Do not round, recompute, settle or auto-retry financial values.
  }
  const write=(path,raw,options)=>{if(!raw||typeof raw!=='object'||Array.isArray(raw))return Promise.reject(new BetaRequestError('INVALID_REQUEST'));return research(path,raw,options);};
  async function billing(path,body){
    if(!token||!subject)throw new BetaRequestError('SIGN_IN_REQUIRED');
    return send('/api/v1/billing/sandbox'+path,{body,mutation:body!==undefined});
  }
  return Object.freeze({
    clear,hasSession:()=>!!token&&!!subject,subject:()=>subject,
    billingPlan:()=>billing('/plan'),billingOrders:()=>billing('/orders'),billingAccess:()=>billing('/access'),
    billingCheckout:requestId=>{if(!uuid(requestId))return Promise.reject(new BetaRequestError('INVALID_REQUEST'));return billing('/checkout',{requestId});},
    billingResume:id=>billing('/orders/'+segment(id)+'/checkout',{}),
    billingReconcile:id=>billing('/orders/'+segment(id)+'/reconcile',{}),
    providers:()=>send('/api/v1/auth/providers',{auth:null}),
    googleStart:()=>{if(!secure())throw new BetaRequestError('HTTPS_REQUIRED');return '/api/v1/auth/google/start';},
    exchangeGoogle:()=>authenticate('/api/v1/auth/google/exchange',{body:{},cookies:true}),
    login:(email,password)=>authenticate('/api/v1/auth/login',{body:{username:email,password},form:true}),
    async logout(all=false){const auth=token;clear();if(auth)await send(all?'/api/v1/auth/logout-all':'/api/v1/auth/logout',{body:{},auth});},
    async workspaces(options={}){if(!token||!subject)throw new BetaRequestError('SIGN_IN_REQUIRED');return send('/api/v1/workspaces',{signal:options.signal});},
    async createWorkspace(name){if(!token||!subject)throw new BetaRequestError('SIGN_IN_REQUIRED');return send('/api/v1/workspaces',{body:{name},mutation:true});},
    selectWorkspace(id){if(!uuid(id))throw new BetaRequestError('INVALID_WORKSPACE');if(!token||!subject)throw new BetaRequestError('SIGN_IN_REQUIRED');workspace=id;generation++;},
    catalog:options=>research('/catalog',undefined,options),access:options=>research('/access',undefined,options),
    createMethod:(raw,options)=>write('/methods',raw,options),createSession:(raw,options)=>write('/sessions',raw,options),
    inspect:(id,options={})=>options.timeframe&&options.timeframe!=='1m'?research('/sessions/'+segment(id)+'/view',{timeframe:options.timeframe},options,false):research('/sessions/'+segment(id),undefined,options),
    statistics:(id,options)=>research('/sessions/'+segment(id)+'/statistics',undefined,options),
    journal:(id,options)=>research('/sessions/'+segment(id)+'/journal',undefined,options),
    activate:(id,options)=>research('/sessions/'+segment(id)+'/activate',{},options),
    review:(id,raw,options)=>write('/sessions/'+segment(id)+'/review',raw,options),
    confirm:(id,raw,options)=>write('/sessions/'+segment(id)+'/confirm',raw,options),
    command:(id,raw,options)=>write('/sessions/'+segment(id)+'/commands',raw,options),
    editJournal:(id,raw,options)=>write('/sessions/'+segment(id)+'/journal',raw,options),
    trash:(id,options)=>research('/sessions/'+segment(id)+'/trash',{},options),restore:(id,options)=>research('/sessions/'+segment(id)+'/restore',{},options),
  });
}
