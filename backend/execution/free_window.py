"""Server-side Free research-window lookup for the jump orchestration (no request input, no financial contract involved).

Returns the exclusive end (ns) of the UTC month a Free account activated for a Session, or None when the Session has no entitlement claim (created before
enforcement or in development) or the account is Pro right now. Tier is derived from PAID, unexpired billing orders only. If the billing ledger cannot be
read, the account is treated as Free (the restrictive reading), never as Pro.
"""
import time

import psycopg


def free_window_end(db, workspace_id, session_id):
    row = db.execute("SELECT actor_id,window_end_ns FROM btl.entitlement_claims WHERE kind='SESSION' AND workspace_id=%s AND session_id=%s "
                     "AND status IN ('RESERVED','COMMITTED') LIMIT 1", (str(workspace_id), session_id)).fetchone()
    if row is None:
        return None
    actor_id, end_ns = row[0], int(row[1])
    now = int(time.time())
    try:
        with db.transaction():                                   # savepoint: an unreadable ledger must not poison the caller's transaction
            paid = db.execute("SELECT 1 FROM btl.sandbox_billing_orders WHERE actor_id=%s AND phase='PAID' AND paid_at<=%s AND expires_at>%s LIMIT 1",
                              (actor_id, now, now)).fetchone()
    except psycopg.errors.InsufficientPrivilege:
        paid = None
    return None if paid else end_ns
