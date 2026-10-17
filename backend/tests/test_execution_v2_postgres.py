"""Native v2 transaction and recovery acceptance; no application database."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import json, os, subprocess, sys, unittest, uuid, tempfile
import psycopg
from psycopg import sql
from pathlib import Path
from unittest.mock import patch
from application.models import TrustedScope
from contracts.primitives import ContractError
from execution.contracts import policy_from_wire
from execution.controller_v2 import ExecutionControllerV2
from execution.postgres_v2 import PostgresExecutionStoreV2
from infrastructure.database import migrate, connect, backup, restore
from execution.postgres import grant_execution_runtime
from tests.test_kernel_v2 import scene_system, fixture, opening

DSN=os.getenv("BTL_TEST_DATABASE_URL")

def command(session,cid,revision,kind,payload=None):
    return dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-COMMAND-2",sessionId=session,
                commandId=cid,expectedRevision=revision,kind=kind,payload=payload or {})

def system(case):return scene_system(case["symbol"],case["primaryRows"],case["conversionRows"])

def controller(h):return ExecutionControllerV2(PostgresExecutionStoreV2(DSN),h.profile,h.primary,conversion_provider=h.fx)

def worker():
    data=json.loads(os.environ["BTL_V2_WORKER"])
    import execution.postgres_v2 as storage
    if data["phase"]=="before":
        native=storage.connect
        @contextmanager
        def interrupted(dsn):
            with native(dsn) as db:
                yield db
                os._exit(73)
        # prepare is read only; only interrupt the write transaction.
        calls=[0]
        @contextmanager
        def selective(dsn):
            calls[0]+=1
            with (native(dsn) if calls[0]==1 else interrupted(dsn)) as db:yield db
        storage.connect=selective
    controller(system(data["case"])).apply(TrustedScope(data["workspace"],"fixture:worker"),data["command"])
    os._exit(74)

@unittest.skipUnless(DSN,"Requires isolated native PostgreSQL; skip is not acceptance")
class ExecutionV2PostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):migrate(DSN)
    def setUp(self):
        self.scope=TrustedScope("v2qa:"+uuid.uuid4().hex,"fixture:actor")
        self.session="fixture:v2";self.revision=0
        self.case=fixture()["scenes"][0];self.h=system(self.case);self.c=controller(self.h)
        self.c.create(self.scope,self.session,policy_from_wire(self.h.state["policy"]),start_ns="100")
    def call(self,kind,payload=None,cid=None):
        raw=command(self.session,cid or "cmd:"+str(self.revision),self.revision,kind,payload)
        result=self.c.apply(self.scope,raw);self.revision=result["state"]["revision"];return result
    def records(self):
        with connect(DSN) as db:
            return {table:db.execute("SELECT content_hash FROM btl."+table+" WHERE workspace_id=%s AND session_id=%s ORDER BY content_hash",(self.scope.workspace_id,self.session)).fetchall()
                    for table in ("tick_sessions","tick_commands","tick_events","tick_checkpoints")}
    def test_all_literal_symbols_durable_and_cold(self):
        from execution.contracts import policy_from_wire
        for i,case in enumerate(fixture()["scenes"]):
            with self.subTest(case=case["name"]):
                h=system(case);c=controller(h);session="fixture:scene:"+str(i)
                c.create(self.scope,session,policy_from_wire(h.state["policy"]),start_ns="100")
                actions=[("ADVANCE",dict(targetNs="100")),("OPEN",opening(case["side"],case["quantity"])),
                         ("ADVANCE",dict(targetNs="110")),("CLOSE",dict(orderId="scene:1",quantity=None)),("ADVANCE",dict(targetNs="120"))]
                for rev,(kind,payload) in enumerate(actions):
                    result=controller(h).apply(self.scope,command(session,"scene:"+str(rev),rev,kind,payload))
                    self.assertTrue(result["durable"])
                for key in ("balance","realizedGross","commission"):self.assertEqual(result["state"][key],case["expected"][key])
                projection=c.inspect(self.scope,session,maximum=256)
                self.assertEqual(set(projection),{"state","events"});self.assertEqual(projection["state"],result["state"])
    def test_concurrent_dedup_conflict_and_scope(self):
        raw=command(self.session,"retry",0,"ADVANCE",dict(targetNs="100"))
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(lambda _:self.c.apply(self.scope,raw),range(12)))
        self.assertTrue(all(r==results[0] for r in results));self.assertEqual(len(self.records()["tick_commands"]),1)
        with patch("execution.controller_v2.SourceJoinV2.resume",side_effect=RuntimeError("provider offline")):
            self.assertEqual(controller(self.h).apply(self.scope,raw),results[0])
        bad=deepcopy(raw);bad["payload"]["targetNs"]="110"
        with self.assertRaisesRegex(ContractError,"IDEMPOTENCY_CONFLICT"):self.c.apply(self.scope,bad)
        bad=deepcopy(raw);bad["commandId"]="stale"
        with self.assertRaisesRegex(ContractError,"STALE_REVISION"):self.c.apply(self.scope,bad)
        with self.assertRaisesRegex(ContractError,"RESOURCE_UNAVAILABLE"):self.c.apply(TrustedScope("other","fixture:actor"),raw)
    def test_cas_does_not_publish_stale_prepared_source(self):
        raw=command(self.session,"advance",0,"ADVANCE",dict(targetNs="100"))
        native=self.c._ExecutionControllerV2__store.run
        def racing(scope,cmd,operation):
            native(scope,command(self.session,"winner",0,"ADVANCE",dict(targetNs="100")),operation)
            return native(scope,cmd,operation)
        with patch.object(self.c._ExecutionControllerV2__store,"run",side_effect=racing):
            with self.assertRaisesRegex(ContractError,"STALE_REVISION"):self.c.apply(self.scope,raw)
        self.assertEqual(len(self.records()["tick_commands"]),1)
    def test_fork_is_cold_idempotent_and_parent_immutable(self):
        self.call("ADVANCE",dict(targetNs="100"));self.call("OPEN",opening(),"open");self.call("ADVANCE",dict(targetNs="110"))
        parent=self.records();raw=command("fixture:child","fork",0,"FORK",dict(parentSessionId=self.session,parentRevision=3))
        child=self.c.apply(self.scope,raw);self.assertEqual(self.c.apply(self.scope,raw),child)
        result=controller(self.h).apply(self.scope,command("fixture:child","close",1,"CLOSE",dict(orderId="open",quantity=None)))
        result=controller(self.h).apply(self.scope,command("fixture:child","tick",2,"ADVANCE",dict(targetNs="120")))
        self.assertEqual(result["state"]["balance"],self.case["expected"]["balance"]);self.assertEqual(self.records(),parent)
    def death(self,phase):
        # Crash across a real foreign-currency EXIT posting, not an empty replay.
        self.case=fixture()["scenes"][1];self.h=system(self.case);self.c=controller(self.h)
        self.session="fixture:crash";self.revision=0
        self.c.create(self.scope,self.session,policy_from_wire(self.h.state["policy"]),start_ns="100")
        self.call("ADVANCE",dict(targetNs="100"));self.call("OPEN",opening(),"open")
        self.call("ADVANCE",dict(targetNs="110"));self.call("CLOSE",dict(orderId="open",quantity=None))
        before=self.records();raw=command(self.session,"worker",4,"ADVANCE",dict(targetNs="120"))
        env=dict(os.environ,BTL_V2_WORKER=json.dumps(dict(phase=phase,case=self.case,workspace=self.scope.workspace_id,command=raw)))
        p=subprocess.run([sys.executable,"-B","-c","from tests.test_execution_v2_postgres import worker; worker()"],cwd=Path(__file__).parents[1],env=env,capture_output=True,timeout=45)
        self.assertEqual(p.returncode,73 if phase=="before" else 74,p.stderr.decode(errors="replace"))
        if phase=="before":self.assertEqual(self.records(),before)
        result=self.c.apply(self.scope,raw);self.assertTrue(result["durable"]);self.assertEqual(result["state"]["revision"],5)
        self.assertEqual(result["state"]["balance"],"12000")
        self.assertEqual(result["state"]["realizedGross"],"2000")
        self.assertEqual(result["state"]["orders"]["open"]["status"],"CLOSED")
        self.assertEqual(len(self.records()["tick_commands"]),5)
        self.assertEqual(self.c.apply(self.scope,raw),result)
    def test_worker_death_before_commit(self):self.death("before")
    def test_worker_death_after_commit(self):self.death("after")

    def test_restricted_runtime_commits_and_evidence_is_append_only(self):
        role="v2_runtime_"+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:
            db.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        grant_execution_runtime(DSN,role)
        @contextmanager
        def restricted(dsn):
            with connect(dsn) as db:
                db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                yield db
        with patch("execution.postgres_v2.connect",restricted):
            result=self.call("ADVANCE",dict(targetNs="100"))
            self.assertTrue(result["durable"])
        for query in ("DELETE FROM btl.tick_events","UPDATE btl.tick_events SET content_hash=content_hash"):
            with self.assertRaises(psycopg.DatabaseError):
                with restricted(DSN) as db:db.execute(query)

    def test_native_dump_empty_target_restore_preserves_exact_receipt(self):
        self.call("ADVANCE",dict(targetNs="100"));self.call("OPEN",opening(),"open")
        self.call("ADVANCE",dict(targetNs="110"));self.call("CLOSE",dict(orderId="open",quantity=None))
        raw=command(self.session,"backup",4,"ADVANCE",dict(targetNs="120"))
        result=self.c.apply(self.scope,raw)
        self.assertEqual(result["state"]["balance"],"11000")
        self.assertEqual(result["state"]["orders"]["open"]["status"],"CLOSED")
        name="v2_restore_"+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:
            db.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        info=psycopg.conninfo.conninfo_to_dict(DSN)
        target_dsn=psycopg.conninfo.make_conninfo(**{**info,"dbname":name})
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"v2.dump"
            sha=backup(DSN,target,os.environ["BTL_PG_BIN"])
            restore(target_dsn,target,sha,os.environ["BTL_PG_BIN"])
        restored=ExecutionControllerV2(PostgresExecutionStoreV2(target_dsn),self.h.profile,self.h.primary,conversion_provider=self.h.fx)
        self.assertEqual(restored.apply(self.scope,raw),result)
        self.assertEqual(restored.inspect(self.scope,self.session),self.c.inspect(self.scope,self.session))

    def test_provider_recovery_does_not_hold_financial_row_lock(self):
        from execution.sources_v2 import SourceJoinV2
        native=SourceJoinV2.resume
        observed=[]
        def probe(*args,**kwargs):
            with connect(DSN) as db:
                row=db.execute("SELECT revision FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s FOR UPDATE NOWAIT",(self.scope.workspace_id,self.session)).fetchone()
                observed.append(row[0])
            return native(*args,**kwargs)
        with patch("execution.controller_v2.SourceJoinV2.resume",side_effect=probe):
            self.call("ADVANCE",dict(targetNs="100"))
        self.assertEqual(observed,[0])

    def test_unreceipted_cash_change_and_corrupt_state_fail_closed(self):
        store=PostgresExecutionStoreV2(DSN);before=self.records()
        raw=command(self.session,"forged",0,"END")
        def forged(state,cp):
            state["balance"]="10001";state["realizedGross"]="1"
            return state,cp,[],None
        with self.assertRaisesRegex(ContractError,"CORRUPT_RECORD"):store.run(self.scope,raw,forged)
        self.assertEqual(self.records(),before)
        with connect(DSN) as db:
            db.execute("UPDATE btl.tick_sessions SET payload=payload || %s::bytea,revision=revision+1 WHERE workspace_id=%s AND session_id=%s",(b" ",self.scope.workspace_id,self.session))
        with self.assertRaisesRegex(ContractError,"CORRUPT_RECORD"):
            self.c.apply(self.scope,command(self.session,"corrupt",1,"END"))
        self.assertEqual(len(self.records()["tick_commands"]),0)
