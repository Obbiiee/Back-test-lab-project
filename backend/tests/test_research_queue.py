"""Actual PostgreSQL queue pressure, scope, ownership, rollback and cancellation."""
import os
import json
import uuid
import unittest
import subprocess
import sys
import time
import tempfile
from unittest.mock import patch
import psycopg
from psycopg import sql
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from cloud import queue
from cloud.research import run
from contracts.primitives import ContractError
from infrastructure.database import connect, migrate
from tests import test_cloud_research as cloud_fixture
from tests.test_research_sessions import method, review_request
from execution.research import ResearchApplication
from application.models import TrustedScope
from execution.research_fixture import research_provider
from market_data.monthly_parquet import write_monthly_parquet
from contracts.canonical import content_hash
from infrastructure.postgres_metrics import collect_job_metrics

DSN = os.getenv('BTL_TEST_DATABASE_URL')


@unittest.skipUnless(DSN, 'Real PostgreSQL required; skip is not acceptance')
class QueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Queue ownership is global within one DB: a running QA service must not
        # consume authored fault jobs. Use a distinct new database, never reset.
        name='btl_queue_qa_'+uuid.uuid4().hex
        with connect(DSN) as db:
            db.autocommit=True
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        cls.dsn=psycopg.conninfo.make_conninfo(DSN,dbname=name)
        migrate(cls.dsn)
        cls.fixture_dsn=patch.object(cloud_fixture,'DSN',cls.dsn)
        cls.fixture_dsn.start()

    @classmethod
    def tearDownClass(cls):
        cls.fixture_dsn.stop()

    def setUp(self):
        # Reuse real verified identity setup, not forged user/workspace fixtures.
        self.fixture = cloud_fixture.CloudResearchTests('test_member_read_only_then_revocation_and_logout')
        self.fixture.setUp()
        self.actor = uuid.UUID(self.fixture.actor)
        self.workspace = uuid.UUID(self.fixture.workspace)
        self.ids = []

    def tearDown(self):
        with connect(self.dsn) as db:
            db.execute('DELETE FROM btl.research_jobs WHERE actor_id=%s', (self.actor,))
        self.fixture.client.close()

    def submit(self, **options):
        job_id = options.pop('job_id', uuid.uuid4())
        self.ids.append(job_id)
        return queue.submit(self.dsn, self.actor, self.workspace, job_id, options.pop('operation','workspace'), options.pop('args',('session:authored-queue', {})), **options)

    def test_stable_identity_quota_and_no_heavy_allocation(self):
        job = self.submit()
        self.assertEqual(self.submit(job_id=job['jobId']), job)
        with self.assertRaises(ContractError) as changed:
            self.submit(job_id=job['jobId'], args=('session:changed', {}))
        self.assertEqual(changed.exception.code, 'IDEMPOTENCY_CONFLICT')
        self.submit()
        with self.assertRaises(ContractError) as full:
            self.submit()
        self.assertEqual(full.exception.code, 'QUEUE_CAPACITY')
        self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,job['jobId'],cancel=True)['state'], 'CANCELLED')
        self.assertEqual(self.submit()['state'], 'QUEUED')

    def test_claims_rotate_between_users_before_revisiting_backlog(self):
        first = self.submit(args=('session:fair-a1', {'timeframe': '1m'}))
        second = self.submit(args=('session:fair-a2', {'timeframe': '1m'}))

        actor_b, headers_b = self.fixture.account()
        workspace_b = self.fixture.client.post('/api/v1/workspaces', headers=headers_b,
                                               json={'name': 'Fair queue QA'}).json()['id']
        third_id = uuid.uuid4()
        third = queue.submit(self.dsn, uuid.UUID(actor_b), uuid.UUID(workspace_b), third_id,
                             'workspace', ('session:fair-b1', {'timeframe': '1m'}))

        claimed = []

        def runner(_dsn, actor_id, _workspace_id, _operation, args, **_options):
            claimed.append((str(actor_id), args[0]))
            return {'sessionId': args[0]}

        for _ in range(3):
            self.assertTrue(queue.work_one(self.dsn, runner))

        self.assertEqual(claimed, [
            (str(self.actor), 'session:fair-a1'),
            (str(uuid.UUID(actor_b)), 'session:fair-b1'),
            (str(self.actor), 'session:fair-a2'),
        ])
        self.assertEqual(queue.inspect(self.dsn, self.actor, self.workspace, first['jobId'])['state'],
                         'SUCCEEDED')
        self.assertEqual(queue.inspect(self.dsn, self.actor, self.workspace, second['jobId'])['state'],
                         'SUCCEEDED')
        self.assertEqual(queue.inspect(self.dsn, uuid.UUID(actor_b), uuid.UUID(workspace_b),
                                       third['jobId'])['state'], 'SUCCEEDED')

    def test_worker_rollback_then_exact_result_recovery(self):
        job = self.submit()
        def crash(*args):
            raise RuntimeError('authored process-stage fault')
        with self.assertRaises(RuntimeError):
            queue.work_one(self.dsn, crash)
        with connect(self.dsn) as db:
            db.execute("UPDATE btl.research_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
                       (job['jobId'],))
        self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,job['jobId'])['state'],'QUEUED')
        self.assertTrue(queue.work_one(self.dsn,lambda *args: {'value':'authored bounded result'}))
        result = queue.inspect(self.dsn,self.actor,self.workspace,job['jobId'])
        self.assertEqual(result['state'],'SUCCEEDED')
        self.assertEqual(result['result'],{'schemaVersion':1,'value':'authored bounded result'})
        self.assertEqual(self.submit(job_id=job['jobId']),result)
        self.assertFalse(queue.work_one(self.dsn,crash))

    def test_first_claim_queue_wait_is_content_hashed_and_not_user_result(self):
        job = self.submit()
        self.assertTrue(queue.work_one(self.dsn, lambda *args: {'value': 'bounded result'}))
        with connect(self.dsn) as db:
            row = db.execute('SELECT queue_metrics,queue_metrics_hash FROM btl.research_jobs WHERE id=%s',
                             (job['jobId'],)).fetchone()
        metrics = json.loads(bytes(row[0]))
        self.assertEqual(content_hash(metrics), row[1])
        self.assertEqual(metrics['artifact'], 'BTL-QUEUE-WAIT-METRICS-1')
        self.assertEqual(metrics['measurementScope'], 'FIRST_DURABLE_ADMISSION_TO_FIRST_WORKER_CLAIM')
        self.assertGreaterEqual(metrics['waitMicroseconds'], 0)
        result = queue.inspect(self.dsn, self.actor, self.workspace, job['jobId'])
        self.assertEqual(result['result'], {'schemaVersion': 1, 'value': 'bounded result'})
        self.assertNotIn('queueMetrics', result)

    def test_actual_process_exit_releases_claim_and_worker_slots(self):
        job=self.submit()
        script="from cloud.queue import work_one; import os; work_one(os.environ['BTL_TEST_DATABASE_URL'], lambda *args: os._exit(17))"
        process=subprocess.run([sys.executable,'-B','-c',script],timeout=15,capture_output=True,env={**os.environ,'BTL_TEST_DATABASE_URL':self.dsn})
        self.assertEqual(process.returncode,17,process.stderr.decode(errors='replace'))
        with connect(self.dsn) as db:
            db.execute("UPDATE btl.research_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
                       (job['jobId'],))
        self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,job['jobId'])['state'],'QUEUED')
        self.assertTrue(queue.work_one(self.dsn,lambda *args:{'value':'after actual process death'}))

    def test_global_worker_slots_are_database_owned(self):
        self.submit()
        with connect(self.dsn) as db:
            for i in range(queue.WORKERS):
                db.execute('SELECT pg_advisory_xact_lock(2020,%s)',(310+i,))
            self.assertFalse(queue.work_one(self.dsn,lambda *args:self.fail('Third worker must not enter')))
        self.assertTrue(queue.work_one(self.dsn,lambda *args:{'value':'slots released'}))

    def test_mounted_read_queue_preserves_canonical_session_and_idempotence(self):
        m=method()
        self.assertEqual(self.fixture.client.post(self.fixture.root+'/methods',headers=self.fixture.headers,json=m).status_code,200)
        session='session:'+uuid.uuid4().hex
        created=self.fixture.client.post(self.fixture.root+'/sessions',headers=self.fixture.headers,json={
            'id':session,'name':'Queue read QA','methodId':m['id'],'initialBalance':'10000','startPeriod':'2020-01'})
        self.assertEqual(created.status_code,200,created.text)
        path=self.fixture.root+'/sessions/'+session
        command_id='command:'+uuid.uuid4().hex
        receipt_status=self.fixture.client.get(path+'/commands/'+command_id,headers=self.fixture.headers)
        self.assertEqual(receipt_status.status_code,200,receipt_status.text)
        self.assertEqual((receipt_status.json()['status'],receipt_status.json()['sessionId'],
                          receipt_status.json()['commandId']),('UNKNOWN',session,command_id))
        before=self.fixture.client.get(path,headers=self.fixture.headers).content
        job=str(uuid.uuid4())
        headers={**self.fixture.headers,'X-BTL-Job':job}
        with patch('cloud.queue.work_one',side_effect=AssertionError('API may not enter heavy work')):
            response=self.fixture.client.post(path+'/view',headers=headers,json={'timeframe':'1m'})
        self.assertEqual(response.status_code,202,response.text)
        self.assertEqual(response.json()['state'],'QUEUED')
        repeated=self.fixture.client.post(path+'/view',headers=headers,json={'timeframe':'1m'})
        self.assertEqual(repeated.content,response.content)
        self.assertTrue(queue.work_one(self.dsn,run))
        status=self.fixture.client.get(self.fixture.root+'/jobs/'+job,headers=self.fixture.headers)
        self.assertEqual(status.json()['state'],'SUCCEEDED')
        completed=self.fixture.client.post(path+'/view',headers=headers,json={'timeframe':'1m'})
        self.assertEqual(completed.status_code,200)
        self.assertEqual(status.json()['result'],completed.json())
        self.assertEqual(self.fixture.client.get(path,headers=self.fixture.headers).content,before)

    def test_api_lifespan_worker_consumes_and_deduplicates_durable_job(self):
        """Exercise the actual API lifespan pump, not a test-side work_one call."""
        from cloud import worker
        service = ResearchApplication(self.dsn, TrustedScope(str(self.workspace), str(self.actor)))
        record = method()
        service.create_method(record)
        session = 'session:' + uuid.uuid4().hex
        service.create_session({'id': session, 'name': 'Lifespan queue QA',
                                'methodId': record['id'], 'initialBalance': '10000',
                                'startPeriod': '2020-01'})
        service.close()

        job_id = str(uuid.uuid4())
        path = self.fixture.root + '/sessions/' + session + '/view'
        headers = {**self.fixture.headers, 'X-BTL-Job': job_id}
        api_client = cloud_fixture.client(self.fixture.app)
        try:
            with api_client as active:
                submitted = active.post(path, headers=headers, json={'timeframe': '1m'})
                self.assertEqual(submitted.status_code, 202, submitted.text)
                self.assertEqual(submitted.json()['state'], 'QUEUED')

                deadline = time.monotonic() + 20
                status = None
                while time.monotonic() < deadline:
                    response = active.get(self.fixture.root + '/jobs/' + job_id,
                                          headers=self.fixture.headers)
                    self.assertEqual(response.status_code, 200, response.text)
                    status = response.json()
                    if status['state'] not in ('QUEUED', 'RUNNING'):
                        break
                    time.sleep(.05)

                self.assertIsNotNone(status)
                self.assertEqual(status['state'], 'SUCCEEDED', status)
                self.assertEqual(status['result']['artifact'], 'BTL-LOCAL-SESSION-VIEW-1')
                self.assertEqual(status['result']['state']['sessionId'], session)

                repeated = active.post(path, headers=headers, json={'timeframe': '1m'})
                self.assertEqual(repeated.status_code, 200, repeated.text)
                self.assertEqual(repeated.json(), status['result'])
        finally:
            api_client.close()
        self.assertTrue(all(slot.process is None for slot in worker._slots),
                        'API lifespan must reap retained native worker children')

    def replay_fixture(self):
        app=ResearchApplication(self.dsn,TrustedScope(str(self.workspace),str(self.actor)))
        m=method();app.create_method(m)
        session='session:'+uuid.uuid4().hex
        created=app.create_session({'id':session,'name':'Queued replay QA','methodId':m['id'],
                                    'initialBalance':'10000','startPeriod':'2020-01'})
        request=review_request(created);reviewed=app.review(request)
        app.confirm(session,{'reviewId':request['requestId'],'reviewHash':reviewed['reviewHash']})
        view=app.inspect(session)
        command={'schemaVersion':1,'artifact':'BTL-TICK-EXECUTION-COMMAND-1','sessionId':session,
                 'commandId':'command:'+uuid.uuid4().hex,'expectedRevision':view['state']['revision'],
                 'kind':'ADVANCE','payload':{'targetNs':str(int(view['state']['throughNs'])+60_000_000_000)}}
        return app,session,command

    def test_native_bounded_worker_revalidates_and_retains_canonical_receipt(self):
        from cloud.worker import run as bounded_run
        app,session,command=self.replay_fixture()
        try:
            job=self.submit(operation='replay',args=(session,command))
            self.assertTrue(queue.work_one(self.dsn,bounded_run))
            result=queue.inspect(self.dsn,self.actor,self.workspace,job['jobId'])
            self.assertEqual(result['state'],'SUCCEEDED')
            before=app.inspect(session)
            self.assertEqual(bounded_run(self.dsn,self.actor,self.workspace,'apply',(session,command),write=True),result['result'])
            self.assertEqual(app.inspect(session),before)
            other,_=self.fixture.account()
            with self.assertRaises(ContractError):
                bounded_run(self.dsn,uuid.UUID(other),self.workspace,'workspace',(session,{'timeframe':'1m'}))
            # A warm controller cache never substitutes for fresh authority.
            bounded_run(self.dsn,self.actor,self.workspace,'workspace',(session,{'timeframe':'1m'}))
            with connect(self.dsn) as db:
                db.execute('UPDATE btl.users SET is_active=false WHERE id=%s',(self.actor,))
            with self.assertRaises(ContractError):
                bounded_run(self.dsn,self.actor,self.workspace,'workspace',(session,{'timeframe':'1m'}))
        finally:
            app.close()

    def test_monthly_parquet_synthetic_source_crosses_authenticated_queue_worker_and_journal(self):
        from cloud import worker
        worker.close()
        source = research_provider()
        token = None
        events = []
        while True:
            page = source.read_page(source.dataset_id, source.dataset_version, token, 64)
            events.extend(page['events'])
            if page['endOfDataset']:
                break
            token = page['nextToken']
        with tempfile.TemporaryDirectory() as temporary:
            root = os.path.join(temporary, 'monthly')
            manifest = write_monthly_parquet(root, iter(events),
                source.describe(source.dataset_id, source.dataset_version),
                expected_version=source.dataset_version, row_group_size=128)
            pin = {
                'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1',
                'BTL_QA_SYNTHETIC_MONTHLY_ROOT': root,
                'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': source.dataset_id,
                'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': source.dataset_version,
                'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': manifest['manifestHash'],
                'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1',
            }
            with patch.dict(os.environ, pin):
                try:
                    path = self.fixture.root
                    record = method()
                    created_method = self.fixture.client.post(path + '/methods',
                        headers=self.fixture.headers, json=record)
                    self.assertEqual(created_method.status_code, 200, created_method.text)
                    session_id = 'session:' + uuid.uuid4().hex
                    request = {'id': session_id, 'name': 'Monthly Parquet queue QA',
                               'methodId': record['id'], 'initialBalance': '10000',
                               'startPeriod': '2020-01'}
                    create_job = str(uuid.uuid4())
                    queued = self.fixture.client.post(path + '/sessions',
                        headers={**self.fixture.headers, 'X-BTL-Job': create_job}, json=request)
                    self.assertEqual(queued.status_code, 202, queued.text)
                    self.assertEqual(queued.json()['state'], 'QUEUED')
                    self.assertTrue(queue.work_one(self.dsn, worker.run))
                    created = self.fixture.client.get(path + '/jobs/' + create_job,
                        headers=self.fixture.headers)
                    self.assertEqual(created.status_code, 200, created.text)
                    self.assertEqual(created.json()['state'], 'SUCCEEDED')
                    with connect(self.dsn) as db:
                        row = db.execute('SELECT queue_metrics,queue_metrics_hash,worker_metrics,worker_metrics_hash FROM btl.research_jobs WHERE id=%s',
                                         (uuid.UUID(create_job),)).fetchone()
                    queue_measurements = json.loads(bytes(row[0]))
                    self.assertEqual(content_hash(queue_measurements), row[1])
                    measurements = json.loads(bytes(row[2]))
                    self.assertEqual(content_hash(measurements), row[3])
                    self.assertEqual(measurements['artifact'], 'BTL-NATIVE-WORKER-METRICS-1')
                    self.assertGreater(measurements['wallNs'], 0)
                    self.assertGreater(measurements['cpuNs'], 0)
                    self.assertGreater(measurements['processPeakRssBytes'], 0)
                    distributions = collect_job_metrics(self.dsn)
                    self.assertGreaterEqual(distributions['queueWaitMicroseconds']['sampleCount'], 1)
                    self.assertGreaterEqual(distributions['worker']['cpuNs']['sampleCount'], 1)
                    view = self.fixture.client.get(path + '/sessions/' + session_id,
                        headers=self.fixture.headers)
                    self.assertEqual(view.status_code, 200, view.text)
                    self.assertEqual((view.json()['state']['datasetId'],
                                      view.json()['state']['datasetVersion']),
                                     (source.dataset_id, source.dataset_version))

                    review = review_request(view.json())
                    reviewed = self.fixture.client.post(path + '/reviews',
                        headers=self.fixture.headers, json=review)
                    self.assertEqual(reviewed.status_code, 200, reviewed.text)
                    pin_body = {'reviewId': review['requestId'],
                                'reviewHash': reviewed.json()['reviewHash']}
                    confirmed = self.fixture.client.post(path + '/sessions/' + session_id + '/confirm',
                        headers=self.fixture.headers, json=pin_body)
                    self.assertEqual(confirmed.status_code, 200, confirmed.text)
                    duplicate = self.fixture.client.post(path + '/sessions/' + session_id + '/confirm',
                        headers=self.fixture.headers, json=pin_body)
                    self.assertEqual(duplicate.content, confirmed.content)
                    status = self.fixture.client.get(path + '/sessions/' + session_id +
                        '/commands/' + review['requestId'], headers=self.fixture.headers)
                    self.assertEqual(status.json()['status'], 'COMMITTED')
                    self.assertTrue(status.json()['receipt']['durable'])

                    confirmed_view = self.fixture.client.get(path + '/sessions/' + session_id,
                        headers=self.fixture.headers).json()
                    advance_id = 'command:' + uuid.uuid4().hex
                    advance = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1',
                               'sessionId': session_id, 'commandId': advance_id,
                               'expectedRevision': confirmed_view['state']['revision'],
                               'kind': 'ADVANCE',
                               'payload': {'targetNs': str(int(confirmed_view['state']['throughNs']) +
                                                          15_000_000_000)}}
                    advance_job = str(uuid.uuid4())
                    queued_advance = self.fixture.client.post(
                        path + '/sessions/' + session_id + '/commands',
                        headers={**self.fixture.headers, 'X-BTL-Job': advance_job}, json=advance)
                    self.assertEqual(queued_advance.status_code, 202, queued_advance.text)
                    self.assertTrue(queue.work_one(self.dsn, worker.run))
                    advance_status = self.fixture.client.get(path + '/jobs/' + advance_job,
                        headers=self.fixture.headers)
                    self.assertEqual(advance_status.json()['state'], 'SUCCEEDED')
                    self.assertTrue(advance_status.json()['result']['durable'])
                    advanced_view = self.fixture.client.get(path + '/sessions/' + session_id,
                        headers=self.fixture.headers).json()
                    self.assertGreater(advanced_view['state']['revision'],
                                       confirmed_view['state']['revision'])

                    journal = self.fixture.client.get(path + '/sessions/' + session_id + '/journal',
                        headers=self.fixture.headers)
                    self.assertEqual(journal.status_code, 200, journal.text)
                    self.assertEqual([order['id'] for order in journal.json()['orders']],
                                     [review['requestId']])
                    note = {'orderId': review['requestId'], 'expectedNoteRevision': 0,
                            'text': 'synthetic monthly parquet QA', 'tags': ['qa']}
                    saved = self.fixture.client.post(path + '/sessions/' + session_id + '/journal',
                        headers=self.fixture.headers, json=note)
                    self.assertEqual(saved.status_code, 200, saved.text)
                    journal = self.fixture.client.get(path + '/sessions/' + session_id + '/journal',
                        headers=self.fixture.headers)
                    self.assertEqual(journal.json()['notes'][0]['text'], note['text'])
                    self.assertEqual(len(journal.json()['orders']), 1)

                    summary = self.fixture.client.get(
                        path + '/sessions/' + session_id + '/summary', headers=self.fixture.headers)
                    self.assertEqual(summary.status_code, 200, summary.text)
                    self.assertEqual(summary.json()['artifact'], 'BTL-SESSION-SUMMARY-1')
                    self.assertEqual((summary.json()['datasetId'], summary.json()['datasetVersion']),
                                     (source.dataset_id, source.dataset_version))
                    self.assertEqual(summary.json()['model'], 'SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION')

                    storage = self.fixture.client.get(
                        path + '/sessions/' + session_id + '/metering/storage',
                        headers=self.fixture.headers)
                    self.assertEqual(storage.status_code, 200, storage.text)
                    self.assertEqual(storage.json()['artifact'], 'BTL-SESSION-STORAGE-METRICS-1')
                    self.assertEqual(storage.json()['integrityStatus'], 'NOT_CHECKED_BY_STORAGE_METER')
                    self.assertIsNone(storage.json()['sharedCanonicalDatasetBytes'])

                    # A second verified tenant traverses the same pinned
                    # immutable Parquet publication through its own Session.
                    actor_two, headers_two = self.fixture.account(
                        email='monthly-parquet-' + uuid.uuid4().hex + '@example.com')
                    self.assertNotEqual(str(actor_two), str(self.fixture.actor))
                    workspace_two = self.fixture.client.post('/api/v1/workspaces', headers=headers_two,
                        json={'name': 'Second shared-source QA trader'})
                    self.assertEqual(workspace_two.status_code, 201, workspace_two.text)
                    root_two = '/api/v1/workspaces/' + workspace_two.json()['id'] + '/research'
                    method_two = method()
                    created_method_two = self.fixture.client.post(root_two + '/methods',
                        headers=headers_two, json=method_two)
                    self.assertEqual(created_method_two.status_code, 200, created_method_two.text)
                    session_two = 'session:' + uuid.uuid4().hex
                    create_job_two = str(uuid.uuid4())
                    queued_two = self.fixture.client.post(root_two + '/sessions',
                        headers={**headers_two, 'X-BTL-Job': create_job_two}, json={
                            'id': session_two, 'name': 'Second Monthly Parquet QA trader',
                            'methodId': method_two['id'], 'initialBalance': '10000',
                            'startPeriod': '2020-01'})
                    self.assertEqual(queued_two.status_code, 202, queued_two.text)
                    self.assertTrue(queue.work_one(self.dsn, worker.run))
                    created_two = self.fixture.client.get(root_two + '/jobs/' + create_job_two,
                        headers=headers_two)
                    self.assertEqual(created_two.json()['state'], 'SUCCEEDED')
                    view_two = self.fixture.client.get(root_two + '/sessions/' + session_two,
                        headers=headers_two)
                    self.assertEqual(view_two.status_code, 200, view_two.text)
                    self.assertEqual((view_two.json()['state']['datasetId'],
                                      view_two.json()['state']['datasetVersion']),
                                     (source.dataset_id, source.dataset_version))
                    review_two = review_request(view_two.json())
                    reviewed_two = self.fixture.client.post(root_two + '/reviews',
                        headers=headers_two, json=review_two)
                    self.assertEqual(reviewed_two.status_code, 200, reviewed_two.text)
                    pin_two = {'reviewId': review_two['requestId'],
                               'reviewHash': reviewed_two.json()['reviewHash']}
                    confirmed_two = self.fixture.client.post(
                        root_two + '/sessions/' + session_two + '/confirm',
                        headers=headers_two, json=pin_two)
                    self.assertEqual(confirmed_two.status_code, 200, confirmed_two.text)
                    duplicate_two = self.fixture.client.post(
                        root_two + '/sessions/' + session_two + '/confirm',
                        headers=headers_two, json=pin_two)
                    self.assertEqual(duplicate_two.content, confirmed_two.content)
                    receipt_two = self.fixture.client.get(
                        root_two + '/sessions/' + session_two + '/commands/' + review_two['requestId'],
                        headers=headers_two)
                    self.assertEqual(receipt_two.json()['status'], 'COMMITTED')
                    self.assertTrue(receipt_two.json()['receipt']['durable'])
                    self.assertEqual(self.fixture.client.get(
                        path + '/sessions/' + session_two, headers=self.fixture.headers).status_code, 404)
                    self.assertEqual(self.fixture.client.get(
                        root_two + '/sessions/' + session_id, headers=headers_two).status_code, 404)
                    confirmed_view_two = self.fixture.client.get(
                        root_two + '/sessions/' + session_two, headers=headers_two).json()
                    advance_two = {
                        'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1',
                        'sessionId': session_two, 'commandId': 'command:' + uuid.uuid4().hex,
                        'expectedRevision': confirmed_view_two['state']['revision'],
                        'kind': 'ADVANCE',
                        'payload': {'targetNs': str(int(confirmed_view_two['state']['throughNs']) +
                                                   15_000_000_000)},
                    }
                    advance_job_two = str(uuid.uuid4())
                    queued_advance_two = self.fixture.client.post(
                        root_two + '/sessions/' + session_two + '/commands',
                        headers={**headers_two, 'X-BTL-Job': advance_job_two}, json=advance_two)
                    self.assertEqual(queued_advance_two.status_code, 202, queued_advance_two.text)
                    self.assertTrue(queue.work_one(self.dsn, worker.run))
                    advanced_two = self.fixture.client.get(root_two + '/jobs/' + advance_job_two,
                        headers=headers_two)
                    self.assertEqual(advanced_two.json()['state'], 'SUCCEEDED')
                    self.assertTrue(advanced_two.json()['result']['durable'])
                    journal_two = self.fixture.client.get(
                        root_two + '/sessions/' + session_two + '/journal', headers=headers_two)
                    self.assertEqual(journal_two.status_code, 200, journal_two.text)
                    self.assertEqual([order['id'] for order in journal_two.json()['orders']],
                                     [review_two['requestId']])
                    summary_two = self.fixture.client.get(
                        root_two + '/sessions/' + session_two + '/summary', headers=headers_two)
                    self.assertEqual((summary_two.json()['datasetId'], summary_two.json()['datasetVersion']),
                                     (source.dataset_id, source.dataset_version))
                    meter_two = self.fixture.client.get(
                        root_two + '/sessions/' + session_two + '/metering/storage', headers=headers_two)
                    self.assertEqual(meter_two.status_code, 200, meter_two.text)
                    self.assertEqual(meter_two.json()['artifact'], 'BTL-SESSION-STORAGE-METRICS-1')

                    failed = self.submit(operation='workspace',
                                         args=(session_id, {'timeframe': 'invalid'}))
                    self.assertTrue(queue.work_one(self.dsn, worker.run))
                    failed_status = queue.inspect(self.dsn, self.actor, self.workspace,
                                                  failed['jobId'])
                    self.assertEqual(failed_status['state'], 'FAILED')
                    with connect(self.dsn) as db:
                        failed_metrics = db.execute(
                            'SELECT worker_metrics,worker_metrics_hash FROM btl.research_jobs WHERE id=%s',
                            (uuid.UUID(failed['jobId']),)).fetchone()
                    error_measurements = json.loads(bytes(failed_metrics[0]))
                    self.assertEqual(content_hash(error_measurements), failed_metrics[1])
                    self.assertGreater(error_measurements['wallNs'], 0)
                finally:
                    worker.close()

    def test_api_lifespan_worker_executes_pinned_monthly_parquet_pipeline(self):
        """Exercise the complete shared-source path through the service worker pump."""
        from cloud import worker
        worker.close()
        source = research_provider()
        token = None
        events = []
        while True:
            page = source.read_page(source.dataset_id, source.dataset_version, token, 64)
            events.extend(page['events'])
            if page['endOfDataset']:
                break
            token = page['nextToken']

        with tempfile.TemporaryDirectory() as temporary:
            root = os.path.join(temporary, 'monthly')
            manifest = write_monthly_parquet(root, iter(events),
                source.describe(source.dataset_id, source.dataset_version),
                expected_version=source.dataset_version, row_group_size=128)
            pin = {
                'BTL_QA_SYNTHETIC_MONTHLY_ENABLE': '1',
                'BTL_QA_SYNTHETIC_MONTHLY_ROOT': root,
                'BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID': source.dataset_id,
                'BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION': source.dataset_version,
                'BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256': manifest['manifestHash'],
                'BTL_TICK_SESSION_STORAGE_FORMAT': 'compact-v1',
            }
            with patch.dict(os.environ, pin):
                api_client = cloud_fixture.client(self.fixture.app)

                def completed_job(client, root_path, job_id):
                    deadline = time.monotonic() + 25
                    while time.monotonic() < deadline:
                        response = client.get(root_path + '/jobs/' + job_id,
                                              headers=self.fixture.headers)
                        self.assertEqual(response.status_code, 200, response.text)
                        result = response.json()
                        if result['state'] not in ('QUEUED', 'RUNNING'):
                            return result
                        time.sleep(.05)
                    self.fail('Timed out waiting for lifespan worker job ' + job_id)

                try:
                    with api_client as active:
                        path = self.fixture.root
                        record = method()
                        created_method = active.post(path + '/methods',
                            headers=self.fixture.headers, json=record)
                        self.assertEqual(created_method.status_code, 200, created_method.text)

                        session_id = 'session:' + uuid.uuid4().hex
                        create_job = str(uuid.uuid4())
                        queued = active.post(path + '/sessions',
                            headers={**self.fixture.headers, 'X-BTL-Job': create_job}, json={
                                'id': session_id, 'name': 'Lifespan Monthly Parquet QA',
                                'methodId': record['id'], 'initialBalance': '10000',
                                'startPeriod': '2020-01'})
                        self.assertEqual(queued.status_code, 202, queued.text)
                        self.assertEqual(queued.json()['state'], 'QUEUED')
                        created = completed_job(active, path, create_job)
                        self.assertEqual(created['state'], 'SUCCEEDED', created)
                        created_response = active.post(path + '/sessions',
                            headers={**self.fixture.headers, 'X-BTL-Job': create_job}, json={
                                'id': session_id, 'name': 'Lifespan Monthly Parquet QA',
                                'methodId': record['id'], 'initialBalance': '10000',
                                'startPeriod': '2020-01'})
                        self.assertEqual(created_response.status_code, 200, created_response.text)
                        self.assertEqual(created_response.json(), created['result'])

                        view = active.get(path + '/sessions/' + session_id,
                                          headers=self.fixture.headers)
                        self.assertEqual(view.status_code, 200, view.text)
                        self.assertEqual((view.json()['state']['datasetId'],
                                          view.json()['state']['datasetVersion']),
                                         (source.dataset_id, source.dataset_version))
                        review = review_request(view.json())
                        reviewed = active.post(path + '/reviews', headers=self.fixture.headers,
                                               json=review)
                        self.assertEqual(reviewed.status_code, 200, reviewed.text)
                        confirmation = {'reviewId': review['requestId'],
                                        'reviewHash': reviewed.json()['reviewHash']}
                        confirmed = active.post(path + '/sessions/' + session_id + '/confirm',
                                                headers=self.fixture.headers, json=confirmation)
                        self.assertEqual(confirmed.status_code, 200, confirmed.text)
                        repeated = active.post(path + '/sessions/' + session_id + '/confirm',
                                               headers=self.fixture.headers, json=confirmation)
                        self.assertEqual(repeated.content, confirmed.content)
                        receipt = active.get(path + '/sessions/' + session_id + '/commands/' +
                                             review['requestId'], headers=self.fixture.headers)
                        self.assertEqual(receipt.status_code, 200, receipt.text)
                        self.assertEqual(receipt.json()['status'], 'COMMITTED')
                        self.assertTrue(receipt.json()['receipt']['durable'])

                        confirmed_view = active.get(path + '/sessions/' + session_id,
                                                    headers=self.fixture.headers).json()
                        advance = {'schemaVersion': 1, 'artifact': 'BTL-TICK-EXECUTION-COMMAND-1',
                                   'sessionId': session_id,
                                   'commandId': 'command:' + uuid.uuid4().hex,
                                   'expectedRevision': confirmed_view['state']['revision'],
                                   'kind': 'ADVANCE',
                                   'payload': {'targetNs': str(int(confirmed_view['state']['throughNs']) +
                                                              15_000_000_000)}}
                        advance_job = str(uuid.uuid4())
                        queued_advance = active.post(
                            path + '/sessions/' + session_id + '/commands',
                            headers={**self.fixture.headers, 'X-BTL-Job': advance_job}, json=advance)
                        self.assertEqual(queued_advance.status_code, 202, queued_advance.text)
                        advance_status = completed_job(active, path, advance_job)
                        self.assertEqual(advance_status['state'], 'SUCCEEDED', advance_status)
                        self.assertTrue(advance_status['result']['durable'])

                        journal = active.get(path + '/sessions/' + session_id + '/journal',
                                             headers=self.fixture.headers)
                        self.assertEqual(journal.status_code, 200, journal.text)
                        self.assertEqual([order['id'] for order in journal.json()['orders']],
                                         [review['requestId']])
                        summary = active.get(path + '/sessions/' + session_id + '/summary',
                                             headers=self.fixture.headers)
                        self.assertEqual(summary.status_code, 200, summary.text)
                        self.assertEqual((summary.json()['datasetId'],
                                          summary.json()['datasetVersion']),
                                         (source.dataset_id, source.dataset_version))
                        meter = active.get(path + '/sessions/' + session_id + '/metering/storage',
                                           headers=self.fixture.headers)
                        self.assertEqual(meter.status_code, 200, meter.text)
                        self.assertEqual(meter.json()['artifact'], 'BTL-SESSION-STORAGE-METRICS-1')
                finally:
                    worker.close()

    def test_replay_process_death_after_inner_commit_recovers_without_duplicate_fill(self):
        app,session,command=self.replay_fixture()
        try:
            job=self.submit(operation='replay',args=(session,command))
            script="""from cloud.queue import work_one
from cloud.research import run
import os
def crash_after(*args,**kwargs):
    run(*args,**kwargs)
    os._exit(17)
work_one(os.environ['BTL_TEST_DATABASE_URL'],crash_after)
"""
            process=subprocess.run([sys.executable,'-B','-c',script],timeout=20,capture_output=True,
                                   env={**os.environ,'BTL_TEST_DATABASE_URL':self.dsn})
            self.assertEqual(process.returncode,17,process.stderr.decode(errors='replace'))
            before=app.inspect(session)
            self.assertEqual(before['state']['revision'],command['expectedRevision']+1)
            self.assertTrue(any(event['kind']=='ENTRY_FILL' for event in before['events']))
            with connect(self.dsn) as db:
                db.execute("UPDATE btl.research_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",
                           (job['jobId'],))
            self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,job['jobId'])['state'],'QUEUED')
            self.assertTrue(queue.work_one(self.dsn,run))
            result=queue.inspect(self.dsn,self.actor,self.workspace,job['jobId'])
            self.assertEqual(result['state'],'SUCCEEDED')
            self.assertTrue(result['result']['durable'])
            self.assertEqual(app.inspect(session),before)
            duplicate=self.submit(operation='replay',args=(session,command))
            self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,duplicate['jobId'],cancel=True)['state'],'RECONCILE_REQUIRED')
            self.assertEqual(app.inspect(session),before,'Cancelled operational retry must not claim the previous fill was absent')
        finally:
            app.close()

    def test_replay_expiry_and_conflict_never_claim_unchanged_financial_state(self):
        app,session,command=self.replay_fixture()
        try:
            original=app.apply(session,command)
            before=app.inspect(session)
            expired=self.submit(operation='replay',args=(session,command))
            with connect(self.dsn) as db:
                db.execute("UPDATE btl.research_jobs SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",(expired['jobId'],))
            self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,expired['jobId'])['state'],'RECONCILE_REQUIRED')
            conflict={**command,'payload':{'targetNs':str(int(command['payload']['targetNs'])+60_000_000_000)}}
            changed=self.submit(operation='replay',args=(session,conflict))
            self.assertTrue(queue.work_one(self.dsn,run))
            self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,changed['jobId'])['state'],'RECONCILE_REQUIRED')
            self.assertEqual(app.inspect(session),before)
            self.assertTrue(original['durable'])
        finally:
            app.close()

    def test_replay_admission_requires_owner_and_refuses_other_mutations(self):
        app,session,command=self.replay_fixture()
        try:
            member,headers=self.fixture.account()
            self.assertEqual(self.fixture.client.post('/api/v1/workspaces/'+str(self.workspace)+'/members',
                            headers=self.fixture.headers,json={'userId':member}).status_code,204)
            with self.assertRaises(ContractError):
                queue.submit(self.dsn,uuid.UUID(member),self.workspace,uuid.uuid4(),'replay',(session,command))
            cancel={**command,'kind':'CANCEL','payload':{'orderId':'order:authored'}}
            with self.assertRaises(ContractError):
                self.submit(operation='replay',args=(session,cancel))
            with connect(self.dsn) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM btl.research_jobs WHERE actor_id=%s',(self.actor,)).fetchone()[0],0)
        finally:
            app.close()

    def test_single_worker_lease_heartbeat_and_cancel_running_is_honest(self):
        first, second = self.submit(), self.submit()
        entered, release = Event(), Event()
        def hold(*args):
            entered.set()
            if not release.wait(8):
                raise RuntimeError('bounded test deadline')
            return {'value':'held result'}
        with ThreadPoolExecutor(max_workers=2) as pool:
            task=pool.submit(queue.work_one,self.dsn,hold)
            try:
                self.assertTrue(entered.wait(5))
                self.assertFalse(queue.work_one(self.dsn,lambda *args:self.fail('single worker slot is exclusive')))
                initial=queue.inspect(self.dsn,self.actor,self.workspace,first['jobId'])
                self.assertEqual(initial['state'],'RUNNING')
                time.sleep(queue.HEARTBEAT_SECONDS + .2)
                running=queue.inspect(self.dsn,self.actor,self.workspace,first['jobId'],cancel=True)
                self.assertEqual(running['state'],'RUNNING')
                self.assertEqual(running['cancellation'],'REQUESTED')
                self.assertEqual(running['attempt'],1)
                self.assertGreater(running['heartbeatAt'],initial['heartbeatAt'])
            finally:
                release.set()
            self.assertTrue(task.result(8))
        finished=queue.inspect(self.dsn,self.actor,self.workspace,first['jobId'])
        self.assertEqual(finished['state'],'CANCELLED')
        self.assertEqual(finished['cancellation'],'CANCELLED')
        self.assertTrue(queue.work_one(self.dsn,lambda *args:{'value':'second'}))
        self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,second['jobId'])['state'],'SUCCEEDED')

    def test_expired_or_corrupt_jobs_never_enter_runner(self):
        expired, corrupt = self.submit(), self.submit()
        with connect(self.dsn) as db:
            db.execute("UPDATE btl.research_jobs SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",(expired['jobId'],))
            db.execute("UPDATE btl.research_jobs SET input=%s WHERE id=%s",(b'{"schemaVersion":1,"operation":"workspace","args":["session:changed",{}]}',corrupt['jobId']))
        self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,expired['jobId'])['state'],'EXPIRED')
        self.assertTrue(queue.work_one(self.dsn,lambda *args:self.fail('invalid job must not execute')))
        self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,expired['jobId'])['state'],'EXPIRED')
        self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,corrupt['jobId'])['state'],'FAILED')

    def test_worker_revalidates_verified_identity_and_foreign_scope_is_refused(self):
        job=self.submit()
        other, headers=self.fixture.account()
        with self.assertRaises(ContractError):
            queue.inspect(self.dsn,uuid.UUID(other),self.workspace,job['jobId'])
        with connect(self.dsn) as db:
            db.execute('UPDATE btl.users SET is_active=false WHERE id=%s',(self.actor,))
        self.assertTrue(queue.work_one(self.dsn,run))
        with connect(self.dsn) as db:
            row=db.execute('SELECT state,result FROM btl.research_jobs WHERE id=%s',(job['jobId'],)).fetchone()
        self.assertEqual(row,('FAILED',None))

    def test_global_ceiling_and_bounded_completed_retention(self):
        # Extra QA actors/workspaces are explicit; clean only these authored job rows.
        subjects=[(self.actor,self.workspace)]
        try:
            for _ in range(8):
                actor,headers=self.fixture.account()
                workspace=self.fixture.client.post('/api/v1/workspaces',headers=headers,json={'name':'Queue pressure QA'}).json()['id']
                subjects.append((uuid.UUID(actor),uuid.UUID(workspace)))
            for actor,workspace in subjects[:8]:
                for _ in range(2):
                    queue.submit(self.dsn,actor,workspace,uuid.uuid4(),'workspace',('session:bounded',{}))
            with self.assertRaises(ContractError) as full:
                queue.submit(self.dsn,*subjects[-1],uuid.uuid4(),'workspace',('session:bounded',{}))
            self.assertEqual(full.exception.code,'QUEUE_CAPACITY')
            with connect(self.dsn) as db:
                db.execute("UPDATE btl.research_jobs SET state='CANCELLED',finished_at=clock_timestamp() WHERE actor_id=ANY(%s)",([a for a,w in subjects],))
            for _ in range(40):
                job=self.submit()
                queue.inspect(self.dsn,self.actor,self.workspace,job['jobId'],cancel=True)
            with connect(self.dsn) as db:
                self.assertLessEqual(db.execute('SELECT count(*) FROM btl.research_jobs').fetchone()[0],queue.RETAINED_LIMIT)
        finally:
            with connect(self.dsn) as db:
                db.execute('DELETE FROM btl.research_jobs WHERE actor_id=ANY(%s)',([a for a,w in subjects],))
