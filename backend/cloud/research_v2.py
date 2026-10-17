"""Opt-in verified synthetic v2 sandbox transport; v1 routes stay unchanged."""
from functools import partial
import uuid
import anyio
from fastapi import Depends, Request
from fastapi.responses import Response
from psycopg.rows import dict_row, tuple_row
from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from contracts.primitives import require, ContractError
from execution.local_api import body
from execution.research_v2 import ResearchApplicationV2
from identity.store import User
from infrastructure.database import connect
from workspace.store import WorkspaceUnit
from workspace.policy import owner

WRITE={'create_method','create_session','activate','review','confirm','apply','edit_note','trash','restore'}

def run(access,actor,workspace,operation,args):
    with connect(access.dsn) as db:
        db.row_factory=dict_row;unit=WorkspaceUnit(db,actor,workspace)
        db.row_factory=tuple_row
        if operation in WRITE:owner(unit.role)
        access.lock(db,actor)
        app=ResearchApplicationV2(access.dsn,TrustedScope(str(workspace),str(actor)))
        if operation=='access':return access.status(db,actor)
        if operation in ('catalog','inspect'):
            value=getattr(app,operation)(*args)
            rows=db.execute('SELECT session_id,trashed_at FROM btl.v2_access_sessions WHERE workspace_id=%s',(str(workspace),)).fetchall()
            saved={sid:('TRASHED' if stamp is not None else 'SAVED') for sid,stamp in rows}
            if operation=='catalog':
                value['savedStates']={meta['id']:saved.get(meta['id'],'UNMANAGED_INTERNAL') for meta in value['sessions']}
            else:value['savedState']=saved.get(args[0],'UNMANAGED_INTERNAL')
            return value

        if operation=='create_session':
            value=app.create_session(args[0],on_create=lambda inner,meta:access.admit_session(inner,actor,workspace,meta))
            access.owner(db,actor,workspace,value['id'])
            return value
        if operation in ('trash','restore'):
            return access.saved_state(db,actor,workspace,args[0],operation=='trash')
        if operation=='activate':return access.activate(db,actor,workspace,app._session(db,args[0])[0])
        if operation in ('review','confirm','apply'):
            sid=args[0];state=app._session(db,sid)[2]
            window=access.window(db,actor,workspace,sid,state)
            # Receipt retries must survive expiry/boundary; they are not new entries.
            retry=False
            if operation=='confirm':
                raw=args[1]
                if type(raw) is dict and type(raw.get('reviewId')) is str:
                    retry=db.execute('SELECT 1 FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s',(str(workspace),sid,raw['reviewId'])).fetchone() is not None
            if operation=='review' or operation=='confirm' and not retry:
                require(int(window['startNs'])<=int(state['throughNs'])<int(window['endNs']),'window','OUTSIDE_TRADABLE_WINDOW')
            if operation=='apply' and args[1].get('kind')=='ADVANCE':
                target=args[1].get('payload',{}).get('targetNs')
                require(type(target) is str and target.isdigit() and len(target)<=24,'target')
                require(int(window['startNs'])<=int(target)<int(window['endNs']),'window','WINDOW_CONTINUATION_UNAVAILABLE')
        return getattr(app,operation)(*args)


def install(app,access):
    prefix='/api/v1/workspaces/{workspace_id}/research-v2'
    current=app.state.current_user;admission=anyio.Semaphore(2);limiter=anyio.CapacityLimiter(2)
    async def execute(user,workspace,operation,*args):
        try:admission.acquire_nowait()
        except anyio.WouldBlock:return response(dict(detail='RESEARCH_BUSY'),429)
        try:
            try:value=await anyio.to_thread.run_sync(partial(run,access,user.id,workspace,operation,args),limiter=limiter)
            except ContractError as error:
                statuses={'RESOURCE_UNAVAILABLE':404,'OWNER_REQUIRED':403,'UNAUTHORIZED':401,'INVALID_INPUT':422,
                          'DAILY_WINDOW_LIMIT':409,'SAVED_SESSION_LIMIT':409,'WINDOW_ACTIVATION_REQUIRED':409,'SESSION_TRASHED':409,'TRASH_EXPIRED':409,
                          'OUTSIDE_TRADABLE_WINDOW':409,'WINDOW_CONTINUATION_UNAVAILABLE':409,'ACCESS_POLICY_DRIFT':503}
                status=statuses.get(error.code,409 if error.code.startswith(('REFUSED_','PROTOCOL_')) else 503)
                return response(dict(detail=error.code if status!=503 else 'SERVICE_UNAVAILABLE'),status)
            return response(value)
        finally:admission.release()
    async def payload(request):
        require(request.headers.get('content-type','').split(';')[0]=='application/json','contentType')
        return await body(request)
    @app.middleware('http')
    async def source_boundary(request,call_next):
        if '/research-v2' in request.url.path and (request.url.query or request.headers.get('x-btl-source')):
            return response(dict(detail='SOURCE_OVERRIDE_FORBIDDEN'),403)
        return await call_next(request)
    @app.get(prefix+'/access')
    async def status(workspace_id:uuid.UUID,user:User=Depends(current)):
        return await execute(user,workspace_id,'access')
    @app.get(prefix+'/catalog')
    async def catalog(workspace_id:uuid.UUID,user:User=Depends(current)):
        return await execute(user,workspace_id,'catalog')
    @app.post(prefix+'/methods')
    async def method(workspace_id:uuid.UUID,request:Request,user:User=Depends(current)):
        return await execute(user,workspace_id,'create_method',await payload(request))
    @app.post(prefix+'/sessions')
    async def session(workspace_id:uuid.UUID,request:Request,user:User=Depends(current)):
        return await execute(user,workspace_id,'create_session',await payload(request))
    @app.get(prefix+'/sessions/{session_id}')
    async def inspect(workspace_id:uuid.UUID,session_id:str,user:User=Depends(current)):
        return await execute(user,workspace_id,'inspect',session_id)
    @app.get(prefix+'/sessions/{session_id}/{operation}')
    async def read(workspace_id:uuid.UUID,session_id:str,operation:str,user:User=Depends(current)):
        require(operation in ('journal','statistics'),'operation','RESOURCE_UNAVAILABLE')
        return await execute(user,workspace_id,operation,session_id)
    @app.post(prefix+'/sessions/{session_id}/{operation}')
    async def write(workspace_id:uuid.UUID,session_id:str,operation:str,request:Request,user:User=Depends(current)):
        mapping={'activate':'activate','review':'review','confirm':'confirm','commands':'apply','journal':'edit_note','trash':'trash','restore':'restore'}
        require(operation in mapping,'operation','RESOURCE_UNAVAILABLE')
        raw=await payload(request)
        if operation in ('activate','trash','restore'):
            require(raw=={},'body');return await execute(user,workspace_id,mapping[operation],session_id)
        return await execute(user,workspace_id,mapping[operation],session_id,raw)


def response(value,status=200):
    raw=canonical_bytes({'schemaVersion':1,**value});require(len(raw)<=8388608,'response','REFUSED_RESPONSE_LIMIT')
    return Response(raw,status_code=status,media_type='application/json',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
