import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:
    from tests import qa_duckdb_day_worker as worker
    import pyarrow
except ImportError:
    worker = None


@unittest.skipIf(worker is None, 'optional DuckDB QA dependencies are not installed')
class DuckWorkerLaunchTests(unittest.TestCase):
    def test_cold_worker_retains_optional_dependency_path_after_pg_env_reset(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json';path.write_text('{}')
            env=dict(BTL_PARQUET_DAY_LAYOUT='single',BTL_PARQUET_DAY_MANIFEST=str(path),
                     BTL_PARQUET_DAY_MANIFEST_SHA256=hashlib.sha256(path.read_bytes()).hexdigest())
            with patch.dict(os.environ,env), patch.object(worker.historical,'load_source'), \
                 patch.object(worker.historical,'MIN_FREE'), patch.object(worker.historical,'MAX_RAM'), \
                 patch.object(worker.arrow_bootstrap,'ParquetDayProvider'), patch('subprocess.run') as native:
                worker.install()
                subprocess.run([sys.executable,'-B','-m','tests.qa_historical_day_v2','--worker'],
                               env={'PYTHONPATH':'/fixture/backend','BTL_TEST_DATABASE_URL':'fixture'})
                args,kwargs=native.call_args
                self.assertIn('tests.qa_duckdb_day_worker',args[0])
                self.assertIn(str(Path(pyarrow.__file__).parents[1]),kwargs['env']['PYTHONPATH'])
                self.assertIn('/fixture/backend',kwargs['env']['PYTHONPATH'])
                self.assertEqual(kwargs['env']['BTL_TEST_DATABASE_URL'],'fixture')
