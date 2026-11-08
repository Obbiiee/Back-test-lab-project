"""Durable exact per-Session completed-trade aggregate read model.

The append-only event ledger remains authoritative. This small projection is
advanced in the same transaction as committed events and supports exact Method
Analytics without folding every Session's event history on each request.
"""
import json
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require
from .analysis import ratio
from .contracts import text

ARTIFACT = 'BTL-TICK-SESSION-ANALYTICS-1'
FORMAT_VERSION = 1


def _empty_totals():
    return dict(tradeCount=0, wins=0, losses=0, breakeven=0, rEligible=0,
        totalNet='0', positive='0', negative='0', totalR='0', totalDuration='0',
        durationCount=0, maxWinStreak=0, maxLossStreak=0, winTail=0, lossTail=0)


def record(session_id, through_sequence, event_head, totals=None):
    value = dict(schemaVersion=1, formatVersion=FORMAT_VERSION, artifact=ARTIFACT,
        sessionId=session_id, throughSequence=through_sequence, eventHead=event_head,
        totals=deepcopy(totals) if totals is not None else _empty_totals())
    value['contentHash'] = content_hash(value)
    return value


def add_trade(value, order):
    """Return a new record with one canonical completed order incorporated."""
    totals = deepcopy(value['totals'])
    net = Fraction(order['net'])
    totals['tradeCount'] += 1
    totals['totalNet'] = text(Fraction(totals['totalNet']) + net)
    if net > 0:
        totals['wins'] += 1
        totals['positive'] = text(Fraction(totals['positive']) + net)
        totals['winTail'] += 1
        totals['lossTail'] = 0
        totals['maxWinStreak'] = max(totals['maxWinStreak'], totals['winTail'])
    elif net < 0:
        totals['losses'] += 1
        totals['negative'] = text(Fraction(totals['negative']) - net)
        totals['lossTail'] += 1
        totals['winTail'] = 0
        totals['maxLossStreak'] = max(totals['maxLossStreak'], totals['lossTail'])
    else:
        totals['breakeven'] += 1
        totals['winTail'] = totals['lossTail'] = 0
    if order.get('rMultiple') is not None:
        r = order['rMultiple']
        totals['totalR'] = text(Fraction(totals['totalR']) + Fraction(
            int(r['numerator']), int(r['denominator'])))
        totals['rEligible'] += 1
    if order.get('durationNs') is not None:
        totals['totalDuration'] = str(int(totals['totalDuration']) + int(order['durationNs']))
        totals['durationCount'] += 1
    return record(value['sessionId'], value['throughSequence'], value['eventHead'], totals)


def metrics(value):
    totals = value['totals']
    count, wins, losses, eligible = (totals['tradeCount'], totals['wins'],
                                     totals['losses'], totals['rEligible'])
    require(count == wins + losses + totals['breakeven'] and 0 <= eligible <= count,
            'sessionAnalyticsTotals', 'CORRUPT_RECORD')
    positive, negative = Fraction(totals['positive']), Fraction(totals['negative'])
    return dict(tradeCount=count, wins=wins, losses=losses,
        breakeven=totals['breakeven'],
        winRate=ratio(Fraction(wins, count)) if count else None,
        averageWin=ratio(positive / wins) if wins else None,
        averageLoss=ratio(-negative / losses) if losses else None,
        expectancy=ratio(Fraction(totals['totalNet']) / count) if count else None,
        profitFactor=ratio(positive / negative) if negative else None,
        maxWinStreak=totals['maxWinStreak'], maxLossStreak=totals['maxLossStreak'],
        rEligible=eligible, rExcluded=count - eligible,
        rReason=None if eligible else 'PREENTRY_R0_NOT_PINNED',
        averageR=ratio(Fraction(totals['totalR']) / eligible) if eligible else None,
        averageDurationNs=ratio(Fraction(int(totals['totalDuration']), totals['durationCount']))
            if totals['durationCount'] else None,
        monteCarlo=dict(status='INSUFFICIENT_SAMPLE' if eligible < 30 else 'NOT_COMPUTED',
                        eligible=eligible, exclusions=count - eligible, minimum=30))


def verify(raw, digest, *, session_id, through_sequence, event_head):
    value = json.loads(raw)
    require(canonical_bytes(value) == raw and content_hash(value) == digest and
        type(value) is dict and set(value) == {'schemaVersion', 'formatVersion', 'artifact',
            'sessionId', 'throughSequence', 'eventHead', 'totals', 'contentHash'} and
        value['schemaVersion'] == 1 and value['formatVersion'] == FORMAT_VERSION and
        value['artifact'] == ARTIFACT and value['contentHash'] == content_hash(
            {key: item for key, item in value.items() if key != 'contentHash'}) and
        (value['sessionId'], value['throughSequence'], value['eventHead']) ==
            (session_id, through_sequence, event_head),
        'sessionAnalyticsProjection', 'CORRUPT_RECORD')
    return value
