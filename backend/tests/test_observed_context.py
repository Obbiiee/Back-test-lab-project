"""Authored controller integration; prior OHLC is never execution evidence."""
from dataclasses import FrozenInstanceError
import hashlib
import json
import unittest
from unittest.mock import patch

from execution.observed_context import prepare_observed_context
from execution.observed_source import ObservedReplaySource
from market_data.context_archive import ContextFilePin, PinnedContextArchive
from market_data.context_warmup import IndicatorSpec
from tests import test_observed_source as fixtures

NS = 10**9


class ObservedContextTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ObservedSourceTests()
        self.fixture.setUp()
        self.root = self.fixture.root
        self.folder, self.pin = self.fixture.snapshot()
        self.source = ObservedReplaySource(self.folder, self.pin, log_root=self.root/'logs')
        self.refs = self.root/'refs'
        self.refs.mkdir()

    def tearDown(self):
        self.fixture.tearDown()

    def archive(self, rows, name='2025-01-1m.json'):
        path = self.refs/name
        raw = json.dumps(rows).encode()
        path.write_bytes(raw)
        pin = ContextFilePin(name, hashlib.sha256(raw).hexdigest(), rows[0][0]*NS, rows[-1][0]*NS)
        return PinnedContextArchive(self.refs, [pin])

    def rows(self, end, n, step=60):
        return [[end-(n-i)*step, '2.001', '2.003', '2.000', '2.002'] for i in range(n)]

    def test_actual_tick_start_clips_closed_buckets_and_keeps_identity_and_parent(self):
        start = self.fixture.start//NS
        rows = self.rows(start, 3)+[[start, '99', '100', '98', '99']]
        archive = self.archive(rows)
        before = hashlib.sha256((self.folder/'archive.sqlite').read_bytes()).hexdigest()
        result = prepare_observed_context(self.source, '2025-01', archive, [IndicatorSpec('SMA',60,period=3)])
        self.assertEqual((result.dataset_id,result.dataset_version,result.start_ns),
                         (self.pin.dataset_id,self.pin.dataset_version,self.fixture.start))
        plan, selection = result.reference_frames[0]
        self.assertEqual((plan.required_bars,selection.available_bars,selection.state),(3,3,'SUFFICIENT_COUNT'))
        self.assertTrue(all(b.close_ns<=result.start_ns for b in selection.candles))
        self.assertEqual(selection.candles[-1].close_ns,start*NS)
        self.assertFalse(selection.execution_authority)
        self.assertEqual(before,hashlib.sha256((self.folder/'archive.sqlite').read_bytes()).hexdigest())
        with self.assertRaises(FrozenInstanceError): result.start_ns=0

    def test_sparse_month_uses_actual_observation_not_calendar_first(self):
        end=self.fixture.march//NS
        archive=self.archive(self.rows(end,2),name='2025-03-1m.json')
        result=prepare_observed_context(self.source,'2025-03',archive,[IndicatorSpec('SMA',60,period=2)])
        self.assertEqual(result.start_ns,self.fixture.march)
        self.assertEqual(result.reference_frames[0][1].available_bars,2)

    def test_unavailable_period_and_invalid_request_never_read_reference_files(self):
        archive=PinnedContextArchive(self.refs,[])
        with patch.object(PinnedContextArchive,'select',side_effect=AssertionError('unexpected I/O')):
            with self.assertRaisesRegex(ValueError,'OBSERVED_PERIOD_UNAVAILABLE'):
                prepare_observed_context(self.source,'2025-02',archive,[IndicatorSpec('SMA',60)])
            with self.assertRaises(ValueError):
                prepare_observed_context(self.source,'2025-01',archive,[IndicatorSpec('UNKNOWN',60)])
            with self.assertRaises(ValueError):
                prepare_observed_context(self.source,'2025-01',None,[])

    def test_future_price_mutations_do_not_change_reference_output(self):
        start=self.fixture.start//NS
        rows=self.rows(start,2)+[[start,'10','11','9','10']]
        first=prepare_observed_context(self.source,'2025-01',self.archive(rows),[IndicatorSpec('SMA',60,period=2)])
        rows[-1][1:]=['bad','future','price','ignored']
        second=prepare_observed_context(self.source,'2025-01',self.archive(rows),[IndicatorSpec('SMA',60,period=2)])
        self.assertEqual(first,second)

    def test_same_frame_union_and_separate_frames_do_not_aggregate_or_fill_missing_history(self):
        start=self.fixture.start//NS
        one=self.archive(self.rows(start,3))
        # An absent 5m file remains absent; it is not constructed from 1m/ticks.
        result=prepare_observed_context(self.source,'2025-01',one,
              [IndicatorSpec('SMA',60,period=2),IndicatorSpec('SMA',60,period=4),IndicatorSpec('SMA',300,period=2)])
        self.assertEqual(len(result.reference_frames),2)
        self.assertEqual([(p.timeframe_seconds,p.required_bars,s.available_bars,s.state) for p,s in result.reference_frames],
                         [(60,4,3,'WARMUP_INCOMPLETE'),(300,2,0,'WARMUP_INCOMPLETE')])

    def test_no_indicators_no_reference_io_and_corrupt_past_refused_without_tick_fallback(self):
        archive=PinnedContextArchive(self.refs,[])
        with patch.object(PinnedContextArchive,'select',side_effect=AssertionError('unexpected I/O')):
            self.assertEqual(prepare_observed_context(self.source,'2025-01',archive,[]).reference_frames,())
        rows=self.rows(self.fixture.start//NS,2);rows[0][2]='1.0'
        with self.assertRaisesRegex(ValueError,'OHLC envelope'):
            prepare_observed_context(self.source,'2025-01',self.archive(rows),[IndicatorSpec('SMA',60,period=2)])
