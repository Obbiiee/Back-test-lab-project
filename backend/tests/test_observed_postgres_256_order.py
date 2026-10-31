"""Bounded legacy-vs-QA-v3 PostgreSQL scale gate for 256 durable orders."""
import hashlib
import json
import os
from pathlib import Path
import cProfile
import pstats
import signal
import shutil
import subprocess
import sys
import time
import unittest
import uuid

from contracts.canonical import canonical_bytes, content_hash
from application.models import TrustedScope
from execution.observed_controller import ObservedExecutionController
from execution.observed_kernel import QA_ORDER_RETENTION_V2, validate_state
from execution.observed_postgres import ObservedExecutionStore, QA3_RESULT, unpack
from infrastructure.database import connect
from tests import test_observed_postgres as pg_fixtures
from tests.qa_historical_day_v2 import allocated, resource_sample

MAX_ORDERS = 256
MAX_WALL_SECONDS = 900
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_RAM_BYTES = 1024 * 1024 * 1024
MIN_FREE_BYTES = 30 * 1024 * 1024 * 1024


def _allocated_wal():
    root = Path(os.environ['BTL_QA_CLUSTER_ROOT']) / 'data' / 'pg_wal'
    return sum(p.stat().st_blocks * 512 for p in root.rglob('*') if p.is_file())


def _guard(root, started):
    if time.monotonic() - started > MAX_WALL_SECONDS:
        raise RuntimeError('RESOURCE_STOP_WALL_15_MINUTES')
    if shutil.disk_usage(root).free < MIN_FREE_BYTES:
        raise RuntimeError('RESOURCE_STOP_DISK_RESERVE_30_GIB')
    artifact_bytes = allocated(root)
    if artifact_bytes > MAX_ARTIFACT_BYTES:
        raise RuntimeError('RESOURCE_STOP_ARTIFACT_512_MIB')
    cpu, ram, *_ = resource_sample(os.environ['BTL_QA_CLUSTER_ROOT'])
    if ram > MAX_RAM_BYTES:
        raise RuntimeError('RESOURCE_STOP_RAM_1_GIB')
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None
    if affinity is not None and len(affinity) != 1:
        raise RuntimeError('RESOURCE_STOP_CPU_AFFINITY_NOT_ONE_CORE')
    return dict(cpuSeconds=round(cpu, 3), capRssBytes=ram, artifactBytes=artifact_bytes,
                freeDiskBytes=shutil.disk_usage(root).free, cpuAffinity=affinity)


def _measure_db(dsn, workspace, session):
    with connect(dsn) as db:
        db_bytes = int(db.execute('SELECT pg_database_size(current_database())').fetchone()[0])
        tables = {}
        for table in ('tick_sessions', 'tick_checkpoints', 'tick_commands', 'tick_events'):
            tuple_bytes, payload_bytes, rows = db.execute(
                f'SELECT coalesce(sum(pg_column_size(t)),0), '
                f'coalesce(sum(octet_length(t.payload)),0), count(*) '
                f'FROM btl.{table} AS t WHERE workspace_id=%s AND session_id=%s',
                (workspace, session)).fetchone()
            tables[table] = dict(tupleBytes=int(tuple_bytes), payloadBytes=int(payload_bytes), rows=int(rows))
        receipts = [int(row[0]) for row in db.execute(
            'SELECT octet_length(payload) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
            (workspace, session)).fetchall()]
        checkpoints = [int(row[0]) for row in db.execute(
            'SELECT octet_length(payload) FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
            (workspace, session)).fetchall()]
        return dict(databaseBytes=db_bytes, tables=tables, receiptPayloadBytes=receipts,
                    checkpointPayloadBytes=checkpoints)


def _lsn():
    with connect(pg_fixtures.DSN) as db:
        return db.execute('SELECT pg_current_wal_lsn()').fetchone()[0]


def _lsn_diff(start, end):
    with connect(pg_fixtures.DSN) as db:
        return int(db.execute('SELECT pg_wal_lsn_diff(%s,%s)', (end, start)).fetchone()[0])


def _make_commands(session, state, count):
    def cmd(cid, revision, kind, payload=None):
        return dict(schemaVersion=1, artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',
                    sessionId=session, commandId=cid, expectedRevision=revision,
                    kind=kind, payload=payload or {})

    commands = [cmd('seed:quote:0', state['revision'], 'ADVANCE', {'targetNs': '0'})]
    # Build each pending order only from the first observed quote. The four
    # far-away LIMIT/STOP levels remain untriggered by the fixture's later
    # quotes, so every lifecycle is accepted then explicitly cancelled.
    revision = 1
    for number in range(1, count + 1):
        side, order_type = (('LONG', 'LIMIT'), ('SHORT', 'LIMIT'),
                            ('LONG', 'STOP'), ('SHORT', 'STOP'))[(number - 1) % 4]
        if side == 'LONG' and order_type == 'LIMIT':
            entry, sl, tp = '2290', '2289', '2291'
        elif side == 'SHORT' and order_type == 'LIMIT':
            entry, sl, tp = '2310', '2311', '2309'
        elif side == 'LONG':
            entry, sl, tp = '2310', '2309', '2311'
        else:
            entry, sl, tp = '2290', '2291', '2289'
        cid = f'order:scale:{number:04d}'
        payload = dict(side=side, orderType=order_type, workflow='PLANNED', entry=entry,
                       quantity='0.01', sl=sl, tp=tp, riskPercent='1', observations=[])
        commands.append(cmd(cid, revision, 'OPEN', payload)); revision += 1
        commands.append(cmd(f'cancel:scale:{number:04d}', revision, 'CANCEL', {'orderId': cid})); revision += 1
    return commands


class ObservedDeltaV3OrderScaleTests(pg_fixtures.ObservedPostgresTests):
    def test_256_order_legacy_vs_qa_v3_with_cold_resume_and_post_commit_kill(self):
        from execution.observed_state_delta_v3 import reconstruct_complete
        import psycopg

        root = Path(os.environ['BTL_QA_DELTA_V3_SCALE_ROOT'])
        started = time.monotonic()
        suffix = uuid.uuid4().hex[:10]
        session = 'session:scale256:' + suffix
        legacy_scope = TrustedScope('observedqa:' + uuid.uuid4().hex, self.scope.actor_ref)
        compact_scope = TrustedScope('observedqa:' + uuid.uuid4().hex, self.scope.actor_ref)
        legacy_dsn = pg_fixtures.isolated_database(pg_fixtures.DSN, 'cp6a4_l256_' + suffix)
        compact_dsn = pg_fixtures.isolated_database(pg_fixtures.DSN, 'cp6a4_v256_' + suffix)
        legacy_store = ObservedExecutionStore(legacy_dsn, order_retention_policy=QA_ORDER_RETENTION_V2)
        compact_store = ObservedExecutionStore(compact_dsn, order_retention_policy=QA_ORDER_RETENTION_V2,
                                               qa_state_delta_v3=True)
        legacy = ObservedExecutionController(legacy_store, lambda _: self.source,
                                             order_retention_policy=QA_ORDER_RETENTION_V2)
        compact = ObservedExecutionController(compact_store, lambda _: self.source,
                                              order_retention_policy=QA_ORDER_RETENTION_V2)
        for controller, scope in ((legacy, legacy_scope), (compact, compact_scope)):
            controller.create(scope, session, self.fx.profile, self.fx.policy,
                              period='1970-01', balance='10000')

        def db_bytes(dsn):
            with connect(dsn) as db:
                return int(db.execute('SELECT pg_database_size(current_database())').fetchone()[0])

        legacy_before = db_bytes(legacy_dsn)
        legacy_lsn_before = _lsn()
        initial = legacy.inspect(legacy_scope, session)['state']
        commands = _make_commands(session, initial, MAX_ORDERS)
        # Guard repeatedly while the baseline is being written; QA-v3 then uses
        # exactly the same serialized command bytes and a separate database.
        legacy_hashes = []
        legacy_timings = []
        seed_result = legacy.apply(legacy_scope, commands[0])
        legacy_hashes.append(hashlib.sha256(canonical_bytes(seed_result)).hexdigest())
        legacy_timings.append(0.0)
        for index, raw in enumerate(commands[1:], 1):
            t = time.perf_counter(); result = legacy.apply(legacy_scope, raw)
            legacy_timings.append(time.perf_counter() - t)
            legacy_hashes.append(hashlib.sha256(canonical_bytes(result)).hexdigest())
            if index % 16 == 0:
                _guard(root, started)
        legacy_final = legacy.inspect(legacy_scope, session)['state']
        legacy_after = db_bytes(legacy_dsn)
        legacy_lsn_after = _lsn()
        legacy_storage = _measure_db(legacy_dsn, legacy_scope.workspace_id, session)
        legacy_wal_bytes = _lsn_diff(legacy_lsn_before, legacy_lsn_after)

        compact_before = db_bytes(compact_dsn)
        compact_lsn_before = _lsn()
        compact_hashes = []
        compact_timings = []
        profile_result = None
        for index, raw in enumerate(commands):
            if index == len(commands) - 1:
                # The last CANCEL is committed in a dedicated worker and the
                # worker is SIGKILLed immediately after the transaction.
                worker_data = dict(profile=self.fx.profile.wire, folder=str(self.folder),
                    proof=str(self.proof), proofHash=self.proof_hash,
                    logs=str(self.root / 'controller-logs'), workspace=compact_scope.workspace_id,
                    actor=compact_scope.actor_ref, dsn=compact_dsn, command=raw,
                    phase='delta_after_commit', qaStateDeltaV3=True,
                    orderRetentionPolicy=QA_ORDER_RETENTION_V2,
                    evidenceRoot=str(root))
                env = dict(os.environ, BTL_OBSERVED_WORKER=json.dumps(worker_data, sort_keys=True))
                proc = subprocess.run([sys.executable, '-B', '-m', 'tests.test_observed_postgres', '--worker'],
                    cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True,
                    text=True, timeout=60)
                if proc.returncode != -signal.SIGKILL:
                    raise RuntimeError('POST_COMMIT_WORKER_DID_NOT_RECEIVE_SIGKILL:' + proc.stderr[-1000:])
                marker = json.loads((root / 'post-commit-worker.json').read_text())
                compact_timings.append(float(marker['commitWallSeconds']))
                # The killed worker did not return a result. Exact retry after
                # cold reconstruction must return the legacy-equivalent result.
                result = compact.apply(compact_scope, raw)
            else:
                if os.environ.get('BTL_QA_DELTA_V3_PROFILE_APPLY') == '1' \
                        and raw['commandId'] == f'order:scale:{MAX_ORDERS:04d}':
                    profiler=cProfile.Profile(); t=time.perf_counter()
                    result=profiler.runcall(compact.apply,compact_scope,raw)
                    profiled_seconds=time.perf_counter()-t
                    stats=pstats.Stats(profiler)
                    rows=[]
                    for (filename,line,function),(primitive,calls,total,cumulative,_callers) in stats.stats.items():
                        rows.append(dict(function=f'{Path(filename).name}:{line}:{function}',calls=calls,
                                         selfSeconds=round(total,6),cumulativeSeconds=round(cumulative,6)))
                    rows.sort(key=lambda row:row['cumulativeSeconds'],reverse=True)
                    profile_result=dict(commandId=raw['commandId'],orderCountBefore=MAX_ORDERS-1,
                        profiledApplySeconds=round(profiled_seconds,6),functionCount=len(rows),
                        topFunctionsByCumulative=rows[:40])
                else:
                    t = time.perf_counter(); result = compact.apply(compact_scope, raw)
                    compact_timings.append(time.perf_counter() - t)
            compact_hashes.append(hashlib.sha256(canonical_bytes(result)).hexdigest())
            if index % 16 == 0:
                _guard(root, started)
        if compact_hashes != legacy_hashes:
            raise AssertionError('PER_COMMAND_LEGACY_QA_V3_PARITY_MISMATCH')
        compact_lsn_after = _lsn()
        compact_final = compact.inspect(compact_scope, session)['state']
        compact_after = db_bytes(compact_dsn)
        compact_storage = _measure_db(compact_dsn, compact_scope.workspace_id, session)
        compact_wal_bytes = _lsn_diff(compact_lsn_before, compact_lsn_after)

        if canonical_bytes(legacy_final) != canonical_bytes(compact_final):
            raise AssertionError('FINAL_FINANCIAL_STATE_PARITY_MISMATCH')
        validate_state(compact_final, order_retention_policy=QA_ORDER_RETENTION_V2)
        if len(compact_final['orders']) != MAX_ORDERS or any(o['status'] != 'CANCELLED'
                                                              for o in compact_final['orders'].values()):
            raise AssertionError('CUMULATIVE_HISTORY_NOT_RETAINED')
        if compact_final['balance'] != '10000' or compact_final['realizedGross'] != '0':
            raise AssertionError('UNEXPECTED_FINANCIAL_CHANGE')

        # Cold resume and exact retry check through a newly constructed adapter.
        cold = ObservedExecutionController(
            ObservedExecutionStore(compact_dsn, order_retention_policy=QA_ORDER_RETENTION_V2,
                                   qa_state_delta_v3=True), lambda _: self.source,
            order_retention_policy=QA_ORDER_RETENTION_V2)
        cold_stats_before=cold.store.qa_state_cache_stats
        t = time.perf_counter(); compact_cold = cold.inspect(compact_scope, session)
        cold_resume_seconds = time.perf_counter() - t
        if canonical_bytes(compact_cold['state']) != canonical_bytes(legacy_final):
            raise AssertionError('COLD_RESUME_STATE_MISMATCH')
        cold_stats_after=cold.store.qa_state_cache_stats
        if cold_stats_after['fullReconstructions'] <= cold_stats_before['fullReconstructions']:
            raise AssertionError('COLD_RESUME_DID_NOT_REBUILD_DURABLE_CHAIN')
        cold_hits_before=cold.store.qa_state_cache_stats['hits']
        cold.inspect(compact_scope,session)
        if cold.store.qa_state_cache_stats['hits']<=cold_hits_before:
            raise AssertionError('VERIFIED_CACHE_NOT_REUSED_AFTER_COLD_REBUILD')
        for index in (0, len(commands) // 2, len(commands) - 1):
            retried = cold.apply(compact_scope, commands[index])
            if hashlib.sha256(canonical_bytes(retried)).hexdigest() != legacy_hashes[index]:
                raise AssertionError('IDEMPOTENT_RETRY_MISMATCH')

        # Independent read-only verification of receipt hashes, command IDs,
        # every order event, event chronology, state and delta commitments.
        with connect(compact_dsn) as db:
            base_row = db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints '
                'WHERE workspace_id=%s AND session_id=%s AND revision=0',
                (compact_scope.workspace_id, session)).fetchone()
            checkpoint_rows = db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints '
                'WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                (compact_scope.workspace_id, session)).fetchall()
            receipt_rows = db.execute('SELECT revision,command_id,command_hash,payload,content_hash '
                'FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                (compact_scope.workspace_id, session)).fetchall()
            event_rows = db.execute('SELECT sequence,event_id,payload,content_hash FROM btl.tick_events '
                'WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',
                (compact_scope.workspace_id, session)).fetchall()
        base = unpack(*base_row)
        delta_wires=[];previous=base['chainHash']
        for expected_revision, row in enumerate(checkpoint_rows[1:], 1):
            revision, payload, sha = row; wire=unpack(payload, sha)
            if revision != expected_revision or wire.get('revision') != expected_revision \
                    or wire.get('previousHash') != previous:
                raise AssertionError('CHECKPOINT_CHAIN_ORDER_OR_PREDECESSOR_MISMATCH')
            delta_wires.append(wire['delta']);previous=wire['chainHash']
        independent_state = reconstruct_complete(base, delta_wires, len(checkpoint_rows) - 1)
        if canonical_bytes(independent_state) != canonical_bytes(compact_final):
            raise AssertionError('INDEPENDENT_DELTA_RECONSTRUCTION_MISMATCH')
        if len(receipt_rows) != len(commands) or len(checkpoint_rows) != len(commands) + 1:
            raise AssertionError('DURABLE_COMMAND_CHECKPOINT_CARDINALITY_MISMATCH')
        for index, (row, raw, result_hash) in enumerate(zip(receipt_rows, commands, legacy_hashes), 1):
            rev, cid, command_hash, payload, sha = row
            if rev != index or cid != raw['commandId'] or command_hash != content_hash(raw):
                raise AssertionError('COMMAND_RECEIPT_BINDING_MISMATCH')
            receipt = unpack(payload, sha)
            if receipt.get('artifact') != QA3_RESULT or receipt.get('stateRevision') != rev:
                raise AssertionError('VERSIONED_RECEIPT_MISMATCH')
            checkpoint = unpack(checkpoint_rows[index][1], checkpoint_rows[index][2])
            if receipt.get('stateHash') != checkpoint.get('stateHash') \
                    or receipt.get('chainHash') != checkpoint.get('chainHash'):
                raise AssertionError('RECEIPT_CHECKPOINT_COMMITMENT_MISMATCH')
        previous_event = base['state']['eventHash']; events=[]
        for sequence, event_id, payload, sha in event_rows:
            event=unpack(payload,sha)
            if event['sequence'] != sequence or event['previousHash'] != previous_event \
                    or event['eventId'] != event_id \
                    or event_id != content_hash({k:v for k,v in event.items() if k!='eventId'}):
                raise AssertionError('INDEPENDENT_EVENT_CHAIN_MISMATCH')
            previous_event=event_id;events.append(event)
        accepted={e['orderId'] for e in events if e['kind']=='ORDER_ACCEPTED'}
        cancelled={e['orderId'] for e in events if e['kind']=='ORDER_CANCELLED'}
        if accepted != set(compact_final['orders']) or cancelled != accepted or len(accepted) != MAX_ORDERS:
            raise AssertionError('INDEPENDENT_ORDER_HISTORY_MISMATCH')
        if previous_event != compact_final['eventHash'] or len(events) != compact_final['nextEventIndex']:
            raise AssertionError('INDEPENDENT_EVENT_HEAD_MISMATCH')
        if any(e['classification']=='SIMULATED_FILL' for e in events):
            raise AssertionError('UNEXPECTED_FILL_IN_CANCELLED_ORDER_STORAGE_FIXTURE')

        # A new store has no warm state and must refuse missing, reordered and
        # byte-corrupted durable deltas. Savepoints keep each fault probe
        # isolated from the retained QA database.
        def rejects_delta_mutation(label, mutate):
            probe=ObservedExecutionStore(compact_dsn,order_retention_policy=QA_ORDER_RETENTION_V2,
                                         qa_state_delta_v3=True)
            with connect(compact_dsn) as db:
                savepoint='qa_probe_'+label
                db.execute(f'SAVEPOINT {savepoint}')
                # The evidence tables are intentionally append-only. Only this
                # private QA corruption probe suppresses their guard trigger;
                # rollback to the savepoint restores both rows and trigger
                # mode before the connection commits.
                db.execute('SET LOCAL session_replication_role = replica')
                mutate(db)
                with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):
                    probe._read(db,compact_scope.workspace_id,session)
                db.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')

        rejects_delta_mutation('missing',lambda db:db.execute(
            'DELETE FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=128',
            (compact_scope.workspace_id,session)))

        def reorder(db):
            a=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=128',
                         (compact_scope.workspace_id,session)).fetchone()
            b=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=129',
                         (compact_scope.workspace_id,session)).fetchone()
            db.execute('UPDATE btl.tick_checkpoints SET payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s AND revision=128',
                       (b[0],b[1],compact_scope.workspace_id,session))
            db.execute('UPDATE btl.tick_checkpoints SET payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s AND revision=129',
                       (a[0],a[1],compact_scope.workspace_id,session))
        rejects_delta_mutation('reordered',reorder)
        rejects_delta_mutation('corrupt',lambda db:db.execute(
            'UPDATE btl.tick_checkpoints SET payload=%s WHERE workspace_id=%s AND session_id=%s AND revision=128',
            (b'corrupt-delta',compact_scope.workspace_id,session)))

        legacy_growth = legacy_after - legacy_before
        compact_growth = compact_after - compact_before
        if compact_growth >= legacy_growth:
            raise AssertionError('QA_V3_HAS_NO_NET_DATABASE_GROWTH_SAVING')
        saved_percent=100*(legacy_growth-compact_growth)/legacy_growth
        if saved_percent<30:
            raise AssertionError('DATABASE_STORAGE_SAVING_BELOW_30_PERCENT')
        legacy_median=sorted(legacy_timings)[len(legacy_timings)//2]
        compact_median=sorted(compact_timings)[len(compact_timings)//2]
        if compact_median>1.5*legacy_median:
            raise AssertionError('QA_V3_APPLY_MEDIAN_ABOVE_1_5X_LEGACY')
        elapsed = time.monotonic() - started
        guard = _guard(root, started)
        report = dict(status='PASS', classification='CP6A4_QA_V3_256_ORDER_STORAGE_SCALE',
            fixture='AUTHORED_QA_XAU_QUOTES; NOT_MARKET_DATA', cumulativeOrders=MAX_ORDERS,
            orderStatuses={'CANCELLED':len(cancelled)}, activeOrderCount=0,
            commandCount=len(commands), eventCount=len(events), eventsByKind={
                kind:sum(e['kind']==kind for e in events) for kind in sorted({e['kind'] for e in events})},
            sourceGroupsRevealed=compact_final['nextGroupIndex'],
            financialState=dict(balance=compact_final['balance'], realizedGross=compact_final['realizedGross'],
                                fills=sum(e['classification']=='SIMULATED_FILL' for e in events)),
            parity=dict(perCommandFullResultSha256Equal=True, finalLogicalStateEqual=True,
                        sourceIdentityEqual=legacy_final['datasetVersion']==compact_final['datasetVersion']),
            recovery=dict(coldResume='PASS', coldResumeSeconds=round(cold_resume_seconds,6),
                          sigkillAfterCommit='PASS', exactRetry='PASS',
                          independentDeltaReconstruction='PASS', receipts='PASS', eventChain='PASS',
                          missingDelta='REJECTED',reorderedDelta='REJECTED',corruptedDelta='REJECTED'),
            cache=dict(warmStore=compact_store.qa_state_cache_stats,
                       afterColdRebuild=cold.store.qa_state_cache_stats),
            storage=dict(legacy=dict(beforeBytes=legacy_before,afterBytes=legacy_after,growthBytes=legacy_growth,
                                      logical=legacy_storage),
                         qaV3=dict(beforeBytes=compact_before,afterBytes=compact_after,growthBytes=compact_growth,
                                   logical=compact_storage),
                         databaseGrowthSavedBytes=legacy_growth-compact_growth,
                         databaseGrowthSavedPercent=round(100*(legacy_growth-compact_growth)/legacy_growth,3),
                         walBytesGenerated=dict(legacy=legacy_wal_bytes,qaV3=compact_wal_bytes),
                         allocatedWalBytes=_allocated_wal()),
            latency=dict(legacyApplyMedianSeconds=legacy_median,
                         legacyApplyP95Seconds=sorted(legacy_timings)[int(.95*(len(legacy_timings)-1))],
                         qaV3ApplyMedianSeconds=compact_median,
                         qaV3ApplyP95Seconds=sorted(compact_timings)[int(.95*(len(compact_timings)-1))],
                         elapsedSeconds=round(elapsed,3)),
            profile=profile_result,
            resources=dict(cpuSeconds=guard['cpuSeconds'],peakCapRssBytes=guard['capRssBytes'],
                           artifactBytes=guard['artifactBytes'],freeDiskBytes=guard['freeDiskBytes'],
                           cpuAffinity=guard['cpuAffinity'],limits=dict(artifactBytes=MAX_ARTIFACT_BYTES,
                           ramBytes=MAX_RAM_BYTES,wallSeconds=MAX_WALL_SECONDS,diskReserveBytes=MIN_FREE_BYTES)),
            sessionId=session, sessionFinalRevision=compact_final['revision'],
            stateHash=content_hash(compact_final), eventHash=compact_final['eventHash'])
        report_path = Path(os.environ['BTL_QA_DELTA_V3_SCALE_REPORT'])
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
        self.assertLessEqual(elapsed, MAX_WALL_SECONDS)

    def test_qa_v3_short_sl_matches_legacy_and_cold_resume(self):
        suffix=uuid.uuid4().hex[:10];session='session:qa3-sl:'+suffix
        legacy_dsn=pg_fixtures.isolated_database(pg_fixtures.DSN,'cp6a5_sll_'+suffix)
        compact_dsn=pg_fixtures.isolated_database(pg_fixtures.DSN,'cp6a5_slv_'+suffix)
        legacy_scope=TrustedScope('observedqa:'+uuid.uuid4().hex,self.scope.actor_ref)
        compact_scope=TrustedScope('observedqa:'+uuid.uuid4().hex,self.scope.actor_ref)
        legacy=ObservedExecutionController(ObservedExecutionStore(legacy_dsn),lambda _:self.source)
        compact=ObservedExecutionController(ObservedExecutionStore(compact_dsn,qa_state_delta_v3=True),
                                            lambda _:self.source)
        for controller,scope in ((legacy,legacy_scope),(compact,compact_scope)):
            controller.create(scope,session,self.fx.profile,self.fx.policy,period='1970-01',balance='10000')
        commands=[
            dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=session,
                 commandId='sl:quote:0',expectedRevision=0,kind='ADVANCE',payload={'targetNs':'0'}),
            dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=session,
                 commandId='sl:short',expectedRevision=1,kind='OPEN',payload=dict(side='SHORT',
                 orderType='MARKET',workflow='PLANNED',entry='2300',quantity='0.01',sl='2300.8',
                 tp='2299',riskPercent='1',observations=[])),
            dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=session,
                 commandId='sl:entry',expectedRevision=2,kind='ADVANCE',payload={'targetNs':str(10**9)}),
            dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=session,
                 commandId='sl:exit',expectedRevision=3,kind='ADVANCE',payload={'targetNs':str(2*10**9)}),
        ]
        legacy_results=[];compact_results=[]
        for raw in commands:
            old=legacy.apply(legacy_scope,raw);new=compact.apply(compact_scope,raw)
            self.assertEqual(canonical_bytes(old),canonical_bytes(new))
            legacy_results.append(old);compact_results.append(new)
        events=[event for result in compact_results for event in result['events']]
        fills=[event for event in events if event['classification']=='SIMULATED_FILL']
        self.assertEqual([event['kind'] for event in fills],['ENTRY_FILL','EXIT_FILL'])
        self.assertEqual(fills[-1]['detail']['reason'],'SL')
        self.assertEqual(compact_results[-1]['state']['orders']['sl:short']['status'],'CLOSED')
        cold=ObservedExecutionController(ObservedExecutionStore(compact_dsn,qa_state_delta_v3=True),
                                         lambda _:self.source)
        resumed=cold.inspect(compact_scope,session)
        self.assertEqual(canonical_bytes(resumed['state']),canonical_bytes(legacy_results[-1]['state']))
        self.assertEqual(resumed['state']['balance'],legacy_results[-1]['state']['balance'])


if __name__ == '__main__' and '--worker' in sys.argv:
    pg_fixtures.worker()
