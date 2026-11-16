"""Verified workspace composition; private loopback datasets are never mounted."""
from functools import partial
from collections import OrderedDict
from threading import RLock
import hashlib
import os
import time
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
from .research_routing import (observed_route as _observed_route, validate_source_selection,
                               monthly_provider_required)
from identity.store import User
from infrastructure.database import connect, capture_database_timing
from workspace.policy import owner
from workspace.store import WorkspaceUnit
from . import queue

_OPERATOR_LOCK=RLock()
_OPERATOR_CATALOGS=OrderedDict()
_MONTHLY_LOCK=RLock()
_MONTHLY_PROVIDER=None
_MONTHLY_PIN=None
_MONTHLY_CATALOGS=OrderedDict()
DIRECT_MUTATION_WAIT_SECONDS = 20
DIRECT_READ_WAIT_SECONDS = 20
DIRECT_OPERATION_CONCURRENCY = 3


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


def _monthly_catalog(dsn):
    path=os.environ.get('BTL_MONTHLY_PARQUET_CATALOG')
    sha=os.environ.get('BTL_MONTHLY_PARQUET_CATALOG_SHA256')
    require((path is None)==(sha is None),'monthlyCatalog','REFUSED_OPERATOR_CATALOG')
    if path is None:return None
    require(len(path)<=4096 and os.path.isabs(path),'monthlyCatalog','REFUSED_OPERATOR_CATALOG')
    from contracts.primitives import digest
    digest(sha,'monthlyCatalogHash')
    from market_data.monthly_catalog import MonthlyParquetCatalog
    key=(hashlib.sha256(dsn.encode()).hexdigest(),path,sha)
    with _OPERATOR_LOCK:
        catalog=_MONTHLY_CATALOGS.get(key)
        if catalog is None:
            catalog=MonthlyParquetCatalog(path,sha);_MONTHLY_CATALOGS[key]=catalog
        _MONTHLY_CATALOGS.move_to_end(key)
        require(len(_MONTHLY_CATALOGS)<=1,'monthlyCatalog','SOURCE_PIN_CHANGED')
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
    require(len(root) <= 4096, 'syntheticMonthlyRoot', 'REFUSED_SOURCE')
    from market_data.monthly_root import pin_monthly_root
    pinned_root = pin_monthly_root(root)
    from contracts.primitives import digest
    digest(dataset_version, 'syntheticMonthlyVersion')
    digest(manifest_hash, 'syntheticMonthlyManifestHash')
    pin = (pinned_root, dataset_id, dataset_version, manifest_hash)
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
    monthly_catalog=_monthly_catalog(dsn)
    if monthly_catalog is not None:
        # The current authenticated Monthly Session route mounts only bounded
        # synthetic fixtures. A rights evidence pin alone is not permission to
        # run the V1 financial engine.
        roots={(entry['root'],entry['datasetId'],entry['datasetVersion'],entry['manifestSha256'])
               for entry in monthly_catalog._entries.values()}
        require(len(roots)<=16,
                'monthlyCatalog','REFUSED_OPERATOR_CATALOG')
        for entry in monthly_catalog._entries.values():
            require(entry['eligibility']=='SYNTHETIC','monthlyEligibility','REFUSED_SOURCE')
        for key,period in sorted(monthly_catalog._entries):
            provider=monthly_catalog.resolve(key,period,verify_file=False)
            require(provider.manifest['sourceRights']['class']=='SYNTHETIC' and
                    provider.manifest['sourceManifest']['evidenceClass']=='SYNTHETIC_CONTRACT_ONLY',
                    'monthlyEligibility','REFUSED_SOURCE')
    return catalog is not None or monthly is not None or monthly_catalog is not None


def close_operator_catalogs():
    global _MONTHLY_PROVIDER, _MONTHLY_PIN
    with _OPERATOR_LOCK:
        for catalog in _OPERATOR_CATALOGS.values():catalog.close()
        _OPERATOR_CATALOGS.clear()
        for catalog in _MONTHLY_CATALOGS.values():catalog.close()
        _MONTHLY_CATALOGS.clear()
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


def _observed_session_uses_product_archive(db,workspace_id,session_id):
    """Select a validator from the persisted Session version, never from HTTP."""
    row=db.execute('SELECT payload,content_hash FROM btl.tick_sessions '
                   'WHERE workspace_id=%s AND session_id=%s',(str(workspace_id),session_id)).fetchone()
    if row is None:return None
    from execution.postgres import unpack
    stored=unpack(row['payload'],row['content_hash'])
    state=stored.get('state')
    if state is None:
        base=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
                        'WHERE workspace_id=%s AND session_id=%s AND revision=0',
                        (str(workspace_id),session_id)).fetchone()
        require(base is not None,'sessionFormat','CORRUPT_RECORD')
        state=unpack(base['payload'],base['content_hash']).get('state')
    require(type(state) is dict and type(state.get('artifact')) is str,
            'sessionFormat','CORRUPT_RECORD')
    from execution.observed_session_dispatch import dispatch_observed_session
    return dispatch_observed_session(state).archive_codec


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
                         'method_family_versions_page', 'method_new_version',
                         'method_lifecycle'):
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
            if operation == 'method_family_versions_page':
                return product_method_lifecycle.versions_page(db, str(workspace_id),
                    args[0], **args[1])
            if operation == 'method_new_version':
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(workspace_id),))
                return product_method_lifecycle.add_version(db, str(workspace_id), args[0], args[1])
            if operation == 'method_lifecycle':
                db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (str(workspace_id),))
            return product_method_lifecycle.set_archived(db, str(workspace_id), args[0], args[1])
        if operation == 'method_analytics':
            catalog = _operator_catalog(dsn)
            monthly_catalog = _monthly_catalog(dsn)
            from .research_routing import method_analytics_family
            from execution.postgres import unpack
            family_rows=[]
            after=''
            method_hash=None
            while True:
                with connect(dsn) as analytics_db:
                    analytics_db.row_factory=dict_row
                    batch=analytics_db.execute(
                        'SELECT session_id,payload,content_hash FROM btl.tick_research_sessions '
                        'WHERE workspace_id=%s AND method_id=%s AND session_id>%s '
                        'ORDER BY session_id LIMIT 65',
                        (str(workspace_id),args[0],after)).fetchall()
                more=len(batch)>64
                for row in batch[:64]:
                    metadata=unpack(row['payload'],row['content_hash'])
                    artifact=metadata.get('artifact')
                    if all(existing_artifact!=artifact for _sid,existing_artifact in family_rows):
                        family_rows.append((row['session_id'],artifact))
                    method_hash=method_hash or metadata.get('methodHash')
                    after=row['session_id']
                selected_family=method_analytics_family(family_rows)
                if selected_family=='mixed':
                    return dict(schemaVersion=1,artifact='BTL-METHOD-ANALYTICS-1',methodId=args[0],
                        methodHash=method_hash,aggregation='POOLED_COMMITTED_COMPLETED_POSITIONS',
                        balancesCombined=False,financialAuthority='COMMITTED_EVENTS_ONLY',status='UNAVAILABLE',
                        reason='MIXED_SESSION_ENGINE',includedSessions=[],
                        excludedSessions=[dict(sessionId=session_id,reason='MIXED_SESSION_ENGINE')
                                          for session_id,_artifact in family_rows],metrics=None)
                if not more:
                    break
            scope = TrustedScope(str(workspace_id), str(actor_id))
            if selected_family == 'observed' and catalog is not None:
                from execution.observed_research import ObservedResearchApplication
                research=ObservedResearchApplication(dsn,scope,catalog,
                    state_storage_format=os.environ.get('BTL_OBSERVED_SESSION_STORAGE_FORMAT') or 'compact-v1',
                    product_order_archive_v1=True)
            else:
                research = ResearchApplication(dsn, scope,
                    synthetic_provider=_synthetic_monthly_provider(),
                    monthly_catalog=monthly_catalog,
                    state_storage_format=os.environ.get('BTL_TICK_SESSION_STORAGE_FORMAT') or 'snapshot-v1')
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
        monthly_catalog=_monthly_catalog(dsn)
        if operation=='create_session':
            require(len(args)==1 and type(args[0]) is dict,'sessionRequest','INVALID_INPUT')
            validate_source_selection(args[0],catalog,monthly_catalog)
        observed=_observed_route(operation,args,catalog,monthly_catalog);session_id=None
        session_metadata=None
        if operation in ('replay_to','jump_next_event'):
            session_id=args[0] if args else None
        elif operation not in ('catalog','create_method','create_session'):
            if operation in ('review','create_session') and args and type(args[0]) is dict:session_id=args[0].get('sessionId')
            elif operation in ('confirm','apply','replay','jump_next_event','workspace','chart_history','bootstrap','inspect','summary','journal','journal_page','terminal_order_page','save_note','command_result') and args:session_id=args[0]
            if operation=='apply' and len(args)>1 and type(args[1]) is dict:session_id=args[1].get('sessionId')
        if type(session_id) is str:
            row=db.execute('SELECT payload,content_hash FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s',(str(workspace_id),session_id)).fetchone()
            if row is not None:
                try:
                    from execution.postgres import unpack
                    session_metadata=unpack(row['payload'],row['content_hash'])
                    observed=session_metadata.get('artifact')=='BTL-OBSERVED-RESEARCH-SESSION-1'
                except (TypeError,ValueError,UnicodeError):
                    raise ContractError('CORRUPT_RECORD','session')
        if monthly_catalog is not None and operation=='create_session' and args and type(args[0]) is dict:
            request=args[0]
            if 'sourceKey' in request:
                selection=monthly_catalog.selection(request['sourceKey'],request.get('period'))
                require(selection['eligibility']=='SYNTHETIC','monthlyEligibility','REFUSED_SOURCE')
                monthly_provider=monthly_catalog.resolve(request['sourceKey'],request['period'])
                monthly_source_key,monthly_period=request['sourceKey'],request['period']
            else:
                monthly_provider=None;monthly_source_key=monthly_period=None
        elif monthly_catalog is not None and type(session_metadata) is dict and 'sourceKey' in session_metadata:
            monthly_source_key=session_metadata['sourceKey'];monthly_period=session_metadata['startPeriod']
            selection=monthly_catalog.selection(monthly_source_key,monthly_period)
            require(selection['eligibility']=='SYNTHETIC' and
                    selection['manifestSha256']==session_metadata.get('monthlyManifestHash'),
                    'monthlySource','REFUSED_SOURCE')
            monthly_provider=(monthly_catalog.resolve(monthly_source_key,monthly_period)
                              if monthly_provider_required(operation) else None)
            # The pinned source identity stays attached to the adapter so
            # _session can verify both metadata and replay/chart reads.
        else:
            monthly_provider=None;monthly_source_key=monthly_period=None
        if operation=='replay_to':
            require(catalog is not None and observed,'replayTo','REFUSED_OBSERVED_OPERATION')
        if operation=='jump_next_event' and observed:
            require(catalog is not None,'jumpNextEvent','REFUSED_OBSERVED_OPERATION')
        monthly = None if observed else _synthetic_monthly_provider()
        if observed:
            from execution.observed_research import ObservedResearchApplication
            archive_codec='none'
            if operation=='create_session':
                selected=_observed_session_uses_product_archive(db,workspace_id,session_id)
                archive_codec='p0-v1' if selected is None else selected
            elif session_id is not None:
                archive_codec=_observed_session_uses_product_archive(db,workspace_id,session_id)
            product_archive=archive_codec=='p0-v1'
            terminal_archive=archive_codec=='integration-v1'
            storage_format=os.environ.get('BTL_OBSERVED_SESSION_STORAGE_FORMAT') or (
                'compact-v1' if archive_codec!='none' else 'snapshot-v1')
            research=ObservedResearchApplication(dsn,TrustedScope(str(workspace_id),str(actor_id)),catalog,
                state_storage_format=storage_format,product_order_archive_v1=product_archive,
                terminal_order_archive_v1=terminal_archive)
        else:
            research=ResearchApplication(dsn,TrustedScope(str(workspace_id),str(actor_id)),
                synthetic_provider=monthly_provider or monthly,
                monthly_catalog=monthly_catalog,
                monthly_source_key=monthly_source_key,monthly_period=monthly_period,
                state_storage_format=os.environ.get('BTL_TICK_SESSION_STORAGE_FORMAT') or 'compact-v1')
        try:
            if observed and operation=='catalog':
                result=research.catalog_view()
                if monthly_catalog is not None:result['monthlySources']=monthly_catalog.public()
                return result
            return getattr(research,operation)(*args)
        finally:
            research.close()


def install(app):
    prefix = '/api/v1/workspaces/{workspace_id}/research'
    current = app.state.current_user
    admission = anyio.Semaphore(DIRECT_OPERATION_CONCURRENCY)
    limiter = anyio.CapacityLimiter(DIRECT_OPERATION_CONCURRENCY)
    # Reserve bounded thread capacity for durable job status polls so they do
    # not queue behind direct research reads or submission transactions.
    job_status_limiter = anyio.CapacityLimiter(2)

    async def json_body(request):
        require(request.headers.get('content-type', '').split(';')[0] == 'application/json', 'contentType')
        require(not request.url.query and not request.headers.get('x-btl-source'), 'source')
        return await body(request)

    async def execute(user, workspace_id, operation, *args, write=False, job_id=None):
        timing_enabled = getattr(app.state, 'qa_timing', False) is True
        admission_started = time.monotonic() if timing_enabled else None
        admitted_at = None
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
                response = queue_response(job)
                if timing_enabled:
                    response.headers['Server-Timing'] = f"research-submit;dur={(time.monotonic()-admission_started)*1000:.3f}"
                return response
            # Persist acceptance before attempting work; busy workers leave a durable job.
            try:
                admission.acquire_nowait()
            except anyio.WouldBlock:
                return Response(canonical_bytes(job), status_code=202, media_type='application/json')
            try:
                from .worker import run as bounded_run
                await anyio.to_thread.run_sync(queue.work_one, app.state.dsn, bounded_run, limiter=limiter)
                job = await anyio.to_thread.run_sync(partial(queue.inspect, app.state.dsn, user.id, workspace_id, job['jobId']), limiter=limiter)
                response = queue_response(job)
                if timing_enabled:
                    response.headers['Server-Timing'] = f"research-submit;dur={(time.monotonic()-admission_started)*1000:.3f}"
                return response
            finally:
                admission.release()
        try:
            # Keep direct read/write work at the existing concurrency of two,
            # but let bounded API requests wait their turn instead of returning
            # repeated RESEARCH_BUSY during normal multi-trader bursts. The
            # outer ApiAdmission caps waiting requests; the wait itself is
            # shorter than the API request deadline and queue TTL.
            # Read-only pages may wait behind the bounded two-slot service
            # admission for up to two thirds of the authenticated API's 30 s
            # request deadline. Mutations retain the shorter bound so their
            # caller has time to resolve a durable receipt before timeout.
            wait_seconds = DIRECT_MUTATION_WAIT_SECONDS if write else DIRECT_READ_WAIT_SECONDS
            with anyio.fail_after(wait_seconds):
                await admission.acquire()
            admitted_at = time.monotonic() if timing_enabled else None
        except TimeoutError:
            response = Response(canonical_bytes({'schemaVersion': 1, 'detail': 'RESEARCH_BUSY'}),
                                status_code=429, media_type='application/json')
            if timing_enabled:
                response.headers['Server-Timing'] = f"research-admission;dur={(time.monotonic()-admission_started)*1000:.3f}"
            return response
        try:
            if timing_enabled:
                def measured_run():
                    started = time.monotonic()
                    cpu_started = time.thread_time_ns()
                    with capture_database_timing() as database_timing:
                        value = run(app.state.dsn, user.id, workspace_id, operation, args, write=write)
                    thread_cpu_ns = time.thread_time_ns() - cpu_started
                    return value, started, database_timing, thread_cpu_ns
                value, thread_started, database_timing, thread_cpu_ns = await anyio.to_thread.run_sync(measured_run, limiter=limiter)
            else:
                value = await anyio.to_thread.run_sync(
                    partial(run, app.state.dsn, user.id, workspace_id, operation, args, write=write),
                    limiter=limiter)
            serialization_started = time.monotonic() if timing_enabled else None
            raw = canonical_bytes({'schemaVersion': 1, **value})
            require(len(raw) <= 8388608, 'response', 'REFUSED_RESPONSE_LIMIT')
            headers = {'X-Content-Type-Options': 'nosniff'}
            if timing_enabled:
                finished = time.monotonic()
                headers['Server-Timing'] = (
                    f"research-admission;dur={(admitted_at-admission_started)*1000:.3f}, "
                    f"research-thread-wait;dur={(thread_started-admitted_at)*1000:.3f}, "
                    f"research-operation;dur={(finished-thread_started)*1000:.3f}, "
                    f"research-thread-cpu;dur={thread_cpu_ns/1_000_000:.3f}, "
                    f"db-admission;dur={database_timing['admissionNs']/1_000_000:.3f}, "
                    f"db-connect;dur={database_timing['connectNs']/1_000_000:.3f}, "
                    f"db-sql;dur={database_timing['sqlNs']/1_000_000:.3f}, "
                    f"db-transaction-exit;dur={database_timing['transactionExitNs']/1_000_000:.3f}, "
                    f"fixture-cache-lock-wait;dur={database_timing['fixtureCacheLockWaitNs']/1_000_000:.3f}, "
                    f"fixture-restore-gate-wait;dur={database_timing['fixtureRestoreGateWaitNs']/1_000_000:.3f}, "
                    f"fixture-timeline-resume;dur={database_timing['fixtureTimelineResumeNs']/1_000_000:.3f}, "
                    f"fixture-past-read;dur={database_timing['fixturePastReadNs']/1_000_000:.3f}, "
                    f"db-sql-count;desc={database_timing['sqlCount']}, "
                    f"research-serialization;dur={(time.monotonic()-serialization_started)*1000:.3f}")
            return Response(raw, media_type='application/json', headers=headers)
        finally:
            admission.release()

    def queue_response(job):
        if job['state'] == 'SUCCEEDED':
            return Response(canonical_bytes(job['result']), media_type='application/json')
        return Response(canonical_bytes(job), status_code=202, media_type='application/json')

    @app.get(prefix + '/jobs/{job_id}')
    async def job_status(workspace_id: uuid.UUID, job_id: uuid.UUID, user: User = Depends(current)):
        timing_enabled = getattr(app.state, 'qa_timing', False) is True
        started = time.monotonic() if timing_enabled else None
        if timing_enabled:
            def measured_inspect():
                thread_started = time.monotonic()
                with capture_database_timing() as database_timing:
                    value = queue.inspect(app.state.dsn, user.id, workspace_id, job_id)
                return value, thread_started, database_timing
            job, thread_started, database_timing = await anyio.to_thread.run_sync(measured_inspect, limiter=job_status_limiter)
        else:
            job = await anyio.to_thread.run_sync(partial(queue.inspect, app.state.dsn, user.id, workspace_id, job_id), limiter=job_status_limiter)
        response = Response(canonical_bytes(job), media_type='application/json')
        if started is not None:
            finished = time.monotonic()
            response.headers['Server-Timing'] = (
                f"queue-thread-wait;dur={(thread_started-started)*1000:.3f}, "
                f"queue-query;dur={(finished-thread_started)*1000:.3f}, "
                f"db-admission;dur={database_timing['admissionNs']/1_000_000:.3f}, "
                f"db-connect;dur={database_timing['connectNs']/1_000_000:.3f}, "
                f"db-sql;dur={database_timing['sqlNs']/1_000_000:.3f}, "
                f"db-transaction-exit;dur={database_timing['transactionExitNs']/1_000_000:.3f}, "
                f"db-sql-count;desc={database_timing['sqlCount']}")
        return response

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
    async def method_family(workspace_id: uuid.UUID, family_id: str,
                            user: User = Depends(current)):
        # Family detail is a bounded compatibility window. Full history uses
        # the separate revision-pinned /versions cursor route below.
        return await execute(user, workspace_id, 'method_family_detail', family_id)

    @app.get(prefix + '/method-families/{family_id}/versions')
    async def method_family_versions(workspace_id: uuid.UUID, family_id: str,
                                     limit: int = Query(25, ge=1, le=50),
                                     cursor: str | None = Query(None, max_length=2048),
                                     user: User = Depends(current)):
        return await execute(user, workspace_id, 'method_family_versions_page', family_id,
            {'limit': limit, 'cursor': cursor})

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
        raw = await json_body(request)
        catalog = await anyio.to_thread.run_sync(_operator_catalog, app.state.dsn, limiter=limiter)
        monthly_catalog = await anyio.to_thread.run_sync(_monthly_catalog, app.state.dsn, limiter=limiter)
        validate_source_selection(raw, catalog, monthly_catalog)
        return await execute(user, workspace_id, 'create_session', raw, write=True, job_id=job_id)

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

    @app.get(prefix + '/sessions/{session_id}/orders/pages')
    async def order_history_page(workspace_id: uuid.UUID, session_id: str, limit: int = 64,
                                 after_sequence: int | None = None, revision: int | None = None,
                                 user: User = Depends(current)):
        return await execute(user, workspace_id, 'order_history_page', session_id,
            {'limit': limit, 'afterSequence': after_sequence, 'revision': revision})

    @app.get(prefix + '/sessions/{session_id}/analytics/pages')
    async def analytics_page(workspace_id: uuid.UUID, session_id: str, limit: int = 32,
                             offset: int = 0, revision: int | None = None,
                             cursor: str | None = Query(None, max_length=2048),
                             user: User = Depends(current)):
        request={'limit': limit, 'offset': offset, 'revision': revision}
        if cursor is not None:request['cursor']=cursor
        return await execute(user, workspace_id, 'analytics_page', session_id,request)

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

    @app.post(prefix + '/sessions/{session_id}/jump-next-event')
    async def jump_next_event(workspace_id: uuid.UUID, session_id: str, request: Request,
                              user: User = Depends(current)):
        raw=await json_body(request)
        queue.jump_next_event_request(raw,session_id)
        job_id=request.headers.get('x-btl-job')
        if job_id is not None:
            try:job_id=uuid.UUID(job_id)
            except ValueError:require(False,'jobId')
        return await execute(user,workspace_id,'jump_next_event',session_id,raw,write=True,job_id=job_id)

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
