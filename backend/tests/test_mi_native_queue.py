"""Native MI service child through the actual PostgreSQL scheduler (QA only)."""
import hashlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from application.models import TrustedScope
from cloud import mi_qa, queue, worker
from contracts.canonical import canonical_bytes
from contracts.primitives import ContractError
from execution import mi_checkpoint, mi_kernel, mi_postgres
from execution.terminal_order_archive import TERMINAL
from infrastructure.database import connect
from tests.mi_harness import FREE, MI
from tests.synthetic_mi import ORDER
from tests import test_research_queue


@unittest.skipUnless(test_research_queue.DSN, "Requires disposable PostgreSQL")
class NativeMIQueue(unittest.TestCase):
    setUpClass = classmethod(test_research_queue.QueueTests.setUpClass.__func__)
    tearDownClass = classmethod(test_research_queue.QueueTests.tearDownClass.__func__)
    tearDown = test_research_queue.QueueTests.tearDown
    submit = test_research_queue.QueueTests.submit
    def setUp(self):
        test_research_queue.QueueTests.setUp(self)
        root = self.enterContext(TemporaryDirectory())
        self.model = MI(ORDER, steps=12)
        self.scope = TrustedScope(str(self.workspace), str(self.actor))
        self.store = mi_postgres.MultiInstrumentStore(self.dsn)
        self.sid = self.model.state["sessionId"]
        pins = mi_checkpoint.pins_from_state(self.model.state)
        blob = canonical_bytes(dict(schemaVersion=1, artifact="BTL-MI-QA-SOURCE-1",
                                    pins=pins, ticks=self.model.ticks))
        path = Path(root) / "fixture.json"
        path.write_bytes(blob)
        sha = hashlib.sha256(blob).hexdigest()
        self.enterContext(patch.dict(os.environ, dict(BTL_PRODUCT_PROFILE="development",
                          BTL_QA_MI_MANIFEST=str(path), BTL_QA_MI_MANIFEST_SHA256=sha)))
        self.addCleanup(worker.close)
        self.store.create(self.scope, self.model.pset, [FREE], FREE.method_id, "10000",
                          self.model.state["startNs"], self.sid, manifest_sha=sha, compact=True)

    def command(self, kind, payload, cid):
        cmd = dict(schemaVersion=1, artifact=mi_kernel.MI_COMMAND, sessionId=self.sid,
                   expectedRevision=self.model.state["revision"], commandId=cid, kind=kind, payload=payload)
        return dict(schemaVersion=1, artifact=mi_qa.REQUEST, command=cmd, jump=False)

    def submit_mi(self, request):
        return self.submit(operation="replay", args=(self.sid, request))["jobId"]

    def inspect(self, job_id):
        return queue.inspect(self.dsn, self.actor, self.workspace, job_id)

    def finish(self, request, job_id=None):
        job_id = job_id or self.submit_mi(request)
        self.assertTrue(queue.work_one(self.dsn, worker.run))
        job = self.inspect(job_id)
        self.assertEqual(job["state"], "SUCCEEDED", job)
        return job["result"]

    def expect(self, request, receipt):
        command = request["command"]
        events = self.model.apply(command["kind"], command["payload"], command["commandId"])
        observed = receipt["state"]
        archived = {key for key, order in self.model.state["orders"].items()
                    if order["status"] in TERMINAL}
        self.assertEqual(observed["artifact"], mi_kernel.MI_COMPACT_STATE)
        self.assertEqual(observed["archived"]["count"], len(archived))
        expected = dict(self.model.state, orders={key: order for key, order in self.model.state["orders"].items()
                                                 if key not in archived})
        self.assertEqual({key: value for key, value in observed.items() if key not in ("artifact", "archived")},
                         {key: value for key, value in expected.items() if key != "artifact"})
        self.assertEqual(receipt["events"], events)

    def reclaim(self, job_id):
        # Advance only this test lease's timestamp to avoid a 30s idle wait.
        with connect(self.dsn) as db:
            db.execute("UPDATE btl.research_jobs SET lease_until=clock_timestamp()-interval '1 second' "
                       "WHERE id=%s AND state='RUNNING'", (job_id,))
        self.assertEqual(self.inspect(job_id)["state"], "QUEUED")

    def test_native_mi_recovery(self):
        zero = self.command("ADVANCE", {"targetNs": str(self.model.at(0))}, "initial")
        self.expect(zero, self.finish(zero))
        for symbol in ("EURUSD", "GBPUSD"):
            # Positions trade on both instruments at the same timestamp.
            order = self.command("OPEN", dict(symbol=symbol, side="LONG", orderType="MARKET",
                workflow="QUICK", entry=self.model.quote(symbol)[1], quantity="0.1", sl=None,
                tp=None, riskPercent="1", observations=[]), symbol)
            self.expect(order, self.finish(order))

        fills = self.command("ADVANCE", {"targetNs": str(self.model.at(2))}, "fills")
        job_id = self.submit_mi(fills)
        worker.close()
        entry = """import os, signal, sys
sys.path[:0] = sys.argv[1:]
from execution import mi_kernel
from cloud.worker import serve
def kill(*args, **kwargs):
    os.kill(os.getpid(), signal.SIGKILL)
mi_kernel.advance = kill
serve()
"""
        with patch.object(worker, "SERVE_ENTRY", entry):
            with self.assertRaisesRegex(RuntimeError, "MI native worker interrupted"):
                queue.work_one(self.dsn, worker.run)
        with connect(self.dsn) as db:
            count = db.execute("SELECT count(*) FROM btl.tick_commands WHERE workspace_id=%s "
                               "AND session_id=%s AND command_id='fills'",
                               (str(self.workspace), self.sid)).fetchone()[0]
        self.assertEqual(count, 0)
        self.reclaim(job_id)
        receipt = self.finish(fills, job_id)
        self.expect(fills, receipt)
        self.assertEqual(self.inspect(job_id)["attempt"], 2)
        self.assertEqual([event["symbol"] for event in receipt["events"]], ["EURUSD", "GBPUSD"])

        pending_symbol = "EURUSD"
        pending = self.command("OPEN", dict(symbol=pending_symbol, side="LONG", orderType="LIMIT",
            workflow="PLANNED", entry="1", quantity="0.1", sl="0.9", tp="1.2",
            riskPercent="1", observations=[]), "remote-limit")
        self.expect(pending, self.finish(pending))

        close = self.command("CLOSE", {"orderId": "EURUSD", "quantity": None}, "close-one")
        self.expect(close, self.finish(close))
        exits = self.command("ADVANCE", {"targetNs": str(self.model.at(4))}, "exits")
        job_id = self.submit_mi(exits)
        worker.close()
        entry = """import os, signal, sys
sys.path[:0] = sys.argv[1:]
from execution.mi_postgres import MultiInstrumentStore
from cloud.worker import serve
apply = MultiInstrumentStore.apply
def kill_after(self, *args, **kwargs):
    apply(self, *args, **kwargs)
    os.kill(os.getpid(), signal.SIGKILL)
MultiInstrumentStore.apply = kill_after
serve()
"""
        with patch.object(worker, "SERVE_ENTRY", entry):
            with self.assertRaisesRegex(RuntimeError, "MI native worker interrupted"):
                queue.work_one(self.dsn, worker.run)
        self.assertEqual(self.store.project(self.scope, self.sid)["metrics"]["tradeCount"], 1)
        self.reclaim(job_id)
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(lambda _: queue.work_one(self.dsn, worker.run), range(2))), 1)
        receipt = self.inspect(job_id)["result"]
        self.expect(exits, receipt)
        self.assertEqual(self.inspect(job_id)["attempt"], 2)
        self.assertEqual(receipt["state"]["orders"]["remote-limit"]["status"], "PENDING")
        self.assertEqual(receipt["state"]["orders"]["GBPUSD"]["status"], "ACTIVE")
        self.assertEqual(self.finish(exits), receipt)
        self.assertEqual(self.store.project(self.scope, self.sid)["metrics"]["tradeCount"], 1)
        archive = self.store.terminal_page(self.scope, self.sid)
        self.assertEqual([row["orderId"] for row in archive["orders"]], ["EURUSD"])
        self.assertNotIn("EURUSD", receipt["state"]["orders"])

    def test_native_pretransaction_sigkill_and_postgres_disconnect_reclaim(self):
        request = self.command("ADVANCE", {"targetNs": str(self.model.at(0))}, "recover-first")
        job_id = self.submit_mi(request)
        pretransaction = """import os, signal, sys
sys.path[:0] = sys.argv[1:]
from execution.mi_postgres import MultiInstrumentStore
from cloud.worker import serve
def kill(self, *args, **kwargs):
    os.kill(os.getpid(), signal.SIGKILL)
MultiInstrumentStore.apply = kill
serve()
"""
        disconnect = """import sys
from contextlib import contextmanager
sys.path[:0] = sys.argv[1:]
from execution import mi_postgres
from cloud.worker import serve
native = mi_postgres.connect
@contextmanager
def interrupted(dsn):
    with native(dsn, pooled=False) as db:
        db.execute("SELECT pg_terminate_backend(pg_backend_pid())")
        yield db
mi_postgres.connect = interrupted
serve()
"""
        for entry, message in ((pretransaction, "MI native worker interrupted"),
                               (disconnect, "Worker infrastructure unavailable")):
            worker.close()
            with patch.object(worker, "SERVE_ENTRY", entry), self.assertRaisesRegex(RuntimeError, message):
                queue.work_one(self.dsn, worker.run)
            self.reclaim(job_id)
        self.expect(request, self.finish(request, job_id))
        self.assertEqual(self.inspect(job_id)["attempt"], 3)

    def test_native_mi_development_gate(self):
        request = self.command("ADVANCE", {"targetNs": str(self.model.at(0))}, "first")
        with patch.dict(os.environ, {"BTL_PRODUCT_PROFILE": "commercial"}):
            with self.assertRaisesRegex(ContractError, "RESOURCE_UNAVAILABLE"):
                self.submit_mi(request)
        self.expect(request, self.finish(request))
