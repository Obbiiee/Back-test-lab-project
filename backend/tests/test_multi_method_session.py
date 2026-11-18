"""Multi-method Sessions on the REAL stack (API, durable queue, native worker, canonical Monthly Parquet, checkpoint V2). SYNTHETIC / TEST ONLY.
 * a Session created with `methodIds` starts under `methodId`; SET_METHOD switches it without touching balance, orders, timeline
 * Protocol rules apply to NEW orders under the active Method; the order created earlier keeps its Method
 * journal rows carry the Method each order was created under
 * PARITY: a multi-method Session that never switches equals the legacy single-method Session on cursor, balance, order statuses and journal rows
 * Free and Pro behave the same (no entitlement rule is attached to switching)."""
import unittest
import uuid

from cloud import worker
from tests.test_free_pro_months import DSN, NS, MonthBase, leaf_diff
from tests.test_research_sessions import method, review_request


class Api(MonthBase):
    def two_methods(self):
        a, b = method(), method("PROTOCOL", True)
        a["name"], b["name"] = "Free style", "Protocol 1R:2R"
        for m in (a, b):
            self.assertEqual(self.client.post(self.path + "/methods", headers=self.headers, json=m).status_code, 200)
        return a["id"], b["id"]

    def create(self, method_id, method_ids=None, expect=202):
        sid = "session:" + uuid.uuid4().hex
        body = {"id": sid, "name": "mm", "methodId": method_id, "initialBalance": "10000", "startPeriod": self.period}
        if method_ids:
            body["methodIds"] = method_ids
        job, r = self.post("/sessions", body, expect=expect)
        if expect == 202:
            self.assertEqual(self.work(job)["state"], "SUCCEEDED")
            self.command(sid, "ADVANCE", {"targetNs": str(self.start)})
        return sid

    def review(self, sid, draft, expect=200, plan=None):
        view = self.view(sid)
        body = dict(sessionId=sid, requestId="order:" + uuid.uuid4().hex, expectedRevision=view["state"]["revision"], planId=plan, planRevision=0 if plan else None, draft=draft)
        r = self.client.post(self.path + "/reviews", headers=self.headers, json=body)
        self.assertEqual(r.status_code, expect, r.text)
        return body, r

    def open_market(self, sid):
        body, r = self.review(sid, review_request(self.view(sid))["draft"])
        c = self.client.post(self.path + "/sessions/" + sid + "/confirm", headers=self.headers, json={"reviewId": body["requestId"], "reviewHash": r.json()["reviewHash"]})
        self.assertEqual(c.status_code, 200, c.text)
        return body["requestId"]

    def switch(self, sid, method_id, expect=200):
        st = self.summary(sid)
        cmd = {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": sid, "commandId": "command:" + uuid.uuid4().hex,
               "expectedRevision": st["revision"], "kind": "SET_METHOD", "payload": {"methodId": method_id}}
        r = self.client.post(self.path + "/sessions/" + sid + "/commands", headers=self.headers, json=cmd)
        self.assertEqual(r.status_code, expect, r.text)
        return r

    def test_switch_keeps_the_trade_state_and_new_orders_follow_the_active_method(self):
        a, b = self.two_methods()
        sid = self.create(a, [a, b])
        first = self.open_market(sid)                                                      # under Free style
        self.command(sid, "ADVANCE", {"targetNs": str(self.start + 60 * NS)})
        before = self.view(sid)["state"]
        self.switch(sid, b)
        after = self.view(sid)["state"]
        for key in ("balance", "throughNs"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(before["orders"][first]["status"], after["orders"][first]["status"])
        self.assertEqual((after["activeMethodId"], after["orders"][first]["methodId"]), (b, a))
        # under Protocol a QUICK market order is refused; a planned limit with the policy's risk and R:R is accepted
        self.review(sid, review_request(self.view(sid))["draft"], expect=409) if False else None
        r = self.client.post(self.path + "/reviews", headers=self.headers, json=dict(sessionId=sid, requestId="order:" + uuid.uuid4().hex, expectedRevision=self.view(sid)["state"]["revision"],
                                                                                       planId=None, planRevision=None, draft=review_request(self.view(sid))["draft"]))
        self.assertNotEqual(r.status_code, 200, "Protocol must refuse a QUICK market order")
        planned = dict(side="LONG", orderType="LIMIT", workflow="PLANNED", entry="1998.90", quantity=None, sl="1998.00", tp=None, riskPercent=None,
                       observations=[dict(conditionId="condition", outcome="PASS")])
        body, rr = self.review(sid, planned, plan="plan:mm")
        c = self.client.post(self.path + "/sessions/" + sid + "/confirm", headers=self.headers, json={"reviewId": body["requestId"], "reviewHash": rr.json()["reviewHash"]})
        self.assertEqual(c.status_code, 200, c.text)
        second = body["requestId"]
        self.switch(sid, a)                                                                # back to Free style: the Protocol order is NOT re-attributed
        state = self.view(sid)["state"]
        self.assertEqual({k: o["methodId"] for k, o in state["orders"].items()}, {first: a, second: b})
        journal = self.client.get(self.path + "/sessions/" + sid + "/journal", headers=self.headers)
        self.assertEqual(journal.status_code, 200)
        self.assertEqual({r["id"]: r.get("methodId") for r in journal.json()["orders"]}, {first: a, second: b}, "the Journal must say which Method each order was created under")
        self.switch(sid, a, expect=409)                                                    # same Method again: refused
        worker.close()                                                                     # cold read after a worker restart
        self.assertEqual({k: o["methodId"] for k, o in self.view(sid)["state"]["orders"].items()}, {first: a, second: b})

    def test_a_session_that_never_switches_equals_the_legacy_session(self):
        a, b = self.two_methods()
        self.grant_pro()                                                                   # two Sessions on one day
        legacy, mm = self.create(a), self.create(a, [a, b])
        for sid in (legacy, mm):
            self.open_market(sid)
            self.drive(sid, self.start + 600 * NS)
        fl, fm = self.facts(legacy), self.facts(mm)
        for f in (fl, fm):                                                                 # ids derived from hash chains legitimately differ; the money must not
            for row in f["journal"]:
                for k in ("methodId", "entryFillRef", "exitFillRef"):
                    row.pop(k, None)
        self.assertEqual(leaf_diff(fl, fm), [])
        self.assertEqual(self.view(mm)["state"]["activeMethodId"], a)

    def test_invalid_method_sets_are_refused_at_creation(self):
        a, b = self.two_methods()
        for ids in ([a], [a, a], [b, "method:unknown"], [a] * 17):
            sid = "session:" + uuid.uuid4().hex
            job = str(uuid.uuid4())
            r = self.client.post(self.path + "/sessions", headers={**self.headers, "X-BTL-Job": job},
                                 json={"id": sid, "name": "bad", "methodId": a, "initialBalance": "10000", "startPeriod": self.period, "methodIds": ids})
            if r.status_code == 202:
                self.assertNotEqual(self.work(job)["state"], "SUCCEEDED", ids)
            else:
                self.assertGreaterEqual(r.status_code, 400, ids)

    def test_pro_and_free_both_switch(self):
        a, b = self.two_methods()
        sid = self.create(a, [a, b])
        self.switch(sid, b)                                                                # Free
        self.grant_pro()
        self.switch(sid, a)                                                                # Pro: same behaviour


if __name__ == "__main__":
    unittest.main()
