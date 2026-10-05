"""Bounded BTL-TICK-EVIDENCE-1, encoded with existing BTL-CJSON-1.

Nanoseconds are decimal strings on the wire (not JS-unsafe JSON integers).
Coverage and source ordering are caller evidence assertions, not certifications.
Only the revealed prefix participates. No interpolation or financial mutation.
"""
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby
import hashlib
import json

from contracts.canonical import canonical_bytes, content_hash, decimal_text
from contracts.primitives import decimal, digest, identifier, require


def ns(value):
    require(type(value) is int and 0 <= value <= 10**22, "nanoseconds")
    return value


@dataclass(frozen=True)
class Quote:
    event_id: str
    time_ns: int
    bid: Decimal | None
    ask: Decimal | None
    source_sequence: int | None = None
    fresh: bool = True
    gap_before: bool = False

    def __post_init__(self):
        identifier(self.event_id, "event_id")
        ns(self.time_ns)
        for side in ("bid", "ask"):
            value = getattr(self, side)
            if value is not None:
                object.__setattr__(self, side, decimal(value, side, positive=True))
        require(self.source_sequence is None or
                (type(self.source_sequence) is int and 0 <= self.source_sequence <= 2**53-1), "sequence")
        require(type(self.fresh) is bool and type(self.gap_before) is bool, "quality_flags")


@dataclass(frozen=True)
class Request:
    dataset_id: str
    dataset_version: str
    dataset_hash: str
    instrument_id: str
    feed_id: str
    profile_version: str
    side: str
    activation_ns: int
    horizon_ns: int
    sl: Decimal
    tp: Decimal
    coverage_start_ns: int
    coverage_end_ns: int
    coverage_complete: bool
    trusted_sequence: bool = False

    def __post_init__(self):
        for field in ("dataset_id", "dataset_version", "instrument_id", "feed_id", "profile_version"):
            identifier(getattr(self, field), field)
        digest(self.dataset_hash, "dataset_hash")
        require(type(self.side) is str and self.side in ("LONG", "SHORT"), "side")
        for field in ("activation_ns", "horizon_ns", "coverage_start_ns", "coverage_end_ns"):
            ns(getattr(self, field))
        require(self.activation_ns <= self.horizon_ns, "horizon")
        require(self.coverage_start_ns <= self.coverage_end_ns, "coverage")
        require(type(self.coverage_complete) is bool and type(self.trusted_sequence) is bool, "evidence_flags")
        object.__setattr__(self, "sl", decimal(self.sl, "sl", positive=True))
        object.__setattr__(self, "tp", decimal(self.tp, "tp", positive=True))
        require(self.sl < self.tp if self.side == "LONG" else self.tp < self.sl, "levels")


@dataclass(frozen=True)
class Decision:
    classification: str
    reason: str
    event_id: str | None
    observed_price: str | None
    evidence_hash: str
    evaluator_version: str = "BTL-TICK-EVIDENCE-1"


def _prepare(request, quotes):
    require(type(request) is Request and type(quotes) is tuple, "immutable_input")
    # Ignore hidden suffix before hashing/validation; callers still own acquisition.
    visible = []
    for quote in quotes:
        require(type(quote) is Quote, "quote")
        if quote.time_ns > request.horizon_ns:
            break
        visible.append(quote)
        require(len(visible) <= 1024, "chunk_limit")
    payload = {"schemaVersion": 1, "artifact": "BTL-TICK-EVIDENCE-1",
               "datasetId": request.dataset_id, "datasetVersion": request.dataset_version,
               "datasetHash": request.dataset_hash, "profileVersion": request.profile_version,
               "instrumentId": request.instrument_id, "feedId": request.feed_id,
               "side": request.side, "activationNs": str(request.activation_ns),
               "horizonNs": str(request.horizon_ns), "sl": request.sl, "tp": request.tp,
               "coverageStartNs": str(request.coverage_start_ns),
               "coverageEndNs": str(request.coverage_end_ns),
               "coverageComplete": request.coverage_complete, "trustedSequence": request.trusted_sequence,
               "quotes": [{"id": q.event_id, "timeNs": str(q.time_ns), "bid": q.bid, "ask": q.ask,
                           "sequence": q.source_sequence, "fresh": q.fresh, "gapBefore": q.gap_before}
                          for q in visible]}
    return visible, payload


def evidence_bytes(request, quotes):
    """Serializable exact evidence artifact; source authenticity is not certified."""
    return canonical_bytes(_prepare(request, quotes)[1])


def load_evidence(raw, expected_hash):
    """Hash-checked strict canonical round trip; never accesses a file or network."""
    digest(expected_hash, "evidence_hash")
    require(type(raw) is bytes and len(raw) <= 1048576, "artifact_bytes")
    require(hashlib.sha256(raw).hexdigest() == expected_hash, "artifact_hash")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        require(False, "artifact_json")
    require(type(data) is dict and canonical_bytes(data) == raw, "canonical_artifact")
    require(data.get("artifact") == "BTL-TICK-EVIDENCE-1", "artifact_version")

    def time(field):
        value = data[field]
        require(type(value) is str and len(value) <= 23 and value.isascii() and value.isdigit(), field)
        parsed = ns(int(value))
        require(str(parsed) == value, field)
        return parsed

    try:
        request = Request(data["datasetId"], data["datasetVersion"], data["datasetHash"],
                          data["instrumentId"], data["feedId"], data["profileVersion"], data["side"],
                          time("activationNs"), time("horizonNs"), data["sl"], data["tp"],
                          time("coverageStartNs"), time("coverageEndNs"),
                          data["coverageComplete"], data["trustedSequence"])
        require(type(data["quotes"]) is list and len(data["quotes"]) <= 1024, "quotes")
        quotes = []
        for row in data["quotes"]:
            require(type(row) is dict and type(row.get("timeNs")) is str and len(row["timeNs"]) <= 23 and
                    row["timeNs"].isascii() and row["timeNs"].isdigit(), "quote_time")
            event_time = ns(int(row["timeNs"]))
            require(str(event_time) == row["timeNs"], "quote_time")
            quotes.append(Quote(row["id"], event_time, row["bid"], row["ask"],
                                row["sequence"], row["fresh"], row["gapBefore"]))
    except (KeyError, TypeError, OverflowError):
        require(False, "artifact_fields")
    quotes = tuple(quotes)
    # Reject unknown fields, alternate representations and hidden suffix records.
    require(evidence_bytes(request, quotes) == raw, "artifact_shape")
    return request, quotes


def evaluate(request, quotes):
    """Evaluate <=1024 revealed quotes, without inferring coverage from quietness.

    No-crossing means no observed crossing in the supplied covered interval,
    not no possible crossing between sampled quotes. Same-time activation is
    unresolved because this minimal contract has no activation sequence token.
    """
    visible, payload = _prepare(request, quotes)
    fingerprint = content_hash(payload)

    def result(kind, reason, quote=None, price=None):
        return Decision(kind, reason, quote.event_id if quote else None,
                        decimal_text(price) if price is not None else None, fingerprint)

    if not request.coverage_complete or not (
            request.coverage_start_ns <= request.activation_ns and request.coverage_end_ns >= request.horizon_ns):
        return result("UNRESOLVED", "INSUFFICIENT_COVERAGE")
    ids = set()
    last_time = last_sequence = None
    for quote in visible:
        if quote.event_id in ids or (last_time is not None and quote.time_ns < last_time):
            return result("UNRESOLVED", "INVALID_CHRONOLOGY")
        ids.add(quote.event_id)
        last_time = quote.time_ns
        if request.trusted_sequence:
            if quote.source_sequence is None or (last_sequence is not None and quote.source_sequence <= last_sequence):
                return result("UNRESOLVED", "INVALID_SOURCE_SEQUENCE")
            last_sequence = quote.source_sequence
    for time, group in groupby(visible, key=lambda q: q.time_ns):
        group = tuple(group)
        if time < request.activation_ns:
            continue
        if time == request.activation_ns:
            return result("UNRESOLVED", "ACTIVATION_ORDER_UNKNOWN")
        if len(group) > 1 and not request.trusted_sequence:
            return result("UNRESOLVED", "TIMESTAMP_TIE")
        for quote in group:
            if quote.gap_before:
                return result("UNRESOLVED", "COVERAGE_GAP")
            if quote.bid is None or quote.ask is None:
                return result("UNRESOLVED", "MISSING_SIDE")
            if not quote.fresh:
                return result("UNRESOLVED", "STALE_QUOTE")
            if quote.bid > quote.ask:
                return result("UNRESOLVED", "CROSSED_QUOTE")
            price = quote.bid if request.side == "LONG" else quote.ask
            stop = price <= request.sl if request.side == "LONG" else price >= request.sl
            target = price >= request.tp if request.side == "LONG" else price <= request.tp
            if stop or target:
                return result("OBSERVED_CROSSING", "SL" if stop else "TP", quote, price)
    return result("NO_OBSERVED_CROSSING", "SUPPLIED_INTERVAL_ONLY")
