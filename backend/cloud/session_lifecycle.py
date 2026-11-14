"""Trash and restore a Session on the default product path. Hides it from the Session list; never touches ticks, receipts, journal or analytics.
A trashed Session can be restored for RESTORE_DAYS. Permanent purge is intentionally NOT implemented (needs an owner retention/erasure decision)."""
from contracts.primitives import ContractError, require, identifier
from psycopg.rows import dict_row, tuple_row
from infrastructure.database import connect

RESTORE_DAYS = 30


def set_trashed(dsn, actor_id, workspace_id, session_id, trashed, *, scope):
    """scope(db, actor, workspace) must raise for a non-owner (same primitive the research routes use)."""
    identifier(session_id, "sessionId")
    require(type(trashed) is bool, "trashed", "INVALID_INPUT")
    with connect(dsn) as db:
        db.row_factory = dict_row
        scope(db, actor_id, workspace_id)
        db.row_factory = tuple_row
        row = db.execute("SELECT 1 FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s", (str(workspace_id), session_id)).fetchone()
        if row is None:
            raise ContractError("RESOURCE_UNAVAILABLE", "session")
        current = db.execute("SELECT trashed_at, clock_timestamp() > trashed_at + make_interval(days => %s) FROM btl.session_lifecycle "
                             "WHERE workspace_id=%s AND session_id=%s FOR UPDATE", (RESTORE_DAYS, str(workspace_id), session_id)).fetchone()
        if trashed:
            db.execute("INSERT INTO btl.session_lifecycle(workspace_id,session_id,trashed_at) VALUES (%s,%s,clock_timestamp()) "
                       "ON CONFLICT (workspace_id,session_id) DO UPDATE SET trashed_at=COALESCE(btl.session_lifecycle.trashed_at, clock_timestamp())",
                       (str(workspace_id), session_id))
        elif current is not None and current[0] is not None:
            if current[1]:
                raise ContractError("TRASH_EXPIRED", "restore")
            db.execute("UPDATE btl.session_lifecycle SET trashed_at=NULL WHERE workspace_id=%s AND session_id=%s", (str(workspace_id), session_id))
        return dict(schemaVersion=1, artifact="BTL-SESSION-LIFECYCLE-1", sessionId=session_id, trashed=trashed, restoreDays=RESTORE_DAYS)
