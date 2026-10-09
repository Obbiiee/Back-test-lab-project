"""Read-only projection of committed events. Never executes or settles orders.

Exact cash postings reconcile against the durable account. Ratios remain exact
rationals; chart rendering may round only its own presentation. No tick/provider
capability or guessed initial risk enters this projection.
"""
from collections import deque
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import content_hash
from contracts.primitives import require
from .contracts import text, validate_state

MAX_ANALYSIS_EVENTS = 4096
ANALYSIS_VERSION = 'BTL-COMMITTED-ANALYSIS-1'


def ratio(value):
    if value is None:
        return None
    value = Fraction(value)
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def metrics(completed):
    nets = [Fraction(row['net']) for row in completed]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n < 0]
    positive, negative = sum(wins, Fraction()), -sum(losses, Fraction())
    streak_win = streak_loss = maximum_win = maximum_loss = 0
    for net in nets:
        streak_win = streak_win + 1 if net > 0 else 0
        streak_loss = streak_loss + 1 if net < 0 else 0
        maximum_win, maximum_loss = max(maximum_win, streak_win), max(maximum_loss, streak_loss)
    return dict(tradeCount=len(nets), wins=len(wins), losses=len(losses), breakeven=sum(n == 0 for n in nets),
        winRate=ratio(Fraction(len(wins), len(nets))) if nets else None,
        averageWin=ratio(positive / len(wins)) if wins else None,
        averageLoss=ratio(-negative / len(losses)) if losses else None,
        expectancy=ratio(sum(nets, Fraction()) / len(nets)) if nets else None,
        profitFactor=ratio(positive / negative) if negative else None,
        maxWinStreak=maximum_win, maxLossStreak=maximum_loss,
        rEligible=0, rExcluded=len(nets), rReason='PREENTRY_R0_NOT_PINNED',
        monteCarlo=dict(status='INSUFFICIENT_SAMPLE', eligible=0, exclusions=len(nets), minimum=30))


def project(state, events, quote):
    validate_state(state)
    provenance = dict(sessionId=state['sessionId'], revision=state['revision'], datasetId=state['datasetId'],
        datasetVersion=state['datasetVersion'], engineVersion=state['engineVersion'], profileHash=state['profileHash'],
        methodHash=state['policy']['definitionHash'], eventHead=state['eventHash'], analysisVersion=ANALYSIS_VERSION,
        model='SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION')
    if state['nextEventIndex'] > MAX_ANALYSIS_EVENTS:
        return dict(status='UNAVAILABLE', reason='REFUSED_ANALYSIS_LIMIT', maximumEvents=MAX_ANALYSIS_EVENTS, provenance=provenance)
    require(state['parent'] is None, 'analysisLineage', 'REFUSED_UNSUPPORTED_LINEAGE')
    previous = content_hash(dict(schemaVersion=1, artifact='BTL-TICK-EXECUTION-SEED-1', sessionId=state['sessionId'],
        datasetId=state['datasetId'], datasetVersion=state['datasetVersion'], profile=state['profile'],
        policy=state['policy'], initialBalance=state['initialBalance']))
    balance = peak = Fraction(state['initialBalance'])
    gross = commission = maximum_drawdown = maximum_percent = Fraction()
    rows, completed = {}, []
    equity, annotations = deque(maxlen=256), deque(maxlen=512)
    count = financial_count = 0
    for event in events:
        require(event['sequence'] == count and event['previousHash'] == previous and
            event['eventId'] == content_hash({k:v for k,v in event.items() if k != 'eventId'}) and
            (event['sessionId'],event['datasetId'],event['datasetVersion'],event['profileHash'],event['methodHash'],event['engineVersion']) ==
            (state['sessionId'],state['datasetId'],state['datasetVersion'],state['profileHash'],state['policy']['definitionHash'],state['engineVersion']),
            'eventChain', 'CORRUPT_RECORD')
        previous = event['eventId']; count += 1
        kind, order_id, detail = event['kind'], event['orderId'], event['detail']
        if kind == 'ORDER_ACCEPTED':
            require(order_id in state['orders'] and order_id not in rows, 'acceptedOrder', 'CORRUPT_RECORD')
            row = dict(id=order_id, **deepcopy(detail['plan']), entryPrice=None, entryTimeNs=None, entryFillRef=None,
                exitTimeNs=None, exitPrice=None, exitFillRef=None, exitReason=None, gross='0', commission='0', netCashChange='0',
                status='PENDING', remaining=detail['plan']['quantity'], rMultiple=None, rReason='PREENTRY_R0_NOT_PINNED',
                mae=None, mfe=None, excursionReason='NOT_COMPUTED_IN_FUNCTIONAL_ALPHA')
            rows[order_id] = row
        elif kind in ('ORDER_CANCELLED', 'EXPIRED_NO_QUOTE'):
            require(order_id in rows, 'order', 'CORRUPT_RECORD')
            rows[order_id]['status'] = 'CANCELLED' if kind == 'ORDER_CANCELLED' else 'EXPIRED'
        elif kind == 'UNRESOLVED':
            for affected in detail['affectedOrderIds']:
                require(affected in rows, 'unresolvedOrder', 'CORRUPT_RECORD')
                rows[affected]['status'] = 'UNRESOLVED'
        if kind not in ('ENTRY_FILL', 'EXIT_FILL'):
            continue
        financial_count += 1
        require(order_id in rows, 'fillOrder', 'CORRUPT_RECORD')
        evidence = detail['evidence']; stamp = int(evidence['timeNs'])
        require(stamp <= int(state['throughNs']) and evidence['eventIds'], 'futureFill', 'CORRUPT_RECORD')
        row = rows[order_id]
        cost, delta = Fraction(detail['commission']), Fraction(detail['balanceDelta'])
        commission += cost
        row['commission'] = text(Fraction(row['commission']) + cost)
        row['netCashChange'] = text(Fraction(row['netCashChange']) + delta)
        if kind == 'ENTRY_FILL':
            require(row['entryFillRef'] is None and detail['quantity'] == row['quantity'] and delta == -cost, 'entry', 'CORRUPT_RECORD')
            row.update(status='ACTIVE', entryPrice=detail['price'], entryTimeNs=evidence['timeNs'], entryFillRef=event['eventId'])
        else:
            require(row['entryFillRef'] == detail['entryFillRef'] and
                Fraction(row['remaining']) - Fraction(detail['quantity']) == Fraction(detail['remaining']) and
                delta == Fraction(detail['gross']) - cost, 'exit', 'CORRUPT_RECORD')
            gross += Fraction(detail['gross'])
            row.update(gross=text(Fraction(row['gross'])+Fraction(detail['gross'])), remaining=detail['remaining'],
                exitTimeNs=evidence['timeNs'], exitPrice=detail['price'], exitFillRef=event['eventId'], exitReason=detail['reason'])
            if Fraction(row['remaining']) == 0:
                row.update(status='CLOSED', net=row['netCashChange'], durationNs=str(stamp-int(row['entryTimeNs'])))
                completed.append(row)
        balance += delta; peak = max(peak, balance)
        drawdown = peak-balance; maximum_drawdown = max(maximum_drawdown, drawdown)
        if peak > 0: maximum_percent = max(maximum_percent, drawdown/peak)
        equity.append(dict(eventId=event['eventId'], sequence=event['sequence'], timeNs=evidence['timeNs'], balance=text(balance)))
        annotations.append(dict(eventId=event['eventId'], orderId=order_id, kind=kind, timeNs=evidence['timeNs'],
            price=detail['price'], side=row['side'], reason=detail.get('reason'), chronologyLimited=evidence['chronologyLimited']))
    require(count == state['nextEventIndex'] and previous == state['eventHash'] and balance == Fraction(state['balance']) and
        gross == Fraction(state['realizedGross']) and commission == Fraction(state['commission']) and set(rows) == set(state['orders']),
        'analysisHead', 'CORRUPT_RECORD')
    indicative = Fraction()
    mark_available = not state['unresolved'] and quote is not None and int(quote['timeNs']) <= int(state['throughNs'])
    for order_id, row in rows.items():
        stored = state['orders'][order_id]
        require(all(row[k] == stored[k] for k in ('status','quantity','remaining','entryPrice','entryFillRef','side','entry','sl','tp','orderType','workflow')),
            'orderProjection', 'CORRUPT_RECORD')
        row['exitRequested'] = stored['exitRequest'] is not None
        row['unrealizedIndicative'] = None
        if row['status'] == 'ACTIVE' and mark_available:
            liquidation = Fraction(quote['bid'] if row['side'] == 'LONG' else quote['ask'])
            mark = (1 if row['side'] == 'LONG' else -1)*(liquidation-Fraction(row['entryPrice']))*Fraction(state['profile']['contractSize'])*Fraction(row['remaining'])
            row['unrealizedIndicative'] = text(mark); indicative += mark
    result = metrics(completed)
    result.update(maxDrawdown=text(maximum_drawdown), maxDrawdownRate=ratio(maximum_percent), unresolved=sum(r['status']=='UNRESOLVED' for r in rows.values()),
        unrealizedExcluded=True, equityBasis='COMMITTED_CASH_POSTINGS', equityWindowStart=max(0,financial_count-256),
        expired=sum(r['status']=='EXPIRED' for r in rows.values()))
    return dict(status='COMPLETE', provenance=provenance, orders=list(rows.values()), completed=completed, metrics=result,
        account=dict(balance=state['balance'], realizedGross=state['realizedGross'], commission=state['commission'],
            netCashChange=text(balance-Fraction(state['initialBalance'])), unrealizedIndicative=text(indicative) if mark_available else None,
            equityIndicative=text(balance+indicative) if mark_available else None, quoteTimeNs=quote['timeNs'] if mark_available else None),
        equity=list(equity), annotations=list(annotations), annotationWindowStart=max(0,financial_count-512))
