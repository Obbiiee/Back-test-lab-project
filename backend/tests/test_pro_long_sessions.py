"""Pro long Sessions and checkpoint V1/V2 compatibility on the REAL stack (API, durable queue, native worker, canonical Monthly Parquet). SYNTHETIC / TEST ONLY.

 * YearJanDec  : ONE Session runs from 2020-01-02 to 2020-12-27, crossing all eleven month boundaries, a worker restart in the middle, and equals an uninterrupted control.
 * YearBoundary: ONE Session runs from 2020-12-01 into 2021-01 (the year boundary) and equals an uninterrupted control.
 * Compat      : a Session started under checkpoint V1 is continued under V2 (lazy, non-destructive migration) and equals a V1-only control; a worker SIGKILLed in the middle of a
                 V2 replay-run is recovered by a cold worker with nothing lost or duplicated.
The synthetic source can only express one instrument, so none of this says anything about multi-instrument Sessions or real market data."""
import os
import subprocess
import sys
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from cloud import worker
from infrastructure.database import connect
from tests.test_free_pro_months import DSN, NS, MonthBase, leaf_diff
from tests.test_replay_run import KILL_WORKER


def month_starts(first_ns, last_ns):
    """First instant of every UTC month strictly after first_ns and not after last_ns."""
    out, d = [], datetime.fromtimestamp(first_ns // NS, timezone.utc)
    year, month = d.year, d.month
    while True:
        month += 1
        if month == 13:
            year, month = year + 1, 1
        ns = int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp()) * NS
        if ns > last_ns:
            return out
        out.append(ns)


class StagedEqualsControl:
    def staged_run_equals_control(self):
        self.grant_pro()
        sid = self.new_session()
        self.assertEqual(sorted(self.orders(sid).values()), ["ACTIVE", "PENDING"])
        bounds = month_starts(self.start, self.end)
        self.assertGreaterEqual(len(bounds), self.EXPECTED_BOUNDARIES)
        step = self.SPEC["gen"].get("step_ns", 60 * NS)
        crossed = []
        for index, boundary in enumerate(bounds):
            self.drive(sid, boundary - 1)
            pre = (self.orders(sid), self.view(sid)["state"]["balance"])
            self.drive(sid, boundary + 3 * step)
            state = self.view(sid)["state"]
            self.assertGreater(int(state["throughNs"]), boundary, "cursor did not pass the boundary")
            self.assertEqual((self.orders(sid), state["balance"]), pre, "state changed at the month boundary " + str(boundary))
            crossed.append(boundary)
            if index == len(bounds) // 2:
                worker.close()                                           # restart the worker in the middle: resume from the durable checkpoint
        self.drive(sid, self.end)
        control = self.new_session()
        self.drive(control, self.end)
        self.assertEqual(leaf_diff(self.facts(sid), self.facts(control)), [], "staged Pro run differs from the uninterrupted control")
        self.assertEqual(int(self.facts(sid)["through"]), self.end)
        print("LONG_SESSION_EVIDENCE " + self.id().split(".")[-2] + " boundariesCrossed=" + str(len(crossed)) + " " + str(self.resource_summary()))


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class YearJanDec(StagedEqualsControl, MonthBase):
    # The synthetic QA source pins a Session start to its authored 2020-01 timeline (execution/research.py fixture constants), so the "year" is 2020.
    SPEC = dict(name="y2020", ticks=16384, period="2020-01", gen=dict(start_ns=int(datetime(2020, 1, 2, tzinfo=timezone.utc).timestamp()) * NS, step_ns=1900 * NS))
    EXPECTED_BOUNDARIES = 11

    def test_one_pro_session_runs_january_to_december_with_parity(self):
        self.staged_run_equals_control()


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class YearBoundary(StagedEqualsControl, MonthBase):
    # first tick 2020-12-01, last tick in January 2021: the YEAR boundary 2020 -> 2021 lies inside the Session
    SPEC = dict(name="dec2020", ticks=4096, period="2020-01", gen=dict(start_ns=int(datetime(2020, 12, 1, tzinfo=timezone.utc).timestamp()) * NS, step_ns=1300 * NS))
    EXPECTED_BOUNDARIES = 1

    def test_one_pro_session_runs_from_december_into_january_with_parity(self):
        self.staged_run_equals_control()


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class Compat(MonthBase):
    SPEC = dict(name="c8192", ticks=8192, period="2020-01", gen={})

    def run_all(self, sid, target):
        self.drive(sid, target)

    def test_v1_session_continued_under_v2_equals_a_v1_only_control(self):
        self.grant_pro()
        with patch.dict(os.environ, {"BTL_TICK_CHECKPOINT_FORMAT": ""}):                 # production default: V1
            worker.close()
            control = self.new_session()
            self.drive(control, self.end)                                               # 8,192 ticks fit the V1 step budget
            sid = self.new_session()
            half = self.start + 3000 * 60 * NS
            self.drive(sid, half)                                                       # committed under V1
            self.assertLess(int(self.view(sid)["state"]["throughNs"]), self.end)
        with patch.dict(os.environ, {"BTL_TICK_CHECKPOINT_FORMAT": "compact-v2"}):        # operator enables V2 and restarts the worker
            worker.close()
            self.drive(sid, self.end)                                                   # the V1 Session is read and continued; V1 data is not rewritten
        worker.close()
        self.assertEqual(leaf_diff(self.facts(sid), self.facts(control)), [], "V1->V2 continuation differs from the V1-only control")
        self.assertEqual(int(self.facts(sid)["through"]), self.end)

    def test_sigkill_during_a_v2_replay_run_then_cold_recovery_loses_and_duplicates_nothing(self):
        from execution import replay_run as rr
        self.grant_pro()
        control = self.new_session()
        self.drive(control, self.end)
        sid = self.new_session()
        st = self.summary(sid)
        request = dict(schemaVersion=1, artifact=rr.REQUEST_ARTIFACT, runId=uuid.uuid4().hex, segment=0, sessionId=sid, expectedRevision=st["revision"], targetNs=str(self.end))
        job, r = self.post("/sessions/" + sid + "/replay-run", request)
        env = {**os.environ, "BTL_TEST_DATABASE_URL": self.dsn, "KILL_AFTER_CHUNKS": "9"}
        killed = subprocess.run([sys.executable, "-B", "-c", KILL_WORKER], timeout=180, capture_output=True, env=env, cwd=os.getcwd())
        self.assertEqual(killed.returncode, -9, killed.stderr.decode(errors="replace")[-400:])
        with connect(self.dsn) as db:
            committed = db.execute("SELECT count(*) FROM btl.tick_commands WHERE session_id=%s AND command_id LIKE 'command:replay-run:%%'", (sid,)).fetchone()[0]
            self.assertEqual(committed, 9, "nine chunks were committed before the process died")
            db.execute("UPDATE btl.research_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s AND state='RUNNING'", (job,))
        for _ in range(200):
            done = self.work(job)
            self.assertEqual(done["state"], "SUCCEEDED", done)
            if not done["result"].get("continuationJobId"):
                break
            job = done["result"]["continuationJobId"]
        self.assertTrue(done["result"]["targetReached"])
        self.assertEqual(leaf_diff(self.facts(sid), self.facts(control)), [], "SIGKILL recovery differs from the uninterrupted control")
        with connect(self.dsn) as db:
            dup = db.execute("SELECT count(*) FROM (SELECT command_id FROM btl.tick_commands WHERE session_id=%s GROUP BY 1 HAVING count(*)>1) d", (sid,)).fetchone()[0]
        self.assertEqual(dup, 0)


if __name__ == "__main__":
    unittest.main()
