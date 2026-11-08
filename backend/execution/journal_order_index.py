"""Append-only, rebuildable order-to-event index for the tick journal."""

import json
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import identifier, require
from .contracts import text

PROJECTION_ARTIFACT = 'BTL-TICK-JOURNAL-ORDER-PROJECTION-1'


def references(events):
    """Return deterministic (order_id, sequence, event_id, kind) index rows."""
    rows = []
    for event in events:
        order_ids = set()
        order_id = event.get('orderId')
        if order_id is not None:
            identifier(order_id, 'orderId')
            order_ids.add(order_id)
        if event['kind'] == 'UNRESOLVED':
            affected = event['detail'].get('affectedOrderIds')
            require(type(affected) is list, 'journalIndex', 'CORRUPT_RECORD')
            for affected_id in affected:
                identifier(affected_id, 'orderId')
                order_ids.add(affected_id)
        for indexed_order_id in sorted(order_ids):
            rows.append((indexed_order_id, event['sequence'], event['eventId'], event['kind']))
    return rows


def _new_order(session_id, order_id, event):
    detail = event['detail']
    plan = deepcopy(detail['plan'])
    row = dict(id=order_id, **plan, entryPrice=None, entryTimeNs=None,
        entryFillRef=None, entryEvidence=None, exitSlices=[], exitTimeNs=None,
        exitPrice=None, exitFillRef=None, exitReason=None, gross='0',
        commission='0', netCashChange='0', status='PENDING',
        remaining=plan['quantity'], rMultiple=None,
        rReason='PREENTRY_R0_NOT_PINNED', mae=None, mfe=None,
        excursionReason='NOT_COMPUTED_IN_FUNCTIONAL_ALPHA')
    require(event['sessionId'] == session_id and row['id'] == order_id,
            'journalProjectionIdentity', 'CORRUPT_RECORD')
    return row


def _apply_order_event(row, event):
    kind = event['kind']
    detail = event['detail']
    if kind == 'ORDER_CANCELLED':
        require(row['status'] == 'PENDING', 'journalProjectionCancel', 'CORRUPT_RECORD')
        row['status'] = 'CANCELLED'
    elif kind == 'EXPIRED_NO_QUOTE':
        require(row['status'] == 'PENDING', 'journalProjectionExpiry', 'CORRUPT_RECORD')
        row['status'] = 'EXPIRED'
    elif kind == 'UNRESOLVED':
        require(row['status'] in ('PENDING', 'ACTIVE'),
                'journalProjectionUnresolved', 'CORRUPT_RECORD')
        row['status'] = 'UNRESOLVED'
    elif kind == 'ENTRY_FILL':
        evidence = detail['evidence']
        require(row['entryFillRef'] is None and detail['quantity'] == row['quantity'],
                'journalProjectionEntry', 'CORRUPT_RECORD')
        cost = Fraction(detail['commission'])
        delta = Fraction(detail['balanceDelta'])
        require(delta == -cost, 'journalProjectionEntryPosting', 'CORRUPT_RECORD')
        row['commission'] = text(Fraction(row['commission']) + cost)
        row['netCashChange'] = text(Fraction(row['netCashChange']) + delta)
        row.update(status='ACTIVE', entryPrice=detail['price'],
            entryTimeNs=evidence['timeNs'], entryFillRef=event['eventId'],
            entryEvidence=dict(groupId=evidence['groupId'],
                               eventIds=deepcopy(evidence['eventIds'])))
    elif kind == 'EXIT_FILL':
        evidence = detail['evidence']
        cost = Fraction(detail['commission'])
        delta = Fraction(detail['balanceDelta'])
        require(row['entryFillRef'] == detail['entryFillRef'] and
                Fraction(row['remaining']) - Fraction(detail['quantity']) ==
                Fraction(detail['remaining']) and delta == Fraction(detail['gross']) - cost,
                'journalProjectionExit', 'CORRUPT_RECORD')
        row['commission'] = text(Fraction(row['commission']) + cost)
        row['netCashChange'] = text(Fraction(row['netCashChange']) + delta)
        row['gross'] = text(Fraction(row['gross']) + Fraction(detail['gross']))
        row.update(remaining=detail['remaining'], exitTimeNs=evidence['timeNs'],
            exitPrice=detail['price'], exitFillRef=event['eventId'],
            exitReason=detail['reason'])
        row['exitSlices'].append(dict(groupId=evidence['groupId'],
            eventIds=deepcopy(evidence['eventIds']), timeNs=evidence['timeNs'],
            remaining=detail['remaining']))
        if Fraction(row['remaining']) == 0:
            require(row['entryTimeNs'] is not None,
                    'journalProjectionDuration', 'CORRUPT_RECORD')
            row.update(status='CLOSED', net=row['netCashChange'],
                       durationNs=str(int(evidence['timeNs']) - int(row['entryTimeNs'])))
    # EXIT_REQUESTED changes the active state, but its presentation is resolved
    # from the current Session state when the indexed page is read.
    return row


def _projection(session_id, order_id, row, event):
    value = dict(schemaVersion=1, formatVersion=1,
        artifact=PROJECTION_ARTIFACT, sessionId=session_id, orderId=order_id,
        lastSequence=event['sequence'], eventId=event['eventId'], order=row)
    value['contentHash'] = content_hash(value)
    return value


def verify_projection(raw, digest, *, session_id, order_id, status, sequence, event_id):
    value = json.loads(raw)
    require(canonical_bytes(value) == raw and content_hash(value) == digest and
            type(value) is dict and
            set(value) == {'schemaVersion', 'formatVersion', 'artifact', 'sessionId',
                           'orderId', 'lastSequence', 'eventId', 'order', 'contentHash'} and
            value['schemaVersion'] == 1 and value['formatVersion'] == 1 and
            value['artifact'] == PROJECTION_ARTIFACT and
            value['contentHash'] == content_hash(
                {key: item for key, item in value.items() if key != 'contentHash'}) and
            (value['sessionId'], value['orderId'], value['lastSequence'], value['eventId']) ==
            (session_id, order_id, sequence, event_id) and
            type(value['order']) is dict and
            (value['order'].get('id'), value['order'].get('status')) == (order_id, status),
            'journal