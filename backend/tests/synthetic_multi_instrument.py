"""Deterministic authored ticks for several instruments (SYNTHETIC / TEST ONLY; a software workload, not a market model)."""
from market_data.instruments import INSTRUMENTS


def ticks_for(symbol, index, count, seed=7, start_ns=1_577_836_800 * 10**9, step_ns=1_000_000_000):
    """`count` ticks for one instrument. Times are on a coarse grid, so several instruments (and several ticks of one instrument) share timestamps."""
    out, state = [], (seed * 1_000_003 + index * 7919) & 0x7fffffff
    for i in range(count):
        state = (state * 1_103_515_245 + 12_345) & 0x7fffffff
        slot = i // 2 if state % 5 == 0 else i                         # every 5th tick repeats the previous slot: an atomic multi-tick group
        bid = 100_000 + (state % 400)
        out.append(dict(timeNs=str(start_ns + (slot + index % 3) * step_ns), instrumentId=symbol, rawOrdinal=str(i), bid=str(bid), ask=str(bid + 12)))
    # sources must be ordered by (timeNs, rawOrdinal) with strictly increasing ordinals inside a group
    out.sort(key=lambda t: (int(t["timeNs"]), int(t["rawOrdinal"])))
    return out


def source(ticks):
    """A re-openable source: open(skip_groups) yields the ticks of the remaining groups."""
    groups, last = [], None
    for t in ticks:
        if last is None or t["timeNs"] != last:
            groups.append([])
            last = t["timeNs"]
        groups[-1].append(t)
    return lambda skip=0: iter([t for g in groups[skip:] for t in g])


def catalogue(count, instruments=None):
    names = list(instruments or INSTRUMENTS)
    data = {name: ticks_for(name, i, count) for i, name in enumerate(names)}
    return names, data, {name: source(ticks) for name, ticks in data.items()}
