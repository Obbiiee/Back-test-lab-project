from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    from tests.qa_parquet_day_provider import ParquetDayProvider, file_sha
except ImportError:
    pa = pq = ParquetDayProvider = None


class Metadata:
    dataset_id = 'fixture:qa'
    def describe_v2(self, *args): return {'metadataOnly': True}
    def close(self): pass


@unittest.skipIf(pa is None, 'optional Parquet QA dependencies are not installed')
class ParquetDayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'day.parquet'
        self.version = 'a'*64
        def position(i):
            return dict(schemaVersion=2, artifact='BTL-TICK-POSITION-2',
                        datasetId='fixture:qa',datasetVersion=self.version,manifestHash=self.version,
                        directoryIndex='0',partitionIndex='0',chunkIndex=str(i//2),
                        eventOffset=str(i%2),globalOrdinal=str(i))
        self.rows = [dict(ordinal=i,time_ns=100+i,position=position(i),next_position=position(i+1),
                         tick=dict(schemaVersion=1,artifact='FIXTURE',datasetVersion=self.version,
                                   timeNs=str(100+i),bid='1.000',ask='1.001')) for i in range(4)]
        pq.write_table(pa.Table.from_pylist(self.rows), self.path,row_group_size=1)
        entry=dict(path=str(self.path),sha256=file_sha(self.path))
        self.manifest=dict(datasetId='fixture:qa',datasetVersion=self.version,requestedStartNs='99',
                           layouts={'single':[entry],'daily':[entry]})

    def tearDown(self): self.temp.cleanup()

    def provider(self, layout='single', manifest=None):
        return ParquetDayProvider('.',self.version,manifest or self.manifest,layout,delegate=Metadata())

    def test_same_pages_preserve_original_chunk_positions_and_precision(self):
        for layout in ('single','daily'):
            p=self.provider(layout)
            try:
                found=p.locate_v2('fixture:qa',self.version,'99')
                page=p.read_page_v2('fixture:qa',self.version,found['position'])
                self.assertEqual(page['events'],[x['tick'] for x in self.rows[:2]])
                self.assertEqual(page['nextPosition'],self.rows[1]['next_position'])
                self.assertFalse(page['endOfDataset'])
                second=p.read_page_v2('fixture:qa',self.version,page['nextPosition'],1)
                self.assertEqual(second['events'],[self.rows[2]['tick']])
            finally:p.close()

    def test_corruption_is_refused_before_read(self):
        with self.path.open('ab') as f:f.write(b'corrupt')
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):self.provider()

    def test_outside_coverage_is_not_false_eof_or_fallback(self):
        p=self.provider()
        try:
            for target in ('98','104'):
                with self.assertRaisesRegex(ValueError,'OUTSIDE'):p.locate_v2('fixture:qa',self.version,target)
            with self.assertRaisesRegex(ValueError,'UNPROVEN_DATASET_EOF'):p.read_page_v2('fixture:qa',self.version,None)
        finally:p.close()

    def test_position_tamper_and_dataset_mismatch_are_refused(self):
        p=self.provider()
        try:
            pos=deepcopy(self.rows[0]['position']);pos['eventOffset']='9'
            with self.assertRaisesRegex(ValueError,'POSITION_MISMATCH'):p.read_page_v2('fixture:qa',self.version,pos)
            with self.assertRaisesRegex(ValueError,'IDENTITY_MISMATCH'):p.locate_v2('wrong',self.version,'100')
        finally:p.close()

    def test_manifest_identity_mismatch_is_refused(self):
        manifest=deepcopy(self.manifest);manifest['datasetVersion']='b'*64
        with self.assertRaisesRegex(ValueError,'IDENTITY_MISMATCH'):self.provider(manifest=manifest)


if __name__ == '__main__': unittest.main()
