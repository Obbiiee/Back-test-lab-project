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
ENTRY = 'import sys; sys.path[:0]=sys.argv[1:]; from cloud.worker import child; child()'
SERVE_ENTRY = 'import sys; sys.path[:0]=sys.argv[1:]; from cloud.worker import serve; serve()'
MAX_JOBS = 32
_exchanges = ThreadPoolExecutor(max_workers=2, thread_name_prefix='btl-native-exchange')


class _Slot:
    """One native child; at most two controller slots, never a consumer handle."""
    def __init__(self):
        self.lock = Lock()
        self.process = None
        self.dsn = None
        self.jobs = 0

    def close(self):
        process, self.process = self.process, None
        self.dsn, self.jobs = None, 0
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
                   or k in ('BTL_OBSERVED_OPERATOR_CATALOG','BTL_OBSERVED_OPERATOR_CATALOG_SHA256')}
    environment['BTL_WORKER_DATABASE'] = dsn
    return environment


def _argv(entry):
    return [getattr(sys, '_base_executable', sys.executable), '-I', '-B', '-c', entry,
            str(Path(__file__).resolve().parents[1]), sysconfig.get_path('purelib')]


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
    slot = next((candidate for candidate in _slots if candidate.lock.acquire(False)), None)
    if slot is None:
        raise RuntimeError('Native worker slots unavailable')
    future = None
    try:
        began = monotonic()
        if slot.process is not None and (slot.dsn != dsn or slot.jobs >= MAX_JOBS or slot.process.poll() is not None):
            slot.close()
        if slot.process is None:
            slot.process = subprocess.Popen(_argv(SERVE_ENTRY), stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                            env=_environment(dsn),
                                            cwd=Path(__file__).resolve().parents[1])
            slot.dsn = dsn
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
    require(operation in ('workspace', 'bootstrap', 'apply'), 'workerOperation')
    return pooled_invoke(dsn, dict(schemaVersion=1, actor=str(actor_id), workspace=str(workspace_id),
                            operation=operation, args=list(args), write=write))


def _execute(raw):
    """Trusted process entry; scope and canonical validation remain in runner."""
    try:
        require(len(raw) <= 32768, 'workerInput')
        request = json.loads(raw)
        require(request.get('schemaVersion') == 1 and
                request.get('operation') in ('workspace', 'bootstrap', 'apply'), 'workerInput')
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
    # EOF on parent exit ends the child; no unrestricted service/socket exists.
    for _ in range(MAX_JOBS):
        raw = sys.stdin.buffer.readline(32770)
        if not raw:
            return
        if not raw.endswith(b'\n') or len(raw) > 32769:
            return
        sys.stdout.buffer.write(_execute(raw[:-1])+b'\n')
        sys.stdout.buffer.flush()
