"""Authored reference-file tests; no source admission or execution authority."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from market_data.context_archive import ContextFilePin, PinnedContextArchive
from market_data.context_warmup import FrameWarmup

NS = 1000000000


class ContextArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.plan = FrameWarmup(60, 2, 1e-6)

    def file(self, name='2023-12-1m.json', rows=None):
        rows = rows or [[0, '10.001', '11.002', '9.003', '10.004'],
                        [60, '10.005', '11.006', '9.007', '10.008']]
        raw = json.dumps(rows).encode()
        (self.folder / name).write_bytes(raw)
        return ContextFilePin(name, hashlib.sha256(raw).hexdigest(), rows[0][0]*NS, rows[-1][0]*NS)

    def test_exact_json_decimal_tokens_and_completed_cutoff(self):
        raw = b'[[0,10.000000000000000001,11,9,10.000000000000000002],[60,10,11,9,10]]'
        name = '2023-12-1m.json'; (self.folder / name).write_bytes(raw)
        pin = ContextFilePin(name, hashlib.sha256(raw).hexdigest(), 0, 60*NS)
        result = PinnedContextArchive(self.folder, [pin]).select(self.plan, trusted_start_ns=120*NS)
        self.assertEqual(result.candles[0].open, '10.000000000000000001')
        self.assertEqual(result.candles[0].close, '10.000000000000000002')
        self.assertEqual(result.state, 'SUFFICIENT_COUNT')
        self.assertFalse(result.execution_authority)
        partial = PinnedContextArchive(self.folder, [pin]).select(self.plan, trusted_start_ns=119*NS)
        self.assertEqual(partial.available_bars, 1)
        self.assertEqual(partial.state, 'WARMUP_INCOMPLETE')

    def test_future_price_mutation_and_future_file_do_not_change_selection(self):
        prefix = [[0,10,11,9,10],[60,10,11,9,10]]
        a = self.file(rows=prefix+[[120,10,11,9,10]])
        first = PinnedContextArchive(self.folder, [a]).select(self.plan, trusted_start_ns=120*NS)
        b = self.file(rows=prefix+[[120,'future','NaN',None,False]])
        future = ContextFilePin('2024-01-1m.json', 'f'*64, 180*NS, 240*NS)
        second = PinnedContextArchive(self.folder, [b, future]).select(self.plan, trusted_start_ns=120*NS)
        self.assertEqual(first, second)  # Missing future file is never opened.

    def test_hash_extent_order_and_ohlc_corruption_refused(self):
        pin = self.file(); archive = PinnedContextArchive(self.folder, [pin])
        (self.folder / pin.name).write_bytes(b'[]')
        with self.assertRaisesRegex(ValueError, 'hash'): archive.select(self.plan, trusted_start_ns=120*NS)
        pin = self.file(rows=[[60,10,11,9,10],[0,10,11,9,10]])
        with self.assertRaises(ValueError): PinnedContextArchive(self.folder, [pin])
        pin = self.file(rows=[[0,10,11,9,10],[60,10,8,9,10]])
        with self.assertRaisesRegex(ValueError, 'OHLC'): PinnedContextArchive(self.folder, [pin]).select(self.plan, trusted_start_ns=120*NS)
        pin = self.file()
        altered = ContextFilePin(pin.name, pin.sha256, 0, 120*NS)
        with self.assertRaisesRegex(ValueError, 'extent'): PinnedContextArchive(self.folder, [altered]).select(self.plan, trusted_start_ns=180*NS)

    def test_paths_symlinks_duplicate_and_overlapping_pins_refused(self):
        pin = self.file()
        for name in ['../2023-12-1m.json', '/tmp/2023-12-1m.json', '2023-13-1m.json']:
            with self.assertRaises(ValueError): PinnedContextArchive(self.folder, [ContextFilePin(name,pin.sha256,0,60*NS)])
        with self.assertRaises(ValueError): PinnedContextArchive(self.folder, [pin,pin])
        other = self.file('2023-11-1m.json')
        with self.assertRaisesRegex(ValueError, 'Overlapping'): PinnedContextArchive(self.folder, [pin,other]).select(self.plan,trusted_start_ns=120*NS)
        (self.folder / pin.name).unlink(); (self.folder / pin.name).symlink_to(self.folder / other.name)
        with self.assertRaises(OSError): PinnedContextArchive(self.folder,[pin]).select(self.plan,trusted_start_ns=120*NS)

    def test_byte_row_and_file_limits(self):
        pin = self.file()
        with patch('market_data.context_archive.MAX_FILE_BYTES', 2):
            with self.assertRaisesRegex(ValueError, 'byte bound'): PinnedContextArchive(self.folder,[pin]).select(self.plan,trusted_start_ns=120*NS)
        with patch('market_data.context_archive.MAX_FILE_ROWS', 1):
            with self.assertRaisesRegex(ValueError, 'row bound'): PinnedContextArchive(self.folder,[pin]).select(self.plan,trusted_start_ns=120*NS)
        other = self.file('2024-01-1m.json', [[120,10,11,9,10]])
        with patch('market_data.context_archive.MAX_FILES', 1):
            result= PinnedContextArchive(self.folder,[pin,other]).select(self.plan,trusted_start_ns=180*NS)
            self.assertEqual(result.available_bars,1)
            self.assertEqual(result.state,'WARMUP_INCOMPLETE')

    def test_gaps_not_interpolated_and_request_checked_before_io(self):
        pin=self.file(rows=[[0,10,11,9,10],[180,10,11,9,10]])
        result=PinnedContextArchive(self.folder,[pin]).select(self.plan,trusted_start_ns=240*NS)
        self.assertEqual([b.open_ns for b in result.candles],[0,180*NS])
        self.assertEqual(PinnedContextArchive(self.folder,[]).select(self.plan,trusted_start_ns=0).available_bars,0)
        with self.assertRaises(ValueError): PinnedContextArchive(self.folder,[pin]).select(self.plan,trusted_start_ns=-1)


if __name__ == '__main__': unittest.main()
