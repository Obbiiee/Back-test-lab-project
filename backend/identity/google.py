"""Opt-in Google OIDC via mature OAuth/PKCE and JWT libraries; no email linking."""
from dataclasses import dataclass,field
from urllib.parse import urlsplit
import base64,hashlib,re,secrets
import anyio,httpx,jwt
from fastapi import Request,HTTPException
from fastapi.responses import JSONResponse,RedirectResponse
from httpx_oauth.clients.google import GoogleOAuth2
from httpx_oauth.exceptions import HTTPXOAuthError
from pydantic import TypeAdapter,EmailStr
from contracts.canonical import content_hash
from contracts.primitives import require,ContractError
from execution.local_api import body
from .google_store import GoogleStateStore

CALLBACK='/api/v1/auth/google/callback'
COOKIE_PATH='/api/v1/auth/google'
BROWSER_COOKIE='btl_google_browser'
HANDOFF_COOKIE='btl_google_handoff'
JWKS='https://www.googleapis.com/oauth2/v3/certs'

@dataclass(frozen=True)
class GoogleConfig:
    client_id:str
    client_secret:str=field(repr=False)
    redirect_uri:str
    def __post_init__(self):
        require(type(self.client_id) is str and 16<=len(self.client_id)<=256 and re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',self.client_id),'googleClientId')
        require(type(self.client_secret) is str and 16<=len(self.client_secret)<=4096 and all(33<=ord(c)<=126 for c in self.client_secret),'googleSecret')
        require(type(self.redirect_uri) is str and len(self.redirect_uri)<=512 and all(33<=ord(c)<=126 for c in self.redirect_uri),'googleRedirect')
        parsed=urlsplit(self.redirect_uri)
        try:port=parsed.port
        except ValueError:require(False,'googleRedirect')
        require(parsed.scheme=='https' and parsed.hostname and '*' not in parsed.hostname and parsed.username is None and parsed.password is None
                and (port is None or 1<=port<=65535) and parsed.path==CALLBACK and not parsed.query and not parsed.fragment,'googleRedirect')
    @property
    def origin(self):
        authority=urlsplit(self.redirect_uri).netloc.lower()
        if authority.endswith(':443'):authority=authority[:-4]
        return 'https://'+authority
    @property
    def config_hash(self):return content_hash(dict(schemaVersion=1,artifact='BTL-GOOGLE-CONFIG-1',clientId=self.client_id,redirectUri=self.redirect_uri))


class GoogleClient(GoogleOAuth2):
    def get_httpx_client(self):return httpx.AsyncClient(timeout=httpx.Timeout(10,connect=5),follow_redirects=False,limits=httpx.Limits(max_connections=2,max_keepalive_connections=1))
    async def send_request(self,client,request,auth,*,exc_class):
        response=await client.send(request,auth=auth,stream=True)
        try:
            response.raise_for_status();blob=bytearray()
            async for chunk in response.aiter_bytes():
                blob.extend(chunk);require(len(blob)<=32768,'googleResponse','GOOGLE_RESPONSE_LIMIT')
            # aiter_bytes already decoded content-encoding; do not decode twice.
            return httpx.Response(response.status_code,content=bytes(blob),headers={'content-type':'application/json'},request=request)
        finally:await response.aclose()


class GoogleVerifier:
    def __init__(self,config):
        self.config=config
        self.keys=jwt.PyJWKClient(JWKS,timeout=5,cache_keys=False,cache_jwk_set=True,lifespan=300)
    def verify(self,token,nonce):
        require(type(token) is str and 1<=len(token)<=16384,'idToken')
        signing=self.keys.get_signing_key_from_jwt(token)
        claims=jwt.decode(token,signing.key,algorithms=['RS256'],audience=self.config.client_id,
                          issuer=('accounts.google.com','https://accounts.google.com'),leeway=30,
                          options={'require':['sub','iss','aud','exp','iat','nonce','email','email_verified']})
        require(type(claims['aud']) is str and claims['aud']==self.config.client_id and type(claims['exp']) is int and type(claims['iat']) is int,'claims')
        require(type(claims['nonce']) is str and claims['nonce'].isascii() and secrets.compare_digest(claims['nonce'],nonce),'nonce')
        require(type(claims['sub']) is str and re.fullmatch(r'[!-~]{1,255}',claims['sub']) and claims['email_verified'] is True,'googleIdentity')
        email=str(TypeAdapter(EmailStr).validate_python(claims['email'])).lower()
        return claims['sub'],email


def opaque(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{32,128}',value),'googleState','GOOGLE_STATE_REFUSED');return value


def cookie(response,name,value,age):
    response.set_cookie(name,value,max_age=age,secure=True,httponly=True,samesite='lax' if name==BROWSER_COOKIE else 'strict',path=COOKIE_PATH)


def clear(response):
    for name in (BROWSER_COOKIE,HANDOFF_COOKIE):response.delete_cookie(name,path=COOKIE_PATH,secure=True,httponly=True,samesite='lax' if name==BROWSER_COOKIE else 'strict')
    return response


def install(app,config,backend,strategy,user_store):
    store=GoogleStateStore(app.state.dsn,config.config_hash)
    client=GoogleClient(config.client_id,config.client_secret,scopes=['openid','email']);verifier=GoogleVerifier(config)
    app.state.google_store,app.state.google_client,app.state.google_verifier=store,client,verifier
    admission=anyio.Semaphore(2);limiter=anyio.CapacityLimiter(2)
    async def threaded(function,*args):return await anyio.to_thread.run_sync(function,*args,limiter=limiter)
    def host(request):
        allowed={urlsplit(config.origin).netloc}
        if urlsplit(config.redirect_uri).port in (None,443):allowed.add(urlsplit(config.origin).netloc+':443')
        if request.url.scheme!='https' or request.headers.get('host','').lower() not in allowed:
            raise HTTPException(status_code=403,detail='GOOGLE_REQUEST_REFUSED')
    def fail(code='GOOGLE_LOGIN_FAILED',status=400):return JSONResponse({'detail':code},status_code=status,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    @app.get('/api/v1/auth/google/start')
    async def start(request:Request):
        host(request);require(not request.url.query,'googleParameters')
        require(request.headers.get('origin') in (None,config.origin),'googleOrigin')
        state,browser,nonce,verifier_text=(secrets.token_urlsafe(32),secrets.token_urlsafe(32),secrets.token_urlsafe(32),secrets.token_urlsafe(48))
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier_text.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
        try:await threaded(store.begin,state,browser,nonce,verifier_text)
        except ContractError:return fail('GOOGLE_BUSY',429)
        url=await client.get_authorization_url(config.redirect_uri,state,scope=['openid','email'],code_challenge=challenge,code_challenge_method='S256',extras_params={'nonce':nonce,'access_type':'online','prompt':'select_account'})
        result=RedirectResponse(url,status_code=303,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
        cookie(result,BROWSER_COOKIE,browser,300);return result
    @app.get(CALLBACK)
    async def callback(request:Request):
        host(request)
        try:admission.acquire_nowait()
        except anyio.WouldBlock:return fail('GOOGLE_BUSY',429)
        try:
            params=request.query_params
            require(len(params.multi_items())<=16 and len(set(params.keys()))==len(params.multi_items()),'googleParameters')
            state=opaque(params.get('state'));browser=opaque(request.cookies.get(BROWSER_COOKIE))
            nonce,verifier_text=await threaded(store.claim,state,browser)
            require(not params.get('error') and type(params.get('code')) is str and 1<=len(params['code'])<=4096,'googleCode')
            token=await client.get_access_token(params['code'],config.redirect_uri,code_verifier=verifier_text)
            subject,email=await threaded(verifier.verify,token.get('id_token'),nonce)
            handoff=secrets.token_urlsafe(32)
            await threaded(store.ready,state,subject,email,handoff)
            result=RedirectResponse(config.origin+'/?auth=google',status_code=303,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
            cookie(result,HANDOFF_COOKIE,handoff,120);return result
        except (ContractError,jwt.PyJWTError,httpx.HTTPError,HTTPXOAuthError,ValueError,TypeError,KeyError):return fail()
        finally:admission.release()
    @app.post('/api/v1/auth/google/exchange')
    async def exchange(request:Request):
        host(request)
        if request.url.query or request.headers.get('origin')!=config.origin or request.headers.get('x-btl-google-exchange')!='1':
            raise HTTPException(status_code=403,detail='GOOGLE_REQUEST_REFUSED')
        require(request.headers.get('content-type','').split(';')[0]=='application/json' and await body(request)=={},'googleBody')
        try:
            uid=await threaded(store.exchange,opaque(request.cookies.get(HANDOFF_COOKIE)),opaque(request.cookies.get(BROWSER_COOKIE)))
            user=await user_store.get(uid)
            require(user is not None and user.is_active and user.is_verified and not user.password_enabled,'googleAccount')
            # No state/user row lock is held across the existing token strategy.
            return clear(await backend.login(strategy(),user))
        except (ContractError,ValueError):return clear(fail())
