"""Offline, operator-labelled GMT CSV import. No network or execution eligibility.

Accepted header: Gmt time,Ask,Bid,AskVolume,BidVolume
Timestamp: DD.MM.YYYY HH:MM:SS.mmm, explicitly UTC by that header.
The accepted format is a strict local adapter contract, not a claim that every
Dukascopy export uses it. Convert other formats explicitly outside this adapter.
"""
import csv
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re

from contracts.canonical import decimal_text
from contracts.primitives import ContractError, decimal, require
from market_data.instruments import instrument
from .contracts import event_id
from .contracts_v2 import ZERO_VERSION
from .provider import Cancellation
from .storage_v2 import DatasetBuilder

FIELDS = ["Gmt time", "Ask", "Bid", "AskVolume", "BidVolume"]
STAMP = re.compile(r"[0-9]{2}\.[0-9]{2}\.[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def source_pin(path):
    sha = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        while block := stream.read(1048576):
            sha.update(block)
            size += len(block)
    return dict(filename=Path(path).name, bytes=size, sha256=sha.hexdigest())


def record(raw):
    require(0 < len(raw) <= 8192, "record", "ARTIFACT_LIMIT")
    try:
        rows = list(csv.reader([raw.decode("utf-8-sig").rstrip("\r\n")], strict=True))
    except (UnicodeError, csv.Error):
        raise ContractError("MALFORMED_RECORD", "csv") from None
    require(len(rows) == 1 and len(rows[0]) == len(FIELDS), "csv", "SCHEMA_MISMATCH")
    return rows[0]


class DukascopyCsvIngestion:
    def __init__(self, source, folder, *, symbol, month, resume=False,
                 packing=(256, 256, 1024), evidence_class="PROVIDER_OBSERVATION"):
        instrument(symbol)
        require(type(month) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}", month), "month")
        try:
            self.start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
            self.end = datetime(self.start.year + (self.start.month == 12),
                                self.start.month % 12 + 1, 1, tzinfo=timezone.utc)
        except ValueError:
            raise ContractError("INVALID_INPUT", "month") from None
        require(evidence_class in ("PROVIDER_OBSERVATION", "SYNTHETIC_CONTRACT_ONLY"), "evidenceClass")
        self.source, self.symbol, self.month = Path(source), symbol, month
        self.pin = source_pin(self.source)
        with self.source.open("rb") as stream:
            require(record(stream.readline(8193)) == FIELDS, "UTC header", "SCHEMA_MISMATCH")
        self.source_id = "dukascopy:csv:" + self.pin["sha256"][:24]
        # Month/symbol are operator labels, pinned even when the file has no symbol column.
        self.meta = dict(datasetId="local:dukascopy:" + symbol + ":" + month + ":" + self.pin["sha256"][:24],
            providerId="dukascopy", feedId="local-unverified:" + symbol,
            instrumentId="dukascopy:" + symbol, providerSymbol=symbol,
            evidenceClass=evidence_class, adapterVersion="DUKASCOPY-LOCAL-CSV-1",
            validatorVersion="BTL-TICK-VALIDATOR-2", ordering=dict(timestamps="VERIFIED_NONDECREASING",
            ties="UNTRUSTED", sequenceScope=None, sequenceEvidenceHash=None))
        sources = [dict(sourceId=self.source_id, archiveHash=None, memberHash=self.pin["sha256"],
            originalName=self.source.name, acquiredAtUtc=None, sourceUrl=None,
            timestampConvention="Explicit Gmt time header; DD.MM.YYYY HH:MM:SS.mmm UTC",
            resolutionNs="1000000", originalScalePolicy="PRESERVE_RAW_TEXT")]
        self.builder = DatasetBuilder(folder, self.meta, sources, self.pin, packing=packing, resume=resume)

    def _event(self, fields, ordinal):
        stamp, ask_raw, bid_raw, ask_volume, bid_volume = fields
        require(STAMP.fullmatch(stamp) is not None, "timestamp", "INVALID_TIMESTAMP")
        try:
            dt = datetime.strptime(stamp, "%d.%m.%Y %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        except ValueError:
            raise ContractError("INVALID_TIMESTAMP", "timestamp") from None
        require(self.start <= dt < self.end, "month", "OUTSIDE_REQUESTED_MONTH")
        bid, ask = decimal(bid_raw, "bid", positive=True), decimal(ask_raw, "ask", positive=True)
        # Sizes are validated, not mapped to candle volume or added to frozen tick fields.
        require(decimal(ask_volume, "askVolume") >= 0 and decimal(bid_volume, "bidVolume") >= 0, "volume")
        delta = dt - EPOCH
        ns = (delta.days * 86400 + delta.seconds) * 1000000000 + delta.microseconds * 1000
        return dict(schemaVersion=1, artifact="BTL-CANONICAL-TICK-1",
            datasetId=self.meta["datasetId"], datasetVersion=ZERO_VERSION,
            providerId=self.meta["providerId"], feedId=self.meta["feedId"], instrumentId=self.meta["instrumentId"],
            eventId=event_id(self.meta["providerId"], self.meta["feedId"], self.pin["sha256"], str(ordinal)),
            timeNs=str(ns), resolutionNs="1000000", bid=decimal_text(bid), ask=decimal_text(ask),
            rawOrdinal=str(ordinal), trustedSequence=None,
            provenance=dict(sourceId=self.source_id, memberHash=self.pin["sha256"], originalTimestamp=stamp),
            quality=dict(evidenceHash=None, quote="CROSSED" if bid > ask else "VALID",
                         freshness="UNKNOWN", gapBefore="UNKNOWN_SILENCE", duplicateOf=None))

    def run(self, *, cancellation=None, stop_after=None):
        cancel = cancellation or Cancellation()
        require(stop_after is None or type(stop_after) is int and stop_after > 0, "stopAfter")
        if self.builder.s["state"] == "INGESTING":
            with self.source.open("rb") as stream:
                stream.readline(8193)
                if self.builder.s["sourceOffset"]:
                    stream.seek(self.builder.s["sourceOffset"])
                ordinal = self.builder.s["count"]
                while raw := stream.readline(8193):
                    cancel.check()
                    self.builder.append(self._event(record(raw), ordinal), source_offset=stream.tell())
                    ordinal += 1
                    if stop_after is not None and ordinal >= stop_after:
                        raise InterruptedError("authored ingestion interruption")
        version = self.builder.finish(verify_source=lambda: source_pin(self.source), cancellation=cancel)
        return dict(artifact="BTL-DUKASCOPY-LOCAL-IMPORT-1", status="STRUCTURAL_PUBLICATION_ONLY",
            datasetId=self.meta["datasetId"], datasetVersion=version, source=dict(self.pin),
            symbol=self.symbol, requestedMonthUtc=self.month, acceptedRows=self.builder.s["count"],
            evidenceClass=self.meta["evidenceClass"], symbolIdentity="OPERATOR_LABEL_UNVERIFIED",
            coverage="UNVERIFIED", freshness="UNKNOWN", rights="UNVERIFIED",
            equalTimestampOrder="UNTRUSTED", executionEligibility="NOT_GRANTED")


def main():
    import argparse
    import json
    import os
    import tempfile
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "store", "symbol", "month", "report"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    report = Path(args.report)
    require(not report.exists(), "report", "OUTPUT_ALREADY_EXISTS")
    importer = DukascopyCsvIngestion(args.source, args.store, symbol=args.symbol, month=args.month, resume=args.resume)
    temporary = None
    try:
        result = importer.run()
        # Exclusive publication avoids replacing an earlier operator report.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=report.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(result, stream, indent=2)
        os.link(temporary, report)
        print(json.dumps(result))
    finally:
        importer.builder.store.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
