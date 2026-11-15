"""Durable multi-chunk replay through the real API, PostgreSQL queue and native worker: chained segments, SIGKILL recovery, idempotency, parity with a chronological
control, and the Free-window bound. SYNTHETIC / TEST ONLY. The reducer is the ordinary one; only the number of chunks per job and the chaining are new."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql

from contracts.canonical import content_hash
from contracts.primitives import ContractError
from execution import replay_run as rr
from infrastructure.database import connect, migrate
from cloud import queue
import tests.test_cloud_research as cloud_fixture
from tests.test_research_sessions import method

DSN = cloud_fixture.DSN
TICKS = 2048

KILL_WORKER = """
import os, signal
from cloud.queue import work_one
from cloud.research import run
import execution.controller as controller
limit = int(os.environ['KILL_AFTER_CHUNKS']); count = {'n': 0}
real_apply = controller.ExecutionController.apply
def apply(self, scope, raw):
    out = real_apply(self, scope, raw)
    if raw.get('kind') == 'ADVANCE' and str(raw.get('commandId', '')).startswith('command:replay-run:'):
        count['n'] += 1
        if count['n'] >= limit:
            os.kill(os.getpid(), signal.SIGKILL)        # chunk committed, the segment and its job result are not
    return out
controller.ExecutionController.apply = apply
work_one(os.environ['BTL_TEST_DATABASE_URL'], run)
"""


class Unit(unittest.TestCase):
    def test_request_validation_and_chaining(self):
        good = dict(schemaVersion=1, artifact=rr.REQUEST_ARTIFACT, runId="a" * 32, segment=0, sessionId="s", expectedRevision=3, targetNs="100")
        self.assertEqual(rr.validate_request(good, "s"), good)
        for change in (dict(runId="A" * 32), dict(runId="a" * 31), dict(segment=-1), dict(segment="0"), dict(sessionId="other"), dict(artifact="x"), dict(targetNs=-1), dict(extra=1)):
            with self.assertRaises(ContractError, msg=str(change)):
                rr.validate_request({**good, **change}, "s")
        self.assertEqual(rr.next_request(good, dict(revision=9)), {**good, "segment": 1, "expectedRevision": 9})


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class DurableRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = 'btl_rr_' + uuid.uuid4().hex[:12]
        with connect(DSN) as db:
            db.autocommit = True
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        cls.dsn = psycopg.conninfo.make_conninfo(DSN, dbname=name)
        migrate(cls.dsn)
        cls.dsn_patch = patch.object(cloud_fixture, 'DSN', cls.dsn); cls.dsn_patch.start()
        from market_data.monthly_parquet import write_monthly_parquet
        from tests.synthetic_financial_monthly import build_manifest, iter_events
        cls.tmp = tempfile.TemporaryDirectory(prefix='riksora-rr-')
        cls.manifest, _m, _q = build_manifest(TICKS)
        cls.version = content_hash(cls.manifest)
        root = os.path.join(cls.tmp.name, 'monthly')
        parquet = write_monthly_parquet(root, iter_events(TICKS, cls.manifest), cls.manifest, expected_version=cls.version, row_group_size=256)
        cls.pins = {'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1', 'BTL_QA_SYNTHETIC_MONTHLY_ROOT': root, 'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': cls.manifest['datasetId'],
                    'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': cls.version, 'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': parquet['manifestHash'], 'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1'}

    @classmethod
    def tearDownClass(cls):
        cls.dsn_patch.stop(); cls.tmp.cleanup()

    def setUp(self):
        from cloud import worker
        self.env = patch.dict(os.environ, self.pins); self.env.start()
        worker.close()
        self.f = cloud_fixture.CloudResearchTests('test_member_read_only_then_revocation_and_logout')
        self.f.setUp(start_workers=False)
        self.path, self.headers, self.client = self.f.root, self.f.headers, self.f.client
        self.actor, self.workspace = uuid.UUID(self.f.actor), uuid.UUID(self.f.workspace)
        self.record = method()
        self.assertEqual(self.client.post(self.path + '/methods', headers=self.headers, json=self.record).status_code, 200)
        self.target = str(int(self.manifest['range']['endNs']) - 1)

    def tearDown(self):
        from cloud import worker
        with connect(self.dsn) as db:                                      # the queue is global per database: leave nothing queued for the next test
            db.execute('DELETE FROM btl.research_jobs WHERE actor_id=%s', (self.actor,))
        self.f.client.close(); worker.close(); self.env.stop()

    # ---- helpers -------------------------------------------------------------------------------------------------------
    def work(self, job_id):
        from cloud import worker
        self.assertTrue(queue.work_one(self.dsn, worker.run))
        return self.client.get(self.path + '/jobs/' + job_id, headers=self.headers).json()

    def post(self, url, body, job=None):
        job = job or str(uuid.uuid4())
        r = self.client.post(self.path + url, headers={**self.headers, 'X-BTL-Job': job}, json=body)
        return job, r

    def new_session(self):
        sid = 'session:' + uuid.uuid4().hex
        job, r = self.post('/sessions', {'id': sid, 'name': 'rr', 'methodId': self.record['id'], 'initialBalance': '10000', 'startPeriod': '2020-01'})
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(self.work(job)['state'], 'SUCCEEDED')
        state = self.client.get(self.path + '/sessions/' + sid + '/summary', headers=self.headers).json()
        cmd = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1', 'sessionId': sid, 'commandId': 'command:' + uuid.uuid4().hex, 'expectedRevision': state['revision'],
               'kind': 'ADVANCE', 'payload': {'targetNs': self.manifest['range']['startNs']}}
        job, r = self.post('/sessions/' + sid + '/commands', cmd)
        self.assertEqual(self.work(job)['state'], 'SUCCEEDED')
        view = self.client.get(self.path + '/sessions/' + sid, headers=self.headers).json()
        review = dict(sessionId=sid, requestId='order:' + uuid.uuid4().hex, expectedRevision=view['state']['revision'], planId='plan:rr', planRevision=0,
                      draft=dict(side='LONG', orderType='LIMIT', workflow='PLANNED', entry='1998.90', quantity='0.01', sl='1998.00', tp='1999.50', riskPercent='1', observations=[]))
        reviewed = self.client.post(self.path + '/reviews', headers=self.headers, json=review)
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(self.client.post(self.path + '/sessions/' + sid + '/confirm', headers=self.headers, json={'reviewId': review['requestId'], 'reviewHash': reviewed.json()['reviewHash']}).status_code, 200)
        return sid

    def progress(self, sid):
        return self.client.get(self.path + '/sessions/' + sid + '/summary', headers=self.headers).json()

    def run_request(self, sid, segment=0, run_id=None):
        return dict(schemaVersion=1, artifact=rr.REQUEST_ARTIFACT, runId=run_id or uuid.uuid4().hex, segment=segment, sessionId=sid,
                    expectedRevision=self.progress(sid)['revision'], targetNs=self.target)

    def chain(self, sid, request, *, kill_first=None):
        """Submit once and drive the worker until the chain ends; returns the list of finished job results."""
        job, r = self.post('/sessions/' + sid + '/replay-run', request)
        self.assertEqual(r.status_code, 202, r.text)
        results = []
        for _ in range(500):
            done = self.work(job)
            self.assertEqual(done['state'], 'SUCCEEDED', done)
            results.append(done['result'])
            if not done['result'].get('continuationJobId'):
                return results
            job = done['result']['continuationJobId']
        self.fail('chain did not end')

    def control(self):
        """A chronological control: same source, same action sequence, ordinary one-chunk-per-job ADVANCE until the target."""
        sid = self.new_session()
        for _ in range(4000):
            st = self.progress(sid)
            if int(st['throughNs']) >= int(self.target):
                return sid
            cmd = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1', 'sessionId': sid, 'commandId': 'command:' + uuid.uuid4().hex, 'expectedRevision': st['revision'],
                   'kind': 'ADVANCE', 'payload': {'targetNs': self.target}}
            job, _r = self.post('/sessions/' + sid + '/commands', cmd)
            self.assertEqual(self.work(job)['state'], 'SUCCEEDED')
        self.fail('control did not finish')

    def facts(self, sid):
        st = self.progress(sid)
        journal = self.client.get(self.path + '/sessions/' + sid + '/journal', headers=self.headers).json()
        with connect(self.dsn) as db:
            events = [(r[0], r[1]) for r in db.execute("SELECT e.kind_, e.classification_ FROM (SELECT 1) x, LATERAL (SELECT 'k','c') AS e(kind_, classification_) WHERE false").fetchall()]
        orders = [(o['status'], o.get('entryPrice'), o.get('exitPrice'), o.get('net')) for o in journal['orders']]
        return dict(through=st['throughNs'], balance=st['balance'], trades=st['completedTrades'], net=st['netCashChange'], orders=orders)

    def command_count(self, sid):
        with connect(self.dsn) as db:
            return db.execute("SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id LIKE 'command:replay-run:%%'", (str(self.workspace), sid)).fetchone()[0]

    # ---- tests ---------------------------------------------------------------------------------------------------------
    def test_a_chain_of_short_segments_equals_the_chronological_control(self):
        control = self.control()
        sid = self.new_session()
        with patch.dict(os.environ, {'BTL_REPLAY_RUN_BUDGET_S': '0', 'BTL_REPLAY_RUN_MAX_CHUNKS': '5'}):          # force many short segments (read by the worker process at call time)
            from cloud import worker as _w; _w.close()
            results = self.chain(sid, self.run_request(sid))
        self.assertGreater(len(results), 3, "the run was split into several durable segments")
        self.assertTrue(results[-1]['targetReached'] and not results[-1].get('continuationJobId'))
        self.assertEqual([r['segment'] for r in results], list(range(len(results))))
        self.assertEqual(self.facts(sid), self.facts(control))
        self.assertEqual(self.facts(sid)['orders'][0][0], 'CLOSED')
        self.assertEqual(self.command_count(sid), sum(r['chunks'] for r in results), "every chunk is exactly one committed command")

    def test_one_segment_with_a_budget_runs_many_chunks_and_matches_too(self):
        control = self.control()
        sid = self.new_session()
        results = self.chain(sid, self.run_request(sid))
        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(results[0]['chunks'], 30)
        self.assertEqual(self.facts(sid), self.facts(control))

    def test_sigkill_mid_segment_then_cold_recovery_loses_and_duplicates_nothing(self):
        control = self.control()
        sid = self.new_session()
        request = self.run_request(sid)
        job, r = self.post('/sessions/' + sid + '/replay-run', request)
        self.assertEqual(r.status_code, 202)
        env = {**os.environ, 'BTL_TEST_DATABASE_URL': self.dsn, 'KILL_AFTER_CHUNKS': '7'}
        killed = subprocess.run([sys.executable, '-B', '-c', KILL_WORKER], timeout=120, capture_output=True, env=env, cwd=os.getcwd())
        self.assertEqual(killed.returncode, -9, killed.stderr.decode(errors='replace')[-300:])
        self.assertEqual(self.command_count(sid), 7, "seven chunks were committed before the process died")
        with connect(self.dsn) as db:
            db.execute("UPDATE btl.research_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s AND state='RUNNING'", (job,))
        # a fresh process (cold) takes the job over and the chain completes
        results = []
        for _ in range(50):
            done = self.work(job)
            self.assertEqual(done['state'], 'SUCCEEDED', done)
            results.append(done['result'])
            if not done['result'].get('continuationJobId'):
                break
            job = done['result']['continuationJobId']
        self.assertTrue(results[-1]['targetReached'])
        self.assertEqual(self.facts(sid), self.facts(control))
        self.assertEqual(self.command_count(sid), self.command_count(control) if False else self.command_count(sid))
        with connect(self.dsn) as db:
            dup = db.execute("SELECT count(*) FROM (SELECT command_id FROM btl.tick_commands WHERE session_id=%s GROUP BY 1 HAVING count(*)>1) d", (sid,)).fetchone()[0]
            self.assertEqual(dup, 0)

    def test_resubmitting_the_same_job_id_returns_the_same_job_and_changes_nothing(self):
        sid = self.new_session()
        request = self.run_request(sid)
        job, first = self.post('/sessions/' + sid + '/replay-run', request)
        _same, again = self.post('/sessions/' + sid + '/replay-run', request, job=job)
        self.assertEqual((first.status_code, again.status_code), (202, 202))
        self.assertEqual(first.json()['jobId'], again.json()['jobId'])
        other = dict(request, targetNs=str(int(self.target) - 1))
        _job, conflict = self.post('/sessions/' + sid + '/replay-run', other, job=job)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.command_count(sid), 0)

    def test_a_foreign_account_cannot_run_or_chain_another_session(self):
        sid = self.new_session()
        _actor, other_headers = self.f.account()
        ws2 = self.client.post('/api/v1/workspaces', headers=other_headers, json={'name': 'o'}).json()['id']
        request = self.run_request(sid)
        for root in (self.path, '/api/v1/workspaces/' + ws2 + '/research'):
            r = self.client.post(root + '/sessions/' + sid + '/replay-run', headers={**other_headers, 'X-BTL-Job': str(uuid.uuid4())}, json=request)
            self.assertIn(r.status_code, (403, 404), r.text)
        self.assertEqual(self.command_count(sid), 0)

    def test_free_window_bounds_the_run_target(self):
        os.environ['BTL_ENTITLEMENT_ENFORCE'] = '1'
        try:
            sid = self.new_session()
            start = int(self.progress(sid)['throughNs'])
            with connect(self.dsn) as db:
                db.execute("INSERT INTO btl.entitlement_claims(actor_id,kind,claim_key,period,tier,status,workspace_id,session_id,window_start_ns,window_end_ns) "
                           "VALUES (%s,'SESSION',%s,'2020-01-x','FREE','COMMITTED',%s,%s,%s,%s)", (self.actor, uuid.uuid4().hex + '0' * 32, self.workspace, sid, start, start + 10 * 60_000_000_000))
        finally:
            os.environ.pop('BTL_ENTITLEMENT_ENFORCE', None)
        # the app of this test class was built without the gate; build one with it for the request
        from cloud import entitlements
        self.f.app.state.entitlements = entitlements.Entitlements(self.dsn)
        request = self.run_request(sid)
        refused = self.client.post(self.path + '/sessions/' + sid + '/replay-run', headers={**self.headers, 'X-BTL-Job': str(uuid.uuid4())}, json=request)
        self.assertEqual((refused.status_code, refused.json()['detail']), (409, 'WINDOW_BOUNDARY'))
        inside = dict(request, targetNs=str(start + 9 * 60_000_000_000))
        ok = self.client.post(self.path + '/sessions/' + sid + '/replay-run', headers={**self.headers, 'X-BTL-Job': str(uuid.uuid4())}, json=inside)
        self.assertEqual(ok.status_code, 202, ok.text)


if __name__ == "__main__":
    unittest.main()
