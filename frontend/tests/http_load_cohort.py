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
    samples, queue, cpu_pct, stop = [], [], [], {'reason': None}
    done = threading.Event()
    proc = subprocess.Popen([sys.executable, '-I', str(DRIVER), '--url', url, '--traders', str(cohort_size), '--cycles', str(cycles),
                             '--think-ms', str(think_ms), '--stagger-ms', str(stagger_ms)],
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
    report['capacity'] = dict(processCpu=cpu_by, measuredSeconds=round(elapsed, 1),
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
