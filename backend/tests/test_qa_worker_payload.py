import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.qa_historical_day_v2 import _persist_worker_payload


class ColdResumeWorkerPayloadTests(unittest.TestCase):
    def test_annual_payload_reproduces_e2big_and_file_reference_starts_worker(self):
        if not sys.platform.startswith('linux'):
            self.skipTest('E2BIG per-string reproduction is Linux-specific')
        with tempfile.TemporaryDirectory(prefix='riksora-worker-payload-') as temporary:
            root = Path(temporary)
            payload = dict(
                dsn='postgresql://qa_root:fixture@/postgres?host=/tmp/qa/socket&port=55439',
                root=str(root), source='/qa/source/archive', proof='/qa/proof.json',
                proofHash='a' * 64, workspace='observedqa:hist-v2:annual-fixture',
                actor='fixture:internal-qa', session='session:hist-v2:annual-fixture',
                dayEnd='1735689599999999999',
                decisionTargets={str(index): str(1704067200000000000 + index)
                                 for index in range(8784)},
                orderDecisionStages=list(range(0, 8784, 6)), eodNs='1735686000000000000',
                dayHours=8784, orderRetentionPolicy={'maxCumulativeOrders': 4096},
                qaStateDeltaV3=True, qaOrderArchiveV1=True,
                stopAfterCompletedTrades=0, partialProbeState=None)
            raw = json.dumps(payload, sort_keys=True, separators=(',', ':'))
            self.assertGreater(len(raw.encode()), 131072)
            with self.assertRaises(OSError) as raised:
                subprocess.run([sys.executable, '-c', 'pass'],
                               env=dict(os.environ, BTL_HISTORICAL_DAY_V2_WORKER=raw),
                               check=True, timeout=10)
            self.assertEqual(raised.exception.errno, errno.E2BIG)

            payload_path, digest = _persist_worker_payload(root, payload)
            self.assertEqual(payload_path.stat().st_mode & 0o777, 0o600)
            env = dict(os.environ,
                       BTL_HISTORICAL_QA_ROOT=str(root),
                       BTL_HISTORICAL_DAY_V2_WORKER_FILE=str(payload_path),
                       BTL_HISTORICAL_DAY_V2_WORKER_SHA256=digest,
                       PYTHONPATH=str(Path(__file__).resolve().parents[1]),
                       PYTHONDONTWRITEBYTECODE='1')
            completed = subprocess.run(
                [sys.executable, '-B', '-m', 'tests.qa_historical_day_v2',
                 '--validate-worker-payload'], env=env, capture_output=True,
                text=True, timeout=20, check=True)
            result = json.loads(completed.stdout)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['decisionTargetCount'], 8784)
            self.assertEqual(result['sessionId'], payload['session'])

    def test_payload_hash_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='riksora-worker-payload-') as temporary:
            root = Path(temporary)
            path, digest = _persist_worker_payload(root, {'session': 'session:test'})
            path.write_text('{"session":"session:tampered"}')
            os.chmod(path, 0o600)
            env = dict(os.environ, BTL_HISTORICAL_QA_ROOT=str(root),
                       BTL_HISTORICAL_DAY_V2_WORKER_FILE=str(path),
                       BTL_HISTORICAL_DAY_V2_WORKER_SHA256=digest,
                       PYTHONPATH=str(Path(__file__).resolve().parents[1]),
                       PYTHONDONTWRITEBYTECODE='1')
            completed = subprocess.run(
                [sys.executable, '-B', '-m', 'tests.qa_historical_day_v2',
                 '--validate-worker-payload'], env=env, capture_output=True,
                text=True, timeout=20)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn('COLD_RESUME_WORKER_PAYLOAD_HASH_MISMATCH', completed.stderr)


if __name__ == '__main__':
    unittest.main()
