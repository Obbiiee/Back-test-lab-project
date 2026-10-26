"""Frozen section 42.15 wire contracts; reuse BTL-CJSON-1 and exact primitives."""
from dataclasses import dataclass
from decimal import Decimal
import json
import re
import hashlib
import math
import struct
from datetime import datetime, timedelta, timezone

from contracts.canonical import canonical_bytes, content_hash, decimal_text
from contracts.primitives import require, identifier, digest, decimal

BINARY64_POLICY = "BINARY64_ROUNDTRIP_DECIMAL_UTC_MS_V1"
BINARY64_TIME = "PARQUET_TIMESTAMP_MS_UTC"


def binary64_price_text(value):
    """Explicit native-scalar projection; never admits floats on canonical wire."""
    require(type(value) is float and math.isfinite(value) and value > 0, "binary64")
    result = decimal_text(Decimal(str(value)))
    require(struct.pack('>d', float(result)) == struct.pack('>d', value),
            "binary64", "BINARY_SOURCE_PROJECTION_MISMATCH")
    return result


def utc_ms_projection(milliseconds):
    require(type(milliseconds) is int and 0 <= milliseconds <= 253402300799999,
            "timestamp_ms", "INVALID_BINARY_TIMESTAMP")
    seconds, ms = divmod(milliseconds, 1000)
    value = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds, milliseconds=ms)
    return str(milliseconds * 1000000), value.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def validate_source_policy(source, evidence_class):
    require(uint(source['resolutionNs']) > 0, "source_resolution")
    policy = source['originalScalePolicy']
    if policy == "PRESERVE_RAW_TEXT":
        return
    require(policy == BINARY64_POLICY and evidence_class == 'PROVIDER_OBSERVATION'
            and source['resolutionNs'] == '1000000' and source['timestampConvention'] == BINARY64_TIME,
            "source_resolution")


def validate_source_projection(source, row):
    """Checks typed-source projections only; raw-text behavior stays unchanged."""
    if source['originalScalePolicy'] != BINARY64_POLICY:
        return
    moment = uint(row['timeNs'])
    ns, iso = utc_ms_projection(moment // 1000000)
    require(row['timeNs'] == ns and row['resolutionNs'] == '1000000'
            and row['provenance']['originalTimestamp'] == iso,
            "timestamp_projection", "BINARY_SOURCE_PROJECTION_MISMATCH")
    for side in ('bid', 'ask'):
        value = row[side]
        require(type(value) is str, side, "BINARY_SOURCE_PROJECTION_MISMATCH")
        require(binary64_price_text(float(value)) == value, side, "BINARY_SOURCE_PROJECTION_MISMATCH")


def uint(value, field="uint", maximum=10**22):
    require(type(value) is str and re.fullmatch(r"0|[1-9][0-9]*", value) is not None,
            field, "INVALID_UNSIGNED_STRING")
    require(len(value) <= 23 and int(value) <= maximum, field)
    return int(value)


def keys(obj, fields):
    require(type(obj) is dict and set(obj) == set(fields.split()), "fields", "SCHEMA_MISMATCH")


def tag(obj, artifact, fields):
    keys(obj, "schemaVersion artifact " + fields)
    require(type(obj["schemaVersion"]) is int and obj["schemaVersion"] == 1
            and obj["artifact"] == artifact, "version", "SCHEMA_MISMATCH")
    return canonical_bytes(obj)


def text(value, field, limit=1024):
    require(type(value) is str and 0 < len(value) <= limit, field)


def nullable_hash(value):
    if value is not None:
        digest(value, "hash")


def price(value):
    if value is None:
        return None
    require(type(value) is str, "price")
    result = decimal(value, "price", positive=True)
    require(decimal_text(result) == value, "price", "NONCANONICAL_PRICE")
    return result


def event_id(provider_id, feed_id, member_hash, ordinal):
    return content_hash(dict(schemaVersion=1, artifact="BTL-TICK-ID-1",
                             providerId=provider_id, feedId=feed_id,
                             memberHash=member_hash, rawOrdinal=ordinal))


@dataclass(frozen=True)
class CanonicalTick:
    """Immutable bytes own identity; callers receive independent wire copies."""
    _bytes: bytes

    def __post_init__(self):
        require(type(self._bytes) is bytes and len(self._bytes)<=1048576,"tick_bytes")
        row=json.loads(self._bytes)
        require(canonical_bytes(row)==self._bytes,"canonical_tick")
        self._validate(row)

    @classmethod
    def from_wire(cls,row):
        if type(row) is dict:
            # Own the mutable containers before encoding and validating them.
            # All accepted leaves are immutable; unexpected types still follow
            # the original validation/constructor path rather than being coerced.
            row = row.copy()
            for field in ('provenance', 'quality'):
                if type(row.get(field)) is dict:
                    row[field] = row[field].copy()
        raw = cls._validate(row)
        if cls is not CanonicalTick or any(type(value) not in (str, type(None))
                                          for value in row['quality'].values()):
            return cls(raw)
        # _validate checks the entire original wire record and returns its
        # canonical immutable bytes. Revalidating those same bytes in
        # __post_init__ adds no check; direct byte construction still uses it.
        tick = object.__new__(cls)
        object.__setattr__(tick, '_bytes', raw)
        return tick

    @staticmethod
    def _validate(row):
        raw = tag(row, "BTL-CANONICAL-TICK-1", "datasetId datasetVersion providerId feedId instrumentId eventId timeNs resolutionNs bid ask rawOrdinal trustedSequence provenance quality")
        for field in ("datasetId", "providerId", "feedId", "instrumentId"):
            identifier(row[field], field)
        digest(row["datasetVersion"], "version")
        digest(row["eventId"], "eventId")
        moment, quantum = uint(row["timeNs"]), uint(row["resolutionNs"])
        require(quantum > 0 and moment % quantum == 0, "resolution", "INVALID_RESOLUTION")
        uint(row["rawOrdinal"])
        if row["trustedSequence"] is not None:
            uint(row["trustedSequence"])
        bid, ask = price(row["bid"]), price(row["ask"])
        p, q = row["provenance"], row["quality"]
        keys(p, "sourceId memberHash originalTimestamp")
        identifier(p["sourceId"], "sourceId")
        digest(p["memberHash"], "memberHash")
        text(p["originalTimestamp"], "timestamp", 128)
        require(row["eventId"] == event_id(row["providerId"], row["feedId"], p["memberHash"], row["rawOrdinal"]), "eventId", "IDENTITY_CONFLICT")
        keys(q, "evidenceHash quote freshness gapBefore duplicateOf")
        nullable_hash(q["evidenceHash"])
        nullable_hash(q["duplicateOf"])
        expected = "MISSING_SIDE" if bid is None or ask is None else "CROSSED" if ask < bid else "VALID"
        require(q["quote"] == expected, "quote", "QUALITY_CONFLICT")
        require(q["freshness"] in ("CONFIRMED", "STALE", "UNKNOWN"), "freshness")
        require(q["gapBefore"] in ("NONE", "KNOWN_SESSION_CLOSED", "MISSING_DATA", "UNKNOWN_SILENCE"), "gap")
        require((q["freshness"] == "UNKNOWN" and q["gapBefore"] == "UNKNOWN_SILENCE")
                or q["evidenceHash"] is not None, "evidence", "MISSING_EVIDENCE_REFERENCE")
        return raw

    @property
    def wire(self):
        return json.loads(self._bytes)

    @property
    def bid(self):
        value = self.wire["bid"]
        return None if value is None else Decimal(value)

    @property
    def ask(self):
        value = self.wire["ask"]
        return None if value is None else Decimal(value)

    @property
    def time_ns(self):
        return int(self.wire["timeNs"])


def interval_rows(rows, range_, kind):
    require(type(rows) is list and len(rows) <= 1024, "intervals")
    previous = int(range_["startNs"])
    for row in rows:
        keys(row, "startNs endNs evidenceHash " + ("status" if kind == "coverage" else "kind"))
        start, end = uint(row["startNs"]), uint(row["endNs"])
        require(previous <= start < end <= int(range_["endNs"]), "intervals", "INVALID_INTERVAL")
        previous = end
        nullable_hash(row["evidenceHash"])
        if kind == "coverage":
            require(row["status"] in ("DECLARED_COMPLETE", "INCOMPLETE", "UNKNOWN"), "coverage")
            require(row["status"] == "UNKNOWN" or row["evidenceHash"] is not None, "coverage_evidence")
        else:
            require(row["kind"] in ("KNOWN_SESSION_CLOSED", "MISSING_DATA", "UNKNOWN_SILENCE"), "gap")
            require(row["kind"] == "UNKNOWN_SILENCE" or row["evidenceHash"] is not None, "gap_evidence")


@dataclass(frozen=True)
class TickManifest:
    _bytes: bytes

    def __post_init__(self):
        require(type(self._bytes) is bytes and len(self._bytes)<=1048576,"manifest_bytes")
        row=json.loads(self._bytes)
        require(canonical_bytes(row)==self._bytes,"canonical_manifest")
        self._validate(row)

    @classmethod
    def from_wire(cls,obj,expected_version=None):
        return cls(cls._validate(obj,expected_version))

    @staticmethod
    def _validate(obj, expected_version=None):
        tag(obj, "BTL-TICK-MANIFEST-1", "datasetId providerId feedId instrumentId providerSymbol evidenceClass adapterVersion validatorVersion sources range ordering coverage gaps rights diagnostics chunks")
        for name in ("datasetId", "providerId", "feedId", "instrumentId", "providerSymbol", "adapterVersion", "validatorVersion"):
            identifier(obj[name], name)
        require(obj["evidenceClass"] in ("SYNTHETIC_CONTRACT_ONLY", "PROVIDER_OBSERVATION"), "evidenceClass")
        r = obj["range"]
        keys(r, "startNs endNs endExclusive")
        require(uint(r["startNs"]) < uint(r["endNs"]) and r["endExclusive"] is True, "range")
        sources = obj["sources"]
        require(type(sources) is list and 1 <= len(sources) <= 128, "sources")
        source_ids, member_hashes = set(), set()
        for s in sources:
            keys(s, "sourceId archiveHash memberHash originalName acquiredAtUtc sourceUrl timestampConvention resolutionNs originalScalePolicy")
            identifier(s["sourceId"], "sourceId")
            require(s["sourceId"] not in source_ids and s["memberHash"] not in member_hashes, "source", "DUPLICATE_SOURCE")
            source_ids.add(s["sourceId"]); member_hashes.add(s["memberHash"])
            digest(s["memberHash"], "memberHash"); nullable_hash(s["archiveHash"])
            for name in ("originalName", "timestampConvention"):
                text(s[name], name)
            if s["sourceUrl"] is not None:
                text(s["sourceUrl"], "sourceUrl")
            if s["acquiredAtUtc"] is not None:
                require(type(s["acquiredAtUtc"]) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", s["acquiredAtUtc"]) is not None, "acquiredAtUtc")
                text(s["acquiredAtUtc"],"acquiredAtUtc",128)
                try:
                    # Calendar validity only. Preserve original timestamp text;
                    # never use datetime's microseconds as canonical tick time.
                    datetime.fromisoformat(s["acquiredAtUtc"])
                except ValueError:
                    require(False,"acquiredAtUtc")
            validate_source_policy(s, obj['evidenceClass'])
        ordering = obj["ordering"]
        keys(ordering, "timestamps ties sequenceScope sequenceEvidenceHash")
        require(ordering["timestamps"] in ("VERIFIED_NONDECREASING", "UNKNOWN", "INVALID"), "ordering")
        require(ordering["ties"] in ("TRUSTED_SEQUENCE", "UNTRUSTED"), "ties")
        nullable_hash(ordering["sequenceEvidenceHash"])
        if ordering["sequenceScope"] is not None:
            identifier(ordering["sequenceScope"], "sequenceScope")
        require((ordering["sequenceScope"] is None) == (ordering["sequenceEvidenceHash"] is None), "sequence_evidence")
        require(ordering["ties"] != "TRUSTED_SEQUENCE" or ordering["sequenceScope"] is not None, "trusted_evidence")
        interval_rows(obj["coverage"], r, "coverage"); interval_rows(obj["gaps"], r, "gaps")
        for c in obj["coverage"]:
            for g in obj["gaps"]:
                require(c["status"] != "DECLARED_COMPLETE" or max(int(c["startNs"]), int(g["startNs"])) >= min(int(c["endNs"]), int(g["endNs"])), "coverage", "COVERAGE_CONFLICT")
        rights = obj["rights"]
        keys(rights, "class evidenceHash"); nullable_hash(rights["evidenceHash"])
        require(rights["class"] in ("SYNTHETIC", "PERSONAL_ONLY", "PUBLIC_GRANTED", "UNKNOWN"), "rights")
        require(obj["evidenceClass"] != "SYNTHETIC_CONTRACT_ONLY" or rights["class"] == "SYNTHETIC", "synthetic_rights")
        require(rights["class"] not in ("PERSONAL_ONLY", "PUBLIC_GRANTED") or rights["evidenceHash"] is not None, "rights_evidence")
        require(type(obj["diagnostics"]) is list and len(obj["diagnostics"]) <= 4096, "diagnostics")
        for d in obj["diagnostics"]:
            keys(d, "hash recordCount"); digest(d["hash"], "diagnostics")
            require(type(d["recordCount"]) is int and 0 <= d["recordCount"] <= 128, "diagnostic_count")
        chunks = obj["chunks"]
        require(type(chunks) is list and 1 <= len(chunks) <= 4096, "chunks")
        last = int(r["startNs"])
        for index, c in enumerate(chunks):
            keys(c, "chunkIndex hash eventCount firstNs lastNs")
            require(uint(c["chunkIndex"]) == index, "chunk_index")
            digest(c["hash"], "chunk_hash")
            require(type(c["eventCount"]) is int and 1 <= c["eventCount"] <= 1024, "event_count")
            first, end = uint(c["firstNs"]), uint(c["lastNs"])
            require(last <= first <= end < int(r["endNs"]), "chunk_times", "ORDER_REVERSAL")
            last = end
        require(expected_version is None or content_hash(obj) == expected_version, "version", "VERSION_MISMATCH")
        return canonical_bytes(obj)

    @property
    def wire(self):
        return json.loads(self._bytes)

    @property
    def version(self):
        return hashlib.sha256(self._bytes).hexdigest()


def chunk_content(chunk):
    return {**{key: value for key, value in chunk.items() if key != "datasetVersion"},
            "events": [{key: value for key, value in event.items() if key != "datasetVersion"}
                       for event in chunk["events"]]}


def validate_chunk(chunk, manifest):
    return _validate_chunk(chunk, manifest)


def _validate_chunk(chunk, manifest, accepted_ticks=None):
    """Internal reuse of owned immutable rows; public wire validation unchanged."""
    m = manifest.wire
    version = manifest.version
    tag(chunk, "BTL-TICK-CHUNK-1", "datasetId datasetVersion chunkIndex events")
    require(chunk["datasetId"] == m["datasetId"] and chunk["datasetVersion"] == version, "chunk_dataset", "VERSION_MISMATCH")
    index = uint(chunk["chunkIndex"])
    require(index < len(m["chunks"]), "chunk_index")
    meta = m["chunks"][index]
    require(type(chunk["events"]) is list and len(chunk["events"]) == meta["eventCount"], "chunk_count")
    require(content_hash(chunk_content(chunk)) == meta["hash"], "chunk_hash", "HASH_MISMATCH")
    if accepted_ticks is None:
        ticks = tuple(CanonicalTick.from_wire(row) for row in chunk["events"])
    else:
        ticks = tuple(accepted_ticks)
        require(len(ticks) == len(chunk['events']) and
                all(type(tick) is CanonicalTick and tick.wire == row
                    for tick, row in zip(ticks, chunk['events'])), 'acceptedChunkRows')
    require(str(ticks[0].time_ns) == meta["firstNs"] and str(ticks[-1].time_ns) == meta["lastNs"], "chunk_range")
    previous, last_source, last_ordinal = -1, -1, -1
    seen, sequences, last_sequence = {}, set(), None
    source_indices={s["sourceId"]:index for index,s in enumerate(m["sources"])}
    for tick in ticks:
        row = tick.wire
        moment = int(row["timeNs"])
        if row["eventId"] in seen:
            require(False,"event","DUPLICATE_DELIVERY" if seen[row["eventId"]]==tick._bytes else "IDENTITY_CONFLICT")
        seen[row["eventId"]]=tick._bytes
        for field in ("datasetId", "providerId", "feedId", "instrumentId"):
            require(row[field] == m[field], field, "IDENTITY_CONFLICT")
        require(row["datasetVersion"] == version, "tick_version", "VERSION_MISMATCH")
        source = next((s for s in m["sources"] if s["sourceId"] == row["provenance"]["sourceId"]), None)
        require(source is not None and source["memberHash"] == row["provenance"]["memberHash"] and source["resolutionNs"] == row["resolutionNs"], "provenance")
        validate_source_projection(source, row)
        source_index=source_indices[source["sourceId"]]
        ordinal=int(row["rawOrdinal"])
        require(source_index>=last_source and (source_index!=last_source or ordinal>last_ordinal),"ordinal","INVALID_SOURCE_ORDINAL")
        last_source,last_ordinal=source_index,ordinal
        require(previous <= moment < int(m["range"]["endNs"]) and moment >= int(m["range"]["startNs"]), "time", "ORDER_REVERSAL")
        if previous!=moment:
            sequences,last_sequence=set(),None
        previous = moment
        if m["ordering"]["ties"]=="TRUSTED_SEQUENCE":
            require(row["trustedSequence"] is not None,"sequence","INVALID_TRUSTED_SEQUENCE")
        if row["trustedSequence"] is not None:
            require(m["ordering"]["sequenceScope"] is not None, "sequence_evidence")
            sequence=int(row["trustedSequence"])
            require(sequence not in sequences and (last_sequence is None or sequence>last_sequence),"sequence","INVALID_TRUSTED_SEQUENCE")
            sequences.add(sequence);last_sequence=sequence
    return ticks
