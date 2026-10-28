"""A serving copy is the same qualified dataset, never an ingestion/admission shortcut."""
from pathlib import Path
import hashlib
import os
import sqlite3
import tempfile
import unittest
import zlib

from ticks.compact_v2 import CompactDatasetBuilder
from ticks.contracts_v2 import ZERO_VERSION
from ticks.provider import Cancellation, SyntheticTickProvider
from ticks.read_snapshot_v2 import export_read_snapshot
from ticks.storage_v2 import DatasetBuilder, DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReadSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        for root, dirs, files in os.walk(self.root, followlinks=False):
            Path(root).chmod(0o700)
            for name in files:
                p = Path(root)/name
                if not p.is_symlink():
                    p.chmod(0o600)
        self.tmp.cleanup()

    def fixture(self, compact=False, complete=True):
        raw = [dict(ordinal=str(i), timeNs=str(t), bid='1.001', ask='1.003', sequence=None)
               for i, t in enumerate((100, 200, 200, 300))]
        p = SyntheticTickProvider(raw)
        description = p.describe(p.dataset_id, p.dataset_version)
        meta = {k: description[k] for k in ('datasetId', 'providerId', 'feedId', 'instrumentId',
                'providerSymbol', 'evidenceClass', 'adapterVersion', 'validatorVersion', 'ordering')}
        source = self.root/('compact' if compact else 'legacy')
        cls = CompactDatasetBuilder if compact else DatasetBuilder
        b = cls(source, meta, description['sources'], {'authored': True})
        try:
            for row in p.read_page(p.dataset_id, p.dataset_version, None, 4)['events']:
                b.append(dict(row, datasetVersion=ZERO_VERSION))
            version = b.finish() if complete else '0'*64
            b.store.db.commit()
            b.store.db.execute('PRAGMA journal_mode=DELETE')
        finally:
            b.store.close()
        return source, meta, version

    def export(self, source, meta, version, target='serving', **kwargs):
        return export_read_snapshot(source, self.root/target, dataset_id=meta['datasetId'],
                                    dataset_version=version, expected_archive_sha256=sha(source/'archive.sqlite'), **kwargs)

    def test_both_parent_layouts_keep_all_objects_bindings_pages_and_parent_bytes(self):
        for compact in (False, True):
            source, meta, version = self.fixture(compact=compact)
            before = sha(source/'archive.sqlite'), (source/'archive.sqlite').stat().st_mtime_ns
            name = 'serving'+str(compact)
            report = self.export(source, meta, version, target=name)
            target = self.root/name
            self.assertEqual(report['datasetVersion'], version)
            self.assertFalse(report['mutableIngestionIndexesCopied'])
            with sqlite3.connect((source/'archive.sqlite').as_uri()+'?mode=ro', uri=True) as original, \
                    sqlite3.connect((target/'archive.sqlite').as_uri()+'?mode=ro', uri=True) as copy:
                for table in ('objects', 'publications'):
                    self.assertEqual(original.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall(),
                                     copy.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall())
                names = {r[0] for r in copy.execute('SELECT name FROM sqlite_master')}
                self.assertFalse({'identities', 'identity_rows', 'journal', 'raw_records'} & names)
            a, b = DiskTickProvider(source, version, read_only=True), DiskTickProvider(target, version, read_only=True)
            try:
                self.assertEqual(a.describe_v2(a.dataset_id, version), b.describe_v2(b.dataset_id, version))
                for t in ('0', '100', '200', '201', '300', '301'):
                    left, right = a.locate_v2(a.dataset_id, version, t), b.locate_v2(b.dataset_id, version, t)
                    self.assertEqual(left, right)
                    if left['position'] is not None:
                        self.assertEqual(a.read_page_v2(a.dataset_id, version, left['position'], 2),
                                         b.read_page_v2(b.dataset_id, version, right['position'], 2))
            finally:
                a.close()
                b.close()
            self.assertEqual((sha(source/'archive.sqlite'), (source/'archive.sqlite').stat().st_mtime_ns), before)
            self.assertEqual((target/'archive.sqlite').stat().st_mode & 0o777, 0o400)
            self.assertEqual(target.stat().st_mode & 0o777, 0o500)

    def test_wrong_fingerprint_or_identity_never_creates_a_destination(self):
        source, meta, version = self.fixture()
        before = sha(source/'archive.sqlite')
        for dataset, fingerprint in ((meta['datasetId'], '0'*64), ('wrong:dataset', before)):
            with self.assertRaises(ValueError):
                export_read_snapshot(source, self.root/'bad', dataset_id=dataset, dataset_version=version,
                                     expected_archive_sha256=fingerprint)
            self.assertFalse((self.root/'bad').exists())
        self.assertEqual(sha(source/'archive.sqlite'), before)

    def test_live_wal_or_incomplete_parent_is_refused(self):
        source, meta, version = self.fixture()
        db = sqlite3.connect(source/'archive.sqlite')
        try:
            db.execute('PRAGMA journal_mode=WAL')
            before = sha(source/'archive.sqlite')
            with self.assertRaisesRegex(ValueError, 'READ_ONLY_SNAPSHOT_REQUIRED'):
                self.export(source, meta, version)
            self.assertEqual(sha(source/'archive.sqlite'), before)
        finally:
            db.close()
        source, meta, version = self.fixture(compact=True, complete=False)
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_INGESTION'):
            self.export(source, meta, version)
        self.assertFalse((self.root/'serving').exists())

    def test_existing_destination_and_source_overlap_never_overwrite_work(self):
        source, meta, version = self.fixture()
        target = self.root/'existing'
        target.mkdir()
        (target/'keep').write_text('user work')
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT_DESTINATION_EXISTS'):
            self.export(source, meta, version, target='existing')
        self.assertEqual((target/'keep').read_text(), 'user work')
        with self.assertRaisesRegex(ValueError, 'SOURCE_SNAPSHOT_OVERLAP'):
            export_read_snapshot(source, source/'child', dataset_id=meta['datasetId'], dataset_version=version,
                                 expected_archive_sha256=sha(source/'archive.sqlite'))
        self.assertFalse((source/'child').exists())

    def test_mid_copy_cancellation_removes_only_our_new_partial(self):
        source, meta, version = self.fixture()
        before = sha(source/'archive.sqlite')
        class Stop(Cancellation):
            calls = 0
            def check(self):
                self.calls += 1
                self.cancelled = self.calls >= 7
                super().check()
        with self.assertRaisesRegex(ValueError, 'CANCELLED'):
            self.export(source, meta, version, cancellation=Stop())
        self.assertFalse((self.root/'serving').exists())
        self.assertEqual(sha(source/'archive.sqlite'), before)

    def test_corrupt_body_is_not_copied_as_a_qualified_snapshot(self):
        source, meta, version = self.fixture()
        with sqlite3.connect(source/'archive.sqlite') as db:
            db.execute("UPDATE objects SET body=? WHERE kind='BTL-TICK-STORAGE-CHUNK-2'", (zlib.compress(b'corrupt'),))
        before = sha(source/'archive.sqlite')
        with self.assertRaisesRegex(ValueError, 'CHILD_HASH_MISMATCH'):
            self.export(source, meta, version)
        self.assertFalse((self.root/'serving').exists())
        self.assertEqual(sha(source/'archive.sqlite'), before)

    def test_serving_file_cannot_be_reopened_by_a_writer_or_used_as_a_new_parent(self):
        source, meta, version = self.fixture()
        self.export(source, meta, version)
        target = self.root/'serving'
        before = sha(target/'archive.sqlite')
        for cls in (DatasetBuilder, CompactDatasetBuilder):
            with self.assertRaisesRegex(ValueError, 'STORAGE_LAYOUT_MISMATCH'):
                cls(target, {}, [], {})
        with self.assertRaisesRegex(ValueError, 'QUALIFIED_PARENT_REQUIRED'):
            export_read_snapshot(target, self.root/'another', dataset_id=meta['datasetId'], dataset_version=version,
                                 expected_archive_sha256=before)
        self.assertEqual(sha(target/'archive.sqlite'), before)

    def test_existing_atomic_replay_checkpoint_recovers_against_the_serving_copy(self):
        source, meta, version = self.fixture(compact=True)
        self.export(source, meta, version)
        original = DiskTickProvider(source, version, read_only=True)
        serving = DiskTickProvider(self.root/'serving', version, read_only=True)
        t = IndexedTickTimeline(original, meta['datasetId'], version, '0', log_folder=self.root/'logs')
        try:
            result = t.advance_through('200', t.cursor)
            self.assertEqual([len(g['events']) for g in result['groups']], [1, 2])
            checkpoint = t.checkpoint()
            before = t.consumer().read_revealed('0', 64)
        finally:
            t.close()
        resumed = IndexedTickTimeline.resume(serving, checkpoint, log_folder=self.root/'logs')
        try:
            self.assertEqual(resumed.checkpoint(), checkpoint)
            self.assertEqual(resumed.consumer().read_revealed('0', 64), before)
            self.assertTrue(all(int(g['timeNs']) <= 200 for g in before))
        finally:
            resumed.close()
            original.close()
            serving.close()
