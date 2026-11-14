"""Default-path Session trash/restore: owner only, tenant isolated, hidden from the list, 30-day restore window, financial evidence untouched."""
import unittest
import uuid

from infrastructure.database import connect
import tests.test_cloud_research as cloud_fixture
from tests.test_research_sessions import method

DSN = cloud_fixture.DSN


@unittest.skipUnless(DSN, 'Real isolated PostgreSQL required; skip is not PASS')
class SessionLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cloud_fixture.CloudResearchTests.setUpClass()

    def setUp(self):
        self.f = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
        self.f.setUp(start_workers=True)

    def tearDown(self):
        self.f.tearDown()
        self.f.client.close()

    def listed(self, headers=None, root=None):
        r = self.f.client.get((root or self.f.root) + "/sessions", headers=headers or self.f.headers)
        self.assertEqual(r.status_code, 200, r.text)
        return [item["metadata"]["id"] for item in r.json()["items"]]

    def test_trash_hides_restore_returns_and_the_window_expires(self):
        f = self.f
        record = method()
        self.assertIn(f.client.post(f.root + "/methods", headers=f.headers, json=record).status_code, (200, 201, 202))
        sid = "session:" + uuid.uuid4().hex
        created = f.client.post(f.root + "/sessions", headers=f.headers, json=dict(id=sid, name="Lifecycle", methodId=record["id"], initialBalance="10000", startPeriod="2020-01"))
        f.completed_job_result(created)
        self.assertIn(sid, self.listed())
        _, other_headers = f.account()
        other_root = "/api/v1/workspaces/" + f.client.post("/api/v1/workspaces", headers=other_headers, json={"name": "Other"}).json()["id"] + "/research"
        self.assertEqual(f.client.post(f.root + "/sessions/" + sid + "/trash", headers=other_headers).status_code, 404, "a non-member is refused like an unknown resource")
        self.assertEqual(f.client.post(other_root + "/sessions/" + sid + "/trash", headers=other_headers).status_code, 404, "a foreign Session id in the caller's own workspace")
        self.assertEqual(f.client.post(f.root + "/sessions/" + sid + "/trash").status_code, 401)
        trashed = f.client.post(f.root + "/sessions/" + sid + "/trash", headers=f.headers)
        self.assertEqual(trashed.status_code, 200, trashed.text)
        self.assertNotIn(sid, self.listed())
        self.assertEqual(f.client.post(f.root + "/sessions/" + sid + "/trash", headers=f.headers).status_code, 200, "idempotent")
        restored = f.client.post(f.root + "/sessions/" + sid + "/restore", headers=f.headers)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertIn(sid, self.listed())
        f.client.post(f.root + "/sessions/" + sid + "/trash", headers=f.headers)
        with connect(DSN) as db:
            db.execute("UPDATE btl.session_lifecycle SET trashed_at = clock_timestamp() - interval '31 days' WHERE session_id=%s", (sid,))
        expired = f.client.post(f.root + "/sessions/" + sid + "/restore", headers=f.headers)
        self.assertEqual((expired.status_code, expired.json()["detail"]), (409, "TRASH_EXPIRED"))
        self.assertNotIn(sid, self.listed())


if __name__ == "__main__":
    unittest.main()
