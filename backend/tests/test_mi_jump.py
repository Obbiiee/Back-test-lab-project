"""QA-only multi-instrument next-event parity; no product or settlement wiring."""
import unittest
from decimal import Decimal

from contracts.canonical import content_hash
from execution import mi_jump
from execution import mi_checkpoint as micp
from execution.contracts import text
from tests import synthetic_mi as syn
from tests.mi_harness import MI
from tests.synthetic_multi_instrument import source


def two_pair_pending():
    symbols = ["EURUSD", "GBPUSD"]
    rows = {}
    trigger = {"EURUSD": "1.099", "GBPUSD": "1.269"}
    bases = {"EURUSD": "1.1", "GBPUSD": "1.27"}
    for symbol in symbols:
        rows[symbol] = []
        for step in range(8):
            bid = (trigger[symbol] if step == 5 else
                   text(Decimal(trigger[symbol]) - Decimal("0.002")) if step == 6 else bases[symbol])
            ask = text(Decimal(bid) + Decimal("0.00020"))
            rows[symbol].append((syn.T0 + step * syn.STEP, bid, ask))
    m = MI(symbols, steps=8, rows_override=rows)
    m.to(m.at(0)); m.to(m.at(1))
    for symbol in symbols:
        entry = text(Decimal(trigger[symbol]) + Decimal("0.00020"))
        m.apply("OPEN", dict(symbol=symbol, side="LONG", orderType="LIMIT", workflow="PLANNED", entry=entry,
                              quantity="0.1", sl=text(Decimal(trigger[symbol]) - Decimal("0.001")),
                              tp="1.2" if symbol == "EURUSD" else "1.4", riskPercent="1", observations=[]), f"pending:{symbol}")
    return m


def clone(m):
    checkpoint = micp.create(m.state, m.timeline.cursor())
    sources = {symbol: source(m.ticks[symbol]) for symbol in m.symbols}
    state, timeline = micp.restore(checkpoint, sources, verified_source_pins=micp.pins_from_state(m.state))
    resumed = MI(m.symbols, steps=len(m.rows[m.symbols[0]]), rows_override=m.rows, state_override=state,
                 cursor=checkpoint["cursor"], event_prefix=m.events, timeline_override=timeline)
    resumed.n = m.n
    return resumed


def chronological_until_event(m, end_step):
    for step in range(2, end_step + 1):
        start = len(m.events)
        m.to(m.at(step))
        new_events = m.events[start:]
        if any(event["kind"] in mi_jump.FINANCIAL_EVENTS for event in new_events):
            return


class MultiInstrumentJump(unittest.TestCase):
    def test_tied_pending_fills_stop_at_same_boundary_as_chronological_replay(self):
        base = two_pair_pending()
        normal, jumped = clone(base), clone(base)
        chronological_until_event(normal, 7)
        result_state, result = mi_jump.run(jumped.state, jumped.timeline, jumped.at(7))
        self.assertEqual(result["status"], "EVENT_FOUND")
        fills = [event for event in result["events"] if event["kind"] == "ENTRY_FILL"]
        self.assertEqual([event["symbol"] for event in fills], ["EURUSD", "GBPUSD"])
        self.assertEqual(len({event["detail"]["timeNs"] for event in fills}), 1)
        jumped.state = result_state
        jumped.events.extend(result["events"])
        self.assertEqual(content_hash(jumped.state), content_hash(normal.state))
        self.assertEqual([event["eventId"] for event in jumped.events], [event["eventId"] for event in normal.events])

        # The next Jump finds the simultaneous protective exits. The exact
        # reducer processes both tied instrument groups before returning.
        normal.to(normal.at(6))
        jumped.state, exit_result = mi_jump.run(jumped.state, jumped.timeline, jumped.at(7))
        exits = [event for event in exit_result["events"] if event["kind"] == "EXIT_FILL"]
        self.assertEqual(exit_result["status"], "EVENT_FOUND")
        self.assertEqual([event["symbol"] for event in exits], ["EURUSD", "GBPUSD"])
        self.assertEqual(len({event["detail"]["timeNs"] for event in exits}), 1)
        jumped.events.extend(exit_result["events"])
        self.assertEqual(content_hash(jumped.state), content_hash(normal.state))
        self.assertEqual([event["eventId"] for event in jumped.events], [event["eventId"] for event in normal.events])

    def test_bounded_search_checkpoint_cancel_and_resume_matches_single_jump(self):
        base = two_pair_pending()
        expected = clone(base)
        expected.state, expected_result = mi_jump.run(expected.state, expected.timeline, expected.at(7))
        split = clone(base)
        split.state, first = mi_jump.run(split.state, split.timeline, split.at(7), max_timestamps=2)
        self.assertEqual(first["status"], "SEARCHING")
        checkpoint = micp.create(split.state, split.timeline.cursor())
        sources = {symbol: source(split.ticks[symbol]) for symbol in split.symbols}
        restored_state, restored_timeline = micp.restore(checkpoint, sources, verified_source_pins=micp.pins_from_state(split.state))
        cancelled_state, cancelled = mi_jump.run(restored_state, restored_timeline, split.at(7), cancelled=lambda: True)
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertEqual(content_hash(cancelled_state), content_hash(restored_state))
        resumed = MI(split.symbols, steps=8, rows_override=split.rows, state_override=restored_state,
                      cursor=checkpoint["cursor"], event_prefix=split.events, timeline_override=restored_timeline)
        resumed.state, second = mi_jump.run(resumed.state, resumed.timeline, resumed.at(7))
        self.assertEqual(second["status"], expected_result["status"])
        self.assertEqual(content_hash(resumed.state), content_hash(expected.state))
        self.assertEqual([event["eventId"] for event in first["events"] + second["events"]],
                         [event["eventId"] for event in expected_result["events"]])

    def test_no_event_until_session_end_keeps_pending_order_pending(self):
        m = MI(["EURUSD"], steps=8)
        m.to(m.at(0))
        m.open("EURUSD", side="LONG", kind="LIMIT", workflow="PLANNED", entry="1", sl="0.9", tp="1.2", cid="far-pending")
        state, result = mi_jump.run(m.state, m.timeline, m.at(7))
        self.assertEqual(result["status"], "NO_EVENT_UNTIL_SESSION_END")
        self.assertEqual(state["orders"]["far-pending"]["status"], "PENDING")
        self.assertFalse(any(event["kind"] in mi_jump.FINANCIAL_EVENTS for event in result["events"]))
        self.assertEqual(result["throughNs"], str(m.at(7)))


if __name__ == "__main__":
    unittest.main()
