"""Bounded explicit operator-run QA experiment. Never imported by application."""
import hashlib,json,multiprocessing,os,resource,shutil,signal,sqlite3,statistics,subprocess,sys,time,zlib
from pathlib import Path
from copy import deepcopy
from contextlib import contextmanager

ROOT=Path('/home/riksora/riksora-qa-evidence/session-storage-20261030/checkpoint5')
E=Path('/home/riksora/riksora-qa-evidence');REPO=Path('/tmp/riksora-beta-integration-current-20261028')
SOURCE_CLUSTER=Path('/tmp/riksora-exclusive-qa-8l28d6oy/data')
DATASET=E/'beta-checkpoints-20261025-jtbqjj1o/xau-binary-recovery-20261026/verified-serving-snapshot'
SNAP=E/'annual-storage-20261030/bounded-gates-v2/1h-snapshot.json'
LOG=E/'annual-storage-20261030/bounded-gates-v2/session-logs/a7e9fca27d74e6d071ba3ad4a5f1a5305e484c10c198314fae1ffa407927c7dd/timeline.sqlite'
BIN=Path('/usr/lib/postgresql/16/bin');START=time.monotonic();BUDGET=512*1024**2;RESERVE=30*1024**3
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
def save(name,obj):
    p=ROOT/name;raw=json.dumps(obj,sort_keys=True,indent=2).encode();tmp=p.with_name(p.name+'.pending')
    with tmp.open('wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    os.replace(tmp,p);guard()
def fingerprint(p):
    s=p.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_mode]
def cgroup():
    rel=next(s for s in Path('/proc/self/cgroup').read_text().splitlines() if s.startswith('0::')).split('::')[1]
    p=Path('/sys/fs/cgroup')/rel.lstrip('/');cpu=dict(s.split() for s in (p/'cpu.stat').read_text().splitlines())
    return dict(cpuUsec=int(cpu['usage_usec']),peakMemoryBytes=int((p/'memory.peak').read_text()),cpuMax=(p/'cpu.max').read_text().strip(),memoryMax=(p/'memory.max').read_text().strip())
def timing(v):return dict(median=statistics.median(v),p95=sorted(v)[int(.95*(len(v)-1))],maximum=max(v),samples=len(v))
def filesizes(folder):
    return {p.name:dict(bytes=p.stat().st_size,allocated=p.stat().st_blocks*512) for p in folder.glob('*.sqlite*')}

def imports():
    global psycopg,sql,canonical_bytes,content_hash,Scope,Store,apply,Provider,Timeline,PreparedRanges,atomic_reference,install_commit_table,refs,verify,validate_envelopes,consumer,source_groups
    import psycopg
    from psycopg import sql
    from contracts.canonical import canonical_bytes,content_hash
    from application.models import TrustedScope as Scope
    from execution.observed_postgres import ObservedExecutionStore as Store
    from execution.observed_kernel import apply
    from ticks.storage_v2 import DiskTickProvider as Provider
    from ticks.timeline_v2 import IndexedTickTimeline as Timeline
    from tests.qa_range_prototype5 import PreparedRanges,atomic_reference,install_commit_table,refs
    from tests.qa_range_verifier5 import verify,validate_envelopes,consumer,source_groups

def dataset():return Provider(DATASET,SEED['controller']['cursor']['datasetVersion'],read_only=True)
def position_records(timeline,before,after):
    if before['positionLogHash']==after['positionLogHash']:return []
    raw=timeline._IndexedTickTimeline__read_block(after['positionLogHash'])
    return json.loads(raw)['records']

def one(dsn,scope,folder,command,prototype=False,fault=None):
    store=Store(dsn);before,prior=store.prepare(scope,command)
    if prior is not None:return prior,True
    provider=dataset();t=Timeline.resume(provider,before['controller'],log_folder=folder/'engine',log_codec='zlib-1')
    ranges=None
    try:
        frame=t.advance_through(command['payload']['targetNs'],t.cursor);cp=t.checkpoint()
        after,events=apply(before['state'],command,reveal=frame,checkpoint=cp)
        replay=dict(throughNs=frame['throughNs'],exhaustedThroughBoundary=frame['exhaustedThroughBoundary'])
        if prototype:
            bind=dict(BINDING,workspace=scope.workspace_id);ranges=PreparedRanges(folder/'ranges.sqlite',bind)
            old=refs(dsn,scope,command['sessionId']);prev=old[-1][2] if old else None
            digest=ranges.prepare(command,before['controller'],cp,position_records(t,before['controller'],cp),prev)
            if fault:fault('after_prepare')
            with atomic_reference(scope,command,digest,fault):result=store.commit(scope,command,before,after,cp,events,replay)
            if fault:fault('after_sql_commit')
            ranges.publish(digest)
            if fault:fault('after_finalize')
        else:result=store.commit(scope,command,before,after,cp,events,replay)
        return result,False
    finally:
        if ranges:ranges.close()
        t.close();provider.close()

def pg_measure(dsn,prototype):
    with psycopg.connect(dsn) as db:
        rel=db.execute("select c.relname,pg_table_size(c.oid),pg_indexes_size(c.oid),pg_total_relation_size(c.oid) from pg_class c join pg_namespace n on n.oid=c.relnamespace where (n.nspname='btl' and c.relname in ('tick_sessions','tick_commands','tick_events','tick_checkpoints')) or (n.nspname='public' and c.relname='qa5_commits') order by c.relname").fetchall()
        return dict(relations=[list(r) for r in rel],sessionAllocatedBytes=sum(r[3] for r in rel),databaseBytes=db.execute('select pg_database_size(current_database())').fetchone()[0])
def create_database(admin,name,prototype):
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    ci=conninfo_to_dict(admin)
    with psycopg.connect(admin,autocommit=True) as db:db.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(name)))
    ci['dbname']=name;dsn=make_conninfo(**ci)
    from infrastructure.database import migrate
    migrate(dsn)
    if prototype:install_commit_table(dsn)
    return dsn

def arm(dsn,prototype):
    folder=ROOT/('prototype' if prototype else 'baseline');folder.mkdir(mode=0o700,exist_ok=True)
    if not os.environ.get('QA5_CONTINUE'):Store(dsn).create(SCOPE,SEED['state'],SEED['controller'])
    receipts=[];lat=[];wall=time.monotonic();cpu=time.process_time()
    for i,command in enumerate(COMMANDS):
        t=time.monotonic();receipt,prior=one(dsn,SCOPE,folder,command,prototype);lat.append(time.monotonic()-t)
        if prior:raise ValueError('UNEXPECTED_RETRY')
        if i<len(ORIGINAL_RECEIPTS) and canonical_bytes(receipt)!=ORIGINAL_RECEIPTS[i]:raise ValueError('ORIGINAL_RECEIPT_MISMATCH')
        receipts.append(receipt);guard()
    cp=Store(dsn).prepare(SCOPE,dict(COMMANDS[-1],commandId='inspect-unused',expectedRevision=len(COMMANDS)))[0]['controller']
    provider=dataset();reads=[]
    if prototype:
        rng=PreparedRanges(folder/'ranges.sqlite',BINDING);rows=rng.rows();committed=refs(dsn,SCOPE,SEED['state']['sessionId']);rng.close()
        t=time.monotonic();verified=verify(BINDING,rows,committed,COMMANDS,SEED,receipts,provider,folder/'verifier-temp')
        cold=time.monotonic()-t;view=consumer(provider,SEED['controller']['cursor']['sessionStartNs'],verified['checkpoint'])
        save('prototype-verification.json',verified)
    else:
        t=time.monotonic();timeline=Timeline.resume(provider,cp,log_folder=folder/'engine');cold=time.monotonic()-t;view=timeline.consumer()
    stream=hashlib.sha256()
    for off in range(0,2222,64):
        t=time.monotonic();batch=view.read_revealed(str(off),min(64,2222-off));reads.append(time.monotonic()-t)
        for group in batch:stream.update(json.dumps(group,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
        guard()
    if view.read_revealed('2222',1)!=[]:raise ValueError('FUTURE_LEAK')
    try:view.read_revealed('2223',1)
    except ValueError:pass
    else:raise ValueError('FUTURE_LEAK')
    if any(hasattr(view,key) for key in ('provider','checkpoint','locate_v2','eof','index')):raise ValueError('CAPABILITY_LEAK')
    if not prototype:timeline.close()
    provider.close()
    measure=pg_measure(dsn,prototype)
    persistent=(folder/'ranges.sqlite') if prototype else (folder/'engine/timeline.sqlite')
    metrics=dict(prototype=prototype,writeLatencySeconds=timing(lat),readLatencySeconds=timing(reads),coldResumeSeconds=cold,
                 wallSeconds=time.monotonic()-wall,cpuSeconds=time.process_time()-cpu,peakRSSKiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 sqliteAllocatedBytes=persistent.stat().st_blocks*512,sqliteBytes=persistent.stat().st_size,
                 postgres=measure,persistentSessionAllocatedBytes=persistent.stat().st_blocks*512+measure['sessionAllocatedBytes'],
                 readGroupHash=stream.hexdigest(),scratchEngineAllocatedBytes=allocated(folder/'engine') if prototype else 0,
                 scratchVerifierAllocatedBytes=allocated(folder/'verifier-temp') if prototype else 0)
    save(('prototype' if prototype else 'baseline')+'-metrics.json',metrics)
    return receipts,metrics

def adversarial(dsn,receipts):
    folder=ROOT/'prototype';r=PreparedRanges(folder/'ranges.sqlite',BINDING);physical=r.rows();r.close();committed=refs(dsn,SCOPE,SEED['state']['sessionId']);tests={}
    cases={'missing':physical[1:],'duplicated':physical+[physical[0]],'corrupted':[(physical[0][0],physical[0][1],b'corrupt')]+physical[1:]}
    for name,rows in cases.items():
        try:validate_envelopes(BINDING,rows,committed,COMMANDS)
        except Exception:tests[name]='PASS_REJECTED'
        else:raise ValueError('ADVERSARY_ACCEPTED:'+name)
    for name,ref in [('reordered',[committed[1],committed[0]]+committed[2:]),('duplicated_commit',committed+[committed[-1]]),('missing_commit',committed[:-1])]:
        try:validate_envelopes(BINDING,physical,ref,COMMANDS)
        except ValueError:tests[name]='PASS_REJECTED'
        else:raise ValueError('ADVERSARY_ACCEPTED:'+name)
    try:validate_envelopes(dict(BINDING,datasetVersion='f'*64),physical,committed,COMMANDS)
    except ValueError:tests['substituted_dataset']='PASS_REJECTED'
    else:raise ValueError('SUBSTITUTED_DATASET_ACCEPTED')
    # Malicious writer constructs an internally consistent chain around a false source commitment.
    changed=[];newrefs=[];previous=None
    for i,(digest,seq,body) in enumerate(physical):
        obj=json.loads(zlib.decompress(body));obj['previousHash']=previous
        if i==0:obj['positionCommitment']='f'*64
        raw=canonical_bytes(obj);previous=hashlib.sha256(raw).hexdigest();changed.append((previous,seq,zlib.compress(raw)));newrefs.append((seq,obj['commandId'],previous))
    p=dataset()
    try:
        try:verify(BINDING,changed,newrefs,COMMANDS,SEED,receipts,p,ROOT/'adversarial-verifier-temp')
        except ValueError:tests['self_consistent_false_source_proof']='PASS_REJECTED'
        else:raise ValueError('FORGED_SOURCE_PROOF_ACCEPTED')
    finally:p.close()
    # Unreferenced future prepare never increases the published prefix.
    extra=deepcopy(json.loads(zlib.decompress(physical[-1][2])));extra['seq']=38;extra['groupEnd']='999999';raw=canonical_bytes(extra)
    validate_envelopes(BINDING,physical+[(hashlib.sha256(raw).hexdigest(),38,zlib.compress(raw))],committed,COMMANDS)
    tests['uncommitted_future_tail']='PASS_IGNORED'
    save('adversarial.json',tests);return tests

def crash_worker(dsn,scope,folder,phase):
    def fault(point):
        if point==phase:os.kill(os.getpid(),signal.SIGKILL)
    one(dsn,scope,folder,COMMANDS[0],True,fault)

def crash_tests(dsn):
    results={}
    for phase in ('after_prepare','before_sql_commit','after_sql_commit','after_finalize'):
        folder=ROOT/('crash-'+phase);folder.mkdir(mode=0o700);scope=Scope('qa5:'+phase,'qa5:actor')
        Store(dsn).create(scope,SEED['state'],SEED['controller'])
        child=multiprocessing.get_context('fork').Process(target=crash_worker,args=(dsn,scope,folder,phase));child.start();child.join(60)
        if child.is_alive():child.kill();child.join();raise ValueError('CRASH_WORKER_TIMEOUT')
        if child.exitcode!=-signal.SIGKILL:raise ValueError('CRASH_NOT_REACHED:'+phase)
        committed_before=refs(dsn,scope,SEED['state']['sessionId']);expected=phase in ('after_sql_commit','after_finalize')
        if bool(committed_before)!=expected:raise ValueError('SQL_ATOMICITY')
        rng=PreparedRanges(folder/'ranges.sqlite',dict(BINDING,workspace=scope.workspace_id))
        validate_envelopes(dict(BINDING,workspace=scope.workspace_id),rng.rows(),committed_before,[COMMANDS[0]] if expected else [])
        if expected:rng.publish(committed_before[-1][2])
        rng.close()
        receipt,was_prior=one(dsn,scope,folder,COMMANDS[0],True)
        if was_prior!=expected or canonical_bytes(receipt)!=ORIGINAL_RECEIPTS[0]:raise ValueError('CRASH_RETRY_PARITY')
        again,was_prior=one(dsn,scope,folder,COMMANDS[0],True)
        if not was_prior or again!=receipt:raise ValueError('IDEMPOTENCY')
        with psycopg.connect(dsn) as db:
            count=db.execute('SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s',(scope.workspace_id,)).fetchone()[0]
        if count!=1 or len(refs(dsn,scope,SEED['state']['sessionId']))!=1:raise ValueError('DUPLICATE_DURABLE_COMMAND')
        conflict=deepcopy(COMMANDS[0]);conflict['payload']['targetNs']=str(int(conflict['payload']['targetNs'])+1)
        try:Store(dsn).prepare(scope,conflict)
        except ValueError:pass
        else:raise ValueError('CONFLICT_ACCEPTED')
        results[phase]=dict(status='PASS',exitCode=child.exitcode,committedBeforeRetry=expected,exactReceipt=True,commandCount=count)
        guard()
    save('crash-retry.json',results);return results

def main():
    global SEED,BINDING,SCOPE,COMMANDS,ORIGINAL_RECEIPTS
    imports();guard();h1=fingerprint(DATASET/'archive.sqlite');source=fingerprint(LOG)
    if (SOURCE_CLUSTER/'postmaster.pid').exists():raise ValueError('SOURCE_CLUSTER_ACTIVE')
    state=subprocess.run([str(BIN/'pg_controldata'),str(SOURCE_CLUSTER)],capture_output=True,text=True,check=True).stdout
    if 'Database cluster state:               shut down' not in state:raise ValueError('SOURCE_CLUSTER_NOT_CLEAN')
    data=ROOT/'pgdata'
    if not os.environ.get('QA5_CONTINUE'):shutil.copytree(SOURCE_CLUSTER,data,copy_function=shutil.copy2)
    guard()
    sock=Path('/tmp/rx5-55740');sock.mkdir(mode=0o700)
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    ci=conninfo_to_dict(json.loads((E/'annual-xau2024-20261030/private-connection.json').read_text())['database']);ci.update(host=str(sock),port='55740');dsn=make_conninfo(**ci)
    subprocess.run([str(BIN/'pg_ctl'),'-D',str(data),'-l',str(ROOT/'postgres.log'),'-o',f"-c listen_addresses='' -k {sock} -p 55740 -c shared_buffers=32MB -c max_connections=30 -c unix_socket_permissions=0700",'-w','start'],check=True,capture_output=True,text=True,timeout=60)
    try:
        final=json.loads(SNAP.read_text());sid=final['state']['sessionId']
        with psycopg.connect(dsn) as db:
            workspace=db.execute('SELECT workspace_id FROM btl.tick_sessions WHERE session_id=%s',(sid,)).fetchone()[0]
            seed=db.execute('SELECT payload FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',(workspace,sid)).fetchone()[0]
            commandrows=db.execute('SELECT command_id,revision,command_hash,payload FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(workspace,sid)).fetchall()
        SEED=json.loads(bytes(seed));SCOPE=Scope(workspace,'qa5:actor');targets=[]
        with sqlite3.connect(LOG.resolve().as_uri()+'?mode=ro',uri=True) as db:
            tip=final['controller']['advanceLogHash']
            while tip:
                body=db.execute('SELECT body FROM blocks WHERE hash=?',(tip,)).fetchone()[0];obj=json.loads(zlib.decompress(body[len(b'BTL-TIMELINE-ZLIB-1\0'):]))
                targets.append(obj['records'][0]['targetNs']);tip=obj['previousHash']
        targets.reverse();COMMANDS=[];ORIGINAL_RECEIPTS=[]
        if len(commandrows)!=36 or len(targets)!=36:raise ValueError('QA_WORKLOAD_NOT_36')
        for (cid,revision,digest,payload),target in zip(commandrows,targets):
            cmd=dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=sid,commandId=cid,expectedRevision=revision-1,kind='ADVANCE',payload=dict(targetNs=target))
            if content_hash(cmd)!=digest:raise ValueError('ORIGINAL_COMMAND_NOT_RECONSTRUCTABLE')
            COMMANDS.append(cmd);ORIGINAL_RECEIPTS.append(bytes(payload))
        COMMANDS.append(dict(COMMANDS[-1],commandId='qa5:zero-reveal',expectedRevision=36,payload=dict(targetNs=targets[-1])))
        BINDING=dict(schemaVersion=1,format='RIKSORA-QA-RANGE-BINDING-1',sessionId=sid,workspace=workspace,datasetId=SEED['state']['datasetId'],datasetVersion=SEED['state']['datasetVersion'],timelineVersion=SEED['controller']['cursor']['timelineVersion'],engineVersion=SEED['state']['engineVersion'],profileHash=SEED['state']['profileHash'],methodHash=SEED['state']['policy']['definitionHash'],sessionStartNs=SEED['state']['startNs'])
        if os.environ.get('QA5_CONTINUE'):
            bc=dict(ci,dbname='qa5_baseline');pc=dict(ci,dbname='qa5_prototype');baseline_dsn=make_conninfo(**bc);prototype_dsn=make_conninfo(**pc)
            ma=json.loads((ROOT/'baseline-metrics.json').read_text())
            with psycopg.connect(baseline_dsn) as db:a=[json.loads(bytes(r[0])) for r in db.execute('SELECT payload FROM btl.tick_commands ORDER BY revision')]
        else:
            baseline_dsn=create_database(dsn,'qa5_baseline',False);prototype_dsn=create_database(dsn,'qa5_prototype',True);a,ma=arm(baseline_dsn,False)
        b,mb=arm(prototype_dsn,True)
        if len(a)!=len(b) or any(canonical_bytes(x)!=canonical_bytes(y) for x,y in zip(a,b)):raise ValueError('RECEIPT_PARITY')
        if ma['readGroupHash']!=mb['readGroupHash'] or ma['readGroupHash']!='caec2ffedfebc4f58d48a4b5dba235091d479a80636e91b8ceb2a1b99b49b9e2':raise ValueError('REVEAL_HASH_PARITY')
        attacks=adversarial(prototype_dsn,b);crashes=crash_tests(prototype_dsn)
        report=dict(status='PASS_BOUNDED_QA_PROTOTYPE',baseline=ma,prototype=mb,adversarial=attacks,crashRecovery=crashes,
                    originalReceiptParity=36,completeReceipts=37,groups=2222,zeroRevealAdvances=1,financialEvents='all existing engine events retained byte-exact; this workload contains no financial fills',
                    economicDecision='NO_GO_FOR_ANNUAL_500MB_CLAIM',contractDecision='EXPERIMENT ONLY; no 42.17/42.19 revision',
                    savingsPercent=100*(ma['persistentSessionAllocatedBytes']-mb['persistentSessionAllocatedBytes'])/ma['persistentSessionAllocatedBytes'],
                    gaps=['writer uses unchanged V2 engine logs as rebuildable scratch; no production range writer or cutover','full receipt/event/checkpoint SQL storage remains unchanged','full-prefix reconstruction required; no trusted checkpoint shortcut','independent verifier uses existing financial reducer/timeline plus separate source-position traversal; not a second engine','no annual group count or annual storage certification','main source workload has no trade fills; zero-reveal is an additional identical control in both arms'],
                    protection=dict(H1Before=h1,H1After=fingerprint(DATASET/'archive.sqlite'),sourceLogBefore=source,sourceLogAfter=fingerprint(LOG),H2H3='NOT_ACCESSED',production='NOT_ACCESSED'),
                    resources=dict(wallSeconds=time.monotonic()-START,cgroup=cgroup(),artifactAllocatedBytes=allocated(ROOT),diskAvailableBytes=shutil.disk_usage(ROOT).free,budgetBytes=BUDGET,reserveBytes=RESERVE))
        if h1!=fingerprint(DATASET/'archive.sqlite') or source!=fingerprint(LOG):raise ValueError('SOURCE_FINGERPRINT_CHANGED')
        save('report.json',report);print(json.dumps({k:report[k] for k in ('status','savingsPercent','economicDecision','resources')},sort_keys=True),flush=True)
    finally:
        subprocess.run([str(BIN/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'],check=True,capture_output=True,text=True,timeout=60);sock.rmdir()
    guard()

if __name__=='__main__':
    try:main()
    except BaseException as error:
        save('partial-report-'+str(time.time_ns())+'.json',dict(status='STOP_PARTIAL',error=type(error).__name__+':'+str(error)[:500],wallSeconds=time.monotonic()-START,artifacts=allocated(ROOT),resources=cgroup()))
        raise
