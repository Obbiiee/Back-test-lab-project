"""Real PostgreSQL worker journey for a deterministic synthetic tick source."""
import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from psycopg import sql

from cloud import queue, worker
from contracts.canonical import content_hash
from execution.contracts import MAX_STEPS
from infrastructure.database import connect, migrate
from market_data.monthly_parquet import write_monthly_parquet
from tests import test_cloud_research as cloud_fixture
from tests.synthetic_financial_monthly import build_manifest, iter_events
from tests.test_research_sessions import method


DSN = os.getenv("BTL_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not acceptance")
class FinancialActiveWorkerAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_name = "btl_financial_worker_" + uuid.uuid4().hex
        with connect(DSN) as db:
            db.autocommit = True
            db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.database_name)))
        cls.dsn = __import__("psycopg").conninfo.make_conninfo(DSN, dbname=cls.database_name)
        migrate(cls.dsn)
        cls.fixture_dsn = patch.object(cloud_fixture, "DSN", cls.dsn)
        cls.fixture_dsn.start()

    @classmethod
    def tearDownClass(cls):
        worker.close()
        cls.fixture_dsn.stop()
        # This class created this UUID-named database in setUpClass; clean up
        # only that disposable database after all clients/workers are closed.
        with connect(DSN) as db:
            db.autocommit = True
            db.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(cls.database_name)))

    def setUp(self):
        worker.close()
        self.fixture = cloud_fixture.CloudResearchTests("test_summary_requires_identity_membership_and_hides_foreign_session")
        self.fixture.setUp(start_workers=False)

    def tearDown(self):
        self.fixture.client.close()

    def _capture_job_metrics(self, job_id):
        """Capture bounded operational metrics before queue retention prunes a row."""
        with connect(self.dsn) as db:
            row = db.execute(
                "SELECT operation,state,queue_metrics,worker_metrics "
                "FROM btl.research_jobs WHERE id=%s", (uuid.UUID(job_id),)
            ).fetchone()
        self.assertIsNotNone(row, f"completed job {job_id} was not retained")
        self.assertEqual(row[1], "SUCCEEDED", f"job {job_id}: {row[1]}")
        self.assertIsNotNone(row[2], f"job {job_id} has no queue metrics")
        self.assertIsNotNone(row[3], f"job {job_id} has no worker metrics")
        return dict(operation=row[0], state=row[1],
            queue=json.loads(bytes(row[2])), worker=json.loads(bytes(row[3])))

    def test_authenticated_monthly_parquet_to_closed_trade_receipt_journal_analytics(self):
        count = int(os.environ.get("BTL_FINANCIAL_WORKER_EVENTS", "512"))
        self.assertIn(count, (512, 2_048, 65_536, 131_072, 262_144))
        # Avoid replaying hundreds/thousands of real durable jobs when the
        # frozen Session checkpoint cannot represent the required advance
        # sequence. A prior bounded attempt reproduced this guard at 16,320.
        minimum_targets = 1 + ((count - 1 + 63) // 64)
        if minimum_targets >= MAX_STEPS:
            self.skipTest(
                f"BLOCKED: {count} unique-timestamp ticks require at least "
                f"{minimum_targets} advance targets; frozen Session budget is {MAX_STEPS}"
            )
        worker_count = queue.WORKERS
        source_manifest, member_hash, _ = build_manifest(count)
        source_version = content_hash(source_manifest)
        with tempfile.TemporaryDirectory(prefix="riksora-financial-worker-source-") as temporary:
            root = Path(temporary) / "monthly"
            parquet_manifest = write_monthly_parquet(root, iter_events(count, source_manifest),
                source_manifest, expected_version=source_version, row_group_size=128)
            pins = {
                "BTL_QA_SYNTHETIC_MONTHLY_ENABLE": "1",
                "BTL_QA_SYNTHETIC_MONTHLY_ROOT": str(root),
                "BTL_QA_SYNTHETIC_MONTHLY_DATASET_ID": source_manifest["datasetId"],
                "BTL_QA_SYNTHETIC_MONTHLY_DATASET_VERSION": source_version,
                "BTL_QA_SYNTHETIC_MONTHLY_MANIFEST_SHA256": parquet_manifest["manifestHash"],
                "BTL_TICK_SESSION_STORAGE_FORMAT": "compact-v1",
            }
            with patch.dict(os.environ, pins):
                started = time.perf_counter()
                with connect(self.dsn) as db:
                    database_bytes_before = db.execute(
                        "SELECT pg_database_size(current_database())").fetchone()[0]
                base = self.fixture.root
                record = method()
                response = self.fixture.client.post(base + "/methods",
                    headers=self.fixture.headers, json=record)
                self.assertEqual(response.status_code, 200, response.text)
                session_id = "session:" + uuid.uuid4().hex
                create_job = str(uuid.uuid4())
                response = self.fixture.client.post(base + "/sessions",
                    headers={**self.fixture.headers, "X-BTL-Job": create_job}, json={
                        "id": session_id, "name": "Synthetic financial-active acceptance",
                        "methodId": record["id"], "initialBalance": "10000", "startPeriod": "2020-01"})
                self.assertEqual(response.status_code, 202, response.text)
                self.assertTrue(queue.work_one(self.dsn, worker.run))
                create_status = self.fixture.client.get(base + "/jobs/" + create_job,
                    headers=self.fixture.headers).json()
                self.assertEqual(create_status["state"], "SUCCEEDED", create_status)
                captured_job_metrics = [self._capture_job_metrics(create_job)]
                view = self.fixture.client.get(base + "/sessions/" + session_id,
                    headers=self.fixture.headers).json()
                self.assertEqual((view["state"]["datasetId"], view["state"]["datasetVersion"]),
                    (source_manifest["datasetId"], source_version))

                # Product review requires a committed visible quote. Reveal
                # the first canonical group through the normal durable worker.
                setup_job = str(uuid.uuid4())
                setup_command = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-1",
                    sessionId=session_id, commandId="command:" + uuid.uuid4().hex,
                    expectedRevision=view["state"]["revision"], kind="ADVANCE",
                    payload={"targetNs": source_manifest["range"]["startNs"]})
                setup_queued = self.fixture.client.post(base + "/sessions/" + session_id + "/commands",
                    headers={**self.fixture.headers, "X-BTL-Job": setup_job}, json=setup_command)
                self.assertEqual(setup_queued.status_code, 202, setup_queued.text)
                self.assertTrue(queue.work_one(self.dsn, worker.run))
                self.assertEqual(self.fixture.client.get(base + "/jobs/" + setup_job,
                    headers=self.fixture.headers).json()["state"], "SUCCEEDED")
                captured_job_metrics.append(self._capture_job_metrics(setup_job))
                view = self.fixture.client.get(base + "/sessions/" + session_id,
                    headers=self.fixture.headers).json()
                self.assertIsNotNone(view["quote"])

                request_id = "order:" + uuid.uuid4().hex
                review = dict(sessionId=session_id, requestId=request_id,
                    expectedRevision=view["state"]["revision"], planId="plan:" + uuid.uuid4().hex,
                    planRevision=0,
                    draft=dict(side="LONG", orderType="LIMIT", workflow="PLANNED",
                        entry="1998.90", quantity="0.01", sl="1998.00", tp="1999.50",
                        riskPercent="1", observations=[]))
                reviewed = self.fixture.client.post(base + "/reviews",
                    headers=self.fixture.headers, json=review)
                if reviewed.status_code != 200:
                    from fastapi.responses import JSONResponse
                    with patch("cloud.workspaces.domain_error_response",
                        side_effect=lambda error: JSONResponse({"error": error.code,
                            "field": error.field}, status_code=500)):
                        diagnostic = self.fixture.client.post(base + "/reviews",
                            headers=self.fixture.headers, json=review)
                    self.fail(f"review failed: {reviewed.status_code}; diagnostic={diagnostic.text}")
                self.assertEqual(reviewed.status_code, 200, reviewed.text)
                confirm_body = {"reviewId": request_id, "reviewHash": reviewed.json()["reviewHash"]}
                confirmed = self.fixture.client.post(base + "/sessions/" + session_id + "/confirm",
                    headers=self.fixture.headers, json=confirm_body)
                self.assertEqual(confirmed.status_code, 200, confirmed.text)
                retry = self.fixture.client.post(base + "/sessions/" + session_id + "/confirm",
                    headers=self.fixture.headers, json=confirm_body)
                self.assertEqual(retry.content, confirmed.content)
                committed = self.fixture.client.get(base + "/sessions/" + session_id +
                    "/commands/" + request_id, headers=self.fixture.headers).json()
                self.assertEqual(committed["status"], "COMMITTED")
                self.assertTrue(committed["receipt"]["durable"])

                target_ns = int(source_manifest["range"]["endNs"]) - 1
                replay_job_ids = []
                # Each accepted ADVANCE is one bounded canonical 64-group
                # command. A long synthetic history is a sequence of durable
                # commands, never one oversized worker job or request payload.
                max_replay_jobs = ((count - 1 + 63) // 64) + 2
                for _ in range(max_replay_jobs):
                    view = self.fixture.client.get(base + "/sessions/" + session_id,
                        headers=self.fixture.headers).json()
                    if int(view["state"]["throughNs"]) >= target_ns:
                        break
                    command_id, job_id = "command:" + uuid.uuid4().hex, str(uuid.uuid4())
                    command = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-1",
                        sessionId=session_id, commandId=command_id,
                        expectedRevision=view["state"]["revision"], kind="ADVANCE",
                        payload={"targetNs": str(target_ns)})
                    queued = self.fixture.client.post(base + "/sessions/" + session_id + "/commands",
                        headers={**self.fixture.headers, "X-BTL-Job": job_id}, json=command)
                    self.assertEqual(queued.status_code, 202, queued.text)
                    self.assertTrue(queue.work_one(self.dsn, worker.run))
                    result = self.fixture.client.get(base + "/jobs/" + job_id,
                        headers=self.fixture.headers).json()
                    self.assertEqual(result["state"], "SUCCEEDED",
                        dict(replayJobIndex=len(replay_job_ids), requestedEvents=count, result=result))
                    self.assertTrue(result["result"]["durable"])
                    replay_job_ids.append(uuid.UUID(job_id))
                    captured_job_metrics.append(self._capture_job_metrics(job_id))
                else:
                    self.fail("bounded ADVANCE jobs did not reach the end of synthetic Session")

                final_view = self.fixture.client.get(base + "/sessions/" + session_id,
                    headers=self.fixture.headers).json()
                self.assertGreaterEqual(int(final_view["state"]["throughNs"]), target_ns)
                journal = self.fixture.client.get(base + "/sessions/" + session_id + "/journal",
                    headers=self.fixture.headers)
                self.assertEqual(journal.status_code, 200, journal.text)
                self.assertEqual([row["status"] for row in journal.json()["orders"]], ["CLOSED"])
                analytics = self.fixture.client.get(base + "/sessions/" + session_id +
                    "/analytics/pages?limit=32&offset=0&revision=" + str(final_view["state"]["revision"]),
                    headers=self.fixture.headers)
                self.assertEqual(analytics.status_code, 200, analytics.text)
                self.assertEqual(analytics.json()["metrics"]["tradeCount"], 1)
                summary = self.fixture.client.get(base + "/sessions/" + session_id + "/summary",
                    headers=self.fixture.headers).json()
                self.assertEqual(summary["completedTrades"], 1)
                self.assertEqual(summary["netCashChange"], "0.7")

                from execution.postgres import unpack
                with connect(self.dsn) as db:
                    event_rows = db.execute("SELECT payload,content_hash FROM btl.tick_events "
                        "WHERE workspace_id=%s AND session_id=%s ORDER BY sequence",
                        (str(self.fixture.workspace), session_id)).fetchall()
                    job_ids = [uuid.UUID(create_job), uuid.UUID(setup_job), *replay_job_ids]
                    # Operational job rows are intentionally bounded by RETAINED_LIMIT.
                    # They may be pruned during a long replay, so durable job completion
                    # and metrics are asserted/captured immediately after each job above.
                    job_rows = db.execute("SELECT state FROM btl.research_jobs "
                        "WHERE state IN ('FAILED','EXPIRED','RECONCILE_REQUIRED')").fetchall()
                    database_bytes_after = db.execute(
                        "SELECT pg_database_size(current_database())").fetchone()[0]
                events = [unpack(raw, digest) for raw, digest in event_rows]
                fills = [event for event in events if event["classification"] == "SIMULATED_FILL"]
                self.assertEqual([event["kind"] for event in fills], ["ENTRY_FILL", "EXIT_FILL"])
                self.assertFalse(job_rows, f"unexpected failed operational jobs: {job_rows}")
                self.assertEqual(len(captured_job_metrics), len(job_ids))
                worker_metrics = [item["worker"] for item in captured_job_metrics]
                queue_metrics = [item["queue"] for item in captured_job_metrics]
                evidence = dict(label="SYNTHETIC / TEST ONLY", eventCount=count,
                    sourceMemberSha256=member_hash, datasetVersion=source_version,
                    parquetManifestHash=parquet_manifest["manifestHash"],
                    configuredWorkerCount=worker_count,
                    replayJobs=len(replay_job_ids), setupQuoteJobs=1,
                    wallSeconds=time.perf_counter()-started,
                    workerCpuSeconds=sum(item["cpuNs"] for item in worker_metrics)/1e9,
                    workerWallSeconds=sum(item["wallNs"] for item in worker_metrics)/1e9,
                    workerPeakRssBytes=max(item["processPeakRssBytes"] for item in worker_metrics),
                    queueWaitMicroseconds=[item["waitMicroseconds"] for item in queue_metrics],
                    workerReadBytes=sum(item["readBytesDelta"] or 0 for item in worker_metrics),
                    workerWriteBytes=sum(item["writeBytesDelta"] or 0 for item in worker_metrics),
                    durableFinancialEvents=[event["kind"] for event in fills],
                    journalStatus=journal.json()["orders"][0]["status"],
                    analyticsTradeCount=analytics.json()["metrics"]["tradeCount"],
                    finalBalance=final_view["state"]["balance"],
                    databaseGrowthBytes=database_bytes_after-database_bytes_before,
                    warning="Local disposable PostgreSQL/real API worker test; no VPS or production capacity claim.")
                print("FINANCIAL_WORKER_EVIDENCE=" + json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
