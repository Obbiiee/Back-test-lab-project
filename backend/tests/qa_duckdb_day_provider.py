"""Optional embedded DuckDB reader for the isolated one-day gate only."""
import duckdb

from contracts.canonical import canonical_bytes
from tests.qa_parquet_day_provider import ParquetDayProvider


class DuckDBDayProvider(ParquetDayProvider):
    def __init__(self, folder, version, manifest, layout, *, delegate=None):
        self.paths = [entry['path'] for entry in manifest['layouts'][layout]]
        super().__init__(folder, version, manifest, layout, delegate=delegate)
        try:
            self.db = duckdb.connect(':memory:', config={
                'threads': '1', 'memory_limit': '128MB',
                'autoload_known_extensions': 'false',
                'autoinstall_known_extensions': 'false',
                'allow_unsigned_extensions': 'false',
                'preserve_insertion_order': 'true',
            })
            # Spill is unnecessary for bounded ordered row-group retrieval.
            # Refuse rather than silently spilling outside the QA budget.
            self.db.execute("SET max_temp_directory_size='0B'")
        except BaseException:
            super().close()
            raise

    def close(self):
        self.db.close()
        super().close()

    def _rows(self, index):
        if index not in self.cache:
            g = self.groups[index]
            # The superclass preserves files in manifest order. Match its
            # verified ParquetFile handle to the exact local manifest path.
            path = self.paths[self.files.index(g[4])]
            cursor = self.db.execute(
                'SELECT * FROM read_parquet(?) WHERE ordinal BETWEEN ? AND ? '
                'AND time_ns BETWEEN ? AND ? ORDER BY ordinal',
                [path, g[0], g[1], g[2], g[3]])
            names = [c[0] for c in cursor.description]
            rows = []
            while True:
                batch = cursor.fetchmany(256)
                if not batch:
                    break
                rows.extend(dict(zip(names,row)) for row in batch)
                if len(rows) > 4096:
                    raise ValueError('DUCKDB_ROW_GROUP_BOUND_EXCEEDED')
            if len(rows) != g[1]-g[0]+1:
                raise ValueError('DUCKDB_ROW_GROUP_COUNT_MISMATCH')
            for offset,row in enumerate(rows):
                if (row['ordinal'] != g[0]+offset or
                        int(row['tick']['timeNs']) != row['time_ns'] or
                        int(row['position']['globalOrdinal']) != row['ordinal'] or
                        row['tick']['datasetVersion'] != self.dataset_version):
                    raise ValueError('DUCKDB_RECORD_BINDING_INVALID')
                canonical_bytes(row['tick'])
            self.cache[index] = rows
            while len(self.cache)>2:
                self.cache.popitem(last=False)
        self.cache.move_to_end(index)
        return self.cache[index]
