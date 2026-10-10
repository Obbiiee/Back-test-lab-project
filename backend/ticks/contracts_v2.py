"""Section 42.17 scalable artifact validators; V1 encoder/wires unchanged."""
import hashlib
import json
from collections.abc import Mapping

from contracts.canonical import _normalize
from contracts.primitives import digest, identifier, require
from .contracts import keys, uint

LIMITS = (256, 1024, 256, 256)
CAPACITY = 17179869184
ZERO_VERSION = "0" * 64
HEADER = "schemaVersion artifact datasetId datasetVersion providerId feedId instrumentId"
SHAPES = {
    "BTL-TICK-DATASET-2": "schemaVersion artifact datasetId providerId feedId instrumentId providerSymbol evidenceClass adapterVersion validatorVersion range ordering eventCount directories sourceCatalogHash evidenceCatalogHash indexContentHash",
    "BTL-TICK-DIRECTORY-2": HEADER + " directoryIndex range eventCount children",
    "BTL-TICK-PARTITION-2": HEADER + " directoryIndex partitionIndex range eventCount children",
    "BTL-TICK-STORAGE-CHUNK-2": HEADER + " directoryIndex partitionIndex chunkIndex firstOrdinal events",
    "BTL-TICK-SOURCE-CATALOG-2": HEADER + " sources",
    "BTL-TICK-EVIDENCE-CATALOG-2": HEADER + " children",
    "BTL-TICK-EVIDENCE-BLOCK-2": HEADER + " blockIndex coverage gaps diagnostics rights",
    "BTL-TICK-TIME-ROOT-2": HEADER + " children",
    "BTL-TICK-TIME-DIRECTORY-2": HEADER + " directoryIndex children",
    "BTL-TICK-TIME-PARTITION-2": HEADER + " directoryIndex partitionIndex partitionHash chunks",
    "BTL-TICK-COMPLETION-2": "schemaVersion artifact datasetId datasetVersion manifestHash validatorVersion indexContentHash sourceCatalogHash",
    "BTL-TICK-INDEX-BINDING-2": "schemaVersion artifact datasetId datasetVersion manifestHash indexContentHash",
    "BTL-TICK-POSITION-2": "schemaVersion artifact datasetId datasetVersion manifestHash directoryIndex partitionIndex chunkIndex eventOffset globalOrdinal",
    "BTL-TICK-PAGE-2": "schemaVersion artifact datasetId datasetVersion events diagnostics nextPosition endOfDataset",
}


def canonical_v2_bytes(value):
    require(isinstance(value, Mapping) and type(value.get("schemaVersion")) is int
            and value["schemaVersion"] == 2, "schemaVersion", "SCHEMA_MISMATCH")
    result = json.dumps(_normalize(value), sort_keys=True, ensure_ascii=False,
                        separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(result) <= 1048576, "serializedSize", "ARTIFACT_LIMIT")
    return result


def hash_v2(value):
    return hashlib.sha256(canonical_v2_bytes(value)).hexdigest()


def payload(value):
    result = {k: v for k, v in value.items() if k != "datasetVersion"}
    if value["artifact"] == "BTL-TICK-STORAGE-CHUNK-2":
        result["events"] = [{k: v for k, v in e.items() if k != "datasetVersion"}
                            for e in value["events"]]
    return result


def content_hash_v2(value):
    return hash_v2(payload(value))


def decode_v2(raw):
    require(type(raw) is bytes and len(raw) <= 1048576, "bytes", "ARTIFACT_LIMIT")
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, "json", "SCHEMA_MISMATCH")
            obj[key] = value
        return obj
    def reject(_):
        require(False, "number", "SCHEMA_MISMATCH")
    obj = json.loads(raw, object_pairs_hook=unique, parse_float=reject, parse_constant=reject)
    require(canonical_v2_bytes(obj) == raw, "canonical", "SCHEMA_MISMATCH")
    return obj


def shape(obj, artifact=None, *, return_bytes=False):
    kind = obj.get("artifact") if type(obj) is dict else None
    require(kind in SHAPES and (artifact is None or kind == artifact), "artifact", "SCHEMA_MISMATCH")
    keys(obj, SHAPES[kind])
    encoded = canonical_v2_bytes(obj)
    for field in ("datasetId", "providerId", "feedId", "instrumentId", "providerSymbol", "adapterVersion", "validatorVersion"):
        if field in obj:
            identifier(obj[field], field)
    for field in ("datasetVersion", "manifestHash", "partitionHash", "sourceCatalogHash", "evidenceCatalogHash", "indexContentHash"):
        if field in obj:
            digest(obj[field], field)
    for field in ("eventCount", "directoryIndex", "partitionIndex", "chunkIndex", "firstOrdinal", "eventOffset", "globalOrdinal", "blockIndex"):
        if field in obj:
            uint(obj[field], field)
    if "directoryIndex" in obj:
        require(int(obj["directoryIndex"]) < 256, "directory", "ARTIFACT_LIMIT")
    if "partitionIndex" in obj:
        require(int(obj["partitionIndex"]) < 1024, "partition", "ARTIFACT_LIMIT")
    if "chunkIndex" in obj:
        require(int(obj["chunkIndex"]) < 256, "chunk", "ARTIFACT_LIMIT")
    if "eventOffset" in obj:
        require(int(obj["eventOffset"]) < 256, "offset", "CORRUPT_INDEX_POINTER")
    if "eventCount" in obj:
        require(0 < int(obj["eventCount"]) <= CAPACITY, "count", "COUNT_CONFLICT")
    if "range" in obj:
        keys(obj["range"], "startNs endNs endExclusive")
        require(uint(obj["range"]["startNs"]) < uint(obj["range"]["endNs"])
                and obj["range"]["endExclusive"] is True, "range", "RANGE_CONFLICT")
    if kind in ("BTL-TICK-TIME-ROOT-2", "BTL-TICK-TIME-DIRECTORY-2"):
        rows = obj["children"]
        maximum = 256 if kind == "BTL-TICK-TIME-ROOT-2" else 1024
        require(type(rows) is list and 1 <= len(rows) <= maximum, "index", "ARTIFACT_LIMIT")
        previous = -1
        for i, row in enumerate(rows):
            keys(row, "index hash firstNs lastNs")
            digest(row["hash"], "index_hash")
            require(uint(row["index"]) == i, "index", "CORRUPT_INDEX_POINTER")
            first, last = uint(row["firstNs"]), uint(row["lastNs"])
            require(previous <= first <= last, "index", "RANGE_CONFLICT")
            previous = last
    if kind == "BTL-TICK-TIME-PARTITION-2":
        rows = obj["chunks"]
        require(type(rows) is list and 1 <= len(rows) <= 256, "index", "ARTIFACT_LIMIT")
        previous, ordinal = -1, None
        for i, row in enumerate(rows):
            keys(row, "chunkIndex chunkHash firstNs lastNs firstOrdinal lastOrdinal firstGroupStart")
            digest(row["chunkHash"], "chunk_hash")
            first, last = uint(row["firstNs"]), uint(row["lastNs"])
            low, high = uint(row["firstOrdinal"]), uint(row["lastOrdinal"])
            require(uint(row["chunkIndex"]) == i and previous <= first <= last and low <= high
                    and (ordinal is None or low == ordinal+1), "index", "CORRUPT_INDEX_POINTER")
            anchor = row["firstGroupStart"]
            keys(anchor, "directoryIndex partitionIndex chunkIndex eventOffset globalOrdinal timeNs")
            for field, limit in (("directoryIndex",256),("partitionIndex",1024),("chunkIndex",256),("eventOffset",256)):
                require(uint(anchor[field]) < limit, "anchor", "CORRUPT_INDEX_POINTER")
            require(uint(anchor["globalOrdinal"]) <= low and uint(anchor["timeNs"]) == first,
                    "anchor", "CORRUPT_INDEX_POINTER")
            previous, ordinal = last, high
    return encoded if return_bytes else obj


def descriptors(rows, maximum, *, first_ordinal=None):
    require(type(rows) is list and 1 <= len(rows) <= maximum, "fanout", "ARTIFACT_LIMIT")
    previous_time, previous_ordinal = -1, None
    for i, d in enumerate(rows):
        keys(d, "index hash eventCount firstNs lastNs firstOrdinal lastOrdinal")
        require(uint(d["index"]) == i, "index", "DUPLICATE_PARTITION")
        digest(d["hash"], "child_hash")
        first, last = uint(d["firstNs"]), uint(d["lastNs"])
        low, high, count = uint(d["firstOrdinal"]), uint(d["lastOrdinal"]), uint(d["eventCount"])
        require(previous_time <= first <= last, "time", "ORDER_REVERSAL")
        require(0 < count == high-low+1, "count", "COUNT_CONFLICT")
        require(previous_ordinal is None or low == previous_ordinal+1, "ordinal", "INVALID_SOURCE_ORDINAL")
        require(len(json.dumps(d, separators=(",", ":")).encode()) <= 2048, "descriptor", "ARTIFACT_LIMIT")
        previous_time, previous_ordinal = last, high
    if first_ordinal is not None:
        require(int(rows[0]["firstOrdinal"]) == first_ordinal, "ordinal", "INVALID_SOURCE_ORDINAL")


def interval_for(children):
    return dict(startNs=children[0]["firstNs"], endNs=str(int(children[-1]["lastNs"])+1), endExclusive=True)


def summary(index, child, *, verified_hash=None):
    if "events" in child:
        rows = child["events"]
        first, last, count = rows[0]["timeNs"], rows[-1]["timeNs"], len(rows)
        low = int(child["firstOrdinal"])
    else:
        ds = child["children"]
        first, last = ds[0]["firstNs"], ds[-1]["lastNs"]
        count, low = sum(int(d["eventCount"]) for d in ds), int(ds[0]["firstOrdinal"])
    return dict(index=str(index), hash=content_hash_v2(child) if verified_hash is None else verified_hash, eventCount=str(count),
                firstNs=first, lastNs=last, firstOrdinal=str(low), lastOrdinal=str(low+count-1))


def validate_container(obj, root, *, expected_hash=None, expected_descriptor=None):
    shape(obj)
    for field in ("datasetId", "providerId", "feedId", "instrumentId"):
        require(obj[field] == root[field], field, "IDENTITY_CONFLICT")
    if expected_hash is not None:
        require(content_hash_v2(obj) == expected_hash, "hash", "CHILD_HASH_MISMATCH")
    if obj["artifact"] in ("BTL-TICK-DIRECTORY-2", "BTL-TICK-PARTITION-2"):
        descriptors(obj["children"], 1024 if obj["artifact"] == "BTL-TICK-DIRECTORY-2" else 256)
        require(obj["range"] == interval_for(obj["children"]), "range", "RANGE_CONFLICT")
        require(int(obj["eventCount"]) == sum(int(d["eventCount"]) for d in obj["children"]), "count", "COUNT_CONFLICT")
    if expected_descriptor is not None:
        require(summary(int(expected_descriptor["index"]), obj) == expected_descriptor, "descriptor", "RANGE_CONFLICT")


def validate_root(root):
    shape(root, "BTL-TICK-DATASET-2")
    require(root["evidenceClass"] in ("PROVIDER_OBSERVATION", "SYNTHETIC_CONTRACT_ONLY"), "evidence")
    ordering = root["ordering"]
    keys(ordering, "timestamps ties sequenceScope sequenceEvidenceHash")
    require(ordering["timestamps"] == "VERIFIED_NONDECREASING", "ordering", "UNVERIFIED_ORDER")
    require(ordering["ties"] in ("UNTRUSTED", "TRUSTED_SEQUENCE"), "ties")
    require((ordering["sequenceScope"] is None) == (ordering["sequenceEvidenceHash"] is None), "sequence")
    if ordering["sequenceScope"] is not None:
        identifier(ordering["sequenceScope"], "scope"); digest(ordering["sequenceEvidenceHash"], "sequence_hash")
    require(ordering["ties"] != "TRUSTED_SEQUENCE" or ordering["sequenceScope"] is not None, "sequence")
    descriptors(root["directories"], 256, first_ordinal=0)
    require(root["range"] == interval_for(root["directories"]), "range", "RANGE_CONFLICT")
    require(int(root["eventCount"]) == sum(int(d["eventCount"]) for d in root["directories"]), "count", "COUNT_CONFLICT")
    return root
