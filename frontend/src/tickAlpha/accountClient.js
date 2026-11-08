import {clearShellCache} from '../pwa.js';
// Existing same-origin HTTPS identity. Bearer tokens live only in this closure.
export function createAccountClient({fetcher=fetch,secure=()=>window.location.protocol==='https:',onExpired=()=>{}}={}){
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
      if(response.status===401){const had=token!==null;token=null;subject=null;generation++;if(had&&authenticated)onExpired();}
      // Never surface rejected payloads/passwords/tokens or raw server errors.
      throw Object.assign(Error(({400:'The request was refused. Check your details and verification.',401:'Sign in again.',403:'This action is not permitted.',404:'This workspace or record is unavailable.',409:'The saved record changed. Reload before retrying.',422:'Check the supplied fields.',426:'Account access requires HTTPS.',429:'The service is busy. Wait and retry.'})[response.status]||'Account service unavailable.'),{status:response.status});
    }
    const value=response.status===204?null:await response.json();
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
      if(result?.schemaVersion!==1||typeof result.access_token!=='string'||result.token_type!=='bearer')
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
export function setAccountTransport(client,workspaceId){
  if(!validUuid(workspaceId)||!validUuid(client.subject()))throw Error('Verified workspace required');
  research={client,root:`/api/v1/workspaces/${workspaceId}/research`,storageScope:`account:${workspaceId}:${client.subject()}`};
}
export function clearAccountTransport(){research=null;}
export function accountTransport(){return research;}
export function accountStorageKey(key){return research?`${research.storageScope}:${key}`:key;}
export function isAccountPage(){return typeof window!=='undefined'&&new URL(window.location.href).searchParams.get('page')==='account';}
