"""Bounded planning and validation helpers for operator-supplied Exness ticks.

This module deliberately performs no network access and grants no data rights.
It uses the repository's existing Exness CSV contract and Monthly Parquet V2
writer; it does not define a second canonical tick encoding.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from contracts.primitives import require
from .exness_v2 import FIELDS, TICK_HISTORY_FIELDS


INSTRUMENTS = (
    "AUDUSD", "EURGBP", "NZDUSD", "USDCHF", "AUDJPY", "CADJPY",
    "EURUSD", "GBPUSD", "NZDJPY", "USDCAD", "CHFJPY", "EURJPY",
    "EURNZD", "GBPJPY", "USDJPY", "XAUUSD",
)
START_YEAR, START_MONTH = 2024, 1
END_YEAR, END_MONTH = 2026, 10
ARTIFACT = "RIKSORA-EXNESS-MONTHLY-PLAN-1"
CHECKPOINT_ARTIFACT = "RIKSORA-EXNESS-MONTHLY-CHECKPOINT-1"
MAX_ARCHIVE_MEMBERS = 4096
MAX_MEMBER_BYTES = 16 * 1024**3
STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}Z\Z")


@dataclass(frozen=True)
class Partition:
    original_symbol: str
    canonical_instrument: str
    year: int
    month: int

    @property
    def period(self):
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def relative_path(self):
        return (Path("datasets") / "exness" / self.original_symbol /
                f"year={self.year:04d}" / f"month={self.month:02d}" / "ticks.parquet")


def required_partitions():
    """Return the frozen 16 × 34 logical partition inventory (544 rows)."""
    rows = []
    year, month = START_YEAR, START_MONTH
    while (year, month) <= (END_YEAR, END_MONTH):
        rows.extend(Partition(symbol, symbol, year, month) for symbol in INSTRUMENTS)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(rows)


def plan():
    """Build a machine-readable inventory without asserting source availability."""
    partitions = required_partitions()
    return {"schemaVersion": 1, "artifact": ARTIFACT,
            "period": {"start": "2024-01", "endInclusive": "2026-10"},
            "instrumentCount": len(INSTRUMENTS), "partitionCount": len(partitions),
            "acquisition": "BLOCKED_RIGHTS_AND_SOURCE_ACCESS_UNVERIFIED",
            "partitions": [{"originalSymbol": row.original_symbol,
                "canonicalInstrument": row.canonical_instrument, "year": row.year,
                "month": row.month, "path": row.relative_path.as_posix(),
                "status": "PENDING"} for row in partitions]}


def partition_for(original_symbol: str, year: int, month: int) -> Partition:
    # Exact spelling is the dataset identity. In particular, XAUUSDm is not
    # silently normalized to XAUUSD.
    require(type(original_symbol) is str and original_symbol in INSTRUMENTS,
            "originalSymbol", "UNMAPPED_PROVIDER_SYMBOL")
    require(type(year) is int and START_YEAR <= year <= END_YEAR and
            type(month) is int and 1 <= month <= 12 and
            (year, month) <= (END_YEAR, END_MONTH), "period", "RANGE_CONFLICT")
    return Partition(original_symbol, original_symbol, year, month)


def _month_bounds_ns(year, month):
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1,
                   tzinfo=timezone.utc)
    return int(start.timestamp()) * 1_000_000_000, int(end.timestamp()) * 1_000_000_000


def sha256_file(path):
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            sha.update(block)
    return sha.hexdigest()


def inspect_zip(path):
    """Inspect ZIP directory metadata only; never extracts or downloads data."""
    entries = []
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        require(0 < len(infos) <= MAX_ARCHIVE_MEMBERS, "archive", "ARTIFACT_LIMIT")
        for info in infos:
            name = info.filename
            member = PurePosixPath(name)
            mode = info.external_attr >> 16
            require(not member.is_absolute() and ".." not in member.parts and
                    "\\" not in name and not (mode & 0o170000) == 0o120000,
                    "archiveMember", "SOURCE_PATH_REFUSED")
            require(not info.flag_bits & 0x1 and info.file_size <= MAX_MEMBER_BYTES,
                    "archiveMember", "ARTIFACT_LIMIT")
            entries.append({"name": name, "bytes": info.file_size,
                            "crc32": f"{info.CRC:08x}", "isCsv": name.lower().endswith(".csv")})
    require(any(row["isCsv"] for row in entries), "archive", "SCHEMA_MISMATCH")
    return {"sha256": sha256_file(path), "bytes": Path(path).stat().st_size,
            "members": entries}


def validate_csv_month(path, *, original_symbol: str, year: int, month: int):
    """Stream-check a source CSV without sorting, dropping, or filling ticks.

    The accepted header matches the already implemented local Exness reader.
    Equal timestamps and duplicate rows are retained; source order is reported
    but never upgraded to trusted sequence evidence.
    """
    partition = partition_for(original_symbol, year, month)
    start_ns, end_ns = _month_bounds_ns(year, month)
    count = equal_times = exact_duplicates = crossed = 0
    first = last = None
    previous_ns = None
    previous_row = None
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader, None)
        require(header in (FIELDS, TICK_HISTORY_FIELDS), "header", "SCHEMA_MISMATCH")
        for values in reader:
            require(len(values) == len(header), "record", "MALFORMED_RECORD")
            row = dict(zip(header, values))
            if "Exness" not in row:
                row["Exness"] = "exness"
            feed, symbol, timestamp, bid_text, ask_text = (row[key] for key in FIELDS)
            require(feed == "exness" and symbol == partition.original_symbol,
                    "symbol", "IDENTITY_CONFLICT")
            require(STAMP.fullmatch(timestamp) is not None, "timestamp", "INVALID_TIMESTAMP")
            moment = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            ns = int(moment.timestamp()) * 1_000_000_000 + moment.microsecond * 1000
            require(start_ns <= ns < end_ns, "timestamp", "RANGE_CONFLICT")
            require(previous_ns is None or ns >= previous_ns, "timestamp", "ORDER_REVERSAL")
            try:
                bid, ask = Decimal(bid_text), Decimal(ask_text)
            except InvalidOperation:
                require(False, "price", "MALFORMED_PRICE")
            require(bid.is_finite() and ask.is_finite() and bid > 0 and ask > 0,
                    "price", "MALFORMED_PRICE")
            crossed += ask < bid
            if previous_ns == ns:
                equal_times += 1
            raw = tuple(row[key] for key in FIELDS)
            exact_duplicates += raw == previous_row
            previous_row = raw
            count += 1
            first = first or timestamp
            last, previous_ns = timestamp, ns
    require(count > 0, "records", "MISSING_REQUIRED_FIELD")
    return {"artifact": "RIKSORA-EXNESS-CSV-VALIDATION-1", "originalSymbol": original_symbol,
            "canonicalInstrument": partition.canonical_instrument, "period": partition.period,
            "recordCount": count, "firstTimestamp": first, "lastTimestamp": last,
            "equalTimestampAdjacentRows": equal_times, "exactDuplicateAdjacentRowsPreserved": exact_duplicates,
            "crossedQuoteRows": crossed, "timestamps": "VERIFIED_NONDECREASING",
            "ties": "UNTRUSTED", "sourceSha256": sha256_file(path),
            "rights": "UNKNOWN", "coverage": "OBSERVED_ROWS_ONLY_NOT_COMPLETE_MONTH"}


class Checkpoint:
    """Atomic resumability ledger; a partition is done only with all hash pins."""
    def __init__(self, path):
        self.path = Path(path)
        self.rows = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            require(raw.get("artifact") == CHECKPOINT_ARTIFACT and raw.get("schemaVersion") == 1 and
                    type(raw.get("partitions")) is dict, "checkpoint", "SCHEMA_MISMATCH")
            self.rows = raw["partitions"]

    @staticmethod
    def _key(partition):
        return f"{partition.original_symbol}/{partition.period}"

    def verified(self, partition, *, source_sha256, parquet_sha256, manifest_sha256):
        row = self.rows.get(self._key(partition), {})
        return row == {"status": "VERIFIED", "sourceSha256": source_sha256,
                       "parquetSha256": parquet_sha256, "manifestSha256": manifest_sha256}

    def mark_verified(self, partition, *, source_sha256, parquet_sha256, manifest_sha256):
        for value in (source_sha256, parquet_sha256, manifest_sha256):
            require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "hash", "INVALID_INPUT")
        self.rows[self._key(partition)] = {"status": "VERIFIED", "sourceSha256": source_sha256,
            "parquetSha256": parquet_sha256, "manifestSha256": manifest_sha256}
        self._save()

    def status(self, partition):
        return self.rows.get(self._key(partition), {"status": "PENDING"})["status"]

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"schemaVersion": 1, "artifact": CHECKPOINT_ARTIFACT,
                              "partitions": self.rows}, sort_keys=True, separators=(",", ":"))
        fd, name = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(name):
                os.unlink(name)
