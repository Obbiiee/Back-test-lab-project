"""Commercial V1 capacity acceptance harness: N active traders, each runs ONE 262,144-tick financial-active Session through the authenticated API, the durable
PostgreSQL queue chain (replay_run) and the native workers, arriving on a seeded schedule, while doing representative reads (job polling, summary, journal).
SYNTHETIC / TEST ONLY. In-process API (TestClient) with the real queue workers and native worker processes; one private PostgreSQL database.

  python -m tools.claude_exp.stack.capacity_20 --ticks 262144 --traders 20 --hour-seconds 3600 --workers 4 --out result.json
Gates (stop and report, never override): MemAvailable < 1 GiB, swap in use, free disk < 30 GB, host CPU > 97 % for 10 consecutive seconds.
"""
import argparse
import collections
import json
import os
import shutil
import statistics
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

TICKS_PER_CHUNK = 64


def pct(values, p):
    values = sorted(values)
    return None if not values else round(values[min(len(values) - 1, int(p / 100 * (len(values) - 1) + 0.5))], 3)


class Gate:
    def __init__(self):
        self.tripped, self.reason, self.cpu_hot = False, None, 0
        self.samples = []
        self.stop = threading.Event()
        self._prev = None

    def host_cpu(self):
        f = [int(x) for x in open('/proc/stat').readline().split()[1:]]
        idle, total = f[3] + f[4], sum(f)
        prev, self._prev = self._prev, (idle, total)
        return None if prev is None else 100.0 * (1 - (idle - prev[0]) / max(1, total - prev[1]))

    def run(self, worker_children, wal_probe):
        while not self.stop.wait(5):
            mem = {l.split(':')[0]: int(l.split()[1]) for l in open('/proc/meminfo')}
            avail_gib, swap_kib = mem['MemAvailable'] / 2**20, mem['SwapTotal'] - mem['SwapFree']
            free_gb = shutil.disk_usage('/').free / 2**30
            cpu = self.host_cpu()
            wcpu, wrss = worker_children()
            self.samples.append(dict(t=round(time.monotonic(), 1), memAvailableGiB=round(avail_gib, 2), hostCpu=None if cpu is None else round(cpu, 1), workerCpuS=round(wcpu, 1), workerPeakRssMb=round(wrss, 1), walBytes=wal_probe()))
            self.cpu_hot = self.cpu_hot + 1 if cpu is not None and cpu > 97 else 0
            for bad, why in ((avail_gib < 1, 'MemAvailable < 1 GiB'), (swap_kib > 0, 'swap in use'), (free_gb < 30, 'free disk < 30 GB'), (self.cpu_hot >= 2, 'host CPU > 97% for 10 s')):
                if bad:
                    self.tripped, self.reason = True, why
                    return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ticks', type=int, default=262144); ap.add_argument('--traders', type=int, default=20); ap.add_argument('--hour-seconds', type=int, default=3600)
    ap.add_argument('--workers', type=int, default=4); ap.add_argument('--burst', action='store_true'); ap.add_argument('--seed', type=int, default=20261115); ap.add_argument('--out')
    a = ap.parse_args()
    os.environ['BTL_RESEARCH_WORKERS'] = str(a.workers)
    os.environ['BTL_QA_VIRTUAL_TRADER_USERS'] = str(max(a.traders, 5))
    os.environ['BTL_TICK_CHECKPOINT_FORMAT'] = 'compact-v2'
    from tests.long_session_driver import fresh_database, db_numbers, worker_children
    from tools.claude_exp.stack.capacity_acceptance import schedule
    import psycopg
    from contracts.canonical import content_hash
    from market_data.monthly_parquet import write_monthly_parquet, MonthlyParquetProvider
    from tests.synthetic_financial_monthly import build_manifest, iter_events
    from ticks import source_acceptance
    from execution import replay_run as rr
    from infrastructure.database import connect
    import tests.test_cloud_research as cloud_fixture
    from tests.test_research_sessions import method
    from unittest.mock import patch

    result = dict(ticks=a.ticks, traders=a.traders, workers=a.workers, mode='burst' if a.burst else 'normal', seed=a.seed, budget='5 vCPU / 14 GiB cgroup (owner addendum 2026-11-14)')
    dsn = fresh_database()
    tmp = tempfile.mkdtemp(prefix='riksora-cap20-')
    t0 = time.monotonic()
    manifest, _m, _q = build_manifest(a.ticks)
    version = content_hash(manifest)
    root = os.path.join(tmp, 'monthly')
    parquet = write_monthly_parquet(root, iter_events(a.ticks, manifest), manifest, expected_version=version, row_group_size=8192)
    adm = os.path.join(tmp, 'accepted'); os.environ['BTL_SOURCE_ACCEPTANCE_DIR'] = adm
    prov = MonthlyParquetProvider(root, expected_dataset_id=manifest['datasetId'], expected_dataset_version=version, expected_manifest_hash=parquet['manifestHash'])
    source_acceptance.accept_offline(prov, manifest['datasetId'], version, adm)
    result['sourcePrepSeconds'] = round(time.monotonic() - t0, 1)
    os.environ.update({'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1', 'BTL_QA_SYNTHETIC_MONTHLY_ROOT': root, 'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': manifest['datasetId'],
                       'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': version, 'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': parquet['manifestHash'], 'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1'})

    def wal_probe():
        try:
            with psycopg.connect(dsn) as db:
                return int(db.execute("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(),'0/0')").fetchone()[0])
        except Exception:
            return None

    gate = Gate()
    plan = schedule(a.seed, a.traders, a.hour_seconds, 8)
    arrivals = [r['arrivalS'] for r in (plan['burstOfEight'] if a.burst else plan['normalLoad'])][:a.traders]
    with patch.object(cloud_fixture, 'DSN', dsn):
        fx = cloud_fixture.CloudResearchTests('test_member_read_only_then_revocation_and_logout')
        fx.setUp(start_workers=True)                                     # real lifespan: queue workers + native worker pool
        try:
            traders = [dict(i=i) for i in range(a.traders)]
            create_lock = threading.Lock()

            def provision(tr):                                           # at ARRIVAL: bearer tokens live 1800 s (session_seconds), so a run longer than that needs fresh logins
                with create_lock:
                    actor, headers = fx.account()
                    ws = fx.client.post('/api/v1/workspaces', headers=headers, json={'name': f"cap-{tr['i']}"}).json()['id']
                    root_path = f'/api/v1/workspaces/{ws}/research'
                    record = method()
                    assert fx.client.post(root_path + '/methods', headers=headers, json=record).status_code == 200
                    tr.update(headers=headers, path=root_path, method=record['id'], actor=actor, ws=ws)
                    time.sleep(2.3)                                      # auth admission is 30/min/IP

            base = db_numbers(dsn)
            latencies, retries, lock = collections.defaultdict(list), collections.Counter(), threading.Lock()
            outcomes = [None] * a.traders

            def call(kind, fn):
                t = time.monotonic(); r = fn()
                # Client recovery, reported separately: the product refuses with 503 SERVICE_BUSY + Retry-After when its shared DB budget is exhausted; the existing frontend retries those (bounded).
                for attempt in range(8):
                    if r.status_code != 503 or '"SERVICE_BUSY"' not in r.text:
                        break
                    with lock:
                        retries['clientRecovery:' + kind + ':SERVICE_BUSY'] += 1
                    time.sleep(min(5.0, float(r.headers.get('Retry-After', '1'))) + 0.2 * attempt); r = fn()
                dt = time.monotonic() - t
                with lock:
                    latencies[kind].append(dt)
                return r

            def trader(tr, arrival):
                client = fx.client
                time.sleep(max(0, arrival - (time.monotonic() - run_start)))
                provision(tr)
                t_sub = time.monotonic(); out = dict(trader=tr['i'], arrivalS=round(arrival, 1), failures=[])
                try:
                    def post(url, body, job=None):
                        job = job or str(uuid.uuid4())
                        for attempt in range(60):
                            r = call('submit', lambda: client.post(tr['path'] + url, headers={**tr['headers'], 'X-BTL-Job': job}, json=body))
                            if r.status_code == 202:
                                return job
                            if r.status_code in (429, 503):
                                with lock:
                                    retries[str(r.status_code) + ':' + r.json().get('detail', '')] += 1
                                time.sleep(min(5, 0.5 * (attempt + 1))); continue
                            raise RuntimeError(f'submit {url} -> {r.status_code} {r.text[:200]}')
                        raise RuntimeError('submit refused 60 times')

                    def wait(job, kind='poll'):
                        last = 0
                        while True:
                            j = call(kind, lambda: client.get(tr['path'] + '/jobs/' + job, headers=tr['headers']))
                            if j.status_code == 404:
                                raise RuntimeError('job pruned')
                            body = j.json()
                            if 'state' not in body:
                                raise RuntimeError(f'poll {job} -> HTTP {j.status_code} {str(body)[:300]}')
                            if body['state'] in ('SUCCEEDED',):
                                return body
                            if body['state'] not in ('QUEUED', 'RUNNING'):
                                raise RuntimeError('job ' + body['state'])
                            if time.monotonic() - last > 15:                  # representative reads while waiting
                                call('summary', lambda: client.get(tr['path'] + '/sessions/' + sid + '/summary', headers=tr['headers'])); last = time.monotonic()
                            time.sleep(2 + (tr['i'] % 3) * 0.4)

                    sid = 'session:' + uuid.uuid4().hex
                    wait(post('/sessions', {'id': sid, 'name': 'cap', 'methodId': tr['method'], 'initialBalance': '10000', 'startPeriod': '2020-01'}))
                    st = call('summary', lambda: client.get(tr['path'] + f'/sessions/{sid}/summary', headers=tr['headers'])).json()
                    wait(post(f'/sessions/{sid}/commands', {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1', 'sessionId': sid, 'commandId': 'command:' + uuid.uuid4().hex,
                                                            'expectedRevision': st['revision'], 'kind': 'ADVANCE', 'payload': {'targetNs': manifest['range']['startNs']}}))
                    view = call('view', lambda: client.get(tr['path'] + f'/sessions/{sid}', headers=tr['headers'])).json()
                    review = dict(sessionId=sid, requestId='order:' + uuid.uuid4().hex, expectedRevision=view['state']['revision'], planId='plan:cap', planRevision=0,
                                  draft=dict(side='LONG', orderType='LIMIT', workflow='PLANNED', entry='1998.90', quantity='0.01', sl='1998.00', tp='1999.50', riskPercent='1', observations=[]))
                    reviewed = call('review', lambda: client.post(tr['path'] + '/reviews', headers=tr['headers'], json=review)).json()
                    assert client.post(tr['path'] + f'/sessions/{sid}/confirm', headers=tr['headers'], json={'reviewId': review['requestId'], 'reviewHash': reviewed['reviewHash']}).status_code == 200
                    t_run = time.monotonic()
                    st = call('summary', lambda: client.get(tr['path'] + f'/sessions/{sid}/summary', headers=tr['headers'])).json()
                    request = dict(schemaVersion=1, artifact=rr.REQUEST_ARTIFACT, runId=uuid.uuid4().hex, segment=0, sessionId=sid, expectedRevision=st['revision'], targetNs=str(int(manifest['range']['endNs']) - 1))
                    job, segments = post(f'/sessions/{sid}/replay-run', request), 0
                    while True:
                        body = wait(job)
                        segments += 1
                        nxt = body['result'].get('continuationJobId')
                        if not nxt:
                            break
                        job = nxt
                    out.update(runSeconds=round(time.monotonic() - t_run, 1), segments=segments)
                    sresp = call('summary', lambda: client.get(tr['path'] + f'/sessions/{sid}/summary', headers=tr['headers']))
                    summary = sresp.json()
                    if 'balance' not in summary:
                        raise RuntimeError(f'final summary -> HTTP {sresp.status_code} {str(summary)[:300]}')
                    journal = call('journal', lambda: client.get(tr['path'] + f'/sessions/{sid}/journal/pages?limit=32', headers=tr['headers'])).json()
                    call('export', lambda: client.get(tr['path'] + f'/sessions/{sid}/export?format=csv', headers=tr['headers']))
                    out.update(facts=dict(balance=summary['balance'], trades=summary['completedTrades'], net=summary['netCashChange'], orders=[(o['status'], o.get('entryPrice'), o.get('exitPrice'), o.get('net')) for o in journal['orders']]),
                               sessionId=sid)
                except Exception as error:                                   # noqa: BLE001 - reported, never hidden
                    out['failures'].append(f'{type(error).__name__}: {str(error)[:300]}')
                out['endToEndSeconds'] = round(time.monotonic() - t_sub, 1)
                outcomes[tr['i']] = out

            threading.Thread(target=gate.run, args=(worker_children, wal_probe), daemon=True).start()
            run_start = time.monotonic()
            threads = [threading.Thread(target=trader, args=(tr, arrivals[tr['i']])) for tr in traders]
            for t in threads:
                t.start()
            while any(t.is_alive() for t in threads):
                if gate.tripped:
                    result['stoppedBy'] = gate.reason
                    break
                time.sleep(2)
            for t in threads:
                t.join(timeout=5 if gate.tripped else None)
            gate.stop.set()
            wall = time.monotonic() - run_start
            after = db_numbers(dsn)
            with connect(dsn) as db:
                waits = []
                for (raw,) in db.execute("SELECT queue_metrics FROM btl.research_jobs WHERE operation='replay_run' AND queue_metrics IS NOT NULL").fetchall():
                    try:
                        m = json.loads(bytes(raw)); waits.append(float(m['waitMicroseconds']) / 1e6)
                    except (ValueError, TypeError, KeyError):
                        pass
                states = dict(db.execute("SELECT state,count(*) FROM btl.research_jobs GROUP BY state").fetchall())
            done = [o for o in outcomes if o and not o['failures']]
            e2e = [o['endToEndSeconds'] for o in done]
            wcpu, wrss = worker_children()
            facts = {json.dumps(o['facts'], sort_keys=True) for o in done}
            result.update(wallSeconds=round(wall, 1), completedTraders=len(done), failedTraders=[o for o in outcomes if o and o['failures']], endToEndSeconds=dict(p50=pct(e2e, 50), p95=pct(e2e, 95), p99=pct(e2e, 99), max=max(e2e) if e2e else None),
                          queueWaitSeconds=dict(n=len(waits), p50=pct(waits, 50), p95=pct(waits, 95), p99=pct(waits, 99), max=max(waits) if waits else None), jobStates=states,
                          retries=dict(retries), latencyMs={k: dict(n=len(v), p50=round(1000 * pct(v, 50)), p95=round(1000 * pct(v, 95)), p99=round(1000 * pct(v, 99))) for k, v in latencies.items()},
                          financialParityAcrossTraders=len(facts) == 1, facts=json.loads(next(iter(facts))) if facts else None,
                          workerCpuSecondsTotal=round(wcpu, 1), workerPeakRssMb=round(wrss, 1), db={k: after[k] - base[k] if k in ('dbBytes', 'walBytes') else after[k] for k in after},
                          hostSamples=dict(maxHostCpu=max([s['hostCpu'] for s in gate.samples if s['hostCpu'] is not None] or [0]), minMemAvailableGiB=min([s['memAvailableGiB'] for s in gate.samples] or [0]),
                                           p95HostCpu=pct([s['hostCpu'] for s in gate.samples if s['hostCpu'] is not None], 95)),
                          costPerTraderWorkerCoreSeconds=round(wcpu / max(1, len(done)), 1))
        finally:
            fx.client.close()
            shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(result, indent=1, default=str))
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=1, default=str))


if __name__ == '__main__':
    main()
