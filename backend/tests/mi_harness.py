"""Harness: the multi-instrument reducer fed by the multi-instrument timeline, and the single-instrument v2 kernel used as the per-instrument reference."""
from copy import deepcopy

from contracts.models import MethodPolicy
from execution import mi_kernel as mi
from execution.profile_set import ProfileSet
from tests import synthetic_mi as syn
from tests.synthetic_multi_instrument import source
from ticks.multi_timeline import MultiTimeline

FREE = MethodPolicy("method:free", "1" * 64, "FREE_STYLE", False, ())
PROTO = MethodPolicy("method:proto", "2" * 64, "PROTOCOL", True, ("c1",), "1", "2")


class MI:
    def __init__(self, symbols, steps=40, balance="10000", policies=None, active="method:free", seed=11, gaps=None, extra=None, rows_override=None,
                 state_override=None, cursor=None, event_prefix=None, timeline_override=None):
        self.symbols = list(symbols)
        self.wires = syn.wires(self.symbols)
        self.rows = {s: (rows_override or {}).get(s) or syn.rows(s, steps, seed, (gaps or {}).get(s, ())) for s in self.symbols}
        self.ticks = {w["symbol"]: syn.canonical(w, self.rows[w["symbol"]], (extra or {}).get(w["symbol"])) for w in self.wires}
        sources = {s: source(t) for s, t in self.ticks.items()}
        self.timeline = timeline_override or MultiTimeline(self.symbols, sources, cursor=cursor)
        self.pset = ProfileSet(self.wires)
        self.state = deepcopy(state_override) if state_override is not None else mi.seed_state("mi:session", self.pset, policies or [FREE], active, balance, str(syn.T0))
        self.events = list(event_prefix or [])
        self.n = int(self.state["nextEventIndex"])

    def apply(self, kind, payload=None, cid=None):
        self.n += 1
        cmd = dict(schemaVersion=1, artifact=mi.MI_COMMAND, sessionId=self.state["sessionId"], commandId=cid or f"cmd:{self.n}",
                   expectedRevision=self.state["revision"], kind=kind, payload=payload or {})
        proposed, events = mi.submit(self.state, cmd)
        if kind == "ADVANCE":
            groups = self.timeline.advance(int(payload["targetNs"]))
            proposed, more = mi.advance(proposed, groups, payload["targetNs"])
            events = events + more
        proposed["revision"] += 1
        mi.validate_state(proposed)
        self.state = proposed
        self.events += events
        return events

    def to(self, t):
        return self.apply("ADVANCE", dict(targetNs=str(t)))

    def at(self, step):
        return syn.T0 + step * syn.STEP

    def quote(self, symbol):
        g = self.state["groups"][symbol]
        return g["events"][0]["bid"], g["events"][0]["ask"]

    def open(self, symbol, side="LONG", lots="0.1", kind="MARKET", workflow="QUICK", entry=None, sl=None, tp=None, cid=None, observations=None, risk="1"):
        bid, ask = self.quote(symbol)
        entry = entry or (ask if side == "LONG" else bid)
        return self.apply("OPEN", dict(symbol=symbol, side=side, orderType=kind, workflow=workflow, entry=entry, quantity=lots, sl=sl, tp=tp, riskPercent=risk,
                                       observations=observations or []), cid)


def reference(symbol, rows_, route_rows, script, steps):
    """The single-instrument v2 kernel (the existing, tested engine) run on the SAME ticks. `script` = {step: [(kind, payload, cid)]}; returns the Harness."""
    from tests.test_kernel_v2 import scene_system
    h = scene_system(symbol, rows_, route_rows)
    for step in range(steps):
        h.tick(syn.T0 + step * syn.STEP)
        for kind, payload, cid in script.get(step, []):
            if kind == "CLOSE" and h.state["orders"].get(payload["orderId"], {}).get("status") != "ACTIVE":
                continue                                                  # the position was already closed by its SL/TP: nothing to close (same rule as the MI runner)
            h.apply(kind, payload, cid)
    return h
