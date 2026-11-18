"""Versioned synthetic MI persistence on the shared append-only tick ledger.

TrustedScope and the source opener are server capabilities. This store has no
public entry point. A PostgreSQL row lock serializes a Session's commands.
"""
from fractions import Fraction

from contracts.canonical import content_hash
from contracts.primitives import digest, require, revision
from infrastructure.database import connect
from ticks.contracts import tag, uint

from . import mi_archive, mi_checkpoint, mi_jump, mi_kernel, mi_projection
from .postgres import pack, scoped, unpack

SESSION = "BTL-TICK-DURABLE-SESSION-MI-1"
RECEIPT = "BTL-TICK-DURABLE-RESULT-MI-1"
MAX_ADVANCE_TIMESTAMPS = 64
MAX_PROJECTION_EVENTS = 4096


def _validate_transition(before, after, events):
    require(all(before[key] == after[key] for key in
                ("sessionId", "artifact", "engineVersion", "profiles", "profileSetHash",
                 "methods", "initialBalance", "startNs")),
            "miPins", "CORRUPT_RECORD")
    require(before.get("archived") == after.get("archived"), "miArchiveMutation", "CORRUPT_RECORD")
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


def _request_hash(command, jump, review_hash=None):
    value = dict(schemaVersion=1, artifact="BTL-MI-COMMAND-REQUEST-1", command=command, jump=jump)
    if review_hash is not None:
        value["reviewHash"] = review_hash
    return content_hash(value)


REVIEW = "BTL-MI-ORDER-REVIEW-1"
REVIEW_TTL_SECONDS = 300


def _review_record(db, workspace, session, review_id):
    row = db.execute("SELECT basis_revision,payload,content_hash FROM btl.tick_mi_order_reviews "
                     "WHERE workspace_id=%s AND session_id=%s AND review_id=%s",
                     (workspace, session, review_id)).fetchone()
    if row is None:
        return None
    value = unpack(*row[1:])
    tag(value, REVIEW, "actorRef command basisHash expiresAt")
    command = mi_kernel.command_wire(value["command"])
    require((command["sessionId"], command["commandId"], command["expectedRevision"]) ==
            (session, review_id, row[0]), "review", "CORRUPT_RECORD")
    return value, row[2]


def _db_seconds(db):
    return db.execute("SELECT floor(extract(epoch FROM clock_timestamp()))::bigint").fetchone()[0]


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
        if "archived" in state:
            from .terminal_order_archive import GENESIS
            archive_tip = db.execute(
                "SELECT sequence,record_hash FROM btl.tick_terminal_orders WHERE workspace_id=%s "
                "AND session_id=%s ORDER BY sequence DESC LIMIT 1", (workspace, session)).fetchone()
            expected = state["archived"]
            require((archive_tip or (-1, GENESIS)) == (expected["count"] - 1, expected["head"]),
                    "miArchiveTip", "CORRUPT_RECORD")
        manifest_sha = envelope.get("manifestSha")
        if manifest_sha is not None:
            digest(manifest_sha, "miManifest")
        return checkpoint, manifest_sha

    def create(self, scope, profile_set, policies, active_method_id, balance, start_ns, session_id, *, manifest_sha=None, compact=False):
        if manifest_sha is not None:
            digest(manifest_sha, "miManifest")
        workspace, session = scoped(scope, session_id)
        state = mi_kernel.seed_state(session, profile_set, policies, active_method_id, balance, start_ns)
        require(type(compact) is bool, "miCompact")
        if compact:
            from .terminal_order_archive import GENESIS
            state.update(artifact=mi_kernel.MI_COMPACT_STATE,
                         archived=dict(count=0, filled=0, gross="0", fees="0", head=GENESIS))
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

    def review(self, scope, raw_command, *, required_manifest_sha, authorize):
        command = mi_kernel.command_wire(raw_command)
        require(command["kind"] == "OPEN", "reviewKind")
        workspace, session = scoped(scope, command["sessionId"])
        with connect(self.dsn) as db:
            checkpoint, sha = self._read(db, workspace, session, lock=True)
            require(sha == required_manifest_sha, "miManifest", "REFUSED_DATASET_MISMATCH")
            review_id = command["commandId"]
            prior = _review_record(db, workspace, session, review_id)
            if prior is not None:
                value, review_hash = prior
                require(value["actorRef"] == scope.actor_ref and value["command"] == command,
                        "review", "REFUSED_IDEMPOTENCY_CONFLICT")
            else:
                state = checkpoint["state"]
                authorize(db, state, command, False)
                mi_kernel.submit(state, command)  # exact reducer validation, discard proposed state
                plan = command["payload"]
                if plan["orderType"] == "MARKET":
                    side = "ask" if plan["side"] == "LONG" else "bid"
                    ticks = state["groups"][plan["symbol"]]["events"]
                    quotes = {Fraction(tick[side]) for tick in ticks}
                    require(quotes == {Fraction(plan["entry"])}, "quote", "MI_REVIEW_MISMATCH")
                value = dict(schemaVersion=1, artifact=REVIEW, actorRef=scope.actor_ref,
                             command=command, basisHash=checkpoint["checkpointHash"],
                             expiresAt=_db_seconds(db) + REVIEW_TTL_SECONDS)
                payload, review_hash = pack(value)
                db.execute("INSERT INTO btl.tick_mi_order_reviews VALUES (%s,%s,%s,%s,%s,%s)",
                           (workspace, session, review_id, state["revision"], payload, review_hash))
            return {key: item for key, item in dict(value, reviewHash=review_hash).items() if key != "actorRef"}

    def apply(self, scope, raw_command, open_sources, *, jump=False, required_manifest_sha=None,
              review_hash=None, require_review=False, authorize=None):
        command = mi_kernel.command_wire(raw_command)
        require(type(jump) is bool and (not jump or command["kind"] == "ADVANCE"), "miJump")
        workspace, session = scoped(scope, command["sessionId"])
        command_hash = _request_hash(command, jump, review_hash)
        with connect(self.dsn) as db:
            checkpoint, manifest_sha = self._read(db, workspace, session, lock=True)
            require(manifest_sha == required_manifest_sha, "miManifest", "REFUSED_DATASET_MISMATCH")
            prior = db.execute(
                "SELECT revision,command_hash,payload,content_hash FROM btl.tick_commands "
                "WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                (workspace, session, command["commandId"])).fetchone()
            if prior:
                if review_hash is not None:
                    reviewed = _review_record(db, workspace, session, command["commandId"])
                    require(reviewed is not None and reviewed[0]["actorRef"] == scope.actor_ref,
                            "review", "RESOURCE_UNAVAILABLE")
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
            if command["kind"] == "OPEN" and (require_review or review_hash is not None):
                require(review_hash is not None, "review", "MI_REVIEW_REQUIRED")
                reviewed = _review_record(db, workspace, session, command["commandId"])
                require(reviewed is not None, "review", "RESOURCE_UNAVAILABLE")
                value, expected_hash = reviewed
                require(expected_hash == review_hash and value["actorRef"] == scope.actor_ref and
                        value["command"] == command, "review", "MI_REVIEW_MISMATCH")
                require(value["basisHash"] == checkpoint["checkpointHash"],
                        "revision", "REFUSED_STALE_REVISION")
                require(_db_seconds(db) < value["expiresAt"], "review", "MI_REVIEW_EXPIRED")
            effective_target = authorize(db, before, command, jump) if authorize else None
            if "archived" in before and command["kind"] == "OPEN":
                terminal = db.execute(
                    "SELECT 1 FROM btl.tick_terminal_orders WHERE workspace_id=%s "
                    "AND session_id=%s AND order_id=%s", (workspace, session, command["commandId"])).fetchone()
                require(terminal is None, "commandId", "REFUSED_IDEMPOTENCY_CONFLICT")
            after, events = mi_kernel.submit(before, command)
            cursor, replay = checkpoint["cursor"], None
            if command["kind"] == "ADVANCE":
                if manifest_sha is None:
                    sources, verified_pins = open_sources()
                else:
                    sources, verified_pins, admitted_sha = open_sources(checkpoint["sourcePins"])
                    require(admitted_sha == manifest_sha, "miManifest", "REFUSED_DATASET_MISMATCH")
                _, timeline = mi_checkpoint.restore(checkpoint, sources, verified_source_pins=verified_pins)
                target = uint(command["payload"]["targetNs"]) if effective_target is None else effective_target
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
            # Event FK is deferred, and archive/checkpoint/receipt share this
            # transaction. Fold only after validating the financial transition.
            mi_archive.append(db, workspace, session, before, after, events)
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

    def command_status(self, scope, raw_command, *, jump, required_manifest_sha, review_hash=None):
        command = mi_kernel.command_wire(raw_command)
        workspace, session = scoped(scope, command["sessionId"])
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            checkpoint, sha = self._read(db, workspace, session)
            require(sha == required_manifest_sha, "miManifest", "REFUSED_DATASET_MISMATCH")
            current = checkpoint["state"]["revision"]
            row = db.execute("SELECT revision,command_hash,payload,content_hash FROM btl.tick_commands "
                             "WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                             (workspace, session, command["commandId"])).fetchone()
            committed_revision = None
            if row is not None:
                if review_hash is not None:
                    reviewed = _review_record(db, workspace, session, command["commandId"])
                    require(reviewed is not None and reviewed[0]["actorRef"] == scope.actor_ref,
                            "review", "RESOURCE_UNAVAILABLE")
                expected = _request_hash(command, jump, review_hash)
                require(row[1] == expected, "commandId", "REFUSED_IDEMPOTENCY_CONFLICT")
                receipt = unpack(*row[2:])
                require(receipt.get("artifact") == RECEIPT and receipt.get("durable") is True and
                        receipt["sessionId"] == session and receipt["commandId"] == command["commandId"] and
                        receipt["commandHash"] == expected and receipt["revision"] == row[0] <= current,
                        "miReceipt", "CORRUPT_RECORD")
                status, committed_revision = "COMMITTED", row[0]
            else:
                status = "NOT_COMMITTED" if current > command["expectedRevision"] else "UNKNOWN"
            return dict(schemaVersion=1, artifact="BTL-MI-COMMAND-STATUS-1", status=status,
                        revision=current, committedRevision=committed_revision)

    def snapshot(self, scope, session_id, *, required_manifest_sha, focus=None, open_sources=None):
        workspace, session = scoped(scope, session_id)
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            checkpoint, manifest_sha = self._read(db, workspace, session)
            require(manifest_sha == required_manifest_sha, "miManifest", "REFUSED_DATASET_MISMATCH")
            state = checkpoint["state"]
            view = dict(schemaVersion=1, artifact="BTL-MI-SESSION-VIEW-1", state=state,
                        equity=mi_kernel.equity(state))
            if focus is not None:
                require(focus in state["groups"], "symbol", "REFUSED_INSTRUMENT_SET")
                view["activeInstrument"] = focus
                view["chart"] = []
                consumed = checkpoint["cursor"]["consumed"][focus]
                if consumed and open_sources is not None:
                    from itertools import groupby, islice
                    sources, _, sha = open_sources(checkpoint["sourcePins"])
                    require(sha == manifest_sha, "miManifest", "REFUSED_DATASET_MISMATCH")
                    start = max(0, consumed - 64)
                    groups = groupby(sources[focus](start), key=lambda tick: tick["timeNs"])
                    for stamp, ticks in islice(groups, consumed - start):
                        require(int(stamp) <= int(state["throughNs"]), "miChart", "REFUSED_FUTURE_EVIDENCE")
                        close_bid = list(ticks)[-1]["bid"]
                        view["chart"].append(dict(timeNs=stamp, bid=close_bid))
                    require(len(view["chart"]) == consumed - start, "miChart", "CORRUPT_RECORD")
            return view

    def terminal_page(self, scope, session_id, *, after_sequence=None, revision_pin=None, limit=32):
        workspace, session = scoped(scope, session_id)
        require(type(limit) is int and 1 <= limit <= 64, "limit")
        require(after_sequence is None or revision_pin is not None, "cursor", "INVALID_CURSOR")
        if after_sequence is not None:
            revision(after_sequence)
        if revision_pin is not None:
            revision(revision_pin)
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            state = self._read(db, workspace, session)[0]["state"]
            require(revision_pin is None or revision_pin == state["revision"], "revision", "STALE_REVISION")
            after = -1 if after_sequence is None else after_sequence
            return mi_archive.page(db, workspace, session, state, after, limit)

    def event_page(self, scope, session_id, *, after_sequence=None, revision_pin=None, limit=32):
        """Read a bounded verified slice of Journal's authoritative event ledger."""
        workspace, session = scoped(scope, session_id)
        require(type(limit) is int and 1 <= limit <= 64, "limit")
        require(after_sequence is None or revision_pin is not None, "cursor", "INVALID_CURSOR")
        if after_sequence is not None:
            revision(after_sequence)
        if revision_pin is not None:
            revision(revision_pin)
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            state = self._read(db, workspace, session)[0]["state"]
            require(revision_pin is None or revision_pin == state["revision"], "revision", "STALE_REVISION")
            start = 0 if after_sequence is None else after_sequence + 1
            require(after_sequence is None or after_sequence < state["nextEventIndex"], "cursor", "INVALID_CURSOR")
            first = max(0, start - 1)
            rows = db.execute(
                "SELECT sequence,event_id,payload,content_hash FROM btl.tick_events "
                "WHERE workspace_id=%s AND session_id=%s AND sequence >= %s ORDER BY sequence LIMIT %s",
                (workspace, session, first, limit + (start > 0))).fetchall()
            require(len(rows) == min(state["nextEventIndex"] - first, limit + (start > 0)),
                    "miPageLength", "CORRUPT_RECORD")
            head = mi_kernel.seed_hash(state) if first == 0 else None
            events = []
            for expected, (sequence, event_id, payload, sha) in enumerate(rows, start=first):
                event = unpack(payload, sha)
                require(expected == sequence == event["sequence"] and event["eventId"] == event_id and
                        event["artifact"] == mi_kernel.MI_EVENT and event["sessionId"] == session and
                        event["profileSetHash"] == state["profileSetHash"] and
                        event_id == content_hash({key: value for key, value in event.items() if key != "eventId"}) and
                        (head is None or event["previousHash"] == head), "miPageChain", "CORRUPT_RECORD")
                head = event_id
                if sequence >= start:
                    events.append(event)
            more = start + len(events) < state["nextEventIndex"]
            require(more or head == state["eventHash"], "miPageHead", "CORRUPT_RECORD")
            return dict(schemaVersion=1, artifact="BTL-MI-EVENT-PAGE-1", revision=state["revision"],
                        events=events, nextAfterSequence=events[-1]["sequence"] if more else None)

    def project(self, scope, session_id):
        workspace, session = scoped(scope, session_id)
        with connect(self.dsn) as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            state = self._read(db, workspace, session)[0]["state"]
            if "archived" in state:
                return mi_archive.summary(db, workspace, session, state)
            require(state["nextEventIndex"] <= MAX_PROJECTION_EVENTS, "miProjection", "REFUSED_ANALYSIS_LIMIT")
            rows = db.execute(
                "SELECT payload,content_hash FROM btl.tick_events "
                "WHERE workspace_id=%s AND session_id=%s ORDER BY sequence LIMIT %s",
                (workspace, session, MAX_PROJECTION_EVENTS + 1)).fetchall()
            result = mi_projection.project(state, [unpack(*row) for row in rows])
            result["artifact"] = "BTL-MI-DURABLE-QA-PROJECTION-1"
            result["provenance"]["financialAuthority"] = "DURABLE_SYNTHETIC_MI_LEDGER_ONLY"
            return result
