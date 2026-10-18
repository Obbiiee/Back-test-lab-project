"""Opt-in durable sandbox billing. No production charge.

Identity is supplied by a trusted server caller. Provider IO never holds DB locks.
API read and billing write roles are deliberately separate. No HMAC test events.
"""
from dataclasses import dataclass
import uuid
from psycopg import sql
from contracts.primitives import require
from execution.postgres import pack, unpack
from infrastructure.database import connect
from .midtrans import SandboxOrder, PaymentState, PaymentError, check, text
from .sandbox_access import SandboxAccess

COLUMNS = 'order_id,actor_id,request_id,plan_version,amount_idr,duration_seconds,phase,transaction_id,paid_at,expires_at,revision,merchant_id'

@dataclass(frozen=True)
class SandboxPlan:
    version: str
    amount_idr: int
    duration_seconds: int

    def __post_init__(self):
        SandboxOrder('btl-sbx-'+'0'*32, 'validation', self.version, self.amount_idr, self.duration_seconds)

@dataclass(frozen=True)
class StoredPayment:
    state: PaymentState
    request_id: str
    revision: int
    merchant_id: str

    def public(self):
        return dict(schemaVersion=1, artifact='BTL-SANDBOX-PAYMENT-1', mode='SANDBOX', fundsCollected=False,
                    orderId=self.state.order.order_id, planVersion=self.state.order.plan_version,
                    amountIdr=str(self.state.order.amount_idr), phase=self.state.phase,
                    expiresAt=str(self.state.expires_at) if self.state.expires_at is not None else None,
                    revision=self.revision)

def identity(value):
    try:
        result=uuid.UUID(str(value))
    except (ValueError,TypeError,AttributeError):
        raise PaymentError('IDENTITY_INVALID') from None
    check(str(result)==str(value),'IDENTITY_INVALID')
    return str(result)

def decode(row):
    order=SandboxOrder(row[0],str(row[1]),row[3],row[4],row[5])
    return StoredPayment(PaymentState(order,row[6],row[7],row[8],row[9]),str(row[2]),row[10],row[11])

class SandboxBilling:
    def __init__(self, dsn, reset_timezone, plan, provider):
        check(type(plan) is SandboxPlan,'PLAN_INVALID')
        check(text(getattr(provider,'merchant_id',None),64),'MERCHANT_INVALID')
        self.merchant_id=provider.merchant_id
        self.dsn,self.plan,self.provider=dsn,plan,provider
        self.access=SandboxAccess(dsn,reset_timezone)

    def _read(self,db,actor,order_id,lock=False):
        check(type(order_id) is str and len(order_id)<=64,'ORDER_INVALID')
        row=db.execute('SELECT '+COLUMNS+' FROM btl.sandbox_billing_orders WHERE actor_id=%s AND order_id=%s'+(' FOR UPDATE' if lock else ''),(actor,order_id)).fetchone()
        check(row is not None,'PAYMENT_UNAVAILABLE')
        return decode(row)

    def create(self,actor,request_id):
        actor,request_id=identity(actor),identity(request_id)
        with connect(self.dsn) as db:
            self.access.lock(db,actor)
            row=db.execute('SELECT '+COLUMNS+' FROM btl.sandbox_billing_orders WHERE actor_id=%s AND request_id=%s',(actor,request_id)).fetchone()
            if row:
                # A request key pins the old offer even after an operator plan change.
                return decode(row)
            order=SandboxOrder('btl-sbx-'+uuid.uuid4().hex,actor,self.plan.version,self.plan.amount_idr,self.plan.duration_seconds)
            db.execute('INSERT INTO btl.sandbox_billing_orders(order_id,actor_id,request_id,plan_version,amount_idr,duration_seconds,phase,revision,merchant_id) VALUES (%s,%s,%s,%s,%s,%s,%s,0,%s)',
                       (order.order_id,actor,request_id,order.plan_version,order.amount_idr,order.duration_seconds,'CREATED',self.merchant_id))
            return StoredPayment(PaymentState(order),request_id,0,self.merchant_id)

    def read(self,actor,order_id):
        with connect(self.dsn) as db:
            return self._read(db,identity(actor),order_id)

    def by_request(self,actor,request_id):
        actor,request_id=identity(actor),identity(request_id)
        with connect(self.dsn) as db:
            row=db.execute('SELECT '+COLUMNS+' FROM btl.sandbox_billing_orders WHERE actor_id=%s AND request_id=%s',(actor,request_id)).fetchone()
            check(row is not None,'PAYMENT_UNAVAILABLE')
            return decode(row)

    def _save(self,db,prior,state,event):
        if state==prior.state:return prior
        revision=prior.revision+1
        payload=dict(schemaVersion=1,artifact='BTL-SANDBOX-PAYMENT-EVENT-1',orderId=state.order.order_id,
                     revision=revision,phase=state.phase,transactionId=state.transaction_id,
                     paidAt=None if state.paid_at is None else str(state.paid_at),
                     expiresAt=None if state.expires_at is None else str(state.expires_at),evidence=event)
        raw,sha=pack(payload)
        db.execute('UPDATE btl.sandbox_billing_orders SET phase=%s,transaction_id=%s,paid_at=%s,expires_at=%s,revision=%s WHERE order_id=%s',
                   (state.phase,state.transaction_id,state.paid_at,state.expires_at,revision,state.order.order_id))
        db.execute('INSERT INTO btl.sandbox_billing_events VALUES (%s,%s,%s,%s)',(state.order.order_id,revision,raw,sha))
        return StoredPayment(state,prior.request_id,revision,prior.merchant_id)

    def checkout(self,actor,order_id):
        actor=identity(actor)
        with connect(self.dsn) as db:
            self.access.lock(db,actor)
            prior=self._read(db,actor,order_id,True)
            check(prior.merchant_id==self.merchant_id,'PAYMENT_MERCHANT_DRIFT')
            started=self._save(db,prior,prior.state.begin_checkout(),dict(kind='CHECKOUT_ADMITTED'))
        # Committed before POST. Timeout/crash leaves CHECKOUT_STARTED, never retries.
        return self.provider.checkout(started.state.order)

    def reconcile(self,actor,order_id):
        actor=identity(actor)
        snapshot=self.read(actor,order_id)
        check(snapshot.merchant_id==self.merchant_id,'PAYMENT_MERCHANT_DRIFT')
        observation=self.provider.status(snapshot.state.order,transaction_id=snapshot.state.transaction_id)
        with connect(self.dsn) as db:
            self.access.lock(db,actor)
            current=self._read(db,actor,order_id,True)
            check(current.revision==snapshot.revision,'STALE_PAYMENT_OBSERVATION')
            now=int(db.execute('SELECT extract(epoch FROM clock_timestamp())').fetchone()[0])
            state=current.state.observe(observation,now)
            return self._save(db,current,state,dict(kind='AUTHENTICATED_STATUS',status=observation.provider_status,disposition=observation.disposition))

    def notification(self,raw):
        # Signature supplies only order ID. No account/status claim from payload.
        order_id=self.provider.authenticate_notification(raw)
        with connect(self.dsn) as db:
            row=db.execute('SELECT actor_id FROM btl.sandbox_billing_orders WHERE order_id=%s',(order_id,)).fetchone()
            check(row is not None,'PAYMENT_UNAVAILABLE')
        return self.reconcile(str(row[0]),order_id)

    def events(self,actor,order_id):
        with connect(self.dsn) as db:
            saved=self._read(db,identity(actor),order_id)
            rows=db.execute('SELECT revision,payload,content_hash FROM btl.sandbox_billing_events WHERE order_id=%s ORDER BY revision LIMIT 1025',(order_id,)).fetchall()
            check(len(rows)<=1024 and len(rows)==saved.revision,'PAYMENT_HISTORY_UNAVAILABLE')
            result=[]
            for expected,(revision,raw,sha) in enumerate(rows,1):
                value=unpack(raw,sha)
                require(revision==expected and value['revision']==revision and value['orderId']==order_id,'billing','CORRUPT_RECORD')
                result.append(value)
            return result

def grant_billing_runtime(dsn,role):
    """Dedicated provider worker only; no identity/tick ledger or test grant INSERT."""
    with connect(dsn) as db:
        db.execute(sql.SQL('GRANT USAGE ON SCHEMA btl TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT,INSERT ON btl.v2_access_accounts,btl.sandbox_billing_orders,btl.sandbox_billing_events TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT UPDATE(reset_timezone) ON btl.v2_access_accounts TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT UPDATE(phase,transaction_id,paid_at,expires_at,revision) ON btl.sandbox_billing_orders TO {}').format(sql.Identifier(role)))

def grant_billing_access_reader(dsn,role):
    with connect(dsn) as db:
        db.execute(sql.SQL('GRANT SELECT ON btl.sandbox_billing_orders TO {}').format(sql.Identifier(role)))


def install(app,billing):
    """Explicit factory opt-in. Worker DSN/merchant config never enter responses."""
    import anyio
    from functools import partial
    from fastapi import Depends,Request
    from fastapi.responses import JSONResponse
    from contracts.primitives import ContractError
    from execution.local_api import body
    from identity.store import User
    current=app.state.current_user
    admission=anyio.Semaphore(2);limiter=anyio.CapacityLimiter(2)
    prefix='/api/v1/billing/sandbox'
    def response(value,status=200):
        return JSONResponse(value,status_code=status,headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    async def execute(fn,*args):
        try:admission.acquire_nowait()
        except anyio.WouldBlock:return response(dict(detail='BILLING_BUSY'),429)
        try:
            try:
                value=await anyio.to_thread.run_sync(partial(fn,*args),limiter=limiter)
                return response(value)
            except PaymentError as error:
                mapping={'PAYMENT_UNAVAILABLE':404,'IDENTITY_INVALID':422,'ORDER_INVALID':422,
                         'CHECKOUT_ALREADY_STARTED':409,'STALE_PAYMENT_OBSERVATION':409,
                         'NOTIFICATION_UNAUTHENTICATED':400,'NOTIFICATION_INVALID':400,'PROVIDER_JSON_INVALID':400}
                status=mapping.get(error.code,503)
                return response(dict(detail=error.code if status!=503 else 'BILLING_UNAVAILABLE',reconciliationRequired=error.uncertain),status)
        finally:admission.release()
    async def payload(request,fields):
        require(request.headers.get('content-type','').split(';')[0]=='application/json','contentType')
        value=await body(request);require(set(value)==set(fields),'body');return value
    @app.middleware('http')
    async def billing_boundary(request,call_next):
        if request.url.path.startswith(prefix):
            if request.url.query or request.headers.get('x-btl-source'):
                return response(dict(detail='BILLING_OVERRIDE_FORBIDDEN'),403)
            try:return await call_next(request)
            except ContractError:return response(dict(detail='INVALID_REQUEST'),422)
        return await call_next(request)
    @app.get(prefix+'/plan')
    async def plan(user:User=Depends(current)):
        return response(dict(schemaVersion=1,mode='SANDBOX',fundsCollected=False,planVersion=billing.plan.version,
                             amountIdr=str(billing.plan.amount_idr),durationSeconds=str(billing.plan.duration_seconds)))
    @app.post(prefix+'/checkout')
    async def checkout(request:Request,user:User=Depends(current)):
        value=await payload(request,('requestId',))
        def run():
            order=billing.create(str(user.id),value['requestId'])
            result=billing.checkout(str(user.id),order.state.order.order_id)
            return dict(payment=billing.read(str(user.id),order.state.order.order_id).public(),redirectUrl=result.redirect_url)
        return await execute(run)
    @app.get(prefix+'/requests/{request_id}')
    async def by_request(request_id:str,user:User=Depends(current)):
        return await execute(lambda:billing.by_request(str(user.id),request_id).public())
    @app.get(prefix+'/orders/{order_id}')
    async def read(order_id:str,user:User=Depends(current)):
        return await execute(lambda:billing.read(str(user.id),order_id).public())
    @app.post(prefix+'/orders/{order_id}/reconcile')
    async def reconcile(order_id:str,request:Request,user:User=Depends(current)):
        await payload(request,())
        return await execute(lambda:billing.reconcile(str(user.id),order_id).public())
    @app.post(prefix+'/notification')
    async def notification(request:Request):
        require(request.headers.get('content-type','').split(';')[0]=='application/json','contentType')
        raw=await request.body()
        # The existing identity boundary enforces HTTPS,16KiB body/rate/admission.
        return await execute(lambda:notification_result(raw))
    def notification_result(raw):
        billing.notification(raw)
        # Never expose private account/order metadata in a provider acknowledgment.
        return dict(schemaVersion=1,mode='SANDBOX',received=True,fundsCollected=False)
