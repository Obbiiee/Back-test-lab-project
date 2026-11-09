"""Real isolated PostgreSQL and real worker-death gates; skips are not PASS."""
from contextlib import contextmanager
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

import psycopg
from psycopg import sql
from application.models import TrustedScope
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from execution.controller import ExecutionController
from execution.postgres import PostgresExecutionStore, grant_execution_runtime, unpack
from execution.analysis import metrics as canonical_metrics, project
from execution.incremental_analytics import metrics as durable_metrics
from infrastructure.database import connect, migrate, backup, restore
from tests.test_execution_goldens import goldens
from tests.test_tick_execution import Harness, provider_for, profile_for, open_plan, command, exercise, assert_case

DSN = os.getenv("BTL_TEST_DATABASE_URL")


def worker_crash():
    """Child receives synthetic fixture instructions privately via environment."""
    data = json.loads(os.environ["BTL_EXECUTION_WORKER_FIXTURE"])
    import execution.postgres as storage
    native = storage.connect
    if data["phase"] == "before":
        @contextmanager
        def death_before_commit(dsn):
            with native(dsn) as db:
                yield db
                # SQL has staged every write, but COMMIT has not happened.
                os._exit(73)
        storage.connect = death_before_commit
    controller = ExecutionController(PostgresExecutionStore(DSN), provider_for(data["case"]))
    controller.apply(TrustedScope(data["workspace"], "fixture:worker"),data["command"])
    # COMMIT succeeded; caller never received the result.
    os._exit(74)


@unittest.skipUnless(DSN,"Requires real isolated PostgreSQL; missing DB is not release PASS")
class TickExecutionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.scope=TrustedScope("tickqa:"+uuid.uuid4().hex,"fixture:actor")
        self.case=goldens()["scenarios"][0]
        self.store=PostgresExecutionStore(DSN)

    def harness(self, case=None, session="fixture:session"):
        return Harness(provider_for(case or self.case),store=self.store,scope=self.scope,session=session)

    def records(self, session="fixture:session"):
        with connect(DSN) as db:
            result={}
            for table in ("tick_sessions","tick_commands","tick_events","tick_checkpoints"):
                rows=db.execute(sql.SQL("SELECT encode(payload,'hex'),content_hash FROM btl.{} WHERE workspace_id=%s AND session_id=%s ORDER BY content_hash").format(sql.Identifier(table)),(self.scope.workspace_id,session)).fetchall()
                result[table]=rows
            return result

    def test_every_financial_golden_uses_actual_durable_adapter(self):
        for index,case in enumerate(goldens()["scenarios"]):
            with self.subTest(case=case["id"]):
                h=exercise(case,self.store,self.scope,session=f"fixture:golden:{index}")
                assert_case(self,case,h)
                with connect(DSN) as db:
                    row=db.execute('SELECT payload,content_hash FROM btl.tick_session_metric_projections '
                        'WHERE workspace_id=%s AND session_id=%s',
                        (self.scope.workspace_id,h.session)).fetchone()
                    event_rows=db.execute('SELECT payload,content_hash FROM btl.tick_events '
                        'WHERE workspace_id=%s AND session_id=%s ORDER BY sequence',
                        (self.scope.workspace_id,h.session)).fetchall()
                self.assertIsNotNone(row)
                durable=unpack(*row)
                events=[unpack(*event_row) for event_row in event_rows]
                expected=project(h.state,events,None)
                self.assertEqual(durable_metrics(durable),canonical_metrics(expected['completed']))

    def test_concurrent_identical_retry_stale_conflict_and_namespace(self):
        h=self.harness();h.call("OPEN",open_plan(self.case["open"]),name="order")
        raw=command(h.session,"advance",h.state["revision"],"ADVANCE",{"targetNs":"2"})
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:h.controller.apply(self.scope,raw),range(12)))
        self.assertTrue(all(r==results[0] for r in results))
        self.assertTrue(results[0]["durable"]);self.assertEqual(results[0]["state"]["balance"],"10030")
        recorded=self.records()
        self.assertEqual(len(recorded["tick_commands"]),2)
        self.assertEqual(len(recorded["tick_events"]),3)
        fresh=ExecutionController(PostgresExecutionStore(DSN),provider_for(self.case))
        self.assertEqual(fresh.apply(self.scope,raw),results[0])
        bad=deepcopy(raw);bad["payload"]["targetNs"]="3"
        with self.assertRaisesRegex(ContractError,"REFUSED_IDEMPOTENCY_CONFLICT"):fresh.apply(self.scope,bad)
        bad=deepcopy(raw);bad["commandId"]="stale"
        with self.assertRaisesRegex(ContractError,"REFUSED_STALE_REVISION"):fresh.apply(self.scope,bad)
        outsider=TrustedScope("other:"+uuid.uuid4().hex,"fixture:actor")
        with self.assertRaisesRegex(ContractError,"RESOURCE_UNAVAILABLE"):fresh.apply(outsider,raw)
        with self.assertRaisesRegex(ContractError,"RESOURCE_UNAVAILABLE"):fresh.inspect(outsider,h.session)
        self.assertEqual(self.records(),recorded)

    def test_terminal_order_archive_is_indexed_immutable_and_keyset_paginated(self):
        h=self.harness(session='fixture:terminal-archive:'+uuid.uuid4().hex)
        for index in range(3):
            order_id=f'archive:order:{index}'
            opened=h.call('OPEN',open_plan(self.case['open']),name=order_id)
            raw=command(h.session,f'archive:cancel:{index}',opened['state']['revision'],
                        'CANCEL',{'orderId':order_id})
            receipt=h.controller.apply(self.scope,raw)
            self.assertEqual(receipt['state']['orders'],{})
            self.assertEqual(h.controller.apply(self.scope,raw),receipt)
        first=self.store.order_history(self.scope,h.session,limit=2)
        self.assertEqual(len(first['records']),2)
        self.assertFalse(first['complete'])
        self.assertEqual(first['records'][0]['order']['status'],'CANCELLED')
        second=self.store.order_history(self.scope,h.session,after_sequence=first['nextCursor'],limit=2)
        self.assertEqual(len(second['records']),1)
        self.assertTrue(second['complete'])
        self.assertEqual(second['records'][0]['sequence'],2)
        self.assertEqual(self.store.archive_order(self.scope,h.session,'archive:order:1')['order']['status'],
                         'CANCELLED')
        with connect(DSN) as db:
            count=db.execute('SELECT count(*) FROM btl.tick_terminal_orders WHERE workspace_id=%s AND session_id=%s',
                             (self.scope.workspace_id,h.session)).fetchone()[0]
        self.assertEqual(count,3)

    def test_new_session_advances_journal_order_index_with_financial_events(self):
        session = 'fixture:journal-index:' + uuid.uuid4().hex
        h = self.harness(session=session)
        order_id = 'journal:order:one'
        h.call('OPEN', open_plan(self.case['open']), name=order_id)
        h.call('CANCEL', dict(orderId=order_id), name='journal:cancel')
        with connect(DSN) as db:
            head = db.execute(
                'SELECT format_version,through_sequence,event_hash,order_count,closed_order_count,analytics_format_version '
                'FROM btl.tick_journal_projection_heads '
                'WHERE workspace_id=%s AND session_id=%s',
                (self.scope.workspace_id, session),
            ).fetchone()
            indexed = db.execute(
                'SELECT i.sequence,i.event_id,i.event_kind,e.payload,e.content_hash '
                'FROM btl.tick_journal_order_events i JOIN btl.tick_events e '
                'ON (e.workspace_id,e.session_id,e.sequence)='
                '(i.workspace_id,i.session_id,i.sequence) '
                'WHERE i.workspace_id=%s AND i.session_id=%s AND i.order_id=%s '
                'ORDER BY i.sequence',
                (self.scope.workspace_id, session, order_id),
            ).fetchall()
            projection_row = db.execute(
                'SELECT p.order_status,p.last_sequence,p.event_id,p.payload,p.content_hash,'
                'i.projection_hash FROM btl.tick_journal_order_projection p '
                'JOIN btl.tick_journal_order_events i '
                'ON (i.workspace_id,i.session_id,i.order_id,i.sequence,i.event_id)='
                '(p.workspace_id,p.session_id,p.order_id,p.last_sequence,p.event_id) '
                'WHERE p.workspace_id=%s AND p.session_id=%s AND p.order_id=%s',
                (self.scope.workspace_id, session, order_id),
            ).fetchone()
            metric_row = db.execute(
                'SELECT payload,content_hash FROM btl.tick_session_metric_projections '
                'WHERE workspace_id=%s AND session_id=%s',
                (self.scope.workspace_id, session),
            ).fetchone()
        self.assertEqual(head, (1, h.state['nextEventIndex'], h.state['eventHash'], 1, 0, 1))
        events = [unpack(row[3], row[4]) for row in indexed]
        self.assertEqual([row[2] for row in indexed], [event['kind'] for event in events])
        self.assertEqual(events[0]['kind'], 'ORDER_ACCEPTED')
        self.assertEqual(events[-1]['kind'], 'ORDER_CANCELLED')
        self.assertEqual([event['sequence'] for event in events], [row[0] for row in indexed])
        self.assertEqual(projection_row[:3], ('CANCELLED', indexed[-1][0], indexed[-1][1]))
        projection = unpack(projection_row[3], projection_row[4])
        self.assertEqual(projection['order']['status'], 'CANCELLED')
        self.assertEqual(projection['contentHash'], projection_row[5])
        metric_projection = unpack(*metric_row)
        self.assertEqual((metric_projection['throughSequence'], metric_projection['eventHead']),
                         (h.state['nextEventIndex'], h.state['eventHash']))
        self.assertEqual(metric_projection['totals']['tradeCount'], 0)

    def test_compact_cold_recovery_uses_periodic_verified_base(self):
        from unittest.mock import patch
        from execution.postgres import COMPACT_RECOVERY_INTERVAL
        h=self.harness(session='fixture:recovery-base:'+uuid.uuid4().hex)
        h.through(0)
        for index in range(COMPACT_RECOVERY_INTERVAL//2):
            order_id=f'recovery:order:{index}'
            opened=h.call('OPEN',open_plan(self.case['open']),name=order_id)
            h.call('CANCEL',dict(orderId=order_id),name=f'recovery:cancel:{index}')
        self.assertGreaterEqual(h.state['revision'],COMPACT_RECOVERY_INTERVAL)
        with connect(DSN) as db:
            row=db.execute('SELECT revision,state_hash,chain_hash,record_hash,payload,content_hash '
                'FROM btl.tick_recovery_bases WHERE workspace_id=%s AND session_id=%s '
                'ORDER BY revision DESC LIMIT 1',(self.scope.workspace_id,h.session)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0],COMPACT_RECOVERY_INTERVAL)
        used=[]
        from execution import observed_state_delta_v3
        original=observed_state_delta_v3.reconstruct_complete
        def track(base,deltas,target_revision,**kwargs):
            used.append(kwargs.get('base_revision',0))
            return original(base,deltas,target_revision,**kwargs)
        with patch('execution.postgres.PostgresExecutionStore._cache_read',return_value=None), \
             patch('execution.postgres.reconstruct_complete',side_effect=track):
            cold=PostgresExecutionStore(DSN).inspect(self.scope,h.session)
        self.assertEqual(cold['state'],h.state)
        self.assertEqual(used,[COMPACT_RECOVERY_INTERVAL])

    def test_compact_v1_matches_snapshot_results_cold_recovery_and_idempotency(self):
        case = self.case
        session = "fixture:compact:" + uuid.uuid4().hex
        snapshot_scope = TrustedScope("tickqa:snapshot:" + uuid.uuid4().hex, "fixture:actor")
        compact_scope = TrustedScope("tickqa:compact:" + uuid.uuid4().hex, "fixture:actor")
        snapshot_store = PostgresExecutionStore(DSN)
        compact_store = PostgresExecutionStore(DSN, state_storage_format="compact-v1")
        snapshot_controller = ExecutionController(snapshot_store, provider_for(case))
        compact_controller = ExecutionController(compact_store, provider_for(case))
        snapshot_controller.create(snapshot_scope, session, profile_for(case))
        compact_controller.create(compact_scope, session, profile_for(case))

        opened = command(session, "compact:open", 0, "OPEN", open_plan(case["open"]))
        expected_open = snapshot_controller.apply(snapshot_scope, opened)
        actual_open = compact_controller.apply(compact_scope, opened)
        self.assertEqual(canonical_bytes(actual_open), canonical_bytes(expected_open))
        self.assertEqual(canonical_bytes(compact_controller.apply(compact_scope, opened)), canonical_bytes(expected_open))

        advanced = command(session, "compact:advance", 1, "ADVANCE", {"targetNs": "2"})
        expected_advance = snapshot_controller.apply(snapshot_scope, advanced)
        actual_advance = compact_controller.apply(compact_scope, advanced)
        self.assertEqual(canonical_bytes(actual_advance), canonical_bytes(expected_advance))
        fresh = ExecutionController(PostgresExecutionStore(DSN), provider_for(case))
        self.assertEqual(canonical_bytes(fresh.apply(compact_scope, advanced)), canonical_bytes(expected_advance))
        self.assertEqual(fresh.inspect(compact_scope, session, maximum=256),
                         compact_controller.inspect(compact_scope, session, maximum=256))
        snapshot_fork = snapshot_controller.fork(snapshot_scope, session, 1, "fixture:compact-child",
                                                 command_id="compact:fork")
        compact_fork = compact_controller.fork(compact_scope, session, 1, "fixture:compact-child",
                                               command_id="compact:fork")
        self.assertEqual(canonical_bytes(compact_fork), canonical_bytes(snapshot_fork))
        self.assertEqual(canonical_bytes(compact_controller.fork(compact_scope, session, 1,
            "fixture:compact-child", command_id="compact:fork")), canonical_bytes(snapshot_fork))
        with connect(DSN) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s",
                                        (compact_scope.workspace_id, session)).fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT count(*) FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s",
                                        (compact_scope.workspace_id, session)).fetchone()[0], 3)

    def _worker_death(self, phase):
        h=self.harness();h.call("OPEN",open_plan(self.case["open"]),name="order")
        before=self.records()
        raw=command(h.session,"worker:advance",h.state["revision"],"ADVANCE",{"targetNs":"2"})
        env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","BTL_EXECUTION_WORKER_FIXTURE":json.dumps({"phase":phase,"case":self.case,"workspace":self.scope.workspace_id,"command":raw})}
        child=subprocess.run([sys.executable,"-B","-c","from tests.test_tick_execution_postgres import worker_crash; worker_crash()"],
                             env=env,cwd=Path(__file__).parents[1],capture_output=True,timeout=30)
        self.assertEqual(child.returncode,73 if phase=="before" else 74,child.stderr.decode(errors="replace"))
        if phase=="before":
            self.assertEqual(self.records(),before)
            self.assertEqual(h.state["revision"],1)
        else:
            self.assertEqual(h.state["revision"],2)
            self.assertEqual(h.state["balance"],"10030")
        result=ExecutionController(PostgresExecutionStore(DSN),provider_for(self.case)).apply(self.scope,raw)
        self.assertEqual(result["state"]["balance"],"10030")
        self.assertEqual(len(self.records()["tick_events"]),3)
        self.assertEqual(len(self.records()["tick_commands"]),2)
        self.assertEqual(h.controller.apply(self.scope,raw),result)
        if phase == 'after':
            page=self.store.order_history(self.scope,h.session,limit=8)
            self.assertEqual(len(page['records']),1)
            self.assertEqual(page['records'][0]['order']['status'],'CLOSED')

    def test_real_worker_death_after_sql_before_commit(self):
        self._worker_death("before")

    def test_real_worker_death_after_commit_before_response(self):
        self._worker_death("after")

    def test_fork_from_committed_checkpoint_is_atomic_idempotent_parent_immutable(self):
        h=self.harness();h.call("OPEN",open_plan(self.case["open"]),name="order");h.through(1)
        point=h.state["revision"];h.through(2)
        parent=self.records()
        fork=h.controller.fork(self.scope,h.session,point,"fixture:child")
        self.assertTrue(fork["durable"]);self.assertEqual(fork["state"]["balance"],"10000")
        self.assertEqual(fork["state"]["parent"]["revision"],point)
        self.assertEqual(fork["state"]["orders"]["order"]["status"],"ACTIVE")
        self.assertEqual(h.controller.fork(self.scope,h.session,point,"fixture:child"),fork)
        with self.assertRaisesRegex(ContractError,"REFUSED_IDEMPOTENCY_CONFLICT"):
            h.controller.fork(self.scope,h.session,0,"fixture:child")
        raw=command("fixture:child","child:advance",1,"ADVANCE",{"targetNs":"2"})
        child=h.controller.apply(self.scope,raw)
        self.assertEqual(child["state"]["balance"],"10030")
        self.assertEqual(self.records(),parent)
        with self.assertRaisesRegex(ContractError,"REFUSED_FORK_POINT"):
            h.controller.fork(self.scope,h.session,999,"fixture:invalid")

    def test_native_append_only_revision_guard_and_exact_account_rebuild(self):
        h=exercise(goldens()["scenarios"][17],self.store,self.scope)
        all_events=h.controller.inspect(self.scope,h.session,maximum=256)["events"]
        from fractions import Fraction
        total=Fraction(h.state["initialBalance"])
        for event in all_events:
            if event["classification"]=="SIMULATED_FILL":
                total+=Fraction(event["detail"]["balanceDelta"])
        self.assertEqual(total,Fraction(h.state["balance"]))
        for table in ("tick_commands","tick_events","tick_checkpoints"):
            with self.subTest(table=table),self.assertRaises(psycopg.IntegrityError):
                with connect(DSN) as db:
                    db.execute(sql.SQL("UPDATE btl.{} SET content_hash=content_hash WHERE workspace_id=%s").format(sql.Identifier(table)),(self.scope.workspace_id,))
        with self.assertRaises(psycopg.IntegrityError):
            with connect(DSN) as db:
                db.execute("UPDATE btl.tick_sessions SET revision=revision WHERE workspace_id=%s",(self.scope.workspace_id,))
        inspected=h.controller.inspect(self.scope,h.session)
        self.assertNotIn("controller",inspected)
        with self.assertRaises(ContractError):h.controller.inspect(self.scope,h.session,maximum=257)

    def test_corrupt_durable_state_fails_without_new_financial_writes(self):
        h=self.harness()
        with connect(DSN) as db:
            db.execute("UPDATE btl.tick_sessions SET payload=payload || %s::bytea,revision=revision+1 WHERE workspace_id=%s AND session_id=%s",(b" ",self.scope.workspace_id,h.session))
        with self.assertRaisesRegex(ContractError,"CORRUPT_RECORD"):
            h.controller.apply(self.scope,command(h.session,"bad",1,"END",{}))
        self.assertEqual(len(self.records()["tick_events"]),0)

    def test_restricted_runtime_role_can_commit_but_cannot_mutate_evidence(self):
        h=self.harness()
        role="tick_runtime_"+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:
            db.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        grant_execution_runtime(DSN,role)
        @contextmanager
        def restricted(dsn):
            with connect(dsn) as db:
                db.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                yield db
        raw=command(h.session,"order",0,"OPEN",open_plan(self.case["open"]))
        with patch("execution.postgres.connect",restricted):
            self.assertTrue(h.controller.apply(self.scope,raw)["durable"])
        for query in ("DELETE FROM btl.tick_events","UPDATE btl.tick_events SET content_hash=content_hash"):
            with self.assertRaises(psycopg.DatabaseError):
                with restricted(DSN) as db:db.execute(query)

    def test_native_backup_empty_target_restore_recovers_identical_receipt(self):
        h=self.harness();h.call("OPEN",open_plan(self.case["open"]),name="order")
        raw=command(h.session,"advance",1,"ADVANCE",{"targetNs":"2"})
        result=h.controller.apply(self.scope,raw)
        name="tick_restore_"+uuid.uuid4().hex
        with psycopg.connect(DSN,autocommit=True) as db:
            db.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        info=psycopg.conninfo.conninfo_to_dict(DSN)
        restored_dsn=psycopg.conninfo.make_conninfo(**{**info,"dbname":name})
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"tick.dump"
            sha=backup(DSN,target,os.environ["BTL_PG_BIN"])
            restore(restored_dsn,target,sha,os.environ["BTL_PG_BIN"])
        restored=ExecutionController(PostgresExecutionStore(restored_dsn),provider_for(self.case))
        self.assertEqual(restored.apply(self.scope,raw),result)
        self.assertEqual(restored.inspect(self.scope,h.session,maximum=256),h.controller.inspect(self.scope,h.session,maximum=256))


if __name__=="__main__":
    unittest.main()
