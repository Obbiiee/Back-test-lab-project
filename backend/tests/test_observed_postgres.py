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
    store=ObservedExecutionStore(DSN,qa_state_delta_v3=bool(data.get('qaStateDeltaV3',False)))
    controller=ObservedExecutionController(store,lambda _:source)
    controller.apply(TrustedScope(data['workspace'],data.get('actor','authored:worker')),data['command'])
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
        from execution.observed_postgres import pack,unpack
        from contextlib import contextmanager
        import execution.observed_postgres as storage
        legacy_scope=self.scope
        qa_scope=TrustedScope(self.scope.workspace_id+':delta-v3',self.scope.actor_ref)
        sid=self.sid
        delta_store=ObservedExecutionStore(DSN,qa_state_delta_v3=True)
        legacy_controller=self.c
        delta_controller=ObservedExecutionController(delta_store,lambda _:self.source)
        delta_controller.create(qa_scope,sid,self.fx.profile,self.fx.policy,period='1970-01',balance='10000')

        paired_timings=[]
        def pair(kind,payload=None,cid=None):
            rev=legacy_controller.inspect(legacy_scope,sid)['state']['revision']
            raw=command(sid,cid or f'parity:{rev}',rev,kind,payload)
            start=time.perf_counter();a=legacy_controller.apply(legacy_scope,raw);legacy_elapsed=time.perf_counter()-start
            start=time.perf_counter();b=delta_controller.apply(qa_scope,raw);delta_elapsed=time.perf_counter()-start
            paired_timings.append((legacy_elapsed,delta_elapsed))
            self.assertEqual(canonical_bytes(a),canonical_bytes(b))
            return a

        pair('ADVANCE',dict(targetNs='0'),'parity:open-quote')
        basis=legacy_controller.inspect(legacy_scope,sid)['state']['quoteBasis'];bid=float(basis['bid']);ask=float(basis['ask'])
        stop=dict(side='LONG',orderType='STOP',workflow='PLANNED',entry=f'{ask+0.1:.3f}',quantity='0.01',
                  sl=f'{ask-0.1:.3f}',tp=f'{ask+1.0:.3f}',riskPercent='1',observations=[])
        pair('OPEN',stop,'order:parity-stop')
        limit=dict(side='LONG',orderType='LIMIT',workflow='PLANNED',entry=f'{bid-5:.3f}',quantity='0.01',
                   sl=f'{bid-6:.3f}',tp=f'{bid-4:.3f}',riskPercent='1',observations=[])
        pair('OPEN',limit,'order:parity-cancel')
        pair('ADVANCE',dict(targetNs=str(S)),'parity:entry')
        pair('ADVANCE',dict(targetNs=str(2*S)),'parity:exit')
        pair('CANCEL',dict(orderId='order:parity-cancel'),'parity:cancel')
        full=legacy_controller.inspect(legacy_scope,sid)['state'];delta_state=delta_controller.inspect(qa_scope,sid)['state']
        self.assertEqual(canonical_bytes(full),canonical_bytes(delta_state))
        self.assertEqual([e['kind'] for e in legacy_controller.inspect(legacy_scope,sid,maximum=64)['events']],
                         [e['kind'] for e in delta_controller.inspect(qa_scope,sid,maximum=64)['events']])
        with connect(DSN) as db:
            rows=db.execute('SELECT revision,payload,content_hash FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(qa_scope.workspace_id,sid)).fetchall()
            receipts=db.execute('SELECT command_id,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(qa_scope.workspace_id,sid)).fetchall()
            events=db.execute('SELECT event_id,payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',(qa_scope.workspace_id,sid)).fetchall()
            legacy_receipts=db.execute('SELECT command_id,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s ORDER BY revision',(legacy_scope.workspace_id,sid)).fetchall()
            legacy_events=db.execute('SELECT event_id,payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',(legacy_scope.workspace_id,sid)).fetchall()
            physical_delta_bytes=db.execute("SELECT pg_total_relation_size('public.btl_qa_state_delta_v3')+pg_total_relation_size('public.btl_qa_state_base_v3')").fetchone()[0]
            database_bytes=db.execute('SELECT pg_database_size(current_database())').fetchone()[0]
        self.assertEqual(len(rows),full['revision']);self.assertEqual(len(receipts),full['revision']);self.assertGreater(len(events),0)
        self.assertEqual([(r[0],r[1],bytes(r[2]),r[3]) for r in receipts],[(r[0],r[1],bytes(r[2]),r[3]) for r in legacy_receipts])
        self.assertEqual([(r[0],bytes(r[1]),r[2]) for r in events],[(r[0],bytes(r[1]),r[2]) for r in legacy_events])
        from execution.observed_postgres import unpack
        from contracts.canonical import content_hash
        with connect(DSN) as db:
            initial_raw,initial_hash=db.execute('SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0',(qa_scope.workspace_id,sid)).fetchone()
        previous=unpack(initial_raw,initial_hash)['state']['eventHash']
        for expected_revision,(command_id,command_hash,payload,receipt_hash) in enumerate(receipts,1):
            result=unpack(payload,receipt_hash)
            self.assertEqual((result['commandId'],result['commandHash'],result['state']['revision']),(command_id,command_hash,expected_revision))
        for sequence,(event_id,payload,event_hash) in enumerate(events):
            event=unpack(payload,event_hash)
            self.assertEqual(event['eventId'],event_id)
            self.assertEqual(content_hash({k:v for k,v in event.items() if k!='eventId'}),event_id)
            self.assertEqual((event['sequence'],event['previousHash']),(sequence,previous))
            previous=event_id
        self.assertEqual(previous,delta_state['eventHash'])
        self.assertGreater(float(full['realizedGross']),0)
        delta_bytes=sum(len(bytes(r[1])) for r in rows)
        self.assertGreater(delta_bytes,0)
        # Force an exception after the QA delta INSERT but before PostgreSQL
        # context exit; the event, receipt, checkpoint, tip, and delta all roll back.
        rollback=command(sid,'parity:rollback',full['revision'],'ADVANCE',dict(targetNs=str(3*S)))
        native=storage.connect;calls=[0]
        @contextmanager
        def fail_after_transaction(dsn):
            calls[0]+=1
            with native(dsn) as db:
                yield db
                if calls[0]==2:raise RuntimeError('QA_V3_FORCED_ABORT')
        storage.connect=fail_after_transaction
        try:
            with self.assertRaisesRegex(RuntimeError,'QA_V3_FORCED_ABORT'):delta_controller.apply(qa_scope,rollback)
        finally:storage.connect=native
        after=delta_controller.inspect(qa_scope,sid)['state'];self.assertEqual(canonical_bytes(after),canonical_bytes(full))
        with connect(DSN) as db:
            self.assertIsNone(db.execute('SELECT 1 FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s AND command_id=%s',(qa_scope.workspace_id,sid,'parity:rollback')).fetchone())
            self.assertIsNone(db.execute('SELECT 1 FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s',(qa_scope.workspace_id,sid,'parity:rollback')).fetchone())
        retry=delta_controller.apply(qa_scope,rollback);self.assertEqual(retry['state']['revision'],full['revision']+1)
        # Committed retry after process death reuses native worker fault hook.
        tip=delta_controller.inspect(qa_scope,sid)['state'];raw=command(sid,'parity:sigkill',tip['revision'],'ADVANCE',dict(targetNs=str(4*S)))
        worker_data=dict(profile=self.fx.profile.wire,folder=str(self.folder),proof=str(self.proof),proofHash=self.proof_hash,
            logs=str(self.root/'controller-logs'),workspace=qa_scope.workspace_id,actor=qa_scope.actor_ref,command=raw,
            phase='delta_after_commit',qaStateDeltaV3=True)
        proc=subprocess.run([sys.executable,'-B','-m','tests.test_observed_postgres','--worker'],
            env=dict(os.environ,BTL_OBSERVED_WORKER=json.dumps(worker_data)),capture_output=True,text=True,timeout=60)
        self.assertEqual(proc.returncode,-signal.SIGKILL,proc.stderr)
        final=delta_controller.inspect(qa_scope,sid)['state'];retry=delta_controller.apply(qa_scope,raw)
        self.assertEqual(canonical_bytes(retry['state']),canonical_bytes(final))
        with connect(DSN) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s',(qa_scope.workspace_id,sid,'parity:sigkill')).fetchone()[0],1)
        with connect(DSN) as db:
            payload=bytes(db.execute('SELECT payload FROM public.btl_qa_state_delta_v3 WHERE workspace_id=%s AND session_id=%s ORDER BY revision DESC LIMIT 1',(qa_scope.workspace_id,sid)).fetchone()[0])
            db.execute('UPDATE public.btl_qa_state_delta_v3 SET payload=%s WHERE workspace_id=%s AND session_id=%s AND revision=%s',(payload[:-1]+bytes([payload[-1]^1]),qa_scope.workspace_id,sid,final['revision']))
        with self.assertRaisesRegex(ValueError,'CORRUPT_RECORD'):delta_controller.inspect(qa_scope,sid)
        report=dict(status='PASS',revisions=full['revision'],
                    fullReceiptPayloadBytes=sum(len(bytes(r[2])) for r in receipts),
                    deltaPayloadBytes=sum(len(bytes(r[1])) for r in rows),
                    deltaAndBaseAllocatedBytes=int(physical_delta_bytes),databaseBytes=int(database_bytes),
                    events=len(events),simulatedFillEvents=sum(1 for _,payload,event_hash in events if unpack(payload,event_hash)['kind'] in ('ENTRY_FILL','EXIT_FILL')),
                    legacyApplySeconds=[round(x[0],6) for x in paired_timings],
                    deltaApplySeconds=[round(x[1],6) for x in paired_timings],
                    note='Full-state checkpoint and receipt format retained; delta measurements are additive, not storage savings.')
        report_path=os.environ.get('BTL_QA_DELTA_V3_REPORT')
        if report_path:Path(report_path).write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')

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
