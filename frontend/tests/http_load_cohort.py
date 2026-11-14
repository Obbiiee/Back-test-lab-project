"""Parent side of the HTTP-level synthetic trader cohort (QA/measurement only). Opt-in via RIKSORA_QA_HTTP_DRIVER=1.

Runs backend/tools/claude_exp/stack/http_driver.py as a separate process against the harness's own real API/queue/worker/PostgreSQL,
and samples host/cgroup/queue state every second. Stops (and reports CAPACITY_RESOURCE_STOP) on the existing gates: MemAvailable < 10 GiB,
free disk < 30 GiB, swap present; plus the addendum's 80% host CPU gate (5 consecutive 1 s samples). Not a browser measurement.
"""
import json, os, subprocess, sys, threading, time
from pathlib import Path

DRIVER = Path(__file__).resolve().parents[2] / 'backend/tools/claude_exp/stack/http_driver.py'


def _cpu_times():
    f = Path('/proc/stat').read_text().splitlines()[0].split()[1:]
    v = list(map(int, f)); idle = v[3] + v[4]
    return sum(v), idle


def run_http_cohort(*, url, delivery, cohort_size, report, dsn, system_resources, nearest_rank, cycles, think_ms, stagger_ms, proc_snapshot=None):
    import psycopg
    began_res = system_resources()
    # Guard against a mis-configured pool: the queue loops, the native slots and the exchange pool must all have the same size
    # (a harness that only patched queue.WORKERS produced invalid 3/4-worker results).
    from cloud import queue as _q0, worker as _w0
    sizes = (_q0.WORKERS, len(_w0._slots), _w0._exchanges._max_workers)
    if len(set(sizes)) != 1:
        raise RuntimeError('HARNESS_WORKER_POOL_MISMATCH')
    report['workerPool'] = dict(queueWorkers=sizes[0], nativeSlots=sizes[1], exchangeThreads=sizes[2])
    trace_path = os.environ.get('RIKSORA_QA_QUEUE_TRACE')
    if trace_path:
        # Measurement-only instrumentation: wraps (does not edit) product functions in this QA process to record timings/exceptions.
        import functools, traceback
        from cloud import queue as _q, worker as _w
        tlock = threading.Lock(); t00 = time.monotonic()
        def _log(**kw):
            kw['t'] = round(time.monotonic() - t00, 3); kw['thread'] = threading.get_ident()
            with tlock, open(trace_path, 'a') as f:
                f.write(json.dumps(kw) + '\n')
        _orig_work, _orig_inv = _q.work_one, _w.pooled_invoke
        @functools.wraps(_orig_work)
        def traced_work(dsn, runner):
            t = time.monotonic()
            try:
                r = _orig_work(dsn, runner)
                if r:
                    _log(ev='work_one', dur=round(time.monotonic() - t, 3), ok=True)
                return r
            except BaseException as e:
                _log(ev='work_one_exc', dur=round(time.monotonic() - t, 3), exc=type(e).__name__, msg=str(e)[:120],
                     tb=''.join(traceback.format_tb(e.__traceback__)[-3:])[-400:])
                raise
        @functools.wraps(_orig_inv)
        def traced_inv(dsn, payload, **kw):
            t = time.monotonic(); busy = sum(1 for sl in _w._slots if sl.lock.locked())
            _log(ev='invoke_start', op=payload.get('operation'), locked=[sl.lock.locked() for sl in _w._slots],
                 proc=[sl.process is not None for sl in _w._slots], jobs=[sl.jobs for sl in _w._slots])
            try:
                r = _orig_inv(dsn, payload, **kw)
                _log(ev='invoke', op=payload.get('operation'), dur=round(time.monotonic() - t, 3), slotsBusyAtStart=busy, ok=True)
                return r
            except BaseException as e:
                _log(ev='invoke_exc', op=payload.get('operation'), dur=round(time.monotonic() - t, 3), slotsBusyAtStart=busy, lockedNow=[sl.lock.locked() for sl in _w._slots], nslots=len(_w._slots),
                     exc=type(e).__name__, msg=str(getattr(e, 'code', e))[:80])
                raise
        _q.work_one, _w.pooled_invoke = traced_work, traced_inv
    samples, queue, cpu_pct, stop = [], [], [], {'reason': None}
    done = threading.Event()
    chart_proc = None; chart_args = []
    if os.environ.get('RIKSORA_QA_CHART') == '1':
        # Combined test: a separate chart-service process (OHLC objects, 5,000-candle history per timeframe) next to the product stack.
        root = Path(__file__).resolve().parents[2] / 'backend'
        chart_proc = subprocess.Popen([sys.executable, '-m', 'tools.claude_exp.stack.chart_server', '--store', os.environ['RIKSORA_QA_CHART_STORE'],
                                       '--source-compact', os.environ['RIKSORA_QA_CHART_COMPACT'], '--source-hash', os.environ['RIKSORA_QA_CHART_HASH'],
                                       '--traders', str(cohort_size)], cwd=root, stdout=subprocess.PIPE, text=True)
        ready = json.loads(chart_proc.stdout.readline())
        chart_args = ['--chart-url', f"http://127.0.0.1:{ready['port']}"]
    proc = subprocess.Popen([sys.executable, '-I', str(DRIVER), '--url', url, '--traders', str(cohort_size), '--cycles', str(cycles),
                             '--think-ms', str(think_ms), '--stagger-ms', str(stagger_ms)] + chart_args,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, start_new_session=True)
    summary = {}
    phase = {'measuring': False}
    cg = Path(began_res['cgroupPath']) if began_res.get('cgroupPath') else None
    snaps = {}

    def sampler():
        last = _cpu_times(); high = 0
        while not done.is_set():
            time.sleep(1)
            if not phase['measuring']:
                last = _cpu_times(); continue
            s = system_resources(); samples.append(s)
            if (s['memAvailableBytes'] is None or s['memAvailableBytes'] < 10 * 1024 ** 3 or
                    s['diskFreeBytes'] < 30 * 1024 ** 3 or s['swapTotalBytes'] != 0):
                stop['reason'] = 'CAPACITY_RESOURCE_STOP'; _kill(); return
            now = _cpu_times(); dt, di = now[0] - last[0], now[1] - last[1]; last = now
            pct = 100 * (dt - di) / dt if dt else 0; cpu_pct.append(pct)
            high = high + 1 if pct > 80 else 0
            if high >= 5:
                stop['reason'] = 'CAPACITY_CPU_GATE_80PCT'; _kill(); return
            try:
                with psycopg.connect(dsn, connect_timeout=2) as db:
                    r = db.execute("""SELECT count(*) FILTER (WHERE state='QUEUED'), count(*) FILTER (WHERE state='RUNNING'),
                        count(*) FILTER (WHERE state IN ('FAILED','EXPIRED','RECONCILE_REQUIRED')),
                        max(extract(epoch FROM (clock_timestamp()-created_at))) FILTER (WHERE state='QUEUED') FROM btl.research_jobs""").fetchone()
                queue.append(dict(queued=r[0], running=r[1], failed=r[2], oldestQueuedSeconds=float(r[3] or 0)))
                if trace_path:
                    with psycopg.connect(dsn, connect_timeout=2) as db2:
                        rr = db2.execute("SELECT operation,attempts,extract(epoch FROM (clock_timestamp()-heartbeat_at)),extract(epoch FROM (clock_timestamp()-created_at)) FROM btl.research_jobs WHERE state='RUNNING'").fetchall()
                    with psycopg.connect(dsn, connect_timeout=2) as db3:
                        term = db3.execute("SELECT count(*) FROM btl.research_jobs WHERE state NOT IN ('QUEUED','RUNNING')").fetchone()[0]
                    _log(ev='terminal_rows', n=term)
                    _log(ev='running_rows', n=len(rr), rows=[[x[0], x[1], round(float(x[2] or 0), 1), round(float(x[3] or 0), 1)] for x in rr][:45])
            except Exception:
                pass

    def _kill():
        try:
            os.killpg(proc.pid, 9)
        except ProcessLookupError:
            pass
    t = threading.Thread(target=sampler, daemon=True); t.start()
    for line in proc.stdout:
        item = json.loads(line)
        if item.get('need') == 'verification':
            proc.stdin.write(json.dumps(dict(email=item['email'], token=delivery.token(item['email'], 'verification'))) + '\n'); proc.stdin.flush()
        elif item.get('progress') == 'ready':
            if proc_snapshot and cg:
                snaps['before'] = proc_snapshot([proc.pid], cg)
            phase['measuring'] = True; t_run = time.monotonic()
        elif 'summary' in item:
            summary = item['summary']
    if proc_snapshot and cg and phase['measuring']:
        try:
            snaps['after'] = proc_snapshot([proc.pid], cg)
        except Exception:
            pass
    driver_acct = {}
    try:
        st = Path(f'/proc/{proc.pid}/stat').read_text(); f = st[st.rfind(')') + 2:].split()
        driver_acct = dict(cpuSeconds=round((int(f[11]) + int(f[12])) / os.sysconf('SC_CLK_TCK'), 2))
    except Exception:
        pass
    chart_acct = {}
    if chart_proc is not None:
        try:
            st = Path(f'/proc/{chart_proc.pid}/stat').read_text(); f = st[st.rfind(')') + 2:].split()
            chart_acct = dict(cpuSeconds=round((int(f[11]) + int(f[12])) / os.sysconf('SC_CLK_TCK'), 2),
                              rssMb=round(int(f[21]) * os.sysconf('SC_PAGE_SIZE') / 2**20, 1))
            hwm = [l for l in Path(f'/proc/{chart_proc.pid}/status').read_text().splitlines() if l.startswith('VmHWM')]
            chart_acct['peakRssMb'] = round(int(hwm[0].split()[1]) / 1024, 1) if hwm else None
        except Exception:
            pass
        chart_proc.kill(); chart_proc.wait()
    proc.wait(); done.set(); t.join(2)
    elapsed = max(0.001, time.monotonic() - t_run) if phase['measuring'] else 0
    cpu0 = began_res['cgroup'].get('cpuUsageUsec') or 0
    cpu1 = max((s['cgroup'].get('cpuUsageUsec') or 0 for s in samples), default=cpu0)
    ticks = os.sysconf('SC_CLK_TCK'); cpu_by = {}
    if 'before' in snaps and 'after' in snaps and elapsed:
        for who in ('service', 'postgres', 'generator'):
            d = max(0, snaps['after'][who + 'CpuTicks'] - snaps['before'][who + 'CpuTicks'])
            cpu_by[who] = dict(cpuSeconds=round(d / ticks, 2), coresAverage=round(d / ticks / elapsed, 3))
        cpu_by['note'] = 'service = API + in-process queue workers (one OS process); generator = HTTP driver; CPU of exited processes is not included'
    report['capacity'] = dict(driverProcess=driver_acct, chartServiceProcess=chart_acct, processCpu=cpu_by, measuredSeconds=round(elapsed, 1),
        measurementKind='HTTP_DRIVER_NO_BROWSER_SYNTHETIC', cohortSize=cohort_size, stopReason=stop['reason'], driver=summary,
        host=dict(memAvailableMinBytes=min((s['memAvailableBytes'] for s in samples), default=None),
                  cgroupMemoryPeakBytes=max((s['cgroup'].get('memoryPeakBytes') or 0 for s in samples), default=None),
                  cgroupCpuCoresAverage=round((cpu1 - cpu0) / 1e6 / elapsed, 3) if elapsed else None,
                  hostCpuBusyPercent=dict(p50=nearest_rank(cpu_pct, .5), p95=nearest_rank(cpu_pct, .95), max=round(max(cpu_pct), 1) if cpu_pct else None),
                  cgroupCpuThrottledUsec=max(0, max((s['cgroup'].get('cpuThrottledUsec') or 0 for s in samples), default=0) -
                                             (began_res['cgroup'].get('cpuThrottledUsec') or 0))),
        queue=dict(maxQueued=max((q['queued'] for q in queue), default=0), maxRunning=max((q['running'] for q in queue), default=0),
                   maxFailed=max((q['failed'] for q in queue), default=0),
                   maxOldestQueuedSeconds=round(max((q['oldestQueuedSeconds'] for q in queue), default=0), 2)))
    if stop['reason']:
        raise RuntimeError(stop['reason'])
    if summary.get('status') != 'DONE' or summary.get('failedTraders'):
        raise RuntimeError('HTTP_COHORT_FAILED')
