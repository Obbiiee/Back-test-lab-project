"""Portable read-only dataset service. Storage and access are injected ports."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from contracts.canonical import canonical_bytes, decimal_text
from contracts.primitives import require, digest

MAX_RESPONSE = 1048576


@dataclass(frozen=True)
class Chunk:
    key: str
    sha256: str
    size: int
    count: int
    first: int
    last: int


@dataclass(frozen=True)
class Dataset:
    dataset_id: str
    version: str
    instrument: str
    feed: str
    chunks: tuple[Chunk, ...]
    rights_ref: str
    audience: str = "PERSONAL_LOCAL"

    def descriptor(self):
        return {"schemaVersion": 1, "datasetId": self.dataset_id, "version": self.version,
                "instrument": self.instrument, "feed": self.feed, "intervalSeconds": 60,
                "priceSide": "BID", "timezone": "UTC", "fidelity": "M1_OHLC",
                "coverageComplete": False, "sideFreshness": "UNKNOWN",
                "intrabarOutcome": "AMBIGUOUS", "volumeMeaning": "UNAVAILABLE",
                "priceEncoding": "EXACT_EXISTING_JSON_DECIMAL_TOKENS",
                "rightsRef": self.rights_ref, "audience": self.audience,
                "publicDisplayApproved": False, "deliveryMode": "LOCAL_RESEARCH",
                "count": sum(c.count for c in self.chunks),
                "first": self.chunks[0].first, "last": self.chunks[-1].last,
                "chunks": [{"sha256": c.sha256, "bytes": c.size, "count": c.count,
                            "first": c.first, "last": c.last} for c in self.chunks]}


class ArtifactStore(Protocol):
    def rows(self, chunk: Chunk) -> tuple: ...


class AccessPolicy(Protocol):
    def check(self, dataset: Dataset) -> None: ...


class PersonalLocalPolicy:
    def check(self, dataset):
        require(dataset.audience == "PERSONAL_LOCAL", "audience", "ACCESS_DENIED")


class DataService:
    def __init__(self, dataset, store: ArtifactStore, access: AccessPolicy):
        require(type(dataset) is Dataset and bool(dataset.chunks), "dataset")
        digest(dataset.version, "version")
        self.dataset, self.store, self.access = dataset, store, access

    def descriptor(self):
        self.access.check(self.dataset)
        return self.dataset.descriptor()

    def read(self, version, start, end, limit=1000, after=None, revealed_before=None):
        self.access.check(self.dataset)  # Every request, never cached permission.
        require(version == self.dataset.version, "version", "VERSION_MISMATCH")
        require(all(type(v) is int and 0 <= v <= 2**53-1 for v in (start, end)), "range")
        require(start < end and end-start <= 32*86400, "range")
        require(type(limit) is int and 1 <= limit <= 10000, "limit")
        require(after is None or (type(after) is int and start <= after < end), "after")
        require(revealed_before is None or (type(revealed_before) is int and 0 <= revealed_before <= 2**53-1), "revealed")
        # Exclusive bound: a full M1 candle is available only once its minute ends.
        # This caller filter is NOT a server-authoritative trading Session cursor.
        upper = min(end, revealed_before) if revealed_before is not None else end
        # Existing BTL-CJSON node budget also bounds page size. Continuation is
        # explicit; a larger requested limit never implies silent truncation.
        page_size = min(limit, 2000)
        selected = []
        more = False
        for chunk in self.dataset.chunks:
            if chunk.last < start or chunk.first >= upper or (after is not None and chunk.last <= after):
                continue
            for row in self.store.rows(chunk):
                time = row[0]
                if time < start or time >= end or (after is not None and time <= after):
                    continue
                if revealed_before is not None and time+60 > revealed_before:
                    continue
                if len(selected) == page_size:
                    more = True
                    break
                selected.append([time, *(decimal_text(Decimal(v)) for v in row[1:])])
            if more:
                break
        result = {"schemaVersion": 1, "datasetId": self.dataset.dataset_id,
                  "version": version, "mode": "LOCAL_RESEARCH", "priceSide": "BID",
                  "intervalSeconds": 60, "rows": selected, "more": more,
                  "nextAfter": selected[-1][0] if more else None,
                  "executionStatus": "NOT_SIMULATED", "fillPrice": None, "pnl": None,
                  "coverageComplete": False, "intrabarOutcome": "AMBIGUOUS"}
        require(len(canonical_bytes(result)) <= MAX_RESPONSE, "response", "RESPONSE_TOO_LARGE")
        return result
