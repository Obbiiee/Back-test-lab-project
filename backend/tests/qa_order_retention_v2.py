"""Isolated QA qualification for the versioned 512-order retention policy.

Uses the existing observed financial engine and private PostgreSQL adapter. The
fixture orders are authored QA LIMIT orders cancelled at the opening quote;
financial fills are qualified separately by qa_historical_day_v2.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

from contracts.canonical import canonical_bytes, content_hash
from execution.observed_kernel import QA_ORDER_RETENTION_V2, validate_state
from execution.observed_postgres import ObservedExecutionStore, read_snapshot
from execution.observed_profile import ObservedExecutionProfile
from infrastructure.database import connect
from tests.qa_historical_day_v2 import allocated, resource_sample

MAX_RAM=1024*1024*1024
MAX_ARTIFACT=2*1024*1024*1024
MIN_FREE=30*1024*1024*1024
MAX_WALL=3600


def command(sid,cid,rev,kind,payload=None):
    return dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=sid,
                commandId=cid,expectedRevision=rev,kind=kind,payload=payload or {})


def write_json(path,value):
    path=Path(path);raw=json.dumps(value,sort_keys=True,separators=(',',':'))+'\n'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:f.write(raw);f.flush();os.fsync(f.fileno())


def check_budget(root,cluster,started):
    if shutil.disk_usage(root).free<MIN_FREE:raise RuntimeError('RESOURCE_STOP_DISK_RESERVE_30_GIB')
    if allocated(root)>MAX_ARTIFACT:raise RuntimeError('RESOURCE_STOP_QA_ARTIFACT_2_GIB')
    cpu,ram,*_=resource_sample(cluster)
    if ram>MAX_RAM:raise RuntimeError('RESOURCE_STOP_RAM_1_GIB')
    if time.monotonic()-started>MAX_WALL:raise RuntimeError('RESOURCE_STOP_WALL_3600S')
    return cpu,ram,allocated(root)


def _check_policy(data,root):
    policy=data['orderRetentionPolicy']
    raw=canonical_bytes(policy)
    if hashlib.sha256(raw).hexdigest()!=data['orderRetentionPolicySha256']:
        raise RuntimeError('ORDER_RETENTION_POLICY_HASH_MISMATCH')
    expected=(Path(root)/'order-retention-policy.json').read_bytes().rstrip(b'\n')
    if raw!=expected or policy!=QA_ORDER_RETENTION_V2:
        raise RuntimeError('ORDER_RETENTION_POLICY_NOT_PINNED')
    return policy


def _independent_history(dsn,scope,sid,policy,expected_orders):
    store=ObservedExecutionStore(dsn,order_retention_policy=policy)
    view=store.inspect(scope,sid,maximum=64);state=view['state'];validate_state(state,order_retention_policy=policy)
    with connect(dsn) as db:
        seed=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',
                        (scope.workspace_id,sid)).fetchone()
        commands=db.execute('SELECT command_id,revision,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                            (scope.workspace_id,sid)).fetchall()
        event_rows=db.execute('SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',
                              (scope.workspace_id,sid)).fetchall()
        db_bytes=int(db.execute('SELECT pg_database_size(current_database())').fetchone()[0])
        relation_bytes={name:int(size) for name,size in db.execute(
            "SELECT relname,pg_total_relation_size(oid) FROM pg_class WHERE relnamespace='btl'::regnamespace AND relkind IN ('r','i') ORDER BY relname")}
        payload_bytes=db.execute('SELECT octet_length(payload) FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',
                                 (scope.workspace_id,sid)).fetchone()[0]
    snapshot=read_snapshot(*seed,order_retention_policy=policy);previous=snapshot['state']['eventHash']
    events=[]
    for sequence,(raw,sha) in enumerate(event_rows):
        from execution.postgres import unpack
        event=unpack(raw,sha)
        if event['sequence']!=sequence or event['previousHash']!=previous:
            raise RuntimeError('INDEPENDENT_EVENT_ORDER_OR_CHAIN_MISMATCH')
        if event['eventId']!=content_hash({k:v for k,v in event.items() if k!='eventId'}):
            raise RuntimeError('INDEPENDENT_EVENT_HASH_MISMATCH')
        previous=event['eventId'];events.append(event)
    if previous!=state['eventHash'] or len(events)!=state['nextEventIndex']:
        raise RuntimeError('INDEPENDENT_EVENT_HEAD_MISMATCH')
    accepted={e['orderId'] for e in events if e['kind']=='ORDER_ACCEPTED'}
    cancelled={e['orderId'] for e in events if e['kind']=='ORDER_CANCELLED'}
    if accepted!=set(state['orders']) or cancelled!=accepted or len(accepted)!=expected_orders:
        raise RuntimeError('INDEPENDENT_ORDER_HISTORY_CARDINALITY_MISMATCH')
    if any(o['status']!='CANCELLED' for o in state['orders'].values()):
        raise RuntimeError('ORDER_HISTORY_NOT_RETAINED')
    if len(commands)!=state['revision'] or any(row[1]!=i+1 for i,row in enumerate(commands)):
        raise RuntimeError('DURABLE_COMMAND_LEDGER_MISMATCH')
    if any(row[3] is None or hashlib.sha256(bytes(row[3])).hexdigest()!=row[4] for row in commands):
        raise RuntimeError('COMMAND_RECEIPT_HASH_MISMATCH')
    return dict(status='PASS',orderCount=len(accepted),cancelledHistoryCount=len(cancelled),
        commandCount=len(commands),eventCount=len(events),eventChainHead=state['eventHash'],
        orderIdsHash=hashlib.sha256(canonical_bytes(dict(schemaVersion=1,
            artifact='BTL-QA-ORDER-ID-SET-1',orderIds=sorted(accepted)))).hexdigest(),
        balance=state['balance'],realizedGross=state['realizedGross'],
        statePayloadBytes=int(payload_bytes),postgresDatabaseBytes=db_bytes,relationBytes=relation_bytes)


def _worker(data,mode):
    root=Path(data['root']);policy=_check_policy(data,root)
    os.environ['BTL_TEST_DATABASE_URL']=data['dsn']
    profile=ObservedExecutionProfile.from_wire(data['profile'])
    from execution.observed_admission import AdmittedObservedSource
    from execution.observed_controller import ObservedExecutionController
    from application.models import TrustedScope
    source=AdmittedObservedSource(data['source'],profile,receipt_path=data['proof'],
        receipt_sha256=data['proofHash'],log_root=data['sourceLogRoot'])
    store=ObservedExecutionStore(data['dsn'],order_retention_policy=policy)
    scope=TrustedScope(data['workspace'],data['actor']);controller=ObservedExecutionController(
        store,lambda _:source,order_retention_policy=policy)
    started=time.monotonic();state=store.inspect(scope,data['session'])['state']
    next_ns=int(state['throughNs'])+int(data['clockStepNs'])
    advance_id=('cold-advance:' if mode=='crash' else 'cold-verify-advance:')+str(data['targetCount'])
    advance=command(data['session'],advance_id,state['revision'],'ADVANCE',{'targetNs':str(next_ns)})
    controller.apply(scope,advance)
    if mode=='crash':
        n=int(data['targetCount']);opening=command(data['session'],f'retention-open:{n:04d}',
            store.inspect(scope,data['session'])['state']['revision'],'OPEN',data['orderPayload'])
        opened=controller.apply(scope,opening);cancel=command(data['session'],f'retention-cancel:{n:04d}',
            opened['state']['revision'],'CANCEL',{'orderId':opening['commandId']})
        t=time.monotonic();controller.apply(scope,cancel);cancel_wall=time.monotonic()-t
        cpu,ram=resource_sample(root/'postgres')[:2]
        write_json(root/f'crash-boundary-{n}.json',dict(schemaVersion=1,artifact='BTL-QA-ORDER-CRASH-BOUNDARY-1',
            orderCount=n,command=cancel,coldResumeWallSeconds=round(time.monotonic()-started,6),
            cancelCommitWallSeconds=round(cancel_wall,6),cpuSeconds=round(cpu,3),ramBytes=ram,
            artifactBytes=allocated(root),pid=os.getpid(),killSignal='SIGKILL'))
        os.kill(os.getpid(),signal.SIGKILL)
    result=_independent_history(data['dsn'],scope,data['session'],policy,int(data['targetCount']))
    state=store.inspect(scope,data['session'])['state']
    if len(state['orders'])!=int(data['targetCount']):raise RuntimeError('COLD_RESUME_ORDER_COUNT_MISMATCH')
    # A fresh process resumes the immutable tick timeline as well as the SQL tip.
    target=int(state['throughNs'])+int(data['clockStepNs'])
    controller.apply(scope,command(data['session'],f'cold-verify:{data["targetCount"]}',state['revision'],
                                    'ADVANCE',{'targetNs':str(target)}))
    result['coldResumeWallSeconds']=round(time.monotonic()-started,6)
    final_state=store.inspect(scope,data['session'])['state']
    if len(final_state['orders'])!=int(data['targetCount']):raise RuntimeError('POST_RESUME_HISTORY_LOSS')
    result['afterColdResumeRevision']=final_state['revision']
    result['afterColdResumeEventHead']=final_state['eventHash']
    write_json(root/f'verification-{data["targetCount"]}.json',result)
    source.close()
    return result


def _run_worker(repository,root,data,mode):
    env=dict(os.environ,BTL_QA_ORDER_WORKER=json.dumps(data,sort_keys=True),BTL_QA_ORDER_WORKER_MODE=mode,
             PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(repository/'backend'))
    proc=subprocess.run([sys.executable,'-B','-m','tests.qa_order_retention_v2','--worker'],
        cwd=repository,env=env,capture_output=True,text=True,timeout=MAX_WALL)
    if mode=='crash':
        if proc.returncode!=-signal.SIGKILL:raise RuntimeError('SIGKILL_NOT_REACHED:'+proc.stderr[-1000:])
        return proc
    if proc.returncode!=0:raise RuntimeError('COLD_VERIFY_WORKER_FAILED:'+proc.stderr[-2000:])
    return json.loads((Path(root)/f'verification-{data["targetCount"]}.json').read_text())


def main():
    root_text=os.environ.get('BTL_QA_ORDER_RETENTION_ROOT')
    if not root_text:raise RuntimeError('SET_BTL_QA_ORDER_RETENTION_ROOT_TO_NEW_EMPTY_PATH')
    root=Path(root_text)
    if root.exists():raise RuntimeError('QA_OUTPUT_PATH_MUST_NOT_EXIST')
    if shutil.disk_usage(root.parent if root.parent.exists() else Path('/')).free<MIN_FREE:
        raise RuntimeError('PREFLIGHT_DISK_RESERVE_BELOW_30_GIB')
    root.mkdir(mode=0o700,parents=False);os.chmod(root,0o700)
    if hasattr(os,'sched_getaffinity'):
        allowed=os.sched_getaffinity(0)
        if allowed:os.sched_setaffinity(0,{min(allowed)})
    policy=QA_ORDER_RETENTION_V2;policy_raw=canonical_bytes(policy)
    write_json(root/'order-retention-policy.json',policy)
    policy_sha=hashlib.sha256(policy_raw).hexdigest()
    run_id='orders512-'+uuid.uuid4().hex[:12]
    started=time.monotonic();initial_free=shutil.disk_usage(root).free
    from deploy.vps.tests.run_private_pg import private_postgres
    with private_postgres(keep=True,root_dir=root/'postgres') as (repository,environment):
        os.environ.update(environment);dsn=environment['BTL_TEST_DATABASE_URL']
        from tests.test_observed_postgres import ObservedPostgresTests
        from execution.observed_controller import ObservedExecutionController
        from execution.observed_postgres import ObservedExecutionStore
        from application.models import TrustedScope
        fixture=ObservedPostgresTests('runTest');fixture.setUpClass();fixture.setUp()
        try:
            sid='session:qa-retention:'+run_id;workspace='observedqa:retention:'+run_id;actor='fixture:retention-v2'
            scope=TrustedScope(workspace,actor)
            store=ObservedExecutionStore(dsn,order_retention_policy=policy)
            controller=ObservedExecutionController(store,lambda _:fixture.source,order_retention_policy=policy)
            controller.create(scope,sid,fixture.fx.profile,fixture.fx.policy,period='1970-01',balance='10000')
            opened=controller.apply(scope,command(sid,'retention-opening-quote',0,'ADVANCE',{'targetNs':'0'}))
            basis=opened['state']['quoteBasis']
            if basis is None:raise RuntimeError('OPENING_QUOTE_NOT_REVEALED')
            from decimal import Decimal
            ask=Decimal(basis['ask']);entry=ask-Decimal('0.1')
            payload=dict(side='LONG',orderType='LIMIT',workflow='PLANNED',entry=format(entry,'f'),quantity='0.01',
                sl=format(entry-Decimal('0.1'),'f'),tp=format(entry+Decimal('0.1'),'f'),riskPercent='1',observations=[])
            common=dict(root=str(root),dsn=dsn,profile=fixture.fx.profile.wire,source=str(fixture.folder),
                proof=str(fixture.proof),proofHash=fixture.proof_hash,sourceLogRoot=str(fixture.root/'controller-logs'),
                workspace=workspace,actor=actor,session=sid,orderRetentionPolicy=policy,
                orderRetentionPolicySha256=policy_sha,orderPayload=payload)
            samples=[];latencies=[];progress_path=root/'progress.jsonl'
            for target_count in (129,256,512):
                current=len(store.inspect(scope,sid)['state']['orders'])
                for n in range(current+1,target_count):
                    state=store.inspect(scope,sid)['state'];t=time.monotonic()
                    op=command(sid,f'retention-open:{n:04d}',state['revision'],
                               'OPEN',payload);opened=controller.apply(scope,op)
                    cp=command(sid,f'retention-cancel:{n:04d}',opened['state']['revision'],
                               'CANCEL',{'orderId':op['commandId']});controller.apply(scope,cp)
                    latencies.append(time.monotonic()-t)
                    if n%16==0:
                        cpu,ram,artifacts=check_budget(root,root/'postgres',started)
                        sample=dict(orderCount=n,elapsedSeconds=round(time.monotonic()-started,3),cpuSeconds=round(cpu,3),
                            ramBytes=ram,artifactBytes=artifacts,dbBytes=_independent_history(dsn,scope,sid,policy,n)['postgresDatabaseBytes'])
                        samples.append(sample);write_json(progress_path,dict(status='RUNNING',**sample))
                data=dict(common,targetCount=target_count,clockStepNs='1')
                before=store.inspect(scope,sid)['state'];cancel_id=f'retention-cancel:{target_count:04d}'
                crash=_run_worker(repository,root,data,'crash')
                marker=json.loads((root/f'crash-boundary-{target_count}.json').read_text())
                retry=controller.apply(scope,marker['command'])
                after=store.inspect(scope,sid)['state']
                if len(after['orders'])!=target_count or after['revision']!=before['revision']+3:
                    raise RuntimeError('POST_CRASH_RETRY_NOT_IDEMPOTENT')
                data['clockStepNs']='1'
                verify=_run_worker(repository,root,data,'verify')
                measure=_independent_history(dsn,scope,sid,policy,target_count)
                measure.update(coldResumeWallSeconds=verify['coldResumeWallSeconds'],
                    postCrashRetryStatus='PASS',processExit=-signal.SIGKILL,
                    crashWorkerColdAdvanceAndOrderCommitSeconds=marker['coldResumeWallSeconds'])
                samples.append(dict(orderCount=target_count,elapsedSeconds=round(time.monotonic()-started,3),
                    cpuSeconds=round(resource_sample(root/'postgres')[0],3),ramBytes=resource_sample(root/'postgres')[1],
                    artifactBytes=allocated(root),dbBytes=measure['postgresDatabaseBytes']))
                write_json(root/f'checkpoint-{target_count}.json',measure)
                check_budget(root,root/'postgres',started)
            active_sid='session:qa-retention-active:'+run_id
            active_scope=TrustedScope(workspace+':active',actor)
            controller.create(active_scope,active_sid,fixture.fx.profile,fixture.fx.policy,period='1970-01',balance='10000')
            active_state=controller.apply(active_scope,command(active_sid,'active-opening-quote',0,'ADVANCE',{'targetNs':'0'}))['state']
            for n in range(1,129):
                op=command(active_sid,f'active-order:{n:04d}',active_state['revision'],'OPEN',payload)
                active_state=controller.apply(active_scope,op)['state']
            before_hash=content_hash(active_state)
            rejected=command(active_sid,'active-order:0129',active_state['revision'],'OPEN',payload)
            try:controller.apply(active_scope,rejected)
            except ValueError as exc:
                if 'REFUSED_ACTIVE_ORDER_LIMIT' not in str(exc):raise
            else:raise RuntimeError('ACTIVE_ORDER_CAP_NOT_ENFORCED')
            active_after=store.inspect(active_scope,active_sid)['state']
            if len(active_after['orders'])!=128 or content_hash(active_after)!=before_hash:
                raise RuntimeError('ACTIVE_ORDER_CAP_MUTATED_SESSION')
            with connect(dsn) as db:
                if db.execute('SELECT 1 FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s',
                    (active_scope.workspace_id,active_sid,'active-order:0129')).fetchone() is not None:
                    raise RuntimeError('REFUSED_ACTIVE_ORDER_COMMAND_PERSISTED')
            command_latencies=sorted(latencies)
            p95=command_latencies[min(len(command_latencies)-1,int(0.95*len(command_latencies)))]
            report=dict(status='PASS',classification='ISOLATED_QA_ORDER_RETENTION_V2',policy=policy,
                policySha256=policy_sha,sessionId=sid,sourceFixture='AUTHORED_QA_NOT_MARKET_DATA',
                thresholds=[json.loads((root/f'checkpoint-{n}.json').read_text()) for n in (129,256,512)],
                commandLatencySeconds=dict(samples=len(latencies),median=sorted(latencies)[len(latencies)//2],p95=p95),
                measurements=dict(elapsedSeconds=round(time.monotonic()-started,3),cpuSeconds=round(resource_sample(root/'postgres')[0],3),
                    peakRamBytes=max(s['ramBytes'] for s in samples),peakArtifactBytes=allocated(root),
                    initialFreeBytes=initial_free,finalFreeBytes=shutil.disk_usage(root).free,
                    resourceLimits=dict(vCPUEquivalent=1,ramBytes=MAX_RAM,artifactBytes=MAX_ARTIFACT,wallSeconds=MAX_WALL,diskReserveBytes=MIN_FREE)),
                activeOrderBoundary=dict(status='PASS',maximumActiveOrders=128,rejectedOrder=129,
                    stateAndCommandLedgerUnchanged=True),
                guarantee=dict(v1DefaultLimit=128,v2MaximumCumulativeOrders=512,v2MaximumLiveOrders=128,
                    allTerminalOrderRecordsRemainInStateAndEvents=True,noHistoryTruncation=True,
                    productionBehaviorChanged=False,financialKernelRulesChanged=False))
            write_json(root/'report.json',report);print(json.dumps(report,sort_keys=True))
        finally:
            fixture.tearDown()


def main_worker():
    data=json.loads(os.environ['BTL_QA_ORDER_WORKER'])
    mode=os.environ['BTL_QA_ORDER_WORKER_MODE']
    if mode=='crash':_worker(data,mode)
    else:_worker(data,mode)


if __name__=='__main__':
    if '--worker' in sys.argv:main_worker()
    else:main()
