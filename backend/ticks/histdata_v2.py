"""Private intake of existing converted HistData UTC CSV/GZIP observations.

Not provider certification or hosted execution eligibility. Never sort, dedup,
assert quote freshness, invent coverage, or convert an already UTC timestamp.
"""
import csv
from datetime import datetime, timezone
import gzip
import hashlib
from pathlib import Path
import re
import time

from contracts.canonical import decimal_text
from contracts.primitives import ContractError, decimal, require
from market_data.instruments import instrument
from .contracts import event_id
from .contracts_v2 import ZERO_VERSION
from .provider import Cancellation
from .storage_v2 import DatasetBuilder

ADAPTER = 'HISTDATA-CONVERTED-UTC-CSV-1'
FIELDS = ['timestamp_utc', 'bid', 'ask']
STAMP = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z')
PRICE = re.compile(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?')
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def source_pin(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'source', 'SOURCE_PATH_REFUSED')
    before = path.stat()
    require(before.st_size <= 2147483648, 'compressedSize', 'ARTIFACT_LIMIT')
    compressed = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1048576):
            compressed.update(block)
    member = hashlib.sha256(); total = 0
    with gzip.open(path, 'rb') as stream:
        while block := stream.read(1048576):
            total += len(block)
            require(total <= 17179869184, 'uncompressedSize', 'ARTIFACT_LIMIT')
            member.update(block)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'source', 'SOURCE_CHANGED')
    return dict(filename=path.name, bytes=before.st_size, sha256=compressed.hexdigest(),
                memberSha256=member.hexdigest(), uncompressedBytes=total)


def parse_record(raw):
    require(type(raw) is bytes and len(raw) <= 8192, 'record', 'ARTIFACT_LIMIT')
    try:
        fields = next(csv.reader([raw.decode('ascii').rstrip('\r\n')], strict=True))
    except (UnicodeError, csv.Error, StopIteration):
        require(False, 'record', 'MALFORMED_RECORD')
    require(len(fields) == 3 and STAMP.fullmatch(fields[0]), 'record', 'SCHEMA_MISMATCH')
    try:
        stamp = datetime.fromisoformat(fields[0].replace('Z', '+00:00'))
    except ValueError:
        require(False, 'timestamp', 'INVALID_TIMESTAMP')
    require(stamp >= EPOCH, 'timestamp', 'INVALID_TIMESTAMP')
    prices = []
    for value in fields[1:]:
        require(len(value) <= 128 and PRICE.fullmatch(value), 'price', 'MALFORMED_PRICE')
        prices.append(decimal_text(decimal(value, positive=True)))
    bid, ask = prices
    require(decimal(bid) <= decimal(ask), 'quote', 'CROSSED_QUOTE')
    delta = stamp-EPOCH
    return fields[0], str((delta.days*86400+delta.seconds)*1000000000 + delta.microseconds*1000), bid, ask


class HistDataIngestion:
    def __init__(self, source, folder, symbol, *, first_rows=100000, resume=False, packing=(256, 256, 1024)):
        instrument(symbol)
        require(first_rows is None or type(first_rows) is int and 1 <= first_rows <= 1000000,
                'firstRows', 'ARTIFACT_LIMIT')
        self.source = Path(source)
        require(re.fullmatch(re.escape(symbol)+r'_[0-9]{4}-[0-9]{2}\.csv\.gz', self.source.name),
                'filenameSymbol', 'IDENTITY_CONFLICT')
        require(not self.source.resolve().is_relative_to(Path(folder).resolve()), 'store', 'SOURCE_PATH_REFUSED')
        self.pin = source_pin(self.source)
        with gzip.open(self.source, 'rb') as stream:
            require(stream.readline(8193).decode('utf-8-sig').rstrip('\r\n').split(',') == FIELDS,
                    'header', 'SCHEMA_MISMATCH')
            parse_record(stream.readline(8193))
        self.first_rows = first_rows
        self.source_id = 'histdata:converted:' + self.pin['memberSha256'][:24]
        dataset = 'local:histdata:' + symbol + ':' + self.pin['sha256'][:24]
        if first_rows is not None:
            dataset += ':first:' + str(first_rows)
        self.meta = dict(datasetId=dataset, providerId='histdata', feedId='local-unverified:'+symbol,
            instrumentId='histdata:'+symbol, providerSymbol=symbol, evidenceClass='PROVIDER_OBSERVATION',
            adapterVersion=ADAPTER, validatorVersion='BTL-TICK-VALIDATOR-2',
            ordering=dict(timestamps='VERIFIED_NONDECREASING', ties='UNTRUSTED',
                          sequenceScope=None, sequenceEvidenceHash=None))
        sources = [dict(sourceId=self.source_id, archiveHash=self.pin['sha256'],
            memberHash=self.pin['memberSha256'], originalName=self.source.name[:-3],
            acquiredAtUtc=None, sourceUrl=None,
            timestampConvention='Converted CSV UTC Z milliseconds; original provider timestamp/provenance UNVERIFIED',
            resolutionNs='1000000', originalScalePolicy='PRESERVE_RAW_TEXT')]
        self.builder = DatasetBuilder(folder, self.meta, sources, self.pin, packing=packing, resume=resume)
        self.audit = self.builder.s.setdefault('histdataAudit', dict(rows=0, adjacentDuplicates=0,
            previousRecordHash=None, firstTimestamp=None, lastTimestamp=None))

    def close(self):
        self.builder.store.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def event(self, row, ordinal):
        stamp, ns, bid, ask = row
        return dict(schemaVersion=1, artifact='BTL-CANONICAL-TICK-1', datasetId=self.meta['datasetId'],
            datasetVersion=ZERO_VERSION, providerId=self.meta['providerId'], feedId=self.meta['feedId'],
            instrumentId=self.meta['instrumentId'],
            eventId=event_id(self.meta['providerId'], self.meta['feedId'], self.pin['memberSha256'], str(ordinal)),
            timeNs=ns, resolutionNs='1000000', bid=bid, ask=ask, rawOrdinal=str(ordinal), trustedSequence=None,
            provenance=dict(sourceId=self.source_id, memberHash=self.pin['memberSha256'], originalTimestamp=stamp),
            quality=dict(evidenceHash=None, quote='VALID', freshness='UNKNOWN', gapBefore='UNKNOWN_SILENCE', duplicateOf=None))

    def run(self, *, cancellation=None, progress=None, stop_after=None):
        cancel = cancellation or Cancellation(); started = time.perf_counter()
        if self.builder.s['state'] == 'INGESTING':
            with gzip.open(self.source, 'rb') as stream:
                stream.readline(8193)
                if self.builder.s['sourceOffset']:
                    stream.seek(self.builder.s['sourceOffset'])
                ordinal = self.builder.s['count']
                while raw := stream.readline(8193):
                    cancel.check()
                    row = parse_record(raw)
                    if self.first_rows is not None and ordinal >= self.first_rows and row[0] != self.audit['lastTimestamp']:
                        break
                    hashed = hashlib.sha256(raw.rstrip(b'\r\n')).hexdigest()
                    self.audit['adjacentDuplicates'] += hashed == self.audit['previousRecordHash']
                    self.audit['previousRecordHash'] = hashed
                    self.audit['firstTimestamp'] = self.audit['firstTimestamp'] or row[0]
                    self.audit['lastTimestamp'] = row[0]; self.audit['rows'] += 1
                    # Builder rejects decreasing timestamps and keeps equal-time groups atomic.
                    self.builder.append(self.event(row, ordinal), source_offset=stream.tell())
                    ordinal += 1
                    if progress and ordinal % 10000 == 0:
                        progress(dict(rows=ordinal, elapsedSeconds=time.perf_counter()-started))
                    if stop_after is not None and ordinal >= stop_after:
                        raise InterruptedError('authored ingestion interruption')
        version = self.builder.finish(verify_source=lambda: source_pin(self.source), cancellation=cancel)
        return dict(status='STRUCTURAL_PUBLICATION_ONLY_NOT_EXECUTION_ACCEPTANCE',
            datasetId=self.meta['datasetId'], datasetVersion=version, acceptedRows=self.builder.s['count'],
            source=self.pin, sourceSelection=dict(kind='FULL_FILE' if self.first_rows is None else 'FIRST_COMPLETE_TIMESTAMP_GROUPS',
                                                 requestedRows=self.first_rows),
            firstTimestamp=self.audit['firstTimestamp'], lastTimestamp=self.audit['lastTimestamp'],
            adjacentDuplicates=self.audit['adjacentDuplicates'], sameTimestampGroups=self.builder.s['tieGroups'],
            sourceSequenceVerified=False, freshness='UNKNOWN', coverage='UNKNOWN', rights='UNKNOWN',
            originalProviderProvenance='UNVERIFIED', elapsedSeconds=time.perf_counter()-started)


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True); parser.add_argument('--store', required=True)
    parser.add_argument('--symbol', required=True); parser.add_argument('--report', required=True)
    parser.add_argument('--first-rows', type=int, default=100000)
    parser.add_argument('--full-file', action='store_true'); parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    # Never overwrite an earlier diagnostic; original datasets remain read-only.
    with Path(args.report).open('x') as report:
        try:
            with HistDataIngestion(args.source, args.store, args.symbol,
                                  first_rows=None if args.full_file else args.first_rows, resume=args.resume) as intake:
                result = intake.run(progress=lambda value: print(json.dumps(value), flush=True))
        except (ContractError, ValueError, EOFError, OSError) as error:
            refusal = dict(status='REFUSED_NOT_PUBLISHED', code=getattr(error, 'code', type(error).__name__))
            json.dump(refusal, report, indent=2)
            print(json.dumps(refusal), flush=True)
            raise SystemExit(1) from None
        json.dump(result, report, indent=2)
    print(json.dumps({k: result[k] for k in ('status', 'datasetId', 'datasetVersion', 'acceptedRows')}))


if __name__ == '__main__':
    main()
