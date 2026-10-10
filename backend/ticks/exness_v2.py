"""Private local whole-second Exness-shaped CSV ingestion; no download/rights grant."""
import csv
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import heapq
from pathlib import Path
import re
import time

from contracts.canonical import decimal_text
from contracts.primitives import decimal, require
from .contracts import event_id
from .contracts_v2 import ZERO_VERSION
from .storage_v2 import DatasetBuilder, DiskTickProvider
from .provider import Cancellation

ADAPTER = "EXNESS-LOCAL-CSV-2"
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.([0-9]{3})Z")
FIELDS = ["Exness", "Symbol", "Timestamp", "Bid", "Ask"]


def source_pin(path):
    path = Path(path)
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1048576):
            sha.update(block)
    return dict(filename=path.name, bytes=path.stat().st_size, sha256=sha.hexdigest())


def parse_record(raw):
    require(len(raw) <= 8192, "record", "ARTIFACT_LIMIT")
    fields = next(csv.reader([raw.decode("utf-8-sig").rstrip("\r\n")], strict=True))
    require(len(fields) == 5, "csv", "MALFORMED_RECORD")
    return dict(zip(FIELDS, fields))


class ExnessIngestion:
    def __init__(self, source, folder, *, resume=False, packing=(256, 256, 1024), first_rows=None):
        require(first_rows is None or type(first_rows) is int and 1 <= first_rows <= 1000000000,
                'firstRows', 'ARTIFACT_LIMIT')
        self.first_rows = first_rows
        self.source = Path(source)
        self.pin = source_pin(source)
        with self.source.open("rb") as stream:
            require(next(csv.reader([stream.readline(8193).decode("utf-8-sig")], strict=True)) == FIELDS, "header", "SCHEMA_MISMATCH")
            first = parse_record(stream.readline(8193))
        require(first["Exness"] == "exness" and first["Symbol"], "feed", "IDENTITY_CONFLICT")
        self.symbol = first["Symbol"]
        self.source_id = "exness:csv:" + self.pin["sha256"][:24]
        self.meta = dict(datasetId="local:exness:"+self.pin["sha256"][:24], providerId="exness", feedId="local-unverified:"+self.symbol,
                         instrumentId="exness:"+self.symbol, providerSymbol=self.symbol, evidenceClass="PROVIDER_OBSERVATION",
                         adapterVersion=ADAPTER, validatorVersion="BTL-TICK-VALIDATOR-2",
                         ordering=dict(timestamps="VERIFIED_NONDECREASING", ties="UNTRUSTED", sequenceScope=None, sequenceEvidenceHash=None))
        if first_rows is not None:
            # Original member hash/ordinals remain the identity authority. Only
            # dataset selection differs; this is never a complete-source claim.
            self.meta['datasetId'] += ':first:'+str(first_rows)
        sources = [dict(sourceId=self.source_id, archiveHash=None, memberHash=self.pin["sha256"], originalName=self.source.name,
                        acquiredAtUtc=None, sourceUrl=None, timestampConvention="CSV UTC Z; observed whole-second values; subsecond ordering/provenance UNVERIFIED",
                        resolutionNs="1000000000", originalScalePolicy="PRESERVE_RAW_TEXT")]
        self.builder = DatasetBuilder(folder, self.meta, sources, self.pin, packing=packing, resume=resume)
        self.builder.store.db.execute("CREATE TABLE IF NOT EXISTS raw_records(hash BLOB PRIMARY KEY) WITHOUT ROWID")
        self.stats = self.builder.s.setdefault("audit", dict(parsedRows=0, rejectedRows=0, malformedTimestamps=0, malformedPrices=0,
            nonFinite=0, nonpositiveBid=0, nonpositiveAsk=0, crossedQuotes=0, exactDuplicateSourceRecords=0,
            firstTimestamp=None, lastTimestamp=None, spreadMin=None, spreadMax=None, spreadSum="0", gapsOver60s=0,
            largestGaps=[], fractional000=0, timestampReversals=0, equalTimestampAdjacent=0))

    def _event(self, row, ordinal):
        require(row["Exness"] == "exness" and row["Symbol"] == self.symbol, "symbol", "IDENTITY_CONFLICT")
        match = STAMP.fullmatch(row["Timestamp"])
        if match is None:
            self.stats["malformedTimestamps"] += 1
            require(False, "timestamp", "INVALID_TIMESTAMP")
        require(match[1] == "000", "source_resolution", "UNSUPPORTED_RESOLUTION")
        try:
            dt = datetime.fromisoformat(row["Timestamp"].replace("Z", "+00:00"))
        except ValueError:
            self.stats["malformedTimestamps"] += 1
            require(False, "timestamp", "INVALID_TIMESTAMP")
        delta = dt-EPOCH
        ns = (delta.days*86400+delta.seconds)*1000000000
        sides = []
        for side in ("Bid", "Ask"):
            try:
                value = Decimal(row[side])
            except Exception:
                self.stats["malformedPrices"] += 1
                require(False, "price", "MALFORMED_PRICE")
            if not value.is_finite():
                self.stats["nonFinite"] += 1
                require(False, "price", "MALFORMED_PRICE")
            if value <= 0:
                self.stats["nonpositive"+side] += 1
                require(False, "price", "MALFORMED_PRICE")
            sides.append(decimal_text(decimal(value, positive=True)))
        bid, ask = sides
        with localcontext() as context:
            context.prec = 4096
            spread = Decimal(ask)-Decimal(bid)
            spread_sum = Decimal(self.stats["spreadSum"])+spread
        self.stats["crossedQuotes"] += spread < 0
        self.stats["spreadSum"] = str(spread_sum)
        self.stats["spreadMin"] = str(spread if self.stats["spreadMin"] is None else min(spread, Decimal(self.stats["spreadMin"])))
        self.stats["spreadMax"] = str(spread if self.stats["spreadMax"] is None else max(spread, Decimal(self.stats["spreadMax"])))
        self.stats["fractional000"] += 1
        previous = self.builder.s["previousTime"]
        if previous is not None:
            difference = ns-previous
            self.stats["timestampReversals"] += difference < 0
            self.stats["equalTimestampAdjacent"] += difference == 0
            if difference > 60*1000000000:
                self.stats["gapsOver60s"] += 1
                heapq.heappush(self.stats["largestGaps"], [difference, self.stats["lastTimestamp"], row["Timestamp"]])
                if len(self.stats["largestGaps"]) > 15:
                    heapq.heappop(self.stats["largestGaps"])
        self.stats["firstTimestamp"] = self.stats["firstTimestamp"] or row["Timestamp"]
        self.stats["lastTimestamp"] = row["Timestamp"]
        return dict(schemaVersion=1, artifact="BTL-CANONICAL-TICK-1", datasetId=self.meta["datasetId"], datasetVersion=ZERO_VERSION,
                    providerId=self.meta["providerId"], feedId=self.meta["feedId"], instrumentId=self.meta["instrumentId"],
                    eventId=event_id(self.meta["providerId"], self.meta["feedId"], self.pin["sha256"], str(ordinal)),
                    timeNs=str(ns), resolutionNs="1000000000", bid=bid, ask=ask, rawOrdinal=str(ordinal), trustedSequence=None,
                    provenance=dict(sourceId=self.source_id, memberHash=self.pin["sha256"], originalTimestamp=row["Timestamp"]),
                    quality=dict(evidenceHash=None, quote="CROSSED" if spread < 0 else "VALID", freshness="UNKNOWN", gapBefore="UNKNOWN_SILENCE", duplicateOf=None))

    def run(self, *, cancellation=None, progress=None, stop_after=None):
        cancel = cancellation or Cancellation()
        start = time.perf_counter()
        if self.builder.s["state"] == "INGESTING":
            with self.source.open("rb") as stream:
                stream.readline(8193)
                if self.builder.s["sourceOffset"]:
                    stream.seek(self.builder.s["sourceOffset"])
                ordinal = self.builder.s["count"]
                while raw := stream.readline(8193):
                    cancel.check()
                    require(len(raw) <= 8192, "record", "ARTIFACT_LIMIT")
                    try:
                        row = parse_record(raw)
                        if self.first_rows is not None and ordinal >= self.first_rows and row['Timestamp'] != self.stats['lastTimestamp']:
                            break
                        self.stats["parsedRows"] += 1
                        e = self._event(row, ordinal)
                        raw_hash = hashlib.sha256(raw.rstrip(b"\r\n")).digest()
                        cursor = self.builder.store.db.execute("INSERT OR IGNORE INTO raw_records VALUES(?)", (raw_hash,))
                        self.stats["exactDuplicateSourceRecords"] += cursor.rowcount == 0
                        self.builder.append(e, source_offset=stream.tell())
                    except Exception:
                        self.stats["rejectedRows"] += 1
                        raise
                    ordinal += 1
                    if progress and ordinal % 100000 == 0:
                        progress(dict(rows=ordinal, elapsedSeconds=time.perf_counter()-start))
                    if stop_after is not None and ordinal >= stop_after:
                        # Test interruption: only already committed offset is resumable.
                        raise InterruptedError("authored ingestion interruption")
        version = self.builder.finish(verify_source=lambda: source_pin(self.source), cancellation=cancel)
        stats = deepcopy_stats(self.stats)
        stats.update(acceptedRows=self.builder.s["count"], sameTimestampGroups=self.builder.s["tieGroups"],
                     atomicGroups=self.builder.s["groups"], maxGroupSize=self.builder.s["maxGroup"],
                     spreadMean=str(Decimal(stats["spreadSum"])/self.builder.s["count"]),
                     source=self.pin, datasetId=self.meta["datasetId"], datasetVersion=version,
                     ingestionSeconds=time.perf_counter()-start, sourceResolutionNs="1000000000",
                     rights="UNKNOWN", provenance="UNVERIFIED", gapClassification="UNKNOWN_SILENCE",
                     duplicateDefinition="identical original CSV record bytes excluding line endings; global disk index")
        stats["stageTimings"] = dict(self.builder.timings, indexConstructionSeconds="NOT SEPARATELY MEASURABLE: streamed alongside chunk/partition construction")
        stats['sourceSelection'] = dict(kind='FULL_SOURCE' if self.first_rows is None else 'FIRST_COMPLETE_TIMESTAMP_GROUPS',
                                       requestedRows=self.first_rows)
        return stats


def deepcopy_stats(stats):
    import json
    return json.loads(json.dumps(stats))


def main():
    """Explicit private import; publication is structural, not market certification."""
    import argparse
    import json
    from .benchmark_v2 import memory
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--store', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--first-rows', type=int, help='Explicit progressive subset; complete the final timestamp group')
    args = parser.parse_args()
    started = time.perf_counter()
    importer = ExnessIngestion(args.source, args.store, resume=args.resume, first_rows=args.first_rows)
    previous = importer.builder.s['count']
    def progress(value):
        print(json.dumps(dict(stage='INGESTING', **value, memory=memory())), flush=True)
    try:
        result = importer.run(progress=progress)
        report = dict(status='STRUCTURAL_PUBLICATION_COMPLETE', ingestion=result,
                      resumedCommittedRows=previous, processedRowsThisInvocation=result['acceptedRows']-previous,
                      thisInvocationSeconds=time.perf_counter()-started, memory=memory(),
                      fullBenchmark='NOT_RUN', financialPrecision='NOT_CERTIFIED',
                      uncertainty='UNKNOWN coverage/freshness; UNTRUSTED equal-time sequence; private use only')
        Path(args.report).write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k != 'ingestion'}), flush=True)
        print(json.dumps(dict(datasetId=result['datasetId'], datasetVersion=result['datasetVersion'],
                              acceptedRows=result['acceptedRows'])), flush=True)
    finally:
        importer.builder.store.close()


if __name__ == '__main__':
    main()
