"""Immutable MI terminal order projection over the shared order archive."""
from contracts.primitives import require

from . import terminal_order_archive as archive
from .postgres import pack, unpack


def append(db, workspace, session, before, after, events):
    finalized = [(key, order) for key, order in after["orders"].items()
                 if order["status"] in archive.TERMINAL and
                 before["orders"].get(key, {}).get("status") not in archive.TERMINAL]
    if not finalized:
        return
    last = db.execute(
        "SELECT sequence,record_hash FROM btl.tick_terminal_orders WHERE workspace_id=%s "
        "AND session_id=%s ORDER BY sequence DESC LIMIT 1", (workspace, session)).fetchone()
    index, previous = (-1, archive.GENESIS) if last is None else last
    for key, order in finalized:
        evidence = [event for event in events if event["orderId"] == key or
                    (event["kind"] == "UNRESOLVED" and key in event["detail"]["affectedOrderIds"])]
        require(evidence, "miArchiveEvidence", "CORRUPT_RECORD")
        index += 1
        record = archive.record(session_id=session, sequence=index, revision=after["revision"],
                                order_id=key, order=order, events=evidence, previous_hash=previous)
        previous = record["recordHash"]
        blob, sha = pack(record)
        db.execute("INSERT INTO btl.tick_terminal_orders VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                   (workspace, session, index, key, order["status"], after["revision"],
                    previous, blob, sha))


def page(db, workspace, session, state, after, limit):
    previous = archive.GENESIS
    if after >= 0:
        anchor = db.execute(
            "SELECT payload,content_hash,record_hash FROM btl.tick_terminal_orders "
            "WHERE workspace_id=%s AND session_id=%s AND sequence=%s",
            (workspace, session, after)).fetchone()
        require(anchor is not None, "cursor", "INVALID_CURSOR")
        value = archive.verify(unpack(*anchor[:2]), session_id=session, sequence=after)
        require(value["recordHash"] == anchor[2], "miArchiveAnchor", "CORRUPT_RECORD")
        previous = value["recordHash"]
    rows = db.execute(
        "SELECT sequence,order_id,terminal_status,finalized_revision,record_hash,payload,content_hash "
        "FROM btl.tick_terminal_orders WHERE workspace_id=%s AND session_id=%s AND sequence>%s "
        "ORDER BY sequence LIMIT %s", (workspace, session, after, limit + 1)).fetchall()
    items = []
    for offset, row in enumerate(rows[:limit], start=after + 1):
        value = archive.verify(unpack(*row[5:]), session_id=session, sequence=offset,
                               previous_hash=previous)
        require((value["sequence"], value["orderId"], value["order"]["status"],
                 value["finalizedRevision"], value["recordHash"]) == tuple(row[:5]) and
                value["order"] == state["orders"].get(value["orderId"]) and
                value["finalizedRevision"] <= state["revision"], "miArchiveRecord", "CORRUPT_RECORD")
        previous = value["recordHash"]
        items.append(value)
    return dict(schemaVersion=1, artifact="BTL-MI-TERMINAL-ORDER-PAGE-1",
                revision=state["revision"], orders=items,
                nextAfterSequence=items[-1]["sequence"] if len(rows) > limit else None)
