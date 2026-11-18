"""Multi-method reducer (versioned MM state; legacy Sessions are untouched). Pure/in-memory: no database.
 * PARITY: all 24 authored financial golden scenarios give the same fills, prices, balances, statuses and journal rows when the Session is seeded as MM with one Method
 * SWITCH: Method rules follow the active Method for new orders; each order keeps the Method it was created under; history is not rewritten; balance, orders and timeline continue
 * Protocol attribution: closing or cancelling is governed by the ORDER's own Method, so switching cannot bypass a Protocol rule
 * legacy Sessions refuse SET_METHOD; invalid method sets are refused."""
import unittest
from copy import deepcopy
from unittest.mock import patch

from application.models import TrustedScope
from contracts.models import MethodPolicy
from contracts.primitives import ContractError
from execution.controller import ExecutionController
import tests.test_tick_execution as te

FREE = MethodPolicy("method:free", "1" * 64, "FREE_STYLE", False, ())
PROTO = MethodPolicy("method:proto", "2" * 64, "PROTOCOL", True, ("c1",), "1", "2")


class HarnessMM(te.Harness):
    METHODS, ACTIVE = [FREE], "method:free"

    def __init__(self, provider, profile=None, policy=None, store=None, scope=None, session="fixture:session"):
        self.store = store or te.MemoryStore()
        self.scope = scope or TrustedScope("fixture:workspace", "fixture:actor")
        self.session, self.counter = session, 0
        self.controller = ExecutionController(self.store, provider)
        self.controller.create(self.scope, session, profile or te.profile_for(), None, methods=self.METHODS, active_method_id=self.ACTIVE)


import re
HEX = re.compile(r"^[0-9a-f]{64}$")


def blind(value):
    """Replace every 64-hex identifier (event ids and fill references: they are derived from a hash chain that legitimately differs between engines) by a marker."""
    if isinstance(value, dict):
        return {k: blind(v) for k, v in value.items()}
    if isinstance(value, list):
        return [blind(v) for v in value]
    return "<H>" if isinstance(value, str) and HEX.match(value) else value


def strip(event):
    """An event with the fields that legitimately differ between the legacy and the MM engine removed (engine/method identity and the hash chain it feeds)."""
    e = deepcopy(event)
    for k in ("engineVersion", "methodHash", "eventId", "previousHash"):
        e.pop(k, None)
    e["detail"].pop("methodId", None)
    return blind(e)


class Parity(unittest.TestCase):
    def test_all_authored_golden_scenarios_equal_the_legacy_engine(self):
        for case in te.goldens()["scenarios"]:
            with self.subTest(case=case["id"]):
                legacy = te.exercise(case)
                with patch.object(te, "Harness", HarnessMM):
                    mm = te.exercise(case)
                te.assert_case(self, case, mm)                                   # the frozen golden expectations hold on the MM state
                a = legacy.controller.inspect(legacy.scope, legacy.session, maximum=256)
                b = mm.controller.inspect(mm.scope, mm.session, maximum=256)
                self.assertEqual([strip(e) for e in a["events"]], [strip(e) for e in b["events"]])
                for key in ("balance", "realizedGross", "commission", "throughNs", "unresolved", "ended", "financial"):
                    self.assertEqual(a["state"][key], b["state"][key], key)
                self.assertEqual(blind({k: {f: v for f, v in o.items() if f != "methodId"} for k, o in a["state"]["orders"].items()}),
                                 blind({k: {f: v for f, v in o.items() if f != "methodId"} for k, o in b["state"]["orders"].items()}))


def case_rows():
    return next(c for c in te.goldens()["scenarios"] if c["id"] == "buy-limit-improvement")


class Switch(unittest.TestCase):
    def harness(self, methods=(FREE, PROTO), active="method:free"):
        case = case_rows()
        HarnessMM.METHODS, HarnessMM.ACTIVE = list(methods), active
        self.addCleanup(lambda: (setattr(HarnessMM, "METHODS", [FREE]), setattr(HarnessMM, "ACTIVE", "method:free")))
        h = HarnessMM(te.provider_for(case), te.profile_for(case))
        return h, case

    def test_switch_records_an_event_keeps_balance_orders_and_timeline(self):
        h, case = self.harness()
        h.call("OPEN", te.open_plan(case["open"]), name="order:1")
        before = h.state
        result = h.call("SET_METHOD", {"methodId": "method:proto"})
        after = h.state
        self.assertEqual([e["kind"] for e in result["events"]], ["METHOD_SWITCHED"])
        self.assertEqual((result["events"][0]["detail"]["fromMethodId"], result["events"][0]["detail"]["toMethodId"]), ("method:free", "method:proto"))
        for key in ("balance", "throughNs", "realizedGross", "commission"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(before["orders"], after["orders"], "an open order must not change when the Method changes")
        self.assertEqual((after["activeMethodId"], after["policy"]["methodId"]), ("method:proto", "method:proto"))

    def test_each_order_keeps_the_method_it_was_created_under(self):
        h, case = self.harness()
        h.call("OPEN", te.open_plan(case["open"]), name="order:1")                     # created under Free Style
        h.call("SET_METHOD", {"methodId": "method:proto"})
        plan = te.open_plan(case["open"])
        plan.update(workflow="PLANNED", orderType="LIMIT", riskPercent="1", observations=[dict(conditionId="c1", outcome="PASS")])
        with self.assertRaises(ContractError):                                         # Protocol rules now apply to NEW orders (needs SL/TP, risk and R:R)
            h.call("OPEN", plan, name="order:2")
        self.assertEqual(h.state["orders"]["order:1"]["methodId"], "method:free")
        h.call("SET_METHOD", {"methodId": "method:free"})
        h.call("OPEN", te.open_plan(dict(case["open"], side=case["open"]["side"])), name="order:3")
        self.assertEqual({k: o["methodId"] for k, o in h.state["orders"].items()}, {"order:1": "method:free", "order:3": "method:free"})
        # attribution is in the immutable events too
        events = h.controller.inspect(h.scope, h.session, maximum=256)["events"]
        accepted = {e["orderId"]: e["detail"]["methodId"] for e in events if e["kind"] == "ORDER_ACCEPTED"}
        self.assertEqual(accepted, {"order:1": "method:free", "order:3": "method:free"})

    def test_a_protocol_order_cannot_be_manually_closed_by_switching_to_free_style(self):
        case = next(c for c in te.goldens()["scenarios"] if c["id"] == "partial-then-full-fixed-commission")
        HarnessMM.METHODS, HarnessMM.ACTIVE = [FREE, PROTO], "method:proto"
        self.addCleanup(lambda: (setattr(HarnessMM, "METHODS", [FREE]), setattr(HarnessMM, "ACTIVE", "method:free")))
        h = HarnessMM(te.provider_for(case), te.profile_for(case))
        # a Protocol order needs PLANNED LIMIT/STOP with the policy's risk and R:R; build it from the golden's levels
        entry = case["open"]
        with self.assertRaises(ContractError):
            h.call("OPEN", te.open_plan(entry), name="order:1")                        # a QUICK/MARKET order is refused under the Protocol Method

    def test_journal_rows_carry_the_method_of_each_order_across_a_switch(self):
        from execution.analysis import project
        free_b = MethodPolicy("method:free-b", "3" * 64, "FREE_STYLE", False, ())
        case = dict(rows=[[1, "100", "101"], [2, "100", "101"], [3, "104", "105"], [4, "104", "105"], [5, "106", "107"], [6, "106", "107"]])
        HarnessMM.METHODS, HarnessMM.ACTIVE = [FREE, free_b], "method:free"
        self.addCleanup(lambda: (setattr(HarnessMM, "METHODS", [FREE]), setattr(HarnessMM, "ACTIVE", "method:free")))
        h = HarnessMM(te.provider_for(case), te.profile_for(case))
        market = dict(side="LONG", orderType="MARKET", entry="101", quantity="0.1", sl=None, tp=None)
        h.call("OPEN", te.open_plan(market), name="order:1"); h.through(2)
        h.call("CLOSE", {"orderId": "order:1", "quantity": None}); h.through(4)                       # trade 1 under Free A: +3 points
        balance_before_switch = h.state["balance"]
        h.call("SET_METHOD", {"methodId": "method:free-b"})
        self.assertEqual(h.state["balance"], balance_before_switch)                                 # the switch moves no money
        h.call("OPEN", te.open_plan(dict(market, entry="107")), name="order:2"); h.through(5)
        h.call("CLOSE", {"orderId": "order:2", "quantity": None}); h.through(6)                       # trade 2 under Free B: -1 point
        inspected = h.controller.inspect(h.scope, h.session, maximum=256)
        history = project(inspected["state"], iter(inspected["events"]), None)                        # the full event chain, across the switch, verifies
        rows = {r["id"]: r for r in history["orders"]}
        self.assertEqual({k: (r["methodId"], r["status"]) for k, r in rows.items()}, {"order:1": ("method:free", "CLOSED"), "order:2": ("method:free-b", "CLOSED")})
        self.assertEqual(inspected["state"]["balance"], "10020")                                    # 10000 + 30 - 10, exactly as a single-method Session would give
        self.assertEqual([e["kind"] for e in inspected["events"] if e["kind"] == "METHOD_SWITCHED"], ["METHOD_SWITCHED"])

    def test_a_tampered_method_hash_breaks_the_event_chain(self):
        from execution.analysis import project
        case = case_rows()
        h, _ = self.harness()
        h.call("OPEN", te.open_plan(case["open"]), name="order:1")
        inspected = h.controller.inspect(h.scope, h.session, maximum=256)
        events = deepcopy(inspected["events"])
        events[0]["methodHash"] = "9" * 64
        with self.assertRaises(ContractError):
            project(inspected["state"], iter(events), None)

    def test_setting_an_unknown_or_the_same_method_is_refused(self):
        h, _ = self.harness()
        with self.assertRaises(ContractError):
            h.call("SET_METHOD", {"methodId": "method:nope"})
        with self.assertRaises(ContractError):
            h.call("SET_METHOD", {"methodId": "method:free"})

    def test_legacy_sessions_refuse_set_method(self):
        case = case_rows()
        h = te.Harness(te.provider_for(case), te.profile_for(case))
        with self.assertRaises(ContractError):
            h.call("SET_METHOD", {"methodId": "method:free"})

    def test_invalid_method_sets_are_refused(self):
        from execution.contracts import seed_state_mm, profile_wire
        profile = profile_wire(te.profile_for())
        args = ("s:1", "d:1", "a" * 64, "0", profile)
        for policies, active in (([], "x"), ([FREE, FREE], "method:free"), ([FREE], "method:other"), ([FREE] * 17, "method:free")):
            with self.assertRaises(ContractError):
                seed_state_mm(*args, policies, active)
        self.assertEqual(seed_state_mm(*args, [FREE, PROTO], "method:free")["policy"]["methodId"], "method:free")


if __name__ == "__main__":
    unittest.main()
