"""Authored RSA/Google-shaped QA only: no real Google keys, login or SMTP."""
import os,time,secrets,uuid,base64,hashlib,unittest,tempfile
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager,asynccontextmanager
from unittest.mock import patch
import httpx,jwt,psycopg
from psycopg import sql
from psycopg.rows import dict_row
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi_users.password import PasswordHelper
from fastapi_users.jwt import generate_jwt
from cloud.app import create_app
from contracts.primitives import ContractError
from infrastructure.database import connect,migrate,backup,restore
from identity.google import GoogleConfig,GoogleVerifier,BROWSER_COOKIE,HANDOFF_COOKIE,COOKIE_PATH
from identity.google_store import key,grant_google_runtime
from tests.test_identity import client,RecordingDelivery,PASSWORD

DSN=os.getenv('BTL_TEST_DATABASE_URL')
CLIENT='12345-authored-qa.apps.googleusercontent.com'
SECRET='fixture-google-client-secret-not-real'
REDIRECT='https://testserver/api/v1/auth/google/callback'

class GoogleConfigurationTests(unittest.TestCase):
    def test_strict_config_disabled_default_and_canonical_origin(self):
        self.assertEqual(GoogleConfig(CLIENT,SECRET,'https://example.com:443/api/v1/auth/google/callback').origin,'https://example.com')
        self.assertNotIn(SECRET,repr(GoogleConfig(CLIENT,SECRET,REDIRECT)))
        for url in ('http://testserver/api/v1/auth/google/callback','https://evil@testserver/api/v1/auth/google/callback',REDIRECT+'?next=evil',REDIRECT+'#token','https://testserver/wrong'):
            with self.assertRaises(ContractError):GoogleConfig(CLIENT,SECRET,url)
        with self.assertRaises(ValueError):create_app('authored:no-db','x'*64,RecordingDelivery(),google_client_id=CLIENT)
        with self.assertRaises(ValueError):create_app('authored:no-db','x'*64,RecordingDelivery(),google_client_id=CLIENT,google_client_secret='x'*64,google_redirect_uri=REDIRECT)

@unittest.skipUnless(DSN,'Requires isolated native PostgreSQL; skip is not acceptance')
class GoogleIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN);cls.private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.jwk=jwt.algorithms.RSAAlgorithm.to_jwk(cls.private.public_key(),as_dict=True)
        cls.jwk.update(kid='authored-qa-key',use='sig',alg='RS256')
    def setUp(self):
        self.auth_secret=secrets.token_urlsafe(48);self.delivery=RecordingDelivery()
        self.app=self.factory(DSN);self.client=client(self.app);self.forms=[]
        self.subject='authored-google:'+uuid.uuid4().hex;self.email=uuid.uuid4().hex+'@example.com'
        self.overrides={};self.bad_signature=False;self.nonce=None
        self.app.state.google_verifier.keys.fetch_data=lambda:{'keys':[self.jwk]}
        self.app.state.google_client.get_httpx_client=lambda:httpx.AsyncClient(transport=httpx.MockTransport(self.token_endpoint),follow_redirects=False,timeout=5)
    def factory(self,dsn):
        return create_app(dsn,self.auth_secret,self.delivery,rate_limit=1000,google_client_id=CLIENT,google_client_secret=SECRET,google_redirect_uri=REDIRECT)
    def token_endpoint(self,request):
        self.assertEqual(str(request.url),'https://oauth2.googleapis.com/token')
        form=parse_qs(request.content.decode());self.forms.append(form)
        self.assertEqual(form['client_id'],[CLIENT]);self.assertEqual(form['client_secret'],[SECRET]);self.assertEqual(form['redirect_uri'],[REDIRECT])
        self.assertEqual(form['grant_type'],['authorization_code'])
        now=int(time.time())
        payload=dict(iss='https://accounts.google.com',sub=self.subject,aud=CLIENT,exp=now+300,iat=now,nonce=self.nonce,email=self.email,email_verified=True)
        payload.update(self.overrides)
        token=jwt.encode(payload,self.other if self.bad_signature else self.private,algorithm='RS256',headers={'kid':'authored-qa-key'})
        return httpx.Response(200,json=dict(access_token='authored-provider-token',token_type='Bearer',expires_in=300,id_token=token))
    def start(self):
        response=self.client.get('/api/v1/auth/google/start',follow_redirects=False)
        self.assertEqual(response.status_code,303,response.text)
        query=parse_qs(urlsplit(response.headers['location']).query)
        self.assertEqual(query['scope'],['openid email']);self.assertEqual(query['code_challenge_method'],['S256'])
        self.assertNotIn(SECRET,response.headers['location']);self.nonce=query['nonce'][0]
        self.assertIn('httponly',response.headers['set-cookie'].lower());self.assertIn('secure',response.headers['set-cookie'].lower())
        return query
    def callback(self,query,status=303,who=None):
        response=(who or self.client).get('/api/v1/auth/google/callback',params=dict(state=query['state'][0],code='authored-code'),follow_redirects=False)
        self.assertEqual(response.status_code,status,response.text);return response
    def exchange(self,who=None,status=200,headers=None):
        response=(who or self.client).post('/api/v1/auth/google/exchange',headers=headers or {'Origin':'https://testserver','X-BTL-Google-Exchange':'1'},json={})
        self.assertEqual(response.status_code,status,response.text);return response
    def login(self):
        query=self.start();self.callback(query);response=self.exchange();return {'Authorization':'Bearer '+response.json()['access_token']}
    def test_pkce_state_cookie_exchange_logout_and_workspace_identity(self):
        query=self.start();self.callback(query)
        verifier=self.forms[0]['code_verifier'][0]
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(query['code_challenge'],[challenge])
        self.assertEqual(self.client.post('/api/v1/auth/google/exchange',json={}).status_code,403)
        response=self.exchange();header={'Authorization':'Bearer '+response.json()['access_token']}
        me=self.client.get('/api/v1/auth/me',headers=header);self.assertEqual(me.status_code,200,me.text)
        self.assertTrue(me.json()['is_verified']);self.assertEqual(me.json()['email'],self.email)
        self.assertEqual(self.client.post('/api/v1/workspaces',headers=header,json=dict(name='Google QA')).status_code,201)
        self.exchange(status=400);self.callback(query,400);self.assertEqual(len(self.forms),1)
        self.assertEqual(self.client.post('/api/v1/auth/logout',headers=header).status_code,204)
        self.assertEqual(self.client.get('/api/v1/auth/me',headers=header).status_code,401)
    def test_foreign_browser_expired_state_duplicate_query_and_source_host_refuse(self):
        query=self.start();self.callback(query,400,client(self.app));self.assertEqual(self.forms,[])
        duplicate=self.client.get('/api/v1/auth/google/callback',params=[('state',query['state'][0]),('state',query['state'][0]),('code','qa')],follow_redirects=False)
        self.assertEqual(duplicate.status_code,400)
        with connect(DSN) as db:
            row=db.execute('SELECT state_hash,browser_hash,config_hash,nonce,verifier FROM btl.google_login_states WHERE state_hash=%s',(key(query['state'][0]),)).fetchone()
            db.execute('DELETE FROM btl.google_login_states WHERE state_hash=%s',(row[0],))
            db.execute("INSERT INTO btl.google_login_states(state_hash,browser_hash,config_hash,nonce,verifier,phase,created_at,expires_at) VALUES (%s,%s,%s,%s,%s,'NEW',clock_timestamp()-interval '10 minutes',clock_timestamp()-interval '5 minutes')",row)
        self.callback(query,400);self.assertEqual(self.forms,[])
        self.assertEqual(self.client.get('/api/v1/auth/google/start',headers={'Host':'foreign.example'},follow_redirects=False).status_code,403)
    def test_signed_fixture_signature_issuer_audience_nonce_time_and_verified_email_refuse(self):
        cases=[dict(iss='https://foreign.example'),dict(aud='another-client'),dict(aud=[CLIENT]),dict(nonce='wrong'),dict(exp=int(time.time())-100),dict(iat=int(time.time())+300),dict(email_verified=False),dict(email_verified='true')]
        for override in cases:
            with self.subTest(case=override):
                self.overrides=override;query=self.start();self.callback(query,400)
        self.overrides={};self.bad_signature=True;query=self.start();self.callback(query,400)
        with connect(DSN) as db:self.assertEqual(db.execute('SELECT count(*) FROM btl.google_identities WHERE subject=%s',(self.subject,)).fetchone()[0],0)
    def test_stable_subject_email_change_and_disabled_user_never_reactivated(self):
        first=self.login();user=self.client.get('/api/v1/auth/me',headers=first).json();original_email=self.email
        self.email=uuid.uuid4().hex+'@example.com';second=self.login();current=self.client.get('/api/v1/auth/me',headers=second).json()
        self.assertEqual(current['id'],user['id']);self.assertEqual(current['email'],original_email)
        with connect(DSN) as db:db.execute('UPDATE btl.users SET is_active=false WHERE id=%s',(user['id'],))
        query=self.start();self.callback(query,400)
        self.assertEqual(self.client.get('/api/v1/auth/me',headers=second).status_code,401)
        with connect(DSN) as db:self.assertFalse(db.execute('SELECT is_active FROM btl.users WHERE id=%s',(user['id'],)).fetchone()[0])
    def test_existing_email_never_links_and_password_recovery_stays_compatible(self):
        registered=self.client.post('/api/v1/auth/register',json=dict(email=self.email,password=PASSWORD));self.assertEqual(registered.status_code,201,registered.text)
        verified=self.client.post('/api/v1/auth/verify',json=dict(token=self.delivery.token(self.email,'verification')));self.assertEqual(verified.status_code,200)
        query=self.start();self.callback(query,400)
        self.assertEqual(self.client.post('/api/v1/auth/login',data=dict(username=self.email,password=PASSWORD)).status_code,200)
        self.assertEqual(self.client.post('/api/v1/auth/forgot-password',json=dict(email=self.email)).status_code,202)
        recovery=self.delivery.token(self.email,'recovery')
        self.assertEqual(self.client.post('/api/v1/auth/reset-password',json=dict(token=recovery,password=PASSWORD+'-new')).status_code,200)
        self.assertEqual(self.client.post('/api/v1/auth/login',data=dict(username=self.email,password=PASSWORD+'-new')).status_code,200)
        with connect(DSN) as db:self.assertEqual(db.execute('SELECT count(*) FROM btl.google_identities WHERE subject=%s',(self.subject,)).fetchone()[0],0)
    def test_google_only_recovery_and_even_signed_reset_cannot_enable_password(self):
        header=self.login();uid=self.client.get('/api/v1/auth/me',headers=header).json()['id'];before=len(self.delivery.messages)
        self.assertEqual(self.client.post('/api/v1/auth/forgot-password',json=dict(email=self.email)).status_code,202)
        self.assertEqual(len(self.delivery.messages),before)
        with connect(DSN) as db:row=db.execute('SELECT hashed_password,password_enabled FROM btl.users WHERE id=%s',(uid,)).fetchone()
        self.assertFalse(row[1])
        token=generate_jwt(dict(sub=uid,password_fgpt=PasswordHelper().hash(row[0]),aud='fastapi-users:reset'),self.auth_secret,1800)
        self.assertEqual(self.client.post('/api/v1/auth/reset-password',json=dict(token=token,password=PASSWORD)).status_code,400)
        with self.assertRaises(psycopg.DatabaseError):
            with connect(DSN) as db:db.execute('UPDATE btl.users SET password_enabled=true WHERE id=%s',(uid,))
        self.assertEqual(self.client.post('/api/v1/auth/login',data=dict(username=self.email,password=PASSWORD)).status_code,400)
        self.assertEqual(self.client.get('/api/v1/auth/me',headers=header).status_code,200)
    def test_concurrent_callback_and_exchange_are_single_use(self):
        query=self.start()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:self.client.get('/api/v1/auth/google/callback',params=dict(state=query['state'][0],code='qa'),follow_redirects=False),range(2)))
        self.assertEqual(sorted(r.status_code for r in responses),[303,400]);self.assertEqual(len(self.forms),1)
        browser=self.client.cookies.get(BROWSER_COOKIE);handoff=self.client.cookies.get(HANDOFF_COOKIE)
        headers={'Origin':'https://testserver','X-BTL-Google-Exchange':'1','Cookie':BROWSER_COOKIE+'='+browser+'; '+HANDOFF_COOKIE+'='+handoff}
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:self.client.post('/api/v1/auth/google/exchange',headers=headers,json={}),range(2)))
        self.assertEqual(sorted(r.status_code for r in responses),[200,400])
        with connect(DSN) as db:
            uid=db.execute('SELECT user_id FROM btl.google_identities WHERE subject=%s',(self.subject,)).fetchone()[0]
            self.assertEqual(db.execute('SELECT count(*) FROM btl.auth_sessions WHERE user_id=%s',(uid,)).fetchone()[0],1)
    def test_restricted_runtime_commits_and_guards_private_state(self):
        import identity.store as identity_store
        role='google_qa_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        grant_google_runtime(DSN,role)
        @contextmanager
        def restricted(dsn):
            with connect(dsn) as db:db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)));yield db
        native=identity_store.connection
        @asynccontextmanager
        async def restricted_async(dsn):
            async with native(dsn) as db:
                await db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)));yield db
        with patch('identity.google_store.connect',restricted),patch('identity.store.connection',restricted_async):header=self.login()
        self.assertEqual(self.client.get('/api/v1/auth/me',headers=header).status_code,200)
        with self.assertRaises(psycopg.DatabaseError):
            with connect(DSN) as db:db.execute('UPDATE btl.google_identities SET initial_email=initial_email WHERE subject=%s',(self.subject,))
        with self.assertRaises(psycopg.DatabaseError):
            with restricted(DSN) as db:db.execute('SELECT * FROM btl.tick_sessions LIMIT 0')
    def test_cold_native_restore_preserves_subject_and_single_use_handoff(self):
        query=self.start();self.callback(query)
        info=psycopg.conninfo.conninfo_to_dict(DSN);name='google_restore_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
        target=psycopg.conninfo.make_conninfo(**{**info,'dbname':name})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'google.dump';sha=backup(DSN,path,os.environ['BTL_PG_BIN']);restore(target,path,sha,os.environ['BTL_PG_BIN'])
        cold=client(self.factory(target));cold.cookies.update(self.client.cookies)
        response=self.exchange(cold);header={'Authorization':'Bearer '+response.json()['access_token']}
        self.assertEqual(cold.get('/api/v1/auth/me',headers=header).json()['email'],self.email)
        self.exchange(cold,400)
        with connect(target) as db:self.assertEqual(db.execute('SELECT count(*) FROM btl.google_identities WHERE subject=%s',(self.subject,)).fetchone()[0],1)
