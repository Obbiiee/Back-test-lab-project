"""Exact serving replication; original acceptance remains mandatory and retained."""
import gzip
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import zlib
import unittest

from contracts.primitives import ContractError
from ticks.histdata_v2 import HistDataIngestion
from ticks.provider import Cancellation
from ticks.serving_v2 import export_serving
from ticks.storage_v2 import DiskTickProvider


class ServingReplicaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name)
        self.source=self.base/'accepted'; self.dest=self.base/'serving'
        raw=self.base/'EURUSD_2021-11.csv.gz'
        raw.write_bytes(gzip.compress(b'timestamp_utc,bid,ask\n'
            b'2021-11-01T00:00:00.000Z,1.1,1.2\n'
            b'2021-11-01T00:01:00.000Z,1.2,1.3\n'
            b'2021-11-01T00:01:00.000Z,1.3,1.4\n',mtime=0))
        with HistDataIngestion(raw,self.source,'EURUSD',first_rows=None,packing=(2,1,2)) as intake:
            self.version=intake.run()['datasetVersion']
        self.before=hashlib.sha256((self.source/'archive.sqlite').read_bytes()).hexdigest()

    def tearDown(self):self.tmp.cleanup()

    def export(self,**options):
        return export_serving(self.source,self.version,self.dest,
                              trusted_local_completion=True,**options)

    def test_exact_artifacts_and_reader_with_original_identity_retained(self):
        result=self.export()
        self.assertFalse(result['financialAdmissionChanged'])
        self.assertEqual(hashlib.sha256((self.source/'archive.sqlite').read_bytes()).hexdigest(),self.before)
        with sqlite3.connect(self.source/'archive.sqlite') as src, sqlite3.connect(self.dest/'archive.sqlite') as dst:
            self.assertEqual(src.execute('select count(*) from identities').fetchone()[0],3)
            for table in ('objects','publications','journal'):
                self.assertEqual(src.execute('select * from '+table+' order by 1').fetchall(),
                                 dst.execute('select * from '+table+' order by 1').fetchall())
        original=DiskTickProvider(self.source,self.version); replica=DiskTickProvider(self.dest,self.version)
        try:
            self.assertEqual(original.describe_v2(original.dataset_id,self.version),replica.describe_v2(replica.dataset_id,self.version))
            self.assertEqual(original.read_page_v2(original.dataset_id,self.version,None,10),
                             replica.read_page_v2(replica.dataset_id,self.version,None,10))
        finally:original.close();replica.close()
        with self.assertRaises(ContractError):
            export_serving(self.dest,self.version,self.base/'second',trusted_local_completion=True)

    def test_explicit_trust_budget_and_cancellation_required(self):
        for options in ({'trusted_local_completion':False},{'max_bytes':1},
                        {'max_objects':1},{'cancellation':Cancellation(True)}):
            with self.subTest(options=options),self.assertRaises(ContractError):
                export_serving(self.source,self.version,self.dest,
                               **({'trusted_local_completion':True}|options))
            self.assertFalse(self.dest.exists())

    def test_existing_or_nested_destination_refused(self):
        self.dest.mkdir()
        for path in (self.dest,self.source/'nested'):
            with self.assertRaises(ContractError):
                export_serving(self.source,self.version,path,trusted_local_completion=True)

    def test_corrupt_artifact_never_publishes(self):
        with sqlite3.connect(self.source/'archive.sqlite') as db:
            db.execute('update objects set body=? where hash=(select min(hash) from objects)',(b'corrupt',))
        with self.assertRaises((ContractError,zlib.error)):
            self.export()
        with sqlite3.connect(self.dest/'archive.sqlite') as db:
            self.assertEqual(db.execute('select count(*) from publications').fetchone()[0],0)

    def test_missing_child_never_publishes(self):
        with sqlite3.connect(self.source/'archive.sqlite') as db:
            db.execute("delete from objects where kind='BTL-TICK-STORAGE-CHUNK-2'")
        with self.assertRaises(ContractError):self.export()
        with sqlite3.connect(self.dest/'archive.sqlite') as db:
            self.assertEqual(db.execute('select count(*) from publications').fetchone()[0],0)

    def test_cancellation_during_copy_never_publishes(self):
        class DuringCopy:
            calls=0
            def check(self):
                self.calls+=1
                if self.calls==4:raise ContractError('CANCELLED','cancel')
        with self.assertRaises(ContractError):self.export(cancellation=DuringCopy())
        with sqlite3.connect(self.dest/'archive.sqlite') as db:
            self.assertEqual(db.execute('select count(*) from publications').fetchone()[0],0)
