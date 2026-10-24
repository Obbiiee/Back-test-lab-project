"""Additive synthetic v2 receipts on the existing opaque tick tables.

Old v1 code/migrations/rows are unchanged. TrustedScope remains controller-only;
this module is not verified HTTP membership or entitlement composition.
"""
from copy import deepcopy
from fractions import Fraction
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, identifier, revision
from ticks.contracts import tag
from infrastructure.database import connect
from .postgres import pack, unpack, scoped
from .kernel_v2 import MAX_EVENTS, command_wire, validate_state, validate_snapshot, emit
from .contracts import exact


def snapshot(state,checkpoint):
    return validate_snapshot(state,checkpoint)


def read_snapshot(raw,sha):
    stored=unpack(raw,sha)
    tag(stored,"BTL-TICK-EXECUTION-CHECKPOINT-2","state controller")
    snapshot(stored["state"],stored["controller"])
    return stored


def checked_result(result,session,command):
    tag(result,"BTL-TICK-EXECUTION-RESULT-2","commandId commandHash state events replay durable model")
    profile=result["state"].get("profile") if type(result["state"]) is dict else None
    require(result["durable"] is True and type(profile) is dict and result["model"]==profile.get("model")
            and result["commandId"]==command["commandId"] and result["commandHash"]==content_hash(command)
            and result["state"]["sessionId"]==session,"receipt","CORRUPT_RECORD")
    validate_state(result["state"])
    return result


class PostgresExecutionStoreV2:
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

    def prepare(self,scope,raw_command):
        """Read-only coherent basis/dedup; expensive source work happens afterwards."""
        command=command_wire(raw_command)
        workspace,session=scoped(scope,command["sessionId"])
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            row=db.execute("SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s",
                           (workspace,session)).fetchone()
            require(row is not None,"session","RESOURCE_UNAVAILABLE")
            stored=read_snapshot(row[0],row[1]);state=stored["state"]
            require((state["revision"],state["datasetVersion"],state["profileHash"])==tuple(row[2:]),"state","CORRUPT_RECORD")
            prior=db.execute("SELECT command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                             (workspace,session,command["commandId"])).fetchone()
            if prior:
                require(prior[0]==content_hash(command),"commandId","REFUSED_IDEMPOTENCY_CONFLICT")
                return stored,checked_result(unpack(prior[1],prior[2]),session,command)
            require(state["revision"]==command["expectedRevision"],"revision","REFUSED_STALE_REVISION")
            return stored,None

    def run(self, scope, raw_command, operation):
        command = command_wire(raw_command)
        workspace, session = scoped(scope, command["sessionId"])
        command_hash = content_hash(command)
        with connect(self.dsn) as db:
            row = db.execute("SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s FOR UPDATE",
                             (workspace, session)).fetchone()
            require(row is not None, "session", "RESOURCE_UNAVAILABLE")
            stored = read_snapshot(row[0], row[1])
            state, checkpoint = stored["state"], stored["controller"]
            snapshot(state, checkpoint)
            require((state["revision"], state["datasetVersion"], state["profileHash"]) == tuple(row[2:]), "state", "CORRUPT_RECORD")
            prior = db.execute("SELECT command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                               (workspace, session, command["commandId"])).fetchone()
            if prior:
                require(prior[0] == command_hash, "commandId", "REFUSED_IDEMPOTENCY_CONFLICT")
                return checked_result(unpack(prior[1], prior[2]), session, command)
            require(command["expectedRevision"] == state["revision"], "revision", "REFUSED_STALE_REVISION")
            next_state, next_checkpoint, events, replay = operation(deepcopy(state), deepcopy(checkpoint))
            require(len(events) <= MAX_EVENTS, "events", "REFUSED_EVENT_LIMIT")
            require(next_state["revision"] == state["revision"] and
                    (next_state["sessionId"], next_state["datasetVersion"], next_state["profileHash"]) ==
                    (state["sessionId"], state["datasetVersion"], state["profileHash"]), "stateTransition")
            require(all(next_state[k]==state[k] for k in ("policy","startNs","initialBalance","profile","engineVersion","datasetId","parent")),"immutableContext")
            postings=[e for e in events if e["classification"]=="SIMULATED_FILL"]
            require(all(e["kind"] in ("ENTRY_FILL","EXIT_FILL") for e in postings),"postings","CORRUPT_RECORD")
            require(Fraction(next_state["balance"])-Fraction(state["balance"])==sum((exact(e["detail"]["cashDelta"],"cash") for e in postings),Fraction(0))
                    and Fraction(next_state["commission"])-Fraction(state["commission"])==sum((exact(e["detail"]["commissionPosted"],"fee") for e in postings),Fraction(0))
                    and Fraction(next_state["realizedGross"])-Fraction(state["realizedGross"])==sum((exact(e["detail"]["grossPosted"],"gross") for e in postings if e["kind"]=="EXIT_FILL"),Fraction(0)),
                    "cashPosting","CORRUPT_RECORD")
            previous_hash, sequence = state["eventHash"], state["nextEventIndex"]
            for event in events:
                tag(event,"BTL-TICK-EXECUTION-EVENT-2","engineVersion sessionId datasetId datasetVersion profileHash methodHash sequence previousHash kind classification orderId detail eventId")
                require(type(event["sequence"]) is int and event["methodHash"]==state["policy"]["definitionHash"],"event")
                value = {k:v for k,v in event.items() if k != "eventId"}
                require(event["sequence"] == sequence and event["previousHash"] == previous_hash and
                        event["eventId"] == content_hash(value) and event["sessionId"] == session
                        and event["engineVersion"]==state["engineVersion"] and event["profileHash"]==state["profileHash"]
                        and event["datasetId"]==state["datasetId"] and event["datasetVersion"]==state["datasetVersion"], "eventChain", "CORRUPT_RECORD")
                previous_hash, sequence = event["eventId"], sequence+1
            require(next_state["eventHash"] == previous_hash and next_state["nextEventIndex"] == sequence, "eventHead", "CORRUPT_RECORD")
            next_state["revision"] += 1
            state_raw, state_hash = pack(snapshot(next_state, next_checkpoint))
            result = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-RESULT-2", commandId=command["commandId"],
                          commandHash=command_hash, state=next_state, events=events, replay=replay,
                          durable=True, model=next_state["profile"]["model"])
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
            stored = read_snapshot(*row)
            state = stored["state"]
            rows = db.execute("SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence >= %s AND sequence < %s ORDER BY sequence LIMIT %s",
                              (workspace,session,after_sequence,state["nextEventIndex"],maximum)).fetchall()
            # Controller checkpoint/schedules are intentionally not projected.
            return {"state":state,"events":[unpack(*row) for row in rows]}

    def statistics(self,scope,session_id):
        """Read-only coherent committed ledger; no provider/source reconstruction."""
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return self._statistics(db,scope,session_id)[0]

    def _statistics(self,db,scope,session_id):
        """Private same-snapshot seam for confirmed review enrichment."""
        from .analysis_v2 import project
        workspace,session=scoped(scope,session_id)
        row=db.execute("SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s",(workspace,session)).fetchone()
        require(row is not None,"session","RESOURCE_UNAVAILABLE")
        stored=read_snapshot(row[0],row[1]);state=stored["state"]
        require((state["revision"],state["datasetVersion"],state["profileHash"])==tuple(row[2:]),"state","CORRUPT_RECORD")
        first=db.execute("SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=0",(workspace,session)).fetchone()
        require(first is not None,"genesis","CORRUPT_RECORD")
        genesis=read_snapshot(*first)["state"]
        def events():
            for offset in range(0,state["nextEventIndex"],256):
                rows=db.execute("SELECT payload,content_hash FROM btl.tick_events WHERE workspace_id=%s AND session_id=%s AND sequence >= %s AND sequence < %s ORDER BY sequence LIMIT 256",(workspace,session,offset,state["nextEventIndex"])).fetchall()
                for row in rows:yield unpack(*row)
        # Refusal happens inside project before touching the event generator.
        return project(state,events(),genesis),state

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
                return checked_result(unpack(prior[1],prior[2]), child_session, command)
            require(command["expectedRevision"] == 0, "revision", "REFUSED_STALE_REVISION")
            require(db.execute("SELECT 1 FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s",(workspace,child_session)).fetchone() is None,
                    "childSession", "REFUSED_FORK_IDENTITY")
            row = db.execute("SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s", (workspace,parent_session,parent_revision)).fetchone()
            require(row is not None, "forkPoint", "REFUSED_FORK_POINT")
            stored = read_snapshot(*row)
            state, checkpoint = stored["state"], stored["controller"]
            snapshot(state, checkpoint)
            require(not state["unresolved"] and not state["ended"], "forkPoint", "REFUSED_FORK_POINT")
            parent = dict(sessionId=parent_session, revision=parent_revision, checkpointHash=row[1], eventHash=state["eventHash"], timeNs=state["throughNs"])
            state.update(sessionId=child_session, revision=0, nextEventIndex=0, parent=parent,
                         eventHash=content_hash(dict(schemaVersion=1, artifact="BTL-TICK-FORK-SEED-2", parent=parent, childSessionId=child_session)))
            self._insert(db, scope, state, checkpoint)
            events = []
            emit(state,events,"SESSION_FORKED",classification="ACCEPTED_COMMAND",parent=parent)
            state["revision"] = 1
            state_raw, state_hash = pack(snapshot(state,checkpoint))
            result = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-RESULT-2", commandId=command["commandId"],
                          commandHash=command_hash, state=state, events=events, replay=None, durable=True,
                          model=state["profile"]["model"])
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
