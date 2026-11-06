"""Vectorized, advisory next-event scans over bounded revealed input.

The scanners never select an execution quote or emit a financial result. They
only identify whether already validated, controller-acknowledged quote or
timestamp groups could change a live order. If exact integer scaling,
supported bounds, or quote-quality proof is unavailable, callers retain the
original chronological Python predicate.
"""
from fractions import Fraction

import numpy as np


MAX_EXACT_INT64 = 2**63 - 1
MAX_SCAN_ROWS = 65536


def _scaled_price(value, scale):
    if type(value) is not str:
        return None
    try:
        amount = Fraction(value) * scale
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if amount.denominator != 1 or abs(amount.numerator) > MAX_EXACT_INT64:
        return None
    return amount.numerator


def scan_untrusted_tie(state, rows):
    """Return exact any-can-change result, or ``None`` to request fallback.

    Preconditions are deliberately strict. The caller has already validated
    canonical tick identity, atomic grouping, profile price precision,
    diagnostics and coverage. This function rechecks quality and equal time so
    it cannot turn an incomplete source proof into an optimization decision.
    """
    if type(rows) is not list or len(rows) < 2 or len(rows) > 1024:
        return None
    try:
        moment = int(rows[0]["timeNs"])
        if any(int(row["timeNs"]) != moment for row in rows):
            return None
        for row in rows:
            quality = row["quality"]
            if (quality["quote"] != "VALID" or quality["freshness"] != "CONFIRMED" or
                    quality["gapBefore"] not in ("NONE", "KNOWN_SESSION_CLOSED") or
                    quality["evidenceHash"] is None or quality["duplicateOf"] is not None):
                return None

        scale = Fraction(state["profile"]["priceScale"])
        bids = [_scaled_price(row["bid"], scale) for row in rows]
        asks = [_scaled_price(row["ask"], scale) for row in rows]
        if any(value is None for value in (*bids, *asks)):
            return None
        bids = np.asarray(bids, dtype=np.int64)
        asks = np.asarray(asks, dtype=np.int64)
        candidate = np.zeros(len(rows), dtype=np.bool_)

        for order in state["orders"].values():
            status = order["status"]
            if status not in ("PENDING", "ACTIVE") or moment < int(order["availableNs"]):
                continue
            long_side = order["side"] == "LONG"
            if status == "PENDING":
                kind = order["orderType"]
                if kind == "MARKET":
                    return True
                entry = _scaled_price(order["entry"], scale)
                if entry is None:
                    return None
                prices = asks if long_side else bids
                if kind == "LIMIT":
                    candidate |= prices <= entry if long_side else prices >= entry
                elif kind == "STOP":
                    candidate |= prices >= entry if long_side else prices <= entry
                else:
                    return None
            elif status == "ACTIVE":
                manual = order["exitRequest"]
                # Mirror the reducer's conservative tie ambiguity predicate.
                # It treats any recorded exit request as potentially changing
                # the result once the order itself is available, even before
                # the request's own execution timestamp.
                if manual is not None:
                    return True
                prices = bids if long_side else asks
                stop_loss, take_profit = order["sl"], order["tp"]
                if stop_loss is not None:
                    threshold = _scaled_price(stop_loss, scale)
                    if threshold is None:
                        return None
                    candidate |= prices <= threshold if long_side else prices >= threshold
                if take_profit is not None:
                    threshold = _scaled_price(take_profit, scale)
                    if threshold is None:
                        return None
                    candidate |= prices >= threshold if long_side else prices <= threshold
        return bool(np.any(candidate))
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return None


def scan_next_group(state, groups):
    """Find the earliest group that could change any live order.

    ``groups`` is limited to the controller-acknowledged reveal passed to the
    current ADVANCE, and must already have passed canonical identity,
    atomic-group, and chronology checks. This function does not query a source
    or discover groups beyond that reveal. It only produces a candidate group
    index; the deterministic chronological reducer still processes that full
    group and decides every financial effect. Unsupported proof/size returns
    ``(False, None)`` so callers retain the original reducer path.
    """
    if type(groups) is not list or len(groups) > 64:
        return False, None
    if not groups:
        return True, None
    try:
        scale = Fraction(state["profile"]["priceScale"])
        times, bids, asks, group_indexes = [], [], [], []
        previous_time = None
        for group_index, group in enumerate(groups):
            if type(group) is not dict or type(group.get("events")) is not list:
                return False, None
            rows = group["events"]
            if not rows or len(rows) > 1024 or len(times) + len(rows) > MAX_SCAN_ROWS:
                return False, None
            moment = int(group["timeNs"])
            if previous_time is not None and moment <= previous_time:
                return False, None
            previous_time = moment
            for row in rows:
                if int(row["timeNs"]) != moment:
                    return False, None
                quality = row["quality"]
                if (quality["quote"] != "VALID" or quality["freshness"] != "CONFIRMED" or
                        quality["gapBefore"] not in ("NONE", "KNOWN_SESSION_CLOSED") or
                        quality["evidenceHash"] is None or quality["duplicateOf"] is not None):
                    return False, None
                bid = _scaled_price(row["bid"], scale)
                ask = _scaled_price(row["ask"], scale)
                if bid is None or ask is None or moment > MAX_EXACT_INT64:
                    return False, None
                times.append(moment)
                bids.append(bid)
                asks.append(ask)
                group_indexes.append(group_index)

        times = np.asarray(times, dtype=np.int64)
        bids = np.asarray(bids, dtype=np.int64)
        asks = np.asarray(asks, dtype=np.int64)
        group_indexes = np.asarray(group_indexes, dtype=np.int64)
        candidate = np.zeros(len(times), dtype=np.bool_)

        for order in state["orders"].values():
            status = order["status"]
            if status not in ("PENDING", "ACTIVE"):
                continue
            available = times >= int(order["availableNs"])
            if status == "PENDING":
                kind = order["orderType"]
                if kind == "MARKET":
                    candidate |= available
                    continue
                entry = _scaled_price(order["entry"], scale)
                if entry is None:
                    return False, None
                prices = asks if order["side"] == "LONG" else bids
                if kind == "LIMIT":
                    crossing = prices <= entry if order["side"] == "LONG" else prices >= entry
                elif kind == "STOP":
                    crossing = prices >= entry if order["side"] == "LONG" else prices <= entry
                else:
                    return False, None
                candidate |= available & crossing
            else:
                if order["exitRequest"] is not None:
                    # Keep can_change's conservative manual-exit treatment.
                    candidate |= available
                prices = bids if order["side"] == "LONG" else asks
                stop_loss, take_profit = order["sl"], order["tp"]
                if stop_loss is not None:
                    threshold = _scaled_price(stop_loss, scale)
                    if threshold is None:
                        return False, None
                    crossed = prices <= threshold if order["side"] == "LONG" else prices >= threshold
                    candidate |= available & crossed
                if take_profit is not None:
                    threshold = _scaled_price(take_profit, scale)
                    if threshold is None:
                        return False, None
                    crossed = prices >= threshold if order["side"] == "LONG" else prices <= threshold
                    candidate |= available & crossed

        locations = np.flatnonzero(candidate)
        return True, None if not len(locations) else int(group_indexes[int(locations[0])])
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return False, None
