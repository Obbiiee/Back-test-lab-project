"""Explicit-run bounded C1+C5+C6 integration, QA only; no public/runtime mount."""
import hashlib,json,multiprocessing,os,re,resource,shutil,signal,sqlite3,statistics,subprocess,time
from contextlib import closing,nullcontext
from copy import deepcopy
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo
from application.models import TrustedScope
from contracts.canonical import canonical_bytes,content_hash
from contracts.models import MethodPolicy
from execution.observed_kernel import apply,seed_state
from execution.observed_profile import ObservedExecutionProfile
from execution.observed_postgres import ObservedExecutionStore
from ticks.storage_v2 import DiskTickProvider
from ticks.timeline_v2 import IndexedTickTimeline
from ticks.read_snapshot_v2 import export_read_snapshot
from tests.qa_range_prototype5 import atomic_reference,install_commit_table,refs
from tests.qa_range_verifier5 import source_groups,consumer
from tests.qa_pg_codec6 import Codec
from tests.qa_pg_verify6 import fetch,decode,audit
from tests.qa_pg_measure6 import measure
from tests.qa_pg_checkpoint6 import create_db,build_commands
from tests.qa_integrated_format7 import Journal,session_lock,baseline_commit_barrier
from tests.qa_integrated_verify7 import verify,history

ROOT=Path('/home/riksora/riksora-qa-evidence/session-storage-20261030/checkpoint7')
E=Path('/home/riksora/riksora-qa-evidence');C1=E/'serving-efficiency-20261030T161839Z'
SOURCE=Path('/tmp/riksora-exclusive-qa-8l28d6oy/data');BIN=Path('/usr/lib/postgresql/16/bin')
START=time.monotonic();BUDGET=512*1024**2;RESERVE=30*1024**3;os.umask(0o077)


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
    if time.monotonic()-START>845:raise RuntimeError('TIME_BUDGET')
def save(name,value):
    p=ROOT/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True);tmp=p.with_name(p.name+'.pending')
    with tmp.open('wb') as stream:stream.write(json.dumps(value,sort_keys=True,indent=2).encode());stream.flush();os.fsync(stream.fileno())
    os.replace(tmp,p)
def cg():
    rel=next(v for v in Path('/proc/self/cgroup').read_text().splitlines() if v.startswith('0::')).split('::')[1]
    p=Path('/sys/fs/cgroup')/rel.lstrip('/');cpu=dict(v.split() for v in (p/'cpu.stat').read_text().splitlines())
    return dict(cpuUsec=int(cpu['usage_usec']),memoryPeakBytes=int((p/'memory.peak').read_text()),cpuMax=(p/'cpu.max').read_text().strip(),memoryMax=(p/'memory.max').read_text().strip())
def stamp(path):
    s=path.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_mode]
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def timing(v):return dict(samples=len(v),median=statistics.median(v) if v else None,p95=sorted(v)[int(.95*(len(v)-1))] if v else None,maximum=max(v) if v else None)
def context(candidate):return Codec().installed() if candidate else nullcontext()


class CountedProvider:
    def __init__(self,folder,version):
        self.inner=DiskTickProvider(folder,version,read_only=True);self.dataset_id=self.inner.dataset_id;self.dataset_version=self.inner.dataset_version;self.rows=0;self.calls=0
    def describe_v2(self,*args):return self.inner.describe_v2(*args)
    def locate_v2(self,*args):return self.inner.locate_v2(*args)
    def read_evidence_v2(self,*args):return self.inner.read_evidence_v2(*args)
    def read_page_v2(self,*args):
        value=self.inner.read_page_v2(*args);self.rows+=len(value['events']);self.calls+=1;return value
    def close(self):self.inner.close()


def source(asset,candidate):return CountedProvider(Path(asset['snapshot' if candidate else 'parent']),asset['seed']['state']['datasetVersion'])
def binding(asset,scope):
    seed=asset['seed'];return dict(schemaVersion=1,format='RIKSORA-QA-INTEGRATED-BINDING-1',workspace=scope.workspace_id,sessionId=seed['state']['sessionId'],datasetId=seed['state']['datasetId'],datasetVersion=seed['state']['datasetVersion'],profileHash=seed['state']['profileHash'],methodHash=seed['state']['policy']['definitionHash'],timelineVersion=seed['controller']['cursor']['timelineVersion'],engineVersion=seed['state']['engineVersion'],strictExecutionEligibility='NOT_GRANTED')


def execute(store,scope,folder,asset,command,candidate,timeline=None,forbid_source=False,fault=None):
    with session_lock(folder):
        before,prior=store.prepare(scope,command)
        if prior is not None:return prior,True,0
        if forbid_source:raise ValueError('RETRY_SOURCE_ACCESS')
        p=None;owned=False
        if timeline is None:
            p=source(asset,candidate);timeline=IndexedTickTimeline.resume(p,before['controller'],log_folder=folder/'engine');owned=True
        journal=None
        try:
            old=before['controller'];cp=old;kwargs={};replay=None;positions=[];ticks=0
            if command['kind']=='ADVANCE':
                frame=timeline.advance_through(command['payload']['targetNs'],timeline.cursor);cp=timeline.checkpoint();kwargs=dict(reveal=frame,checkpoint=cp)
                replay=dict(throughNs=frame['throughNs'],exhaustedThroughBoundary=frame['exhaustedThroughBoundary']);ticks=sum(len(g['events']) for g in frame['groups'])
                if cp['positionLogHash']!=old['positionLogHash']:positions=json.loads(timeline._IndexedTickTimeline__read_block(cp['positionLogHash']))['records']
            after,events=apply(before['state'],command,**kwargs)
            journal=Journal(folder/'session.sqlite',binding(asset,scope));committed=refs(store.dsn,scope,command['sessionId']) if candidate else []
            digest=journal.prepare_command(command,old,cp,positions,committed[-1][2] if committed else None,candidate)
            if fault:fault('after_prepare')
            if candidate:
                with atomic_reference(scope,command,digest,fault):receipt=store.commit(scope,command,before,after,cp,events,replay)
            else:
                with baseline_commit_barrier(fault):receipt=store.commit(scope,command,before,after,cp,events,replay)
            if fault:fault('after_sql_commit')
            if candidate:journal.publish(digest)
            if fault:fault('after_finalize')
            return receipt,False,ticks
        finally:
            if journal:journal.close()
            if owned:timeline.close();p.close()


def pg_physical(dsn):
    with psycopg.connect(dsn,autocommit=True) as db:db.execute('CHECKPOINT')
    with psycopg.connect(dsn) as db:
        result=measure(db,ROOT/'pgdata')
        row=db.execute("SELECT oid,reltoastrelid,pg_total_relation_size(oid) FROM pg_class WHERE oid=to_regclass('public.qa5_commits')").fetchone()
        if row:
            oid,toast,total=row;parents=[oid]+([toast] if toast else []);oids=parents+[r[0] for r in db.execute('SELECT indexrelid FROM pg_index WHERE indrelid=ANY(%s)',(parents,))];files=[]
            for relative, in db.execute('SELECT pg_relation_filepath(x) FROM unnest(%s::oid[]) x',(oids,)):
                path=ROOT/'pgdata'/relative;pattern=re.compile(re.escape(path.name)+r'(?:_(?:fsm|vm|init))?(?:\.\d+)?$')
                for p in path.parent.iterdir():
                    if pattern.fullmatch(p.name):files.append(dict(path=str(p.relative_to(ROOT/'pgdata')),size=p.stat().st_size,allocated=p.stat().st_blocks*512))
            if sum(f['size'] for f in files)!=total:raise ValueError('REFERENCE_PHYSICAL_ACCOUNTING')
            extra=dict(table='qa5_commits',filesystemAllocatedBytes=sum(f['allocated'] for f in files),postgresReportedBytes=total,files=files)
            result['tables'].append(extra);result['filesystemAllocatedBytes']+=extra['filesystemAllocatedBytes']
        return result


def snapshot_metrics(dsn,folder,candidate,timeline):
    timeline._IndexedTickTimeline__db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    pg=pg_physical(dsn);journal=folder/'session.sqlite';engine=folder/'engine/timeline.sqlite'
    sqlite=journal.stat().st_blocks*512+(0 if candidate else engine.stat().st_blocks*512)
    return dict(postgres=pg,sessionSQLiteAllocatedBytes=sqlite,sessionAllocatedBytes=sqlite+pg['filesystemAllocatedBytes'],engineScratchAllocatedBytes=allocated(folder/'engine') if candidate else 0)


def assets():
    from tests.test_observed_kernel import ObservedKernelTests
    fixture=object.__new__(ObservedKernelTests);fixture.root=ROOT/'financial-source';fixture.root.mkdir(mode=0o700);fixture.handles=[];fixture.serial=0;fixture.policy=MethodPolicy('method:qa','a'*64,'FREE_STYLE',False,())
    quotes=[]
    for cycle in range(64):
        for offset,(bid,ask) in enumerate([('2300','2300.1'),('2298.9','2299'),('2301','2301.1'),('2302','2302.1'),('2299.9','2300')]):quotes.append(((cycle*5+offset)*10**9,bid,ask))
    fixture.setup_stream(quotes);seed=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-CHECKPOINT-1',state=fixture.state,controller=fixture.timeline.checkpoint());fixture.timeline.close();fixture.provider.close()
    parent=fixture.root/'store';(parent/'archive.sqlite').chmod(0o400);snapshot=fixture.root/'derived-serving'
    projected=export_read_snapshot(parent,snapshot,dataset_id=seed['state']['datasetId'],dataset_version=seed['state']['datasetVersion'],expected_archive_sha256=sha(parent/'archive.sqlite'))
    cmds=build_commands()
    for old in build_commands():
        new=deepcopy(old);new['expectedRevision']+=256
        if new['kind']=='OPEN':new['commandId']=new['commandId'].rsplit(':',1)[0]+':'+f"{int(new['commandId'].rsplit(':',1)[1])+32:03}"
        else:new['commandId']=f"command:{new['expectedRevision']:04}"
        if new['kind']=='ADVANCE':new['payload']['targetNs']=str(int(new['payload']['targetNs'])+160*10**9)
        cmds.append(new)
    financial=dict(name='financial-128',parent=str(parent),snapshot=str(snapshot),seed=seed,commands=cmds,cycles=64,sourceClass='AUTHORED_OBSERVED_QA',export=projected)
    proof=json.loads((C1/'report.json').read_text());realparent=C1/'validated-parent';realsnapshot=C1/'derived-serving'
    if sha(realparent/'archive.sqlite')!=proof['export']['parentArchiveSha256'] or sha(realsnapshot/'archive.sqlite')!=proof['export']['archiveSha256']:raise ValueError('C1_EXISTING_PIN_CHANGED')
    before={str(p):stamp(p) for p in (realparent/'archive.sqlite',realsnapshot/'archive.sqlite')}
    p=CountedProvider(realparent,proof['sliceDatasetVersion']);desc=p.describe_v2(p.dataset_id,p.dataset_version);root=desc['root'];start=root['range']['startNs']
    t=IndexedTickTimeline(p,p.dataset_id,p.dataset_version,start,log_folder=ROOT/'real-seed',log_codec='zlib-1')
    from tests.test_observed_kernel import BASE
    raw=deepcopy(BASE);raw['primary']=dict(datasetId=p.dataset_id,datasetVersion=p.dataset_version,providerId=root['providerId'],feedId=root['feedId'],feedInstrumentId=root['instrumentId'],providerSymbol=root['providerSymbol'],evidenceClass=root['evidenceClass'])
    profile=ObservedExecutionProfile.from_wire(raw);cp=t.checkpoint();state=seed_state('session:xau-qa7',profile,fixture.policy,cp);t.close()
    realcommands=[];last=None
    for index,(_,group) in enumerate(source_groups(p,start),1):
        if index%64==0 or index==2222:
            last=group['timeNs'];realcommands.append(dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=state['sessionId'],commandId=f'real:advance:{len(realcommands)}',expectedRevision=len(realcommands),kind='ADVANCE',payload=dict(targetNs=last)))
        if index==2222:break
    if index!=2222:raise ValueError('C1_PREFIX_MISSING')
    realcommands.append(dict(realcommands[-1],commandId='real:zero-reveal',expectedRevision=len(realcommands)))
    p.close();q=CountedProvider(realsnapshot,proof['sliceDatasetVersion'])
    if q.describe_v2(q.dataset_id,q.dataset_version)!=desc:raise ValueError('C1_PUBLICATION_PARITY')
    q.close()
    real=dict(name='xau-2222',parent=str(realparent),snapshot=str(realsnapshot),seed=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-CHECKPOINT-1',state=state,controller=cp),commands=realcommands,cycles=0,sourceClass='ACCEPTED_C1_DERIVATIVE_XAUUSD2024_REPLAY_ONLY_NO_FINANCIAL_ADMISSION',pinnedFiles=before)
    save('assets.json',dict(financial=financial,xau=real));return [real,financial]


def load_data(dsn,scope,asset,candidate):
    with psycopg.connect(dsn) as db:return fetch(db,scope.workspace_id,asset['seed']['state']['sessionId'],candidate)


def arm(dsn,asset,candidate):
    name=asset['name']+('-candidate' if candidate else '-baseline');folder=ROOT/name;folder.mkdir(mode=0o700)
    scope=TrustedScope('qa7:'+asset['name'],'qa7:actor');seed=asset['seed'];commands=asset['commands'];store=ObservedExecutionStore(dsn)
    wall=time.monotonic();cpu=time.process_time();p=source(asset,candidate)
    timeline=IndexedTickTimeline(p,p.dataset_id,p.dataset_version,seed['state']['startNs'],log_folder=folder/'engine',log_codec='zlib-1')
    journal=Journal(folder/'session.sqlite',binding(asset,scope));journal.close();writes=[];ticks=0;originals={};interim=[]
    with context(candidate):
        store.create(scope,seed['state'],seed['controller']);interim.append(dict(commands=0,**snapshot_metrics(dsn,folder,candidate,timeline)))
        write_cpu=cg()['cpuUsec'];write_wall=time.monotonic();provider_rows=p.rows
        for index,command in enumerate(commands):
            t=time.monotonic();receipt,prior,count=execute(store,scope,folder,asset,command,candidate,timeline)
            writes.append(time.monotonic()-t);ticks+=count
            if prior:raise ValueError('UNEXPECTED_RETRY')
            if index in (0,len(commands)//2,len(commands)-1):originals[index]=canonical_bytes(receipt)
            if index+1 in (16,64,256,512,len(commands)):
                interim.append(dict(commands=index+1,**snapshot_metrics(dsn,folder,candidate,timeline)))
            guard()
        write_stage_cpu=(cg()['cpuUsec']-write_cpu)/1e6;write_stage_wall=time.monotonic()-write_wall;write_delivered=p.rows-provider_rows
        retry=[]
        for index,original in originals.items():
            t=time.monotonic();value,prior,_=execute(store,scope,folder,asset,commands[index],candidate,forbid_source=True)
            if not prior or canonical_bytes(value)!=original:raise ValueError('EXACT_RETRY')
            retry.append(time.monotonic()-t)
        altered=deepcopy(commands[0]);altered['payload']['targetNs']=str(int(altered['payload']['targetNs'])+1)
        try:execute(store,scope,folder,asset,altered,candidate,forbid_source=True)
        except ValueError as error:
            if 'IDEMPOTENCY_CONFLICT' not in str(error):raise
        else:raise ValueError('CONFLICT_ACCEPTED')
        boundary=None
        if asset['cycles']==64:
            probe=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=seed['state']['sessionId'],commandId='order:129',expectedRevision=512,kind='OPEN',payload=deepcopy(commands[1]['payload']))
            before=store.prepare(scope,probe)[0];before_hash=content_hash(before)
            try:execute(store,scope,folder,asset,probe,candidate,timeline)
            except ValueError as error:
                if 'REFUSED_STATE_LIMIT' not in str(error):raise
            else:raise ValueError('129TH_ORDER_ACCEPTED')
            after=store.prepare(scope,probe)[0]
            if content_hash(after)!=before_hash or len(after['state']['orders'])!=128:raise ValueError('BOUNDARY_STATE_CHANGED')
            with closing(sqlite3.connect((folder/'session.sqlite').resolve().as_uri()+'?mode=ro',uri=True)) as db:
                if db.execute('SELECT count(*) FROM intents').fetchone()[0]!=512:raise ValueError('REJECTED_INTENT_PERSISTED')
            boundary=dict(status='PASS',retainedOrders=128,attempt129='REFUSED_STATE_LIMIT',stateUnchanged=True)
        checkpoint=timeline.checkpoint();timeline.close();p.close();native_cold=None
        if not candidate:
            t=time.monotonic();peek=dict(commands[-1],commandId='qa7:cold-probe',expectedRevision=len(commands));stored,prior=store.prepare(scope,peek)
            p=source(asset,False);native=IndexedTickTimeline.resume(p,stored['controller'],log_folder=folder/'engine');native_cold=time.monotonic()-t
            if native.checkpoint()!=checkpoint:raise ValueError('NATIVE_COLD_CHECKPOINT')
    # No writer-generated index or cache is supplied to the independent verifier.
    cold_cpu=cg()['cpuUsec'];t=time.monotonic();data=load_data(dsn,scope,asset,candidate);committed=refs(dsn,scope,seed['state']['sessionId']) if candidate else []
    vp=source(asset,candidate);verified=verify(data,folder/'session.sqlite',binding(asset,scope),committed,candidate,vp,folder/'independent-engine')
    verified_cold=time.monotonic()-t;verified_cold_cpu=(cg()['cpuUsec']-cold_cpu)/1e6
    if verified['checkpoint']!=checkpoint:raise ValueError('VERIFIED_COLD_CHECKPOINT')
    oracle=audit(data,commands,seed,asset['cycles'])
    view=consumer(vp,seed['state']['startNs'],checkpoint) if candidate else native.consumer()
    read_lat=[];stream=hashlib.sha256();end=int(checkpoint['cursor']['nextGroupIndex'])
    for offset in range(0,end,64):
        t=time.monotonic();batch=view.read_revealed(str(offset),min(64,end-offset));read_lat.append(time.monotonic()-t)
        for group in batch:stream.update(json.dumps(group,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
        guard()
    if stream.hexdigest()!=verified['groupHash'] or view.read_revealed(str(end),1)!=[]:raise ValueError('READ_REVEAL_PARITY')
    try:view.read_revealed(str(end+1),1)
    except ValueError:pass
    else:raise ValueError('FUTURE_EXPOSED')
    if any(hasattr(view,key) for key in ('provider','checkpoint','locate_v2','index','eof')):raise ValueError('CONSUMER_CAPABILITY')
    if not candidate:native.close();p.close()
    vp.close();persistent=interim[-1];parent_bytes=allocated(Path(asset['parent']));snapshot_bytes=allocated(Path(asset['snapshot']))
    results=dict(status='PASS',lane=asset['name'],candidate=candidate,commands=len(commands),groups=verified['groups'],processedTicks=ticks,
                 writeStageCgroupCPUSeconds=write_stage_cpu,writeStageWallSeconds=write_stage_wall,
                 cpuSecondsPerMillionRevealedTicks=write_stage_cpu/ticks*1e6 if ticks else None,
                 providerRowsDeliveredDuringWrite=write_delivered,providerRowsAreNotRevealedTicks=True,
                 writeLatencySeconds=timing(writes),readLatencySeconds=timing(read_lat),retryLatencySeconds=timing(retry),
                 nativeColdResumeSeconds=native_cold,verifiedColdResumeSeconds=verified_cold,verifiedColdCgroupCPUSeconds=verified_cold_cpu,
                 persistent=persistent,incrementalSnapshots=interim,retainedCanonicalParentBytes=parent_bytes,servingStoreBytes=snapshot_bytes if candidate else parent_bytes,
                 servingRolePlusSessionBytes=(snapshot_bytes if candidate else parent_bytes)+persistent['sessionAllocatedBytes'],
                 retainedParentPlusServingPlusSessionBytes=parent_bytes+(snapshot_bytes if candidate else 0)+persistent['sessionAllocatedBytes'],
                 candidateLegacyScratchBytes=allocated(folder/'engine') if candidate else 0,verifierScratchBytes=allocated(folder/'independent-engine'),
                 independentVerification=verified,financialOracle=oracle,orderBoundary=boundary,wallSeconds=time.monotonic()-wall,cpuSeconds=time.process_time()-cpu,
                 workerPeakRSSKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save(name+'/metrics.json',results);guard()


def arm_worker(*args):
    try:arm(*args)
    except BaseException as error:
        label=args[1]['name']+('-candidate' if args[2] else '-baseline')
        save(label+'/failure.json',dict(status='FAIL',error=type(error).__name__+':'+str(error)[:500]));raise


def run_children(specs,timeout=120):
    children=[];start=time.monotonic()
    for target,args in specs:
        process=multiprocessing.get_context('fork').Process(target=target,args=args);process.start();children.append(process)
    while any(c.is_alive() for c in children):
        try:
            guard()
            if time.monotonic()-start>timeout:raise RuntimeError('WORKER_TIMEOUT')
        except BaseException:
            for child in children:
                if child.is_alive():child.kill()
            for child in children:child.join()
            raise
        for child in children:child.join(.1)
    return [c.exitcode for c in children]


def create_session_db(admin,name,candidate):
    dsn=create_db(admin,name,candidate)
    if candidate:install_commit_table(dsn)
    return dsn


def seed_prefix(dsn,asset,candidate,scope,folder,count=3):
    folder.mkdir(mode=0o700,parents=True,exist_ok=True);store=ObservedExecutionStore(dsn);p=source(asset,candidate)
    t=IndexedTickTimeline(p,p.dataset_id,p.dataset_version,asset['seed']['state']['startNs'],log_folder=folder/'engine',log_codec='zlib-1')
    with context(candidate):
        store.create(scope,asset['seed']['state'],asset['seed']['controller'])
        for command in asset['commands'][:count]:execute(store,scope,folder,asset,command,candidate,t)
    t.close();p.close()


def verify_case(dsn,asset,candidate,scope,folder,label):
    data=load_data(dsn,scope,asset,candidate);committed=refs(dsn,scope,asset['seed']['state']['sessionId']) if candidate else []
    p=source(asset,candidate)
    try:result=verify(data,folder/'session.sqlite',binding(asset,scope),committed,candidate,p,folder/label)
    finally:p.close()
    return data,committed,result


def fatal_worker(dsn,asset,candidate,scope,folder,phase):
    def fault(point):
        if point==phase:os.kill(os.getpid(),signal.SIGKILL)
    with context(candidate):execute(ObservedExecutionStore(dsn),scope,folder,asset,asset['commands'][3],candidate,fault=fault)


def crash_tests(admin,asset):
    results={};last_case=None
    for candidate in (False,True):
        dsn=create_session_db(admin,'qa7_fault_'+('c' if candidate else 'b'),candidate)
        phases=('after_prepare','before_sql_commit','after_sql_commit','after_finalize') if candidate else ('before_sql_commit','after_sql_commit')
        for phase in phases:
            name=('candidate' if candidate else 'baseline')+'-'+phase;scope=TrustedScope('qa7:fault:'+name,'qa7:actor');folder=ROOT/('crash-'+name)
            seed_prefix(dsn,asset,candidate,scope,folder)
            with psycopg.connect(dsn) as db:objects_before=db.execute('SELECT count(*) FROM public.qa6_objects').fetchone()[0] if candidate else None
            codes=run_children([(fatal_worker,(dsn,asset,candidate,scope,folder,phase))],60)
            if codes!=[-9]:raise ValueError('SIGKILL_NOT_REACHED')
            with psycopg.connect(dsn) as db:
                revision=db.execute('SELECT revision FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',(scope.workspace_id,asset['seed']['state']['sessionId'])).fetchone()[0]
                objects_after=db.execute('SELECT count(*) FROM public.qa6_objects').fetchone()[0] if candidate else None
            committed_before=phase in ('after_sql_commit','after_finalize')
            if revision!=(4 if committed_before else 3) or (candidate and not committed_before and objects_before!=objects_after):raise ValueError('CROSS_STORE_ATOMICITY')
            data,committed,cold=verify_case(dsn,asset,candidate,scope,folder,'cold-before-retry')
            if cold['balance']!=('10002' if committed_before else '10000'):raise ValueError('RECOVERY_BALANCE')
            if candidate and committed:
                journal=Journal(folder/'session.sqlite',binding(asset,scope));journal.publish(committed[-1][2]);journal.close()
            with context(candidate):
                receipt,prior,_=execute(ObservedExecutionStore(dsn),scope,folder,asset,asset['commands'][3],candidate,forbid_source=committed_before)
                if prior!=committed_before:raise ValueError('RECOVERY_IDEMPOTENCY')
                retry,prior,_=execute(ObservedExecutionStore(dsn),scope,folder,asset,asset['commands'][3],candidate,forbid_source=True)
                if not prior or canonical_bytes(retry)!=canonical_bytes(receipt):raise ValueError('RETRY_CHANGED')
            data,committed,final=verify_case(dsn,asset,candidate,scope,folder,'cold-after-retry')
            commands,_=history(data,folder/'session.sqlite',binding(asset,scope),committed,candidate)
            checked=audit(data,commands,asset['seed'],None,oracle=dict(TP=1,SL=0,balance='10002',orders=1))
            results[name]=dict(status='PASS',SIGKILL=-9,revisionAfterKill=revision,objectCountBefore=objects_before,objectCountAfterKill=objects_after,coldBeforeRetry=cold,final=final,financialOracle=checked)
            if candidate:last_case=(dsn,scope,folder)
            guard()
    save('crash-tests.json',results);return results,last_case


def multi_worker(dsn,asset,scope,folder,command,barrier,label):
    barrier.wait(15);start=time.monotonic()
    try:
        with context(True):receipt,prior,ticks=execute(ObservedExecutionStore(dsn),scope,folder,asset,command,True)
        result=dict(status='PASS',prior=prior,ticks=ticks,receiptHash=content_hash(receipt),balance=receipt['state']['balance'])
    except ValueError as error:
        if 'REFUSED_STALE_REVISION' not in str(error):raise
        result=dict(status='EXPECTED_STALE',error=str(error))
    result.update(wallSeconds=time.monotonic()-start,workerPeakRSSKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    save('multi/'+label+'.json',result)


def multi_tests(admin,asset):
    dsn=create_session_db(admin,'qa7_multi',True);results={}
    for case in ('distinct-sessions','duplicate-command','competing-intents'):
        specs=[];sessions=[];barrier=multiprocessing.get_context('fork').Barrier(2)
        if case=='distinct-sessions':
            for i in range(2):
                scope=TrustedScope(f'qa7:multi:{case}:{i}','qa7:actor');folder=ROOT/'multi'/f'{case}-{i}'
                seed_prefix(dsn,asset,True,scope,folder);sessions.append((scope,folder))
                specs.append((multi_worker,(dsn,asset,scope,folder,asset['commands'][3],barrier,case+'-'+str(i))))
        else:
            scope=TrustedScope('qa7:multi:'+case,'qa7:actor');folder=ROOT/'multi'/case;seed_prefix(dsn,asset,True,scope,folder);sessions.append((scope,folder))
            for i in range(2):
                command=deepcopy(asset['commands'][3])
                if case=='competing-intents' and i:command['commandId']='multi:competing'
                specs.append((multi_worker,(dsn,asset,scope,folder,command,barrier,case+'-'+str(i))))
        cpu=cg()['cpuUsec'];start=time.monotonic();codes=run_children(specs,90);elapsed=time.monotonic()-start;used_cpu=(cg()['cpuUsec']-cpu)/1e6
        if codes!=[0,0]:raise ValueError('MULTI_WORKER_FAILURE')
        output=[json.loads((ROOT/'multi'/f'{case}-{i}.json').read_text()) for i in range(2)]
        if case=='duplicate-command' and (sum(x['prior'] for x in output)!=1 or output[0]['receiptHash']!=output[1]['receiptHash']):raise ValueError('MULTI_DUPLICATE')
        if case=='competing-intents' and sorted(x['status'] for x in output)!=['EXPECTED_STALE','PASS']:raise ValueError('MULTI_STALE')
        verified=[]
        for scope,folder in sessions:
            data,committed,proof=verify_case(dsn,asset,True,scope,folder,'independent-recovery')
            commands,_=history(data,folder/'session.sqlite',binding(asset,scope),committed,True)
            audit(data,commands,asset['seed'],None,oracle=dict(TP=1,SL=0,balance='10002',orders=1));verified.append(proof)
        results[case]=dict(status='PASS',workers=2,distinctSessions=len(sessions),outputs=output,wallSeconds=elapsed,cgroupCPUSeconds=used_cpu,
                           cpuSecondsPerSuccessfulSessionOperation=used_cpu/len(sessions),verification=verified,
                           measurementLimit='single operation, two OS workers under one shared CPU quota; not steady-state cost or capacity certification')
        guard()
    save('multi-tests.json',results);return results


def adversarial(asset,last_case):
    dsn,scope,folder=last_case;data=load_data(dsn,scope,asset,True);committed=refs(dsn,scope,asset['seed']['state']['sessionId']);expected=binding(asset,scope);results={}
    for name,mutation in [('missing-prepare','DELETE FROM prepared WHERE seq=4'),('missing-intent',"DELETE FROM intents WHERE id='command:0003'"),('corrupt-prepare','UPDATE prepared SET body=zeroblob(8) WHERE seq=4')]:
        copy=ROOT/'adversarial'/name;copy.mkdir(mode=0o700,parents=True);destination=copy/'session.sqlite'
        with closing(sqlite3.connect((folder/'session.sqlite').resolve().as_uri()+'?mode=ro',uri=True)) as old,closing(sqlite3.connect(destination)) as new:
            old.backup(new);new.execute(mutation);new.commit()
        try:history(data,destination,expected,committed,True)
        except Exception:results[name]='PASS_REJECTED'
        else:raise ValueError('ADVERSARY_ACCEPTED:'+name)
    for name,references in [('missing-reference',committed[:-1]),('reordered-reference',[committed[1],committed[0]]+committed[2:]),('duplicated-reference',committed+[committed[-1]])]:
        try:history(data,folder/'session.sqlite',expected,references,True)
        except Exception:results[name]='PASS_REJECTED'
        else:raise ValueError('ADVERSARY_ACCEPTED:'+name)
    for name,altered in [('substituted-binding',dict(expected,datasetVersion='f'*64))]:
        try:history(data,folder/'session.sqlite',altered,committed,True)
        except Exception:results[name]='PASS_REJECTED'
        else:raise ValueError('ADVERSARY_ACCEPTED:'+name)
    # Independent object decoder and financial replay must reject a broken shared root.
    broken=dict(data,objects=dict(data['objects']));digest=bytes(data['tip'][0])[len(b'QA6-DAG-ROOT-1\0'):];broken['objects'].pop(digest)
    p=source(asset,True)
    try:
        try:verify(broken,folder/'session.sqlite',expected,committed,True,p,ROOT/'adversarial/object-verifier')
        except Exception:results['missing-shared-object']='PASS_REJECTED'
        else:raise ValueError('CORRUPT_OBJECT_ACCEPTED')
    finally:p.close()
    save('adversarial.json',results);return results


def byte_parity(a_dsn,b_dsn,asset):
    scope=TrustedScope('qa7:'+asset['name'],'qa7:actor');a=load_data(a_dsn,scope,asset,False);b=load_data(b_dsn,scope,asset,True);counts={}
    for table,pi,hi in [('commands',3,4),('events',2,3),('checkpoints',1,2)]:
        if len(a[table])!=len(b[table]):raise ValueError('BYTE_ROW_COUNT')
        total=0
        for left,right in zip(a[table],b[table]):
            if left[:pi]!=right[:pi] or left[hi]!=right[hi]:raise ValueError('BYTE_IDENTITY')
            _,raw=decode(left[pi],left[hi],None);_,actual=decode(right[pi],right[hi],b['objects'])
            if raw!=actual:raise ValueError('BYTE_PAYLOAD')
            total+=len(raw)
        counts[table]=dict(rows=len(a[table]),bytesCompared=total)
    return counts


def main():
    guard()
    if shutil.disk_usage(ROOT).free<RESERVE+BUDGET:raise ValueError('PREFLIGHT_HEADROOM')
    save('PLAN.json',dict(format='RIKSORA-QA-INTEGRATED-1',baselineCommit='7875628490e3c44f50c5f940bf60dc63f18a5b7d',limits=dict(newArtifactBytes=BUDGET,cpu='1 equivalent TOTAL across PostgreSQL and workers',RAMBytes=1073741824,executionSeconds=900,diskReserve=RESERVE),lanes=['C1 actual XAU 2222 groups, ADVANCE only; no financial admission promoted','320 authored ticks / 512 commands / 128 retained orders and rejection of 129'],maxWorkers=2,estimatedPeakNewArtifactsBytes=350*1024**2,protected='H1/H2/H3 and old evidence never modified',contracts='unchanged; versioned QA adapters only'))
    if (SOURCE/'postmaster.pid').exists():raise ValueError('SOURCE_QA_ACTIVE')
    status=subprocess.check_output([str(BIN/'pg_controldata'),str(SOURCE)],text=True)
    if 'Database cluster state:               shut down' not in status:raise ValueError('SOURCE_QA_NOT_CLEAN')
    all_assets=assets();guard();data=ROOT/'pgdata';shutil.copytree(SOURCE,data,copy_function=shutil.copy2);sock=Path('/tmp/rx7-main');sock.mkdir(mode=0o700)
    ci=conninfo_to_dict(json.loads((E/'annual-xau2024-20261030/private-connection.json').read_text())['database']);ci.update(host=str(sock),port='55940');admin=make_conninfo(**ci)
    subprocess.run([str(BIN/'pg_ctl'),'-D',str(data),'-l',str(ROOT/'postgres.log'),'-o',f"-c listen_addresses='' -k {sock} -p 55940 -c shared_buffers=32MB -c max_connections=30 -c unix_socket_permissions=0700",'-w','start'],check=True,capture_output=True,text=True,timeout=60)
    try:
        results=[]
        for asset in all_assets:
            pair=[];dsns=[]
            for candidate in (False,True):
                dsn=create_session_db(admin,'qa7_'+('real' if asset['cycles']==0 else 'financial')+('_c' if candidate else '_b'),candidate);dsns.append(dsn)
                codes=run_children([(arm_worker,(dsn,asset,candidate))],650)
                if codes!=[0]:raise ValueError('INTEGRATED_ARM_FAILURE:'+asset['name']+str(candidate))
                pair.append(json.loads((ROOT/(asset['name']+('-candidate' if candidate else '-baseline'))/'metrics.json').read_text()))
            for key in ('commands','groups','ticks','balance','orders','TP','SL','checkpoint','stateHash','receiptStreamHash','groupHash'):
                if pair[0]['independentVerification'][key]!=pair[1]['independentVerification'][key]:raise ValueError('INTEGRATED_PARITY:'+key)
            checked=byte_parity(dsns[0],dsns[1],asset)
            results.append(dict(lane=asset['name'],baseline=pair[0],candidate=pair[1],exactByteParity=checked,
                                sessionSavingPercent=100*(pair[0]['persistent']['sessionAllocatedBytes']-pair[1]['persistent']['sessionAllocatedBytes'])/pair[0]['persistent']['sessionAllocatedBytes']))
            save('progress.json',dict(completedLanes=[r['lane'] for r in results],results=results));guard()
        faults,last=crash_tests(admin,all_assets[1]);attacks=adversarial(all_assets[1],last);multi=multi_tests(admin,all_assets[1])
        for asset in all_assets:
            for path,before in asset.get('pinnedFiles',{}).items():
                if stamp(Path(path))!=before:raise ValueError('C1_ARTIFACT_CHANGED')
        report=dict(status='PASS_BOUNDED_INTEGRATED_QA',results=results,crashRecovery=faults,adversarial=attacks,multiWorker=multi,
                    production='NOT_TOUCHED',H1H2H3='NOT_ACCESSED',authorities='42.17/42.19 UNCHANGED',annualReplay='NOT_RUN',
                    realXAUFinancialAdmission='NOT_GRANTED; real lane is replay only; actual native fills tested on authored QA ticks',
                    limitations=['range/codec adapter is QA-only; no production format or approved contract amendment','per-Session Linux file lock serializes same-Session workers; no thread/distributed qualification','candidate legacy engine logs and verifier logs are rebuildable scratch retained as QA evidence','canonical parent retained locally; projection is additional host storage, not deleted-parent savings','full 2024 compact serving export and annual Session remain untested','128 retained orders enforced, not raised; commands beyond boundary refused','CPU/million ticks is small-sample normalization including persistence; no million-tick benchmark or user capacity certification'],
                    resources=dict(wallSeconds=time.monotonic()-START,cgroup=cg(),newArtifactAllocatedBytes=allocated(ROOT),budgetBytes=BUDGET,freeDiskBytes=shutil.disk_usage(ROOT).free,reserveBytes=RESERVE))
        save('report.json',report);print(json.dumps(dict(status=report['status'],storage=[dict(lane=r['lane'],baseline=r['baseline']['persistent']['sessionAllocatedBytes'],candidate=r['candidate']['persistent']['sessionAllocatedBytes'],savingPercent=r['sessionSavingPercent']) for r in results],resources=report['resources']),sort_keys=True),flush=True)
    finally:
        subprocess.run([str(BIN/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'],check=True,capture_output=True,text=True,timeout=60);sock.rmdir()
    guard()


if __name__=='__main__':
    try:main()
    except BaseException as error:
        save('partial-'+str(time.time_ns())+'.json',dict(status='STOP_PARTIAL',error=type(error).__name__+':'+str(error)[:500],wallSeconds=time.monotonic()-START,cgroup=cg(),artifacts=allocated(ROOT)))
        raise
