"""Append-only audit events. Failure to record never changes the outcome of the audited request (best effort, logged), because the audit trail
must not become a new way to lose a user's work; it carries no payloads, secrets or financial values."""
import logging

from infrastructure.database import connect

log = logging.getLogger("btl.audit")


def record(dsn, actor_id, workspace_id, action, target=None, outcome="OK"):
    try:
        with connect(dsn) as db:
            db.execute("INSERT INTO btl.audit_events(actor_id,workspace_id,action,target,outcome) VALUES (%s,%s,%s,%s,%s)",
                       (str(actor_id), None if workspace_id is None else str(workspace_id), action, None if target is None else str(target)[:200], outcome))
    except Exception:                                                  # noqa: BLE001 - deliberately best effort
        log.exception("audit event not recorded: %s", action)
