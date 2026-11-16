import unittest
from tests.test_qa_parquet_day_provider import ParquetDayTests, Metadata
try:
    from tests.qa_duckdb_day_provider import DuckDBDayProvider
except ImportError:
    DuckDBDayProvider = None


@unittest.skipIf(DuckDBDayProvider is None, 'optional DuckDB/Parquet QA dependencies are not installed')
class DuckDBDayTests(ParquetDayTests):
    def provider(self, layout='single', manifest=None):
        return DuckDBDayProvider('.',self.version,manifest or self.manifest,layout,delegate=Metadata())
