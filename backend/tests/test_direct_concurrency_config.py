"""DIRECT_OPERATION_CONCURRENCY is configurable, default 3, bounded 1..8; nothing else about admission changes."""
import os
import unittest
from unittest.mock import patch

from cloud import research
from contracts.primitives import ContractError


class DirectConcurrencyConfig(unittest.TestCase):
    def test_default_is_three_when_unset_or_empty(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('BTL_DIRECT_OPERATION_CONCURRENCY', None)
            self.assertEqual(research.direct_operation_concurrency(), 3)
        with patch.dict(os.environ, {'BTL_DIRECT_OPERATION_CONCURRENCY': ''}):
            self.assertEqual(research.direct_operation_concurrency(), 3)
        self.assertEqual(research.DIRECT_OPERATION_CONCURRENCY, 3)

    def test_accepts_only_integers_from_one_to_eight(self):
        for good in ('1', '3', '4', '6', '8'):
            with patch.dict(os.environ, {'BTL_DIRECT_OPERATION_CONCURRENCY': good}):
                self.assertEqual(research.direct_operation_concurrency(), int(good))
        for bad in ('0', '9', '-1', '3.5', 'x', '１'):
            with patch.dict(os.environ, {'BTL_DIRECT_OPERATION_CONCURRENCY': bad}):
                with self.assertRaises(ContractError, msg=bad):
                    research.direct_operation_concurrency()


if __name__ == '__main__':
    unittest.main()
