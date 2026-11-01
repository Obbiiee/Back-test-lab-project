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
from execution.observed_kernel import (MAX_ACTIVE_ORDERS, MAX_ORDERS, QA_ORDER_RETENTION_V2,
                                       QA_ORDER_RETENTION_V3, QA_ORDER_RETENTION_V4,
                                       STATE_QA_ARCHIVE_V1, validate_state)
from execution.observed_postgres import ObservedExecutionStore, QA3_RESULT
from execution.observed_profile import ObservedExecutionProfile, historical_technical_profile
from execution.contracts import text
from infrastructure.database import connect, migrate
from ticks.storage_v2 import DiskTickProvider
from tests import qa_perf_instrumentation as PERF

DAY = '2024-01-02'
PERIOD = '2024-01'
S = 1_000_000_000
REQUESTED_DAY_COUNT = int(os.environ.get('BTL_QA_HISTORICAL_DAYS', '1'))
WEEKLY_QA = REQUESTED_DAY_COUNT == 7
MONTHLY_QA = REQUESTED_DAY_COUNT == 30
QA_STATE_DELTA_V3 = os.environ.get('BTL_QA_HISTORICAL_STATE_FORMAT') == 'qa-v3'
QA_ORDER_ARCHIVE_V1 = os.environ.get('BTL_QA_ORDER_ARCHIVE_V1') == '1'
USE_QA_STATE_DELTA_V3 = QA_STATE_DELTA_V3 or QA_ORDER_ARCHIVE_V1
TRADE_GRID_V1 = os.environ.get('BTL_QA_TRADE_SCENARIO') == 'observed-hourly-grid-v1'
STOP_AFTER_COMPLETED_TRADES = int(os.environ.get('BTL_QA_STOP_AFTER_COMPLETED_TRADES','0'))
MAX_WALL = 18_000.0 if MONTHLY_QA else 5400.0 if WEEKLY_QA else 3600.0
MAX_ARTIFACT = (4608 if MONTHLY_QA else 1536 if WEEKLY_QA else 512) * 1024 * 1024
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


def _hash_canonical_records(artifact,records):
    """Hash an ordered stream of small canonical records without a giant JSON node tree."""
    digest=hashlib.sha256();domain=b'BTL-QA-FRAMED-CANONICAL-RECORDS-1\0'
    name=artifact.encode('utf-8');digest.update(domain);digest.update(len(name).to_bytes(4,'big'));digest.update(name)
    count=0
    for record in records:
        wire=canonical_bytes(record if type(record) is dict and record.get('schemaVersion')==1
                             else dict(schemaVersion=1,record=record))
        digest.update(len(wire).to_bytes(8,'big'));digest.update(wire);count+=1
    digest.update(b'\xffRECORD-COUNT\0');digest.update(count.to_bytes(8,'big'))
    return digest.hexdigest()


def _financial_state_digest(state,orders):
    fields=('throughNs','balance','initialBalance','realizedGross','commission','unresolved','ended')
    order_fields=('side','orderType','workflow','entry','quantity','sl','tp','status','availableNs','remaining',
                  'entryPrice','entryCost','grossPosted','riskBalance','exitRequest')
    if len(orders)<=256:
        projection=dict(schemaVersion=1,artifact='BTL-OBSERVED-FINANCIAL-STATE-COMPARISON-1',
            **{k:state[k] for k in fields})
        projection['orders']={oid:{k:o[k] for k in order_fields} for oid,o in sorted(orders.items())}
        return 'BTL-OBSERVED-FINANCIAL-STATE-COMPARISON-1',hashlib.sha256(canonical_bytes(projection)).hexdigest()
    records=[dict(recordType='STATE',**{k:state[k] for k in fields},orderCount=len(orders))]
    records.extend(dict(recordType='ORDER',orderId=oid,order={k:o[k] for k in order_fields})
                   for oid,o in sorted(orders.items()))
    return 'BTL-OBSERVED-FINANCIAL-STATE-COMPARISON-2-STREAM',_hash_canonical_records(
        'BTL-OBSERVED-FINANCIAL-STATE-COMPARISON-2-STREAM',records)


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
    if time.monotonic()-started > MAX_WALL: raise RuntimeError('RESOURCE_STOP_WALL_BUDGET')
    if shutil.disk_usage(root).free < MIN_FREE: raise RuntimeError('RESOURCE_STOP_DISK_RESERVE_30_GIB')
    used = allocated(root)
    if used > MAX_ARTIFACT: raise RuntimeError('RESOURCE_STOP_ARTIFACT_BUDGET')
    cpu, ram, current_process_rss, postgres_rss = resource_sample(cluster_root)
    PEAK_RAM=max(PEAK_RAM,ram);PEAK_ARTIFACT=max(PEAK_ARTIFACT,used)
    if ram > MAX_RAM: raise RuntimeError('RESOURCE_STOP_RAM_1_GIB')
    return used, cpu, ram, current_process_rss, postgres_rss


def command(sid, cid, revision, kind, payload=None):
    return dict(schemaVersion=1, artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',
                sessionId=sid, commandId=cid, expectedRevision=revision,
                kind=kind, payload=payload or {})


def _command_latency_summary(samples_ns):
    ordered=sorted(int(value) for value in samples_ns)
    if not ordered:return dict(count=0,p50Ms=None,p95Ms=None)
    def nearest_rank(percent):return ordered[max(0,(percent*len(ordered)+99)//100-1)]/1_000_000
    return dict(count=len(ordered),p50Ms=round(nearest_rank(50),3),p95Ms=round(nearest_rank(95),3))


def load_source(profile, source_path, proof_path, proof_hash, log_root):
    batch_groups=int(os.environ.get('BTL_QA_HISTORICAL_BATCH_GROUPS','64'))
    if batch_groups not in (64,96,128,256):raise RuntimeError('INVALID_QA_HISTORICAL_BATCH_GROUPS')
    shared=os.environ.get('BTL_QA_SHARED_CANONICAL_SOURCE_V1')=='1'
    source=AdmittedObservedSource(source_path, profile, receipt_path=proof_path,
                                  receipt_sha256=proof_hash, log_root=log_root,
                                  timeline_storage_mode='shared-source-v1' if shared else 'session-log-v2')
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
        # Each order needs its own durable cancellation receipt. A tier-only
        # suffix collides when several grid orders are pending at one boundary.
        order_key=hashlib.sha256(oid.encode('utf-8')).hexdigest()[:16]
        controller.apply(scope,command(sid,f'cancel:stage:{stage:02d}:{order_key}',state['revision'],'CANCEL',{'orderId':oid}))
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
    if TRADE_GRID_V1 and selected_plan is None:
        # A fixed two-band order grid is created only from the currently
        # revealed Bid/Ask. It increases genuine order opportunities without
        # changing the kernel, reading future quotes, or manufacturing fills.
        far=Decimal('0.005')
        plans=plans+(
            ('LONG','LIMIT',ask-far,ask-far-risk,ask-far+risk),
            ('LONG','STOP',ask+far,ask+far-risk,ask+far+risk),
            ('SHORT','LIMIT',bid+far,bid+far+risk,bid+far-risk),
            ('SHORT','STOP',bid-far,bid-far+risk,bid-far-risk),
        )
    if selected_plan is not None:
        plans=tuple(plan for plan in plans if plan[:2]==selected_plan)
        if len(plans)!=1:raise RuntimeError('TWO_DAY_ORDER_PLAN_INVALID')
    for plan in plans:
        side,otype,entry,sl,tp=plan
        tier='near' if plan in plans[:4] else 'far'
        suffix=f':{tier}' if TRADE_GRID_V1 and selected_plan is None else ''
        state=store.inspect(scope,sid)['state'];cid=f'order:stage:{stage:02d}:{side.lower()}:{otype.lower()}{suffix}'
        payload=dict(side=side,orderType=otype,workflow='PLANNED',entry=format(entry,'f'),quantity='0.01',
                     sl=format(sl,'f'),tp=format(tp,'f'),riskPercent='1',observations=[])
        controller.apply(scope,command(sid,cid,state['revision'],'OPEN',payload))
    return True


def _events_committed_by_result(store,scope,sid,result,from_sequence):
    if result.get('eventsComplete') is True:return result['events']
    output=[];offset=from_sequence;end=int(result['state']['nextEventIndex'])
    while offset<end:
        page=store.inspect(scope,sid,after_sequence=offset,maximum=64)
        rows=page['events']
        if not rows:raise RuntimeError('COMMITTED_EVENT_PAGE_MISSING')
        output.extend(rows);offset=int(rows[-1]['sequence'])+1
    return output


def _partial_probe_stage(events,order_id):
    stage='WAIT_ENTRY'
    for event in events:
        if event.get('orderId')!=order_id:continue
        if event['kind']=='ENTRY_FILL':stage='NEED_FIRST_REQUEST'
        elif event['kind']=='EXIT_REQUESTED':
            if stage=='NEED_FIRST_REQUEST':stage='WAIT_PARTIAL_EXIT'
            elif stage=='NEED_FINAL_REQUEST':stage='WAIT_FINAL_EXIT'
        elif event['kind']=='EXIT_FILL':
            remaining=event['detail']['remaining']
            if remaining=='0.01' and stage=='WAIT_PARTIAL_EXIT':stage='NEED_FINAL_REQUEST'
            elif remaining=='0' and stage=='WAIT_FINAL_EXIT':stage='DONE'
            elif remaining=='0':stage='FAILED_CLOSED_WITHOUT_PARTIAL'
    return stage


def _advance_partial_probe(controller,store,scope,sid,partial_probe,committed_events):
    if partial_probe is None:return False
    order_id=partial_probe['orderId']
    probe_events=[event for event in committed_events if event.get('orderId')==order_id]
    if not probe_events and partial_probe.get('stage') not in ('NEED_FIRST_REQUEST','NEED_FINAL_REQUEST'):
        return False
    observed=partial_probe.setdefault('observedEvents',[])
    observed.extend(probe_events)
    partial_probe['stage']=_partial_probe_stage(observed,order_id)
    state=store.inspect(scope,sid)['state']
    if partial_probe['stage']=='NEED_FIRST_REQUEST':
        order=state['orders'].get(order_id)
        if order is None or order['status']!='ACTIVE' or order['remaining']!='0.02':
            raise RuntimeError('PARTIAL_CLOSE_PROBE_NOT_ACTIVE_AFTER_ENTRY')
        receipt=controller.apply(scope,command(sid,'close:cp6a7-partial-probe:first',state['revision'],'CLOSE',
                                               {'orderId':order_id,'quantity':'0.01'}))
        observed.extend(e for e in receipt.get('events',[]) if e.get('orderId')==order_id)
        partial_probe['stage']=_partial_probe_stage(observed,order_id)
        return True
    elif partial_probe['stage']=='NEED_FINAL_REQUEST':
        order=state['orders'].get(order_id)
        if order is None or order['status']!='ACTIVE' or order['remaining']!='0.01':
            raise RuntimeError('PARTIAL_CLOSE_PROBE_REMAINING_STATE_MISMATCH')
        receipt=controller.apply(scope,command(sid,'close:cp6a7-partial-probe:rest',state['revision'],'CLOSE',
                                               {'orderId':order_id,'quantity':None}))
        observed.extend(e for e in receipt.get('events',[]) if e.get('orderId')==order_id)
        partial_probe['stage']=_partial_probe_stage(observed,order_id)
        return True
    elif partial_probe['stage']=='FAILED_CLOSED_WITHOUT_PARTIAL':
        raise RuntimeError('PARTIAL_CLOSE_PROBE_CLOSED_BEFORE_MANUAL_PARTIAL')
    return False


def advance_until(controller, store, scope, sid, target, root, cluster_root, started, *, decision_targets,
                  order_decision_stages, eod_ns, day_hours, first_stage=None, trade_gate=None,
                  partial_probe=None):
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
    if trade_gate is not None and 'completedTradeCount' not in trade_gate:
        trade_gate['completedTradeCount']=sum(e['kind']=='EXIT_FILL' and e['detail'].get('remaining')=='0'
            for e in _all_events(store,scope,sid))
        trade_gate['crossings']=[]
        trade_gate['crossedThresholds']=[]
    while not reached:
        elapsed=max(0,int(state['throughNs'])-int(state['startNs']))
        stage_before=min(day_hours-1,elapsed//(3600*S))
        decision_boundary=int(decision_targets.get(str(stage_before+1),target))
        eod_decision=int(os.environ.get('BTL_QA_HISTORICAL_EOD_DECISION_NS',str(target)))
        if stage_before>=max(order_decision_stages) and int(state['throughNs'])<eod_decision:
            decision_boundary=min(decision_boundary,eod_decision)
        advance_target=(pending_target if pending_target is not None else
                        min(target,decision_boundary) if decision_boundary>int(state['throughNs']) else target)
        previous_event_index=int(state['nextEventIndex'])
        raw=command(sid,f'advance:{state["revision"]}',state['revision'],'ADVANCE',{'targetNs':str(advance_target)})
        if first and first_stage:
            with PERF.measured_stage(first_stage): result=controller.apply(scope,raw)
        else:
            result=controller.apply(scope,raw)
        first=False
        reached=result['replay']['exhaustedThroughBoundary'] and advance_target>=target
        state=result['state']
        gate_reached=False
        committed_events=[]
        if trade_gate is not None or partial_probe is not None:
            committed_events=_events_committed_by_result(store,scope,sid,result,previous_event_index)
        if partial_probe is not None:
            if _advance_partial_probe(controller,store,scope,sid,partial_probe,committed_events):
                state=store.inspect(scope,sid)['state']
        if trade_gate is not None:
            for event in committed_events:
                if event['kind']!='EXIT_FILL' or event['detail'].get('remaining')!='0':continue
                trade_gate['completedTradeCount']+=1
                for threshold in trade_gate['thresholds']:
                    if (threshold not in trade_gate['crossedThresholds'] and
                            trade_gate['completedTradeCount']>=threshold):
                        trade_gate['crossedThresholds'].append(threshold)
                        trade_gate['crossings'].append(dict(targetCompletedTrades=threshold,
                            actualCompletedTrades=trade_gate['completedTradeCount'],
                            revision=state['revision'],eventSequence=event['sequence'],
                            orderId=event['orderId'],eventId=event['eventId'],
                            throughNs=event['detail']['evidence']['timeNs']))
            gate_reached=(trade_gate['completedTradeCount']>=trade_gate['targetCompletedTrades'])
        pending_target=None if result['replay']['exhaustedThroughBoundary'] else advance_target
        used,cpu,ram,current_process_rss,postgres_rss=assert_budgets(root,cluster_root,started)
        progress=dict(status='RUNNING',sessionId=sid,revision=state['revision'],throughNs=state['throughNs'],
                      nextGroupIndex=state['nextGroupIndex'],targetNs=str(advance_target),allocatedBytes=used,
                      cpuSeconds=round(cpu,3),ramBytes=ram,currentProcessRssBytes=current_process_rss,
                      postgresTreeCurrentRssBytes=postgres_rss,retainedOrderCount=len(state['orders']),updatedUnixNs=time.time_ns())
        if trade_gate is not None:
            progress['completedTradeCount']=trade_gate['completedTradeCount']
            progress['tradeCountGateCrossings']=trade_gate['crossings']
        if partial_probe is not None:
            progress['partialCloseProbeStage']=partial_probe['stage']
        memory_sample(root,cluster_root,first_stage or 'replay',state=state,started=started)
        temp=Path(root)/'.progress.tmp';temp.write_text(json.dumps(progress,sort_keys=True)+'\n');os.chmod(temp,0o600);temp.replace(Path(root)/'progress.json')
        if not gate_reached and int(state['throughNs'])>=eod_ns and not state['unresolved']:
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
        if not gate_reached and int(state['throughNs']) < eod_ns and stage in order_decision_stages and current < stage:
            source=controller._source(ObservedExecutionProfile.from_wire(state['profile']))
            selected_plan=None
            if day_hours>=48 and stage>=24 and not TRADE_GRID_V1:
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
        if gate_reached:break


def _all_events(store, scope, sid):
    result=[];offset=0
    while True:
        page=store.inspect(scope,sid,after_sequence=offset,maximum=64)
        events=page['events'];result.extend(events)
        if page['nextEventSequence'] is None:break
        offset=page['nextEventSequence']
    return result


def _logical_order_map(store, scope, sid, state):
    """Build complete order history for offline verification/reporting only."""
    orders={oid:deepcopy(order) for oid,order in state['orders'].items()}
    if state.get('artifact') != STATE_QA_ARCHIVE_V1:
        return orders
    offset=0
    while True:
        page=store.order_history(scope,sid,offset=offset,maximum=256)
        for record in page['records']:
            if record['orderId'] in orders:raise RuntimeError('DUPLICATE_HOT_ARCHIVED_ORDER_ID')
            orders[record['orderId']]=record['order']
        if page['nextOffset'] is None:break
        offset=page['nextOffset']
    if len(orders)!=state['orderArchive']['count']+len(state['orders']):
        raise RuntimeError('ARCHIVE_ORDER_HISTORY_COUNT_MISMATCH')
    return orders


def verify_durable_receipts(dsn, workspace, sid, expected_revision):
    """Independently check every immutable QA command receipt and revision."""
    from execution.postgres import unpack
    with connect(dsn) as db:
        rows=db.execute('SELECT revision,command_id,command_hash,payload,content_hash '
                        'FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                        (workspace,sid)).fetchall()
        checkpoints=db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints '
                               'WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                               (workspace,sid)).fetchall()
    if len(rows)!=expected_revision:raise RuntimeError('INDEPENDENT_RECEIPT_COUNT_MISMATCH')
    checkpoint_wires={revision:unpack(payload,sha) for revision,payload,sha in checkpoints}
    if len(checkpoint_wires)!=expected_revision+1 or 0 not in checkpoint_wires:
        raise RuntimeError('INDEPENDENT_RECEIPT_CHECKPOINT_COUNT_MISMATCH')
    advance_count=0;ledger=[]
    for expected,(revision,command_id,command_hash,payload,receipt_hash) in enumerate(rows,1):
        result=unpack(payload,receipt_hash)
        if revision!=expected or result.get('commandId')!=command_id or result.get('commandHash')!=command_hash:
            raise RuntimeError('INDEPENDENT_RECEIPT_IDENTITY_MISMATCH')
        if result.get('artifact')==QA3_RESULT:
            checkpoint=checkpoint_wires.get(revision,{})
            if (result.get('stateRevision')!=revision or checkpoint.get('revision')!=revision or
                    result.get('stateHash')!=checkpoint.get('stateHash') or
                    result.get('chainHash')!=checkpoint.get('chainHash') or result.get('durable') is not True):
                raise RuntimeError('INDEPENDENT_COMPACT_RECEIPT_CHECKPOINT_MISMATCH')
        elif result.get('durable') is not True or result.get('state',{}).get('revision')!=revision:
            raise RuntimeError('INDEPENDENT_RECEIPT_STATE_MISMATCH')
        if command_id.startswith('advance:'):
            advance_count+=1
            if result.get('replay') is None:raise RuntimeError('INDEPENDENT_ADVANCE_RECEIPT_MISMATCH')
        elif result.get('replay') is not None:
            raise RuntimeError('INDEPENDENT_NONADVANCE_RECEIPT_MISMATCH')
        ledger.append(dict(revision=revision,commandId=command_id,commandHash=command_hash,receiptHash=receipt_hash))
    return dict(status='PASS',commands=len(rows),advanceCommands=advance_count,
                ledgerHashFormat='BTL-INDEPENDENT-COMMAND-LEDGER-2-STREAM',
                ledgerSha256=_hash_canonical_records('BTL-INDEPENDENT-COMMAND-LEDGER-2-STREAM',ledger))


def independent_verify(source, store, scope, sid, start_ns, end_ns, *, gap_threshold_ns=60*S,
                       order_retention_policy=None):
    state=store.inspect(scope,sid)['state'];events=_all_events(store,scope,sid)
    validate_state(state,order_retention_policy=order_retention_policy)
    orders=_logical_order_map(store,scope,sid,state)
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
                evidence=fill['detail']['evidence'];order=orders[fill['orderId']]
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
        if event['detail'].get('commission','0')!='0':
            raise RuntimeError('ZERO_COMMISSION_MODEL_FILL_MISMATCH')
        if event['kind']=='EXIT_FILL':exact_total+=Fraction(event['detail']['grossPosted'])
    if Fraction(state['balance'])!=Fraction(state['initialBalance'])+exact_total:
        raise RuntimeError('INDEPENDENT_CASH_RECONCILIATION_MISMATCH')
    if Fraction(state['realizedGross'])!=exact_total:raise RuntimeError('INDEPENDENT_REALIZED_GROSS_MISMATCH')
    completed=0;reconciled_trades=[];trade_audit=[]
    profile_wire=state['profile'];contract_size=Fraction(profile_wire['contractSize'])
    money_scale=int(profile_wire['moneyScale']);money_quantum=Decimal(1).scaleb(-money_scale)
    for oid,order in orders.items():
        history=by_order.get(oid,[])
        entries=[e for e in history if e['kind']=='ENTRY_FILL']
        exits=[e for e in history if e['kind']=='EXIT_FILL']
        if order['status']=='CLOSED':
            if len(entries)!=1 or not exits:raise RuntimeError('INDEPENDENT_COMPLETED_TRADE_CARDINALITY:'+oid)
            entry=entries[0];entry_detail=entry['detail']
            exit_quantity=sum((Fraction(e['detail']['quantity']) for e in exits),Fraction(0))
            exit_gross=sum((Fraction(e['detail']['grossPosted']) for e in exits),Fraction(0))
            if (entry_detail['price']!=order['entryPrice'] or entry_detail['quantity']!=order['quantity'] or
                    order['entryFillRef']!=entry['eventId']):
                raise RuntimeError('INDEPENDENT_TRADE_ENTRY_MISMATCH:'+oid)
            if exit_quantity!=Fraction(order['quantity']) or exit_gross!=Fraction(order['grossPosted']) or order['remaining']!='0':
                raise RuntimeError('INDEPENDENT_TRADE_EXIT_OR_PNL_MISMATCH:'+oid)
            cumulative_exit=Fraction(0);trade_exits=[]
            for exit_event in exits:
                detail=exit_event['detail'];size=Fraction(detail['quantity'])
                exact_pnl=(Fraction(detail['price'])-Fraction(entry_detail['price'])) * \
                    (1 if order['side']=='LONG' else -1) * contract_size * size
                if Fraction(detail['grossExact'])!=exact_pnl:
                    raise RuntimeError('INDEPENDENT_TRADE_GROSS_EXACT_MISMATCH:'+oid)
                posted=(Decimal(exact_pnl.numerator)/Decimal(exact_pnl.denominator)).quantize(
                    money_quantum,rounding=ROUND_HALF_EVEN)
                # Compare monetary values, not decimal spelling: the kernel's
                # canonical text strips insignificant trailing zeroes (e.g.
                # "0.5"), while Decimal.quantize may produce "0.50".
                if Fraction(detail['grossPosted'])!=Fraction(posted):
                    raise RuntimeError('INDEPENDENT_TRADE_GROSS_POSTED_MISMATCH:'+oid)
                if detail['entryFillRef']!=entry['eventId']:
                    raise RuntimeError('INDEPENDENT_TRADE_EXIT_ENTRY_LINK_MISMATCH:'+oid)
                cumulative_exit+=size
                if Fraction(detail['remaining'])!=Fraction(order['quantity'])-cumulative_exit:
                    raise RuntimeError('INDEPENDENT_TRADE_REMAINING_QUANTITY_MISMATCH:'+oid)
                trade_exits.append(dict(eventId=exit_event['eventId'],sequence=exit_event['sequence'],
                    timeNs=detail['evidence']['timeNs'],price=detail['price'],quantity=detail['quantity'],
                    grossExact=detail['grossExact'],grossPosted=detail['grossPosted'],
                    remaining=detail['remaining'],reason=detail['reason'],
                    bid=detail['evidence']['bid'],ask=detail['evidence']['ask'],
                    groupId=detail['evidence']['groupId'],sourceEventIds=detail['evidence']['eventIds']))
            completed+=1
            reconciled_trades.append(dict(orderId=oid,entryEventId=entry['eventId'],
                exitEventIds=[e['eventId'] for e in exits],entryTimeNs=entry_detail['evidence']['timeNs'],
                exitTimeNs=exits[-1]['detail']['evidence']['timeNs'],quantity=order['quantity'],
                entryPrice=order['entryPrice'],exitGrossPosted=text(exit_gross),status=order['status']))
            trade_audit.append(dict(orderId=oid,side=order['side'],orderType=order['orderType'],
                entry=dict(eventId=entry['eventId'],sequence=entry['sequence'],timeNs=entry_detail['evidence']['timeNs'],
                    price=entry_detail['price'],quantity=entry_detail['quantity'],
                    bid=entry_detail['evidence']['bid'],ask=entry_detail['evidence']['ask'],
                    groupId=entry_detail['evidence']['groupId'],sourceEventIds=entry_detail['evidence']['eventIds']),
                exits=trade_exits,quantity=order['quantity'],grossPosted=text(exit_gross),
                status=order['status'],commissionModel='NONE',commission='0'))
        elif order['status'] in ('CLOSED','ACTIVE','UNRESOLVED') and entries and len(entries)!=1:
            raise RuntimeError('INDEPENDENT_ORDER_ENTRY_CARDINALITY:'+oid)
    if state.get('artifact')==STATE_QA_ARCHIVE_V1:
        accepted={e['orderId'] for e in events if e['kind']=='ORDER_ACCEPTED'}
        if accepted!=set(orders):raise RuntimeError('INDEPENDENT_ARCHIVE_ACCEPTED_ORDER_SET_MISMATCH')
        if state['commission']!='0':raise RuntimeError('ZERO_COMMISSION_MODEL_RECONCILIATION_MISMATCH')
    partial_close_events=[e for e in fills if e['kind']=='EXIT_FILL' and e['detail']['remaining']!='0']
    return dict(status='PASS',independentSourceTicks=seen,independentTimestampGroups=groups,
                independentlyMatchedFills=matched,entryFills=fill_count['ENTRY_FILL'],exitFills=fill_count['EXIT_FILL'],
                reconciledGross=format(exact_total,'f'),reconciledBalance=state['balance'],
                eventChainHead=state['eventHash'],firstSourceQuoteNs=first_quote_ns,lastSourceQuoteNs=last_quote_ns,
                sourceObservedGaps=source_gaps,sourceConsistentOrderOrdering='PASS',
                completedTradeCount=completed,
                tradeDetailsHashFormat='BTL-QA-CP6A7-COMPLETED-TRADES-2-STREAM',
                tradeDetailsSha256=_hash_canonical_records('BTL-QA-CP6A7-COMPLETED-TRADES-2-STREAM',reconciled_trades),
                tradeAudit=trade_audit,
                tradeAuditHashFormat='BTL-QA-CP6A7-TRADE-AUDIT-2-STREAM',
                tradeAuditSha256=_hash_canonical_records('BTL-QA-CP6A7-TRADE-AUDIT-2-STREAM',trade_audit),
                partialCloseExitCount=len(partial_close_events),
                partialCloseOrderIds=sorted({e['orderId'] for e in partial_close_events}),
                tradeFinancialReconciliation='PASS')


def worker(dsn, root, source_path, proof_path, proof_hash, workspace, actor, sid, day_end, decision_targets,
           order_decision_stages, eod_ns, day_hours, order_retention_policy=None, qa_state_delta_v3=False,
           qa_order_archive_v1=False, stop_after_completed_trades=0, partial_probe_state=None):
    global PEAK_RAM,PEAK_ARTIFACT
    os.environ['BTL_TEST_DATABASE_URL']=dsn
    store=ObservedExecutionStore(dsn,order_retention_policy=order_retention_policy,
                                 qa_state_delta_v3=qa_state_delta_v3,qa_order_archive_v1=qa_order_archive_v1)
    with PERF.measured_stage('cold_resume_setup'):
        proof=json.loads(Path(proof_path).read_text())
        with connect(dsn) as db:
            stored=store._read(db,workspace,sid)
        state=stored['state']
        profile=ObservedExecutionProfile.from_wire(state['profile'])
        source=load_source(profile,Path(source_path),Path(proof_path),proof_hash,root/'source-logs')
        PEAK_RAM=max(PEAK_RAM,resource_sample(os.environ['BTL_QA_CLUSTER_ROOT'])[1])
    scope=__import__('application.models',fromlist=['TrustedScope']).TrustedScope(workspace,actor)
    controller=ObservedExecutionController(store,lambda _:source,order_retention_policy=order_retention_policy)
    if partial_probe_state is not None:
        partial_probe_state['observedEvents']=[e for e in _all_events(store,scope,sid)
            if e.get('orderId')==partial_probe_state['orderId']]
        partial_probe_state['stage']=_partial_probe_stage(partial_probe_state['observedEvents'],
                                                            partial_probe_state['orderId'])
        if _advance_partial_probe(controller,store,scope,sid,partial_probe_state,[]):
            state=store.inspect(scope,sid)['state']
    resume_revision=state['revision'];resume_state_hash=content_hash(state)
    start=int(state['startNs']);target=day_end
    trade_gate=(dict(targetCompletedTrades=stop_after_completed_trades,
                     thresholds=[100,500,1000,2000],crossings=[],crossedThresholds=[])
                if stop_after_completed_trades else None)
    with PERF.measured_stage('replay'):
        for _ in advance_until(controller,store,scope,sid,target,root,os.environ['BTL_QA_CLUSTER_ROOT'],
                               float(os.environ['BTL_QA_RUN_STARTED']),decision_targets=decision_targets,
                               order_decision_stages=order_decision_stages,eod_ns=eod_ns,day_hours=day_hours,
                               first_stage='cold_resume_first_command',trade_gate=trade_gate,
                               partial_probe=partial_probe_state):
            pass
    Path(root,'worker-resource.json').write_text(json.dumps(dict(peakRamBytes=PEAK_RAM,
        peakArtifactBytes=PEAK_ARTIFACT,qaStateCache=store.qa_state_cache_stats),sort_keys=True)+'\n')
    os.chmod(Path(root,'worker-resource.json'),0o600)
    Path(root,'worker-performance.json').write_text(json.dumps(PERF.snapshot(),sort_keys=True)+'\n')
    os.chmod(Path(root,'worker-performance.json'),0o600)
    source.close()
    return dict(status='PASS',workerProcessRestarted=True,throughNs=store.inspect(scope,sid)['state']['throughNs'],
                resumeRevision=resume_revision,resumeStateHash=resume_state_hash,
                completedTradeCount=(trade_gate['completedTradeCount'] if trade_gate else None),
                tradeGateReached=(trade_gate['completedTradeCount']>=stop_after_completed_trades
                                  if trade_gate else False),
                tradeCountGateCrossings=(trade_gate['crossings'] if trade_gate else []),
                partialProbeState=partial_probe_state,
                qaStateCache=store.qa_state_cache_stats)


def main_worker():
    PERF.install()
    data=json.loads(os.environ['BTL_HISTORICAL_DAY_V2_WORKER'])
    result=worker(data['dsn'],Path(data['root']),data['source'],data['proof'],data['proofHash'],
                  data['workspace'],data['actor'],data['session'],int(data['dayEnd']),data['decisionTargets'],
                  set(data['orderDecisionStages']),int(data['eodNs']),int(data['dayHours']),
                  data.get('orderRetentionPolicy'),data.get('qaStateDeltaV3',False),
                  data.get('qaOrderArchiveV1',False),data.get('stopAfterCompletedTrades',0),
                  data.get('partialProbeState'))
    Path(data['root'],'worker-result.json').write_text(json.dumps(result,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))


def main():
    global PEAK_RAM,PEAK_ARTIFACT
    PERF.install()
    root_text=os.environ.get('BTL_HISTORICAL_QA_ROOT')
    if not root_text:raise RuntimeError('SET_BTL_HISTORICAL_QA_ROOT_TO_NEW_EMPTY_PATH')
    root=Path(root_text)
    if root.exists():raise RuntimeError('QA_OUTPUT_PATH_MUST_NOT_EXIST')
    disk_free_before=shutil.disk_usage(root.parent if root.parent.exists() else Path('/')).free
    if disk_free_before<MIN_FREE:
        raise RuntimeError('PREFLIGHT_DISK_RESERVE_BELOW_30_GIB')
    if MONTHLY_QA and disk_free_before<MIN_FREE+MAX_ARTIFACT:
        raise RuntimeError('PREFLIGHT_MONTH_BUDGET_WOULD_BREACH_30_GIB_RESERVE')
    root.mkdir(mode=0o700,parents=False)
    os.chmod(root,0o700);tempfile.tempdir=str(root);os.environ['TMPDIR']=str(root)
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    batch_groups=int(os.environ.get('BTL_QA_HISTORICAL_BATCH_GROUPS','64'))
    if batch_groups not in (64,96,128,256):raise RuntimeError('INVALID_QA_HISTORICAL_BATCH_GROUPS')
    os.environ['BTL_QA_HISTORICAL_BATCH_GROUPS']=str(batch_groups)
    day_count=int(os.environ.get('BTL_QA_HISTORICAL_DAYS','1'))
    if day_count not in (1,2,3,7,30):raise RuntimeError('INVALID_QA_HISTORICAL_DAY_COUNT')
    if QA_STATE_DELTA_V3 and day_count != 30:raise RuntimeError('QA_V3_HISTORICAL_PATH_RESERVED_FOR_MONTH_GATE')
    if TRADE_GRID_V1 and (day_count not in (1,30) or not QA_ORDER_ARCHIVE_V1 or
                          (day_count==30 and STOP_AFTER_COMPLETED_TRADES!=2000) or
                          (day_count==1 and STOP_AFTER_COMPLETED_TRADES!=0)):
        raise RuntimeError('QA_TRADE_GRID_REQUIRES_ISOLATED_ARCHIVE_AND_VALID_TRADE_GATE')
    if QA_ORDER_ARCHIVE_V1:os.environ['BTL_ENABLE_QA_ORDER_ARCHIVE_V1']='1'
    if MONTHLY_QA:
        grid_probe=None
        if TRADE_GRID_V1:
            probe_path=os.environ.get('BTL_QA_TRADE_GRID_PREFLIGHT_JSON')
            if not probe_path or not Path(probe_path).is_file():
                raise RuntimeError('TRADE_GRID_MONTH_REQUIRES_MEASURED_PREFLIGHT_JSON')
            grid_probe=json.loads(Path(probe_path).read_text())
            if (grid_probe.get('status')!='PASS' or grid_probe.get('period')!='2024-01-02 UTC' or
                    grid_probe.get('sourceFinancialVerification')!='PASS' or
                    grid_probe.get('partialClose')!='PASS' or
                    int(grid_probe.get('peakRamBytes',MAX_RAM+1))>MAX_RAM or
                    int(grid_probe.get('activeOrderCap',0))!=MAX_ACTIVE_ORDERS or
                    int(grid_probe.get('completedTrades',0))<100):
                raise RuntimeError('TRADE_GRID_PREFLIGHT_EVIDENCE_NOT_ACCEPTED')
            target=int(STOP_AFTER_COMPLETED_TRADES)
            observed_per_day=int(grid_probe['completedTrades'])
            order_count_per_day=int(grid_probe['acceptedOrders'])
            # Require the target to fit with only 60% of the observed daily
            # closed-trade rate. This is a conservative coverage allowance,
            # not a prediction that future days will match January 2.
            projected_days=(target+max(1,int(observed_per_day*0.60))-1)//max(1,int(observed_per_day*0.60))
            projected_orders=projected_days*order_count_per_day
            daily_artifacts=int(grid_probe['totalArtifactBytes'])
            daily_seconds=int(grid_probe['endToEndSeconds'])
            artifact_projection=(daily_artifacts*projected_days*5+3)//4
            runtime_projection=(daily_seconds*projected_days*5+3)//4
            if projected_orders>QA_ORDER_RETENTION_V4['maxCumulativeOrders']:
                raise RuntimeError('TRADE_GRID_ORDER_ARCHIVE_PREflight_LIMIT')
            if artifact_projection>MAX_ARTIFACT or runtime_projection>MAX_WALL:
                raise RuntimeError('TRADE_GRID_PROJECTED_BUDGET_EXCEEDED')
            if disk_free_before-artifact_projection<MIN_FREE:
                raise RuntimeError('TRADE_GRID_PROJECTED_DISK_RESERVE_EXCEEDED')
        preflight=dict(status='PASS',period='2024-01-02..2024-01-31 UTC',continuousDays=30,
            sourceRights='CC-BY-4.0 dataset card; underlying feed authority not independently verified',
            orderLimit=(QA_ORDER_RETENTION_V4 if TRADE_GRID_V1 else
                        QA_ORDER_RETENTION_V3 if QA_ORDER_ARCHIVE_V1 else QA_ORDER_RETENTION_V2)['maxCumulativeOrders'],
            orderCountUpperBound=(179+29*22*8 if TRADE_GRID_V1 else 90+29*22),
            orderCountEmpiricalProjection=(projected_orders if TRADE_GRID_V1 else
                                           round(90+(178-90)/6*29)),
            full30DayMaximumScheduledOrders=(179+29*22*8 if TRADE_GRID_V1 else None),
            full30DayMaximumWouldExceedArchiveLimit=(179+29*22*8>QA_ORDER_RETENTION_V4['maxCumulativeOrders']
                if TRADE_GRID_V1 else False),
            priorSevenDayOrders=178,priorSevenDayArtifactsBytes=722509824,
            measuredTwoDayArtifactsBytes=252645376,measuredTwoDayRuntimeSeconds=1278.426,
            targetTradeCount=STOP_AFTER_COMPLETED_TRADES if TRADE_GRID_V1 else None,
            tradeScenario='OBSERVED_HOURLY_GRID_V1_TWO_PRICE_BANDS' if TRADE_GRID_V1 else None,
            projectedTradeGateDays=(projected_days if TRADE_GRID_V1 else 30),
            measuredGridProbe=grid_probe,
            projectedTradeRateFactor=0.60 if TRADE_GRID_V1 else None,
            projectedArtifactBytesLinear=(daily_artifacts*projected_days if TRADE_GRID_V1 else round(722509824*30/7)),
            projectedArtifactBytesWithMargin=(artifact_projection if TRADE_GRID_V1 else round(722509824*30/7*1.4)),
            projectedRuntimeSecondsLinear=(daily_seconds*projected_days if TRADE_GRID_V1 else round(3272.204*30/7)),
            projectedRuntimeSecondsWithMargin=(runtime_projection if TRADE_GRID_V1 else round(3272.204*30/7*1.25)),
            budgets=dict(artifactBytes=MAX_ARTIFACT,wallSeconds=MAX_WALL,ramBytes=MAX_RAM,
                         vcpuEquivalent=1,diskReserveBytes=MIN_FREE),
            disk=dict(freeBeforeBytes=disk_free_before,
                freeIfFullArtifactBudgetUsedBytes=disk_free_before-MAX_ARTIFACT,
                reserveAfterFullArtifactBudgetBytes=disk_free_before-MAX_ARTIFACT-MIN_FREE),
            annualProjection=dict(artifactBytesApprox=37800000000,
                availableAboveReserveBytes=disk_free_before-MIN_FREE,
                gate='NO_GO_INSUFFICIENT_CURRENT_DISK_HEADROOM'),
            persistenceFormat='QA_ARCHIVE_V1+QA_STATE_DELTA_V3' if QA_ORDER_ARCHIVE_V1 else
                'QA_STATE_DELTA_V3' if QA_STATE_DELTA_V3 else 'LEGACY_FULL_STATE',
            cumulativeOrderPolicy='QA archive v1 + QA retention v4 max4096, active128' if TRADE_GRID_V1 else
                'QA archive v1 max 1024' if QA_ORDER_ARCHIVE_V1 else 'existing QA v2, max 512')
        (root/'preflight.json').write_text(json.dumps(preflight,sort_keys=True,indent=2)+'\n')
        os.chmod(root/'preflight.json',0o600)
    day_hours=24*day_count
    order_retention_policy=(QA_ORDER_RETENTION_V4 if TRADE_GRID_V1 else
                            QA_ORDER_RETENTION_V3 if QA_ORDER_ARCHIVE_V1 else
                            QA_ORDER_RETENTION_V2 if day_count>=3 else None)
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
        timelineStorageMode='shared-source-v1' if os.environ.get('BTL_QA_SHARED_CANONICAL_SOURCE_V1')=='1' else 'session-log-v2',
        tradeScenario='OBSERVED_HOURLY_GRID_V1_TWO_PRICE_BANDS' if TRADE_GRID_V1 else 'ACCEPTED_CP5_DECISION_SCHEDULE',
        ordersPerHourlyDecision=8 if TRADE_GRID_V1 else 1,
        stopAfterCompletedTrades=STOP_AFTER_COMPLETED_TRADES if TRADE_GRID_V1 else None,
        persistenceFormat='QA_ARCHIVE_V1+QA_STATE_DELTA_V3' if QA_ORDER_ARCHIVE_V1 else
            'QA_STATE_DELTA_V3' if QA_STATE_DELTA_V3 else 'LEGACY_FULL_STATE',
        firstDayOrderStages=sorted(range(0,22)),
        additionalDayOrderStages=[sorted(range(d*24,d*24+22)) for d in range(1,day_count)],
        orderRetentionPolicy=order_retention_policy or dict(schemaVersion=1,artifact='BTL-ORDER-RETENTION-V1',maxCumulativeOrders=MAX_ORDERS),
        maxCumulativeOrders=(order_retention_policy or {}).get('maxCumulativeOrders',MAX_ORDERS),
        additionalDayOrdersPerDecision=8 if TRADE_GRID_V1 else 1 if day_count>1 else None,
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
        store=ObservedExecutionStore(dsn,order_retention_policy=order_retention_policy,
                                     qa_state_delta_v3=USE_QA_STATE_DELTA_V3,
                                     qa_order_archive_v1=QA_ORDER_ARCHIVE_V1)
        scope=__import__('application.models',fromlist=['TrustedScope']).TrustedScope(workspace,actor)
        controller=ObservedExecutionController(store,lambda _:source,order_retention_policy=order_retention_policy)
        initial=controller.create(scope,session,profile,method,period=PERIOD,day=DAY,balance='10000')
        initial_state_bytes=len(canonical_bytes(initial))
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
        partial_probe_state=None
        if TRADE_GRID_V1:
            partial_probe_id='order:far:cp6a7-partial-probe'
            state=store.inspect(scope,session)['state'];basis=state['quoteBasis']
            entry=Decimal(basis['ask'])+Decimal('0.001')
            controller.apply(scope,command(session,'order:far:cp6a7-partial-probe',state['revision'],'OPEN',
                dict(side='LONG',orderType='STOP',workflow='PLANNED',entry=format(entry,'f'),quantity='0.02',
                     sl=format(entry-Decimal('50'),'f'),tp=format(entry+Decimal('50'),'f'),
                     riskPercent='1',observations=[])))
            partial_probe_state=dict(orderId=partial_probe_id,stage='WAIT_ENTRY',observedEvents=[])
        # Durable progress before a real worker process restart.
        resume_target=start+(24*3600*S-1 if day_count>=2 else 4*3600*S)
        with PERF.measured_stage('replay'):
            for _ in advance_until(controller,store,scope,session,resume_target,root,root/'postgres',started,
                                   decision_targets=decision_targets,order_decision_stages=order_decision_stages,
                                   eod_ns=eod_ns,day_hours=day_hours,partial_probe=partial_probe_state):pass
        before_restart=store.inspect(scope,session)['state']
        memory_sample(root,root/'postgres','before_cold_resume',state=before_restart,started=started)
        source.close()
        worker_data=dict(dsn=dsn,root=str(root),source=str(SOURCE),proof=str(PROOF),proofHash=proof_hash,
                         workspace=workspace,actor=actor,session=session,dayEnd=day_end,
                         decisionTargets=decision_targets,orderDecisionStages=sorted(order_decision_stages),
                         eodNs=eod_ns,dayHours=day_hours,orderRetentionPolicy=order_retention_policy,
                         qaStateDeltaV3=USE_QA_STATE_DELTA_V3,qaOrderArchiveV1=QA_ORDER_ARCHIVE_V1,
                         stopAfterCompletedTrades=STOP_AFTER_COMPLETED_TRADES,
                         partialProbeState=({k:partial_probe_state[k] for k in ('orderId','stage')}
                                            if partial_probe_state else None))
        env=dict(os.environ,BTL_HISTORICAL_DAY_V2_WORKER=json.dumps(worker_data),
                 BTL_TEST_DATABASE_URL=dsn,BTL_QA_CLUSTER_ROOT=str(root/'postgres'),
                 BTL_QA_RUN_STARTED=str(started),PYTHONDONTWRITEBYTECODE='1')
        proc=subprocess.run([sys.executable,'-B','-m','tests.qa_historical_day_v2','--worker'],cwd=repository,
                            env=env,capture_output=True,text=True,timeout=max(1,int(MAX_WALL-(time.monotonic()-started))))
        if proc.returncode!=0:raise RuntimeError('COLD_RESUME_WORKER_FAILED:'+proc.stderr[-2000:])
        worker_result=json.loads(Path(root,'worker-result.json').read_text())
        state=store.inspect(scope,session)['state']
        trade_gate_reached=worker_result.get('tradeGateReached',False)
        if int(state['throughNs'])<day_end and not trade_gate_reached:
            raise RuntimeError('UTC_DAY_BOUNDARY_NOT_REACHED')
        verification_end=int(state['throughNs'])
        final=source=load_source(profile,SOURCE,PROOF,proof_hash,root/'source-logs-independent')
        source.assert_current()
        with PERF.measured_stage('independent_verification'):
            verification=independent_verify(source,store,scope,session,start,verification_end,
                                            order_retention_policy=order_retention_policy)
            receipt_verification=verify_durable_receipts(dsn,scope.workspace_id,session,state['revision'])
        source.assert_current()
        source.close()
        memory_sample(root,root/'postgres','independent_verification_complete',state=state,started=started)
        events=_all_events(store,scope,session)
        with connect(dsn) as db:
            receipt_rows=db.execute('SELECT revision,command_id,command_hash,content_hash FROM btl.tick_commands '
                                    'WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                                    (scope.workspace_id,session)).fetchall()
        event_transcript_hash=_hash_canonical_records('BTL-OBSERVED-EVENT-TRANSCRIPT-2-STREAM',
            (e['eventId'] for e in events))
        receipt_ledger_hash=_hash_canonical_records('BTL-OBSERVED-RECEIPT-LEDGER-2-STREAM',
            (dict(revision=r[0],commandId=r[1],commandHash=r[2],receiptHash=r[3]) for r in receipt_rows))
        semantic_events=[]
        for event in events:
            if event['kind']=='REPLAY_ADVANCED':continue
            detail=dict(event['detail']);detail.pop('entryFillRef',None)
            semantic_events.append(dict(kind=event['kind'],classification=event['classification'],
                                        orderId=event['orderId'],detail=detail))
        if len(semantic_events)<=1000:
            semantic_event_hash=hashlib.sha256(canonical_bytes(dict(schemaVersion=1,
                artifact='BTL-OBSERVED-FINANCIAL-TRANSCRIPT-1',events=semantic_events))).hexdigest()
            semantic_event_hash_format='BTL-OBSERVED-FINANCIAL-TRANSCRIPT-1'
        else:
            semantic_event_hash=_hash_canonical_records('BTL-OBSERVED-FINANCIAL-TRANSCRIPT-2-STREAM',semantic_events)
            semantic_event_hash_format='BTL-OBSERVED-FINANCIAL-TRANSCRIPT-2-STREAM'
        logical_orders=_logical_order_map(store,scope,session,state)
        financial_state_hash_format,financial_state_hash=_financial_state_digest(state,logical_orders)
        observed_orders={oid:{'side':o['side'],'orderType':o['orderType'],'status':o['status'],'entryPrice':o['entryPrice'],
                              'remaining':o['remaining']} for oid,o in sorted(logical_orders.items())}
        order_types=Counter(o['orderType'] for o in logical_orders.values())
        statuses=Counter(o['status'] for o in logical_orders.values())
        kinds=Counter(e['kind'] for e in events)
        gap_events=[e for e in events if e['kind']=='DATA_GAP_LIMITATION']
        order_acceptance_events=[e for e in events if e['kind']=='ORDER_ACCEPTED']
        accepted_order_ids={e['orderId'] for e in order_acceptance_events}
        retained_order_ids=set(logical_orders)
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
        qa_cache_stats=worker_result.get('qaStateCache')
        if QA_STATE_DELTA_V3 and (not qa_cache_stats or qa_cache_stats.get('fullReconstructions',0)<1
                                  or qa_cache_stats.get('misses',0)<1 or qa_cache_stats.get('hits',0)<1):
            raise RuntimeError('QA_V3_COLD_CACHE_MISS_RECONSTRUCTION_OR_WARM_HIT_NOT_PROVEN')
        if QA_ORDER_ARCHIVE_V1 and (not qa_cache_stats or qa_cache_stats.get('fullReconstructions',0)<1
                                    or qa_cache_stats.get('misses',0)<1):
            raise RuntimeError('QA_ARCHIVE_COLD_STATE_RECONSTRUCTION_NOT_PROVEN')
        phase_metrics=PERF.merge(PERF.snapshot(),worker_phases)
        command_latency_samples=phase_metrics.pop('_commandLatencySamplesNs',{})
        replay_wall=sum(row.get('wallNs',0) for name,phases in phase_metrics.items()
                        if name=='replay' for key,row in phases.items() if key=='stage.wall')/1e9
        verify_wall=phase_metrics.get('independent_verification',{}).get('stage.wall',{}).get('wallNs',0)/1e9
        pg_prepare=sum(row.get('wallNs',0) for phases in phase_metrics.values() for key,row in phases.items() if key=='postgres.prepare')/1e9
        pg_commit=sum(row.get('wallNs',0) for phases in phase_metrics.values() for key,row in phases.items() if key=='postgres.commit')/1e9
        replay_apply=sum(row.get('wallNs',0) for name,phases in phase_metrics.items()
                         if name in ('replay','cold_resume_first_command') for key,row in phases.items() if key=='command.total')/1e9
        with connect(dsn) as db:postgres_db_bytes=int(db.execute('SELECT pg_database_size(current_database())').fetchone()[0])
        timeline_files=[]
        for timeline_path in sorted((root/'source-logs').rglob('timeline.sqlite')):
            stat=timeline_path.stat()
            timeline_files.append(dict(path=str(timeline_path.relative_to(root)),
                allocatedBytes=stat.st_blocks*512,logicalBytes=stat.st_size))
        timeline_allocated=sum(item['allocatedBytes'] for item in timeline_files)
        actual_end_date=datetime.fromtimestamp(verification_end//S,timezone.utc).strftime('%Y-%m-%d')
        actual_days=((verification_end-start)//(86400*S))+1
        summary=dict(status='PASS',classification=profile.wire['executionLabel'],
            executionModel=profile.wire['model'],
            executionEligibility='NOT_GRANTED',technicalSimulationEligibility='PASS',sourceRights='UNKNOWN',
            persistenceFormat='QA_ARCHIVE_V1+QA_STATE_DELTA_V3' if QA_ORDER_ARCHIVE_V1 else
                'QA_STATE_DELTA_V3' if QA_STATE_DELTA_V3 else 'LEGACY_FULL_STATE',
            qaStateCache=dict(worker=qa_cache_stats,parent=store.qa_state_cache_stats),
            costAssumptions=dict(bidAsk='observed source Bid/Ask applied by execution model',
                commissionModel=profile.wire['commissionModel'],
                commissionPerLotSide=profile.wire['commissionPerLotSide'],
                slippageModel=profile.wire['slippageModel'],latencyModel=profile.wire['latencyModel']),
            sourceProvenance='PROVIDER_OBSERVATION',datasetId=profile.wire['primary']['datasetId'],
            datasetVersion=profile.wire['primary']['datasetVersion'],qualificationReceiptSha256=proof_hash,
            archiveSha256=proof['snapshotSha256'],period=DAY if actual_days==1 else DAY+'/'+actual_end_date,
            timelineStorageMode='shared-source-v1' if os.environ.get('BTL_QA_SHARED_CANONICAL_SOURCE_V1')=='1' else 'session-log-v2',
            sharedSourceBinding=(source.source_pin if os.environ.get('BTL_QA_SHARED_CANONICAL_SOURCE_V1')=='1' else None),
            dayStartNs=str(start),dayEndNs=str(verification_end),requestedPeriodEndNs=str(day_end),continuousDays=actual_days,
            firstSourceQuoteNs=verification['firstSourceQuoteNs'],lastSourceQuoteNs=verification['lastSourceQuoteNs'],
            tickCount=verification['independentSourceTicks'],timestampGroupCount=verification['independentTimestampGroups'],
            gapCount=len(gap_events),gapKinds=dict(Counter(e['detail']['gapKind'] for e in gap_events)),
            sourceObservedGaps=verification['sourceObservedGaps'],
            unknownCoverageGapCount=sum(g['kind']=='UNKNOWN_COVERAGE_GAP' for g in verification['sourceObservedGaps']),
            stateGrowth=dict(initialCanonicalBytes=initial_state_bytes,finalCanonicalBytes=len(canonical_bytes(state))),
            commandCount=state['revision'],eventCount=len(events),orderTypeCounts=dict(order_types),
            orderStatusCounts=dict(statuses),eventKinds=dict(kinds),orders=observed_orders,
            cumulativeOrderHistory=dict(status='PASS',retainedOrderCount=len(retained_order_ids),
                terminalArchivedOrderCount=state.get('orderArchive',{}).get('count',0),
                activeHotOrderCount=len(state['orders']),
                maximumRetainedOrders=max_retained_orders,durableOrderAcceptedEvents=len(accepted_order_ids),
                noHistoricalOrderPruning=True,allOrderIdsMatchState=True),
            startingBalance=state['initialBalance'],endingBalance=state['balance'],
            realizedGross=state['realizedGross'],independentVerification=verification,
            targetCompletedTrades=STOP_AFTER_COMPLETED_TRADES or None,
            completedTradeCount=verification['completedTradeCount'],
            tradeCountGateCrossings=worker_result.get('tradeCountGateCrossings',[]),
            parity=dict(eventTranscriptHashFormat='BTL-OBSERVED-EVENT-TRANSCRIPT-2-STREAM',
                        eventTranscriptSha256=event_transcript_hash,
                        receiptLedgerHashFormat='BTL-OBSERVED-RECEIPT-LEDGER-2-STREAM',
                        receiptLedgerSha256=receipt_ledger_hash,
                        semanticEventHashFormat=semantic_event_hash_format,
                        semanticFinancialEventSha256=semantic_event_hash,
                        financialStateHashFormat=financial_state_hash_format,financialStateSha256=financial_state_hash,
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
                independentFullVerificationWallSeconds=round(verify_wall,3),
                commandLatencyMs=dict(replay=_command_latency_summary(command_latency_samples.get('replay',[])),
                    coldResumeFirstCommand=_command_latency_summary(command_latency_samples.get('cold_resume_first_command',[])))),
            storage=dict(postgresDatabaseBytes=postgres_db_bytes,postgresClusterAllocatedBytes=allocated(root/'postgres'),
                perSessionTimelineAllocatedBytes=timeline_allocated,perSessionTimelineFiles=timeline_files,
                totalQaArtifactBytes=allocated(root)),
            measured=dict(elapsedSeconds=round(time.monotonic()-started,3),cpuSeconds=round(resource_sample(root/'postgres')[0]-metrics['cpuStart'],3),
                          peakRamBytes=max(PEAK_RAM,worker_resource.get('peakRamBytes',0),memory_summary['peakCapMethodSampleBytes']),peakArtifactBytes=max(PEAK_ARTIFACT,worker_resource.get('peakArtifactBytes',0),allocated(root)),
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
            partialCloseExitEvents=verification['partialCloseExitCount'],
            endingBalance=state['balance'],realizedGross=state['realizedGross'])
        if day_count==1 and not TRADE_GRID_V1:
            expected=decision_fixture['baselineResults']
            # This runner now reports the partial-exit count explicitly. The
            # accepted decision schedule has no partial-close probe; require
            # zero when the older pinned golden omits this measurement.
            expected_match=all(actual.get(key)==value for key,value in expected.items()) and \
                actual['partialCloseExitEvents']==expected.get('partialCloseExitEvents',0)
            if (semantic_event_hash!=decision_fixture['baselineSemanticFinancialEventSha256'] or
                financial_state_hash!=decision_fixture['baselineFinancialStateSha256'] or not expected_match):
                summary['status']='FAIL';summary['acceptanceFailure']='CANONICAL_FINANCIAL_PARITY_MISMATCH'
                summary['baselineParityExpected']=expected;summary['candidateParityActual']=actual
        else:
            summary['multiDayFinancialResult']=actual
            if len(retained_order_ids)>max_retained_orders:
                summary['status']='FAIL';summary['acceptanceFailure']='CUMULATIVE_ORDER_LIMIT_EXCEEDED'
        if STOP_AFTER_COMPLETED_TRADES and verification['completedTradeCount']<STOP_AFTER_COMPLETED_TRADES:
            summary['status']='FAIL';summary['acceptanceFailure']='COMPLETED_TRADE_GATE_NOT_REACHED'
        if STOP_AFTER_COMPLETED_TRADES:
            missing=[n for n in (100,500,1000,2000)
                     if n not in {x['targetCompletedTrades'] for x in summary['tradeCountGateCrossings']}]
            if missing:
                summary['status']='FAIL';summary['acceptanceFailure']='TRADE_COUNT_GATE_CROSSING_MISSING'
                summary['missingTradeCountGates']=missing
        if TRADE_GRID_V1:
            probe_id='order:far:cp6a7-partial-probe'
            probe=next((t for t in verification['tradeAudit'] if t['orderId']==probe_id),None)
            partial_exits=(probe or {}).get('exits',[])
            probe_ok=(worker_result.get('partialProbeState',{}).get('stage')=='DONE' and probe is not None and
                      len(partial_exits)==2 and
                      [(x['quantity'],x['remaining'],x['reason']) for x in partial_exits]==
                      [('0.01','0.01','MANUAL'),('0.01','0','MANUAL')])
            summary['partialCloseProbe']=dict(status='PASS' if probe_ok else 'FAIL',orderId=probe_id,
                orderState=(worker_result.get('partialProbeState',{}).get('stage')),
                entryQuantity=probe['entry']['quantity'] if probe else None,
                exits=[{k:x.get(k) for k in ('eventId','timeNs','price','quantity','grossPosted','remaining','reason')}
                       for x in partial_exits])
            if not probe_ok:
                summary['status']='FAIL';summary['acceptanceFailure']='REAL_SOURCE_PARTIAL_CLOSE_PROBE_FAILED'
        report=root/'report.json';report.write_text(json.dumps(summary,indent=2,sort_keys=True,ensure_ascii=False)+'\n');report.chmod(0o600)
        metrics['peakArtifact']=allocated(root)
        assert_budgets(root,root/'postgres',started)
        (root/'resource-final.json').write_text(json.dumps(dict(cpuSeconds=summary['measured']['cpuSeconds'],
            peakRamBytes=metrics['peakRam'],peakArtifactBytes=allocated(root),freeBytes=shutil.disk_usage(root).free),sort_keys=True)+'\n')
        os.chmod(root/'resource-final.json',0o600)
        if TRADE_GRID_V1:
            print(json.dumps({k:summary.get(k) for k in ('status','period','tickCount','completedTradeCount',
                'targetCompletedTrades','endingBalance','realizedGross','acceptanceFailure','measured','storage')},
                sort_keys=True,ensure_ascii=False))
        else:
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
