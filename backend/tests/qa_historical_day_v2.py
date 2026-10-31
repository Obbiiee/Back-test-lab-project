"""QA-only, one-UTC-day observed-tick financial simulation (no production wiring).

Run with a new BTL_HISTORICAL_QA_ROOT outside the repository. The isolated
PostgreSQL cluster and all generated logs/evidence stay under that directory.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

from contracts.canonical import canonical_bytes, content_hash
from contracts.models import MethodPolicy
from execution.observed_admission import AdmittedObservedSource
from execution.observed_controller import ObservedExecutionController
from execution.observed_kernel import MAX_ORDERS, QA_ORDER_RETENTION_V2, validate_state
from execution.observed_postgres import ObservedExecutionStore
from execution.observed_profile import ObservedExecutionProfile, historical_technical_profile
from infrastructure.database import connect, migrate
from ticks.storage_v2 import DiskTickProvider
from tests import qa_perf_instrumentation as PERF

DAY = '2024-01-02'
PERIOD = '2024-01'
S = 1_000_000_000
MAX_WALL = 3600.0
MAX_ARTIFACT = 512 * 1024 * 1024
MAX_RAM = 1024 * 1024 * 1024
MIN_FREE = 30 * 1024 * 1024 * 1024
PEAK_RAM = 0
PEAK_ARTIFACT = 0
SOURCE = Path('/home/riksora/riksora-qa-evidence/beta-checkpoints-20261025-jtbqjj1o/xau-binary-recovery-20261026/verified-serving-snapshot')
PROOF = Path('/home/riksora/riksora-qa-evidence/beta-checkpoints-20261025-jtbqjj1o/xau-binary-recovery-20261026/resumable-parity/final-report.json')
PROFILE_FIXTURE = Path(__file__).parent/'fixtures/observed_profile_vectors.json'
CONFIG_FIXTURE = Path(__file__).parent/'fixtures/historical_technical_simulation_qa.json'


def allocated(root):
    total = 0
    for base, dirs, files in os.walk(root):
        for name in files:
            try:
                total += (Path(base)/name).stat().st_blocks * 512
            except FileNotFoundError:
                pass
    return total


def _proc(pid):
    """Return parent pid, CPU seconds and current RSS for a Linux process."""
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        rest = raw[raw.rfind(')')+2:].split()
        ppid = int(rest[1]); ticks = int(rest[11])+int(rest[12])
        status = Path(f'/proc/{pid}/status').read_text()
        rss_kib = int(next(line.split()[1] for line in status.splitlines() if line.startswith('VmRSS:')))
        return ppid, ticks/os.sysconf('SC_CLK_TCK'), rss_kib*1024
    except (OSError, StopIteration, ValueError, IndexError):
        return None


def resource_sample(cluster_root):
    own_status = Path('/proc/self/status').read_text()
    own_rss = int(next(line.split()[1] for line in own_status.splitlines() if line.startswith('VmRSS:'))) * 1024
    own = resource.getrusage(resource.RUSAGE_SELF)
    child = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = own.ru_utime + own.ru_stime + child.ru_utime + child.ru_stime
    own_peak_rss = max(own_rss, own.ru_maxrss*1024)
    postgres_rss = 0
    postmaster_file = Path(cluster_root)/'data/postmaster.pid'
    if postmaster_file.exists():
        try: root_pid = int(postmaster_file.read_text().splitlines()[0])
        except (OSError, ValueError, IndexError): root_pid = None
        if root_pid:
            procs = {}
            for item in Path('/proc').iterdir():
                if item.name.isdigit():
                    stats = _proc(item.name)
                    if stats: procs[int(item.name)] = stats
            included = {root_pid}
            changed = True
            while changed:
                changed = False
                for pid, (ppid, _, _) in procs.items():
                    if ppid in included and pid not in included:
                        included.add(pid); changed = True
            for pid in included:
                if pid in procs:
                    _, proc_cpu, proc_rss = procs[pid]; cpu += proc_cpu; postgres_rss += proc_rss
    # Keep the historical QA cap measurement unchanged: process high-water RSS
    # plus the current RSS of the isolated PostgreSQL process tree. Also return
    # current RSS components so multi-day runs can distinguish growth from a
    # one-time high-water mark.
    return cpu, own_peak_rss+postgres_rss, own_rss, postgres_rss


def memory_sample(root, cluster_root, phase, *, state=None, started=None):
    cpu, cap_rss, process_rss, postgres_rss = resource_sample(cluster_root)
    row=dict(phase=phase,pid=os.getpid(),elapsedSeconds=round(time.monotonic()-started,3) if started else None,
             processCurrentRssBytes=process_rss,postgresTreeCurrentRssBytes=postgres_rss,
             capMethodSampleBytes=cap_rss,processHighWaterRssBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
             revision=state.get('revision') if state else None,nextGroupIndex=state.get('nextGroupIndex') if state else None,
             throughNs=state.get('throughNs') if state else None,retainedOrderCount=len(state.get('orders',{})) if state else None,
             cpuSeconds=round(cpu,3))
    path=Path(root)/'memory-trace.jsonl'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    with os.fdopen(fd,'a') as stream:
        stream.write(json.dumps(row,sort_keys=True)+'\n');stream.flush()
    return row


def assert_budgets(root, cluster_root, started):
    global PEAK_RAM, PEAK_ARTIFACT
    if time.monotonic()-started > MAX_WALL: raise RuntimeError('RESOURCE_STOP_WALL_60_MIN')
    if shutil.disk_usage(root).free < MIN_FREE: raise RuntimeError('RESOURCE_STOP_DISK_RESERVE_30_GIB')
    used = allocated(root)
    if used > MAX_ARTIFACT: raise RuntimeError('RESOURCE_STOP_ARTIFACT_512_MIB')
    cpu, ram, current_process_rss, postgres_rss = resource_sample(cluster_root)
    PEAK_RAM=max(PEAK_RAM,ram);PEAK_ARTIFACT=max(PEAK_ARTIFACT,used)
    if ram > MAX_RAM: raise RuntimeError('RESOURCE_STOP_RAM_1_GIB')
    return used, cpu, ram, current_process_rss, postgres_rss


def command(sid, cid, revision, kind, payload=None):
    return dict(schemaVersion=1, artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',
                sessionId=sid, commandId=cid, expectedRevision=revision,
                kind=kind, payload=payload or {})


def load_source(profile, source_path, proof_path, proof_hash, log_root):
    batch_groups=int(os.environ.get('BTL_QA_HISTORICAL_BATCH_GROUPS','64'))
    if batch_groups not in (64,96,128,256):raise RuntimeError('INVALID_QA_HISTORICAL_BATCH_GROUPS')
    source=AdmittedObservedSource(source_path, profile, receipt_path=proof_path,
                                  receipt_sha256=proof_hash, log_root=log_root)
    # This opt-in is confined to the isolated QA runner. Product and manual
    # replay keep IndexedTimelineCache's default of 64 groups.
    source.cache.max_groups_per_advance=batch_groups
    return source


def _db_command_ids(dsn, workspace, session):
    with connect(dsn) as db:
        rows = db.execute('SELECT command_id FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s',
                          (workspace, session)).fetchall()
    result=[]
    for (cid,) in rows:
        parts=cid.split(':')
        if len(parts)>=4 and parts[:2]==['order','stage'] and parts[2].isdigit():
            result.append(int(parts[2]))
    return max(result) if result else -1


def _pending_timeline_target(controller, scope, sid, state):
    """Return a committed partial ADVANCE target, validating its state binding.

    A Batch-256 reveal can stop before its requested time boundary. After a
    cold resume the runner must continue that exact durable target before it
    chooses a later hourly decision boundary.
    """
    source=controller._source(ObservedExecutionProfile.from_wire(state['profile']))
    path=source.cache._folder(scope,sid)/'timeline.sqlite'
    if not path.exists():return None
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT body FROM heads WHERE id=1').fetchone()
    if row is None:raise RuntimeError('TIMELINE_HEAD_MISSING')
    checkpoint=json.loads(row[0]);cursor=checkpoint.get('cursor',{})
    expected=(state['datasetId'],state['datasetVersion'],state['throughNs'],state['nextGroupIndex'],
              state['sourceCursorRevision'],state['sourcePrefixHash'])
    actual=(cursor.get('datasetId'),cursor.get('datasetVersion'),cursor.get('throughNs'),cursor.get('nextGroupIndex'),
            cursor.get('revision'),cursor.get('visiblePrefixHash'))
    if actual!=expected:raise RuntimeError('DURABLE_TIMELINE_STATE_MISMATCH')
    pending=cursor.get('pendingTargetNs')
    return None if pending is None else int(pending)


def _stage_orders(controller, store, source, scope, sid, state, stage, basis, *, selected_plan=None):
    if basis is None or int(state['throughNs'])-int(basis['timeNs']) > 60*S: return False
    pending=[oid for oid,o in state['orders'].items() if o['status']=='PENDING' and not oid.startswith('order:far:')]
    for oid in pending:
        state=store.inspect(scope,sid)['state']
        controller.apply(scope,command(sid,f'cancel:stage:{stage:02d}:{oid.rsplit(":",1)[-1]}',state['revision'],'CANCEL',{'orderId':oid}))
    state=store.inspect(scope,sid)['state'];b=state['quoteBasis']
    if b is None or int(state['throughNs'])-int(b['timeNs'])>60*S:return False
    bid=Decimal(b['bid']);ask=Decimal(b['ask']);step=Decimal('0.001')
    # Protective levels must clear the currently observed spread. Otherwise a
    # pending order can fill on Ask/Bid and immediately stop out on the
    # opposite side of that same quote. Size the symmetric bracket from only
    # this revealed quote; no future prices are consulted.
    risk=max(Decimal('0.50'),ask-bid+Decimal('0.01'))
    plans=(
        ('LONG','LIMIT',ask-step,ask-step-risk,ask-step+risk),
        ('LONG','STOP',ask+step,ask+step-risk,ask+step+risk),
        ('SHORT','LIMIT',bid+step,bid+step+risk,bid+step-risk),
        ('SHORT','STOP',bid-step,bid-step+risk,bid-step-risk),
    )
    if selected_plan is not None:
        plans=tuple(plan for plan in plans if plan[:2]==selected_plan)
        if len(plans)!=1:raise RuntimeError('TWO_DAY_ORDER_PLAN_INVALID')
    for side,otype,entry,sl,tp in plans:
        state=store.inspect(scope,sid)['state'];cid=f'order:stage:{stage:02d}:{side.lower()}:{otype.lower()}'
        payload=dict(side=side,orderType=otype,workflow='PLANNED',entry=format(entry,'f'),quantity='0.01',
                     sl=format(sl,'f'),tp=format(tp,'f'),riskPercent='1',observations=[])
        controller.apply(scope,command(sid,cid,state['revision'],'OPEN',payload))
    return True


def advance_until(controller, store, scope, sid, target, root, cluster_root, started, *, decision_targets,
                  order_decision_stages, eod_ns, day_hours, first_stage=None):
    reached=False
    first=True
    # This runner is the sole writer for its isolated QA Session. Reuse the
    # exact state returned by the preceding durable apply instead of opening a
    # separate PostgreSQL inspect transaction before every ADVANCE. The
    # controller's prepare/commit revision checks remain authoritative, so a
    # concurrent or stale write still fails closed.
    state=store.inspect(scope,sid)['state']
    target=int(target)
    pending_target=_pending_timeline_target(controller,scope,sid,state)
    while not reached:
        elapsed=max(0,int(state['throughNs'])-int(state['startNs']))
        stage_before=min(day_hours-1,elapsed//(3600*S))
        decision_boundary=int(decision_targets.get(str(stage_before+1),target))
        eod_decision=int(os.environ.get('BTL_QA_HISTORICAL_EOD_DECISION_NS',str(target)))
        if stage_before>=max(order_decision_stages) and int(state['throughNs'])<eod_decision:
            decision_boundary=min(decision_boundary,eod_decision)
        advance_target=(pending_target if pending_target is not None else
                        min(target,decision_boundary) if decision_boundary>int(state['throughNs']) else target)
        raw=command(sid,f'advance:{state["revision"]}',state['revision'],'ADVANCE',{'targetNs':str(advance_target)})
        if first and first_stage:
            with PERF.measured_stage(first_stage): result=controller.apply(scope,raw)
        else:
            result=controller.apply(scope,raw)
        first=False
        reached=result['replay']['exhaustedThroughBoundary'] and advance_target>=target
        state=result['state']
        pending_target=None if result['replay']['exhaustedThroughBoundary'] else advance_target
        used,cpu,ram,current_process_rss,postgres_rss=assert_budgets(root,cluster_root,started)
        progress=dict(status='RUNNING',sessionId=sid,revision=state['revision'],throughNs=state['throughNs'],
                      nextGroupIndex=state['nextGroupIndex'],targetNs=str(advance_target),allocatedBytes=used,
                      cpuSeconds=round(cpu,3),ramBytes=ram,currentProcessRssBytes=current_process_rss,
                      postgresTreeCurrentRssBytes=postgres_rss,retainedOrderCount=len(state['orders']),updatedUnixNs=time.time_ns())
        memory_sample(root,cluster_root,first_stage or 'replay',state=state,started=started)
        temp=Path(root)/'.progress.tmp';temp.write_text(json.dumps(progress,sort_keys=True)+'\n');os.chmod(temp,0o600);temp.replace(Path(root)/'progress.json')
        if int(state['throughNs'])>=eod_ns and not state['unresolved']:
            for oid,order in sorted(state['orders'].items()):
                if order['status']=='PENDING':
                    state=store.inspect(scope,sid)['state']
                    controller.apply(scope,command(sid,f'eod:cancel:{oid}',state['revision'],'CANCEL',{'orderId':oid}))
                elif order['status']=='ACTIVE' and order['exitRequest'] is None:
                    state=store.inspect(scope,sid)['state']
                    controller.apply(scope,command(sid,f'eod:close:{oid}',state['revision'],'CLOSE',{'orderId':oid,'quantity':None}))
            state=store.inspect(scope,sid)['state']
        # Stage orders only from the current revealed quote and durable clock.
        stage=min(day_hours-1,max(0,(int(state['throughNs'])-int(state['startNs']))//(3600*S)))
        current=_db_command_ids(os.environ['BTL_TEST_DATABASE_URL'],scope.workspace_id,sid)
        if int(state['throughNs']) < eod_ns and stage in order_decision_stages and current < stage:
            source=controller._source(ObservedExecutionProfile.from_wire(state['profile']))
            selected_plan=None
            if day_hours>=48 and stage>=24:
                rotations=(('LONG','LIMIT'),('SHORT','STOP'),('LONG','STOP'),('SHORT','LIMIT'))
                selected_plan=rotations[(stage-24)%len(rotations)]
            _stage_orders(controller,store,source,scope,sid,state,stage,state['quoteBasis'],selected_plan=selected_plan)
            if stage==0:
                after=store.inspect(scope,sid)['state'];bid=Decimal(after['quoteBasis']['bid']);ask=Decimal(after['quoteBasis']['ask'])
                for label,side,otype,entry,sl,tp in (
                    ('long-limit','LONG','LIMIT',bid-Decimal('50'),bid-Decimal('51'),bid-Decimal('49')),
                    ('long-stop','LONG','STOP',ask+Decimal('50'),ask+Decimal('49'),ask+Decimal('51')),
                ):
                    after=store.inspect(scope,sid)['state']
                    controller.apply(scope,command(sid,f'order:far:{label}',after['revision'],'OPEN',
                        dict(side=side,orderType=otype,workflow='PLANNED',entry=format(entry,'f'),quantity='0.01',
                             sl=format(sl,'f'),tp=format(tp,'f'),riskPercent='1',observations=[])))
            # Staging is a separate series of durable order commands. Refresh
            # once after that bounded batch so the next ADVANCE carries its
            # actual committed revision into the controller's CAS checks.
            state=store.inspect(scope,sid)['state']
        yield result


def _all_events(store, scope, sid):
    result=[];offset=0
    while True:
        page=store.inspect(scope,sid,after_sequence=offset,maximum=64)
        events=page['events'];result.extend(events)
        if page['nextEventSequence'] is None:break
        offset=page['nextEventSequence']
    return result


def verify_durable_receipts(dsn, workspace, sid, expected_revision):
    """Independently check every immutable QA command receipt and revision."""
    from execution.postgres import unpack
    with connect(dsn) as db:
        rows=db.execute('SELECT revision,command_id,command_hash,payload,content_hash '
                        'FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                        (workspace,sid)).fetchall()
    if len(rows)!=expected_revision:raise RuntimeError('INDEPENDENT_RECEIPT_COUNT_MISMATCH')
    advance_count=0;ledger=[]
    for expected,(revision,command_id,command_hash,payload,receipt_hash) in enumerate(rows,1):
        result=unpack(payload,receipt_hash)
        if revision!=expected or result.get('commandId')!=command_id or result.get('commandHash')!=command_hash:
            raise RuntimeError('INDEPENDENT_RECEIPT_IDENTITY_MISMATCH')
        if result.get('durable') is not True or result.get('state',{}).get('revision')!=revision:
            raise RuntimeError('INDEPENDENT_RECEIPT_STATE_MISMATCH')
        if command_id.startswith('advance:'):
            advance_count+=1
            if result.get('replay') is None:raise RuntimeError('INDEPENDENT_ADVANCE_RECEIPT_MISMATCH')
        elif result.get('replay') is not None:
            raise RuntimeError('INDEPENDENT_NONADVANCE_RECEIPT_MISMATCH')
        ledger.append(dict(revision=revision,commandId=command_id,commandHash=command_hash,receiptHash=receipt_hash))
    return dict(status='PASS',commands=len(rows),advanceCommands=advance_count,
                ledgerSha256=hashlib.sha256(canonical_bytes(dict(schemaVersion=1,
                    artifact='BTL-INDEPENDENT-COMMAND-LEDGER-1',rows=ledger))).hexdigest())


def independent_verify(source, store, scope, sid, start_ns, end_ns, *, gap_threshold_ns=60*S,
                       order_retention_policy=None):
    state=store.inspect(scope,sid)['state'];events=_all_events(store,scope,sid)
    validate_state(state,order_retention_policy=order_retention_policy)
    # Recompute the whole event commitment chain independently from stored rows.
    if events:
        genesis=content_hash(dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-SEED-1',sessionId=sid,
            profileHash=state['profileHash'],policy=state['policy'],startNs=state['startNs'],initialBalance=state['initialBalance']))
        previous=genesis
        for i,event in enumerate(events):
            body={k:v for k,v in event.items() if k!='eventId'}
            if event['sequence']!=i or event['previousHash']!=previous or event['eventId']!=content_hash(body):
                raise RuntimeError('INDEPENDENT_EVENT_CHAIN_MISMATCH')
            previous=event['eventId']
        if previous!=state['eventHash']:raise RuntimeError('INDEPENDENT_EVENT_HEAD_MISMATCH')
    fills=[e for e in events if e['classification']=='SIMULATED_FILL']
    by_time=defaultdict(list)
    for event in fills:by_time[event['detail']['evidence']['timeNs']].append(event)
    provider=source.provider()
    try:
        located=provider.locate_v2(source.dataset_id,source.version,str(start_ns));position=located['position']
        if position is None:raise RuntimeError('INDEPENDENT_SOURCE_START_MISSING')
        time_ns=None;rows=[];seen=0;groups=0;matched=0;first_quote_ns=None;last_quote_ns=None;previous_group_ns=None
        source_gaps=[]
        def verify_group(moment,group_rows):
            nonlocal groups,matched,first_quote_ns,last_quote_ns,previous_group_ns
            groups+=1
            if len(group_rows)>1: raise RuntimeError('INDEPENDENT_UNTRUSTED_TIE_IN_ONE_DAY')
            row=group_rows[0];ids=[r['eventId'] for r in group_rows]
            if first_quote_ns is None:first_quote_ns=str(moment)
            if previous_group_ns is not None and moment-previous_group_ns>gap_threshold_ns:
                closed=all(r['quality']['gapBefore']=='KNOWN_SESSION_CLOSED' for r in group_rows)
                source_gaps.append(dict(startNs=str(previous_group_ns),endNs=str(moment),elapsedNs=str(moment-previous_group_ns),
                    kind='MARKET_CLOSED' if closed else 'UNKNOWN_COVERAGE_GAP',quoteAvailable=True,sourceQuality='UNKNOWN'))
            previous_group_ns=moment;last_quote_ns=str(moment)
            gid=content_hash(dict(schemaVersion=1,artifact='BTL-TICK-GROUP-ID-1',datasetVersion=source.version,
                                  timeNs=str(moment),eventIds=ids))
            for fill in by_time.get(str(moment),[]):
                evidence=fill['detail']['evidence'];order=state['orders'][fill['orderId']]
                if evidence['groupId']!=gid or evidence['eventIds']!=ids or evidence['bid']!=row['bid'] or evidence['ask']!=row['ask']:
                    raise RuntimeError('INDEPENDENT_FILL_SOURCE_EVIDENCE_MISMATCH')
                if fill['kind']=='ENTRY_FILL': expected=row['ask'] if order['side']=='LONG' else row['bid']
                else: expected=row['bid'] if order['side']=='LONG' else row['ask']
                if fill['detail']['price']!=expected:raise RuntimeError('INDEPENDENT_FILL_PRICE_MISMATCH')
                matched+=1
        while position is not None:
            page=provider.read_page_v2(source.dataset_id,source.version,position,256)
            for row in page['events']:
                moment=int(row['timeNs'])
                if moment>end_ns:
                    position=None;break
                if moment<start_ns:continue
                if time_ns is None:time_ns=moment
                if moment!=time_ns:
                    verify_group(time_ns,rows);rows=[];time_ns=moment
                rows.append(row);seen+=1
            if position is not None:
                position=page['nextPosition']
                if not page['events'] and position is not None:raise RuntimeError('INDEPENDENT_SOURCE_NO_PROGRESS')
        if rows:verify_group(time_ns,rows)
    finally:provider.close()
    if matched!=len(fills):raise RuntimeError('INDEPENDENT_FILL_COUNT_MISMATCH')
    by_order=defaultdict(list)
    for event in events:
        if event['kind'] in ('ENTRY_FILL','EXIT_FILL'):by_order[event['orderId']].append(event)
    for oid,history in by_order.items():
        entries=[e for e in history if e['kind']=='ENTRY_FILL']
        if len(entries)!=1:raise RuntimeError('INDEPENDENT_ORDER_ENTRY_CARDINALITY_MISMATCH:'+oid)
        entry=entries[0]
        for exit_event in (e for e in history if e['kind']=='EXIT_FILL'):
            if exit_event['sequence']<=entry['sequence'] or int(exit_event['detail']['evidence']['timeNs'])<int(entry['detail']['evidence']['timeNs']):
                raise RuntimeError('INDEPENDENT_ORDER_EVENT_ORDER_MISMATCH:'+oid)
    exact_total=Fraction(0)
    fill_count=Counter()
    for event in fills:
        fill_count[event['kind']]+=1
        if event['kind']=='EXIT_FILL':exact_total+=Fraction(event['detail']['grossPosted'])
    if Fraction(state['balance'])!=Fraction(state['initialBalance'])+exact_total:
        raise RuntimeError('INDEPENDENT_CASH_RECONCILIATION_MISMATCH')
    if Fraction(state['realizedGross'])!=exact_total:raise RuntimeError('INDEPENDENT_REALIZED_GROSS_MISMATCH')
    return dict(status='PASS',independentSourceTicks=seen,independentTimestampGroups=groups,
                independentlyMatchedFills=matched,entryFills=fill_count['ENTRY_FILL'],exitFills=fill_count['EXIT_FILL'],
                reconciledGross=format(exact_total,'f'),reconciledBalance=state['balance'],
                eventChainHead=state['eventHash'],firstSourceQuoteNs=first_quote_ns,lastSourceQuoteNs=last_quote_ns,
                sourceObservedGaps=source_gaps,sourceConsistentOrderOrdering='PASS')


def worker(dsn, root, source_path, proof_path, proof_hash, workspace, actor, sid, day_end, decision_targets,
           order_decision_stages, eod_ns, day_hours, order_retention_policy=None):
    global PEAK_RAM,PEAK_ARTIFACT
    os.environ['BTL_TEST_DATABASE_URL']=dsn
    with PERF.measured_stage('cold_resume_setup'):
        proof=json.loads(Path(proof_path).read_text())
        with connect(dsn) as db:
            row=db.execute('SELECT payload,content_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',
                           (workspace,sid)).fetchone()
        if row is None:raise RuntimeError('COLD_RESUME_SESSION_MISSING')
        from execution.postgres import unpack
        snapshot=unpack(row[0],row[1]);state=snapshot['state']
        profile=ObservedExecutionProfile.from_wire(state['profile'])
        source=load_source(profile,Path(source_path),Path(proof_path),proof_hash,root/'source-logs')
        PEAK_RAM=max(PEAK_RAM,resource_sample(os.environ['BTL_QA_CLUSTER_ROOT'])[1])
    store=ObservedExecutionStore(dsn,order_retention_policy=order_retention_policy)
    scope=__import__('application.models',fromlist=['TrustedScope']).TrustedScope(workspace,actor)
    controller=ObservedExecutionController(store,lambda _:source,order_retention_policy=order_retention_policy)
    resume_revision=state['revision'];resume_state_hash=content_hash(state)
    start=int(state['startNs']);target=day_end
    with PERF.measured_stage('replay'):
        for _ in advance_until(controller,store,scope,sid,target,root,os.environ['BTL_QA_CLUSTER_ROOT'],
                               float(os.environ['BTL_QA_RUN_STARTED']),decision_targets=decision_targets,
                               order_decision_stages=order_decision_stages,eod_ns=eod_ns,day_hours=day_hours,
                               first_stage='cold_resume_first_command'):
            pass
    Path(root,'worker-resource.json').write_text(json.dumps(dict(peakRamBytes=PEAK_RAM,peakArtifactBytes=PEAK_ARTIFACT),sort_keys=True)+'\n')
    os.chmod(Path(root,'worker-resource.json'),0o600)
    Path(root,'worker-performance.json').write_text(json.dumps(PERF.snapshot(),sort_keys=True)+'\n')
    os.chmod(Path(root,'worker-performance.json'),0o600)
    source.close()
    return dict(status='PASS',workerProcessRestarted=True,throughNs=store.inspect(scope,sid)['state']['throughNs'],
                resumeRevision=resume_revision,resumeStateHash=resume_state_hash)


def main_worker():
    PERF.install()
    data=json.loads(os.environ['BTL_HISTORICAL_DAY_V2_WORKER'])
    result=worker(data['dsn'],Path(data['root']),data['source'],data['proof'],data['proofHash'],
                  data['workspace'],data['actor'],data['session'],int(data['dayEnd']),data['decisionTargets'],
                  set(data['orderDecisionStages']),int(data['eodNs']),int(data['dayHours']),data.get('orderRetentionPolicy'))
    Path(data['root'],'worker-result.json').write_text(json.dumps(result,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))


def main():
    global PEAK_RAM,PEAK_ARTIFACT
    PERF.install()
    root_text=os.environ.get('BTL_HISTORICAL_QA_ROOT')
    if not root_text:raise RuntimeError('SET_BTL_HISTORICAL_QA_ROOT_TO_NEW_EMPTY_PATH')
    root=Path(root_text)
    if root.exists():raise RuntimeError('QA_OUTPUT_PATH_MUST_NOT_EXIST')
    if shutil.disk_usage(root.parent if root.parent.exists() else Path('/')).free<MIN_FREE:
        raise RuntimeError('PREFLIGHT_DISK_RESERVE_BELOW_30_GIB')
    root.mkdir(mode=0o700,parents=False)
    os.chmod(root,0o700);tempfile.tempdir=str(root);os.environ['TMPDIR']=str(root)
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    batch_groups=int(os.environ.get('BTL_QA_HISTORICAL_BATCH_GROUPS','64'))
    if batch_groups not in (64,96,128,256):raise RuntimeError('INVALID_QA_HISTORICAL_BATCH_GROUPS')
    os.environ['BTL_QA_HISTORICAL_BATCH_GROUPS']=str(batch_groups)
    day_count=int(os.environ.get('BTL_QA_HISTORICAL_DAYS','1'))
    if day_count not in (1,2,3):raise RuntimeError('INVALID_QA_HISTORICAL_DAY_COUNT')
    day_hours=24*day_count
    order_retention_policy=QA_ORDER_RETENTION_V2 if day_count==3 else None
    decision_fixture=json.loads((Path(__file__).parent/'fixtures/historical_day_v2_decision_schedule.json').read_text())
    if decision_fixture.get('day')!=DAY:
        raise RuntimeError('ORDER_DECISION_SCHEDULE_DAY_MISMATCH')
    available=os.sched_getaffinity(0)
    if available:os.sched_setaffinity(0,{min(available)})
    started=time.monotonic();wall_start=time.time();initial_free=shutil.disk_usage(root).free
    proof_raw=PROOF.read_bytes();proof_hash=hashlib.sha256(proof_raw).hexdigest();proof=json.loads(proof_raw)
    vector=json.loads(PROFILE_FIXTURE.read_text());base=next(v['profile'] for v in vector['profiles'] if v['name']=='hf-2024-identity-not-admission')
    profile=ObservedExecutionProfile.from_wire(historical_technical_profile(base,proof_hash))
    config=json.loads(CONFIG_FIXTURE.read_text())
    if config['productionEnabled'] or config['executionLabel']!=profile.wire['executionLabel'] or config['gapPolicy']!=profile.wire['gapPolicy']:
        raise RuntimeError('QA_CONFIGURATION_CONTRACT_MISMATCH')
    if profile.wire['primary']['datasetId']!=proof['datasetId'] or profile.wire['primary']['datasetVersion']!=proof['datasetVersion']:
        raise RuntimeError('SOURCE_PROFILE_RECEIPT_MISMATCH')
    if proof.get('status')!='PASS' or proof.get('classification')!='FULL_BINARY_SOURCE_PUBLIC_PAGE_PARITY_NOT_FINANCIAL_ADMISSION':
        raise RuntimeError('SOURCE_QUALIFICATION_RECEIPT_NOT_ACCEPTED')
    if decision_fixture.get('datasetVersion')!=profile.wire['primary']['datasetVersion'] or decision_fixture.get('day')!=DAY:
        raise RuntimeError('ORDER_DECISION_SCHEDULE_SOURCE_MISMATCH')
    decision_targets=decision_fixture['decisionTargets']
    calendar=datetime.strptime(DAY,'%Y-%m-%d').replace(tzinfo=timezone.utc)
    midnight_ns=int(calendar.timestamp()*S)
    day_end=midnight_ns+day_hours*3600*S-1
    order_decision_stages=set(range(0,22))
    eod_ns=midnight_ns+(23*3600*S)
    if day_count>=2:
        # Keep the accepted Jan-2 targets byte-for-byte. Shift the same pinned
        # decision moments for each additional day; add no-order boundaries for
        # the two omitted hours so no batch can cross an hour.
        offset_ns=int(decision_targets['0'])-midnight_ns
        decision_targets={str(k):v for k,v in decision_targets.items()}
        for hour in (22,23):decision_targets[str(hour)]=str(midnight_ns+hour*3600*S+offset_ns)
        for day_index in range(1,day_count):
            shift=day_index*86400*S
            for hour in range(24):
                key=day_index*24+hour
                if hour<=21:
                    decision_targets[str(key)]=str(int(decision_fixture['decisionTargets'][str(hour)])+shift)
                    order_decision_stages.add(key)
                else:decision_targets[str(key)]=str(midnight_ns+key*3600*S+offset_ns)
        eod_ns=midnight_ns+(day_hours-1)*3600*S
        eod_decision=int(decision_fixture['baselineEodDecisionNs'])+(day_count-1)*86400*S
    else:
        decision_targets={str(k):v for k,v in decision_targets.items()}
        eod_decision=int(decision_fixture['baselineEodDecisionNs'])
    os.environ['BTL_QA_HISTORICAL_EOD_DECISION_NS']=str(eod_decision)
    (root/'memory-trace.jsonl').touch(mode=0o600)
    os.chmod(root/'memory-trace.jsonl',0o600)
    schedule_config=dict(schemaVersion=1,artifact='BTL-QA-REPLAY-CONFIG-1',batchGroups=batch_groups,
        maximumBatchGroups=256,continuousDays=day_count,orderDecisionBoundarySeconds=3600,
        firstDayOrderStages=sorted(range(0,22)),
        additionalDayOrderStages=[sorted(range(d*24,d*24+22)) for d in range(1,day_count)],
        orderRetentionPolicy=order_retention_policy or dict(schemaVersion=1,artifact='BTL-ORDER-RETENTION-V1',maxCumulativeOrders=MAX_ORDERS),
        maxCumulativeOrders=(order_retention_policy or {}).get('maxCumulativeOrders',MAX_ORDERS),
        additionalDayOrdersPerDecision=1 if day_count>1 else None,
        decisionTargets=decision_targets,eodDecisionNs=str(eod_decision),sourceProcessing='ALL_OBSERVED_GROUPS',
        productionEnabled=False)
    (root/'replay-config.json').write_text(json.dumps(schedule_config,sort_keys=True)+'\n')
    os.chmod(root/'replay-config.json',0o600)
    run_id=os.environ.get('BTL_HISTORICAL_QA_RUN_ID',uuid.uuid4().hex)
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,31}',run_id):raise RuntimeError('INVALID_QA_RUN_ID')
    session='session:hist-v2:'+run_id
    workspace='observedqa:hist-v2:'+run_id;actor='fixture:internal-qa'
    method=MethodPolicy('method:hist-v2:'+run_id,'a'*64,'FREE_STYLE',False,())
    metrics=dict(cpuStart=resource_sample(root/'postgres')[0],peakRam=0,peakArtifact=0)
    summary={}
    from deploy.vps.tests.run_private_pg import private_postgres
    with private_postgres(keep=True,root_dir=root/'postgres') as (repository,env):
        os.environ.update(env);dsn=env['BTL_TEST_DATABASE_URL'];migrate(dsn)
        source=load_source(profile,SOURCE,PROOF,proof_hash,root/'source-logs')
        PEAK_RAM=max(PEAK_RAM,resource_sample(root/'postgres')[1])
        store=ObservedExecutionStore(dsn,order_retention_policy=order_retention_policy)
        scope=__import__('application.models',fromlist=['TrustedScope']).TrustedScope(workspace,actor)
        controller=ObservedExecutionController(store,lambda _:source,order_retention_policy=order_retention_policy)
        initial=controller.create(scope,session,profile,method,period=PERIOD,day=DAY,balance='10000')
        start=int(initial['startNs'])
        eod_ns=start+(day_hours-1)*3600*S
        # Reveal the opening quote, then submit the first order batch using only
        # this already revealed Bid/Ask. Duplicate retry is required to be exact.
        first=command(session,'advance:opening',0,'ADVANCE',{'targetNs':str(start)})
        receipt=controller.apply(scope,first);retry=controller.apply(scope,first)
        if canonical_bytes(receipt)!=canonical_bytes(retry):raise RuntimeError('IDEMPOTENT_RETRY_MISMATCH')
        state=receipt['state'];basis=state['quoteBasis']
        if basis is None:raise RuntimeError('OPENING_QUOTE_NOT_REVEALED')
        _stage_orders(controller,store,source,scope,session,state,0,basis)
        state=store.inspect(scope,session)['state'];bid=Decimal(state['quoteBasis']['bid']);ask=Decimal(state['quoteBasis']['ask'])
        for label,side,otype,entry,sl,tp in (
            ('long-limit','LONG','LIMIT',bid-Decimal('50'),bid-Decimal('51'),bid-Decimal('49')),
            ('long-stop','LONG','STOP',ask+Decimal('50'),ask+Decimal('49'),ask+Decimal('51')),
        ):
            state=store.inspect(scope,session)['state']
            controller.apply(scope,command(session,f'order:far:{label}',state['revision'],'OPEN',
                dict(side=side,orderType=otype,workflow='PLANNED',entry=format(entry,'f'),quantity='0.01',
                     sl=format(sl,'f'),tp=format(tp,'f'),riskPercent='1',observations=[])))
        # Durable progress before a real worker process restart.
        resume_target=start+(24*3600*S-1 if day_count==2 else 4*3600*S)
        with PERF.measured_stage('replay'):
            for _ in advance_until(controller,store,scope,session,resume_target,root,root/'postgres',started,
                                   decision_targets=decision_targets,order_decision_stages=order_decision_stages,
                                   eod_ns=eod_ns,day_hours=day_hours):pass
        before_restart=store.inspect(scope,session)['state']
        memory_sample(root,root/'postgres','before_cold_resume',state=before_restart,started=started)
        source.close()
        worker_data=dict(dsn=dsn,root=str(root),source=str(SOURCE),proof=str(PROOF),proofHash=proof_hash,
                         workspace=workspace,actor=actor,session=session,dayEnd=day_end,
                         decisionTargets=decision_targets,orderDecisionStages=sorted(order_decision_stages),
                         eodNs=eod_ns,dayHours=day_hours,orderRetentionPolicy=order_retention_policy)
        env=dict(os.environ,BTL_HISTORICAL_DAY_V2_WORKER=json.dumps(worker_data),
                 BTL_TEST_DATABASE_URL=dsn,BTL_QA_CLUSTER_ROOT=str(root/'postgres'),
                 BTL_QA_RUN_STARTED=str(started),PYTHONDONTWRITEBYTECODE='1')
        proc=subprocess.run([sys.executable,'-B','-m','tests.qa_historical_day_v2','--worker'],cwd=repository,
                            env=env,capture_output=True,text=True,timeout=max(1,int(MAX_WALL-(time.monotonic()-started))))
        if proc.returncode!=0:raise RuntimeError('COLD_RESUME_WORKER_FAILED:'+proc.stderr[-2000:])
        state=store.inspect(scope,session)['state']
        if int(state['throughNs'])<day_end:raise RuntimeError('UTC_DAY_BOUNDARY_NOT_REACHED')
        final=source=load_source(profile,SOURCE,PROOF,proof_hash,root/'source-logs-independent')
        with PERF.measured_stage('independent_verification'):
            verification=independent_verify(source,store,scope,session,start,day_end,
                                            order_retention_policy=order_retention_policy)
            receipt_verification=verify_durable_receipts(dsn,scope.workspace_id,session,state['revision'])
        source.close()
        memory_sample(root,root/'postgres','independent_verification_complete',state=state,started=started)
        events=_all_events(store,scope,session)
        with connect(dsn) as db:
            receipt_rows=db.execute('SELECT revision,command_id,command_hash,content_hash FROM btl.tick_commands '
                                    'WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                                    (scope.workspace_id,session)).fetchall()
        event_transcript_hash=hashlib.sha256(canonical_bytes(dict(schemaVersion=1,
            artifact='BTL-OBSERVED-EVENT-TRANSCRIPT-1',eventIds=[e['eventId'] for e in events]))).hexdigest()
        receipt_ledger_hash=hashlib.sha256(canonical_bytes(dict(schemaVersion=1,
            artifact='BTL-OBSERVED-RECEIPT-LEDGER-1',rows=[dict(revision=r[0],commandId=r[1],
            commandHash=r[2],receiptHash=r[3]) for r in receipt_rows]))).hexdigest()
        semantic_events=[]
        for event in events:
            if event['kind']=='REPLAY_ADVANCED':continue
            detail=dict(event['detail']);detail.pop('entryFillRef',None)
            semantic_events.append(dict(kind=event['kind'],classification=event['classification'],
                                        orderId=event['orderId'],detail=detail))
        semantic_event_hash=hashlib.sha256(canonical_bytes(dict(schemaVersion=1,
            artifact='BTL-OBSERVED-FINANCIAL-TRANSCRIPT-1',events=semantic_events))).hexdigest()
        state_projection=dict(schemaVersion=1,artifact='BTL-OBSERVED-FINANCIAL-STATE-COMPARISON-1',
            **{k:state[k] for k in ('throughNs','balance','initialBalance','realizedGross','commission','unresolved','ended')})
        state_projection['orders']={oid:{k:o[k] for k in ('side','orderType','workflow','entry','quantity','sl','tp','status',
            'availableNs','remaining','entryPrice','entryCost','grossPosted','riskBalance','exitRequest')}
            for oid,o in sorted(state['orders'].items())}
        financial_state_hash=hashlib.sha256(canonical_bytes(state_projection)).hexdigest()
        observed_orders={oid:{'side':o['side'],'orderType':o['orderType'],'status':o['status'],'entryPrice':o['entryPrice'],
                              'remaining':o['remaining']} for oid,o in sorted(state['orders'].items())}
        order_types=Counter(o['orderType'] for o in state['orders'].values())
        statuses=Counter(o['status'] for o in state['orders'].values())
        kinds=Counter(e['kind'] for e in events)
        gap_events=[e for e in events if e['kind']=='DATA_GAP_LIMITATION']
        order_acceptance_events=[e for e in events if e['kind']=='ORDER_ACCEPTED']
        accepted_order_ids={e['orderId'] for e in order_acceptance_events}
        retained_order_ids=set(state['orders'])
        max_retained_orders=(order_retention_policy or {}).get('maxCumulativeOrders',MAX_ORDERS)
        order_history_complete=accepted_order_ids==retained_order_ids and len(retained_order_ids)<=max_retained_orders
        if not order_history_complete:raise RuntimeError('DURABLE_ORDER_HISTORY_MISMATCH')
        memory_rows=[json.loads(line) for line in (root/'memory-trace.jsonl').read_text().splitlines() if line.strip()]
        current_rss=[int(r['processCurrentRssBytes'])+int(r['postgresTreeCurrentRssBytes']) for r in memory_rows]
        cold_samples=[r for r in memory_rows if r['phase']=='cold_resume_first_command']
        memory_summary=dict(measurement='max(process VmRSS, process ru_maxrss) + current isolated PostgreSQL descendant VmRSS; separate current process and PG components recorded per ADVANCE',
            historicalCheckpointMethodSha256='8a1e97452254ff80144ab0e226feb29a3ace84ac34974d9ac36457cd17e58911',
            historicalBatch128MethodSameAsBatch256=True,traceSamples=len(memory_rows),
            peakCapMethodSampleBytes=max((int(r['capMethodSampleBytes']) for r in memory_rows),default=0),
            peakCurrentProcessPlusPostgresRssBytes=max(current_rss,default=0),
            firstReplayCurrentRssBytes=current_rss[0] if current_rss else None,
            beforeColdResumeCurrentRssBytes=(current_rss[-2] if len(current_rss)>=2 else None),
            afterColdResumeFirstAdvance=dict(processCurrentRssBytes=cold_samples[0]['processCurrentRssBytes'],
                postgresTreeCurrentRssBytes=cold_samples[0]['postgresTreeCurrentRssBytes'],
                capMethodSampleBytes=cold_samples[0]['capMethodSampleBytes']) if cold_samples else None,
            finalCurrentRssBytes=current_rss[-1] if current_rss else None,
            maxRetainedOrderCount=max((int(r['retainedOrderCount']) for r in memory_rows if r['retainedOrderCount'] is not None),default=0))
        worker_result=json.loads((root/'worker-result.json').read_text()) if (root/'worker-result.json').exists() else {}
        worker_resource=json.loads((root/'worker-resource.json').read_text()) if (root/'worker-resource.json').exists() else {}
        worker_phases=json.loads((root/'worker-performance.json').read_text()) if (root/'worker-performance.json').exists() else {}
        phase_metrics=PERF.merge(PERF.snapshot(),worker_phases)
        replay_wall=sum(row.get('wallNs',0) for name,phases in phase_metrics.items()
                        if name=='replay' for key,row in phases.items() if key=='stage.wall')/1e9
        verify_wall=phase_metrics.get('independent_verification',{}).get('stage.wall',{}).get('wallNs',0)/1e9
        pg_prepare=sum(row.get('wallNs',0) for phases in phase_metrics.values() for key,row in phases.items() if key=='postgres.prepare')/1e9
        pg_commit=sum(row.get('wallNs',0) for phases in phase_metrics.values() for key,row in phases.items() if key=='postgres.commit')/1e9
        replay_apply=sum(row.get('wallNs',0) for name,phases in phase_metrics.items()
                         if name in ('replay','cold_resume_first_command') for key,row in phases.items() if key=='command.total')/1e9
        with connect(dsn) as db:postgres_db_bytes=int(db.execute('SELECT pg_database_size(current_database())').fetchone()[0])
        summary=dict(status='PASS',classification=profile.wire['executionLabel'],
            executionEligibility='NOT_GRANTED',technicalSimulationEligibility='PASS',sourceRights='UNKNOWN',
            sourceProvenance='PROVIDER_OBSERVATION',datasetId=profile.wire['primary']['datasetId'],
            datasetVersion=profile.wire['primary']['datasetVersion'],qualificationReceiptSha256=proof_hash,
            archiveSha256=proof['snapshotSha256'],period=DAY if day_count==1 else '2024-01-02/2024-01-03',
            dayStartNs=str(start),dayEndNs=str(day_end),continuousDays=day_count,
            firstSourceQuoteNs=verification['firstSourceQuoteNs'],lastSourceQuoteNs=verification['lastSourceQuoteNs'],
            tickCount=verification['independentSourceTicks'],timestampGroupCount=verification['independentTimestampGroups'],
            gapCount=len(gap_events),gapKinds=dict(Counter(e['detail']['gapKind'] for e in gap_events)),
            sourceObservedGaps=verification['sourceObservedGaps'],
            unknownCoverageGapCount=sum(g['kind']=='UNKNOWN_COVERAGE_GAP' for g in verification['sourceObservedGaps']),
            commandCount=state['revision'],eventCount=len(events),orderTypeCounts=dict(order_types),
            orderStatusCounts=dict(statuses),eventKinds=dict(kinds),orders=observed_orders,
            cumulativeOrderHistory=dict(status='PASS',retainedOrderCount=len(retained_order_ids),
                maximumRetainedOrders=max_retained_orders,durableOrderAcceptedEvents=len(accepted_order_ids),
                noHistoricalOrderPruning=True,allOrderIdsMatchState=True),
            startingBalance=state['initialBalance'],endingBalance=state['balance'],
            realizedGross=state['realizedGross'],independentVerification=verification,
            parity=dict(eventTranscriptSha256=event_transcript_hash,receiptLedgerSha256=receipt_ledger_hash,
                        semanticFinancialEventSha256=semantic_event_hash,financialStateSha256=financial_state_hash,
                        finalStateSha256=content_hash(state),resumeStateSha256=worker_result.get('resumeStateHash')),
            coldResume=dict(status='PASS',processRestarted=True,resumedFromRevision=before_restart['revision'],
                            finalRevision=state['revision'],sameSession=session),
            idempotencyRetry='PASS',productionChanged=False,sourceChanged=False,memory=memory_summary,
            performanceBreakdown=dict(exclusive=False,phases=phase_metrics),
            replayBatch=dict(maxGroups=batch_groups,advanceCommands=receipt_verification['advanceCommands'],
                             averageTicksPerAdvance=round(verification['independentSourceTicks']/receipt_verification['advanceCommands'],3),
                             durableReceiptVerification=receipt_verification),
            performanceSummary=dict(userFacingReplayWallSeconds=round(replay_wall,3),
                endToEndWallSeconds=round(time.monotonic()-started,3),
                coldResumeWallSeconds=round(
                    phase_metrics.get('cold_resume_setup',{}).get('stage.wall',{}).get('wallNs',0)/1e9+
                    phase_metrics.get('cold_resume_first_command',{}).get('stage.wall',{}).get('wallNs',0)/1e9,3),
                controllerApplyWallSeconds=round(replay_apply,3),postgresPrepareWallSeconds=round(pg_prepare,3),
                postgresCommitWallSeconds=round(pg_commit,3),postgresPersistenceWallSeconds=round(pg_prepare+pg_commit,3),
                independentFullVerificationWallSeconds=round(verify_wall,3)),
            storage=dict(postgresDatabaseBytes=postgres_db_bytes,postgresClusterAllocatedBytes=allocated(root/'postgres'),
                totalQaArtifactBytes=allocated(root)),
            measured=dict(elapsedSeconds=round(time.monotonic()-started,3),cpuSeconds=round(resource_sample(root/'postgres')[0]-metrics['cpuStart'],3),
                          peakRamBytes=max(PEAK_RAM,worker_resource.get('peakRamBytes',0)),peakArtifactBytes=max(PEAK_ARTIFACT,worker_resource.get('peakArtifactBytes',0),allocated(root)),
                          initialFreeBytes=initial_free,finalFreeBytes=shutil.disk_usage(root).free,
                          vCPUEquivalentLimit=1,
                          peakRamLimitBytes=MAX_RAM,artifactLimitBytes=MAX_ARTIFACT))
        if not kinds['ENTRY_FILL'] or not kinds['EXIT_FILL'] or not kinds['DATA_GAP_LIMITATION']:
            summary['status']='FAIL';summary['acceptanceFailure']='REQUIRED_FILL_OR_GAP_EVIDENCE_ABSENT'
        if not any(e['kind']=='EXIT_FILL' and e['detail']['reason']=='TP' for e in events) or not any(e['kind']=='EXIT_FILL' and e['detail']['reason']=='SL' for e in events):
            summary['status']='FAIL';summary['acceptanceFailure']='BOTH_SL_AND_TP_NOT_OBSERVED'
        actual=dict(entries=kinds['ENTRY_FILL'],exits=kinds['EXIT_FILL'],
            stopLosses=sum(e['kind']=='EXIT_FILL' and e['detail']['reason']=='SL' for e in events),
            takeProfits=sum(e['kind']=='EXIT_FILL' and e['detail']['reason']=='TP' for e in events),
            endingBalance=state['balance'],realizedGross=state['realizedGross'])
        if day_count==1:
            expected=decision_fixture['baselineResults']
            if (semantic_event_hash!=decision_fixture['baselineSemanticFinancialEventSha256'] or
                financial_state_hash!=decision_fixture['baselineFinancialStateSha256'] or actual!=expected):
                summary['status']='FAIL';summary['acceptanceFailure']='CANONICAL_FINANCIAL_PARITY_MISMATCH'
                summary['baselineParityExpected']=expected;summary['candidateParityActual']=actual
        else:
            summary['twoDayFinancialResult']=actual
            if len(retained_order_ids)>max_retained_orders:
                summary['status']='FAIL';summary['acceptanceFailure']='CUMULATIVE_ORDER_LIMIT_EXCEEDED'
        report=root/'report.json';report.write_text(json.dumps(summary,indent=2,sort_keys=True,ensure_ascii=False)+'\n');report.chmod(0o600)
        metrics['peakArtifact']=allocated(root)
        assert_budgets(root,root/'postgres',started)
        (root/'resource-final.json').write_text(json.dumps(dict(cpuSeconds=summary['measured']['cpuSeconds'],
            peakRamBytes=metrics['peakRam'],peakArtifactBytes=allocated(root),freeBytes=shutil.disk_usage(root).free),sort_keys=True)+'\n')
        os.chmod(root/'resource-final.json',0o600)
        print(json.dumps(summary,sort_keys=True,ensure_ascii=False))
    return 0 if summary['status']=='PASS' else 2


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        try:main_worker()
        except BaseException:
            traceback.print_exc();raise SystemExit(1)
    else:
        # Do not catch SystemExit(0) as a failure: main() uses its return code
        # as the QA runner's process status after writing the durable report.
        raise SystemExit(main())
