"""Server-side Free/Pro admission for new Sessions (opt-in BTL_ENTITLEMENT_ENFORCE=1): one Free window per entitlement day, Pro unlimited, idempotent retry."""
import os
import time
import unittest
import uuid
from unittest.mock import patch

from infrastructure.database import connect
import tests.test_cloud_research as cloud_fixture
from tests.test_research_sessions import method

DSN = cloud_fixture.DSN


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class EntitlementTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BTL_ENTITLEMENT_ENFORCE": "1", "BTL_ENTITLEMENT_RESET_TIMEZONE": "UTC"})
        self.env.start()
        self.fixture = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
        cloud_fixture.CloudResearchTests.setUpClass()
        self.fixture.setUp(start_workers=True)

    def tearDown(self):
        self.fixture.tearDown()
        self.fixture.client.close()
        self.env.stop()

    def create(self, headers, root, method_id, name):
        body = dict(id="session:" + uuid.uuid4().hex, name=name, methodId=method_id, initialBalance="10000", startPeriod="2020-01")
        return body, self.fixture.client.post(root + "/sessions", headers=headers, json=body)

    def method_id(self, headers, root):
        record = method()
        created = self.fixture.client.post(root + "/methods", headers=headers, json=record)
        self.assertIn(created.status_code, (200, 201, 202), created.text)
        return record["id"]

    def test_free_gets_one_window_per_day_and_pro_is_unlimited(self):
        f = self.fixture
        mid = self.method_id(f.headers, f.root)
        first_body, first = self.create(f.headers, f.root, mid, "one")
        self.assertIn(first.status_code, (200, 201, 202), first.text)
        _, second = self.create(f.headers, f.root, mid, "two")
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(second.json()["detail"], "DAILY_WINDOW_LIMIT")
        retry = f.client.post(f.root + "/sessions", headers=f.headers, json=first_body)        # same request: not a second window
        self.assertNotEqual(retry.status_code, 409, retry.text)
        # another account is not affected by this account's day
        actor2, headers2 = f.account()
        root2 = "/api/v1/workspaces/" + f.client.post("/api/v1/workspaces", headers=headers2, json={"name": "Other"}).json()["id"] + "/research"
        mid2 = self.method_id(headers2, root2)
        _, other = self.create(headers2, root2, mid2, "other")
        self.assertIn(other.status_code, (200, 201, 202), other.text)
        # a PAID, unexpired order makes the same account Pro (tier comes from the server-side ledger only)
        now = int(time.time())
        with connect(DSN) as db:
            db.execute("INSERT INTO btl.sandbox_billing_orders(order_id,actor_id,request_id,merchant_id,plan_version,amount_idr,duration_seconds,phase,transaction_id,paid_at,expires_at,revision) "
                       "VALUES (%s,%s,%s,'m','p',1000,2592000,'PAID',%s,%s,%s,1)", ("btl-sbx-" + uuid.uuid4().hex, f.actor, uuid.uuid4(), "t" + uuid.uuid4().hex, now - 10, now - 10 + 2592000))
        _, pro = self.create(f.headers, f.root, mid, "three")
        self.assertIn(pro.status_code, (200, 201, 202), pro.text)
        # a refund/chargeback (order REVERSED) removes Pro immediately: the day's Free window is then already used, so the next new window is refused
        with connect(DSN) as db:
            db.execute("UPDATE btl.sandbox_billing_orders SET phase='REVERSED', revision=revision+1 WHERE actor_id=%s", (f.actor,))
        _, after_refund = self.create(f.headers, f.root, mid, "four")
        self.assertEqual((after_refund.status_code, after_refund.json()["detail"]), (409, "DAILY_WINDOW_LIMIT"))

    def test_the_gate_is_off_without_the_opt_in_flag(self):
        f = self.fixture
        with patch.dict(os.environ, {"BTL_ENTITLEMENT_ENFORCE": "0"}):
            self.assertIsNone(__import__("cloud.entitlements", fromlist=["x"]).from_environment(DSN))
        self.assertIsNotNone(f.app.state.entitlements)


if __name__ == "__main__":
    unittest.main()
