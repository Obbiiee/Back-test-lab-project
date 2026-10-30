"""Indexed, causal replay controller with private disk acknowledgement logs.

Preserves V1 runtime. No prices generated, execution, or account mutations.
"""
from copy import deepcopy
from pathlib import Path
import sqlite3
import json
import zlib
import re

from contracts.primitives import require, digest
from .contracts import keys, uint, CanonicalTick
from .contracts_v2 import canonical_v2_bytes, decode_v2, hash_v2, shape, CanonicalGroupBudget
from .provider import Cancellation, empty_diagnostics
from .timeline import CURSOR_FIELDS, RevealedView, make_group
from .storage_v2 import connect
from .evidence_v2 import PAGE, CURSOR, WINDOW_NS, ROW_LOCAL, CODES, eligible
from .provider import diagnostic_counts

VERSION = "BTL-TICK-TIMELINE-2"

_HASH_TEXT = re.compile(r"^[0-9a-f]{64}$")
_DELTA_KEYS = {"generation", "blockIndex", "groupIndex", "directoryIndex", "partitionIndex",
               "chunkIndex", "eventOffset", "globalOrdinal", "recordOffset", "targetNs",
               "rawOrdinal", "revision", "nextGroupIndex"}


def _varint(value):
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7f) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _read_varint(data, offset):
    value = shift = 0
    while offset < len(data) and shift <= 63:
        byte = data[offset]; offset += 1
        value |= (byte & 0x7f) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
    raise ValueError("CORRUPT_RECORD")


def _compact_block(raw):
    """Reversible block-local dictionary, numeric delta and binary-hash codec."""
    root = json.loads(raw)
    frequencies, order = {}, []
    def visit(value):
        if isinstance(value, str):
            if value not in frequencies: order.append(value); frequencies[value] = 0
            frequencies[value] += 1
        elif isinstance(value, list):
            for child in value: visit(child)
        elif isinstance(value, dict):
            for key, child in value.items(): visit(key); visit(child)
    visit(root)
    dictionary = [s for s in order if frequencies[s] >= 2 and len(s.encode("utf-8")) >= 4 and not _HASH_TEXT.fullmatch(s)]
    refs = {value: index for index, value in enumerate(dictionary)}
    out = bytearray(b"BTL-TIMELINE-DDZ-1\0")
    out.extend(_varint(len(dictionary)))
    for value in dictionary:
        encoded = value.encode("utf-8"); out.extend(_varint(len(encoded))); out.extend(encoded)
    previous = {}
    def string(value, key=None):
        if key in _DELTA_KEYS and value.isascii() and value.isdecimal():
            current = int(value); delta = current - previous.get(key, 0); previous[key] = current
            zigzag = 2 * delta if delta >= 0 else -2 * delta - 1
            out.append(5); out.extend(_varint(zigzag)); return
        if _HASH_TEXT.fullmatch(value):
            out.append(4); out.extend(bytes.fromhex(value)); return
        if value in refs:
            out.append(3); out.extend(_varint(refs[value])); return
        encoded = value.encode("utf-8"); out.append(2); out.extend(_varint(len(encoded))); out.extend(encoded)
    def node(value, key=None):
        if value is None: out.append(0)
        elif value is False: out.append(1)
        elif value is True: out.append(2)
        elif type(value) is int:
            out.append(6); out.extend(_varint(value))
        elif isinstance(value, str): out.append(9); string(value, key)
        elif isinstance(value, list):
            out.append(7); out.extend(_varint(len(value)))
            for child in value: node(child)
        elif isinstance(value, dict):
            out.append(8); out.extend(_varint(len(value)))
            for child_key, child in value.items(): string(child_key); node(child, child_key)
        else: raise ValueError("SCHEMA_MISMATCH")
    node(root)
    return bytes(out)


def _expand_compact_block(encoded):
    data = memoryview(encoded); offset = len(b"BTL-TIMELINE-DDZ-1\0")
    count, offset = _read_varint(data, offset)
    if count > 4096: raise ValueError("ARTIFACT_LIMIT")
    dictionary = []
    for _ in range(count):
        size, offset = _read_varint(data, offset)
        if size > 1048576 or offset + size > len(data): raise ValueError("CORRUPT_RECORD")
        dictionary.append(bytes(data[offset:offset+size]).decode("utf-8")); offset += size
    previous, node_count = {}, [0]
    def string(key=None):
        nonlocal offset
        if offset >= len(data): raise ValueError("CORRUPT_RECORD")
        tag = data[offset]; offset += 1
        if tag == 2:
            size, offset = _read_varint(data, offset)
            if size > 1048576 or offset + size > len(data): raise ValueError("CORRUPT_RECORD")
            value = bytes(data[offset:offset+size]).decode("utf-8"); offset += size
        elif tag == 3:
            index, offset = _read_varint(data, offset)
            if index >= len(dictionary): raise ValueError("CORRUPT_RECORD")
            value = dictionary[index]
        elif tag == 4:
            if offset + 32 > len(data): raise ValueError("CORRUPT_RECORD")
            value = bytes(data[offset:offset+32]).hex(); offset += 32
        elif tag == 5:
            zigzag, offset = _read_varint(data, offset)
            delta = zigzag // 2 if zigzag % 2 == 0 else -(zigzag // 2)-1
            value = str(previous.get(key, 0)+delta); previous[key] = int(value)
        else: raise ValueError("CORRUPT_RECORD")
        return value
    def node(key=None, depth=0):
        nonlocal offset
        if depth > 32: raise ValueError("ARTIFACT_LIMIT")
        node_count[0] += 1
        if node_count[0] > 16384: raise ValueError("ARTIFACT_LIMIT")
        if offset >= len(data): raise ValueError("CORRUPT_RECORD")
        tag = data[offset]; offset += 1
        if tag == 0: return None
        if tag == 1: return False
        if tag == 2: return True
        if tag == 9: return string(key)
        if tag == 6:
            value, offset = _read_varint(data, offset); return value
        if tag == 7:
            size, offset = _read_varint(data, offset)
            if size > 32768: raise ValueError("ARTIFACT_LIMIT")
            return [node(depth=depth+1) for _ in range(size)]
        if tag == 8:
            size, offset = _read_varint(data, offset)
            if size > 16384: raise ValueError("ARTIFACT_LIMIT")
            result = {}
            for _ in range(size):
                child_key = string()
                if child_key in result: raise ValueError("CORRUPT_RECORD")
                result[child_key] = node(child_key, depth+1)
            return result
        raise ValueError("CORRUPT_RECORD")
    result = node()
    if offset != len(data): raise ValueError("CORRUPT_RECORD")
    return result


class IndexedTickTimeline:
    def __init__(self, provider, dataset_id, dataset_version, session_start_ns="0", *, log_folder, allow_threads=False, log_codec=None, lookup_layout="dense", max_groups_per_advance=64):
        require(log_codec in (None, 'raw', 'zlib-1', 'delta-dict-zlib-1'), 'logCodec', 'INVALID_INPUT')
        require(lookup_layout in ('dense', 'range-v1'), 'lookupLayout', 'INVALID_INPUT')
        require(type(max_groups_per_advance) is int and 1 <= max_groups_per_advance <= 256,
                'maxGroupsPerAdvance', 'INVALID_INPUT')
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
        # Physical-only opt-in on NEW logs. Existing archives are never migrated.
        # Existing compressed logs identify themselves on cold resume; wire/hash
        # identity always refers to the original uncompressed canonical bytes.
        present = None
        if self.__log_path.exists():
            with sqlite3.connect(self.__log_path.resolve().as_uri()+'?mode=ro', uri=True) as probe:
                if probe.execute("SELECT 1 FROM sqlite_master WHERE name='log_layout'").fetchone():
                    rows = probe.execute('SELECT codec FROM log_layout').fetchall()
                    require(len(rows) == 1 and rows[0][0] in ('zlib-1', 'delta-dict-zlib-1'), 'logCodec', 'CORRUPT_RECORD')
                    present = rows[0][0]
                else:
                    present = 'raw'
        require(present is None or log_codec is None or present == log_codec,
                'logCodec', 'REFUSED_LOG_LAYOUT')
        self.__log_codec = present or log_codec or 'raw'
        self.__lookup_layout = lookup_layout
        self.__max_groups_per_advance = max_groups_per_advance
        self.__db = connect(self.__log_path, allow_threads=allow_threads)
        if self.__log_codec != 'raw':
            self.__db.execute('CREATE TABLE IF NOT EXISTS log_layout(codec TEXT PRIMARY KEY) WITHOUT ROWID')
            self.__db.execute("INSERT OR IGNORE INTO log_layout VALUES(?)", (self.__log_codec,))
        self.__db.execute("CREATE TABLE IF NOT EXISTS blocks(hash TEXT PRIMARY KEY, body BLOB NOT NULL) WITHOUT ROWID")
        self.__db.execute("CREATE TABLE IF NOT EXISTS heads(id INTEGER PRIMARY KEY CHECK(id=1), body BLOB NOT NULL)")
        self.__db.execute("CREATE TEMP TABLE fences(source TEXT PRIMARY KEY, ordinal TEXT NOT NULL, sourceOrder INTEGER NOT NULL) WITHOUT ROWID")
        self.__db.execute("CREATE TEMP TABLE delivered(source TEXT, ordinal TEXT, code TEXT, body TEXT NOT NULL, PRIMARY KEY(source,ordinal,code)) WITHOUT ROWID")
        self.__db.execute("CREATE TEMP TABLE page_diagnostics(source TEXT, ordinal TEXT, code TEXT, body TEXT NOT NULL, PRIMARY KEY(source,ordinal,code)) WITHOUT ROWID")
        if self.__lookup_layout == 'range-v1':
            self.__db.execute("CREATE TEMP TABLE position_lookup(groupStart INTEGER PRIMARY KEY, groupCount INTEGER NOT NULL, blockHash TEXT NOT NULL)")
        else:
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
        rows, time, group_position = [], None, None
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
            for offset, row in enumerate(page["events"]):
                CanonicalTick._validate(row)
                require(row["datasetVersion"] == self.__version and all(row[k] == self.__root[k] for k in
                        ("datasetId", "providerId", "feedId", "instrumentId")), "event", "IDENTITY_CONFLICT")
                require(int(row["timeNs"]) >= self.__start and (time is None or int(row["timeNs"]) >= int(time)), "time", "ORDER_REVERSAL")
                if time is not None and row["timeNs"] != time:
                    require(group_position is not None, "boundary", "INCOMPLETE_ATOMIC_BOUNDARY")
                    yield group_position, make_group(rows, self.__version)
                    rows, group_position = [], None
                if group_position is None:
                    # The page start is provider-validated. Its event offset and
                    # global ordinal give the exact first event of this atomic
                    # timestamp group without a second index lookup per group.
                    group_position = dict(position,
                                          eventOffset=str(int(position["eventOffset"])+offset),
                                          globalOrdinal=str(int(position["globalOrdinal"])+offset))
                time = row["timeNs"]
                rows.append(row)
                require(len(rows) <= 1024, "group", "GROUP_LIMIT")
            successor = page["nextPosition"]
            if successor is not None:
                require(successor != position and int(successor["globalOrdinal"]) == int(position["globalOrdinal"])+len(page["events"]), "position", "CORRUPT_INDEX_POINTER")
            position = successor
        if rows:
            require(group_position is not None, "boundary", "INCOMPLETE_ATOMIC_BOUNDARY")
            yield group_position, make_group(rows, self.__version)

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
        if self.__log_codec == 'zlib-1':
            body = b'BTL-TIMELINE-ZLIB-1\0'+zlib.compress(raw, 6)
        elif self.__log_codec == 'delta-dict-zlib-1':
            body = b'BTL-TIMELINE-DDZ-1\0'+zlib.compress(_compact_block(raw), 6)
        else:
            body = raw
        self.__db.execute("INSERT OR IGNORE INTO blocks VALUES(?,?)", (hash_, body))
        require(self.__read_block(hash_) == raw, "log", "IDENTITY_CONFLICT")
        return hash_

    def __read_block(self, hash_):
        # Bound both input and inflation before allocating an attacker-controlled
        # SQLite blob. A compressed stream must terminate exactly once, with no
        # trailing/concatenated stream. Canonical/hash checks remain unchanged.
        row = self.__db.execute('SELECT substr(body,1,1049601),length(body) FROM blocks WHERE hash=?', (hash_,)).fetchone()
        if row is None:
            return None
        body, size = row
        require(type(body) is bytes, 'log', 'CORRUPT_RECORD')
        require(size <= 1049600, 'log', 'ARTIFACT_LIMIT')
        if self.__log_codec in ('zlib-1', 'delta-dict-zlib-1'):
            prefix = b'BTL-TIMELINE-ZLIB-1\0' if self.__log_codec == 'zlib-1' else b'BTL-TIMELINE-DDZ-1\0'
            require(body.startswith(prefix), 'log', 'CORRUPT_RECORD')
            try:
                decoder = zlib.decompressobj()
                raw = decoder.decompress(body[len(prefix):], 1048577)
            except zlib.error:
                require(False, 'log', 'CORRUPT_RECORD')
            require(len(raw) <= 1048576 and decoder.eof and not decoder.unused_data
                    and not decoder.unconsumed_tail, 'log', 'CORRUPT_RECORD')
            if self.__log_codec == 'delta-dict-zlib-1':
                try:
                    logical = _expand_compact_block(raw)
                    canonical = canonical_v2_bytes(logical)
                except (UnicodeDecodeError, ValueError, OverflowError):
                    require(False, 'log', 'CORRUPT_RECORD')
                require(len(canonical) <= 1048576, 'log', 'ARTIFACT_LIMIT')
                return canonical
            return raw
        require(len(body) <= 1048576, 'log', 'ARTIFACT_LIMIT')
        return body

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
            row = self.__read_block(tip)
            require(row is not None, "log", "INCOMPLETE_INGESTION")
            block = decode_v2(row)
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
                if len(groups) >= self.__max_groups_per_advance:
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
                    position_block_count = 0
                    for offset in range(0, len(groups), 128):
                        stop = min(len(groups), offset + 128)
                        records = [dict(groupIndex=str(start_index+i), position=p, groupId=g["groupId"], successorCursorHash=cursor_hash)
                                   for i, (p, g) in enumerate(zip(positions[offset:stop], groups[offset:stop]), start=offset)]
                        position_tip = self.__append_block("BTL-TICK-POSITION-LOG-2", self.__position_blocks+position_block_count,
                                                            position_tip, records)
                        position_block_count += 1
                        if self.__lookup_layout == 'range-v1':
                            self.__db.execute("INSERT INTO position_lookup VALUES(?,?,?)", (start_index+offset, stop-offset, position_tip))
                        else:
                            self.__db.executemany("INSERT INTO position_lookup VALUES(?,?,?)",
                                [(start_index+i, position_tip, i-offset) for i in range(offset, stop)])
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
            self.__advance_blocks += 1
            if groups:
                self.__position_blocks += (len(groups)+127)//128
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
        if self.__lookup_layout == 'range-v1':
            anchors = self.__db.execute("SELECT groupStart,groupCount,blockHash FROM position_lookup WHERE groupStart<? AND groupStart+groupCount>? ORDER BY groupStart", (wanted, start))
            covered = start
            for group_start, group_count, block_hash in anchors:
                require(group_start <= covered < group_start+group_count, "membership", "INCOMPLETE_INGESTION")
                stored = self.__read_block(block_hash)
                require(stored is not None, "log", "INCOMPLETE_INGESTION")
                block = decode_v2(stored)
                require(hash_v2(block) == block_hash and block["artifact"] == "BTL-TICK-POSITION-LOG-2"
                        and block["datasetId"] == self.__id and block["datasetVersion"] == self.__version
                        and block["timelineVersion"] == VERSION and block["generation"] == str(self.__generation), "membership", "IDENTITY_CONFLICT")
                require(type(block["records"]) is list and len(block["records"]) == group_count, "membership", "CORRUPT_INDEX_POINTER")
                for offset, record in enumerate(block["records"]):
                    index = group_start+offset
                    if index < start or index >= wanted:
                        continue
                    keys(record, "groupIndex position groupId successorCursorHash")
                    require(uint(record["groupIndex"]) == index, "membership", "IDENTITY_CONFLICT")
                    records.append(record)
                    covered = index+1
            require(covered == wanted, "prefix", "INCOMPLETE_ATOMIC_BOUNDARY")
        else:
            for index, block_hash, offset in self.__db.execute("SELECT groupIndex,blockHash,recordOffset FROM position_lookup WHERE groupIndex>=? AND groupIndex<? ORDER BY groupIndex", (start, wanted)):
                stored = self.__read_block(block_hash)
                require(stored is not None, "log", "INCOMPLETE_INGESTION")
                block = decode_v2(stored)
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
        replacement = IndexedTickTimeline(provider, dataset_id, dataset_version, session_start_ns, log_folder=log_folder,
                                           log_codec=self.__log_codec, lookup_layout=self.__lookup_layout,
                                           max_groups_per_advance=self.__max_groups_per_advance)
        replacement.__generation = self.__generation+1; replacement.__initialize()
        self.cancel(); self.__active = False
        return replacement

    def checkpoint(self):
        require(self.__active, "timeline", "REPLACED_TIMELINE")
        return dict(schemaVersion=2, artifact="BTL-TICK-CHECKPOINT-2", cursor=self.cursor,
                    advanceLogHash=self.__advance_tip, positionLogHash=self.__position_tip)

    @classmethod
    def resume(cls, provider, checkpoint, *, log_folder, allow_threads=False, log_codec=None, lookup_layout="dense", max_groups_per_advance=64):
        keys(checkpoint, "schemaVersion artifact cursor advanceLogHash positionLogHash")
        require(checkpoint["artifact"] == "BTL-TICK-CHECKPOINT-2", "checkpoint", "SCHEMA_MISMATCH")
        canonical_v2_bytes(checkpoint)
        cursor = checkpoint["cursor"]
        keys(cursor, "schemaVersion artifact " + CURSOR_FIELDS)
        require(cursor["artifact"] == "BTL-TICK-CURSOR-2" and cursor["timelineVersion"] == VERSION, "cursor", "SCHEMA_MISMATCH")
        result = cls(provider, cursor["datasetId"], cursor["datasetVersion"], cursor["sessionStartNs"], log_folder=log_folder, allow_threads=allow_threads, log_codec=log_codec, lookup_layout=lookup_layout, max_groups_per_advance=max_groups_per_advance)
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
