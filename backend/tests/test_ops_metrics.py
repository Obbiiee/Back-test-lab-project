import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools import ops_metrics as m

DSN = os.getenv("BTL_TEST_DATABASE_URL")
GOOD = dict(host=dict(memAvailableGiB=8, swapUsedMiB=0, loadPerCpu=0.2, diskFreeGiB=120),
            database=dict(reachable=True, queueDepth=0, oldestQueuedWaitS=0, failedLastHour=0), backupAgeHours=3)


class Evaluate(unittest.TestCase):
    def test_ok_and_each_threshold(self):
        self.assertEqual(m.evaluate(GOOD), ("OK", []))
        def with_(path, value):
            import copy
            s = copy.deepcopy(GOOD); a, b = path; s[a][b] = value if b != "backupAgeHours" else value; return s
        self.assertEqual(m.evaluate(with_(("host", "swapUsedMiB"), 5))[0], "CRIT")
        self.assertEqual(m.evaluate(with_(("host", "memAvailableGiB"), 1.5))[0], "WARN")
        self.assertEqual(m.evaluate(with_(("host", "memAvailableGiB"), 0.5))[0], "CRIT")
        self.assertEqual(m.evaluate(with_(("host", "diskFreeGiB"), 35))[0], "WARN")
        self.assertEqual(m.evaluate(with_(("host", "diskFreeGiB"), 20))[0], "CRIT")
        self.assertEqual(m.evaluate(with_(("database", "queueDepth"), 9))[0], "WARN")
        self.assertEqual(m.evaluate(with_(("database", "oldestQueuedWaitS"), 130))[0], "CRIT")
        self.assertEqual(m.evaluate(with_(("database", "failedLastHour"), 10))[0], "CRIT")
        s = dict(GOOD, backupAgeHours=None); self.assertEqual(m.evaluate(s)[0], "CRIT")
        s = dict(GOOD, backupAgeHours=30); self.assertEqual(m.evaluate(s)[0], "WARN")
        s = dict(GOOD, database=dict(reachable=False)); self.assertEqual(m.evaluate(s)[0], "CRIT")


@unittest.skipUnless(DSN, "Real isolated PostgreSQL required; skip is not PASS")
class Live(unittest.TestCase):
    def test_script_reports_the_real_queue_and_exits_with_the_status(self):
        from infrastructure.database import migrate
        migrate(DSN)
        marker = Path(tempfile.mkdtemp()) / "backup.ok"; marker.write_text("x")
        env = dict(os.environ, BTL_DATABASE_URL=DSN, BTL_BACKUP_MARKER=str(marker))
        out = subprocess.run([sys.executable, "-I", "tools/ops_metrics.py"], capture_output=True, text=True, env=env, cwd=Path(__file__).resolve().parents[1])
        snap = json.loads(out.stdout)
        self.assertTrue(snap["database"]["reachable"])
        self.assertIn("queueDepth", snap["database"])
        self.assertLess(snap["backupAgeHours"], 1)
        self.assertEqual(out.returncode, {"OK": 0, "WARN": 1, "CRIT": 2}[snap["status"]])
        self.assertNotIn("postgresql://", out.stdout)


if __name__ == "__main__":
    unittest.main()
