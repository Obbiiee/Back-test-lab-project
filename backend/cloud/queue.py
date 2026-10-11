"""Bounded PostgreSQL read-job queue; never queues financial mutations.

Row + advisory transaction locks own a worker until completion. A process death
rolls back the claim: the original QUEUED row survives without a lease guess.
No provider handle/evidence is serialized. Worker authorization is revalidated.
"""
import json
import uuid
from contextlib import asynccontextmanager
from time import monotonic

import anyio
from psycopg.rows import dict_row
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, ContractError, identifier
from infrastructure.database import connect
from workspace.store import WorkspaceUnit

GLOBAL_LIMIT = 16
USER_LIMIT = 2
RETAINED_LIMIT = 32
WORKERS = 2
OPERATIONS = frozenset(('workspace', 'bootstrap'))


def scoped(db, actor_id, workspace_id):
    db.row_factory = dict_row
    return WorkspaceUnit(db, actor_id, workspace_id)


def view(row):
    return {'schemaVersion': 1, 'jobId': str(row['id']), 'state': row['state'],
            'result': json.loads(bytes(row['result'])) if row['result'] is not None else None}


def submit(dsn, actor_id, workspace_id, job_id, operation, args):
    job_id = uuid.UUID(str(job_id))
    require(operation in OPERATIONS and type(args) in (tuple, list) and len(args) == 2, 'job')
    identifier(args[0], 'sessionId')
    require(type(args[1]) is dict, 'request')
    payload = {'schemaVersion': 1, 'operation': operation, 'args': list(args)}
    raw = canonical_bytes(payload)
    require(len(raw) <= 16384, 'request')
    digest = content_hash(payload)
    with connect(dsn) as db:
        scoped(db, actor_id, workspace_id)
        # Serialize inexpensive count/admission across all API processes.
        db.execute('SELECT pg_advisory_xact_lock(2020,300)')
        previous = db.execute('SELECT * FROM btl.research_jobs WHERE id=%s', (job_id,)).fetchone()
        if previous:
            require((previous['actor_id'], previous['workspace_id']) == (actor_id, workspace_id), 'job', 'RESOURCE_UNAVAILABLE')
            require(previous['input_hash'] == digest, 'jobInput', 'IDEMPOTENCY_CONFLICT')
            return view(previous)
        db.execute("UPDATE btl.research_jobs SET state='EXPIRED',finished_at=clock_timestamp() WHERE id IN (SELECT id FROM btl.research_jobs WHERE state='QUEUED' AND expires_at<clock_timestamp() FOR UPDATE SKIP LOCKED)")
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
            claimed = db.execute("SELECT id FROM btl.research_jobs WHERE id=%s FOR UPDATE SKIP LOCKED", (job_id,)).fetchone()
            if not claimed:
                return {**view(row), 'state': 'RUNNING', 'cancellation': 'WAIT_FOR_RESULT'}
            if cancel:
                row = db.execute("UPDATE btl.research_jobs SET state='CANCELLED',finished_at=clock_timestamp() WHERE id=%s AND state='QUEUED' RETURNING *", (job_id,)).fetchone() or row
            elif not db.execute('SELECT clock_timestamp()<%s AS valid',(row['expires_at'],)).fetchone()['valid']:
                row = db.execute("UPDATE btl.research_jobs SET state='EXPIRED',finished_at=clock_timestamp() WHERE id=%s RETURNING *",(job_id,)).fetchone()
        return view(row)


def work_one(dsn, runner):
    """One bounded read task. No waiting for another worker or session lock."""
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
            result = runner(dsn, row['actor_id'], row['workspace_id'], row['operation'], tuple(args))
            require(monotonic()-start <= 30, 'deadline', 'EXPIRED')
            raw = canonical_bytes({'schemaVersion': 1, **result})
            require(len(raw) <= 8388608, 'result', 'REFUSED_RESPONSE_LIMIT')
            state = 'SUCCEEDED'
        except ContractError as error:
            raw = None
            state = 'EXPIRED' if error.code == 'EXPIRED' else 'FAILED'
        # Infrastructure/process faults intentionally roll back, leaving QUEUED.
        db.execute('UPDATE btl.research_jobs SET state=%s,result=%s,finished_at=clock_timestamp() WHERE id=%s', (state, raw, row['id']))
        return True


@asynccontextmanager
async def lifespan(app):
    from .research import run
    limiter = anyio.CapacityLimiter(WORKERS)
    async def worker():
        while True:
            try:
                await anyio.to_thread.run_sync(work_one, app.state.dsn, run, limiter=limiter)
            except Exception:
                # DB outage never runs a task outside admission or exposes errors.
                await anyio.sleep(1)
            await anyio.sleep(.25)
    async with anyio.create_task_group() as group:
        for _ in range(WORKERS):
            group.start_soon(worker)
        try:
            yield
        finally:
            group.cancel_scope.cancel()
