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

    def test_switch_is_refused_and_the_session_keeps_its_method(self):
        # owner decision 2026-11-18: no method change inside a Session; a different method is a new Session
        a, b = self.two_methods()
        sid = self.create(a, [a, b])
        first = self.open_market(sid)
        self.command(sid, "ADVANCE", {"targetNs": str(self.start + 60 * NS)})
        before = self.view(sid)["state"]
        r = self.switch(sid, b, expect=409)
        self.assertEqual(r.json()["detail"], "METHOD_CHANGE_REQUIRES_NEW_SESSION")
        after = self.view(sid)["state"]
        self.assertEqual((before["balance"], before["throughNs"], before["activeMethodId"]), (after["balance"], after["throughNs"], a))
        self.assertEqual(after["orders"][first]["status"], before["orders"][first]["status"])

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

    def test_pro_and_free_both_refuse_a_method_switch(self):
        a, b = self.two_methods()
        sid = self.create(a, [a, b])
        self.switch(sid, b, expect=409)                                                    # Free
        self.grant_pro()
        self.switch(sid, b, expect=409)                                                    # Pro: the same rule
        self.assertEqual(self.view(sid)["state"]["activeMethodId"], a)


if __name__ == "__main__":
    unittest.main()
