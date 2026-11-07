"""Verified workspace composition; private loopback datasets are never mounted."""
from functools import partial
from collections import OrderedDict
from threading import RLock
import hashlib
import os
import uuid

import anyio
from fastapi import Depends, Request, Query
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
_MONTHLY_LOCK=RLock()
_MONTHLY_PROVIDER=None
_MONTHLY_PIN=None


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


def _synthetic_monthly_provider():
    """Resolve only a server-pinned synthetic QA fixture; requests carry no path."""
    values = tuple(os.environ.get(name) for name in (
        'BTL_QA_SYNTHETIC_MONTHLY_ROOT', 'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID',
        'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION', 'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256'))
    if not any(values):
        return None
    require(os.environ.get('BTL_QA_SYNTHETIC_MONTHLY_ENABLE') == '1' and all(values),
            'syntheticMonthly', 'REFUSED_SOURCE')
    root, dataset_id, dataset_version, manifest_hash = values
    require(len(root) <= 4096 and os.path.isabs(root), 'syntheticMonthlyRoot', 'REFUSED_SOURCE')
    from contracts.primitives import digest
    digest(dataset_version, 'syntheticMonthlyVersion')
    digest(manifest_hash, 'syntheticMonthlyManifestHash')
    pin = (os.path.realpath(root), dataset_id, dataset_version, manifest_hash)
    global _MONTHLY_PROVIDER, _MONTHLY_PIN
    with _MONTHLY_LOCK:
        require(_MONTHLY_PIN in (None, pin), 'syntheticMonthly', 'SOURCE_PIN_CHANGED')
        if _MONTHLY_PROVIDER is None:
            from market_data.monthly_parquet import MonthlyParquetProvider
            provider = MonthlyParquetProvider(pin[0], expected_dataset_id=dataset_id,
                expected_dataset_version=dataset_version, expected_manifest_hash=manifest_hash)
            manifest = provider.describe(dataset_id, dataset_version)
            require(manifest['evidenceClass'] == 'SYNTHETIC_CONTRACT_ONLY' and
                    manifest['rights']['class'] == 'SYNTHETIC' and not manifest['diagnostics'],
                    'syntheticMonthly', 'REFUSED_SOURCE')
            _MONTHLY_PROVIDER, _MONTHLY_PIN = provider, pin
        return _MONTHLY_PROVIDER


def warm_worker_sources(dsn):
    """Admit all server-pinned sources before the native worker accepts jobs."""
    catalog = _operator_catalog(dsn)
    if catalog is not None:
        for profile_hash in sorted(catalog._profiles):
            catalog.resolve(profile_hash)
    monthly = _synthetic_monthly_provider()
    return catalog is not None or monthly is not None


def close_operator_catalogs():
    global _MONTHLY_PROVIDER, _MONTHLY_PIN
    with _OPERATOR_LOCK:
        for catalog in _OPERATOR_CATALOGS.values():catalog.close()
        _OPERATOR_CATALOGS.clear()
    with _MONTHLY_LOCK:
        _MONTHLY_PROVIDER = None
        _MONTHLY_PIN = None


def warm_operator_sources(dsn):
    """Admit configured source pins before a Session request needs them."""
    catalog = _operator_catalog(dsn)
    if catalog is None:
        return False
    for profile_hash in sorted(catalog._profiles):
        catalog.resolve(profile_hash)
    return True


def run(dsn, actor_id, workspace_id, operation, args=(), *, write=False):
    # Keep verified-user/membership locks through the INNER service commit.
    # The external source selector is an operator catalog; HTTP supplies only
    # public keys, periods and normal trading intentions.
    with connect(dsn) as db:
        db.row_factory = dict_row
        if operation == 'storage_metrics':
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        unit = WorkspaceUnit(db, actor_id, workspace_id)
        if write:
            owner(unit.role)
        if operation in ('method_page', 'method_detail', 'session_page',
                         'method_family_page', 'method_family_detail',
                         'method_new_version', 'method_lifecycle'):
            from execution import product_read_model
            from execution import product_method_lifecycle
            if operation == 'method_page':
                return product_read_model.methods(db, str(workspace_id), **args[0])
            if operation == 'method_detail':
                return product_read_model.method(db, str(workspace_id), args[0])
            if operation == 'session_page':
                return product_read_model.sessions(db, str(workspace_id), **args[0])
            if operation == 'method_family_page':
                return product_method_lifecycle.page(db, str(workspace_id), **args[0])
            if operation == 'method_family_detail':
                return product_method_lifecycle.detail(db, str(workspace_id), args[0])
            if operation == 'method_new_version':
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(workspace_id),))
                return product_method_lifecycle.add_version(db, str(workspace_id), args[0], args[1])
            if operation == 'method_lifecycle':
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(workspace_id),))
            return product_method_lifecycle.set_archived(db, str(workspace_id), args[0], args[1])
        if operation == 'method_analytics':
            catalog=_operator_catalog(dsn)
            observed_method=False
            if catalog is not None:
                with connect(dsn) as db:
                    db.row_factory=dict_row
                    candidates=db.execute('SELECT payload,content_hash FROM btl.tick_research_sessions '
                        'WHERE workspace_id=%s AND method_id=%s ORDER BY session_id LIMIT 128',
                        (str(workspace_id),args[0])).fetchall()
                from execution.postgres import unpack
                observed_method=any(unpack(row['payload'],row['content_hash']).get('artifact')==
                    'BTL-OBSERVED-RESEARCH-SESSION-1' for row in candidates)
            if catalog is not None and observed_method:
                from execution.observed_research import ObservedResearchApplication
                research=ObservedResearchApplication(dsn,TrustedScope(str(workspace_id),str(actor_id)),catalog,
                    state_storage_format=os.environ.get('BTL_OBSERVED_SESSION_STORAGE_FORMAT') or 'compact-v1')
            else:
                research = ResearchApplication(dsn, TrustedScope(str(workspace_id), str(actor_id)),
                    synthetic_provider=_synthetic_monthly_provider(),
                    state_storage_format=os.environ.get('BTL_TICK_SESSION_STORAGE_FORMAT') or 'compact-v1')
            try:
                return research.method_analytics(args[0])
            finally:
                research.close()
        if operation == 'storage_metrics':
            owner(unit.role)
            require(type(args) in (tuple, list) and len(args) == 1, 'storageMetrics')
            from execution.session_storage_metrics import collect
            return collect(db, str(workspace_id), args[0])
        catalog=_operator_catalog(dsn)
        observed=False;session_id=None
        if catalog is not None:
            if operation in ('catalog','create_method'):
                observed=True
            elif operation=='create_session':
                observed=bool(args and type(args[0]) is dict and 'sourceKey' in args[0])
            elif operation=='replay_to':
                session_id=args[0] if args else None
                observed=True
            elif operation in ('summary','inspect','journal','journal_page','terminal_order_page','save_note','confirm','apply','bootstrap','workspace','chart_history','review','command_result'):
                if operation in ('review','create_session') and args and type(args[0]) is dict:session_id=args[0].get('sessionId')
                elif operation in ('confirm','apply','workspace','chart_history','bootstrap','inspect','summary','journal','journal_page','terminal_order_page','save_note','command_result') and args:session_id=args[0]
                if operation=='apply' and len(args)>1 and type(args[1]) is dict:session_id=args[1].get('sessionId')
                if type(session_id) is str:
                    row=db.execute('SELECT payload,content_hash FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s',(str(workspace_id),session_id)).fetchone()
                    if row is not None:
                        try:
                            from execution.postgres import unpack
                            meta=unpack(row['payload'],row['content_hash']);observed=meta.get('artifact')=='BTL-OBSERVED-RESEARCH-SESSION-1'
                        except (TypeError,ValueError,UnicodeError):
                            raise ContractError('CORRUPT_RECORD','session')
        if operation=='replay_to':
            require(catalog is not None and observed,'replayTo','REFUSED_OBSERVED_OPERATION')
        monthly = None if observed else _synthetic_monthly_provider()
        if observed:
            from execution.observed_research import ObservedResearchApplication
            research=ObservedResearchApplication(dsn,TrustedScope(str(workspace_id),str(actor_id)),catalog,
                state_storage_format=os.environ.get('BTL_OBSERVED_SESSION_STORAGE_FORMAT') or 'compact-v1')
        else:
            research=ResearchApplication(dsn,TrustedScope(str(workspace_id),str(actor_id)),
                synthetic_provider=monthly,
                state_storage_format=os.environ.get('BTL_TICK_SESSION_STORAGE_FORMAT') or 'compact-v1')
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

    @app.get(prefix + '/sessions/{session_id}/metering/storage')
    async def storage_metrics(workspace_id: uuid.UUID, session_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'storage_metrics', session_id)

    @app.get(prefix + '/sessions/{session_id}/commands/{command_id}')
    async def command_result(workspace_id: uuid.UUID, session_id: str, command_id: str,
                             user: User = Depends(current)):
        return await execute(user, workspace_id, 'command_result', session_id, command_id)

    @app.get(prefix + '/catalog')
    async def catalog(workspace_id: uuid.UUID, user: User = Depends(current)):
        return await execute(user, workspace_id, 'catalog')

    @app.get(prefix + '/methods')
    async def methods(workspace_id: uuid.UUID, limit: int = Query(25, ge=1, le=50),
                      after: str | None = None, user: User = Depends(current)):
        return await execute(user, workspace_id, 'method_page', {'limit': limit, 'after': after})

    @app.get(prefix + '/methods/{method_id}')
    async def method_detail(workspace_id: uuid.UUID, method_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'method_detail', method_id)

    @app.get(prefix + '/methods/{method_id}/analytics')
    async def method_analytics(workspace_id: uuid.UUID, method_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'method_analytics', method_id)

    @app.get(prefix + '/method-families')
    async def method_families(workspace_id: uuid.UUID, limit: int = Query(25, ge=1, le=50),
                              after: str | None = None, include_archived: bool = Query(False, alias='includeArchived'),
                              user: User = Depends(current)):
        return await execute(user, workspace_id, 'method_family_page',
                             {'limit': limit, 'after': after, 'include_archived': include_archived})

    @app.get(prefix + '/method-families/{family_id}')
    async def method_family(workspace_id: uuid.UUID, family_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'method_family_detail', family_id)

    @app.post(prefix + '/method-families/{family_id}/versions')
    async def method_version(workspace_id: uuid.UUID, family_id: str, request: Request,
                             user: User = Depends(current)):
        return await execute(user, workspace_id, 'method_new_version', family_id,
                             await json_body(request), write=True)

    @app.post(prefix + '/method-families/{family_id}/lifecycle')
    async def method_lifecycle(workspace_id: uuid.UUID, family_id: str, request: Request,
                               user: User = Depends(current)):
        return await execute(user, workspace_id, 'method_lifecycle', family_id,
                             await json_body(request), write=True)

    @app.get(prefix + '/sessions')
    async def sessions(workspace_id: uuid.UUID, limit: int = Query(25, ge=1, le=50),
                       after: str | None = None, method_id: str | None = Query(None, alias='methodId'),
                       user: User = Depends(current)):
        return await execute(user, workspace_id, 'session_page',
                             {'limit': limit, 'after': after, 'method_id': method_id})

    @app.post(prefix + '/methods')
    async def method(workspace_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await execute(user, workspace_id, 'create_method', await json_body(request), write=True)

    @app.post(prefix + '/sessions')
    async def create_session(workspace_id: uuid.UUID, request: Request, user: User = Depends(current)):
        job_id = request.headers.get('x-btl-job')
        if job_id is not None:
            try:
                job_id = uuid.UUID(job_id)
            except ValueError:
                require(False, 'jobId')
        return await execute(user, workspace_id, 'create_session', await json_body(request), write=True,
                             job_id=job_id)

    @app.post(prefix + '/reviews')
    async def review(workspace_id: uuid.UUID, request: Request, user: User = Depends(current)):
        return await execute(user, workspace_id, 'review', await json_body(request), write=True)

    @app.get(prefix + '/sessions/{session_id}')
    async def inspect(workspace_id: uuid.UUID, session_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'inspect', session_id)

    @app.get(prefix + '/sessions/{session_id}/journal')
    async def journal(workspace_id: uuid.UUID, session_id: str, user: User = Depends(current)):
        return await execute(user, workspace_id, 'journal', session_id)

    @app.get(prefix + '/sessions/{session_id}/journal/pages')
    async def journal_page(workspace_id: uuid.UUID, session_id: str, limit: int = 32,
                           cursor: str | None = None, user: User = Depends(current)):
        return await execute(user, workspace_id, 'journal_page', session_id,
                             {'limit': limit, 'cursor': cursor})

    @app.get(prefix + '/sessions/{session_id}/terminal-orders')
    async def terminal_orders(workspace_id: uuid.UUID, session_id: str,
                              limit: int = Query(64, ge=1, le=128),
                              after_sequence: int | None = Query(None, ge=0, alias='afterSequence'),
                              user: User = Depends(current)):
        return await execute(user, workspace_id, 'terminal_order_page', session_id,
                             {'limit': limit, 'afterSequence': after_sequence})

    @app.post(prefix + '/sessions/{session_id}/replay-to')
    async def replay_to(workspace_id: uuid.UUID, session_id: str, request: Request,
                        user: User = Depends(current)):
        raw=await json_body(request)
        queue.replay_to_request(raw,session_id)
        job_id=request.headers.get('x-btl-job')
        if job_id is not None:
            try:job_id=uuid.UUID(job_id)
            except ValueError:require(False,'jobId')
        return await execute(user,workspace_id,'replay_to',session_id,raw,write=True,job_id=job_id)

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
