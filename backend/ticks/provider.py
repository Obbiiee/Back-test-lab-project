"""Offline provider port and SYNTHETIC / TEST ONLY implementation."""
from dataclasses import dataclass
import json
from typing import Protocol
from copy import deepcopy

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require
from .contracts import (CanonicalTick, TickManifest, event_id, chunk_content,
                        validate_chunk, uint, keys, tag)


class TickDataProvider(Protocol):
    def describe(self, dataset_id: str, dataset_version: str) -> dict: ...
    def read_page(self, dataset_id: str, dataset_version: str,
                  after_token: dict | None, max_events: int) -> dict: ...


@dataclass
class Cancellation:
    cancelled: bool = False

    def check(self):
        require(type(self.cancelled) is bool,"cancel")
        require(not self.cancelled, "cancel", "CANCELLED")


def diagnostic_counts(records):
    counts = {}
    for record in records:
        counts[record["code"]] = counts.get(record["code"], 0) + 1
    return counts


def empty_diagnostics():
    return {"records": [], "counts": {}, "truncated": False}


class SyntheticTickProvider:
    """Immutable stored canonical chunks. No CSV, HTTP, execution or accounts.

    Authored rows only; source labels/hashes are synthetic, never Exness evidence.
    describe/read_page are the same boundary consumed for any future provider.
    """
    label = "SYNTHETIC / TEST ONLY"

    def __init__(self, rows, *, dataset_id="synthetic:test", resolution_ns="1",
                 chunk_size=64, trusted=False, gaps=None, coverage=None,
                 diagnostics=None):
        require(type(rows) in (list, tuple) and bool(rows), "rows", "EMPTY_DATASET")
        require(type(chunk_size) is int and 1 <= chunk_size <= 1024, "chunk_size")
        require(type(trusted) is bool,"trusted")
        require(diagnostics is None or (type(diagnostics) in (list,tuple) and len(diagnostics)<=128),"synthetic_diagnostics","DIAGNOSTIC_LIMIT")
        # Authored record hash owns original text/scale; it is not market evidence.
        member_hash = content_hash({"schemaVersion": 1, "artifact": "BTL-SYNTHETIC-RAW-1", "rows": list(rows), "diagnostics": diagnostics or []})
        proof = content_hash({"schemaVersion": 1, "artifact": "BTL-SYNTHETIC-SEMANTICS-1", "label": self.label})
        events = []
        for row in rows:
            keys(row, "ordinal timeNs bid ask sequence")
            quote = "MISSING_SIDE" if row["bid"] is None or row["ask"] is None else "VALID"
            from .contracts import price
            bid, ask = price(row["bid"]), price(row["ask"])
            if bid is not None and ask is not None and ask < bid:
                quote = "CROSSED"
            event = dict(schemaVersion=1, artifact="BTL-CANONICAL-TICK-1",
                         datasetId=dataset_id, datasetVersion="0"*64,
                         providerId="SYNTHETIC", feedId="TEST_ONLY", instrumentId="SYNTHETIC_INSTRUMENT",
                         eventId=event_id("SYNTHETIC", "TEST_ONLY", member_hash, row["ordinal"]),
                         timeNs=row["timeNs"], resolutionNs=resolution_ns,
                         bid=row["bid"], ask=row["ask"], rawOrdinal=row["ordinal"],
                         trustedSequence=row["sequence"],
                         provenance=dict(sourceId="synthetic:source", memberHash=member_hash,
                                         originalTimestamp="SYNTHETIC_NS:" + row["timeNs"]),
                         quality=dict(evidenceHash=None, quote=quote, freshness="UNKNOWN",
                                      gapBefore="UNKNOWN_SILENCE", duplicateOf=None))
            events.append(CanonicalTick.from_wire(event).wire)
        chunks = []
        for offset in range(0, len(events), chunk_size):
            chunks.append(dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1", datasetId=dataset_id,
                               datasetVersion="0"*64, chunkIndex=str(len(chunks)), events=events[offset:offset+chunk_size]))
        records = [] if diagnostics is None else list(deepcopy(diagnostics))
        for record in records:
            keys(record,"sourceId memberHash rawOrdinal timeNs code rawRecordHash")
            record.update(sourceId="synthetic:source",memberHash=member_hash)
        diagnostic_blocks = [dict(schemaVersion=1, artifact="BTL-TICK-DIAGNOSTICS-1",
                                  datasetId=dataset_id, records=records[offset:offset+128],
                                  counts=diagnostic_counts(records[offset:offset+128]), truncated=False)
                             for offset in range(0, len(records), 128)]
        manifest = dict(schemaVersion=1, artifact="BTL-TICK-MANIFEST-1", datasetId=dataset_id,
                        providerId="SYNTHETIC", feedId="TEST_ONLY", instrumentId="SYNTHETIC_INSTRUMENT",
                        providerSymbol="SYNTHETIC_TEST_ONLY", evidenceClass="SYNTHETIC_CONTRACT_ONLY",
                        adapterVersion="SYNTHETIC-1", validatorVersion="BTL-TICK-VALIDATOR-1",
                        sources=[dict(sourceId="synthetic:source", archiveHash=None, memberHash=member_hash,
                                      originalName="SYNTHETIC_TEST_ONLY", acquiredAtUtc=None, sourceUrl=None,
                                      timestampConvention="SYNTHETIC Unix UTC ns; no market evidence",
                                      resolutionNs=resolution_ns, originalScalePolicy="PRESERVE_RAW_TEXT")],
                        range=dict(startNs=events[0]["timeNs"], endNs=str(int(events[-1]["timeNs"])+1), endExclusive=True),
                        ordering=dict(timestamps="VERIFIED_NONDECREASING",
                                      ties="TRUSTED_SEQUENCE" if trusted else "UNTRUSTED",
                                      sequenceScope="synthetic:sequence" if any(e["trustedSequence"] is not None for e in events) else None,
                                      sequenceEvidenceHash=proof if any(e["trustedSequence"] is not None for e in events) else None),
                        coverage=[] if coverage is None else coverage, gaps=[] if gaps is None else gaps,
                        rights=dict(class_="SYNTHETIC"), diagnostics=[dict(hash=content_hash(b), recordCount=len(b["records"])) for b in diagnostic_blocks],
                        chunks=[dict(chunkIndex=c["chunkIndex"], hash=content_hash(chunk_content(c)),
                                     eventCount=len(c["events"]), firstNs=c["events"][0]["timeNs"], lastNs=c["events"][-1]["timeNs"]) for c in chunks])
        manifest["rights"] = {"class": "SYNTHETIC", "evidenceHash": None}
        self.__manifest = TickManifest.from_wire(manifest)
        self.__chunks = []
        for c in chunks:
            c["datasetVersion"] = self.dataset_version
            for e in c["events"]:
                e["datasetVersion"] = self.dataset_version
            validate_chunk(c, self.__manifest)
            self.__chunks.append(canonical_bytes(c))
        # Per-source ordinal index belongs to adapter; timeline never accesses it.
        self.__events = tuple(canonical_bytes(e) for e in events)
        self.__ordinal_positions={}
        for index,event in enumerate(events):
            self.__ordinal_positions.setdefault(event["rawOrdinal"],[]).append(index)
        self.__diagnostics = canonical_bytes(dict(schemaVersion=1, artifact="BTL-SYNTHETIC-DIAGNOSTICS-1", records=records))

    @property
    def dataset_id(self):
        return self.__manifest.wire["datasetId"]

    @property
    def dataset_version(self):
        return self.__manifest.version

    def describe(self, dataset_id, dataset_version):
        require(dataset_id == self.dataset_id and dataset_version == self.dataset_version,
                "dataset", "VERSION_MISMATCH")
        return self.__manifest.wire

    def read_page(self, dataset_id, dataset_version, after_token=None, max_events=1024):
        self.describe(dataset_id, dataset_version)
        require(type(max_events) is int and 1 <= max_events <= 1024, "max_events")
        position = 0
        if after_token is not None:
            tag(after_token, "BTL-TICK-PAGE-TOKEN-1", "datasetVersion sourceIndex afterRawOrdinal")
            require(after_token["datasetVersion"] == dataset_version and after_token["sourceIndex"] == "0", "token", "VERSION_MISMATCH")
            if after_token["afterRawOrdinal"] is not None:
                uint(after_token["afterRawOrdinal"])
                found = self.__ordinal_positions.get(after_token["afterRawOrdinal"],[])
                require(len(found) == 1, "token", "INVALID_PAGE_TOKEN")
                position = found[0]+1
        result = dict(schemaVersion=1, artifact="BTL-TICK-PAGE-1", datasetId=dataset_id,
                      datasetVersion=dataset_version, events=[], diagnostics=empty_diagnostics(),
                      nextToken=None, endOfDataset=False)
        while position < len(self.__events) and len(result["events"]) < max_events:
            event = json.loads(self.__events[position])
            result["events"].append(event)
            result["nextToken"] = dict(schemaVersion=1, artifact="BTL-TICK-PAGE-TOKEN-1",
                                       datasetVersion=dataset_version, sourceIndex="0", afterRawOrdinal=event["rawOrdinal"])
            try:
                canonical_bytes(result)
            except ValueError:
                result["events"].pop()
                require(bool(result["events"]), "page", "RECORD_LIMIT")
                result["nextToken"]["afterRawOrdinal"] = result["events"][-1]["rawOrdinal"]
                break
            position += 1
        result["endOfDataset"] = position == len(self.__events)
        if result["endOfDataset"]:
            result["nextToken"] = None
        # Diagnostic blocks supplied on bounded first page; test provider refuses
        # unsupported large diagnostic payload rather than truncate silently.
        if after_token is None or after_token["afterRawOrdinal"] is None:
            records = json.loads(self.__diagnostics)["records"]
            require(len(records) <= 128, "synthetic_diagnostics", "DIAGNOSTIC_LIMIT")
            result["diagnostics"] = dict(records=records, counts=diagnostic_counts(records), truncated=False)
        canonical_bytes(result)
        return result


def validate_provider(provider, dataset_id, dataset_version, cancellation=None, diagnostic_sink=None):
    """Offline ingestion acceptance, bounded one chunk and one tie group at once."""
    cancel = cancellation or Cancellation()
    manifest = TickManifest.from_wire(provider.describe(dataset_id, dataset_version), dataset_version)
    m = manifest.wire
    require(m["datasetId"] == dataset_id and m["ordering"]["timestamps"] == "VERIFIED_NONDECREASING", "ordering", "UNVERIFIED_ORDER")
    token, chunk_index, buffer, previous, last_source, last_ordinal = None, 0, [], -1, -1, -1
    tie_time, tie_sequence, tie_count = None, None, 0
    seen_ids, tie_sequences, tie_rows, tie_bytes = {}, set(), [], 0
    diagnostic_records, diagnostic_block_index = [], 0
    sources = {s["sourceId"]: i for i, s in enumerate(m["sources"])}
    while True:
        cancel.check()
        page = provider.read_page(dataset_id, dataset_version, token, 64)
        tag(page, "BTL-TICK-PAGE-1", "datasetId datasetVersion events diagnostics nextToken endOfDataset")
        require(page["datasetId"] == dataset_id and page["datasetVersion"] == dataset_version, "page_dataset", "VERSION_MISMATCH")
        require(type(page["events"]) is list and len(page["events"]) <= 64 and type(page["endOfDataset"]) is bool, "page")
        keys(page["diagnostics"], "records counts truncated")
        require(type(page["diagnostics"]["records"]) is list and type(page["diagnostics"]["counts"]) is dict and all(type(count) is int and 0<=count<=2**53-1 for count in page["diagnostics"]["counts"].values()),"diagnostic_shape")
        require(page["diagnostics"]["truncated"] is False and len(page["diagnostics"]["records"]) <= 128, "diagnostics", "INCOMPLETE_DIAGNOSTICS")
        require(page["diagnostics"]["counts"] == diagnostic_counts(page["diagnostics"]["records"]), "diagnostic_counts")
        for record in page["diagnostics"]["records"]:
            keys(record, "sourceId memberHash rawOrdinal timeNs code rawRecordHash")
            require(record["timeNs"] is not None, "diagnostic_time", "UNLOCATED_INVALID_RECORD")
            from contracts.primitives import digest
            digest(record["rawRecordHash"], "record_hash")
            uint(record["timeNs"]);uint(record["rawOrdinal"])
            require(int(m["range"]["startNs"])<=int(record["timeNs"])<int(m["range"]["endNs"]),"diagnostic_range")
            source_record = next((s for s in m["sources"] if s["sourceId"]==record["sourceId"]),None)
            require(source_record is not None and source_record["memberHash"]==record["memberHash"], "diagnostic_source")
            require(record["code"] in ("MALFORMED_PRICE","INVALID_TIMESTAMP","UNSUPPORTED_RESOLUTION","MISSING_SIDE","CROSSED_QUOTE","ORDER_REVERSAL","SUSPECT_REPEAT"), "diagnostic_code")
            if record["code"] in ("MALFORMED_PRICE","INVALID_TIMESTAMP","UNSUPPORTED_RESOLUTION"):
                require(any(g["kind"]=="MISSING_DATA" and int(g["startNs"])<=int(record["timeNs"])<int(g["endNs"]) for g in m["gaps"]), "diagnostic_gap", "UNBOUNDED_INVALID_RECORD")
            require(diagnostic_block_index < len(m["diagnostics"]), "diagnostics", "EXTRA_DIAGNOSTIC")
            diagnostic_records.append(record)
            descriptor=m["diagnostics"][diagnostic_block_index]
            if len(diagnostic_records)==descriptor["recordCount"]:
                block=dict(schemaVersion=1,artifact="BTL-TICK-DIAGNOSTICS-1",datasetId=dataset_id,
                           records=diagnostic_records,counts=diagnostic_counts(diagnostic_records),truncated=False)
                require(content_hash(block)==descriptor["hash"],"diagnostics","HASH_MISMATCH")
                if diagnostic_sink is not None:
                    for accepted in diagnostic_records:diagnostic_sink(accepted)
                diagnostic_records=[];diagnostic_block_index+=1
        for raw in page["events"]:
            cancel.check()
            tick = CanonicalTick.from_wire(raw)
            row = tick.wire
            source = sources.get(row["provenance"]["sourceId"], -1)
            ordinal = int(row["rawOrdinal"])
            if row["eventId"] in seen_ids:
                require(False, "event", "DUPLICATE_DELIVERY" if content_hash(row) == seen_ids[row["eventId"]] else "IDENTITY_CONFLICT")
            seen_ids[row["eventId"]] = content_hash(row)
            require(source >= last_source and (source != last_source or ordinal > last_ordinal), "ordinal", "INVALID_SOURCE_ORDINAL")
            require(tick.time_ns >= previous, "time", "ORDER_REVERSAL")
            if tick.time_ns != tie_time:
                if tie_rows:
                    try:
                        canonical_bytes(dict(schemaVersion=1, artifact="BTL-TICK-GROUP-CHECK-1", events=tie_rows))
                    except ValueError:
                        require(False, "tie", "GROUP_LIMIT")
                tie_time, tie_sequence, tie_count = tick.time_ns, None, 0
                tie_sequences, tie_rows, tie_bytes = set(), [], 0
            tie_count += 1
            require(tie_count <= 1024, "tie", "GROUP_LIMIT")
            sequence = row["trustedSequence"]
            if m["ordering"]["ties"] == "TRUSTED_SEQUENCE":
                require(sequence is not None, "sequence", "INVALID_TRUSTED_SEQUENCE")
            if sequence is not None:
                require(sequence not in tie_sequences and (tie_sequence is None or int(sequence) > tie_sequence), "sequence", "INVALID_TRUSTED_SEQUENCE")
                tie_sequences.add(sequence)
                tie_sequence = int(sequence)
            tie_rows.append(row)
            tie_bytes += len(tick._bytes)
            require(tie_bytes <= 1048576, "tie", "GROUP_LIMIT")
            duplicate = row["quality"]["duplicateOf"]
            require(duplicate is None or (duplicate in seen_ids and duplicate != row["eventId"]), "duplicate_reference", "UNVERIFIED_DUPLICATE_REFERENCE")
            last_source, last_ordinal, previous = source, ordinal, tick.time_ns
            buffer.append(row)
            require(chunk_index < len(m["chunks"]), "chunks", "EXTRA_EVENT")
            if len(buffer) == m["chunks"][chunk_index]["eventCount"]:
                validate_chunk(dict(schemaVersion=1, artifact="BTL-TICK-CHUNK-1", datasetId=dataset_id,
                                    datasetVersion=dataset_version, chunkIndex=str(chunk_index), events=buffer), manifest)
                chunk_index += 1; buffer = []
        require(page["events"] or page["diagnostics"]["records"] or page["endOfDataset"], "page", "NO_PROGRESS")
        if page["endOfDataset"]:
            require(page["nextToken"] is None, "eof_token")
            break
        require(page["nextToken"] is not None and page["nextToken"] != token, "token", "NO_PROGRESS")
        tag(page["nextToken"], "BTL-TICK-PAGE-TOKEN-1", "datasetVersion sourceIndex afterRawOrdinal")
        require(page["nextToken"]["datasetVersion"] == dataset_version, "token_version")
        source_position=uint(page["nextToken"]["sourceIndex"])
        require(source_position<len(m["sources"]),"token_source")
        ordinal_position=-1 if page["nextToken"]["afterRawOrdinal"] is None else uint(page["nextToken"]["afterRawOrdinal"])
        before=(-1,-1) if token is None else (int(token["sourceIndex"]),-1 if token["afterRawOrdinal"] is None else int(token["afterRawOrdinal"]))
        require((source_position,ordinal_position)>before,"token","NO_PROGRESS")
        token = page["nextToken"]
    require(not buffer and chunk_index == len(m["chunks"]), "chunks", "TRUNCATED_DATASET")
    if tie_rows:
        try:
            canonical_bytes(dict(schemaVersion=1, artifact="BTL-TICK-GROUP-CHECK-1", events=tie_rows))
        except ValueError:
            require(False, "tie", "GROUP_LIMIT")
    require(not diagnostic_records and diagnostic_block_index==len(m["diagnostics"]), "diagnostics", "TRUNCATED_DIAGNOSTICS")
    return manifest
