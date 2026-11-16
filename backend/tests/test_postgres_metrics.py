"""Read-only global PostgreSQL size and WAL metering contract."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from infrastructure.database import migrate
from infrastructure.postgres_metrics import ARTIFACT, collect, compare
from contracts.primitives import ContractError
from contracts.canonical import canonical_bytes, content_hash
from infrastructure.postgres_metrics import collect_job_metrics, summarize_job_metric_rows


DSN = os.getenv("BTL_TEST_DATABASE_URL")


@unittest.skipUnless(DSN, "Isolated PostgreSQL required; skip is not acceptance")
class PostgresMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def test_collect_is_global_read_only_snapshot_with_explicit_unknown_attribution(self):
        measured = collect(DSN)
        self.assertEqual(measured["artifact"], ARTIFACT)
        self.assertEqual(measured["measurementScope"], "DATABASE_AND_SERVER_GLOBAL_SNAPSHOT")
        self.assertEqual(measured["databaseScope"], "CURRENT_DATABASE")
        self.assertEqual(measured["walScope"], "POSTGRESQL_SERVER")
        self.assertGreater(measured["databaseBytes"], 0)
        self.assertTrue(any(row["relation"] == "research_jobs" for row in measured["relations"]))
        if measured["retainedWalFileStatus"] == "AVAILABLE_RETAINED_FILE_BYTES":
            self.assertIsInstance(measured["retainedWalFileBytes"], int)
        else:
            self.assertIsNone(measured["retainedWalFileBytes"])
        self.assertIsNone(measured["perSessionWalBytes"])
        self.assertIsNone(measured["perSessionPhysicalBytes"])
        if measured["walStatus"] == "AVAILABLE_CUMULATIVE_COUNTER":
            self.assertIsInstance(measured["walGeneratedBytesSinceReset"], int)
        else:
            self.assertIsNone(measured["walGeneratedBytesSinceReset"])

    def test_delta_requires_same_database_and_stable_wal_reset_epoch(self):
        before = collect(DSN)
        after = deepcopy(before)
        after["measuredAt"] = (
            datetime.fromisoformat(before["measuredAt"]) + timedelta(seconds=1)
        ).isoformat()
        after["databaseBytes"] += 4096
        after["relations"][0]["totalBytes"] += 1024
        delta = compare(before, after)
        self.assertEqual(delta["databaseBytesDelta"], 4096)
        self.assertEqual(delta["attribution"], "CURRENT_DATABASE_AND_SERVER_WAL_GLOBAL_ONLY")
        self.assertIsNone(delta["perSessionWalBytesDelta"])
        self.assertEqual(delta["relationStatus"], "COMPARABLE")
        relation = before["relations"][0]["relation"]
        relation_delta = next(row for row in delta["relationDeltas"] if row["relation"] == relation)
        self.assertEqual(relation_delta["totalBytesDelta"], 1024)
        if before["retainedWalFileStatus"] == "AVAILABLE_RETAINED_FILE_BYTES":
            self.assertEqual(delta["retainedWalFileDeltaStatus"], "COMPARABLE")
            self.assertEqual(delta["retainedWalFileBytesDelta"], 0)
        else:
            self.assertEqual(delta["retainedWalFileDeltaStatus"], "NOT_COMPARABLE_OR_UNAVAILABLE")
            self.assertIsNone(delta["retainedWalFileBytesDelta"])

        reset = deepcopy(after)
        if reset["walStatus"] == "AVAILABLE_CUMULATIVE_COUNTER":
            reset["walStatsResetAt"] = (
                datetime.fromisoformat(reset["walStatsResetAt"]) + timedelta(seconds=1)
            ).isoformat()
            reset["walGeneratedBytesSinceReset"] = 9000
        incomparable = compare(before, reset)
        self.assertEqual(incomparable["walDeltaStatus"], "NOT_COMPARABLE_RESET_OR_UNAVAILABLE")
        self.assertIsNone(incomparable["walGeneratedBytesDelta"])

        other_database = deepcopy(after)
        other_database["database"] = "other"
        with self.assertRaisesRegex(ContractError, "REFUSED_METRIC_IDENTITY_MISMATCH"):
            compare(before, other_database)

        other_server = deepcopy(after)
        other_server["serverStartedAt"] = "2026-11-01T00:00:00+00:00"
        with self.assertRaisesRegex(ContractError, "REFUSED_METRIC_IDENTITY_MISMATCH"):
            compare(before, other_server)

    def test_bounded_job_metric_distribution_verifies_hashes_and_reports_p50_p95(self):
        rows = []
        for index, (wait, cpu) in enumerate(((10, 100), (20, 200), (100, 400))):
            queue_metric = {
                "schemaVersion": 1, "artifact": "BTL-QUEUE-WAIT-METRICS-1",
                "measurementScope": "FIRST_DURABLE_ADMISSION_TO_FIRST_WORKER_CLAIM",
                "clock": "POSTGRESQL_CLOCK_TIMESTAMP_MICROSECOND", "waitMicroseconds": wait,
            }
            worker_metric = {
                "schemaVersion": 1, "artifact": "BTL-NATIVE-WORKER-METRICS-1",
                "measurementScope": "ONE_JOB_CPU_IO_PROCESS_LIFETIME_RSS_HIGH_WATER",
                "wallNs": cpu * 2, "cpuNs": cpu, "processPeakRssBytes": 1024 + index,
                "readBytesDelta": 10 + index, "writeBytesDelta": 20 + index,
                "readSyscallsDelta": 3 + index, "writeSyscallsDelta": 4 + index,
            }
            queue_raw, worker_raw = canonical_bytes(queue_metric), canonical_bytes(worker_metric)
            rows.append({
                "state": "SUCCEEDED", "queue_metrics": queue_raw,
                "queue_metrics_hash": content_hash(queue_metric),
                "worker_metrics": worker_raw, "worker_metrics_hash": content_hash(worker_metric),
            })

        report = summarize_job_metric_rows(rows, 3)
        self.assertEqual(report["queueWaitMicroseconds"]["p50"], 20)
        self.assertEqual(report["queueWaitMicroseconds"]["p95"], 100)
        self.assertEqual(report["worker"]["cpuNs"]["p50"], 200)
        self.assertEqual(report["worker"]["cpuNs"]["p95"], 400)
        self.assertEqual(report["worker"]["processPeakRssBytes"]["sampleCount"], 3)
        self.assertEqual(report["postgresProcessCpuAndWAL"], "NOT_ATTRIBUTED_TO_JOBS")
        self.assertNotIn("actorId", report)
        self.assertNotIn("sessionId", report)

        corrupted = deepcopy(rows)
        corrupted[0]["worker_metrics_hash"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "CORRUPT_RECORD"):
            summarize_job_metric_rows(corrupted, 3)

    def test_database_collector_returns_bounded_job_sample(self):
        report = collect_job_metrics(DSN, 7)
        self.assertEqual(report["artifact"], "BTL-OPERATIONAL-JOB-METRICS-1")
        self.assertEqual(report["sampleLimit"], 7)
        self.assertLessEqual(report["sampledJobs"], 7)

    def test_operator_cli_emits_snapshot_and_comparable_delta(self):
        environment = {**os.environ, "BTL_DATABASE_URL": DSN, "PYTHONPATH": "."}
        with tempfile.TemporaryDirectory() as folder:
            baseline_path = Path(folder) / "baseline.json"
            snapshot = subprocess.run(
                [sys.executable, "-m", "infrastructure.database", "metrics",
                 "--job-sample-limit", "7"],
                env=environment, check=True, capture_output=True, text=True, timeout=10,
            )
            baseline_path.write_text(snapshot.stdout, encoding="utf-8")
            delta = subprocess.run(
                [sys.executable, "-m", "infrastructure.database", "metrics",
                 "--baseline", str(baseline_path), "--job-sample-limit", "7"],
                env=environment, check=True, capture_output=True, text=True, timeout=10,
            )
        report = json.loads(delta.stdout)
        self.assertEqual(report["artifact"], "BTL-POSTGRES-CAPACITY-DELTA-1")
        self.assertEqual(report["attribution"], "CURRENT_DATABASE_AND_SERVER_WAL_GLOBAL_ONLY")
        self.assertEqual(report["currentOperationalJobMetrics"]["artifact"],
                         "BTL-OPERATIONAL-JOB-METRICS-1")
        self.assertEqual(report["currentOperationalJobMetrics"]["sampleLimit"], 7)


if __name__ == "__main__":
    unittest.main()
