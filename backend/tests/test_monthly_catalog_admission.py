"""Catalog selector admission does not load the Parquet runtime."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from contracts.canonical import canonical_bytes
from market_data.monthly_catalog import CATALOG_ARTIFACT


class MonthlyCatalogAdmissionTests(unittest.TestCase):
    def test_public_catalog_loads_without_pyarrow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'catalog.json'
            value = dict(schemaVersion=1, artifact=CATALOG_ARTIFACT, catalogVersion=1,
                sources=[dict(key='source:synthetic', period='2024-01', label='Synthetic January',
                    root='/srv/riksora/synthetic', datasetId='dataset:synthetic',
                    datasetVersion='a' * 64, manifestSha256='b' * 64,
                    eligibility='SYNTHETIC', eligibilityEvidenceSha256=None)])
            raw = canonical_bytes(value)
            path.write_bytes(raw)
            path.chmod(0o400)
            code = (
                'import sys; '
                'from market_data.monthly_catalog import MonthlyParquetCatalog; '
                f'catalog=MonthlyParquetCatalog({str(path)!r},{hashlib.sha256(raw).hexdigest()!r}); '
                'assert catalog.public()[0]["model"] == "SYNTHETIC_FIXTURE"; '
                'assert "pyarrow" not in sys.modules'
            )
            environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
            result = subprocess.run([sys.executable, '-c', code], env=environment,
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
