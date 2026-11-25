"""Monthly tick source backed by plain Compact Tick files (additive, opt-in, default OFF).

Why this exists: the data format owners chose for tick storage is the plain Compact Parquet (`BTL-COMPACT-TICK-1`:
ts_ns, bid, ask, ordinal, is_crossed, group_id). This class lets the UNCHANGED canonical timeline, reducer, checkpoint and
receipt contracts read that storage directly, with no second copy of the dataset.

Authority is unchanged. The canonical Monthly manifest (`manifest.json`, pinned by hash) still carries the canonical
source manifest and, per row group, `canonicalEventHash`. This class only changes WHERE rows come from: canonical events are
rebuilt per row group from the Compact rows by a named deterministic reconstruction rule and are verified against
`canonicalEventHash` BEFORE use. A wrong rule, a wrong admission hint, a modified Compact file or a wrong pin fails closed
(`CHILD_HASH_MISMATCH` / `SOURCE_PIN_CHANGED`). The admission record is therefore a hint, never an authority.

Everything else (page tokens, equal-timestamp groups, ordering, month checks, revealed windows, caches) is inherited from
`MonthlyParquetProvider` without modification.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

import numpy as np

from contracts.canonical import canonical_bytes, content_hash, decimal_text
from contracts.primitives import digest, require
from market_data import monthly_parquet as _mp
from market_data.compact_tick import CompactTickReader
from market_data.monthly_parquet import MonthlyParquetProvider
from ticks.contracts import event_id

ADMISSION_ARTIFACT = "BTL-COMPACT-MONTHLY-ADMISSION-1"
RULE_SYNTHETIC_FINANCIAL_V1 = "synthetic-financial-v1"
RULES = (RULE_SYNTHETIC_FINANCIAL_V1,)          # real-source rules are added only with their own admission evidence


def validate_admission(admission):
    require(type(admission) is dict and set(admission) == {"schemaVersion", "artifact", "rule", "qualityEvidenceHash"} and
            admission["schemaVersion"] == 1 and admission["artifact"] == ADMISSION_ARTIFACT and
            admission["rule"] in RULES, "admission", "REFUSED_SOURCE")
    digest(admission["qualityEvidenceHash"], "qualityEvidenceHash")
    return dict(admission)


def admission_record(quality_evidence_hash, rule=RULE_SYNTHETIC_FINANCIAL_V1):
    return validate_admission(dict(schemaVersion=1, artifact=ADMISSION_ARTIFACT, rule=rule,
                                   qualityEvidenceHash=quality_evidence_hash))


def adopt_monthly_manifest(reference_manifest, compact_manifest):
    """Same canonical authority, storage entries re-pointed at the Compact files; returns a new pinned manifest dict.

    Only `files[].sha256/bytes` (storage identity) change. Every canonical field (source manifest, row-group canonical
    event hashes, dataset identity) is copied unchanged, so a Session pinned to the dataset keeps its dataset version.
    """
    manifest = {key: value for key, value in reference_manifest.items() if key != "manifestHash"}
    by_month = {entry["month"]: entry for entry in compact_manifest["files"]}
    require(set(by_month) == {entry["month"] for entry in manifest["files"]} and
            compact_manifest["eventCount"] == manifest["eventCount"], "compactFiles", "COUNT_CONFLICT")
    files = []
    for entry in manifest["files"]:
        child = by_month[entry["month"]]
        require(child["eventCount"] == entry["eventCount"] and child["firstTimeNs"] == entry["firstTimeNs"] and
                child["lastTimeNs"] == entry["lastTimeNs"], "compactFiles", "COUNT_CONFLICT")
        files.append(dict(entry, sha256=child["sha256"], bytes=child["bytes"]))
    manifest["files"] = files
    manifest["manifestHash"] = content_hash(manifest)
    return manifest


def write_adopted_manifest(root, reference_manifest, compact_manifest):
    from pathlib import Path
    manifest = adopt_monthly_manifest(reference_manifest, compact_manifest)
    target = Path(root).resolve() / "manifest.json"
    require(not target.exists(), "manifest", "IMMUTABLE_ALREADY_PUBLISHED")
    target.write_bytes(canonical_bytes(manifest))
    return manifest


class _FileShim:
    """What `iter_range` asks of an opened Parquet file; the rows are served from Compact by `_read_row_group_file`."""

    def __init__(self, entry):
        class _Meta:
            num_rows = entry["eventCount"]
            num_row_groups = len(entry["rowGroups"])
        self.schema_arrow = _mp.SCHEMA
        self.metadata = _Meta()

    def close(self):
        return None


class CompactBackedMonthlyProvider(MonthlyParquetProvider):
    def __init__(self, root, *, admission, expected_manifest_hash, expected_compact_manifest_hash,
                 expected_dataset_id=None, expected_dataset_version=None, reader_factory=CompactTickReader):
        super().__init__(root, expected_dataset_id=expected_dataset_id, expected_dataset_version=expected_dataset_version,
                         expected_manifest_hash=expected_manifest_hash)
        self._admission = validate_admission(admission)
        self._compact = reader_factory(self.root, expected_manifest_hash=expected_compact_manifest_hash)
        parent = self._compact.parent
        require((parent["datasetId"], parent["datasetVersion"]) == (self.dataset_id, self.dataset_version),
                "compactParent", "IDENTITY_CONFLICT")
        require(len(self.manifest["sourceIdentity"]) == 1, "sourceIdentity", "REFUSED_SOURCE")      # one source: ordinal == global index
        by_month = {entry["month"]: entry for entry in self._compact.manifest["files"]}
        require(set(by_month) == {entry["month"] for entry in self._files} and
                self._compact.manifest["eventCount"] == self.manifest["eventCount"], "compactFiles", "COUNT_CONFLICT")
        for entry in self._files:
            child = by_month[entry["month"]]
            require(child["sha256"] == entry["sha256"] and child["bytes"] == entry["bytes"] and
                    child["eventCount"] == entry["eventCount"], "compactFiles", "CHILD_HASH_MISMATCH")
        self._divisor = Decimal(10) ** int(self._compact.manifest["priceScale"])

    # --- storage identity -------------------------------------------------------------------------------------------
    def verify_file_hash(self, month):
        require(self._file_for_month(month) is not None, "month", "REFUSED_SOURCE_NOT_AVAILABLE")
        self._compact.verify_file(month)             # size + SHA-256 + Parquet footer of the Compact file
        return True

    def _open_parquet(self, relative):
        entry = next((e for e in self._files if e["path"] == relative), None)
        require(entry is not None, "file", "MISSING_CHILD")
        return _FileShim(entry)

    # --- row source ---------------------------------------------------------------------------------------------------
    def _text(self, value):
        return decimal_text(Decimal(int(value)) / self._divisor)

    def _event(self, ts, bid, ask, ordinal):
        source = self.manifest["sourceIdentity"][0]
        time_ns, raw_ordinal = str(int(ts)), str(int(ordinal))
        return dict(
            schemaVersion=1, artifact="BTL-CANONICAL-TICK-1", datasetId=self.dataset_id, datasetVersion=self.dataset_version,
            providerId=self.manifest["providerId"], feedId=self.manifest["feedId"], instrumentId=self.manifest["instrumentId"],
            eventId=event_id(self.manifest["providerId"], self.manifest["feedId"], source["memberHash"], raw_ordinal),
            timeNs=time_ns, resolutionNs=source["resolutionNs"], bid=self._text(bid), ask=self._text(ask),
            rawOrdinal=raw_ordinal, trustedSequence=None,
            provenance=dict(sourceId=source["sourceId"], memberHash=source["memberHash"], originalTimestamp="SYNTHETIC_NS:" + time_ns),
            quality=dict(evidenceHash=self._admission["qualityEvidenceHash"], quote="VALID", freshness="CONFIRMED",
                         gapBefore="NONE", duplicateOf=None))

    def _read_row_group_file(self, parquet, file_entry, group_entry):
        first_ordinal, last_ordinal = int(group_entry["firstOrdinal"]), int(group_entry["lastOrdinal"])
        window = self._compact.read_range(int(group_entry["firstTimeNs"]), int(group_entry["lastTimeNs"]) + 1)
        keep = (window["ordinal"] >= first_ordinal) & (window["ordinal"] <= last_ordinal)
        ts, bid, ask, ordinal = (window[name][keep] for name in ("ts_ns", "bid", "ask", "ordinal"))
        count = group_entry["eventCount"]
        require(len(ts) == count, "rowGroupCount", "CORRUPT_RECORD")
        first_global = group_entry["firstGlobalIndex"]
        require(int(ordinal[0]) == first_global and bool(np.all(np.diff(ordinal) == 1)),
                "ordinal", "INVALID_SOURCE_ORDINAL")                      # one source, contiguous: ordinal == global index
        sha = hashlib.sha256()
        events = []
        last_time = last_ordinal_seen = -1
        for i in range(count):
            event = self._event(ts[i], bid[i], ask[i], ordinal[i])
            time_ns, ordn = int(event["timeNs"]), int(event["rawOrdinal"])
            require(time_ns >= last_time and ordn > last_ordinal_seen, "eventOrder", "ORDER_REVERSAL")
            require(_mp._month(time_ns) == file_entry["month"], "month", "RANGE_CONFLICT")
            last_time, last_ordinal_seen = time_ns, ordn
            sha.update(canonical_bytes(event))
            sha.update(b"\n")
            events.append(event)
        require(sha.hexdigest() == group_entry["canonicalEventHash"], "canonicalEventHash", "CHILD_HASH_MISMATCH")
        require(events[0]["timeNs"] == group_entry["firstTimeNs"] and events[-1]["timeNs"] == group_entry["lastTimeNs"] and
                events[0]["rawOrdinal"] == group_entry["firstOrdinal"] and events[-1]["rawOrdinal"] == group_entry["lastOrdinal"],
                "rowGroupBounds", "CORRUPT_INDEX_POINTER")
        timestamps = np.asarray(ts, dtype=np.int64)
        require(bool(np.all(timestamps[1:] >= timestamps[:-1])), "timestampIndex", "ORDER_REVERSAL")
        indices = np.arange(first_global, first_global + count, dtype=np.int64)
        require(int(indices[-1]) == group_entry["lastGlobalIndex"], "globalIndex", "CORRUPT_INDEX_POINTER")
        return events, timestamps, indices
