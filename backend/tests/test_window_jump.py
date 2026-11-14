"""Free window x Jump orchestration against the real reducer: a PENDING order never fills outside the activated month, active positions keep their lifecycle,
and every outcome equals a chronological replay under the same entitlement. The reducer is untouched; only the upper bound of the ordinary ADVANCE is lowered."""
import time
import unittest
import uuid

from application.models import TrustedScope
from execution.research import ResearchApplication
from execution.research_fixture import STEP_NS
from infrastructure.database import connect
import tests.test_cloud_research as cloud_fixture
from tests.test_research_sessions import method, review_request

DSN = cloud_fixture.DSN
# Fixture price path (authored): bid = 2000 + 0.05*phase for phase 0..120, then falling 0.05 per step; ask = bid + 0.10; one tick per 15 s step; Sessions start at step 120.
START_STEP = 120


def command(sid, state, kind, payload, tag="w"):
    return {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": sid, "commandId": f"{tag}:" + uuid.uuid4().hex,
            "expectedRevision": state["revision"], "kind": kind, "payload": payload}


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class WindowJumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cloud_fixture.CloudResearchTests.setUpClass()

    def setUp(self):
        self.f = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
        self.f.setUp(start_workers=False)
        self.app = ResearchApplication(DSN, TrustedScope(self.f.workspace, self.f.actor))
        self.free = method("FREE_STYLE")
        self.proto = method("PROTOCOL")
        for m in (self.free, self.proto):
            self.app.create_method(m)

    def tearDown(self):
        self.app.close(); self.f.client.close()

    # -------------------------------------------------------------------------------------------------------------
    def session(self, m, *, end_steps=None):
        """A Session; with end_steps it is a Free-window Session whose window ends end_steps after its start (via a real claim row), otherwise a control."""
        sid = "session:" + uuid.uuid4().hex
        self.app.create_session(dict(id=sid, name="wj", methodId=m["id"], initialBalance="10000", startPeriod="2020-01"))
        if end_steps is not None:
            start = int(self.state(sid)["throughNs"])
            with connect(DSN) as db:
                db.execute("INSERT INTO btl.entitlement_claims(actor_id,kind,claim_key,period,tier,status,workspace_id,session_id,window_start_ns,window_end_ns) "
                           "VALUES (%s,'SESSION',%s,%s,'FREE','COMMITTED',%s,%s,%s,%s)",
                           (self.f.actor, uuid.uuid4().hex + "0" * 32, "2020-01-" + uuid.uuid4().hex[:6], self.f.workspace, sid, start, start + end_steps * STEP_NS))
        return sid

    def state(self, sid):
        return self.app.inspect(sid)["state"]

    def go_pro(self):
        now = int(time.time())
        with connect(DSN) as db:
            db.execute("INSERT INTO btl.sandbox_billing_orders(order_id,actor_id,request_id,merchant_id,plan_version,amount_idr,duration_seconds,phase,transaction_id,paid_at,expires_at,revision) "
                       "VALUES (%s,%s,%s,'m','p',1000,2592000,'PAID',%s,%s,%s,1)", ("btl-sbx-" + uuid.uuid4().hex, self.f.actor, uuid.uuid4(), "t" + uuid.uuid4().hex, now - 10, now - 10 + 2592000))

    def open_order(self, sid, draft, plan=None):
        view = self.app.inspect(sid)
        request = review_request(view)
        request["draft"].update(draft)
        if plan or request["draft"]["workflow"] == "PLANNED":
            request["planId"], request["planRevision"] = plan or "plan:wj", 0
        reviewed = self.app.review(request)
        self.app.confirm(sid, dict(reviewId=request["requestId"], reviewHash=reviewed["reviewHash"]))

    def advance_to(self, sid, target):
        """Chronological replay: the canonical ADVANCE one fixture step at a time."""
        for _ in range(1024):
            st = self.state(sid)
            if int(st["throughNs"]) >= target or st["ended"]:
                return st
            self.app.apply(sid, command(sid, st, "ADVANCE", {"targetNs": str(min(target, int(st["throughNs"]) + STEP_NS))}, "adv"))
        self.fail("no progress")

    def jump_until_done(self, sid):
        """Repeat Jump to Next Event until it stops; returns the final status and the number of calls."""
        for calls in range(1, 200):
            st = self.state(sid)
            result = self.app.jump_next_event(sid, {"schemaVersion": 1, "artifact": "BTL-JUMP-NEXT-EVENT-1", "requestId": uuid.uuid4().hex, "sessionId": sid,
                                                   "expectedRevision": st["revision"], "timeframe": "1m"})
            if result["status"] != "SEARCHING":
                return result["status"], calls
        self.fail("jump did not settle")

    def live(self, sid):
        return sorted((o["status"], o["side"]) for o in self.state(sid)["orders"].values() if o["status"] in ("PENDING", "ACTIVE"))

    def ledger(self, sid):
        """Committed financial facts that must match across paths: closed orders (side, entry, exit, net) and the realised balance."""
        page = self.app.journal_page(sid, {"limit": 32, "cursor": None})
        rows = [(o["side"], o["status"], o.get("entryPrice"), o.get("exitPrice"), o.get("net")) for o in page["orders"]]
        return sorted(rows, key=str), self.state(sid)["balance"]

    # -------------------------------------------------------------------------------------------------------------
    def test_protocol_pending_limit_never_fills_after_the_boundary_and_pro_fills_identically_to_a_chronological_replay(self):
        # the planned LIMIT (entry 2005) would fill 22 steps after the start; the Free window ends 10 steps after it
        free, control, pro = (self.session(self.proto, end_steps=10), self.session(self.proto), self.session(self.proto, end_steps=10))
        for sid in (free, control, pro):
            self.open_order(sid, dict(orderType="LIMIT", workflow="PLANNED", entry="2005", sl="2003", quantity=None, riskPercent=None), plan="plan:wj")
            self.assertEqual(self.live(sid), [("PENDING", "LONG")])
        end = int(self.state(free)["throughNs"]) + 10 * STEP_NS
        status, _calls = self.jump_until_done(free)
        st = self.state(free)
        self.assertEqual(status, "NO_EVENT_UNTIL_SESSION_END")
        self.assertLess(int(st["throughNs"]), end, "the cursor never passes the last tick of the window")
        self.assertEqual(self.live(free), [("PENDING", "LONG")], "the pending order did not fill outside the window")
        self.assertEqual(st["balance"], "10000")
        # chronological replay under the same entitlement (to the same cursor) gives the same committed state
        self.advance_to(control, int(st["throughNs"]))
        self.assertEqual((self.state(control)["throughNs"], self.live(control), self.state(control)["balance"]), (st["throughNs"], self.live(free), st["balance"]))
        # cancellation is always allowed and ends the window cleanly
        order_id = next(iter(self.state(free)["orders"]))
        self.app.apply(free, command(free, self.state(free), "CANCEL", {"orderId": order_id}))
        self.assertEqual(self.live(free), [])
        # Pro (billing ledger) is not limited: the same jump fills across the month boundary and equals the chronological replay
        self.go_pro()
        status, _ = self.jump_until_done(pro)
        self.assertEqual(status, "EVENT_FOUND")
        self.assertEqual(self.live(pro), [("ACTIVE", "LONG")])
        self.advance_to(control, int(self.state(pro)["throughNs"]))
        self.assertEqual((self.live(control), self.state(control)["balance"]), (self.live(pro), self.state(pro)["balance"]))

    def test_active_position_keeps_its_lifecycle_and_equals_chronological_replay(self):
        for kind_side, draft in (("sl", dict(side="LONG", entry="2006.10", sl="2005.5", tp="2010")), ("tp", dict(side="SHORT", entry="2006.00", sl="2008", tp="2005.0"))):
            free, control = self.session(self.free, end_steps=5), self.session(self.free)
            for sid in (free, control):
                self.open_order(sid, dict(orderType="MARKET", workflow="PLANNED", quantity="0.1", riskPercent="1", **draft))
                self.advance_to(sid, int(self.state(sid)["throughNs"]) + STEP_NS)      # the market order fills at the next quote
            self.assertEqual(self.live(free), [("ACTIVE", "LONG" if kind_side == "sl" else "SHORT")])
            status, _ = self.jump_until_done(free)                                     # exit lies after the 5-step window: continuation of the already-open lifecycle
            self.assertEqual(status, "EVENT_FOUND", kind_side)
            self.assertEqual(self.live(free), [])
            self.advance_to(control, int(self.state(free)["throughNs"]))
            self.assertEqual(self.ledger(free), self.ledger(control), kind_side)
            self.assertNotEqual(self.state(free)["balance"], "10000", "the exit really realised PnL")

    def test_mixed_active_and_pending_orders_stop_at_the_boundary_then_cancel_and_continue(self):
        free, control = self.session(self.free, end_steps=8), self.session(self.free)
        for sid in (free, control):
            self.open_order(sid, dict(side="LONG", orderType="MARKET", workflow="PLANNED", entry="2006.10", quantity="0.1", riskPercent="1", sl="2004.0", tp="2010"))
            self.advance_to(sid, int(self.state(sid)["throughNs"]) + STEP_NS)
            self.open_order(sid, dict(side="SHORT", orderType="STOP", workflow="PLANNED", entry="2004.5", quantity="0.1", riskPercent="1", sl="2007", tp="2001"))
        self.assertEqual(self.live(free), [("ACTIVE", "LONG"), ("PENDING", "SHORT")])
        status, _ = self.jump_until_done(free)                                         # SELL STOP would trigger ~ step 30 (after the window) and so would the SL
        self.assertEqual(status, "NO_EVENT_UNTIL_SESSION_END")
        self.assertEqual(self.live(free), [("ACTIVE", "LONG"), ("PENDING", "SHORT")], "nothing filled or closed after the window")
        for sid in (free, control):
            self.advance_to(sid, int(self.state(free)["throughNs"]))
            pending = next(oid for oid, o in self.state(sid)["orders"].items() if o["status"] == "PENDING")
            self.app.apply(sid, command(sid, self.state(sid), "CANCEL", {"orderId": pending}))
        status, _ = self.jump_until_done(free)                                         # now only the active position is left: continuation, unbounded
        self.assertEqual(status, "EVENT_FOUND")
        self.advance_to(control, int(self.state(free)["throughNs"]))
        self.assertEqual(self.ledger(free), self.ledger(control))

    def test_a_pending_stop_order_is_bounded_too_and_a_retry_is_idempotent(self):
        free = self.session(self.free, end_steps=10)
        self.open_order(free, dict(side="SHORT", orderType="STOP", workflow="PLANNED", entry="2004.0", quantity="0.1", riskPercent="1", sl="2007", tp="2001"))
        st = self.state(free)
        raw = {"schemaVersion": 1, "artifact": "BTL-JUMP-NEXT-EVENT-1", "requestId": uuid.uuid4().hex, "sessionId": free, "expectedRevision": st["revision"], "timeframe": "1m"}
        first = self.app.jump_next_event(free, raw)
        after_first = self.state(free)
        again = self.app.jump_next_event(free, raw)                                    # the same request again (lost response / worker restart): no second command
        after_again = self.state(free)
        self.assertEqual((after_again["revision"], after_again["throughNs"], after_again["balance"]), (after_first["revision"], after_first["throughNs"], after_first["balance"]))
        self.assertEqual((first["status"], again["status"]), (again["status"], first["status"]))
        self.assertEqual(self.live(free), [("PENDING", "SHORT")])
        self.assertLess(int(after_again["throughNs"]), int(st["throughNs"]) + 10 * STEP_NS)

    def test_an_unreadable_billing_ledger_is_treated_as_free_and_a_session_without_claim_is_unrestricted(self):
        from execution.free_window import free_window_end
        free = self.session(self.free, end_steps=10)
        control = self.session(self.free)
        with connect(DSN) as db:
            self.assertEqual(free_window_end(db, self.f.workspace, free), int(self.state(free)["throughNs"]) + 10 * STEP_NS)
            self.assertIsNone(free_window_end(db, self.f.workspace, control))


if __name__ == "__main__":
    unittest.main()
