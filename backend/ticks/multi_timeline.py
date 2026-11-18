"""Deterministic multi-instrument timeline (stage 1 of the multi-pair design; NOT wired into any Session, reducer or API).

Merges per-instrument canonical tick groups into ONE ordered stream for a Session that pins an ordered instrument list.
Contract (each point is tested in tests/test_multi_timeline.py):
  * total order is (timeNs, instrumentIndex, rawOrdinal), where instrumentIndex is the position in the PINNED list, never arrival order or a name sort;
  * a timestamp group is atomic per (timeNs, instrument): all its ticks are emitted together, in rawOrdinal order, never split by an `advance` target;
  * `advance(target_ns)` returns only groups with timeNs <= target_ns; nothing later leaves this object (the controller-private peek of the next group's time is
    never exposed), so a consumer cannot learn a future tick, gap or EOF;
  * `last_quotes()` holds, per instrument, the last revealed quote (never a later one); an instrument with no tick yet is None;
  * `cursor()` / `resume()` give exact checkpoint and resume: the remainder after a resume equals the uninterrupted remainder.
A source is a callable `open(skip_groups) -> iterator of tick dicts` ordered by (timeNs, rawOrdinal); it must be re-openable so a cursor can be honoured.
"""
from contracts.primitives import ContractError, require

MAX_INSTRUMENTS = 16


def _t(tick):
    return int(tick["timeNs"])


class _Source:
    def __init__(self, name, open_fn, skip):
        self.name, self.open_fn, self.consumed = name, open_fn, skip
        self._it, self._peek, self._carry, self._last = open_fn(skip), None, None, None

    def _next_tick(self):
        if self._carry is not None:
            tick, self._carry = self._carry, None
            return tick
        return next(self._it, None)

    def _fill(self):
        """Controller-private: read the next group (all ticks sharing one timeNs) without publishing it."""
        if self._peek is not None:
            return self._peek
        first = self._next_tick()
        if first is None:
            return None
        group = [first]
        while True:
            nxt = self._next_tick()
            if nxt is None:
                break
            if _t(nxt) == _t(first):
                group.append(nxt)
            else:
                self._carry = nxt
                break
        require(all(int(a["rawOrdinal"]) < int(b["rawOrdinal"]) for a, b in zip(group, group[1:])), "groupOrder", "REFUSED_GROUP_ORDER")
        if self._last is not None:
            require(_t(first) > self._last, "sourceOrder", "REFUSED_SOURCE_ORDER")      # a source may never go backwards or repeat a group time
        self._peek = group
        return group

    def next_time(self):
        group = self._fill()
        return None if group is None else _t(group[0])

    def take(self):
        group = self._fill()
        self._peek, self._last = None, _t(group[0])
        self.consumed += 1
        return group


class MultiTimeline:
    def __init__(self, instruments, sources, *, cursor=None):
        require(type(instruments) is list and 1 <= len(instruments) <= MAX_INSTRUMENTS and len(set(instruments)) == len(instruments), "instruments", "REFUSED_INSTRUMENT_SET")
        require(set(sources) == set(instruments), "sources", "REFUSED_INSTRUMENT_SET")
        self.instruments = list(instruments)
        skip = {name: 0 for name in instruments}
        self.frontier_ns = 0
        self.quotes = {name: None for name in instruments}
        if cursor is not None:
            require(cursor["instruments"] == self.instruments, "cursor", "REFUSED_CURSOR_MISMATCH")
            skip = dict(cursor["consumed"])
            self.frontier_ns = int(cursor["frontierNs"])
            self.quotes = {name: cursor["quotes"][name] for name in instruments}
        self._src = [_Source(name, sources[name], skip[name]) for name in instruments]

    def advance(self, target_ns):
        """Groups with timeNs <= target_ns, in total order. Each item: dict(timeNs, instrument, instrumentIndex, events)."""
        require(type(target_ns) is int and target_ns >= self.frontier_ns, "target", "REFUSED_REWIND")
        out = []
        while True:
            best = None
            for index, src in enumerate(self._src):
                when = src.next_time()
                if when is not None and when <= target_ns and (best is None or (when, index) < best[0]):
                    best = ((when, index), src)
            if best is None:
                break
            (when, index), src = best
            events = src.take()
            self.quotes[src.name] = dict(timeNs=str(when), bid=events[-1]["bid"], ask=events[-1]["ask"])
            out.append(dict(timeNs=when, instrument=src.name, instrumentIndex=index, events=events))
        self.frontier_ns = target_ns
        return out

    def last_quotes(self):
        return {name: (None if q is None else dict(q)) for name, q in self.quotes.items()}

    def _controller_next_time(self):
        """Private scheduling peek for trusted controller code; never pass this to a consumer/view."""
        values = [source.next_time() for source in self._src]
        return min((value for value in values if value is not None), default=None)

    def cursor(self):
        return dict(schemaVersion=1, artifact="BTL-MULTI-TIMELINE-CURSOR-1", instruments=list(self.instruments), frontierNs=str(self.frontier_ns),
                    consumed={s.name: s.consumed for s in self._src}, quotes=self.last_quotes())
