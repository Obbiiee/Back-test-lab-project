"""Frozen 42.19 private sidecars, bounded queries and causal page validation.

Declarations remain private. Coverage has no causal availability proof and is
therefore uniformly UNKNOWN. Audited row-local diagnostics require a source fence.
"""
from copy import deepcopy
import sqlite3

from contracts.primitives import require, digest, identifier
from .contracts import keys, uint, interval_rows, nullable_hash
from .contracts_v2 import canonical_v2_bytes, hash_v2, shape, validate_container
from .provider import diagnostic_counts

WINDOW_NS = 86400000000000
ROW_LOCAL = frozenset(("MALFORMED_PRICE", "MISSING_SIDE", "CROSSED_QUOTE", "UNSUPPORTED_RESOLUTION"))
CODES = ROW_LOCAL | {"INVALID_TIMESTAMP", "ORDER_REVERSAL", "SUSPECT_REPEAT"}
REQUEST = "schemaVersion artifact datasetId datasetVersion manifestHash sessionStartNs fromNs throughNs sourceFence maxRecords cursor"
PAGE = "schemaVersion artifact datasetId datasetVersion manifestHash evidenceCatalogHash requestHash coverage diagnostics nextCursor"
CURSOR = "schemaVersion artifact datasetId datasetVersion manifestHash evidenceCatalogHash requestHash blockIndex entryOffset"


def diagnostic(record, root, sources):
    keys(record, "sourceId memberHash rawOrdinal timeNs code rawRecordHash")
    source = next((s for s in sources if s["sourceId"] == record["sourceId"]), None)
    require(source is not None and source["memberHash"] == record["memberHash"], "source", "IDENTITY_CONFLICT")
    digest(record["rawRecordHash"], "rawRecordHash")
    uint(record["rawOrdinal"])
    require(record["timeNs"] is not None, "location", "UNLOCATED_INVALID_RECORD")
    time = uint(record["timeNs"])
    require(int(root["range"]["startNs"]) <= time < int(root["range"]["endNs"]), "time", "RANGE_CONFLICT")
    require(record["code"] in CODES, "code", "SCHEMA_MISMATCH")
    require(record["code"] != "INVALID_TIMESTAMP", "location", "UNLOCATED_INVALID_RECORD")


def entries(block):
    for kind in ("coverage", "gaps", "diagnostics"):
        for row in block[kind]:
            yield kind, row


def validate_block(block, descriptor, root, sources):
    validate_container(block, root, expected_hash=descriptor["hash"])
    shape(block, "BTL-TICK-EVIDENCE-BLOCK-2")
    require(block["blockIndex"] == descriptor["index"], "block", "CORRUPT_INDEX_POINTER")
    require(all(type(block[k]) is list for k in ("coverage", "gaps", "diagnostics")), "entries", "SCHEMA_MISMATCH")
    count = sum(len(block[k]) for k in ("coverage", "gaps", "diagnostics"))
    require(count <= 128 and uint(descriptor["recordCount"]) == count, "count", "EVIDENCE_LIMIT")
    interval_rows(block["coverage"], root["range"], "coverage")
    interval_rows(block["gaps"], root["range"], "gaps")
    for record in block["diagnostics"]:
        diagnostic(record, root, sources)
    rights = block["rights"]
    keys(rights, "class evidenceHash")
    nullable_hash(rights["evidenceHash"])
    require(rights["class"] in ("SYNTHETIC", "PERSONAL_ONLY", "PUBLIC_GRANTED", "UNKNOWN"), "rights", "SCHEMA_MISMATCH")
    require(root["evidenceClass"] != "SYNTHETIC_CONTRACT_ONLY" or rights["class"] == "SYNTHETIC", "rights", "IDENTITY_CONFLICT")
    require(root["evidenceClass"] != "PROVIDER_OBSERVATION" or rights["class"] != "SYNTHETIC", "rights", "IDENTITY_CONFLICT")
    require(rights["class"] not in ("PERSONAL_ONLY", "PUBLIC_GRANTED") or rights["evidenceHash"] is not None, "rights", "SCHEMA_MISMATCH")
    start, end = None, None
    for kind, row in entries(block):
        lo = uint(row["timeNs"] if kind == "diagnostics" else row["startNs"])
        hi = lo if kind == "diagnostics" else uint(row["endNs"])-1
        start = lo if start is None else min(start, lo)
        end = hi if end is None else max(end, hi)
    if start is None:
        start = end = int(root["range"]["startNs"])
    require((descriptor["firstNs"], descriptor["lastNs"]) == (str(start), str(end)), "range", "RANGE_CONFLICT")


def catalog(store, root, version):
    obj = store.get(root["evidenceCatalogHash"], version)
    validate_container(obj, root, expected_hash=root["evidenceCatalogHash"])
    shape(obj, "BTL-TICK-EVIDENCE-CATALOG-2")
    rows = obj["children"]
    require(type(rows) is list and len(rows) <= 256, "catalog", "EVIDENCE_LIMIT")
    for i, row in enumerate(rows):
        keys(row, "index hash firstNs lastNs recordCount")
        require(uint(row["index"]) == i, "block", "CORRUPT_INDEX_POINTER")
        digest(row["hash"], "blockHash")
        require(uint(row["firstNs"]) <= uint(row["lastNs"]), "range", "RANGE_CONFLICT")
        require(uint(row["recordCount"]) <= 128, "count", "EVIDENCE_LIMIT")
    return obj


def accept_sidecars(store, root, version, sources, *, audit_record=None, cancellation=None):
    """All-block acceptance; interval ordering/uniqueness stay in disk temp tables.

    audit_record is an adapter-owned verification of actual original row bytes,
    code, time and source identity; a claimed hash alone cannot pass publication.
    """
    obj = catalog(store, root, version)
    db = store.db
    db.execute("CREATE TEMP TABLE IF NOT EXISTS evidence_intervals(kind TEXT, start TEXT, end TEXT, status TEXT)")
    db.execute("CREATE TEMP TABLE IF NOT EXISTS evidence_records(source TEXT, ordinal TEXT, code TEXT, body TEXT, PRIMARY KEY(source,ordinal,code)) WITHOUT ROWID")
    db.execute("DELETE FROM evidence_intervals")
    db.execute("DELETE FROM evidence_records")
    rights = None
    try:
        import json
        for d in obj["children"]:
            if cancellation is not None:
                cancellation.check()
            block = store.get(d["hash"], version)
            validate_block(block, d, root, sources)
            require(rights is None or rights == block["rights"], "rights", "IDENTITY_CONFLICT")
            rights = block["rights"]
            for kind, row in entries(block):
                if kind != "diagnostics":
                    db.execute("INSERT INTO evidence_intervals VALUES(?,?,?,?)", (kind, row["startNs"].zfill(23), row["endNs"].zfill(23), row.get("status", row.get("kind"))))
                else:
                    require(audit_record is not None and audit_record(deepcopy(row)) is True, "original_record", "INCOMPLETE_DIAGNOSTICS")
                    try:
                        db.execute("INSERT INTO evidence_records VALUES(?,?,?,?)", (row["sourceId"], row["rawOrdinal"], row["code"], json.dumps(row)))
                    except sqlite3.IntegrityError:
                        require(False, "diagnostic", "IDENTITY_CONFLICT")
        for kind in ("coverage", "gaps"):
            previous = ""
            for start, end in db.execute("SELECT start,end FROM evidence_intervals WHERE kind=? ORDER BY start,end", (kind,)):
                require(start >= previous, "interval", "COVERAGE_CONFLICT")
                previous = end
        conflict = db.execute("SELECT 1 FROM evidence_intervals c JOIN evidence_intervals g ON c.start<g.end AND g.start<c.end WHERE c.kind='coverage' AND c.status='DECLARED_COMPLETE' AND g.kind='gaps' LIMIT 1").fetchone()
        require(conflict is None, "coverage", "COVERAGE_CONFLICT")
        for (raw,) in db.execute("SELECT body FROM evidence_records"):
            row = json.loads(raw)
            retained = db.execute("SELECT 1 FROM identities WHERE source=? AND ordinal=?",
                                  (row["sourceId"], row["rawOrdinal"])).fetchone()
            # Retained crossed/missing-side quotes carry their own conservative
            # quality. Quarantining that same invalid input removes the tick,
            # so its located hole must instead be preserved in private gaps.
            quarantined = row["code"] in (ROW_LOCAL | {"ORDER_REVERSAL"}) and retained is None
            if quarantined or row["code"] in ("MALFORMED_PRICE", "UNSUPPORTED_RESOLUTION"):
                time = row["timeNs"].zfill(23)
                missing = db.execute("SELECT 1 FROM evidence_intervals WHERE kind='gaps' AND status='MISSING_DATA' AND start<=? AND end>? LIMIT 1", (time, time)).fetchone()
                require(missing is not None, "invalid_record", "INCOMPLETE_DIAGNOSTICS")
    finally:
        db.execute("DROP TABLE evidence_intervals")
        db.execute("DROP TABLE evidence_records")


def query(request, root, version, sources):
    keys(request, REQUEST)
    require(request["artifact"] == "BTL-TICK-EVIDENCE-REQUEST-2", "request", "SCHEMA_MISMATCH")
    canonical_v2_bytes(request)
    require(request["datasetId"] == root["datasetId"], "dataset", "DATASET_MISMATCH")
    require(request["datasetVersion"] == version and request["manifestHash"] == version, "version", "VERSION_MISMATCH")
    start, low, high = (uint(request[k]) for k in ("sessionStartNs", "fromNs", "throughNs"))
    require(start <= low <= high and high-low <= WINDOW_NS, "window", "RANGE_CONFLICT")
    require(type(request["maxRecords"]) is int and 1 <= request["maxRecords"] <= 128, "quota", "EVIDENCE_LIMIT")
    require(type(request["sourceFence"]) is list and len(request["sourceFence"]) <= 128, "fence", "EVIDENCE_LIMIT")
    order = {s["sourceId"]: i for i, s in enumerate(sources)}
    fence, previous = {}, -1
    for pair in request["sourceFence"]:
        keys(pair, "sourceId rawOrdinal")
        i = order.get(pair["sourceId"], -1)
        require(i > previous, "fence", "IDENTITY_CONFLICT")
        fence[pair["sourceId"]] = uint(pair["rawOrdinal"])
        previous = i
    return hash_v2(dict(request, cursor=None)), fence


def cursor(value, request_hash, root, version, descriptors):
    keys(value, CURSOR)
    require(value["artifact"] == "BTL-TICK-EVIDENCE-CURSOR-2", "cursor", "SCHEMA_MISMATCH")
    canonical_v2_bytes(value)
    require(value["datasetId"] == root["datasetId"] and value["datasetVersion"] == version and value["manifestHash"] == version
            and value["evidenceCatalogHash"] == root["evidenceCatalogHash"] and value["requestHash"] == request_hash, "cursor", "IDENTITY_CONFLICT")
    bi, offset = uint(value["blockIndex"]), uint(value["entryOffset"])
    require(bi < len(descriptors) and offset < int(descriptors[bi]["recordCount"]), "pointer", "CORRUPT_INDEX_POINTER")
    return bi, offset


def eligible(record, request, fence):
    return (record["code"] in ROW_LOCAL and int(request["sessionStartNs"]) <= int(record["timeNs"]) <= int(request["throughNs"])
            and record["sourceId"] in fence and int(record["rawOrdinal"]) <= fence[record["sourceId"]])


def read_sidecars(store, root, version, sources, request):
    request_hash, fence = query(request, root, version, sources)
    ds = catalog(store, root, version)["children"]
    initial = request["cursor"] is None
    bi, offset = (0, 0) if initial else cursor(request["cursor"], request_hash, root, version, ds)
    coverage = [] if not initial or request["fromNs"] == request["throughNs"] else [dict(startNs=request["fromNs"], endNs=request["throughNs"], status="UNKNOWN", evidenceHash=None)]
    records, successor = [], None
    quota = request["maxRecords"]-len(coverage)
    for index in range(bi, len(ds)):
        d = ds[index]
        block = store.get(d["hash"], version)
        validate_block(block, d, root, sources)
        for entry_index, (kind, row) in enumerate(entries(block)):
            if index == bi and entry_index < offset:
                continue
            if kind == "diagnostics" and eligible(row, request, fence):
                if len(records) == quota:
                    successor = dict(schemaVersion=2, artifact="BTL-TICK-EVIDENCE-CURSOR-2", datasetId=root["datasetId"], datasetVersion=version,
                        manifestHash=version, evidenceCatalogHash=root["evidenceCatalogHash"], requestHash=request_hash, blockIndex=str(index), entryOffset=str(entry_index))
                    break
                records.append(deepcopy(row))
        if successor is not None:
            break
    page = dict(schemaVersion=2, artifact="BTL-TICK-EVIDENCE-PAGE-2", datasetId=root["datasetId"], datasetVersion=version,
                manifestHash=version, evidenceCatalogHash=root["evidenceCatalogHash"], requestHash=request_hash, coverage=coverage,
                diagnostics=dict(records=records, counts=diagnostic_counts(records), truncated=False), nextCursor=successor)
    canonical_v2_bytes(page)
    return page
