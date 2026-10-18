"""Isolated native sandbox ledger and entitlement composition. No real merchant."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import os,uuid,threading,tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import psycopg
from psycopg import sql
from cloud.billing import SandboxBilling,SandboxPlan,grant_billing_runtime,grant_billing_access_reader
from cloud.midtrans import Observation,PaymentError,Checkout
from cloud.sandbox_access import SandboxAccess,grant_sandbox_access_runtime
from infrastructure.database import connect,migrate,backup,restore

DSN=os.getenv('BTL_TEST_DATABASE_URL')
PLAN=SandboxPlan('authored-qa-not-for-sale',10000,86400)

class Provider:
    merchant_id="G_QA"
    def __init__(self):self.posts=0;self.disposition='PAID_EVIDENCE';self.failure=False;self.hook=lambda:None
    def checkout(self,order):
        self.posts+=1;self.hook()
        if self.failure:raise PaymentError('PROVIDER_REQUEST_UNCERTAIN',uncertain=True)
        return Checkout('https://app.sandbox.midtrans.com/snap/v4/redir/authored-qa')
    def status(self,order,*,transaction_id=None):
        self.hook()
        return Observation(order.order_id,'qa-'+order.order_id,'authored',self.disposition)
    def authenticate_notification(self,raw):return raw.decode()

@unittest.skipUnless(DSN,'Requires isolated native PostgreSQL; skip is not acceptance')
class BillingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(DSN)
    def setUp(self):
        self.actor=str(uuid.uuid4());self.other=str(uuid.uuid4());self.provider=Provider()
        with connect(DSN) as db:
            for actor in (self.actor,self.other):
                db.execute("INSERT INTO btl.users(id,email,hashed_password) VALUES (%s,%s,'authored-unused')",(actor,actor+'@example.com'))
        self.billing=SandboxBilling(DSN,'UTC',PLAN,self.provider)
        self.order=self.billing.create(self.actor,str(uuid.uuid4()))
        self.oid=self.order.state.order.order_id
    def tier(self,actor=None,dsn=None,billing=True):
        access=SandboxAccess(dsn or DSN,'UTC',billing=billing)
        with connect(dsn or DSN) as db:
            access.lock(db,actor or self.actor)
            return access.status(db,actor or self.actor)['tier']
    def test_idempotent_pins_scoping_and_disabled_default(self):
        changed=SandboxBilling(DSN,'UTC',SandboxPlan('new-offer',20000,90000),self.provider)
        self.assertEqual(changed.create(self.actor,self.order.request_id),self.order)
        with self.assertRaises(PaymentError):self.billing.read(self.other,self.oid)
        with self.assertRaises(PaymentError):self.billing.checkout(self.other,self.oid)
        self.assertEqual(self.tier(),'FREE')
        paid=self.billing.reconcile(self.actor,self.oid)
        self.assertEqual(paid.state.phase,'PAID');self.assertEqual(self.tier(),'PRO')
        self.assertEqual(self.tier(self.other),'FREE');self.assertEqual(self.tier(billing=False),'FREE')
    def test_merchant_change_refuses_old_checkout_and_reconciliation(self):
        changed=Provider();changed.merchant_id="OTHER_QA"
        cold=SandboxBilling(DSN,"UTC",PLAN,changed)
        self.assertEqual(cold.by_request(self.actor,self.order.request_id),self.order)
        for operation in (cold.checkout,cold.reconcile):
            with self.assertRaises(PaymentError) as cm:operation(self.actor,self.oid)
            self.assertEqual(cm.exception.code,"PAYMENT_MERCHANT_DRIFT")
        self.assertEqual(changed.posts,0);self.assertEqual(self.tier(),"FREE")

    def test_one_post_after_concurrent_checkout_and_no_locks_during_io(self):
        def unlocked():
            with connect(DSN) as db:
                db.execute('SELECT actor_id FROM btl.v2_access_accounts WHERE actor_id=%s FOR UPDATE NOWAIT',(self.actor,))
                db.execute('SELECT order_id FROM btl.sandbox_billing_orders WHERE order_id=%s FOR UPDATE NOWAIT',(self.oid,))
        self.provider.hook=unlocked
        def run(_):
            try:return self.billing.checkout(self.actor,self.oid).mode
            except PaymentError as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(sorted(results),['CHECKOUT_ALREADY_STARTED','SANDBOX']);self.assertEqual(self.provider.posts,1)
    def test_uncertain_post_survives_restart_and_never_reposts(self):
        self.provider.failure=True
        with self.assertRaises(PaymentError):self.billing.checkout(self.actor,self.oid)
        cold=SandboxBilling(DSN,'UTC',PLAN,self.provider)
        self.assertEqual(cold.read(self.actor,self.oid).state.phase,'CHECKOUT_STARTED')
        with self.assertRaises(PaymentError):cold.checkout(self.actor,self.oid)
        self.assertEqual(self.provider.posts,1)
        self.assertEqual(cold.reconcile(self.actor,self.oid).state.phase,'PAID')
    def test_duplicates_reversal_and_delayed_success(self):
        self.billing.checkout(self.actor,self.oid)
        paid=self.billing.reconcile(self.actor,self.oid)
        self.assertEqual(self.billing.reconcile(self.actor,self.oid),paid)
        self.assertEqual(len(self.billing.events(self.actor,self.oid)),2)
        self.provider.disposition='REVERSED'
        reversed_state=self.billing.notification(self.oid.encode())
        self.assertEqual(self.tier(),'FREE');self.provider.disposition='PAID_EVIDENCE'
        self.assertEqual(self.billing.reconcile(self.actor,self.oid),reversed_state)
        self.assertEqual(len(self.billing.events(self.actor,self.oid)),3)
    def test_expiry_and_other_paid_order_are_independent(self):
        paid=self.billing.reconcile(self.actor,self.oid)
        access=SandboxAccess(DSN,'UTC',billing=True)
        from datetime import datetime,timezone
        with patch.object(access,'now',return_value=datetime.fromtimestamp(paid.state.expires_at,tz=timezone.utc)):
            with connect(DSN) as db:self.assertEqual(access.status(db,self.actor)['tier'],'FREE')
        second=self.billing.create(self.actor,str(uuid.uuid4()))
        self.billing.reconcile(self.actor,second.state.order.order_id)
        self.provider.disposition='REVERSED';self.billing.reconcile(self.actor,self.oid)
        self.assertEqual(self.tier(),'PRO')
    def test_stale_parallel_observation_cannot_overwrite_new_revision(self):
        barrier=threading.Barrier(2);self.provider.hook=lambda:barrier.wait(timeout=10)
        def run(_):
            try:return self.billing.reconcile(self.actor,self.oid).state.phase
            except PaymentError as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(sorted(results),['PAID','STALE_PAYMENT_OBSERVATION'])
        self.assertEqual(len(self.billing.events(self.actor,self.oid)),1)
    def test_database_pin_guards_and_separate_worker_role(self):
        role='billing_qa_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        grant_billing_runtime(DSN,role)
        @contextmanager
        def restricted(dsn):
            with connect(dsn) as db:
                db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)));yield db
        with patch('cloud.billing.connect',restricted):
            self.billing.checkout(self.actor,self.oid);self.billing.reconcile(self.actor,self.oid)
        for statement in ('SELECT * FROM btl.tick_sessions LIMIT 0','SELECT * FROM btl.users LIMIT 0',
                          'INSERT INTO btl.sandbox_access_events SELECT * FROM btl.sandbox_access_events LIMIT 0',
                          'UPDATE btl.sandbox_billing_orders SET amount_idr=1',
                          'DELETE FROM btl.sandbox_billing_orders'):
            with self.assertRaises(psycopg.DatabaseError):
                with restricted(DSN) as db:db.execute(statement)
        for statement in ("UPDATE btl.sandbox_billing_orders SET actor_id=%s,revision=revision+1 WHERE order_id=%s",
                          "UPDATE btl.sandbox_billing_orders SET paid_at=paid_at+1,expires_at=expires_at+1,revision=revision+1 WHERE actor_id=%s AND order_id=%s"):
            with self.assertRaises(psycopg.DatabaseError):
                with connect(DSN) as db:db.execute(statement,(self.other if 'actor_id=%s,revision' in statement else self.actor,self.oid))
        reader='billing_reader_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(reader)))
        grant_sandbox_access_runtime(DSN,reader);grant_billing_access_reader(DSN,reader)
        with connect(DSN) as db:
            db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(reader)))
            self.assertEqual(SandboxAccess(DSN,'UTC',billing=True).status(db,self.actor)['tier'],'PRO')
        with self.assertRaises(psycopg.DatabaseError):
            with connect(DSN) as db:
                db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(reader)))
                db.execute("UPDATE btl.sandbox_billing_orders SET phase='PAID'")
    def test_cold_backup_restore_preserves_paid_state_and_journal(self):
        self.billing.checkout(self.actor,self.oid);paid=self.billing.reconcile(self.actor,self.oid)
        info=psycopg.conninfo.conninfo_to_dict(DSN);name='billing_restore_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
        target=psycopg.conninfo.make_conninfo(**{**info,'dbname':name})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'billing.dump';sha=backup(DSN,path,os.environ['BTL_PG_BIN']);restore(target,path,sha,os.environ['BTL_PG_BIN'])
        cold=SandboxBilling(target,'UTC',PLAN,self.provider)
        self.assertEqual(cold.read(self.actor,self.oid),paid)
        self.assertEqual(cold.events(self.actor,self.oid),self.billing.events(self.actor,self.oid))
        self.assertEqual(self.tier(dsn=target),'PRO')
        with self.assertRaises(PaymentError):cold.checkout(self.actor,self.oid)


@unittest.skipUnless(DSN,'Requires isolated native PostgreSQL; skip is not acceptance')
class BillingHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(DSN)
    def setUp(self):
        import secrets,httpx
        from cloud.app import create_app
        from cloud.midtrans import SnapSandbox,SandboxConfig
        from tests.test_identity import RecordingDelivery,client,PASSWORD
        self.delivery=RecordingDelivery();self.tx={};self.posts=0;self.fail_checkout=False;self.key='SB-Mid-server-authored-fixture-not-real'
        def handler(request):
            import json
            if request.method=='POST':
                self.posts+=1;order=json.loads(request.content)['transaction_details']
                self.tx[order['order_id']]=dict(order_id=order['order_id'],gross_amount=str(order['gross_amount']),merchant_id='G_QA',currency='IDR',
                    transaction_id='qa-'+order['order_id'],transaction_status='settlement',fraud_status='accept',payment_type='credit_card',status_code='200')
                if self.fail_checkout:raise httpx.ReadTimeout('authored uncertain checkout')
                return httpx.Response(201,json=dict(token='authored',redirect_url='https://app.sandbox.midtrans.com/snap/v4/redir/authored'))
            oid=request.url.path.split('/')[-2]
            return httpx.Response(200,json=self.tx[oid])
        provider=SnapSandbox(SandboxConfig(self.key,'G_QA'),transport=httpx.MockTransport(handler))
        self.billing=SandboxBilling(DSN,'UTC',PLAN,provider)
        self.app=create_app(DSN,secrets.token_urlsafe(48),self.delivery,rate_limit=1000,sandbox_reset_timezone='UTC',sandbox_billing=self.billing)
        self.client=client(self.app);email=uuid.uuid4().hex+'@example.com'
        self.actor=self.client.post('/api/v1/auth/register',json=dict(email=email,password=PASSWORD)).json()['id']
        self.client.post('/api/v1/auth/verify',json=dict(token=self.delivery.token(email,'verification')))
        token=self.client.post('/api/v1/auth/login',data=dict(username=email,password=PASSWORD)).json()['access_token']
        self.headers={'Authorization':'Bearer '+token};self.root='/api/v1/billing/sandbox'
        self.ws=self.client.post('/api/v1/workspaces',headers=self.headers,json=dict(name='Billing QA')).json()['id']
    def access(self):return self.client.get('/api/v1/workspaces/'+self.ws+'/research-v2/access',headers=self.headers).json()
    def checkout(self):
        self.request_id=str(uuid.uuid4());r=self.client.post(self.root+'/checkout',headers=self.headers,json=dict(requestId=self.request_id))
        self.assertEqual(r.status_code,200,r.text);return r.json()['payment']['orderId']
    def test_verified_checkout_reconcile_and_pro_access(self):
        self.assertEqual(self.client.get(self.root+'/plan').status_code,401)
        self.assertEqual(self.access()['tier'],'FREE');oid=self.checkout()
        self.assertEqual(self.access()['tier'],'FREE')
        response=self.client.post(self.root+'/orders/'+oid+'/reconcile',headers=self.headers,json={})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['phase'],'PAID');self.assertEqual(self.access()['tier'],'PRO')
        self.assertFalse(response.json()['fundsCollected']);self.assertEqual(response.headers['x-content-type-options'],'nosniff')
        duplicate=self.client.post(self.root+'/checkout',headers=self.headers,json=dict(requestId=self.request_id))
        self.assertEqual(duplicate.status_code,409);self.assertEqual(self.posts,1)
    def test_uncertain_checkout_recovers_by_request_without_repost(self):
        self.fail_checkout=True;request_id=str(uuid.uuid4())
        response=self.client.post(self.root+'/checkout',headers=self.headers,json=dict(requestId=request_id))
        self.assertEqual(response.status_code,503,response.text);self.assertTrue(response.json()['reconciliationRequired'])
        saved=self.client.get(self.root+'/requests/'+request_id,headers=self.headers)
        self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json()['phase'],'CHECKOUT_STARTED')
        oid=saved.json()['orderId']
        self.assertEqual(self.client.post(self.root+'/orders/'+oid+'/reconcile',headers=self.headers,json={}).status_code,200)
        self.assertEqual(self.access()['tier'],'PRO');self.assertEqual(self.posts,1)

    def test_signed_notification_is_signal_and_refund_revokes(self):
        import hashlib,json
        oid=self.checkout()
        raw=dict(order_id=oid,status_code='200',gross_amount='10000.00',transaction_status='forged-success')
        raw['signature_key']=hashlib.sha512((oid+'20010000.00'+self.key).encode()).hexdigest()
        self.tx[oid]['transaction_status']='pending'
        response=self.client.post(self.root+'/notification',json=raw)
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(self.access()['tier'],'FREE')
        self.assertNotIn('orderId',response.json())
        self.tx[oid]['transaction_status']='settlement';self.client.post(self.root+'/notification',json=raw)
        self.assertEqual(self.access()['tier'],'PRO')
        self.tx[oid]['transaction_status']='refund';self.client.post(self.root+'/notification',json=raw)
        self.assertEqual(self.access()['tier'],'FREE')
        raw['signature_key']='0'*128
        self.assertEqual(self.client.post(self.root+'/notification',json=raw).status_code,400)
    def test_scope_overrides_and_disabled_mount_refuse(self):
        import secrets
        from cloud.app import create_app
        from tests.test_identity import client
        oid=self.checkout()
        self.assertEqual(self.client.get(self.root+'/orders/'+oid).status_code,401)
        self.assertEqual(self.client.post(self.root+'/checkout',headers=self.headers,json=dict(requestId=str(uuid.uuid4()),amountIdr='1')).status_code,422)
        self.assertEqual(self.client.get(self.root+'/plan?amount=1',headers=self.headers).status_code,403)
        self.assertEqual(self.client.post(self.root+'/orders/'+oid+'/reconcile',headers=self.headers,json={'tier':'PRO'}).status_code,422)
        # A different account cannot read the first account's order.
        with connect(DSN) as db:
            other=str(uuid.uuid4());db.execute("INSERT INTO btl.users(id,email,hashed_password) VALUES (%s,%s,'authored-unused')",(other,other+'@example.com'))
        with self.assertRaises(PaymentError):self.billing.read(other,oid)
        disabled=client(create_app(DSN,secrets.token_urlsafe(48),self.delivery,rate_limit=1000))
        self.assertEqual(disabled.get(self.root+'/plan').status_code,404)
        with self.assertRaises(ValueError):create_app(DSN,secrets.token_urlsafe(48),self.delivery,sandbox_billing=self.billing)

if __name__=='__main__':unittest.main()
