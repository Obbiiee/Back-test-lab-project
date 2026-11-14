"""Free/Pro admission: durable reservation ledger (RESERVED -> COMMITTED | RELEASED), two quotas, idempotency, concurrency, fail-closed profile."""
import os
import threading
import time
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from contracts.primitives import ContractError
from infrastructure.database import connect
from cloud import entitlements as ent
import tests.test_cloud_research as cloud_fixture
from tests.test_research_sessions import method

DSN = cloud_fixture.DSN
OK = (200, 201, 202)


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class EntitlementTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BTL_ENTITLEMENT_ENFORCE": "1", "BTL_ENTITLEMENT_RESET_TIMEZONE": "UTC"})
        self.env.start()
        self.fixture = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
        cloud_fixture.CloudResearchTests.setUpClass()
        self.fixture.setUp(start_workers=True)
        f = self.fixture
        record = method()
        self.assertIn(f.client.post(f.root + "/methods", headers=f.headers, json=record).status_code, OK)
        self.mid = record["id"]
        self.ent = ent.Entitlements(DSN)

    def tearDown(self):
        self.fixture.tearDown()
        self.fixture.client.close()
        self.env.stop()

    def body(self, period="2020-01", name="s"):
        return dict(id="session:" + uuid.uuid4().hex, name=name, methodId=self.mid, initialBalance="10000", startPeriod=period)

    def post(self, body, headers=None, root=None, extra=None):
        f = self.fixture
        return f.client.post((root or f.root) + "/sessions", headers={**(headers or f.headers), **(extra or {})}, json=body)

    def status(self):
        r = self.fixture.client.get(self.fixture.root + "/entitlements", headers=self.fixture.headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def backdate(self, kind, period):
        with connect(DSN) as db:
            db.execute("UPDATE btl.entitlement_claims SET period=%s||substr(claim_key,1,6) WHERE actor_id=%s AND kind=%s", (period, self.fixture.actor, kind))

    def claims(self):
        with connect(DSN) as db:
            return db.execute("SELECT kind,status FROM btl.entitlement_claims WHERE actor_id=%s ORDER BY kind,period", (self.fixture.actor,)).fetchall()

    # -------------------------------------------------------------------------------------------------------------------
    def test_success_uses_one_token_a_second_session_is_refused_with_the_exact_reset(self):
        f = self.fixture
        first = self.body()
        created = self.post(first)
        f.completed_job_result(created)
        status = self.status()
        self.assertEqual((status["tier"], status["sessions"]["used"], status["windows"]["used"]), ("FREE", 1, 1))
        self.assertEqual(sorted(self.claims()), [("SESSION", "COMMITTED"), ("WINDOW", "COMMITTED")])
        refused = self.post(self.body())
        self.assertEqual(refused.status_code, 409, refused.text)
        out = refused.json()
        self.assertEqual((out["detail"], out["quota"], out["resetTimezone"]), ("SESSION_MONTH_LIMIT", "SESSION", "UTC"))
        now = datetime.now(timezone.utc)
        want = datetime(now.year + (now.month == 12), now.month % 12 + 1, 1, tzinfo=timezone.utc)
        self.assertEqual(datetime.fromisoformat(out["resetsAt"]), want)

    def test_retry_after_commit_returns_the_same_result_and_no_second_token(self):
        f = self.fixture
        body = self.body()
        job = str(uuid.uuid4())
        view = f.completed_job_result(self.post(body, extra={"X-BTL-Job": job}))
        again = self.post(body, extra={"X-BTL-Job": job})                      # lost response: the client asks again with the same ids
        self.assertIn(again.status_code, OK, again.text)
        self.assertEqual(f.completed_job_result(again)["metadata"]["id"], view["metadata"]["id"])
        self.assertEqual(self.status()["sessions"]["used"], 1)
        self.assertEqual(len([c for c in self.claims() if c[1] == "COMMITTED"]), 2)

    def test_failure_before_commit_gives_the_token_back(self):
        f = self.fixture
        # (a) refused by validation before the queue: the route releases
        bad = self.body(); bad["initialBalance"] = "not-a-number"
        r = self.post(bad)
        deadline = time.monotonic() + 20
        while self.status()["sessions"]["used"] and time.monotonic() < deadline:          # the worker refuses it asynchronously; the job ends FAILED/RECONCILE_REQUIRED
            time.sleep(0.5)
        self.assertEqual(self.status()["sessions"]["used"], 0, "a failed creation must not consume the monthly token")
        self.assertTrue(all(c[1] == "RELEASED" for c in self.claims()))
        # (b) admitted but the worker never produced the Session: stale RESERVED with no live job is released by settlement
        keys = self.ent.reserve(f.actor, f.workspace, self.body("2020-01"))
        self.assertEqual(self.status()["sessions"]["used"], 1)
        with connect(DSN) as db:
            db.execute("UPDATE btl.entitlement_claims SET reserved_at = clock_timestamp() - interval '10 minutes' WHERE actor_id=%s AND status='RESERVED'", (f.actor,))
        self.assertEqual(self.status()["sessions"]["used"], 0)
        # (c) the day is genuinely available again
        f.completed_job_result(self.post(self.body()))
        self.assertEqual(self.status()["sessions"]["used"], 1)
        self.assertIsNotNone(keys)

    def test_a_live_job_is_never_released_by_age(self):
        f = self.fixture
        job = uuid.uuid4()
        with connect(DSN) as db:
            db.execute("INSERT INTO btl.research_jobs(id,actor_id,workspace_id,operation,input,input_hash,state) VALUES (%s,%s,%s,'workspace',%s,%s,'QUEUED')",
                       (job, f.actor, f.workspace, b"{}", "0" * 64))
        self.ent.reserve(f.actor, f.workspace, self.body(), job)
        with connect(DSN) as db:
            db.execute("UPDATE btl.entitlement_claims SET reserved_at = clock_timestamp() - interval '10 minutes' WHERE actor_id=%s", (f.actor,))
        self.assertEqual(self.status()["sessions"]["used"], 1, "QUEUED job still owns the reservation")
        with connect(DSN) as db:
            db.execute("UPDATE btl.research_jobs SET state='FAILED', finished_at=clock_timestamp() WHERE id=%s", (job,))
        self.assertEqual(self.status()["sessions"]["used"], 0, "a failed job releases immediately")

    def test_parallel_requests_cannot_activate_twice(self):
        f = self.fixture
        results = []
        def go():
            try:
                self.ent.reserve(f.actor, f.workspace, self.body())
                results.append("ok")
            except ent.QuotaRefused as refused:
                results.append(refused.code)
        threads = [threading.Thread(target=go) for _ in range(6)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(results.count("ok"), 1, results)
        self.assertEqual(len([c for c in self.claims() if c[1] == "RESERVED"]), 2)

    def test_window_quota_is_one_new_month_per_utc_day_and_reuse_is_free(self):
        f = self.fixture
        f.completed_job_result(self.post(self.body("2020-01")))
        self.backdate("SESSION", "2000-01")                                       # the monthly Session token is a separate quota
        other_month = self.post(self.body("2020-02"))
        self.assertEqual((other_month.status_code, other_month.json()["detail"], other_month.json()["quota"]), (409, "WINDOW_DAY_LIMIT", "WINDOW"))
        again = self.post(self.body("2020-01"))                                  # the already activated month: no new window token
        self.assertIn(again.status_code, OK, again.text)
        f.completed_job_result(again)
        self.assertEqual(self.status()["windows"]["used"], 1)
        self.backdate("WINDOW", "2000-01-01"); self.backdate("SESSION", "2000-02")   # the UTC day and month turned over
        self.assertEqual(self.status()["windows"]["used"], 0)
        self.assertIn(self.post(self.body("2020-01", "again")).status_code, OK)

    def test_free_cannot_forge_pro_and_a_paid_order_is_the_only_source(self):
        f = self.fixture
        f.completed_job_result(self.post(self.body()))
        for extra in ({"X-BTL-Tier": "PRO"}, {"X-Plan": "pro"}, {"Cookie": "tier=PRO"}):
            self.assertEqual(self.post(self.body(), extra=extra).status_code, 409)
        forged = self.body(); forged["tier"] = "PRO"
        self.assertNotIn(self.post(forged).status_code, OK)
        self.assertEqual(self.status()["tier"], "FREE")
        now = int(time.time())
        with connect(DSN) as db:
            db.execute("INSERT INTO btl.sandbox_billing_orders(order_id,actor_id,request_id,merchant_id,plan_version,amount_idr,duration_seconds,phase,transaction_id,paid_at,expires_at,revision) "
                       "VALUES (%s,%s,%s,'m','p',1000,2592000,'PAID',%s,%s,%s,1)", ("btl-sbx-" + uuid.uuid4().hex, f.actor, uuid.uuid4(), "t" + uuid.uuid4().hex, now - 10, now - 10 + 2592000))
        self.assertEqual(self.status()["tier"], "PRO")
        self.assertIsNone(self.status()["sessions"]["limit"])
        f.completed_job_result(self.post(self.body("2020-01", "pro-two")))
        # a refund/chargeback removes Pro at once; evidence of the earlier Sessions is untouched, only new admission is limited again
        with connect(DSN) as db:
            db.execute("UPDATE btl.sandbox_billing_orders SET phase='REVERSED', revision=revision+1 WHERE actor_id=%s", (f.actor,))
        self.assertEqual(self.status()["tier"], "FREE")
        self.assertEqual(self.post(self.body()).status_code, 409)
        with connect(DSN) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM btl.tick_sessions WHERE workspace_id=%s", (f.workspace,)).fetchone()[0], 2)

    def test_expiry_removes_pro_and_tenants_do_not_share_quotas(self):
        f = self.fixture
        now = int(time.time())
        with connect(DSN) as db:
            db.execute("INSERT INTO btl.sandbox_billing_orders(order_id,actor_id,request_id,merchant_id,plan_version,amount_idr,duration_seconds,phase,transaction_id,paid_at,expires_at,revision) "
                       "VALUES (%s,%s,%s,'m','p',1000,100,'PAID',%s,%s,%s,1)", ("btl-sbx-" + uuid.uuid4().hex, f.actor, uuid.uuid4(), "t" + uuid.uuid4().hex, now - 200, now - 100))
        self.assertEqual(self.status()["tier"], "FREE", "an expired order is not Pro")
        f.completed_job_result(self.post(self.body()))
        actor2, headers2 = f.account()
        ws2 = f.client.post("/api/v1/workspaces", headers=headers2, json={"name": "Other"}).json()["id"]
        root2 = "/api/v1/workspaces/" + ws2 + "/research"
        record = method(); f.client.post(root2 + "/methods", headers=headers2, json=record)
        body2 = dict(id="session:" + uuid.uuid4().hex, name="o", methodId=record["id"], initialBalance="10000", startPeriod="2020-01")
        f.completed_job_result(f.client.post(root2 + "/sessions", headers=headers2, json=body2), root=root2, headers=headers2)
        # a foreign workspace cannot be reserved against, and leaves no claim behind
        before = len(self.claims())
        foreign = f.client.post(root2 + "/sessions", headers=f.headers, json=self.body())
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(len(self.claims()), before)

    def test_commercial_and_staging_profiles_fail_closed(self):
        for profile in ("commercial", "staging"):
            with patch.dict(os.environ, {"BTL_PRODUCT_PROFILE": profile, "BTL_ENTITLEMENT_ENFORCE": "0"}):
                with self.assertRaises(ContractError):
                    ent.from_environment(DSN)
            with patch.dict(os.environ, {"BTL_PRODUCT_PROFILE": profile, "BTL_ENTITLEMENT_ENFORCE": "1", "BTL_ENTITLEMENT_RESET_TIMEZONE": "Asia/Jakarta"}):
                with self.assertRaises(ContractError):
                    ent.from_environment(DSN)
            with patch.dict(os.environ, {"BTL_PRODUCT_PROFILE": profile, "BTL_ENTITLEMENT_ENFORCE": "1"}):
                self.assertIsNotNone(ent.from_environment(DSN))
        with patch.dict(os.environ, {"BTL_PRODUCT_PROFILE": "development", "BTL_ENTITLEMENT_ENFORCE": "0"}):
            self.assertIsNone(ent.from_environment(DSN))
        with patch.dict(os.environ, {"BTL_PRODUCT_PROFILE": "typo"}):
            with self.assertRaises(ContractError):
                ent.from_environment(DSN)


if __name__ == "__main__":
    unittest.main()
