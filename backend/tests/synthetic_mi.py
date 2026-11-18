"""Deterministic canonical ticks and profile sets for the multi-instrument reducer (SYNTHETIC / TEST ONLY; a workload, not a market model)."""
import json
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

from contracts.canonical import content_hash
from execution.contracts import text
from ticks.contracts import event_id

VECTORS = json.loads((Path(__file__).parent / "fixtures/execution_profiles_v2.json").read_text())["vectors"]
ORDER = [v["name"] for v in VECTORS]                                     # the pinned instrument order used by every test
BASE = dict(AUDUSD="0.65", EURGBP="0.86", NZDUSD="0.60", USDCHF="0.88", AUDJPY="98.0", CADJPY="110.0", EURUSD="1.10", GBPUSD="1.27", NZDJPY="90.0",
            USDCAD="1.36", CHFJPY="170.0", EURJPY="165.0", EURNZD="1.83", GBPJPY="190.0", USDJPY="150.0", XAUUSD="2000.0")
T0, STEP = 100, 10                                                       # the v2 reference harness starts at 100; ages are in ns, so every route quote is fresh


def wires(symbols, version="a" * 64):
    out = []
    for name in symbols:
        w = deepcopy(next(v["input"] for v in VECTORS if v["name"] == name))
        w["primary"]["datasetVersion"] = version
        out.append(w)
    by = {w["symbol"]: w for w in out}
    for w in out:                                                          # one shared timeline: the conversion pin IS the route instrument's primary source
        if w["conversion"] is not None:
            route = by.get(w["conversion"]["symbol"])
            if route is not None:                                         # a missing route is left unbound on purpose: the reducer must refuse such a set
                w["conversion"].update({k: route["primary"][k] for k in ("datasetId", "datasetVersion", "providerId", "feedId", "feedInstrumentId")})
    return out


def tick_size(symbol):
    return Fraction(next(v["input"]["tickSize"] for v in VECTORS if v["name"] == symbol))


def rows(symbol, steps, seed=11, gaps=()):
    """[(timeNs, bid, ask)] on the shared grid T0, T0+STEP, ...; `gaps` are step indexes with no tick for this instrument (so quotes can go stale or tie-break)."""
    size, state, bid = tick_size(symbol), (seed * 7919 + ORDER.index(symbol) * 104729) & 0x7fffffff, Fraction(BASE[symbol])
    out = []
    for i in range(steps):
        state = (state * 1_103_515_245 + 12_345) & 0x7fffffff
        bid += (state % 21 - 10) * size * (3 if size >= Fraction(1, 1000) else 20)   # a few ticks of walk
        if bid <= size * 100:
            bid = Fraction(BASE[symbol])
        if i in gaps:
            continue
        out.append((T0 + i * STEP, text(bid), text(bid + size * (12 if size < Fraction(1, 1000) else 8))))
    return out


def canonical(wire, rows_, extra_per_step=None):
    """Canonical tick wires for one instrument. `extra_per_step` maps a time to additional (bid, ask) rows at the SAME timestamp (an atomic multi-tick group)."""
    src, symbol = wire["primary"], wire["symbol"]
    member = content_hash(dict(schemaVersion=1, member=symbol)); evidence = content_hash(dict(schemaVersion=1, evidence=symbol))
    out, ordinal = [], 0
    for t, bid, ask in rows_:
        for b, a in [(bid, ask)] + list((extra_per_step or {}).get(t, [])):
            out.append(dict(schemaVersion=1, artifact="BTL-CANONICAL-TICK-1", datasetId=src["datasetId"], datasetVersion=src["datasetVersion"], providerId=src["providerId"],
                            feedId=src["feedId"], instrumentId=src["feedInstrumentId"], eventId=event_id(src["providerId"], src["feedId"], member, str(ordinal)), timeNs=str(t),
                            resolutionNs="1", bid=b, ask=a, rawOrdinal=str(ordinal), trustedSequence=None,
                            provenance=dict(sourceId="mi:" + symbol, memberHash=member, originalTimestamp="SYNTHETIC_NS:" + str(t)),
                            quality=dict(evidenceHash=evidence, quote="VALID", freshness="CONFIRMED", gapBefore="NONE", duplicateOf=None)))
            ordinal += 1
    return out
