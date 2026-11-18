"""Synthetic integration checks. The DSN must point to a disposable cluster."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
import signal
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from application.models import TrustedScope
from contracts.primitives import ContractError
from execution import mi_checkpoint, mi_kernel, mi_postgres
from infrastructure.database import connect, migrate
from tests.mi_harness import FREE, MI
from tests.synthetic_mi import ORDER
from tests.synthetic_multi_instrument import source

DSN = os.environ.get("BTL_TEST_DATABASE_URL")


def fixture():
    return MI(["EURUSD", "GBPUSD"], steps=12)


def sources(model):
    return ({symbol: source(model.ticks[symbol]) for symbol in model.symbols},
            mi_checkpoint.pins_from_state(model.state))


def crash_child():
    workspace, command, phase = json.loads(os.environ["BTL_MI_TEST_CHILD"])
    native = mi_postgres.connect

    @contextmanager
    def interrupted(dsn):
        with native(dsn, pooled=False) as db:
            if phase == "commit":
                db.execute("SET LOCAL application_name = 'mi-test-commit'")
            yield db
            if phase == "before":
                os.kill(os.getpid(), signal.SIGKILL)
        os.kill(os.getpid(), signal.SIGKILL)

    with patch.object(mi_postgres, "connect", interrupted):
        mi_postgres.MultiInstrumentStore(DSN).apply(
            TrustedScope(workspace, "fixture:mi"), command, lambda: sources(fixture()))


@unittest.skipUnless(DSN, "requires disposable PostgreSQL")
class MultiInstrumentPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.scope = TrustedScope("qa:" + uuid4().hex, "fixture:mi")
        self.model = fixture()
        self.sid = self.model.state["sessionId"]
        self.store = mi_postgres.MultiInstrumentStore(DSN)
        seed = self.store.create(self.scope, self.model.pset, [FREE], FREE.method_id, "10000",
                                 self.model.state["startNs"], self.sid)
        self.assertEqual(seed, self.model.state)
        self.open_sources = lambda: sources(self.model)

    def cmd(self, kind, payload, cid):
        return dict(schemaVersion=1, artifact=mi_kernel.MI_COMMAND, sessionId=self.sid,
                    expectedRevision=self.model.state["revision"], commandId=cid, kind=kind, payload=payload)

    def apply(self, kind, payload, cid):
        command = self.cmd(kind, payload, cid)
        result = self.store.apply(self.scope, command, self.open_sources)
        expected = self.model.apply(kind, payload, cid)
        self.assertEqual(result["state"], self.model.state)
        self.assertEqual(result["events"], expected)
        return result

    def open_both(self):
        self.apply("ADVANCE", {"targetNs": str(self.model.at(0))}, "initial")
        for symbol in self.model.symbols:
            self.apply("OPEN", dict(symbol=symbol, side="LONG", orderType="MARKET", workflow="QUICK",
                                    entry=self.model.quote(symbol)[1], quantity="0.1", sl=None,
                                    tp=None, riskPercent="1", observations=[]), symbol)

    def records(self):
        with connect(DSN) as db:
            return tuple(db.execute(f"SELECT count(*) FROM btl.{table} WHERE workspace_id=%s AND session_id=%s",
                         (self.scope.workspace_id, self.sid)).fetchone()[0]
                         for table in ("tick_commands", "tick_events", "tick_checkpoints"))

    def test_lifecycle_projection_and_retry(self):
        self.open_both()
        self.apply("ADVANCE", {"targetNs": str(self.model.at(2))}, "entries")
        for symbol in self.model.symbols:
            self.apply("CLOSE", {"orderId": symbol, "quantity": None}, "close:" + symbol)
        payload = {"targetNs": str(self.model.at(4))}
        command = self.cmd("ADVANCE", payload, "exits")
        result = self.apply("ADVANCE", payload, "exits")
        cold = mi_postgres.MultiInstrumentStore(DSN)
        self.assertEqual(cold.apply(self.scope, command, lambda: self.fail("retry reopened provider")), result)
        projection = cold.project(self.scope, self.sid)
        self.assertEqual({row["symbol"] for row in projection["completed"]}, set(self.model.symbols))
        self.assertEqual(projection["account"]["balance"], self.model.state["balance"])
        self.assertEqual(projection["provenance"]["financialAuthority"], "DURABLE_SYNTHETIC_MI_LEDGER_ONLY")
        with self.assertRaisesRegex(ContractError, "RESOURCE_UNAVAILABLE"):
            cold.apply(TrustedScope("other", self.scope.actor_ref), command, self.open_sources)
        with self.assertRaisesRegex(ContractError, "RESOURCE_UNAVAILABLE"):
            cold.project(TrustedScope("other", self.scope.actor_ref), self.sid)

    def test_concurrent_delivery_conflict_and_stale_revision(self):
        command = self.cmd("ADVANCE", {"targetNs": str(self.model.at(0))}, "same")
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: self.store.apply(self.scope, command, self.open_sources), range(6)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(self.records(), (1, 0, 2))
        with self.assertRaisesRegex(ContractError, "IDEMPOTENCY_CONFLICT"):
            self.store.apply(self.scope, dict(command, payload={"targetNs": str(self.model.at(1))}), self.open_sources)
        with self.assertRaisesRegex(ContractError, "STALE_REVISION"):
            self.store.apply(self.scope, dict(command, commandId="other"), self.open_sources)

    def test_sigkill_before_and_after_commit_with_tied_fills(self):
        self.open_both()
        command = self.cmd("ADVANCE", {"targetNs": str(self.model.at(2))}, "fills")
        before = self.records()
        for phase in ("before", "after"):
            child = subprocess.run([sys.executable, "-m", "tests.test_mi_postgres"],
                                   env=dict(os.environ, BTL_MI_TEST_CHILD=json.dumps(
                                       [self.scope.workspace_id, command, phase])), timeout=15, check=False)
            self.assertEqual(child.returncode, -signal.SIGKILL)
            if phase == "before":
                self.assertEqual(self.records(), before)
        result = self.store.apply(self.scope, command, lambda: self.fail("committed retry reopened provider"))
        expected = self.model.apply("ADVANCE", command["payload"], "fills")
        self.assertEqual(result["state"], self.model.state)
        self.assertEqual(result["events"], expected)
        self.assertEqual([event["symbol"] for event in expected], self.model.symbols)
        self.assertEqual(len({event["detail"]["timeNs"] for event in expected}), 1)
        self.assertEqual(self.records(), (before[0] + 1, before[1] + 2, before[2] + 1))


    def test_cold_read_preserves_creation_order_for_same_instrument_fills(self):
        self.apply("ADVANCE", {"targetNs": str(self.model.at(0))}, "initial")
        for order_id in ("z-created-first", "a-created-second"):
            self.apply("OPEN", dict(symbol="EURUSD", side="LONG", orderType="MARKET",
                                    workflow="QUICK", entry=self.model.quote("EURUSD")[1],
                                    quantity="0.1", sl=None, tp=None, riskPercent="1",
                                    observations=[]), order_id)
        self.store = mi_postgres.MultiInstrumentStore(DSN)
        receipt = self.apply("ADVANCE", {"targetNs": str(self.model.at(2))}, "entries")
        self.assertEqual([event["orderId"] for event in receipt["events"]],
                         ["z-created-first", "a-created-second"])

    def test_maximum_instrument_set_creates_and_resumes(self):
        self.model = MI(ORDER, steps=4)
        self.sid = "mi:all"
        self.model.state = mi_kernel.seed_state(self.sid, self.model.pset, [FREE], FREE.method_id,
                                                 "10000", self.model.state["startNs"])
        self.store.create(self.scope, self.model.pset, [FREE], FREE.method_id, "10000",
                          self.model.state["startNs"], self.sid)
        self.apply("ADVANCE", {"targetNs": str(self.model.at(0))}, "initial")
        self.store = mi_postgres.MultiInstrumentStore(DSN)
        self.apply("ADVANCE", {"targetNs": str(self.model.at(3))}, "continued")
        self.assertEqual(self.store.create(self.scope, self.model.pset, [FREE], FREE.method_id,
                                          "10000", self.model.state["startNs"], self.sid), self.model.state)

    def test_jump_persists_same_tied_boundary_as_causal_advance(self):
        self.open_both()
        target = {"targetNs": str(self.model.at(7))}
        command = self.cmd("ADVANCE", target, "jump")
        result = self.store.apply(self.scope, command, self.open_sources, jump=True)
        expected = self.model.to(self.model.at(1))
        self.assertEqual(result["state"], self.model.state)
        self.assertEqual(result["events"], expected)
        self.assertEqual(result["replay"]["status"], "EVENT_FOUND")
        self.assertEqual(self.store.apply(self.scope, command, self.open_sources, jump=True), result)
        with self.assertRaisesRegex(ContractError, "IDEMPOTENCY_CONFLICT"):
            self.store.apply(self.scope, command, self.open_sources)

    def test_source_pin_mismatch_leaves_no_partial_revision(self):
        command = self.cmd("ADVANCE", {"targetNs": str(self.model.at(0))}, "bad-pin")
        openers, pins = self.open_sources()
        pins["EURUSD"]["datasetVersion"] = "f" * 64
        with self.assertRaisesRegex(ContractError, "REFUSED_DATASET_MISMATCH"):
            self.store.apply(self.scope, command, lambda: (openers, pins))
        self.assertEqual(self.records(), (0, 0, 1))
        self.apply("ADVANCE", command["payload"], "bad-pin")

    def test_disconnect_during_deferred_commit_rolls_back(self):
        self.open_both()
        command = self.cmd("ADVANCE", {"targetNs": str(self.model.at(2))}, "fills")
        before = self.records()
        with connect(DSN) as db:
            db.execute("""
                CREATE FUNCTION btl.mi_test_delay() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF current_setting('application_name') = 'mi-test-commit' THEN
                        PERFORM pg_sleep(10);
                    END IF;
                    RETURN NEW;
                END $$;
                CREATE CONSTRAINT TRIGGER mi_test_delay AFTER INSERT ON btl.tick_checkpoints
                    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION btl.mi_test_delay()
            """)
        try:
            with subprocess.Popen([sys.executable, "-m", "tests.test_mi_postgres"],
                                  env=dict(os.environ, BTL_MI_TEST_CHILD=json.dumps(
                                      [self.scope.workspace_id, command, "commit"])),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as child:
                try:
                    for _ in range(70):
                        with connect(DSN, pooled=False) as db:
                            waiting = db.execute(
                                "SELECT pid FROM pg_stat_activity WHERE application_name='mi-test-commit' "
                                "AND wait_event='PgSleep' AND query='COMMIT'").fetchone()
                            if waiting:
                                self.assertTrue(db.execute("SELECT pg_terminate_backend(%s, 3000)",
                                                           waiting).fetchone()[0])
                                break
                        time.sleep(0.05)
                    else:
                        self.fail("child never reached deferred COMMIT")
                    _, stderr = child.communicate(timeout=5)
                    self.assertNotEqual(child.returncode, 0)
                    self.assertIn(b"terminating connection", stderr)
                finally:
                    if child.poll() is None:
                        child.kill()
            self.assertEqual(self.records(), before)
            self.apply("ADVANCE", command["payload"], "fills")
        finally:
            with connect(DSN) as db:
                db.execute("DROP TRIGGER mi_test_delay ON btl.tick_checkpoints; DROP FUNCTION btl.mi_test_delay()")


if __name__ == "__main__":
    if os.environ.get("BTL_MI_TEST_CHILD"):
        crash_child()
    else:
        unittest.main()
