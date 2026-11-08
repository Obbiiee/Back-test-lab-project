"""Durable terminal-order archive for newly created observed Sessions."""
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require, digest, identifier
from ticks.contracts import keys
from .contracts import text

ARTIFACT = 'BTL-OBSERVED-TERMINAL-ORDER-ARCHIVE-1'
GENESIS = content_hash(dict(schemaVersion=1, artifact=ARTIFACT+'-GENESIS'))


def summary(count=0, gross='0', head=GENESIS):
    require(type(count) is int and count >= 0, 'archiveCount', 'CORRUPT_RECORD')
    require(type(gross) is str and Fraction(gross).denominator > 0, 'archiveGross', 'CORRUPT_RECORD')
    digest(head, 'digest')
    return dict(schemaVersion=1, artifact=ARTIFACT+'-SUMMARY', count=count,
                grossPosted=text(Fraction(gross)), headHash=head)


def append(previous, *, session_id, revision, order_id, order):
    require(previous.get('artifact') == ARTIFACT+'-SUMMARY', 'archiveSummary', 'CORRUPT_RECORD')
    identifier(order_id, 'identifier')
    require(type(session_id) is str and type(revision) is int and revision > 0,
            'archiveBinding', 'CORRUPT_RECORD')
    require(order.get('status') in ('CANCELLED', 'CLOSED', 'EXPIRED', 'UNRESOLVED'),
            'archiveTerminal', 'CORRUPT_RECORD')
    row = dict(schemaVersion=1, artifact=ARTIFACT, sessionId=session_id,
               sequence=previous['count'], finalizedRevision=revision,
               orderId=order_id, previousHash=previous['headHash'], order=deepcopy(order))
    row['orderHash'] = content_hash(dict(schemaVersion=1, artifact=ARTIFACT+'-ORDER', order=order))
    row['recordHash'] = content_hash(row)
    return row


def verify_record(row, *, expected_sequence=None, previous_hash=None):
    keys(row, 'schemaVersion artifact sessionId sequence finalizedRevision orderId previousHash order orderHash recordHash')
    require(row.get('schemaVersion') == 1 and row.get('artifact') == ARTIFACT,
            'archiveArtifact', 'CORRUPT_RECORD')
    require(type(row['sessionId']) is str and type(row['sequence']) is int and row['sequence'] >= 0
            and type(row['finalizedRevision']) is int and row['finalizedRevision'] > 0,
            'archiveBinding', 'CORRUPT_RECORD')
    identifier(row['orderId'], 'identifier')
    require(row['recordHash'] == content_hash({k: v for k, v in row.items() if k != 'recordHash'}),
            'archiveHash', 'CORRUPT_RECORD')
    require(row['orderHash'] == content_hash(dict(schemaVersion=1, artifact=ARTIFACT+'-ORDER', order=row['order'])),
            'archiveOrderHash', 'CORRUPT_RECORD')
    require(row['order']['status'] in ('CANCELLED', 'CLOSED', 'EXPIRED', 'UNRESOLVED'),
            'archiveTerminal', 'CORRUPT_RECORD')
    if expected_sequence is not None:
        require(row['sequence'] == expected_sequence, 'archiveSequence', 'CORRUPT_RECORD')
    if previous_hash is not None:
        require(row['previousHash'] == previous_hash, 'archiveChain', 'CORRUPT_RECORD')
    canonical_bytes(row)
    return row


def advance(previous, rows):
    count = previous['count']; gross = Fraction(previous['grossPosted']); head = previous['headHash']
    for row in rows:
        verify_record(row, expected_sequence=count, previous_hash=head)
        count += 1; head = row['recordHash']; gross += Fraction(row['order']['grossPosted'])
    return summary(count, text(gross), head)


def verify_complete(rows, expected_summary, *, collect=False):
    current = summary(); seen = set(); gross = Fraction(0); orders = {} if collect else None
    for row in rows:
        verify_record(row, expected_sequence=current['count'], previous_hash=current['headHash'])
        require(row['orderId'] not in seen, 'archiveDuplicateOrder', 'CORRUPT_RECORD')
        seen.add(row['orderId'])
        if collect: orders[row['orderId']] = deepcopy(row['order'])
        gross += Fraction(row['order']['grossPosted'])
        current = summary(current['count']+1, text(gross), row['recordHash'])
    require(current == expected_summary, 'archiveSummaryMismatch', 'CORRUPT_RECORD')
    return dict(orders=orders, summary=current, count=len(seen))
