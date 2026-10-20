import hashlib,importlib.util,json,os,tempfile,unittest,uuid,zipfile
from pathlib import Path
import psycopg
from psycopg import sql
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('odoo_recovery',ROOT/'integrations/odoo/recovery.py');recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)
DSN=os.getenv('BTL_TEST_DATABASE_URL');BIN=os.getenv('BTL_PG_BIN')
class RecoveryArchiveTests(unittest.TestCase):
    def archive(self,path,*,name='database.dump',content=b'authored dump',symlink=False):
        manifest=dict(format='BTL-ODOO-COLD-BACKUP-1',database='authored_source',odooSourceCommit='a'*40,files={name:dict(bytes=len(content),sha256=hashlib.sha256(content).hexdigest())})
        with zipfile.ZipFile(path,'w') as z:
            info=zipfile.ZipInfo(name)
            if symlink:info.external_attr=0o120777<<16
            z.writestr(info,content)
            if name!='database.dump':
                z.writestr('database.dump',b'authored dump');manifest['files']['database.dump']=dict(bytes=13,sha256=hashlib.sha256(b'authored dump').hexdigest())
            z.writestr('MANIFEST.json',json.dumps(manifest))
        return recovery.fingerprint(path)
    def test_trusted_hash_tamper_and_attachment_content_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'authored.zip';sha=self.archive(path);self.assertEqual(recovery.checked(path,sha)['database'],'authored_source')
            with path.open('ab') as out:out.write(b'changed')
            with self.assertRaises(ValueError):recovery.checked(path,sha)
            for name in ('../outside','filestore/aa/'+'a'*40):
                sha=self.archive(path,name=name)
                with self.assertRaises(ValueError):recovery.checked(path,sha)
            sha=self.archive(path,symlink=True)
            with self.assertRaises(ValueError):recovery.checked(path,sha)
    def test_quiescence_required_before_any_filesystem_or_database_operation(self):
        with self.assertRaises(ValueError):recovery.backup('not-a-dsn','missing','missing','missing','a'*40)
        with self.assertRaises(ValueError):recovery.restore('not-a-dsn','missing','missing','0'*64,'missing')

@unittest.skipUnless(DSN and BIN,'Fresh native PostgreSQL and pg tools required; skip is not acceptance')
class RecoveryNativeTests(unittest.TestCase):
    def test_actual_dump_restore_blob_integrity_and_refusal_before_overwrite(self):
        source='odoo_source_'+uuid.uuid4().hex[:12];target='odoo_restore_'+uuid.uuid4().hex[:12]
        with psycopg.connect(DSN,autocommit=True) as db:
            for name in (source,target):db.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
        source_dsn=psycopg.conninfo.make_conninfo(DSN,dbname=source);target_dsn=psycopg.conninfo.make_conninfo(DSN,dbname=target)
        data=b'Authored Odoo attachment recovery QA';key=hashlib.sha1(data).hexdigest();rel=key[:2]+'/'+key
        with psycopg.connect(source_dsn) as db:
            db.execute('CREATE TABLE ir_attachment(id integer PRIMARY KEY,store_fname text,file_size bigint,checksum text)')
            db.execute('INSERT INTO ir_attachment VALUES (1,%s,%s,%s)',(rel,len(data),key))
            db.execute('CREATE TABLE cash_probe(id integer PRIMARY KEY,amount_idr integer)');db.execute('INSERT INTO cash_probe VALUES (1,8500)')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);store=root/source;blob=store/rel;blob.parent.mkdir(parents=True);blob.write_bytes(data);archive=root/'backup.zip'
            with psycopg.connect(source_dsn):
                with self.assertRaises(ValueError):recovery.backup(source_dsn,store,archive,BIN,'a'*40,quiesced=True)
            self.assertFalse(archive.exists())
            with self.assertRaises(ValueError):recovery.backup(source_dsn,store,store/'overlap.zip',BIN,'a'*40,quiesced=True)
            self.assertFalse((store/'overlap.zip').exists())
            result=recovery.backup(source_dsn,store,archive,BIN,'a'*40,quiesced=True)
            if os.name!='nt':self.assertEqual(archive.stat().st_mode&0o077,0)
            self.assertTrue(recovery.restore(target_dsn,root/target,archive,result['sha256'],BIN,quiesced=True)['restored'])
            self.assertEqual((root/target/rel).read_bytes(),data)
            with psycopg.connect(target_dsn) as db:self.assertEqual(db.execute('SELECT amount_idr FROM cash_probe').fetchall(),[(8500,)])
            with self.assertRaises(ValueError):recovery.restore(target_dsn,root/(target+'_new'),archive,result['sha256'],BIN,quiesced=True)
            blob.write_bytes(b'x'*len(data))
            with self.assertRaises(ValueError):recovery.backup(source_dsn,store,root/'bad.zip',BIN,'a'*40,quiesced=True)
