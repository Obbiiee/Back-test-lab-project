"""Tiny authored CSV fixtures only; no provider download."""
import json,os,sqlite3,subprocess,sys,tempfile,unittest,zlib
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from market_data.instruments import INSTRUMENTS
from ticks.dukascopy_batch import plan,ingest
from ticks.dukascopy_csv import DukascopyCsvIngestion,source_pin
from tests.test_dukascopy_csv import HEADER,ROW

class DukascopyBatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'source';self.source.mkdir();self.store=self.root/'store'
        for symbol in INSTRUMENTS:(self.source/(symbol+'.csv')).write_text(HEADER+ROW,encoding='utf-8')
    def tearDown(self):self.tmp.cleanup()
    def run_batch(self,**kwargs):return ingest(self.source,self.store,'2026-09',evidence_class='SYNTHETIC_CONTRACT_ONLY',**kwargs)
    def test_all16_exact_pins_structural_only_and_resume(self):
        before={s:source_pin(self.source/(s+'.csv')) for s in INSTRUMENTS};result=self.run_batch()
        self.assertEqual(result['instruments'],list(INSTRUMENTS));self.assertEqual(len(result['imports']),16)
        self.assertEqual(result['coverage'],'UNVERIFIED');self.assertEqual(result['executionEligibility'],'NOT_GRANTED')
        for row in result['imports']:
            self.assertEqual(row['source'],before[row['symbol']]);self.assertEqual(row['acceptedRows'],1)
            self.assertEqual(row['equalTimestampOrder'],'UNTRUSTED');self.assertEqual(row['evidenceClass'],'SYNTHETIC_CONTRACT_ONLY')
        self.assertEqual(self.run_batch(resume=True),result)
        self.assertEqual({s:source_pin(self.source/(s+'.csv')) for s in INSTRUMENTS},before)
    def test_late_missing_or_bad_header_preflight_no_output(self):
        last=self.source/'XAUUSD.csv';last.unlink()
        with self.assertRaises(FileNotFoundError):self.run_batch()
        self.assertFalse(self.store.exists());last.write_text('Local time,Ask,Bid,AskVolume,BidVolume\n'+ROW,encoding='utf-8')
        with self.assertRaises(ValueError):self.run_batch()
        self.assertFalse(self.store.exists())
    def test_month_overlap_and_hardlink_alias_refused(self):
        for month in ('2026-13','2026-9','0000-01'):
            with self.assertRaises(ValueError):plan(self.source,self.store,month)
        for target in (self.source,self.source/'nested',self.root):
            with self.assertRaises(ValueError):plan(self.source,target,'2026-09')
        target=self.source/'EURGBP.csv';target.unlink();os.link(self.source/'AUDUSD.csv',target)
        with self.assertRaisesRegex(ValueError,'DUPLICATE_SOURCE_FILE'):self.run_batch()
        self.assertFalse(self.store.exists())
    def test_interruption_retains_completed_store_and_resume(self):
        native=DukascopyCsvIngestion.run;completed=[]
        def interrupted(importer,*args,**kwargs):
            if importer.symbol=='EURGBP':raise InterruptedError('authored interruption')
            result=native(importer,*args,**kwargs);completed.append(result);return result
        with patch.object(DukascopyCsvIngestion,'run',interrupted):
            with self.assertRaises(InterruptedError):self.run_batch()
        self.assertEqual(len(completed),1);self.assertTrue((self.store/'AUDUSD').exists())
        result=self.run_batch(resume=True);self.assertEqual(result['imports'][0],completed[0]);self.assertEqual(len(result['imports']),16)
    def test_changed_source_after_preflight_refuses(self):
        native=source_pin;calls=0
        def changed(path):
            nonlocal calls
            calls+=1;pin=native(path);return {**pin,'sha256':'f'*64} if calls>16 else pin
        with patch('ticks.dukascopy_batch.source_pin',changed):
            with self.assertRaisesRegex(ValueError,'SOURCE_PIN_CHANGED'):self.run_batch()
        self.assertFalse(self.store.exists())
    def test_completed_store_corruption_refuses_resume(self):
        self.run_batch()
        with closing(sqlite3.connect(self.store/'AUDUSD'/'archive.sqlite')) as db:
            db.execute("UPDATE objects SET body=? WHERE hash=(SELECT hash FROM objects LIMIT 1)",(zlib.compress(b'corrupt authored fixture'),));db.commit()
        with self.assertRaises(ValueError):self.run_batch(resume=True)
    def test_completed_source_changed_during_later_pair_refuses_batch(self):
        native=DukascopyCsvIngestion.run
        def changed(importer,*args,**kwargs):
            result=native(importer,*args,**kwargs)
            if importer.symbol=='XAUUSD':(self.source/'AUDUSD.csv').write_text(HEADER+ROW+ROW,encoding='utf-8')
            return result
        with patch.object(DukascopyCsvIngestion,'run',changed):
            with self.assertRaisesRegex(ValueError,'SOURCE_PIN_CHANGED'):self.run_batch()
    def test_cli_exclusive_report_and_no_report_after_failure(self):
        report=self.root/'report.json';command=[sys.executable,'-B','-m','ticks.dukascopy_batch','--source-directory',str(self.source),'--store-directory',str(self.store),'--month','2026-09','--report',str(report)]
        result=subprocess.run(command,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(report.read_text(encoding='utf-8'));self.assertEqual(len(data['imports']),16);self.assertEqual(data['rights'],'UNVERIFIED')
        original=report.read_bytes();self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0);self.assertEqual(report.read_bytes(),original)
        report.unlink();(self.source/'EURGBP.csv').write_text(HEADER+ROW.replace('01.09','01.10'),encoding='utf-8');command[command.index('--store-directory')+1]=str(self.root/'invalid')
        self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0);self.assertFalse(report.exists())

if __name__=='__main__':unittest.main()
