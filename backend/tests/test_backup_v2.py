"""Private snapshot backup retains registry; no live service/database access."""
import gzip
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zlib

from contracts.primitives import ContractError
from ticks.backup_v2 import backup_store
from ticks.histdata_v2 import HistDataIngestion
from ticks.provider import Cancellation
from ticks.storage_v2 import DiskTickProvider

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        raw=self.root/'EURUSD_2021-11.csv.gz'
        raw.write_bytes(gzip.compress(b'timestamp_utc,bid,ask\n2021-11-01T00:00:00.000Z,1.1,1.2\n2021-11-01T00:01:00.000Z,1.2,1.3\n',mtime=0))
        self.source=self.root/'source';self.dest=self.root/'backup'
        with HistDataIngestion(raw,self.source,'EURUSD',first_rows=None,packing=(1,1,1)) as intake:
            self.version=intake.run()['datasetVersion']
    def tearDown(self):self.tmp.cleanup()
    def backup(self,**opts):return backup_store(self.source,self.version,self.dest,trusted_local_completion=True,**opts)
    def test_all_tables_exact_and_independent_cold_reader(self):
        before=(self.source/'archive.sqlite').read_bytes();r=self.backup()
        self.assertEqual(r['retainedIdentityRows'],2);self.assertFalse(r['financialAdmissionChanged'])
        self.assertEqual((self.source/'archive.sqlite').read_bytes(),before)
        with sqlite3.connect(self.source/'archive.sqlite') as a,sqlite3.connect(self.dest/'archive.sqlite') as b:
            for table in ['objects','publications','journal','identities']:
                self.assertEqual(a.execute('select * from '+table+' order by 1').fetchall(),b.execute('select * from '+table+' order by 1').fetchall())
        self.assertEqual(hashlib.sha256((self.dest/'archive.sqlite').read_bytes()).hexdigest(),r['archiveSha256'])
        a=DiskTickProvider(self.source,self.version);b=DiskTickProvider(self.dest,self.version)
        try:self.assertEqual(a.read_page_v2(a.dataset_id,self.version,None,10),b.read_page_v2(b.dataset_id,self.version,None,10))
        finally:a.close();b.close()
    def test_trust_budget_wrong_version_and_existing_path_refused(self):
        with self.assertRaises(ContractError):backup_store(self.source,self.version,self.dest)
        for opts in [{'max_bytes':1},{'max_objects':1},{'timeout_seconds':False}]:
            with self.assertRaises(ContractError):self.backup(**opts)
        with self.assertRaises(ContractError):backup_store(self.source,'f'*64,self.dest,trusted_local_completion=True)
        self.assertFalse(self.dest.exists());self.dest.mkdir()
        with self.assertRaises(ContractError):self.backup()
        with self.assertRaises(ContractError):backup_store(self.source,self.version,self.source/'nested',trusted_local_completion=True)
    def test_cancelled_backup_is_not_published(self):
        with self.assertRaises(ContractError):self.backup(cancellation=Cancellation(True))
        class Later:
            count=0
            def check(self):
                self.count+=1
                if self.count==4:raise ContractError('CANCELLED','cancel')
        with self.assertRaises(ContractError):self.backup(cancellation=Later())
        self.assertFalse((self.dest/'archive.sqlite').exists())
    def test_corrupt_compressed_object_does_not_publish(self):
        with sqlite3.connect(self.source/'archive.sqlite') as db:db.execute('update objects set body=? where hash=(select min(hash) from objects)',(b'bad',))
        with self.assertRaises((ContractError,zlib.error)):self.backup()
        self.assertFalse((self.dest/'archive.sqlite').exists())
    def test_missing_child_does_not_publish(self):
        with sqlite3.connect(self.source/'archive.sqlite') as db:db.execute("delete from objects where kind='BTL-TICK-STORAGE-CHUNK-2'")
        with self.assertRaises(ContractError):self.backup()
        self.assertFalse((self.dest/'archive.sqlite').exists())
    def test_registry_loss_refused_before_copy(self):
        with sqlite3.connect(self.source/'archive.sqlite') as db:db.execute('delete from identities where event=(select min(event) from identities)')
        with self.assertRaises(ContractError):self.backup()
        self.assertFalse(self.dest.exists())
