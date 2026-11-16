"""Stage runner for the VPS1 maximum-economic-capacity benchmark (SYNTHETIC / TEST ONLY; V2 checkpoint opt-in QA).

  python capacity_http.py stage --name s01 --spec swing:1,scalper:1 --duration 120 --ramp 10 --ticks 65536 --workers 3
  python capacity_http.py sut ...        (internal: runs PostgreSQL + real FastAPI/uvicorn + queue + native workers inside ONE cgroup scope)

Topology (all on VPS1, owner budget 5 vCPU / 14 GiB, cgroup-enforced):
  scope A (SUT)       PostgreSQL 17 + uvicorn/FastAPI API + durable queue + native workers   CPUQuota 400 %, MemoryMax 11G, cores 0-3
  scope B (generator) capacity_http_driver.py (httpx asyncio)                                CPUQuota 100 %, MemoryMax 2G,  core 4
  core 5 / remainder  OS, this orchestrator (light polling)
Affinity is NOT exclusive CPU; cache, memory bandwidth and I/O are still shared. Loopback HTTP, no TLS, no reverse proxy.
Gates (stop, never override): MemAvailable < 1 GiB, swap in use, free disk < 30 GB, host CPU > 97 % for 10 s, SUT oom_kill > 0.
"""
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
BACKEND = HERE.parents[3]
sys.path.insert(0, str(BACKEND))
PY = sys.executable
HOME = Path.home()
CACHE = HOME / 'bench' / 'cap' / 'source'
RUNS = HOME / 'bench' / 'cap' / 'runs'
PG_BIN = Path(os.environ.get('BTL_PG_BIN', HOME / 'tools' / 'pg17' / 'bin'))


# ===================================================== SUT (inside scope A) =====================================================
def sut(a):
    from contracts.canonical import content_hash
    from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
    from tests.synthetic_financial_monthly import build_manifest, iter_events
    from ticks import source_acceptance
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    src_dir = CACHE / str(a.ticks); src_dir.mkdir(parents=True, exist_ok=True)
    info_file = src_dir / 'source.json'
    manifest, _m, _q = build_manifest(a.ticks)
    version = content_hash(manifest)
    if not info_file.exists():
        root = src_dir / 'monthly'
        parquet = write_monthly_parquet(str(root), iter_events(a.ticks, manifest), manifest, expected_version=version, row_group_size=8192)
        prov = MonthlyParquetProvider(str(root), expected_dataset_id=manifest['datasetId'], expected_dataset_version=version, expected_manifest_hash=parquet['manifestHash'])
        source_acceptance.accept_offline(prov, manifest['datasetId'], version, str(src_dir / 'accepted'))
        info_file.write_text(json.dumps(dict(ticks=a.ticks, datasetId=manifest['datasetId'], version=version, manifestHash=parquet['manifestHash'],
                                             startNs=str(manifest['range']['startNs']), endNs=str(manifest['range']['endNs']))))
    info = json.loads(info_file.read_text())
    shutil.copy(info_file, work / 'source.json')
    pgdata = work / 'pg'
    env = dict(os.environ, PATH=f'{PG_BIN}:{os.environ["PATH"]}')
    subprocess.run([str(PG_BIN / 'initdb'), '-D', str(pgdata), '-U', 'postgres', '--auth=trust', '-E', 'UTF8'], check=True, env=env, stdout=subprocess.DEVNULL)
    subprocess.run([str(PG_BIN / 'pg_ctl'), '-D', str(pgdata), '-w', '-l', str(work / 'pg.log'), '-o',
                    f'-p {a.pg_port} -k {work} -c listen_addresses=127.0.0.1 -c shared_buffers=512MB -c max_connections=200', 'start'], check=True, env=env, stdout=subprocess.DEVNULL)
    from tools.claude_exp.stack import local_stack as ls
    ls.setup(argparse.Namespace(pg_port=a.pg_port))
    os.environ.update({'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1', 'BTL_QA_SYNTHETIC_MONTHLY_ROOT': str(src_dir / 'monthly'), 'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': info['datasetId'],
                       'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': info['version'], 'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': info['manifestHash'],
                       'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1', 'BTL_TICK_CHECKPOINT_FORMAT': 'compact-v2', 'BTL_SOURCE_ACCEPTANCE_DIR': str(src_dir / 'accepted'),
                       'BTL_RESEARCH_WORKERS': str(a.workers), 'BTL_QA_VIRTUAL_TRADER_USERS': '200'})
    ls.STATE = work / 'state'
    import asyncio
    import uvicorn
    from cloud.app import create_app
    secret = 'cap-benchmark-secret-' + 'x' * 64
    app = create_app(ls.dsn('btl_app', ls.APP_PW, a.pg_port), secret, ls.Outbox(work / 'outbox.jsonl'), rate_limit=30, sandbox_reset_timezone='UTC')
    if os.environ.get('BTL_BENCH_QA_TIMING') == '1':
        app.state.qa_timing = True                       # Server-Timing headers (slot wait / hold); identical for every compared configuration
    config = uvicorn.Config(app, host='127.0.0.1', port=a.port, proxy_headers=True, forwarded_allow_ips='127.0.0.1', access_log=False, log_level='warning')
    server = uvicorn.Server(config)

    def stop(*_):
        server.should_exit = True
    signal.signal(signal.SIGTERM, stop)
    (work / 'READY').write_text('ready')
    try:
        asyncio.run(server.serve())
    finally:
        subprocess.run([str(PG_BIN / 'pg_ctl'), '-D', str(pgdata), '-m', 'fast', 'stop'], env=env, stdout=subprocess.DEVNULL)


# ===================================================== stage orchestration =====================================================
def meminfo():
    return {l.split(':')[0]: int(l.split()[1]) for l in open('/proc/meminfo')}


def host_cpu(prev):
    f = [int(x) for x in open('/proc/stat').readline().split()[1:]]
    idle, total = f[3] + f[4], sum(f)
    if prev is None:
        return None, (idle, total)
    return 100.0 * (1 - (idle - prev[0]) / max(1, total - prev[1])), (idle, total)


def cgroup_dir(unit):
    out = subprocess.run(['systemctl', '--user', 'show', '-p', 'ControlGroup', '--value', unit + '.scope'], capture_output=True, text=True).stdout.strip()
    return Path('/sys/fs/cgroup' + out)


def read_kv(path):
    try:
        return {k: int(v) for k, v in (l.split() for l in Path(path).read_text().splitlines())}
    except (OSError, ValueError):
        return {}


class Procs:
    """Per-component CPU seconds inside the SUT cgroup (postgres / API / native worker / other), accumulated per pid."""
    def __init__(self, cg):
        self.cg, self.seen, self.total = cg, {}, {}
        self.clk = os.sysconf('SC_CLK_TCK')
        self.rss_peak = {}

    def classify(self, pid):
        try:
            cmd = Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode(errors='ignore')
        except OSError:
            return None
        if 'postgres' in cmd or 'postmaster' in cmd:
            return 'postgresql'
        if 'cloud.worker' in cmd or 'cloud/worker' in cmd or ' worker' in cmd and 'serve' in cmd:
            return 'financialWorker'
        return 'apiAndOther'

    def sample(self):
        try:
            pids = [int(x) for x in (self.cg / 'cgroup.procs').read_text().split()]
        except OSError:
            return
        for pid in pids:
            try:
                f = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
                cpu = (int(f[11]) + int(f[12])) / self.clk
                rss = int(f[21]) * 4096 / 2**20
            except (OSError, IndexError, ValueError):
                continue
            cls = self.seen.get(pid, (None, 0.0))[0] or self.classify(pid)
            if cls is None:
                continue
            prev = self.seen.get(pid, (cls, 0.0))[1]
            self.total[cls] = self.total.get(cls, 0.0) + max(0.0, cpu - prev)
            self.seen[pid] = (cls, cpu)
            self.rss_peak[cls] = max(self.rss_peak.get(cls, 0.0), rss)


def stage(a):
    ts = time.strftime('%Y%m%d-%H%M%S')
    run = RUNS / f'{a.name}-{ts}'; run.mkdir(parents=True, exist_ok=True)
    result = dict(name=a.name, spec=a.spec, mode=a.mode, ticks=a.ticks, workers=a.workers, seed=a.seed, duration=a.duration, thinkScale=a.think_scale,
                  budget=dict(sutCpuQuotaPct=a.sut_cpu, sutMemoryMax=a.sut_mem, sutCores=a.sut_cores, generatorCpuQuotaPct=a.drv_cpu, generatorMemoryMax=a.drv_mem, generatorCores=a.drv_cores,
                              note='same-host, affinity-isolated, loopback HTTP without TLS/proxy; affinity is not exclusive CPU'), gates={})
    # ---------- preflight ----------
    # wait (bounded) until the host is quiet: instantaneous host CPU over 5 s, not the lagging 1-minute load average
    quiet = None
    for _ in range(40):
        _c, p0 = host_cpu(None); time.sleep(5); quiet, _p = host_cpu(p0)
        if quiet is not None and quiet < 10:
            break
    mi = meminfo()
    busy = subprocess.run(['pgrep', '-f', r'^[^ ]*python[^ ]* .*(capacity_http_driver|capacity_20|long_session_driver)'], capture_output=True, text=True).stdout.split()
    pre = dict(memAvailableGiB=round(mi['MemAvailable'] / 2**20, 2), swapUsedKiB=mi['SwapTotal'] - mi['SwapFree'], diskFreeGB=round(shutil.disk_usage('/').free / 2**30, 1),
               otherBenchmarkPids=busy, load1=os.getloadavg()[0], hostCpuPctBeforeStart=None if quiet is None else round(quiet, 1))
    result['preflight'] = pre
    if pre['memAvailableGiB'] < 4 or pre['swapUsedKiB'] > 0 or pre['diskFreeGB'] < 40 or busy or (quiet is None or quiet >= 10):
        result['abortedByPreflight'] = True
        (run / 'result.json').write_text(json.dumps(result, indent=1)); print(json.dumps(result, indent=1)); return 2
    sut_unit, drv_unit = f'btl-sut-{ts}', f'btl-drv-{ts}'
    port, pg_port = a.port, a.pg_port
    sut_log = open(run / 'sut.log', 'w')
    scope = ['systemd-run', '--user', '--scope', '--quiet', '--expand-environment=no']
    sut_cmd = scope + [f'--unit={sut_unit}', '-p', f'CPUQuota={a.sut_cpu}%', '-p', f'MemoryMax={a.sut_mem}', '-p', 'MemorySwapMax=0', 'taskset', '-c', a.sut_cores,
                       PY, str(HERE), 'sut', '--ticks', str(a.ticks), '--workers', str(a.workers), '--port', str(port), '--pg-port', str(pg_port), '--work', str(run / 'work')]
    sut_env = dict(os.environ, PATH=f'{PG_BIN}:{os.environ["PATH"]}', BTL_PG_BIN=str(PG_BIN))
    if a.direct_slots is not None:
        sut_env['BTL_DIRECT_OPERATION_CONCURRENCY'] = str(a.direct_slots); sut_env['BTL_BENCH_QA_TIMING'] = '1'
    for flag, env in ((a.db_budget, 'BTL_DB_BUDGET'), (a.api_limit, 'BTL_API_ADMISSION_LIMIT'), (a.api_wait, 'BTL_API_ADMISSION_WAIT_LIMIT')):
        if flag is not None:
            sut_env[env] = str(flag); sut_env['BTL_BENCH_QA_TIMING'] = '1'
    if a.fixture_cache is not None:
        sut_env['BTL_FIXTURE_CACHE_ENTRIES'] = str(a.fixture_cache); sut_env['BTL_BENCH_QA_TIMING'] = '1'
    result['directSlots'] = a.direct_slots if a.direct_slots is not None else 'default(3), timing off'
    result['admissionConfig'] = dict(dbBudget=a.db_budget or 12, apiActive=a.api_limit or 8, apiWait=a.api_wait or 16, clientOpt=bool(a.client_opt), fixtureCache=a.fixture_cache or 16)
    sp = subprocess.Popen(sut_cmd, stdout=sut_log, stderr=subprocess.STDOUT, env=sut_env)
    t0 = time.monotonic()
    while not (run / 'work' / 'READY').exists():
        if sp.poll() is not None or time.monotonic() - t0 > 1800:
            result['sutStartFailed'] = True
            (run / 'result.json').write_text(json.dumps(result, indent=1)); print(open(run / 'sut.log').read()[-2000:]); return 3
        time.sleep(1)
    result['sutReadySeconds'] = round(time.monotonic() - t0, 1)
    sut_cg = cgroup_dir(sut_unit)
    procs = Procs(sut_cg)
    # ---------- idle baseline (fixed infrastructure cost) ----------
    c0, t_idle = read_kv(sut_cg / 'cpu.stat'), time.monotonic()
    for _ in range(a.idle):
        time.sleep(1); procs.sample()
    c1 = read_kv(sut_cg / 'cpu.stat')
    result['idleBaseline'] = dict(seconds=a.idle, sutCpuSeconds=round((c1.get('usage_usec', 0) - c0.get('usage_usec', 0)) / 1e6, 3),
                                  sutMemoryCurrentMb=round(read_kv(sut_cg / 'memory.stat').get('anon', 0) / 2**20, 1), memoryCurrentMb=round(int((sut_cg / 'memory.current').read_text()) / 2**20, 1),
                                  byComponentCpuSeconds={k: round(v, 3) for k, v in procs.total.items()})
    # ---------- driver ----------
    drv_cmd = scope + [f'--unit={drv_unit}', '-p', f'CPUQuota={a.drv_cpu}%', '-p', f'MemoryMax={a.drv_mem}', '-p', 'MemorySwapMax=0', 'taskset', '-c', a.drv_cores,
                       PY, str(HERE.with_name('capacity_http_driver.py')), '--port', str(port), '--source', str(run / 'work' / 'source.json'), '--outbox', str(run / 'work' / 'outbox.jsonl'),
                       '--spec', a.spec, '--mode', a.mode, '--seed', str(a.seed), '--duration', str(a.duration), '--ramp', str(a.ramp), '--think-scale', str(a.think_scale), '--client-opt', str(a.client_opt), '--out', str(run / 'driver.json')]
    drv_log = open(run / 'driver.log', 'w')
    base = read_kv(sut_cg / 'cpu.stat'); base_t = time.monotonic()
    import psycopg
    dsn = f'host=127.0.0.1 port={pg_port} dbname=btl user=postgres'
    def db(q):
        try:
            with psycopg.connect(dsn, connect_timeout=3) as c:
                return c.execute(q).fetchall()
        except Exception:
            return []
    wal0 = (db("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(),'0/0')") or [[0]])[0][0]
    sess0 = (db("SELECT sessions FROM pg_stat_database WHERE datname='btl'") or [[0]])[0][0]
    dp = subprocess.Popen(drv_cmd, stdout=drv_log, stderr=subprocess.STDOUT)
    time.sleep(1.5)
    try:
        drv_cg = cgroup_dir(drv_unit)
    except Exception:
        drv_cg = None
    last_d, last_dpeak = {}, None
    prev, hot, series, qmax, qage = None, 0, [], 0, 0.0
    pg_max = 0
    tripped = None
    while dp.poll() is None:
        time.sleep(2)
        procs.sample()
        if drv_cg is not None and (drv_cg / 'cpu.stat').exists():
            last_d = read_kv(drv_cg / 'cpu.stat')
            try: last_dpeak = int((drv_cg / 'memory.peak').read_text())
            except (OSError, ValueError): pass
        m = meminfo(); cpu, prev = host_cpu(prev)
        hot = hot + 1 if cpu is not None and cpu > 97 else 0
        ev = read_kv(sut_cg / 'memory.events')
        s = read_kv(sut_cg / 'cpu.stat')
        q = db("SELECT count(*) FILTER (WHERE state='QUEUED'), coalesce(extract(epoch from now()-min(created_at) FILTER (WHERE state='QUEUED')),0), count(*) FILTER (WHERE state='RUNNING') FROM btl.research_jobs")
        qd, qa, running = (q[0] if q else (0, 0, 0))
        pgc = (db("SELECT count(*) FROM pg_stat_activity WHERE datname='btl'") or [[0]])[0][0]
        pg_max = max(pg_max, pgc)
        qmax, qage = max(qmax, qd), max(qage, float(qa))
        series.append(dict(t=round(time.monotonic() - base_t, 1), hostCpu=None if cpu is None else round(cpu, 1), memAvailGiB=round(m['MemAvailable'] / 2**20, 2),
                           sutCpuS=round((s.get('usage_usec', 0) - base.get('usage_usec', 0)) / 1e6, 1), sutMemMb=round(int((sut_cg / 'memory.current').read_text()) / 2**20), queued=qd, running=running, pgConns=pgc))
        for bad, why in ((m['MemAvailable'] < 2**20, 'MemAvailable < 1 GiB'), (m['SwapTotal'] - m['SwapFree'] > 0, 'swap in use'), (shutil.disk_usage('/').free < 30 * 2**30, 'free disk < 30 GB'),
                         (hot >= 5, 'host CPU > 97% for 10 s'), (ev.get('oom_kill', 0) > 0, 'SUT oom_kill')):
            if bad:
                tripped = why; break
        if tripped:
            dp.terminate(); break
    wall = time.monotonic() - base_t
    s = read_kv(sut_cg / 'cpu.stat'); peak = int((sut_cg / 'memory.peak').read_text()) if (sut_cg / 'memory.peak').exists() else None
    wal1 = (db("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(),'0/0')") or [[0]])[0][0]
    sess1 = (db("SELECT sessions FROM pg_stat_database WHERE datname='btl'") or [[0]])[0][0]
    dbq = db("SELECT pg_database_size('btl'), (SELECT count(*) FROM btl.tick_checkpoints), (SELECT coalesce(sum(octet_length(payload)),0) FROM btl.tick_checkpoints), (SELECT count(*) FROM btl.tick_events), (SELECT coalesce(sum(octet_length(payload)),0) FROM btl.tick_events)")
    states = dict(db("SELECT state,count(*) FROM btl.research_jobs GROUP BY state"))
    ops = {r[0]: dict(n=r[1]) for r in db("SELECT operation,count(*) FROM btl.research_jobs GROUP BY operation")}
    waits = [float(json.loads(bytes(r[0]))['waitMicroseconds']) / 1e6 for r in db("SELECT queue_metrics FROM btl.research_jobs WHERE queue_metrics IS NOT NULL")]
    waits.sort()
    def pc(p): return None if not waits else round(waits[min(len(waits) - 1, int(p / 100 * (len(waits) - 1) + .5))], 3)
    dcpu, dpeak = last_d, last_dpeak
    result.update(wallSeconds=round(wall, 1), stoppedByGate=tripped, sut=dict(
        cpuSecondsTotal=round((s.get('usage_usec', 0) - base.get('usage_usec', 0)) / 1e6, 1), throttledUsec=s.get('throttled_usec'), nrThrottled=s.get('nr_throttled'), memoryPeakMb=None if peak is None else round(peak / 2**20),
        byComponentCpuSeconds={k: round(v, 1) for k, v in procs.total.items()}, byComponentRssPeakMb={k: round(v) for k, v in procs.rss_peak.items()}, pgConnectionsMax=pg_max, pgSessionsOpened=int(sess1 - sess0)),
        generator=dict(cgroupCpuSeconds=round(dcpu.get('usage_usec', 0) / 1e6, 1), cgroupMemoryPeakMb=None if dpeak is None else round(dpeak / 2**20), note='generator cost is NOT counted in the SUT'),
        database=dict(sizeBytes=dbq[0][0] if dbq else None, checkpointRows=dbq[0][1] if dbq else None, checkpointBytes=dbq[0][2] if dbq else None, eventRows=dbq[0][3] if dbq else None,
                      eventBytes=dbq[0][4] if dbq else None, walBytes=int(wal1 - wal0)),
        queue=dict(jobStates=states, jobsByOperation=ops, maxQueued=qmax, maxOldestQueuedAgeSeconds=round(qage, 1), waitSeconds=dict(n=len(waits), p50=pc(50), p95=pc(95), p99=pc(99), max=None if not waits else round(waits[-1], 3))),
        hostSeries=series[:: max(1, len(series) // 120)])
    if (run / 'driver.json').exists():
        d = json.loads((run / 'driver.json').read_text()); result['driver'] = d
    # ---------- teardown (stop the scopes; never leave a benchmark running) ----------
    subprocess.run(['systemctl', '--user', 'stop', f'{sut_unit}.scope'], capture_output=True)
    subprocess.run(['systemctl', '--user', 'stop', f'{drv_unit}.scope'], capture_output=True)
    sp.wait(timeout=60)
    (run / 'result.json').write_text(json.dumps(result, indent=1, default=str))
    print('STAGE_DONE', run / 'result.json', 'gate=', tripped)
    return 0 if not tripped else 4


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('sut'); s.add_argument('--ticks', type=int, required=True); s.add_argument('--workers', type=int, default=3); s.add_argument('--port', type=int, default=8101)
    s.add_argument('--pg-port', type=int, default=54431); s.add_argument('--work', required=True); s.set_defaults(f=sut)
    s = sub.add_parser('stage'); s.add_argument('--name', required=True); s.add_argument('--spec', required=True); s.add_argument('--mode', default='load'); s.add_argument('--ticks', type=int, default=65536)
    s.add_argument('--workers', type=int, default=3); s.add_argument('--seed', type=int, default=1); s.add_argument('--duration', type=float, default=120); s.add_argument('--ramp', type=float, default=10)
    s.add_argument('--think-scale', type=float, default=1.0); s.add_argument('--idle', type=int, default=15); s.add_argument('--direct-slots', type=int, default=None)
    s.add_argument('--db-budget', type=int, default=None); s.add_argument('--api-limit', type=int, default=None); s.add_argument('--api-wait', type=int, default=None); s.add_argument('--client-opt', type=int, default=0); s.add_argument('--fixture-cache', type=int, default=None)
    s.add_argument('--port', type=int, default=8101); s.add_argument('--pg-port', type=int, default=54431)
    s.add_argument('--sut-cpu', default='400'); s.add_argument('--sut-mem', default='11G'); s.add_argument('--sut-cores', default='0-3')
    s.add_argument('--drv-cpu', default='100'); s.add_argument('--drv-mem', default='2G'); s.add_argument('--drv-cores', default='4')
    s.set_defaults(f=lambda a: sys.exit(stage(a)))
    a = ap.parse_args(); a.f(a)
