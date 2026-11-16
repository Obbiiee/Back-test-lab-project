"""Durable, bounded aggregates for the Observed committed-event analytics API."""
import base64
import binascii
import json
import re
import zlib
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import canonical_bytes
from contracts.primitives import identifier, require, revision
from .analysis import RESEARCH_VERSION
from .contracts import text
from .observed_profile import MODEL

ARTIFACT='BTL-TICK-SESSION-ANALYTICS-PROJECTION-1'
# Stable public name used by the hosted Method Analytics adapter.
ANALYTICS_PROJECTION_ARTIFACT=ARTIFACT
WINDOW_ARTIFACT='BTL-TICK-SESSION-ANALYTICS-WINDOW-1'
MAX_PROJECTION_BYTES=65536
ANALYTICS_CURSOR_ARTIFACT='BTL-OBSERVED-ANALYTICS-CURSOR-1'


def encode_trade_cursor(session_id,session_revision,after_sequence,after_order_id):
    identifier(session_id,'sessionId');revision(session_revision)
    require(type(after_sequence) is int and 0<=after_sequence<=2**53-1,
            'cursor','INVALID_CURSOR')
    identifier(after_order_id,'afterOrderId')
    value=dict(schemaVersion=1,artifact=ANALYTICS_CURSOR_ARTIFACT,sessionId=session_id,
        revision=session_revision,afterSequence=after_sequence,afterOrderId=after_order_id)
    return base64.urlsafe_b64encode(canonical_bytes(value)).decode('ascii').rstrip('=')


def decode_trade_cursor(token,session_id):
    identifier(session_id,'sessionId')
    require(type(token) is str and 1<=len(token)<=2048 and
        re.fullmatch(r'[A-Za-z0-9_-]+',token) is not None,'cursor','INVALID_CURSOR')
    try:
        raw=base64.urlsafe_b64decode(token+'='*(-len(token)%4));value=json.loads(raw)
    except (ValueError,UnicodeError,binascii.Error):
        require(False,'cursor','INVALID_CURSOR')
    try:
        canonical=type(value) is dict and canonical_bytes(value)==raw
    except (TypeError,ValueError):
        canonical=False
    require(canonical and set(value)==
        {'schemaVersion','artifact','sessionId','revision','afterSequence','afterOrderId'} and
        value.get('schemaVersion')==1 and value.get('artifact')==ANALYTICS_CURSOR_ARTIFACT and
        value.get('sessionId')==session_id,'cursor','INVALID_CURSOR')
    revision(value.get('revision'),'revision')
    require(type(value.get('afterSequence')) is int and
        0<=value['afterSequence']<=2**53-1,'cursor','INVALID_CURSOR')
    identifier(value.get('afterOrderId'),'afterOrderId')
    return value['revision'],value['afterSequence'],value['afterOrderId']


def ratio(value):
    value=Fraction(value)
    return dict(numerator=str(value.numerator),denominator=str(value.denominator))


def completed_trade_row(order_id,order,history):
    """Convert a closed indexed order into the frozen Analytics trade row."""
    require(type(order) is dict and type(history) is dict and
        history.get('entryTimeNs') is not None and history.get('exitTimeNs') is not None and
        history.get('entryFillRef') is not None and history.get('exitFillRef') is not None,
        'analyticsOrderHistory','CORRUPT_RECORD')
    return dict(id=order_id,side=order['side'],status='CLOSED',quantity=order['quantity'],
        remaining='0',entry=order['entryPrice'],entryPrice=order['entryPrice'],
        entryTimeNs=history['entryTimeNs'],exitTimeNs=history['exitTimeNs'],
        entryFillRef=history['entryFillRef'],sl=order['sl'],tp=order['tp'],
        exitPrice=history['exitPrice'],exitFillRef=history['exitFillRef'],
        exitReason=history['exitReason'],gross=history['exactGross'],commission='0',
        net=order['grossPosted'],durationNs=str(int(history['exitTimeNs'])-int(history['entryTimeNs'])),
        mae=None,mfe=None,excursionReason='OBSERVED_EXCURSIONS_NOT_COMPUTED',
        rMultiple=None,rReason='PREENTRY_REVIEW_RISK_NOT_JOINED')


def _encode_windows(curve,annotations):
    wire=dict(schemaVersion=1,artifact=WINDOW_ARTIFACT,curve=curve[-256:],annotations=annotations[-512:])
    return base64.b64encode(zlib.compress(canonical_bytes(wire),6)).decode('ascii')


def _decode_windows(value):
    try:
        compressed=base64.b64decode(value,validate=True)
        decoder=zlib.decompressobj()
        raw=decoder.decompress(compressed,1_048_577)
        require(len(raw)<=1_048_576 and decoder.eof and not decoder.unconsumed_tail,
                'analyticsProjectionWindow','CORRUPT_RECORD')
        wire=json.loads(raw)
    except (ValueError, zlib.error, UnicodeError):
        require(False,'analyticsProjectionWindow','CORRUPT_RECORD')
    require(type(wire) is dict and wire.get('schemaVersion')==1 and wire.get('artifact')==WINDOW_ARTIFACT
        and type(wire.get('curve')) is list and len(wire['curve'])<=256
        and type(wire.get('annotations')) is list and len(wire['annotations'])<=512,
        'analyticsProjectionWindow','CORRUPT_RECORD')
    require(canonical_bytes(wire)==raw,'analyticsProjectionWindow','CORRUPT_RECORD')
    return wire['curve'],wire['annotations']


def initial_projection(state):
    value=dict(schemaVersion=1,artifact=ARTIFACT,sessionId=state['sessionId'],revision=state['revision'],
        eventHead=state['eventHash'],initialBalance=state['initialBalance'],tradeCount=0,wins=0,losses=0,
        breakeven=0,positive='0',negative='0',net='0',durationNs='0',currentStreakSign=0,
        currentStreakLength=0,maxWinStreak=0,maxLossStreak=0,unresolved=0,expired=0,cancelled=0,
        financialCount=0,balance=state['balance'],peak=state['balance'],maxDrawdown='0',
        maxDrawdownRate=ratio(Fraction()),windowBlob=_encode_windows([],[]))
    require(len(canonical_bytes(value))<=MAX_PROJECTION_BYTES,'analyticsProjection','REFUSED_PROJECTION_LIMIT')
    return value


def advance_projection(previous,events,state,order_changes):
    """Fold only the new command's events into an exact bounded summary."""
    value=deepcopy(previous)
    require(value.get('artifact')==ARTIFACT and value.get('sessionId')==state['sessionId'] and
        value.get('revision')+1==state['revision'],'analyticsProjectionHead','CORRUPT_RECORD')
    by_order={row['orderId']:row for row in order_changes}
    curve,annotations=_decode_windows(value['windowBlob'])
    balance=Fraction(value['balance']);peak=Fraction(value['peak'])
    max_drawdown=Fraction(value['maxDrawdown']);max_drawdown_rate=Fraction(
        int(value['maxDrawdownRate']['numerator']),int(value['maxDrawdownRate']['denominator']))
    for event in events:
        kind=event['kind'];detail=event['detail'];order_id=event['orderId']
        if kind in ('ORDER_CANCELLED','EXPIRED_NO_QUOTE'):
            value['cancelled' if kind=='ORDER_CANCELLED' else 'expired']+=1
        elif kind=='UNRESOLVED':
            value['unresolved']+=len(detail['affectedOrderIds'])
        if kind not in ('ENTRY_FILL','EXIT_FILL'):
            continue
        projection=by_order.get(order_id)
        require(projection is not None,'analyticsProjectionOrder','CORRUPT_RECORD')
        order=projection['order'];evidence=detail['evidence'];moment=evidence['timeNs']
        balance+=Fraction(detail['balanceDelta']);peak=max(peak,balance)
        drawdown=peak-balance;max_drawdown=max(max_drawdown,drawdown)
        if peak>0:max_drawdown_rate=max(max_drawdown_rate,drawdown/peak)
        value['financialCount']+=1
        curve.append(dict(sequence=event['sequence'],eventId=event['eventId'],orderId=order_id,
            timeNs=moment,balance=text(balance),drawdown=text(drawdown)))
        annotations.append(dict(eventId=event['eventId'],orderId=order_id,kind=kind,timeNs=moment,
            price=detail['price'],side=order['side'],reason=detail.get('reason'),
            chronologyLimited=evidence['chronologyLimited']))
        if kind=='EXIT_FILL' and detail['remaining']=='0':
            posted=Fraction(order['grossPosted']);trade_count=value['tradeCount']+1
            value['tradeCount']=trade_count;value['net']=text(Fraction(value['net'])+posted)
            value['durationNs']=str(int(value['durationNs'])+
                int(projection['history']['exitTimeNs'])-int(projection['history']['entryTimeNs']))
            if posted>0:
                value['wins']+=1;value['positive']=text(Fraction(value['positive'])+posted)
                if value['currentStreakSign']==1:value['currentStreakLength']+=1
                else:value['currentStreakSign']=1;value['currentStreakLength']=1
                value['maxWinStreak']=max(value['maxWinStreak'],value['currentStreakLength'])
            elif posted<0:
                value['losses']+=1;value['negative']=text(Fraction(value['negative'])-posted)
                if value['currentStreakSign']==-1:value['currentStreakLength']+=1
                else:value['currentStreakSign']=-1;value['currentStreakLength']=1
                value['maxLossStreak']=max(value['maxLossStreak'],value['currentStreakLength'])
            else:
                value['breakeven']+=1;value['currentStreakSign']=0;value['currentStreakLength']=0
    value.update(revision=state['revision'],eventHead=state['eventHash'],balance=text(balance),peak=text(peak),
        maxDrawdown=text(max_drawdown),maxDrawdownRate=ratio(max_drawdown_rate),
        windowBlob=_encode_windows(curve,annotations))
    require(balance==Fraction(state['balance']),'analyticsProjectionBalance','CORRUPT_RECORD')
    require(value['tradeCount']<=value['financialCount'],'analyticsProjectionCounts','CORRUPT_RECORD')
    require(len(canonical_bytes(value))<=MAX_PROJECTION_BYTES,'analyticsProjection','REFUSED_PROJECTION_LIMIT')
    return value


def analytics_view(value,state):
    """Produce the frozen aggregate portion of the Analytics page response."""
    trade_count=value['tradeCount'];wins=value['wins'];losses=value['losses']
    positive=Fraction(value['positive']);negative=Fraction(value['negative']);net=Fraction(value['net'])
    durations=int(value['durationNs'])
    win_rate=ratio(Fraction(wins,trade_count)) if trade_count else None
    average_win=ratio(positive/wins) if wins else None
    average_loss=ratio(-negative/losses) if losses else None
    expectancy=ratio(net/trade_count) if trade_count else None
    profit_factor=ratio(positive/negative) if negative else None
    curve,annotations=_decode_windows(value['windowBlob'])
    metrics=dict(tradeCount=trade_count,wins=wins,losses=losses,breakeven=value['breakeven'],
        winRate=win_rate,averageWin=average_win,averageLoss=average_loss,expectancy=expectancy,
        profitFactor=profit_factor,maxWinStreak=value['maxWinStreak'],maxLossStreak=value['maxLossStreak'],
        rEligible=0,rExcluded=trade_count,averageR=None,
        averageDurationNs=ratio(Fraction(durations,trade_count)) if trade_count else None,
        monteCarlo=dict(status='INSUFFICIENT_SAMPLE',eligible=0,exclusions=trade_count,minimum=30),
        closed=trade_count,profitFactorReason='NO_REALIZED_LOSSES' if profit_factor is None else None,
        realizedNetCompleted=text(net),unresolved=value['unresolved'],expired=value['expired'],
        cancelled=value['cancelled'],totalR=None,rAvailable=0,rReason='INCOMPLETE_R_COVERAGE',
        rBasis='IMMUTABLE_PREENTRY_CONFIRMED_RISK_REQUIRED',maxDrawdown=value['maxDrawdown'],
        maxDrawdownRate=value['maxDrawdownRate'],unrealizedExcluded=True,
        equityWindowStart=max(0,value['financialCount']-256))
    provenance=dict(sessionId=state['sessionId'],revision=state['revision'],engineVersion=state['engineVersion'],
        model=MODEL,datasetId=state['datasetId'],
        datasetVersion=state['datasetVersion'],profileHash=state['profileHash'],
        methodHash=state['policy']['definitionHash'],analysisVersion=RESEARCH_VERSION)
    account=dict(currency='USD',initialBalance=state['initialBalance'],balance=state['balance'],
        netCashChange=text(Fraction(state['balance'])-Fraction(state['initialBalance'])),
        realizedGross=state['realizedGross'],commission='0',unrealizedIndicative=None,equityIndicative=None)
    return dict(metrics=metrics,provenance=provenance,account=account,equity=curve,
        equityWindowStart=max(0,value['financialCount']-256),annotations=annotations,
        annotationWindowStart=max(0,value['financialCount']-512))
