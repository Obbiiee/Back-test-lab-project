"""Authored native HistData replay integration, not real-provider fill acceptance."""
from copy import deepcopy
from dataclasses import asdict
import gzip
from pathlib import Path
import tempfile
import unittest

from application.models import TrustedScope
from contracts.primitives import ContractError
from execution.histdata_source import HistDataReplaySource
from execution.historical import IndexedTimelineCache
from market_data.context_warmup import FrameWarmup
from ticks.histdata_v2 import HistDataIngestion

START=1635724800*10**9


class HistDataSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        source=self.root/'EURUSD_2021-11.csv.gz'
        source.write_bytes(gzip.compress(b'timestamp_utc,bid,ask\n'
            b'2021-11-01T00:00:00.000Z,1.1,1.2\n'
            b'2021-11-01T00:01:00.000Z,1.2,1.3\n'
            b'2021-11-01T00:02:00.000Z,1.3,1.4\n'
            b'2021-11-01T00:02:00.000Z,1.4,1.5\n'
            b'2021-11-01T00:03:00.000Z,1.5,1.6\n',mtime=0))
        with HistDataIngestion(source,self.root/'store','EURUSD',first_rows=None,packing=(2,1,2)) as intake:
            self.report=intake.run()
        self.source=HistDataReplaySource(self.root/'store',self.report['datasetVersion'],'EURUSD',log_root=self.root/'logs')
        self.scope=TrustedScope('workspace:one','actor:one')
        self.cache=IndexedTimelineCache(self.source)

    def tearDown(self):
        self.cache.close();self.tmp.cleanup()

    def test_identity_and_period_selection_without_profile_fabrication(self):
        self.assertEqual(self.source.start_for_period('2021-11'),START)
        self.assertIn('UNKNOWN',self.source.label)
        self.assertFalse(hasattr(self.source,'profile'))
        with self.assertRaises(ContractError):
            HistDataReplaySource(self.root/'store',self.report['datasetVersion'],'GBPUSD',log_root=self.root/'wrong')
        for period in ['2021-12','2021-10','0000-01','2021-1']:
            with self.assertRaises(ContractError):self.source.start_for_period(period)

    def test_complete_tied_groups_and_scoped_cold_checkpoint_recovery(self):
        timeline=self.cache.new_timeline(self.scope,'session:one',START)
        checkpoint=timeline.checkpoint();self.cache.seed(self.scope,'session:one',timeline)
        result,saved=self.cache.reveal(self.scope,'session:one',checkpoint,str(START+120*10**9))
        self.assertEqual([len(g['events']) for g in result['groups']],[1,1,2])
        first=self.cache.window(self.scope,'session:one',saved)
        self.assertTrue(all(int(g['timeNs'])<=START+120*10**9 for g in first))
        self.assertTrue(all(e['quality']['freshness']=='UNKNOWN' for g in first for e in g['events']))
        self.cache.close();self.cache=IndexedTimelineCache(self.source)
        self.assertEqual(self.cache.window(self.scope,'session:one',saved),first)
        other=TrustedScope('workspace:two','actor:one')
        with self.assertRaises(ContractError):self.cache.window(other,'session:one',saved)
        self.assertEqual(self.cache.window(self.scope,'session:one',saved),first)

    def test_source_substitution_and_unknown_context_remain_explicit(self):
        timeline=self.cache.new_timeline(self.scope,'session:one',START)
        cp=timeline.checkpoint();self.cache.seed(self.scope,'session:one',timeline)
        forged=deepcopy(cp);forged['cursor']['datasetVersion']='f'*64
        with self.assertRaises(ContractError):self.cache.window(self.scope,'session:one',forged)
        context=self.source.context(FrameWarmup(60,2,1e-6),trusted_start_ns=START+180*10**9)
        self.assertEqual(context.ambiguous_buckets,1)
        self.assertEqual(context.coverage,'UNKNOWN');self.assertFalse(context.execution_authority)
        self.assertNotIn('folder',asdict(context))
        self.assertEqual(len(context.selection.candles),2)

    def test_prefix_is_not_admitted_as_full_source(self):
        with HistDataIngestion(self.root/'EURUSD_2021-11.csv.gz',self.root/'prefix',
                               'EURUSD',first_rows=1) as intake:
            report=intake.run()
        with self.assertRaises(ContractError) as error:
            HistDataReplaySource(self.root/'prefix',report['datasetVersion'],'EURUSD',
                                 log_root=self.root/'prefix-logs')
        self.assertEqual(error.exception.code,'REFUSED_PREFIX_AS_FULL_SOURCE')
