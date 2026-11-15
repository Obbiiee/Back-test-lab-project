"""Free-window Jump through the durable PostgreSQL queue with a worker that is SIGKILLed at four points; every recovery runs in a fresh worker process
(cold recovery) and the committed result must equal a chronological replay of a control Session under the same entitlement. Reducer untouched."""
import os
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql

from application.models import TrustedScope
from cloud import queue
from execution.research import ResearchApplication
from execution.research_fixture import STEP_NS
from infrastructure.database import connect, migrate
import tests.test_cloud_research as cloud_fixture
from tests.test_research_sessions import method, review_request

DSN = cloud_fixture.DSN

WORKER = """
import os, signal
from cloud.queue import work_one
from cloud.research import run
import execution.controller as controller
mode = os.environ['KILL_AT']
kill = lambda: os.kill(os.getpid(), signal.SIGKILL)
if mode == 'before_run':
    kill()
real_apply = controller.ExecutionController.apply
def apply(self, scope, raw):
    if mode == 'before_commit':
        kill()                                   # the ADVANCE is decided but nothing is committed
    result = real_apply(self, scope, raw)
    if mode == 'after_commit':
        kill()                                   # committed, the job result is not yet recorded
    return result
controller.ExecutionController.apply = apply
def runner(*a, **k):
    value = run(*a, **k)
    if mode == 'after_run':
        kill()                                   # everything done, only the queue bookkeeping is missing
    return value
work_one(os.environ['BTL_TEST_DATABASE_URL'], runner)
"""


def command(sid, state, kind, payload):
    return {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": sid, "commandId": "c:" + uuid.uuid4().hex,
            "expectedRevision": state["revision"], "kind": kind, "payload": payload}


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class WindowJumpRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = 'btl_wjr_' + uuid.uuid4().hex[:12]
        with connect(DSN) as db:
            db.autocommit = True
            db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        cls.dsn = psycopg.conninfo.make_conninfo(DSN, dbname=name)
        migrate(cls.dsn)
        cls.patch = patch.object(cloud_fixture, 'DSN', cls.dsn); cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()

    def setUp(self):
        self.f = cloud_fixture.CloudResearchTests('test_member_read_only_then_revocation_and_logout')
        self.f.setUp(start_workers=False)
        self.actor, self.workspace = uuid.UUID(self.f.actor), uuid.UUID(self.f.workspace)
        self.app = ResearchApplication(self.dsn, TrustedScope(str(self.workspace), str(self.actor)))
        self.proto = method("PROTOCOL"); self.free = method("FREE_STYLE")
        for m in (self.proto, self.free):
            self.app.create_method(m)

    def tearDown(self):
        self.app.close(); self.f.client.close()

    # ------------------------------------------------------------------------------------------------------
    def session(self, m, end_steps=None):
        sid = "session:" + uuid.uuid4().hex
        self.app.create_session(dict(id=sid, name="wjr", methodId=m["id"], initialBalance="10000", startPeriod="2020-01"))
        if end_steps is not None:
            start = int(self.state(sid)["throughNs"])
            with connect(self.dsn) as db:
                db.execute("INSERT INTO btl.entitlement_claims(actor_id,kind,claim_key,period,tier,status,workspace_id,session_id,window_start_ns,window_end_ns) "
                           "VALUES (%s,'SESSION',%s,%s,'FREE','COMMITTED',%s,%s,%s,%s)",
                           (self.actor, uuid.uuid4().hex + "0" * 32, "2020-01-" + uuid.uuid4().hex[:6], self.workspace, sid, start, start + end_steps * STEP_NS))
        return sid

    def state(self, sid):
        return self.app.inspect(sid)["state"]

    def plan(self, sid, draft, protocol=False):
        request = review_request(self.app.inspect(sid), protocol=protocol)
        request["draft"].update(draft)
        if request["draft"]["workflow"] == "PLANNED":
            request["planId"], request["planRevision"] = "plan:wjr", 0
        reviewed = self.app.review(request)
        self.app.confirm(sid, dict(reviewId=request["requestId"], reviewHash=reviewed["reviewHash"]))

    def advance_to(self, sid, target):
        for _ in range(1024):
            st = self.state(sid)
            if int(st["throughNs"]) >= target:
                return
            self.app.apply(sid, command(sid, st, "ADVANCE", {"targetNs": str(min(target, int(st["throughNs"]) + STEP_NS))}))

    def submit_jump(self, sid):
        st = self.state(sid)
        raw = {"schemaVersion": 1, "artifact": "BTL-JUMP-NEXT-EVENT-1", "requestId": uuid.uuid4().hex, "sessionId": sid, "expectedRevision": st["revision"], "timeframe": "1m"}
        job = queue.submit(self.dsn, self.actor, self.workspace, uuid.uuid4(), 'jump_next_event', (sid, raw))
        return job, raw

    def worker(self, kill_at=None):
        env = {**os.environ, 'BTL_TEST_DATABASE_URL': self.dsn, 'KILL_AT': kill_at or 'none'}
        return subprocess.run([sys.executable, '-B', '-c', WORKER], timeout=60, capture_output=True, env=env, cwd=os.getcwd())

    def expire_lease(self, job):
        with connect(self.dsn) as db:        # a job killed before it was claimed is still QUEUED (no lease to expire)
            db.execute("UPDATE btl.research_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s AND state='RUNNING'", (job['jobId'],))

    def commands(self, sid, rid):
        with connect(self.dsn) as db:
            return db.execute("SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id LIKE %s", (str(self.workspace), sid, f"jump:{rid}:r%")).fetchone()[0]

    def facts(self, sid):
        page = self.app.journal_page(sid, {"limit": 32, "cursor": None})
        rows = sorted(((o["side"], o["status"], o.get("entryPrice"), o.get("exitPrice"), o.get("net")) for o in page["orders"]), key=str)
        st = self.state(sid)
        return dict(through=st["throughNs"], balance=st["balance"], live=sorted((o["status"], o["side"]) for o in st["orders"].values() if o["status"] in ("PENDING", "ACTIVE")), ledger=rows)

    # ------------------------------------------------------------------------------------------------------
    def check_pending_scenario(self, kill_at):
        """Protocol LIMIT (would fill 22 steps in) with a 10-step Free window: the bounded jump, killed at `kill_at`, recovers to the chronological state."""
        free, control = self.session(self.proto, 10), self.session(self.proto)
        for sid in (free, control):
            self.plan(sid, dict(orderType="LIMIT", workflow="PLANNED", entry="2005", sl="2003", quantity=None, riskPercent=None), protocol=True)
        end = int(self.state(free)["throughNs"]) + 10 * STEP_NS
        job, raw = self.submit_jump(free)
        killed = self.worker(kill_at)
        self.assertEqual(killed.returncode, -9, killed.stderr.decode(errors='replace')[-400:])
        self.expire_lease(job)
        self.assertEqual(queue.inspect(self.dsn, self.actor, self.workspace, job['jobId'])['state'], 'QUEUED')
        committed_before_recovery = self.commands(free, raw['requestId'])
        self.assertEqual(committed_before_recovery, 1 if kill_at in ('after_commit', 'after_run') else 0, kill_at)
        self.assertEqual(self.worker().returncode, 0)                                  # a fresh process takes the job over
        result = queue.inspect(self.dsn, self.actor, self.workspace, job['jobId'])
        self.assertEqual(result['state'], 'SUCCEEDED')
        self.assertEqual(result['result']['status'], 'NO_EVENT_UNTIL_SESSION_END')
        self.assertEqual(self.commands(free, raw['requestId']), 1, "exactly one committed command for the request")
        facts = self.facts(free)
        self.assertLess(int(facts['through']), end)
        self.assertEqual(facts['live'], [("PENDING", "LONG")], "nothing filled outside the window")
        self.advance_to(control, int(facts['through']))
        self.assertEqual(self.facts(control), facts, "identical to the chronological replay under the same entitlement")

    def test_pending_order_jump_killed_before_run(self):
        self.check_pending_scenario('before_run')

    def test_pending_order_jump_killed_before_commit(self):
        self.check_pending_scenario('before_commit')

    def test_pending_order_jump_killed_after_commit(self):
        self.check_pending_scenario('after_commit')

    def test_pending_order_jump_killed_after_run(self):
        self.check_pending_scenario('after_run')

    def test_open_position_stop_loss_beyond_the_boundary_with_a_kill_after_commit(self):
        free, control = self.session(self.free, 5), self.session(self.free)
        for sid in (free, control):
            self.plan(sid, dict(side="LONG", orderType="MARKET", workflow="PLANNED", entry="2006.10", quantity="0.1", riskPercent="1", sl="2005.5", tp="2010"))
            self.advance_to(sid, int(self.state(sid)["throughNs"]) + STEP_NS)
        job, raw = self.submit_jump(free)
        self.assertEqual(self.worker('after_commit').returncode, -9)
        self.expire_lease(job)
        self.assertEqual(self.worker().returncode, 0)
        result = queue.inspect(self.dsn, self.actor, self.workspace, job['jobId'])
        # the killed worker had already committed the exit that ended the last live order: the retry returns the ORIGINAL committed outcome
        self.assertEqual((result['state'], result['result']['status']), ('SUCCEEDED', 'EVENT_FOUND'))
        self.assertEqual(self.commands(free, raw['requestId']), 1)
        facts = self.facts(free)
        self.assertEqual(facts['live'], [])
        self.advance_to(control, int(facts['through']))
        self.assertEqual(self.facts(control), facts)
        self.assertNotEqual(facts['balance'], "10000")

    def test_two_workers_reconcile_the_same_request_to_the_same_original_result(self):
        free, control = self.session(self.free, 5), self.session(self.free)
        for sid in (free, control):
            self.plan(sid, dict(side="LONG", orderType="MARKET", workflow="PLANNED", entry="2006.10", quantity="0.1", riskPercent="1", sl="2005.5", tp="2010"))
            self.advance_to(sid, int(self.state(sid)["throughNs"]) + STEP_NS)
        job_a, raw = self.submit_jump(free)
        self.assertEqual(self.worker('after_commit').returncode, -9)             # committed (the exit fill), job A not finalised
        # a second job carrying the very same request (another worker / a client retry with a new job id) is admitted and reconciled first
        job_b = queue.submit(self.dsn, self.actor, self.workspace, uuid.uuid4(), 'jump_next_event', (free, raw))
        self.expire_lease(job_a)
        outcomes = {}
        for _ in range(2):
            self.assertEqual(self.worker().returncode, 0)
        for name, job in (("A", job_a), ("B", job_b)):
            row = queue.inspect(self.dsn, self.actor, self.workspace, job['jobId'])
            outcomes[name] = (row['state'], row['result']['status'], row['result']['throughNs'])
        self.assertEqual(outcomes["A"], outcomes["B"])
        self.assertEqual(outcomes["A"][:2], ("SUCCEEDED", "EVENT_FOUND"))
        self.assertEqual(self.commands(free, raw['requestId']), 1, "one committed command for one request, however many workers saw it")
        self.advance_to(control, int(self.state(free)["throughNs"]))
        self.assertEqual(self.facts(control), self.facts(free))

    def test_retry_of_the_same_job_id_after_completion_returns_the_stored_result(self):
        free = self.session(self.proto, 10)
        self.plan(free, dict(orderType="LIMIT", workflow="PLANNED", entry="2005", sl="2003", quantity=None, riskPercent=None), protocol=True)
        job, raw = self.submit_jump(free)
        self.assertEqual(self.worker().returncode, 0)
        first = queue.inspect(self.dsn, self.actor, self.workspace, job['jobId'])
        again = queue.submit(self.dsn, self.actor, self.workspace, job['jobId'], 'jump_next_event', (free, raw))
        self.assertEqual(again['jobId'], job['jobId'])
        self.assertEqual(queue.inspect(self.dsn, self.actor, self.workspace, job['jobId'])['result'], first['result'])
        self.assertEqual(self.commands(free, raw['requestId']), 1)


if __name__ == "__main__":
    unittest.main()
