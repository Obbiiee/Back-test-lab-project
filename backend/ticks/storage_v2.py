"""Local SQLite immutable content store + transactional bounded ingestion.

No API, execution, chart, or account imports. Completion is a private atomic
SQLite publication. Content payloads omit cyclical versions, materialized when
read; SHA-256 verifies every disk object. Staging remains non-authoritative.
"""
from bisect import bisect_left
from copy import deepcopy
from collections import OrderedDict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import zlib
from typing import Protocol

from contracts.primitives import require, digest
from .contracts import CanonicalTick, TickManifest, uint, keys
from .contracts_v2 import (ZERO_VERSION, canonical_v2_bytes, decode_v2, hash_v2,
                          payload, shape, validate_root, validate_container,
                          descriptors, interval_for, summary)
from .provider import empty_diagnostics, Cancellation
from .timeline import make_group
from .evidence_v2 import accept_sidecars, read_sidecars


class IndexedTickDataProvider(Protocol):
    def describe_v2(self, dataset_id: str, dataset_version: str) -> dict: ...
    def locate_v2(self, dataset_id: str, dataset_version: str, target_ns: str) -> dict: ...
    def read_page_v2(self, dataset_id: str, dataset_version: str, position: dict | None, max_events: int) -> dict: ...
    def read_evidence_v2(self, request: dict) -> dict: ...


def connect(path, *, allow_threads=False):
    # Cross-worker use is opt-in and requires the controller's shared RLock.
    db = sqlite3.connect(path, check_same_thread=not allow_threads)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("PRAGMA cache_size=-2048" if allow_threads else "PRAGMA cache_size=-8192")
    db.execute("PRAGMA temp_store=FILE")
    db.execute("PRAGMA mmap_size=0")
    return db


class ArtifactStore:
    def __init__(self, folder, *, create=False, allow_threads=False):
        self.folder = Path(folder).resolve()
        if create:
            self.folder.mkdir(parents=True, exist_ok=True)
        require((self.folder / "archive.sqlite").is_file() or create, "store", "INCOMPLETE_INGESTION")
        self.db = connect(self.folder / "archive.sqlite", allow_threads=allow_threads)
        if create:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS objects(hash TEXT PRIMARY KEY, body BLOB NOT NULL, kind TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS publications(version TEXT PRIMARY KEY, root BLOB NOT NULL, receipt BLOB NOT NULL, binding BLOB NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS journal(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS identities(event BLOB PRIMARY KEY, digest BLOB NOT NULL, source TEXT NOT NULL, ordinal TEXT NOT NULL, UNIQUE(source,ordinal)) WITHOUT ROWID;
            """)
            self.db.commit()

    def close(self):
        self.db.close()

    def put(self, artifact):
        # shape validates the full envelope once. Strip cyclical versions from
        # its already normalized JSON, preserving the exact canonical bytes.
        normalized = json.loads(shape(artifact, return_bytes=True))
        raw = json.dumps(payload(normalized), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
        require(len(raw) <= 1048576, "serializedSize", "ARTIFACT_LIMIT")
        hash_ = hashlib.sha256(raw).hexdigest()
        self.db.execute("INSERT OR IGNORE INTO objects VALUES(?,?,?)", (hash_, zlib.compress(raw, 1), artifact["artifact"]))
        # Collision / alternate compressed delivery must never overwrite bytes.
        require(self.raw(hash_) == raw, "object", "IDENTITY_CONFLICT")
        return hash_

    def raw(self, hash_):
        digest(hash_, "object_hash")
        stored = self.db.execute("SELECT body FROM objects WHERE hash=?", (hash_,)).fetchone()
        require(stored is not None, "object", "MISSING_CHILD")
        decoder = zlib.decompressobj()
        raw = decoder.decompress(stored[0], 1048577)
        require(len(raw) <= 1048576 and decoder.eof and not decoder.unused_data
                and not decoder.unconsumed_tail, "compressed", "ARTIFACT_LIMIT")
        require(hashlib.sha256(raw).hexdigest() == hash_, "object", "CHILD_HASH_MISMATCH")
        return raw

    def get(self, hash_, version):
        obj = decode_v2(self.raw(hash_))
        obj["datasetVersion"] = version
        for event in obj.get("events", []):
            event["datasetVersion"] = version
        shape(obj)
        return obj

    def save_journal(self, state):
        raw = json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False)
        require(len(raw.encode()) <= 8*1048576, "journal", "ARTIFACT_LIMIT")
        self.db.execute("INSERT OR REPLACE INTO journal VALUES('ingestion',?)", (raw,))
        self.db.commit()

    def journal(self):
        row = self.db.execute("SELECT value FROM journal WHERE key='ingestion'").fetchone()
        return None if row is None else json.loads(row[0])


def header(metadata, version=ZERO_VERSION):
    return dict(schemaVersion=2, datasetVersion=version,
                **{k: metadata[k] for k in ("datasetId", "providerId", "feedId", "instrumentId")})


def index_descriptor(index, obj, d, store):
    return dict(index=str(index), hash=store.put(obj), firstNs=d["firstNs"], lastNs=d["lastNs"])


def validate_sources(root, sources):
    # Reuse exact V1 source/ordering/evidence validators, not another source schema.
    m = {k: root[k] for k in ("datasetId", "providerId", "feedId", "instrumentId", "providerSymbol", "evidenceClass", "adapterVersion", "validatorVersion", "range", "ordering")}
    start = root["range"]["startNs"]
    m.update(schemaVersion=1, artifact="BTL-TICK-MANIFEST-1", sources=sources, coverage=[], gaps=[], diagnostics=[],
             rights=dict(**{"class": "SYNTHETIC" if root["evidenceClass"] == "SYNTHETIC_CONTRACT_ONLY" else "UNKNOWN", "evidenceHash": None}),
             chunks=[dict(chunkIndex="0", hash=ZERO_VERSION, eventCount=1, firstNs=start, lastNs=start)])
    TickManifest.from_wire(m)


def _copy_validated_tick(row):
    # CanonicalTick._validate has already proved this fixed schema: every value
    # is immutable except these two flat dictionaries. Copy all mutable levels
    # explicitly while retaining the same isolation as deepcopy.
    return dict(row, provenance=dict(row["provenance"]), quality=dict(row["quality"]))


class DatasetBuilder:
    """One chunk/group + bounded ancestors. Dataset identity uniqueness on disk.

    Sizes are packing choices <= frozen limits, not changed contract limits.
    Checkpoints commit at storage chunks; bounded unfinished tie state persists.
    Generic builder currently rejects malformed input rather than quarantining.
    """
    def __init__(self, folder, metadata, sources, source_pin, *, packing=(256, 256, 1024), resume=False):
        require(len(packing) == 3 and all(type(v) is int and 1 <= v <= limit for v, limit in zip(packing, (256, 256, 1024))), "packing")
        self.store = ArtifactStore(folder, create=True)
        try:
            old = self.store.journal()
            pin = dict(metadata=metadata, sources=sources, sourcePin=source_pin, packing=list(packing))
            if old is not None:
                require(resume and old["pin"] == pin and old["state"] != "COMPLETE", "resume", "INCOMPLETE_INGESTION")
                self.s = old
                # All committed content is hash-verified before accepting resumed offsets.
                for hash_, in self.store.db.execute("SELECT hash FROM objects"):
                    self.store.raw(hash_)
                require(self.store.db.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == old["count"], "resume", "IDENTITY_CONFLICT")
            else:
                self.s = dict(pin=pin, state="INGESTING", count=0, sourceOffset=0, chunk=[], chunks=[], partitions=[],
                              directories=[], indexChunks=[], indexPartitions=[], indexDirectories=[], group=[], groupStart=None,
                              previousTime=None, previousSource=-1, previousOrdinal=-1, previousSequence=None,
                              firstNs=None, lastNs=None, ties=0, tieGroups=0, groups=0, maxGroup=0)
                self.store.save_journal(self.s)
            self.meta, self.sources, self.packing = metadata, sources, packing
            self.h = header(metadata)
            self.source_map = {s["sourceId"]: (i, s) for i, s in enumerate(sources)}
            require(1 <= len(sources) <= 128 and len(self.source_map) == len(sources), "sources", "SOURCE_LIMIT")
        except BaseException:
            self.store.close()
            raise

    def _group_end(self):
        if self.s["group"]:
            make_group(self.s["group"], ZERO_VERSION)
            n = len(self.s["group"])
            self.s["groups"] += 1
            self.s["tieGroups"] += n > 1
            self.s["maxGroup"] = max(n, self.s["maxGroup"])

    def append(self, row, *, source_offset=0):
        require(self.s["state"] == "INGESTING", "state", "INCOMPLETE_INGESTION")
        require(row["datasetVersion"] == ZERO_VERSION, "provisional", "VERSION_MISMATCH")
        raw = CanonicalTick._validate(row)
        event_digest = hashlib.sha256(raw).digest()
        event_key = bytes.fromhex(row["eventId"])
        seen = self.store.db.execute("SELECT digest FROM identities WHERE event=?", (event_key,)).fetchone()
        require(seen is None, "identity", "DUPLICATE_DELIVERY" if seen and seen[0] == event_digest else "IDENTITY_CONFLICT")
        for field in ("datasetId", "providerId", "feedId", "instrumentId"):
            require(row[field] == self.meta[field], field, "IDENTITY_CONFLICT")
        source = self.source_map.get(row["provenance"]["sourceId"])
        require(source is not None and source[1]["memberHash"] == row["provenance"]["memberHash"]
                and source[1]["resolutionNs"] == row["resolutionNs"], "source", "IDENTITY_CONFLICT")
        ordinal, time = int(row["rawOrdinal"]), int(row["timeNs"])
        require(source[0] >= self.s["previousSource"] and (source[0] != self.s["previousSource"] or ordinal > self.s["previousOrdinal"]), "ordinal", "INVALID_SOURCE_ORDINAL")
        require(self.s["previousTime"] is None or time >= self.s["previousTime"], "time", "ORDER_REVERSAL")
        sequence = row["trustedSequence"]
        order = self.meta["ordering"]
        require(sequence is None or order["sequenceEvidenceHash"] is not None, "sequence", "MISSING_EVIDENCE_REFERENCE")
        require(order["ties"] != "TRUSTED_SEQUENCE" or sequence is not None, "sequence", "INVALID_TRUSTED_SEQUENCE")
        if self.s["previousTime"] != time:
            self._group_end()
            self.s["group"], self.s["previousSequence"] = [], None
            self.s["groupStart"] = dict(directoryIndex=str(len(self.s["directories"])), partitionIndex=str(len(self.s["partitions"])),
                                        chunkIndex=str(len(self.s["chunks"])), eventOffset=str(len(self.s["chunk"])),
                                        globalOrdinal=str(self.s["count"]), timeNs=row["timeNs"])
        else:
            self.s["ties"] += 1
        require(sequence is None or self.s["previousSequence"] is None or int(sequence) > int(self.s["previousSequence"]), "sequence", "INVALID_TRUSTED_SEQUENCE")
        if sequence is not None:
            self.s["previousSequence"] = sequence
        self.s["group"].append(_copy_validated_tick(row))
        require(len(self.s["group"]) <= 1024, "group", "GROUP_LIMIT")
        require(row["quality"]["duplicateOf"] is None or self.store.db.execute("SELECT 1 FROM identities WHERE event=?", (bytes.fromhex(row["quality"]["duplicateOf"]),)).fetchone() is not None, "duplicate", "UNVERIFIED_DUPLICATE_REFERENCE")
        try:
            self.store.db.execute("INSERT INTO identities VALUES(?,?,?,?)", (event_key, event_digest, row["provenance"]["sourceId"], row["rawOrdinal"]))
        except sqlite3.IntegrityError:
            require(False, "ordinal", "INVALID_SOURCE_ORDINAL")
        if not self.s["chunk"]:
            self.s["chunkAnchor"] = deepcopy(self.s["groupStart"])
        self.s["chunk"].append(_copy_validated_tick(row))
        self.s["firstNs"] = self.s["firstNs"] or row["timeNs"]
        self.s["lastNs"] = row["timeNs"]
        self.s["previousTime"], self.s["previousSource"], self.s["previousOrdinal"] = time, source[0], ordinal
        self.s["count"] += 1
        self.s["sourceOffset"] = source_offset
        if len(self.s["chunk"]) >= self.packing[0]:
            self._flush_chunk()
            # Transaction granularity is an implementation choice, not a wire
            # change. Keep a bounded <=4096-record uncommitted tail, FULL fsync.
            if self.s["count"] % (self.packing[0]*16) == 0:
                self.store.save_journal(self.s)

    def _flush_chunk(self):
        if not self.s["chunk"]:
            return
        di, pi, ci = len(self.s["directories"]), len(self.s["partitions"]), len(self.s["chunks"])
        require(di < 256, "capacity", "ARTIFACT_LIMIT")
        chunk = dict(self.h, artifact="BTL-TICK-STORAGE-CHUNK-2", directoryIndex=str(di), partitionIndex=str(pi), chunkIndex=str(ci),
                     firstOrdinal=str(self.s["count"]-len(self.s["chunk"])), events=self.s["chunk"])
        # put validates the full envelope AND versionless payload budgets, writes
        # and hash-verifies bytes; reuse that proven hash rather than encode twice.
        d = summary(ci, chunk, verified_hash=self.store.put(chunk))
        self.s["chunks"].append(d)
        self.s["indexChunks"].append(dict(chunkIndex=str(ci), chunkHash=d["hash"], firstNs=d["firstNs"], lastNs=d["lastNs"],
                                           firstOrdinal=d["firstOrdinal"], lastOrdinal=d["lastOrdinal"], firstGroupStart=self.s["chunkAnchor"]))
        self.s["chunk"] = []
        if len(self.s["chunks"]) == self.packing[1]:
            self._flush_partition()

    def _flush_partition(self):
        if not self.s["chunks"]:
            return
        di, pi = len(self.s["directories"]), len(self.s["partitions"])
        part = dict(self.h, artifact="BTL-TICK-PARTITION-2", directoryIndex=str(di), partitionIndex=str(pi),
                    range=interval_for(self.s["chunks"]), eventCount=str(sum(int(d["eventCount"]) for d in self.s["chunks"])), children=self.s["chunks"])
        d = summary(pi, part, verified_hash=self.store.put(part))
        leaf = dict(self.h, artifact="BTL-TICK-TIME-PARTITION-2", directoryIndex=str(di), partitionIndex=str(pi),
                    partitionHash=d["hash"], chunks=self.s["indexChunks"])
        self.s["partitions"].append(d)
        self.s["indexPartitions"].append(index_descriptor(pi, leaf, d, self.store))
        self.s["chunks"], self.s["indexChunks"] = [], []
        if len(self.s["partitions"]) == self.packing[2]:
            self._flush_directory()

    def _flush_directory(self):
        if not self.s["partitions"]:
            return
        di = len(self.s["directories"])
        obj = dict(self.h, artifact="BTL-TICK-DIRECTORY-2", directoryIndex=str(di),
                   range=interval_for(self.s["partitions"]), eventCount=str(sum(int(d["eventCount"]) for d in self.s["partitions"])), children=self.s["partitions"])
        d = summary(di, obj, verified_hash=self.store.put(obj))
        index = dict(self.h, artifact="BTL-TICK-TIME-DIRECTORY-2", directoryIndex=str(di), children=self.s["indexPartitions"])
        self.s["directories"].append(d)
        self.s["indexDirectories"].append(index_descriptor(di, index, d, self.store))
        self.s["partitions"], self.s["indexPartitions"] = [], []

    def finish(self, *, verify_source=None, cancellation=None, evidence_blocks=None, audit_record=None):
        started = time.perf_counter()
        self.timings = {}
        cancel = cancellation or Cancellation()
        cancel.check()
        require(self.s["count"] > 0, "empty", "EMPTY_DATASET")
        if self.s["state"] == "INGESTING":
            self._group_end()
            self._flush_chunk(); self._flush_partition(); self._flush_directory()
            self.s["state"] = "VALIDATING"
            self.store.save_journal(self.s)
        require(self.s["state"] in ("VALIDATING", "INDEXING", "FINALIZING"), "state", "INCOMPLETE_INGESTION")
        self.s["state"] = "INDEXING"; self.store.save_journal(self.s)
        source = dict(self.h, artifact="BTL-TICK-SOURCE-CATALOG-2", sources=self.sources)
        evidence = dict(self.h, artifact="BTL-TICK-EVIDENCE-CATALOG-2", children=[])
        if evidence_blocks is not None:
            # Iterator input, never a history-sized list of sidecar bodies.
            for i, body in enumerate(evidence_blocks):
                require(i < 256, "blocks", "EVIDENCE_LIMIT")
                block = dict(body, **self.h)
                require(block["blockIndex"] == str(i), "block", "CORRUPT_INDEX_POINTER")
                first, last, count = None, None, 0
                for kind in ("coverage", "gaps", "diagnostics"):
                    for row in block[kind]:
                        lo = uint(row["timeNs"] if kind == "diagnostics" else row["startNs"])
                        hi = lo if kind == "diagnostics" else uint(row["endNs"])-1
                        first = lo if first is None else min(first, lo)
                        last = hi if last is None else max(last, hi)
                        count += 1
                require(count <= 128, "block", "EVIDENCE_LIMIT")
                if first is None:
                    first = last = int(self.s["firstNs"])
                evidence["children"].append(dict(index=str(i), hash=self.store.put(block), firstNs=str(first), lastNs=str(last), recordCount=str(count)))
        prior_evidence = self.s.get("evidenceCatalogHash")
        evidence_hash = self.store.put(evidence)
        if prior_evidence is not None:
            if evidence_blocks is None:
                evidence_hash = prior_evidence
            else:
                require(evidence_hash == prior_evidence, "resume_evidence", "IDENTITY_CONFLICT")
        self.s["evidenceCatalogHash"] = evidence_hash
        self.store.save_journal(self.s)
        index = dict(self.h, artifact="BTL-TICK-TIME-ROOT-2", children=self.s["indexDirectories"])
        root = dict(schemaVersion=2, artifact="BTL-TICK-DATASET-2", **self.meta,
                    range=interval_for(self.s["directories"]), eventCount=str(self.s["count"]), directories=self.s["directories"],
                    sourceCatalogHash=self.store.put(source), evidenceCatalogHash=evidence_hash, indexContentHash=self.store.put(index))
        validate_root(root); validate_sources(root, self.sources)
        version = hash_v2(root)
        self.s["state"] = "FINALIZING"; self.store.save_journal(self.s)
        self.timings["finalMetadataSeconds"] = time.perf_counter()-started
        # Stream every immutable edge/body and boundary before publishing. Identity
        # uniqueness has already been validated in the committed disk UNIQUE table.
        validation_started = time.perf_counter()
        self._verify_tree(root, version, cancel)
        accept_sidecars(self.store, root, version, self.sources, audit_record=audit_record, cancellation=cancel)
        require(self.store.db.execute("SELECT COUNT(*) FROM identities").fetchone()[0] == self.s["count"], "identities", "IDENTITY_CONFLICT")
        if verify_source is not None:
            require(verify_source() == self.s["pin"]["sourcePin"], "source", "IDENTITY_CONFLICT")
        self.timings["finalValidationIncludingSourceHashSeconds"] = time.perf_counter()-validation_started
        cancel.check()
        publication_started = time.perf_counter()
        receipt = dict(schemaVersion=2, artifact="BTL-TICK-COMPLETION-2", datasetId=root["datasetId"], datasetVersion=version,
                       manifestHash=version, validatorVersion=root["validatorVersion"], indexContentHash=root["indexContentHash"], sourceCatalogHash=root["sourceCatalogHash"])
        binding = dict(schemaVersion=2, artifact="BTL-TICK-INDEX-BINDING-2", datasetId=root["datasetId"], datasetVersion=version,
                       manifestHash=version, indexContentHash=root["indexContentHash"])
        self.store.db.execute("INSERT INTO publications VALUES(?,?,?,?)", (version, canonical_v2_bytes(root), canonical_v2_bytes(receipt), canonical_v2_bytes(binding)))
        self.s["state"] = "COMPLETE"
        self.store.save_journal(self.s)  # same FULL synchronous transaction as publication
        self.store.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.timings["publicationSeconds"] = time.perf_counter()-publication_started
        return version

    def _verify_tree(self, root, version, cancel):
        previous, first_ordinal, group_anchor = -1, 0, None
        index_root = self.store.get(root["indexContentHash"], version)
        validate_container(index_root, root, expected_hash=root["indexContentHash"])
        require(len(index_root["children"]) == len(root["directories"]), "index", "MISSING_INDEX")
        for di, d in enumerate(root["directories"]):
            cancel.check()
            directory = self.store.get(d["hash"], version)
            validate_container(directory, root, expected_hash=d["hash"], expected_descriptor=d)
            require(int(directory["directoryIndex"]) == di, "directory", "CORRUPT_INDEX_POINTER")
            ix = index_root["children"][di]
            require(ix["index"] == str(di) and (ix["firstNs"], ix["lastNs"]) == (d["firstNs"], d["lastNs"]), "index", "RANGE_CONFLICT")
            idir = self.store.get(ix["hash"], version)
            validate_container(idir, root, expected_hash=ix["hash"])
            require(int(idir["directoryIndex"]) == di, "index", "CORRUPT_INDEX_POINTER")
            require(len(idir["children"]) == len(directory["children"]), "index", "MISSING_INDEX")
            for pi, p in enumerate(directory["children"]):
                part = self.store.get(p["hash"], version)
                validate_container(part, root, expected_hash=p["hash"], expected_descriptor=p)
                require(int(part["directoryIndex"]) == di and int(part["partitionIndex"]) == pi,
                        "partition", "CORRUPT_INDEX_POINTER")
                ixp = idir["children"][pi]
                require(ixp["index"] == str(pi) and (ixp["firstNs"], ixp["lastNs"]) == (p["firstNs"], p["lastNs"]), "index", "RANGE_CONFLICT")
                leaf = self.store.get(ixp["hash"], version)
                validate_container(leaf, root, expected_hash=ixp["hash"])
                require(int(leaf["directoryIndex"]) == di and int(leaf["partitionIndex"]) == pi,
                        "index", "CORRUPT_INDEX_POINTER")
                require(leaf["partitionHash"] == p["hash"] and len(leaf["chunks"]) == len(part["children"]), "index", "PARTITION_HASH_MISMATCH")
                for ci, c in enumerate(part["children"]):
                    cancel.check()
                    chunk = self.store.get(c["hash"], version)
                    validate_container(chunk, root, expected_hash=c["hash"], expected_descriptor=c)
                    require(int(chunk["directoryIndex"]) == di and int(chunk["partitionIndex"]) == pi
                            and int(chunk["chunkIndex"]) == ci, "chunk", "CORRUPT_INDEX_POINTER")
                    require(int(chunk["firstOrdinal"]) == first_ordinal, "ordinal", "INVALID_SOURCE_ORDINAL")
                    require(1 <= len(chunk["events"]) <= 256, "chunk", "ARTIFACT_LIMIT")
                    # Semantic acceptance was performed for exactly these payload
                    # bytes before commit; finalization verifies their content hash.
                    for global_offset, e in enumerate(chunk["events"]):
                        original = dict(e, datasetVersion=ZERO_VERSION)
                        accepted = self.store.db.execute("SELECT digest,source,ordinal FROM identities WHERE event=?", (bytes.fromhex(e["eventId"]),)).fetchone()
                        raw = CanonicalTick._validate(original)
                        require(accepted is not None and accepted[0] == hashlib.sha256(raw).digest()
                                and accepted[1] == e["provenance"]["sourceId"] and str(accepted[2]) == e["rawOrdinal"], "acceptance", "IDENTITY_CONFLICT")
                        require(int(e["timeNs"]) >= previous, "seam", "ORDER_REVERSAL")
                        if int(e["timeNs"]) != previous:
                            group_anchor = dict(directoryIndex=str(di), partitionIndex=str(pi), chunkIndex=str(ci),
                                                eventOffset=str(global_offset), globalOrdinal=str(first_ordinal+global_offset), timeNs=e["timeNs"])
                        if e is chunk["events"][0]:
                            expected_anchor = deepcopy(group_anchor)
                        previous = int(e["timeNs"])
                    entry = leaf["chunks"][ci]
                    require(all(entry[k] == c[k] for k in ("firstNs", "lastNs", "firstOrdinal", "lastOrdinal")) and entry["chunkHash"] == c["hash"] and entry["chunkIndex"] == str(ci), "index", "CORRUPT_INDEX_POINTER")
                    anchor = entry["firstGroupStart"]
                    require(anchor == expected_anchor, "anchor", "CORRUPT_INDEX_POINTER")
                    first_ordinal += len(chunk["events"])
        require(first_ordinal == int(root["eventCount"]), "count", "COUNT_CONFLICT")


class DiskTickProvider:
    """IndexedTickDataProvider V2. Open with an explicitly pinned accepted root.

    Host private completion is trusted composition (not remote self-certification).
    Every accessed immutable descendant is checked against its pinned parent.
    No all-history scan, cache or event identity index in process RAM.
    """
    def __init__(self, folder, dataset_version, *, allow_threads=False):
        digest(dataset_version, "version")
        self.__store = ArtifactStore(folder, allow_threads=allow_threads)
        self.__cache_limit = (4 if allow_threads else 16)*1048576
        try:
            self.__open(dataset_version)
        except BaseException:
            self.__store.close()
            raise

    def __open(self, dataset_version):
        publication = self.__store.db.execute("SELECT root,receipt,binding FROM publications WHERE version=?", (dataset_version,)).fetchone()
        require(publication is not None, "completion", "INCOMPLETE_INGESTION")
        self.__root, receipt, binding = map(decode_v2, publication)
        validate_root(self.__root)
        require(hash_v2(self.__root) == dataset_version, "root", "MANIFEST_HASH_MISMATCH")
        shape(receipt, "BTL-TICK-COMPLETION-2"); shape(binding, "BTL-TICK-INDEX-BINDING-2")
        for obj in (receipt, binding):
            require(obj["datasetId"] == self.__root["datasetId"] and obj["datasetVersion"] == dataset_version
                    and obj["manifestHash"] == dataset_version and obj["indexContentHash"] == self.__root["indexContentHash"], "completion", "VERSION_MISMATCH")
        require(receipt["sourceCatalogHash"] == self.__root["sourceCatalogHash"] and receipt["validatorVersion"] == self.__root["validatorVersion"], "completion", "INCOMPLETE_INGESTION")
        self.dataset_version, self.dataset_id = dataset_version, self.__root["datasetId"]
        self.__cache, self.__cache_bytes = OrderedDict(), 0
        self.__paths = {}
        self.__receipt, self.__binding = receipt, binding
        self.__sources = self._load(self.__root["sourceCatalogHash"])["sources"]
        validate_sources(self.__root, self.__sources)
        self.__source_map = {s["sourceId"]: s for s in self.__sources}
        evidence = self._load(self.__root["evidenceCatalogHash"])
        # Trusted local receipt follows full offline acceptance. Query paths
        # recheck catalog/block hashes and semantics against this pinned root.
        shape(evidence, "BTL-TICK-EVIDENCE-CATALOG-2")

    def close(self):
        self.__store.close()

    def _identity(self, dataset_id, version):
        require(dataset_id == self.dataset_id, "dataset", "DATASET_MISMATCH")
        require(version == self.dataset_version, "version", "VERSION_MISMATCH")

    def _load(self, hash_):
        if hash_ in self.__cache:
            self.__cache.move_to_end(hash_)
            return self.__cache[hash_][0]
        obj = self.__store.get(hash_, self.dataset_version)
        validate_container(obj, self.__root, expected_hash=hash_)
        if obj["artifact"] == "BTL-TICK-STORAGE-CHUNK-2":
            previous = -1
            require(1 <= len(obj["events"]) <= 256, "chunk", "ARTIFACT_LIMIT")
            for event in obj["events"]:
                CanonicalTick._validate(event)
                require(all(event[k] == self.__root[k] for k in ("datasetId", "providerId", "feedId", "instrumentId")), "identity", "IDENTITY_CONFLICT")
                source = self.__source_map.get(event["provenance"]["sourceId"])
                require(source is not None and source["memberHash"] == event["provenance"]["memberHash"] and source["resolutionNs"] == event["resolutionNs"], "source", "IDENTITY_CONFLICT")
                require(int(event["timeNs"]) >= previous, "time", "ORDER_REVERSAL")
                previous = int(event["timeNs"])
        # Actual recursive Python object sizes, conservatively counting shared
        # references repeatedly; temporary measurement set does not scale with N.
        def size(value):
            if isinstance(value, dict):
                return sys.getsizeof(value)+sum(size(k)+size(v) for k, v in value.items())
            if isinstance(value, list):
                return sys.getsizeof(value)+sum(size(v) for v in value)
            return sys.getsizeof(value)
        cost = size(obj)
        while self.__cache and self.__cache_bytes+cost > self.__cache_limit:
            _, (_, old_cost) = self.__cache.popitem(last=False)
            self.__cache_bytes -= old_cost
            self.__paths.clear()
        if cost <= self.__cache_limit:
            self.__cache[hash_] = (obj, cost)
            self.__cache_bytes += cost
        return obj

    def describe_v2(self, dataset_id, version):
        self._identity(dataset_id, version)
        return deepcopy(dict(root=self.__root, completion=self.__receipt, indexBinding=self.__binding))

    def read_evidence_v2(self, request):
        return read_sidecars(self.__store, self.__root, self.dataset_version, self.__sources, request)

    def _path(self, di, pi, ci):
        if (di, pi, ci) in self.__paths:
            return self.__paths[di, pi, ci]
        ds = self.__root["directories"]
        require(0 <= di < len(ds), "directory", "CORRUPT_INDEX_POINTER")
        directory = self._load(ds[di]["hash"])
        validate_container(directory, self.__root, expected_descriptor=ds[di])
        require(int(directory["directoryIndex"]) == di and 0 <= pi < len(directory["children"]), "partition", "CORRUPT_INDEX_POINTER")
        pd = directory["children"][pi]
        part = self._load(pd["hash"])
        validate_container(part, self.__root, expected_descriptor=pd)
        require(int(part["directoryIndex"]) == di and int(part["partitionIndex"]) == pi and 0 <= ci < len(part["children"]), "chunk", "CORRUPT_INDEX_POINTER")
        cd = part["children"][ci]
        chunk = self._load(cd["hash"])
        validate_container(chunk, self.__root, expected_descriptor=cd)
        require(int(chunk["directoryIndex"]) == di and int(chunk["partitionIndex"]) == pi and int(chunk["chunkIndex"]) == ci, "path", "CORRUPT_INDEX_POINTER")
        require(1 <= len(chunk["events"]) <= 256, "chunk", "ARTIFACT_LIMIT")
        self.__paths[di, pi, ci] = (directory, part, chunk)
        return directory, part, chunk

    def _position(self, di, pi, ci, offset, ordinal):
        return dict(schemaVersion=2, artifact="BTL-TICK-POSITION-2", datasetId=self.dataset_id,
                    datasetVersion=self.dataset_version, manifestHash=self.dataset_version,
                    directoryIndex=str(di), partitionIndex=str(pi), chunkIndex=str(ci), eventOffset=str(offset), globalOrdinal=str(ordinal))

    def _check_position(self, position):
        shape(position, "BTL-TICK-POSITION-2")
        self._identity(position["datasetId"], position["datasetVersion"])
        require(position["manifestHash"] == self.dataset_version, "manifest", "MANIFEST_HASH_MISMATCH")
        di, pi, ci, offset = (int(position[k]) for k in ("directoryIndex", "partitionIndex", "chunkIndex", "eventOffset"))
        directory, part, chunk = self._path(di, pi, ci)
        require(offset < len(chunk["events"]) and int(position["globalOrdinal"]) == int(chunk["firstOrdinal"])+offset, "pointer", "CORRUPT_INDEX_POINTER")
        return di, pi, ci, offset, directory, part, chunk

    def _next_chunk(self, di, pi, ci, directory, part):
        if ci+1 < len(part["children"]):
            return di, pi, ci+1
        if pi+1 < len(directory["children"]):
            return di, pi+1, 0
        if di+1 < len(self.__root["directories"]):
            return di+1, 0, 0
        return None

    def read_page_v2(self, dataset_id, version, position, max_events=256):
        self._identity(dataset_id, version)
        require(type(max_events) is int and 1 <= max_events <= 256, "max_events", "ARTIFACT_LIMIT")
        result = dict(schemaVersion=2, artifact="BTL-TICK-PAGE-2", datasetId=dataset_id, datasetVersion=version,
                      events=[], diagnostics=empty_diagnostics(), nextPosition=None, endOfDataset=position is None)
        if position is None:
            return result
        di, pi, ci, offset, directory, part, chunk = self._check_position(position)
        # Stop at physical chunk boundary; valid bounded pages need not fill quota.
        count = min(max_events, len(chunk["events"])-offset)
        while count:
            result["events"] = deepcopy(chunk["events"][offset:offset+count])
            next_offset = offset+count
            next_ordinal = int(chunk["firstOrdinal"])+next_offset
            if next_offset < len(chunk["events"]):
                result["nextPosition"] = self._position(di, pi, ci, next_offset, next_ordinal)
            else:
                next_chunk = self._next_chunk(di, pi, ci, directory, part)
                result["nextPosition"] = None if next_chunk is None else self._position(*next_chunk, 0, next_ordinal)
            result["endOfDataset"] = result["nextPosition"] is None
            try:
                canonical_v2_bytes(result)
                return result
            except ValueError:
                count //= 2
        require(False, "page", "ARTIFACT_LIMIT")

    def locate_v2(self, dataset_id, version, target_ns):
        self._identity(dataset_id, version)
        target = uint(target_ns)
        index = self._load(self.__root["indexContentHash"])
        require(len(index["children"]) == len(self.__root["directories"]), "index", "MISSING_INDEX")
        def choose(rows):
            return bisect_left([int(r["lastNs"]) for r in rows], target)
        di = choose(index["children"])
        if di == len(index["children"]):
            return dict(position=None, groupTimeNs=None)
        d = index["children"][di]
        require(d["index"] == str(di) and (d["firstNs"], d["lastNs"]) == (self.__root["directories"][di]["firstNs"], self.__root["directories"][di]["lastNs"]), "index", "RANGE_CONFLICT")
        idir = self._load(d["hash"])
        require(int(idir["directoryIndex"]) == di, "index", "CORRUPT_INDEX_POINTER")
        pi = choose(idir["children"])
        require(pi < len(idir["children"]), "index", "CORRUPT_INDEX_POINTER")
        p = idir["children"][pi]
        leaf = self._load(p["hash"])
        require(int(leaf["directoryIndex"]) == di and int(leaf["partitionIndex"]) == pi, "index", "CORRUPT_INDEX_POINTER")
        ci = choose(leaf["chunks"])
        require(ci < len(leaf["chunks"]), "index", "CORRUPT_INDEX_POINTER")
        entry = leaf["chunks"][ci]
        directory, part, chunk = self._path(di, pi, ci)
        cd = part["children"][ci]
        require(leaf["partitionHash"] == directory["children"][pi]["hash"] and entry["chunkHash"] == cd["hash"]
                and all(entry[k] == cd[k] for k in ("firstNs", "lastNs", "firstOrdinal", "lastOrdinal")), "index", "CORRUPT_INDEX_POINTER")
        offset = bisect_left([int(e["timeNs"]) for e in chunk["events"]], target)
        require(offset < len(chunk["events"]), "index", "CORRUPT_INDEX_POINTER")
        time = chunk["events"][offset]["timeNs"]
        if time == entry["firstNs"]:
            a = entry["firstGroupStart"]
            keys(a, "directoryIndex partitionIndex chunkIndex eventOffset globalOrdinal timeNs")
            require(a["timeNs"] == time, "anchor", "CORRUPT_INDEX_POINTER")
            position = self._position(*(uint(a[k]) for k in ("directoryIndex", "partitionIndex", "chunkIndex", "eventOffset", "globalOrdinal")))
            _, _, _, ao, _, _, achunk = self._check_position(position)
            require(achunk["events"][ao]["timeNs"] == time, "anchor", "CORRUPT_INDEX_POINTER")
        else:
            position = self._position(di, pi, ci, offset, int(chunk["firstOrdinal"])+offset)
        # Validate actual predecessor, not the index's assertion alone.
        global_ordinal = int(position["globalOrdinal"])
        if global_ordinal:
            predecessor = self._by_ordinal(global_ordinal-1)
            require(int(predecessor["timeNs"]) < int(time), "boundary", "INCOMPLETE_ATOMIC_BOUNDARY")
        return dict(position=position, groupTimeNs=time)

    def _by_ordinal(self, ordinal):
        ds = self.__root["directories"]
        di = bisect_left([int(d["lastOrdinal"]) for d in ds], ordinal)
        directory = self._load(ds[di]["hash"])
        pi = bisect_left([int(d["lastOrdinal"]) for d in directory["children"]], ordinal)
        part = self._load(directory["children"][pi]["hash"])
        ci = bisect_left([int(d["lastOrdinal"]) for d in part["children"]], ordinal)
        _, _, chunk = self._path(di, pi, ci)
        offset = ordinal-int(chunk["firstOrdinal"])
        require(0 <= offset < len(chunk["events"]), "ordinal", "CORRUPT_INDEX_POINTER")
        return chunk["events"][offset]
