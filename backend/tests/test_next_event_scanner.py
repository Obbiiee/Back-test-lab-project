"""Exact candidate parity for the controller-side vectorized tie scanner."""
import random
import unittest
from unittest.mock import patch

from contracts.canonical import canonical_bytes
from execution.engine import can_change
from execution.next_event import scan_untrusted_tie
from tests.test_execution_goldens import goldens
from tests.test_tick_execution import Harness, open_plan, provider_for


def quote(time_ns, bid, ask, *, quality=None):
    return {
        "timeNs": str(time_ns), "bid": str(bid), "ask": str(ask),
        "quality": quality or {
            "quote": "VALID", "freshness": "CONFIRMED", "gapBefore": "NONE",
            "evidenceHash": "a" * 64, "duplicateOf": None,
        },
    }


def order(*, status, side, order_type="LIMIT", entry="100", sl=None, tp=None,
          available="0", exit_request=None):
    return {
        "status": status, "side": side, "orderType": order_type, "entry": entry,
        "sl": sl, "tp": tp, "availableNs": available, "exitRequest": exit_request,
    }


class NextEventScannerTests(unittest.TestCase):
    def state(self, orders):
        return {"profile": {"priceScale": "1000"}, "orders": orders}

    def test_vectorized_candidate_matches_chronological_predicate(self):
        randomizer = random.Random(43017)
        statuses = ("PENDING", "ACTIVE", "CLOSED", "CANCELLED")
        kinds = ("MARKET", "LIMIT", "STOP")
        for case in range(250):
            orders = {}
            for index in range(randomizer.randint(0, 12)):
                status = randomizer.choice(statuses)
                orders[str(index)] = order(
                    status=status, side=randomizer.choice(("LONG", "SHORT")),
                    order_type=randomizer.choice(kinds),
                    entry=str(randomizer.randint(90, 110)),
                    sl=None if randomizer.randrange(3) == 0 else str(randomizer.randint(90, 105)),
                    tp=None if randomizer.randrange(3) == 0 else str(randomizer.randint(95, 115)),
                    available=str(randomizer.choice((0, 100, 200))),
                    exit_request=(None if randomizer.randrange(3) else
                                  {"availableNs": str(randomizer.choice((0, 100, 200)))}) if status == "ACTIVE" else None,
                )
            moment = randomizer.choice((50, 150, 250))
            rows = [quote(moment, randomizer.randint(90, 110), randomizer.randint(90, 110))
                    for _ in range(randomizer.randint(2, 64))]
            state = self.state(orders)
            expected = any(can_change(state, row) for row in rows)
            self.assertIs(scan_untrusted_tie(state, rows), expected,
                          f"case={case} orders={orders} rows={rows}")

    def test_market_protection_manual_exit_and_availability_edges(self):
        cases = [
            ({"m": order(status="PENDING", side="LONG", order_type="MARKET")}, True),
            ({"l": order(status="PENDING", side="LONG", entry="101")}, False),
            ({"l": order(status="PENDING", side="LONG", entry="101")}, True),
            ({"s": order(status="ACTIVE", side="LONG", sl="99", tp="110")}, False),
            ({"s": order(status="ACTIVE", side="LONG", sl="99", tp="110")}, True),
            ({"x": order(status="ACTIVE", side="SHORT", exit_request={"availableNs": "150"})}, True),
            ({"x": order(status="ACTIVE", side="SHORT", exit_request={"availableNs": "100"})}, True),
        ]
        groups = [
            [quote(100, 100, 102)],
            [quote(100, 100, 102)],
            [quote(100, 100, 102), quote(100, 100, 100)],
            [quote(100, 100, 100)],
            [quote(100, 98, 100), quote(100, 100, 100)],
            [quote(100, 100, 100)],
            [quote(100, 100, 100)],
        ]
        for (orders, expected), rows in zip(cases, groups):
            self.assertIs(scan_untrusted_tie(self.state(orders), rows * 2), expected)

    def test_unproven_quality_and_unbounded_integer_fall_back(self):
        state = self.state({"p": order(status="PENDING", side="LONG", order_type="MARKET")})
        invalid = quote(100, 100, 101, quality={
            "quote": "VALID", "freshness": "UNKNOWN", "gapBefore": "NONE",
            "evidenceHash": "a" * 64, "duplicateOf": None,
        })
        self.assertIsNone(scan_untrusted_tie(state, [invalid, quote(100, 100, 101)]))
        too_large = quote(100, str(2**63), "101")
        self.assertIsNone(scan_untrusted_tie(self.state({}), [too_large, too_large]))
        self.assertIsNone(scan_untrusted_tie(state, [quote(100, 100, 101)]))

    def test_engine_uses_scanner_for_changing_untrusted_tie_and_keeps_frozen_result(self):
        case = next(row for row in goldens()["scenarios"] if row["id"] == "changing-untrusted-tie")
        harness = Harness(provider_for(case))
        harness.call("OPEN", open_plan(case["open"]), name="scanner:order")
        with patch("execution.engine.scan_untrusted_tie", wraps=scan_untrusted_tie) as scanner:
            harness.through(2)
        self.assertEqual(scanner.call_count, 1)
        self.assertTrue(harness.state["unresolved"])
        self.assertEqual(harness.state["balance"], case["balance"])
        events = harness.controller.inspect(harness.scope, harness.session, maximum=256)["events"]
        self.assertIn("UNRESOLVED_EQUAL_TIME_ORDER",
                      [event["detail"].get("reason") for event in events if event["kind"] == "UNRESOLVED"])

        fallback = Harness(provider_for(case))
        fallback.call("OPEN", open_plan(case["open"]), name="scanner:order")
        with patch("execution.engine.scan_untrusted_tie", return_value=None):
            fallback.through(2)
        fallback_events = fallback.controller.inspect(fallback.scope, fallback.session, maximum=256)["events"]
        check = lambda state, rows: canonical_bytes({
            "schemaVersion": 1, "artifact": "BTL-NEXT-EVENT-SCANNER-PARITY-1",
            "state": state, "events": rows,
        })
        self.assertEqual(check(harness.state, events), check(fallback.state, fallback_events))


if __name__ == "__main__":
    unittest.main()
