"""Indexed, causal replay controller with private disk acknowledgement logs.

Preserves V1 runtime. No prices generated, execution, or account mutations.
"""
from copy import deepcopy
from pathlib import Path
import sqlite3
import json

from contracts.primitives import require, digest
from .contracts import keys, uint, CanonicalTick
from .contracts_v2 import canonical_v2_bytes, decode_v2, hash_v2, shape, CanonicalGroupBudget
from .provider import Cancellation, empty_diagnostics
from .timeline import CURSOR_FIELDS, RevealedView, make_group
from .storage_v2 import connect
from .evidence_v2 import PAGE, CURSOR, WINDOW_NS, ROW_LOCAL, CODES, eligible
from .provider import diagnostic_counts

VERSION = "BTL-TICK-TIMELINE-2"


class IndexedTickTimeline:
    def __init__(self, provider, dataset_id, dataset_version, session_start_ns="0", *, log_folder, allow_threads=False):
        described = provider.describe_v2(dataset_id, dataset_version)
        keys(described, "root completion indexBinding")
        for key, artifact in (("completion", "BTL-TICK-COMPLETION-2"), ("indexBinding", "BTL-TICK-INDEX-BINDING-2")):
            envelope = described[key]
            shape(envelope, artifact)
            require(envelope["datasetId"] == dataset_id and envelope["datasetVersion"] == dataset_version
                    and envelope["manifestHash"] == dataset_version and envelope["indexContentHash"] == described["root"]["indexContentHash"], "binding", "VERSION_MISMATCH")
        require(described["root"]["datasetId"] == dataset_id and hash_v2(described["root"]) == dataset_version, "root", "VERSION_MISMATCH")
        self.__provider, self.__id, self.__version = provider, dataset_id, dataset_version
        self.__root = described["root"]
        folder = Path(log_folder); folder.mkdir(parents=True, exist_ok=True)
        self.__log_path = folder / "timeline.sqlite"
        self.__db = connect(self.__log_path, allow_threads=allow_threads)
        self.__db.execute("CREATE TABLE IF NOT EXISTS blocks(hash TEXT PRIMARY KEY, body BLOB NOT NULL) WITHOUT ROWID")
        self.__db.execute("CREATE TABLE IF NOT EXISTS heads(id INTEGER PRIMARY KEY CHECK(id=1), body BLOB NOT NULL)")
        self.__db.execute("CREATE TEMP TABLE fences(source TEXT PRIMARY KEY, ordinal TEXT NOT NULL, sourceOrder INTEGER NOT NULL) WITHOUT ROWID")
        self.__db.execute("CREATE TEMP TABLE delivered(source TEXT, ordinal TEXT, code TEXT, body TEXT NOT NULL, PRIMARY KEY(source,ordinal,code)) WITHOUT ROWID")
        self.__db.execute("CREATE TEMP TABLE page_diagnostics(source TEXT, ordinal TEXT, code TEXT, body TEXT NOT NULL, PRIMARY KEY(source,ordinal,code)) WITHOUT ROWID")
        self.__db.execute("CREATE TEMP TABLE position_lookup(groupIndex INTEGER PRIMARY KEY, blockHash TEXT NOT NULL, recordOffset INTEGER NOT NULL)")
        self.__db.commit()
        self.__start, self.__generation, self.__epoch, self.__active = uint(session_start_ns), 0, 0, True
        try:
            self.__initialize()
        except BaseException:
            self.__db.close()
            raise

    def close(self):
        self.__db.close()

    def __initialize(self):
        self.__db.execute("DELETE FROM fences")
        self.__db.execute("DELETE FROM delivered")
        self.__db.execute("DELETE FROM page_diagnostics")
        self.__db.execute("DELETE FROM position_lookup")
        self.__db.commit()
        self.__next_position = self.__provider.locate_v2(self.__id, self.__version, str(self.__start))["position"]
        self.__iterator = self.__groups(self.__next_position)
        self.__pending = None
        self.__has_pending = False
        self.__advance_tip = self.__position_tip = None
        self.__advance_blocks = self.__position_blocks = 0
        initial = dict(schemaVersion=2, artifact="BTL-TICK-PREFIX-2", datasetId=self.__id, datasetVersion=self.__version,
                       timelineVersion=VERSION, generation=str(self.__generation), sessionStartNs=str(self.__start),
                       throughNs=str(self.__start), groups=[], coverage=[], diagnostics=empty_diagnostics())
        self.__cursor = dict(schemaVersion=2, artifact="BTL-TICK-CURSOR-2", datasetId=self.__id, datasetVersion=self.__version,
                             timelineVersion=VERSION, generation=str(self.__generation), revision="0", sessionStartNs=str(self.__start),
                             throughNs=str(self.__start), pendingTargetNs=None, visiblePrefixHash=hash_v2(initial), nextGroupIndex="0", lastGroupId=None)

    @property
    def cursor(self):
        return deepcopy(self.__cursor)

    def consumer(self):
        generation = self.__generation
        def read(index, maximum):
            require(self.__active and generation == self.__generation, "view", "STALE_GENERATION")
            return self.read_revealed(index, maximum)
        def cursor():
            require(self.__active and generation == self.__generation, "view", "STALE_GENERATION")
            return self.cursor
        return RevealedView(read, cursor)

    def __groups(self, position):
        rows, time = [], None
        while position is not None:
            page = self.__provider.read_page_v2(self.__id, self.__version, position, 256)
            shape(page, "BTL-TICK-PAGE-2")
            require(page["datasetId"] == self.__id and page["datasetVersion"] == self.__version, "page", "VERSION_MISMATCH")
            require(type(page["events"]) is list and 1 <= len(page["events"]) <= 256, "page", "ARTIFACT_LIMIT")
            d = page["diagnostics"]
            keys(d, "records counts truncated")
            require(type(d["records"]) is list and len(d["records"]) <= 128 and d["truncated"] is False
                    and type(d["counts"]) is dict and all(type(v) is int for v in d["counts"].values())
                    and d["counts"] == diagnostic_counts(d["records"]), "diagnostics", "INCOMPLETE_DIAGNOSTICS")
            for record in d["records"]:
                keys(record, "sourceId memberHash rawOrdinal timeNs code rawRecordHash")
                uint(record["timeNs"]); uint(record["rawOrdinal"])
                digest(record["memberHash"], "memberHash"); digest(record["rawRecordHash"], "rawRecordHash")
                require(record["code"] in CODES, "diagnostic", "SCHEMA_MISMATCH")
                identity = (record["sourceId"], record["rawOrdinal"], record["code"])
                body = json.dumps(record, sort_keys=True, separators=(",", ":"))
                previous = self.__db.execute("SELECT body FROM page_diagnostics WHERE source=? AND ordinal=? AND code=?", identity).fetchone()
                require(previous is None or previous[0] == body, "diagnostic", "IDENTITY_CONFLICT")
                self.__db.execute("INSERT OR IGNORE INTO page_diagnostics VALUES(?,?,?,?)", (*identity, body))
            require(type(page["endOfDataset"]) is bool and page["endOfDataset"] == (page["nextPosition"] is None), "eof", "SCHEMA_MISMATCH")
            for row in page["events"]:
                CanonicalTick._validate(row)
                require(row["datasetVersion"] == self.__version and all(row[k] == self.__root[k] for k in
                        ("datasetId", "providerId", "feedId", "instrumentId")), "event", "IDENTITY_CONFLICT")
                require(int(row["timeNs"]) >= self.__start and (time is None or int(row["timeNs"]) >= int(time)), "time", "ORDER_REVERSAL")
                if time is not None and row["timeNs"] != time:
                    start = self.__provider.locate_v2(self.__id, self.__version, time)["position"]
                    require(start is not None, "boundary", "INCOMPLETE_ATOMIC_BOUNDARY")
                    yield start, make_group(rows, self.__version)
                    rows = []
                time = row["timeNs"]
                rows.append(row)
                require(len(rows) <= 1024, "group", "GROUP_LIMIT")
            successor = page["nextPosition"]
            if successor is not None:
                require(successor != position and int(successor["globalOrdinal"]) == int(position["globalOrdinal"])+len(page["events"]), "position", "CORRUPT_INDEX_POINTER")
            position = successor
        if rows:
            start = self.__provider.locate_v2(self.__id, self.__version, time)["position"]
            require(start is not None, "boundary", "INCOMPLETE_ATOMIC_BOUNDARY")
            yield start, make_group(rows, self.__version)

    def __peek(self):
        if not self.__has_pending:
            self.__pending = next(self.__iterator, None)
            self.__has_pending = True
        return self.__pending

    def __restore(self):
        self.__iterator = self.__groups(self.__next_position)
        self.__pending, self.__has_pending = None, False

    def __append_block(self, artifact, index, previous, records):
        block = dict(schemaVersion=2, artifact=artifact, datasetId=self.__id, datasetVersion=self.__version,
                     timelineVersion=VERSION, generation=str(self.__generation), blockIndex=str(index), previousHash=previous, records=records)
        raw, hash_ = canonical_v2_bytes(block), hash_v2(block)
        self.__db.execute("INSERT OR IGNORE INTO blocks VALUES(?,?)", (hash_, raw))
        require(self.__db.execute("SELECT body FROM blocks WHERE hash=?", (hash_,)).fetchone()[0] == raw, "log", "IDENTITY_CONFLICT")
        return hash_

    def __evidence(self, old, through, groups, cancel, epoch):
        for group in groups:
            for row in group["events"]:
                source, ordinal = row["provenance"]["sourceId"], row["rawOrdinal"]
                existing = self.__db.execute("SELECT ordinal FROM fences WHERE source=?", (source,)).fetchone()
                if existing is None:
                    order = self.__db.execute("SELECT COUNT(*) FROM fences").fetchone()[0]
                    require(order < 128, "fence", "SOURCE_LIMIT")
                    self.__db.execute("INSERT INTO fences VALUES(?,?,?)", (source, ordinal, order))
                else:
                    require(int(ordinal) > int(existing[0]), "ordinal", "INVALID_SOURCE_ORDINAL")
                    self.__db.execute("UPDATE fences SET ordinal=? WHERE source=?", (ordinal, source))
        fence = [dict(sourceId=s, rawOrdinal=o) for s, o in self.__db.execute("SELECT source,ordinal FROM fences ORDER BY sourceOrder")]
        fence_map = {p["sourceId"]: int(p["rawOrdinal"]) for p in fence}
        records, low = [], old
        while True:
            high = min(through, low+WINDOW_NS)
            request = dict(schemaVersion=2, artifact="BTL-TICK-EVIDENCE-REQUEST-2", datasetId=self.__id, datasetVersion=self.__version,
                           manifestHash=self.__version, sessionStartNs=str(self.__start), fromNs=str(low), throughNs=str(high),
                           sourceFence=fence, maxRecords=128, cursor=None)
            query_hash, previous_position = hash_v2(request), None
            for _ in range(32769):
                cancel.check(); require(epoch == self.__epoch, "cancel", "CANCELLED")
                page = self.__provider.read_evidence_v2(deepcopy(request))
                keys(page, PAGE); canonical_v2_bytes(page)
                require(page["artifact"] == "BTL-TICK-EVIDENCE-PAGE-2" and page["datasetId"] == self.__id
                        and page["datasetVersion"] == self.__version and page["manifestHash"] == self.__version
                        and page["evidenceCatalogHash"] == self.__root["evidenceCatalogHash"] and page["requestHash"] == query_hash, "evidence", "IDENTITY_CONFLICT")
                expected_coverage = [] if request["cursor"] is not None or low == high else [dict(startNs=str(low), endNs=str(high), status="UNKNOWN", evidenceHash=None)]
                require(page["coverage"] == expected_coverage, "coverage", "COVERAGE_CONFLICT")
                d = page["diagnostics"]
                keys(d, "records counts truncated")
                require(type(d["records"]) is list and type(d["counts"]) is dict and all(type(v) is int for v in d["counts"].values())
                        and len(d["records"])+len(page["coverage"]) <= 128
                        and d["truncated"] is False and d["counts"] == diagnostic_counts(d["records"]), "diagnostics", "INCOMPLETE_DIAGNOSTICS")
                for record in d["records"]:
                    keys(record, "sourceId memberHash rawOrdinal timeNs code rawRecordHash")
                    uint(record["timeNs"]); uint(record["rawOrdinal"])
                    digest(record["memberHash"], "memberHash"); digest(record["rawRecordHash"], "rawRecordHash")
                    require(eligible(record, request, fence_map), "diagnostic", "INCOMPLETE_DIAGNOSTICS")
                    identity = (record["sourceId"], record["rawOrdinal"], record["code"])
                    body = json.dumps(record, sort_keys=True, separators=(",", ":"))
                    prior = self.__db.execute("SELECT body FROM delivered WHERE source=? AND ordinal=? AND code=?", identity).fetchone()
                    require(prior is None or prior[0] == body, "diagnostic", "IDENTITY_CONFLICT")
                    duplicate = self.__db.execute("SELECT body FROM page_diagnostics WHERE source=? AND ordinal=? AND code=?", identity).fetchone()
                    require(duplicate is None or duplicate[0] == body, "diagnostic", "IDENTITY_CONFLICT")
                    inserted = self.__db.execute("INSERT OR IGNORE INTO delivered VALUES(?,?,?,?)", (*identity, body))
                    if inserted.rowcount:
                        records.append(deepcopy(record))
                        require(len(records) <= 128, "reveal", "EVIDENCE_LIMIT")
                successor = page["nextCursor"]
                if successor is None:
                    break
                keys(successor, CURSOR); canonical_v2_bytes(successor)
                require(successor["artifact"] == "BTL-TICK-EVIDENCE-CURSOR-2" and all(successor[k] == page[k] for k in
                        ("datasetId", "datasetVersion", "manifestHash", "evidenceCatalogHash", "requestHash")), "cursor", "IDENTITY_CONFLICT")
                position = (uint(successor["blockIndex"]), uint(successor["entryOffset"]))
                require(position[0] < 256 and position[1] < 128 and (previous_position is None or position > previous_position), "cursor", "CORRUPT_INDEX_POINTER")
                previous_position = position
                request["cursor"] = deepcopy(successor)
            else:
                require(False, "pagination", "CORRUPT_INDEX_POINTER")
            if high == through:
                break
            low = high
        # Tick-page duplicates are never another reveal owner. Eligible copies
        # must have a byte-identical accepted sidecar record; future copies stay
        # private until their fence/time becomes eligible.
        final_request = dict(request, throughNs=str(through))
        for source, ordinal, code, body in self.__db.execute("SELECT source,ordinal,code,body FROM page_diagnostics"):
            record = json.loads(body)
            if eligible(record, final_request, fence_map):
                accepted = self.__db.execute("SELECT body FROM delivered WHERE source=? AND ordinal=? AND code=?", (source, ordinal, code)).fetchone()
                require(accepted is not None and accepted[0] == body, "diagnostic", "INCOMPLETE_DIAGNOSTICS")
        return dict(records=records, counts=diagnostic_counts(records), truncated=False)

    def __blocks(self, tip, artifact):
        expected = None
        while tip is not None:
            row = self.__db.execute("SELECT body FROM blocks WHERE hash=?", (tip,)).fetchone()
            require(row is not None, "log", "INCOMPLETE_INGESTION")
            block = decode_v2(row[0])
            keys(block, "schemaVersion artifact datasetId datasetVersion timelineVersion generation blockIndex previousHash records")
            require(hash_v2(block) == tip and block["artifact"] == artifact, "log", "IDENTITY_CONFLICT")
            require(block["datasetId"] == self.__id and block["datasetVersion"] == self.__version and block["timelineVersion"] == VERSION
                    and block["generation"] == str(self.__generation), "log", "VERSION_MISMATCH")
            index = uint(block["blockIndex"])
            require(expected is None or index == expected-1, "log", "INCOMPLETE_INGESTION")
            require(type(block["records"]) is list and 1 <= len(block["records"]) <= 128, "log", "ARTIFACT_LIMIT")
            require((index == 0) == (block["previousHash"] is None), "log", "INCOMPLETE_INGESTION")
            yield block
            expected, tip = index, block["previousHash"]

    def advance_through(self, target_ns, expected_cursor, cancellation=None):
        require(self.__active, "timeline", "REPLACED_TIMELINE")
        keys(expected_cursor, "schemaVersion artifact " + CURSOR_FIELDS)
        canonical_v2_bytes(expected_cursor)
        target = uint(target_ns)
        require(expected_cursor == self.__cursor, "cursor", "STALE_CURSOR")
        require(target >= int(self.__cursor["throughNs"]), "target", "BACKWARD_ADVANCE")
        require(self.__cursor["pendingTargetNs"] in (None, target_ns), "target", "ADVANCE_IN_PROGRESS")
        cancel = cancellation or Cancellation(); cancel.check()
        epoch, old = self.__epoch, int(self.__cursor["throughNs"])
        packed = CanonicalGroupBudget("BTL-TICK-STEP-CHECK-2")
        groups, positions = packed.groups, []
        try:
            while (pending := self.__peek()) is not None and int(pending[1]["timeNs"]) <= target:
                cancel.check(); require(epoch == self.__epoch, "cancel", "CANCELLED")
                if len(groups) == 64:
                    break
                try:
                    packed.append(pending[1])
                except ValueError:
                    require(bool(groups), "group", "GROUP_LIMIT")
                    break
                positions.append(pending[0])
                self.__has_pending = False
            pending = self.__peek()
            done = pending is None or int(pending[1]["timeNs"]) > target
            through = target if done else int(groups[-1]["timeNs"]) if groups else old
            coverage = [] if through == old else [dict(startNs=str(old), endNs=str(through), status="UNKNOWN", evidenceHash=None)]
            diagnostics, updated = self.__evidence(old, through, groups, cancel, epoch), self.cursor
            noop = not groups and not diagnostics["records"] and through == old and updated["pendingTargetNs"] is None
            if not noop:
                step = dict(schemaVersion=2, artifact="BTL-TICK-PREFIX-STEP-2", previousHash=updated["visiblePrefixHash"], throughNs=str(through),
                            groups=groups, coverage=coverage, diagnostics=diagnostics)
                updated.update(revision=str(int(updated["revision"])+1), throughNs=str(through), nextGroupIndex=str(int(updated["nextGroupIndex"])+len(groups)),
                               lastGroupId=groups[-1]["groupId"] if groups else updated["lastGroupId"], pendingTargetNs=None if done else target_ns,
                               visiblePrefixHash=hash_v2(step))
            result = dict(schemaVersion=2, artifact="BTL-TICK-REVEAL-2", datasetId=self.__id, datasetVersion=self.__version, timelineVersion=VERSION,
                          generation=updated["generation"], sessionStartNs=str(self.__start), targetNs=target_ns, throughNs=str(through), groups=groups,
                          coverage=coverage, diagnostics=diagnostics, visiblePrefixHash=updated["visiblePrefixHash"], cursor=updated, exhaustedThroughBoundary=done)
            canonical_v2_bytes(result)
            cancel.check(); require(epoch == self.__epoch, "cancel", "CANCELLED")
            advance_tip, position_tip = self.__advance_tip, self.__position_tip
            if not noop:
                cursor_hash = hash_v2(updated)
                advance_tip = self.__append_block("BTL-TICK-ADVANCE-LOG-2", self.__advance_blocks, advance_tip,
                                                 [dict(targetNs=target_ns, predecessorCursorHash=hash_v2(self.__cursor), successorCursorHash=cursor_hash)])
                if groups:
                    start_index = int(self.__cursor["nextGroupIndex"])
                    position_tip = self.__append_block("BTL-TICK-POSITION-LOG-2", self.__position_blocks, position_tip,
                        [dict(groupIndex=str(start_index+i), position=p, groupId=g["groupId"], successorCursorHash=cursor_hash)
                         for i, (p, g) in enumerate(zip(positions, groups))])
                    self.__db.executemany("INSERT INTO position_lookup VALUES(?,?,?)", [(start_index+i, position_tip, i) for i in range(len(groups))])
                persisted = dict(schemaVersion=2, artifact="BTL-TICK-CHECKPOINT-2", cursor=updated,
                                 advanceLogHash=advance_tip, positionLogHash=position_tip)
                self.__db.execute("INSERT OR REPLACE INTO heads VALUES(1,?)", (canonical_v2_bytes(persisted),))
                self.__db.commit()
            else:
                self.__db.rollback()
        except BaseException:
            self.__db.rollback()
            self.__restore()
            raise
        if not noop:
            self.__advance_tip, self.__position_tip = advance_tip, position_tip
            self.__advance_blocks += 1; self.__position_blocks += bool(groups)
        self.__cursor = updated
        self.__next_position = None if pending is None else pending[0]
        return deepcopy(result)

    def next_group(self, expected_cursor, cancellation=None):
        require(expected_cursor == self.__cursor and self.__cursor["pendingTargetNs"] is None, "cursor", "STALE_CURSOR")
        (cancellation or Cancellation()).check()
        pending = self.__peek()
        return self.advance_through(self.__cursor["throughNs"] if pending is None else pending[1]["timeNs"], expected_cursor, cancellation)

    def read_revealed(self, from_group_index="0", max_groups=64):
        require(self.__active, "timeline", "REPLACED_TIMELINE")
        start = uint(from_group_index)
        require(type(max_groups) is int and 1 <= max_groups <= 1024, "groups")
        end = int(self.__cursor["nextGroupIndex"])
        require(start <= end, "index", "UNREVEALED_INDEX")
        wanted, records = min(end, start+max_groups), []
        # Rebuildable connection-private disk index. Membership is checked
        # against canonical hash-bound blocks produced by committed reveals.
        for index, block_hash, offset in self.__db.execute("SELECT groupIndex,blockHash,recordOffset FROM position_lookup WHERE groupIndex>=? AND groupIndex<? ORDER BY groupIndex", (start, wanted)):
            stored = self.__db.execute("SELECT body FROM blocks WHERE hash=?", (block_hash,)).fetchone()
            require(stored is not None, "log", "INCOMPLETE_INGESTION")
            block = decode_v2(stored[0])
            require(hash_v2(block) == block_hash and block["artifact"] == "BTL-TICK-POSITION-LOG-2"
                    and block["datasetId"] == self.__id and block["datasetVersion"] == self.__version
                    and block["timelineVersion"] == VERSION and block["generation"] == str(self.__generation), "membership", "IDENTITY_CONFLICT")
            require(0 <= offset < len(block["records"]), "membership", "CORRUPT_INDEX_POINTER")
            record = block["records"][offset]
            keys(record, "groupIndex position groupId successorCursorHash")
            require(uint(record["groupIndex"]) == index, "membership", "IDENTITY_CONFLICT")
            records.append(record)
        require(len(records) == wanted-start, "prefix", "INCOMPLETE_ATOMIC_BOUNDARY")
        records.sort(key=lambda r: int(r["groupIndex"]))
        packed = CanonicalGroupBudget("BTL-TICK-VIEW-CHECK-2")
        groups = packed.groups
        # Membership records form one contiguous acknowledged prefix. Stream
        # it once instead of rereading a whole provider page for every group.
        observed = self.__groups(records[0]["position"]) if records else iter(())
        for record in records:
            position, group = next(observed)
            require(position == record["position"] and group["groupId"] == record["groupId"]
                    and int(group["timeNs"]) <= int(self.__cursor["throughNs"]), "prefix", "IDENTITY_CONFLICT")
            try:
                packed.append(group)
            except ValueError:
                require(bool(groups), "group", "GROUP_LIMIT")
                break
        return deepcopy(groups)

    def reset(self, session_start_ns=None):
        require(self.__active, "timeline", "REPLACED_TIMELINE")
        if session_start_ns is not None:
            self.__start = uint(session_start_ns)
        self.cancel(); self.__generation += 1; self.__initialize()
        return self.cursor

    def cancel(self):
        self.__epoch += 1

    def seek(self, target_ns, cancellation=None):
        require(uint(target_ns) >= self.__start, "target", "BEFORE_SESSION_START")
        self.reset()
        while True:
            result = self.advance_through(target_ns, self.cursor, cancellation)
            if result["exhaustedThroughBoundary"]:
                return result

    def replace_dataset(self, provider, dataset_id, dataset_version, session_start_ns="0", *, log_folder):
        require(self.__active, "timeline", "REPLACED_TIMELINE")
        replacement = IndexedTickTimeline(provider, dataset_id, dataset_version, session_start_ns, log_folder=log_folder)
        replacement.__generation = self.__generation+1; replacement.__initialize()
        self.cancel(); self.__active = False
        return replacement

    def checkpoint(self):
        require(self.__active, "timeline", "REPLACED_TIMELINE")
        return dict(schemaVersion=2, artifact="BTL-TICK-CHECKPOINT-2", cursor=self.cursor,
                    advanceLogHash=self.__advance_tip, positionLogHash=self.__position_tip)

    @classmethod
    def resume(cls, provider, checkpoint, *, log_folder, allow_threads=False):
        keys(checkpoint, "schemaVersion artifact cursor advanceLogHash positionLogHash")
        require(checkpoint["artifact"] == "BTL-TICK-CHECKPOINT-2", "checkpoint", "SCHEMA_MISMATCH")
        canonical_v2_bytes(checkpoint)
        cursor = checkpoint["cursor"]
        keys(cursor, "schemaVersion artifact " + CURSOR_FIELDS)
        require(cursor["artifact"] == "BTL-TICK-CURSOR-2" and cursor["timelineVersion"] == VERSION, "cursor", "SCHEMA_MISMATCH")
        result = cls(provider, cursor["datasetId"], cursor["datasetVersion"], cursor["sessionStartNs"], log_folder=log_folder, allow_threads=allow_threads)
        try:
            return result.__reconstruct(checkpoint, cursor)
        except BaseException:
            result.close()
            raise

    def __reconstruct(self, checkpoint, cursor):
        result = self
        result.__generation = uint(cursor["generation"]); result.__initialize()
        # Verify the ORIGINAL position chain before replay can regenerate any
        # blocks. Reconstruction must not silently repair a missing/corrupt
        # acknowledged log and turn incomplete durable evidence into success.
        remaining = uint(cursor["nextGroupIndex"])
        for block in result.__blocks(checkpoint["positionLogHash"], "BTL-TICK-POSITION-LOG-2"):
            for record in reversed(block["records"]):
                keys(record, "groupIndex position groupId successorCursorHash")
                remaining -= 1
                require(remaining >= 0 and uint(record["groupIndex"]) == remaining, "position_log", "INCOMPLETE_INGESTION")
                digest(record["groupId"], "groupId"); digest(record["successorCursorHash"], "cursorHash")
                position = record["position"]
                shape(position, "BTL-TICK-POSITION-2")
                require(position["datasetId"] == result.__id and position["datasetVersion"] == result.__version
                        and position["manifestHash"] == result.__version, "position_log", "VERSION_MISMATCH")
        require(remaining == 0, "position_log", "INCOMPLETE_INGESTION")
        result.__db.execute("CREATE TEMP TABLE reconstruction(blockIndex INTEGER PRIMARY KEY, record TEXT NOT NULL)")
        count = 0
        for block in result.__blocks(checkpoint["advanceLogHash"], "BTL-TICK-ADVANCE-LOG-2"):
            require(len(block["records"]) == 1, "advance_log", "SCHEMA_MISMATCH")
            record = block["records"][0]
            keys(record, "targetNs predecessorCursorHash successorCursorHash")
            result.__db.execute("INSERT INTO reconstruction VALUES(?,?)", (int(block["blockIndex"]), json.dumps(record)))
            count += 1
        require(count == uint(cursor["revision"]), "checkpoint", "INCOMPLETE_INGESTION")
        for (raw,) in result.__db.execute("SELECT record FROM reconstruction ORDER BY blockIndex"):
            record = json.loads(raw)
            require(hash_v2(result.cursor) == record["predecessorCursorHash"], "checkpoint", "IDENTITY_CONFLICT")
            result.advance_through(record["targetNs"], result.cursor)
            require(hash_v2(result.cursor) == record["successorCursorHash"], "checkpoint", "IDENTITY_CONFLICT")
        require(result.checkpoint() == checkpoint, "checkpoint", "IDENTITY_CONFLICT")
        result.__db.execute("DROP TABLE reconstruction")
        return result
