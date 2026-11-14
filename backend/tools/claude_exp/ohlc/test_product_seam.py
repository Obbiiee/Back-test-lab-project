"""Product seam: BTL-PAST-CHART-CONTEXT-1 served from precomputed objects equals the independent oracle (previous month only)."""
import os
import sys
import unittest
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from execution import claude_ohlc_seam as seam                                  # noqa: E402
from tools.claude_exp.ohlc import oracle                                        # noqa: E402
from tools.claude_exp.ohlc.test_service import build_world, ts, CANARY_2S       # noqa: E402

FIELDS = set('schemaVersion artifact datasetId datasetVersion startTime endTime timeframe priceBasis volumeAvailable coverage executionAuthority status candles nextOffset'.split())


class Seam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ticks, cls.cut, cls.reader, cls.store, cls.src = build_world()
        cls.env = mock.patch.dict(os.environ, BTL_CLAUDE_OHLC_ROOT=str(cls.store.root), BTL_CLAUDE_OHLC_INSTRUMENT='TESTUSD')
        cls.env.start()
        cls.state = dict(startNs=str(ts('2026-05-04T00:00:00')), datasetId='local:test:svc', datasetVersion='b' * 64)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()

    def pages(self, tf):
        out, off = [], 0
        while True:
            p = seam.past_context(self.state, tf, off)
            self.assertEqual(set(p), FIELDS)
            out += p['candles']
            if p['nextOffset'] is None:
                return p, out
            self.assertEqual(p['nextOffset'], off + 512)
            self.assertEqual(len(p['candles']), 512)
            off = p['nextOffset']

    def test_all_timeframes_equal_oracle_previous_month_only(self):
        start, end = int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp()), int(datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp())
        for tf, name in seam.TF.items():
            w = seam.SECONDS[tf]
            exp = [b for b in oracle.aggregate(self.ticks, w) if start <= b['t'] // 10**9 and b['t'] // 10**9 + w <= end]
            p, got = self.pages(tf)
            self.assertEqual((p['startTime'], p['endTime'], p['priceBasis'], p['executionAuthority'], p['coverage']),
                             (start, end, 'EXACT_REVEALED_MID_DISPLAY_ONLY', False, 'UNKNOWN'))
            self.assertEqual(len(got), len(exp), tf)
            for g, e in zip(got, exp):
                self.assertEqual(g['time'], e['t'] // 10**9)
                for k, f in (('open', 'o'), ('high', 'h'), ('low', 'l'), ('close', 'c')):
                    self.assertEqual(Fraction(g[k]), e[f], (tf, g['time'], k))

    def test_no_future_or_canary_bytes(self):
        for tf in seam.TF:
            _, got = self.pages(tf)
            self.assertTrue(all(c['time'] < int(datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp()) for c in got))
            self.assertNotIn('7.7778', repr(got))

    def test_refusals_and_flag(self):
        for bad in (('2m', 0), ('1m', -1), ('1m', 50001), ('1m', '0')):
            with self.assertRaises(Exception):
                seam.past_context(self.state, *bad)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('BTL_CLAUDE_OHLC_ROOT')
            self.assertFalse(seam.enabled())
        self.assertEqual(seam.past_context(dict(self.state, startNs=str(ts('2026-09-02T00:00:00'))), '1h', 0)['candles'], [])


if __name__ == '__main__':
    unittest.main()
