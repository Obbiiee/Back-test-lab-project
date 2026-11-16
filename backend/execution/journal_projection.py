"""Pure projection helpers for the bounded Observed Journal read model."""
from copy import deepcopy
from fractions import Fraction

from contracts.primitives import require
from .contracts import text


def journal_order_summary(order_id,status,order,history):
    """Convert one verified projection record to the frozen Journal row shape."""
    completed=status=='CLOSED'
    if completed:
        require(type(history) is dict and history.get('entryTimeNs') is not None and
            history.get('exitTimeNs') is not None and history.get('entryFillRef') is not None and
            history.get('exitFillRef') is not None,'journalProjectionHistory','CORRUPT_RECORD')
    row=dict(id=order_id,side=order['side'],status=status,quantity=order['quantity'],
        remaining=order['remaining'],entry=order['entry'],entryPrice=order['entryPrice'],
        entryTimeNs=history['entryTimeNs'] if completed else None,
        entryFillRef=history['entryFillRef'] if completed else None,sl=order['sl'],tp=order['tp'],
        exitRequested=order['exitRequest'] is not None,
        exitPrice=history['exitPrice'] if completed else None,
        exitFillRef=history['exitFillRef'] if completed else None,
        exitReason=history['exitReason'] if completed else None,
        gross=order['grossPosted'],commission='0',net=order['grossPosted'],
        netCashChange=order['grossPosted'],unrealizedIndicative=None,mae=None,mfe=None,
        excursionReason='OBSERVED_EXCURSIONS_NOT_COMPUTED')
    return row


def journal_projection_changes(events, state, archive_records=None, prior_history=None):
    """Build final per-order rows touched by a committed command.

    The immutable ledger remains authoritative. This helper only describes a
    replaceable read projection and is deterministic for synthetic tests.
    """
    archived = {row['orderId']: row['order'] for row in (archive_records or [])}
    touched = {}
    history = {}
    for event in events:
        kind = event['kind']
        affected = ([event['orderId']] if event['orderId'] is not None else [])
        if kind == 'UNRESOLVED':
            affected.extend(event['detail']['affectedOrderIds'])
        for order_id in affected:
            if order_id not in history:
                history[order_id] = deepcopy((prior_history or {}).get(order_id, dict(
                    entryTimeNs=None, entryFillRef=None, exitTimeNs=None, exitPrice=None,
                    exitFillRef=None, exitReason=None, exactGross='0', exitFills=0)))
            details = event['detail']
            if kind == 'ENTRY_FILL':
                history[order_id].update(entryTimeNs=details['evidence']['timeNs'],
                                          entryFillRef=event['eventId'])
            elif kind == 'EXIT_FILL':
                prior_gross = Fraction(history[order_id]['exactGross'])
                history[order_id].update(exitTimeNs=details['evidence']['timeNs'],
                    exitPrice=details['price'], exitFillRef=event['eventId'],
                    exitReason=details['reason'], exactGross=text(prior_gross+Fraction(details['grossExact'])),
                    exitFills=history[order_id]['exitFills']+1)
            prior = touched.get(order_id)
            if prior is None or prior['sequence'] < event['sequence']:
                touched[order_id] = event
    rows = []
    for order_id, event in touched.items():
        order = state['orders'].get(order_id, archived.get(order_id))
        require(type(order) is dict, 'journalProjectionOrder', 'CORRUPT_RECORD')
        status = order.get('status')
        require(status in ('PENDING','ACTIVE','CLOSED','CANCELLED','EXPIRED','UNRESOLVED'),
                'journalProjectionStatus', 'CORRUPT_RECORD')
        rows.append(dict(orderId=order_id, status=status, sequence=event['sequence'],
                         eventId=event['eventId'], kind=event['kind'], order=deepcopy(order),
                         history=history[order_id]))
    return sorted(rows, key=lambda row: (row['sequence'], row['orderId']))
