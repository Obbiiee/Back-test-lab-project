"""Immutable MI terminal order projection over the shared order archive."""
from fractions import Fraction

from contracts.primitives import require
from .contracts import text

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
        if "archived" in after:
            totals = after["archived"]
            require(totals["count"] == index and totals["head"] == record["previousHash"],
                    "miArchiveTip", "CORRUPT_RECORD")
            totals["count"] += 1
            totals["head"] = previous
            totals["filled"] += int(order["entryFillRef"] is not None)
            totals["gross"] = text(Fraction(totals["gross"]) + Fraction(order["grossPosted"]))
            totals["fees"] = text(Fraction(totals["fees"]) + Fraction(order["entryCostPosted"]) +
                                  Fraction(order["exitCostPosted"]))
            del after["orders"][key]
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
                (value["order"] == state["orders"].get(value["orderId"]) if "archived" not in state
                 else value["orderId"] not in state["orders"]) and
                value["finalizedRevision"] <= state["revision"], "miArchiveRecord", "CORRUPT_RECORD")
        previous = value["recordHash"]
        items.append(value)
    return dict(schemaVersion=1, artifact="BTL-MI-TERMINAL-ORDER-PAGE-1",
                revision=state["revision"], orders=items,
                nextAfterSequence=items[-1]["sequence"] if len(rows) > limit else None)


def summary(db, workspace, session, state):
    """Stream terminal records under the pinned revision, with fixed-size accumulators."""
    from .analysis import ratio

    totals = [0, 0, Fraction(), Fraction()]
    buckets = {key: {} for key in ("symbol", "methodId")}
    overall = [0, 0, 0, Fraction()]
    previous = archive.GENESIS

    def add(bucket, net):
        bucket[0] += 1
        bucket[1] += int(net > 0)
        bucket[2] += int(net < 0)
        bucket[3] += net

    def result(bucket):
        count, wins, losses, net = bucket
        return dict(tradeCount=count, wins=wins, losses=losses,
                    breakeven=count - wins - losses, netCashChange=text(net),
                    winRate=ratio(Fraction(wins, count)) if count else None)

    with db.cursor(name="mi_terminal_analytics") as cursor:
        cursor.itersize = 64
        cursor.execute(
            "SELECT sequence,order_id,terminal_status,finalized_revision,record_hash,payload,content_hash "
            "FROM btl.tick_terminal_orders WHERE workspace_id=%s AND session_id=%s ORDER BY sequence",
            (workspace, session))
        for row in cursor:
            value = archive.verify(unpack(*row[5:]), session_id=session, sequence=totals[0],
                                   previous_hash=previous)
            order = value["order"]
            require(tuple(row[:5]) == (value["sequence"], value["orderId"], order["status"],
                                        value["finalizedRevision"], value["recordHash"]) and
                    value["finalizedRevision"] <= state["revision"] and
                    value["orderId"] not in state["orders"] and order["methodId"] in state["methods"] and
                    order["symbol"] in state["groups"], "miArchiveRecord", "CORRUPT_RECORD")
            totals[0] += 1
            totals[1] += int(order["entryFillRef"] is not None)
            gross = Fraction(order["grossPosted"])
            fees = Fraction(order["entryCostPosted"]) + Fraction(order["exitCostPosted"])
            totals[2] += gross
            totals[3] += fees
            previous = value["recordHash"]
            if order["status"] == "CLOSED":
                net = gross - fees
                add(overall, net)
                for key, groups in buckets.items():
                    add(groups.setdefault(order[key], [0, 0, 0, Fraction()]), net)

    expected = state["archived"]
    require((totals[0], totals[1], text(totals[2]), text(totals[3]), previous) ==
            (expected["count"], expected["filled"], expected["gross"], expected["fees"], expected["head"]),
            "miAnalyticsArchive", "CORRUPT_RECORD")
    return dict(schemaVersion=1, artifact="BTL-MI-DURABLE-ANALYTICS-1", sessionId=session,
                revision=state["revision"], eventHead=state["eventHash"], metrics=result(overall),
                byPair={key: result(value) for key, value in buckets["symbol"].items()},
                byMethod={key: result(value) for key, value in buckets["methodId"].items()},
                account={key: state[key] for key in ("balance", "commission", "realizedGross")})
