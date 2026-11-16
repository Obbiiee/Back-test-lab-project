"""Durable authenticated intake; Odoo is never a request-path dependency."""
import uuid
from functools import partial
import anyio
from psycopg import sql
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from infrastructure.database import connect
from identity.store import User
from contracts.primitives import require, ContractError
from execution.local_api import body

def grant_support_runtime(dsn,role):
    with connect(dsn) as db:
        db.execute(sql.SQL('GRANT USAGE ON SCHEMA btl TO {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('GRANT SELECT,INSERT ON btl.support_requests TO {}').format(sql.Identifier(role)))

def listing(dsn,actor):
    with connect(dsn) as db:
        rows=db.execute('SELECT id,title,message,created_at,request_id FROM btl.support_requests WHERE actor_id=%s ORDER BY created_at DESC,id LIMIT 51',(actor,)).fetchall()
    return dict(schemaVersion=1,items=[dict(id=str(r[0]),title=r[1],message=r[2],createdAt=r[3].isoformat(),requestId=str(r[4])) for r in rows[:50]],truncated=len(rows)>50)

def submit(dsn,actor,value):
    require(type(value) is dict and set(value)=={'requestId','title','message'},'support')
    try:rid=uuid.UUID(value['requestId']);require(str(rid)==value['requestId'],'requestId')
    except (ValueError,TypeError,AttributeError):raise ContractError('INVALID_REQUEST','requestId') from None
    for key,limit in (('title',160),('message',4000)):
        text=value[key];require(type(text) is str and 1<=len(text.strip())<=limit and len(text)<=limit and all(c in '\n\t' or 32<=ord(c)<=0x10ffff and not 0xd800<=ord(c)<=0xdfff for c in text),key)
    with connect(dsn) as db:
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('support:'+str(actor),))
        prior=db.execute('SELECT id,title,message FROM btl.support_requests WHERE actor_id=%s AND request_id=%s',(actor,rid)).fetchone()
        if prior:
            require(prior[1:]==(value['title'],value['message']),'support','SUPPORT_CONFLICT')
            return dict(schemaVersion=1,id=str(prior[0]),saved=True)
        count=db.execute("SELECT count(*) FROM btl.support_requests WHERE actor_id=%s AND created_at>=clock_timestamp()-interval '24 hours'",(actor,)).fetchone()[0]
        require(count<10,'support','SUPPORT_LIMIT')
        sid=uuid.uuid4();db.execute('INSERT INTO btl.support_requests(id,actor_id,request_id,title,message) VALUES (%s,%s,%s,%s,%s)',(sid,actor,rid,value['title'],value['message']))
        return dict(schemaVersion=1,id=str(sid),saved=True)

def install(app):
    current=app.state.current_user;limiter=anyio.CapacityLimiter(2);admission=anyio.Semaphore(2)
    def response(value,status=200):return JSONResponse(value,status_code=status,headers={'Cache-Control':'no-store'})
    async def run(fn,*args):
        try:admission.acquire_nowait()
        except anyio.WouldBlock:return response({'detail':'SUPPORT_BUSY'},429)
        try:
            try:return response(await anyio.to_thread.run_sync(partial(fn,*args),limiter=limiter))
            except ContractError as e:return response({'detail':e.code},429 if e.code=='SUPPORT_LIMIT' else 409 if e.code=='SUPPORT_CONFLICT' else 422)
        finally:admission.release()
    @app.get('/api/v1/support')
    async def tickets(request:Request,user:User=Depends(current)):
        if request.url.query:return response({'detail':'INVALID_REQUEST'},422)
        return await run(listing,app.state.dsn,user.id)
    @app.post('/api/v1/support')
    async def create(request:Request,user:User=Depends(current)):
        if request.url.query or request.headers.get('content-type','').split(';')[0]!='application/json':return response({'detail':'INVALID_REQUEST'},422)
        try:value=await body(request)
        except ContractError:return response({'detail':'INVALID_REQUEST'},422)
        return await run(submit,app.state.dsn,user.id,value)
