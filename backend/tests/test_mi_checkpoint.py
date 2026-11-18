"""Synthetic QA-only checkpoint/restart tests for the isolated MI reducer.

These tests do not integrate the experimental state into the Product worker or
change legacy V1/V2 Session checkpoint formats.
"""
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy

from contracts.canonical import content_hash
from contracts.primitives import ContractError
from execution import mi_checkpoint as micp
from tests import synthetic_mi as syn
from tests.mi_harness import MI
from tests.synthetic_multi_instrument import source
from tests.test_mi_kernel import STEPS, run_mi, script

CUT = 13
_KILL_AFTER_CHECKPOINT = r"""
import json, os, signal, sys
from execution.mi_checkpoint import create
from tests import synthetic_mi as syn
from tests.test_mi_kernel import run_mi
m, _ = run_mi(syn.ORDER, through_steps=13)
payload = {"checkpoint": create(m.state, m.timeline.cursor()), "events": m.events, "commandCount": m.n}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(payload, f, separators=(",", ":"))
os.kill(os.getpid(), signal.SIGKILL)
"""


def restore_harness(payload):
    cp = payload["checkpoint"]
    base = MI(syn.ORDER, steps=STEPS)
    sources = {symbol: source(base.ticks[symbol]) for symbol in syn.ORDER}
    state, timeline = micp.restore(cp, sources, verified_source_pins=micp.pins_from_state(base.state))
    resumed = MI(syn.ORDER, steps=STEPS, rows_override=base.rows, state_override=state,
                 cursor=cp["cursor"], event_prefix=payload["events"], timeline_override=timeline)
    resumed.n = int(payload["commandCount"])
    scripts = {symbol: script(symbol, resumed.rows[symbol]) for symbol in syn.ORDER}
    for step in range(CUT, STEPS):
        resumed.to(resumed.at(step))
        for symbol in resumed.symbols:
            for kind, data, cid in scripts[symbol].get(step, []):
                if kind == "OPEN":
                    resumed.apply("OPEN", dict(data, symbol=symbol), f"{symbol}:{cid}")
                elif resumed.state["orders"].get(f"{symbol}:{data['orderId']}", {}).get("status") == "ACTIVE":
                    resumed.apply("CLOSE", dict(data, orderId=f"{symbol}:{data['orderId']}"))
    return resumed


class MultiInstrumentCheckpoint(unittest.TestCase):
    def test_cold_process_restart_after_sigkill_resumes_to_identical_state_and_event_chain(self):
        with tempfile.TemporaryDirectory(prefix="riksora-mi-cp-") as tmp:
            path = os.path.join(tmp, "checkpoint.json")
            proc = subprocess.run([sys.executable, "-B", "-c", _KILL_AFTER_CHECKPOINT, path], cwd=os.getcwd(),
                                  timeout=90, capture_output=True)
            self.assertEqual(proc.returncode, -signal.SIGKILL, proc.stderr.decode(errors="replace")[-1000:])
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)

        resumed = restore_harness(payload)
        control, _ = run_mi(syn.ORDER)
        self.assertEqual(content_hash(resumed.state), content_hash(control.state))
        self.assertEqual([event["eventId"] for event in resumed.events], [event["eventId"] for event in control.events])
        self.assertEqual(resumed.state["eventHash"], control.state["eventHash"])
        self.assertEqual(resumed.state["balance"], control.state["balance"])
        self.assertEqual(sum(o["status"] == "CLOSED" for o in resumed.state["orders"].values()),
                         sum(o["status"] == "CLOSED" for o in control.state["orders"].values()))

    def test_corrupt_or_mismatched_checkpoint_and_source_pin_are_refused(self):
        partial, _ = run_mi(syn.ORDER, through_steps=CUT)
        checkpoint = micp.create(partial.state, partial.timeline.cursor())
        base = MI(syn.ORDER, steps=STEPS)
        sources = {symbol: source(base.ticks[symbol]) for symbol in syn.ORDER}
        initial = MI(syn.ORDER, steps=STEPS)
        empty_checkpoint = micp.create(initial.state, initial.timeline.cursor())
        _empty_state, empty_timeline = micp.restore(empty_checkpoint, sources, verified_source_pins=micp.pins_from_state(initial.state))
        self.assertEqual(empty_timeline.last_quotes(), {symbol: None for symbol in syn.ORDER})
        with self.assertRaises(ContractError):
            bad = deepcopy(checkpoint); bad["state"]["balance"] = "10001.00"
            micp.restore(bad, sources, verified_source_pins=micp.pins_from_state(base.state))
        with self.assertRaises(ContractError):
            pins = micp.pins_from_state(base.state); pins["EURUSD"]["datasetVersion"] = "f" * 64
            micp.restore(checkpoint, sources, verified_source_pins=pins)
        with self.assertRaises(ContractError):
            bad = deepcopy(checkpoint); bad["cursor"]["frontierNs"] = str(int(bad["cursor"]["frontierNs"]) + 1)
            bad["checkpointHash"] = content_hash({key: value for key, value in bad.items() if key != "checkpointHash"})
            micp.restore(bad, sources, verified_source_pins=micp.pins_from_state(base.state))
        for legacy in (dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-CHECKPOINT-1"),
                       dict(schemaVersion=1, artifact="BTL-TICK-COMPACT-CHECKPOINT-1")):
            with self.assertRaises(ContractError):
                micp.restore(legacy, sources, verified_source_pins=micp.pins_from_state(base.state))


if __name__ == "__main__":
    unittest.main()
