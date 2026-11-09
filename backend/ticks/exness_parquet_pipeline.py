"""Private, resumable CSV/ZIP-to-existing-Monthly-Parquet preparation.

No downloader is implemented: all inputs are explicitly supplied local files.
The pipeline uses BTL-CANONICAL-TICK-1 and the existing immutable
MonthlyParquetProvider/writer. It never exposes a source through the runtime
catalog; admission remains a separately pinned rights operation.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

from contracts.canonical import canonical_bytes, content_hash, decimal_text
from contracts.primitives import ContractError, decimal, require
from market_data.monthly_parquet import MonthlyParquetProvider, write_monthly_parquet
from ticks.contracts import TickManifest, chunk_content, event_id
from ticks.contracts_v2 import ZERO_VERSION
from .exness_monthly import (
    END_MONTH, END_YEAR, INSTRUMENTS, START_MONTH, START_YEAR,
    Partition, inspect_zip, partition_for, required_partitions, sha256_file,
)
from .exness_v2 import FIELDS, TICK_HISTORY_FIELDS


INVENTORY_ARTIFACT = "RIKSORA-EXNESS-MONTHLY-INVENTORY-1"
RIGHTS_ARTIFACT = "RIKSORA-EXNESS-RIGHTS-EVIDENCE-1"
RIGHTS = ("automatedAcquisition", "privateStorage", "commercialCompute",
          "derivedPresentation", "redistribution", "retention")
STATUSES = frozenset(("PENDING", "AVAILABLE", "VERIFIED", "FAILED", "BLOCKED"))
MAX_SOURCE_BYTES = 16 * 1024**3
MAX_SOURCE_ROW_BYTES = 8192
MAX_MANIFEST_CHUNKS = 4096
CHUNK_EVENTS = 1024
STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}Z\Z")


def _period(year, month):
    return f"{year:04d}-{month:02d}"


def _epoch_ns(text):
    require(STAMP.fullmatch(text) is not None, "timestamp", "INVALID_TIMESTAMP")
    try:
        moment = datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        require(False, "timestamp", "INVALID_TIMESTAMP")
    return int(moment.timestamp()) * 1_000_000_000 + moment.microsecond * 1000


def _source_rows(path, symbol):
    """Validate the whole source in source order and yield exact raw ordinals."""
    previous_ns = None
    with Path(path).open("rb") as stream:
        first = stream.readline(MAX_SOURCE_ROW_BYTES + 1)
        require(0 < len(first) <= MAX_SOURCE_ROW_BYTES, "header", "ARTIFACT_LIMIT")
        header = next(csv.reader([first.decode("utf-8-sig").rstrip("\r\n")], strict=True), None)
        require(header in (FIELDS, TICK_HISTORY_FIELDS), "header", "SCHEMA_MISMATCH")
        ordinal = 0
        while raw := stream.readline(MAX_SOURCE_ROW_BYTES + 1):
            require(len(raw) <= MAX_SOURCE_ROW_BYTES, "record", "ARTIFACT_LIMIT")
            row = next(csv.reader([raw.decode("utf-8").rstrip("\r\n")], strict=True))
            require(len(row) == len(header), "record", "MALFORMED_RECORD")
            fields = dict(zip(header, row))
            require(fields.get("Exness", "exness") == "exness" and fields.get("Symbol") == symbol,
                    "symbol", "IDENTITY_CONFLICT")
            timestamp = fields.get("Timestamp")
            time_ns = _epoch_ns(timestamp)
            require(previous_ns is None or time_ns >= previous_ns, "timestamp", "ORDER_REVERSAL")
            try:
                bid = Decimal(fields["Bid"])
                ask = Decimal(fields["Ask"])
            except (KeyError, InvalidOperation):
                require(False, "price", "MALFORMED_PRICE")
            require(bid.is_finite() and ask.is_finite() and bid > 0 and ask > 0,
                    "price", "MALFORMED_PRICE")
            previous_ns = time_ns
            yield ordinal, timestamp, time_ns, decimal_text(decimal(bid, "bid", positive=True)), \
                decimal_text(decimal(ask, "ask", positive=True))
            ordinal += 1


def _event(row, *, dataset_id, feed_id, instrument_id, symbol, source_id, member_hash,
           provider_id="exness", version=ZERO_VERSION):
    ordinal, original_timestamp, time_ns, bid, ask = row
    crossed = Decimal(ask) < Decimal(bid)
    return {
        "schemaVersion": 1, "artifact": "BTL-CANONICAL-TICK-1",
        "datasetId": dataset_id, "datasetVersion": version,
        "providerId": provider_id, "feedId": feed_id, "instrumentId": instrument_id,
        "eventId": event_id(provider_id, feed_id, member_hash, str(ordinal)),
        "timeNs": str(time_ns), "resolutionNs": "1000000", "bid": bid, "ask": ask,
        "rawOrdinal": str(ordinal), "trustedSequence": None,
        "provenance": {"sourceId": source_id, "memberHash": member_hash,
                       "originalTimestamp": original_timestamp},
        "quality": {"evidenceHash": None, "quote": "CROSSED" if crossed else "VALID",
                    "freshness": "UNKNOWN", "gapBefore": "UNKNOWN_SILENCE", "duplicateOf": None},
    }


def _source_manifest(csv_path, partition, *, archive_hash=None, original_name=None,
                     synthetic_fixture=False):
    source_hash = sha256_file(csv_path)
    source_id = ("synthetic:exness-csv-fixture" if synthetic_fixture else
                 "exness:csv:" + source_hash[:24])
    dataset_id = (f"synthetic:exness-csv:{source_hash[:24]}:{partition.period}" if synthetic_fixture else
                  f"local:exness:{source_hash[:24]}:{partition.period}")
    provider_id = "SYNTHETIC" if synthetic_fixture else "exness"
    feed_id = "SYNTHETIC_EXNESS_CSV_FIXTURE" if synthetic_fixture else f"local-unverified:{partition.original_symbol}"
    instrument_id = "SYNTHETIC_INSTRUMENT" if synthetic_fixture else f"exness:{partition.original_symbol}"
    provider_symbol = "SYNTHETIC_TEST_ONLY" if synthetic_fixture else partition.original_symbol
    source = {"sourceId": source_id, "archiveHash": archive_hash, "memberHash": source_hash,
        "originalName": (("SYNTHETIC_ONLY_" if synthetic_fixture else "") +
                         (original_name or Path(csv_path).name)), "acquiredAtUtc": None, "sourceUrl": None,
        "timestampConvention": ("SYNTHETIC_ONLY CSV UTC Z millisecond fixture" if synthetic_fixture else
            "CSV UTC Z millisecond timestamps; provenance and equal-time chronology unverified"),
        "resolutionNs": "1000000", "originalScalePolicy": "PRESERVE_RAW_TEXT"}
    chunk_descriptors = []
    events, first_ns, last_ns = [], None, None
    for row in _source_rows(csv_path, partition.original_symbol):
        if datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S.%fZ").strftime("%Y-%m") != partition.period:
            continue
        first_ns = row[2] if first_ns is None else first_ns
        last_ns = row[2]
        events.append(_event(row, dataset_id=dataset_id, feed_id=feed_id,
            instrument_id=instrument_id, symbol=partition.original_symbol,
            source_id=source_id, member_hash=source_hash, provider_id=provider_id))
        if len(events) == CHUNK_EVENTS:
            chunk_descriptors.append(_chunk_descriptor(events, dataset_id, len(chunk_descriptors)))
            events = []
    if events:
        chunk_descriptors.append(_chunk_descriptor(events, dataset_id, len(chunk_descriptors)))
    require(chunk_descriptors and first_ns is not None and last_ns is not None,
            "period", "REFUSED_SOURCE_NOT_AVAILABLE")
    require(len(chunk_descriptors) <= MAX_MANIFEST_CHUNKS, "chunks", "ARTIFACT_LIMIT")
    manifest = {
        "schemaVersion": 1, "artifact": "BTL-TICK-MANIFEST-1",
        "datasetId": dataset_id, "providerId": provider_id, "feedId": feed_id,
        "instrumentId": instrument_id, "providerSymbol": provider_symbol,
        "evidenceClass": "SYNTHETIC_CONTRACT_ONLY" if synthetic_fixture else "PROVIDER_OBSERVATION",
        "adapterVersion": "SYNTHETIC-EXNESS-CSV-1" if synthetic_fixture else "EXNESS-MONTHLY-PARQUET-1",
        "validatorVersion": "BTL-TICK-VALIDATOR-2", "sources": [source],
        "range": {"startNs": str(first_ns), "endNs": str(last_ns + 1), "endExclusive": True},
        "ordering": {"timestamps": "VERIFIED_NONDECREASING", "ties": "UNTRUSTED",
                      "sequenceScope": None, "sequenceEvidenceHash": None},
        "coverage": [], "gaps": [], "rights": ({"class": "SYNTHETIC", "evidenceHash": None}
            if synthetic_fixture else {"class": "UNKNOWN", "evidenceHash": None}),
        "diagnostics": [], "chunks": chunk_descriptors,
    }
    checked = TickManifest.from_wire(manifest)
    return checked.wire, checked.version, source_hash, (first_ns, last_ns)


def _chunk_descriptor(events, dataset_id, index):
    chunk = {"schemaVersion": 1, "artifact": "BTL-TICK-CHUNK-1", "datasetId": dataset_id,
             "datasetVersion": ZERO_VERSION, "chunkIndex": str(index), "events": events}
    return {"chunkIndex": str(index), "hash": content_hash(chunk_content(chunk)),
            "eventCount": len(events), "firstNs": events[0]["timeNs"],
            "lastNs": events[-1]["timeNs"]}


def _events_for(csv_path, partition, source_manifest, dataset_version):
    source = source_manifest["sources"][0]
    for row in _source_rows(csv_path, partition.original_symbol):
        if datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S.%fZ").strftime("%Y-%m") == partition.period:
            yield _event(row, dataset_id=source_manifest["datasetId"],
                feed_id=source_manifest["feedId"], instrument_id=source_manifest["instrumentId"],
            symbol=partition.original_symbol, source_id=source["sourceId"],
            member_hash=source["memberHash"], provider_id=source_manifest["providerId"],
            version=dataset_version)


def validate_rights_evidence(path, expected_sha256):
    """Require separately reviewed, hash-pinned rights for all requested uses."""
    actual = sha256_file(path)
    require(actual == expected_sha256, "rightsEvidence", "SOURCE_PIN_CHANGED")
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    require(type(value) is dict and value.get("schemaVersion") == 1 and
            value.get("artifact") == RIGHTS_ARTIFACT and
            type(value.get("reviewer")) is str and value["reviewer"].strip() and
            type(value.get("providerEntity")) is str and value["providerEntity"].strip() and
            type(value.get("evidenceSha256")) is str and
            re.fullmatch(r"[0-9a-f]{64}", value["evidenceSha256"]) is not None and
            type(value.get("permissions")) is dict and
            set(value["permissions"]) == set(RIGHTS) and
            all(value["permissions"][scope] is True for scope in RIGHTS),
            "rightsEvidence", "REFUSED_SOURCE")
    return actual, value


class ExnessInventory:
    """Private status map for all 544 logical partitions; never a runtime catalog."""
    def __init__(self, path, *, rights_ready=False):
        self.path = Path(path)
        self.rights_ready = rights_ready
        self.partitions = {}
        if self.path.exists():
            value = json.loads(self.path.read_text(encoding="utf-8"))
            require(value.get("schemaVersion") == 1 and value.get("artifact") == INVENTORY_ARTIFACT,
                    "inventory", "SCHEMA_MISMATCH")
            self.partitions = value["partitions"]
            expected = {self.key(row) for row in required_partitions()}
            require(type(self.partitions) is dict and set(self.partitions) == expected and
                    all(type(row) is dict and row.get("status") in STATUSES
                        for row in self.partitions.values()),
                    "inventory", "SCHEMA_MISMATCH")
        else:
            initial = "PENDING" if rights_ready else "BLOCKED"
            reason = None if rights_ready else "PROVIDER_RIGHTS_NOT_VERIFIED"
            for row in required_partitions():
                self.partitions[self.key(row)] = {"originalSymbol": row.original_symbol,
                    "canonicalInstrument": row.canonical_instrument, "year": row.year,
                    "month": row.month, "status": initial, "reason": reason}
            self._save()

    @staticmethod
    def key(partition):
        return f"{partition.original_symbol}/{partition.year:04d}-{partition.month:02d}"

    def status(self, partition):
        return self.partitions[self.key(partition)]["status"]

    def block_all(self, reason):
        self.partitions = {key: {**row, "status": "BLOCKED", "reason": reason}
                           for key, row in self.partitions.items()}
        self._save()

    def update_symbol(self, symbol, status, **evidence):
        require(status in STATUSES, "status", "INVALID_INPUT")
        matched = False
        for key, row in self.partitions.items():
            if row["originalSymbol"] == symbol:
                self.partitions[key] = {**row, **evidence, "status": status}
                matched = True
        require(matched, "symbol", "IDENTITY_CONFLICT")
        self._save()

    def update(self, partition, status, **evidence):
        require(status in STATUSES, "status", "INVALID_INPUT")
        row = self.partitions[self.key(partition)]
        if status == "VERIFIED" and evidence.get("manifestHash") is not None:
            history = list(row.get("versions", []))
            version = {key: evidence[key] for key in
                       ("datasetId", "datasetVersion", "manifestHash", "eventCount", "root", "files")
                       if key in evidence}
            if version and not any(item.get("manifestHash") == version["manifestHash"] for item in history):
                history.append(version)
            evidence["versions"] = history
        self.partitions[self.key(partition)] = {**row, **evidence, "status": status}
        self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        value = {"schemaVersion": 1, "artifact": INVENTORY_ARTIFACT,
            "layout": "EXISTING_MONTHLY_PARQUET_YYYY-MM_TICKS_PARQUET",
            "rightsStatus": "VERIFIED" if self.rights_ready else "BLOCKED",
            "period": {"start": f"{START_YEAR:04d}-{START_MONTH:02d}",
                       "endInclusive": f"{END_YEAR:04d}-{END_MONTH:02d}"},
            "partitionCount": 544, "partitions": self.partitions}
        raw = canonical_bytes(value)
        fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def _existing_verified(root, partition, *, member_hash, archive_hash=None, synthetic_fixture=False):
    manifest_path = Path(root) / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_bytes())
        provider = MonthlyParquetProvider(root, expected_dataset_id=manifest["datasetId"],
            expected_dataset_version=manifest["datasetVersion"],
            expected_manifest_hash=manifest["manifestHash"])
        source = provider.manifest["sourceManifest"]
        source_row = source["sources"][0]
        expected_id = (f"synthetic:exness-csv:{member_hash[:24]}:{partition.period}" if synthetic_fixture else
                       f"local:exness:{member_hash[:24]}:{partition.period}")
        require(provider.dataset_id == expected_id and source_row["memberHash"] == member_hash and
                source_row["archiveHash"] == archive_hash and
                source["providerSymbol"] == ("SYNTHETIC_TEST_ONLY" if synthetic_fixture else partition.original_symbol) and
                source["instrumentId"] == ("SYNTHETIC_INSTRUMENT" if synthetic_fixture else f"exness:{partition.original_symbol}") and
                _period_for_ns(int(source["range"]["startNs"]))[:4] == f"{partition.year:04d}" and
                _period_for_ns(int(source["range"]["startNs"])) == partition.period,
                "existingDataset", "IDENTITY_CONFLICT")
        provider.verify_file_hash(partition.period)
        return {"status": "VERIFIED", "datasetId": provider.dataset_id,
                "datasetVersion": provider.dataset_version, "manifestHash": provider.manifest_hash,
                "eventCount": provider.manifest["eventCount"], "files": provider.manifest["files"],
                "root": str(Path(root).resolve()), "reused": True}
    except (ContractError, OSError, KeyError, ValueError, StopIteration):
        require(False, "existingDataset", "IMMUTABLE_IDENTITY_CONFLICT")


def _period_for_ns(value):
    return datetime.fromtimestamp(value // 1_000_000_000, timezone.utc).strftime("%Y-%m")


def convert_csv_partition(csv_path, partition: Partition, output_root, *, archive_hash=None,
                          original_name=None, inventory=None, rights_evidence_path=None,
                          rights_evidence_sha256=None,
                          synthetic_fixture=False, row_group_size=65_536):
    """Convert one observed UTC month, or reuse its exact verified publication."""
    require(type(synthetic_fixture) is bool, "syntheticFixture", "INVALID_INPUT")
    rights_hash = None
    rights_json = None
    if not synthetic_fixture:
        require(rights_evidence_path is not None and rights_evidence_sha256 is not None,
                "rightsEvidence", "REFUSED_SOURCE")
        _rights_hash, rights_json = validate_rights_evidence(rights_evidence_path,
                                                              rights_evidence_sha256)
    source_hash = sha256_file(csv_path)
    output_root = Path(output_root)
    if output_root.exists():
        result = _existing_verified(output_root, partition, member_hash=source_hash,
                                    archive_hash=archive_hash, synthetic_fixture=synthetic_fixture)
        if inventory is not None:
            inventory.update(partition, "VERIFIED", **{k:v for k,v in result.items() if k != "status"})
        return result
    if inventory is not None:
        inventory.update(partition, "AVAILABLE", sourceSha256=source_hash,
                         archiveSha256=archive_hash, sourceName=original_name or Path(csv_path).name)
    source_manifest, source_version, pinned_source_hash, bounds = _source_manifest(
        csv_path, partition, archive_hash=archive_hash, original_name=original_name,
        synthetic_fixture=synthetic_fixture)
    require(pinned_source_hash == source_hash, "source", "SOURCE_PIN_CHANGED")
    if rights_json is not None:
        source_manifest["rights"] = {"class": "PUBLIC_GRANTED", "evidenceHash": rights_json["evidenceSha256"]}
        source_version = TickManifest.from_wire(source_manifest).version
    # Price/time event identity is tied to exact source bytes and source row
    # ordinal. Contract-only fixtures use a distinct synthetic provider identity.
    events = _events_for(csv_path, partition, source_manifest, source_version)
    result_manifest = write_monthly_parquet(output_root, events, source_manifest,
        expected_version=source_version, row_group_size=row_group_size)
    require(sha256_file(csv_path) == source_hash, "source", "SOURCE_PIN_CHANGED")
    provider = MonthlyParquetProvider(output_root, expected_dataset_id=source_manifest["datasetId"],
        expected_dataset_version=source_version, expected_manifest_hash=result_manifest["manifestHash"])
    provider.verify_all()
    provider.verify_file_hash(partition.period)
    result = {"status": "VERIFIED", "datasetId": source_manifest["datasetId"],
        "datasetVersion": source_version, "manifestHash": result_manifest["manifestHash"],
        "eventCount": result_manifest["eventCount"], "files": result_manifest["files"],
        "root": str(output_root.resolve()), "reused": False,
        "sourceSha256": source_hash, "rights": source_manifest["rights"]}
    if inventory is not None:
        inventory.update(partition, "VERIFIED", **{k:v for k,v in result.items() if k != "status"})
    return result


def extract_zip_member(zip_path, member_name, destination):
    """Stream one explicitly selected CSV member; never trusts member paths."""
    metadata = inspect_zip(zip_path)
    matches = [member for member in metadata["members"] if member["name"] == member_name and member["isCsv"]]
    require(len(matches) == 1, "archiveMember", "REFUSED_SOURCE_NOT_AVAILABLE")
    destination = Path(destination)
    total = 0
    with zipfile.ZipFile(zip_path) as archive, archive.open(member_name, "r") as source, \
            destination.open("xb") as target:
        while block := source.read(1024 * 1024):
            total += len(block)
            require(total <= MAX_SOURCE_BYTES, "archiveMember", "ARTIFACT_LIMIT")
            target.write(block)
        target.flush()
        os.fsync(target.fileno())
    require(total == matches[0]["bytes"], "archiveMember", "CORRUPT_RECORD")
    return metadata["sha256"], sha256_file(destination), total


def convert_zip_member(zip_path, member_name, partition, output_root, *, inventory=None,
                       rights_evidence_path=None, rights_evidence_sha256=None,
                       synthetic_fixture=False, row_group_size=65_536):
    archive_hash = sha256_file(zip_path)
    output_root = Path(output_root)
    if output_root.exists():
        manifest_path = output_root / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes()) if manifest_path.is_file() else {}
        source = manifest.get("sourceManifest", {}).get("sources", [{}])[0]
        if source.get("archiveHash") == archive_hash and source.get("originalName") == member_name:
            result = _existing_verified(output_root, partition,
                member_hash=source.get("memberHash"), archive_hash=archive_hash,
                synthetic_fixture=synthetic_fixture)
            if inventory is not None:
                inventory.update(partition, "VERIFIED", **{k:v for k,v in result.items() if k != "status"})
            return result
        require(False, "existingDataset", "IMMUTABLE_IDENTITY_CONFLICT")
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".exness-source-", dir=output_root.parent) as temp:
        csv_path = Path(temp) / "source.csv"
        got_archive, _member_hash, _bytes = extract_zip_member(zip_path, member_name, csv_path)
        require(got_archive == archive_hash, "archive", "SOURCE_PIN_CHANGED")
        return convert_csv_partition(csv_path, partition, output_root, archive_hash=archive_hash,
            original_name=member_name, inventory=inventory,
            rights_evidence_path=rights_evidence_path,
            rights_evidence_sha256=rights_evidence_sha256,
            synthetic_fixture=synthetic_fixture, row_group_size=row_group_size)


def process_csv_source(csv_path, original_symbol, output_base, *, inventory_path,
                       archive_hash=None, original_name=None,
                       rights_evidence_path=None, rights_evidence_sha256=None,
                       synthetic_fixture=False, row_group_size=65_536):
    """Inventory and publish each target month observed in one CSV source.

    A restart verifies existing immutable roots and skips their conversion,
    then continues with other observed periods. Missing periods remain pending.
    """
    require(type(original_symbol) is str and original_symbol in INSTRUMENTS,
            "originalSymbol", "UNMAPPED_PROVIDER_SYMBOL")
    rights_ready = synthetic_fixture
    rights_document_hash = "SYNTHETIC_FIXTURE_ONLY" if synthetic_fixture else None
    if not synthetic_fixture:
        if rights_evidence_path is not None and rights_evidence_sha256 is not None:
            rights_document_hash, _rights_value = validate_rights_evidence(
                rights_evidence_path, rights_evidence_sha256)
            rights_ready = True
    inventory = ExnessInventory(inventory_path, rights_ready=rights_ready)
    if not rights_ready:
        inventory.block_all("PROVIDER_RIGHTS_NOT_VERIFIED")
        return {"status": "BLOCKED", "reason": "PROVIDER_RIGHTS_NOT_VERIFIED",
                "partitionCount": 544, "completed": 0}

    observed = set()
    try:
        require(Path(csv_path).stat().st_size <= MAX_SOURCE_BYTES,
                "source", "ARTIFACT_LIMIT")
        source_hash = sha256_file(csv_path)
        for row in _source_rows(csv_path, original_symbol):
            period = _period_for_ns(row[2])
            year, month = map(int, period.split("-"))
            if (START_YEAR, START_MONTH) <= (year, month) <= (END_YEAR, END_MONTH):
                observed.add((year, month))
    except (ContractError, OSError, UnicodeError, csv.Error, ValueError) as exc:
        reason = getattr(exc, "code", type(exc).__name__)
        evidence = {"reason": reason, "sourceName": Path(csv_path).name}
        if "source_hash" in locals():
            evidence["sourceSha256"] = source_hash
        inventory.update_symbol(original_symbol, "FAILED", **evidence)
        return {"status": "FAILED", "reason": getattr(exc, "code", type(exc).__name__),
                "sourceSha256": locals().get("source_hash"), "completed": 0}

    output_base = Path(output_base)
    results = []
    for year, month in sorted(observed):
        partition = partition_for(original_symbol, year, month)
        source_identity = {"schemaVersion": 1, "artifact": "RIKSORA-EXNESS-PARTITION-REVISION-1",
            "sourceSha256": source_hash, "archiveSha256": archive_hash,
            "rightsDocumentSha256": rights_document_hash,
            "period": partition.period, "symbol": original_symbol}
        revision = content_hash(source_identity)[:16]
        root = (output_base / original_symbol / f"year={year:04d}" /
                f"month={month:02d}" / f"source={revision}")
        inventory.update(partition, "AVAILABLE", sourceSha256=source_hash,
                         archiveSha256=archive_hash, sourceName=original_name or Path(csv_path).name)
        try:
            result = convert_csv_partition(csv_path, partition, root, archive_hash=archive_hash,
                original_name=original_name, inventory=inventory,
                rights_evidence_path=rights_evidence_path,
                rights_evidence_sha256=rights_evidence_sha256,
                synthetic_fixture=synthetic_fixture, row_group_size=row_group_size)
        except (ContractError, OSError, csv.Error, ValueError) as exc:
            code = getattr(exc, "code", type(exc).__name__)
            status = "BLOCKED" if code in ("IMMUTABLE_ALREADY_PUBLISHED", "SOURCE_PATH_REFUSED") else "FAILED"
            inventory.update(partition, status, reason=code)
            results.append({"period": partition.period, "status": status, "reason": code})
            continue
        results.append({"period": partition.period, **result})
    require(sha256_file(csv_path) == source_hash, "source", "SOURCE_PIN_CHANGED")
    return {"status": "COMPLETE" if results and all(row["status"] == "VERIFIED" for row in results)
            else "PARTIAL", "sourceSha256": source_hash,
            "sourceName": original_name or Path(csv_path).name, "archiveSha256": archive_hash,
            "observedTargetMonths": len(observed),
            "completed": sum(row["status"] == "VERIFIED" for row in results), "partitions": results}


def process_zip_member(zip_path, member_name, original_symbol, output_base, *, inventory_path,
                       rights_evidence_path=None, rights_evidence_sha256=None,
                       synthetic_fixture=False, row_group_size=65_536):
    """Stream one named member to private temp storage and process its months."""
    if not synthetic_fixture and (rights_evidence_path is None or rights_evidence_sha256 is None):
        inventory = ExnessInventory(inventory_path, rights_ready=False)
        inventory.block_all("PROVIDER_RIGHTS_NOT_VERIFIED")
        return {"status": "BLOCKED", "reason": "PROVIDER_RIGHTS_NOT_VERIFIED",
                "partitionCount": 544, "completed": 0}
    if not synthetic_fixture:
        validate_rights_evidence(rights_evidence_path, rights_evidence_sha256)
    archive_hash = sha256_file(zip_path)
    metadata = inspect_zip(zip_path)
    require(metadata["sha256"] == archive_hash, "archive", "SOURCE_PIN_CHANGED")
    require(sum(member["name"] == member_name and member["isCsv"]
                for member in metadata["members"]) == 1,
            "archiveMember", "REFUSED_SOURCE_NOT_AVAILABLE")
    output_base = Path(output_base)
    output_base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".exness-extract-", dir=output_base) as temp:
        csv_path = Path(temp) / "selected-member.csv"
        extracted_archive_hash, member_hash, _bytes = extract_zip_member(zip_path, member_name, csv_path)
        require(extracted_archive_hash == archive_hash, "archive", "SOURCE_PIN_CHANGED")
        result = process_csv_source(csv_path, original_symbol, output_base,
            inventory_path=inventory_path, archive_hash=archive_hash,
            original_name=member_name, rights_evidence_path=rights_evidence_path,
            rights_evidence_sha256=rights_evidence_sha256,
            synthetic_fixture=synthetic_fixture, row_group_size=row_group_size)
        result["archiveMemberSha256"] = member_hash
        return result


def inspect_publication_recovery(output_root):
    """Read-only inspection of an interrupted immutable-writer reservation."""
    root = Path(output_root)
    lock = root.parent / f".{root.name}.publish.lock"
    stages = sorted(root.parent.glob(f".{root.name}.staging-*"))
    if not lock.exists():
        return {"status": "NO_STALE_LOCK", "stagingPaths": [str(path) for path in stages]}
    match = re.fullmatch(r"pid=([1-9][0-9]*)\n", lock.read_text(encoding="ascii"))
    require(match is not None, "publicationLock", "REFUSED_SOURCE")
    pid = int(match.group(1))
    try:
        os.kill(pid, 0)
        status = "ACTIVE_OR_UNKNOWN_OWNER"
    except ProcessLookupError:
        status = "STALE_LOCK_REQUIRES_EXPLICIT_RECOVERY"
    except PermissionError:
        status = "ACTIVE_OR_UNKNOWN_OWNER"
    return {"status": status, "pid": pid, "lockPath": str(lock),
            "stagingPaths": [str(path) for path in stages]}


def recover_interrupted_publication(output_root, *, confirm_stale_lock=False):
    """Remove a confirmed dead writer lock only; preserve every staging file."""
    require(confirm_stale_lock is True, "recoveryConfirmation", "REFUSED_SOURCE")
    root = Path(output_root)
    require(not root.exists(), "publication", "IMMUTABLE_ALREADY_PUBLISHED")
    state = inspect_publication_recovery(root)
    require(state["status"] == "STALE_LOCK_REQUIRES_EXPLICIT_RECOVERY",
            "publicationLock", "REFUSED_SOURCE")
    Path(state["lockPath"]).unlink()
    return {"status": "RETRY_FROM_SOURCE_START", "stagingPaths": state["stagingPaths"]}


def measure_sample(sample_zip, sample_csv, sample_parquet):
    """Return observed byte sizes; no estimation or market-data claim."""
    return {"zipBytes": Path(sample_zip).stat().st_size, "csvBytes": Path(sample_csv).stat().st_size,
            "parquetBytes": Path(sample_parquet).stat().st_size,
            "zipSha256": sha256_file(sample_zip), "csvSha256": sha256_file(sample_csv),
            "parquetSha256": sha256_file(sample_parquet)}


def estimate_capacity(sample_by_symbol, *, available_bytes, reserve_bytes, months=34):
    """Conservative arithmetic only; requires a measured sample for each symbol."""
    require(type(sample_by_symbol) is dict and set(sample_by_symbol) == set(INSTRUMENTS),
            "capacitySamples", "MISSING_REQUIRED_FIELD")
    require(type(available_bytes) is int and type(reserve_bytes) is int and
            available_bytes >= 0 and reserve_bytes >= 0 and reserve_bytes < available_bytes and
            type(months) is int and 1 <= months <= 34, "capacity", "INVALID_INPUT")
    totals = {key: 0 for key in ("zipBytes", "csvBytes", "parquetBytes")}
    for symbol, row in sample_by_symbol.items():
        require(row.get("originalSymbol") == symbol and row.get("measured") is True and
                type(row.get("sampleMonth")) is str and
                re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", row["sampleMonth"]) is not None,
                "capacitySample", "UNVERIFIED_SAMPLE")
        for key in totals:
            require(type(row.get(key)) is int and row[key] > 0, "capacitySample", "INVALID_INPUT")
            hash_key = key.replace("Bytes", "Sha256")
            require(type(row.get(hash_key)) is str and
                    re.fullmatch(r"[0-9a-f]{64}", row[hash_key]) is not None,
                    "capacitySample", "UNVERIFIED_SAMPLE")
            totals[key] += row[key] * months
    # Keep compressed original evidence, one CSV extraction, one Parquet
    # staging file, plus explicit operator reserve. This is a planning estimate,
    # not a capacity certification or download authorization.
    temporary = max(row["csvBytes"] + row["parquetBytes"] for row in sample_by_symbol.values())
    required = totals["zipBytes"] + totals["parquetBytes"] + temporary + reserve_bytes
    return {"artifact": "RIKSORA-EXNESS-CAPACITY-ESTIMATE-1", "sampleCount": len(sample_by_symbol),
        "monthsPerInstrument": months, "estimatedRetainedZipBytes": totals["zipBytes"],
        "estimatedParquetBytes": totals["parquetBytes"],
        "peakTemporaryBytes": temporary, "reserveBytes": reserve_bytes,
        "requiredBytes": required, "availableBytes": available_bytes,
        "status": "PASS_ESTIMATE_ONLY" if required <= available_bytes else "BLOCKED_INSUFFICIENT_SPACE",
        "marketDataCertification": "NOT_APPLICABLE"}
