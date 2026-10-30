"""Controller-only native process deadline; no new financial implementation."""
import atexit
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
from threading import Lock
from time import monotonic
import uuid

from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError, require

MAX_RESULT = 8388608
DEADLINE = 30
STARTUP_WARMUP_DEADLINE = 180
ENTRY = 'import sys; sys.path[:0]=sys.argv[1:]; from cloud.worker import child; child()'
SERVE_ENTRY = 'import sys; sys.path[:0]=sys.argv[1:]; from cloud.worker import serve; serve()'
# Keep the hash-pinned observed archive admitted across replay chunks. The
# process remains bounded and is still reaped on every timeout/service close;
# frequent recycling would rehash the entire multi-GB archive every 32 jobs.
MAX_JOBS = 4096
WARM_REQUEST = b'{"control":"WARM_OPERATOR_SOURCES","schemaVersion":1}\n'
_exchanges = ThreadPoolExecutor(max_workers=2, thread_name_prefix='btl-native-exchange')


class _Slot:
    """One native child; at most two controller slots, never a consumer handle."""
    def __init__(self):
        self.lock = Lock()
        self.process = None
        self.dsn = None
        self.jobs = 0
        self.ready = False

    def close(self):
        process, self.process = self.process, None
        self.dsn, self.jobs, self.ready = None, 0, False
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdin.close()
            process.stdout.close()


_slots = (_Slot(), _Slot())


def close():
    # API lifespan invokes this after its admitted worker threads finish.
    for slot in _slots:
        with slot.lock:
            slot.close()
    from .research import close_operator_catalogs
    close_operator_catalogs()


atexit.register(close)


def _environment(dsn):
    environment = {k: v for k, v in os.environ.items()
                   if k.upper() in ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP')
                   or k in ('BTL_OBSERVED_OPERATOR_CATALOG','BTL_OBSERVED_OPERATOR_CATALOG_SHA256','BTL_QA_TIMELINE_LOG_CODEC')}
    require(environment.get('BTL_QA_TIMELINE_LOG_CODEC') in (None, 'raw', 'zlib-1'), 'logCodec')
    environment['BTL_WORKER_DATABASE'] = dsn
    require(type(MAX_JOBS) is int and 1 <= MAX_JOBS <= 120000, 'workerJobLimit')
    environment['BTL_WORKER_MAX_JOBS'] = str(MAX_JOBS)
    return environment


def _argv(entry):
    return [getattr(sys, '_base_executable', sys.executable), '-I', '-B', '-c', entry,
            str(Path(__file__).resolve().parents[1]), sysconfig.get_path('purelib')]


def _start_slot(slot, dsn, timeout):
    slot.process = subprocess.Popen(_argv(SERVE_ENTRY), stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    env=_environment(dsn),
                                    cwd=Path(__file__).resolve().parents[1])
    slot.dsn = dsn
    process = slot.process
    future = _exchanges.submit(lambda: (process.stdin.write(WARM_REQUEST), process.stdin.flush(),
                                        process.stdout.readline(MAX_RESULT+2))[2])
    try:
        raw = future.result(timeout=timeout)
    except FutureTimeout:
        slot.close()
        try:
            future.result()
        except Exception:
            pass
        raise ContractError('EXPIRED', 'workerWarmupDeadline') from None
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        slot.close()
        raise ContractError('WORKER_UNAVAILABLE', 'workerWarmup') from None
    if not (raw.endswith(b'\n') and type(result) is dict and result.get('schemaVersion') == 1
            and result.get('ready') is True):
        slot.close()
        raise ContractError('WORKER_UNAVAILABLE', 'workerWarmup')
    slot.ready = True


def warm_sources(dsn, *, deadline=STARTUP_WARMUP_DEADLINE):
    """Admit configured sources before queued work starts, outside job deadlines."""
    require(type(deadline) in (int, float) and 0 < deadline <= STARTUP_WARMUP_DEADLINE, 'deadline')
    if not os.environ.get('BTL_OBSERVED_OPERATOR_CATALOG'):
        return False
    slot = _slots[0]
    if not slot.lock.acquire(False):
        raise ContractError('RESEARCH_BUSY', 'workerWarmup')
    try:
        if slot.process is not None and (slot.dsn != dsn or slot.process.poll() is not None):
            slot.close()
        if slot.process is None:
            _start_slot(slot, dsn, deadline)
        return slot.ready
    finally:
        slot.lock.release()


def _result(raw):
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise RuntimeError('Worker result unavailable') from None
    require(type(value) is dict, 'workerResult', 'CORRUPT_RECORD')
    if value.get('infrastructureFailure'):
        raise RuntimeError('Worker infrastructure unavailable')
    if value.get('error'):
        raise ContractError(value['error'], 'worker')
    require(value.get('schemaVersion') == 1 and type(value.get('result')) is dict,
            'workerResult', 'CORRUPT_RECORD')
    return value['result']


def pooled_invoke(dsn, payload, *, deadline=DEADLINE):
    """Reuse bounded immutable fixture caches; scope is revalidated per job.

    The job deadline still kills/reaps its exact child. No result from a killed
    process can be reused; durable financial reconciliation remains queue-owned.
    """
    require(type(deadline) in (int, float) and 0 < deadline <= DEADLINE, 'deadline')
    raw = canonical_bytes(payload)
    require(len(raw) <= 32768, 'workerInput')
    # The configured catalog and its admitted handles live in one controller
    # process. Keep observed-family work on the warmed slot instead of causing
    # a second full archive admission in a parallel cold slot.
    observed_family = (type(payload) is dict and payload.get('operation') in ('apply', 'replay_to')
                       and type(payload.get('args')) is list and len(payload['args']) == 2
                       and type(payload['args'][1]) is dict
                      and payload['args'][1].get('artifact') in ('BTL-OBSERVED-EXECUTION-COMMAND-1', 'BTL-OBSERVED-REPLAY-TO-1'))
    candidates = (_slots[0],) if observed_family and os.environ.get('BTL_OBSERVED_OPERATOR_CATALOG') else _slots
    slot = next((candidate for candidate in candidates if candidate.lock.acquire(False)), None)
    if slot is None:
        raise RuntimeError('Native worker slots unavailable')
    future = None
    try:
        if slot.process is not None and (slot.dsn != dsn or slot.jobs >= MAX_JOBS or slot.process.poll() is not None):
            slot.close()
        if slot.process is None:
            # Source admission belongs to the startup phase, including safe
            # slot rotation after MAX_JOBS or a killed worker. It must not eat
            # into the separate per-job execution deadline.
            _start_slot(slot, dsn, STARTUP_WARMUP_DEADLINE)
        began = monotonic()
        process = slot.process
        def exchange():
            process.stdin.write(raw+b'\n')
            process.stdin.flush()
            return process.stdout.readline(MAX_RESULT+2)
        future = _exchanges.submit(exchange)
        try:
            output = future.result(timeout=max(0, deadline-(monotonic()-began)))
        except FutureTimeout:
            slot.close()
            # Killing the child closes its pipe and releases the bounded reader.
            try:
                future.result()
            except Exception:
                pass
            raise ContractError('EXPIRED', 'workerDeadline') from None
        require(output.endswith(b'\n') and len(output) <= MAX_RESULT+1,
                'workerResult', 'WORKER_UNAVAILABLE')
        slot.jobs += 1
        return _result(output)
    except BaseException:
        slot.close()
        raise
    finally:
        slot.lock.release()


def invoke(dsn, payload, *, deadline=DEADLINE):
    """Only server-owned paths/entrypoint; credentials never enter argv/output."""
    require(type(deadline) in (int, float) and 0 < deadline <= DEADLINE, 'deadline')
    raw = canonical_bytes(payload)
    require(len(raw) <= 32768, 'workerInput')
    # Bypass Windows venv launcher: terminating a launcher alone could leave
    # its real Python child executing. -I also rejects inherited Python hooks.
    try:
        completed = subprocess.run(
            _argv(ENTRY),
            input=raw, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=_environment(dsn), timeout=deadline,
            cwd=Path(__file__).resolve().parents[1])
    except subprocess.TimeoutExpired:
        # subprocess.run kills and reaps this exact native process before raise.
        raise ContractError('EXPIRED', 'workerDeadline') from None
    require(completed.returncode == 0 and len(completed.stdout) <= MAX_RESULT,
            'workerResult', 'WORKER_UNAVAILABLE')
    return _result(completed.stdout)


def run(dsn, actor_id, workspace_id, operation, args=(), *, write=False):
    require(operation in ('create_session', 'workspace', 'bootstrap', 'chart_history', 'apply', 'replay_to'), 'workerOperation')
    return pooled_invoke(dsn, dict(schemaVersion=1, actor=str(actor_id), workspace=str(workspace_id),
                            operation=operation, args=list(args), write=write))


def _execute(raw):
    """Trusted process entry; scope and canonical validation remain in runner."""
    try:
        require(len(raw) <= 32768, 'workerInput')
        request = json.loads(raw)
        require(request.get('schemaVersion') == 1 and
                request.get('operation') in ('create_session', 'workspace', 'bootstrap', 'chart_history', 'apply', 'replay_to'), 'workerInput')
        from .research import run as authorized_run
        result = authorized_run(os.environ['BTL_WORKER_DATABASE'], uuid.UUID(request['actor']),
                                uuid.UUID(request['workspace']), request['operation'],
                                tuple(request['args']), write=request['write'])
        output = canonical_bytes(dict(schemaVersion=1, result=result))
        require(len(output) <= MAX_RESULT, 'result', 'REFUSED_RESPONSE_LIMIT')
    except ContractError as error:
        output = canonical_bytes(dict(schemaVersion=1, error=error.code))
    except Exception:
        output = canonical_bytes(dict(schemaVersion=1, infrastructureFailure=True))
    return output


def child():
    sys.stdout.buffer.write(_execute(sys.stdin.buffer.read(32769)))
    sys.stdout.buffer.flush()


def serve():
    # The first private pipe message warms only operator-pinned source handles.
    # It is bounded by the parent's startup deadline and never becomes a job.
    raw = sys.stdin.buffer.readline(32770)
    if raw != WARM_REQUEST:
        return
    try:
        dsn = os.environ['BTL_WORKER_DATABASE']
        from .research import _operator_catalog
        catalog = _operator_catalog(dsn)
        if catalog is not None:
            for profile_hash in sorted(catalog._profiles):
                catalog.resolve(profile_hash)
        ready = True
    except Exception:
        ready = False
    sys.stdout.buffer.write(canonical_bytes(dict(schemaVersion=1, ready=ready))+b'\n')
    sys.stdout.buffer.flush()
    if not ready:
        return
    # EOF on parent exit ends the child; no unrestricted service/socket exists.
    job_limit = int(os.environ.get('BTL_WORKER_MAX_JOBS', str(MAX_JOBS)))
    require(1 <= job_limit <= 120000, 'workerJobLimit')
    for _ in range(job_limit):
        raw = sys.stdin.buffer.readline(32770)
        if not raw:
            return
        if not raw.endswith(b'\n') or len(raw) > 32769:
            return
        sys.stdout.buffer.write(_execute(raw[:-1])+b'\n')
        sys.stdout.buffer.flush()
