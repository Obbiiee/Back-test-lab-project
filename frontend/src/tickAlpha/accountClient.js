// Existing same-origin HTTPS identity. Bearer tokens live only in this closure.
export function createAccountClient({fetcher=fetch,secure=()=>window.location.protocol==='https:'}={}){
  let token=null,subject=null,generation=0;
  async function request(path,{method='GET',body,form=false,authenticated=true,signal,jobId}={}){
    if(!secure())throw Error('Account access requires HTTPS. The private local workspace remains separate.');
    if(!/^\/api\/v1\/(auth|workspaces)(\/|$)/.test(path))throw Error('Unsupported account route');
    if(authenticated&&!token)throw Error('Sign in to continue.');
    const current=generation;
    const deadline=AbortSignal.timeout(30000);
    const boundedSignal=signal?AbortSignal.any([signal,deadline]):deadline;
    const response=await fetcher(path,{method,cache:'no-store',credentials:'omit',signal:boundedSignal,
      headers:{...(authenticated?{Authorization:`Bearer ${token}`} : {}),...(jobId?{'X-BTL-Job':jobId}:{}),...(body===undefined?{}:{'Content-Type':form?'application/x-www-form-urlencoded':'application/json'})},
      ...(body===undefined?{}:{body:form?new URLSearchParams(body).toString():JSON.stringify(body)})});
    if(current!==generation)throw Error('Account changed; this response was discarded.');
    if(!response.ok){
      if(response.status===401){token=null;subject=null;generation++;}
      // Never surface rejected payloads/passwords/tokens or raw server errors.
      throw Error(({400:'The request was refused. Check your details and verification.',401:'Sign in again.',403:'This action is not permitted.',404:'This workspace or record is unavailable.',409:'The saved record changed. Reload before retrying.',422:'Check the supplied fields.',426:'Account access requires HTTPS.',429:'The service is busy. Wait and retry.'})[response.status]||'Account service unavailable.');
    }
    const value=response.status===204?null:await response.json();
    if(current!==generation)throw Error('Account changed; this response was discarded.');
    return value;
  }
  return {
    request,
    async login(email,password){
      token=null;subject=null;generation++;
      const result=await request('/api/v1/auth/login',{method:'POST',body:{username:email,password},form:true,authenticated:false});
      if(typeof result?.access_token!=='string'||result.token_type!=='bearer')throw Error('Unsupported account response.');
      token=result.access_token;
      const me=await request('/api/v1/auth/me');
      if(!validUuid(me?.id)||me.is_verified!==true||me.is_active!==true){token=null;throw Error('Verified account required.');}
      subject=me.id;return me;
    },
    async logout(all=false){try{await request(all?'/api/v1/auth/logout-all':'/api/v1/auth/logout',{method:'POST'});}finally{token=null;subject=null;generation++;}},
    clear(){token=null;subject=null;generation++;},
    hasSession(){return token!==null;},
    subject(){return subject;},
  };
}

let research=null;
const validUuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
export function setAccountTransport(client,workspaceId){
  if(!validUuid(workspaceId)||!validUuid(client.subject()))throw Error('Verified workspace required');
  research={client,root:`/api/v1/workspaces/${workspaceId}/research`,storageScope:`account:${workspaceId}:${client.subject()}`};
}
export function clearAccountTransport(){research=null;}
export function accountTransport(){return research;}
export function accountStorageKey(key){return research?`${research.storageScope}:${key}`:key;}
export function isAccountPage(){return typeof window!=='undefined'&&new URL(window.location.href).searchParams.get('page')==='account';}
