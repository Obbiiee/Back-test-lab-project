"""No financial admission or future projection from pinned controller replay."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import sqlite3
import tempfile
import unittest

from application.models import TrustedScope
from execution.historical import IndexedTimelineCache
from execution.observed_source import ObservedDatasetPin, ObservedReplaySource
from ticks.compact_v2 import CompactDatasetBuilder
from ticks.contracts import event_id
from ticks.contracts_v2 import ZERO_VERSION
from ticks.provider import SyntheticTickProvider
from ticks.storage_v2 import DatasetBuilder


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def at(year, month, day):
    return (datetime(year, month, day, tzinfo=timezone.utc)-EPOCH).days*86400*10**9


class ObservedSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.start = at(2025, 1, 2)+50_000_000
        self.march = at(2025, 3, 3)

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self, name='source #?', compact=False, observation=True):
        times = [self.start, self.start, self.start+10**9, self.march]
        fixture = SyntheticTickProvider([dict(ordinal=str(i), timeNs=str(t), bid='1.001', ask='1.003', sequence=None)
                                         for i, t in enumerate(times)])
        description = fixture.describe(fixture.dataset_id, fixture.dataset_version)
        meta = {k: description[k] for k in ('datasetId', 'providerId', 'feedId', 'instrumentId',
                'providerSymbol', 'evidenceClass', 'adapterVersion', 'validatorVersion', 'ordering')}
        meta.update(providerId='authored-observation-qa', feedId='fixture:xauusd',
                    instrumentId='fixture:XAUUSD', providerSymbol='XAUUSD', adapterVersion='AUTHORED-OBSERVATION-QA-1')
        if observation:
            meta['evidenceClass'] = 'PROVIDER_OBSERVATION'
        sources = description['sources']
        events = fixture.read_page(fixture.dataset_id, fixture.dataset_version, None, 4)['events']
        cls = CompactDatasetBuilder if compact else DatasetBuilder
        folder = self.root/name
        builder = cls(folder, meta, sources, {'authoredFixture': True})
        try:
            for i, raw in enumerate(events):
                e = deepcopy(raw)
                e.update(datasetVersion=ZERO_VERSION, providerId=meta['providerId'], feedId=meta['feedId'],
                         instrumentId=meta['instrumentId'], eventId=event_id(meta['providerId'], meta['feedId'], sources[0]['memberHash'], str(i)))
                e['quality'].update(freshness='UNKNOWN', gapBefore='UNKNOWN_SILENCE')
                builder.append(e)
            version = builder.finish()
            builder.store.db.execute('PRAGMA journal_mode=DELETE')
        finally:
            builder.store.close()
        pin = ObservedDatasetPin(meta['datasetId'], version, meta['providerId'], meta['feedId'],
                                 meta['instrumentId'], meta['providerSymbol'])
        return folder, pin

    def test_both_layouts_select_requested_month_without_financial_profile_or_source_writes(self):
        for compact in (False, True):
            folder, pin = self.snapshot(str(compact), compact=compact)
            file = folder/'archive.sqlite'
            before = hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_mtime_ns
            source = ObservedReplaySource(folder, pin, log_root=self.root/'logs')
            self.assertEqual(source.start_for_period('2025-01'), self.start)
            self.assertEqual(source.start_for_period('2025-03'), self.march)
            self.assertEqual(source.execution_eligibility, 'NOT_GRANTED')
            self.assertFalse(hasattr(source, 'profile'))
            self.assertEqual((hashlib.sha256(file.read_bytes()).hexdigest(), file.stat().st_mtime_ns), before)
            self.assertEqual([f.name for f in folder.iterdir()], ['archive.sqlite'])

    def test_empty_month_never_shifts_to_a_later_month_or_another_year(self):
        folder, pin = self.snapshot()
        source = ObservedReplaySource(folder, pin, log_root=self.root/'logs')
        for period in ('2024-12', '2025-02', '2025-04', '2026-01'):
            with self.subTest(period=period), self.assertRaisesRegex(ValueError, 'OBSERVED_PERIOD_UNAVAILABLE'):
                source.start_for_period(period)

    def test_calendar_and_type_validation_precedes_index_use(self):
        folder, pin = self.snapshot()
        source = ObservedReplaySource(folder, pin, log_root=self.root/'logs')
        for period in (None, 202501, '2025-1', '2025-13', '0000-01', '2025-01/../../', '9999-12'):
            with self.subTest(period=period), self.assertRaises(ValueError):
                source.start_for_period(period)

    def test_immutable_pin_and_every_source_identity_are_checked(self):
        folder, pin = self.snapshot()
        with self.assertRaises(FrozenInstanceError):
            pin.provider_symbol = 'XAUUSDm'
        for changes in (dict(dataset_id='wrong:dataset'), dict(dataset_version='0'*64),
                        dict(provider_id='wrong-provider'), dict(feed_id='wrong-feed'),
                        dict(instrument_id='wrong:instrument'), dict(provider_symbol='XAUUSDm')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ObservedReplaySource(folder, replace(pin, **changes), log_root=self.root/'logs')
        with self.assertRaises(ValueError):
            ObservedReplaySource(folder, dict(pin.__dict__), log_root=self.root/'logs')
        self.assertFalse((self.root/'logs').exists())

    def test_synthetic_contract_is_not_relabelled_as_observations(self):
        folder, pin = self.snapshot(observation=False)
        with self.assertRaisesRegex(ValueError, 'REFUSED_OBSERVED_SOURCE'):
            ObservedReplaySource(folder, pin, log_root=self.root/'logs')

    def test_live_wal_snapshot_is_refused_instead_of_checkpointed(self):
        folder, pin = self.snapshot()
        db = sqlite3.connect(folder/'archive.sqlite')
        try:
            db.execute('PRAGMA journal_mode=WAL')
            before = hashlib.sha256((folder/'archive.sqlite').read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, 'READ_ONLY_SNAPSHOT_REQUIRED'):
                ObservedReplaySource(folder, pin, log_root=self.root/'logs')
            self.assertEqual(hashlib.sha256((folder/'archive.sqlite').read_bytes()).hexdigest(), before)
        finally:
            db.close()

    def test_symlink_or_source_log_overlap_is_refused(self):
        folder, pin = self.snapshot()
        link = self.root/'linked'
        link.symlink_to(folder, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'SOURCE_PATH_REFUSED'):
            ObservedReplaySource(link, pin, log_root=self.root/'logs')
        with self.assertRaisesRegex(ValueError, 'SOURCE_LOG_OVERLAP'):
            ObservedReplaySource(folder, pin, log_root=folder/'logs')
        self.assertFalse((folder/'logs').exists())

    def test_existing_cache_reveals_atomic_past_only_and_recovers_committed_window(self):
        folder, pin = self.snapshot(compact=True)
        source = ObservedReplaySource(folder, pin, log_root=self.root/'logs')
        scope = TrustedScope('workspace:observed-qa', 'actor:observed-qa')
        cache = IndexedTimelineCache(source)
        try:
            timeline = cache.new_timeline(scope, 'session:observed', source.start_for_period('2025-01'))
            checkpoint = timeline.checkpoint()
            cache.seed(scope, 'session:observed', timeline)
            step, checkpoint = cache.reveal(scope, 'session:observed', checkpoint, str(self.start+60*10**9))
            self.assertEqual([len(g['events']) for g in step['groups']], [2, 1])
            before = cache.window(scope, 'session:observed', checkpoint)
            self.assertTrue(all(int(g['timeNs']) < self.march for g in before))
            self.assertTrue(all(e['trustedSequence'] is None and e['quality']['freshness'] == 'UNKNOWN'
                                for g in before for e in g['events']))
            cache.close()
            cache = IndexedTimelineCache(source)
            self.assertEqual(cache.window(scope, 'session:observed', checkpoint), before)
        finally:
            cache.close()
