"""Versioned, append-only archive projection for terminal tick orders.

Financial events remain the authority. This compact index records the final
order state and the event IDs emitted on the command that finalized it.
"""
from copy import deepcopy

from contracts.canonical import content_hash, canonical_bytes
from contracts.primitives import require, identifier

ARTIFACT = "BTL-TICK-TERMINAL-ORDER-ARCHIVE-1"
GENESIS = content_hash({"schemaVersion": 1, "artifact": ARTIFACT + "-GENESIS"})
TERMINAL = {"CANCELLED", "CLOSED", "EXPIRED", "UNRESOLVED"}


def terminal_orders(before, after, events):
    """Build terminal final states from the validated transition and events."""
    orders = deepcopy(before["orders"])
    lifecycle = {order_id: [] for order_id in orders}
    for event in events:
        kind, order_id, detail = event["kind"], event["orderId"], event["detail"]
        if kind == "UNRESOLVED":
            for affected in detail["affectedOrderIds"]:
                if affected in orders:
                    orders[affected]["status"] = "UNRESOLVED"
                    orders[affected]["exitRequest"] = None
                    lifecycle[affected].append(deepcopy(event))
        if kind == "ORDER_ACCEPTED":
            require(order_id not in orders, "archiveOrder", "CORRUPT_RECORD")
            plan = deepcopy(detail["plan"])
            orders[order_id] = dict(plan, status="PENDING", availableNs=detail["availableNs"],
                remaining=plan["quantity"], entryPrice=None, entryFillRef=None,
                entryCost="0", exitRequest=None)
            lifecycle[order_id] = []
        if order_id in orders:
            lifecycle[order_id].append(deepcopy(event))
            order = orders[order_id]
            if kind == "ORDER_CANCELLED":
                order["status"] = "CANCELLED"
            elif kind == "EXPIRED_NO_QUOTE":
                order["status"] = "EXPIRED"
            elif kind == "EXIT_REQUESTED":
                order["exitRequest"] = deepcopy(detail["request"])
            elif kind == "ENTRY_FILL":
                order.update(status="ACTIVE", entryPrice=detail["price"],
                    entryFillRef=event["eventId"], entryCost=detail["commission"])
            elif kind == "EXIT_FILL":
                order.update(status="CLOSED" if detail["remaining"] == "0" else "ACTIVE",
                    remaining=detail["remaining"], exitRequest=None)

    finalized = {}
    for order_id, order in orders.items():
        if order_id not in after["orders"]:
            require(order["status"] in TERMINAL, "archiveTerminal", "CORRUPT_RECORD")
            finalized[order_id] = dict(order=deepcopy(order), events=lifecycle.get(order_id, []))
    # Every removed order must be accounted for; active state remains bounded.
    require(set(before["orders"]) - set(after["orders"]) <= set(finalized),
            "archiveMissing", "CORRUPT_RECORD")
    return finalized


def record(*, session_id, sequence, revision, order_id, order, events, previous_hash):
    identifier(session_id, "sessionId")
    identifier(order_id, "orderId")
    require(type(sequence) is int and sequence >= 0 and type(revision) is int and revision > 0,
            "archiveBinding", "CORRUPT_RECORD")
    require(order.get("status") in TERMINAL, "archiveTerminal", "CORRUPT_RECORD")
    value = dict(schemaVersion=1, formatVersion=1, artifact=ARTIFACT,
        sessionId=session_id, sequence=sequence, finalizedRevision=revision,
        orderId=order_id, previousHash=previous_hash, order=deepcopy(order),
        terminalEvents=deepcopy(events))
    value["orderHash"] = content_hash({"schemaVersion": 1, "artifact": ARTIFACT + "-ORDER", "order": order})
    value["recordHash"] = content_hash(value)
    return value


def verify(value, *, session_id=None, sequence=None, previous_hash=None):
    require(type(value) is dict and set(value) == {"schemaVersion", "formatVersion", "artifact",
        "sessionId", "sequence", "finalizedRevision", "orderId", "previousHash", "order",
        "terminalEvents", "orderHash", "recordHash"}, "archiveRecord", "CORRUPT_RECORD")
    require(value["schemaVersion"] == 1 and value["formatVersion"] == 1 and
        value["artifact"] == ARTIFACT and value["order"].get("status") in TERMINAL,
        "archiveVersion", "CORRUPT_RECORD")
    identifier(value["sessionId"], "sessionId"); identifier(value["orderId"], "orderId")
    require(type(value["sequence"]) is int and value["sequence"] >= 0 and
        type(value["finalizedRevision"]) is int and value["finalizedRevision"] > 0,
        "archiveBinding", "CORRUPT_RECORD")
    require(value["orderHash"] == content_hash({"schemaVersion": 1,
        "artifact": ARTIFACT + "-ORDER", "order": value["order"]}), "archiveOrderHash", "CORRUPT_RECORD")
    require(value["recordHash"] == content_hash({k: v for k, v in value.items() if k != "recordHash"}),
        "archiveHash", "CORRUPT_RECORD")
    if session_id is not None:
        require(value["sessionId"] == session_id, "archiveSession", "CORRUPT_RECORD")
    if sequence is not None:
        require(value["sequence"] == sequence, "archiveSequence", "CORRUPT_RECORD")
    if previous_hash is not None:
        require(value["previousHash"] == previous_hash, "archiveChain", "CORRUPT_RECORD")
    canonical_bytes(value)
    return value
