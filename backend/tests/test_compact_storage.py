"""Opt-in physical layout retains the existing logical validation authority."""
from copy import deepcopy
from pathlib import Path
import hashlib
import sqlite3
import tempfile
import unittest
import zlib

from ticks.compact_v2 import CompactDatasetBuilder, CompactExnessMillisecondIngestion
from ticks.contracts import event_id
from ticks.contracts_v2 import ZERO_VERSION
from ticks.exness_v2 import ExnessMillisecondIngestion
from ticks.provider import Cancellation, SyntheticTickProvider
from ticks.storage_v2 import DatasetBuilder, DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline


class CompactStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.resources = []

    def tearDown(self):
        for resource in reversed(self.resources):
            try:
                resource.close()
            except sqlite3.ProgrammingError:
                pass
        self.tmp.cleanup()

    def inputs(self, count=6):
        # A streamed source fixture must not enlarge the frozen canonical-array
        # limit just to cross the 4096-row durable checkpoint.
        times = [100, 200, 200, 300, 400, 500] if count == 6 else [1]
        p = SyntheticTickProvider([dict(ordinal=str(i), timeNs=str(t), bid='1.001', ask='1.003', sequence=None)
                                   for i, t in enumerate(times)])
        description = p.describe(p.dataset_id, p.dataset_version)
        meta = {k: description[k] for k in ('datasetId', 'providerId', 'feedId', 'instrumentId',
                'providerSymbol', 'evidenceClass', 'adapterVersion', 'validatorVersion', 'ordering')}
        events = []
        token = None
        while True:
            page = p.read_page(p.dataset_id, p.dataset_version, token, 256)
            events.extend(dict(e, datasetVersion=ZERO_VERSION) for e in page['events'])
            if page['endOfDataset']:
                break
            token = page['nextToken']
        sources = deepcopy(description['sources'])
        if count != 6:
            member = hashlib.sha256(b''.join(f'{i},{i+1},1.001,1.003\n'.encode() for i in range(count))).hexdigest()
            sources[0]['memberHash'] = member
            template = events[0]
            events = []
            for i in range(count):
                row = deepcopy(template)
                row.update(rawOrdinal=str(i), timeNs=str(i+1),
                           eventId=event_id(meta['providerId'], meta['feedId'], member, str(i)))
                row['provenance'].update(memberHash=member, originalTimestamp=str(i+1))
                events.append(row)
        return meta, sources, events

    def builder(self, cls, name, inputs, **kwargs):
        meta, sources, _ = inputs
        b = cls(self.root/name, meta, sources, {'authored': True}, **kwargs)
        self.resources.append(b.store)
        return b

    def build(self, cls, name, inputs):
        b = self.builder(cls, name, inputs)
        for i, row in enumerate(inputs[2]):
            b.append(deepcopy(row), source_offset=i+1)
        version = b.finish()
        return b, version

    def provider(self, name, version, **kwargs):
        p = DiskTickProvider(self.root/name, version, **kwargs)
        self.resources.append(p)
        return p

    def test_full_logical_objects_identities_publication_and_pages_equal(self):
        inputs = self.inputs()
        old, expected = self.build(DatasetBuilder, 'old', inputs)
        new, actual = self.build(CompactDatasetBuilder, 'new', inputs)
        self.assertEqual(actual, expected)
        for table in ('identities', 'objects', 'publications', 'journal'):
            self.assertEqual(old.store.db.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall(),
                             new.store.db.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall())
        a, b = self.provider('old', expected), self.provider('new', actual)
        self.assertEqual(a.describe_v2(a.dataset_id, expected), b.describe_v2(b.dataset_id, actual))
        for ns in ('0', '100', '150', '200', '201', '500', '501'):
            left, right = a.locate_v2(a.dataset_id, expected, ns), b.locate_v2(b.dataset_id, actual, ns)
            self.assertEqual(left, right)
            if left['position'] is not None:
                self.assertEqual(a.read_page_v2(a.dataset_id, expected, left['position'], 2),
                                 b.read_page_v2(b.dataset_id, actual, right['position'], 2))

    def test_mixed_writers_refuse_without_changing_closed_original(self):
        inputs = self.inputs()
        for cls, wrong, name in ((DatasetBuilder, CompactDatasetBuilder, 'legacy'),
                                  (CompactDatasetBuilder, DatasetBuilder, 'compact')):
            b, _ = self.build(cls, name, inputs)
            b.store.db.execute('PRAGMA journal_mode=DELETE')
            b.store.close()
            path = self.root/name/'archive.sqlite'
            before = hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns
            with self.assertRaisesRegex(ValueError, 'STORAGE_LAYOUT_MISMATCH'):
                self.builder(wrong, name, inputs, resume=True)
            self.assertEqual((hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns), before)
            self.assertEqual([p.name for p in path.parent.iterdir()], ['archive.sqlite'])

    def test_uniqueness_and_foreign_keys_are_enforced_and_failed_insert_is_atomic(self):
        b, _ = self.build(CompactDatasetBuilder, 'new', self.inputs())
        db = b.store.db
        event, digest, source, ordinal = db.execute('SELECT * FROM identities LIMIT 1').fetchone()
        source_count = db.execute('SELECT count(*) FROM identity_sources').fetchone()[0]
        db.commit()
        for row in ((event, b'x'*32, 'different-source', 'new'),
                    (b'y'*32, digest, source, ordinal)):
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO identities VALUES(?,?,?,?)', row)
            db.rollback()
            self.assertEqual(db.execute('SELECT count(*) FROM identities').fetchone()[0], 6)
            self.assertEqual(db.execute('SELECT count(*) FROM identity_sources').fetchone()[0], source_count)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute('INSERT INTO identity_rows VALUES(?,?,?,?)', (b'z'*32, digest, 999999, '0'))
        db.rollback()
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_cancel_and_resume_cross_real_durable_boundary_with_identical_hash(self):
        inputs = self.inputs(4200)
        _, expected = self.build(DatasetBuilder, 'old', inputs)
        partial = self.builder(CompactDatasetBuilder, 'new', inputs)
        for i, row in enumerate(inputs[2]):
            partial.append(row, source_offset=i+1)
        with self.assertRaisesRegex(ValueError, 'CANCELLED'):
            partial.finish(cancellation=Cancellation(True))
        self.assertEqual(partial.store.db.execute('SELECT count(*) FROM publications').fetchone()[0], 0)
        partial.store.close()
        resumed = self.builder(CompactDatasetBuilder, 'new', inputs, resume=True)
        self.assertEqual(resumed.s['count'], 4096)
        for i in range(resumed.s['count'], len(inputs[2])):
            resumed.append(inputs[2][i], source_offset=i+1)
        self.assertEqual(resumed.finish(), expected)

    def test_corrupt_identity_refuses_normal_finalization(self):
        inputs = self.inputs()
        b = self.builder(CompactDatasetBuilder, 'new', inputs)
        for row in inputs[2]:
            b.append(row)
        b.store.db.execute('UPDATE identity_rows SET digest=?', (b'x'*32,))
        with self.assertRaisesRegex(ValueError, 'IDENTITY_CONFLICT'):
            b.finish()
        self.assertEqual(b.store.db.execute('SELECT count(*) FROM publications').fetchone()[0], 0)

    def test_readonly_snapshot_atomic_ties_causal_clipping_and_cold_checkpoint(self):
        b, version = self.build(CompactDatasetBuilder, 'new', self.inputs())
        b.store.db.execute('PRAGMA journal_mode=DELETE')
        b.store.close()
        archive = self.root/'new/archive.sqlite'
        before = hashlib.sha256(archive.read_bytes()).hexdigest()
        p = self.provider('new', version, read_only=True)
        t = IndexedTickTimeline(p, p.dataset_id, version, '0', log_folder=self.root/'log')
        try:
            result = t.advance_through('200', t.cursor)
            self.assertEqual([len(g['events']) for g in result['groups']], [1, 2])
            self.assertTrue(all(int(g['timeNs']) <= 200 for g in t.consumer().read_revealed('0', 64)))
            checkpoint = t.checkpoint()
        finally:
            t.close()
        resumed = IndexedTickTimeline.resume(p, checkpoint, log_folder=self.root/'log')
        try:
            self.assertEqual(resumed.checkpoint(), checkpoint)
        finally:
            resumed.close()
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), before)

    def test_corrupt_chunk_still_fails_existing_reader_hash_check(self):
        b, version = self.build(CompactDatasetBuilder, 'new', self.inputs())
        b.store.db.execute("UPDATE objects SET body=? WHERE kind='BTL-TICK-STORAGE-CHUNK-2'", (zlib.compress(b'bad'),))
        b.store.db.commit()
        p = self.provider('new', version)
        with self.assertRaisesRegex(ValueError, 'CHILD_HASH_MISMATCH'):
            p.read_page_v2(p.dataset_id, version, p.locate_v2(p.dataset_id, version, '0')['position'], 2)

    def test_native_ms_adapter_and_duplicate_records_have_identical_logical_versions(self):
        source = self.root/'native.csv'
        source.write_text('Exness,Symbol,Timestamp,Bid,Ask\n' +
                          'exness,XAUUSD,2025-01-02 00:00:00.050Z,2625.100,2625.210\n'*2 +
                          'exness,XAUUSD,2025-01-02 00:00:00.051Z,2625.100,2625.210\n')
        reports = []
        for cls, name in ((ExnessMillisecondIngestion, 'old'), (CompactExnessMillisecondIngestion, 'new')):
            ingestion = cls(source, self.root/name)
            self.resources.append(ingestion.builder.store)
            report = ingestion.run()
            self.assertEqual(report['exactDuplicateSourceRecords'], 1)
            self.assertEqual(report['sourceResolutionNs'], '1000000')
            reports.append(report)
        self.assertEqual(reports[0]['datasetVersion'], reports[1]['datasetVersion'])
        self.assertEqual(reports[1]['acceptedRows'], 3)

    def test_multiple_sources_keep_distinct_ordinal_namespaces_and_atomic_order(self):
        meta, sources, seed = self.inputs()
        other = deepcopy(sources[0])
        other['sourceId'] += ':second'
        other['memberHash'] = hashlib.sha256(b'authored second source').hexdigest()
        sources.append(other)
        rows = []
        for source_index, ordinal, moment in ((0, 0, 100), (0, 1, 200), (1, 0, 200), (1, 1, 300)):
            source = sources[source_index]
            row = deepcopy(seed[0])
            row.update(rawOrdinal=str(ordinal), timeNs=str(moment),
                       eventId=event_id(meta['providerId'], meta['feedId'], source['memberHash'], str(ordinal)))
            row['provenance'].update(sourceId=source['sourceId'], memberHash=source['memberHash'],
                                     originalTimestamp=str(moment))
            rows.append(row)
        inputs = meta, sources, rows
        old, expected = self.build(DatasetBuilder, 'old', inputs)
        new, actual = self.build(CompactDatasetBuilder, 'new', inputs)
        self.assertEqual(actual, expected)
        self.assertEqual(new.store.db.execute('SELECT count(*) FROM identity_sources').fetchone()[0], 2)
        self.assertEqual(old.store.db.execute('SELECT * FROM identities ORDER BY event').fetchall(),
                         new.store.db.execute('SELECT * FROM identities ORDER BY event').fetchall())

    def test_compact_writer_rejects_symlinked_archive(self):
        if not hasattr(Path, 'symlink_to'):
            self.skipTest('No symlink API')
        inputs = self.inputs()
        b, _ = self.build(DatasetBuilder, 'old', inputs)
        b.store.close()
        folder = self.root/'linked'
        folder.mkdir()
        (folder/'archive.sqlite').symlink_to(self.root/'old/archive.sqlite')
        with self.assertRaisesRegex(ValueError, 'SOURCE_PATH_REFUSED'):
            self.builder(CompactDatasetBuilder, 'linked', inputs)
