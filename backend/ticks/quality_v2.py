"""Private converted-HistData quality reports, NEVER dataset/fill admission.

Reuses the strict existing parser. Source order/rows remain untouched; reports
are offline/controller-only and must not be projected into a replay consumer.
"""
import gzip
import hashlib
import json
from pathlib import Path
import re
import zlib

from contracts.primitives import ContractError, digest, require
from market_data.instruments import instrument
from .histdata_v2 import parse_record, source_pin
from .provider import Cancellation


def _stat(path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns


def audit_file(source, symbol, *, expected_member_sha256=None,
               max_rows=20000000, cancellation=None):
    """Bounded-memory full-file numeric/order diagnostic; no partial success.

max_rows bounds work; source_pin has existing 2GiB compressed/16GiB member
bounds. Cancellation is checked before/after whole bounded pin phases and per
record; pinning itself is not interruptible by this cancellation capability.
No event-id uniqueness, provider precision, gaps/freshness, market coverage or
source permission certification is performed. Empty/malformed data refuses.
"""
    instrument(symbol)
    source = Path(source)
    require(re.fullmatch(re.escape(symbol)+r'_[0-9]{4}-[0-9]{2}\.csv\.gz', source.name),
            'filenameSymbol', 'IDENTITY_CONFLICT')
    require(type(max_rows) is int and 1 <= max_rows <= 100000000,
            'maxRows', 'ARTIFACT_LIMIT')
    if expected_member_sha256 is not None:
        digest(expected_member_sha256, 'memberHash')
    cancel = cancellation or Cancellation()
    cancel.check(); before = _stat(source); pin = source_pin(source); cancel.check()
    if expected_member_sha256 is not None:
        require(pin['memberSha256'] == expected_member_sha256, 'source', 'SOURCE_CHANGED')
    rows = valid = invalid = reversals = ties = ambiguous = oversized = 0
    group_size = 0; group_ambiguous = False
    previous_ns = previous_quote = None
    first = last = None; largest_group = 0; max_silence = 0
    examples = []; codes = {}; observed = hashlib.sha256(); observed_bytes = 0
    with gzip.open(source, 'rb') as stream:
        header = stream.readline(8193); observed.update(header); observed_bytes += len(header)
        require(header.rstrip(b'\r\n') == b'timestamp_utc,bid,ask',
                'header', 'SCHEMA_MISMATCH')
        while raw := stream.readline(8193):
            cancel.check()
            require(len(raw) <= 8192, 'record', 'ARTIFACT_LIMIT')
            observed.update(raw); observed_bytes += len(raw)
            require(observed_bytes <= pin['uncompressedBytes'], 'source', 'SOURCE_CHANGED')
            rows += 1
            require(rows <= max_rows, 'rows', 'QUALITY_ROW_LIMIT')
            try:
                stamp, ns, bid, ask = parse_record(raw)
            except ContractError as error:
                invalid += 1; codes[error.code] = codes.get(error.code, 0)+1
                if len(examples) < 8:
                    examples.append(dict(rawOrdinal=str(rows-1), code=error.code))
                continue
            valid += 1; now = int(ns); quote = (bid, ask)
            if first is None:
                first = stamp
            last = stamp
            if previous_ns is not None:
                if now < previous_ns:
                    reversals += 1
                    if len(examples) < 8:
                        examples.append(dict(rawOrdinal=str(rows-1), code='ORDER_REVERSAL'))
                max_silence = max(max_silence, now-previous_ns)
            if now == previous_ns:
                ties += 1; group_size += 1
                if quote != previous_quote and not group_ambiguous:
                    ambiguous += 1; group_ambiguous = True
            else:
                group_size = 1; group_ambiguous = False
            if group_size == 1025:
                oversized += 1
            largest_group = max(largest_group, group_size)
            previous_ns, previous_quote = now, quote
    require(observed.hexdigest() == pin['memberSha256']
            and observed_bytes == pin['uncompressedBytes'], 'source', 'SOURCE_CHANGED')
    cancel.check(); final_pin = source_pin(source); cancel.check()
    require(pin == final_pin and before == _stat(source), 'source', 'SOURCE_CHANGED')
    require(rows > 0, 'rows', 'EMPTY_DATASET')
    refused = bool(invalid or reversals or oversized)
    return dict(schemaVersion=1, artifact='BTL-PRIVATE-HISTDATA-QUALITY-1',
                status='QUALITY_REFUSED' if refused else 'NUMERIC_ORDER_PASS_NOT_ACCEPTANCE',
                symbol=symbol, source=pin, completedSourceRead=True,
                rows=rows, validNumericRows=valid, invalidRows=invalid,
                invalidCodes=codes, orderReversals=reversals,
                equalTimeValidPairs=ties, ambiguousTimestampGroups=ambiguous,
                oversizedTimestampGroups=oversized, largestTimestampGroup=largest_group,
                maxObservedSilenceNs=str(max_silence), firstTimestamp=first, lastTimestamp=last,
                examples=examples, sourceStable=True, rawOrdinalIsTrustedSequence=False,
                canonicalDatasetPublished=False, financialAdmission=False,
                coverage='UNKNOWN', freshness='UNKNOWN', rights='UNKNOWN',
                fullSemanticAcceptance=False)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--symbol', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--expected-member-sha256')
    parser.add_argument('--max-rows', type=int, default=20000000)
    args = parser.parse_args()
    # Exclusive report creation: never overwrite a prior result/source.
    with Path(args.report).open('x') as report:
        try:
            result = audit_file(args.source, args.symbol,
                                expected_member_sha256=args.expected_member_sha256,
                                max_rows=args.max_rows)
        except (ValueError, OSError, EOFError, zlib.error) as error:
            result = dict(status='QUALITY_SCAN_INCOMPLETE',
                          code=getattr(error, 'code', type(error).__name__),
                          financialAdmission=False, canonicalDatasetPublished=False)
            json.dump(result, report, indent=2)
            print(json.dumps(result)); raise SystemExit(1) from None
        json.dump(result, report, indent=2)
        # A completed scan with bad rows is still a refusal, not successful data.
        print(json.dumps({k: result[k] for k in ('status', 'rows', 'invalidRows', 'orderReversals')}))
        if result['status'] == 'QUALITY_REFUSED':
            raise SystemExit(2)


if __name__ == '__main__':
    main()
