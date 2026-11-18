"""Free/Pro month contract on the REAL stack (API, durable PostgreSQL queue, native worker, canonical Monthly Parquet, compact checkpoint V2).
SYNTHETIC / TEST ONLY: one authored tick per minute starting 2020-01-30 crosses the month boundaries Jan->Feb and Feb->Mar.

 * PRO: one Session runs from January through March WITHOUT being reset. A PENDING order and an ACTIVE position that exist before each boundary are
   unchanged by it; the long run equals a single uninterrupted control run (same events, balance, orders, journal); a worker restart in the middle
   (checkpoint + resume) changes nothing; many Sessions are admitted.
 * FREE: the Session stops at the end of its activated month; nothing is closed, cancelled or rewritten; the pending order survives untouched;
   second Session on the same UTC day is refused; reading an old Session (summary, journal, analytics) never consumes quota.
The reducer, fill rules and entitlement semantics are the ordinary ones; this module only drives them."""
import os
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import psycopg
from psycopg import sql

from cloud import queue, worker
from contracts.canonical import content_hash
from execution import replay_run as rr
from infrastructure.database import connect, migrate
import tests.test_cloud_research as cloud_fixture
from tests.test_research_sessions import method, review_request

DSN = cloud_fixture.DSN
TICKS = int(os.environ.get("BTL_FP_TICKS", "65536"))                         # 65,536 ticks = 2020-01-30 .. 2020-03-15
NS = 1_000_000_000


def utc_ns(y, m, d=1):
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp()) * NS


FEB1, MAR1 = utc_ns(2020, 2), utc_ns(2020, 3)


def leaf_diff(a, b, path=""):
    """Every differing leaf between two JSON-like values, so a parity failure names the exact field."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [d for k in sorted(set(a) | set(b)) for d in leaf_diff(a.get(k), b.get(k), path + "/" + str(k))]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in leaf_diff(x, y, path + "[" + str(i) + "]")]
    return [] if a == b else [(path, a, b)]


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class MonthContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        name = "btl_fp_months_" + uuid.uuid4().hex
        with connect(DSN) as db:
            db.autocommit = True
            db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        cls.name, cls.dsn = name, psycopg.conninfo.make_conninfo(DSN, dbname=name)
        migrate(cls.dsn)
        cls.dsn_patch = patch.object(cloud_fixture, "DSN", cls.dsn)
        cls.dsn_patch.start()
        from market_data.monthly_parquet import write_monthly_parquet
        from tests.synthetic_financial_monthly import build_manifest, iter_events
        cls.tmp = tempfile.TemporaryDirectory(prefix="riksora-fp-")
        cls.manifest, _m, _q = build_manifest(TICKS)
        cls.version = content_hash(cls.manifest)
        cache = os.environ.get("BTL_FP_DATA_CACHE")                      # optional: reuse the deterministic synthetic Parquet between runs (derived data, never committed)
        root = os.path.join(cache or cls.tmp.name, "monthly")
        marker = os.path.join(cache, "manifest-hash") if cache else None
        if marker and os.path.exists(marker):
            with open(marker) as handle:
                parquet = {"manifestHash": handle.read().strip()}
        else:
            parquet = write_monthly_parquet(root, iter_events(TICKS, cls.manifest), cls.manifest, expected_version=cls.version, row_group_size=4096)
            if marker:
                open(marker, "w").write(parquet["manifestHash"])
        accepted = os.path.join(cache or cls.tmp.name, "accepted")
        if not os.path.isdir(accepted):                                  # offline source acceptance, exactly as the provisioning of the public application does it
            from market_data.monthly_parquet import MonthlyParquetProvider
            from ticks import source_acceptance
            provider = MonthlyParquetProvider(root, expected_dataset_id=cls.manifest["datasetId"], expected_dataset_version=cls.version, expected_manifest_hash=parquet["manifestHash"])
            source_acceptance.accept_offline(provider, cls.manifest["datasetId"], cls.version, accepted)
        cls.pins = {"BTL_SOURCE_ACCEPTANCE_DIR": accepted, "BTL_QA_SYNTHETIC_MONTHLY_ENABLE": "1", "BTL_QA_SYNTHETIC_MONTHLY_ROOT": root, "BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID": cls.manifest["datasetId"],
                    "BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION": cls.version, "BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256": parquet["manifestHash"],
                    "BTL_TICK_SESSION_STORAGE_FORMAT": "compact-v1", "BTL_TICK_CHECKPOINT_FORMAT": "compact-v2",
                    "BTL_ENTITLEMENT_ENFORCE": "1", "BTL_ENTITLEMENT_RESET_TIMEZONE": "UTC", "BTL_REPLAY_RUN_BUDGET_S": "20"}
        cls.end = int(cls.manifest["range"]["endNs"]) - 1
        cls.start = int(cls.manifest["range"]["startNs"])

    @classmethod
    def tearDownClass(cls):
        worker.close()
        cls.dsn_patch.stop()
        cls.tmp.cleanup()
        with connect(DSN) as db:
            db.autocommit = True
            db.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(cls.name)))

    def setUp(self):
        self.env = patch.dict(os.environ, self.pins)
        self.env.start()
        worker.close()
        worker.warm_sources(self.dsn)                                   # what the API lifespan does before any job gets its 30 s deadline
        self.f = cloud_fixture.CloudResearchTests("test_member_read_only_then_revocation_and_logout")
        self.f.setUp(start_workers=False)
        self.path, self.headers, self.client = self.f.root, self.f.headers, self.f.client
        self.actor = self.f.actor
        self.record = method()
        self.assertEqual(self.client.post(self.path + "/methods", headers=self.headers, json=self.record).status_code, 200)

    def tearDown(self):
        with connect(self.dsn) as db:
            db.execute("DELETE FROM btl.research_jobs WHERE actor_id=%s", (uuid.UUID(self.actor),))
        self.f.client.close()
        worker.close()
        self.env.stop()

    # ---- helpers ------------------------------------------------------------------------------------------------------
    def grant_pro(self):
        now = int(time.time())
        with connect(self.dsn) as db:
            db.execute("INSERT INTO btl.sandbox_billing_orders(order_id,actor_id,request_id,merchant_id,plan_version,amount_idr,duration_seconds,phase,transaction_id,paid_at,expires_at,revision) "
                       "VALUES (%s,%s,%s,'m','p',1000,2592000,'PAID',%s,%s,%s,1)", ("btl-sbx-" + uuid.uuid4().hex, self.actor, uuid.uuid4(), "t" + uuid.uuid4().hex, now - 10, now - 10 + 2592000))

    def work(self, job_id):
        self.assertTrue(queue.work_one(self.dsn, worker.run))
        return self.client.get(self.path + "/jobs/" + job_id, headers=self.headers).json()

    def post(self, url, body, expect=202):
        job = str(uuid.uuid4())
        r = self.client.post(self.path + url, headers={**self.headers, "X-BTL-Job": job}, json=body)
        self.assertEqual(r.status_code, expect, r.text)
        return job, r

    def summary(self, sid):
        r = self.client.get(self.path + "/sessions/" + sid + "/summary", headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def view(self, sid):
        r = self.client.get(self.path + "/sessions/" + sid, headers=self.headers)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def orders(self, sid):
        return {k: v["status"] for k, v in self.view(sid)["state"]["orders"].items()}

    def command(self, sid, kind, payload, expect=202):
        st = self.summary(sid)
        cmd = {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": sid, "commandId": "command:" + uuid.uuid4().hex,
               "expectedRevision": st["revision"], "kind": kind, "payload": payload}
        job, r = self.post("/sessions/" + sid + "/commands", cmd, expect=expect)
        if expect == 202:
            self.assertEqual(self.work(job)["state"], "SUCCEEDED")
        return r

    def new_session(self, period="2020-01", with_orders=True, expect_created=True):
        sid = "session:" + uuid.uuid4().hex
        job, r = self.post("/sessions", {"id": sid, "name": "fp", "methodId": self.record["id"], "initialBalance": "10000", "startPeriod": period}, expect=202 if expect_created else 409)
        if not expect_created:
            return r
        started = time.monotonic()
        done = self.work(job)
        self.assertEqual(done["state"], "SUCCEEDED", (done, round(time.monotonic() - started, 1)))
        self.command(sid, "ADVANCE", {"targetNs": str(self.start)})
        if with_orders:
            view = self.view(sid)
            pending = dict(sessionId=sid, requestId="order:" + uuid.uuid4().hex, expectedRevision=view["state"]["revision"], planId="plan:fp", planRevision=0,
                           draft=dict(side="LONG", orderType="LIMIT", workflow="PLANNED", entry="1998.90", quantity="0.01", sl="1998.00", tp="1999.50", riskPercent="1", observations=[]))
            self.confirm(sid, pending)
            market = review_request(self.view(sid))                      # a QUICK market LONG, no SL/TP: stays ACTIVE across every boundary
            self.confirm(sid, market)
            self.command(sid, "ADVANCE", {"targetNs": str(self.start + 60 * NS)})      # the next tick fills the market order: ACTIVE position + PENDING limit
        return sid

    def confirm(self, sid, review):
        reviewed = self.client.post(self.path + "/reviews", headers=self.headers, json=review)
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        confirmed = self.client.post(self.path + "/sessions/" + sid + "/confirm", headers=self.headers, json={"reviewId": review["requestId"], "reviewHash": reviewed.json()["reviewHash"]})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

    def drive(self, sid, target, segments=4000):
        """replay-run (durable, server-chained segments) until the cursor reaches target or cannot move; returns the last result."""
        st = self.summary(sid)
        request = dict(schemaVersion=1, artifact=rr.REQUEST_ARTIFACT, runId=uuid.uuid4().hex, segment=0, sessionId=sid, expectedRevision=st["revision"], targetNs=str(target))
        job, _r = self.post("/sessions/" + sid + "/replay-run", request)
        last = None
        for _ in range(segments):
            done = self.work(job)
            self.assertEqual(done["state"], "SUCCEEDED", done)
            last = done["result"]
            if not last.get("continuationJobId"):
                return last
            job = last["continuationJobId"]
        self.fail("replay-run chain did not end")

    def facts(self, sid):
        """Everything financial about a Session, with identifiers stripped, so two runs can be compared for exact equality."""
        view = self.view(sid)
        st = view["state"]
        journal = self.client.get(self.path + "/sessions/" + sid + "/journal", headers=self.headers).json()
        orders = [{k: v for k, v in o.items() if k not in ("id", "sessionId", "orderId", "commandId", "reviewId", "requestId", "planId", "entryFillRef", "exitFillRef")} for o in journal["orders"]]   # fill refs are event ids (they embed the Session identity)
        summ = {k: v for k, v in self.summary(sid).items() if k not in ("revision", "sessionId", "id", "updatedAt", "name")}
        with connect(self.dsn) as db:
            n_events = db.execute("SELECT count(*) FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s", (self.f.workspace, sid)).fetchone()[0]
        return dict(through=st["throughNs"], balance=st["balance"], orderStatus=sorted(v["status"] for v in st["orders"].values()), journal=orders, summary=summ, events=n_events)

    # ---- PRO ----------------------------------------------------------------------------------------------------------
    def test_pro_one_session_runs_through_three_months_with_parity_and_restart(self):
        self.grant_pro()
        self.assertEqual(self.client.get(self.path + "/entitlements", headers=self.headers).json()["tier"], "PRO")
        sid = self.new_session()
        before = self.orders(sid)
        self.assertEqual(sorted(before.values()), ["ACTIVE", "PENDING"])
        snaps = {}
        stages = [("preFeb", FEB1 - 1), ("postFeb", FEB1 + 120 * NS), ("preMar", MAR1 - 1), ("postMar", MAR1 + 120 * NS), ("end", self.end)]
        for index, (label, target) in enumerate(stages):
            self.drive(sid, target)
            st = self.view(sid)["state"]
            self.assertGreaterEqual(int(st["throughNs"]), min(target, self.end) - 60 * NS, label)
            snaps[label] = (dict(self.orders(sid)), st["balance"], int(st["throughNs"]))
            if label == "postFeb":
                worker.close()                                           # worker restart in the middle: the next segment resumes from the durable checkpoint
        # the Session crossed 2 month boundaries without a reset: same Session id, monotonic cursor, no new Session needed
        self.assertGreater(snaps["postFeb"][2], FEB1)
        self.assertGreater(snaps["postMar"][2], MAR1)
        # state at each boundary: the boundary itself changes nothing (pending stays pending, active stays active, cash balance unchanged)
        self.assertEqual(snaps["preFeb"][0], snaps["postFeb"][0], "orders changed at the Jan->Feb boundary")
        self.assertEqual(snaps["preMar"][0], snaps["postMar"][0], "orders changed at the Feb->Mar boundary")
        self.assertEqual(snaps["preFeb"][1], snaps["postFeb"][1])
        self.assertEqual(snaps["preMar"][1], snaps["postMar"][1])
        self.assertEqual(sorted(snaps["preFeb"][0].values()), ["ACTIVE", "PENDING"])
        # control: an identical Session run in ONE uninterrupted replay-run to the end
        control = self.new_session()
        self.drive(control, self.end)
        a, b = self.facts(sid), self.facts(control)
        self.assertEqual(leaf_diff(a, b), [], "staged Pro run with restart differs from the uninterrupted control")
        self.assertEqual(int(a["through"]), self.end)
        # no tick lost or duplicated: the cursor reached the last tick exactly and event counts equal
        self.assertEqual(a["events"], b["events"])

    def test_pro_admits_many_sessions_and_records_them(self):
        self.grant_pro()
        ids = [self.new_session(with_orders=False) for _ in range(4)]
        self.assertEqual(len(set(ids)), 4)
        st = self.client.get(self.path + "/entitlements", headers=self.headers).json()
        self.assertEqual((st["tier"], st["sessions"]["limit"], st["windows"]["limit"]), ("PRO", None, None))
        # NOTE: the synthetic source can only START in its first month (2020-01), so a Pro "second new month on the same day" cannot be driven with this fixture;
        # the quota layer is exercised for it in test_entitlements (period/claim level) and Pro crossing months inside one Session is proven above.

    def test_pro_expiry_mid_session_keeps_the_history_and_falls_back_to_free_rules(self):
        self.grant_pro()
        sid = self.new_session()
        self.drive(sid, FEB1 + 120 * NS)                                  # Pro: already past the Jan->Feb boundary
        before = (self.orders(sid), self.view(sid)["state"]["balance"], int(self.view(sid)["state"]["throughNs"]))
        self.assertGreater(before[2], FEB1)
        with connect(self.dsn) as db:                                      # the paid period ends (expiry / refund): tier is derived from PAID, unexpired orders only
            db.execute("UPDATE btl.sandbox_billing_orders SET phase='REVERSED', revision=revision+1 WHERE actor_id=%s", (self.actor,))
        self.assertEqual(self.client.get(self.path + "/entitlements", headers=self.headers).json()["tier"], "FREE")
        # nothing is closed, cancelled or rewritten; the Session and its journal stay readable
        self.assertEqual((self.orders(sid), self.view(sid)["state"]["balance"], int(self.view(sid)["state"]["throughNs"])), before)
        for suffix in ("", "/summary", "/journal"):
            self.assertEqual(self.client.get(self.path + "/sessions/" + sid + suffix, headers=self.headers).status_code, 200, suffix)
        # but it can no longer reveal data beyond the activated month (the window is behind the cursor): only Cancel/Close/End/Jump-with-position remain
        st = self.summary(sid)
        r = self.client.post(self.path + "/sessions/" + sid + "/replay-run", headers={**self.headers, "X-BTL-Job": str(uuid.uuid4())},
                             json=dict(schemaVersion=1, artifact=rr.REQUEST_ARTIFACT, runId=uuid.uuid4().hex, segment=0, sessionId=sid, expectedRevision=st["revision"], targetNs=str(self.end)))
        self.assertEqual((r.status_code, r.json()["detail"]), (409, "WINDOW_ENDED_CONTINUATION_ONLY"))
        self.assertEqual((self.orders(sid), int(self.view(sid)["state"]["throughNs"])), (before[0], before[2]))
        # Pro again (renewal): the same Session continues from exactly where it was
        self.grant_pro()
        self.drive(sid, MAR1 + 120 * NS)
        self.assertGreater(int(self.view(sid)["state"]["throughNs"]), MAR1)

    # ---- FREE ---------------------------------------------------------------------------------------------------------
    def test_free_session_stops_at_the_end_of_its_month_without_touching_orders(self):
        sid = self.new_session()
        before = self.orders(sid)
        end_of_window = FEB1 - 1
        self.drive(sid, end_of_window)
        mid = self.view(sid)["state"]
        self.assertLess(int(mid["throughNs"]), FEB1)
        # going beyond the activated month is refused on every advancing route; the response says why
        for route, body in (("/sessions/" + sid + "/replay-run", dict(schemaVersion=1, artifact=rr.REQUEST_ARTIFACT, runId=uuid.uuid4().hex, segment=0, sessionId=sid,
                                                                       expectedRevision=mid["revision"], targetNs=str(self.end))),
                            ("/sessions/" + sid + "/commands", {"schemaVersion": 1, "artifact": "BTL-TICK-EXECUTION-COMMAND-1", "sessionId": sid, "commandId": "command:" + uuid.uuid4().hex,
                                                                "expectedRevision": mid["revision"], "kind": "ADVANCE", "payload": {"targetNs": str(self.end)}})):
            r = self.client.post(self.path + route, headers={**self.headers, "X-BTL-Job": str(uuid.uuid4())}, json=body)
            self.assertEqual(r.status_code, 409, (route, r.text))
            self.assertIn(r.json()["detail"], ("WINDOW_BOUNDARY", "WINDOW_ENDED_CONTINUATION_ONLY"))
        self.assertEqual(self.orders(sid), before, "the window boundary changed an order")
        self.assertEqual(int(self.view(sid)["state"]["throughNs"]), int(mid["throughNs"]), "refused request moved the cursor")

    def test_free_second_session_same_utc_day_is_refused_and_old_session_stays_readable(self):
        sid = self.new_session()
        self.drive(sid, FEB1 - 1)
        refused = self.new_session(expect_created=False)
        self.assertEqual(refused.json()["detail"], "SESSION_DAY_LIMIT")
        used = self.client.get(self.path + "/entitlements", headers=self.headers).json()
        self.assertEqual((used["sessions"]["used"], used["sessions"]["limit"]), (1, 1))
        # reading is free: summary, journal, analytics, export and the Session list consume nothing and still work after the quota is used
        for suffix in ("", "/summary", "/journal", "/analytics/pages?limit=8&offset=0&revision=" + str(self.summary(sid)["revision"])):
            r = self.client.get(self.path + "/sessions/" + sid + suffix, headers=self.headers)
            self.assertEqual(r.status_code, 200, (suffix, r.text))
        after = self.client.get(self.path + "/entitlements", headers=self.headers).json()
        self.assertEqual(after["sessions"]["used"], 1)
        self.assertEqual(self.client.get(self.path + "/sessions?limit=50", headers=self.headers).status_code, 200)

    def serve(self):
        """The real app behind a real uvicorn loop (one event loop, as in production). TestClient opens a new loop per request, which is not valid for concurrency tests."""
        import socket
        import threading
        import uvicorn
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        server = uvicorn.Server(uvicorn.Config(self.client.app, host="127.0.0.1", port=port, proxy_headers=True, forwarded_allow_ips="127.0.0.1", log_level="warning", access_log=False))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.1)
        self.assertTrue(server.started)
        self.addCleanup(lambda: (setattr(server, "should_exit", True), thread.join(30)))
        return port

    def test_free_parallel_requests_and_second_tab_cannot_open_two_sessions(self):
        import httpx
        import threading
        port = self.serve()
        outcomes, lock = [], threading.Lock()

        def attempt(index, period):
            sid = "session:" + uuid.uuid4().hex
            headers = {**self.headers, "X-BTL-Job": str(uuid.uuid4()), "X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113." + str(10 + index)}
            with httpx.Client(base_url="http://127.0.0.1:%d" % port, timeout=60) as tab:                        # each "tab" is its own connection and its own client address
                r = tab.post(self.path + "/sessions", headers=headers, json={"id": sid, "name": "tab", "methodId": self.record["id"], "initialBalance": "10000", "startPeriod": period})
            with lock:
                outcomes.append((r.status_code, (r.json() or {}).get("detail")))
        # eight "tabs" at once: same month and different months (a different month is also a second window activation)
        threads = [threading.Thread(target=attempt, args=(i, "2020-01" if i % 2 == 0 else "2020-02")) for i in range(8)]
        [t.start() for t in threads]
        [t.join(90) for t in threads]
        self.assertEqual(len(outcomes), 8, outcomes)
        accepted = [o for o in outcomes if o[0] in (200, 202)]
        self.assertEqual(len(accepted), 1, outcomes)
        self.assertTrue(all(o[1] in ("SESSION_DAY_LIMIT", "WINDOW_DAY_LIMIT", "ACTIVATION_IN_PROGRESS") for o in outcomes if o not in accepted), outcomes)
        with connect(self.dsn) as db:
            live = db.execute("SELECT kind,count(*) FROM btl.entitlement_claims WHERE actor_id=%s AND status IN ('RESERVED','COMMITTED') GROUP BY kind ORDER BY kind", (self.actor,)).fetchall()
        self.assertEqual(live, [("SESSION", 1), ("WINDOW", 1)])

if __name__ == "__main__":
    unittest.main()
