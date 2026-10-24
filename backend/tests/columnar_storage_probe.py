"""Offline, optional-dependency experiment; never a production provider/admission.

Run from repository root with PYTHONPATH including backend and the existing runtime
site-packages. See --help. Prepare requires a NEW private output directory.
Raw/validation/identity stores remain retained. ORDER BY ordinal reconstructs
recorded source order ONLY; it does not assert trusted market ordering.
"""
import argparse
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import resource
import shutil
import sqlite3
import sys
import time

BATCH = 4096


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def size(path):
    p = Path(path)
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.is_dir() else p.stat().st_size


def stats(values):
    ordered = sorted(values)
    return {'count': len(values), 'p50Ms': ordered[len(ordered)//2]*1000,
            'p95Ms': ordered[math.ceil(len(ordered)*.95)-1]*1000}


def measure(fn):
    wall, cpu = time.perf_counter(), time.process_time()
    result = fn()
    return result, {'wallSeconds': time.perf_counter()-wall, 'cpuSeconds': time.process_time()-cpu}


def provider(plan):
    from ticks.storage_v2 import DiskTickProvider
    p = DiskTickProvider(Path(plan['out'])/'snapshot', plan['report']['datasetVersion'])
    assert p.dataset_id == plan['report']['datasetId']
    return p


def start_ns(plan):
    from ticks.histdata_v2 import parse_record
    return parse_record((plan['report']['firstTimestamp']+',1,1\n').encode('ascii'))[1]


def pages(p, start):
    pos = p.locate_v2(p.dataset_id, p.dataset_version, str(start))['position']
    while pos is not None:
        page = p.read_page_v2(p.dataset_id, p.dataset_version, pos, 256)
        yield page['events']
        pos = page['nextPosition']


def canonical(row):
    from contracts.canonical import canonical_bytes
    return canonical_bytes(row)


def batches(rows):
    while part := list(itertools.islice(rows, BATCH)):
        yield part


def schema():
    import pyarrow as pa
    return pa.schema([('ordinal', pa.int64()), ('time_ns', pa.int64()),
                      ('bid', pa.string()), ('ask', pa.string()), ('event_id', pa.string()),
                      ('source_id', pa.string()), ('raw_ordinal', pa.string()),
                      ('canonical', pa.binary()), ('sha256', pa.binary(32)), ('raw_record', pa.binary())])


def encoded(row, ordinal, raw=b''):
    wire = canonical(row)
    return dict(ordinal=ordinal, time_ns=int(row['timeNs']), bid=row['bid'], ask=row['ask'],
                event_id=row['eventId'], source_id=row['provenance']['sourceId'],
                raw_ordinal=row['rawOrdinal'], canonical=wire, sha256=hashlib.sha256(wire).digest(), raw_record=raw)


def write_parquet(path, rows):
    import pyarrow as pa
    import pyarrow.parquet as pq
    with pq.ParquetWriter(path, schema(), compression='zstd', compression_level=6,
                          use_dictionary=True, write_statistics=True) as writer:
        for part in batches(iter(rows)):
            writer.write_table(pa.Table.from_pylist(part, schema=schema()), row_group_size=BATCH)


def duck(path, temp):
    import duckdb
    # Embedded local query only. No extension install, service, user SQL or credentials.
    con = duckdb.connect(':memory:', config={'threads': '1', 'memory_limit': '256MB',
        'temp_directory': str(temp), 'autoinstall_known_extensions': 'false',
        'autoload_known_extensions': 'false'})
    con.read_parquet(str(path)).create_view('ticks')
    return con


def records_hash(rows):
    h = hashlib.sha256(); raw_h = hashlib.sha256(); count = 0; previous = -1
    for row in rows:
        assert row['ordinal'] == count and row['time_ns'] >= previous
        blob = row['canonical']; event = json.loads(blob)
        assert hashlib.sha256(blob).digest() == row['sha256']
        assert canonical(event) == blob
        assert (int(event['timeNs']), event['bid'], event['ask'], event['eventId'],
                event['provenance']['sourceId'], event['rawOrdinal']) == (
                row['time_ns'], row['bid'], row['ask'], row['event_id'], row['source_id'], row['raw_ordinal'])
        from ticks.contracts import CanonicalTick
        CanonicalTick.from_wire(event)
        h.update(len(blob).to_bytes(4, 'big')); h.update(blob)
        raw_h.update(row['raw_record']); count += 1; previous = row['time_ns']
    return {'rows': count, 'canonicalStreamSha256': h.hexdigest(), 'rawPrefixSha256': raw_h.hexdigest()}


def export(plan):
    from ticks.histdata_v2 import parse_record
    out = Path(plan['out']); assert not (out/'ticks.parquet').exists(); p = provider(plan); samples = []; h = hashlib.sha256(); raw_h = hashlib.sha256()
    count = 0; previous = None; group_count = 0
    def rows():
        nonlocal count, previous, group_count
        with gzip.open(plan['source'], 'rb') as source:
            assert source.readline().strip() == b'timestamp_utc,bid,ask'
            for page in pages(p, start_ns(plan)):
                for event in page:
                    if count >= plan['limit'] and event['timeNs'] != previous:
                        return
                    raw = source.readline(8193); parsed = parse_record(raw)
                    assert parsed == (event['provenance']['originalTimestamp'], event['timeNs'], event['bid'], event['ask'])
                    assert event['rawOrdinal'] == str(count)
                    row = encoded(event, count, raw)
                    h.update(len(row['canonical']).to_bytes(4, 'big')); h.update(row['canonical']); raw_h.update(raw)
                    if count % max(1, plan['limit']//20) == 0: samples.append({'ordinal': count, 'timeNs': event['timeNs']})
                    group_count += event['timeNs'] != previous; previous = event['timeNs']; count += 1
                    yield row
    try:
        _, timing = measure(lambda: write_parquet(out/'ticks.parquet', rows()))
    finally:
        p.close()
    import pyarrow, pyarrow.parquet as pq
    report = {'rows': count, 'timestampGroups': group_count, 'canonicalStreamSha256': h.hexdigest(),
              'rawPrefixSha256': raw_h.hexdigest(), 'samples': samples, 'conversion': timing,
              'parquetBytes': size(out/'ticks.parquet'), 'parquetSha256': digest(out/'ticks.parquet'),
              'rowGroups': pq.ParquetFile(out/'ticks.parquet').num_row_groups, 'pyarrowVersion': pyarrow.__version__,
              'source': plan['report']['source'], 'datasetId': plan['report']['datasetId'],
              'datasetVersion': plan['report']['datasetVersion'], 'reportSha256': plan['reportSha256'],
              'scope': 'BOUNDED_REFERENCE_PREFIX_NOT_ADMISSION', 'trustedSequence': False, 'rights': 'UNKNOWN'}
    (out/'manifest.json').write_text(json.dumps(report, indent=2))
    return report


def group_digest(events):
    from ticks.timeline import make_group
    h = hashlib.sha256()
    for _, group in itertools.groupby(events, key=lambda r: r['timeNs']):
        rows = list(group); blob = canonical({'schemaVersion':1,'artifact':'BTL-TICK-GROUP-CHECK-1','group':make_group(rows, rows[0]['datasetVersion'])})
        h.update(len(blob).to_bytes(4, 'big')); h.update(blob)
    return h.hexdigest()


def query_probe(plan, kind):
    out = Path(plan['out']); m = json.loads((out/'manifest.json').read_text()); seeks = []; replays = []; checks = []
    p = provider(plan) if kind == 'baseline' else None
    con = duck(out/'ticks.parquet', out/'duck-tmp') if p is None else None
    for sample in m['samples']:
        start = int(sample['timeNs']); end = start + 10**9
        def seek():
            if p is not None:
                return next(pages(p, start), [])
            return [json.loads(r[0]) for r in con.execute(
                'SELECT canonical FROM ticks WHERE time_ns >= ? ORDER BY ordinal LIMIT 256', [start]).fetchall()]
        page, t = measure(seek); seeks.append(t['wallSeconds'])
        assert page and all(int(r['timeNs']) >= start for r in page)
        # Seek page lengths differ at SQLite chunk boundaries; only group-replay
        # hashes below compare identical complete timestamp intervals.
        def replay():
            if p is not None:
                events = []
                for part in pages(p, start):
                    events.extend(r for r in part if int(r['timeNs']) <= end)
                    if any(int(r['timeNs']) > end for r in part): break
            else:
                events = [json.loads(r[0]) for r in con.execute(
                    'SELECT canonical FROM ticks WHERE time_ns BETWEEN ? AND ? ORDER BY ordinal', [start, end]).fetchall()]
            # Both bounds include complete timestamp groups. No future/EOF projected to consumers.
            return group_digest(events)
        group_hash, t = measure(replay); replays.append(t['wallSeconds'])
        checks.append(group_hash)
    if p is not None:p.close()
    if con is not None:con.close()
    return {'seek': stats(seeks), 'groupReplay': stats(replays), 'checks': checks,
            'scope': '20 new seeks; handles reused; OS page cache uncontrolled; controller-only group hash, not full UI latency'}



def query_only(plan):
    return query_probe(plan, 'candidate')


def arrow_only(plan):
    import pyarrow.parquet as pq
    out = Path(plan['out']); m = json.loads((out/'manifest.json').read_text())
    def rows():
        for batch in pq.ParquetFile(out/'ticks.parquet').iter_batches(batch_size=BATCH, use_threads=False):
            yield from batch.to_pylist()
    result, timing = measure(lambda: records_hash(rows()))
    assert all(result[k] == m[k] for k in ('rows','canonicalStreamSha256','rawPrefixSha256'))
    return {'scan':timing,'parity':result}


def candidate(plan):
    import pyarrow.parquet as pq
    out = Path(plan['out']); m = json.loads((out/'manifest.json').read_text())
    def scan():
        for batch in pq.ParquetFile(out/'ticks.parquet').iter_batches(batch_size=BATCH, use_threads=False):
            yield from batch.to_pylist()
    arrow, at = measure(lambda: records_hash(scan()))
    con = duck(out/'ticks.parquet', out/'duck-tmp')
    def scan_duck():
        names = [f.name for f in schema()]
        cursor = con.execute('SELECT * FROM ticks ORDER BY ordinal')
        while part := cursor.fetchmany(BATCH):
            yield from (dict(zip(names, r)) for r in part)
    duck_result, dt = measure(lambda: records_hash(scan_duck())); con.close()
    assert arrow == duck_result
    assert all(arrow[k] == m[k] for k in ('rows','canonicalStreamSha256','rawPrefixSha256'))
    result = query_probe(plan, 'candidate')
    return dict(result, arrowFullScan=at, duckFullScan=dt, tickParity=arrow)


def baseline(plan):
    p = provider(plan); m = json.loads((Path(plan['out'])/'manifest.json').read_text())
    def scan():
        count = 0
        for part in pages(p, start_ns(plan)):
            for event in part:
                if count == m['rows']:return count
                count += 1
        return count
    count, timing = measure(scan); p.close(); assert count == m['rows']
    return dict(query_probe(plan, 'baseline'), fullValidatedScan=timing, rows=count)


class RoundTripProvider:
    """TEST ONLY page-payload substitution; delegates existing manifest/tokens.

    This deliberately does not claim a standalone production provider contract.
    Original source manifest/chunk hashes are rechecked by the existing timeline.
    """
    def __init__(self, original, path):
        self.original = original; self.dataset_id = original.dataset_id; self.dataset_version = original.dataset_version
        token = None; rows = []
        while True:
            page = original.read_page(self.dataset_id, self.dataset_version, token, 64)
            offset = len(rows)
            rows.extend(encoded(e, offset+i) for i,e in enumerate(page['events']))
            assert len(rows) <= 4096  # authored financial fixtures only
            token = page['nextToken']
            if page['endOfDataset']:break
        write_parquet(path, rows)
        self.con = duck(path, path.parent/'tmp')
    def describe(self, *args):return self.original.describe(*args)
    def read_page(self, *args):
        page = self.original.read_page(*args)
        ids = [e['eventId'] for e in page['events']]
        if ids:
            rows = self.con.execute('SELECT canonical FROM ticks WHERE event_id IN (SELECT unnest(?)) ORDER BY ordinal',[ids]).fetchall()
            rebuilt = [json.loads(r[0]) for r in rows]
            assert rebuilt == page['events']; page['events'] = rebuilt
        return page
    def close(self):self.con.close()


def financial(plan):
    from tests.test_kernel_v2 import fixture, scene_system, opening
    outputs = []
    fixture_dir = Path(plan['out'])/'financial-fixtures'; fixture_dir.mkdir(mode=0o700)
    for index, case in enumerate(fixture()['scenes']):
        outcomes=[]
        for mode in ('baseline','parquet'):
            h = scene_system(case['symbol'],case['primaryRows'],case['conversionRows']); wrappers=[]
            if mode == 'parquet':
                h.primary = RoundTripProvider(h.primary,fixture_dir/f'fixture-{index}-primary.parquet');wrappers.append(h.primary)
                if h.fx is not None:h.fx=RoundTripProvider(h.fx,fixture_dir/f'fixture-{index}-fx.parquet');wrappers.append(h.fx)
            try:
                h.tick(100);h.apply('OPEN',opening(case['side'],case['quantity']),'open');h.tick(110)
                h.apply('CLOSE',{'orderId':'open','quantity':None});h.tick(120)
                for key in ('balance','realizedGross','commission'):assert h.state[key]==case['expected'][key]
                assert h.state['orders']['open']['status']==case['expected']['status']
                outcomes.append(canonical({'schemaVersion':1,'artifact':'BTL-OFFLINE-PARITY-1','state':h.state,'events':h.events,'checkpoint':h.checkpoint}))
            finally:
                for w in wrappers:w.close()
        assert outcomes[0]==outcomes[1];outputs.append(hashlib.sha256(outcomes[0]).hexdigest())
    # Authored AUDJPY/CHFJPY use USDJPY conversion; fresh and stale evidence via unchanged kernel/source tests.
    from tests.test_profile_v2 import vectors
    routes={v['name']:v['input']['conversion']['symbol'] for v in vectors() if v['name'] in ('AUDJPY','CHFJPY')}
    assert routes=={'AUDJPY':'USDJPY','CHFJPY':'USDJPY'}
    from tests.test_sources_v2 import setup
    from execution.sources_v2 import SourceJoinV2
    route_evidence = {}
    selected = {'EURUSD','GBPUSD','AUDUSD','USDCHF','EURGBP','AUDJPY','CHFJPY','XAUUSD'}
    assert 'USDJPY' not in selected
    for symbol in routes:
        status = []
        for t in (100, 61000000100):
            profile, primary, fx = setup(symbol=symbol, primary_rows=[(t,'150','150.002')],
                                         fx_rows=[(50,'150','150.002'),(200000000000,'151','151.002')])
            join = SourceJoinV2(profile, primary, start_ns=str(t), conversion_provider=fx)
            frame = join.reveal(str(t), join.checkpoint())
            status.append(frame['pairs'][0]['conversionStatus'])
            if t == 100:
                fresh_profile = profile
                fresh_group = frame['conversionGroups'][frame['pairs'][0]['conversionGroupId']]
        # Synthetic selector bounds its lookup window and reports MISSING once
        # the old group is outside it. The direct validator reports STALE.
        assert status == ['ELIGIBLE_SYNTHETIC','UNRESOLVED_FX_MISSING']
        from execution.conversion import convert_usd
        from contracts.primitives import ContractError
        convert_usd('1','JPY','100',pin=fresh_profile.wire['conversion'],group=fresh_group)
        try:
            convert_usd('1','JPY','61000000100',pin=fresh_profile.wire['conversion'],group=fresh_group)
        except ContractError as error:
            assert error.code == 'UNRESOLVED_FX_STALE'
        else:
            raise AssertionError('STALE_FX_NOT_REFUSED')
        route_evidence[symbol] = {'selector':status, 'directStaleRefusal':True}
    return {'scenes':len(outputs),'exactStateEventCheckpointParity':True,'hashes':outputs,'internalRoutes':routes,
            'freshStaleRouteEvidence':route_evidence, 'realHistoricalFinancialAcceptance':False}



def recovery(plan):
    import pyarrow.parquet as pq
    out = Path(plan['out']); original = out/'ticks.parquet'
    backup = out/'backup.parquet'; restored = out/'restored.parquet'
    assert not backup.exists() and not restored.exists()
    for src, dst in ((original, backup), (backup, restored)):
        with src.open('rb') as read, dst.open('xb') as write:
            shutil.copyfileobj(read, write, 1024*1024); write.flush(); os.fsync(write.fileno())
    assert digest(original) == digest(backup) == digest(restored)
    def rows():
        for batch in pq.ParquetFile(restored).iter_batches(batch_size=BATCH, use_threads=False):
            yield from batch.to_pylist()
    result = records_hash(rows()); m = json.loads((out/'manifest.json').read_text())
    assert all(result[k] == m[k] for k in ('rows','canonicalStreamSha256','rawPrefixSha256'))
    # Negative integrity check: same canonical bytes, altered declared digest.
    row = next(rows()); row['sha256'] = b'0'*32
    try:
        records_hash([row])
    except AssertionError:
        pass
    else:
        raise AssertionError('CORRUPT_HASH_NOT_REFUSED')
    return {'newCopyRestored':True, 'tamperedHashRefused':True, 'parity':result,
            'backupBytes':size(backup), 'restoreBytes':size(restored),
            'scope':'LOCAL_COPY_ONLY_NOT_OFFHOST_DISASTER_RECOVERY'}


def prepare(plan):
    out=Path(plan['out']);out.mkdir(mode=0o700,parents=True,exist_ok=False);(out/'snapshot').mkdir(mode=0o700)
    before=digest(Path(plan['store'])/'archive.sqlite');source_before=digest(plan['source'])
    assert source_before==plan['report']['source']['sha256']
    src=sqlite3.connect((Path(plan['store'])/'archive.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    dst=sqlite3.connect(out/'snapshot/archive.sqlite')
    try:src.backup(dst)
    finally:dst.close();src.close()
    assert digest(Path(plan['store'])/'archive.sqlite')==before
    return {'originalArchiveSha256':before,'sourceSha256':source_before,'snapshotBytes':size(out/'snapshot'),
            'originalStoreBytes':size(plan['store']),'sourceBytes':size(plan['source'])}


def main():
    if not __debug__:raise RuntimeError('Integrity assertions require Python without -O')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True,help='private JSON with out,store,source,report,reportSha256,limit (<=100000)')
    parser.add_argument('--phase',choices=('prepare','export','baseline','candidate','financial','recovery','arrow_only','query_only'),required=True)
    args=parser.parse_args();plan=json.loads(Path(args.plan).read_text());assert type(plan['limit']) is int and 1<=plan['limit']<=100000
    assert Path(plan['out']).resolve()!=Path(plan['store']).resolve()
    os.nice(10)
    if hasattr(os,'sched_getaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert not (Path(plan['out'])/(args.phase+'-result.json')).exists()
    result,timing=measure(lambda:globals()[args.phase](plan))
    status = dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    result.update(processTiming=timing,procVmHwmBytes=int(status['VmHWM'].split()[0])*1024,
                  peakRssBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                  environment={'python':sys.version.split()[0],'cpuAffinity':sorted(os.sched_getaffinity(0))})
    path=Path(plan['out'])/(args.phase+'-result.json')
    with path.open('x') as f:json.dump(result,f,indent=2)
    print(json.dumps({'phase':args.phase,'report':str(path),'timing':timing,'peakRssBytes':result['peakRssBytes']}),flush=True)


if __name__=='__main__':main()
