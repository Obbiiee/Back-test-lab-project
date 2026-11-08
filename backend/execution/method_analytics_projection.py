"""Combine fixed-size, revision-pinned Session aggregates for Method analytics."""
from fractions import Fraction

from contracts.primitives import require
from .contracts import text


def summarize(method_id, method_hash, units, included, excluded):
    """Build the frozen pooled-position response without loading trade rows."""
    common=dict(schemaVersion=1,artifact='BTL-METHOD-ANALYTICS-1',methodId=method_id,
        methodHash=method_hash,aggregation='POOLED_COMMITTED_COMPLETED_POSITIONS',
        balancesCombined=False,financialAuthority='COMMITTED_EVENTS_ONLY')
    if len(units)>1:
        return dict(**common,status='UNAVAILABLE',reason='INCOMPATIBLE_FINANCIAL_UNITS',
            includedSessions=[],excludedSessions=excluded+[
                dict(sessionId=item['session']['sessionId'],reason='MULTIPLE_FINANCIAL_UNITS')
                for item in included],metrics=None)
    totals=dict(tradeCount=0,wins=0,losses=0,breakeven=0,positive=Fraction(),
                negative=Fraction(),net=Fraction(),durationNs=0)
    sessions=[]
    for item in included:
        projection=item['projection']
        for key in ('tradeCount','wins','losses','breakeven'):
            require(type(projection.get(key)) is int and projection[key]>=0,
                'analyticsProjection','CORRUPT_RECORD')
            totals[key]+=projection[key]
        require(projection['wins']+projection['losses']+projection['breakeven']==
                projection['tradeCount'] and
                item['session'].get('tradeCount')==projection['tradeCount'],
                'analyticsProjection','CORRUPT_RECORD')
        for key in ('positive','negative','net'):
            totals[key]+=Fraction(projection[key])
        positive=Fraction(projection['positive']);negative=Fraction(projection['negative'])
        duration=int(projection['durationNs'])
        require(positive>=0 and negative>=0 and
                Fraction(projection['net'])==positive-negative and duration>=0,
                'analyticsProjection','CORRUPT_RECORD')
        totals['durationNs']+=duration
        sessions.append(item['session'])
    count=totals['tradeCount'];wins=totals['wins'];losses=totals['losses']
    def ratio(value):
        if value is None:return None
        value=Fraction(value)
        return dict(numerator=str(value.numerator),denominator=str(value.denominator))
    metrics=dict(tradeCount=count,wins=wins,losses=losses,breakeven=totals['breakeven'],
        winRate=ratio(Fraction(wins,count) if count else None),
        averageWin=ratio(totals['positive']/wins if wins else None),
        averageLoss=ratio(-totals['negative']/losses if losses else None),
        expectancy=ratio(totals['net']/count if count else None),
        profitFactor=ratio(totals['positive']/totals['negative']
                           if totals['negative'] else None),
        rEligible=0,rExcluded=count,rReason='PREENTRY_R0_NOT_PINNED',averageR=None,
        averageDurationNs=ratio(Fraction(totals['durationNs'],count) if count else None),
        monteCarlo=dict(status='INSUFFICIENT_SAMPLE',eligible=0,exclusions=count,minimum=30))
    unit=next(iter(units),None)
    return dict(**common,status='COMPLETE',accountCurrency=unit[2] if unit else None,
        completedTradeNet=text(totals['net']),includedSessions=sessions,
        excludedSessions=excluded,metrics=metrics)
