"""Long-session tier driver (SYNTHETIC / TEST ONLY): one financial-active Session of N ticks through the authenticated API, the durable PostgreSQL queue and the
native worker, driven only by ordinary client calls (ADVANCE jobs re-issued until the target is reached), with measurements and a chronological control.

Run:  BTL_TEST_DATABASE_URL=... python -m tests.long_session_driver --ticks 16384 [--out result.json]
"""
import argparse
import json
import os
import resource
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql

from contracts.canonical import content_hash
from infrastructure.database import connect, migrate
from cloud import queue

DSN = os.getenv('BTL_TEST_DATABASE_URL')


def fresh_database():
    name = 'btl_long_' + uuid.uuid4().hex[:10]
    with connect(DSN) as db:
        db.autocommit = True
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    dsn = psycopg.conninfo.make_conninfo(DSN, dbname=name)
    migrate(dsn)
    return dsn


def db_numbers(dsn):
    with psycopg.connect(dsn) as db:
        size = db.execute("SELECT pg_database_size(current_database())").fetchone()[0]
        wal = int(db.execute("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(),'0/0')").fetchone()[0])
        ck = db.execute("SELECT count(*), coalesce(max(octet_length(payload)),0), coalesce(sum(octet_length(payload)),0) FROM btl.tick_checkpoints").fetchone()
        ev = db.execute("SELECT count(*), coalesce(sum(octet_length(payload)),0) FROM btl.tick_events").fetchone()
        cm = db.execute("SELECT count(*) FROM btl.tick_commands").fetchone()[0]
    return dict(dbBytes=size, walBytes=wal, checkpointRows=ck[0], checkpointMaxBytes=ck[1], checkpointTotalBytes=ck[2], eventRows=ev[0], eventBytes=ev[1], commandRows=cm)


def run_tier(ticks, *, max_jobs=4000, deadline_s=3000, log=print, direct=False):
    import functools; log = functools.partial(print, file=__import__('sys').stderr)
    import tests.test_cloud_research as cloud_fixture
    from cloud import worker
    from market_data.monthly_parquet import write_monthly_parquet
    from tests.synthetic_financial_monthly import build_manifest, iter_events
    from tests.test_research_sessions import method
    dsn = fresh_database()
    result = dict(ticks=ticks)
    with patch.object(cloud_fixture, 'DSN', dsn):
        fixture = cloud_fixture.CloudResearchTests('test_member_read_only_then_revocation_and_logout')
        fixture.setUp(start_workers=False)
        try:
            worker.close()
            t0 = time.monotonic()
            manifest, _m, _q = build_manifest(ticks)
            version = content_hash(manifest)
            with tempfile.TemporaryDirectory(prefix='riksora-long-') as tmp:
                root = os.path.join(tmp, 'monthly')
                parquet = write_monthly_parquet(root, iter_events(ticks, manifest), manifest, expected_version=version, row_group_size=8192 if ticks > 8192 else 128)
                result['sourceBuildSeconds'] = round(time.monotonic() - t0, 2)
                pins = {'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1', 'BTL_QA_SYNTHETIC_MONTHLY_ROOT': root, 'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': manifest['datasetId'],
                        'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': version, 'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': parquet['manifestHash'], 'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1'}
                with patch.dict(os.environ, pins):
                    path, headers, client = fixture.root, fixture.headers, fixture.client
                    record = method()
                    assert client.post(path + '/methods', headers=headers, json=record).status_code == 200
                    before = db_numbers(dsn)
                    cpu0, wall0 = time.process_time(), time.monotonic()
                    sid = 'session:' + uuid.uuid4().hex

                    phases = {'submit': 0.0, 'work': 0.0, 'jobget': 0.0, 'summary': 0.0}

                    def work(job_id):
                        t = time.monotonic()
                        assert queue.work_one(dsn, worker.run)
                        phases['work'] += time.monotonic() - t; t = time.monotonic()
                        job = client.get(path + '/jobs/' + job_id, headers=headers).json()
                        phases['jobget'] += time.monotonic() - t
                        return job

                    def post_job(url, body):
                        job_id = str(uuid.uuid4())
                        t = time.monotonic()
                        queued = client.post(path + url, headers={**headers, 'X-BTL-Job': job_id}, json=body)
                        phases['submit'] += time.monotonic() - t
                        assert queued.status_code == 202, queued.text
                        return job_id

                    job = work(post_job('/sessions', {'id': sid, 'name': 'long', 'methodId': record['id'], 'initialBalance': '10000', 'startPeriod': '2020-01'}))
                    assert job['state'] == 'SUCCEEDED', job
                    view = client.get(path + '/sessions/' + sid, headers=headers).json()
                    start_ns = manifest['range']['startNs']
                    cmd = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1', 'sessionId': sid, 'commandId': 'command:' + uuid.uuid4().hex,
                           'expectedRevision': view['state']['revision'], 'kind': 'ADVANCE', 'payload': {'targetNs': start_ns}}
                    job = work(post_job('/sessions/' + sid + '/commands', cmd))
                    assert job['state'] == 'SUCCEEDED', job
                    view = client.get(path + '/sessions/' + sid, headers=headers).json()
                    review = dict(sessionId=sid, requestId='order:' + uuid.uuid4().hex, expectedRevision=view['state']['revision'], planId='plan:' + uuid.uuid4().hex, planRevision=0,
                                  draft=dict(side='LONG', orderType='LIMIT', workflow='PLANNED', entry='1998.90', quantity='0.01', sl='1998.00', tp='1999.50', riskPercent='1', observations=[]))
                    reviewed = client.post(path + '/reviews', headers=headers, json=review)
                    assert reviewed.status_code == 200, reviewed.text
                    assert client.post(path + '/sessions/' + sid + '/confirm', headers=headers, json={'reviewId': review['requestId'], 'reviewHash': reviewed.json()['reviewHash']}).status_code == 200
                    target = str(int(manifest['range']['endNs']) - 1)
                    jobs, job_seconds, refusals = 0, [], {}
                    if direct:                                   # engine + durable commit only: no HTTP, no queue, no native worker (diagnosis)
                        from cloud.research import run as research_run, _synthetic_monthly_provider
                        from application.models import TrustedScope
                        from execution.research import ResearchApplication
                        hot = os.environ.get('BTL_DIRECT_HOT') == '1'
                        groups = int(os.environ.get('BTL_DIRECT_GROUPS', '64'))
                        app = ResearchApplication(dsn, TrustedScope(str(fixture.workspace), str(fixture.actor)), synthetic_provider=_synthetic_monthly_provider(),
                                                  state_storage_format='compact-v1') if hot else None
                        if hot and groups != 64:
                            app._ResearchApplication__timeline_cache.max_groups_per_advance = groups
                        t_loop = time.monotonic(); n = 0
                        while n < max_jobs:
                            progress = client.get(path + '/sessions/' + sid + '/summary', headers=headers).json()
                            if int(progress['throughNs']) >= int(target):
                                break
                            cmd = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1', 'sessionId': sid, 'commandId': 'command:' + uuid.uuid4().hex,
                                   'expectedRevision': progress['revision'], 'kind': 'ADVANCE', 'payload': {'targetNs': target}}
                            t = time.monotonic(); (app.apply(sid, cmd) if hot else research_run(dsn, fixture.actor, fixture.workspace, 'apply', (sid, cmd), write=True)); job_seconds.append(time.monotonic() - t); n += 1
                        result.update(direct=True, chunks=n, throughGroups=progress.get('completedTrades'), lastThrough=progress['throughNs'], firstTenthSeconds=round(sum(job_seconds[:max(1, n // 10)]) / max(1, n // 10), 3), lastTenthSeconds=round(sum(job_seconds[-max(1, n // 10):]) / max(1, n // 10), 3), directSecondsPerChunk=round(sum(job_seconds) / max(1, n), 4), directLoopSeconds=round(time.monotonic() - t_loop, 1))
                        return result
                    while jobs < max_jobs and time.monotonic() - wall0 < deadline_s:
                        view = client.get(path + '/sessions/' + sid, headers=headers).json()
                        if int(view['state']['throughNs']) >= int(target):
                            break
                        cmd = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1', 'sessionId': sid, 'commandId': 'command:' + uuid.uuid4().hex,
                               'expectedRevision': view['state']['revision'], 'kind': 'ADVANCE', 'payload': {'targetNs': target}}
                        t = time.monotonic()
                        job = work(post_job('/sessions/' + sid + '/commands', cmd))
                        job_seconds.append(time.monotonic() - t); jobs += 1
                        if job['state'] != 'SUCCEEDED':
                            result['stoppedBy'] = dict(state=job['state'], detail=str(job)[:600]); break
                    final = client.get(path + '/sessions/' + sid + '/summary', headers=headers).json()
                    tv = time.monotonic(); client.get(path + '/sessions/' + sid, headers=headers); result['fullViewSeconds'] = round(time.monotonic() - tv, 2)
                    result.update(jobs=jobs, reachedTarget=int(final['throughNs']) >= int(target), wallSeconds=round(time.monotonic() - wall0, 1),
                                  parentCpuSeconds=round(time.process_time() - cpu0, 1), peakRssMbParent=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                                  childPeakRssMb=round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1),
                                  jobSecondsByDecile=[round(sum(job_seconds[i * len(job_seconds) // 10:(i + 1) * len(job_seconds) // 10]) / max(1, len(job_seconds[i * len(job_seconds) // 10:(i + 1) * len(job_seconds) // 10])), 3) for i in range(10)] if job_seconds else None, phasesPerJob={k: round(v / max(1, jobs), 3) for k, v in phases.items()}, jobSeconds=dict(p50=round(sorted(job_seconds)[len(job_seconds) // 2], 2) if job_seconds else None, max=round(max(job_seconds), 2) if job_seconds else None))
                    after = db_numbers(dsn)
                    result['db'] = {k: after[k] - before[k] if k in ('dbBytes', 'walBytes') else after[k] for k in after}
                    if result['reachedTarget']:
                        summary = client.get(path + '/sessions/' + sid + '/summary', headers=headers).json()
                        journal = client.get(path + '/sessions/' + sid + '/journal', headers=headers).json()
                        result['summary'] = dict(completedTrades=summary['completedTrades'], netCashChange=summary['netCashChange'], balance=summary['balance'], revision=summary['revision'])
                        result['journalOrders'] = [(o['status'], o.get('entryPrice'), o.get('exitPrice'), o.get('net')) for o in journal['orders']]
        finally:
            fixture.client.close()
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--ticks', type=int, required=True); ap.add_argument('--out'); ap.add_argument('--max-jobs', type=int, default=4000); ap.add_argument('--direct', action='store_true')
    args = ap.parse_args()
    out = run_tier(args.ticks, max_jobs=args.max_jobs, direct=args.direct)
    print(json.dumps(out, indent=1, default=str))
    if args.out:
        open(args.out, 'w').write(json.dumps(out, indent=1, default=str))
