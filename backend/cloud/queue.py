"""Bounded PostgreSQL scheduling, never independent financial authority.

Committed RUNNING leases expose worker ownership and heartbeat. A database
advisory session lock fences each worker slot; a process death releases that
lock, and lease expiry triggers bounded retry or reconciliation. No provider
handle/evidence is serialized. Worker authorization is revalidated.
"""
import logging
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from threading import Event, Thread
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
MAX_JOB_ATTEMPTS = 3
LEASE_SECONDS = 30
HEARTBEAT_SECONDS = 5
QUEUE_TTL_SECONDS = 60
OPERATIONS = frozenset(('create_session', 'workspace', 'bootstrap', 'chart_history', 'replay', 'replay_to', 'jump_next_event'))
MUTATING_OPERATIONS = frozenset(('create_session', 'replay', 'replay_to', 'jump_next_event'))

_CLAIM_NEXT_JOB = """
SELECT j.* FROM btl.research_jobs j
LEFT JOIN btl.research_queue_actor_turns t ON t.actor_id=j.actor_id
WHERE j.state='QUEUED'
  AND NOT EXISTS (
      SELECT 1 FROM btl.research_jobs p
      WHERE p.actor_id=j.actor_id AND p.state='QUEUED'
        AND (p.created_at,p.id)<(j.created_at,j.id)
  )
  AND NOT EXISTS (
      SELECT 1 FROM btl.research_jobs r
      WHERE r.actor_id=j.actor_id AND r.state='RUNNING'
  )
ORDER BY CASE WHEN j.operation='replay_to'
                AND j.created_at>statement_timestamp()-interval '5 seconds'
              THEN 1 ELSE 0 END,
         t.last_claimed_at NULLS FIRST,j.created_at,j.id
LIMIT 1 FOR UPDATE OF j SKIP LOCKED
"""


def scoped(db, actor_id, workspace_id):
    db.row_factory = dict_row
    return WorkspaceUnit(db, actor_id, workspace_id)


def view(row):
    cancellation = ('CANCELLED' if row['state'] == 'CANCELLED' else 'NOT_REQUESTED')
    if row.get('cancel_requested_at') is not None and row['state'] != 'CANCELLED':
        cancellation = ('REQUESTED' if row['state'] == 'RUNNING' else
                        'TOO_LATE' if row['state'] == 'SUCCEEDED' else 'RECONCILE_REQUIRED')
    return {'schemaVersion': 1, 'jobId': str(row['id']), 'state': row['state'],
            'result': json.loads(bytes(row['result'])) if row['result'] is not None else None,
            'attempt': row.get('attempts', 0), 'heartbeatAt': row.get('heartbeat_at'),
            'cancellation': cancellation}


def _reap_expired_leases(db):
    """Requeue a bounded number of abandoned claims; never discard financial uncertainty."""
    return db.execute("""
        WITH expired AS (
            SELECT id FROM btl.research_jobs
            WHERE state='RUNNING' AND lease_until <= clock_timestamp()
            ORDER BY lease_until,id LIMIT 32 FOR UPDATE SKIP LOCKED
        )
        UPDATE btl.research_jobs j SET
            state = CASE
                WHEN j.cancel_requested_at IS NOT NULL AND j.operation NOT IN ('replay','replay_to','jump_next_event','create_session') THEN 'CANCELLED'
                WHEN j.cancel_requested_at IS NOT NULL THEN 'RECONCILE_REQUIRED'
                WHEN j.attempts < %s THEN 'QUEUED'
                WHEN j.operation IN ('replay','replay_to','jump_next_event','create_session') THEN 'RECONCILE_REQUIRED'
                ELSE 'FAILED'
            END,
            expires_at = CASE WHEN j.cancel_requested_at IS NULL AND j.attempts < %s
                              THEN clock_timestamp() + (%s * interval '1 second') ELSE j.expires_at END,
            result = NULL,
            finished_at = CASE WHEN j.cancel_requested_at IS NULL AND j.attempts < %s
                               THEN NULL ELSE clock_timestamp() END,
            lease_owner = NULL, lease_until = NULL, heartbeat_at = NULL
        FROM expired WHERE j.id=expired.id
        RETURNING j.id
    """, (MAX_JOB_ATTEMPTS, MAX_JOB_ATTEMPTS, QUEUE_TTL_SECONDS, MAX_JOB_ATTEMPTS)).fetchall()


def _expire_queued(db):
    return db.execute("""
        UPDATE btl.research_jobs SET
            state=CASE WHEN operation IN ('replay','replay_to','jump_next_event','create_session') THEN 'RECONCILE_REQUIRED' ELSE 'EXPIRED' END,
            finished_at=clock_timestamp()
        WHERE state='QUEUED' AND expires_at < clock_timestamp()
    """).rowcount


def replay_command(raw, session_id, session_artifact):
    """Validate the command dialect against authenticated durable Session metadata."""
    if session_artifact == 'BTL-OBSERVED-RESEARCH-SESSION-1':
        from execution.observed_kernel import command_wire as validate
        expected = 'BTL-OBSERVED-EXECUTION-COMMAND-1'
    elif session_artifact == 'BTL-LOCAL-SESSION-1':
        validate = command_wire
        expected = 'BTL-TICK-EXECUTION-COMMAND-1'
    else:
        require(False, 'sessionModel', 'REFUSED_SESSION_MODEL')
    require(type(raw) is dict and raw.get('artifact') == expected,
            'command', 'REFUSED_COMMAND_DIALECT')
    command = validate(raw)
    require(command['sessionId'] == session_id and command['kind'] in ('ADVANCE', 'SEEK'), 'replay')
    return command


def _persisted_session_artifact(db, workspace_id, session_id):
    """Return a model only after workspace-scoped canonical payload verification."""
    row = db.execute('SELECT payload,content_hash FROM btl.tick_research_sessions '
                     'WHERE workspace_id=%s AND session_id=%s', (workspace_id, session_id)).fetchone()
    require(row is not None, 'session', 'RESOURCE_UNAVAILABLE')
    from execution.postgres import unpack
    try:
        metadata = unpack(row['payload'], row['content_hash'])
    except (TypeError, ValueError, UnicodeError, KeyError) as error:
        raise ContractError('CORRUPT_RECORD', 'session') from error
    artifact = metadata.get('artifact') if type(metadata) is dict else None
    require(artifact in ('BTL-LOCAL-SESSION-1', 'BTL-OBSERVED-RESEARCH-SESSION-1'),
            'sessionModel', 'REFUSED_SESSION_MODEL')
    require(metadata.get('schemaVersion') == 1 and metadata.get('id') == session_id,
            'session', 'CORRUPT_RECORD')
    return artifact


def replay_to_request(raw, session_id):
    tag(raw, 'BTL-OBSERVED-REPLAY-TO-1', 'requestId sessionId expectedRevision targetNs timeframe')
    require(raw['sessionId'] == session_id, 'replayTo')
    require(type(raw['requestId']) is str and len(raw['requestId']) == 32
            and all(char in '0123456789abcdef' for char in raw['requestId']), 'requestId')
    revision(raw['expectedRevision'])
    uint(raw['targetNs'])
    require(type(raw['timeframe']) is str and raw['timeframe'] in ('1m','3m','5m','15m','30m','1h','2h','4h','D'), 'timeframe')
    return raw


def jump_next_event_request(raw, session_id):
    from execution.jump_next_event import validate_request
    return validate_request(raw, session_id)


def _worker_measurements(result):
    """Bound and persist optional worker telemetry without changing job truth."""
    value = getattr(result, 'worker_metrics', None)
    if value is None:
        return None, None
    try:
        require(type(value) is dict and value.get('schemaVersion') == 1 and
                value.get('artifact') == 'BTL-NATIVE-WORKER-METRICS-1',
                'workerMetrics', 'CORRUPT_RECORD')
        raw = canonical_bytes(value)
        require(len(raw) <= 4096, 'workerMetrics', 'ARTIFACT_LIMIT')
        return raw, content_hash(value)
    except Exception as error:
        # Operational telemetry is auxiliary: a telemetry encoding problem
        # must never convert a committed financial command into a failed job.
        logging.getLogger(__name__).warning(
            'research_job_metrics_omitted error_type=%s', type(error).__name__)
        return None, None


def _queue_wait_measurements(created_at, claimed_at):
    """Hash first durable admission-to-claim delay at PostgreSQL timestamp precision."""
    if (not isinstance(created_at, datetime) or not isinstance(claimed_at, datetime) or
            created_at.tzinfo is None or claimed_at.tzinfo is None):
        return None, None
    delta = claimed_at.astimezone(timezone.utc) - created_at.astimezone(timezone.utc)
    if delta < timedelta(0):
        return None, None
    wait_us = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    value = {
        'schemaVersion': 1,
        'artifact': 'BTL-QUEUE-WAIT-METRICS-1',
        'measurementScope': 'FIRST_DURABLE_ADMISSION_TO_FIRST_WORKER_CLAIM',
        'clock': 'POSTGRESQL_CLOCK_TIMESTAMP_MICROSECOND',
        'waitMicroseconds': wait_us,
    }
    raw = canonical_bytes(value)
    return raw, content_hash(value)


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
    if operation == 'replay_to':
        replay_to_request(args[1], args[0])
    elif operation == 'jump_next_event':
        jump_next_event_request(args[1], args[0])
    payload = {'schemaVersion': 1, 'operation': operation, 'args': list(args)}
    raw = canonical_bytes(payload)
    require(len(raw) <= 16384, 'request')
    digest = content_hash(payload)
    with connect(dsn) as db:
        unit = scoped(db, actor_id, workspace_id)
        if operation in ('replay', 'replay_to', 'jump_next_event', 'create_session'):
            owner(unit.role)
        if operation in ('replay', 'replay_to', 'jump_next_event'):
            session_artifact = _persisted_session_artifact(db, str(workspace_id), args[0])
            if operation == 'replay':
                replay_command(args[1], args[0], session_artifact)
            elif operation == 'replay_to':
                require(session_artifact == 'BTL-OBSERVED-RESEARCH-SESSION-1',
                        'replayTo', 'REFUSED_OBSERVED_OPERATION')
            else:
                jump_next_event_request(args[1], args[0])
        # Serialize inexpensive count/admission across all API processes.
        db.execute('SELECT pg_advisory_xact_lock(2020,300)')
        previous = db.execute('SELECT * FROM btl.research_jobs WHERE id=%s', (job_id,)).fetchone()
        if previous:
            require((previous['actor_id'], previous['workspace_id']) == (actor_id, workspace_id), 'job', 'RESOURCE_UNAVAILABLE')
            require(previous['input_hash'] == digest, 'jobInput', 'IDEMPOTENCY_CONFLICT')
            return view(previous)
        _reap_expired_leases(db)
        _expire_queued(db)
        counts = db.execute("SELECT count(*) AS global_count,count(*) FILTER (WHERE actor_id=%s) AS user_count FROM btl.research_jobs WHERE state='QUEUED'", (actor_id,)).fetchone()
        require(counts['global_count'] < GLOBAL_LIMIT and counts['user_count'] < USER_LIMIT, 'queue', 'QUEUE_CAPACITY')
        # Bounded completed operational receipts; canonical financial history is untouched.
        db.execute("DELETE FROM btl.research_jobs WHERE id IN (SELECT id FROM btl.research_jobs WHERE state NOT IN ('QUEUED','RUNNING') ORDER BY finished_at DESC,id OFFSET %s)", (RETAINED_LIMIT-GLOBAL_LIMIT-1,))
        row = db.execute("INSERT INTO btl.research_jobs(id,actor_id,workspace_id,operation,input,input_hash,state) VALUES (%s,%s,%s,%s,%s,%s,'QUEUED') RETURNING *",
                         (job_id, actor_id, workspace_id, operation, raw, digest)).fetchone()
        return view(row)


def inspect(dsn, actor_id, workspace_id, job_id, *, cancel=False):
    with connect(dsn) as db:
        scoped(db, actor_id, workspace_id)
        row = db.execute('SELECT * FROM btl.research_jobs WHERE id=%s AND actor_id=%s AND workspace_id=%s',
                         (job_id, actor_id, workspace_id)).fetchone()
        require(row is not None, 'job', 'RESOURCE_UNAVAILABLE')
        if not cancel and row['state'] == 'QUEUED':
            # Status polling is a hot path. Do not run global recovery scans or
            # lock a healthy queued row; reconcile only this job when its own
            # durable deadline has actually elapsed.
            state = ('RECONCILE_REQUIRED' if row['operation'] in MUTATING_OPERATIONS else 'EXPIRED')
            recovered = db.execute("""
                UPDATE btl.research_jobs SET state=%s,result=NULL,finished_at=clock_timestamp()
                WHERE id=%s AND actor_id=%s AND workspace_id=%s AND state='QUEUED'
                  AND expires_at <= clock_timestamp() RETURNING *
            """, (state, job_id, actor_id, workspace_id)).fetchone()
            return view(recovered or row)
        if not cancel and row['state'] == 'RUNNING':
            # Recover just this expired lease if it is the polled job. A
            # heartbeat/finalizer racing this update wins by changing the
            # lease predicate; mutating jobs remain reconciliation-required
            # once cancellation/retry certainty is lost.
            cancelled = row.get('cancel_requested_at') is not None
            retry = not cancelled and row['attempts'] < MAX_JOB_ATTEMPTS
            state = ('CANCELLED' if cancelled and row['operation'] not in MUTATING_OPERATIONS else
                     'RECONCILE_REQUIRED' if cancelled or not retry and row['operation'] in MUTATING_OPERATIONS else
                     'FAILED' if not retry else 'QUEUED')
            recovered = db.execute("""
                UPDATE btl.research_jobs SET state=%s,
                    expires_at=CASE WHEN %s THEN clock_timestamp()+(%s*interval '1 second') ELSE expires_at END,
                    result=NULL,finished_at=CASE WHEN %s THEN NULL ELSE clock_timestamp() END,
                    lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL
                WHERE id=%s AND actor_id=%s AND workspace_id=%s AND state='RUNNING'
                  AND lease_until <= clock_timestamp() RETURNING *
            """, (state, state == 'QUEUED', QUEUE_TTL_SECONDS, state == 'QUEUED',
                  job_id, actor_id, workspace_id)).fetchone()
            return view(recovered or row)
        if row['state'] == 'QUEUED':
            # SKIP LOCKED: a claim that won the race is reported as RUNNING, never cancelled falsely.
            claimed = db.execute("SELECT * FROM btl.research_jobs WHERE id=%s FOR UPDATE SKIP LOCKED", (job_id,)).fetchone()
            if not claimed:
                return {**view(row), 'state': 'RUNNING', 'cancellation': 'WAIT_FOR_RESULT'}
            row = claimed
            if row['state'] != 'QUEUED':
                return view(row)
            if cancel:
                state = 'RECONCILE_REQUIRED' if row['operation'] in MUTATING_OPERATIONS or row['operation']=='create_session' else 'CANCELLED'
                row = db.execute("UPDATE btl.research_jobs SET state=%s,cancel_requested_at=clock_timestamp(),finished_at=clock_timestamp() WHERE id=%s AND state='QUEUED' RETURNING *", (state, job_id)).fetchone() or row
            elif not db.execute('SELECT clock_timestamp()<%s AS valid',(row['expires_at'],)).fetchone()['valid']:
                state = 'RECONCILE_REQUIRED' if row['operation'] in MUTATING_OPERATIONS or row['operation']=='create_session' else 'EXPIRED'
                row = db.execute("UPDATE btl.research_jobs SET state=%s,finished_at=clock_timestamp() WHERE id=%s AND state='QUEUED' RETURNING *",(state, job_id)).fetchone()
        elif row['state'] == 'RUNNING' and cancel:
            row = db.execute("UPDATE btl.research_jobs SET cancel_requested_at=COALESCE(cancel_requested_at,clock_timestamp()) WHERE id=%s AND state='RUNNING' RETURNING *",
                             (job_id,)).fetchone() or row
        return view(row)


def work_one(dsn, runner):
    """Claim durably, heartbeat a short lease, and finalize by lease fencing token."""
    with connect(dsn) as db:
        db.row_factory = dict_row
        slot = next((i for i in range(WORKERS) if db.execute(
            'SELECT pg_try_advisory_lock(2020,%s) AS acquired', (310+i,)).fetchone()['acquired']), None)
        if slot is None:
            return False
        _reap_expired_leases(db)
        _expire_queued(db)
        # FIFO per actor; cross-actor short reads can pass a fresh multi-chunk
        # replay. Aging returns long jobs to the ordinary fair rotation.
        row = db.execute(_CLAIM_NEXT_JOB).fetchone()
        if row is None:
            return False
        if not db.execute('SELECT clock_timestamp()<%s AS valid', (row['expires_at'],)).fetchone()['valid']:
            state = 'RECONCILE_REQUIRED' if row['operation'] in MUTATING_OPERATIONS else 'EXPIRED'
            db.execute('UPDATE btl.research_jobs SET state=%s,finished_at=clock_timestamp() WHERE id=%s AND state=\'QUEUED\'',
                       (state, row['id']))
            return True
        lease_owner = uuid.uuid4()
        row = db.execute("""
            UPDATE btl.research_jobs SET state='RUNNING',lease_owner=%s,
                lease_until=clock_timestamp() + (%s * interval '1 second'),
                heartbeat_at=clock_timestamp(),attempts=attempts+1
            WHERE id=%s AND state='QUEUED' RETURNING *
        """, (lease_owner, LEASE_SECONDS, row['id'])).fetchone()
        require(row is not None, 'jobClaim', 'RESOURCE_UNAVAILABLE')
        db.execute("""
            INSERT INTO btl.research_queue_actor_turns(actor_id,last_claimed_at)
            VALUES (%s,clock_timestamp())
            ON CONFLICT(actor_id) DO UPDATE SET last_claimed_at=EXCLUDED.last_claimed_at
        """, (row['actor_id'],))
        if row['attempts'] == 1:
            queue_metrics_raw, queue_metrics_hash = _queue_wait_measurements(row['created_at'], row['heartbeat_at'])
            if queue_metrics_raw is not None:
                db.execute("""
                    UPDATE btl.research_jobs SET queue_metrics=%s,queue_metrics_hash=%s
                    WHERE id=%s AND state='RUNNING' AND lease_owner=%s
                      AND queue_metrics IS NULL AND queue_metrics_hash IS NULL
                """, (queue_metrics_raw, queue_metrics_hash, row['id'], lease_owner))
        db.commit()  # Release the row lock; the session-level worker slot stays fenced.
        started = monotonic()
        stop_heartbeat = Event()

        def heartbeat():
            while not stop_heartbeat.wait(HEARTBEAT_SECONDS):
                try:
                    with connect(dsn) as beat_db:
                        refreshed = beat_db.execute("""
                            UPDATE btl.research_jobs SET heartbeat_at=clock_timestamp(),
                                lease_until=clock_timestamp() + (%s * interval '1 second')
                            WHERE id=%s AND state='RUNNING' AND lease_owner=%s RETURNING id
                        """, (LEASE_SECONDS, row['id'], lease_owner)).fetchone()
                    if refreshed is None:
                        return
                except Exception as error:
                    logging.getLogger(__name__).warning(
                        'research_job_heartbeat_failed job_id=%s error_type=%s',
                        row['id'], type(error).__name__)

        heartbeat_thread = Thread(target=heartbeat, name=f"btl-job-heartbeat-{row['id']}", daemon=True)
        heartbeat_thread.start()
        worker_metrics_raw = worker_metrics_hash = None
        try:
            try:
                payload = json.loads(bytes(row['input']))
            except (ValueError, UnicodeError):
                raise ContractError('CORRUPT_RECORD', 'job') from None
            require(content_hash(payload) == row['input_hash'] and payload['operation'] == row['operation'], 'jobHash', 'CORRUPT_RECORD')
            args = payload['args']
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
            elif row['operation'] == 'jump_next_event':
                result = runner(dsn, row['actor_id'], row['workspace_id'], 'jump_next_event', tuple(args), write=True)
            elif row['operation'] == 'create_session':
                result = runner(dsn, row['actor_id'], row['workspace_id'], 'create_session', tuple(args), write=True)
            else:
                result = runner(dsn, row['actor_id'], row['workspace_id'], row['operation'], tuple(args))
                require(monotonic()-started <= 30, 'deadline', 'EXPIRED')
            raw = canonical_bytes({'schemaVersion': 1, **result})
            require(len(raw) <= 8388608, 'result', 'REFUSED_RESPONSE_LIMIT')
            worker_metrics_raw, worker_metrics_hash = _worker_measurements(result)
            state = 'SUCCEEDED'
        except ContractError as error:
            logging.getLogger(__name__).warning(
                'research_job_failed job_id=%s operation=%s error_code=%s error_field=%s error_source=%s',
                row['id'], row['operation'], error.code, error.field,
                getattr(error,'source','worker'))
            worker_metrics_raw, worker_metrics_hash = _worker_measurements(error)
            raw = None
            state = 'RECONCILE_REQUIRED' if row['operation'] in MUTATING_OPERATIONS else ('EXPIRED' if error.code == 'EXPIRED' else 'FAILED')
        except BaseException:
            # Leave RUNNING durable. Lease expiry performs the bounded retry or
            # reconciliation transition after this process and its heartbeat exit.
            raise
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=HEARTBEAT_SECONDS + 1)

        latest = db.execute('SELECT cancel_requested_at FROM btl.research_jobs WHERE id=%s AND state=\'RUNNING\' AND lease_owner=%s FOR UPDATE',
                             (row['id'], lease_owner)).fetchone()
        if latest is None:
            return True  # A newer fencing token owns recovery; durable inner receipt remains authoritative.
        cancelled = latest['cancel_requested_at'] is not None
        if cancelled and row['operation'] not in MUTATING_OPERATIONS:
            state, raw = 'CANCELLED', None
        elif cancelled and state != 'SUCCEEDED':
            state, raw = 'RECONCILE_REQUIRED', None
        db.execute("""
            UPDATE btl.research_jobs SET state=%s,result=%s,worker_metrics=%s,worker_metrics_hash=%s,
                finished_at=clock_timestamp(),
                lease_owner=NULL,lease_until=NULL,heartbeat_at=NULL
            WHERE id=%s AND state='RUNNING' AND lease_owner=%s
        """, (state, raw, worker_metrics_raw, worker_metrics_hash, row['id'], lease_owner))
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
