"""MI compact state and streaming Analytics on disposable PostgreSQL."""
import os
import unittest
from fractions import Fraction
from uuid import uuid4

from application.models import TrustedScope
from contracts.models import MethodPolicy
from contracts.primitives import ContractError
from execution import mi_kernel, mi_postgres
from infrastructure.database import migrate
from tests.mi_harness import FREE, MI
from tests.test_mi_postgres import sources

DSN = os.getenv("BTL_TEST_DATABASE_URL")
OTHER = MethodPolicy("method:other", "2" * 64, "FREE_STYLE", False, ())


@unittest.skipUnless(DSN, "requires disposable PostgreSQL")
class CompactMI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        migrate(DSN)

    def setUp(self):
        self.model = MI(["EURUSD"], steps=5, policies=[FREE, OTHER])
        self.scope = TrustedScope("qa:" + uuid4().hex, "fixture:mi")
        self.store = mi_postgres.MultiInstrumentStore(DSN)
        self.sid = self.model.state["sessionId"]
        self.rev = 0
        self.state = self.store.create(self.scope, self.model.pset, [FREE, OTHER],
            FREE.method_id, "10000", self.model.state["startNs"], self.sid, compact=True)

    def apply(self, kind, payload, cid=None):
        cmd = dict(schemaVersion=1, artifact=mi_kernel.MI_COMMAND, sessionId=self.sid,
                   expectedRevision=self.rev, commandId=cid or f"cmd:{self.rev}", kind=kind, payload=payload)
        result = self.store.apply(self.scope, cmd, lambda: sources(self.model))
        self.rev += 1
        self.state = result["state"]
        return cmd, result

    def trade_and_cancel(self, count):
        self.apply("ADVANCE", {"targetNs": str(self.model.at(0))})
        plan = dict(symbol="EURUSD", side="LONG", orderType="LIMIT", workflow="PLANNED",
                    entry="1", quantity="0.1", sl="0.9", tp="1.2", riskPercent="1", observations=[])
        self.apply("OPEN", plan, "retained")
        for i in range(count):
            self.apply("OPEN", plan, f"cancelled:{i}")
            self.apply("CANCEL", {"orderId": f"cancelled:{i}"})
        bid0, ask0 = self.model.rows["EURUSD"][0][1:]
        self.apply("OPEN", dict(plan, entry=ask0, orderType="MARKET", workflow="QUICK", sl=None, tp=None), "trade")
        self.apply("ADVANCE", {"targetNs": str(self.model.at(1))})
        self.apply("CLOSE", {"orderId": "trade", "quantity": None})
        cmd, receipt = self.apply("ADVANCE", {"targetNs": str(self.model.at(2))})
        entry = Fraction(self.model.rows["EURUSD"][1][2])
        exit_ = Fraction(self.model.rows["EURUSD"][2][1])
        profile = self.model.wires[0]
        gross = (exit_ - entry) * Fraction(profile["contractSize"]) / 10
        fees = Fraction(profile["commissionPerLotSide"]) / 5
        return cmd, receipt, gross, fees

    def test_archive_releases_capacity_and_preserves_deduplication(self):
        cmd, receipt, gross, fees = self.trade_and_cancel(130)
        self.assertEqual(set(self.state["orders"]), {"retained"})
        self.assertEqual(self.state["archived"]["count"], 131)
        self.assertEqual(Fraction(self.state["balance"]), 10000 + gross - fees)
        self.assertEqual(self.store.apply(self.scope, cmd, lambda: self.fail("opened source on retry")), receipt)
        summary = self.store.project(self.scope, self.sid)
        self.assertEqual(summary["metrics"]["tradeCount"], 1)
        self.assertEqual(Fraction(summary["metrics"]["netCashChange"]), gross - fees)
        first = self.store.terminal_page(self.scope, self.sid, limit=64)
        second = self.store.terminal_page(self.scope, self.sid, limit=64,
            after_sequence=first["nextAfterSequence"], revision_pin=first["revision"])
        last = self.store.terminal_page(self.scope, self.sid, limit=64,
            after_sequence=second["nextAfterSequence"], revision_pin=second["revision"])
        self.assertEqual(len(last["orders"]), 3)
        self.assertEqual(last["orders"][-1]["orderId"], "trade")
        with self.assertRaisesRegex(ContractError, "IDEMPOTENCY_CONFLICT"):
            self.apply("OPEN", dict(symbol="EURUSD", side="LONG", orderType="LIMIT", workflow="PLANNED",
                        entry="1", quantity="0.1", sl="0.9", tp="1.2", riskPercent="1", observations=[]), "cancelled:0")

    def test_actual_ledger_above_10000_events(self):
        _, _, gross, fees = self.trade_and_cancel(1)
        # Real durable commands append to the same chain without change to PnL.
        for i in range(10_000):
            self.apply("SET_METHOD", {"methodId": OTHER.method_id if i % 2 == 0 else FREE.method_id})
        self.assertGreater(self.state["nextEventIndex"], 10_000)
        analytics = self.store.project(self.scope, self.sid)
        self.assertEqual(analytics["eventHead"], self.state["eventHash"])
        self.assertEqual(analytics["metrics"]["tradeCount"], 1)
        self.assertEqual(Fraction(analytics["byPair"]["EURUSD"]["netCashChange"]), gross - fees)
        self.assertEqual(Fraction(analytics["byMethod"][FREE.method_id]["netCashChange"]), gross - fees)
