import os,secrets,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from psycopg import sql
import psycopg
from cloud.app import create_app
from cloud.support import submit,listing,grant_support_runtime
from infrastructure.database import migrate,connect
from contracts.primitives import ContractError
from tests.test_identity import RecordingDelivery,client,PASSWORD
DSN=os.getenv('BTL_TEST_DATABASE_URL')
@unittest.skipUnless(DSN,'Requires fresh native PostgreSQL; skip is not acceptance')
class SupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(DSN)
    def setUp(self):
        delivery=RecordingDelivery();self.http=client(create_app(DSN,secrets.token_urlsafe(48),delivery,rate_limit=1000));self.email=uuid.uuid4().hex+'@example.com'
        self.http.post('/api/v1/auth/register',json={'email':self.email,'password':PASSWORD})
        self.http.post('/api/v1/auth/verify',json={'token':delivery.token(self.email,'verification')})
        token=self.http.post('/api/v1/auth/login',data={'username':self.email,'password':PASSWORD}).json()['access_token'];self.headers={'Authorization':'Bearer '+token}
        self.actor=self.http.get('/api/v1/auth/me',headers=self.headers).json()['id']
    def value(self):return dict(requestId=str(uuid.uuid4()),title='Authored question',message='Authored QA only')
    def test_verified_intake_duplicate_reload_and_account_isolation(self):
        value=self.value();a=self.http.post('/api/v1/support',headers=self.headers,json=value);self.assertEqual(a.status_code,200)
        self.assertEqual(self.http.post('/api/v1/support',headers=self.headers,json=value).json(),a.json())
        rows=self.http.get('/api/v1/support',headers=self.headers).json();self.assertEqual(len(rows['items']),1);self.assertEqual(rows['items'][0]['message'],value['message'])
        self.assertEqual(listing(DSN,uuid.uuid4())['items'],[])
        self.assertEqual(self.http.post('/api/v1/support',headers=self.headers,json={**value,'message':'Conflict'}).status_code,409)
        self.assertEqual(self.http.get('/api/v1/support').status_code,401)
    def test_bounded_shape_rate_and_concurrent_idempotency(self):
        value=self.value()
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:submit(DSN,self.actor,value),range(2)))
        self.assertEqual(results[0],results[1])
        for _ in range(9):submit(DSN,self.actor,self.value())
        with self.assertRaises(ContractError):submit(DSN,self.actor,self.value())
        self.assertEqual(submit(DSN,self.actor,value),results[0])
        for bad in ({**value,'actor':self.actor},{**value,'title':' '},{**value,'message':'x'*4001}):
            self.assertEqual(self.http.post('/api/v1/support',headers=self.headers,json=bad).status_code,422)
    def test_restricted_support_role_cannot_mutate_or_read_passwords(self):
        role='support_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        grant_support_runtime(DSN,role)
        with connect(DSN) as db:
            db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)))
            db.execute('INSERT INTO btl.support_requests(id,actor_id,request_id,title,message) VALUES (%s,%s,%s,%s,%s)',(uuid.uuid4(),self.actor,uuid.uuid4(),'QA','QA'))
        for statement in ('UPDATE btl.support_requests SET title=title','DELETE FROM btl.support_requests','SELECT hashed_password FROM btl.users'):
            with self.assertRaises(psycopg.DatabaseError):
                with connect(DSN) as db:db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)));db.execute(statement)
