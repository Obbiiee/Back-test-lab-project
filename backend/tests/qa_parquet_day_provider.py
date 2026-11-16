"""Private bounded QA projection; never mounted by production/admission APIs."""
from bisect import bisect_left
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from contracts.canonical import canonical_bytes
from ticks.contracts_v2 import canonical_v2_bytes
from ticks.provider import empty_diagnostics
from ticks.storage_v2 import DiskTickProvider


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def chunk_key(position):
    return tuple(position[k] for k in ('directoryIndex', 'partitionIndex', 'chunkIndex'))


class ParquetDayProvider:
    """Exact original position wires, bounded read cache, explicit scope refusal.

    Canonical SQLite supplies only frozen publication/sidecar metadata here.
    Tick pages and seeks come exclusively from validated Parquet projections.
    """
    def __init__(self, folder, version, manifest, layout, *, delegate=None):
        if layout not in ('single', 'daily'):
            raise ValueError('INVALID_LAYOUT')
        pa.set_cpu_count(1)
        pa.set_io_thread_count(1)
        self.meta = delegate or DiskTickProvider(folder, version, allow_threads=True, read_only=True)
        self.dataset_id, self.dataset_version = self.meta.dataset_id, version
        self.cache = OrderedDict()
        self.files = []
        self.groups = []
        try:
            if manifest['datasetVersion'] != version or manifest['datasetId'] != self.dataset_id:
                raise ValueError('PROJECTION_IDENTITY_MISMATCH')
            self.low_ns = int(manifest['requestedStartNs'])
            for entry in manifest['layouts'][layout]:
                path = Path(entry['path'])
                if path.is_symlink() or file_sha(path) != entry['sha256']:
                    raise ValueError('PROJECTION_HASH_MISMATCH')
                pf = pq.ParquetFile(path)
                names = pf.schema_arrow.names
                if names != ['ordinal', 'time_ns', 'position', 'next_position', 'tick']:
                    raise ValueError('PROJECTION_SCHEMA_MISMATCH')
                self.files.append(pf)
                # Nested columns precede tick fields; first two scalar columns
                # have stable physical indices in this frozen QA projection.
                for index in range(pf.metadata.num_row_groups):
                    rg = pf.metadata.row_group(index)
                    ordinal, moment = rg.column(0).statistics, rg.column(1).statistics
                    if ordinal is None or moment is None:
                        raise ValueError('PROJECTION_STATISTICS_MISSING')
                    self.groups.append((ordinal.min, ordinal.max, moment.min, moment.max, pf, index))
            self.groups.sort(key=lambda item: item[0])
            if not self.groups or any(a[1]+1 != b[0] or a[3] > b[2]
                                      for a,b in zip(self.groups,self.groups[1:])):
                raise ValueError('PROJECTION_ORDER_OR_COVERAGE_INVALID')
            self.ordinal_ends = [g[1] for g in self.groups]
            self.time_ends = [g[3] for g in self.groups]
        except BaseException:
            self.meta.close()
            raise

    def close(self):
        self.cache.clear()
        self.meta.close()
        for pf in self.files:
            pf.close()

    def _identity(self, dataset, version):
        if dataset != self.dataset_id or version != self.dataset_version:
            raise ValueError('PROJECTION_IDENTITY_MISMATCH')

    def _rows(self, index):
        if index not in self.cache:
            g = self.groups[index]
            rows = g[4].read_row_group(g[5], use_threads=False).to_pylist()
            for row in rows:
                event = row['tick']
                if (int(event['timeNs']) != row['time_ns'] or
                        int(row['position']['globalOrdinal']) != row['ordinal'] or
                        event['datasetVersion'] != self.dataset_version):
                    raise ValueError('PROJECTION_RECORD_BINDING_INVALID')
                canonical_bytes(event)
            self.cache[index] = rows
            while len(self.cache) > 2:
                self.cache.popitem(last=False)
        self.cache.move_to_end(index)
        return self.cache[index]

    def describe_v2(self, dataset, version):
        self._identity(dataset, version)
        return self.meta.describe_v2(dataset, version)

    def read_evidence_v2(self, request):
        return self.meta.read_evidence_v2(request)

    def locate_v2(self, dataset, version, target_ns):
        self._identity(dataset, version)
        target = int(target_ns)
        i = bisect_left(self.time_ends, target)
        if target < self.low_ns or i == len(self.groups):
            raise ValueError('OUTSIDE_PARQUET_QA_COVERAGE')
        for row in self._rows(i):
            if row['time_ns'] >= target:
                return dict(position=deepcopy(row['position']), groupTimeNs=str(row['time_ns']))
        raise ValueError('PARQUET_SEEK_STATISTICS_MISMATCH')

    def read_page_v2(self, dataset, version, position, max_events=256):
        self._identity(dataset, version)
        if type(max_events) is not int or not 1 <= max_events <= 256:
            raise ValueError('INVALID_PAGE_LIMIT')
        if position is None:
            raise ValueError('UNPROVEN_DATASET_EOF')
        ordinal = int(position['globalOrdinal'])
        i = bisect_left(self.ordinal_ends, ordinal)
        if i == len(self.groups) or ordinal < self.groups[i][0]:
            raise ValueError('OUTSIDE_PARQUET_QA_COVERAGE')
        selected = []
        key = chunk_key(position)
        while i < len(self.groups) and len(selected) < max_events:
            for row in self._rows(i):
                if row['ordinal'] < ordinal:
                    continue
                if not selected and row['position'] != position:
                    raise ValueError('PROJECTION_POSITION_MISMATCH')
                if chunk_key(row['position']) != key:
                    break
                selected.append(row)
                if len(selected) == max_events:
                    break
            if selected and (selected[-1]['next_position'] is None or
                             chunk_key(selected[-1]['next_position']) != key):
                break
            i += 1
        if not selected:
            raise ValueError('PROJECTION_PAGE_EMPTY')
        while selected:
            next_position = selected[-1]['next_position']
            result = dict(schemaVersion=2, artifact='BTL-TICK-PAGE-2', datasetId=dataset,
                          datasetVersion=version, events=[r['tick'] for r in selected],
                          diagnostics=empty_diagnostics(), nextPosition=next_position,
                          endOfDataset=next_position is None)
            try:
                canonical_v2_bytes(result)
                return deepcopy(result)
            except ValueError:
                selected = selected[:len(selected)//2]
        raise ValueError('PROJECTION_PAGE_SERIALIZATION_LIMIT')
