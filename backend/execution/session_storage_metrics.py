"""Read-only PostgreSQL row/payload accounting for one scoped Session.

These counters deliberately do not claim allocated table/index/TOAST/WAL bytes.
Canonical market data is shared and is not attributed to a Session.
"""
from contracts.primitives import identifier, require


_TABLES = (
    ("sessionState", "tick_sessions"),
    ("sessionMetadata", "tick_research_sessions"),
    ("sessionMetadataV2", "tick_v2_research_sessions"),
    ("commandsAndReceipts", "tick_commands"),
    ("events", "tick_events"),
    ("checkpoints", "tick_checkpoints"),
    ("reviews", "tick_order_reviews"),
    ("reviewsV2", "tick_v2_order_reviews"),
    ("journalNotes", "tick_journal_notes"),
    ("journalNotesV2", "tick_v2_journal_notes"),
)


def collect(db, workspace_id, session_id):
    """Return a stable snapshot of row and canonical payload sizes.

    Caller must already hold verified workspace membership. SQL identifiers
    come only from the static allowlist above; the supplied scope values remain
    parameters. One exact index-backed count/aggregate is made per table.
    """
    identifier(session_id, "sessionId")
    present = db.execute(
        "SELECT EXISTS(SELECT 1 FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s) "
        "AND (EXISTS(SELECT 1 FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s) "
        "OR EXISTS(SELECT 1 FROM btl.tick_v2_research_sessions WHERE workspace_id=%s AND session_id=%s)) "
        "AS session_found",
        (workspace_id, session_id, workspace_id, session_id, workspace_id, session_id),
    ).fetchone()["session_found"]
    require(present, "session", "RESOURCE_UNAVAILABLE")

    rows = {}
    for category, table in _TABLES:
        measured = db.execute(
            f"SELECT count(*) AS row_count,coalesce(sum(pg_column_size(t)),0) AS tuple_bytes,"
            f"coalesce(sum(octet_length(t.payload)),0) AS payload_bytes FROM btl.{table} AS t "
            "WHERE workspace_id=%s AND session_id=%s",
            (workspace_id, session_id),
        ).fetchone()
        count = measured["row_count"]
        tuple_bytes = measured["tuple_bytes"]
        payload_bytes = measured["payload_bytes"]
        rows[category] = {"rows": count, "tupleBytes": tuple_bytes, "payloadBytes": payload_bytes}

    return {
        "schemaVersion": 1,
        "artifact": "BTL-SESSION-STORAGE-METRICS-1",
        "workspaceId": str(workspace_id),
        "sessionId": session_id,
        "integrityStatus": "NOT_CHECKED_BY_STORAGE_METER",
        "measurementScope": "SESSION_ROWS_AND_CANONICAL_PAYLOAD_BYTES",
        "allocation": "NOT_PHYSICAL_TABLE_INDEX_TOAST_OR_WAL_ALLOCATION",
        "sharedCanonicalDatasetBytes": None,
        "perSessionWalBytes": None,
        "tables": rows,
        "totals": {
            "rows": sum(item["rows"] for item in rows.values()),
            "tupleBytes": sum(item["tupleBytes"] for item in rows.values()),
            "payloadBytes": sum(item["payloadBytes"] for item in rows.values()),
        },
        "tradeCount": None,
        "tradeCountStatus": "NOT_COMPUTED_FROM_STORAGE_COUNTERS",
    }
