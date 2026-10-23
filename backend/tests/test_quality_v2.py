"""Quality diagnostics never publish/admit data; authored bounded fixtures."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contracts.primitives import ContractError
from ticks.provider import Cancellation
from ticks.quality_v2 import audit_file, main
from ticks.histdata_v2 import source_pin

H=b'timestamp_utc,bid,ask\n'
A=b'2021-11-01T00:00:00.000Z,1.10000,1.20000\n'
B=b'2021-11-01T00:00:01.000Z,1.2,1.3\n'
C=b'2021-11-01T00:00:01.000Z,1.3,1.4\n'


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'EURUSD_2021-11.csv.gz';self.write(A+B)
    def tearDown(self):self.tmp.cleanup()
    def write(self,rows):self.source.write_bytes(gzip.compress(H+rows,mtime=0))
    def test_full_numeric_and_source_pin_without_source_change_or_admission(self):
        before=self.source.read_bytes();r=audit_file(self.source,'EURUSD')
        self.assertEqual(r['rows'],2);self.assertEqual(r['validNumericRows'],2)
        self.assertEqual(r['source']['memberSha256'],hashlib.sha256(H+A+B).hexdigest())
        self.assertEqual(r['maxObservedSilenceNs'],'1000000000')
        self.assertEqual(r,audit_file(self.source,'EURUSD'))
        self.assertEqual(self.source.read_bytes(),before)
        self.assertFalse(r['financialAdmission']);self.assertFalse(r['canonicalDatasetPublished'])
        self.assertEqual(r['coverage'],'UNKNOWN');self.assertEqual(r['freshness'],'UNKNOWN')
    def test_invalid_price_time_and_crossed_quotes_have_bounded_nonprice_examples(self):
        bad=b'2021-11-01T00:00:00.000Z,1.3,1.2\n'
        self.write(A+bad*20+b'2021-02-30T00:00:00.000Z,1,2\n'+B)
        r=audit_file(self.source,'EURUSD');self.assertEqual(r['invalidRows'],21)
        self.assertEqual(len(r['examples']),8);self.assertEqual(r['status'],'QUALITY_REFUSED')
        self.assertEqual(r['examples'][0]['rawOrdinal'],'1')
        self.assertEqual(set(r['examples'][0]),{'rawOrdinal','code'})
    def test_reversal_and_ambiguous_groups_preserved_without_sorting(self):
        self.write(A+B+C+A);r=audit_file(self.source,'EURUSD')
        self.assertEqual(r['orderReversals'],1);self.assertEqual(r['equalTimeValidPairs'],1)
        self.assertEqual(r['ambiguousTimestampGroups'],1);self.assertFalse(r['rawOrdinalIsTrustedSequence'])
        self.assertEqual(r['status'],'QUALITY_REFUSED')
    def test_group_overflow_and_row_budget_are_not_partial_acceptance(self):
        self.write(A*1025);r=audit_file(self.source,'EURUSD')
        self.assertEqual(r['oversizedTimestampGroups'],1);self.assertEqual(r['largestTimestampGroup'],1025)
        self.assertEqual(r['status'],'QUALITY_REFUSED')
        with self.assertRaises(ContractError) as e:audit_file(self.source,'EURUSD',max_rows=1024)
        self.assertEqual(e.exception.code,'QUALITY_ROW_LIMIT')
    def test_empty_header_oversized_record_and_hash_substitution_refused(self):
        for data in [H,b'wrong\n'+A,H+b'x'*8193+b'\n']:
            self.source.write_bytes(gzip.compress(data,mtime=0))
            with self.assertRaises(ContractError):audit_file(self.source,'EURUSD')
        self.write(A)
        with self.assertRaises(ContractError):audit_file(self.source,'EURUSD',expected_member_sha256='f'*64)
        with self.assertRaises(ContractError):audit_file(self.source,'GBPUSD')
        with self.assertRaises(ContractError):audit_file(self.source,'EURUSD',max_rows=True)
    def test_cancellation_before_and_during_scan_has_no_success(self):
        with self.assertRaises(ContractError):audit_file(self.source,'EURUSD',cancellation=Cancellation(True))
        class During:
            count=0
            def check(self):
                self.count+=1
                if self.count==4:raise ContractError('CANCELLED','cancel')
        with self.assertRaises(ContractError) as e:audit_file(self.source,'EURUSD',cancellation=During())
        self.assertEqual(e.exception.code,'CANCELLED')
    def test_source_replacement_and_truncated_gzip_refused(self):
        outer=self
        class Change:
            count=0
            def check(self):
                self.count+=1
                if self.count==3:outer.write(A+C)
        with self.assertRaises((ContractError,EOFError,OSError)):
            audit_file(self.source,'EURUSD',cancellation=Change())
        self.write(A);self.source.write_bytes(self.source.read_bytes()[:-5])
        with self.assertRaises((EOFError,OSError)):audit_file(self.source,'EURUSD')
    def test_observed_stream_must_match_the_pinned_member_not_only_final_stat(self):
        pin=source_pin(self.source);pin['memberSha256']='f'*64
        with patch('ticks.quality_v2.source_pin',return_value=pin),self.assertRaises(ContractError) as e:
            audit_file(self.source,'EURUSD')
        self.assertEqual(e.exception.code,'SOURCE_CHANGED')
    def test_cli_refusal_and_exclusive_report_never_overwrite(self):
        report=self.root/'report.json';self.write(B+A)
        args=['quality','--source',str(self.source),'--symbol','EURUSD','--report',str(report)]
        with patch('sys.argv',args),self.assertRaises(SystemExit) as e:main()
        self.assertEqual(e.exception.code,2);self.assertEqual(json.loads(report.read_text())['status'],'QUALITY_REFUSED')
        before=report.read_bytes()
        with patch('sys.argv',args),self.assertRaises(FileExistsError):main()
        self.assertEqual(report.read_bytes(),before)
