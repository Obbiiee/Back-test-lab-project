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
RESEARCH_VERSION = 'BTL-PINNED-RESEARCH-1'


def planned_risk(state, command):
    """Explicit nominal risk reviewed before confirmation; never a fill prediction."""
    plan = command['payload']
    amount = None
    if plan['sl'] is not None:
        amount = (abs(Fraction(plan['entry'])-Fraction(plan['sl'])) *
                  Fraction(plan['quantity']) * Fraction(state['profile']['contractSize']) +
                  2 * Fraction(state['profile']['commissionPerLotSide']) * Fraction(plan['quantity']))
        require(amount > 0, 'plannedRisk', 'CORRUPT_RECORD')
    return dict(schemaVersion=1, artifact='BTL-PREENTRY-RISK-1',
        sessionId=state['sessionId'], datasetId=state['datasetId'], datasetVersion=state['datasetVersion'],
        profileHash=state['profileHash'], throughNs=state['throughNs'], commandHash=content_hash(command),
        amount=text(amount) if amount is not None else None,
        reason=None if amount is not None else 'NO_PLANNED_STOP',
        basis='INTENT_ENTRY_TO_INITIAL_STOP_PLUS_FIXED_ROUND_TRIP_COMMISSION')


def ratio(value):
    if value is None:
        return None
    value = Fraction(value)
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def excursions(completed, groups, state):
    """Observed liquidation excursions from an already revealed bounded prefix.

    Canonical closed positions prove accepted coverage while exposed. This does
    not infer missing ticks; absent boundaries or uncertain exposure return null.
    """
    require(len(groups)<=1024, 'excursionGroups','REFUSED_RESEARCH_LIMIT')
    require(all(int(g['timeNs'])<=int(state['throughNs']) for g in groups),
            'excursionFuture','REFUSED_FUTURE_EVIDENCE')
    results = {}
    for row in completed:
        unavailable = dict(mae=None,mfe=None,excursionReason='REVEALED_HISTORY_LIMIT')
        results[row['id']] = unavailable
        lo,hi = int(row['entryTimeNs']),int(row['exitTimeNs'])
        span = [g for g in groups if lo<=int(g['timeNs'])<=hi]
        entry = row['entryEvidence']; exits = row['exitSlices']
        if not span or not entry or not exits:
            continue
        ids = {g['groupId'] for g in span}
        if entry['groupId'] not in ids or any(e['groupId'] not in ids for e in exits):
            continue
        if sum(len(g['events']) for g in span)>16384:
            unavailable['excursionReason']='REVEALED_RESEARCH_LIMIT';continue
        remaining=Fraction(row['quantity']); favorable=adverse=Fraction(); started=False; consumed=0; reason=None
        for group in span:
            boundaries = group['groupId']==entry['groupId'] or any(e['groupId']==group['groupId'] for e in exits)
            if group['order']=='UNTRUSTED' and boundaries and len({(t['bid'],t['ask']) for t in group['events']})>1:
                reason='UNRESOLVED_EXCURSION_CHRONOLOGY';break
            for tick in group['events']:
                if not started:
                    if group['groupId']!=entry['groupId'] or tick['eventId'] not in entry['eventIds']:
                        continue
                    started=True
                quality=tick['quality']
                require(tick['datasetId']==state['datasetId'] and tick['datasetVersion']==state['datasetVersion'] and
                        tick['timeNs']==group['timeNs'],'excursionIdentity','CORRUPT_RECORD')
                if (quality['quote']!='VALID' or quality['freshness']!='CONFIRMED' or
                    quality['gapBefore'] not in ('NONE','KNOWN_SESSION_CLOSED') or
                    quality['evidenceHash'] is None or quality['duplicateOf'] is not None):
                    reason='UNRESOLVED_EXCURSION_EVIDENCE';break
                liquidation=Fraction(tick['bid'] if row['side']=='LONG' else tick['ask'])
                value=(1 if row['side']=='LONG' else -1)*(liquidation-Fraction(row['entryPrice']))*Fraction(state['profile']['contractSize'])*remaining
                favorable=max(favorable,value);adverse=max(adverse,-value)
                while consumed<len(exits) and exits[consumed]['groupId']==group['groupId'] and tick['eventId'] in exits[consumed]['eventIds']:
                    next_remaining=Fraction(exits[consumed]['remaining'])
                    require(0<=next_remaining<remaining,'excursionExposure','CORRUPT_RECORD')
                    remaining=next_remaining;consumed+=1
                if remaining==0:
                    break
            if reason or remaining==0:
                break
        if reason:
            unavailable['excursionReason']=reason
        elif started and remaining==0 and consumed==len(exits):
            results[row['id']]=dict(mae=text(adverse),mfe=text(favorable),excursionReason=None,
                excursionBasis='OBSERVED_LIQUIDATION_GROSS_REMAINING_EXPOSURE',excursionVersion='BTL-CAUSAL-EXCURSIONS-1')
    return results


def metrics(completed):
    trade_count = wins = losses = breakeven = r_eligible = duration_count = 0
    total_net = positive = negative = total_r = total_duration = Fraction()
    streak_win = streak_loss = maximum_win = maximum_loss = 0
    for row in completed:
        net = Fraction(row['net'])
        trade_count += 1
        total_net += net
        if net > 0:
            wins += 1
            positive += net
        elif net < 0:
            losses += 1
            negative -= net
        else:
            breakeven += 1
        streak_win = streak_win + 1 if net > 0 else 0
        streak_loss = streak_loss + 1 if net < 0 else 0
        maximum_win, maximum_loss = max(maximum_win, streak_win), max(maximum_loss, streak_loss)
        r_multiple = row.get('rMultiple')
        if r_multiple is not None:
            total_r += Fraction(int(r_multiple['numerator']), int(r_multiple['denominator']))
            r_eligible += 1
        duration = row.get('durationNs')
        if duration is not None:
            total_duration += int(duration)
            duration_count += 1
    return dict(tradeCount=trade_count, wins=wins, losses=losses, breakeven=breakeven,
        winRate=ratio(Fraction(wins, trade_count)) if trade_count else None,
        averageWin=ratio(positive / wins) if wins else None,
        averageLoss=ratio(-negative / losses) if losses else None,
        expectancy=ratio(total_net / trade_count) if trade_count else None,
        profitFactor=ratio(positive / negative) if negative else None,
        maxWinStreak=maximum_win, maxLossStreak=maximum_loss,
        rEligible=r_eligible, rExcluded=trade_count-r_eligible,
        rReason=None if r_eligible else 'PREENTRY_R0_NOT_PINNED',
        averageR=ratio(total_r / r_eligible) if r_eligible else None,
        averageDurationNs=ratio(Fraction(total_duration, duration_count)) if duration_count else None,
        monteCarlo=dict(status='INSUFFICIENT_SAMPLE' if r_eligible<30 else 'NOT_COMPUTED',
                        eligible=r_eligible, exclusions=trade_count-r_eligible, minimum=30))


def pool_metrics(session_metrics):
    """Pool exact trade summaries without retaining rows from all Sessions.

    Session boundaries have no shared chronology, so cross-session streaks are
    intentionally omitted. Money, rates, durations, and R averages are
    recombined from exact rational aggregates emitted by ``metrics``.
    """
    def value(raw):
        return None if raw is None else Fraction(int(raw['numerator']),int(raw['denominator']))

    trades=wins=losses=breakeven=r_eligible=0
    net=positive=negative=total_r=total_duration=Fraction()
    for item in session_metrics:
        count=int(item['tradeCount']);win_count=int(item['wins']);loss_count=int(item['losses'])
        be_count=int(item['breakeven']);r_count=int(item['rEligible'])
        require(count==win_count+loss_count+be_count and 0<=r_count<=count,
                'analyticsMetrics','CORRUPT_RECORD')
        trades+=count;wins+=win_count;losses+=loss_count;breakeven+=be_count;r_eligible+=r_count
        average_win=value(item['averageWin']);average_loss=value(item['averageLoss'])
        average_net=value(item['expectancy']);average_r=value(item['averageR'])
        average_duration=value(item['averageDurationNs'])
        require((win_count==0)==(average_win is None) and (loss_count==0)==(average_loss is None)
                and (count==0)==(average_net is None) and (r_count==0)==(average_r is None)
                and (count==0)==(average_duration is None),
                'analyticsMetrics','CORRUPT_RECORD')
        positive+=Fraction() if average_win is None else average_win*win_count
        negative+=Fraction() if average_loss is None else -average_loss*loss_count
        net+=Fraction() if average_net is None else average_net*count
        total_r+=Fraction() if average_r is None else average_r*r_count
        total_duration+=Fraction() if average_duration is None else average_duration*count
    return dict(tradeCount=trades,wins=wins,losses=losses,breakeven=breakeven,
        winRate=ratio(Fraction(wins,trades)) if trades else None,
        averageWin=ratio(positive/wins) if wins else None,
        averageLoss=ratio(-negative/losses) if losses else None,
        expectancy=ratio(net/trades) if trades else None,
        profitFactor=ratio(positive/negative) if negative else None,
        rEligible=r_eligible,rExcluded=trades-r_eligible,
        rReason=None if r_eligible else 'PREENTRY_R0_NOT_PINNED',
        averageR=ratio(total_r/r_eligible) if r_eligible else None,
        averageDurationNs=ratio(total_duration/trades) if trades else None,
        monteCarlo=dict(status='INSUFFICIENT_SAMPLE' if r_eligible<30 else 'NOT_COMPUTED',
                        eligible=r_eligible,exclusions=trades-r_eligible,minimum=30))


def project(state, events, quote):
    validate_state(state)
    provenance = dict(sessionId=state['sessionId'], revision=state['revision'], datasetId=state['datasetId'],
        datasetVersion=state['datasetVersion'], engineVersion=state['engineVersion'], profileHash=state['profileHash'],
        methodHash=state['policy']['definitionHash'], eventHead=state['eventHash'], analysisVersion=ANALYSIS_VERSION,
        model='SIMULATED_QUOTE_BASELINE_NOT_BROKER_EXECUTION')
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
            require(order_id not in rows, 'acceptedOrder', 'CORRUPT_RECORD')
            row = dict(id=order_id, **deepcopy(detail['plan']), entryPrice=None, entryTimeNs=None, entryFillRef=None,
                entryEvidence=None, exitSlices=[],
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
            row.update(status='ACTIVE', entryPrice=detail['price'], entryTimeNs=evidence['timeNs'], entryFillRef=event['eventId'],
                       entryEvidence=dict(groupId=evidence['groupId'],eventIds=deepcopy(evidence['eventIds'])))
        else:
            require(row['entryFillRef'] == detail['entryFillRef'] and
                Fraction(row['remaining']) - Fraction(detail['quantity']) == Fraction(detail['remaining']) and
                delta == Fraction(detail['gross']) - cost, 'exit', 'CORRUPT_RECORD')
            gross += Fraction(detail['gross'])
            row.update(gross=text(Fraction(row['gross'])+Fraction(detail['gross'])), remaining=detail['remaining'],
                exitTimeNs=evidence['timeNs'], exitPrice=detail['price'], exitFillRef=event['eventId'], exitReason=detail['reason'])
            row['exitSlices'].append(dict(groupId=evidence['groupId'],eventIds=deepcopy(evidence['eventIds']),
                                         timeNs=evidence['timeNs'],remaining=detail['remaining']))
            if Fraction(row['remaining']) == 0:
                row.update(status='CLOSED', net=row['netCashChange'], durationNs=str(stamp-int(row['entryTimeNs'])))
                completed.append(row)
        balance += delta; peak = max(peak, balance)
        drawdown = peak-balance; maximum_drawdown = max(maximum_drawdown, drawdown)
        if peak > 0: maximum_percent = max(maximum_percent, drawdown/peak)
        equity.append(dict(eventId=event['eventId'], sequence=event['sequence'], timeNs=evidence['timeNs'], balance=text(balance)))
        annotations.append(dict(eventId=event['eventId'], orderId=order_id, kind=kind, timeNs=evidence['timeNs'],
            price=detail['price'], side=row['side'], reason=detail.get('reason'), chronologyLimited=evidence['chronologyLimited']))
    active_rows={order_id:row for order_id,row in rows.items() if row['status'] in ('PENDING','ACTIVE')}
    require(count == state['nextEventIndex'] and previous == state['eventHash'] and balance == Fraction(state['balance']) and
        gross == Fraction(state['realizedGross']) and commission == Fraction(state['commission']) and set(active_rows) == set(state['orders']),
        'analysisHead', 'CORRUPT_RECORD')
    indicative = Fraction()
    mark_available = not state['unresolved'] and quote is not None and int(quote['timeNs']) <= int(state['throughNs'])
    for order_id, row in active_rows.items():
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
