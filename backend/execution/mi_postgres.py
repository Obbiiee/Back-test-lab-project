"""Versioned synthetic MI persistence on the shared append-only tick ledger.

TrustedScope and the source opener are server capabilities. This store has no
public entry point. A PostgreSQL row lock serializes a Session's commands.
"""
from fractions import Fraction

from contracts.canonical import content_hash
from contracts.primitives import digest, require
from infrastructure.database import connect
from ticks.contracts import tag, uint

from . import mi_checkpoint, mi_jump, mi_kernel, mi_projection
from .postgres import pack, scoped, unpack

SESSION = "BTL-TICK-DURABLE-SESSION-MI-1"
RECEIPT = "BTL-TICK-DURABLE-RESULT-MI-1"
MAX_ADVANCE_TIMESTAMPS = 64
MAX_PROJECTION_EVENTS = 4096


def _validate_transition(before, after, events):
    require(all(before[key] == after[key] for key in
                ("sessionId", "engineVersion", "profiles", "profileSetHash",
                 "methods", "initialBalance", "startNs")),
            "miPins", "CORRUPT_RECORD")
    require(len(events) <= mi_kernel.MAX_EVENTS, "miEvents", "REFUSED_EVENT_LIMIT")
    for order_id, order in before["orders"].items():
        new = after["orders"].get(order_id)
        require(new is not None and all(new[key] == order[key] for key in ("symbol", "methodId")),
                "miAttribution", "CORRUPT_RECORD")
    head, sequence = before["eventHash"], before["nextEventIndex"]
    cash = fees = gross = Fraction()
    for event in events:
        require(event["artifact"] == mi_kernel.MI_EVENT and
                event["sessionId"] == before["sessionId"] and
                event["engineVersion"] == before["engineVersion"] and
                event["profileSetHash"] == before["profileSetHash"] and
                event["sequence"] == sequence and event["previousHash"] == head and
                event["eventId"] == content_hash({k: v for k, v in event.items() if k != "eventId"}),
                "miEventChain", "CORRUPT_RECORD")
        head, sequence = event["eventId"], sequence + 1
        if event["kind"] in ("ENTRY_FILL", "EXIT_FILL"):
            order = after["orders"].get(event["orderId"])
            require(order is not None and order["symbol"] == event["symbol"],
                    "miFillAttribution", "CORRUPT_RECORD")
            detail = event["detail"]
            cash += Fraction(detail["cashDelta"])
            fees += Fraction(detail["commissionPosted"])
            if event["kind"] == "EXIT_FILL":
                gross += Fraction(detail["grossPosted"])
    require((after["eventHash"], after["nextEventIndex"]) == (head, sequence) and
            all(Fraction(after[key]) - Fraction(before[key]) == delta for key, delta in
                (("balance", cash), ("commission", fees), ("realizedGross", gross))),
            "miPostings", "CORRUPT_RECORD")


def _source_hash(checkpoint):
    return content_hash(dict(schemaVersion=1, artifact="BTL-MI-SOURCE-PINS-1",
                             pins=checkpoint["sourcePins"]))


def _envelope(workspace, checkpoint, manifest_sha):
    # The reducer iterates orders in creation order. Canonical JSON sorts map
    # keys, so persist that order explicitly rather than changing execution.
    envelope = dict(schemaVersion=1, artifact=SESSION, workspaceId=workspace,
                    checkpoint=checkpoint, orderIds=list(checkpoint["state"]["orders"]))
    if manifest_sha is not None:
        envelope["manifestSha"] = manifest_sha
    return envelope


def _checkpoint(envelope, workspace):
    tag(envelope, SESSION, "workspaceId checkpoint orderIds" +
        (" manifestSha" if "manifestSha" in envelope else ""))
    checkpoint = envelope["checkpoint"]
    state = mi_checkpoint.validate(checkpoint)
    order_ids = envelope["orderIds"]
    require(envelope["workspaceId"] == workspace and type(order_ids) is list and
            all(type(key) is str for key in order_ids) and
            len(order_ids) == len(state["orders"]) and set(order_ids) == set(state["orders"]),
            "miOrderSequence", "CORRUPT_RECORD")
    state["orders"] = {key: state["orders"][key] for key in order_ids}
    checkpoint["state"] = state
    return checkpoint


class MultiInstrumentStore:
    def __init__(self, dsn):
        self.dsn = dsn

    @staticmethod
    def _read(db, workspace, session, *, lock=False):
        row = db.execute(
            "SELECT payload,content_hash,revision,dataset_version,profile_hash "
            "FROM btl.tick_sessions WHERE workspace_id=%s AND session_id=%s" +
            (" FOR UPDATE" if lock else ""), (workspace, session)).fetchone()
        require(row is not None, "session", "RESOURCE_UNAVAILABLE")
        envelope = unpack(*row[:2])
        require(envelope.get("artifact") == SESSION, "sessionModel", "REFUSED_SESSION_MODEL")
        checkpoint = _checkpoint(envelope, workspace)
        state = checkpoint["state"]
        require(envelope["workspaceId"] == workspace and state["sessionId"] == session and
                tuple(row[2:]) == (state["revision"], _source_hash(checkpoint),
                                   state["profileSetHash"]), "miSession", "CORRUPT_RECORD")
        tip = db.execute(
            "SELECT content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s "
            "AND session_id=%s AND revision=%s", (workspace, session, state["revision"])).fetchone()
        require(tip == (row[1],), "miCheckpointTip", "CORRUPT_RECORD")
        manifest_sha = envelope.get("manifestSha")
        if manifest_sha is not None:
            digest(manifest_sha, "miManifest")
        return checkpoint, manifest_sha

    def create(self, scope, profile_set, policies, active_method_id, balance, start_ns, session_id, *, manifest_sha=None):
        if manifest_sha is not None:
            digest(manifest_sha, "miManifest")
        workspace, session = scoped(scope, session_id)
        state = mi_kernel.seed_state(session, profile_set, policies, active_method_id, balance, start_ns)
        require(Fraction(balance) == Fraction(state["initialBalance"]), "moneyPrecision")
        symbols = list(profile_set.symbols)
        cursor = dict(schemaVersion=1, artifact="BTL-MULTI-TIMELINE-CURSOR-1",
                      instruments=symbols, frontierNs="0", consumed=dict.fromkeys(symbols, 0),
                      quotes=dict.fromkeys(symbols))
        checkpoint = mi_checkpoint.create(state, cursor)
        raw, sha = pack(_envelope(workspace, checkpoint, manifest_sha))
        with connect(self.dsn) as db:
            inserted = db.execute(
                "INSERT INTO btl.tick_sessions VALUES (%s,%s,%s,%s,0,%s,%s) "
                "ON CONFLICT (workspace_id,session_id) DO NOTHING RETURNING session_id",
                (workspace, session, _source_hash(checkpoint),
                 state["profileSetHash"], raw, sha)).fetchone()
            if inserted:
                db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,0,%s,%s)",
                           (workspace, session, raw, sha))
                return state
            current, _ = self._read(db, workspace, session, lock=True)
            genesis = db.execute(
                "SELECT content_hash FROM btl.tick_checkpoints "
                "WHERE workspace_id=%s AND session_id=%s AND revision=0", (workspace, session)).fetchone()
            require(genesis == (sha,), "sessionId", "REFUSED_IDEMPOTENCY_CONFLICT")
            return current["state"]

    def apply(self, scope, raw_command, open_sources, *, jump=False, required_manifest_sha=None):
        command = mi_kernel.command_wire(raw_command)
        require(type(jump) is bool and (not jump or command["kind"] == "ADVANCE"), "miJump")
        workspace, session = scoped(scope, command["sessionId"])
        command_hash = content_hash(dict(schemaVersion=1, artifact="BTL-MI-COMMAND-REQUEST-1", command=command, jump=jump))
        with connect(self.dsn) as db:
            checkpoint, manifest_sha = self._read(db, workspace, session, lock=True)
            require(manifest_sha == required_manifest_sha, "miManifest", "REFUSED_DATASET_MISMATCH")
            prior = db.execute(
                "SELECT revision,command_hash,payload,content_hash FROM btl.tick_commands "
                "WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                (workspace, session, command["commandId"])).fetchone()
            if prior:
                require(prior[1] == command_hash, "commandId", "REFUSED_IDEMPOTENCY_CONFLICT")
                result = unpack(*prior[2:])
                tag(result, RECEIPT, "sessionId commandId commandHash revision state events replay durable")
                require(result["sessionId"] == session and result["commandId"] == command["commandId"] and
                        result["commandHash"] == command_hash and result["revision"] == prior[0] ==
                        command["expectedRevision"] + 1 and result["durable"] is True,
                        "miReceipt", "CORRUPT_RECORD")
                committed = db.execute(
                    "SELECT payload,content_hash FROM btl.tick_checkpoints WHERE workspace_id=%s "
                    "AND session_id=%s AND revision=%s", (workspace, session, prior[0])).fetchone()
                require(committed is not None, "miReceiptCheckpoint", "CORRUPT_RECORD")
                saved = unpack(*committed)
                committed_state = _checkpoint(saved, workspace)["state"]
                require(committed_state == result["state"],
                        "miReceiptCheckpoint", "CORRUPT_RECORD")
                result["state"] = committed_state
                return result
            before = checkpoint["state"]
            after, events = mi_kernel.submit(before, command)
            cursor, replay = checkpoint["cursor"], None
            if command["kind"] == "ADVANCE":
                if manifest_sha is None:
                    sources, verified_pins = open_sources()
                else:
                    sources, verified_pins, admitted_sha = open_sources(checkpoint["sourcePins"])
                    require(admitted_sha == manifest_sha, "miManifest", "REFUSED_DATASET_MISMATCH")
                _, timeline = mi_checkpoint.restore(checkpoint, sources, verified_source_pins=verified_pins)
                target = uint(command["payload"]["targetNs"])
                if jump:
                    after, replay = mi_jump.run(after, timeline, target, max_timestamps=MAX_ADVANCE_TIMESTAMPS)
                    events = replay.pop("events")
                else:
                    groups = []
                    for _ in range(MAX_ADVANCE_TIMESTAMPS):
                        moment = timeline._controller_next_time()
                        if moment is None or moment > target:
                            break
                        groups.extend(timeline.advance(moment))
                    moment = timeline._controller_next_time()
                    require(moment is None or moment > target, "miAdvance", "REFUSED_REPLAY_LIMIT")
                    groups.extend(timeline.advance(target))
                    after, events = mi_kernel.advance(after, groups, str(target))
                cursor = timeline.cursor()

            _validate_transition(before, after, events)
            after["revision"] = before["revision"] + 1
            new = mi_checkpoint.create(after, cursor)
            raw, sha = pack(_envelope(workspace, new, manifest_sha))
            result = dict(schemaVersion=1, artifact=RECEIPT, sessionId=session,
                          commandId=command["commandId"], commandHash=command_hash,
                          revision=after["revision"], state=after, events=events,
                          replay=replay, durable=True)
            blob, digest = pack(result)
            db.execute("INSERT INTO btl.tick_commands VALUES (%s,%s,%s,%s,%s,%s,%s)",
                       (workspace, session, command["commandId"], after["revision"], command_hash, blob, digest))
            for event in events:
                blob, digest = pack(event)
                db.execute("INSERT INTO btl.tick_events VALUES (%s,%s,%s,%s,%s,%s,%s)",
                           (workspace, session, command["commandId"], event["eventId"],
                            event["sequence"], blob, digest))
            db.execute("INSERT INTO btl.tick_checkpoints VALUES (%s,%s,%s,%s,%s)",
                       (workspace, session, after["revision"], raw, sha))
            db.execute("UPDATE btl.tick_sessions SET revision=%s,payload=%s,content_hash=%s "
                       "WHERE workspace_id=%s AND session_id=%s",
                       (after["revision"], raw, sha, workspace, session))
        return result

    def project(self, scope, session_id):
        workspace, session = scoped(scope, session_id)
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            state = self._read(db, workspace, session)[0]["state"]
            require(state["nextEventIndex"] <= MAX_PROJECTION_EVENTS, "miProjection", "REFUSED_ANALYSIS_LIMIT")
            rows = db.execute(
                "SELECT payload,content_hash FROM btl.tick_events "
                "WHERE workspace_id=%s AND session_id=%s ORDER BY sequence LIMIT %s",
                (workspace, session, MAX_PROJECTION_EVENTS + 1)).fetchall()
            result = mi_projection.project(state, [unpack(*row) for row in rows])
            result["artifact"] = "BTL-MI-DURABLE-QA-PROJECTION-1"
            result["provenance"]["financialAuthority"] = "DURABLE_SYNTHETIC_MI_LEDGER_ONLY"
            return result
