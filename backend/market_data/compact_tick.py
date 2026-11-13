"""Compact columnar tick derivative: fast reads from an already validated tick dataset.

This is a DERIVED, NON-AUTHORITATIVE projection. It does not replace the
authoritative canonical tick path (``monthly_parquet`` / ``ticks.contracts``),
does not change any frozen contract or hash, grants no source rights, and never
settles a trade. Each file set records its parent dataset identity so a result
can always be traced back to the authoritative dataset it was derived from.

Cost model: validation happens ONCE, vectorised per block, when the files are
written. Reading is plain Arrow column access with no per-tick Python object,
JSON or hash. Prices are exact scaled integers (never binary floats).
Distinct records sharing a timestamp are kept in source order with their source
ordinal and a ``group_id`` so a consumer can advance them atomically; source
order is NOT promoted to a trusted venue sequence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import digest, require

SCHEMA_VERSION = 1
ARTIFACT = "BTL-COMPACT-TICK-1"
MANIFEST_NAME = "compact.json"
WRITER = "market_data.compact_tick/1"
COMPRESSION = "zstd"
COMPRESSION_LEVEL = 3
DEFAULT_BLOCK_ROWS = 65_536
MAX_BLOCK_ROWS = 1_048_576
MAX_SCALE = 18
INT64_MAX = 2**63 - 1
_PRICE = re.compile(r"[0-9]+(?:\.[0-9]+)?")
_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
EVIDENCE_CLASSES = ("PROVIDER_OBSERVATION", "SYNTHETIC_CONTRACT_ONLY")
COLUMNS = ("ts_ns", "bid", "ask", "ordinal", "is_crossed", "group_id")

SCHEMA = pa.schema([
    pa.field("ts_ns", pa.int64(), nullable=False),
    pa.field("bid", pa.int64(), nullable=False),
    pa.field("ask", pa.int64(), nullable=False),
    pa.field("ordinal", pa.int64(), nullable=False),
    pa.field("is_crossed", pa.bool_(), nullable=False),
    pa.field("group_id", pa.int64(), nullable=False),
], metadata={
    b"btl.format": ARTIFACT.encode(),
    b"btl.derived": b"true",
    b"btl.authoritative": b"false",
    b"btl.timestamp-unit": b"nanoseconds-since-unix-epoch",
    b"btl.price": b"exact scaled integer; scale in compact.json",
    b"btl.ordinal": b"source ordinal; not a trusted venue sequence",
})


def _scaled(text, scale, field):
    """Exact decimal text -> scaled integer; refuses anything not exactly representable."""
    require(type(text) is str and _PRICE.fullmatch(text) is not None, field, "MALFORMED_PRICE")
    whole, _, frac = text.partition(".")
    require(len(frac) <= scale or not frac[scale:].strip("0"), field, "PRECISION_LOSS")
    value = int((whole + frac[:scale].ljust(scale, "0")).lstrip("0") or "0")
    require(0 < value <= INT64_MAX, field, "MALFORMED_PRICE")
    return value


def _month_labels(ts):
    return (ts.astype("datetime64[ns]").astype("datetime64[M]")).astype(str)


def _sha256_file(path):
    sha = hashlib.sha256()
    with open(path, "rb") as stream:
        while block := stream.read(1 << 20):
            sha.update(block)
    return sha.hexdigest()


def _sync(path):
    with open(path, "rb+") as stream:
        try:
            os.fsync(stream.fileno())
        except OSError:
            pass  # not every platform allows it on every handle; data is already closed/flushed


def write_compact(root, events, *, parent, scale, block_rows=DEFAULT_BLOCK_ROWS,
                  evidence_class="PROVIDER_OBSERVATION", rights=None, ordering=None):
    """Write immutable per-UTC-month files plus ``compact.json``.

    ``events`` yields mappings with ``timeNs``, ``bid``, ``ask`` (exact decimal
    text) and ``rawOrdinal`` (canonical wire events qualify). ``parent`` pins the
    authoritative dataset: ``datasetId``, ``datasetVersion`` (64-hex) and,
    optionally, ``manifestHash``. Input order is preserved and verified, never
    sorted. Existing output is never replaced.
    """
    require(type(block_rows) is int and 1 <= block_rows <= MAX_BLOCK_ROWS, "blockRows", "ARTIFACT_LIMIT")
    require(type(scale) is int and 0 <= scale <= MAX_SCALE, "scale", "INVALID_INPUT")
    require(evidence_class in EVIDENCE_CLASSES, "evidenceClass", "INVALID_INPUT")
    require(type(parent) is dict and type(parent.get("datasetId")) is str and parent["datasetId"],
            "parent", "MISSING_REQUIRED_FIELD")
    digest(parent.get("datasetVersion"), "parentDatasetVersion")
    if parent.get("manifestHash") is not None:
        digest(parent["manifestHash"], "parentManifestHash")
    rights = rights or {"class": "UNKNOWN", "evidenceHash": None}
    ordering = ordering or {"timestamps": "VERIFIED_NONDECREASING", "ties": "UNTRUSTED"}
    require(evidence_class != "SYNTHETIC_CONTRACT_ONLY" or rights.get("class") == "SYNTHETIC",
            "rights", "SYNTHETIC_RIGHTS")
    final = Path(root).resolve()
    require(not final.exists(), "immutable", "IMMUTABLE_ALREADY_PUBLISHED")
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))

    files, state = [], dict(prev_ts=-1, prev_ord=-1, group=-1, total=0, crossed=0, ties=0, max_group=0,
                            run=0, writer=None, month=None, rows=0, groups=[], first=None, last=None)

    def close_month():
        if state["writer"] is None:
            return
        state["writer"].close()
        path = stage / state["month"] / "ticks.parquet"
        _sync(path)
        meta = pq.ParquetFile(path).metadata
        require(meta.num_rows == state["rows"] and meta.num_row_groups == len(state["groups"]),
                "parquetFooter", "CORRUPT_RECORD")
        files.append(dict(month=state["month"], path=f"{state['month']}/ticks.parquet",
                          sha256=_sha256_file(path), bytes=path.stat().st_size, eventCount=state["rows"],
                          firstTimeNs=str(state["first"][0]), lastTimeNs=str(state["last"][0]),
                          firstOrdinal=str(state["first"][1]), lastOrdinal=str(state["last"][1]),
                          rowGroups=state["groups"]))
        state.update(writer=None, month=None, rows=0, groups=[], first=None, last=None)

    def flush(ts, bid, ask, ordn):
        n = len(ts)
        if n == 0:
            return
        ts = np.asarray(ts, dtype=np.int64); bid = np.asarray(bid, dtype=np.int64)
        ask = np.asarray(ask, dtype=np.int64); ordn = np.asarray(ordn, dtype=np.int64)
        require(ts[0] >= state["prev_ts"] and bool(np.all(np.diff(ts) >= 0)), "eventOrder", "ORDER_REVERSAL")
        require(ordn[0] > state["prev_ord"] and bool(np.all(np.diff(ordn) > 0)), "ordinal", "INVALID_SOURCE_ORDINAL")
        new = np.empty(n, dtype=bool)
        new[0] = ts[0] != state["prev_ts"]
        new[1:] = ts[1:] != ts[:-1]
        group = state["group"] + np.cumsum(new)
        crossed = ask < bid
        state["crossed"] += int(crossed.sum())
        state["ties"] += int((~new).sum())
        # Longest run of equal timestamps; a run may continue across block boundaries.
        starts = np.flatnonzero(new)
        if len(starts) == 0:
            state["run"] += n
            state["max_group"] = max(state["max_group"], state["run"])
        else:
            if starts[0] > 0:
                state["run"] += int(starts[0])
                state["max_group"] = max(state["max_group"], state["run"])
            lengths = np.diff(np.append(starts, n))
            state["max_group"] = max(state["max_group"], int(lengths.max()))
            state["run"] = int(lengths[-1])
        months = _month_labels(ts)
        cuts = np.flatnonzero(months[1:] != months[:-1]) + 1
        for lo, hi in zip(np.concatenate(([0], cuts)), np.concatenate((cuts, [n]))):
            month = str(months[lo])
            if state["month"] is not None and month != state["month"]:
                close_month()
            if state["month"] is None:
                (stage / month).mkdir(exist_ok=True)
                state["writer"] = pq.ParquetWriter(
                    stage / month / "ticks.parquet", SCHEMA, compression=COMPRESSION,
                    compression_level=COMPRESSION_LEVEL, write_statistics=True, version="2.6")
                state["month"] = month
            table = pa.Table.from_arrays(
                [pa.array(ts[lo:hi]), pa.array(bid[lo:hi]), pa.array(ask[lo:hi]), pa.array(ordn[lo:hi]),
                 pa.array(crossed[lo:hi]), pa.array(group[lo:hi])], schema=SCHEMA)
            state["writer"].write_table(table, row_group_size=hi - lo)
            state["groups"].append(dict(index=len(state["groups"]), eventCount=int(hi - lo),
                                        firstTimeNs=str(int(ts[lo])), lastTimeNs=str(int(ts[hi - 1])),
                                        firstGroup=int(group[lo]), lastGroup=int(group[hi - 1])))
            state["rows"] += int(hi - lo)
            state["first"] = state["first"] or (int(ts[lo]), int(ordn[lo]))
            state["last"] = (int(ts[hi - 1]), int(ordn[hi - 1]))
        state["prev_ts"], state["prev_ord"], state["group"] = int(ts[-1]), int(ordn[-1]), int(group[-1])
        state["total"] += n

    try:
        ts, bid, ask, ordn = [], [], [], []
        for event in events:
            t, o = int(event["timeNs"]), int(event["rawOrdinal"])
            require(0 <= t <= INT64_MAX and o >= 0, "event", "RANGE_CONFLICT")
            ts.append(t); ordn.append(o)
            bid.append(_scaled(event["bid"], scale, "bid")); ask.append(_scaled(event["ask"], scale, "ask"))
            if len(ts) == block_rows:
                flush(ts, bid, ask, ordn)
                ts, bid, ask, ordn = [], [], [], []
        flush(ts, bid, ask, ordn)
        close_month()
        require(state["total"] > 0, "events", "EMPTY_DATASET")
    except BaseException:
        if state["writer"] is not None:
            state["writer"].close()
        raise  # the unpublished staging directory is kept for inspection; it is never a dataset

    payload = dict(
        schemaVersion=SCHEMA_VERSION, artifact=ARTIFACT, derived=True, authoritative=False, writer=WRITER,
        parent=dict(datasetId=parent["datasetId"], datasetVersion=parent["datasetVersion"],
                    manifestHash=parent.get("manifestHash")),
        evidenceClass=evidence_class, ordering=ordering, rights=rights, priceScale=scale,
        columns=list(COLUMNS), layout="ONE_FILE_PER_UTC_MONTH", blockRows=block_rows,
        compression=dict(codec=COMPRESSION, level=COMPRESSION_LEVEL),
        eventCount=state["total"], groupCount=state["group"] + 1,
        quality=dict(crossedQuotes=state["crossed"], equalTimestampTicks=state["ties"],
                     maxGroupSize=state["max_group"]),
        files=files)
    manifest = {**payload, "manifestHash": content_hash(payload)}
    (stage / MANIFEST_NAME).write_bytes(canonical_bytes(manifest))
    _sync(stage / MANIFEST_NAME)
    require(not final.exists(), "immutable", "IMMUTABLE_ALREADY_PUBLISHED")
    os.rename(stage, final)
    return manifest


class CompactTickReader:
    """Read bounded ranges as NumPy columns; every file is pinned by SHA-256 in the manifest.

    The reader returns only rows inside the requested ``[start_ns, end_ns)``
    window. Enforcing a no-look-ahead ``end_ns`` is the caller's (controller's)
    responsibility, exactly as for the authoritative provider.
    """

    def __init__(self, root, *, expected_manifest_hash=None):
        self.root = Path(root).resolve()
        raw = (self.root / MANIFEST_NAME).read_bytes()
        manifest = json.loads(raw)
        require(type(manifest) is dict and canonical_bytes(manifest) == raw, "manifest", "SCHEMA_MISMATCH")
        require(manifest.get("schemaVersion") == SCHEMA_VERSION and manifest.get("artifact") == ARTIFACT
                and manifest.get("derived") is True and manifest.get("authoritative") is False,
                "manifest", "SCHEMA_MISMATCH")
        supplied = manifest.pop("manifestHash", None)
        digest(supplied, "manifestHash")
        require(content_hash(manifest) == supplied, "manifestHash", "CHILD_HASH_MISMATCH")
        manifest["manifestHash"] = supplied
        if expected_manifest_hash is not None:
            require(supplied == expected_manifest_hash, "manifestHash", "SOURCE_PIN_CHANGED")
        require(list(manifest["columns"]) == list(COLUMNS), "columns", "SCHEMA_MISMATCH")
        require(type(manifest["priceScale"]) is int and 0 <= manifest["priceScale"] <= MAX_SCALE,
                "priceScale", "SCHEMA_MISMATCH")
        self.manifest, self.scale = manifest, manifest["priceScale"]
        self._files = {}
        last = -1
        for entry in manifest["files"]:
            require(_MONTH.fullmatch(entry["month"]) is not None and entry["month"] > (self._files and max(self._files) or ""),
                    "month", "SCHEMA_MISMATCH")
            require(entry["path"] == f"{entry['month']}/ticks.parquet", "path", "SCHEMA_MISMATCH")
            require(int(entry["firstTimeNs"]) >= last, "files", "ORDER_REVERSAL")
            last = int(entry["lastTimeNs"])
            self._files[entry["month"]] = entry
        require(sum(item["eventCount"] for item in manifest["files"]) == manifest["eventCount"],
                "eventCount", "COUNT_CONFLICT")

    @property
    def parent(self):
        return dict(self.manifest["parent"])

    def price(self, value):
        """Scaled integer -> exact Decimal."""
        return Decimal(int(value)).scaleb(-self.scale)

    def verify_file(self, month):
        entry = self._files[month]
        path = self.root / entry["path"]
        require(path.stat().st_size == entry["bytes"] and _sha256_file(path) == entry["sha256"],
                "file", "CHILD_HASH_MISMATCH")
        footer = pq.ParquetFile(path).metadata
        require(footer.num_rows == entry["eventCount"] and footer.num_row_groups == len(entry["rowGroups"]),
                "parquetFooter", "CORRUPT_RECORD")

    def verify_all(self, *, deep=False):
        """Hash every file; ``deep`` also re-checks order, ordinals, groups and crossed counts."""
        for month in self._files:
            self.verify_file(month)
        if deep:
            prev_ts = prev_ord = prev_group = -1
            crossed = 0
            for block in self.iter_blocks(0, INT64_MAX, atomic=False):
                ts, ordn, group = block["ts_ns"], block["ordinal"], block["group_id"]
                require(ts[0] >= prev_ts and bool(np.all(np.diff(ts) >= 0)), "order", "ORDER_REVERSAL")
                require(ordn[0] > prev_ord and bool(np.all(np.diff(ordn) > 0)), "ordinal", "INVALID_SOURCE_ORDINAL")
                same = np.empty(len(ts), dtype=bool)
                same[0] = ts[0] == prev_ts
                same[1:] = ts[1:] == ts[:-1]
                expected = prev_group + np.cumsum(~same)
                require(bool(np.array_equal(expected, group)), "group", "COUNT_CONFLICT")
                crossed += int(block["is_crossed"].sum())
                require(bool(np.array_equal(block["is_crossed"], block["ask"] < block["bid"])),
                        "crossed", "COUNT_CONFLICT")
                prev_ts, prev_ord, prev_group = int(ts[-1]), int(ordn[-1]), int(group[-1])
            require(crossed == self.manifest["quality"]["crossedQuotes"], "crossed", "COUNT_CONFLICT")
        return dict(eventCount=self.manifest["eventCount"], files=len(self._files))

    def _row_groups(self, start_ns, end_ns):
        for month, entry in self._files.items():
            if int(entry["lastTimeNs"]) < start_ns or int(entry["firstTimeNs"]) >= end_ns:
                continue
            parquet = pq.ParquetFile(self.root / entry["path"])
            for group in entry["rowGroups"]:
                if int(group["lastTimeNs"]) < start_ns or int(group["firstTimeNs"]) >= end_ns:
                    continue
                table = parquet.read_row_group(group["index"])
                yield {name: table.column(name).to_numpy() for name in COLUMNS}

    def iter_blocks(self, start_ns, end_ns, *, atomic=True):
        """Yield column dicts for ``[start_ns, end_ns)``.

        With ``atomic`` (default) a timestamp group is never split between two
        yielded blocks, so equal-timestamp ticks always advance together.
        """
        require(type(start_ns) is int and type(end_ns) is int and 0 <= start_ns <= end_ns, "range", "RANGE_CONFLICT")
        carry = None
        for block in self._row_groups(start_ns, end_ns):
            lo = int(np.searchsorted(block["ts_ns"], start_ns, side="left"))
            hi = int(np.searchsorted(block["ts_ns"], end_ns, side="left"))
            if hi <= lo:
                continue
            block = {name: array[lo:hi] for name, array in block.items()}
            if atomic:
                if carry is not None:
                    block = {name: np.concatenate((carry[name], block[name])) for name in COLUMNS}
                    carry = None
                cut = int(np.searchsorted(block["ts_ns"], block["ts_ns"][-1], side="left"))
                if cut == 0:
                    carry = block
                    continue
                carry = {name: array[cut:] for name, array in block.items()}
                block = {name: array[:cut] for name, array in block.items()}
            yield block
        if carry is not None and len(carry["ts_ns"]):
            yield carry

    def read_range(self, start_ns, end_ns):
        """Whole window as one set of arrays (bounded by the caller's window)."""
        blocks = list(self.iter_blocks(start_ns, end_ns, atomic=False))
        if not blocks:
            return {name: np.empty(0, dtype=SCHEMA.field(name).type.to_pandas_dtype()) for name in COLUMNS}
        return {name: np.concatenate([block[name] for block in blocks]) for name in COLUMNS}

    def iter_groups(self, start_ns, end_ns):
        """Yield ``(ts_ns, slice_of_each_column)`` one atomic timestamp group at a time."""
        for block in self.iter_blocks(start_ns, end_ns, atomic=True):
            ts = block["ts_ns"]
            starts = np.flatnonzero(np.concatenate(([True], ts[1:] != ts[:-1])))
            ends = np.append(starts[1:], len(ts))
            for a, b in zip(starts, ends):
                yield int(ts[a]), {name: block[name][a:b] for name in COLUMNS}
