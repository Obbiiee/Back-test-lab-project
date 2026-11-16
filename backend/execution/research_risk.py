"""Indexed lookup of committed pre-entry risk pins for analytics projection."""


def fetch_review_pins(db, workspace_id, session_id, order_ids):
    """Return every matching accepted review without a lifetime order ceiling.

    The caller already holds a bounded database snapshot and supplies the
    committed order IDs from its event projection. This lookup must not impose
    the active-order limit on cumulative terminal history.
    """
    if not order_ids:
        return []
    return db.execute(
        'SELECT r.review_id,r.payload,r.content_hash,c.command_hash,c.revision '
        'FROM btl.tick_order_reviews r JOIN btl.tick_commands c '
        'ON r.workspace_id=c.workspace_id AND r.session_id=c.session_id AND r.review_id=c.command_id '
        'WHERE r.workspace_id=%s AND r.session_id=%s AND r.review_id=ANY(%s)',
        (workspace_id, session_id, order_ids),
    ).fetchall()
