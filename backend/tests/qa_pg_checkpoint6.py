"""Explicit-run isolated financial persistence experiment. No application entry point."""
import hashlib,json,multiprocessing,os,resource,shutil,signal,statistics,subprocess,time
from contextlib import contextmanager,nullcontext
from copy import deepcopy
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from application.models import TrustedScope
from contracts.canonical import canonical_bytes,content_hash
from contracts.models import MethodPolicy
from execution.observed_kernel import apply
from execution.observed_postgres import ObservedExecutionStore
import execution.observed_postgres as storage
from infrastructure.database import migrate
from ticks.storage_v2 import DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline
from tests.qa_pg_codec6 import Codec,install_schema
from tests.qa_pg_verify6 import fetch,audit,decode
from tests.qa_pg_measure6 import measure

ROOT=Path('/home/riksora/riksora-qa-evidence/session-storage-20261030/checkpoint6')
E=Path('/home/riksora/riksora-qa-evidence');SOURCE=Path('/tmp/riksora-exclusive-qa-8l28d6oy/data')
BIN=Path('/usr/lib/postgresql/16/bin');START=time.monotonic();BUDGET=512*1024**2;RESERVE=30*1024**3
SCOPE=TrustedScope('qa6:finance','qa6:actor');SID='session:qa';SIZES=(0,16,64,256)
os.umask(0o077)


def allocated(path):
    total=0
    for p in path.rglob('*'):
        try:
            if p.is_file():total+=p.stat().st_blocks*512
        except FileNotFoundError:pass
    return total
def guard():
    if allocated(ROOT)>BUDGET:raise RuntimeError('ARTIFACT_BUDGET')
    if shutil.disk_usage(ROOT).free<RESERVE:raise RuntimeError('DISK_RESERVE')
    if time.monotonic()-START>850:raise RuntimeError('TIME_BUDGET')
def save(name,value):
    p=ROOT/name;p.parent.mkdir(mode=0o700,exist_ok=True,parents=True);tmp=p.with_name(p.name+'.pending')
    with tmp.open('wb') as f:f.write(json.dumps(value,sort_keys=True,indent=2).encode());f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
def cg():
    line=next(x for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'));p=Path('/sys/fs/cgroup')/line.split('::')[1].lstrip('/')
    cpu=dict(x.split() for x in (p/'cpu.stat').read_text().splitlines())
    return dict(cpuUsec=int(cpu['usage_usec']),memoryPeakBytes=int((p/'memory.peak').read_text()),cpuMax=(p/'cpu.max').read_text().strip(),memoryMax=(p/'memory.max').read_text().strip())
def timings(v):return dict(samples=len(v),median=statistics.median(v) if v else None,p95=sorted(v)[int(.95*(len(v)-1))] if v else None,maximum=max(v) if v else None)
def codec_context(compact):return Codec().installed() if compact else nullcontext()
def provider():return DiskTickProvider(ROOT/'source/store',SEED['state']['datasetVersion'],read_only=True)
def build_commands():
    result=[]
    for cycle in range(32):
        plan=lambda typ:dict(side='LONG',orderType=typ,workflow='PLANNED',entry='2299' if typ=='LIMIT' else '2302',quantity='0.01',sl='2298' if typ=='LIMIT' else '2300',tp='2301' if typ=='LIMIT' else '2304',riskPercent='1',observations=[])
        t=cycle*5*10**9
        intents=[('ADVANCE',dict(targetNs=str(t)),None),('OPEN',plan('LIMIT'),f'order:limit:{cycle:03}'),
                 ('ADVANCE',dict(targetNs=str(t+10**9)),None),('ADVANCE',dict(targetNs=str(t+2*10**9)),None),
                 ('OPEN',plan('STOP'),f'order:stop:{cycle:03}'),('ADVANCE',dict(targetNs=str(t+3*10**9)),None),
                 ('ADVANCE',dict(targetNs=str(t+4*10**9)),None),('ADVANCE',dict(targetNs=str(t+4*10**9)),None)]
        for kind,payload,cid in intents:
            revision=len(result);result.append(dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=SID,commandId=cid or f'command:{revision:04}',expectedRevision=revision,kind=kind,payload=payload))
    return result


def propose(store,scope,command,timeline,forbid_source=False):
    before,prior=store.prepare(scope,command)
    if prior is not None:return prior,True
    if forbid_source:raise ValueError('RETRY_OPENED_SOURCE')
    cp=before['controller'];kwargs={};replay=None
    if command['kind']=='ADVANCE':
        frame=timeline.advance_through(command['payload']['targetNs'],timeline.cursor);cp=timeline.checkpoint()
        kwargs=dict(reveal=frame,checkpoint=cp);replay=dict(throughNs=frame['throughNs'],exhaustedThroughBoundary=frame['exhaustedThroughBoundary'])
    after,events=apply(before['state'],command,**kwargs)
    return store.commit(scope,command,before,after,cp,events,replay),False


def create_db(admin,name,compact):
    ci=conninfo_to_dict(admin)
    with psycopg.connect(admin,autocommit=True) as db:db.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
    ci['dbname']=name;dsn=make_conninfo(**ci);migrate(dsn)
    if compact:install_schema(dsn)
    return dsn


def physical(dsn):
    with psycopg.connect(dsn,autocommit=True) as db:db.execute('CHECKPOINT')
    with psycopg.connect(dsn) as db:return measure(db,ROOT/'pgdata')


def arm(dsn,compact,size):
    label=('compact' if compact else 'baseline')+f'-{size}';folder=ROOT/label;folder.mkdir(mode=0o700)
    store=ObservedExecutionStore(dsn);writes=[];read_lat=[];start=time.monotonic();cpu=time.process_time()
    empty=physical(dsn);p=provider();timeline=IndexedTickTimeline(p,p.dataset_id,p.dataset_version,'0',log_folder=folder/'timeline',log_codec='zlib-1')
    with codec_context(compact):
        t=time.monotonic();store.create(SCOPE,SEED['state'],SEED['controller']);seed_seconds=time.monotonic()-t
        originals={}
        for i,command in enumerate(COMMANDS[:size]):
            t=time.monotonic();receipt,prior=propose(store,SCOPE,command,timeline);writes.append(time.monotonic()-t)
            if prior:raise ValueError('UNEXPECTED_PRIOR')
            if i in (0,size//2,size-1):originals[i]=canonical_bytes(receipt)
            guard()
        for _ in range(5):
            after=0
            while True:
                t=time.monotonic();view=store.inspect(SCOPE,SID,after,64);read_lat.append(time.monotonic()-t)
                if view['nextEventSequence'] is None:break
                after=view['nextEventSequence']
        retries=[]
        for i,raw in originals.items():
            t=time.monotonic();receipt,prior=propose(store,SCOPE,COMMANDS[i],None,True)
            if not prior or canonical_bytes(receipt)!=raw:raise ValueError('RETRY_RECEIPT')
            retries.append(time.monotonic()-t)
        if size:
            conflict=deepcopy(COMMANDS[0]);conflict['payload']['targetNs']='1'
            try:store.prepare(SCOPE,conflict)
            except ValueError:pass
            else:raise ValueError('CONFLICT_ACCEPTED')
        cp=timeline.checkpoint();timeline.close();p.close()
        t=time.monotonic();peek=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=SID,commandId='probe:unused',expectedRevision=size,kind='ADVANCE',payload=dict(targetNs=cp['cursor']['throughNs']))
        stored,prior=store.prepare(SCOPE,peek);p=provider();cold=IndexedTickTimeline.resume(p,stored['controller'],log_folder=folder/'timeline')
        if prior is not None or cold.checkpoint()!=cp:raise ValueError('COLD_RESUME')
        cold_seconds=time.monotonic()-t;temp_pages=cold._IndexedTickTimeline__db.execute('PRAGMA temp.page_count').fetchone()[0]
        cold.close();p.close()
    with psycopg.connect(dsn) as db:data=fetch(db,SCOPE.workspace_id,SID,compact)
    t=time.monotonic();audited=audit(data,COMMANDS[:size],SEED,size//8);audit_seconds=time.monotonic()-t
    dbstats=physical(dsn);sqlite=folder/'timeline/timeline.sqlite'
    result=dict(status='PASS',compact=compact,commands=size,events=audited['events'],checkpoints=audited['checkpoints'],emptyPostgres=empty,postgres=dbstats,
                sqliteAllocatedBytes=sqlite.stat().st_blocks*512,sqliteFileBytes=sqlite.stat().st_size,
                combinedAllocatedBytes=dbstats['filesystemAllocatedBytes']+sqlite.stat().st_blocks*512,
                writeLatencySeconds=timings(writes),readLatencySeconds=timings(read_lat),retryLatencySeconds=timings(retries),
                seedWriteSeconds=seed_seconds,coldResumeSeconds=cold_seconds,tempPageBytes=temp_pages*4096,
                independentAuditSeconds=audit_seconds,audit=audited,wallSeconds=time.monotonic()-start,cpuSeconds=time.process_time()-cpu,
                workerPeakRSSKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(label+'/metrics.json',result);guard()


def arm_worker(*args):
    try:arm(*args)
    except BaseException as e:
        label=('compact' if args[1] else 'baseline')+f'-{args[2]}'
        save(label+'/failure.json',dict(error=type(e).__name__+':'+str(e)[:500]));raise


@contextmanager
def fatal_commit(phase):
    native=storage.connect
    @contextmanager
    def wrapped(dsn):
        with native(dsn) as db:
            yield db
            if phase=='before':os.kill(os.getpid(),signal.SIGKILL)
        if phase=='after':os.kill(os.getpid(),signal.SIGKILL)
    storage.connect=wrapped
    try:yield
    finally:storage.connect=native


def crash_worker(dsn,compact,scope,folder,phase):
    store=ObservedExecutionStore(dsn)
    with codec_context(compact):
        before,prior=store.prepare(scope,COMMANDS[3]);p=provider();t=IndexedTickTimeline.resume(p,before['controller'],log_folder=folder/'timeline')
        frame=t.advance_through(COMMANDS[3]['payload']['targetNs'],t.cursor);cp=t.checkpoint();after,events=apply(before['state'],COMMANDS[3],reveal=frame,checkpoint=cp)
        replay=dict(throughNs=frame['throughNs'],exhaustedThroughBoundary=frame['exhaustedThroughBoundary'])
        with fatal_commit(phase):store.commit(scope,COMMANDS[3],before,after,cp,events,replay)


def crash_tests(admin):
    results={}
    for compact in (False,True):
        dsn=create_db(admin,'qa6_crash_'+('c' if compact else 'b'),compact)
        for phase in ('before','after'):
            key=('compact' if compact else 'baseline')+'-'+phase;folder=ROOT/('crash-'+key);folder.mkdir(mode=0o700)
            scope=TrustedScope('qa6:crash:'+key,'qa6:actor');store=ObservedExecutionStore(dsn);p=provider();t=IndexedTickTimeline(p,p.dataset_id,p.dataset_version,'0',log_folder=folder/'timeline',log_codec='zlib-1')
            with codec_context(compact):
                store.create(scope,SEED['state'],SEED['controller'])
                for command in COMMANDS[:3]:propose(store,scope,command,t)
            t.close();p.close()
            with psycopg.connect(dsn) as db:objects_before=db.execute('SELECT count(*) FROM public.qa6_objects').fetchone()[0] if compact else None
            child=multiprocessing.get_context('fork').Process(target=crash_worker,args=(dsn,compact,scope,folder,phase));child.start();child.join(60)
            if child.is_alive():child.kill();child.join();raise ValueError('CRASH_TIMEOUT')
            if child.exitcode!=-9:raise ValueError('WORKER_NOT_KILLED')
            with psycopg.connect(dsn) as db:
                revision=db.execute('SELECT revision FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',(scope.workspace_id,SID)).fetchone()[0]
                objects_after=db.execute('SELECT count(*) FROM public.qa6_objects').fetchone()[0] if compact else None
            if revision!=(3 if phase=='before' else 4):raise ValueError('CRASH_SQL_ATOMICITY')
            if compact and phase=='before' and objects_before!=objects_after:raise ValueError('ORPHAN_CODEC_OBJECTS')
            with codec_context(compact):
                peek=dict(COMMANDS[3]);stored,prior=store.prepare(scope,peek)
                if phase=='before':
                    p=provider();t=IndexedTickTimeline.resume(p,stored['controller'],log_folder=folder/'timeline');receipt,was_prior=propose(store,scope,COMMANDS[3],t);t.close();p.close()
                else:receipt,was_prior=propose(store,scope,COMMANDS[3],None,True)
                if was_prior!=(phase=='after') or receipt['state']['balance']!='10002':raise ValueError('CRASH_RETRY_BALANCE')
                retry,found=propose(store,scope,COMMANDS[3],None,True)
                if not found or canonical_bytes(retry)!=canonical_bytes(receipt):raise ValueError('CRASH_DUPLICATE')
            with psycopg.connect(dsn) as db:data=fetch(db,scope.workspace_id,SID,compact)
            checked=audit(data,COMMANDS[:4],SEED,None,oracle=dict(TP=1,SL=0,balance='10002',orders=1))
            results[key]=dict(status='PASS',SIGKILL=child.exitcode,objectsBefore=objects_before,objectsAfterKill=objects_after,independentAudit=checked)
            guard()
    save('crash-recovery.json',results);return results


def adversarial(dsn):
    with psycopg.connect(dsn) as db:data=fetch(db,SCOPE.workspace_id,SID,True)
    results={}
    def reject(name,altered):
        try:audit(altered,COMMANDS,SEED,32)
        except Exception:results[name]='PASS_REJECTED'
        else:raise ValueError('ADVERSARIAL_ACCEPTED:'+name)
    bad=dict(data,events=data['events'][:-1]);reject('missing_tail_event',bad)
    reject('reordered_commands',dict(data,commands=[data['commands'][1],data['commands'][0]]+data['commands'][2:]))
    reject('duplicated_events',dict(data,events=data['events']+[data['events'][-1]]))
    reject('missing_checkpoint',dict(data,checkpoints=data['checkpoints'][:-1]))
    root=bytes(data['tip'][0])[len(b'QA6-DAG-ROOT-1\0'):]
    objects=dict(data['objects']);objects.pop(root);reject('missing_shared_object',dict(data,objects=objects))
    objects=dict(data['objects']);objects[root]=objects[root][:-1]+bytes([objects[root][-1]^1]);reject('corrupted_shared_object',dict(data,objects=objects))
    reject('substituted_tip',dict(data,tip=(data['checkpoints'][0][1],data['tip'][1])))
    objects=dict(data['objects']);objects[root]=objects[root]+b'trailing';reject('trailing_stream',dict(data,objects=objects))
    import zlib
    objects=dict(data['objects']);objects[root]=b'QA6-DAG-ZLIB-1\0'+zlib.compress(b'x'*1048577);reject('inflation_limit',dict(data,objects=objects))
    save('adversarial.json',results);return results


def main():
    global SEED,COMMANDS
    guard()
    if (SOURCE/'postmaster.pid').exists():raise ValueError('SOURCE_QA_ACTIVE')
    state=subprocess.check_output([str(BIN/'pg_controldata'),str(SOURCE)],text=True)
    if 'Database cluster state:               shut down' not in state:raise ValueError('SOURCE_QA_NOT_CLEAN')
    source_stamp=[SOURCE.stat().st_ino,SOURCE.stat().st_mtime_ns]
    from tests.test_observed_kernel import ObservedKernelTests
    fixture=object.__new__(ObservedKernelTests);fixture.root=ROOT/'source';fixture.root.mkdir(mode=0o700);fixture.handles=[];fixture.serial=0;fixture.policy=MethodPolicy('method:qa','a'*64,'FREE_STYLE',False,())
    quotes=[]
    for cycle in range(32):
        for offset,(bid,ask) in enumerate([('2300','2300.1'),('2298.9','2299'),('2301','2301.1'),('2302','2302.1'),('2299.9','2300')]):quotes.append(((cycle*5+offset)*10**9,bid,ask))
    fixture.setup_stream(quotes);SEED=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-CHECKPOINT-1',state=fixture.state,controller=fixture.timeline.checkpoint())
    fixture.timeline.close();fixture.provider.close();(ROOT/'source/store/archive.sqlite').chmod(0o400)
    COMMANDS=build_commands();save('workload.json',dict(seed=SEED,commands=COMMANDS,source='AUTHORED_OBSERVED_QA; actual existing pending/SL/TP engine; not broker or annual market acceptance'))
    data=ROOT/'pgdata';shutil.copytree(SOURCE,data,copy_function=shutil.copy2);guard();sock=Path('/tmp/rx6-55840');sock.mkdir(mode=0o700)
    ci=conninfo_to_dict(json.loads((E/'annual-xau2024-20261030/private-connection.json').read_text())['database']);ci.update(host=str(sock),port='55840');admin=make_conninfo(**ci)
    subprocess.run([str(BIN/'pg_ctl'),'-D',str(data),'-l',str(ROOT/'postgres.log'),'-o',f"-c listen_addresses='' -k {sock} -p 55840 -c shared_buffers=32MB -c max_connections=30 -c unix_socket_permissions=0700",'-w','start'],check=True,capture_output=True,text=True,timeout=60)
    try:
        results=[];largest=None
        for size in SIZES:
            pair=[]
            for compact in (False,True):
                label=('compact' if compact else 'baseline')+f'-{size}';dsn=create_db(admin,'qa6_'+('c' if compact else 'b')+str(size),compact)
                child=multiprocessing.get_context('fork').Process(target=arm_worker,args=(dsn,compact,size));child.start()
                while child.is_alive():
                    try:guard()
                    except BaseException:child.kill();child.join();raise
                    child.join(.25)
                if child.exitcode:raise ValueError('ARM_FAILURE:'+label)
                pair.append(json.loads((ROOT/label/'metrics.json').read_text()))
                if compact and size==256:largest=dsn
            if pair[0]['audit']!=pair[1]['audit']:raise ValueError('BASELINE_COMPACT_LOGICAL_PARITY')
            results.append(dict(commands=size,baseline=pair[0],compact=pair[1],savingBytes=pair[0]['combinedAllocatedBytes']-pair[1]['combinedAllocatedBytes'],savingPercent=100*(pair[0]['combinedAllocatedBytes']-pair[1]['combinedAllocatedBytes'])/pair[0]['combinedAllocatedBytes']))
            save('progress.json',dict(completedSizes=[p['commands'] for p in results],results=results));guard()
        attacks=adversarial(largest);crashes=crash_tests(admin)
        slopes=[]
        for lower,upper in zip(results,results[1:]):
            slopes.append(dict(fromCommands=lower['commands'],toCommands=upper['commands'],baselineBytesPerAdditionalCommand=(upper['baseline']['combinedAllocatedBytes']-lower['baseline']['combinedAllocatedBytes'])/(upper['commands']-lower['commands']),compactBytesPerAdditionalCommand=(upper['compact']['combinedAllocatedBytes']-lower['compact']['combinedAllocatedBytes'])/(upper['commands']-lower['commands'])))
        report=dict(status='PASS_BOUNDED_FINANCIAL_PERSISTENCE_EXPERIMENT',results=results,slopes=slopes,adversarial=attacks,crashRecovery=crashes,
                    model='SQLite existing zlib logs in both arms; same existing PostgreSQL tables/financial reducer; QA physical DAG references plus immutable shared objects in candidate only',
                    target500MB='NOT_CERTIFIED: no annual workload or user Session-count distribution measured',production='NOT_TOUCHED',H1H2H3='NOT_ACCESSED',contracts='UNCHANGED',
                    resources=dict(wallSeconds=time.monotonic()-START,cgroup=cg(),allocatedArtifacts=allocated(ROOT),budget=BUDGET,freeDisk=shutil.disk_usage(ROOT).free,reserve=RESERVE))
        if source_stamp!=[SOURCE.stat().st_ino,SOURCE.stat().st_mtime_ns]:raise ValueError('SOURCE_CLUSTER_CHANGED')
        save('report.json',report);print(json.dumps(dict(status=report['status'],storage=[dict(commands=x['commands'],baseline=x['baseline']['combinedAllocatedBytes'],compact=x['compact']['combinedAllocatedBytes'],savingPercent=x['savingPercent']) for x in results],resources=report['resources']),sort_keys=True),flush=True)
    finally:
        subprocess.run([str(BIN/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'],check=True,capture_output=True,text=True,timeout=60);sock.rmdir()
    guard()


if __name__=='__main__':
    try:main()
    except BaseException as error:
        save('partial-'+str(time.time_ns())+'.json',dict(status='STOP_PARTIAL',error=type(error).__name__+':'+str(error)[:500],wallSeconds=time.monotonic()-START,cgroup=cg(),allocatedArtifacts=allocated(ROOT)))
        raise
