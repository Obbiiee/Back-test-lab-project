"""Read-only, bounded-memory verification of a completed CP6A-10 annual Session.

This program never issues Session commands. PostgreSQL is started only from an
isolated byte-for-byte snapshot and every verifier transaction is read-only.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from copy import deepcopy
import fcntl
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from threading import Event, Lock, Thread
import time
import traceback
import uuid

import psycopg
from psycopg.conninfo import make_conninfo

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require
from execution.observed_admission import AdmittedObservedSource
from execution.observed_kernel import (QA_ORDER_RETENTION_V4, STATE_QA_ARCHIVE_V1,
    validate_snapshot, validate_state)
from execution.observed_order_archive_v1 import verify_complete as verify_archive_complete
from execution.observed_profile import ObservedExecutionProfile
from execution.observed_postgres import (QA3_CHECKPOINT_BASE, QA3_CHECKPOINT_DELTA,
    QA3_CHECKPOINT, QA3_RESULT, ObservedExecutionStore, check_events)
from execution.observed_state_delta_v3 import reconstruct
from execution.postgres import unpack
from tests.qa_historical_day_v2 import (_hash_canonical_records, _financial_state_digest,
    annual_order_acceptance_upper_bound)


REPOSITORY = Path(__file__).resolve().parents[2]
SOURCE = Path('/home/riksora/riksora-qa-evidence/beta-checkpoints-20261025-jtbqjj1o/'
              'xau-binary-recovery-20261026/verified-serving-snapshot')
PROOF = Path('/home/riksora/riksora-qa-evidence/beta-checkpoints-20261025-jtbqjj1o/'
             'xau-binary-recovery-20261026/resumable-parity/final-report.json')
EXPECTED_SESSION = 'session:hist-v2:cp6a10-year-20261101'
EXPECTED_WORKSPACE = 'observedqa:hist-v2:cp6a10-year-20261101'
EXPECTED_GROUPS = 56_208_511
EXPECTED_FINAL_REVISION = 220_616
REQUESTED_START_NS = '1704067200000000000'
EXPECTED_START_NS = '1704150000312000000'
EXPECTED_TARGET_NS = '1735689599999999999'
MIN_FREE = 30 * 1024**3
MAX_RAM = 1024**3
MEMORY_HIGH = 768 * 1024**2
SOFT_RAM_STOP = 896 * 1024**2
MAX_RUNTIME = 72 * 3600
BATCH = 32
S = 1_000_000_000


class VerificationError(RuntimeError):
    pass


def _canonical_record_wire(record):
    """Encode an internal verifier record in the existing BTL-CJSON-1 envelope.

    Timeline group identity remains the frozen BTL-TICK-GROUP-ID-1 value. These
    chain entries are verifier projections, so unversioned projections use the
    same {schemaVersion: 1, record: ...} envelope as RecordHasher.
    """
    value=(record if type(record) is dict and record.get('schemaVersion') == 1
           else dict(schemaVersion=1,record=record))
    return canonical_bytes(value)


class RecordHasher:
    def __init__(self, artifact):
        self.digest = hashlib.sha256()
        self.digest.update(b'BTL-QA-FRAMED-CANONICAL-RECORDS-1\0')
        name = artifact.encode('utf-8')
        self.digest.update(len(name).to_bytes(4, 'big'))
        self.digest.update(name)
        self.count = 0

    def add(self, record):
        wire = _canonical_record_wire(record)
        self.digest.update(len(wire).to_bytes(8, 'big'))
        self.digest.update(wire)
        self.count += 1

    def hexdigest(self):
        h = self.digest.copy()
        h.update(b'\xffRECORD-COUNT\0')
        h.update(self.count.to_bytes(8, 'big'))
        return h.hexdigest()


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    raw = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode('utf-8') + b'\n'
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        dfd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _sha256_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb',buffering=0) as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def _validate_annual_preflight(path):
    raw=Path(path).read_bytes();preflight=json.loads(raw)
    cgroup=preflight.get('cgroup',{})
    if (preflight.get('status')!='PASS' or preflight.get('annualGroups')!=EXPECTED_GROUPS or
            preflight.get('annualOrderLimit')!=4096 or
            preflight.get('annualScheduleMaximumOrders')!=1469 or
            preflight.get('annualWallBudgetSeconds')!=MAX_RUNTIME or
            preflight.get('projectedAnnualArtifactBytes',0)>preflight.get('annualArtifactBudgetBytes',0) or
            preflight.get('qualificationRows')!=EXPECTED_GROUPS or
            preflight.get('minimumFreeBytes')!=MIN_FREE or
            preflight.get('sourceRights')!='UNKNOWN' or
            preflight.get('executionEligibility')!='NOT_GRANTED' or
            cgroup.get('cpuEquivalent')!=1.0 or cgroup.get('memoryMaxBytes')!=MAX_RAM or
            cgroup.get('memorySwapMaxBytes')!=0):
        raise VerificationError('ANNUAL_RESOURCE_PREFLIGHT_EVIDENCE_INVALID')
    return preflight,hashlib.sha256(raw).hexdigest()


def _seal_progress(value):
    core={k:v for k,v in value.items() if k!='recordHash'}
    value['recordHash']=content_hash(dict(schemaVersion=1,
        artifact='RIKSORA-ANNUAL-SOURCE-VERIFY-PROGRESS-2',body=core))
    return value


def _coverage_boundary_gaps(first_ns,last_ns,through_ns):
    first=int(first_ns);last=int(last_ns);through=int(through_ns);requested=int(REQUESTED_START_NS)
    if first<requested or last<first or through<last:
        raise VerificationError('SOURCE_COVERAGE_BOUNDARY_CHRONOLOGY_INVALID')
    gaps=[]
    if first-requested>60*S:
        gaps.append(dict(startNs=REQUESTED_START_NS,endNs=str(first),
            elapsedNs=str(first-requested),kind='UNKNOWN_COVERAGE_GAP',quoteAvailable=False,
            sourceQuality='UNKNOWN',boundary='REQUESTED_INTERVAL_PREFIX'))
    if through-last>60*S:
        gaps.append(dict(startNs=str(last),endNs=str(through),elapsedNs=str(through-last),
            kind='UNKNOWN_COVERAGE_GAP',quoteAvailable=False,sourceQuality='UNKNOWN',
            boundary='REQUESTED_INTERVAL_SUFFIX'))
    return gaps


def _enable_qa_shared_source_mode(annual_root):
    root=Path(annual_root).resolve(strict=True)
    if not root.is_dir():
        raise VerificationError('HISTORICAL_QA_ROOT_INVALID')
    os.environ['BTL_HISTORICAL_QA_ROOT']=str(root)
    os.environ['BTL_QA_SHARED_CANONICAL_SOURCE_V1']='1'


def _verify_timeline_session_binding(state,cursor,target_ns):
    checks={
        'groupIndex':state.get('nextGroupIndex')==str(EXPECTED_GROUPS) and
            cursor.get('nextGroupIndex')==str(EXPECTED_GROUPS),
        'target':state.get('throughNs')==target_ns and cursor.get('throughNs')==target_ns,
        'sessionStart':cursor.get('sessionStartNs')==EXPECTED_START_NS,
        'cursorRevision':str(cursor.get('revision'))==str(state.get('sourceCursorRevision')),
        'sourcePrefixHash':cursor.get('visiblePrefixHash')==state.get('sourcePrefixHash'),
    }
    if not all(checks.values()):
        failed=','.join(key for key,value in checks.items() if not value)
        raise VerificationError('TIMELINE_SESSION_CHECKPOINT_MISMATCH:'+failed)
    return dict(status='PASS',checks=checks,sessionSourceCursorRevision=state['sourceCursorRevision'],
        timelineCursorRevision=cursor['revision'],sessionSourcePrefixHash=state['sourcePrefixHash'],
        timelineVisiblePrefixHash=cursor['visiblePrefixHash'])


def _source_verification_input_hash(snapshot_manifest_sha,state_hash,source_version):
    return content_hash(dict(schemaVersion=1,
        artifact='RIKSORA-ANNUAL-SOURCE-VERIFICATION-INPUT-1',
        snapshotManifestSha256=snapshot_manifest_sha,sessionStateHash=state_hash,
        sourceVersion=source_version))


def _cgroup():
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    relative = next((r.split('::', 1)[1].lstrip('/') for r in rows if r.startswith('0::')), None)
    if relative is None:
        raise VerificationError('CGROUP_V2_REQUIRED')
    root = Path('/sys/fs/cgroup') / relative
    cpu = (root / 'cpu.max').read_text().split()
    memory_max = int((root / 'memory.max').read_text())
    memory_high = int((root / 'memory.high').read_text())
    swap_max = int((root / 'memory.swap.max').read_text())
    if len(cpu) != 2 or cpu[0] == 'max' or int(cpu[0]) / int(cpu[1]) > 1.0001:
        raise VerificationError('CPU_LIMIT_NOT_BOUNDED_TO_ONE_CORE')
    if memory_max != MAX_RAM or memory_high != MEMORY_HIGH or swap_max != 0:
        raise VerificationError('MEMORY_OR_SWAP_LIMIT_MISMATCH')
    return root


class ProcessIoSampler:
    """Sample /proc I/O for every process in the verifier cgroup."""
    def __init__(self,cgroup,interval=0.1):
        self.cgroup=Path(cgroup);self.interval=interval;self.stop_event=Event();self.lock=Lock()
        self.last={};self.finalized={key:0 for key in ('read_bytes','write_bytes','rchar','wchar')}
        self.samples=0;self.errors=0
        self.thread=Thread(target=self._run,name='riksora-cp6a10-io-sampler',daemon=True)

    def start(self):
        self._sample()
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():self.thread.join(timeout=2)

    @staticmethod
    def _process(pid):
        raw=Path(f'/proc/{pid}/stat').read_text()
        fields=raw[raw.rfind(')')+2:].split()
        start_time=int(fields[19])
        values={}
        for line in Path(f'/proc/{pid}/io').read_text().splitlines():
            key,value=line.split(':',1);values[key.strip()]=int(value)
        return start_time,values

    def _sample(self):
        active={}
        for raw_pid in self.cgroup.joinpath('cgroup.procs').read_text().splitlines():
            try:
                pid=int(raw_pid);start,values=self._process(pid)
                active[(pid,start)]={key:values.get(key,0) for key in self.finalized}
            except (OSError,ValueError,IndexError):
                continue
        with self.lock:
            for identity,values in self.last.items():
                if identity not in active:
                    for key in self.finalized:self.finalized[key]+=values[key]
            self.last=active
            self.samples+=1

    def _run(self):
        while not self.stop_event.is_set():
            try:self._sample()
            except OSError:
                with self.lock:self.errors+=1
            self.stop_event.wait(self.interval)
        try:self._sample()
        except OSError:
            with self.lock:self.errors+=1

    def snapshot(self,force=False):
        if force:self._sample()
        with self.lock:
            totals=dict(self.finalized)
            for values in self.last.values():
                for key in totals:totals[key]+=values[key]
            return dict(**totals,processesObserved=len(self.last),samples=self.samples,
                        samplingErrors=self.errors,source='sum of /proc/<pid>/io for cgroup.procs')


def _resource_snapshot(cgroup,io_sampler=None,force_io_sample=False):
    try:
        io_stat=[line.split() for line in (cgroup/'io.stat').read_text().splitlines()]
    except OSError:
        io_stat=None
    out = dict(cgroupPath=str(cgroup), sampledUtc=datetime.now(timezone.utc).isoformat(),
        memoryCurrentBytes=int((cgroup/'memory.current').read_text()),
        memoryPeakBytes=int((cgroup/'memory.peak').read_text()),
        memoryMaxBytes=int((cgroup/'memory.max').read_text()),
        memoryEvents=dict(line.split() for line in (cgroup/'memory.events').read_text().splitlines()),
        cpuStat=dict(line.split() for line in (cgroup/'cpu.stat').read_text().splitlines()),
        ioStat=io_stat,
        processIo=io_sampler.snapshot(force=force_io_sample) if io_sampler is not None else None,
        processPeakRssBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    out['memoryEvents'] = {k:int(v) for k,v in out['memoryEvents'].items()}
    out['cpuStat'] = {k:int(v) for k,v in out['cpuStat'].items()}
    if out['ioStat'] is not None:
        out['ioStat'] = {row[0]:{k:int(v) for k,v in (pair.split('=') for pair in row[1:])}
                         for row in out['ioStat']}
    return out


def _io_delta(before, after):
    if before.get('ioStat') is None or after.get('ioStat') is None:
        keys=('read_bytes','write_bytes','rchar','wchar')
        before_io=before.get('processIo') or {}
        after_io=after.get('processIo') or {}
        return dict(source='sum of /proc/<pid>/io for cgroup.procs',
                    **{key:max(0,after_io.get(key,0)-before_io.get(key,0))
                       for key in keys},
                    samples=after_io.get('samples',0),
                    samplingErrors=after_io.get('samplingErrors',0))
    keys=('rbytes','wbytes','rios','wios')
    totals={key:0 for key in keys}
    for device,current in after.items():
        prior=before.get(device,{})
        for key in keys:
            totals[key]+=max(0,current.get(key,0)-prior.get(key,0))
    return totals


def _guard(cgroup, started,io_sampler=None):
    if time.monotonic() - started > MAX_RUNTIME:
        raise VerificationError('VERIFIER_RUNTIME_LIMIT')
    if shutil.disk_usage('/home/riksora').free < MIN_FREE:
        raise VerificationError('DISK_RESERVE_BELOW_30_GIB')
    sample = _resource_snapshot(cgroup,io_sampler)
    if sample['memoryCurrentBytes'] >= SOFT_RAM_STOP:
        raise VerificationError('MEMORY_SOFT_STOP_900_MIB')
    if sample['memoryEvents'].get('oom_kill', 0) or sample['memoryEvents'].get('oom_group_kill', 0):
        raise VerificationError('OOM_EVENT_OBSERVED')
    return sample


def _verify_manifest_tree(manifest, root):
    """Recheck every manifest path without following links or loading file bodies."""
    root=Path(root).resolve(strict=True)
    entries=manifest.get('entries')
    if not isinstance(entries,list) or len(entries)>100_000:
        raise VerificationError('SNAPSHOT_MANIFEST_ENTRY_COUNT_INVALID')
    expected={};total_bytes=0;allocated_bytes=0
    for entry in entries:
        rel=entry.get('path')
        if not isinstance(rel,str) or rel.startswith('/') or '..' in Path(rel).parts or rel in expected:
            raise VerificationError('SNAPSHOT_MANIFEST_PATH_INVALID')
        expected[rel]=entry
    actual=set()
    for base,dirs,files in os.walk(root,followlinks=False):
        base=Path(base)
        for name in dirs+files:
            path=base/name
            rel=path.relative_to(root).as_posix()
            actual.add(rel)
            if path.is_symlink():
                raise VerificationError('SNAPSHOT_EXTERNAL_OR_INTERNAL_LINK_REFUSED:'+rel)
    if actual!=set(expected):
        raise VerificationError('SNAPSHOT_MANIFEST_PATH_SET_MISMATCH')
    for rel,entry in expected.items():
        path=root/rel
        info=os.lstat(path)
        if entry.get('type')!='directory' and entry.get('type')!='file':
            raise VerificationError('SNAPSHOT_MANIFEST_UNSUPPORTED_ENTRY:'+rel)
        actual_type='directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'other'
        if (actual_type!=entry['type'] or stat.S_IMODE(info.st_mode)!=entry.get('mode') or
                (actual_type=='file' and info.st_size!=entry.get('size'))):
            raise VerificationError('SNAPSHOT_MANIFEST_METADATA_MISMATCH:'+rel)
        if actual_type=='file':
            digest=hashlib.sha256()
            with path.open('rb',buffering=0) as stream:
                for block in iter(lambda:stream.read(4*1024*1024),b''):
                    digest.update(block)
            if digest.hexdigest()!=entry.get('sha256'):
                raise VerificationError('SNAPSHOT_FILE_HASH_MISMATCH:'+rel)
            total_bytes+=info.st_size;allocated_bytes+=info.st_blocks*512
    return dict(entries=len(entries),regularFiles=sum(e['type']=='file' for e in entries),
        logicalBytes=total_bytes,allocatedBytes=allocated_bytes)


def _pg_control_data(pg_controldata, data_dir):
    result=subprocess.run([str(pg_controldata),str(data_dir)],check=True,capture_output=True,
                          text=True,timeout=30)
    parsed={}
    for line in result.stdout.splitlines():
        if ':' in line:
            key,value=line.split(':',1);parsed[key.strip()]=value.strip()
    return parsed


def _verify_snapshot(snapshot_root, manifest_path):
    snapshot_root=Path(snapshot_root).resolve(strict=True)
    manifest_bytes=Path(manifest_path).read_bytes()
    manifest=json.loads(manifest_bytes)
    if (manifest.get('status')!='PASS' or
            manifest.get('artifact')!='RIKSORA-CP6A-10-POSTGRES-SNAPSHOT-MANIFEST-1' or
            Path(manifest.get('snapshotPath','')).resolve()!=snapshot_root):
        raise VerificationError('SNAPSHOT_MANIFEST_INVALID')
    source_stats=_verify_manifest_tree(manifest,manifest['sourcePath'])
    snapshot_stats=_verify_manifest_tree(manifest,snapshot_root)
    if any(source_stats[key]!=snapshot_stats[key] for key in ('entries','regularFiles','logicalBytes')):
        raise VerificationError('SNAPSHOT_SOURCE_AND_COPY_MANIFEST_DIFFER')
    source_root=Path(manifest['sourcePath']).resolve(strict=True)
    source_inodes={(os.stat(source_root/entry['path']).st_dev,os.stat(source_root/entry['path']).st_ino)
                   for entry in manifest['entries'] if entry['type']=='file'}
    for entry in manifest['entries']:
        if entry['type']=='file':
            info=os.stat(snapshot_root/entry['path'])
            if (info.st_dev,info.st_ino) in source_inodes:
                raise VerificationError('SNAPSHOT_NOT_ISOLATED_HARDLINK_DETECTED:'+entry['path'])
    data_dir=snapshot_root/'data'
    if (data_dir/'postmaster.pid').exists() or not (data_dir/'PG_VERSION').is_file():
        raise VerificationError('SNAPSHOT_POSTGRES_ACTIVE_OR_VERSION_MISSING')
    snapshot_major=(data_dir/'PG_VERSION').read_text().strip()
    source_data=Path(manifest['sourcePath'])/'data'
    source_major=(source_data/'PG_VERSION').read_text().strip()
    if snapshot_major!=source_major or not snapshot_major.isdigit():
        raise VerificationError('SNAPSHOT_POSTGRES_MAJOR_VERSION_MISMATCH')
    pg_controldata=f'/usr/lib/postgresql/{snapshot_major}/bin/pg_controldata'
    if not Path(pg_controldata).is_file():
        raise VerificationError('SNAPSHOT_POSTGRES_CONTROLDATA_BINARY_MISSING:'+snapshot_major)
    control=_pg_control_data(pg_controldata,data_dir)
    source_control=_pg_control_data(pg_controldata,source_data)
    if (control.get('Database cluster state')!='shut down' or
            source_control.get('Database cluster state')!='shut down' or
            control.get('Database system identifier')!=source_control.get('Database system identifier') or
            control.get('Catalog version number')!=source_control.get('Catalog version number') or
            control.get('pg_control version number')!=source_control.get('pg_control version number')):
        raise VerificationError('SNAPSHOT_POSTGRES_IDENTITY_OR_SHUTDOWN_STATE_INVALID')
    tablespaces=list((data_dir/'pg_tblspc').iterdir())
    if tablespaces:
        raise VerificationError('SNAPSHOT_EXTERNAL_TABLESPACE_REQUIRES_EXPLICIT_VALIDATION')
    pgdata_allocated=sum(os.lstat(Path(manifest['snapshotPath'])/entry['path']).st_blocks*512
        for entry in manifest['entries'] if entry['type']=='file' and entry['path'].startswith('data/'))
    wal_allocated=sum(os.lstat(Path(manifest['snapshotPath'])/entry['path']).st_blocks*512
        for entry in manifest['entries'] if entry['type']=='file' and entry['path'].startswith('data/pg_wal/'))
    return dict(status='PASS',manifestSha256=hashlib.sha256(manifest_bytes).hexdigest(),
        manifest=manifest,snapshotStats=snapshot_stats,control=control,
        originalClusterControl=source_control,tablespaceEntries=0,
        pgDataAllocatedBytes=pgdata_allocated,walAllocatedBytes=wal_allocated,
        pgControlDataBinary=pg_controldata,pgMajorVersion=snapshot_major)


def _resolve_pg_bin(snapshot_root, pg_bin_dir=None):
    pg_version=(Path(snapshot_root)/'data'/'PG_VERSION').read_text().strip()
    binary_dir=Path(pg_bin_dir) if pg_bin_dir is not None else Path('/usr/lib/postgresql')/pg_version/'bin'
    if not binary_dir.is_dir():
        raise VerificationError('POSTGRES_13_SERVER_NOT_AVAILABLE:'+str(binary_dir))
    binary_dir=binary_dir.resolve(strict=True)
    required=[binary_dir/name for name in ('postgres','pg_ctl','pg_controldata')]
    if not all(path.is_file() and os.access(path,os.X_OK) for path in required):
        raise VerificationError('POSTGRES_13_BINARIES_INCOMPLETE')
    version=subprocess.run([str(required[0]),'--version'],check=True,capture_output=True,
                           text=True,timeout=30).stdout.strip()
    if not version.startswith(f'postgres (PostgreSQL) {pg_version}.'):
        raise VerificationError('POSTGRES_SERVER_MAJOR_VERSION_MISMATCH:'+version)
    return binary_dir


def _copy_runtime_cluster(snapshot_root, output_root, manifest, pg_control_data):
    source=Path(snapshot_root)/'data'
    runtime_root=Path(output_root)/'postgres-working-copy'
    runtime_data=runtime_root/'data'
    if runtime_root.exists():
        raise VerificationError('RUNTIME_POSTGRES_COPY_PATH_ALREADY_EXISTS')
    allocated=sum(os.stat(source/entry['path'][5:]).st_blocks*512
                  for entry in manifest['entries']
                  if entry['type']=='file' and entry['path'].startswith('data/'))
    free=shutil.disk_usage('/home/riksora').free
    if free-allocated-1024**3<MIN_FREE:
        raise VerificationError('DISK_RESERVE_PRECHECK_FOR_RUNTIME_COPY_FAILED')
    runtime_root.mkdir(mode=0o700,parents=True)
    command=['/usr/bin/cp','-a','--sparse=always','--reflink=auto',str(source),str(runtime_data)]
    subprocess.run(command,check=True,capture_output=True,text=True,timeout=3600)
    subset=[]
    for entry in manifest['entries']:
        if entry['path'].startswith('data/') and entry['type'] in ('directory','file'):
            copied=dict(entry);copied['path']=entry['path'][5:]
            subset.append(copied)
    stats=_verify_manifest_tree(dict(entries=subset),runtime_data)
    root_entry=next(entry for entry in manifest['entries'] if entry['path']=='data')
    if stat.S_IMODE(os.stat(runtime_data).st_mode)!=root_entry['mode']:
        raise VerificationError('RUNTIME_POSTGRES_COPY_ROOT_MODE_MISMATCH')
    if (runtime_data/'postmaster.pid').exists():
        raise VerificationError('RUNTIME_POSTGRES_COPY_CONTAINS_ACTIVE_PID')
    control=_pg_control_data(pg_control_data,runtime_data)
    original=_pg_control_data(pg_control_data,source)
    if (control.get('Database system identifier')!=original.get('Database system identifier') or
            control.get('Database cluster state')!='shut down' or
            control.get('pg_control version number')!=original.get('pg_control version number') or
            control.get('Catalog version number')!=original.get('Catalog version number')):
        raise VerificationError('RUNTIME_POSTGRES_COPY_IDENTITY_OR_STATE_MISMATCH')
    if shutil.disk_usage('/home/riksora').free<MIN_FREE:
        raise VerificationError('DISK_RESERVE_BELOW_30_GIB_AFTER_RUNTIME_COPY')
    return runtime_root,runtime_data,dict(copyCommand=command,logicalBytes=stats['logicalBytes'],
        allocatedBytes=stats['allocatedBytes'],sourceSystemIdentifier=original['Database system identifier'],
        runtimeSystemIdentifier=control['Database system identifier'],reusedExistingCopy=False)


def _reuse_runtime_cluster(snapshot_root, runtime_data, manifest, pg_control_data):
    """Reuse an isolated working copy only after a full snapshot manifest recheck."""
    snapshot_data=Path(snapshot_root)/'data'
    runtime_data=Path(runtime_data)
    if runtime_data.is_symlink() or not runtime_data.is_dir():
        raise VerificationError('RUNTIME_POSTGRES_REUSE_PATH_INVALID')
    subset=[]
    for entry in manifest['entries']:
        if entry['path'].startswith('data/') and entry['type'] in ('directory','file'):
            copied=dict(entry);copied['path']=entry['path'][5:]
            subset.append(copied)
    stats=_verify_manifest_tree(dict(entries=subset),runtime_data)
    if (runtime_data/'postmaster.pid').exists():
        raise VerificationError('RUNTIME_POSTGRES_REUSE_HAS_ACTIVE_PID')
    control=_pg_control_data(pg_control_data,runtime_data)
    original=_pg_control_data(pg_control_data,snapshot_data)
    if (control.get('Database system identifier')!=original.get('Database system identifier') or
            control.get('Database cluster state')!='shut down' or
            control.get('pg_control version number')!=original.get('pg_control version number') or
            control.get('Catalog version number')!=original.get('Catalog version number')):
        raise VerificationError('RUNTIME_POSTGRES_REUSE_IDENTITY_OR_STATE_MISMATCH')
    if shutil.disk_usage('/home/riksora').free<MIN_FREE:
        raise VerificationError('DISK_RESERVE_BELOW_30_GIB_BEFORE_RUNTIME_REUSE')
    return runtime_data.parent,runtime_data,dict(copyCommand=None,logicalBytes=stats['logicalBytes'],
        allocatedBytes=stats['allocatedBytes'],sourceSystemIdentifier=original['Database system identifier'],
        runtimeSystemIdentifier=control['Database system identifier'],reusedExistingCopy=True)


def _assert_postgres_cgroup(pid, cgroup):
    relative=str(cgroup.relative_to('/sys/fs/cgroup'))
    rows=Path(f'/proc/{pid}/cgroup').read_text().splitlines()
    actual=next((row.split('::',1)[1].lstrip('/') for row in rows if row.startswith('0::')),None)
    if actual!=relative:
        raise VerificationError('POSTGRES_NOT_IN_VERIFIER_CGROUP')
    return actual


def _hold_single_run_lock(path):
    path=Path(path)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError as error:
        os.close(fd)
        raise VerificationError('ANNUAL_VERIFIER_ALREADY_RUNNING') from error
    return fd


def _assert_no_replay_or_postannual_service():
    units=('riksora-cp6a10-annual-resume-20261101.service',
           'riksora-cp6a10-shared-source-20261101.service',
           'riksora-cp6a10-postannual.service')
    history={}
    properties=('ActiveState','SubState','Result','MemoryPeak','MemoryHigh','MemoryMax','MemorySwapMax','CPUQuotaPerSecUSec')
    for unit in units:
        result=subprocess.run(['systemctl','--user','show',unit,*[f'-p{p}' for p in properties]],
                              capture_output=True,text=True,timeout=15)
        if result.returncode!=0:
            raise VerificationError('SYSTEMD_ACCEPTANCE_STATE_UNREADABLE:'+unit)
        values=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
        history[unit]=values
        if values.get('ActiveState')=='active':
            raise VerificationError('ANNUAL_OR_POSTANNUAL_RUNNER_ACTIVE:'+unit)
    if history[units[0]].get('Result')!='oom-kill' or int(history[units[0]].get('MemoryPeak',0))!=MAX_RAM:
        raise VerificationError('ORIGINAL_ANNUAL_OOM_EVIDENCE_CHANGED_OR_MISSING')
    return history


def _stream(conn, query, params, *, batch=BATCH, name=None):
    cursor = conn.cursor(name=name or ('verify_' + uuid.uuid4().hex))
    cursor.itersize = batch
    cursor.execute(query, params)
    try:
        while True:
            rows = cursor.fetchmany(batch)
            if not rows:
                break
            for row in rows:
                yield row
    finally:
        cursor.close()


def _restore_final_state(conn, store, workspace, session, order_policy, progress_path, target_ns,
                         cgroup, started, worker_result, resume_evidence,io_sampler=None):
    row = conn.execute('SELECT payload,content_hash,revision,dataset_version,profile_hash '
        'FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s', (workspace, session)).fetchone()
    if row is None:
        raise VerificationError('SESSION_ROW_MISSING')
    wire = unpack(row[0], row[1])
    if (wire.get('artifact') != QA3_CHECKPOINT or wire.get('revision') != row[2] or
            row[2] != EXPECTED_FINAL_REVISION or wire.get('chainHash') is None):
        raise VerificationError('SESSION_TIP_IDENTITY_OR_REVISION_MISMATCH')
    base_row = conn.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
        'WHERE workspace_id=%s AND session_id=%s AND revision=0', (workspace, session)).fetchone()
    if base_row is None:
        raise VerificationError('CHECKPOINT_BASE_MISSING')
    base = unpack(base_row[0], base_row[1])
    if (base.get('artifact') != QA3_CHECKPOINT_BASE or base.get('revision') != 0 or
            base.get('stateHash') != base.get('chainHash')):
        raise VerificationError('CHECKPOINT_BASE_INVALID')
    controller_box = {'controller': base.get('controller'), 'count': 0, 'lastChain': base.get('chainHash')}
    def validate_each(state, revision):
        validate_snapshot(state, controller_box['controller'], order_retention_policy=order_policy)
        if revision==548 and (content_hash(state)!=worker_result['resumeStateHash'] or
                state.get('nextGroupIndex')!=resume_evidence['nextGroupIndex'] or
                state.get('throughNs')!=resume_evidence['throughNs']):
            raise VerificationError('RESUMED_CHECKPOINT_STATE_HASH_OR_POSITION_MISMATCH')
    def deltas():
        expected = 1
        query = ('SELECT revision,payload,content_hash FROM btl.tick_checkpoints '
                 'WHERE workspace_id=%s AND session_id=%s AND revision>0 ORDER BY revision')
        for revision, payload, sha in _stream(conn, query, (workspace, session), batch=16,
                                             name='stream_checkpoints_' + uuid.uuid4().hex):
            _guard(cgroup, started,io_sampler)
            checkpoint = unpack(payload, sha)
            if (revision != expected or checkpoint.get('revision') != revision or
                    checkpoint.get('artifact') != QA3_CHECKPOINT_DELTA or
                    checkpoint.get('stateHash') != checkpoint.get('delta',{}).get('body',{}).get('stateHash') or
                    checkpoint.get('chainHash') != checkpoint.get('delta',{}).get('body',{}).get('recordHash')):
                raise VerificationError('CHECKPOINT_ROW_BINDING_OR_SEQUENCE_INVALID')
            if revision==548 and (checkpoint.get('stateHash')!=worker_result['resumeStateHash'] or
                    checkpoint.get('chainHash')!=resume_evidence['checkpointChainHash']):
                raise VerificationError('RESUMED_CHECKPOINT_CHAIN_HASH_MISMATCH')
            controller_box.update(controller=checkpoint.get('controller'), count=revision,
                                  lastChain=checkpoint.get('chainHash'))
            expected += 1
            yield checkpoint['delta']
        if controller_box['count'] != EXPECTED_FINAL_REVISION:
            raise VerificationError('CHECKPOINT_COUNT_OR_TIP_MISMATCH')
    state = reconstruct(base, deltas(), state_callback=validate_each)
    if (state.get('revision') != row[2] or content_hash(state) != wire.get('stateHash') or
            controller_box['lastChain'] != wire.get('chainHash') or
            wire.get('controller') != controller_box['controller'] or
            state.get('datasetVersion') != row[3] or state.get('profileHash') != row[4]):
        raise VerificationError('RECONSTRUCTED_STATE_DOES_NOT_MATCH_SESSION_TIP')
    validate_state(state, order_retention_policy=order_policy)
    validate_snapshot(state, wire['controller'], order_retention_policy=order_policy)
    count = conn.execute('SELECT count(*) FROM btl.tick_checkpoints '
        'WHERE workspace_id=%s AND session_id=%s', (workspace, session)).fetchone()[0]
    if count != EXPECTED_FINAL_REVISION + 1:
        raise VerificationError('CHECKPOINT_ROW_COUNT_MISMATCH')
    progress = json.loads(progress_path.read_text())
    progress_checks={
        'progressStatus':progress.get('status')=='RUNNING',
        'progressTarget':progress.get('targetNs')==target_ns,
        'progressSession':progress.get('sessionId')==session,
        'progressRevision':progress.get('revision')==state['revision'],
        'progressGroupIndex':progress.get('nextGroupIndex')==state['nextGroupIndex'],
        'progressThrough':progress.get('throughNs')==state['throughNs'],
        'requestedSourceStart':state.get('startNs')==EXPECTED_START_NS,
        'annualTarget':state.get('throughNs')==EXPECTED_TARGET_NS,
        'completeGroupCount':state.get('nextGroupIndex')==str(EXPECTED_GROUPS),
    }
    if not all(progress_checks.values()):
        failed=','.join(key for key,value in progress_checks.items() if not value)
        raise VerificationError('PROGRESS_AND_RECONSTRUCTED_STATE_MISMATCH:'+failed)
    return state, wire, base


def _load_resume_evidence(root, session, target_ns):
    worker=json.loads((root/'worker-result.json').read_text())
    resume=json.loads((root/'resume-checkpoint-verification-attempt-3.json').read_text())
    if (worker.get('status')!='PASS' or worker.get('workerProcessRestarted') is not True or
            worker.get('throughNs')!=target_ns or worker.get('resumeRevision')!=548 or
            type(worker.get('resumeStateHash')) is not str or len(worker['resumeStateHash'])!=64):
        raise VerificationError('ANNUAL_WORKER_RESULT_OR_COLD_RESUME_EVIDENCE_INVALID')
    before=resume.get('eventCountsBefore');after=resume.get('eventCountsAfter')
    if (resume.get('status')!='PASS' or resume.get('idempotentOpeningRetry')!='PASS' or
            resume.get('sessionId')!=session or resume.get('revision')!=548 or
            resume.get('nextGroupIndex')!='137708' or resume.get('throughNs')!='1704236400311999999' or
            resume.get('sourceRights')!='UNKNOWN' or resume.get('executionEligibility')!='NOT_GRANTED' or
            resume.get('sourceDatasetId')!='local:hf-community:XAUUSD:2024:53011f22a5887999a2c883a2' or
            resume.get('sourceDatasetVersion')!='87e3c3355dccc3afafef837a56d24046275dcf8ee6d1173a929a10279f14e743' or
            before!=after or before is None or before.get('total')!=557 or
            resume.get('durableReceiptVerification',{}).get('status')!='PASS' or
            resume.get('durableReceiptVerification',{}).get('commands')!=548 or
            resume.get('durableReceiptVerification',{}).get('advanceCommands')!=539):
        raise VerificationError('DURABLE_COLD_RESUME_OR_IDEMPOTENCY_PROOF_INVALID')
    return worker,resume


def _verify_receipts(conn, workspace, session, expected_revision, cgroup, started,io_sampler=None):
    counts = conn.execute('SELECT (SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s),'
        '(SELECT count(*) FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s)',
        (workspace,session,workspace,session)).fetchone()
    if counts != (expected_revision, expected_revision + 1):
        raise VerificationError('COMMAND_OR_CHECKPOINT_COUNT_MISMATCH')
    base = conn.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
        'WHERE workspace_id=%s AND session_id=%s AND revision=0',(workspace,session)).fetchone()
    if base is None or unpack(base[0],base[1]).get('revision') != 0:
        raise VerificationError('GENESIS_CHECKPOINT_INVALID')
    hasher = RecordHasher('BTL-INDEPENDENT-COMMAND-LEDGER-2-STREAM')
    advance_count = 0
    expected = 1
    query = ('SELECT c.revision,c.command_id,c.command_hash,c.payload,c.content_hash,'
             'p.revision,p.payload,p.content_hash FROM btl.tick_commands c '
             'LEFT JOIN btl.tick_checkpoints p ON p.workspace_id=c.workspace_id '
             'AND p.session_id=c.session_id AND p.revision=c.revision '
             'WHERE c.workspace_id=%s AND c.session_id=%s ORDER BY c.revision')
    for rev,cid,command_hash,payload,receipt_hash,cp_rev,cp_payload,cp_hash in _stream(
            conn,query,(workspace,session),batch=8,name='stream_receipts_'+uuid.uuid4().hex):
        _guard(cgroup, started,io_sampler)
        if rev != expected or cp_rev != rev:
            raise VerificationError('RECEIPT_REVISION_OR_CHECKPOINT_JOIN_GAP')
        result = unpack(payload, receipt_hash)
        checkpoint = unpack(cp_payload, cp_hash)
        if result.get('commandId') != cid or result.get('commandHash') != command_hash:
            raise VerificationError('RECEIPT_COMMAND_BINDING_MISMATCH')
        if result.get('artifact') == QA3_RESULT:
            if (result.get('stateRevision') != rev or checkpoint.get('revision') != rev or
                    result.get('stateHash') != checkpoint.get('stateHash') or
                    result.get('chainHash') != checkpoint.get('chainHash') or
                    result.get('durable') is not True):
                raise VerificationError('COMPACT_RECEIPT_CHECKPOINT_BINDING_MISMATCH')
            replay = result.get('replay')
        else:
            if result.get('durable') is not True or result.get('state',{}).get('revision') != rev:
                raise VerificationError('FULL_RECEIPT_INVALID')
            replay = result.get('replay')
        if cid.startswith('advance:'):
            if replay is None:
                raise VerificationError('ADVANCE_RECEIPT_MISSING_REPLAY')
            advance_count += 1
        elif replay is not None:
            raise VerificationError('NONADVANCE_RECEIPT_HAS_REPLAY')
        hasher.add(dict(revision=rev,commandId=cid,commandHash=command_hash,receiptHash=receipt_hash))
        expected += 1
    if expected != expected_revision + 1:
        raise VerificationError('RECEIPT_STREAM_COUNT_MISMATCH')
    return dict(status='PASS',commands=expected_revision,advanceCommands=advance_count,
                checkpointRows=expected_revision+1,
                ledgerHashFormat='BTL-INDEPENDENT-COMMAND-LEDGER-2-STREAM',
                ledgerSha256=hasher.hexdigest())


def _stream_events_and_fills(conn, workspace, session, state, cgroup, started,io_sampler=None):
    genesis = content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-SEED-1',
        sessionId=session,profileHash=state['profileHash'],policy=state['policy'],
        startNs=state['startNs'],initialBalance=state['initialBalance']))
    previous = genesis
    expected_sequence = 0
    transcript = RecordHasher('BTL-OBSERVED-EVENT-TRANSCRIPT-2-STREAM')
    semantic = RecordHasher('BTL-OBSERVED-FINANCIAL-TRANSCRIPT-2-STREAM')
    kinds = Counter()
    fills_by_time = defaultdict(list)
    fill_event_count = 0
    accepted_by_stage = Counter()
    gap_kinds = Counter()
    query = ('SELECT sequence,event_id,payload,content_hash FROM btl.tick_events '
             'WHERE workspace_id=%s AND session_id=%s ORDER BY sequence')
    for seq,event_id,payload,sha in _stream(conn,query,(workspace,session),batch=16,
                                             name='stream_events_'+uuid.uuid4().hex):
        _guard(cgroup, started,io_sampler)
        event = unpack(payload,sha)
        expected_sequence,previous = check_events([event],state,expected_sequence,previous)
        if seq != event['sequence'] or event_id != event['eventId']:
            raise VerificationError('EVENT_ROW_IDENTITY_MISMATCH')
        transcript.add(event_id)
        kind = event['kind']; kinds[kind] += 1
        if kind != 'REPLAY_ADVANCED':
            detail = dict(event['detail']); detail.pop('entryFillRef',None)
            semantic.add(dict(kind=kind,classification=event['classification'],
                              orderId=event['orderId'],detail=detail))
        if event['classification'] == 'SIMULATED_FILL':
            fill_event_count += 1
            if fill_event_count > 2 * 4096:
                raise VerificationError('SIMULATED_FILL_MEMORY_BOUND_EXCEEDED')
            if event['kind'] not in ('ENTRY_FILL','EXIT_FILL'):
                raise VerificationError('UNKNOWN_SIMULATED_FILL_EVENT_KIND')
            fills_by_time[event['detail']['evidence']['timeNs']].append(event)
        if kind == 'ORDER_ACCEPTED':
            offset = int(event['detail']['availableNs']) - int(state['startNs'])
            if offset < 0:
                raise VerificationError('ORDER_DECISION_PRECEDES_SESSION_START')
            accepted_by_stage[offset // (3600*S)] += 1
        if kind == 'DATA_GAP_LIMITATION':
            gap_kinds[event['detail']['gapKind']] += 1
    if expected_sequence != state['nextEventIndex'] or previous != state['eventHash']:
        raise VerificationError('EVENT_CHAIN_HEAD_OR_COUNT_MISMATCH')
    return dict(eventCount=expected_sequence,eventKinds=dict(kinds),
        eventTranscriptSha256=transcript.hexdigest(),semanticFinancialEventSha256=semantic.hexdigest(),
        semanticEventHashFormat='BTL-OBSERVED-FINANCIAL-TRANSCRIPT-2-STREAM',
        fillsByTime=fills_by_time,fillEventCount=fill_event_count,
        acceptedByStage=dict(accepted_by_stage),gapKinds=dict(gap_kinds))


def _orders_from_archive(conn, workspace, session, state):
    store = ObservedExecutionStore('unused',order_retention_policy=QA_ORDER_RETENTION_V4,
                                   qa_state_delta_v3=True,qa_order_archive_v1=True)
    def rows():
        query=('SELECT sequence,order_id,finalized_revision,record_hash,payload,content_hash '
               'FROM public.btl_qa_terminal_order_archive_v1 WHERE workspace_id=%s AND session_id=%s '
               'ORDER BY sequence')
        for seq,oid,rev,record_hash,payload,sha in _stream(conn,query,(workspace,session),batch=16,
                                                           name='stream_archive_'+uuid.uuid4().hex):
            record=unpack(payload,sha)
            if (record.get('sequence')!=seq or record.get('orderId')!=oid or
                    record.get('finalizedRevision')!=rev or record.get('recordHash')!=record_hash):
                raise VerificationError('ARCHIVE_ROW_BINDING_MISMATCH')
            yield record
    verified=verify_archive_complete(rows(),state['orderArchive'],collect=True)
    orders=verified['orders']
    for oid,order in state['orders'].items():
        if oid in orders:
            raise VerificationError('HOT_ARCHIVE_ORDER_ID_COLLISION')
        orders[oid]=deepcopy(order)
    if len(orders) != state['orderArchive']['count'] + len(state['orders']):
        raise VerificationError('ORDER_HISTORY_COUNT_MISMATCH')
    return orders,verified


def _verify_source(source, state, orders_for_source, fills_by_time, progress_path,
                   input_hash, cgroup, started,io_sampler=None):
    provider=source.provider()
    try:
        located=provider.locate_v2(source.dataset_id,source.version,REQUESTED_START_NS)
        position=located.get('position')
        if (position is None or int(located['groupTimeNs'])!=int(state['startNs']) or
                state['startNs']!=EXPECTED_START_NS):
            raise VerificationError('SOURCE_START_POSITION_INVALID')
        progress = _load_source_progress(progress_path,input_hash,state)
        if progress is None:
            progress=_seal_progress(dict(schemaVersion=1,artifact='RIKSORA-ANNUAL-SOURCE-VERIFY-PROGRESS-2',
                inputHash=input_hash,sessionId=state['sessionId'],stateHash=content_hash(state),
                nextPosition=position,groups=0,ticks=0,firstQuoteNs=None,lastQuoteNs=None,
                previousGroupNs=None,matchedFillEventIds=[],sourceGapCounts={},sourceGapChain='0'*64,
                groupChainHash='0'*64,status='RUNNING',pages=0))
        matched=set(progress['matchedFillEventIds'])
        if len(matched)>2*4096:
            raise VerificationError('SOURCE_PROGRESS_FILL_SET_OVERSIZED')
        groups=int(progress['groups']);ticks=int(progress['ticks'])
        first=progress['firstQuoteNs'];last=progress['lastQuoteNs']
        previous_time=int(progress['previousGroupNs']) if progress['previousGroupNs'] is not None else None
        source_gap_counts=Counter(progress['sourceGapCounts'])
        source_gap_chain=progress['sourceGapChain'];chain=progress['groupChainHash']
        position=progress['nextPosition'];pages=int(progress.get('pages',0))
        while position is not None:
            _guard(cgroup,started,io_sampler)
            page=provider.read_page_v2(source.dataset_id,source.version,position,256)
            events=page.get('events',[])
            if not events:
                raise VerificationError('SOURCE_PAGE_EMPTY_WITH_POSITION')
            grouped=[]
            moment=None;rows=[]
            for row in events:
                t=int(row['timeNs'])
                if t > int(state['throughNs']):
                    raise VerificationError('SOURCE_HAS_GROUP_AFTER_SESSION_TIP')
                if moment is None:
                    moment=t
                elif moment != t:
                    grouped.append((moment,rows));moment=t;rows=[]
                rows.append(row)
            if rows:
                grouped.append((moment,rows))
            for moment,group_rows in grouped:
                if previous_time is not None and moment <= previous_time:
                    raise VerificationError('SOURCE_CHRONOLOGY_OR_ATOMIC_GROUP_SPLIT')
                row=group_rows[0];event_ids=[r['eventId'] for r in group_rows]
                gid=content_hash(dict(schemaVersion=1,artifact='BTL-TICK-GROUP-ID-1',
                                      datasetVersion=source.version,timeNs=str(moment),eventIds=event_ids))
                group_record=dict(timeNs=str(moment),groupId=gid,eventIds=event_ids,
                                  bid=row['bid'],ask=row['ask'])
                chain=hashlib.sha256(bytes.fromhex(chain)+_canonical_record_wire(group_record)).hexdigest()
                if first is None:first=str(moment)
                if previous_time is not None and moment-previous_time>60*S:
                    closed=all(item['quality']['gapBefore']=='KNOWN_SESSION_CLOSED'
                               for item in group_rows)
                    gap=dict(startNs=str(previous_time),endNs=str(moment),
                        elapsedNs=str(moment-previous_time),
                        kind='MARKET_CLOSED' if closed else 'UNKNOWN_COVERAGE_GAP',
                        quoteAvailable=True,sourceQuality='UNKNOWN')
                    source_gap_chain=hashlib.sha256(bytes.fromhex(source_gap_chain)+_canonical_record_wire(gap)).hexdigest()
                    source_gap_counts[gap['kind']]+=1
                for fill in fills_by_time.get(str(moment),[]):
                    evidence=fill['detail']['evidence']
                    order=orders_for_source[fill['orderId']]
                    if len({(item['bid'],item['ask']) for item in group_rows})!=1:
                        raise VerificationError('SIMULATED_FILL_FROM_AMBIGUOUS_TIMESTAMP_GROUP')
                    if (evidence['groupId']!=gid or evidence['eventIds']!=event_ids or
                            evidence['bid']!=row['bid'] or evidence['ask']!=row['ask']):
                        raise VerificationError('FILL_SOURCE_EVIDENCE_MISMATCH')
                    expected=row['ask'] if fill['kind']=='ENTRY_FILL' and order['side']=='LONG' else \
                             row['bid'] if fill['kind']=='ENTRY_FILL' else \
                             row['bid'] if order['side']=='LONG' else row['ask']
                    if fill['detail']['price']!=expected:
                        raise VerificationError('FILL_PRICE_SOURCE_MISMATCH')
                    matched.add(fill['eventId'])
                previous_time=moment;last=str(moment);groups+=1;ticks+=len(group_rows)
            pages+=1
            position=page.get('nextPosition')
            if pages%64==0 or position is None:
                progress=_seal_progress(dict(schemaVersion=1,artifact='RIKSORA-ANNUAL-SOURCE-VERIFY-PROGRESS-2',
                    inputHash=input_hash,sessionId=state['sessionId'],
                    stateHash=content_hash(state),nextPosition=position,groups=groups,ticks=ticks,
                    firstQuoteNs=first,lastQuoteNs=last,
                    previousGroupNs=str(previous_time) if previous_time is not None else None,
                    matchedFillEventIds=sorted(matched),sourceGapCounts=dict(source_gap_counts),
                    sourceGapChain=source_gap_chain,
                    groupChainHash=chain,status='RUNNING',pages=pages))
                _atomic_json(progress_path,progress)
        if groups!=EXPECTED_GROUPS or groups!=int(state['nextGroupIndex']):
            raise VerificationError('FULL_SOURCE_GROUP_COUNT_MISMATCH')
        expected_fills={event['eventId'] for rows in fills_by_time.values() for event in rows}
        if matched!=expected_fills:
            raise VerificationError('SOURCE_FILL_MATCH_SET_MISMATCH')
        boundary_gaps=_coverage_boundary_gaps(first,last,state['throughNs'])
        final=dict(status='PASS',independentSourceTicks=ticks,independentTimestampGroups=groups,
            independentlyMatchedFills=len(matched),firstSourceQuoteNs=first,lastSourceQuoteNs=last,
            sourceGapCounts=dict(source_gap_counts),sourceGapChainSha256=source_gap_chain,
            coverageBoundaryGaps=boundary_gaps,
            coverageBoundaryGapSha256=content_hash(dict(schemaVersion=1,
                artifact='RIKSORA-ANNUAL-COVERAGE-BOUNDARIES-1',gaps=boundary_gaps)),
            reportedCoverageGapCount=sum(source_gap_counts.values())+len(boundary_gaps),
            unknownCoverageGapCount=source_gap_counts.get('UNKNOWN_COVERAGE_GAP',0)+
                sum(gap['kind']=='UNKNOWN_COVERAGE_GAP' for gap in boundary_gaps),
            sourceGroupRollingSha256=chain)
        progress['status']='PASS';progress['result']=final;_seal_progress(progress)
        _atomic_json(progress_path,progress)
        return final
    finally:
        provider.close()


def _load_source_progress(path,input_hash,state):
    path=Path(path)
    if not path.exists():
        return None
    try:
        value=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError) as error:
        raise VerificationError('SOURCE_PROGRESS_UNREADABLE') from error
    if (value.get('schemaVersion')!=1 or
            value.get('artifact')!='RIKSORA-ANNUAL-SOURCE-VERIFY-PROGRESS-2' or
            value.get('inputHash')!=input_hash or value.get('sessionId')!=state['sessionId'] or
            value.get('stateHash')!=content_hash(state) or value.get('status') not in ('RUNNING','PASS') or
            type(value.get('groups')) is not int or value['groups']<0 or value['groups']>EXPECTED_GROUPS):
        raise VerificationError('SOURCE_PROGRESS_IDENTITY_OR_RANGE_INVALID')
    expected_hash=content_hash(dict(schemaVersion=1,artifact='RIKSORA-ANNUAL-SOURCE-VERIFY-PROGRESS-2',
        body={k:v for k,v in value.items() if k!='recordHash'}))
    if value.get('recordHash')!=expected_hash:
        raise VerificationError('SOURCE_PROGRESS_HASH_MISMATCH')
    matched=value.get('matchedFillEventIds');gap_counts=value.get('sourceGapCounts')
    if (not isinstance(matched,list) or len(matched)>8192 or len(set(matched))!=len(matched) or
            not isinstance(gap_counts,dict) or
            any(key not in ('MARKET_CLOSED','UNKNOWN_COVERAGE_GAP') or type(count) is not int or count<0
                for key,count in gap_counts.items()) or
            not isinstance(value.get('sourceGapChain'),str) or len(value['sourceGapChain'])!=64 or
            not isinstance(value.get('groupChainHash'),str) or len(value['groupChainHash'])!=64):
        raise VerificationError('SOURCE_PROGRESS_BOUND_OR_HASH_STATE_INVALID')
    if value.get('status')=='PASS':
        if value.get('groups')!=EXPECTED_GROUPS:
            raise VerificationError('SOURCE_PROGRESS_PASS_COUNT_INVALID')
        return value
    return value


def _check_replay_config(root, state, source):
    config=json.loads((root/'replay-config.json').read_text())
    schedule=config.get('annualSchedule',{})
    slots=schedule.get('utcSlots')
    additional=config.get('additionalDayOrderStages',[])
    if (config.get('artifact')!='BTL-QA-REPLAY-CONFIG-1' or
            config.get('continuousDays')!=366 or config.get('timelineStorageMode')!='shared-source-v1' or
            config.get('sourceProcessing')!='ALL_OBSERVED_GROUPS' or
            config.get('maximumScheduledOrderAcceptances')!=1469 or
            config.get('maxCumulativeOrders')!=4096 or
            config.get('productionEnabled') is not False or
            schedule.get('version')!='cp6a10-annual-v1' or
            schedule.get('maximumAcceptances')!=1469 or schedule.get('annualLimit')!=4096 or
            schedule.get('firstDayMaximumAcceptances')!=9 or
            schedule.get('subsequentDayMaximumAcceptances')!=4 or
            slots!=[0,6,12,18] or config.get('firstDayOrderStages')!=slots or
            len(additional)!=365 or
            additional!=[[day*24+hour for hour in slots] for day in range(1,366)] or
            config.get('ordersPerHourlyDecision')!=1 or
            config.get('additionalDayOrdersPerDecision')!=1 or
            state.get('datasetId')!=source.dataset_id or state.get('datasetVersion')!=source.version):
        raise VerificationError('PINNED_ANNUAL_REPLAY_CONFIG_MISMATCH')
    if annual_order_acceptance_upper_bound(366)!=1469:
        raise VerificationError('ANNUAL_ORDER_BOUND_IMPLEMENTATION_MISMATCH')
    maximum_by_stage={stage:(6 if stage==0 else 1) for stage in slots}
    for day in additional:
        maximum_by_stage.update({stage:1 for stage in day})
    if sum(maximum_by_stage.values())!=1469 or len(maximum_by_stage)!=1464:
        raise VerificationError('PINNED_ANNUAL_ORDER_SCHEDULE_BOUND_MISMATCH')
    return config,maximum_by_stage


def _check_source_pin(timeline_path,source):
    import sqlite3
    p=Path(timeline_path)
    if p.is_symlink() or not p.is_file():
        raise VerificationError('TIMELINE_SQLITE_PATH_INVALID')
    before=p.stat()
    conn=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        conn.execute('PRAGMA query_only=ON')
        result=conn.execute('PRAGMA quick_check').fetchone()[0]
        if result!='ok':
            raise VerificationError('TIMELINE_SQLITE_QUICK_CHECK_FAILED:'+str(result))
        body=json.loads(conn.execute('SELECT body FROM heads WHERE id=1').fetchone()[0])
    finally:
        conn.close()
    if (body.get('artifact')!='BTL-TICK-SHARED-SOURCE-CHECKPOINT-1' or
            body.get('sourcePin')!=source.source_pin):
        raise VerificationError('TIMELINE_SOURCE_PIN_MISMATCH')
    after=p.stat()
    if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(
            after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns):
        raise VerificationError('TIMELINE_SQLITE_CHANGED_DURING_READ_ONLY_VERIFICATION')
    return dict(status='PASS',quickCheck=result,sourcePin=body['sourcePin'],
                cursor=body.get('cursor'),path=str(p),sha256=_sha256_file(p),
                logicalBytes=after.st_size,allocatedBytes=after.st_blocks*512)


def _start_postgres(pg_bin_dir, runtime_root, port):
    root=Path(runtime_root).resolve(strict=True)
    data=root/'data';log=root/'server.log'
    if (data/'postmaster.pid').exists():
        raise VerificationError('SNAPSHOT_POSTGRES_ACTIVE_OR_PASSWORD_MISSING')
    socket=Path(tempfile.mkdtemp(prefix='rv',dir='/run/user/1000'))
    os.chmod(socket,0o700)
    pg_ctl=str(Path(pg_bin_dir)/'pg_ctl')
    status=subprocess.run([pg_ctl,'-D',str(data),'status'],capture_output=True,text=True,timeout=30)
    if status.returncode==0:
        raise VerificationError('SNAPSHOT_POSTGRES_ALREADY_ACTIVE')
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','BTL_'))}
    env['PYTHONDONTWRITEBYTECODE']='1'
    command=[pg_ctl,'-D',str(data),'-l',str(log),'-o',
        f"-c listen_addresses='' -k {socket} -p {port} -c shared_buffers=32MB "
        '-c max_connections=16 -c default_transaction_read_only=on','-w','start']
    try:
        subprocess.run(command,env=env,check=True,capture_output=True,text=True,timeout=120)
    except BaseException:
        if socket.is_dir() and socket.parent==Path('/run/user/1000'):
            shutil.rmtree(socket)
        raise
    pid=int((data/'postmaster.pid').read_text().splitlines()[0])
    return dict(root=root,data=data,socket=socket,log=log,pgCtl=pg_ctl,port=port,env=env,pid=pid)


def _stop_postgres(pg):
    if pg is None:return
    try:
        subprocess.run([pg['pgCtl'],'-D',str(pg['data']),'-m','fast','-w','stop'],
                       env=pg['env'],check=True,capture_output=True,text=True,timeout=120)
    finally:
        if pg['socket'].is_dir() and pg['socket'].parent==Path('/run/user/1000'):
            shutil.rmtree(pg['socket'])


def run(args):
    output=Path(args.output_root).resolve()
    lock_fd=_hold_single_run_lock(output.parent/'annual-streaming-verifier.lock')
    io_sampler=None
    try:
        cgroup=_cgroup()
        io_sampler=ProcessIoSampler(cgroup)
        io_sampler.start()
        return _run_locked(args,lock_fd,cgroup,io_sampler)
    finally:
        if io_sampler is not None:io_sampler.stop()
        os.close(lock_fd)


def _run_locked(args, lock_fd,cgroup,io_sampler):
    started=time.monotonic()
    root=Path(args.annual_root).resolve(strict=True)
    requested_snapshot=Path(args.pg_snapshot)
    requested_output=Path(args.output_root)
    if requested_snapshot.is_symlink() or requested_output.is_symlink():
        raise VerificationError('SNAPSHOT_OR_OUTPUT_PATH_IS_SYMLINK')
    pg_snapshot=Path(args.pg_snapshot).resolve(strict=True)
    output=requested_output.resolve()
    output.mkdir(mode=0o700,parents=True,exist_ok=True)
    if output.is_symlink() or output.stat().st_mode & 0o077:
        raise VerificationError('OUTPUT_DIRECTORY_MODE_INVALID')
    if any((output/name).exists() for name in ('verification-report.json','source-progress.json')):
        raise VerificationError('OUTPUT_PATH_ALREADY_CONTAINS_VERIFICATION_EVIDENCE')
    initial=_guard(cgroup,started,io_sampler)
    prior_services=_assert_no_replay_or_postannual_service()
    if args.session_id!=EXPECTED_SESSION:
        raise VerificationError('UNEXPECTED_SESSION_ID')
    if args.target_ns!=EXPECTED_TARGET_NS:
        raise VerificationError('ANNUAL_TARGET_NS_MISMATCH')
    pg=None;source=None;result=None
    preflight_path=root.parent/'annual-resource-preflight.json'
    preflight,preflight_sha=_validate_annual_preflight(preflight_path)
    snapshot_info=_verify_snapshot(pg_snapshot,args.snapshot_manifest)
    pg_bin_dir=_resolve_pg_bin(pg_snapshot,args.pg_bin_dir)
    if args.runtime_data_dir is None:
        runtime_root,runtime_data,runtime_copy=_copy_runtime_cluster(
            pg_snapshot,output,snapshot_info['manifest'],snapshot_info['pgControlDataBinary'])
    else:
        runtime_root,runtime_data,runtime_copy=_reuse_runtime_cluster(
            pg_snapshot,args.runtime_data_dir,snapshot_info['manifest'],snapshot_info['pgControlDataBinary'])
    worker_result,resume_evidence=_load_resume_evidence(root,args.session_id,args.target_ns)
    immutable_inputs={
        'annualResourcePreflight':preflight_path,
        'annualProgress':root/'progress.json',
        'workerResult':root/'worker-result.json',
        'resumeCheckpointProof':root/'resume-checkpoint-verification-attempt-3.json',
        'annualReplayConfig':root/'replay-config.json',
        'snapshotManifest':args.snapshot_manifest,
        'oomInterruptionReport':root.parent/'annual-resume-attempt-3'/'oom-interruption-report.json',
    }
    immutable_hashes={key:_sha256_file(path) for key,path in immutable_inputs.items()}
    try:
        pg=_start_postgres(pg_bin_dir,runtime_root,args.port)
        pg_cgroup=_assert_postgres_cgroup(pg['pid'],cgroup)
        password=(pg_snapshot/'password').read_text().strip()
        dsn=make_conninfo(host=str(pg['socket']),port=args.port,dbname='postgres',
                          user='qa_root',password=password)
        os.environ['BTL_ENABLE_QA_ORDER_ARCHIVE_V1']='1'
        store=ObservedExecutionStore(dsn,order_retention_policy=QA_ORDER_RETENTION_V4,
                                     qa_state_delta_v3=True,qa_order_archive_v1=True)
        with psycopg.connect(dsn) as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            state,session_wire,base=_restore_final_state(conn,store,EXPECTED_WORKSPACE,
                args.session_id,QA_ORDER_RETENTION_V4,root/'progress.json',args.target_ns,cgroup,started,
                worker_result,resume_evidence,io_sampler)
            if state.get('artifact')!=STATE_QA_ARCHIVE_V1:
                raise VerificationError('SESSION_ORDER_ARCHIVE_FORMAT_MISMATCH')
            _enable_qa_shared_source_mode(root)
            source=AdmittedObservedSource(SOURCE,ObservedExecutionProfile.from_wire(state['profile']),
                receipt_path=PROOF,receipt_sha256=state['profile']['technicalEligibility']['qualificationReceiptHash'],
                log_root=output/'source-logs',timeline_storage_mode='shared-source-v1')
            source_stat=(SOURCE/'archive.sqlite').stat()
            pinned=preflight['sourceFingerprint']
            if (source.source_archive_sha256!=preflight.get('sourceSha256') or
                    source.qualification_hash!=preflight.get('qualificationSha256') or
                    preflight.get('qualificationPath')!=str(PROOF) or
                    (source_stat.st_dev,source_stat.st_ino,source_stat.st_size,source_stat.st_mtime_ns)!=
                    (pinned.get('device'),pinned.get('inode'),pinned.get('sizeBytes'),pinned.get('modifiedNs'))):
                raise VerificationError('ANNUAL_PREFLIGHT_SOURCE_IDENTITY_OR_FINGERPRINT_MISMATCH')
            config,allowed_stages=_check_replay_config(root,state,source)
            timeline=_check_source_pin(args.timeline_path,source)
            timeline_binding=_verify_timeline_session_binding(state,timeline['cursor'],args.target_ns)
            if (source.profile.wire['sourceQuality']['rights']!='UNKNOWN' or
                    source.execution_eligibility!='NOT_GRANTED' or
                    source.profile.wire['executionLabel']!='EXPERIMENTAL — UNVERIFIED SOURCE — SIMULATED EXECUTION'):
                raise VerificationError('SOURCE_RIGHTS_OR_EXECUTION_ELIGIBILITY_PROMOTION')
            store._verify_order_archive(conn,EXPECTED_WORKSPACE,args.session_id,state,full=True)
            orders,archive= _orders_from_archive(conn,EXPECTED_WORKSPACE,args.session_id,state)
            if len(orders)>4096 or len(state['orders'])>128:
                raise VerificationError('CUMULATIVE_OR_ACTIVE_ORDER_LIMIT_EXCEEDED')
            event_result=_stream_events_and_fills(conn,EXPECTED_WORKSPACE,args.session_id,state,cgroup,started,io_sampler)
            if len(event_result['fillsByTime'])>8192:
                raise VerificationError('FILL_MAP_LIMIT_EXCEEDED')
            for stage,count in event_result['acceptedByStage'].items():
                if stage not in allowed_stages or count>allowed_stages.get(stage,0):
                    raise VerificationError('ORDER_ACCEPTANCE_OUTSIDE_PINNED_SCHEDULE')
            accepted_count=sum(event_result['acceptedByStage'].values())
            if accepted_count>1469 or accepted_count!=len(orders):
                raise VerificationError('ANNUAL_ORDER_SCHEDULE_COUNT_MISMATCH')
            receipt_result=_verify_receipts(conn,EXPECTED_WORKSPACE,args.session_id,
                state['revision'],cgroup,started,io_sampler)
            source_result=_verify_source(source,state,orders,event_result['fillsByTime'],
                output/'source-progress.json',_source_verification_input_hash(
                    snapshot_info['manifestSha256'],session_wire['stateHash'],source.version),
                cgroup,started,io_sampler)
            if source_result['independentSourceTicks']!=preflight['qualificationRows']:
                raise VerificationError('INDEPENDENT_SOURCE_ROW_COUNT_DIFFERS_FROM_QUALIFICATION')
            order_type_counts=Counter(o['orderType'] for o in orders.values())
            order_status_counts=Counter(o['status'] for o in orders.values())
            closed_count=sum(o['status']=='CLOSED' for o in orders.values())
            if event_result['fillEventCount']!=source_result['independentlyMatchedFills']:
                raise VerificationError('INDEPENDENT_FILL_COUNT_MISMATCH')
            if not event_result['eventKinds'].get('ENTRY_FILL') or not event_result['eventKinds'].get('EXIT_FILL'):
                raise VerificationError('REQUIRED_SIMULATED_FILL_EVENTS_MISSING')
            if not event_result['eventKinds'].get('DATA_GAP_LIMITATION'):
                raise VerificationError('DATA_GAP_LIMITATION_EVIDENCE_MISSING')
            financial_hash_format,financial_hash=_financial_state_digest(state,orders)
            source.assert_current()
            result=dict(
                schemaVersion=1,artifact='RIKSORA-CP6A-10-ANNUAL-STREAMING-VERIFICATION-1',
                status='PASS',verifiedUtc=datetime.now(timezone.utc).isoformat(),
                classification=state['profile']['executionLabel'],
                sessionId=args.session_id,revision=state['revision'],stateHash=session_wire['stateHash'],
                source=dict(status='PASS',datasetId=source.dataset_id,datasetVersion=source.version,
                    archiveSha256=source.source_archive_sha256,qualificationReceiptSha256=source.qualification_hash,
                    sharedSourceBinding=source.source_pin,timeline=timeline,sessionTimelineBinding=timeline_binding),
                schedule=dict(status='PASS',acceptedOrders=accepted_count,maximumScheduledAcceptances=1469,
                    cumulativeOrderLimit=4096,activeOrderLimit=128,ordersByDecisionStage=event_result['acceptedByStage'],
                    sourceProcessing=config['sourceProcessing']),
                coverage=source_result,
                checkpoint=dict(status='PASS',revision=state['revision'],nextGroupIndex=state['nextGroupIndex'],
                    timestampGroups=EXPECTED_GROUPS,checkpointRows=state['revision']+1,
                    checkpointChainHash=session_wire['chainHash'],stateHash=session_wire['stateHash']),
                receipts=receipt_result,
                events=dict(status='PASS',count=event_result['eventCount'],kinds=event_result['eventKinds'],
                    eventHash=state['eventHash'],eventTranscriptSha256=event_result['eventTranscriptSha256'],
                    semanticFinancialEventSha256=event_result['semanticFinancialEventSha256']),
                financial=dict(status='PASS',balance=state['balance'],initialBalance=state['initialBalance'],
                    realizedGross=state['realizedGross'],commission=state['commission'],
                    stateHashFormat=financial_hash_format,stateHash=financial_hash,
                    entryFills=event_result['eventKinds'].get('ENTRY_FILL',0),
                    exitFills=event_result['eventKinds'].get('EXIT_FILL',0),
                    completedTrades=closed_count,tradeLifecycleAndCash='PASS',
                    tradeAuditSourceMatch='PASS'),
                orderHistory=dict(status='PASS',count=len(orders),archived=archive['count'],
                    hot=len(state['orders']),types=dict(order_type_counts),statuses=dict(order_status_counts),
                    noHistoricalOrderPruning=True),
                coldResume=dict(status='PASS',processRestarted=True,resumedFromRevision=548,
                    resumedStateHash=worker_result['resumeStateHash'],finalRevision=state['revision']),
                idempotency=resume_evidence,
                sourceRights='UNKNOWN',executionEligibility='NOT_GRANTED',
                workerOutputConsistency=dict(status='PASS',workerResultStatus=worker_result['status'],
                    workerCompletedThroughNs=worker_result['throughNs'],
                    durableProgressRevision=json.loads((root/'progress.json').read_text())['revision'],
                    durableProgressNextGroupIndex=json.loads((root/'progress.json').read_text())['nextGroupIndex']),
                inputManifest={key:dict(path=str(path),sha256=immutable_hashes[key],sizeBytes=path.stat().st_size)
                    for key,path in immutable_inputs.items()},
                priorAnnualService=dict(unit='riksora-cp6a10-annual-resume-20261101.service',
                    result=prior_services['riksora-cp6a10-annual-resume-20261101.service'].get('Result'),
                    memoryPeakBytes=int(prior_services['riksora-cp6a10-annual-resume-20261101.service'].get('MemoryPeak',0)),
                    memoryMaxBytes=int(prior_services['riksora-cp6a10-annual-resume-20261101.service'].get('MemoryMax',0)),
                    runnerRestarted=False),
                measured=dict(startedUtc=datetime.fromtimestamp(time.time()-(time.monotonic()-started),timezone.utc).isoformat(),
                    elapsedSeconds=round(time.monotonic()-started,3),initialResource=initial,
                    postgresCgroupPath=pg_cgroup,postgresPid=pg['pid'],
                    runtimePostgresCopy=runtime_copy,diskFreeBytes=shutil.disk_usage('/home/riksora').free,
                pgClusterSnapshotBytes=snapshot_info['pgDataAllocatedBytes'],
                pgWalBytes=snapshot_info['walAllocatedBytes']),
                snapshot=dict(status=snapshot_info['status'],manifestSha256=snapshot_info['manifestSha256'],
                    clusterSystemIdentifier=snapshot_info['control']['Database system identifier'],
                    postgresMajorVersion=snapshot_info['pgMajorVersion'],
                    pgControlVersion=snapshot_info['control']['pg_control version number'],
                    originalClusterState=snapshot_info['originalClusterControl']['Database cluster state'],
                    tablespaceEntries=snapshot_info['tablespaceEntries']),
                limits=dict(cpuMax='1 CPU',memoryHighBytes=MEMORY_HIGH,memoryMaxBytes=MAX_RAM,softStopBytes=SOFT_RAM_STOP,
                    swapMaxBytes=0,minimumFreeDiskBytes=MIN_FREE),
                noReplayCommandsIssued=True,originalPostgresClusterModified=False,
                sourceChanged=False,productionChanged=False)
            result['inputManifest']['timelineSqlite']=dict(path=timeline['path'],sha256=timeline['sha256'],
                sizeBytes=timeline['logicalBytes'])
            result['inputManifest']['sourceArchive']=dict(path=str(SOURCE/'archive.sqlite'),
                sha256=source.source_archive_sha256,sizeBytes=(SOURCE/'archive.sqlite').stat().st_size)
            result['inputManifest']['qualificationReceipt']=dict(path=str(PROOF),
                sha256=source.qualification_hash,sizeBytes=PROOF.stat().st_size)
            idempotency=result['idempotency']
            if (idempotency.get('status')!='PASS' or idempotency.get('idempotentOpeningRetry')!='PASS' or
                    idempotency.get('sessionId')!=args.session_id or
                    result['coldResume']['status']!='PASS' or source_result['status']!='PASS'):
                raise VerificationError('PRIOR_COLD_RESUME_OR_IDEMPOTENCY_EVIDENCE_INVALID')
            result['runtimePostgresCgroupBounded']=True
        return result
    finally:
        if source is not None:
            source.close()
        if pg is not None:
            if result is not None and 'measured' in result:
                try:
                    proc=Path(f"/proc/{pg['pid']}/status")
                    if proc.exists():
                        result['measured']['postgresPeakRssBytes']=int(next(
                            line.split()[1] for line in proc.read_text().splitlines()
                            if line.startswith('VmHWM:')))*1024
                except Exception:
                    result['measured']['postgresPeakRssBytes']=None
            _stop_postgres(pg)
        if result is not None:
            original_after=_verify_manifest_tree(snapshot_info['manifest'],snapshot_info['manifest']['sourcePath'])
            snapshot_after=_verify_manifest_tree(snapshot_info['manifest'],pg_snapshot)
            if (any(original_after[key]!=snapshot_info['snapshotStats'][key]
                    for key in ('entries','regularFiles','logicalBytes')) or
                    any(snapshot_after[key]!=snapshot_info['snapshotStats'][key]
                    for key in ('entries','regularFiles','logicalBytes'))):
                raise VerificationError('ORIGINAL_OR_SNAPSHOT_CHANGED_DURING_VERIFICATION')
            if any(_sha256_file(path)!=immutable_hashes[key] for key,path in immutable_inputs.items()):
                raise VerificationError('ACCEPTANCE_INPUT_EVIDENCE_CHANGED_DURING_VERIFICATION')
            if _sha256_file(args.timeline_path)!=result['inputManifest']['timelineSqlite']['sha256']:
                raise VerificationError('TIMELINE_SQLITE_HASH_CHANGED_DURING_VERIFICATION')
            final_resource=_resource_snapshot(cgroup,io_sampler,force_io_sample=True)
            cpu_delta=max(0,final_resource['cpuStat'].get('usage_usec',0)-
                          initial['cpuStat'].get('usage_usec',0))
            result['measured'].update(resourceFinal=final_resource,
                cpuCgroupUsec=cpu_delta,cpuCgroupSeconds=cpu_delta/1_000_000,
                snapshotAndOriginalAfterRun='BYTE_IDENTICAL_TO_MANIFEST',
                elapsedSeconds=round(time.monotonic()-started,3),
                diskFreeBytes=shutil.disk_usage('/home/riksora').free,
                diskIoDelta=_io_delta(initial,final_resource),
                verifierEvidenceBytes=sum(p.stat().st_size for p in output.rglob('*')
                    if p.is_file() and not p.is_relative_to(runtime_root)))
            if result['measured']['diskFreeBytes']<MIN_FREE:
                raise VerificationError('DISK_RESERVE_BELOW_30_GIB_AT_FINALIZATION')
            if final_resource['memoryPeakBytes']>=SOFT_RAM_STOP:
                raise VerificationError('MEMORY_EARLY_STOP_THRESHOLD_CROSSED')
            if (final_resource['memoryEvents'].get('oom_kill',0)>0 or
                    final_resource['memoryEvents'].get('oom_group_kill',0)>0):
                raise VerificationError('OOM_EVENT_OBSERVED_DURING_VERIFICATION')
            _atomic_json(output/'verification-report.json',result)
            _atomic_json(output/'verification-status.json',dict(status='PASS',stage='complete',
                report=str(output/'verification-report.json'),verifiedUtc=result['verifiedUtc']))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--annual-root',type=Path,required=True)
    parser.add_argument('--pg-snapshot',type=Path,required=True)
    parser.add_argument('--snapshot-manifest',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--timeline-path',type=Path,required=True)
    parser.add_argument('--session-id',required=True)
    parser.add_argument('--target-ns',required=True)
    parser.add_argument('--port',type=int,default=55441)
    parser.add_argument('--pg-bin-dir',type=Path)
    parser.add_argument('--runtime-data-dir',type=Path,
        help='reuse an existing isolated PGDATA only after a full snapshot manifest recheck')
    args=parser.parse_args()
    try:
        result=run(args)
        print(json.dumps({'status':result['status'],'groups':result['coverage']['independentTimestampGroups'],
            'revision':result['revision'],'report':str(Path(args.output_root)/'verification-report.json')},sort_keys=True))
        return 0
    except BaseException as error:
        traceback.print_exc()
        output=Path(args.output_root)
        try:
            _atomic_json(output/'verification-status.json',dict(status='FAILED_SAFELY',
                stage='verification',errorCode=type(error).__name__+':'+str(error),
                checkedUtc=datetime.now(timezone.utc).isoformat(),
                checkpointPath=str(Path(args.annual_root)/'progress.json')))
        except Exception:
            pass
        return 2


if __name__=='__main__':
    raise SystemExit(main())
