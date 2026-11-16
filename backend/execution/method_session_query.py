"""Bounded keyset batches for Method analytics Session scans."""
from contracts.primitives import identifier, require

METHOD_ANALYTICS_BATCH_SIZE = 32


def method_session_batch(db, workspace_id, method_id, *, after=None):
    require(after is None or type(after) is str, 'afterSessionId', 'INVALID_CURSOR')
    if after is not None:
        identifier(after, 'afterSessionId')
    if after is None:
        rows = db.execute(
            'SELECT session_id,payload,content_hash FROM btl.tick_research_sessions '
            'WHERE workspace_id=%s AND method_id=%s '
            'ORDER BY session_id LIMIT %s',
            (workspace_id, method_id, METHOD_ANALYTICS_BATCH_SIZE + 1),
        ).fetchall()
    else:
        rows = db.execute(
            'SELECT session_id,payload,content_hash FROM btl.tick_research_sessions '
            'WHERE workspace_id=%s AND method_id=%s AND session_id>%s '
            'ORDER BY session_id LIMIT %s',
            (workspace_id, method_id, after, METHOD_ANALYTICS_BATCH_SIZE + 1),
        ).fetchall()
    more = len(rows) > METHOD_ANALYTICS_BATCH_SIZE
    return rows[:METHOD_ANALYTICS_BATCH_SIZE], more

