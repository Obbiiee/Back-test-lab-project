"""Read-only pair/Method projection tests for isolated MI committed events."""
import unittest

from contracts.models import MethodPolicy
from contracts.primitives import ContractError
from execution import mi_projection
from tests.mi_harness import FREE, MI


FREE_2 = MethodPolicy("method:free-2", "3" * 64, "FREE_STYLE", False, ())


class MultiInstrumentProjection(unittest.TestCase):
    def _portfolio(self):
        m = MI(["EURUSD", "GBPUSD"], steps=12, policies=[FREE, FREE_2])
        m.to(m.at(0))
        m.open("EURUSD", cid="eur-order")
        m.apply("SET_METHOD", {"methodId": FREE_2.method_id})
        m.open("GBPUSD", cid="gbp-order")
        m.to(m.at(4))
        for order_id in ("eur-order", "gbp-order"):
            if m.state["orders"][order_id]["status"] == "ACTIVE":
                m.apply("CLOSE", {"orderId": order_id, "quantity": None})
        m.to(m.at(6))
        return m

    def test_journal_and_analytics_group_by_order_pair_and_creation_method(self):
        m = self._portfolio()
        result = mi_projection.project(m.state, m.events)
        self.assertEqual(result["artifact"], "BTL-MI-QA-VERIFIED-PROJECTION-1")
        self.assertEqual(result["provenance"]["financialAuthority"], "QA_VERIFIED_SYNTHETIC_EVENT_LEDGER_ONLY")
        self.assertEqual({row["id"]: row["symbol"] for row in result["orders"]},
                         {"eur-order": "EURUSD", "gbp-order": "GBPUSD"})
        self.assertEqual({row["id"]: row["methodId"] for row in result["orders"]},
                         {"eur-order": FREE.method_id, "gbp-order": FREE_2.method_id})
        self.assertEqual(set(result["byPair"]), {"EURUSD", "GBPUSD"})
        self.assertEqual(set(result["byMethod"]), {FREE.method_id, FREE_2.method_id})
        self.assertEqual(sum(group["closedTrades"] for group in result["byPair"].values()), len(result["completed"]))
        self.assertEqual(sum(group["closedTrades"] for group in result["byMethod"].values()), len(result["completed"]))
        self.assertEqual(result["account"]["balance"], m.state["balance"])
        self.assertEqual(result["provenance"]["eventHead"], m.state["eventHash"])

    def test_projection_refuses_incomplete_or_corrupt_committed_event_ledger(self):
        m = self._portfolio()
        with self.assertRaises(ContractError) as incomplete:
            mi_projection.project(m.state, m.events[:-1])
        self.assertEqual(incomplete.exception.code, "REFUSED_INCOMPLETE_EVENT_LEDGER")

        corrupt = [dict(event) for event in m.events]
        corrupt[1] = dict(corrupt[1], symbol="USDJPY")
        with self.assertRaises(ContractError) as invalid:
            mi_projection.project(m.state, corrupt)
        self.assertEqual(invalid.exception.code, "CORRUPT_RECORD")


if __name__ == "__main__":
    unittest.main()
