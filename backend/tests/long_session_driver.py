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


def normalised_events(dsn, sid):
    import re
    from execution.postgres import unpack
    with psycopg.connect(dsn) as db:
        raw = [unpack(p, h) for p, h in db.execute("SELECT payload,content_hash FROM btl.tick_events WHERE session_id=%s ORDER BY sequence", (sid,)).fetchall()]
    text = json.dumps(raw, sort_keys=True); seen = {}
    text = re.sub(r"(?:session|order|command|c|jump):[0-9a-f]{32}", lambda m: seen.setdefault(m.group(0), "ID%d" % len(seen)), text)
    return re.sub(r"[0-9a-f]{64}", "H", text)


def worker_children():
    """(cpu seconds, peak RSS MiB) summed over the live native worker slot processes (QA measurement only)."""
    from cloud import worker
    cpu, rss, tick = 0.0, 0.0, os.sysconf('SC_CLK_TCK')
    for slot in worker._slots:
        proc = getattr(slot, 'process', None)
        if proc is None or proc.poll() is not None:
            continue
        try:
            stat = open(f'/proc/{proc.pid}/stat').read(); f = stat[stat.rfind(')') + 2:].split()
            cpu += (int(f[11]) + int(f[12])) / tick
            for line in open(f'/proc/{proc.pid}/status'):
                if line.startswith('VmHWM'):
                    rss = max(rss, int(line.split()[1]) / 1024)
        except OSError:
            pass
    return cpu, rss


def run_tier(ticks, *, max_jobs=4000, deadline_s=3000, log=print, direct=False, mode='chunk-jobs'):
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
                if os.environ.get('BTL_ADMIT_SOURCES') == '1':          # offline source admission (the full acceptance scan, once, outside any request deadline)
                    from market_data.monthly_parquet import MonthlyParquetProvider
                    from ticks import source_acceptance
                    adm = os.path.join(tmp, 'accepted'); os.environ['BTL_SOURCE_ACCEPTANCE_DIR'] = adm
                    prov = MonthlyParquetProvider(root, expected_dataset_id=manifest['datasetId'], expected_dataset_version=version, expected_manifest_hash=parquet['manifestHash'])
                    ta = time.monotonic(); source_acceptance.accept_offline(prov, manifest['datasetId'], version, adm); result['sourceAdmissionSeconds'] = round(time.monotonic() - ta, 1)
                pins = {'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1', 'BTL_QA_SYNTHETIC_MONTHLY_ROOT': root, 'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': manifest['datasetId'],
                        'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': version, 'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': parquet['manifestHash'], 'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1'}
                with patch.dict(os.environ, pins):
                    path, headers, client = fixture.root, fixture.headers, fixture.client
                    record = method()
                    assert client.post(path + '/methods', headers=headers, json=record).status_code == 200
                    before = db_numbers(dsn)
                    cpu0, wall0 = time.process_time(), time.monotonic()
                    def make_session():
                        sid_ = 'session:' + uuid.uuid4().hex
                        assert work(post_job('/sessions', {'id': sid_, 'name': 'long', 'methodId': record['id'], 'initialBalance': '10000', 'startPeriod': '2020-01'}))['state'] == 'SUCCEEDED'
                        st_ = client.get(path + '/sessions/' + sid_ + '/summary', headers=headers).json()
                        c_ = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1', 'sessionId': sid_, 'commandId': 'command:' + uuid.uuid4().hex, 'expectedRevision': st_['revision'], 'kind': 'ADVANCE', 'payload': {'targetNs': manifest['range']['startNs']}}
                        assert work(post_job('/sessions/' + sid_ + '/commands', c_))['state'] == 'SUCCEEDED'
                        v_ = client.get(path + '/sessions/' + sid_, headers=headers).json()
                        r_ = dict(sessionId=sid_, requestId='order:' + uuid.uuid4().hex, expectedRevision=v_['state']['revision'], planId='plan:' + uuid.uuid4().hex, planRevision=0,
                                  draft=dict(side='LONG', orderType='LIMIT', workflow='PLANNED', entry='1998.90', quantity='0.01', sl='1998.00', tp='1999.50', riskPercent='1', observations=[]))
                        rv_ = client.post(path + '/reviews', headers=headers, json=r_)
                        assert rv_.status_code == 200, rv_.text
                        assert client.post(path + '/sessions/' + sid_ + '/confirm', headers=headers, json={'reviewId': r_['requestId'], 'reviewHash': rv_.json()['reviewHash']}).status_code == 200
                        return sid_

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

                    sid = make_session()
                    target = str(int(manifest['range']['endNs']) - 1)
                    jobs, job_seconds, refusals = 0, [], {}
                    if mode == 'run':                            # ONE request; the queue chains the segments
                        from execution import replay_run as rr
                        cpu_w0, _r0 = worker_children()
                        progress = client.get(path + '/sessions/' + sid + '/summary', headers=headers).json()
                        request = dict(schemaVersion=1, artifact=rr.REQUEST_ARTIFACT, runId=uuid.uuid4().hex, segment=0, sessionId=sid, expectedRevision=progress['revision'], targetNs=target)
                        t_run = time.monotonic()
                        start_ns = int(manifest['range']['startNs'])
                        mid = str(start_ns + int((int(target) - start_ns) * 0.6))
                        request['targetNs'] = mid                    # phase 1: up to 60 %, then a cold restart, then the rest
                        job = post_job('/sessions/' + sid + '/replay-run', request)
                        segments, phase2 = [], False
                        while True:
                            t = time.monotonic()
                            done = work(job)
                            if done['state'] != 'SUCCEEDED':
                                result['stoppedBy'] = dict(state=done['state'], detail=str(done)[:500]); break
                            segments.append(dict(seconds=round(time.monotonic() - t, 2), chunks=done['result']['chunks'], through=done['result']['throughNs']))
                            if time.monotonic() - t_run > deadline_s:
                                result['stoppedBy'] = 'DEADLINE'; break
                            if not done['result'].get('continuationJobId'):
                                if phase2 or done['result']['targetReached'] is False or int(done['result']['throughNs']) >= int(target):
                                    break
                                # cold restart: the native worker processes (and their timeline caches) are killed; the next segment must rebuild from PostgreSQL only
                                cpu_mid, _r = worker_children()
                                from cloud import worker as _w
                                _w.close()
                                phase2 = True
                                progress = client.get(path + '/sessions/' + sid + '/summary', headers=headers).json()
                                request = dict(schemaVersion=1, artifact=rr.REQUEST_ARTIFACT, runId=uuid.uuid4().hex, segment=0, sessionId=sid, expectedRevision=progress['revision'], targetNs=target)
                                t_cold = time.monotonic()
                                job = post_job('/sessions/' + sid + '/replay-run', request)
                                done2 = work(job)
                                result['coldRestart'] = dict(firstSegmentSeconds=round(time.monotonic() - t_cold, 2), chunks=done2['result']['chunks'], state=done2['state'],
                                                             steadySecondsPerChunk=round(sorted(x['seconds'] / max(1, x['chunks']) for x in segments)[len(segments) // 2], 3) if segments else None)
                                if done2['state'] != 'SUCCEEDED':
                                    result['stoppedBy'] = dict(state=done2['state'], detail=str(done2)[:400]); break
                                segments.append(dict(seconds=round(time.monotonic() - t_cold, 2), chunks=done2['result']['chunks'], through=done2['result']['throughNs']))
                                if not done2['result'].get('continuationJobId'):
                                    break
                                job = done2['result']['continuationJobId']
                                continue
                            job = done['result']['continuationJobId']
                        cpu_w1, rss_w = worker_children()
                        final = client.get(path + '/sessions/' + sid + '/summary', headers=headers).json()
                        result.update(mode='run', segments=len(segments), chunks=sum(x['chunks'] for x in segments), runWallSeconds=round(time.monotonic() - t_run, 1),
                                      segmentSeconds=dict(p50=sorted(x['seconds'] for x in segments)[len(segments) // 2], max=max(x['seconds'] for x in segments)) if segments else None,
                                      workerCpuSeconds=round(cpu_w1 - cpu_w0, 1), workerPeakRssMb=round(rss_w, 1), reachedTarget=int(final['throughNs']) >= int(target),
                                      parentCpuSeconds=round(time.process_time() - cpu0, 1), setupSeconds=round(t_run - wall0, 1), wallSeconds=round(time.monotonic() - wall0, 1))
                        after = db_numbers(dsn)
                        result['db'] = {k: after[k] - before[k] if k in ('dbBytes', 'walBytes') else after[k] for k in after}
                        if result['reachedTarget']:
                            journal = client.get(path + '/sessions/' + sid + '/journal', headers=headers).json()
                            result['facts'] = dict(through=final['throughNs'], balance=final['balance'], trades=final['completedTrades'], net=final['netCashChange'],
                                                   orders=[(o['status'], o.get('entryPrice'), o.get('exitPrice'), o.get('net')) for o in journal['orders']])
                            # chronological control: same source, same action sequence, ordinary one-chunk ADVANCE commands in one hot process
                            from cloud.research import _synthetic_monthly_provider
                            from application.models import TrustedScope
                            from execution.research import ResearchApplication
                            cid = make_session()
                            capp = ResearchApplication(dsn, TrustedScope(str(fixture.workspace), str(fixture.actor)), synthetic_provider=_synthetic_monthly_provider(), state_storage_format='compact-v1')
                            t_c = time.monotonic(); chunks_c = 0
                            while True:
                                st = capp.summary(cid)
                                if int(st['throughNs']) >= int(target):
                                    break
                                capp.apply(cid, {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1', 'sessionId': cid, 'commandId': 'command:' + uuid.uuid4().hex,
                                                 'expectedRevision': st['revision'], 'kind': 'ADVANCE', 'payload': {'targetNs': target}}); chunks_c += 1
                            cs = client.get(path + '/sessions/' + cid + '/summary', headers=headers).json()
                            cj = client.get(path + '/sessions/' + cid + '/journal', headers=headers).json()
                            ctrl = dict(through=cs['throughNs'], balance=cs['balance'], trades=cs['completedTrades'], net=cs['netCashChange'],
                                        orders=[(o['status'], o.get('entryPrice'), o.get('exitPrice'), o.get('net')) for o in cj['orders']])
                            result['control'] = dict(seconds=round(time.monotonic() - t_c, 1), chunks=chunks_c, equal=ctrl == result['facts'], revisionEqual=cs['revision'] == final['revision'], eventsEqual=normalised_events(dsn, cid) == normalised_events(dsn, sid))
                        return result
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
    ap = argparse.ArgumentParser(); ap.add_argument('--ticks', type=int, required=True); ap.add_argument('--out'); ap.add_argument('--max-jobs', type=int, default=4000); ap.add_argument('--direct', action='store_true'); ap.add_argument('--mode', default='chunk-jobs', choices=('chunk-jobs', 'run'))
    args = ap.parse_args()
    out = run_tier(args.ticks, max_jobs=args.max_jobs, direct=args.direct, mode=args.mode)
    print(json.dumps(out, indent=1, default=str))
    if args.out:
        open(args.out, 'w').write(json.dumps(out, indent=1, default=str))
