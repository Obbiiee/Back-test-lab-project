"""Native authored disk ticks; no real-source execution or hosted acceptance."""
from dataclasses import asdict
import gzip
from pathlib import Path
import tempfile
import unittest

from contracts.primitives import ContractError
from market_data.context_warmup import FrameWarmup
from market_data.tick_context import load_tick_context
from ticks.histdata_v2 import HistDataIngestion
from ticks.storage_v2 import DiskTickProvider
from ticks.provider import Cancellation

NS = 1000000000
START = 1635724800  # 2021-11-01T00:00:00Z


class TickContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.path = Path(self.tmp.name); self.handles=[]

    def tearDown(self):
        for provider in self.handles: provider.close()
        self.tmp.cleanup()

    def provider(self, rows, name='a'):
        from datetime import datetime, timezone
        directory = self.path/name; directory.mkdir()
        source=directory/'EURUSD_2021-11.csv.gz'
        text='timestamp_utc,bid,ask\n'
        for seconds, bid in rows:
            stamp=datetime.fromtimestamp(START+seconds,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            text+=f'{stamp},{bid},20\n'
        source.write_bytes(gzip.compress(text.encode(),mtime=0))
        with HistDataIngestion(source,directory/'store','EURUSD',first_rows=None,packing=(2,1,2)) as intake:
            report=intake.run()
        provider=DiskTickProvider(directory/'store',report['datasetVersion']);self.handles.append(provider)
        return provider

    def load(self, provider, **kwargs):
        return load_tick_context(provider, FrameWarmup(60,2,1e-6),
                                 trusted_start_ns=(START+180)*NS,**kwargs)

    def test_exact_bid_ohlc_completed_and_future_invariance(self):
        past=[(0,'10.00001'),(20,'12.00001'),(59,'9.00001'),(60,'11'),(80,'13'),(119,'12'),(120,'10'),(179,'11')]
        a=self.load(self.provider(past+[(180,'15')]))
        b=self.load(self.provider(past+[(180,'19'),(300,'18')],'b'))
        self.assertEqual(asdict(a),asdict(b))
        self.assertEqual(a.selection.state,'SUFFICIENT_COUNT')
        self.assertEqual([(c.open,c.high,c.low,c.close) for c in a.selection.candles],
                         [('11','13','11','12'),('10','11','10','11')])
        self.assertTrue(all(c.close_ns<=(START+180)*NS for c in a.selection.candles))
        self.assertFalse(a.execution_authority);self.assertEqual(a.coverage,'UNKNOWN')
        self.assertNotIn('datasetVersion',asdict(a)); self.assertNotIn('provider',asdict(a))

    def test_ambiguous_group_across_physical_chunks_omits_bucket(self):
        p=self.provider([(0,'10'),(60,'11'),(60,'12'),(60,'11'),(120,'13')])
        a=self.load(p)
        self.assertEqual(a.ambiguous_buckets,1)
        self.assertEqual([c.open for c in a.selection.candles],['10','13'])
        self.assertEqual(a.coverage,'UNKNOWN')

    def test_identical_ties_and_missing_buckets_not_filled(self):
        p=self.provider([(0,'10'),(0,'10'),(120,'13')])
        a=self.load(p);self.assertEqual(a.ambiguous_buckets,0)
        self.assertEqual(len(a.selection.candles),2)
        b=load_tick_context(p,FrameWarmup(60,3,1e-6),trusted_start_ns=(START+180)*NS)
        self.assertEqual(b.selection.state,'WARMUP_INCOMPLETE')

    def test_partial_bucket_excluded_and_empty_context(self):
        p=self.provider([(0,'10'),(60,'11'),(120,'12'),(130,'19')])
        a=load_tick_context(p,FrameWarmup(60,2,1e-6),trusted_start_ns=(START+135)*NS)
        self.assertEqual([c.open for c in a.selection.candles],['10','11'])
        empty=load_tick_context(p,FrameWarmup(60,2,1e-6),trusted_start_ns=0)
        self.assertEqual(empty.selection.state,'WARMUP_INCOMPLETE')

    def test_read_budgets_fail_without_partial_success(self):
        p=self.provider([(0,'10'),(10,'11'),(60,'12'),(120,'13'),(180,'14')])
        for kwargs in [dict(max_events=2),dict(max_pages=1)]:
            with self.assertRaises(ContractError) as error:self.load(p,**kwargs)
            self.assertEqual(error.exception.code,'CONTEXT_BUDGET_EXCEEDED')
        for kwargs in [dict(max_events=True),dict(max_pages=0),dict(lookback_buckets=1)]:
            with self.assertRaises(ContractError):self.load(p,**kwargs)

    def test_cancellation_and_lookup_near_end(self):
        p=self.provider([(0,'10'),(60,'11')]); cancel=Cancellation(cancelled=True)
        with self.assertRaises(ContractError):self.load(p,cancellation=cancel)
        a=load_tick_context(p,FrameWarmup(60,2,1e-6),trusted_start_ns=(START+3600)*NS)
        self.assertEqual(a.selection.available_bars,0)

    def test_mid_read_cancellation_and_invalid_controller_inputs(self):
        class MidReadCancellation(Cancellation):
            calls=0
            def check(self):
                self.calls+=1
                self.cancelled=self.calls>=5
                super().check()
        p=self.provider([(0,'10'),(10,'11'),(60,'12'),(120,'13')])
        with self.assertRaises(ContractError) as error:self.load(p,cancellation=MidReadCancellation())
        self.assertEqual(error.exception.code,'CANCELLED')
        with self.assertRaises(ContractError):self.load(object())
        for value in [True,-1,2**63]:
            with self.assertRaises(ContractError):
                load_tick_context(p,FrameWarmup(60,2,1e-6),trusted_start_ns=value)
