"""Vectorized, advisory next-event scan for one atomic timestamp tie.

The scan never selects an execution quote or emits a financial result. It only
answers the conservative question used for untrusted, non-equivalent ties:
could any row in this already validated timestamp group change a live order?
If exact integer scaling or quote-quality proof is unavailable, callers must
use the chronological Python predicate.
"""
from fractions import Fraction

import numpy as np


MAX_EXACT_INT64 = 2**63 - 1


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
