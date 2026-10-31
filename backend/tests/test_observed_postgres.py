"""Native new-family isolated transactions/source admission; never production DB."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import hashlib,json,os,signal,subprocess,sys,time,unittest,uuid

from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from execution.observed_admission import AdmittedObservedSource
from execution.observed_controller import ObservedExecutionController
from execution.observed_postgres import ObservedExecutionStore
from infrastructure.database import migrate,connect
from tests import test_observed_kernel as fixtures

DSN=os.getenv('BTL_TEST_DATABASE_URL');S=10**9

def command(sid,cid,rev,kind,payload=None):
    return dict(schemaVersion=1,artifact='BTL-OBSERVED-EXECUTION-COMMAND-1',sessionId=sid,commandId=cid,expectedRevision=rev,kind=kind,payload=payload or {})


def isolated_database(admin_dsn,name):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    dsn=make_conninfo(admin_dsn,dbname=name)
    with psycopg.connect(admin_dsn,autocommit=True) as db:
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    migrate(dsn)
    return dsn


def worker():
    import execution.observed_postgres as storage
    from execution.observed_profile import ObservedExecutionProfile
    data=json.loads(os.environ['BTL_OBSERVED_WORKER']);profile=ObservedExecutionProfile.from_wire(data['profile'])
    source=AdmittedObservedSource(data['folder'],profile,receipt_path=data['proof'],receipt_sha256=data['proofHash'],log_root=data['logs'])
    if data['phase']=='before':
        native=storage.connect;calls=[0]
        @contextmanager
        def interrupted(dsn):
            calls[0]+=1
            with native(dsn) as db:
                yield db
                if calls[0]==2:os._exit(73)
        storage.connect=interrupted
    order_policy=data.get('orderRetentionPolicy')
    store=ObservedExecutionStore(data.get('dsn',DSN),order_retention_policy=order_policy,
                                qa_state_delta_v3=bool(data.get('qaStateDeltaV3',False)),
                                qa_order_archive_v1=bool(data.get('qaOrderArchiveV1',False)))
    controller=ObservedExecutionController(store,lambda _:source,order_retention_policy=order_policy)
    started=time.perf_counter()
    controller.apply(TrustedScope(data['workspace'],data.get('actor','authored:worker')),data['command'])
    if data.get('evidenceRoot'):
        marker=Path(data['evidenceRoot'])/'post-commit-worker.json'
        marker.write_text(json.dumps(dict(commandId=data['command']['commandId'],
            commitWallSeconds=time.perf_counter()-started,processId=os.getpid()),sort_keys=True)+'\n')
    if data['phase']=='delta_after_commit':os.kill(os.getpid(),signal.SIGKILL)
    os._exit(74)


@unittest.skipUnless(DSN,'Requires exclusive native PostgreSQL; skipped is not acceptance')
class ObservedPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(DSN)

    def setUp(self):
        self.fx=fixtures.ObservedKernelTests();self.fx.setUp();self.fx.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301'),(2*S,'2302','2302.1')])
        self.root=self.fx.root;folder=self.root/'store';archive=folder/'archive.sqlite';self.folder=folder
        self.proof=self.root/'qualification.json';self.receipt=dict(status='QUALIFIED_MONTH_PASS_NOT_FINANCIAL_ADMISSION',scope='AUTHORED_QA_ONLY_NOT_MARKET_DATA',rows=3,sourceParityReceipts=1,sqliteIntegrity='ok',indexedSeekChecks=3,datasetId=self.fx.profile.wire['primary']['datasetId'],datasetVersion=self.fx.profile.wire['primary']['datasetVersion'],readArchiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        # Independent authored whole-input checks before the operator receipt.
        for target in ('0','500000000','1000000000'):self.assertIsNotNone(self.fx.provider.locate_v2(self.fx.provider.dataset_id,self.fx.provider.dataset_version,target)['position'])
        page=self.fx.provider.read_page_v2(self.fx.provider.dataset_id,self.fx.provider.dataset_version,self.fx.provider.locate_v2(self.fx.provider.dataset_id,self.fx.provider.dataset_version,'0')['position'],3)
        self.assertEqual([e['bid'] for e in page['events']],['2300','2300.9','2302'])
        import sqlite3
        with sqlite3.connect(archive.as_uri()+'?mode=ro',uri=True) as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.proof.write_text(json.dumps(self.receipt));self.proof_hash=hashlib.sha256(self.proof.read_bytes()).hexdigest();archive.chmod(0o400);folder.chmod(0o500)
        self.source=AdmittedObservedSource(folder,self.fx.profile,receipt_path=self.proof,receipt_sha256=self.proof_hash,log_root=self.root/'controller-logs')
        self.scope=TrustedScope('observedqa:'+uuid.uuid4().hex,'authored:actor');self.sid='session:observed';self.store=ObservedExecutionStore(DSN);self.c=self.controller();self.rev=0
        self.c.create(self.scope,self.sid,self.fx.profile,self.fx.policy,period='1970-01')

    def controller(self):return ObservedExecutionController(self.store,lambda _:self.source)

    def tearDown(self):
        self.source.close();self.folder.chmod(0o700);(self.folder/'archive.sqlite').chmod(0o600);self.fx.tearDown()

    def call(self,kind,payload=None,cid=None):
        raw=command(self.sid,cid or 'cmd:'+str(self.rev),self.rev,kind,payload);result=self.controller().apply(self.scope,raw);self.rev=result['state']['revision'];return result

    def test_qa_order_archive_v1_integrates_kernel_postgres_recovery_and_ledger(self):
        from contextlib import contextmanager
        from execution.observed_kernel import QA_ORDER_RETENTION_V3
        from execution.observed_analysis import ObservedStatistics
        import execution.observed_postgres as storage
        # The shared fixture used by the surrounding class has three quotes;
        # this bounded parity test needs a fourth observed quote to trigger TP.
        self.source.close();self.folder.chmod(0o700);(self.folder/'archive.sqlite').chmod(0o600);self.fx.tearDown()
        self.fx=fixtures.ObservedKernelTests();self.fx.setUp()
        self.fx.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301'),
                              (2*S,'2302','2302.1'),(3*S,'2303','2303.1')])
        self.root=self.fx.root;self.folder=self.root/'store';archive=self.folder/'archive.sqlite'
        self.proof=self.root/'qualification.json'
        self.receipt=dict(status='QUALIFIED_MONTH_PASS_NOT_FINANCIAL_ADMISSION',scope='AUTHORED_QA_ONLY_NOT_MARKET_DATA',
            rows=4,sourceParityReceipts=1,sqliteIntegrity='ok',indexedSeekChecks=3,
            datasetId=self.fx.profile.wire['primary']['datasetId'],datasetVersion=self.fx.profile.wire['primary']['datasetVersion'],
            readArchiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        self.proof.write_text(json.dumps(self.receipt));self.proof_hash=hashlib.sha256(self.proof.read_bytes()).hexdigest()
        archive.chmod(0o400);self.folder.chmod(0o500)
        self.source=AdmittedObservedSource(self.folder,self.fx.profile,receipt_path=self.proof,
            receipt_sha256=self.proof_hash,log_root=self.root/'controller-logs')
        previous_gate=os.environ.get('BTL_ENABLE_QA_ORDER_ARCHIVE_V1')
        os.environ['BTL_ENABLE_QA_ORDER_ARCHIVE_V1']='1'
        suffix=uuid.uuid4().hex[:10]
        qa_dsn=isolated_database(DSN,'orderarch_'+suffix)
        qa_scope=TrustedScope('observedqa:archive:'+suffix,'authored:actor');sid='session:archive:'+suffix
        self.scope=qa_scope;self.sid=sid
        qa_source=AdmittedObservedSource(self.folder,self.fx.profile,receipt_path=self.proof,
            receipt_sha256=self.proof_hash,log_root=self.root/'archive-controller-logs')
        try:
            qa_store=ObservedExecutionStore(qa_dsn,order_retention_policy=QA_ORDER_RETENTION_V3,
                qa_state_delta_v3=True,qa_order_archive_v1=True)
            qa=ObservedExecutionController(qa_store,lambda _:qa_source,order_retention_policy=QA_ORDER_RETENTION_V3)
            qa.create(qa_scope,sid,self.fx.profile,self.fx.policy,period='1970-01',balance='10000')
            def call(raw):return qa.apply(qa_scope,raw)
            results=[];commands=[]
            def issue(cid,rev,kind,payload):
                raw=command(sid,cid,rev,kind,payload);commands.append(raw);results.append(call(raw));return results[-1]
            issue('archive:quote',0,'ADVANCE',dict(targetNs='0'))
            plan=dict(side='LONG',orderType='STOP',workflow='PLANNED',entry='2301.5',quantity='0.01',
                sl='2300.5',tp='2302.5',riskPercent='1',observations=[])
            issue('order:archive:closed',1,'OPEN',plan)
            issue('archive:entry',2,'ADVANCE',dict(targetNs=str(2*S)))
            closed=issue('archive:tp',3,'ADVANCE',dict(targetNs=str(3*S)))
            self.assertEqual(closed['state']['orders'],{},
                'ORDER_NOT_ARCHIVED: '+json.dumps(closed['state']['orders'],sort_keys=True)+' events='+
                json.dumps(closed['events'],sort_keys=True))
            self.assertEqual(closed['state']['orderArchive']['count'],1)
            self.assertGreater(float(closed['state']['realizedGross']),0)
            archived=qa_store.archive_order(qa_scope,sid,'order:archive:closed')
            self.assertEqual(archived['status'],'CLOSED')
            self.assertEqual(qa_store.order_history(qa_scope,sid)['total'],1)

            # Existing full-history reducer is the reference. Run the exact
            # commands in a second isolated QA database and compare every event
            # plus financial outputs while preserving its legacy state format.
            legacy_dsn=isolated_database(DSN,'orderref_'+suffix)
            reference_source=AdmittedObservedSource(self.folder,self.fx.profile,receipt_path=self.proof,
                receipt_sha256=self.proof_hash,log_root=self.root/'archive-reference-logs')
            legacy_scope=TrustedScope(qa_scope.workspace_id,qa_scope.actor_ref)
            legacy=ObservedExecutionController(ObservedExecutionStore(legacy_dsn),lambda _:reference_source)
            legacy.create(legacy_scope,sid,self.fx.profile,self.fx.policy,period='1970-01',balance='10000')
            legacy_results=[legacy.apply(legacy_scope,raw) for raw in commands]
            for compact,full in zip(results,legacy_results):
                self.assertEqual(compact['events'],full['events'])
                self.assertEqual((compact['state']['balance'],compact['state']['realizedGross']),
                                 (full['state']['balance'],full['state']['realizedGross']))
            self.assertEqual(archived,legacy_results[-1]['state']['orders']['order:archive:closed'])

            # Archive the other supported terminal outcomes through the real
            # kernel path: END expires a pending order and marks an open
            # position unresolved without synthesizing an exit fill.
            terminal_sid='session:archive:terminal:'+suffix
            terminal_scope=TrustedScope('observedqa:archive-terminal:'+suffix,'authored:actor')
            qa.create(terminal_scope,terminal_sid,self.fx.profile,self.fx.policy,period='1970-01',balance='10000')
            terminal_state=qa.apply(terminal_scope,command(terminal_sid,'terminal:quote',0,'ADVANCE',dict(targetNs='0')))['state']
            pending=dict(plan,side='LONG',orderType='LIMIT',entry='2290',sl='2289',tp='2291')
            terminal_state=qa.apply(terminal_scope,command(terminal_sid,'terminal:pending',terminal_state['revision'],'OPEN',pending))['state']
            live=dict(plan,side='LONG',orderType='STOP',entry='2301.5',sl='2300.5',tp='2302.5')
            terminal_state=qa.apply(terminal_scope,command(terminal_sid,'terminal:live',terminal_state['revision'],'OPEN',live))['state']
            terminal_state=qa.apply(terminal_scope,command(terminal_sid,'terminal:entry',terminal_state['revision'],'ADVANCE',dict(targetNs=str(2*S))) )['state']
            terminal_end=qa.apply(terminal_scope,command(terminal_sid,'terminal:end',terminal_state['revision'],'END'))['state']
            self.assertEqual(terminal_end['orderArchive']['count'],2)
            terminal_history=qa_store.order_history(terminal_scope,terminal_sid,maximum=8)['records']
            self.assertEqual({row['order']['status'] for row in terminal_history},{'EXPIRED','UNRESOLVED'})
            self.assertEqual(terminal_end['balance'],'10000')
            terminal_cold=ObservedExecutionController(ObservedExecutionStore(qa_dsn,
                order_retention_policy=QA_ORDER_RETENTION_V3,qa_state_delta_v3=True,qa_order_archive_v1=True),
                lambda _:qa_source,order_retention_policy=QA_ORDER_RETENTION_V3)
            self.assertEqual(terminal_cold.inspect(terminal_scope,terminal_sid)['state'],terminal_end)

            # Fresh store has no LRU entry: it must reconstruct the delta chain,
            # stream the event ledger, and verify every archive record.
            fresh_store=ObservedExecutionStore(qa_dsn,order_retention_policy=QA_ORDER_RETENTION_V3,
                qa_state_delta_v3=True,qa_order_archive_v1=True)
            fresh=ObservedExecutionController(fresh_store,lambda _:qa_source,order_retention_policy=QA_ORDER_RETENTION_V3)
            recovered=fresh.inspect(qa_scope,sid)['state']
            self.assertEqual(recovered,closed['state'])
            self.assertGreaterEqual(fresh_store.qa_state_cache_stats['fullReconstructions'],2)
            stats=ObservedStatistics(fresh_store).inspect(qa_scope,sid)
            self.assertEqual(stats['status'],'COMPLETE')
            self.assertEqual(stats['metrics']['closed'],1)
            self.assertEqual(fresh.apply(qa_scope,commands[-1]),closed)

            # Open a second terminal order and abort the DB context after all
            # writes but before commit. State, event, receipt and archive must
            # all roll back together.
            current=fresh.inspect(qa_scope,sid)['state']
            pending=dict(plan,orderType='LIMIT',entry='2290',sl='2289',tp='2291')
            open_raw=command(sid,'order:archive:cancel',current['revision'],'OPEN',pending)
            opened=fresh.apply(qa_scope,open_raw);cancel_raw=command(sid,'archive:cancel',opened['state']['revision'],
                'CANCEL',dict(orderId='order:archive:cancel'))
            native=storage.connect;counter=[0]
            @contextmanager
            def fail_before_commit(dsn):
                counter[0]+=1
                with native(dsn) as db:
                    yield db
                    if counter[0]==2:raise RuntimeError('QA_ARCHIVE_ROLLBACK_INJECTED')
            with patch.object(storage,'connect',fail_before_commit):
                with self.assertRaisesRegex(RuntimeError,'QA_ARCHIVE_ROLLBACK_INJECTED'):
                    fresh.apply(qa_scope,cancel_raw)
            post_rollback=fresh.inspect(qa_scope,sid)['state']
            self.assertEqual(post_rollback['revision'],opened['state']['revision'])
            self.assertEqual(post_rollback['orderArchive']['count'],1)

            # A process killed after commit must recover one archive append;
            # retry returns the durable receipt and cannot append it twice.
            worker_data=dict(profile=self.fx.profile.wire,folder=str(self.folder),proof=str(self.proof),
                proofHash=self.proof_hash,logs=str(self.root/'archive-worker-logs'),workspace=qa_scope.workspace_id,
                actor=qa_scope.actor_ref,dsn=qa_dsn,command=cancel_raw,phase='delta_after_commit',
                qaStateDeltaV3=True,qaOrderArchiveV1=True,orderRetentionPolicy=QA_ORDER_RETENTION_V3)
            env=dict(os.environ,BTL_OBSERVED_WORKER=json.dumps(worker_data,sort_keys=True),
                     BTL_TEST_DATABASE_URL=qa_dsn,BTL_ENABLE_QA_ORDER_ARCHIVE_V1='1')
            proc=subprocess.run([sys.executable,'-B','-m','tests.test_observed_postgres','--worker'],
                cwd=Path(__file__).resolve().parents[2],env=env,capture_output=True,text=True,timeout=90)
            self.assertEqual(proc.returncode,-signal.SIGKILL,proc.stderr)
            after_kill=fresh.inspect(qa_scope,sid)['state']
            self.assertEqual(after_kill['orderArchive']['count'],2)
            retried=fresh.apply(qa_scope,cancel_raw)
            self.assertEqual(retried['state'],after_kill)
            self.assertEqual(qa_store.order_history(qa_scope,sid,offset=0,maximum=8)['total'],2)
            with connect(qa_dsn) as db:
                saved=db.execute('SELECT workspace_id,session_id,sequence,order_id,finalized_revision,record_hash,payload,content_hash '
                    'FROM public.btl_qa_terminal_order_archive_v1 WHERE workspace_id=%s AND session_id=%s AND sequence=0',
                    (qa_scope.workspace_id,sid)).fetchone()
                db.execute('ALTER TABLE public.btl_qa_terminal_order_archive_v1 DISABLE TRIGGER ALL')
                db.execute('DELETE FROM public.btl_qa_terminal_order_archive_v1 WHERE workspace_id=%s AND session_id=%s AND sequence=0',
                    (qa_scope.workspace_id,sid))
                db.execute('ALTER TABLE public.btl_qa_terminal_order_archive_v1 ENABLE TRIGGER ALL')
            with self.assertRaises(ValueError):
                ObservedExecutionController(ObservedExecutionStore(qa_dsn,order_retention_policy=QA_ORDER_RETENTION_V3,
                    qa_state_delta_v3=True,qa_order_archive_v1=True),lambda _:qa_source,
                    order_retention_policy=QA_ORDER_RETENTION_V3).inspect(qa_scope,sid)
            with connect(qa_dsn) as db:
                db.execute('INSERT INTO public.btl_qa_terminal_order_archive_v1 '
                    '(workspace_id,session_id,sequence,order_id,finalized_revision,record_hash,payload,content_hash) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',saved)
                db.execute('ALTER TABLE public.btl_qa_terminal_order_archive_v1 DISABLE TRIGGER ALL')
                db.execute('UPDATE public.btl_qa_terminal_order_archive_v1 SET sequence=7 '
                    'WHERE workspace_id=%s AND session_id=%s AND sequence=0',(qa_scope.workspace_id,sid))
                db.execute('ALTER TABLE public.btl_qa_terminal_order_archive_v1 ENABLE TRIGGER ALL')
            with self.assertRaises(ValueError):
                ObservedExecutionController(ObservedExecutionStore(qa_dsn,order_retention_policy=QA_ORDER_RETENTION_V3,
                    qa_state_delta_v3=True,qa_order_archive_v1=True),lambda _:qa_source,
                    order_retention_policy=QA_ORDER_RETENTION_V3).inspect(qa_scope,sid)
            with connect(qa_dsn) as db:
                db.execute('ALTER TABLE public.btl_qa_terminal_order_archive_v1 DISABLE TRIGGER ALL')
                db.execute('UPDATE public.btl_qa_terminal_order_archive_v1 SET sequence=0,record_hash=%s '
                    'WHERE workspace_id=%s AND session_id=%s AND sequence=7',
                    ('0'*64,qa_scope.workspace_id,sid))
                db.execute('ALTER TABLE public.btl_qa_terminal_order_archive_v1 ENABLE TRIGGER ALL')
            with self.assertRaises(ValueError):
                ObservedExecutionController(ObservedExecutionStore(qa_dsn,order_retention_policy=QA_ORDER_RETENTION_V3,
                    qa_state_delta_v3=True,qa_order_archive_v1=True),lambda _:qa_source,
                    order_retention_policy=QA_ORDER_RETENTION_V3).inspect(qa_scope,sid)
            reference_source.close()
        finally:
            qa_source.close()
            if previous_gate is None:os.environ.pop('BTL_ENABLE_QA_ORDER_ARCHIVE_V1',None)
            else:os.environ['BTL_ENABLE_QA_ORDER_ARCHIVE_V1']=previous_gate

    def opening(self):return dict(side='LONG',orderType='MARKET',workflow='QUICK',entry='2300.1',quantity='0.01',sl=None,tp=None,riskPercent='1',observations=[])

    def test_actual_transactions_cold_source_and_source_outage_receipt_and_journal(self):
        self.call('ADVANCE',dict(targetNs='0'));self.call('OPEN',self.opening(),cid='order:one');self.call('ADVANCE',dict(targetNs=str(S)));self.source.cache.close()
        self.call('CLOSE',dict(orderId='order:one',quantity=None));raw=command(self.sid,'final',self.rev,'ADVANCE',dict(targetNs=str(2*S)));result=self.controller().apply(self.scope,raw)
        self.assertTrue(result['durable']);self.assertEqual(result['state']['balance'],'10001')
        self.source.cache.close();offline=self.root/'offline';self.folder.rename(offline)
        try:
            retry=ObservedExecutionController(self.store,lambda _:(_ for _ in ()).throw(AssertionError('source must not be opened'))).apply(self.scope,raw)
            self.assertEqual(canonical_bytes(result),canonical_bytes(retry))
            view=self.controller().inspect(self.scope,self.sid,maximum=64);self.assertEqual(view['state']['balance'],'10001');self.assertEqual(len([e for e in view['events'] if e['kind']=='EXIT_FILL']),1)
        finally:offline.rename(self.folder)

    def test_replay_to_uses_existing_durable_advances_and_recovers_idempotently(self):
        from execution.observed_research import ObservedResearchApplication
        app=object.__new__(ObservedResearchApplication);app.dsn=DSN;app.scope=self.scope;app.controller=self.controller()
        def current_state():return self.c.inspect(self.scope,self.sid)['state']
        app._session=lambda db,session:(None,None,current_state(),None)
        app.inspect=lambda session,timeframe:{'metadata':{'id':session},'state':current_state()}
        request=dict(schemaVersion=1,artifact='BTL-OBSERVED-REPLAY-TO-1',requestId=uuid.uuid4().hex,
                     sessionId=self.sid,expectedRevision=0,targetNs=str(2*S),timeframe='1m')
        first=app.replay_to(self.sid,request)
        self.assertTrue(first['targetReached']);self.assertEqual(first['advances'],1)
        self.assertEqual(first['view']['state']['nextGroupIndex'],'3')
        retry=app.replay_to(self.sid,request)
        self.assertTrue(retry['targetReached']);self.assertEqual(retry['advances'],0)
        self.assertEqual(retry['view']['state']['revision'],first['view']['state']['revision'])
        stale=dict(request,requestId=uuid.uuid4().hex)
        with self.assertRaisesRegex(ValueError,'REFUSED_STALE_REVISION'):app.replay_to(self.sid,stale)

    def test_concurrent_duplicate_conflict_and_other_workspace_refused(self):
        raw=command(self.sid,'same',0,'ADVANCE',dict(targetNs='0'))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.controller().apply(self.scope,deepcopy(raw)),range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.controller().inspect(self.scope,self.sid)['state']['revision'],1)
        changed=deepcopy(raw);changed['payload']['targetNs']=str(S)
        with self.assertRaisesRegex(ValueError,'REFUSED_IDEMPOTENCY_CONFLICT'):self.controller().apply(self.scope,changed)
        with self.assertRaisesRegex(ValueError,'RESOURCE_UNAVAILABLE'):self.controller().inspect(TrustedScope('other:workspace','other:actor'),self.sid)
        with self.assertRaises(ValueError):self.controller().inspect({'workspace_id':self.scope.workspace_id},self.sid)

    def test_before_commit_process_death_rolls_back_after_commit_death_retries_once(self):
        raw=command(self.sid,'worker',0,'ADVANCE',dict(targetNs='0'))
        data=dict(profile=self.fx.profile.wire,folder=str(self.folder),proof=str(self.proof),proofHash=self.proof_hash,logs=str(self.root/'controller-logs'),workspace=self.scope.workspace_id,command=raw,phase='before')
        def run(phase):
            data['phase']=phase;env=dict(os.environ,BTL_OBSERVED_WORKER=json.dumps(data))
            return subprocess.run([sys.executable,'-B','-m','tests.test_observed_postgres','--worker'],env=env,capture_output=True,text=True,timeout=60)
        before=run('before');self.assertEqual(before.returncode,73,before.stderr);self.assertEqual(self.c.inspect(self.scope,self.sid)['state']['revision'],0)
        after=run('after');self.assertEqual(after.returncode,74,after.stderr);view=self.c.inspect(self.scope,self.sid);self.assertEqual(view['state']['revision'],1)
        retry=self.c.apply(self.scope,raw);self.assertEqual(retry['state'],view['state'])

    def test_qa_v3_postgres_delta_atomic_financial_parity_and_recovery(self):
        from contextlib import contextmanager
        import psycopg
        import execution.observed_postgres as storage
        from execution.observed_postgres import QA3_RESULT,unpack
        from contracts.canonical import content_hash
        sid=self.sid;legacy_scope=self.scope
        qa_scope=TrustedScope(self.scope.workspace_id+':delta-v3',self.scope.actor_ref)
        suffix=uuid.uuid4().hex[:12]
        legacy_dsn=isolated_database(DSN,'cp6a4_legacy_'+suffix)
        delta_dsn=isolated_database(DSN,'cp6a4_v3_'+suffix)
        legacy_store=ObservedExecutionStore(legacy_dsn)
        delta_store=ObservedExecutionStore(delta_dsn,qa_state_delta_v3=True)
        legacy_controller=ObservedExecutionController(legacy_store,lambda _:self.source)
        delta_controller=ObservedExecutionController(delta_store,lambda _:self.source)

        def database_bytes(dsn):
            with connect(dsn) as db:return int(db.execute('SELECT pg_database_size(current_database())').fetchone()[0])
        def current_lsn():
            with connect(DSN) as db:return db.execute('SELECT pg_current_wal_lsn()').fetchone()[0]
        def wal_delta(first,last):
            with connect(DSN) as db:return int(db.execute('SELECT pg_wal_lsn_diff(%s,%s)',(last,first)).fetchone()[0])
        def checkpoint_cluster():
            with psycopg.connect(DSN,autocommit=True) as db:db.execute('CHECKPOINT')
        def wal_allocated_bytes():
            root=Path(os.environ['BTL_QA_CLUSTER_ROOT'])/'data'/'pg_wal'
            return sum(path.stat().st_blocks*512 for path in root.rglob('*') if path.is_file())
        def write_footprint(dsn,workspace,revision_number,command_id=None):
            with connect(dsn) as db:
                def rows(table,where,params):
                    return db.execute(f'SELECT coalesce(sum(pg_column_size(t)),0),coalesce(sum(octet_length(t.payload)),0) FROM {table} AS t WHERE {where}',params).fetchone()
                measures=[rows('btl.tick_sessions','workspace_id=%s AND session_id=%s',(workspace,sid)),
                          rows('btl.tick_checkpoints','workspace_id=%s AND session_id=%s AND revision=%s',(workspace,sid,revision_number))]
                if command_id is not None:
                    measures.append(rows('btl.tick_commands','workspace_id=%s AND session_id=%s AND command_id=%s',(workspace,sid,command_id)))
                    measures.append(rows('btl.tick_events','workspace_id=%s AND session_id=%s AND command_id=%s',(workspace,sid,command_id)))
                return dict(tupleBytes=sum(int(x[0]) for x in measures),payloadBytes=sum(int(x[1]) for x in measures))

        legacy_before=database_bytes(legacy_dsn);delta_before=database_bytes(delta_dsn)
        legacy_rows_written=0;legacy_payload_written=0
        checkpoint_cluster();legacy_wal_before=wal_allocated_bytes();legacy_lsn_start=current_lsn();legacy_controller.create(legacy_scope,sid,self.fx.profile,self.fx.policy,period='1970-01',balance='10000')
        legacy_create_footprint=write_footprint(legacy_dsn,legacy_scope.workspace_id,0)
        legacy_rows_written+=legacy_create_footprint['tupleBytes'];legacy_payload_written+=legacy_create_footprint['payloadBytes']
        legacy_times=[];legacy_results=[];commands=[]
        def apply_legacy(raw):
            start=time.perf_counter();result=legacy_controller.apply(legacy_scope,raw);elapsed=time.perf_counter()-start
            legacy_times.append(elapsed);legacy_results.append(result);commands.append(raw)
            size=write_footprint(legacy_dsn,legacy_scope.workspace_id,result['state']['revision'],raw['commandId'])
            nonlocal legacy_rows_written,legacy_payload_written
            legacy_rows_written+=size['tupleBytes'];legacy_payload_written+=size['payloadBytes']
            return result

        first=apply_legacy(command(sid,'parity:open-quote',0,'ADVANCE',dict(targetNs='0')))
        basis=first['state']['quoteBasis'];bid=float(basis['bid']);ask=float(basis['ask'])
        stop=dict(side='LONG',orderType='STOP',workflow='PLANNED',entry=f'{ask+0.1:.3f}',quantity='0.01',
                  sl=f'{ask-0.1:.3f}',tp=f'{ask+1.0:.3f}',riskPercent='1',observations=[])
        apply_legacy(command(sid,'order:parity-stop',1,'OPEN',stop))
        limit=dict(side='LONG',orderType='LIMIT',workflow='PLANNED',entry=f'{bid-5:.3f}',quantity='0.01',
                   sl=f'{bid-6:.3f}',tp=f'{bid-4:.3f}',riskPercent='1',observations=[])
        apply_legacy(command(sid,'order:parity-cancel',2,'OPEN',limit))
        apply_legacy(command(sid,'parity:entry',3,'ADVANCE',dict(targetNs=str(S))))
        apply_legacy(command(sid,'parity:exit',4,'ADVANCE',dict(targetNs=str(2*S))))
        apply_legacy(command(sid,'parity:cancel',5,'CANCEL',dict(orderId='order:parity-cancel')))
        legacy_lsn_end=current_lsn();legacy_after=database_bytes(legacy_dsn);legacy_wal_after=wal_allocated_bytes()

        checkpoint_cluster()
        qa_wal_before=wal_allocated_bytes();delta_lsn_start=current_lsn();delta_controller.create(qa_scope,sid,self.fx.profile,self.fx.policy,period='1970-01',balance='10000')
        delta_create_footprint=write_footprint(delta_dsn,qa_scope.workspace_id,0)
        delta_rows_written=delta_create_footprint['tupleBytes'];delta_payload_written=delta_create_footprint['payloadBytes']
        delta_times=[];delta_results=[]
        for index,raw in enumerate(commands):
            if index<5:
                start=time.perf_counter();result=delta_controller.apply(qa_scope,raw);elapsed=time.perf_counter()-start
                delta_times.append(elapsed)
            else:
                worker_data=dict(profile=self.fx.profile.wire,folder=str(self.folder),proof=str(self.proof),proofHash=self.proof_hash,
                    logs=str(self.root/'controller-logs'),workspace=qa_scope.workspace_id,actor=qa_scope.actor_ref,
                    dsn=delta_dsn,command=raw,phase='delta_after_commit',qaStateDeltaV3=True)
                proc=subprocess.run([sys.executable,'-B','-m','tests.test_observed_postgres','--worker'],
                    env=dict(os.environ,BTL_OBSERVED_WORKER=json.dumps(worker_data)),capture_output=True,text=True,timeout=60)
                self.assertEqual(proc.returncode,-signal.SIGKILL,proc.stderr)
                start=time.perf_counter();result=delta_controller.apply(qa_scope,raw);elapsed=time.perf_counter()-start
            self.assertEqual(canonical_bytes(legacy_results[index]),canonical_bytes(result))
            delta_results.append(result)
            size=write_footprint(delta_dsn,qa_scope.workspace_id,result['state']['revision'],raw['commandId'])
            delta_rows_written+=size['tupleBytes'];delta_payload_written+=size['payloadBytes']
        delta_lsn_end=current_lsn();delta_after=database_bytes(delta_dsn);qa_wal_after=wal_allocated_bytes()
        self.assertEqual(len(commands),6)
        self.assertGreater(float(legacy_results[-1]['state']['realizedGross']),0)
        self.assertEqual(canonical_bytes(legacy_results[-1]['state']),canonical_bytes(delta_results[-1]['state']))

        # Cold reconstruction, all receipt retries, and independent raw ledger checks.
        start=time.perf_counter();legacy_cold=ObservedExecutionController(ObservedExecutionStore(legacy_dsn),lambda _:self.source).inspect(legacy_scope,sid);legacy_cold_seconds=time.perf_counter()-start
        fresh_delta_controller=ObservedExecutionController(ObservedExecutionStore(delta_dsn,qa_state_delta_v3=True),lambda _:self.source)
        start=time.perf_counter();delta_cold=fresh_delta_controller.inspect(qa_scope,sid);delta_cold_seconds=time.perf_counter()-start
        self.assertEqual(canonical_bytes(legacy_cold['state']),canonical_bytes(delta_cold['state']))
        for raw,wanted in zip(commands,legacy_results):
            replayed=fresh_delta_controller.apply(qa_scope,raw)
            self.assertEqual(canonical_bytes(replayed),canonical_bytes(wanted))

        with connect(legacy_dsn) as db:
            legacy_receipts=db.execute('SELECT revision,command_id,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(legacy_scope.workspace_id,sid)).fetchall()
            legacy_events=db.execute('SELECT event_id,payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',(legacy_scope.workspace_id,sid)).fetchall()
        with connect(delta_dsn) as db:
            receipt_rows=db.execute('SELECT revision,command_id,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(qa_scope.workspace_id,sid)).fetchall()
            event_rows=db.execute('SELECT event_id,payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',(qa_scope.workspace_id,sid)).fetchall()
            checkpoint_rows=db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(qa_scope.workspace_id,sid)).fetchall()
            tip_row=db.execute('SELECT payload,content_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',(qa_scope.workspace_id,sid)).fetchone()
            base_payload=bytes(checkpoint_rows[0][1])
            delta_payloads=[bytes(r[1]) for r in checkpoint_rows[1:]]
            total_counts=db.execute('SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s',(qa_scope.workspace_id,sid)).fetchone()[0]

        self.assertEqual(total_counts,6);self.assertEqual(len(receipt_rows),6);self.assertEqual(len(checkpoint_rows),7)
        self.assertEqual(len(legacy_receipts),6);self.assertEqual(len(event_rows),len(legacy_events))
        # Receipt format hashes are verified against their own versioned bytes.
        from execution.observed_state_delta_v3 import reconstruct,reconstruct_complete
        base_wire=unpack(base_payload,checkpoint_rows[0][2])
        self.assertEqual(base_wire['artifact'],'BTL-OBSERVED-EXECUTION-CHECKPOINT-BASE-3')
        previous=base_wire['chainHash'];deltas=[]
        for index,(row,wire_payload) in enumerate(zip(checkpoint_rows[1:],delta_payloads),1):
            rev,payload,digest=row;checkpoint=unpack(payload,digest)
            self.assertEqual((checkpoint['revision'],checkpoint['previousHash']),(index,previous))
            self.assertEqual(checkpoint['artifact'],'BTL-OBSERVED-EXECUTION-CHECKPOINT-DELTA-3')
            self.assertNotIn('state',checkpoint)
            deltas.append(checkpoint['delta']);previous=checkpoint['chainHash']
            rebuilt=reconstruct_complete(base_wire,deltas,index)
            self.assertEqual(checkpoint['stateHash'],content_hash(rebuilt))
        for index,(legacy_row,compact_row) in enumerate(zip(legacy_receipts,receipt_rows)):
            revision_number,command_id,command_hash,legacy_payload,legacy_hash=legacy_row
            compact_revision,compact_id,compact_command_hash,compact_payload,compact_hash=compact_row
            self.assertEqual((revision_number,command_id,command_hash),(compact_revision,compact_id,compact_command_hash))
            old_receipt=unpack(legacy_payload,legacy_hash)
            compact_receipt=unpack(compact_payload,compact_hash)
            self.assertEqual(compact_receipt['artifact'],QA3_RESULT)
            self.assertNotIn('state',compact_receipt)
            self.assertEqual(compact_receipt['stateHash'],content_hash(delta_results[index]['state']))
            checkpoint_wire=unpack(checkpoint_rows[index+1][1],checkpoint_rows[index+1][2])
            self.assertEqual(compact_receipt['chainHash'],checkpoint_wire['chainHash'])
            self.assertEqual(canonical_bytes(old_receipt['state']),canonical_bytes(delta_results[index]['state']))
            self.assertEqual(old_receipt['events'],compact_receipt['events'])
        previous=unpack(base_payload,checkpoint_rows[0][2])['state']['eventHash']
        for sequence,(event_id,payload,digest) in enumerate(event_rows):
            event=unpack(payload,digest)
            self.assertEqual(event['eventId'],event_id)
            self.assertEqual(content_hash({k:v for k,v in event.items() if k!='eventId'}),event_id)
            self.assertEqual((event['sequence'],event['previousHash']),(sequence,previous));previous=event_id
        self.assertEqual(previous,delta_cold['state']['eventHash'])
        fills=[unpack(p,h) for _,p,h in event_rows]
        self.assertEqual([e['kind'] for e in fills if e['classification']=='SIMULATED_FILL'],['ENTRY_FILL','EXIT_FILL'])
        self.assertEqual(next(e for e in fills if e['kind']=='EXIT_FILL')['detail']['reason'],'TP')
        self.assertEqual(legacy_cold['state']['balance'],delta_cold['state']['balance'])
        self.assertEqual([(r[0],bytes(r[1]),r[2]) for r in legacy_events],[(r[0],bytes(r[1]),r[2]) for r in event_rows])

        # Recovery must reject omitted, reordered, and corrupted checkpoint deltas.
        with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):reconstruct_complete(base_wire,deltas[:2]+deltas[3:],6)
        with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):reconstruct(base_wire,[deltas[1],deltas[0],*deltas[2:]])
        corrupt=deepcopy(deltas);corrupt[2]['body']['previousHash']='0'*64
        with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):reconstruct(base_wire,corrupt)
        # Opt-in reader still opens an ordinary legacy v1 Session unchanged.
        compat=ObservedExecutionController(ObservedExecutionStore(legacy_dsn,qa_state_delta_v3=True),lambda _:self.source)
        self.assertEqual(canonical_bytes(compat.inspect(legacy_scope,sid)['state']),canonical_bytes(legacy_cold['state']))

        # Force a failed QA-v3 transition. All writes, including compact receipt
        # and checkpoint delta, must roll back in the same transaction.
        native=storage.connect;calls=[0]
        @contextmanager
        def fail_after_transaction(dsn):
            calls[0]+=1
            with native(dsn) as db:
                yield db
                if calls[0]==2:raise RuntimeError('QA_V3_FORCED_ABORT')
        rollback=command(sid,'parity:rollback',6,'ADVANCE',dict(targetNs=str(3*S)))
        storage.connect=fail_after_transaction
        try:
            with self.assertRaisesRegex(RuntimeError,'QA_V3_FORCED_ABORT'):delta_controller.apply(qa_scope,rollback)
        finally:storage.connect=native
        self.assertEqual(canonical_bytes(delta_controller.inspect(qa_scope,sid)['state']),canonical_bytes(delta_cold['state']))
        with connect(delta_dsn) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s',(qa_scope.workspace_id,sid)).fetchone()[0],6)
            self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s',(qa_scope.workspace_id,sid)).fetchone()[0],7)

        # Exact payload, tuple and database growth accounting for each isolated DB.
        def final_sizes(dsn,workspace,qa=False):
            with connect(dsn) as db:
                specs=[('btl.tick_commands','workspace_id=%s AND session_id=%s'),('btl.tick_events','workspace_id=%s AND session_id=%s'),
                       ('btl.tick_checkpoints','workspace_id=%s AND session_id=%s'),('btl.tick_sessions','workspace_id=%s AND session_id=%s')]
                result={}
                for table,where in specs:
                    values=db.execute(f'SELECT coalesce(sum(pg_column_size(t)),0),coalesce(sum(octet_length(t.payload)),0) FROM {table} AS t WHERE {where}',(workspace,sid)).fetchone()
                    result[table]=dict(tupleBytes=int(values[0]),payloadBytes=int(values[1]))
                result['receiptPayloadSizes']=[int(r[0]) for r in db.execute('SELECT octet_length(payload) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(workspace,sid)).fetchall()]
                result['checkpointPayloadSizes']=[int(r[0]) for r in db.execute('SELECT octet_length(payload) FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(workspace,sid)).fetchall()]
                result['tipPayloadBytes']=int(db.execute('SELECT octet_length(payload) FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s',(workspace,sid)).fetchone()[0])
                if qa:
                    result['deltaPayloadSizes']=[len(canonical_bytes(unpack(payload,digest)['delta'])) for revision_number,payload,digest in db.execute('SELECT revision,payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision>0 ORDER BY revision',(workspace,sid)).fetchall()]
                return result
        legacy_final=final_sizes(legacy_dsn,legacy_scope.workspace_id)
        delta_final=final_sizes(delta_dsn,qa_scope.workspace_id,True)
        legacy_total_db_growth=legacy_after-legacy_before;delta_total_db_growth=delta_after-delta_before
        legacy_total_physical_growth=legacy_total_db_growth+legacy_wal_after-legacy_wal_before
        delta_total_physical_growth=delta_total_db_growth+qa_wal_after-qa_wal_before
        logical_legacy=sum(x['tupleBytes'] for x in legacy_final.values() if isinstance(x,dict) and 'tupleBytes' in x)
        logical_delta=sum(x['tupleBytes'] for x in delta_final.values() if isinstance(x,dict) and 'tupleBytes' in x)
        storage_pass=delta_total_physical_growth<legacy_total_physical_growth and delta_rows_written<legacy_rows_written
        report=dict(status='PASS' if storage_pass else 'NO_GO',commands=6,events=len(event_rows),simulatedFills=2,finalBalance=delta_cold['state']['balance'],
            legacyDatabaseBeforeBytes=legacy_before,legacyDatabaseAfterBytes=legacy_after,legacyDatabaseGrowthBytes=legacy_total_db_growth,
            qaV3DatabaseBeforeBytes=delta_before,qaV3DatabaseAfterBytes=delta_after,qaV3DatabaseGrowthBytes=delta_total_db_growth,
            legacyWalAllocatedBeforeBytes=legacy_wal_before,legacyWalAllocatedAfterBytes=legacy_wal_after,
            qaV3WalAllocatedBeforeBytes=qa_wal_before,qaV3WalAllocatedAfterBytes=qa_wal_after,
            legacyTotalPhysicalGrowthBytes=legacy_total_physical_growth,qaV3TotalPhysicalGrowthBytes=delta_total_physical_growth,
            legacyLogicalRowWriteBytes=legacy_rows_written,qaV3LogicalRowWriteBytes=delta_rows_written,
            legacyLogicalPayloadWriteBytes=legacy_payload_written,qaV3LogicalPayloadWriteBytes=delta_payload_written,
            legacyFinalRows=legacy_final,qaV3FinalRows=delta_final,
            legacyReceiptPayloadSizes=legacy_final['receiptPayloadSizes'],qaV3ReceiptPayloadSizes=delta_final['receiptPayloadSizes'],
            legacyCheckpointPayloadSizes=legacy_final['checkpointPayloadSizes'],qaV3CheckpointPayloadSizes=delta_final['checkpointPayloadSizes'],
            legacyTipPayloadBytes=legacy_final['tipPayloadBytes'],qaV3TipPayloadBytes=delta_final['tipPayloadBytes'],
            qaV3DeltaPayloadSizes=delta_final['deltaPayloadSizes'],
            legacyWalBytes=wal_delta(legacy_lsn_start,legacy_lsn_end),qaV3WalBytes=wal_delta(delta_lsn_start,delta_lsn_end),
            legacyApplySeconds=[round(x,6) for x in legacy_times[:5]],qaV3ApplySeconds=[round(x,6) for x in delta_times],
            legacyColdResumeSeconds=round(legacy_cold_seconds,6),qaV3ColdResumeSeconds=round(delta_cold_seconds,6),
            legacyLogicalFinalRowBytes=logical_legacy,qaV3LogicalFinalRowBytes=logical_delta,
            note='Physical DB growth includes PostgreSQL metadata and indexes; WAL bytes are LSN deltas; QA-v3 receipt hashes are format-specific.')
        report_path=os.environ.get('BTL_QA_DELTA_V3_REPORT')
        if report_path:Path(report_path).write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
        self.assertLess(delta_total_physical_growth,legacy_total_physical_growth,'NO_NET_POSTGRES_STORAGE_SAVINGS')
        self.assertLess(delta_rows_written,legacy_rows_written,'NO_NET_LOGICAL_ROW_SAVINGS')

    def test_mutated_session_tip_cannot_replace_immutable_checkpoint(self):
        from execution.postgres import pack
        view=self.c.inspect(self.scope,self.sid);state=view['state'];stored,_=self.store.prepare(self.scope,command(self.sid,'peek',0,'END'))
        bad=deepcopy(stored);bad['state']['revision']=1;bad['state']['quoteBasis']=None;raw,sha=pack(bad)
        with connect(DSN) as db:db.execute('UPDATE btl.tick_sessions SET revision=1,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s',(raw,sha,self.scope.workspace_id,self.sid))
        with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):self.c.inspect(self.scope,self.sid)

    def test_failed_write_transaction_keeps_state_and_then_source_orphan_recovers(self):
        import execution.observed_postgres as storage
        native=storage.connect;calls=[0]
        @contextmanager
        def interrupted(dsn):
            calls[0]+=1
            with native(dsn) as db:
                yield db
                if calls[0]==2:raise RuntimeError('authored precommit failure')
        raw=command(self.sid,'rollback',0,'ADVANCE',dict(targetNs='0'))
        with patch.object(storage,'connect',interrupted),self.assertRaises(RuntimeError):self.c.apply(self.scope,raw)
        self.assertEqual(self.c.inspect(self.scope,self.sid)['state']['revision'],0)
        result=self.c.apply(self.scope,raw);self.assertEqual(result['state']['revision'],1)

    def test_guarded_source_hash_permissions_and_exact_day_selection(self):
        self.assertEqual(self.source.start_for_period('1970-01',day='1970-01-01'),0)
        with self.assertRaisesRegex(ValueError,'OBSERVED_PERIOD_UNAVAILABLE'):self.source.start_for_period('1970-01',day='1970-01-02')
        with self.assertRaises(ValueError):AdmittedObservedSource(self.folder,self.fx.profile,receipt_path=self.proof,receipt_sha256='0'*64,log_root=self.root/'bad')
        (self.folder/'archive.sqlite').chmod(0o600)
        with self.assertRaisesRegex(ValueError,'REFUSED_UNPROTECTED_SOURCE'):self.source.assert_current()
        (self.folder/'archive.sqlite').chmod(0o400)


    def test_restricted_runtime_commits_but_cannot_modify_evidence(self):
        import psycopg
        from psycopg import sql
        from execution.postgres import grant_execution_runtime
        role='observed_runtime_'+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        grant_execution_runtime(DSN,role)
        @contextmanager
        def restricted(dsn):
            with connect(dsn) as db:
                db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)));yield db
        with patch('execution.observed_postgres.connect',restricted):
            self.call('ADVANCE',dict(targetNs='0'));self.call('OPEN',self.opening(),cid='restricted:order');self.call('ADVANCE',dict(targetNs=str(S)))
            self.call('CLOSE',dict(orderId='restricted:order',quantity=None));result=self.call('ADVANCE',dict(targetNs=str(2*S)))
            self.assertEqual(result['state']['balance'],'10001')
        for query in ('DELETE FROM btl.tick_events','UPDATE btl.tick_events SET content_hash=content_hash'):
            with self.assertRaises(psycopg.DatabaseError):
                with restricted(DSN) as db:db.execute(query)

    def test_nonempty_sidecar_is_not_admitted_by_empty_catalog_capability(self):
        other=fixtures.ObservedKernelTests();other.setUp();other.setup_stream([(0,'2300','2300.1'),(S,'2300.9','2301')],diagnostic=True)
        folder=other.root/'store';archive=folder/'archive.sqlite';proof=other.root/'proof.json'
        try:
            r=dict(self.receipt,rows=2,datasetId=other.profile.wire['primary']['datasetId'],datasetVersion=other.profile.wire['primary']['datasetVersion'],readArchiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest())
            proof.write_text(json.dumps(r));archive.chmod(0o400);folder.chmod(0o500)
            with self.assertRaisesRegex(ValueError,'REFUSED_UNSUPPORTED_OBSERVED_SIDECARS'):
                AdmittedObservedSource(folder,other.profile,receipt_path=proof,receipt_sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),log_root=other.root/'guarded-logs')
        finally:folder.chmod(0o700);archive.chmod(0o600);other.tearDown()

    def test_observed_research_application_method_session_review_statistics_journal(self):
        from threading import RLock
        from collections import OrderedDict
        from execution.observed_catalog import ObservedCatalog
        from execution.observed_profile import MODEL
        from execution.observed_research import ObservedResearchApplication
        catalog=object.__new__(ObservedCatalog);key='source:2024-01'
        catalog._entries={key:dict(key=key,period='2024-01',label='Authored QA XAUUSD',profile=self.fx.profile.wire)}
        private=dict(profile=self.fx.profile.wire,folder=str(self.folder),receiptPath=str(self.proof),receiptSha256=self.proof_hash,logRoot=str(self.root/'controller-logs'))
        catalog._profiles={self.fx.profile.profile_hash:private};catalog._cache=OrderedDict([(self.fx.profile.profile_hash,self.source)]);catalog._lock=RLock()
        catalog.public=lambda:[dict(key=key,period='2024-01',label='Authored QA XAUUSD',model=MODEL,profileHash=self.fx.profile.profile_hash,profile=self.fx.profile.wire)]
        app=ObservedResearchApplication(DSN,self.scope,catalog)
        method=dict(schemaVersion=1,artifact='BTL-LOCAL-METHOD-1',id='method:observed-app',name='Observed app QA',kind='FREE_STYLE',checklistOn=False,conditions=[],riskPercent=None,rr=None)
        app_sid='session:observed-app';session=dict(id=app_sid,name='Observed app QA',methodId=method['id'],initialBalance='10000',sourceKey=key,period='2024-01',day=None)
        with patch.object(self.source,'start_for_period',return_value=0):
            app.create_method(method);view=app.create_session(session)
            self.assertEqual(view['metadata']['model'],MODEL);self.assertEqual(view['analysis']['status'],'COMPLETE')
            app.apply(app_sid,command(app_sid,'app:advance:0',0,'ADVANCE',dict(targetNs='0')))
            request=dict(sessionId=app_sid,requestId='app:order',expectedRevision=1,planId=None,planRevision=None,
                draft=dict(side='LONG',orderType='MARKET',workflow='QUICK',entry='2300.1',quantity='0.01',sl=None,tp=None,riskPercent='1',observations=[]))
            # The browser's planned ticket omits quantity and asks the server
            # to size it from risk. Explicit-lot API requests miss this path.
            planned=deepcopy(request)
            planned.update(requestId='app:planned-review',planId='plan:browser',planRevision=0)
            planned['draft'].update(orderType='LIMIT',workflow='PLANNED',entry='2300',
                                    quantity=None,sl='2299',tp='2302',riskPercent='0.1')
            sized=app.review(planned)
            self.assertEqual(sized['review']['command']['payload']['quantity'],'0.1')
            self.assertEqual(app.review(planned),sized)
            self.assertEqual(app.summary(app_sid)['revision'],1)
            reviewed=app.review(request);accepted=app.confirm(app_sid,dict(reviewId='app:order',reviewHash=reviewed['reviewHash']))
            self.assertTrue(accepted['durable'])
            latest=app.summary(app_sid);app.apply(app_sid,command(app_sid,'app:advance:1',latest['revision'],'ADVANCE',dict(targetNs=str(S))))
            current=app.summary(app_sid);app.apply(app_sid,command(app_sid,'app:close',current['revision'],'CLOSE',dict(orderId='app:order',quantity=None)))
            current=app.summary(app_sid);app.apply(app_sid,command(app_sid,'app:advance:2',current['revision'],'ADVANCE',dict(targetNs=str(2*S))))
            result=app.inspect(app_sid);self.assertEqual(result['analysis']['metrics']['tradeCount'],1)
            self.assertEqual(result['analysis']['completed'][0]['id'],'app:order')
            self.assertEqual(result['analysis']['completed'][0]['exitTimeNs'],str(2*S))
            saved=app.save_note(app_sid,dict(orderId='app:order',expectedNoteRevision=0,text='Observed app acceptance',tags=['qa']))
            self.assertEqual(saved['noteRevision'],1)
            with patch.object(catalog,'resolve',side_effect=AssertionError('Journal must not admit market archives')):
                self.assertEqual(app.journal(app_sid)['notes'][0]['text'],'Observed app acceptance')


if __name__=='__main__' and '--worker' in sys.argv:worker()
