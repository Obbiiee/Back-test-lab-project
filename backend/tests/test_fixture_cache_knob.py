"""BTL_FIXTURE_CACHE_ENTRIES: default 16 (contract), bounded 1..512, ASCII digits only, forwarded to the native worker."""
import os
import unittest
from unittest.mock import patch

from contracts.primitives import ContractError
from execution import workspace


class FixtureCacheKnob(unittest.TestCase):
    def test_default_and_range(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('BTL_FIXTURE_CACHE_ENTRIES', None)
            self.assertEqual(workspace.fixture_cache_entries(), 16)
        self.assertEqual(workspace.FIXTURE_CACHE_ENTRIES_DEFAULT, 16)
        for good in ('1', '16', '64', '512'):
            with patch.dict(os.environ, {'BTL_FIXTURE_CACHE_ENTRIES': good}):
                self.assertEqual(workspace.fixture_cache_entries(), int(good))
        for bad in ('0', '513', '-1', '2.5', 'x', '６４'):
            with patch.dict(os.environ, {'BTL_FIXTURE_CACHE_ENTRIES': bad}):
                with self.assertRaises(ContractError, msg=bad):
                    workspace.fixture_cache_entries()

    def test_worker_environment_forwards_a_valid_value_only(self):
        from cloud import worker
        src = open(worker.__file__, encoding='utf8').read()
        self.assertIn("'BTL_FIXTURE_CACHE_ENTRIES'", src)
        self.assertIn("fixtureCacheEntries", src)


if __name__ == '__main__':
    unittest.main()
