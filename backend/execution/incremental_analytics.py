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

ARTIFACT_V1 = 'BTL-TICK-SESSION-ANALYTICS-1'
ARTIFACT = 'BTL-TICK-SESSION-ANALYTICS-2'
FORMAT_VERSION = 2


def _empty_totals():
    return dict(tradeCount=0, wins=0, losses=0, breakeven=0, rEligible=0,
        totalNet='0', positive='0', negative='0', totalR='0/1', totalDuration='0',
        durationCount=0, maxWinStreak=0, maxLossStreak=0, winTail=0, lossTail=0)


def record(session_id, through_sequence, event_head, totals=None):
    totals=deepcopy(totals) if totals is not None else _empty_totals()
    # Version 1 stored a decimal approximation slot that cannot represent all
    # exact rational R values. Upgrade legacy totals without rounding them.
    version=1 if type(totals.get('totalR')) is str and '/' not in totals['totalR'] else 2
    totals['totalR']=_encode_total_r(_decode_total_r(totals['totalR'],version))
    value = dict(schemaVersion=1, formatVersion=FORMAT_VERSION, artifact=ARTIFACT,
        sessionId=session_id, throughSequence=through_sequence, eventHead=event_head,
        totals=totals)
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
    total_r=_decode_total_r(totals['totalR'],value.get('formatVersion',1))
    if order.get('rMultiple') is not None:
        r = order['rMultiple']
        total_r += Fraction(int(r['numerator']), int(r['denominator']))
        totals['rEligible'] += 1
    totals['totalR']=_encode_total_r(total_r)
    if order.get('durationNs') is not None:
        totals['totalDuration'] = str(int(totals['totalDuration']) + int(order['durationNs']))
        totals['durationCount'] += 1
    return record(value['sessionId'], value['throughSequence'], value['eventHead'], totals)


def metrics(value):
    totals = value['totals']
    _validate_totals(totals,value.get('formatVersion',1))
    count, wins, losses, eligible = (totals['tradeCount'], totals['wins'],
                                     totals['losses'], totals['rEligible'])
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
        averageR=ratio(_decode_total_r(totals['totalR'],value.get('formatVersion',1)) / eligible) if eligible else None,
        averageDurationNs=ratio(Fraction(int(totals['totalDuration']), totals['durationCount']))
            if totals['durationCount'] else None,
        monteCarlo=dict(status='INSUFFICIENT_SAMPLE' if eligible < 30 else 'NOT_COMPUTED',
                        eligible=eligible, exclusions=count - eligible, minimum=30))


def _encode_total_r(value):
    value=Fraction(value)
    return f'{value.numerator}/{value.denominator}'


def _decode_total_r(raw,version):
    require(type(raw) is str,'sessionAnalyticsTotals','CORRUPT_RECORD')
    try:
        if version==1:
            result=Fraction(raw)
            require(text(result)==raw,'sessionAnalyticsTotals','CORRUPT_RECORD')
            return result
        require(version==2 and '/' in raw,'sessionAnalyticsTotals','CORRUPT_RECORD')
        numerator,denominator=raw.split('/',1)
        require(numerator.lstrip('-').isdigit() and denominator.isdigit() and
                denominator!='0','sessionAnalyticsTotals','CORRUPT_RECORD')
        result=Fraction(int(numerator),int(denominator))
        require(_encode_total_r(result)==raw,'sessionAnalyticsTotals','CORRUPT_RECORD')
        return result
    except (TypeError,ValueError,ZeroDivisionError,OverflowError):
        require(False,'sessionAnalyticsTotals','CORRUPT_RECORD')


def _validate_totals(totals,version):
    fields = {'tradeCount', 'wins', 'losses', 'breakeven', 'rEligible', 'totalNet',
        'positive', 'negative', 'totalR', 'totalDuration', 'durationCount',
        'maxWinStreak', 'maxLossStreak', 'winTail', 'lossTail'}
    require(type(totals) is dict and set(totals) == fields,
            'sessionAnalyticsTotals', 'CORRUPT_RECORD')
    counters = fields - {'totalNet', 'positive', 'negative', 'totalR', 'totalDuration'}
    require(all(type(totals[name]) is int and totals[name] >= 0 for name in counters),
            'sessionAnalyticsTotals', 'CORRUPT_RECORD')
    count, wins, losses = totals['tradeCount'], totals['wins'], totals['losses']
    require(count == wins + losses + totals['breakeven'] and
            totals['rEligible'] <= count and totals['durationCount'] <= count and
            totals['maxWinStreak'] <= wins and totals['maxLossStreak'] <= losses and
            totals['winTail'] <= totals['maxWinStreak'] and
            totals['lossTail'] <= totals['maxLossStreak'] and
            not (totals['winTail'] and totals['lossTail']),
            'sessionAnalyticsTotals', 'CORRUPT_RECORD')
    try:
        amounts = {name: Fraction(totals[name])
                   for name in ('totalNet', 'positive', 'negative')}
        amounts['totalR']=_decode_total_r(totals['totalR'],version)
        duration = totals['totalDuration']
        duration_value = int(duration)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        require(False, 'sessionAnalyticsTotals', 'CORRUPT_RECORD')
    require(all(type(totals[name]) is str and text(amounts[name]) == totals[name]
                for name in ('totalNet', 'positive', 'negative')) and
            amounts['positive'] >= 0 and amounts['negative'] >= 0 and
            amounts['totalNet'] == amounts['positive'] - amounts['negative'] and
            type(duration) is str and duration_value >= 0 and str(duration_value) == duration and
            (totals['durationCount'] > 0 or duration_value == 0),
            'sessionAnalyticsTotals', 'CORRUPT_RECORD')


def verify(raw, digest, *, session_id, through_sequence, event_head):
    value = json.loads(raw)
    version=value.get('formatVersion') if type(value) is dict else None
    artifact=ARTIFACT if version==FORMAT_VERSION else ARTIFACT_V1
    require(canonical_bytes(value) == raw and content_hash(value) == digest and
        type(value) is dict and set(value) == {'schemaVersion', 'formatVersion', 'artifact',
            'sessionId', 'throughSequence', 'eventHead', 'totals', 'contentHash'} and
        value['schemaVersion'] == 1 and version in (1,FORMAT_VERSION) and
        value['artifact'] == artifact and value['contentHash'] == content_hash(
            {key: item for key, item in value.items() if key != 'contentHash'}) and
        (value['sessionId'], value['throughSequence'], value['eventHead']) ==
            (session_id, through_sequence, event_head),
        'sessionAnalyticsProjection', 'CORRUPT_RECORD')
    _validate_totals(value['totals'],version)
    return value
