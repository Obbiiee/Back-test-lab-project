"""Bounded compatibility catalog windows remain explicitly pageable."""
import unittest

from execution.catalog_window import catalog_window


class CatalogWindowTests(unittest.TestCase):
    def test_oversized_catalog_returns_window_and_preserves_next_key(self):
        rows = [(f'item:{index:03d}', {'id': index}) for index in range(130)]
        page, more = catalog_window(rows)
        self.assertEqual(len(page), 128)
        self.assertTrue(more)
        self.assertEqual(page[-1][0], 'item:127')
        self.assertEqual(rows[len(page)][0], 'item:128')

    def test_complete_catalog_does_not_advertise_more_pages(self):
        rows = [(f'item:{index:03d}', {'id': index}) for index in range(128)]
        page, more = catalog_window(rows)
        self.assertEqual(page, rows)
        self.assertFalse(more)


if __name__ == '__main__':
    unittest.main()
