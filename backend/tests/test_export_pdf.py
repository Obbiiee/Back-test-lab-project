"""PDF report of a Session: real file, real committed numbers, no markup injection, tenant isolation."""
import io
import unittest
import uuid

from application.models import TrustedScope
from execution.research import ResearchApplication
from execution.research_fixture import STEP_NS
import tests.test_cloud_research as cloud_fixture
from tests.test_research_sessions import method, review_request

DSN = cloud_fixture.DSN
try:
    from pypdf import PdfReader
except ImportError:                      # verification-only dependency; the product depends on reportlab only
    PdfReader = None


def pdf_text(data):
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


@unittest.skipUnless(DSN and PdfReader, 'Real isolated PostgreSQL and pypdf (verification only) required; skip is not PASS')
class PdfRoute(unittest.TestCase):
    def setUp(self):
        self.f = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
        self.f.setUp(start_workers=True)
        f = self.f
        self.record = method()
        self.assertEqual(f.client.post(f.root + "/methods", headers=f.headers, json=self.record).status_code, 200)
        self.sid = "session:" + uuid.uuid4().hex
        self.name = "Weird <b>name</b> (with) =cmd & 'quotes'"
        f.completed_job_result(f.client.post(f.root + "/sessions", headers=f.headers, json=dict(id=self.sid, name=self.name, methodId=self.record["id"], initialBalance="10000", startPeriod="2020-01")))
        self.app = ResearchApplication(DSN, TrustedScope(f.workspace, f.actor))

    def tearDown(self):
        self.app.close(); self.f.tearDown(); self.f.client.close()

    def advance(self, steps):
        target = int(self.app.inspect(self.sid)["state"]["throughNs"]) + steps * STEP_NS
        for _ in range(512):
            state = self.app.inspect(self.sid)["state"]
            if int(state["throughNs"]) >= target:
                return
            self.app.apply(self.sid, {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": self.sid, "commandId": "p-adv:" + uuid.uuid4().hex,
                                      "expectedRevision": state["revision"], "kind": "ADVANCE", "payload": {"targetNs": str(int(state["throughNs"]) + STEP_NS)}})

    def trade(self):
        f = self.f
        view = self.app.inspect(self.sid)
        req = review_request(view)
        rv = f.client.post(f.root + "/reviews", headers=f.headers, json=req).json()
        self.assertEqual(f.client.post(f.root + "/sessions/" + self.sid + "/confirm", headers=f.headers, json={"reviewId": req["requestId"], "reviewHash": rv["reviewHash"]}).status_code, 200)
        self.advance(1)
        state = self.app.inspect(self.sid)["state"]
        self.app.apply(self.sid, {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": self.sid, "commandId": "p-close:" + uuid.uuid4().hex,
                                  "expectedRevision": state["revision"], "kind": "CLOSE", "payload": {"orderId": next(iter(state["orders"])), "quantity": None}})
        self.advance(1)

    def get(self, headers=None, root=None, sid=None):
        f = self.f
        return f.client.get((root or f.root) + "/sessions/" + (sid or self.sid) + "/export?format=pdf", headers=headers or f.headers)

    def test_report_contains_the_committed_numbers_and_nothing_invented(self):
        empty = self.get()
        self.assertEqual(empty.status_code, 200, empty.text[:200])
        self.assertTrue(empty.content.startswith(b"%PDF") and empty.headers["content-type"] == "application/pdf")
        text0 = pdf_text(empty.content)
        self.assertIn("RIKSORA", text0)
        self.assertIn("Not available", text0, "metrics the ledger cannot supply must say so")
        self.trade()
        response = self.get()
        self.assertEqual(response.status_code, 200)
        text = pdf_text(response.content)
        summary = self.app.summary(self.sid)
        for needle in ("RIKSORA", "Backtest report", "Starting balance", "10000", "Ending realized balance", str(summary["balance"]), "Total trades",
                       "Win rate", "Profit factor", "Expectancy", "Average R", "Maximum drawdown", "Realized balance curve", "Report generated", "Not live or broker fills"):
            self.assertIn(needle, text, needle)
        self.assertIn("Weird <b>name</b>", text, "names are drawn literally, never parsed as markup")
        journal = self.f.client.get(self.f.root + "/sessions/" + self.sid + "/journal", headers=self.f.headers).json()
        order = journal["orders"][0]
        self.assertIn(str(order["entryPrice"]), text)
        self.assertIn(str(order["net"]), text)
        self.assertIn("0.0000 (0/1)", text, "win rate and profit factor of the single losing trade, exact fraction shown")
        self.assertIn("-1.5000 (-3/2)", text, "expectancy")
        self.assertNotIn("numerator", text, "no raw object may leak into the report")
        self.assertIn("1.5", text.split("Maximum drawdown")[1][:12])
        self.assertLess(len(response.content), 200_000)

    def test_unauthenticated_and_foreign_requests_get_no_report(self):
        f = self.f
        self.assertEqual(f.client.get(f.root + "/sessions/" + self.sid + "/export?format=pdf").status_code, 401)
        _, other = f.account()
        ws2 = f.client.post("/api/v1/workspaces", headers=other, json={"name": "Other"}).json()["id"]
        root2 = "/api/v1/workspaces/" + ws2 + "/research"
        self.assertEqual(self.get(other, f.root).status_code, 404)
        self.assertEqual(self.get(other, root2).status_code, 404)


if __name__ == "__main__":
    unittest.main()
