"""Bounded worker-pool configuration checks; no worker jobs are started."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from cloud.worker_config import parse_worker_count


class WorkerPoolConfigurationTests(unittest.TestCase):
    def test_default_and_supported_counts_are_bounded(self):
        self.assertEqual(parse_worker_count(None), 2)
        self.assertEqual([parse_worker_count(str(value)) for value in range(1, 5)],
                         [1, 2, 3, 4])

    def test_invalid_values_fail_closed(self):
        for value in ("", "0", "5", "-1", "2.0", " 2", "02", 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_worker_count(value)

    def test_queue_and_native_slots_use_the_same_configured_count(self):
        backend = Path(__file__).resolve().parents[1]
        script = (
            "import json; from cloud import queue, worker; "
            "print(json.dumps({'queue':queue.WORKERS,'slots':len(worker._slots),"
            "'exchanges':worker._exchanges._max_workers}))"
        )
        for count in ("1", "2", "3", "4"):
            env = dict(os.environ, BTL_RESEARCH_WORKERS=count)
            completed = subprocess.run([sys.executable, "-c", script], cwd=backend,
                env=env, check=True, capture_output=True, text=True, timeout=10)
            self.assertEqual(json.loads(completed.stdout), {
                "queue": int(count), "slots": int(count), "exchanges": int(count)})

    def test_invalid_environment_stops_startup(self):
        backend = Path(__file__).resolve().parents[1]
        completed = subprocess.run([sys.executable, "-c", "import cloud.queue"],
            cwd=backend, env=dict(os.environ, BTL_RESEARCH_WORKERS="5"),
            capture_output=True, text=True, timeout=10)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("BTL_RESEARCH_WORKERS", completed.stderr)


if __name__ == "__main__":
    unittest.main()
