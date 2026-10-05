"""Offline HistData ASCII ticks only; no download, account or replay integration.

Source ordinal identifies a row, never certifies equal-time event ordering.
No per-side freshness evidence is supplied: imported quotes remain fresh=False.
"""
import re
from datetime import datetime, timedelta, timezone
from decimal import localcontext

from contracts.canonical import decimal_text
from contracts.primitives import ContractError, identifier, require, decimal
from .evaluator import Quote

EST = timezone(timedelta(hours=-5))  # Provider specifies fixed EST, no DST.
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def parse_tick(line, ordinal, source_id):
    identifier(source_id, "source_id")
    require(type(ordinal) is int and 1 <= ordinal <= 2**53-1, "ordinal")
    require(type(line) is str and len(line) <= 8192, "source_line")
    fields = line.rstrip("\r\n").split(",")
    require(len(fields) == 4 and re.fullmatch(r"[0-9]{8} [0-9]{9}", fields[0]), "tick_fields")
    try:
        stamp = datetime.strptime(fields[0][:15], "%Y%m%d %H%M%S").replace(tzinfo=EST)
        stamp += timedelta(milliseconds=int(fields[0][15:]))
    except ValueError:
        require(False, "source_timestamp")
    delta = stamp.astimezone(timezone.utc) - EPOCH
    time_ns = (delta.days*86400 + delta.seconds)*10**9 + delta.microseconds*1000
    bid, ask = decimal(fields[1], "bid", positive=True), decimal(fields[2], "ask", positive=True)
    require(bid <= ask, "crossed_quote")
    require(decimal(fields[3], "source_volume") >= 0, "source_volume")
    return Quote(f"{source_id}:{ordinal}", time_ns, bid, ask, fresh=False)


def inspect_ticks(lines, source_id, max_rows=100000):
    """Bounded streaming diagnostic; no sorting, deduplication or coverage claims.

    Count adjacent repeats only (not global duplicates). Malformed rows remain
    in source bytes and poison acceptance; statistics never certify a feed.
    """
    identifier(source_id, "source_id")
    require(type(max_rows) is int and 1 <= max_rows <= 100000, "row_limit")
    report = dict(rows=0, valid_rows=0, invalid_rows=0, timestamp_ties=0,
                  out_of_order=0, adjacent_repeats=0, zero_spread=0, gaps_over_60s=0,
                  max_gap_ns="0", first_ns=None, last_ns=None,
                  min_spread=None, max_spread=None, coverage_complete=False,
                  source_sequence_verified=False, side_freshness_verified=False)
    previous = None
    previous_line = None
    for ordinal, line in enumerate(lines, 1):
        require(ordinal <= max_rows, "row_limit")
        report["rows"] += 1
        if line == previous_line:
            report["adjacent_repeats"] += 1
        previous_line = line
        try:
            quote = parse_tick(line, ordinal, source_id)
        except ContractError:
            report["invalid_rows"] += 1
            continue
        report["valid_rows"] += 1
        if report["first_ns"] is None:
            report["first_ns"] = str(quote.time_ns)
        report["last_ns"] = str(quote.time_ns)
        if previous is not None:
            gap = quote.time_ns - previous
            report["timestamp_ties"] += gap == 0
            report["out_of_order"] += gap < 0
            report["gaps_over_60s"] += gap > 60*10**9
            report["max_gap_ns"] = str(max(int(report["max_gap_ns"]), gap))
        previous = quote.time_ns
        with localcontext() as context:
            context.prec = 4096
            spread = quote.ask - quote.bid
        report["zero_spread"] += spread == 0
        for key, compare in (("min_spread", min), ("max_spread", max)):
            value = spread if report[key] is None else compare(decimal(report[key]), spread)
            report[key] = decimal_text(value)
    report["structural_status"] = ("EMPTY" if not report["rows"] else
                                   "REJECT" if report["invalid_rows"] or report["out_of_order"] else
                                   "STRUCTURAL_CHECKS_PASS_PRECISION_UNCERTIFIED")
    return report
