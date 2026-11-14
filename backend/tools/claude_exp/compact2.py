"""Compact tick v2: LOSSLESS re-encoding of a verified compact v1 month (about 4x smaller). Derived, non-authoritative, like v1.

Stored per tick: dt (time delta), dbid (bid delta), dspread (ask - bid delta). Everything else v1 stores is recomputed on read:
  ts_ns    = rowGroup.firstTimeNs + cumsum(dt) * unit            unit = 1,000,000 (ms precision proven for the month) or 1
  bid      = rowGroup.firstBid + cumsum(dbid)
  ask      = bid + rowGroup.firstSpread + cumsum(dspread)         (a crossed quote has a negative spread: still exact)
  ordinal  = rowGroup.firstOrdinal + index                        (refused at write time unless the source ordinals are contiguous)
  is_crossed = ask < bid
  group_id = rowGroup.firstGroup + cumsum(ts != previous ts)
Every row group carries its own anchors, so any row group decodes alone (seek and no-look-ahead windows work exactly as in v1).
`CompactV2Reader` is a drop-in for `CompactTickReader` (same methods, same six logical columns), and `verify_equal` proves a month decodes
to the byte-identical arrays of its v1 source. Nothing is deleted by this module.
"""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import digest, require
from market_data.compact_tick import CompactTickReader, COLUMNS, INT64_MAX, MANIFEST_NAME as V1_MANIFEST

ARTIFACT = "BTL-COMPACT-TICK-2"
MANIFEST_NAME = "compact2.json"
WRITER = "tools.claude_exp.compact2/1"
LEVEL = 19
STORED = ("dt", "dbid", "dspread")
SCHEMA = pa.schema([pa.field(n, pa.int64(), nullable=False) for n in STORED], metadata={
    b"btl.format": ARTIFACT.encode(), b"btl.derived": b"true", b"btl.authoritative": b"false",
    b"btl.note": b"delta encoded; anchors in compact2.json row groups"})
ENCODING = {n: "DELTA_BINARY_PACKED" for n in STORED}


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def _decode(chunk, group, unit):
    n = int(group["eventCount"])
    dt = chunk["dt"].to_numpy()
    ts = int(group["firstTimeNs"]) + np.cumsum(dt, dtype=np.int64) * unit
    bid = int(group["firstBid"]) + np.cumsum(chunk["dbid"].to_numpy(), dtype=np.int64)
    ask = bid + int(group["firstSpread"]) + np.cumsum(chunk["dspread"].to_numpy(), dtype=np.int64)
    step = np.zeros(n, dtype=np.int64)                      # row 0 keeps firstGroup; a later row opens a new group when its time differs
    step[1:] = ts[1:] != ts[:-1]
    return dict(ts_ns=ts, bid=bid, ask=ask, ordinal=int(group["firstOrdinal"]) + np.arange(n, dtype=np.int64),
                is_crossed=ask < bid, group_id=int(group["firstGroup"]) + np.cumsum(step, dtype=np.int64))


def encode_month(src_root, dst_root):
    """v1 month directory -> v2 month directory (refuses to overwrite; returns the v2 manifest)."""
    src = CompactTickReader(src_root)
    src.verify_all(deep=True)                               # never re-encode something that was not already proven
    final = Path(dst_root).resolve()
    require(not final.exists(), "immutable", "IMMUTABLE_ALREADY_PUBLISHED")
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    files = []
    for month, entry in src._files.items():
        first_ts = int(entry["firstTimeNs"])
        unit = 1_000_000
        for block in src.iter_blocks(int(entry["firstTimeNs"]), int(entry["lastTimeNs"]) + 1, atomic=False):
            if bool(np.any(block["ts_ns"] % 1_000_000)):
                unit = 1
                break
        (stage / month).mkdir()
        path = stage / month / "ticks2.parquet"
        writer = pq.ParquetWriter(path, SCHEMA, compression="zstd", compression_level=LEVEL, use_dictionary=False,
                                  column_encoding=ENCODING, write_statistics=True, version="2.6")
        groups, rows, expected_ord = [], 0, None
        for block in src.iter_blocks(int(entry["firstTimeNs"]), int(entry["lastTimeNs"]) + 1, atomic=False):
            ts, bid, ask, ordn, gid = block["ts_ns"], block["bid"], block["ask"], block["ordinal"], block["group_id"]
            n = len(ts)
            require(bool(np.array_equal(ordn, ordn[0] + np.arange(n, dtype=np.int64))), "ordinal", "NON_CONTIGUOUS_ORDINAL")
            if expected_ord is not None:
                require(int(ordn[0]) == expected_ord, "ordinal", "NON_CONTIGUOUS_ORDINAL")
            expected_ord = int(ordn[-1]) + 1
            spread = ask - bid
            dt = np.diff(ts, prepend=ts[0])
            require(unit == 1 or bool(np.all(dt % unit == 0)), "time", "PRECISION_LOSS")
            table = pa.Table.from_arrays([pa.array(dt // unit), pa.array(np.diff(bid, prepend=bid[0])),
                                          pa.array(np.diff(spread, prepend=spread[0]))], schema=SCHEMA)
            writer.write_table(table, row_group_size=n)
            groups.append(dict(index=len(groups), eventCount=int(n), firstTimeNs=str(int(ts[0])), lastTimeNs=str(int(ts[-1])),
                               firstBid=int(bid[0]), firstSpread=int(spread[0]), firstOrdinal=int(ordn[0]),
                               firstGroup=int(gid[0]), lastGroup=int(gid[-1])))
            rows += n
        writer.close()
        require(rows == entry["eventCount"], "eventCount", "COUNT_CONFLICT")
        files.append(dict(month=month, path=f"{month}/ticks2.parquet", sha256=_sha256_file(path), bytes=path.stat().st_size,
                          eventCount=rows, firstTimeNs=entry["firstTimeNs"], lastTimeNs=entry["lastTimeNs"],
                          firstOrdinal=entry["firstOrdinal"], lastOrdinal=entry["lastOrdinal"], timeUnitNs=unit, rowGroups=groups))
    m = src.manifest
    payload = dict(schemaVersion=1, artifact=ARTIFACT, derived=True, authoritative=False, writer=WRITER,
                   parent=dict(m["parent"]), derivedFrom=dict(artifact=m["artifact"], manifestHash=m["manifestHash"]),
                   evidenceClass=m["evidenceClass"], ordering=m["ordering"], rights=m["rights"], priceScale=m["priceScale"],
                   columns=list(STORED), logicalColumns=list(COLUMNS), layout="ONE_FILE_PER_UTC_MONTH", blockRows=m["blockRows"],
                   compression=dict(codec="zstd", level=LEVEL, encoding="DELTA_BINARY_PACKED"), eventCount=m["eventCount"],
                   groupCount=m["groupCount"], quality=m["quality"], files=files)
    manifest = {**payload, "manifestHash": content_hash(payload)}
    (stage / MANIFEST_NAME).write_bytes(canonical_bytes(manifest))
    os.rename(stage, final)
    return manifest


class CompactV2Reader(CompactTickReader):
    """Same interface and logical columns as CompactTickReader; decodes the delta format."""

    def __init__(self, root, *, expected_manifest_hash=None):
        self.root = Path(root).resolve()
        raw = (self.root / MANIFEST_NAME).read_bytes()
        manifest = json.loads(raw)
        require(type(manifest) is dict and canonical_bytes(manifest) == raw, "manifest", "SCHEMA_MISMATCH")
        require(manifest.get("artifact") == ARTIFACT and manifest.get("derived") is True and manifest.get("authoritative") is False,
                "manifest", "SCHEMA_MISMATCH")
        supplied = manifest.pop("manifestHash", None)
        digest(supplied, "manifestHash")
        require(content_hash(manifest) == supplied, "manifestHash", "CHILD_HASH_MISMATCH")
        manifest["manifestHash"] = supplied
        if expected_manifest_hash is not None:
            require(supplied == expected_manifest_hash, "manifestHash", "SOURCE_PIN_CHANGED")
        require(list(manifest["columns"]) == list(STORED), "columns", "SCHEMA_MISMATCH")
        self.manifest, self.scale = manifest, manifest["priceScale"]
        self._files = {}
        last = -1
        for entry in manifest["files"]:
            require(entry["path"] == f"{entry['month']}/ticks2.parquet", "path", "SCHEMA_MISMATCH")
            require(int(entry["firstTimeNs"]) >= last, "files", "ORDER_REVERSAL")
            last = int(entry["lastTimeNs"])
            self._files[entry["month"]] = entry
        require(sum(e["eventCount"] for e in manifest["files"]) == manifest["eventCount"], "eventCount", "COUNT_CONFLICT")

    def verify_file(self, month):
        entry = self._files[month]
        path = self.root / entry["path"]
        require(path.stat().st_size == entry["bytes"] and _sha256_file(path) == entry["sha256"], "file", "CHILD_HASH_MISMATCH")
        meta = pq.ParquetFile(path).metadata
        require(meta.num_rows == entry["eventCount"] and meta.num_row_groups == len(entry["rowGroups"]), "parquetFooter", "CORRUPT_RECORD")

    def _row_groups(self, start_ns, end_ns):
        for month, entry in self._files.items():
            if int(entry["lastTimeNs"]) < start_ns or int(entry["firstTimeNs"]) >= end_ns:
                continue
            parquet = pq.ParquetFile(self.root / entry["path"])
            for group in entry["rowGroups"]:
                if int(group["lastTimeNs"]) < start_ns or int(group["firstTimeNs"]) >= end_ns:
                    continue
                yield _decode(parquet.read_row_group(group["index"]), group, entry["timeUnitNs"])


def open_compact(root, **kw):
    """Open a v1 or v2 month directory (whichever manifest is present)."""
    root = Path(root)
    if (root / MANIFEST_NAME).exists():
        return CompactV2Reader(root, **kw)
    return CompactTickReader(root, **kw)


def verify_equal(v1_root, v2_root):
    """Decode both and require identical arrays for all six logical columns. Returns the number of ticks compared."""
    a, b = CompactTickReader(v1_root), CompactV2Reader(v2_root)
    require(a.scale == b.scale and a.manifest["eventCount"] == b.manifest["eventCount"], "shape", "COUNT_CONFLICT")
    require(b.manifest["derivedFrom"]["manifestHash"] == a.manifest["manifestHash"], "derivedFrom", "SOURCE_PIN_CHANGED")
    ba, bb = a.iter_blocks(0, INT64_MAX, atomic=False), b.iter_blocks(0, INT64_MAX, atomic=False)
    total = 0
    for x, y in zip(ba, bb):
        for col in COLUMNS:
            require(x[col].dtype == y[col].dtype and bool(np.array_equal(x[col], y[col])), col, "DECODE_MISMATCH")
        total += len(x["ts_ns"])
    require(total == a.manifest["eventCount"], "count", "COUNT_CONFLICT")
    require(next(ba, None) is None and next(bb, None) is None, "blocks", "COUNT_CONFLICT")
    return total
