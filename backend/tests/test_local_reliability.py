"""Bounded repeated-use acceptance; not an hours-long soak or capacity certification."""
import os,secrets,unittest,uuid
from unittest.mock import patch
from cloud.app import create_app
from infrastructure.database import migrate
from contracts.canonical import content_hash
from tests.test_identity import RecordingDelivery,client,PASSWORD
from tests.test_research_sessions import method
from tests.test_kernel_v2 import opening
from tests.test_execution_v2_postgres import command
from execution.research_fixture_v2 import START_NS,STEP_NS
DSN=os.getenv('BTL_TEST_DATABASE_URL')
@unittest.skipUnless(DSN,'Fresh isolated PostgreSQL required; skip is not acceptance')
class LocalReliabilityTests(unittest.TestCase):
    def test_twelve_free_trade_cycles_cold_identity_retry_stats_and_journal(self):
        migrate(DSN);delivery=RecordingDelivery();secret=secrets.token_urlsafe(48)
        def fresh():return client(create_app(DSN,secret,delivery,rate_limit=1000,sandbox_reset_timezone='UTC'))
        http=fresh();email=uuid.uuid4().hex+'@example.com'
        self.assertEqual(http.post('/api/v1/auth/register',json=dict(email=email,password=PASSWORD)).status_code,201)
        self.assertEqual(http.post('/api/v1/auth/verify',json=dict(token=delivery.token(email,'verification'))).status_code,200)
        def login():
            r=http.post('/api/v1/auth/login',data=dict(username=email,password=PASSWORD));self.assertEqual(r.status_code,200);return {'Authorization':'Bearer '+r.json()['access_token']}
        headers=login();ws=http.post('/api/v1/workspaces',headers=headers,json={'name':'Bounded repeated-use QA'}).json()['id'];root='/api/v1/workspaces/'+ws+'/research-v2';sid='session:repeated';rev=0
        def post(path,value):
            r=http.post(root+path,headers=headers,json=value);self.assertEqual(r.status_code,200,r.text);return r.json()
        def get(path):
            r=http.get(root+path,headers=headers);self.assertEqual(r.status_code,200,r.text);return r.json()
        m=method();post('/methods',m);raw=dict(id=sid,name='Repeated Free practice',methodId=m['id'],symbol='EURUSD',startPeriod='2020-01',initialBalance='10000');post('/sessions',raw);path='/sessions/'+sid
        post(path+'/activate',{});activation_day=get('/access')['entitlementDay']
        def call(kind,payload):
            nonlocal rev
            raw=command(sid,'repeat:'+str(rev),rev,kind,payload);saved=post(path+'/commands',raw)
            # Lost-result replay of the same request must not append another event.
            self.assertEqual(post(path+'/commands',raw),saved);rev=saved['state']['revision'];return saved
        call('ADVANCE',dict(targetNs=str(START_NS)))
        expected=['10000.03','10000.06','10000.09','10000.12','10000.15','10000.18','10000.21','10000.24','10000.17','10000.1','10000.03','9999.96']
        for index,balance in enumerate(expected):
            oid='order:repeat:'+str(index)
            review=post(path+'/review',dict(id=oid,expectedRevision=rev,payload=opening(entry='999')));request=dict(reviewId=oid,reviewHash=content_hash(review))
            saved=post(path+'/confirm',request);rev=saved['state']['revision']
            if index==5:
                http.post('/api/v1/auth/logout-all',headers=headers);old=headers;http.close();http=fresh();headers=login()
                self.assertEqual(http.get('/api/v1/auth/me',headers=old).status_code,401)
            self.assertEqual(post(path+'/confirm',request),saved)
            call('ADVANCE',dict(targetNs=str(START_NS+(2*index+1)*STEP_NS)))
            call('CLOSE',dict(orderId=oid,quantity=None));call('ADVANCE',dict(targetNs=str(START_NS+(2*index+2)*STEP_NS)))
            stats=get(path+'/statistics');self.assertEqual(stats['account']['balance'],balance);self.assertEqual(stats['metrics']['tradeCount'],index+1)
            note=dict(orderId=oid,expectedNoteRevision=0,text='Authored cycle '+str(index),tags=['qa']);self.assertEqual(post(path+'/journal',note),post(path+'/journal',note))
            post(path+'/trash',{});post(path+'/restore',{})
            http.post('/api/v1/auth/logout-all',headers=headers);http.close();http=fresh();headers=login()
            self.assertEqual(get(path+'/statistics'),stats);self.assertEqual(len(get(path+'/journal')['notes']),index+1)
        self.assertEqual(stats['metrics']['wins'],8);self.assertEqual(stats['metrics']['losses'],4)
        access=get('/access');self.assertEqual(access['tier'],'FREE');same_day=access['entitlementDay']==activation_day;self.assertEqual(access['freeActivationAvailable'],not same_day)
        post('/sessions',{**raw,'id':'session:second'})
        refused=http.post(root+'/sessions/session:second/activate',headers=headers,json={})
        if same_day:self.assertEqual(refused.status_code,409);self.assertEqual(refused.json()['detail'],'DAILY_WINDOW_LIMIT')
        else:self.assertEqual(refused.status_code,200)
        with patch('execution.research_v2.binding',side_effect=RuntimeError('Controlled source outage')):
            view=get(path);self.assertEqual(view['displayStatus'],'SOURCE_DISPLAY_UNAVAILABLE');self.assertEqual(get(path+'/statistics'),stats)
        self.assertEqual(get(path)['state']['revision'],rev);http.close()
