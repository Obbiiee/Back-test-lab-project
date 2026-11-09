import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from market_data.monthly_catalog import CATALOG_ARTIFACT, MonthlyParquetCatalog
from market_data.monthly_parquet import write_monthly_parquet
from tests.test_monthly_parquet import JAN_LAST, FEB_FIRST
from ticks.provider import SyntheticTickProvider


class MonthlyCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'dataset'
        source = SyntheticTickProvider([
            dict(ordinal='0', timeNs=str(JAN_LAST - 1), bid='1.001', ask='1.003', sequence=None),
            dict(ordinal='1', timeNs=str(FEB_FIRST), bid='1.002', ask='1.004', sequence=None),
        ], chunk_size=2)
        events = []
        token = None
        while True:
            page = source.read_page(source.dataset_id, source.dataset_version, token, 64)
            events.extend(page['events'])
            if page['endOfDataset']:
                break
            token = page['nextToken']
        manifest = write_monthly_parquet(self.root, iter(events),
            source.describe(source.dataset_id, source.dataset_version),
            expected_version=source.dataset_version, row_group_size=2)
        self.dataset = (source, manifest)

    def tearDown(self):
        self.temp.cleanup()

    def catalog_file(self, *, eligibility='SYNTHETIC', evidence=None, root=None):
        source, manifest = self.dataset
        value = dict(schemaVersion=1, artifact=CATALOG_ARTIFACT, catalogVersion=1,
            sources=[dict(key='source:synthetic', period='2024-01', label='Synthetic January',
                root=str(root or self.root), datasetId=source.dataset_id,
                datasetVersion=source.dataset_version, manifestSha256=manifest['manifestHash'],
                eligibility=eligibility, eligibilityEvidenceSha256=evidence)])
        path = Path(self.temp.name) / 'monthly-catalog.json'
        raw = canonical_bytes(value)
        path.write_bytes(raw)
        path.chmod(0o400)
        return path, hashlib.sha256(raw).hexdigest()

    def test_operator_catalog_resolves_only_pinned_shared_dataset(self):
        path, sha = self.catalog_file()
        catalog = MonthlyParquetCatalog(path, sha)
        public = catalog.public()
        self.assertEqual(public, [dict(key='source:synthetic', period='2024-01',
                                       label='Synthetic January', layout='MONTHLY_PARQUET_ZSTD',
                                       eligibility='SYNTHETIC', model='SYNTHETIC_FIXTURE')])
        self.assertNotIn('root', public[0])
        first = catalog.resolve('source:synthetic', '2024-01')
        second = catalog.resolve('source:synthetic', '2024-01')
        self.assertIs(first, second)
        self.assertTrue(first.verify_file_hash('2024-01'))
        self.assertEqual(first.dataset_id, self.dataset[0].dataset_id)
        self.assertEqual(first.first_time_for_month('2024-01'), JAN_LAST - 1)
        with self.assertRaises(ContractError):
            catalog.resolve('source:synthetic', '2024-02')
        catalog.close()

    def test_non_synthetic_rights_evidence_cannot_promote_synthetic_manifest(self):
        path, sha = self.catalog_file(eligibility='RIGHTS_EVIDENCE_PINNED', evidence='a' * 64)
        catalog = MonthlyParquetCatalog(path, sha)
        self.assertEqual(catalog.public(), [])
        with self.assertRaises(ContractError):
            catalog.resolve('source:synthetic', '2024-01')

    def test_catalog_hash_and_file_permissions_are_pinned(self):
        path, sha = self.catalog_file()
        with self.assertRaises(ContractError):
            MonthlyParquetCatalog(path, '0' * 64)
        path.chmod(0o600)
        with self.assertRaises(ContractError):
            MonthlyParquetCatalog(path, sha)


if __name__ == '__main__':
    unittest.main()
