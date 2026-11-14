"""Independent golden oracle for tick -> OHLC. Deliberately naive and self-contained.

It shares no code with the engine (no numpy, no pyarrow, no repo aggregation helper): one pass over ticks, Python ints and Fractions only.
Locked before any candidate is judged. Contract (RULES_VERSION):

  * bucket = [start, start + tf) with start = floor(ts / tf) * tf; epoch is a UTC midnight and every tf divides 86400 s, so D1 and
    all intraday buckets are anchored at UTC midnight and never straddle a month/year boundary
  * price basis per tick: MID = (bid + ask) / 2 exactly, BID = bid, ASK = ask. Never an average of per-bucket highs
  * open/close = first/last tick of the bucket in SOURCE order (equal timestamps keep their source order); high/low = extremes
  * a bar exists only for a bucket that contains at least one tick: no synthetic bar for a gap or weekend
  * `quoteCount` counts quotes; it is NOT a traded volume and no volume field exists
  * timestamps must be non-decreasing; a decrease is a corrupt source and raises CorruptSource (never silently re-sorted)
"""
from fractions import Fraction

RULES_VERSION = "UTC-MIDNIGHT-HALF-OPEN-1"
TIMEFRAMES = (("M1", 60), ("M3", 180), ("M5", 300), ("M15", 900), ("M30", 1800), ("H1", 3600), ("H2", 7200), ("H4", 14400), ("D1", 86400))
NS = 10**9


class CorruptSource(ValueError):
    pass


def tick_price(bid, ask, basis):
    b, a = Fraction(bid), Fraction(ask)
    if b <= 0 or a <= 0:
        raise CorruptSource("NON_POSITIVE_PRICE")
    return {"MID": (b + a) / 2, "BID": b, "ASK": a}[basis]


def aggregate(ticks, tf_seconds, basis="MID"):
    """ticks: iterable of (ts_ns:int, bid:str, ask:str). Returns list of dict bars (Fractions)."""
    width = tf_seconds * NS
    bars, cur, last_ts = [], None, None
    for ts, bid, ask in ticks:
        if last_ts is not None and ts < last_ts:
            raise CorruptSource("TIMESTAMP_ORDER")
        last_ts = ts
        p = tick_price(bid, ask, basis)
        start = ts - (ts % width)
        if cur is None or cur["t"] != start:
            if cur is not None:
                bars.append(cur)
            cur = dict(t=start, o=p, h=p, l=p, c=p, n=1, first=ts, last=ts)
        else:
            cur["h"] = max(cur["h"], p)
            cur["l"] = min(cur["l"], p)
            cur["c"] = p
            cur["n"] += 1
            cur["last"] = ts
    if cur is not None:
        bars.append(cur)
    return bars


def all_timeframes(ticks, basis="MID"):
    ticks = list(ticks)
    return {name: aggregate(ticks, seconds, basis) for name, seconds in TIMEFRAMES}


def at_cursor(ticks, tf_seconds, cursor_ns, basis="MID"):
    """What a replay at cursor T may see: completed bars with end <= T, plus the forming bar from ticks with ts <= T only."""
    width = tf_seconds * NS
    revealed = [t for t in ticks if t[0] <= cursor_ns]
    bars = aggregate(revealed, tf_seconds, basis)
    completed = [b for b in bars if b["t"] + width <= cursor_ns]
    active = [b for b in bars if b["t"] + width > cursor_ns]
    return completed, (active[0] if active else None)
