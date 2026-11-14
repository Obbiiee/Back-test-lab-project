"""The chart-history route inside the real product app: identity, tenant isolation and a cursor taken from the durable Session (not from the request)."""
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from application.models import TrustedScope
from execution.research import ResearchApplication
from tests.test_chart_history import world
import tests.test_cloud_research as cloud_fixture
from infrastructure.database import migrate
from tests.test_research_sessions import method


DSN = cloud_fixture.DSN


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class ChartRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)
        cls.reader, cls.store_dir, cls.source = world()
        cls.registry = Path(tempfile.mkdtemp(prefix="ch-reg-")) / "registry.json"
        cls.registry.write_text(json.dumps(dict(schemaVersion=1, store=cls.store_dir, basis="BID",
                                                rules=[dict(datasetIdPrefix="synthetic:", instrument="TESTUSD", sourceHashes=[cls.source], tickRoot=None)])))

    def setUp(self):
        self.env = patch.dict(os.environ, {"BTL_CHART_REGISTRY": str(self.registry)})
        self.env.start()
        self.fixture = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
        self.fixture.setUp(start_workers=False)
        f = self.fixture
        app = ResearchApplication(DSN, TrustedScope(f.workspace, f.actor))
        m = method(); app.create_method(m)
        self.session = "session:" + uuid.uuid4().hex
        app.create_session(dict(id=self.session, name="Chart route QA", methodId=m["id"], initialBalance="10000", startPeriod="2020-01"))
        self.summary = app.summary(self.session)
        app.close()
        self.path = f.root + "/sessions/" + self.session + "/chart-bars"

    def tearDown(self):
        self.fixture.client.close()
        self.env.stop()

    def test_capabilities_announce_the_chart_history_so_the_client_never_probes_a_missing_route(self):
        f = self.fixture
        caps = f.client.get("/api/v1/workspaces/" + f.workspace + "/capabilities", headers=f.headers).json()
        self.assertEqual(caps["chartHistory"], {"available": True, "maxCandles": 5000})
        self.assertFalse(caps["entitlement"]["enforced"])
        with patch.dict(os.environ, {"BTL_CHART_REGISTRY": ""}):
            f2 = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
            f2.setUp(start_workers=False)
            try:
                caps2 = f2.client.get("/api/v1/workspaces/" + f2.workspace + "/capabilities", headers=f2.headers).json()
                self.assertEqual(caps2["chartHistory"]["available"], False)
            finally:
                f2.client.close()

    def test_identity_ownership_and_the_cursor_comes_from_the_durable_session(self):
        f = self.fixture
        self.assertEqual(f.client.get(self.path + "?timeframe=1h").status_code, 401, "no bearer token")
        own = f.client.get(self.path + "?timeframe=1h&limit=100", headers=f.headers)
        self.assertEqual(own.status_code, 200, own.text)
        body = own.json()
        self.assertEqual(body["artifact"], "BTL-CHART-HISTORY-PAGE-1")
        self.assertEqual(body["cursorNs"], str(self.summary["throughNs"]), "the cursor is the committed Session cursor")
        self.assertEqual(body["revision"], self.summary["revision"])
        self.assertEqual(own.headers["cache-control"], "no-store")
        self.assertNotIn("ohlc/", own.text)
        # a request cannot move the cursor: unknown query parameters change nothing
        spoof = f.client.get(self.path + "?timeframe=1h&limit=100&cursorNs=9999999999999999999&through=1", headers=f.headers)
        self.assertEqual(spoof.json()["cursorNs"], body["cursorNs"])
        foreign_actor, foreign_headers = f.account()
        self.assertNotEqual(foreign_actor, f.actor)
        self.assertEqual(f.client.get(self.path + "?timeframe=1h", headers=foreign_headers).status_code, 404)
        other = f.client.post("/api/v1/workspaces", headers=foreign_headers, json={"name": "Foreign chart QA"}).json()["id"]
        foreign_path = "/api/v1/workspaces/" + other + "/research/sessions/" + self.session + "/chart-bars?timeframe=1h"
        self.assertEqual(f.client.get(foreign_path, headers=foreign_headers).status_code, 404)
        unknown = f.root + "/sessions/session:does-not-exist/chart-bars?timeframe=1h"
        self.assertEqual(f.client.get(unknown, headers=f.headers).status_code, 404, "unknown Session answers like a foreign one")

    def test_hostile_parameters_and_unconfigured_deployments(self):
        f = self.fixture
        for query in ("timeframe=7m", "timeframe=1h&limit=0", "timeframe=1h&limit=2000", "timeframe=1h&before=-5", "timeframe=1h&before=abc"):
            self.assertIn(f.client.get(self.path + "?" + query, headers=f.headers).status_code, (400, 404, 422), query)
        f.client.close()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BTL_CHART_REGISTRY", None)
            g = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
            g.setUp(start_workers=False)
            try:
                path = g.root + "/sessions/session:any/chart-bars?timeframe=1h"
                self.assertEqual(g.client.get(path, headers=g.headers).status_code, 404, "no registry configured: the route behaves like an unknown resource")
            finally:
                g.client.close()


if __name__ == "__main__":
    unittest.main()
