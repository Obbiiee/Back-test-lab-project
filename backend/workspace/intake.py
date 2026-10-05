"""Verified membership + registered backtest + intake in ONE DB transaction."""
from psycopg.rows import dict_row, tuple_row
from application.models import TrustedScope
from contracts.primitives import require, ContractError
from infrastructure.database import connect
from infrastructure.postgres import PostgresUnit
from .store import WorkspaceUnit


class MembershipWorkflow:
    def __init__(self, dsn, actor_id, workspace_id, session_id):
        self.dsn, self.actor_id, self.workspace_id, self.session_id = dsn, actor_id, workspace_id, session_id

    def run(self, scope, session_id, operation):
        expected = TrustedScope(str(self.workspace_id), str(self.actor_id))
        require(type(scope) is TrustedScope and scope == expected and session_id == str(self.session_id), "scope", "SCOPE_MISMATCH")
        with connect(self.dsn) as db:
            db.row_factory = dict_row
            unit = WorkspaceUnit(db, self.actor_id, self.workspace_id)
            try:
                resource = unit.resource(self.session_id, write=True)
            except ContractError as error:
                if error.code == "WRITE_FORBIDDEN":
                    raise ContractError("RESOURCE_UNAVAILABLE", "session") from None
                raise
            require(resource["kind"] == "BACKTEST", "session", "RESOURCE_UNAVAILABLE")
            # Reuse the unchanged durable adapter, with the same connection and
            # held identity/membership/resource locks; never cache a naked scope.
            db.row_factory = tuple_row
            return operation(PostgresUnit(db, scope, session_id))
