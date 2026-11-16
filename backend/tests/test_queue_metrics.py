import unittest
from datetime import datetime, timedelta, timezone

from cloud.queue import _queue_wait_measurements
from contracts.canonical import content_hash


class QueueMetricsTests(unittest.TestCase):
    def test_wait_uses_exact_microsecond_delta_and_content_hash(self):
        created = datetime(2026, 11, 6, 1, tzinfo=timezone.utc)
        claimed = created + timedelta(seconds=2, microseconds=17)
        raw, digest = _queue_wait_measurements(created, claimed)
        import json
        value = json.loads(raw)
        self.assertEqual(value['waitMicroseconds'], 2_000_017)
        self.assertEqual(digest, content_hash(value))

    def test_naive_or_inverted_timestamps_fail_closed(self):
        created = datetime(2026, 11, 6, 1, tzinfo=timezone.utc)
        for start, end in ((created.replace(tzinfo=None), created),
                           (created, created - timedelta(microseconds=1))):
            with self.subTest(start=start, end=end):
                self.assertEqual(_queue_wait_measurements(start, end), (None, None))


if __name__ == '__main__':
    unittest.main()
