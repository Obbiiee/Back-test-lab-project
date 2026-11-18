"""QA MI HTTP, entitlement, real worker and tenant integration."""
import hashlib
import os
import time
import uuid
import unittest
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cloud import queue, worker
from contracts.canonical import canonical_bytes
from execution import mi_checkpoint
from execution.contracts import text
from tests.mi_harness import MI
from tests.test_research_queue import DSN, QueueTests
from tests.test_research_sessions import method
from infrastructure.database import connect

# Reuse authenticated fixture setup while avoiding inheritance of its test cases.
@unittest.skipUnless(DSN, "requires disposable PostgreSQL")
class ProductMI(unittest.TestCase):
    setUpClass = classmethod(QueueTests.setUpClass.__func__)
    tearDownClass = classmethod(QueueTests.tearDownClass.__func__)
    tearDown = QueueTests.tearDown

    def setUp(self):
        QueueTests.setUp(self)
        self.root_dir = Path(self.enterContext(TemporaryDirectory()))
        self.configure(MI(["EURUSD", "GBPUSD"], steps=7))
        self.addCleanup(worker.close)

    def configure(self, model):
        fixture = canonical_bytes(dict(schemaVersion=1, artifact="BTL-MI-QA-PRODUCT-SOURCE-1",
            pins=mi_checkpoint.pins_from_state(model.state), profiles=model.wires,
            ticks=model.ticks, startPeriod="1970-01"))
        path = self.root_dir / "market.json"
        path.write_bytes(fixture)
        self.enterContext(patch.dict(os.environ, dict(BTL_PRODUCT_PROFILE="development",
            BTL_QA_MI_MANIFEST=str(path), BTL_QA_MI_MANIFEST_SHA256=hashlib.sha256(fixture).hexdigest())))

    def test_create_queue_trade_resume_and_read_durable_projections(self):
        client, headers = self.fixture.client, self.fixture.headers
        base = self.fixture.root
        record = method()
        setup = client.post(base + "/methods", json=record, headers=headers)
        self.assertEqual(setup.status_code, 200, setup.text)
        catalog = client.get(base + "/mi/catalog", headers=headers)
        self.assertEqual(catalog.status_code, 200, catalog.text)
        self.assertEqual(catalog.json()["symbols"], ["EURUSD", "GBPUSD"])
        raw = dict(schemaVersion=1, artifact="BTL-MI-SESSION-CREATE-1", id="session:mi-api",
                   instrumentIds=["GBPUSD", "EURUSD"], methodIds=[record["id"]],
                   activeMethodId=record["id"], initialBalance="10000")
        created = client.post(base + "/mi/sessions", json=raw, headers=headers)
        self.assertEqual(created.status_code, 200, created.text)
        uri = base + "/mi/sessions/" + raw["id"]
        self.assertEqual(client.post(base + "/mi/sessions", json=raw, headers=headers).status_code, 200)
        self.assertGreaterEqual(client.post(base + "/mi/sessions", json=dict(raw, id="session:extra"),
                                           headers=headers).status_code, 400)
        revision = 0

        def send(kind, payload, cid, jump=False):
            nonlocal revision
            cmd = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-MI-1", sessionId=raw["id"],
                       commandId=cid, expectedRevision=revision, kind=kind, payload=payload)
            request = dict(schemaVersion=1, artifact="BTL-MI-QUEUE-REQUEST-1", command=cmd, jump=jump)
            admitted = client.post(uri + "/commands", headers=headers, json=request)
            self.assertEqual(admitted.status_code, 202, admitted.text)
            self.assertTrue(queue.work_one(self.dsn, worker.run))
            status = client.get(base + "/jobs/" + admitted.json()["jobId"], headers=headers).json()
            self.assertEqual(status["state"], "SUCCEEDED", status)
            revision += 1
            return status["result"]

        first = send("ADVANCE", {"targetNs": "100"}, "first")
        for symbol in ("EURUSD", "GBPUSD"):
            quote = first["state"]["groups"][symbol]["events"][-1]
            send("OPEN", dict(symbol=symbol, side="LONG", orderType="MARKET", workflow="QUICK",
                entry=quote["ask"], quantity="0.1", sl=None, tp=None, riskPercent="1", observations=[]), symbol)
        fills = send("ADVANCE", {"targetNs": "140"}, "jump", jump=True)
        self.assertEqual([event["symbol"] for event in fills["events"]], ["EURUSD", "GBPUSD"])
        send("CLOSE", {"orderId": "EURUSD", "quantity": None}, "close")
        send("ADVANCE", {"targetNs": "130"}, "exit")
        durable = client.get(uri + "/journal", headers=headers).json()
        self.assertEqual(durable["orders"][0]["order"]["symbol"], "EURUSD")
        analytics = client.get(uri + "/analytics", headers=headers).json()
        self.assertEqual(analytics["metrics"]["tradeCount"], 1)
        view = client.get(uri + "?instrument=GBPUSD", headers=headers).json()
        self.assertEqual(view["activeInstrument"], "GBPUSD")
        self.assertEqual([row["timeNs"] for row in view["chart"]], ["100", "110", "120", "130"])
        self.assertEqual(view["state"]["orders"]["GBPUSD"]["status"], "ACTIVE")
        stale = dict(schemaVersion=1, artifact="BTL-MI-QUEUE-REQUEST-1", jump=False,
                     command=dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-MI-1",
                                  sessionId=raw["id"], commandId="stale", expectedRevision=0, kind="END", payload={}))
        outcome = client.post(uri + "/command-status", headers=headers, json=stale)
        self.assertEqual(outcome.json()["status"], "NOT_COMMITTED")
        first_request = dict(stale, command=dict(stale["command"], commandId="first",
                             kind="ADVANCE", payload={"targetNs": "100"}))
        self.assertEqual(client.post(uri + "/command-status", headers=headers,
                                     json=first_request).json()["status"], "COMMITTED")
        _, other = self.fixture.account()
        self.assertEqual(client.get(uri, headers=other).status_code, 404)

    def test_protocol_and_cross_month_entitlement_use_canonical_queue(self):
        boundary = 31 * 86400 * 10**9
        symbols = ["EURUSD", "GBPUSD"]
        model = MI(symbols, steps=4, rows_override={
            symbol: [(boundary - 10, "1.25", "1.2502"), (boundary + 10, "1.26", "1.2602")]
            for symbol in symbols})
        self.configure(model)
        client, headers, base = self.fixture.client, self.fixture.headers, self.fixture.root
        record = method("PROTOCOL", on=True)
        created_method = client.post(base + "/methods", headers=headers, json=record)
        self.assertEqual(created_method.status_code, 200, created_method.text)
        raw = dict(schemaVersion=1, artifact="BTL-MI-SESSION-CREATE-1", id="session:mi-pro",
                   instrumentIds=symbols, methodIds=[record["id"]],
                   activeMethodId=record["id"], initialBalance="10000")
        created = client.post(base + "/mi/sessions", headers=headers, json=raw)
        self.assertEqual(created.status_code, 200, created.text)
        path = base + "/mi/sessions/" + raw["id"]

        def execute(kind, payload, expected, cid):
            request = dict(schemaVersion=1, artifact="BTL-MI-QUEUE-REQUEST-1", jump=False,
                command=dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-COMMAND-MI-1", sessionId=raw["id"],
                             commandId=cid, expectedRevision=expected, kind=kind, payload=payload))
            accepted = client.post(path + "/commands", headers=headers, json=request)
            self.assertEqual(accepted.status_code, 202, accepted.text)
            self.assertTrue(queue.work_one(self.dsn, worker.run))
            return client.get(base + "/jobs/" + accepted.json()["jobId"], headers=headers).json()

        self.assertEqual(execute("ADVANCE", {"targetNs": str(boundary - 10)}, 0, "jan")["state"], "SUCCEEDED")
        profile = model.wires[0]
        step = Fraction(profile["lotStep"])
        risk_per_lot = Fraction(profile["contractSize"]) / 100 + 2 * Fraction(profile["commissionPerLotSide"])
        units = Fraction(100) / risk_per_lot / step
        lots = step * (units.numerator // units.denominator)
        quantity = text(lots)
        planned = dict(symbol="EURUSD", side="LONG", orderType="LIMIT", workflow="PLANNED",
                       entry="1.2", sl="1.19", tp="1.22", quantity=quantity, riskPercent="1",
                       observations=[dict(conditionId="condition", outcome="PASS")])
        placed = execute("OPEN", planned, 1, "protocol")
        self.assertEqual(placed["state"], "SUCCEEDED", placed)
        self.assertEqual(placed["result"]["state"]["orders"]["protocol"]["status"], "PENDING")
        target = {"targetNs": str(boundary + 10)}
        refused = execute("ADVANCE", target, 2, "free-feb")
        self.assertEqual(refused["state"], "RECONCILE_REQUIRED")
        self.assertEqual(client.get(path, headers=headers).json()["state"]["revision"], 2)
        now = int(time.time())
        with connect(self.dsn) as db:
            db.execute("INSERT INTO btl.sandbox_billing_orders(order_id,actor_id,request_id,merchant_id,"
                       "plan_version,amount_idr,duration_seconds,phase,transaction_id,paid_at,expires_at,revision) "
                       "VALUES (%s,%s,%s,'m','p',1000,2592000,'PAID',%s,%s,%s,1)",
                       ("btl-sbx-" + uuid.uuid4().hex, self.fixture.actor, uuid.uuid4(),
                        "t" + uuid.uuid4().hex, now - 10, now - 10 + 2592000))
        resumed = execute("ADVANCE", target, 2, "pro-feb")
        self.assertEqual(resumed["state"], "SUCCEEDED", resumed)
        self.assertEqual(resumed["result"]["state"]["throughNs"], target["targetNs"])
        self.assertEqual(resumed["result"]["state"]["orders"]["protocol"]["status"], "PENDING")
