"""Bounded closed-trade SQL page selection with a keyset cursor path."""

from contracts.primitives import identifier, require


def closed_trade_rows(db, workspace_id, session_id, *, limit, offset, total,
                      cursor=None, event_count=None):
    require(type(limit) is int and 1 <= limit <= 64, "limit", "INVALID_INPUT")
    require(type(offset) is int and offset >= 0 and type(total) is int and total >= 0,
            "offset", "INVALID_CURSOR")
    if cursor is None:
        require(offset <= total, "offset", "INVALID_CURSOR")
        rows = db.execute(
            "SELECT last_sequence,order_id,payload,content_hash FROM btl.tick_journal_order_projection "
            "WHERE workspace_id=%s AND session_id=%s AND order_status='CLOSED' "
            'ORDER BY last_sequence,order_id COLLATE "C" OFFSET %s LIMIT %s',
            (workspace_id, session_id, offset, limit + 1),
        ).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        require(len(rows) == min(limit, total - offset),
                "analyticsOrderProjection", "CORRUPT_RECORD")
        return rows, more

    require(type(cursor) is tuple and len(cursor) == 2 and
            type(cursor[0]) is int and cursor[0] >= 0 and
            type(cursor[1]) is str and type(event_count) is int and
            0 <= cursor[0] < event_count,
            "cursor", "INVALID_CURSOR")
    after_sequence, after_order_id = cursor
    identifier(after_order_id, "afterOrderId")
    prior = db.execute(
        "SELECT order_id FROM btl.tick_journal_order_projection "
        "WHERE workspace_id=%s AND session_id=%s AND order_status='CLOSED' "
        'AND last_sequence=%s AND order_id=%s COLLATE "C"',
        (workspace_id, session_id, after_sequence, after_order_id),
    ).fetchone()
    require(prior is not None, "cursor", "INVALID_CURSOR")
    rows = db.execute(
        "SELECT last_sequence,order_id,payload,content_hash FROM btl.tick_journal_order_projection "
        "WHERE workspace_id=%s AND session_id=%s AND order_status='CLOSED' "
        'AND (last_sequence,order_id COLLATE "C")>(%s,%s::text COLLATE "C") '
        'ORDER BY last_sequence,order_id COLLATE "C" LIMIT %s',
        (workspace_id, session_id, after_sequence, after_order_id, limit + 1),
    ).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    require(len(rows) <= total, "analyticsOrderProjection", "CORRUPT_RECORD")
    return rows, more
