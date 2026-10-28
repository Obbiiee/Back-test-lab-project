"""Bounded PostgreSQL scheduling, never independent financial authority.

Row + advisory transaction locks own a worker until completion. A process death
rolls back the claim: the original QUEUED row survives without a lease guess.
No provider handle/evidence is serialized. Worker authorization is revalidated.
"""
import logging
import json
import uuid
from contextlib import asynccontextmanager
from time import monotonic

import anyio
from psycopg.rows import dict_row
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, ContractError, identifier, revision
from infrastructure.database import connect
from workspace.store import WorkspaceUnit
from workspace.policy import owner
from execution.contracts import command_wire
from ticks.contracts import tag, uint

GLOBAL_LIMIT = 16
USER_LIMIT = 2
RETAINED_LIMIT = 32
WORKERS = 2
OPERATIONS = frozenset(('create_session', 'workspace', 'bootstrap', 'chart_history', 'replay', 'replay_to'))


def scoped(db, actor_id, workspace_id):
    db.row_factory = dict_row
    return WorkspaceUnit(db, actor_id, workspace_id)


def view(row):
    return {'schemaVersion': 1, 'jobId': str(row['id']), 'state': row['state'],
            'result': json.loads(bytes(row['result'])) if row['result'] is not None else None}


def replay_command(raw, session_id):
    """Validate the frozen command dialect selected by this request's tag.

    The worker still resolves the persisted Session family and revalidates the
    command there. Queue admission only performs bounded wire validation.
    """
    if type(raw) is dict and raw.get('artifact') == 'BTL-OBSERVED-EXECUTION-COMMAND-1':
        from execution.observed_kernel import command_wire as validate
    else:
        validate = command_wire
    command = validate(raw)
    require(command['sessionId'] == session_id and command['kind'] in ('ADVANCE', 'SEEK'), 'replay')
    return command


def replay_to_request(raw, session_id):
    tag(raw, 'BTL-OBSERVED-REPLAY-TO-1', 'requestId sessionId expectedRevision targetNs timeframe')
    require(raw['sessionId'] == session_id, 'replayTo')
    require(type(raw['requestId']) is str and len(raw['requestId']) == 32
            and all(char in '0123456789abcdef' for char in raw['requestId']), 'requestId')
    revision(raw['expectedRevision'])
    uint(raw['targetNs'])
    require(type(raw['timeframe']) is str and raw['timeframe'] in ('1m','3m','5m','15m','30m','1h','2h','4h','D'), 'timeframe')
    return raw


def submit(dsn, actor_id, workspace_id, job_id, operation, args):
    job_id = uuid.UUID(str(job_id))
    require(operation in OPERATIONS and type(args) in (tuple, list)
            and len(args) == (1 if operation == 'create_session' else 2), 'job')
    if operation == 'create_session':
        require(type(args[0]) is dict, 'sessionRequest')
        identifier(args[0].get('id'), 'sessionId')
    else:
        identifier(args[0], 'sessionId')
        require(type(args[1]) is dict, 'request')
    if operation == 'replay':
        replay_command(args[1], args[0])
    elif operation == 'replay_to':
        replay_to_request(args[1], args[0])
    payload = {'schemaVersion': 1, 'operation': operation, 'args': list(args)}
    raw = canonical_bytes(payload)
    require(len(raw) <= 16384, 'request')
    digest = content_hash(payload)
    with connect(dsn) as db:
        unit = scoped(db, actor_id, workspace_id)
        if operation in ('replay', 'replay_to', 'create_session'):
            owner(unit.role)
        # Serialize inexpensive count/admission across all API processes.
        db.execute('SELECT pg_advisory_xact_lock(2020,300)')
        previous = db.execute('SELECT * FROM btl.research_jobs WHERE id=%s', (job_id,)).fetchone()
        if previous:
            require((previous['actor_id'], previous['workspace_id']) == (actor_id, workspace_id), 'job', 'RESOURCE_UNAVAILABLE')
            require(previous['input_hash'] == digest, 'jobInput', 'IDEMPOTENCY_CONFLICT')
            return view(previous)
        db.execute("UPDATE btl.research_jobs SET state=CASE WHEN operation IN ('replay','replay_to') THEN 'RECONCILE_REQUIRED' ELSE 'EXPIRED' END,finished_at=clock_timestamp() WHERE id IN (SELECT id FROM btl.research_jobs WHERE state='QUEUED' AND expires_at<clock_timestamp() FOR UPDATE SKIP LOCKED)")
        counts = db.execute("SELECT count(*) AS global_count,count(*) FILTER (WHERE actor_id=%s) AS user_count FROM btl.research_jobs WHERE state='QUEUED'", (actor_id,)).fetchone()
        require(counts['global_count'] < GLOBAL_LIMIT and counts['user_count'] < USER_LIMIT, 'queue', 'QUEUE_CAPACITY')
        # Bounded completed operational receipts; canonical financial history is untouched.
        db.execute("DELETE FROM btl.research_jobs WHERE id IN (SELECT id FROM btl.research_jobs WHERE state<>'QUEUED' ORDER BY finished_at DESC,id OFFSET %s)", (RETAINED_LIMIT-GLOBAL_LIMIT-1,))
        row = db.execute("INSERT INTO btl.research_jobs(id,actor_id,workspace_id,operation,input,input_hash,state) VALUES (%s,%s,%s,%s,%s,%s,'QUEUED') RETURNING *",
                         (job_id, actor_id, workspace_id, operation, raw, digest)).fetchone()
        return view(row)


def inspect(dsn, actor_id, workspace_id, job_id, *, cancel=False):
    with connect(dsn) as db:
        scoped(db, actor_id, workspace_id)
        row = db.execute('SELECT * FROM btl.research_jobs WHERE id=%s AND actor_id=%s AND workspace_id=%s',
                         (job_id, actor_id, workspace_id)).fetchone()
        require(row is not None, 'job', 'RESOURCE_UNAVAILABLE')
        if row['state'] == 'QUEUED':
            # SKIP LOCKED: already executing read work is not falsely reported cancelled.
            claimed = db.execute("SELECT * FROM btl.research_jobs WHERE id=%s FOR UPDATE SKIP LOCKED", (job_id,)).fetchone()
            if not claimed:
                return {**view(row), 'state': 'RUNNING', 'cancellation': 'WAIT_FOR_RESULT'}
            row = claimed
            if row['state'] != 'QUEUED':
                return view(row)
            if cancel:
                state = 'RECONCILE_REQUIRED' if row['operation'] in ('replay','replay_to','create_session') else 'CANCELLED'
                row = db.execute("UPDATE btl.research_jobs SET state=%s,finished_at=clock_timestamp() WHERE id=%s AND state='QUEUED' RETURNING *", (state, job_id)).fetchone() or row
            elif not db.execute('SELECT clock_timestamp()<%s AS valid',(row['expires_at'],)).fetchone()['valid']:
                state = 'RECONCILE_REQUIRED' if row['operation'] in ('replay','replay_to','create_session') else 'EXPIRED'
                row = db.execute("UPDATE btl.research_jobs SET state=%s,finished_at=clock_timestamp() WHERE id=%s AND state='QUEUED' RETURNING *",(state, job_id)).fetchone()
        return view(row)


def work_one(dsn, runner):
    """One admitted task, retaining exclusive database-owned worker scope."""
    with connect(dsn) as db:
        db.row_factory = dict_row
        slot = next((i for i in range(WORKERS) if db.execute('SELECT pg_try_advisory_xact_lock(2020,%s) AS acquired', (310+i,)).fetchone()['acquired']), None)
        if slot is None:
            return False
        # Oldest head per actor first: one actor cannot consume both slots.
        row = db.execute("SELECT * FROM btl.research_jobs j WHERE state='QUEUED' AND NOT EXISTS (SELECT 1 FROM btl.research_jobs p WHERE p.actor_id=j.actor_id AND p.state='QUEUED' AND (p.created_at,p.id)<(j.created_at,j.id)) ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
        if row is None:
            return False
        start = monotonic()
        try:
            try:
                payload = json.loads(bytes(row['input']))
            except (ValueError, UnicodeError):
                raise ContractError('CORRUPT_RECORD', 'job') from None
            require(content_hash(payload) == row['input_hash'] and payload['operation'] == row['operation'], 'jobHash', 'CORRUPT_RECORD')
            args = payload['args']
            require(db.execute('SELECT clock_timestamp()<%s AS valid', (row['expires_at'],)).fetchone()['valid'], 'deadline', 'EXPIRED')
            # Existing runner locks verified membership through the actual read.
            if row['operation'] == 'replay':
                # Existing permanent command dedup recovers an inner COMMIT if
                # the process died before this operational job acknowledgement.
                result = runner(dsn, row['actor_id'], row['workspace_id'], 'apply', tuple(args), write=True)
            elif row['operation'] == 'replay_to':
                result = runner(dsn, row['actor_id'], row['workspace_id'], 'replay_to', tuple(args), write=True)
                # The native worker applies its 30s execution deadline after
                # any bounded pinned-source re-admission. Keep that separate
                # startup allowance from the queue transaction's wall time.
            elif row['operation'] == 'create_session':
                result = runner(dsn, row['actor_id'], row['workspace_id'], 'create_session', tuple(args), write=True)
            else:
                result = runner(dsn, row['actor_id'], row['workspace_id'], row['operation'], tuple(args))
                require(monotonic()-start <= 30, 'deadline', 'EXPIRED')
            raw = canonical_bytes({'schemaVersion': 1, **result})
            require(len(raw) <= 8388608, 'result', 'REFUSED_RESPONSE_LIMIT')
            state = 'SUCCEEDED'
        except ContractError as error:
            logging.getLogger(__name__).warning(
                'research_job_failed job_id=%s operation=%s error_code=%s',
                row['id'], row['operation'], error.code)
            raw = None
            state = 'RECONCILE_REQUIRED' if row['operation'] in ('replay','replay_to','create_session') else ('EXPIRED' if error.code == 'EXPIRED' else 'FAILED')
        # Infrastructure/process faults intentionally roll back, leaving QUEUED.
        db.execute('UPDATE btl.research_jobs SET state=%s,result=%s,finished_at=clock_timestamp() WHERE id=%s', (state, raw, row['id']))
        return True


@asynccontextmanager
async def lifespan(app):
    from .worker import run, close, warm_sources
    limiter = anyio.CapacityLimiter(WORKERS)
    async def worker():
        while True:
            try:
                await anyio.to_thread.run_sync(work_one, app.state.dsn, run, limiter=limiter)
            except Exception:
                # DB outage never runs a task outside admission or exposes errors.
                await anyio.sleep(1)
            await anyio.sleep(.25)
    try:
        # Hash/admit configured immutable sources before a replay job receives
        # its separate 30-second execution budget. No consumer sees this handle.
        await anyio.to_thread.run_sync(warm_sources, app.state.dsn)
        async with anyio.create_task_group() as group:
            for _ in range(WORKERS):
                group.start_soon(worker)
            try:
                yield
            finally:
                group.cancel_scope.cancel()
    finally:
        # Reap after admitted threads finish, including failed/cancelled exit.
        with anyio.CancelScope(shield=True):
            await anyio.to_thread.run_sync(close)
