"""Low-overhead QA-only timing for the historical one-day acceptance runner.

Timers are observational only. Nested entries are inclusive and intentionally
overlap; stage totals and top-level command wall/CPU time do not sum together.
"""
from collections import defaultdict
from contextlib import contextmanager
import sys
import time
from pathlib import Path

_data = defaultdict(lambda: {'wallNs': 0, 'cpuNs': 0, 'calls': 0})
_stage = 'setup'
_installed = False


def _record(name, wall, cpu, server_cpu=0):
    row = _data[( _stage, name)]
    row['wallNs'] += wall
    row['cpuNs'] += cpu
    row['calls'] += 1
    if server_cpu: row['postgresServerCpuNs'] = row.get('postgresServerCpuNs', 0) + server_cpu


def _postgres_cpu_ns():
    root = Path(__import__('os').environ.get('BTL_QA_CLUSTER_ROOT', ''))
    try: root_pid = int((root/'data/postmaster.pid').read_text().splitlines()[0])
    except (OSError, ValueError, IndexError): return 0
    processes = {}
    for item in Path('/proc').iterdir():
        if not item.name.isdigit(): continue
        try:
            raw = (item/'stat').read_text(); rest = raw[raw.rfind(')')+2:].split()
            processes[int(item.name)] = (int(rest[1]), int(rest[11])+int(rest[12]))
        except (OSError, ValueError, IndexError): pass
    included = {root_pid}; changed = True
    while changed:
        changed = False
        for pid, (parent, _) in processes.items():
            if parent in included and pid not in included:
                included.add(pid); changed = True
    ticks = sum(processes[pid][1] for pid in included if pid in processes)
    return int(ticks*1_000_000_000/__import__('os').sysconf('SC_CLK_TCK'))


@contextmanager
def phase(name, *, postgres_cpu=False):
    wall = time.perf_counter_ns(); cpu = time.process_time_ns()
    pg_before = _postgres_cpu_ns() if postgres_cpu else 0
    try:
        yield
    finally:
        pg_after = _postgres_cpu_ns() if postgres_cpu else 0
        _record(name, time.perf_counter_ns()-wall, time.process_time_ns()-cpu,
                max(0, pg_after-pg_before))


@contextmanager
def stage(name):
    global _stage
    previous = _stage; _stage = name
    try:
        yield
    finally:
        _stage = previous


def _wrap(module, name, label):
    original = getattr(module, name, None)
    if not callable(original) or getattr(original, '__qa_perf_wrapped__', False):
        return
    def measured(*args, **kwargs):
        with phase(label):
            return original(*args, **kwargs)
    measured.__name__ = getattr(original, '__name__', name)
    measured.__qa_perf_wrapped__ = True
    setattr(module, name, measured)


def _wrap_method(cls, name, label, *, postgres_cpu=False):
    original = getattr(cls, name, None)
    if not callable(original) or getattr(original, '__qa_perf_wrapped__', False):
        return
    def measured(self, *args, **kwargs):
        with phase(label, postgres_cpu=postgres_cpu):
            return original(self, *args, **kwargs)
    measured.__name__ = getattr(original, '__name__', name)
    measured.__qa_perf_wrapped__ = True
    setattr(cls, name, measured)


class _TimedSQLite:
    """Proxy the timeline-owned SQLite connection; provider DBs stay separate."""
    def __init__(self, connection): self._connection = connection
    def execute(self, *args, **kwargs):
        with phase('sqlite.execute'): return self._connection.execute(*args, **kwargs)
    def executemany(self, *args, **kwargs):
        with phase('sqlite.executemany'): return self._connection.executemany(*args, **kwargs)
    def executescript(self, *args, **kwargs):
        with phase('sqlite.executescript'): return self._connection.executescript(*args, **kwargs)
    def commit(self, *args, **kwargs):
        with phase('sqlite.commit'): return self._connection.commit(*args, **kwargs)
    def rollback(self, *args, **kwargs):
        with phase('sqlite.rollback'): return self._connection.rollback(*args, **kwargs)
    def __getattr__(self, key): return getattr(self._connection, key)


def install():
    """Install timers on the existing QA controller/storage functions once."""
    global _installed
    if _installed: return
    import contracts.canonical as canonical
    import ticks.contracts_v2 as contracts_v2
    import ticks.storage_v2 as storage_v2
    import ticks.timeline_v2 as timeline_v2
    import execution.observed_admission as admission
    import execution.observed_controller as controller
    import execution.observed_kernel as kernel
    import execution.observed_postgres as postgres
    import execution.historical as historical

    # All loaded aliases point at these same functions. Patch aliases so costs
    # inside reducer, source timeline, packing and validation are observed.
    targets = [(canonical.content_hash, 'hash.content_hash'),
               (canonical.canonical_bytes, 'encoding.canonical_json'),
               (contracts_v2.hash_v2, 'hash.hash_v2'),
               (contracts_v2.canonical_v2_bytes, 'encoding.canonical_v2')]
    aliases = {}
    for module in list(sys.modules.values()):
        values = getattr(module, '__dict__', None)
        if not values: continue
        for name, value in list(values.items()):
            for original, label in targets:
                if value is original:
                    aliases[(id(module), name)] = (module, name, label, value)
                    break
    wrappers = {}
    for _, (_, _, label, original) in aliases.items():
        if original not in wrappers:
            def make_wrapper(fn, metric):
                def measured(*args, **kwargs):
                    with phase(metric): return fn(*args, **kwargs)
                measured.__name__ = getattr(fn, '__name__', metric)
                measured.__qa_perf_wrapped__ = True
                return measured
            wrappers[original] = make_wrapper(original, label)
    for module, name, _, original in aliases.values():
        setattr(module, name, wrappers[original])

    _wrap(admission, '_sha', 'source.archive_sha256')
    _wrap(controller, 'apply', 'kernel.reduce')
    _wrap_method(controller.ObservedExecutionController, 'apply', 'command.total')
    for method, label in (('prepare', 'postgres.prepare'), ('commit', 'postgres.commit'),
                          ('inspect', 'postgres.inspect')):
        _wrap_method(postgres.ObservedExecutionStore, method, label, postgres_cpu=True)
    _wrap_method(historical.IndexedTimelineCache, 'reveal', 'timeline.reveal')
    _wrap_method(historical.IndexedTimelineCache, '_entry', 'timeline.cache_entry')
    _wrap_method(timeline_v2.IndexedTickTimeline, 'advance_through', 'timeline.advance')
    _wrap_method(storage_v2.DiskTickProvider, 'read_page_v2', 'market_data.read_page')
    _wrap_method(storage_v2.DiskTickProvider, 'read_evidence_v2', 'market_data.read_evidence')
    for method, label in (('_fills', 'kernel.order_evaluation'), ('_advance', 'kernel.advance')):
        _wrap(kernel, method, label)

    original_connect = timeline_v2.connect
    def timed_connect(*args, **kwargs): return _TimedSQLite(original_connect(*args, **kwargs))
    timed_connect.__qa_perf_wrapped__ = True
    timeline_v2.connect = timed_connect
    _installed = True


def snapshot():
    result = {}
    for (stage_name, name), value in sorted(_data.items()):
        result.setdefault(stage_name, {})[name] = dict(value)
    return result


def merge(*snapshots):
    result = defaultdict(lambda: defaultdict(lambda: {'wallNs': 0, 'cpuNs': 0, 'calls': 0}))
    for snap in snapshots:
        for stage_name, phases in snap.items():
            for name, row in phases.items():
                target = result[stage_name][name]
                for key in ('wallNs', 'cpuNs', 'calls', 'postgresServerCpuNs'):
                    if key in row: target[key] = target.get(key, 0) + row[key]
    return {stage_name: dict(phases) for stage_name, phases in result.items()}
