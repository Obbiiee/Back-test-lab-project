"""Existing PostgreSQL transaction boundary; no public API or hidden market data."""
from copy import deepcopy
import hashlib
import json

from psycopg import sql
from application.models import TrustedScope
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, identifier, revision
from infrastructure.database import connect
from .contracts import MAX_EVENTS, command_wire, validate_state
from .engine import emit


def pack(value):
    raw = canonical_bytes(value)
    return raw, hashlib.sha256(raw).hexdigest()


def unpack(raw, expected):
    raw = bytes(raw)
    require(len(raw) <= 1048576 and hashlib.sha256(raw).hexdigest() == expected, "record", "CORRUPT_RECORD")
    value = json.loads(raw)
    require(canonical_bytes(value) == raw, "record", "CORRUPT_RECORD")
    return value


def snapshot(state, checkpoint):
    validate_state(state)
    require(checkpoint["cursor"]["throughNs"] == state["throughNs"] and
            checkpoint["cursor"]["nextGroupIndex"] == state["nextGroupIndex"] and
            checkpoint["cursor"]["datasetId"] == state["datasetId"] and
            checkpoint["cursor"]["datasetVersion"] == state["datasetVersion"], "checkpoint", "CORRUPT_RECORD")
    return dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-CHECKPOINT-1", state=state, controller=checkpoint)


def scoped(scope, session_id):
    require(type(scope) is TrustedScope, "scope", "SCOPE_REQUIRED")
    identifier(session_id, "sessionId")
    return scope.workspace_id, session_id


class PostgresExecutionStore:
    """One connection/row lock per bounded local command; not public composition."""
    def __init__(self, dsn):
        self.dsn = dsn

    def _insert(self, db, scope, state, checkpoint):
        workspace, session = scoped(scope, state["sessionId"])
        raw, sha = pack(snapshot(state, checkpoint))
        db.execute("INSERT INTO btl.tick_sessions VALUES (%s,%s,%s,%s,%s,%s,%s)",
                   (workspace, session, state["datasetVersion"], state["profileHash"], state["revision"], raw, sha))
        db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",
                   (workspace, session, state["revision"], raw, sha))

    def create(self, scope, state, checkpoint):
        with connect(self.dsn) as db:
            self._insert(db, scope, state, checkpoint)

    def run(self, scope, raw_command, operation):
        command = command_wire(raw_command)
        workspace, session = scoped(scope, command["sessionId"])
        command_hash = content_hash(command)
        with connect(self.dsn) as db:
            row = db.execute("SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s FOR UPDATE",
                             (workspace, session)).fetchone()
            require(row is not None, "session", "RESOURCE_UNAVAILABLE")
            stored = unpack(row[0], row[1])
            state, checkpoint = stored["state"], stored["controller"]
            snapshot(state, checkpoint)
            require((state["revision"], state["datasetVersion"], state["profileHash"]) == tuple(row[2:]), "state", "CORRUPT_RECORD")
            prior = db.execute("SELECT command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                               (workspace, session, command["commandId"])).fetchone()
            if prior:
                require(prior[0] == command_hash, "commandId", "REFUSED_IDEMPOTENCY_CONFLICT")
                return unpack(prior[1], prior[2])
            require(command["expectedRevision"] == state["revision"], "revision", "REFUSED_STALE_REVISION")
            next_state, next_checkpoint, events, replay = operation(deepcopy(state), deepcopy(checkpoint))
            require(len(events) <= MAX_EVENTS, "events", "REFUSED_EVENT_LIMIT")
            require(next_state["revision"] == state["revision"] and
                    (next_state["sessionId"], next_state["datasetVersion"], next_state["profileHash"]) ==
                    (state["sessionId"], state["datasetVersion"], state["profileHash"]), "stateTransition")
            previous_hash, sequence = state["eventHash"], state["nextEventIndex"]
            for event in events:
                value = {k:v for k,v in event.items() if k != "eventId"}
                require(event["sequence"] == sequence and event["previousHash"] == previous_hash and
                        event["eventId"] == content_hash(value) and event["sessionId"] == session, "eventChain", "CORRUPT_RECORD")
                previous_hash, sequence = event["eventId"], sequence+1
            require(next_state["eventHash"] == previous_hash and next_state["nextEventIndex"] == sequence, "eventHead", "CORRUPT_RECORD")
            next_state["revision"] += 1
            state_raw, state_hash = pack(snapshot(next_state, next_checkpoint))
            result = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-RESULT-1", commandId=command["commandId"],
                          commandHash=command_hash, state=next_state, events=events, replay=replay,
                          durable=True, model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION")
            result_raw, result_hash = pack(result)
            db.execute("INSERT INTO btl.tick_commands VALUES (%s,%s,%s,%s,%s,%s,%s)",
                       (workspace, session, command["commandId"], next_state["revision"], command_hash, result_raw, result_hash))
            for event in events:
                event_raw, event_hash = pack(event)
                db.execute("INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           (workspace, session, command["commandId"], event["eventId"], event["sequence"], event_raw, event_hash))
            db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",
                       (workspace, session, next_state["revision"], state_raw, state_hash))
            db.execute("UPDATE btl.tick_sessions SET revision=%s,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s",
                       (next_state["revision"], state_raw, state_hash, workspace, session))
        # Publication follows successful COMMIT; an after-commit crash is handled by durable dedup.
        return deepcopy(result)

    def inspect(self, scope, session_id, after_sequence=0, maximum=64):
        workspace, session = scoped(scope, session_id)
        revision(after_sequence)
        require(type(maximum) is int and 1 <= maximum <= 256, "maximum")
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            row = db.execute("SELECT payload,content_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s", (workspace,session)).fetchone()
            require(row is not None, "session", "RESOURCE_UNAVAILABLE")
            state = unpack(*row)["state"]
            validate_state(state)
            rows = db.execute("SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence >= %s ORDER BY sequence LIMIT %s",
                              (workspace,session,after_sequence,maximum)).fetchall()
            # Controller checkpoint/schedules are intentionally not projected.
            return {"state":state,"events":[unpack(*row) for row in rows]}

    def fork(self, scope, raw_command):
        command = command_wire(raw_command)
        require(command["kind"] == "FORK", "kind")
        workspace, child_session = scoped(scope, command["sessionId"])
        parent_session, parent_revision = command["payload"]["parentSessionId"], command["payload"]["parentRevision"]
        command_hash = content_hash(command)
        require(child_session != parent_session, "fork", "REFUSED_FORK_IDENTITY")
        with connect(self.dsn) as db:
            lock_key = int(content_hash(dict(schemaVersion=1, artifact="BTL-TICK-CREATE-LOCK-1", workspaceId=workspace, sessionId=child_session))[:16],16)
            if lock_key >= 2**63:
                lock_key -= 2**64
            db.execute("SELECT pg_advisory_xact_lock(%s)",(lock_key,))
            prior = db.execute("SELECT command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                               (workspace,child_session,command["commandId"])).fetchone()
            if prior:
                require(prior[0] == command_hash, "commandId", "REFUSED_IDEMPOTENCY_CONFLICT")
                return unpack(prior[1],prior[2])
            require(command["expectedRevision"] == 0, "revision", "REFUSED_STALE_REVISION")
            require(db.execute("SELECT 1 FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s",(workspace,child_session)).fetchone() is None,
                    "childSession", "REFUSED_FORK_IDENTITY")
            row = db.execute("SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s", (workspace,parent_session,parent_revision)).fetchone()
            require(row is not None, "forkPoint", "REFUSED_FORK_POINT")
            stored = unpack(*row)
            state, checkpoint = stored["state"], stored["controller"]
            snapshot(state, checkpoint)
            require(not state["unresolved"] and not state["ended"], "forkPoint", "REFUSED_FORK_POINT")
            parent = dict(sessionId=parent_session, revision=parent_revision, checkpointHash=row[1], eventHash=state["eventHash"], timeNs=state["throughNs"])
            state.update(sessionId=child_session, revision=0, nextEventIndex=0, parent=parent,
                         eventHash=content_hash(dict(schemaVersion=1, artifact="BTL-TICK-FORK-SEED-1", parent=parent, childSessionId=child_session)))
            self._insert(db, scope, state, checkpoint)
            events = []
            emit(state,events,"SESSION_FORKED",classification="ACCEPTED_COMMAND",parent=parent)
            state["revision"] = 1
            state_raw, state_hash = pack(snapshot(state,checkpoint))
            result = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-RESULT-1", commandId=command["commandId"],
                          commandHash=command_hash, state=state, events=events, replay=None, durable=True,
                          model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION")
            result_raw, result_hash = pack(result)
            db.execute("INSERT INTO btl.tick_commands VALUES (%s,%s,%s,%s,%s,%s,%s)",
                       (workspace,child_session,command["commandId"],1,command_hash,result_raw,result_hash))
            for event in events:
                event_raw,event_hash=pack(event)
                db.execute("INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           (workspace,child_session,command["commandId"],event["eventId"],event["sequence"],event_raw,event_hash))
            db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",(workspace,child_session,1,state_raw,state_hash))
            db.execute("UPDATE btl.tick_sessions SET revision=1,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s",(state_raw,state_hash,workspace,child_session))
        return deepcopy(result)


def grant_execution_runtime(dsn, role):
    """Explicit operator action; no automatic role creation or credentials."""
    with connect(dsn) as db:
        db.execute(sql.SQL("GRANT USAGE ON SCHEMA btl TO {}").format(sql.Identifier(role)))
        db.execute(sql.SQL("GRANT SELECT,INSERT ON btl.tick_sessions,btl.tick_commands,btl.tick_events,btl.tick_checkpoints TO {}").format(sql.Identifier(role)))
        db.execute(sql.SQL("GRANT UPDATE(revision,payload,content_hash) ON btl.tick_sessions TO {}").format(sql.Identifier(role)))
