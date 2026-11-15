import json
import tempfile
import unittest
from pathlib import Path

from tools import ops_alert as a

GOOD = dict(host=dict(memAvailableGiB=8, swapUsedMiB=0, loadPerCpu=0.2, diskFreeGiB=120), database=dict(reachable=True, queueDepth=0, oldestQueuedWaitS=0, failedLastHour=0), backupAgeHours=3)
BAD = dict(GOOD, backupAgeHours=None)
WARN = dict(GOOD, backupAgeHours=30)


class Alert(unittest.TestCase):
    def test_decisions(self):
        self.assertIsNone(a.decide("OK", None, 0, 3600))
        self.assertEqual(a.decide("WARN", None, 0, 3600), "WARN")
        self.assertIsNone(a.decide("WARN", dict(status="WARN", at=100), 200, 3600))
        self.assertEqual(a.decide("WARN", dict(status="WARN", at=100), 4000, 3600), "WARN")
        self.assertEqual(a.decide("CRIT", dict(status="WARN", at=100), 200, 3600), "CRIT")
        self.assertEqual(a.decide("OK", dict(status="CRIT", at=100), 200, 3600), "RECOVERED")

    def test_command_is_called_once_per_incident_and_on_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "sent.log"
            env = dict(BTL_ALERT_STATE=str(Path(tmp) / "state.json"), BTL_ALERT_CMD=f"sh -c 'echo \"$0\" >> {log}' {{message}}", BTL_ALERT_REPEAT_S="3600")
            self.assertEqual(a.main(env, WARN)[0], "WARN")
            self.assertIsNone(a.main(env, WARN)[0])                      # suppressed
            self.assertEqual(a.main(env, BAD)[0], "CRIT")                # worse: immediate
            self.assertEqual(a.main(env, GOOD)[0], "RECOVERED")
            self.assertIsNone(a.main(env, GOOD)[0])
            sent = log.read_text().strip().splitlines()
            self.assertEqual(len(sent), 3)
            self.assertTrue(sent[0].startswith("RIKSORA WARN") and sent[1].startswith("RIKSORA CRIT") and sent[2].startswith("RIKSORA RECOVERED"))
            self.assertNotIn("postgresql://", log.read_text())


if __name__ == "__main__":
    unittest.main()
