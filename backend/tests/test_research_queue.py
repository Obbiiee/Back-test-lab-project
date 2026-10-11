"""Actual PostgreSQL queue pressure, scope, ownership, rollback and cancellation."""
import os
import uuid
import unittest
import subprocess
import sys
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
from tests.test_research_sessions import method

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
        before=self.fixture.client.get(path,headers=self.fixture.headers).content
        job=str(uuid.uuid4())
        headers={**self.fixture.headers,'X-BTL-Job':job}
        response=self.fixture.client.post(path+'/view',headers=headers,json={'timeframe':'1m'})
        self.assertEqual(response.status_code,200,response.text)
        repeated=self.fixture.client.post(path+'/view',headers=headers,json={'timeframe':'1m'})
        self.assertEqual(repeated.content,response.content)
        status=self.fixture.client.get(self.fixture.root+'/jobs/'+job,headers=self.fixture.headers)
        self.assertEqual(status.json()['state'],'SUCCEEDED')
        self.assertEqual(status.json()['result'],response.json())
        self.assertEqual(self.fixture.client.get(path,headers=self.fixture.headers).content,before)

    def test_two_workers_cannot_run_same_actor_and_cancel_running_is_honest(self):
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
                self.assertFalse(queue.work_one(self.dsn,lambda *args:self.fail('same actor may not occupy both workers')))
                self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,first['jobId'],cancel=True)['state'],'RUNNING')
            finally:
                release.set()
            self.assertTrue(task.result(8))
        self.assertTrue(queue.work_one(self.dsn,lambda *args:{'value':'second'}))
        self.assertEqual(queue.inspect(self.dsn,self.actor,self.workspace,second['jobId'])['state'],'SUCCEEDED')

    def test_expired_or_corrupt_jobs_never_enter_runner(self):
        expired, corrupt = self.submit(), self.submit()
        with connect(self.dsn) as db:
            db.execute("UPDATE btl.research_jobs SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",(expired['jobId'],))
            db.execute("UPDATE btl.research_jobs SET input=%s WHERE id=%s",(b'{"schemaVersion":1,"operation":"workspace","args":["session:changed",{}]}',corrupt['jobId']))
        for _ in range(2):
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
