"""Verified workspace composition; private loopback datasets are never mounted."""
from functools import partial
from collections import OrderedDict
from threading import RLock
import hashlib
import os
import uuid

import anyio
from fastapi import Depends, Request
from fastapi.responses import Response
from psycopg.rows import dict_row

from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from contracts.primitives import require, ContractError
from execution.local_api import body
from execution.research import ResearchApplication
from identity.store import User
from infrastructure.database import connect
from workspace.policy import owner
from workspace.store import WorkspaceUnit
from . import queue

_OPERATOR_LOCK=RLock()
_OPERATOR_CATALOGS=OrderedDict()


def _operator_catalog(dsn):
    path=os.environ.get('BTL_OBSERVED_OPERATOR_CATALOG');sha=os.environ.get('BTL_OBSERVED_OPERATOR_CATALOG_SHA256')
    require((path is None)==(sha is None),'operatorCatalog','REFUSED_OPERATOR_CATALOG')
    if path is None:return None
    require(len(path)<=4096 and os.path.isabs(path),'operatorCatalog','REFUSED_OPERATOR_CATALOG')
    from execution.observed_catalog import ObservedCatalog
    key=(hashlib.sha256(dsn.encode()).hexdigest(),path,sha)
    with _OPERATOR_LOCK:
        catalog=_OPERATOR_CATALOGS.get(key)
        if catalog is None:
            catalog=ObservedCatalog(path,sha);_OPERATOR_CATALOGS[key]=catalog
        _OPERATOR_CATALOGS.move_to_end(key)
        # A single configured catalog per DB process; changing its pin requires
        # a clean worker restart, which also closes the exact old capability.
        require(len(_OPERATOR_CATALOGS)<=1,'operatorCatalog','SOURCE_PIN_CHANGED')
        return catalog


def close_operator_catalogs():
    with _OPERATOR_LOCK:
        for catalog in _OPERATOR_CATALOGS.values():catalog.close()
        _OPERATOR_CATALOGS.clear()


def run(dsn, actor_id, workspace_id, operation, args=(), *, write=False):
    # Keep verified-user/membership locks through the INNER service commit.
    # The external source selector is an operator catalog; HTTP supplies only
    # public keys, periods and normal trading intentions.
    with connect(dsn) as db:
        db.row_factory = dict_row
        unit = WorkspaceUnit(db, actor_id, workspace_id)
        if write:
            owner(unit.role)
        catalog=_operator_catalog(dsn)
        observed=False;session_id=None
        if catalog is not None:
            if operation in ('catalog','create_method'):
                observed=True
            elif operation=='create_session':
                observed=bool(args and type(args[0]) is dict and 'sourceKey' in args[0])
            elif operation in ('summary','inspect','journal','save_note','confirm','apply','bootstrap','workspace','chart_history','review'):
                if operation in ('review','create_session') and args and type(args[0]) is dict:session_id=args[0].get('sessionId')
                elif operation in ('confirm','apply','workspace','chart_history','bootstrap','inspect','summary','journal','save_note') and args:session_id=args[0]
                if operation=='apply' and len(args)>1 and type(args[1]) is dict:session_id=args[1].get('sessionId')
                if type(session_id) is str:
                    row=db.execute('SELECT payload,content_hash FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s',(str(workspace_id),session_id)).fetchone()
                    if row is not None:
                        try:
                            from execution.postgres import unpack
                            meta=unpack(row['payload'],row['content_hash']);observed=meta.get('artifact')=='BTL-OBSERVED-RESEARCH-SESSION-1'
                        except (TypeError,ValueError,UnicodeError):
                            raise ContractError('CORRUPT_RECORD','session')
            if observed:
                from execution.observed_research import ObservedResearchApplication
                research=ObservedResearchApplication(dsn,TrustedScope(str(workspace_id),str(actor_id)),catalog)
            else:
                research=ResearchApplication(dsn,TrustedScope(str(workspace_id),str(actor_id)))
        else:
            research=ResearchApplication(dsn,TrustedScope(str(workspace_id),str(actor_id)))
        try:
            return research.catalog_view() if observed and operation=='catalog' else getattr(research,operation)(*args)
        finally:
            research.close()


def install(app):
    prefix = '/api/v1/workspaces/{workspace_id}/research'
    current = app.state.current_user
    admission = anyio.Semaphore(2)
    limiter = anyio.CapacityLimiter(2)

    async def json_body(request):
        require(request.headers.get('content-type', '').split(';')[0] == 'application/json', 'contentType')
        require(not request.url.query and not request.headers.get('x-btl-source'), 'source')
        return await body(request)

    async def execute(user, workspace_id, operation, *args, write=False, job_id=None):
        if operation == 'apply' and args[-1].get('kind') in ('ADVANCE','SEEK'):
            operation = 'replay'
        if operation in queue.OPERATIONS:
            try:
                job = await anyio.to_thread.run_sync(partial(queue.submit, app.state.dsn, user.id, workspace_id,
                                                            job_id or uuid.uuid4(), operation, args), limiter=limiter)
            except ContractError as error:
                if error.code != 'QUEUE_CAPACITY':
                    raise
                return Response(canonical_bytes({'schemaVersion': 1, 'detail': 'QUEUE_CAPACITY'}), status_code=429,
                                media_type='application/json', headers={'Retry-After': '1'})
            # Modern clients acknowledge durable admission and poll. Heavy work
            # belongs to the bounded lifespan workers, never this HTTP request.
            if job_id is not None:
                return queue_response(job)
            # Persist acceptance before attempting work; busy workers leave a durable job.
            try:
                admission.acquire_nowait()
            except anyio.WouldBlock:
                return Response(canonical_bytes(job), status_code=202, media_type='application/json')
            try:
                from .worker import run as bounded_run
                await anyio.to_thread.run_sync(queue.work_one, app.state.dsn, bounded_run, limiter=limiter)
                job = await anyio.to_thread.run_sync(partial(queue.inspect, app.state.dsn, user.id, workspace_id, job['jobId']), limiter=limiter)
                return queue_response(job)
            finally:
                admission.release()
        try:
            admission.acquire_nowait()
        except anyio.WouldBlock:
            return Response(canonical_bytes({'schemaVersion': 1, 'detail': 'RESEARCH_BUSY'}),
                            status_code=429, media_type='application/json')
        try:
            value = await anyio.to_thread.run_sync(
                partial(run, app.state.dsn, user.id, workspace_id, operation, args, write=write),
                limiter=limiter)
            raw = canonical_bytes({'schemaVersion': 1, **value})
            require(len(raw) <= 8388608, 'response', 'REFUSED_RESPONSE_LIMIT')
            return Response(raw, media_type='application/json', headers={'X-Content-Type-Options': 'nosniff'})
        finally:
            admission.release()

    def queue_response(job):
        if job['state'] == 'SUCCEEDED':
            return Response(canonical_bytes(job['result']), media_type='application/json')
        return Response(canonical_bytes(job), status_code=202, media_type='application/json')

    @app.get(prefix + '/jobs/{job_id}')
    async def job_status(workspace_id: uuid.UUID, job_id: uuid.UUID, user: User = Depends(current)):
        job = await anyio.to_thread.run_sync(partial(queue.inspect, app.state.dsn, user.id, workspace_id, job_id), limiter=limiter)
        return Response(canonical_bytes(job), media_type='application/json')

    @app.post(prefix + '/jobs/{job_id}/cancel')
    async def cancel_job(workspace_id: uuid.UUID, job_id: uuid.UUID, user: User = Depends(current)):
        job = await anyio.to_thread.run_sync(partial(queue.inspect, app.state.dsn, user.id, workspace_id, job_id, cancel=True), limiter=limiter)
        return Response(canonical_bytes(job), media_type='application/json')

    @app.get(prefix + '/sessions/{session_id}/summary')
    async def summary(workspace_id: uuid.UUID, session_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'summary', session_id)

    @app.get(prefix + '/catalog')
    async def catalog(workspace_id: uuid.UUID, user: User = Depends(current)):
        return await execute(user, workspace_id, 'catalog')

    @app.post(prefix + '/methods')
    async def method(workspace_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await execute(user, workspace_id, 'create_method', await json_body(request), write=True)

    @app.post(prefix + '/sessions')
    async def create_session(workspace_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await execute(user, workspace_id, 'create_session', await json_body(request), write=True)

    @app.post(prefix + '/reviews')
    async def review(workspace_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await execute(user, workspace_id, 'review', await json_body(request), write=True)

    @app.get(prefix + '/sessions/{session_id}')
    async def inspect(workspace_id: uuid.UUID, session_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'inspect', session_id)

    @app.get(prefix + '/sessions/{session_id}/journal')
    async def journal(workspace_id: uuid.UUID, session_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'journal', session_id)

    @app.post(prefix + '/sessions/{session_id}/{operation}')
    async def session_operation(workspace_id: uuid.UUID, session_id: str, operation: str,
                                request: Request, user: User = Depends(current)):
        operations = {'view': ('workspace', False), 'bootstrap': ('bootstrap', False),
                      'chart-history': ('chart_history', False),
                      'journal': ('save_note', True), 'confirm': ('confirm', True), 'commands': ('apply', True)}
        require(operation in operations, 'operation', 'RESOURCE_UNAVAILABLE')
        name, write = operations[operation]
        raw = await json_body(request)
        queued = name in queue.OPERATIONS or (name == 'apply' and raw.get('kind') in ('ADVANCE','SEEK'))
        job_id = request.headers.get('x-btl-job') if queued else None
        if job_id is not None:
            try:
                job_id = uuid.UUID(job_id)
            except ValueError:
                require(False,'jobId')
        return await execute(user, workspace_id, name, session_id, raw, write=write, job_id=job_id)
