"""Free window boundary against the real reducer: no force-close, no new exposure after the boundary, continuation only through Jump/CLOSE/CANCEL."""
import os
import time
import unittest
import uuid
from unittest.mock import patch

from application.models import TrustedScope
from execution.research import ResearchApplication
from execution.research_fixture import STEP_NS
from infrastructure.database import connect
import tests.test_cloud_research as cloud_fixture
from tests.test_research_sessions import method, review_request

DSN = cloud_fixture.DSN


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class WindowGuardTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BTL_ENTITLEMENT_ENFORCE": "1", "BTL_ENTITLEMENT_RESET_TIMEZONE": "UTC"})
        self.env.start()
        self.f = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
        cloud_fixture.CloudResearchTests.setUpClass()
        self.f.setUp(start_workers=True)
        f = self.f
        record = method()
        self.assertEqual(f.client.post(f.root + "/methods", headers=f.headers, json=record).status_code, 200)
        self.sid = "session:" + uuid.uuid4().hex
        created = f.client.post(f.root + "/sessions", headers=f.headers, json=dict(id=self.sid, name="Window", methodId=record["id"], initialBalance="10000", startPeriod="2020-01"))
        self.view = f.completed_job_result(created)
        self.app = ResearchApplication(DSN, TrustedScope(f.workspace, f.actor))

    def tearDown(self):
        self.app.close()
        self.f.tearDown(); self.f.client.close(); self.env.stop()

    def state(self):
        return self.app.inspect(self.sid)["state"]

    def set_end(self, end_ns):
        with connect(DSN) as db:
            db.execute("UPDATE btl.entitlement_claims SET window_end_ns=%s WHERE workspace_id=%s AND session_id=%s AND kind='SESSION'", (end_ns, self.f.workspace, self.sid))

    def advance_to(self, target):
        for _ in range(512):
            state = self.state()
            if int(state["throughNs"]) >= target or state["ended"]:
                return state
            self.app.apply(self.sid, {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": self.sid, "commandId": "w-adv:" + uuid.uuid4().hex,
                                      "expectedRevision": state["revision"], "kind": "ADVANCE", "payload": {"targetNs": str(int(state["throughNs"]) + STEP_NS)}})
        self.fail("could not reach target")

    def open_market(self):
        f = self.f
        view = self.app.inspect(self.sid)
        request = review_request(view)
        reviewed = f.client.post(f.root + "/reviews", headers=f.headers, json=request)
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        return f.client.post(f.root + "/sessions/" + self.sid + "/confirm", headers=f.headers, json={"reviewId": request["requestId"], "reviewHash": reviewed.json()["reviewHash"]})

    def command(self, kind, payload):
        state = self.state()
        return self.f.client.post(self.f.root + "/sessions/" + self.sid + "/commands", headers=self.f.headers,
            json={"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": self.sid, "commandId": "w-cmd:" + uuid.uuid4().hex,
                  "expectedRevision": state["revision"], "kind": kind, "payload": payload})

    def jump(self):
        state = self.state()
        return self.f.client.post(self.f.root + "/sessions/" + self.sid + "/jump-next-event", headers=self.f.headers,
            json={"schemaVersion": 1, "artifact": "BTL-JUMP-NEXT-EVENT-1", "requestId": uuid.uuid4().hex, "sessionId": self.sid, "expectedRevision": state["revision"], "timeframe": "1m"})

    def test_open_position_survives_the_boundary_without_force_close_or_new_exposure(self):
        f = self.f
        start = int(self.state()["throughNs"])
        end = start + 4 * STEP_NS
        self.set_end(end)
        filled = self.open_market()
        self.assertEqual(filled.status_code, 200, filled.text)                       # OPEN inside the window is fine
        self.advance_to(start + 2 * STEP_NS)
        self.assertEqual(sum(o["status"] == "ACTIVE" for o in self.state()["orders"].values()), 1)
        # before the boundary a step may not cross it, and the refusal says where it can go
        crossing = self.command("ADVANCE", {"targetNs": str(end + STEP_NS)})
        self.assertEqual(crossing.status_code, 409, crossing.text)
        self.assertEqual((crossing.json()["detail"], crossing.json()["maxTargetNs"]), ("WINDOW_BOUNDARY", str(end)))
        # reach the boundary with the position still open: nothing is closed, priced or reset
        before_balance = self.state()["balance"]
        state = self.advance_to(end)
        self.assertEqual(state["balance"], before_balance, "the boundary must not realise anything")
        self.assertEqual(sum(o["status"] == "ACTIVE" for o in state["orders"].values()), 1, "no force-close at the boundary")
        # after the boundary: no new trade, no free stepping into the next month
        refused_open = self.open_market()
        self.assertEqual((refused_open.status_code, refused_open.json()["detail"]), (409, "WINDOW_ENDED"))
        step = self.command("ADVANCE", {"targetNs": str(end + STEP_NS)})
        self.assertEqual((step.status_code, step.json()["detail"]), (409, "WINDOW_ENDED_CONTINUATION_ONLY"))
        # continuation: Jump to Next Event is allowed with an ACTIVE position; CLOSE stays allowed
        closed = self.command("CLOSE", {"orderId": next(iter(self.state()["orders"])), "quantity": None})
        self.assertNotEqual(closed.status_code, 409, closed.text)                    # the close intent is accepted after the boundary...
        resolved = self.jump()                                                      # ...and settles at the next committed quote through Jump (ADVANCE stays refused)
        self.assertIn(resolved.status_code, (200, 202), resolved.text)
        f.completed_job_result(resolved)
        self.assertEqual(sum(o["status"] == "ACTIVE" for o in self.state()["orders"].values()), 0)
        done = self.jump()
        self.assertEqual((done.status_code, done.json()["detail"]), (409, "WINDOW_COMPLETED"))
        # Free -> Pro with the window already over: Pro is not limited by the Free window
        now = int(time.time())
        with connect(DSN) as db:
            db.execute("INSERT INTO btl.sandbox_billing_orders(order_id,actor_id,request_id,merchant_id,plan_version,amount_idr,duration_seconds,phase,transaction_id,paid_at,expires_at,revision) "
                       "VALUES (%s,%s,%s,'m','p',1000,2592000,'PAID',%s,%s,%s,1)", ("btl-sbx-" + uuid.uuid4().hex, f.actor, uuid.uuid4(), "t" + uuid.uuid4().hex, now - 10, now - 10 + 2592000))
        self.assertNotEqual(self.command("ADVANCE", {"targetNs": str(end + STEP_NS)}).status_code, 409)

    def test_a_session_without_a_claim_or_a_pro_account_is_not_limited(self):
        with connect(DSN) as db:
            db.execute("DELETE FROM btl.entitlement_claims WHERE workspace_id=%s AND session_id=%s", (self.f.workspace, self.sid))
        start = int(self.state()["throughNs"])
        self.assertNotEqual(self.command("ADVANCE", {"targetNs": str(start + STEP_NS)}).status_code, 409)

    def test_cancel_close_and_end_are_never_blocked_by_the_window(self):
        from cloud import window_guard
        from cloud.entitlements import Entitlements
        start = int(self.state()["throughNs"])
        self.set_end(start + STEP_NS)
        self.advance_to(start + 2 * STEP_NS)
        for kind in ("CANCEL", "CLOSE", "END"):
            self.assertIsNone(window_guard.check(Entitlements(DSN), DSN, self.f.actor, self.f.workspace, self.sid, kind))


class WindowGuardRuleTable(unittest.TestCase):
    """Every rule branch with a stubbed ledger view (the real reducer path is exercised above)."""
    END = 10**15

    def run_check(self, kind, *, through, active=0, pending=0, tier="FREE", target=None, window=True):
        from cloud import window_guard
        class Stub:
            def session_window(_self, ws, sid):
                return dict(startNs=0, endNs=self.END, tier=tier) if window else None
        with patch.object(window_guard, "live_orders", return_value=dict(throughNs=through, active=active, pending=pending, ended=False)):
            try:
                window_guard.check(Stub(), "dsn", "a", "w", "s", kind, target)
                return None
            except window_guard.WindowRefused as refused:
                return refused.code

    def test_rules(self):
        R = self.run_check
        self.assertIsNone(R("OPEN", through=10))
        self.assertEqual(R("OPEN", through=self.END), "WINDOW_ENDED")
        self.assertIsNone(R("ADVANCE", through=10, target=self.END))
        self.assertEqual(R("ADVANCE", through=10, target=self.END + 1), "WINDOW_BOUNDARY")
        self.assertEqual(R("ADVANCE", through=self.END, target=self.END + 1), "WINDOW_ENDED_CONTINUATION_ONLY")
        self.assertEqual(R("JUMP", through=self.END, pending=1, active=1), "PENDING_AT_WINDOW_END")
        self.assertEqual(R("JUMP", through=self.END), "WINDOW_COMPLETED")
        self.assertIsNone(R("JUMP", through=self.END, active=2))
        self.assertIsNone(R("JUMP", through=10, pending=1))                     # far from the boundary: ordinary Jump
        for kind in ("CANCEL", "CLOSE", "END"):
            self.assertIsNone(R(kind, through=self.END + 5000, pending=3))
        self.assertIsNone(R("OPEN", through=self.END + 5000, tier="PRO"))
        self.assertIsNone(R("ADVANCE", through=self.END + 5000, tier="PRO", target=self.END + 9999))
        self.assertIsNone(R("OPEN", through=self.END + 5000, window=False))


if __name__ == "__main__":
    unittest.main()
