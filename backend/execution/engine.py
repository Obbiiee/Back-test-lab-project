"""Pure exact reducer. No transport, provider, storage, clock or candle access.

Returned transitions are proposals. Only the durable controller commit publishes
SIMULATED_FILL; an observed quote is never a broker execution claim.
"""
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import canonical_bytes, content_hash
from contracts.models import validate_action
from contracts.primitives import require, ContractError, digest
from ticks.contracts import CanonicalTick, keys, uint
from ticks.timeline import make_group
from .contracts import (ENGINE_VERSION, MAX_EVENTS, MAX_ORDERS, command_wire, exact,
                        money, open_payload, policy_from_wire, price, text, validate_state)


def emit(state, events, kind, *, order_id=None, classification="OBSERVED_FEED_EVENT", **detail):
    require(len(events) < MAX_EVENTS, "events", "REFUSED_EVENT_LIMIT")
    event = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-EVENT-1", engineVersion=ENGINE_VERSION,
                 sessionId=state["sessionId"], datasetId=state["datasetId"], datasetVersion=state["datasetVersion"],
                 profileHash=state["profileHash"], methodHash=state["policy"]["definitionHash"],
                 sequence=state["nextEventIndex"], previousHash=state["eventHash"],
                 kind=kind, classification=classification, orderId=order_id, detail=detail)
    event["eventId"] = content_hash(event)
    state["eventHash"] = event["eventId"]
    state["nextEventIndex"] += 1
    events.append(event)
    return event["eventId"]


def unresolved(state, events, reason, evidence=None):
    if state["unresolved"]:
        return
    affected = []
    for order_id, order in state["orders"].items():
        if order["status"] in ("PENDING", "ACTIVE"):
            order["status"] = "UNRESOLVED"
            affected.append(order_id)
    state["unresolved"] = True
    emit(state, events, "UNRESOLVED", classification="UNRESOLVED", reason=reason,
         affectedOrderIds=affected, evidence=evidence)


def submit(state, raw):
    validate_state(state)
    command = command_wire(raw)
    require(command["sessionId"] == state["sessionId"], "session", "REFUSED_SESSION_MISMATCH")
    require(command["expectedRevision"] == state["revision"], "revision", "REFUSED_STALE_REVISION")
    state, events = deepcopy(state), []
    kind, payload = command["kind"], command["payload"]
    require(kind in ("ADVANCE", "SEEK") or not state["ended"], "ended", "REFUSED_SESSION_ENDED")
    require(kind in ("ADVANCE", "SEEK", "END") or not state["unresolved"], "unresolved", "REFUSED_UNRESOLVED_SESSION")
    if kind == "OPEN":
        require(len(state["orders"]) < MAX_ORDERS, "orders", "REFUSED_STATE_LIMIT")
        order_id = command["commandId"]
        require(order_id not in state["orders"], "order", "REFUSED_ORDER_EXISTS")
        policy = policy_from_wire(state["policy"])
        plan = open_payload(payload, state["profile"], policy, state["balance"])
        order = dict(plan, status="PENDING", availableNs=state["throughNs"], remaining=plan["quantity"],
                     entryPrice=None, entryFillRef=None, entryCost="0", exitRequest=None)
        state["orders"][order_id] = order
        emit(state, events, "ORDER_ACCEPTED", order_id=order_id, classification="ACCEPTED_COMMAND",
             commandId=command["commandId"], availableNs=order["availableNs"], plan=plan)
    elif kind in ("CANCEL", "CLOSE"):
        order_id = payload["orderId"]
        order = state["orders"].get(order_id)
        require(order is not None, "order", "REFUSED_ORDER_UNAVAILABLE")
        policy = policy_from_wire(state["policy"])
        if kind == "CANCEL":
            require(order["status"] == "PENDING", "order", "REFUSED_NOT_PENDING")
            validate_action(policy, "CANCEL_PENDING")
            order["status"] = "CANCELLED"
            emit(state, events, "ORDER_CANCELLED", order_id=order_id, classification="ACCEPTED_COMMAND")
        else:
            validate_action(policy, "MANUAL_CLOSE" if payload["quantity"] is None else "PARTIAL_CLOSE")
            require(order["status"] == "ACTIVE" and order["exitRequest"] is None, "position", "REFUSED_NOT_ACTIVE")
            size = Fraction(order["remaining"]) if payload["quantity"] is None else exact(payload["quantity"], "partialQuantity", True)
            if payload["quantity"] is not None:
                require(size < Fraction(order["remaining"]), "quantity", "REFUSED_PARTIAL_QUANTITY")
                require((size / Fraction(state["profile"]["lotStep"])).denominator == 1, "quantity", "REFUSED_LOT_PRECISION")
            order["exitRequest"] = dict(quantity=text(size), availableNs=state["throughNs"], commandId=command["commandId"])
            emit(state, events, "EXIT_REQUESTED", order_id=order_id, classification="ACCEPTED_COMMAND", request=order["exitRequest"])
    elif kind == "END":
        for order_id, order in state["orders"].items():
            if order["status"] == "PENDING":
                order["status"] = "EXPIRED"
                emit(state, events, "EXPIRED_NO_QUOTE", order_id=order_id, classification="UNRESOLVED", reason="UNRESOLVED_NO_QUOTE")
            elif order["status"] == "ACTIVE":
                unresolved(state, events, "UNRESOLVED_SESSION_END_ACTIVE")
        state["ended"] = True
        emit(state, events, "SESSION_ENDED", classification="ACCEPTED_COMMAND", throughNs=state["throughNs"])
    elif kind == "SEEK":
        require(not state["financial"] and not state["unresolved"] and not state["ended"] and
                not any(o["status"] in ("PENDING", "ACTIVE") for o in state["orders"].values()),
                "seek", "REFUSED_REWIND_REQUIRES_FORK")
    return state, events


def live(state):
    return any(o["status"] in ("PENDING", "ACTIVE") for o in state["orders"].values())


def crossing(order, quote):
    side = Fraction(quote["ask"] if order["side"] == "LONG" else quote["bid"])
    if order["orderType"] == "MARKET":
        return True
    direction = 1 if order["side"] == "LONG" else -1
    difference = direction * (side - Fraction(order["entry"]))
    return difference <= 0 if order["orderType"] == "LIMIT" else difference >= 0


def protective(order, quote):
    value = Fraction(quote["bid"] if order["side"] == "LONG" else quote["ask"])
    direction = 1 if order["side"] == "LONG" else -1
    if order["sl"] is not None and direction * (value - Fraction(order["sl"])) <= 0:
        return "SL"
    if order["tp"] is not None and direction * (value - Fraction(order["tp"])) >= 0:
        return "TP"
    return None


def can_change(state, quote):
    for order in state["orders"].values():
        if int(quote["timeNs"]) < int(order["availableNs"]):
            continue
        if order["status"] == "PENDING" and crossing(order, quote):
            return True
        if order["status"] == "ACTIVE" and (order["exitRequest"] is not None or protective(order, quote)):
            return True
    return False


def coverage_complete(coverage, start, end):
    if start == end:
        return True
    cursor = start
    for row in coverage:
        lo, hi = int(row["startNs"]), int(row["endNs"])
        if hi <= cursor:
            continue
        if lo > cursor or row["status"] != "DECLARED_COMPLETE" or row["evidenceHash"] is None:
            return False
        cursor = max(cursor, hi)
        if cursor >= end:
            return True
    return False


def quote_fill(state, events, quote, group, refs):
    p, scale = state["profile"], state["profile"]["moneyScale"]
    rate, contract = Fraction(p["commissionPerLotSide"]), Fraction(p["contractSize"])
    for order_id, order in state["orders"].items():
        if order["status"] not in ("PENDING", "ACTIVE") or int(quote["timeNs"]) < int(order["availableNs"]):
            continue
        evidence = dict(groupId=group["groupId"], timeNs=group["timeNs"], order=group["order"],
                        eventIds=refs, quote=deepcopy(quote) if len(refs) == 1 else None,
                        bid=quote["bid"], ask=quote["ask"], chronologyLimited=group["order"] == "UNTRUSTED" and len(group["events"]) > 1)
        if order["status"] == "PENDING" and crossing(order, quote):
            transaction = Fraction(quote["ask"] if order["side"] == "LONG" else quote["bid"])
            size = Fraction(order["quantity"])
            cost = money(size*rate, scale)
            order.update(status="ACTIVE", entryPrice=text(transaction), entryCost=cost)
            state["commission"] = text(Fraction(state["commission"])+Fraction(cost))
            state["balance"] = text(Fraction(state["balance"])-Fraction(cost))
            state["financial"] = True
            order["entryFillRef"] = emit(state, events, "ENTRY_FILL", order_id=order_id, classification="SIMULATED_FILL",
                price=text(transaction), quantity=text(size), commission=cost, balanceDelta=text(-Fraction(cost)),
                evidence=evidence, executionModel="QUOTE_BASELINE_NOT_BROKER_FILL")
        if order["status"] != "ACTIVE":
            continue
        reason = protective(order, quote)
        manual = order["exitRequest"]
        if reason is None and manual is not None and int(quote["timeNs"]) >= int(manual["availableNs"]):
            reason = "MANUAL"
        if reason is None:
            continue
        size = Fraction(manual["quantity"]) if reason == "MANUAL" else Fraction(order["remaining"])
        exit_price = Fraction(quote["bid"] if order["side"] == "LONG" else quote["ask"])
        direction = 1 if order["side"] == "LONG" else -1
        gross_exact = direction * (exit_price-Fraction(order["entryPrice"]))*contract*size
        gross, cost = money(gross_exact, scale), money(size*rate, scale)
        allocated = Fraction(order["entryCost"])*size/Fraction(order["quantity"])
        remaining = Fraction(order["remaining"])-size
        order.update(remaining=text(remaining), status="CLOSED" if remaining == 0 else "ACTIVE", exitRequest=None)
        delta = Fraction(gross)-Fraction(cost)
        state["realizedGross"] = text(Fraction(state["realizedGross"])+Fraction(gross))
        state["commission"] = text(Fraction(state["commission"])+Fraction(cost))
        state["balance"] = text(Fraction(state["balance"])+delta)
        state["financial"] = True
        emit(state, events, "EXIT_FILL", order_id=order_id, classification="SIMULATED_FILL", price=text(exit_price),
             quantity=text(size), remaining=text(remaining), reason=reason, gross=gross, commission=cost,
             entryFillRef=order["entryFillRef"], entryCostAllocationExact={"numerator":str(allocated.numerator),"denominator":str(allocated.denominator)},
             netRealized=money(gross_exact-allocated-Fraction(cost), scale),
             netIsDerived=True, balanceDelta=text(delta), evidence=evidence,
             executionModel="QUOTE_BASELINE_NOT_BROKER_FILL")


def advance(state, groups, coverage, diagnostics, through_ns):
    """Only controller-acknowledged, causally clipped inputs; no EOF parameter."""
    validate_state(state)
    state, events = deepcopy(state), []
    through = uint(through_ns)
    require(through >= int(state["throughNs"]), "advance", "REFUSED_BACKWARD_ADVANCE")
    require(type(groups) is list and len(groups) <= 64, "groups", "REFUSED_REVEAL_LIMIT")
    require(type(coverage) is list and len(coverage) <= 2048, "coverage")
    for c in coverage:
        keys(c, "startNs endNs status evidenceHash")
        require(int(state["throughNs"]) <= uint(c["startNs"]) < uint(c["endNs"]) <= through,
                "coverage", "REFUSED_FUTURE_EVIDENCE")
        require(c["status"] in ("DECLARED_COMPLETE", "INCOMPLETE", "UNKNOWN"), "coverage")
        if c["evidenceHash"] is not None:
            digest(c["evidenceHash"], "coverageHash")
    keys(diagnostics, "records counts truncated")
    require(type(diagnostics["records"]) is list and len(diagnostics["records"]) <= 128 and diagnostics["truncated"] is False, "diagnostics")
    require(all(int(state["throughNs"]) <= uint(d["timeNs"]) <= through for d in diagnostics["records"]),
            "diagnostics", "REFUSED_FUTURE_EVIDENCE")
    previous = int(state["throughNs"])
    for index, group in enumerate(groups):
        keys(group, "groupId timeNs order events")
        moment = uint(group["timeNs"])
        require(previous <= moment <= through and (index == 0 or previous < moment), "groupTime", "REFUSED_FUTURE_EVIDENCE")
        require(index != 0 or state["nextGroupIndex"] == "0" or moment > previous,
                "groupFence", "REFUSED_REPEATED_GROUP")
        require(type(group["events"]) is list and 0 < len(group["events"]) <= 1024, "atomicGroup")
        rows = [CanonicalTick.from_wire(r).wire for r in group["events"]]
        require(all(r["timeNs"] == group["timeNs"] and r["datasetId"] == state["datasetId"] and
                    r["datasetVersion"] == state["datasetVersion"] and
                    r["providerId"] == state["profile"]["providerId"] and r["feedId"] == state["profile"]["feedId"] and
                    r["instrumentId"] == state["profile"]["feedInstrumentId"] for r in rows), "groupIdentity", "REFUSED_DATASET_MISMATCH")
        require(make_group(rows, state["datasetVersion"]) == group, "atomicGroup", "REFUSED_GROUP_IDENTITY")
        if group["order"] == "TRUSTED_SEQUENCE":
            sequences = [int(r["trustedSequence"]) for r in rows]
            require(sequences == sorted(set(sequences)), "sequence", "REFUSED_GROUP_ORDER")
        active = live(state) and not state["unresolved"] and not state["ended"]
        if active and not coverage_complete(coverage, previous, moment):
            unresolved(state, events, "UNRESOLVED_COVERAGE", dict(throughNs=group["timeNs"]))
        elif active and any(int(d["timeNs"]) <= moment for d in diagnostics["records"]):
            unresolved(state, events, "UNRESOLVED_DIAGNOSTIC", dict(throughNs=group["timeNs"]))
        elif active:
            bad = any(r["quality"]["quote"] != "VALID" or r["quality"]["freshness"] != "CONFIRMED" or
                      r["quality"]["gapBefore"] not in ("NONE", "KNOWN_SESSION_CLOSED") or
                      r["quality"]["evidenceHash"] is None or r["quality"]["duplicateOf"] is not None for r in rows)
            if bad:
                unresolved(state, events, "UNRESOLVED_QUOTE_QUALITY", dict(groupId=group["groupId"], timeNs=group["timeNs"]))
            else:
                try:
                    for row in rows:
                        price(row["bid"], state["profile"]); price(row["ask"], state["profile"])
                except ContractError:
                    unresolved(state, events, "UNRESOLVED_QUOTE_PRECISION", dict(groupId=group["groupId"]))
                if not state["unresolved"]:
                    equivalent = len({(r["bid"], r["ask"]) for r in rows}) == 1
                    if group["order"] == "UNTRUSTED" and len(rows) > 1:
                        before = len(events)
                        if equivalent:
                            quote_fill(state, events, rows[0], group, sorted(r["eventId"] for r in rows))
                        elif any(can_change(state, r) for r in rows):
                            unresolved(state, events, "UNRESOLVED_EQUAL_TIME_ORDER", dict(groupId=group["groupId"], timeNs=group["timeNs"]))
                        # No financial action is a proven common outcome; no row is selected as chronology.
                        if len(events) == before:
                            emit(state, events, "CHRONOLOGY_LIMITATION", groupId=group["groupId"],
                                 timeNs=group["timeNs"], commonOutcome="NO_FINANCIAL_ACTION")
                    else:
                        for row in rows:
                            quote_fill(state, events, row, group, [row["eventId"]])
        previous = moment
        state["throughNs"] = group["timeNs"]
        state["nextGroupIndex"] = str(int(state["nextGroupIndex"])+1)
    if live(state) and not state["unresolved"] and not state["ended"]:
        if not coverage_complete(coverage, previous, through):
            unresolved(state, events, "UNRESOLVED_COVERAGE", dict(throughNs=through_ns))
        elif any(previous < int(d["timeNs"]) <= through for d in diagnostics["records"]):
            unresolved(state, events, "UNRESOLVED_DIAGNOSTIC", dict(throughNs=through_ns))
    state["throughNs"] = through_ns
    validate_state(state)
    return state, events
