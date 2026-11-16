"""QA-only PostgreSQL storage/cache/recovery scale gate at 1,024 orders."""
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import contextmanager

from application.models import TrustedScope
from contracts.canonical import canonical_bytes, content_hash
from execution.observed_kernel import QA_ORDER_RETENTION_V3, validate_state
from execution.observed_postgres import (ObservedExecutionStore, QA3_CHECKPOINT_BASE,
                                         QA3_RESULT, unpack)
from execution.observed_state_delta_v3 import reconstruct_complete
from infrastructure.database import connect
from tests import test_observed_postgres as pg_fixtures
from tests.qa_historical_day_v2 import allocated, resource_sample
from tests import test_observed_kernel as kernel_fixtures
from tests.test_observed_postgres import isolated_database

TARGET = int(os.environ.get('BTL_QA_ORDER_SCALE_TARGET', '1024'))
if TARGET not in (128, 512, 800, 1024):
    raise RuntimeError('QA_SCALE_TARGET_MUST_BE_128_512_800_OR_1024')
RAM_CAP = 1024 * 1024 * 1024
ARTIFACT_CAP = 512 * 1024 * 1024
DISK_RESERVE = 30 * 1024 * 1024 * 1024
WALL_CAP = 3600


def canonical_node_count(value):
    """Match canonical normalizer accounting: each JSON value is one node."""
    if isinstance(value, dict):
        return 1 + sum(canonical_node_count(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return 1 + sum(canonical_node_count(child) for child in value)
    return 1


@contextmanager
def resume_private_postgres(root):
    """Restart only the retained Unix-socket QA cluster for prefix resume."""
    from psycopg.conninfo import make_conninfo
    binaries=Path('/usr/lib/postgresql/16/bin');data=root/'data';socket=root/'socket'
    if (data/'postmaster.pid').exists():raise RuntimeError('QA_CLUSTER_ALREADY_RUNNING')
    if not (data/'PG_VERSION').is_file() or not (root/'password').is_file():
        raise RuntimeError('RETAINED_QA_CLUSTER_INCOMPLETE')
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','BTL_'))}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    def pg(args):return subprocess.run(args,env=env,check=True,timeout=60,capture_output=True)
    pg([str(binaries/'pg_ctl'),'-D',str(data),'-l',str(root/'server.log'),'-o',
        f"-c listen_addresses='' -k {socket} -p 55439 -c shared_buffers=32MB -c max_connections=50",'-w','start'])
    secret=(root/'password').read_text()
    connection=make_conninfo(host=str(socket),port=55439,dbname='postgres',user='qa_root',password=secret)
    values=dict(BTL_TEST_DATABASE_URL=connection,BTL_PG_BIN=str(binaries),BTL_QA_CLUSTER_ROOT=str(root))
    try:
        yield values
    finally:
        pg([str(binaries/'pg_ctl'),'-D',str(data),'-m','fast','-w','stop'])


def command(sid, cid, revision, kind, payload=None):
    return dict(schemaVersion=1, artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',
                sessionId=sid, commandId=cid, expectedRevision=revision,
                kind=kind, payload=payload or {})


def measure(dsn, workspace, sid):
    with connect(dsn) as db:
        db_bytes = int(db.execute('SELECT pg_database_size(current_database())').fetchone()[0])
        result = {}
        for table in ('tick_sessions', 'tick_checkpoints', 'tick_commands', 'tick_events'):
            row = db.execute(f'SELECT coalesce(sum(pg_column_size(t)),0), '
                f'coalesce(sum(octet_length(t.payload)),0),count(*) FROM btl.{table} t '
                'WHERE workspace_id=%s AND session_id=%s', (workspace, sid)).fetchone()
            result[table] = dict(allocatedTupleBytes=int(row[0]), payloadBytes=int(row[1]), rows=int(row[2]))
        archive = db.execute('SELECT coalesce(sum(pg_column_size(t)),0),'
            'coalesce(sum(octet_length(t.payload)),0),count(*) '
            'FROM public.btl_qa_terminal_order_archive_v1 t '
            'WHERE workspace_id=%s AND session_id=%s',(workspace,sid)).fetchone()
        result['terminalOrderArchive'] = dict(allocatedTupleBytes=int(archive[0]),
            payloadBytes=int(archive[1]),rows=int(archive[2]))
        result['sessionPayloadBytes'] = int(db.execute(
            'SELECT octet_length(payload) FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',
            (workspace, sid)).fetchone()[0])
        return dict(databaseBytes=db_bytes, tables=result)


class ObservedPostgres1024OrderScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from infrastructure.database import migrate
        cls.admin_dsn=os.environ.get('BTL_TEST_DATABASE_URL')
        if not cls.admin_dsn:raise RuntimeError('ISOLATED_QA_POSTGRES_DSN_MISSING')
        migrate(cls.admin_dsn)

    def setUp(self):
        from execution.observed_admission import AdmittedObservedSource
        self.fx=kernel_fixtures.ObservedKernelTests();self.fx.setUp()
        self.fx.setup_stream([(0,'2300','2300.1'),(10**9,'2300.9','2301'),(2*10**9,'2302','2302.1')])
        self.root=self.fx.root;self.folder=self.root/'store';archive=self.folder/'archive.sqlite'
        self.proof=self.root/'qualification.json'
        receipt=dict(status='QUALIFIED_MONTH_PASS_NOT_FINANCIAL_ADMISSION',scope='AUTHORED_QA_ONLY_NOT_MARKET_DATA',
            rows=3,sourceParityReceipts=1,sqliteIntegrity='ok',indexedSeekChecks=3,
            datasetId=self.fx.profile.wire['primary']['datasetId'],datasetVersion=self.fx.profile.wire['primary']['datasetVersion'],
            readArchiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        self.proof.write_text(json.dumps(receipt));self.proof_hash=hashlib.sha256(self.proof.read_bytes()).hexdigest()
        archive.chmod(0o400);self.folder.chmod(0o500)
        self.source=AdmittedObservedSource(self.folder,self.fx.profile,receipt_path=self.proof,
            receipt_sha256=self.proof_hash,log_root=self.root/'controller-logs')

    def tearDown(self):
        self.source.close();self.folder.chmod(0o700);(self.folder/'archive.sqlite').chmod(0o600);self.fx.tearDown()

    def test_qa_v3_1024_cumulative_orders_storage_cache_and_recovery(self):
        from execution.postgres import unpack as decode

        root = Path(os.environ['BTL_QA_ORDER_SCALE_ROOT'])
        started = time.monotonic()
        resuming=bool(os.environ.get('BTL_QA_ORDER_SCALE_RESUME'))
        suffix = uuid.uuid4().hex[:10]
        if resuming:
            from psycopg.conninfo import make_conninfo
            with connect(self.admin_dsn) as db:
                names=[row[0] for row in db.execute("SELECT datname FROM pg_database WHERE datname LIKE 'scale1024_%' AND datallowconn").fetchall()]
            if len(names)!=1:raise RuntimeError('RESUME_EXPECTED_ONE_PRIVATE_SCALE_DATABASE')
            dsn=make_conninfo(self.admin_dsn,dbname=names[0])
            with connect(dsn) as db:
                rows=db.execute('SELECT workspace_id,session_id FROM btl.tick_sessions').fetchall()
            if len(rows)!=1:raise RuntimeError('RESUME_EXPECTED_ONE_DURABLE_SCALE_SESSION')
            scope=TrustedScope(rows[0][0],'authored:actor');sid=rows[0][1]
        else:
            sid = 'session:scale1024:' + suffix
            scope = TrustedScope('observedqa:scale1024:' + suffix, 'authored:actor')
            dsn = isolated_database(self.admin_dsn, 'scale1024_' + suffix)
        store = ObservedExecutionStore(dsn, order_retention_policy=QA_ORDER_RETENTION_V3,
                                       qa_state_delta_v3=True, qa_order_archive_v1=True)
        controller = __import__('execution.observed_controller', fromlist=['ObservedExecutionController']).ObservedExecutionController(
            store, lambda _: self.source, order_retention_policy=QA_ORDER_RETENTION_V3)
        if not resuming:
            controller.create(scope, sid, self.fx.profile, self.fx.policy, period='1970-01', balance='10000')
        if resuming:
            state=controller.inspect(scope,sid)['state']
            progress_path=root/'progress.jsonl'
            historical=[json.loads(row) for row in progress_path.read_text().splitlines() if row.strip()]
            prior_target={512:128,800:512,1024:800}[TARGET]
            prior=next((row for row in reversed(historical) if row.get('orderCount')==prior_target),None)
            if prior is None:raise RuntimeError(f'RESUME_{prior_target}_MILESTONE_EVIDENCE_MISSING')
            milestones={str(prior_target):dict(progress=prior,source='durable progress sample from retained prefix')}
        else:
            state = controller.apply(scope, command(sid, 'scale:opening-quote', 0, 'ADVANCE', {'targetNs': '0'}))['state']
            progress_path=root/'progress.jsonl'
            milestones={}
        basis = state['quoteBasis']
        if basis is None:
            raise AssertionError('OPENING_QUOTE_NOT_REVEALED')
        # Valid observed-quote based planned orders. Far LIMIT/STOP levels are
        # cancelled before further market data is revealed; this is a storage
        # stress fixture, not a claim of 1,024 executed trades.
        payloads = (
            dict(side='LONG', orderType='LIMIT', entry='2290', sl='2289', tp='2291'),
            dict(side='SHORT', orderType='LIMIT', entry='2310', sl='2311', tp='2309'),
            dict(side='LONG', orderType='STOP', entry='2310', sl='2309', tp='2311'),
            dict(side='SHORT', orderType='STOP', entry='2290', sl='2291', tp='2289'),
        )
        latency = []
        archived_before = state.get('orderArchive', {}).get('count', 0)
        for number in range(archived_before + len(state['orders']) + 1, TARGET + 1):
            selected = payloads[(number - 1) % len(payloads)]
            order_id = f'order:scale:{number:04d}'
            plan = dict(selected, workflow='PLANNED', quantity='0.01', riskPercent='1', observations=[])
            opened = controller.apply(scope, command(sid, order_id, state['revision'], 'OPEN', plan))
            state=opened['state']
            cancel = command(sid, f'cancel:scale:{number:04d}', opened['state']['revision'],
                             'CANCEL', {'orderId': order_id})
            if number == TARGET:
                data = dict(profile=self.fx.profile.wire, folder=str(self.folder), proof=str(self.proof),
                    proofHash=self.proof_hash, logs=str(self.root / 'controller-logs'),
                    workspace=scope.workspace_id, actor=scope.actor_ref, dsn=dsn, command=cancel,
                    phase='delta_after_commit', qaStateDeltaV3=True, qaOrderArchiveV1=True,
                    orderRetentionPolicy=QA_ORDER_RETENTION_V3, evidenceRoot=str(root))
                env = dict(os.environ, BTL_OBSERVED_WORKER=json.dumps(data, sort_keys=True))
                worker_started = time.perf_counter()
                proc = subprocess.run([sys.executable, '-B', '-m', 'tests.test_observed_postgres', '--worker'],
                    cwd=Path(__file__).resolve().parents[2], env=env, capture_output=True, text=True, timeout=60)
                if proc.returncode != -signal.SIGKILL:
                    raise AssertionError('POST_COMMIT_WORKER_NOT_SIGKILLED:' + proc.stderr[-1000:])
                worker_seconds = time.perf_counter() - worker_started
                before_retry = time.perf_counter()
                retried = controller.apply(scope, cancel)
                latency.append(time.perf_counter() - before_retry)
                state=retried['state']
                if retried['state']['revision'] != cancel['expectedRevision'] + 1:
                    raise AssertionError('POST_COMMIT_RETRY_REVISION_MISMATCH')
            else:
                before_apply = time.perf_counter()
                state=controller.apply(scope, cancel)['state']
                latency.append(time.perf_counter() - before_apply)
            if number in (128, 512, 800, 1024, TARGET):
                validate_state(state, order_retention_policy=QA_ORDER_RETENTION_V3)
                milestones[str(number)] = dict(measurement=measure(dsn, scope.workspace_id, sid),
                    stateBytes=len(canonical_bytes(state)), stateNodes=canonical_node_count(state),
                    orderArchiveCount=state['orderArchive']['count'],
                    activeOrderCount=len(state['orders']), revision=state['revision'],
                    cache=dict(store.qa_state_cache_stats), medianCancelApplySeconds=sorted(latency)[len(latency)//2])
            if number % 32 == 0:
                if time.monotonic() - started > WALL_CAP:
                    raise RuntimeError('RESOURCE_STOP_WALL_15_MINUTES')
                if allocated(root) > ARTIFACT_CAP:
                    raise RuntimeError('RESOURCE_STOP_ARTIFACT_512_MIB')
                if shutil.disk_usage(root).free < DISK_RESERVE:
                    raise RuntimeError('RESOURCE_STOP_DISK_RESERVE_30_GIB')
                _, ram, *_ = resource_sample(os.environ['BTL_QA_CLUSTER_ROOT'])
                if ram > RAM_CAP:
                    raise RuntimeError('RESOURCE_STOP_RAM_1_GIB')
                sample=dict(orderCount=number,revision=state['revision'],elapsedSeconds=round(time.monotonic()-started,3),
                    ramBytes=ram,artifactBytes=allocated(root),databaseBytes=measure(dsn,scope.workspace_id,sid)['databaseBytes'],
                    medianCancelApplySeconds=sorted(latency)[len(latency)//2])
                with progress_path.open('a') as stream:
                    stream.write(json.dumps(sample,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())

        final = controller.inspect(scope, sid)['state']
        cache_warm = dict(store.qa_state_cache_stats)
        cold_store = ObservedExecutionStore(dsn, order_retention_policy=QA_ORDER_RETENTION_V3,
                                            qa_state_delta_v3=True, qa_order_archive_v1=True)
        cold_controller = __import__('execution.observed_controller', fromlist=['ObservedExecutionController']).ObservedExecutionController(
            cold_store, lambda _: self.source, order_retention_policy=QA_ORDER_RETENTION_V3)
        resume_started = time.perf_counter()
        recovered = cold_controller.inspect(scope, sid)['state']
        cold_resume_seconds = time.perf_counter() - resume_started
        if canonical_bytes(recovered) != canonical_bytes(final):
            raise AssertionError('COLD_RESUME_STATE_MISMATCH')
        after_reconstruct = dict(cold_store.qa_state_cache_stats)
        cold_controller.inspect(scope, sid)
        if after_reconstruct['fullReconstructions'] < 1 or cold_store.qa_state_cache_stats['hits'] < 1:
            raise AssertionError('COLD_RECONSTRUCTION_OR_VERIFIED_CACHE_HIT_NOT_PROVEN')
        if final.get('orderArchive', {}).get('count') != TARGET or final['orders']:
            raise AssertionError('CUMULATIVE_HISTORY_NOT_RETAINED')
        history=[];offset=0
        while True:
            page=cold_store.order_history(scope,sid,offset=offset,maximum=256)
            history.extend(page['records'])
            if page['nextOffset'] is None:break
            offset=page['nextOffset']
        if len(history)!=TARGET or any(row['order']['status']!='CANCELLED' for row in history):
            raise AssertionError('ARCHIVED_HISTORY_QUERY_MISMATCH')
        if final['balance'] != '10000' or final['realizedGross'] != '0':
            raise AssertionError('CANCELLED_FIXTURE_CHANGED_FINANCIAL_STATE')

        # Independent full reconstruction from immutable PostgreSQL records.
        with connect(dsn) as db:
            base_row = db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',
                                  (scope.workspace_id, sid)).fetchone()
            checkpoints = db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                                     (scope.workspace_id, sid)).fetchall()
            receipts = db.execute('SELECT revision,command_id,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',
                                  (scope.workspace_id, sid)).fetchall()
            events = db.execute('SELECT sequence,event_id,payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',
                                (scope.workspace_id, sid)).fetchall()
        base = decode(*base_row)
        if base.get('artifact') != QA3_CHECKPOINT_BASE:
            raise AssertionError('VERSIONED_BASE_SNAPSHOT_MISSING')
        deltas=[];previous=base['chainHash']
        for expected, (revision, raw, sha) in enumerate(checkpoints[1:], 1):
            wire=decode(raw,sha)
            if revision != expected or wire.get('revision') != expected or wire.get('previousHash') != previous:
                raise AssertionError('DELTA_SEQUENCE_OR_PREDECESSOR_MISMATCH')
            deltas.append(wire['delta']);previous=wire['chainHash']
        independent_state=reconstruct_complete(base,deltas,len(checkpoints)-1)
        if canonical_bytes(independent_state) != canonical_bytes(final):
            raise AssertionError('INDEPENDENT_RECONSTRUCTION_PARITY_MISMATCH')
        validate_state(independent_state,order_retention_policy=QA_ORDER_RETENTION_V3)
        if len(receipts) != final['revision'] or len(checkpoints) != final['revision']+1:
            raise AssertionError('RECEIPT_CHECKPOINT_CARDINALITY_MISMATCH')
        for expected, (revision, cid, chash, raw, sha) in enumerate(receipts, 1):
            receipt=decode(raw,sha);checkpoint=decode(checkpoints[expected][1],checkpoints[expected][2])
            if revision != expected or receipt.get('artifact') != QA3_RESULT or receipt.get('stateRevision') != expected:
                raise AssertionError('RECEIPT_REVISION_OR_FORMAT_MISMATCH')
            if receipt.get('commandId') != cid or receipt.get('commandHash') != chash:
                raise AssertionError('RECEIPT_COMMAND_BINDING_MISMATCH')
            if receipt.get('stateHash') != checkpoint.get('stateHash') or receipt.get('chainHash') != checkpoint.get('chainHash'):
                raise AssertionError('RECEIPT_CHECKPOINT_BINDING_MISMATCH')
        prior=base['state']['eventHash'];event_wires=[]
        for sequence, event_id, raw, sha in events:
            event=decode(raw,sha)
            if event['sequence'] != sequence or event['previousHash'] != prior or event['eventId'] != event_id:
                raise AssertionError('INDEPENDENT_EVENT_ORDER_MISMATCH')
            if event_id != content_hash({k:v for k,v in event.items() if k!='eventId'}):
                raise AssertionError('INDEPENDENT_EVENT_HASH_MISMATCH')
            prior=event_id;event_wires.append(event)
        accepted={e['orderId'] for e in event_wires if e['kind']=='ORDER_ACCEPTED'}
        cancelled={e['orderId'] for e in event_wires if e['kind']=='ORDER_CANCELLED'}
        archived_ids={row['orderId'] for row in history}
        if accepted != archived_ids or cancelled != accepted or len(accepted) != TARGET:
            raise AssertionError('INDEPENDENT_ORDER_HISTORY_MISMATCH')
        if prior != final['eventHash'] or len(event_wires) != final['nextEventIndex']:
            raise AssertionError('INDEPENDENT_EVENT_HEAD_MISMATCH')

        # Refuse active order 129 without a durable command or state mutation.
        if TARGET == 1024:
            active_sid='session:scale1024-active:'+suffix
            active_scope=TrustedScope('observedqa:scale1024-active:'+suffix, 'authored:actor')
            controller.create(active_scope, active_sid, self.fx.profile, self.fx.policy, period='1970-01', balance='10000')
            state=controller.apply(active_scope, command(active_sid,'active:quote',0,'ADVANCE',{'targetNs':'0'}))['state']
            active_payload=dict(side='LONG',orderType='LIMIT',workflow='PLANNED',entry='2290',quantity='0.01',
                                sl='2289',tp='2291',riskPercent='1',observations=[])
            for n in range(1,129):
                state=controller.apply(active_scope,command(active_sid,f'active:{n:03d}',state['revision'],'OPEN',active_payload))['state']
            before_hash=content_hash(state);refused=command(active_sid,'active:129',state['revision'],'OPEN',active_payload)
            with self.assertRaisesRegex(ValueError,'REFUSED_ACTIVE_ORDER_LIMIT'):
                controller.apply(active_scope,refused)
            after=controller.inspect(active_scope,active_sid)['state']
            if content_hash(after) != before_hash:
                raise AssertionError('ACTIVE_129_REFUSAL_MUTATED_STATE')
            with connect(dsn) as db:
                if db.execute('SELECT 1 FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s',
                              (active_scope.workspace_id,active_sid,'active:129')).fetchone():
                    raise AssertionError('REFUSED_ACTIVE_COMMAND_PERSISTED')

        report=dict(status='PASS',classification='QA_ARCHIVE_V1_POSTGRESQL_CUMULATIVE_ORDER_STORAGE_RECOVERY',
            policy=QA_ORDER_RETENTION_V3,fixture='AUTHORED_QA_TICKS_ORDER_STORAGE_STRESS_NOT_MARKET_TRADES',
            milestones=milestones,verification=dict(independentDeltaReconstruction='PASS',receiptChain='PASS',
                eventChain='PASS',completeOrderHistory='PASS',coldResume='PASS',coldResumeSeconds=cold_resume_seconds,
                postCommitSigkill='PASS',identicalRetry='PASS',activeOrder129='REFUSED_WITHOUT_MUTATION'),
            counts=dict(cumulativeOrders=len(accepted),archivedOrders=len(archived_ids),hotOrders=len(final['orders']),cancelledOrders=len(cancelled),fills=0,
                        financialEventCount=sum(e['classification']=='SIMULATED_FILL' for e in event_wires),
                        commands=len(receipts),events=len(event_wires)),
            latencySeconds=dict(cancelMedian=sorted(latency)[len(latency)//2],
                cancelP95=sorted(latency)[int(.95*(len(latency)-1))],postCommitWorkerSeconds=worker_seconds),
            cache=dict(warmStore=cache_warm,coldStoreAfterReconstruction=after_reconstruct,
                       coldStoreAfterVerifiedRead=cold_store.qa_state_cache_stats),
            resource=dict(elapsedSeconds=round(time.monotonic()-started,3),
                cpuSeconds=round(resource_sample(os.environ['BTL_QA_CLUSTER_ROOT'])[0],3),
                capRssBytes=resource_sample(os.environ['BTL_QA_CLUSTER_ROOT'])[1],
                artifactsAllocatedBytes=allocated(root),diskFreeBytes=shutil.disk_usage(root).free,
                caps=dict(ramBytes=RAM_CAP,artifactBytes=ARTIFACT_CAP,diskReserveBytes=DISK_RESERVE,wallSeconds=WALL_CAP)),
            financialSemantics='No fills; cancelled-order storage stress only. Not evidence for 2,000 completed trades.',
            productionChanged=False)
        output=root/f'report-{TARGET}.json';output.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n');output.chmod(0o600)
        print(json.dumps(report,sort_keys=True))


def main():
    root_text=os.environ.get('BTL_QA_ORDER_SCALE_ROOT')
    if not root_text:raise RuntimeError('SET_BTL_QA_ORDER_SCALE_ROOT_TO_NEW_EMPTY_PATH')
    root=Path(root_text)
    resuming=bool(os.environ.get('BTL_QA_ORDER_SCALE_RESUME'))
    if root.exists() != resuming:raise RuntimeError('QA_OUTPUT_ROOT_RESUME_STATE_MISMATCH')
    if shutil.disk_usage(root.parent if root.parent.exists() else Path('/')).free < DISK_RESERVE:
        raise RuntimeError('PREFLIGHT_DISK_RESERVE_BELOW_30_GIB')
    if not resuming:root.mkdir(mode=0o700,parents=False);root.chmod(0o700)
    tempfile.tempdir=str(root);os.environ['TMPDIR']=str(root);os.environ['PYTHONDONTWRITEBYTECODE']='1'
    os.environ['BTL_ENABLE_QA_ORDER_ARCHIVE_V1']='1'
    if hasattr(os,'sched_getaffinity'):
        allowed=os.sched_getaffinity(0)
        if allowed:os.sched_setaffinity(0,{min(allowed)})
    if resuming:
        cluster_context=resume_private_postgres(root/'postgres')
    else:
        from deploy.vps.tests.run_private_pg import private_postgres
        cluster_context=private_postgres(keep=True,root_dir=root/'postgres')
    with cluster_context as private:
        if resuming:
            environment=private
        else:
            _repository,environment=private
        os.environ.update(environment)
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(ObservedPostgres1024OrderScaleTests)
        outcome=unittest.TextTestRunner(verbosity=2).run(suite)
        if not outcome.wasSuccessful() or outcome.testsRun != 1 or outcome.skipped:
            failure=dict(status='FAIL',classification='QA_ARCHIVE_V1_POSTGRESQL_CUMULATIVE_ORDER_STORAGE_RECOVERY',
                         failures=[str(e[1])[-2000:] for e in outcome.failures],
                         errors=[str(e[1])[-2000:] for e in outcome.errors])
            (root/'failure.json').write_text(json.dumps(failure,sort_keys=True,indent=2)+'\n')
            (root/'failure.json').chmod(0o600)
            return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
