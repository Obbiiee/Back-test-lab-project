"""Immutable monthly Parquet derivative of an already validated tick dataset.

This adapter does not ingest market data, alter canonical event identity, grant
source rights, or settle trades. It stores exact canonical tick fields alongside
typed timestamp/ordinal columns used only for bounded seeking and pruning.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import numpy as np
import pyarrow as pa
import pyarrow.fs as pafs
import pyarrow.parquet as pq

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import digest, identifier, require
from .monthly_root import monthly_object_path, parse_s3_monthly_root
from ticks.contracts import CanonicalTick, TickManifest, validate_chunk, uint, tag

SCHEMA_VERSION = 1
MANIFEST_ARTIFACT = "BTL-TICK-MONTHLY-PARQUET-MANIFEST-2"
FORMAT_ARTIFACT = "BTL-CANONICAL-TICK-1"
COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3
DEFAULT_ROW_GROUP_SIZE = 65_536
MAX_ROW_GROUP_SIZE = 65_536
READ_BATCH_SIZE = 8_192
MAX_TIMESTAMP_GROUP_EVENTS = 1_024
HASH_ALGORITHM = "SHA256(BTL-CJSON-1 canonical event bytes joined by LF)"
MANIFEST_FIELDS = {
    "schemaVersion", "artifact", "manifestVersion", "layout", "datasetId", "datasetVersion",
    "providerId", "feedId", "instrumentId", "canonicalEventArtifact", "canonicalEventIdentity",
    "sourceManifestHash", "sourceIdentity", "ordering", "sourceRights", "sourceRange", "coverage",
    "gaps", "diagnostics", "compression", "rowGroupSize", "rowGroupHashAlgorithm", "eventCount",
    "sourceManifest", "files", "manifestHash",
}

SCHEMA = pa.schema([
    pa.field("schema_version", pa.int16(), nullable=False),
    pa.field("artifact", pa.string(), nullable=False),
    pa.field("dataset_id", pa.string(), nullable=False),
    pa.field("dataset_version", pa.string(), nullable=False),
    pa.field("provider_id", pa.string(), nullable=False),
    pa.field("feed_id", pa.string(), nullable=False),
    pa.field("instrument_id", pa.string(), nullable=False),
    pa.field("event_id", pa.string(), nullable=False),
    pa.field("timestamp_ns", pa.int64(), nullable=False),
    pa.field("global_index", pa.int64(), nullable=False),
    pa.field("resolution_ns", pa.int64(), nullable=False),
    pa.field("source_index", pa.int16(), nullable=False),
    pa.field("bid", pa.string(), nullable=True),
    pa.field("ask", pa.string(), nullable=True),
    pa.field("source_ordinal", pa.string(), nullable=False),
    pa.field("trusted_sequence", pa.string(), nullable=True),
    pa.field("provenance_json", pa.binary(), nullable=False),
    pa.field("quality_json", pa.binary(), nullable=False),
], metadata={
    b"riksora.format": MANIFEST_ARTIFACT.encode(),
    b"riksora.canonical-event": FORMAT_ARTIFACT.encode(),
    b"riksora.canonical-event-schema-version": b"1",
    b"riksora.timestamp-unit": b"nanoseconds-since-unix-epoch",
    b"riksora.ordinal-semantics": b"original-source-ordinal; not trusted sequence",
})


def _month(time_ns: int) -> str:
    require(0 <= time_ns <= 2**63 - 1, "timestamp", "RANGE_CONFLICT")
    return datetime.fromtimestamp(time_ns // 1_000_000_000, timezone.utc).strftime("%Y-%m")


def _json_object(raw: bytes, expected_fields=None):
    def unique(pairs):
        value = {}
        for key, child in pairs:
            require(key not in value, "manifest", "SCHEMA_MISMATCH")
            value[key] = child
        return value
    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        require(False, "manifest", "SCHEMA_MISMATCH")
    require(type(value) is dict and canonical_bytes(value) == raw, "manifest", "SCHEMA_MISMATCH")
    if expected_fields is not None:
        require(set(value) == set(expected_fields) and value.get("schemaVersion") == 1,
                "manifest", "SCHEMA_MISMATCH")
    return value


def _event_to_row(event):
    wire = CanonicalTick.from_wire(event).wire
    time_ns = int(wire["timeNs"])
    resolution_ns = int(wire["resolutionNs"])
    require(time_ns <= 2**63 - 1 and resolution_ns <= 2**63 - 1, "timestamp", "RANGE_CONFLICT")
    return {
        "schema_version": wire["schemaVersion"], "artifact": wire["artifact"],
        "dataset_id": wire["datasetId"], "dataset_version": wire["datasetVersion"],
        "provider_id": wire["providerId"], "feed_id": wire["feedId"],
        "instrument_id": wire["instrumentId"], "event_id": wire["eventId"],
        "timestamp_ns": time_ns, "resolution_ns": resolution_ns,
        "bid": wire["bid"], "ask": wire["ask"], "source_ordinal": wire["rawOrdinal"],
        "trusted_sequence": wire["trustedSequence"],
        "provenance_json": canonical_bytes({"schemaVersion": 1, **wire["provenance"]}),
        "quality_json": canonical_bytes({"schemaVersion": 1, **wire["quality"]}),
        "_wire": wire,
    }


def _row_to_event(row):
    provenance = _json_object(row["provenance_json"], {"schemaVersion", "sourceId", "memberHash", "originalTimestamp"})
    quality = _json_object(row["quality_json"], {"schemaVersion", "evidenceHash", "quote", "freshness", "gapBefore", "duplicateOf"})
    provenance.pop("schemaVersion", None)
    quality.pop("schemaVersion", None)
    event = {
        "schemaVersion": row["schema_version"], "artifact": row["artifact"],
        "datasetId": row["dataset_id"], "datasetVersion": row["dataset_version"],
        "providerId": row["provider_id"], "feedId": row["feed_id"],
        "instrumentId": row["instrument_id"], "eventId": row["event_id"],
        "timeNs": str(row["timestamp_ns"]), "resolutionNs": str(row["resolution_ns"]),
        "bid": row["bid"], "ask": row["ask"], "rawOrdinal": row["source_ordinal"],
        "trustedSequence": row["trusted_sequence"], "provenance": provenance, "quality": quality,
    }
    return CanonicalTick.from_wire(event).wire


def _atomic_publish(temp_path: Path, target: Path):
    """Publish one new immutable file without replacing an existing object."""
    require(not target.exists(), "immutable", "IMMUTABLE_ALREADY_PUBLISHED")
    os.link(temp_path, target, follow_symlinks=False)
    temp_path.unlink()
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _sha256_file(path: Path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1_048_576):
            sha.update(block)
    return sha.hexdigest()


def _validate_source_manifest(source_manifest, expected_version=None):
    require(expected_version is not None, "expectedVersion", "MISSING_REQUIRED_FIELD")
    checked = TickManifest.from_wire(source_manifest, expected_version)
    manifest = checked.wire
    require(manifest["ordering"]["timestamps"] == "VERIFIED_NONDECREASING",
            "ordering", "UNVERIFIED_ORDER")
    require(manifest["range"]["endExclusive"] is True, "range", "RANGE_CONFLICT")
    return checked


def _write_monthly_parquet_reserved(root, events, source_manifest, *, expected_version=None,
                                    row_group_size=DEFAULT_ROW_GROUP_SIZE):
    """Stream validated canonical events into immutable UTC month files.

    Only one bounded row group is held in memory. Input order is preserved and
    checked; the writer never sorts ties or upgrades untrusted sequence data.
    Existing files/manifests are never overwritten.
    """
    require(type(row_group_size) is int and 1 <= row_group_size <= MAX_ROW_GROUP_SIZE,
            "rowGroupSize", "ARTIFACT_LIMIT")
    source = _validate_source_manifest(source_manifest, expected_version)
    source_wire = source.wire
    source_indices = {item["sourceId"]: index for index, item in enumerate(source_wire["sources"])}
    final_root = Path(root).resolve()
    final_root.parent.mkdir(parents=True, exist_ok=True)
    require(not final_root.exists(), "immutable", "IMMUTABLE_ALREADY_PUBLISHED")
    root = Path(tempfile.mkdtemp(prefix=f".{final_root.name}.staging-", dir=final_root.parent))
    manifest_path = root / "manifest.json"

    files = []
    current_month = None
    current_temp = None
    writer = None
    rows = []
    row_groups = []
    quality_counts = None
    total_events = 0
    previous_time = -1
    previous_source = -1
    previous_ordinal = -1
    source_chunk_index = 0
    source_chunk_events = []

    def finish_row_group():
        nonlocal rows, row_groups, writer, quality_counts
        if not rows:
            return
        table_rows = [{k: v for k, v in row.items() if k != "_wire"} for row in rows]
        table = pa.Table.from_pylist(table_rows, schema=SCHEMA)
        writer.write_table(table, row_group_size=len(rows))
        sha = hashlib.sha256()
        for row in rows:
            sha.update(canonical_bytes(row["_wire"]))
            sha.update(b"\n")
        row_groups.append({
            "index": len(row_groups), "eventCount": len(rows),
            "firstTimeNs": str(rows[0]["timestamp_ns"]), "lastTimeNs": str(rows[-1]["timestamp_ns"]),
            "firstOrdinal": rows[0]["source_ordinal"], "lastOrdinal": rows[-1]["source_ordinal"],
            "firstSourceIndex": rows[0]["source_index"], "lastSourceIndex": rows[-1]["source_index"],
            "firstGlobalIndex": rows[0]["global_index"], "lastGlobalIndex": rows[-1]["global_index"],
            "canonicalEventHash": sha.hexdigest(),
        })
        rows = []

    def finish_month():
        nonlocal writer, current_temp, row_groups, quality_counts, current_month
        if writer is None:
            return
        finish_row_group()
        writer.close()
        with current_temp.open("rb") as stream:
            os.fsync(stream.fileno())
        target = root / current_month / "ticks.parquet"
        _atomic_publish(current_temp, target)
        parquet = pq.ParquetFile(target)
        require(parquet.metadata.num_rows == sum(group["eventCount"] for group in row_groups) and
                parquet.metadata.num_row_groups == len(row_groups), "parquetFooter", "CORRUPT_RECORD")
        files.append({
            "month": current_month, "path": f"{current_month}/ticks.parquet", "sha256": _sha256_file(target),
            "bytes": target.stat().st_size, "eventCount": parquet.metadata.num_rows,
            "firstTimeNs": row_groups[0]["firstTimeNs"], "lastTimeNs": row_groups[-1]["lastTimeNs"],
            "firstOrdinal": row_groups[0]["firstOrdinal"], "lastOrdinal": row_groups[-1]["lastOrdinal"],
            "rowGroups": row_groups, "sourceQualityCounts": quality_counts,
        })
        writer = current_temp = None
        row_groups = []
        quality_counts = None

    try:
        for source_event in events:
            row = _event_to_row(source_event)
            event = row["_wire"]
            require((event["datasetId"], event["datasetVersion"], event["providerId"],
                     event["feedId"], event["instrumentId"]) ==
                    (source_wire["datasetId"], source.version, source_wire["providerId"],
                     source_wire["feedId"], source_wire["instrumentId"]),
                    "eventIdentity", "IDENTITY_CONFLICT")
            time_ns = row["timestamp_ns"]
            ordinal = int(row["source_ordinal"])
            source_index = source_indices.get(event["provenance"]["sourceId"])
            require(source_index is not None, "provenance", "IDENTITY_CONFLICT")
            source_record = source_wire["sources"][source_index]
            require(event["provenance"]["memberHash"] == source_record["memberHash"] and
                    event["resolutionNs"] == source_record["resolutionNs"],
                    "provenance", "IDENTITY_CONFLICT")
            require(time_ns >= previous_time and source_index >= previous_source and
                    (source_index != previous_source or ordinal > previous_ordinal),
                    "eventOrder", "ORDER_REVERSAL")
            row["source_index"] = source_index
            row["global_index"] = total_events
            month = _month(time_ns)
            require(int(source_wire["range"]["startNs"]) <= time_ns < int(source_wire["range"]["endNs"]),
                    "eventRange", "RANGE_CONFLICT")
            if current_month is not None and month != current_month:
                require(month > current_month, "monthOrder", "ORDER_REVERSAL")
                finish_month()
            if current_month != month:
                month_dir = root / month
                month_dir.mkdir(exist_ok=True)
                target = month_dir / "ticks.parquet"
                require(not target.exists(), "immutable", "IMMUTABLE_ALREADY_PUBLISHED")
                fd, temp_name = tempfile.mkstemp(prefix=".ticks-", suffix=".partial", dir=month_dir)
                os.close(fd)
                current_temp = Path(temp_name)
                writer = pq.ParquetWriter(current_temp, SCHEMA, compression=COMPRESSION,
                    compression_level=COMPRESSION_LEVEL, write_statistics=True,
                    use_dictionary=["artifact", "dataset_id", "dataset_version", "provider_id",
                                    "feed_id", "instrument_id"], version="2.6",
                    write_page_checksum=True)
                current_month = month
                quality_counts = {"quote": {}, "freshness": {}, "gapBefore": {}}
            rows.append(row)
            require(source_chunk_index < len(source_wire["chunks"]),
                    "sourceChunks", "INCOMPLETE_INGESTION")
            source_chunk = source_wire["chunks"][source_chunk_index]
            source_chunk_events.append(event)
            require(len(source_chunk_events) <= source_chunk["eventCount"],
                    "sourceChunkCount", "COUNT_CONFLICT")
            if len(source_chunk_events) == source_chunk["eventCount"]:
                validate_chunk(dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1",
                                    datasetId=source_wire["datasetId"], datasetVersion=source.version,
                                    chunkIndex=str(source_chunk_index), events=source_chunk_events), source)
                source_chunk_events = []
                source_chunk_index += 1
            for field, key in (("quote", "quote"), ("freshness", "freshness"), ("gapBefore", "gapBefore")):
                value = event["quality"][key]
                counts = quality_counts[field]
                counts[value] = counts.get(value, 0) + 1
            previous_time, previous_source, previous_ordinal = time_ns, source_index, ordinal
            total_events += 1
            if len(rows) == row_group_size:
                finish_row_group()
        finish_month()
    except BaseException:
        if writer is not None:
            writer.close()
        # An unpublished staging directory is intentionally retained so a
        # failed conversion is inspectable and cannot masquerade as a dataset.
        raise

    require(total_events > 0, "events", "EMPTY_DATASET")
    require(not source_chunk_events and source_chunk_index == len(source_wire["chunks"]) and
            total_events == sum(item["eventCount"] for item in source_wire["chunks"]),
            "eventCount", "INCOMPLETE_INGESTION")
    require(files[0]["firstTimeNs"] == source_wire["range"]["startNs"] and
            int(files[-1]["lastTimeNs"]) < int(source_wire["range"]["endNs"]),
            "sourceRange", "INCOMPLETE_INGESTION")
    payload = {
        "schemaVersion": SCHEMA_VERSION, "artifact": MANIFEST_ARTIFACT,
        "manifestVersion": 2, "layout": "ONE_FILE_PER_UTC_MONTH",
        "datasetId": source_wire["datasetId"], "datasetVersion": source.version,
        "providerId": source_wire["providerId"], "feedId": source_wire["feedId"],
        "instrumentId": source_wire["instrumentId"], "canonicalEventArtifact": FORMAT_ARTIFACT,
        "canonicalEventIdentity": "PRESERVED_EVENT_ID_FIELD", "sourceManifestHash": source.version,
        "sourceIdentity": source_wire["sources"],
        "sourceManifest": source_wire,
        "ordering": source_wire["ordering"], "sourceRights": source_wire["rights"],
        "sourceRange": source_wire["range"], "coverage": source_wire["coverage"],
        "gaps": source_wire["gaps"], "diagnostics": source_wire["diagnostics"],
        "compression": {"codec": COMPRESSION, "level": COMPRESSION_LEVEL},
        "rowGroupSize": row_group_size, "rowGroupHashAlgorithm": HASH_ALGORITHM,
        "eventCount": total_events, "files": files,
    }
    manifest = {**payload, "manifestHash": content_hash(payload)}
    raw_manifest = canonical_bytes(manifest)
    fd, temp_name = tempfile.mkstemp(prefix=".manifest-", suffix=".partial", dir=root)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw_manifest)
        stream.flush()
        os.fsync(stream.fileno())
    _atomic_publish(Path(temp_name), manifest_path)
    directory = os.open(root, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    require(not final_root.exists(), "immutable", "IMMUTABLE_ALREADY_PUBLISHED")
    os.rename(root, final_root)
    parent = os.open(final_root.parent, os.O_RDONLY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return manifest


def write_monthly_parquet(root, events, source_manifest, *, expected_version=None,
                          row_group_size=DEFAULT_ROW_GROUP_SIZE):
    """Publish once; an O_EXCL sibling reservation prevents duplicate writers.

    A stale reservation after process death fails closed and requires explicit
    operator inspection. It is never auto-removed as a recovery shortcut.
    """
    final_root = Path(root).resolve()
    final_root.parent.mkdir(parents=True, exist_ok=True)
    reservation = final_root.parent / f".{final_root.name}.publish.lock"
    try:
        fd = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        require(False, "publisher", "IMMUTABLE_ALREADY_PUBLISHED")
    try:
        os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(fd)
        os.close(fd)
        fd = None
        return _write_monthly_parquet_reserved(final_root, events, source_manifest,
                                               expected_version=expected_version,
                                               row_group_size=row_group_size)
    finally:
        if fd is not None:
            os.close(fd)
        reservation.unlink(missing_ok=True)


class MonthlyParquetProvider:
    """Read only requested UTC months and row groups; verify canonical rows."""
    def __init__(self, root, *, expected_dataset_id=None, expected_dataset_version=None,
                 expected_manifest_hash=None, filesystem=None):
        require(isinstance(root, (str, Path)), "root", "REFUSED_SOURCE")
        root_text = str(root)
        if "://" in root_text:
            self.root, bucket, prefix = parse_s3_monthly_root(root_text)
            self._base_path = f"{bucket}/{prefix}"
            if filesystem is None:
                self._filesystem, self._base_path = pafs.FileSystem.from_uri(self.root)
            else:
                self._filesystem = filesystem
        else:
            self.root = Path(root).resolve()
            self._base_path = str(self.root)
            self._filesystem = filesystem or pafs.LocalFileSystem()
        require(isinstance(self._filesystem, pafs.FileSystem), "filesystem", "REFUSED_SOURCE")
        raw = self._read_object("manifest.json")
        manifest = _json_object(raw, MANIFEST_FIELDS)
        require(manifest.get("schemaVersion") == SCHEMA_VERSION and
                manifest.get("artifact") == MANIFEST_ARTIFACT and manifest.get("manifestVersion") == 2,
                "manifestVersion", "SCHEMA_MISMATCH")
        supplied_hash = manifest.pop("manifestHash", None)
        digest(supplied_hash, "manifestHash")
        require(content_hash(manifest) == supplied_hash, "manifestHash", "CHILD_HASH_MISMATCH")
        manifest["manifestHash"] = supplied_hash
        ordered = (type(manifest.get("ordering")) is dict and
                   manifest["ordering"].get("timestamps") == "VERIFIED_NONDECREASING")
        require(ordered, "ordering", "UNVERIFIED_ORDER")
        require(manifest["canonicalEventArtifact"] == FORMAT_ARTIFACT and
                manifest["canonicalEventIdentity"] == "PRESERVED_EVENT_ID_FIELD" and
                manifest["compression"] == {"codec": COMPRESSION, "level": COMPRESSION_LEVEL},
                "manifestContract", "SCHEMA_MISMATCH")
        require(manifest.get("datasetVersion") == manifest.get("sourceManifestHash") and
                type(manifest.get("eventCount")) is int and manifest["eventCount"] > 0 and
                type(manifest.get("rowGroupSize")) is int and
                1 <= manifest["rowGroupSize"] <= MAX_ROW_GROUP_SIZE,
                "manifestContract", "SCHEMA_MISMATCH")
        require(expected_manifest_hash is not None,
                "expectedManifestHash", "MISSING_REQUIRED_FIELD")
        for field in ("datasetId", "providerId", "feedId", "instrumentId"):
            identifier(manifest[field], field)
        digest(manifest["datasetVersion"], "datasetVersion")
        digest(manifest["sourceManifestHash"], "sourceManifestHash")
        if expected_dataset_id is not None:
            require(manifest["datasetId"] == expected_dataset_id, "datasetId", "IDENTITY_CONFLICT")
        if expected_dataset_version is not None:
            require(manifest["datasetVersion"] == expected_dataset_version,
                    "datasetVersion", "VERSION_MISMATCH")
        if expected_manifest_hash is not None:
            require(supplied_hash == expected_manifest_hash, "manifestHash", "CHILD_HASH_MISMATCH")
        self.manifest = manifest
        self._source_manifest = TickManifest.from_wire(manifest["sourceManifest"], manifest["datasetVersion"]).wire
        require(self._source_manifest["datasetId"] == manifest["datasetId"] and
                self._source_manifest["sources"] == manifest["sourceIdentity"] and
                self._source_manifest["ordering"] == manifest["ordering"] and
                self._source_manifest["coverage"] == manifest["coverage"] and
                self._source_manifest["gaps"] == manifest["gaps"] and
                self._source_manifest["rights"] == manifest["sourceRights"],
                "sourceManifest", "IDENTITY_CONFLICT")
        self._dataset_id = manifest["datasetId"]
        self._dataset_version = manifest["datasetVersion"]
        self.manifest_hash = supplied_hash
        require(type(manifest.get("sourceIdentity")) is list and
                1 <= len(manifest["sourceIdentity"]) <= 128,
                "sourceIdentity", "SCHEMA_MISMATCH")
        self._source_indices = {}
        for index, source in enumerate(manifest["sourceIdentity"]):
            require(type(source) is dict and type(source.get("sourceId")) is str and
                    type(source.get("memberHash")) is str and type(source.get("resolutionNs")) is str and
                    source["sourceId"] not in self._source_indices,
                    "sourceIdentity", "SCHEMA_MISMATCH")
            identifier(source["sourceId"], "sourceId")
            digest(source["memberHash"], "memberHash")
            require(uint(source["resolutionNs"]) > 0, "resolutionNs", "SCHEMA_MISMATCH")
            self._source_indices[source["sourceId"]] = index
        self._files = manifest["files"]
        require(type(self._files) is list and 1 <= len(self._files) <= 4096 and bool(self._files),
                "files", "INCOMPLETE_INGESTION")
        previous_month = None
        total = 0
        for entry in self._files:
            require(type(entry) is dict and set(entry) == {
                "month", "path", "sha256", "bytes", "eventCount", "firstTimeNs", "lastTimeNs",
                "firstOrdinal", "lastOrdinal", "rowGroups", "sourceQualityCounts"},
                "fileIndex", "SCHEMA_MISMATCH")
            require(type(entry.get("month")) is str and
                    re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", entry["month"]) is not None and
                    entry["path"] == f"{entry['month']}/ticks.parquet" and
                    (previous_month is None or entry["month"] > previous_month),
                    "fileOrder", "CORRUPT_INDEX_POINTER")
            digest(entry["sha256"], "fileHash")
            require(type(entry["eventCount"]) is int and entry["eventCount"] > 0 and
                    type(entry["bytes"]) is int and entry["bytes"] > 0 and
                    type(entry["rowGroups"]) is list and
                    1 <= len(entry["rowGroups"]) <= 4096,
                    "fileIndex", "CORRUPT_INDEX_POINTER")
            require(all(type(group) is dict and set(group) == {
                            "index", "eventCount", "firstTimeNs", "lastTimeNs", "firstOrdinal",
                            "lastOrdinal", "firstSourceIndex", "lastSourceIndex",
                            "firstGlobalIndex", "lastGlobalIndex", "canonicalEventHash"} and
                        group.get("index") == index and type(group.get("eventCount")) is int and
                        1 <= group["eventCount"] <= manifest["rowGroupSize"] and
                        type(group.get("firstTimeNs")) is str and type(group.get("lastTimeNs")) is str and
                        type(group.get("firstSourceIndex")) is int and type(group.get("lastSourceIndex")) is int and
                        type(group.get("firstGlobalIndex")) is int and type(group.get("lastGlobalIndex")) is int and
                        group["firstGlobalIndex"] == total + sum(prior["eventCount"] for prior in entry["rowGroups"][:index]) and
                        group["firstGlobalIndex"] <= group["lastGlobalIndex"] and
                        uint(group["firstTimeNs"]) <= uint(group["lastTimeNs"]) and
                        _month(uint(group["firstTimeNs"])) == entry["month"] and
                        _month(uint(group["lastTimeNs"])) == entry["month"] and
                        (index == 0 or uint(entry["rowGroups"][index - 1]["lastTimeNs"]) <= uint(group["firstTimeNs"])) and
                        type(group.get("canonicalEventHash")) is str
                        for index, group in enumerate(entry["rowGroups"])),
                    "rowGroupIndex", "CORRUPT_INDEX_POINTER")
            require(sum(group["eventCount"] for group in entry["rowGroups"]) == entry["eventCount"],
                    "rowGroupCount", "CORRUPT_INDEX_POINTER")
            require(entry["firstTimeNs"] == entry["rowGroups"][0]["firstTimeNs"] and
                    entry["lastTimeNs"] == entry["rowGroups"][-1]["lastTimeNs"],
                    "fileBounds", "CORRUPT_INDEX_POINTER")
            for group in entry["rowGroups"]:
                digest(group["canonicalEventHash"], "canonicalEventHash")
            total += entry["eventCount"]
            previous_month = entry["month"]
        require(total == manifest["eventCount"], "eventCount", "COUNT_CONFLICT")

    def _object_path(self, relative):
        return monthly_object_path(self.root, self._base_path, relative)

    def _read_object(self, relative):
        path = self._object_path(relative)
        info = self._filesystem.get_file_info(path)
        require(info.type == pafs.FileType.File, "file", "MISSING_CHILD")
        with self._filesystem.open_input_file(path) as stream:
            return stream.read()

    def _open_parquet(self, relative):
        path = self._object_path(relative)
        info = self._filesystem.get_file_info(path)
        require(info.type == pafs.FileType.File, "file", "MISSING_CHILD")
        return pq.ParquetFile(self._filesystem.open_input_file(path))

    def verify_file_hash(self, month):
        entry = self._file_for_month(month)
        path = self._object_path(entry["path"])
        info = self._filesystem.get_file_info(path)
        require(info.type == pafs.FileType.File and info.size == entry["bytes"],
                "file", "MISSING_CHILD")
        sha = hashlib.sha256()
        with self._filesystem.open_input_file(path) as stream:
            while block := stream.read(READ_BATCH_SIZE):
                sha.update(block)
        require(sha.hexdigest() == entry["sha256"],
                "fileHash", "CHILD_HASH_MISMATCH")
        return True

    def _file_for_month(self, month):
        return next((entry for entry in self._files if entry["month"] == month), None)

    def first_time_for_month(self, month):
        """Return a pinned first timestamp without loading beyond one row group."""
        require(type(month) is str and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) is not None,
                "month", "INVALID_INPUT")
        entry = self._file_for_month(month)
        require(entry is not None, "month", "REFUSED_SOURCE_NOT_AVAILABLE")
        group = entry["rowGroups"][0]
        events, _timestamps, _indices = self._read_row_group(entry["path"], entry, group)
        require(events and events[0]["timeNs"] == entry["firstTimeNs"],
                "monthStart", "CORRUPT_INDEX_POINTER")
        return int(events[0]["timeNs"])

    def _read_row_group(self, path, file_entry, group_entry):
        parquet = self._open_parquet(path)
        try:
            return self._read_row_group_file(parquet, file_entry, group_entry)
        finally:
            parquet.close()

    def _read_row_group_file(self, parquet, file_entry, group_entry):
        require(parquet.schema_arrow.remove_metadata().equals(SCHEMA.remove_metadata()),
                "parquetSchema", "SCHEMA_MISMATCH")
        index = group_entry["index"]
        require(index < parquet.metadata.num_row_groups, "rowGroup", "CORRUPT_INDEX_POINTER")
        meta = parquet.metadata.row_group(index)
        require(meta.num_rows == group_entry["eventCount"], "rowGroupCount", "CORRUPT_RECORD")
        require(all(meta.column(i).compression == "ZSTD" for i in range(meta.num_columns)),
                "compression", "SCHEMA_MISMATCH")
        sha = hashlib.sha256()
        events = []
        timestamps = np.empty(group_entry["eventCount"], dtype=np.int64)
        global_indices = np.empty(group_entry["eventCount"], dtype=np.int64)
        offset = 0
        last_time = -1
        last_source = -1
        last_ordinal = -1
        for batch in parquet.iter_batches(batch_size=READ_BATCH_SIZE,
                row_groups=[index], columns=SCHEMA.names, use_threads=False):
            rows = batch.to_pylist()
            count = len(rows)
            require(count > 0 and offset + count <= group_entry["eventCount"],
                    "rowGroupCount", "CORRUPT_RECORD")
            timestamps[offset:offset+count] = batch.column("timestamp_ns").to_numpy(
                zero_copy_only=False)
            global_indices[offset:offset+count] = batch.column("global_index").to_numpy(
                zero_copy_only=False)
            for row in rows:
                event = _row_to_event(row)
                require((event["datasetId"], event["datasetVersion"], event["providerId"],
                         event["feedId"], event["instrumentId"]) ==
                        (self.dataset_id, self.dataset_version, self.manifest["providerId"],
                         self.manifest["feedId"], self.manifest["instrumentId"]),
                        "eventIdentity", "IDENTITY_CONFLICT")
                time_ns = int(event["timeNs"])
                ordinal = int(event["rawOrdinal"])
                source_index = row["source_index"]
                require(type(source_index) is int and 0 <= source_index < len(self.manifest["sourceIdentity"]) and
                        time_ns >= last_time and source_index >= last_source and
                        (source_index != last_source or ordinal > last_ordinal),
                        "eventOrder", "ORDER_REVERSAL")
                source_record = self.manifest["sourceIdentity"][source_index]
                require(event["provenance"]["sourceId"] == source_record["sourceId"] and
                        event["provenance"]["memberHash"] == source_record["memberHash"] and
                        event["resolutionNs"] == source_record["resolutionNs"],
                        "provenance", "IDENTITY_CONFLICT")
                require(_month(time_ns) == file_entry["month"], "month", "RANGE_CONFLICT")
                last_time, last_source, last_ordinal = time_ns, source_index, ordinal
                sha.update(canonical_bytes(event)); sha.update(b"\n")
                events.append(event)
            offset += count
        require(offset == group_entry["eventCount"], "rowGroupCount", "CORRUPT_RECORD")
        require(sha.hexdigest() == group_entry["canonicalEventHash"],
                "canonicalEventHash", "CHILD_HASH_MISMATCH")
        require(events and events[0]["timeNs"] == group_entry["firstTimeNs"] and
                events[-1]["timeNs"] == group_entry["lastTimeNs"] and
                events[0]["rawOrdinal"] == group_entry["firstOrdinal"] and
                events[-1]["rawOrdinal"] == group_entry["lastOrdinal"] and
                self._source_indices[events[0]["provenance"]["sourceId"]] == group_entry["firstSourceIndex"] and
                self._source_indices[events[-1]["provenance"]["sourceId"]] == group_entry["lastSourceIndex"],
                "rowGroupBounds", "CORRUPT_INDEX_POINTER")
        require(len(timestamps) == len(events) and np.all(timestamps[1:] >= timestamps[:-1]),
                "timestampIndex", "ORDER_REVERSAL")
        require(len(global_indices) == len(events) and
                int(global_indices[0]) == group_entry["firstGlobalIndex"] and
                int(global_indices[-1]) == group_entry["lastGlobalIndex"],
                "globalIndex", "CORRUPT_INDEX_POINTER")
        return events, timestamps, global_indices

    @property
    def dataset_id(self):
        return self._dataset_id

    @property
    def dataset_version(self):
        return self._dataset_version

    def describe(self, dataset_id, dataset_version):
        require((dataset_id, dataset_version) == (self.dataset_id, self.dataset_version),
                "dataset", "VERSION_MISMATCH")
        return deepcopy(self._source_manifest)

    def read_page(self, dataset_id, dataset_version, after_token=None, max_events=64):
        self.describe(dataset_id, dataset_version)
        require(type(max_events) is int and 1 <= max_events <= 64, "max_events", "ARTIFACT_LIMIT")
        require(not self._source_manifest["diagnostics"], "diagnostics", "INCOMPLETE_DIAGNOSTICS")
        start = 0
        if after_token is not None:
            tag(after_token, "BTL-TICK-PAGE-TOKEN-1", "datasetVersion sourceIndex afterRawOrdinal")
            require(after_token["datasetVersion"] == dataset_version, "token", "VERSION_MISMATCH")
            source_index = uint(after_token["sourceIndex"])
            require(source_index < len(self._source_manifest["sources"]), "token", "INVALID_PAGE_TOKEN")
            require(after_token["afterRawOrdinal"] is not None, "token", "INVALID_PAGE_TOKEN")
            ordinal = uint(after_token["afterRawOrdinal"])
            found = False
            for entry in self._files:
                for group in entry["rowGroups"]:
                    low = (group["firstSourceIndex"], int(group["firstOrdinal"]))
                    high = (group["lastSourceIndex"], int(group["lastOrdinal"]))
                    if low <= (source_index, ordinal) <= high:
                        events, _times, indices = self._read_row_group(entry["path"], entry, group)
                        for event, global_index in zip(events, indices):
                            if (self._source_indices[event["provenance"]["sourceId"]],
                                    int(event["rawOrdinal"])) == (source_index, ordinal):
                                start = int(global_index) + 1
                                found = True
                                break
                    if found:
                        break
                if found:
                    break
            require(found, "token", "INVALID_PAGE_TOKEN")
        selected = []
        stop = start + max_events
        for entry in self._files:
            for group in entry["rowGroups"]:
                if group["lastGlobalIndex"] < start:
                    continue
                if group["firstGlobalIndex"] >= stop:
                    break
                events, _times, indices = self._read_row_group(entry["path"], entry, group)
                selected.extend(event for event, index in zip(events, indices)
                                if start <= int(index) < stop)
            if len(selected) >= max_events:
                break
        selected = selected[:max_events]
        while True:
            end = start + len(selected) == self.manifest["eventCount"]
            result = dict(schemaVersion=1, artifact="BTL-TICK-PAGE-1", datasetId=dataset_id,
                          datasetVersion=dataset_version, events=selected,
                          diagnostics={"records": [], "counts": {}, "truncated": False},
                          nextToken=None, endOfDataset=end)
            if selected and not end:
                last = selected[-1]
                result["nextToken"] = dict(schemaVersion=1, artifact="BTL-TICK-PAGE-TOKEN-1",
                    datasetVersion=dataset_version,
                    sourceIndex=str(self._source_indices[last["provenance"]["sourceId"]]),
                    afterRawOrdinal=last["rawOrdinal"])
            try:
                canonical_bytes(result)
                return result
            except ValueError:
                require(len(selected) > 1, "page", "RECORD_LIMIT")
                selected = selected[:max(1, len(selected)//2)]

    def iter_range(self, start_ns, end_ns):
        """Yield exact canonical ticks in [start_ns, end_ns), in source order."""
        require(type(start_ns) is int and type(end_ns) is int and 0 <= start_ns < end_ns <= 2**63,
                "range", "RANGE_CONFLICT")
        previous_time, previous_source, previous_ordinal = -1, -1, -1
        for file_entry in self._files:
            if int(file_entry["lastTimeNs"]) < start_ns or int(file_entry["firstTimeNs"]) >= end_ns:
                continue
            parquet = self._open_parquet(file_entry["path"])
            try:
                require(parquet.schema_arrow.remove_metadata().equals(SCHEMA.remove_metadata()) and
                        parquet.metadata.num_rows == file_entry["eventCount"] and
                        parquet.metadata.num_row_groups == len(file_entry["rowGroups"]),
                        "parquetSchema", "SCHEMA_MISMATCH")
                for group in file_entry["rowGroups"]:
                    if int(group["lastTimeNs"]) < start_ns or int(group["firstTimeNs"]) >= end_ns:
                        continue
                    events, timestamps, _indices = self._read_row_group_file(parquet, file_entry, group)
                    # Verify each row-group proof before using its index to prune candidates.
                    if self.manifest["ordering"]["timestamps"] == "VERIFIED_NONDECREASING":
                        lo = int(np.searchsorted(timestamps, np.int64(start_ns), side="left"))
                        hi = (len(timestamps) if end_ns == 2**63 else
                              int(np.searchsorted(timestamps, np.int64(end_ns), side="left")))
                        candidates = events[lo:hi]
                    else:  # Defensive fallback if a future manifest version allows unproven order.
                        candidates = [event for event in events
                                      if start_ns <= int(event["timeNs"]) < end_ns]
                    for event in candidates:
                        moment = int(event["timeNs"])
                        ordinal = int(event["rawOrdinal"])
                        source_id = event["provenance"]["sourceId"]
                        require(source_id in self._source_indices,
                                "sourceIdentity", "IDENTITY_CONFLICT")
                        source_index = self._source_indices[source_id]
                        require(moment >= previous_time and source_index >= previous_source and
                                (source_index != previous_source or ordinal > previous_ordinal),
                                "datasetOrder", "ORDER_REVERSAL")
                        previous_time, previous_source, previous_ordinal = moment, source_index, ordinal
                        yield event
            finally:
                parquet.close()

    def iter_groups(self, start_ns, end_ns):
        """Yield whole equal-timestamp groups, even across Arrow batches/groups."""
        pending_time = None
        pending = []
        for event in self.iter_range(start_ns, end_ns):
            time_ns = event["timeNs"]
            if pending_time is not None and time_ns != pending_time:
                yield {"timeNs": pending_time, "events": pending}
                pending = []
            pending_time = time_ns
            pending.append(event)
            require(len(pending) <= MAX_TIMESTAMP_GROUP_EVENTS, "timestampGroup", "GROUP_LIMIT")
        if pending:
            yield {"timeNs": pending_time, "events": pending}

    def verify_all(self):
        """Full, explicit integrity pass; never performed implicitly by a seek."""
        for entry in self._files:
            self.verify_file_hash(entry["month"])
        first = int(self._files[0]["firstTimeNs"])
        last = int(self._files[-1]["lastTimeNs"])
        count = sum(1 for _ in self.iter_range(first, last + 1))
        require(count == self.manifest["eventCount"], "eventCount", "COUNT_CONFLICT")
        return {"status": "PASS", "manifestHash": self.manifest_hash, "eventCount": count}
