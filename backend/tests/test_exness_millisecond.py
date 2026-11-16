"""Native Exness timestamp precision without changing the legacy reader."""
from pathlib import Path
import tempfile
import unittest

from ticks.exness_v2 import ExnessIngestion, ExnessMillisecondIngestion
from ticks.storage_v2 import DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline


class ExnessMillisecondTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, stamps):
        p = self.root / 'original.csv'
        p.write_text('Exness,Symbol,Timestamp,Bid,Ask\n' + ''.join(
            f'exness,XAUUSD,{stamp},2625.100,2625.210\n' for stamp in stamps))
        return p

    def ingest(self, cls, source, name='store', **kwargs):
        ingestion = cls(source, self.root / name, **kwargs)
        try:
            report = ingestion.run()
            sources = ingestion.builder.sources
        finally:
            ingestion.builder.store.close()
        return report, sources

    def events(self, name, report):
        provider = DiskTickProvider(self.root / name, report['datasetVersion'])
        try:
            position = provider.locate_v2(provider.dataset_id, provider.dataset_version, '0')['position']
            events = []
            while position is not None:
                page = provider.read_page_v2(provider.dataset_id, provider.dataset_version, position, 256)
                events.extend(page['events'])
                position = page['nextPosition']
            return events
        finally:
            provider.close()

    def test_exact_milliseconds_original_text_and_unknown_quality(self):
        stamps = ['2025-01-02 00:00:00.001Z', '2025-01-02 00:00:00.999Z',
                  '2025-01-02 00:00:01.000Z']
        report, sources = self.ingest(ExnessMillisecondIngestion, self.source(stamps))
        events = self.events('store', report)
        self.assertEqual([e['timeNs'] for e in events],
                         ['1735776000001000000', '1735776000999000000', '1735776001000000000'])
        self.assertEqual([e['provenance']['originalTimestamp'] for e in events], stamps)
        self.assertEqual(report['fractional000'], 1)
        self.assertEqual(report['sourceResolutionNs'], '1000000')
        self.assertEqual(sources[0]['originalScalePolicy'], 'PRESERVE_RAW_TEXT')
        for e in events:
            self.assertEqual(e['bid'], '2625.1')
            self.assertEqual(e['resolutionNs'], '1000000')
            self.assertIsNone(e['trustedSequence'])
            self.assertEqual(e['quality']['freshness'], 'UNKNOWN')
            self.assertEqual(e['quality']['gapBefore'], 'UNKNOWN_SILENCE')

    def test_legacy_policy_metadata_and_millisecond_refusal_unchanged(self):
        p = self.source(['2025-01-02 00:00:00.000Z'])
        report, sources = self.ingest(ExnessIngestion, p)
        self.assertEqual(report['sourceResolutionNs'], '1000000000')
        self.assertEqual(report['fractional000'], 1)
        self.assertEqual(sources[0]['timestampConvention'],
                         'CSV UTC Z; observed whole-second values; subsecond ordering/provenance UNVERIFIED')
        p = self.source(['2025-01-02 00:00:00.050Z'])
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_RESOLUTION'):
            self.ingest(ExnessIngestion, p, 'refused')

    def test_same_millisecond_is_an_atomic_untrusted_group(self):
        p = self.source(['2025-01-02 00:00:00.050Z'] * 2 + ['2025-01-02 00:00:00.051Z'])
        report, _ = self.ingest(ExnessMillisecondIngestion, p)
        provider = DiskTickProvider(self.root / 'store', report['datasetVersion'])
        timeline = IndexedTickTimeline(provider, provider.dataset_id, provider.dataset_version,
                                       '1735776000000000000', log_folder=self.root / 'log')
        try:
            result = timeline.advance_through('1735776000050000000', timeline.cursor)
            self.assertEqual([len(g['events']) for g in result['groups']], [2])
            self.assertTrue(all(e['trustedSequence'] is None for e in result['groups'][0]['events']))
            self.assertEqual(report['sameTimestampGroups'], 1)
        finally:
            timeline.close()
            provider.close()

    def test_invalid_calendar_fraction_and_offset_are_refused(self):
        for i, stamp in enumerate(['2025-02-30 00:00:00.050Z', '2025-01-02 00:00:00.05Z',
                                   '2025-01-02 00:00:00.050001Z', '2025-01-02 00:00:00.050+01:00']):
            with self.subTest(stamp=stamp), self.assertRaisesRegex(ValueError, 'INVALID_TIMESTAMP'):
                self.ingest(ExnessMillisecondIngestion, self.source([stamp]), f'invalid{i}')

    def test_legacy_and_native_pins_cannot_be_interchanged_on_resume(self):
        source = self.source(['2025-01-02 00:00:00.000Z', '2025-01-02 00:00:01.000Z'])
        old = ExnessIngestion(source, self.root / 'partial')
        try:
            with self.assertRaises(InterruptedError):
                old.run(stop_after=1)
        finally:
            old.builder.store.close()
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_INGESTION'):
            ExnessMillisecondIngestion(source, self.root / 'partial', resume=True)

    def test_interrupted_native_resume_matches_uninterrupted_version(self):
        # Cross the actual durable 4096-row boundary; this tests persisted state,
        # not merely retrying an empty staging database.
        stamps = [f'2025-01-02 00:00:{i // 1000:02d}.{i % 1000:03d}Z' for i in range(4200)]
        source = self.source(stamps)
        expected, _ = self.ingest(ExnessMillisecondIngestion, source, 'full')
        interrupted = ExnessMillisecondIngestion(source, self.root / 'resumed')
        try:
            with self.assertRaises(InterruptedError):
                interrupted.run(stop_after=4097)
        finally:
            interrupted.builder.store.close()
        actual, _ = self.ingest(ExnessMillisecondIngestion, source, 'resumed', resume=True)
        self.assertEqual(actual['acceptedRows'], 4200)
        self.assertEqual(actual['datasetVersion'], expected['datasetVersion'])
        self.assertEqual(self.events('resumed', actual), self.events('full', expected))
