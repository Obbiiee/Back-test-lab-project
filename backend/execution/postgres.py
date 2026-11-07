"""Existing PostgreSQL transaction boundary; no public API or hidden market data."""
from copy import deepcopy
from collections import OrderedDict
import hashlib
import json
from threading import RLock
from uuid import uuid4

from psycopg import sql
from application.models import TrustedScope
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, identifier, revision
from infrastructure.database import connect
from .contracts import MAX_EVENTS, command_wire, validate_state
from .engine import emit
from .observed_state_delta_v3 import encode_compact_base, encode_compact_delta, reconstruct_complete
from .terminal_order_archive import GENESIS as ORDER_ARCHIVE_GENESIS, record as terminal_record
from .terminal_order_archive import terminal_orders, verify as verify_terminal_record


COMPACT_BASE = "BTL-TICK-EXECUTION-COMPACT-BASE-1"
COMPACT_POINTER = "BTL-TICK-EXECUTION-COMPACT-POINTER-1"
COMPACT_DELTA = "BTL-TICK-EXECUTION-COMPACT-DELTA-1"
COMPACT_RECEIPT = "BTL-TICK-EXECUTION-COMPACT-RESULT-1"
_COMPACT_CACHE = OrderedDict()
_COMPACT_CACHE_LOCK = RLock()
_COMPACT_CACHE_MAX = 4


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
    def __init__(self, dsn, *, state_storage_format="compact-v1"):
        require(state_storage_format in ("snapshot-v1", "compact-v1"),
                "stateStorageFormat", "REFUSED_STATE_VERSION")
        self.dsn = dsn
        self.state_storage_format = state_storage_format

    def _cache_key(self, workspace, session):
        return hashlib.sha256(self.dsn.encode("utf-8")).hexdigest(), workspace, session

    def _cache_read(self, workspace, session, pointer):
        key = self._cache_key(workspace, session)
        with _COMPACT_CACHE_LOCK:
            row = _COMPACT_CACHE.get(key)
            if row is None or (row["revision"], row["stateHash"], row["chainHash"], row["controller"]) != (
                    pointer["revision"], pointer["stateHash"], pointer["chainHash"], pointer["controller"]):
                _COMPACT_CACHE.pop(key, None)
                return None
            _COMPACT_CACHE.move_to_end(key)
            return deepcopy(row["state"])

    def _cache_write(self, workspace, session, state, controller, chain_hash):
        key = self._cache_key(workspace, session)
        with _COMPACT_CACHE_LOCK:
            _COMPACT_CACHE[key] = dict(revision=state["revision"], stateHash=content_hash(state),
                                       chainHash=chain_hash, state=deepcopy(state),
                                       controller=deepcopy(controller))
            _COMPACT_CACHE.move_to_end(key)
            while len(_COMPACT_CACHE) > _COMPACT_CACHE_MAX:
                _COMPACT_CACHE.popitem(last=False)

    def _reconstruct_compact(self, db, workspace, session, target_revision, *, require_tip=False):
        revision(target_revision)
        base_row = db.execute("SELECT payload,content_hash FROM btl.tick_checkpoints "
                              "WHERE workspace_id=%s AND session_id=%s AND revision=0",
                              (workspace, session)).fetchone()
        require(base_row is not None, "compactBase", "CORRUPT_RECORD")
        base = unpack(*base_row)
        require(set(base) == {"schemaVersion", "formatVersion", "artifact", "revision", "state", "stateHash", "chainHash", "controller"} and
                base.get("schemaVersion") == 1 and base.get("formatVersion") == 1 and
                base.get("artifact") == COMPACT_BASE and base.get("revision") == 0 and
                base.get("stateHash") == content_hash(base.get("state")) == base.get("chainHash"),
                "compactBase", "CORRUPT_RECORD")
        if require_tip:
            tip = db.execute("SELECT revision FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s",
                             (workspace, session)).fetchone()
            require(tip is not None and tip[0] == target_revision, "compactTip", "CORRUPT_RECORD")
            count, maximum = db.execute("SELECT count(*),max(revision) FROM btl.tick_checkpoints "
                "WHERE workspace_id=%s AND session_id=%s AND revision>0",
                (workspace, session)).fetchone()
            require(count == target_revision and maximum == (target_revision or None),
                    "compactTip", "CORRUPT_RECORD")
        count = db.execute("SELECT count(*) FROM btl.tick_checkpoints WHERE workspace_id=%s "
                           "AND session_id=%s AND revision>0 AND revision<=%s",
                           (workspace, session, target_revision)).fetchone()[0]
        require(count == target_revision, "compactChain", "CORRUPT_RECORD")
        previous = base["chainHash"]
        current_controller = [base["controller"]]
        def deltas():
            nonlocal previous
            with db.cursor(name="btl_tick_delta_" + uuid4().hex) as rows:
                rows.execute("SELECT revision,payload,content_hash FROM btl.tick_checkpoints "
                             "WHERE workspace_id=%s AND session_id=%s AND revision>0 AND revision<=%s "
                             "ORDER BY revision", (workspace, session, target_revision))
                for expected, (rev, payload, sha) in enumerate(rows, 1):
                    checkpoint = unpack(payload, sha)
                    require(set(checkpoint) == {"schemaVersion", "formatVersion", "artifact", "revision",
                                "stateHash", "chainHash", "previousHash", "delta", "controller"} and
                            checkpoint.get("schemaVersion") == 1 and checkpoint.get("formatVersion") == 1 and
                            checkpoint.get("artifact") == COMPACT_DELTA and checkpoint.get("revision") == rev == expected and
                            checkpoint.get("previousHash") == previous and
                            checkpoint.get("stateHash") == checkpoint.get("delta", {}).get("body", {}).get("stateHash") and
                            checkpoint.get("chainHash") == checkpoint.get("delta", {}).get("body", {}).get("recordHash"),
                            "compactChain", "CORRUPT_RECORD")
                    current_controller[0] = checkpoint["controller"]
                    previous = checkpoint["chainHash"]
                    yield checkpoint["delta"]
        def validate_each(state, _rev):
            snapshot(state, current_controller[0])
        state = reconstruct_complete(base, deltas(), target_revision, state_callback=validate_each)
        return state, previous, current_controller[0]

    def _load_row(self, db, workspace, session, row, *, require_tip=False):
        wire = unpack(row[0], row[1])
        if wire.get("artifact") != COMPACT_POINTER:
            stored = wire
            snapshot(stored["state"], stored["controller"])
            return stored
        require(set(wire) == {"schemaVersion", "formatVersion", "artifact", "revision", "stateHash", "chainHash", "controller"} and
                wire.get("schemaVersion") == 1 and wire.get("formatVersion") == 1 and
                wire.get("revision") == row[2], "compactPointer", "CORRUPT_RECORD")
        tip = db.execute("SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s "
                         "AND session_id=%s AND revision=%s", (workspace, session, row[2])).fetchone()
        require(tip is not None, "compactTip", "CORRUPT_RECORD")
        tip_wire = unpack(*tip)
        require(tip_wire.get("artifact") in (COMPACT_BASE, COMPACT_DELTA) and
                tip_wire.get("revision") == row[2] and tip_wire.get("stateHash") == wire.get("stateHash") and
                tip_wire.get("chainHash") == wire.get("chainHash") and
                tip_wire.get("controller") == wire.get("controller"), "compactTip", "CORRUPT_RECORD")
        state = self._cache_read(workspace, session, wire)
        if state is None:
            state, chain_hash, controller = self._reconstruct_compact(
                db, workspace, session, row[2], require_tip=require_tip)
            self._cache_write(workspace, session, state, controller, chain_hash)
        else:
            chain_hash, controller = wire["chainHash"], wire["controller"]
        require(wire.get("stateHash") == content_hash(state) and wire.get("chainHash") == chain_hash and
                wire.get("controller") == controller, "compactPointer", "CORRUPT_RECORD")
        stored = snapshot(state, controller)
        require((state["revision"], state["datasetVersion"], state["profileHash"]) == tuple(row[2:]),
                "compactPointer", "CORRUPT_RECORD")
        return stored

    def read_session(self, db, scope, session, row):
        workspace, session = scoped(scope, session)
        return self._load_row(db, workspace, session, row, require_tip=True)

    def _compact_receipt(self, command, row, db, workspace, session):
        wire = unpack(row[2], row[3])
        require(set(wire) == {"schemaVersion", "formatVersion", "artifact", "commandId", "commandHash",
                    "stateRevision", "stateHash", "chainHash", "events", "replay", "durable", "model"} and
                wire.get("schemaVersion") == 1 and wire.get("formatVersion") == 1 and
                wire.get("artifact") == COMPACT_RECEIPT and wire.get("commandId") == command["commandId"] and
                wire.get("commandHash") == content_hash(command) == row[1] and wire.get("stateRevision") == row[0],
                "receipt", "CORRUPT_RECORD")
        require(wire.get("durable") is True and wire.get("model") ==
                "SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION", "receipt", "CORRUPT_RECORD")
        state, chain_hash, _controller = self._reconstruct_compact(db, workspace, session, row[0])
        require(wire.get("stateHash") == content_hash(state) and wire.get("chainHash") == chain_hash,
                "receiptState", "CORRUPT_RECORD")
        prior_state, _prior_chain, _prior_controller = self._reconstruct_compact(db, workspace, session, row[0]-1)
        events = wire.get("events")
        require(type(events) is list and len(events) <= MAX_EVENTS, "receipt", "CORRUPT_RECORD")
        previous, sequence = prior_state["eventHash"], prior_state["nextEventIndex"]
        for event in events:
            require(event.get("sequence") == sequence and event.get("previousHash") == previous and
                    event.get("sessionId") == session and
                    event.get("eventId") == content_hash({k: v for k, v in event.items() if k != "eventId"}),
                    "receiptEvents", "CORRUPT_RECORD")
            previous = event["eventId"]
            sequence += 1
        require(sequence == state["nextEventIndex"] and previous == state["eventHash"],
                "receiptEvents", "CORRUPT_RECORD")
        replay = wire.get("replay")
        if replay is None:
            require(command["kind"] not in ("ADVANCE", "SEEK"), "receiptReplay", "CORRUPT_RECORD")
        else:
            require(set(replay) == {"throughNs", "exhaustedThroughBoundary"} and
                    command["kind"] in ("ADVANCE", "SEEK") and
                    replay["throughNs"] == state["throughNs"] and
                    type(replay["exhaustedThroughBoundary"]) is bool, "receiptReplay", "CORRUPT_RECORD")
        result = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-RESULT-1",
                      commandId=command["commandId"], commandHash=content_hash(command), state=state,
                      events=events, replay=replay, durable=True,
                      model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION")
        require(result["state"]["revision"] == row[0], "receiptState", "CORRUPT_RECORD")
        return result

    def _insert(self, db, scope, state, checkpoint):
        workspace, session = scoped(scope, state["sessionId"])
        snap = snapshot(state, checkpoint)
        if self.state_storage_format == "compact-v1":
            base = encode_compact_base(state)
            base.update(artifact=COMPACT_BASE, chainHash=base["stateHash"], controller=deepcopy(checkpoint))
            raw_base, sha_base = pack(base)
            raw, sha = pack(dict(schemaVersion=1, formatVersion=1, artifact=COMPACT_POINTER,
                revision=state["revision"], stateHash=base["stateHash"], chainHash=base["chainHash"],
                controller=deepcopy(checkpoint)))
        else:
            raw, sha = pack(snap)
        db.execute("INSERT INTO btl.tick_sessions VALUES (%s,%s,%s,%s,%s,%s,%s)",
                   (workspace, session, state["datasetVersion"], state["profileHash"], state["revision"], raw, sha))
        if self.state_storage_format == "compact-v1":
            db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",
                       (workspace, session, state["revision"], raw_base, sha_base))
        else:
            db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",
                       (workspace, session, state["revision"], raw, sha))

    @staticmethod
    def _append_terminal_orders(db, workspace, session, revision_value, finalized):
        if not finalized:
            return
        last = db.execute("SELECT sequence,record_hash,payload,content_hash FROM btl.tick_terminal_orders "
                          "WHERE workspace_id=%s AND session_id=%s ORDER BY sequence DESC LIMIT 1",
                          (workspace, session)).fetchone()
        if last is None:
            sequence, previous_hash = 0, ORDER_ARCHIVE_GENESIS
        else:
            prior = unpack(last[2], last[3])
            verify_terminal_record(prior, session_id=session, sequence=last[0])
            require(prior["recordHash"] == last[1], "terminalArchiveHead", "CORRUPT_RECORD")
            sequence, previous_hash = last[0] + 1, last[1]
        for order_id in sorted(finalized):
            item = finalized[order_id]
            value = terminal_record(session_id=session, sequence=sequence,
                revision=revision_value, order_id=order_id, order=item["order"],
                events=item["events"], previous_hash=previous_hash)
            raw, digest = pack(value)
            db.execute("INSERT INTO btl.tick_terminal_orders "
                "(workspace_id,session_id,sequence,order_id,terminal_status,finalized_revision,record_hash,payload,content_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (workspace, session, sequence, order_id, item["order"]["status"], revision_value,
                 value["recordHash"], raw, digest))
            sequence += 1
            previous_hash = value["recordHash"]

    def create(self, scope, state, checkpoint):
        with connect(self.dsn) as db:
            self._insert(db, scope, state, checkpoint)
        if self.state_storage_format == "compact-v1":
            workspace, session = scoped(scope, state["sessionId"])
            self._cache_write(workspace, session, state, checkpoint, content_hash(state))

    def run(self, scope, raw_command, operation):
        command = command_wire(raw_command)
        workspace, session = scoped(scope, command["sessionId"])
        command_hash = content_hash(command)
        with connect(self.dsn) as db:
            row = db.execute("SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s FOR UPDATE",
                             (workspace, session)).fetchone()
            require(row is not None, "session", "RESOURCE_UNAVAILABLE")
            stored = self._load_row(db, workspace, session, row, require_tip=True)
            state, checkpoint = stored["state"], stored["controller"]
            snapshot(state, checkpoint)
            require((state["revision"], state["datasetVersion"], state["profileHash"]) == tuple(row[2:]), "state", "CORRUPT_RECORD")
            prior = db.execute("SELECT revision,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                               (workspace, session, command["commandId"])).fetchone()
            if prior:
                require(prior[1] == command_hash, "commandId", "REFUSED_IDEMPOTENCY_CONFLICT")
                if unpack(prior[2], prior[3]).get("artifact") == COMPACT_RECEIPT:
                    return self._compact_receipt(command, prior, db, workspace, session)
                return unpack(prior[2], prior[3])
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
            finalized_orders = terminal_orders(state, next_state, events)
            logical_snapshot = snapshot(next_state, next_checkpoint)
            compact_mode = unpack(row[0], row[1]).get("artifact") == COMPACT_POINTER
            if compact_mode:
                chain_hash = unpack(row[0], row[1])["chainHash"]
                delta = encode_compact_delta(state, next_state, chain_hash)
                next_chain = delta["body"]["recordHash"]
                checkpoint_wire = dict(schemaVersion=1, formatVersion=1, artifact=COMPACT_DELTA,
                    revision=next_state["revision"], stateHash=content_hash(next_state), chainHash=next_chain,
                    previousHash=chain_hash, delta=delta, controller=deepcopy(next_checkpoint))
                session_wire = dict(schemaVersion=1, formatVersion=1, artifact=COMPACT_POINTER,
                    revision=next_state["revision"], stateHash=content_hash(next_state), chainHash=next_chain,
                    controller=deepcopy(next_checkpoint))
                state_raw, state_hash = pack(session_wire)
                checkpoint_raw, checkpoint_hash = pack(checkpoint_wire)
                result_wire = dict(schemaVersion=1, formatVersion=1, artifact=COMPACT_RECEIPT,
                    commandId=command["commandId"], commandHash=command_hash,
                    stateRevision=next_state["revision"], stateHash=content_hash(next_state), chainHash=next_chain,
                    events=deepcopy(events), replay=deepcopy(replay), durable=True,
                    model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION")
                result_raw, result_hash = pack(result_wire)
            else:
                state_raw, state_hash = pack(logical_snapshot)
                result_raw = result_hash = None
            result = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-RESULT-1", commandId=command["commandId"],
                          commandHash=command_hash, state=next_state, events=events, replay=replay,
                          durable=True, model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION")
            if result_raw is None:
                result_raw, result_hash = pack(result)
            db.execute("INSERT INTO btl.tick_commands VALUES (%s,%s,%s,%s,%s,%s,%s)",
                       (workspace, session, command["commandId"], next_state["revision"], command_hash, result_raw, result_hash))
            for event in events:
                event_raw, event_hash = pack(event)
                db.execute("INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           (workspace, session, command["commandId"], event["eventId"], event["sequence"], event_raw, event_hash))
            self._append_terminal_orders(db, workspace, session, next_state["revision"], finalized_orders)
            if compact_mode:
                db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",
                           (workspace, session, next_state["revision"], checkpoint_raw, checkpoint_hash))
            else:
                db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",
                           (workspace, session, next_state["revision"], state_raw, state_hash))
            db.execute("UPDATE btl.tick_sessions SET revision=%s,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s",
                       (next_state["revision"], state_raw, state_hash, workspace, session))
        # Publication follows successful COMMIT; an after-commit crash is handled by durable dedup.
        if compact_mode:
            self._cache_write(workspace, session, next_state, next_checkpoint, next_chain)
        return deepcopy(result)

    def archive_order(self, scope, session_id, order_id):
        workspace, session = scoped(scope, session_id)
        identifier(order_id, "orderId")
        with connect(self.dsn) as db:
            row = db.execute("SELECT payload,content_hash,record_hash,sequence,terminal_status FROM btl.tick_terminal_orders "
                "WHERE workspace_id=%s AND session_id=%s AND order_id=%s",
                (workspace, session, order_id)).fetchone()
            if row is None:
                return None
            value = unpack(row[0], row[1])
            verify_terminal_record(value, session_id=session, sequence=row[3])
            require(value["recordHash"] == row[2] and value["orderId"] == order_id and value["order"]["status"]==row[4],
                    "terminalArchiveLookup", "CORRUPT_RECORD")
            return deepcopy(value)

    def order_history(self, scope, session_id, *, after_sequence=None, limit=64):
        workspace, session = scoped(scope, session_id)
        require(after_sequence is None or (type(after_sequence) is int and after_sequence >= -1), "cursor")
        require(type(limit) is int and 1 <= limit <= 128, "limit")
        with connect(self.dsn) as db:
            if after_sequence is None or after_sequence < 0:
                previous_hash = ORDER_ARCHIVE_GENESIS
                start = 0
            else:
                prior = db.execute("SELECT payload,content_hash,record_hash,terminal_status FROM btl.tick_terminal_orders "
                    "WHERE workspace_id=%s AND session_id=%s AND sequence=%s",
                    (workspace, session, after_sequence)).fetchone()
                require(prior is not None, "cursor", "REFUSED_STALE_CURSOR")
                value = unpack(prior[0], prior[1])
                verify_terminal_record(value, session_id=session, sequence=after_sequence)
                require(value["recordHash"] == prior[2] and value["order"]["status"]==prior[3], "terminalArchiveCursor", "CORRUPT_RECORD")
                previous_hash, start = prior[2], after_sequence + 1
            rows = db.execute("SELECT payload,content_hash,record_hash,sequence,terminal_status FROM btl.tick_terminal_orders "
                "WHERE workspace_id=%s AND session_id=%s AND sequence >= %s "
                "ORDER BY sequence LIMIT %s", (workspace, session, start, limit + 1)).fetchall()
            values = []
            for raw, digest, record_hash, sequence, terminal_status in rows:
                value = unpack(raw, digest)
                verify_terminal_record(value, session_id=session, sequence=sequence,
                                       previous_hash=previous_hash)
                require(value["recordHash"] == record_hash, "terminalArchiveLookup", "CORRUPT_RECORD")
                require(value["order"]["status"] == terminal_status, "terminalArchiveStatus", "CORRUPT_RECORD")
                values.append(value)
                previous_hash = record_hash
            page = values[:limit]
            return dict(schemaVersion=1, artifact="BTL-TICK-TERMINAL-ORDER-PAGE-1",
                sessionId=session, records=page,
                nextCursor=page[-1]["sequence"] if len(values) > limit and page else None,
                complete=len(values) <= limit)

    def inspect(self, scope, session_id, after_sequence=0, maximum=64):
        workspace, session = scoped(scope, session_id)
        revision(after_sequence)
        require(type(maximum) is int and 1 <= maximum <= 256, "maximum")
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            row = db.execute("SELECT payload,content_hash,revision,dataset_version,profile_hash FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s", (workspace,session)).fetchone()
            require(row is not None, "session", "RESOURCE_UNAVAILABLE")
            state = self._load_row(db, workspace, session, row, require_tip=True)["state"]
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
            prior = db.execute("SELECT revision,command_hash,payload,content_hash FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                               (workspace,child_session,command["commandId"])).fetchone()
            if prior:
                require(prior[1] == command_hash, "commandId", "REFUSED_IDEMPOTENCY_CONFLICT")
                if unpack(prior[2],prior[3]).get("artifact") == COMPACT_RECEIPT:
                    return self._compact_receipt(command, prior, db, workspace, child_session)
                return unpack(prior[2],prior[3])
            require(command["expectedRevision"] == 0, "revision", "REFUSED_STALE_REVISION")
            require(db.execute("SELECT 1 FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s",(workspace,child_session)).fetchone() is None,
                    "childSession", "REFUSED_FORK_IDENTITY")
            row = db.execute("SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s AND session_id=%s AND revision=%s", (workspace,parent_session,parent_revision)).fetchone()
            require(row is not None, "forkPoint", "REFUSED_FORK_POINT")
            stored_wire = unpack(*row)
            if stored_wire.get("artifact") in (COMPACT_BASE, COMPACT_DELTA):
                parent_state, _parent_chain, parent_checkpoint = self._reconstruct_compact(
                    db, workspace, parent_session, parent_revision)
                stored = snapshot(parent_state, parent_checkpoint)
            else:
                stored = stored_wire
            state, checkpoint = stored["state"], stored["controller"]
            snapshot(state, checkpoint)
            require(not state["unresolved"] and not state["ended"], "forkPoint", "REFUSED_FORK_POINT")
            logical_checkpoint_hash = pack(snapshot(state, checkpoint))[1]
            parent = dict(sessionId=parent_session, revision=parent_revision,
                          checkpointHash=logical_checkpoint_hash, eventHash=state["eventHash"],
                          timeNs=state["throughNs"])
            state.update(sessionId=child_session, revision=0, nextEventIndex=0, parent=parent,
                         eventHash=content_hash(dict(schemaVersion=1, artifact="BTL-TICK-FORK-SEED-1", parent=parent, childSessionId=child_session)))
            self._insert(db, scope, state, checkpoint)
            events = []
            emit(state,events,"SESSION_FORKED",classification="ACCEPTED_COMMAND",parent=parent)
            state["revision"] = 1
            logical_snapshot = snapshot(state, checkpoint)
            compact_mode = self.state_storage_format == "compact-v1"
            if compact_mode:
                base_state, base_chain, _base_controller = self._reconstruct_compact(db, workspace, child_session, 0)
                delta = encode_compact_delta(base_state, state, base_chain)
                chain_hash = delta["body"]["recordHash"]
                checkpoint_wire = dict(schemaVersion=1,formatVersion=1,artifact=COMPACT_DELTA,
                    revision=1,stateHash=content_hash(state),chainHash=chain_hash,
                    previousHash=base_chain,delta=delta,controller=deepcopy(checkpoint))
                pointer = dict(schemaVersion=1,formatVersion=1,artifact=COMPACT_POINTER,revision=1,
                    stateHash=content_hash(state),chainHash=chain_hash,controller=deepcopy(checkpoint))
                state_raw,state_hash=pack(pointer);checkpoint_raw,checkpoint_hash=pack(checkpoint_wire)
            else:
                state_raw, state_hash = pack(logical_snapshot)
            result = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-RESULT-1", commandId=command["commandId"],
                          commandHash=command_hash, state=state, events=events, replay=None, durable=True,
                          model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION")
            if compact_mode:
                compact_result=dict(schemaVersion=1,formatVersion=1,artifact=COMPACT_RECEIPT,
                    commandId=command["commandId"],commandHash=command_hash,stateRevision=1,
                    stateHash=content_hash(state),chainHash=chain_hash,events=deepcopy(events),replay=None,
                    durable=True,model="SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION")
                result_raw,result_hash=pack(compact_result)
            else:
                result_raw, result_hash = pack(result)
            db.execute("INSERT INTO btl.tick_commands VALUES (%s,%s,%s,%s,%s,%s,%s)",
                       (workspace,child_session,command["commandId"],1,command_hash,result_raw,result_hash))
            for event in events:
                event_raw,event_hash=pack(event)
                db.execute("INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           (workspace,child_session,command["commandId"],event["eventId"],event["sequence"],event_raw,event_hash))
            if compact_mode:
                db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",(workspace,child_session,1,checkpoint_raw,checkpoint_hash))
            else:
                db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",(workspace,child_session,1,state_raw,state_hash))
            db.execute("UPDATE btl.tick_sessions SET revision=1,payload=%s,content_hash=%s WHERE workspace_id=%s AND session_id=%s",(state_raw,state_hash,workspace,child_session))
        if compact_mode:
            self._cache_write(workspace, child_session, state, checkpoint, chain_hash)
        return deepcopy(result)


def grant_execution_runtime(dsn, role):
    """Explicit operator action; no automatic role creation or credentials."""
    with connect(dsn) as db:
        db.execute(sql.SQL("GRANT USAGE ON SCHEMA btl TO {}").format(sql.Identifier(role)))
        db.execute(sql.SQL("GRANT SELECT,INSERT ON btl.tick_sessions,btl.tick_commands,btl.tick_events,btl.tick_checkpoints,btl.tick_terminal_orders TO {}").format(sql.Identifier(role)))
        db.execute(sql.SQL("GRANT UPDATE(revision,payload,content_hash) ON btl.tick_sessions TO {}").format(sql.Identifier(role)))
