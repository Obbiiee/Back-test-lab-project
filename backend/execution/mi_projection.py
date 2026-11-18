"""Read-only Journal and Analytics views for the isolated MI reducer.

This module consumes a complete committed MI event ledger plus its validated
state. It never has provider/tick access and cannot execute or settle orders.
It is not routed through Product/API storage yet.
"""
from collections import defaultdict
from fractions import Fraction

from contracts.canonical import content_hash
from contracts.primitives import require

from .analysis import metrics
from .contracts import text
from . import mi_kernel


ARTIFACT = "BTL-MI-COMMITTED-PROJECTION-1"


def project(state, events):
    """Verify the full MI chain and return symbol/Method-attributed views."""
    mi_kernel.validate_state(state)
    require(type(events) is list and len(events) == state["nextEventIndex"],
            "miProjection", "REFUSED_INCOMPLETE_EVENT_LEDGER")

    method_ids = set(state["methods"])
    method_hashes = {wire["definitionHash"] for wire in state["methods"].values()}
    previous = mi_kernel.seed_hash(state)
    accepted = {}
    accepted_sequence = {}
    fills = defaultdict(list)
    for sequence, event in enumerate(events):
        require(type(event) is dict and event.get("sequence") == sequence and
                event.get("previousHash") == previous and
                event.get("eventId") == content_hash({k: v for k, v in event.items() if k != "eventId"}) and
                event.get("sessionId") == state["sessionId"] and
                event.get("profileSetHash") == state["profileSetHash"] and
                event.get("engineVersion") == state["engineVersion"] and
                event.get("methodHash") in method_hashes,
                "miProjectionEvent", "CORRUPT_RECORD")
        previous = event["eventId"]
        kind, order_id = event["kind"], event["orderId"]
        require(type(kind) is str and (order_id is None or type(order_id) is str) and
                type(event.get("detail")) is dict,
                "miProjectionEvent", "CORRUPT_RECORD")
        if kind == "ORDER_ACCEPTED":
            order = state["orders"].get(order_id)
            require(order is not None and order_id not in accepted and
                    event.get("symbol") == order["symbol"] and
                    event["detail"].get("methodId") == order["methodId"] and
                    order["methodId"] in method_ids,
                    "miProjectionOrder", "CORRUPT_RECORD")
            plan = event["detail"].get("plan")
            require(type(plan) is dict and all(plan.get(key) == order.get(key) for key in
                    ("symbol", "methodId", "side", "orderType", "workflow", "entry", "quantity", "sl", "tp", "riskPercent", "observations")),
                    "miProjectionPlan", "CORRUPT_RECORD")
            accepted[order_id] = event
            accepted_sequence[order_id] = sequence
        elif kind in ("ENTRY_FILL", "EXIT_FILL"):
            require(order_id in accepted and event.get("symbol") == accepted[order_id]["symbol"] and
                    event.get("classification") == "SIMULATED_FILL" and
                    type(event.get("detail")) is dict and
                    type(event["detail"].get("primaryEvidence")) is dict and
                    int(event["detail"]["primaryEvidence"]["timeNs"]) <= int(state["throughNs"]),
                    "miProjectionFill", "CORRUPT_RECORD")
            fills[order_id].append(event)

    require(previous == state["eventHash"] and set(accepted) == set(state["orders"]),
            "miProjectionHead", "CORRUPT_RECORD")

    orders, completed = [], []
    for order_id in sorted(accepted, key=lambda key: accepted_sequence[key]):
        order = state["orders"][order_id]
        order_fills = fills[order_id]
        entries = [event for event in order_fills if event["kind"] == "ENTRY_FILL"]
        exits = [event for event in order_fills if event["kind"] == "EXIT_FILL"]
        require(len(entries) <= 1 and (order["entryFillRef"] is None) == (len(entries) == 0) and
                (not entries or entries[0]["eventId"] == order["entryFillRef"]),
                "miProjectionEntry", "CORRUPT_RECORD")
        if entries:
            detail = entries[0]["detail"]
            require(detail["price"] == order["entryPrice"] and detail["quantity"] == order["quantity"] and
                    detail["commissionPosted"] == order["entryCostPosted"],
                    "miProjectionEntry", "CORRUPT_RECORD")
        prior_remaining = Fraction(order["quantity"])
        for event in exits:
            detail = event["detail"]
            prior_remaining -= Fraction(detail["quantity"])
            require(prior_remaining >= 0 and detail["remaining"] == text(prior_remaining),
                    "miProjectionExit", "CORRUPT_RECORD")
        require((not exits or prior_remaining == Fraction(order["remaining"])) and
                (order["status"] == "CLOSED") == (Fraction(order["remaining"]) == 0 and bool(entries)),
                "miProjectionExit", "CORRUPT_RECORD")
        require(sum((Fraction(event["detail"]["grossPosted"]) for event in exits), Fraction()) ==
                Fraction(order["grossPosted"]) and
                sum((Fraction(event["detail"]["commissionPosted"]) for event in exits), Fraction()) ==
                Fraction(order["exitCostPosted"]), "miProjectionExit", "CORRUPT_RECORD")
        entry_time = entries[0]["detail"]["primaryEvidence"]["timeNs"] if entries else None
        exit_time = exits[-1]["detail"]["primaryEvidence"]["timeNs"] if exits else None
        exit_slices = [{"eventId": event["eventId"], "timeNs": event["detail"]["primaryEvidence"]["timeNs"],
                        "price": event["detail"]["price"], "quantity": event["detail"]["quantity"],
                        "gross": event["detail"]["grossPosted"], "commission": event["detail"]["commissionPosted"],
                        "reason": event["detail"]["reason"]} for event in exits]
        net = Fraction(order["grossPosted"]) - Fraction(order["entryCostPosted"]) - Fraction(order["exitCostPosted"])
        row = dict(id=order_id, symbol=order["symbol"], methodId=order["methodId"], side=order["side"],
                   orderType=order["orderType"], workflow=order["workflow"], status=order["status"],
                   entry=order["entry"], quantity=order["quantity"], remaining=order["remaining"],
                   entryPrice=order["entryPrice"], entryTimeNs=entry_time, entryFillRef=order["entryFillRef"],
                   exitSlices=exit_slices, exitTimeNs=exit_time, gross=order["grossPosted"],
                   commission=text(Fraction(order["entryCostPosted"]) + Fraction(order["exitCostPosted"])),
                   net=text(net), rMultiple=None, rReason="PREENTRY_R0_NOT_PINNED",
                   durationNs=None if entry_time is None or exit_time is None else str(int(exit_time) - int(entry_time)))
        orders.append(row)
        if order["status"] == "CLOSED":
            require(entry_time is not None and exit_time is not None and Fraction(order["remaining"]) == 0,
                    "miProjectionClosed", "CORRUPT_RECORD")
            completed.append(row)

    def grouped(field):
        groups = defaultdict(list)
        for row in completed:
            groups[row[field]].append(row)
        return {key: dict(closedTrades=len(rows), netCashChange=text(sum((Fraction(row["net"]) for row in rows), Fraction())),
                          metrics=metrics(rows)) for key, rows in sorted(groups.items())}

    account = dict(balance=state["balance"], realizedGross=state["realizedGross"], commission=state["commission"],
                   equity=mi_kernel.equity(state))
    return dict(schemaVersion=1, artifact=ARTIFACT, status="COMPLETE", sessionId=state["sessionId"],
                revision=state["revision"], orders=orders, completed=completed, metrics=metrics(completed),
                byPair=grouped("symbol"), byMethod=grouped("methodId"), account=account,
                provenance=dict(engineVersion=state["engineVersion"], profileSetHash=state["profileSetHash"],
                                eventHead=state["eventHash"], throughNs=state["throughNs"],
                                financialAuthority="VERIFIED_COMMITTED_MI_EVENTS_ONLY"))
