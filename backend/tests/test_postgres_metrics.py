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

    def test_operator_cli_emits_snapshot_and_comparable_delta(self):
        environment = {**os.environ, "BTL_DATABASE_URL": DSN, "PYTHONPATH": "."}
        with tempfile.TemporaryDirectory() as folder:
            baseline_path = Path(folder) / "baseline.json"
            snapshot = subprocess.run(
                [sys.executable, "-m", "infrastructure.database", "metrics"],
                env=environment, check=True, capture_output=True, text=True, timeout=10,
            )
            baseline_path.write_text(snapshot.stdout, encoding="utf-8")
            delta = subprocess.run(
                [sys.executable, "-m", "infrastructure.database", "metrics",
                 "--baseline", str(baseline_path)],
                env=environment, check=True, capture_output=True, text=True, timeout=10,
            )
        report = json.loads(delta.stdout)
        self.assertEqual(report["artifact"], "BTL-POSTGRES-CAPACITY-DELTA-1")
        self.assertEqual(report["attribution"], "CURRENT_DATABASE_AND_SERVER_WAL_GLOBAL_ONLY")


if __name__ == "__main__":
    unittest.main()
