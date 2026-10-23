"""Authored converted UTC fixtures; no provider rights/execution certification."""
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from contracts.primitives import ContractError
from ticks.histdata_v2 import HistDataIngestion, parse_record, source_pin, main
from ticks.storage_v2 import DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline

HEADER = b'timestamp_utc,bid,ask\n'
ROWS = [b'2021-10-01T05:00:00.001Z,1.10000,1.10020\n',
        b'2021-10-01T05:00:00.002Z,1.10001,1.10021\n',
        b'2021-10-01T05:00:00.002Z,1.10001,1.10021\n',
        b'2021-10-01T05:00:00.003Z,1.10002,1.10022\n',
        b'2021-10-01T05:00:00.004Z,1.10003,1.10023\n']


class HistDataV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.source = self.root/'EURUSD_2021-10.csv.gz'
        self.write(ROWS)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rows):
        self.source.write_bytes(gzip.compress(HEADER+b''.join(rows), mtime=0))

    def intake(self, folder='store', **kwargs):
        return HistDataIngestion(self.source, self.root/folder, 'EURUSD', packing=(2, 1, 2), **kwargs)

    def test_utc_and_exact_prices_no_second_est_conversion(self):
        stamp, ns, bid, ask = parse_record(ROWS[0])
        self.assertEqual(ns, '1633064400001000000')
        self.assertEqual((bid, ask), ('1.1', '1.1002'))
        for bad in [b'20211001 000000001,1.1,1.2,0\n', b'2021-10-01T05:00:00Z,1.1,1.2\n',
                    b'2021-10-01T05:00:00.001Z,NaN,1.2\n', b'2021-10-01T05:00:00.001Z,1.3,1.2\n',
                    b'2021-10-01T05:00:00.001Z,0,1.2\n', b'2021-10-01T05:00:00.001Z,1e0,1.2\n']:
            with self.assertRaises(ContractError): parse_record(bad)

    def test_atomic_prefix_duplicate_preservation_and_private_timeline(self):
        before = self.source.read_bytes()
        with self.intake(first_rows=2) as intake:
            result = intake.run()
        self.assertEqual(result['acceptedRows'], 3)
        self.assertEqual(result['adjacentDuplicates'], 1)
        self.assertEqual(result['rights'], 'UNKNOWN')
        self.assertEqual(self.source.read_bytes(), before)
        with self.provider('store', result) as provider:
            manifest = provider.describe_v2(provider.dataset_id, provider.dataset_version)
            self.assertEqual(manifest['root']['ordering']['ties'], 'UNTRUSTED')
            position = provider.locate_v2(provider.dataset_id, provider.dataset_version, manifest['root']['range']['startNs'])['position']; events = []
            while True:
                page = provider.read_page_v2(provider.dataset_id, provider.dataset_version, position, 10)
                events.extend(page['events'])
                if page['endOfDataset']: break
                position = page['nextPosition']
            self.assertEqual(len(events), 3)
            self.assertEqual(len({e['eventId'] for e in events}), 3)
            self.assertTrue(all(e['trustedSequence'] is None and e['quality']['freshness']=='UNKNOWN' for e in events))
            with self.timeline(provider) as timeline:
                observed = timeline.advance_through('1633064400001000000', timeline.cursor)
                self.assertEqual(len(observed['groups']), 1)
                self.assertTrue(all(int(g['timeNs']) <= 1633064400001000000 for g in observed['groups']))

    def provider(self, folder, result):
        from contextlib import closing
        return closing(DiskTickProvider(self.root/folder, result['datasetVersion']))

    def timeline(self, provider):
        from contextlib import closing
        return closing(IndexedTickTimeline(provider, provider.dataset_id, provider.dataset_version,
                                           '1633064400001000000', log_folder=self.root/'logs'))

    def test_reversal_refused_not_sorted_or_published(self):
        self.write([ROWS[1], ROWS[0]])
        with self.intake(first_rows=None) as intake:
            with self.assertRaises(ContractError) as error: intake.run()
            self.assertEqual(error.exception.code, 'ORDER_REVERSAL')
            self.assertNotEqual(intake.builder.s['state'], 'COMPLETE')

    def test_interruption_resume_matches_uninterrupted_dataset(self):
        with self.intake('whole', first_rows=None) as intake: whole = intake.run()
        with self.intake('partial', first_rows=None) as intake:
            with self.assertRaises(InterruptedError): intake.run(stop_after=4)
        with self.intake('partial', first_rows=None, resume=True) as intake: resumed = intake.run()
        self.assertEqual(resumed['datasetVersion'], whole['datasetVersion'])
        self.assertEqual(resumed['acceptedRows'], len(ROWS))
        self.assertEqual(resumed['adjacentDuplicates'], whole['adjacentDuplicates'])

    def test_changed_input_refused_at_publication_and_resume(self):
        with self.intake(first_rows=None) as intake:
            original = intake.builder.finish
            def finish(**kwargs):
                self.write(ROWS+[b'2021-10-01T05:00:00.005Z,1.2,1.3\n'])
                return original(**kwargs)
            with patch.object(intake.builder, 'finish', finish):
                with self.assertRaises(ContractError): intake.run()
        with self.assertRaises(ContractError): self.intake(first_rows=None, resume=True)

    def test_cli_refusal_writes_explicit_report_without_silent_empty_file(self):
        import json
        self.write([ROWS[1], ROWS[0]])
        report = self.root/'refusal.json'
        args = ['intake', '--source', str(self.source), '--store', str(self.root/'cli'),
                '--symbol', 'EURUSD', '--report', str(report)]
        with patch('sys.argv', args):
            with self.assertRaises(SystemExit) as error: main()
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(json.loads(report.read_text()), {'status': 'REFUSED_NOT_PUBLISHED', 'code': 'ORDER_REVERSAL'})

    def test_incomplete_gzip_symbol_and_partial_file_refused(self):
        with self.assertRaises(ContractError): HistDataIngestion(self.source, self.root/'wrong', 'GBPUSD')
        part = self.root/'EURUSD_2021-10.csv.gz.part'; part.write_bytes(self.source.read_bytes())
        with self.assertRaises(ContractError): HistDataIngestion(part, self.root/'part', 'EURUSD')
        self.source.write_bytes(self.source.read_bytes()[:-8])
        with self.assertRaises((EOFError, OSError)): source_pin(self.source)


if __name__ == '__main__': unittest.main()
