"""Actual PostgreSQL queue pressure, scope, ownership, rollback and cancellation."""
import os
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
