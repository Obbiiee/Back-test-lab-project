"""Bounded exact engine2 ledger projection; no quotes or settlement capability."""
from collections import deque
from copy import deepcopy
from fractions import Fraction
from contracts.canonical import content_hash
from contracts.primitives import require
from ticks.contracts import tag, uint
from .kernel_v2 import validate_state, ratio as fraction
from .contracts import text
from .analysis import metrics, ratio

MAX_ANALYSIS_EVENTS=4096
VERSION="BTL-COMMITTED-STATISTICS-2"
EVENT_FIELDS="engineVersion sessionId datasetId datasetVersion profileHash methodHash sequence previousHash kind classification orderId detail eventId"

def project(state,events,genesis):
    validate_state(state)
    provenance=dict(sessionId=state["sessionId"],revision=state["revision"],engineVersion=state["engineVersion"],
                    datasetId=state["datasetId"],datasetVersion=state["datasetVersion"],profileHash=state["profileHash"],
                    methodHash=state["policy"]["definitionHash"],eventHead=state["eventHash"],analysisVersion=VERSION,
                    model=state["profile"]["model"])
    def unavailable(reason):return dict(schemaVersion=1,artifact=VERSION,status="UNAVAILABLE",reason=reason,provenance=provenance)
    if state["nextEventIndex"]>MAX_ANALYSIS_EVENTS:return unavailable("REFUSED_ANALYSIS_LIMIT")
    if state["parent"] is not None:return unavailable("UNSUPPORTED_LINEAGE")
    validate_state(genesis)
    require(all(state[k]==genesis[k] for k in ("sessionId","engineVersion","datasetId","datasetVersion","profileHash","policy","startNs","initialBalance","parent"))
            and genesis["revision"]==0 and genesis["nextEventIndex"]==0 and genesis["orders"]=={}
            and genesis["balance"]==genesis["initialBalance"],"genesis","CORRUPT_RECORD")
    seed=dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-SEED-2",sessionId=genesis["sessionId"],profileHash=genesis["profileHash"],
              policy=genesis["policy"],initialBalance=genesis["initialBalance"],sourceCheckpointHash=genesis["sourceCheckpointHash"])
    require(genesis["eventHash"]==content_hash(seed),"genesisHash","CORRUPT_RECORD")
    previous=genesis["eventHash"];count=financial_count=0
    balance=peak=Fraction(genesis["initialBalance"]);gross=fees=max_dd=max_rate=Fraction(0)
    orders={};entry_times={};completed=[];curve=deque(maxlen=256);last_time=int(state["startNs"])
    allowed={"ORDER_ACCEPTED","ORDER_CANCELLED","EXPIRED_NO_QUOTE","EXIT_REQUESTED","UNRESOLVED","ENTRY_FILL","EXIT_FILL","SESSION_ENDED","CHRONOLOGY_LIMITATION"}
    for event in events:
        require(count<MAX_ANALYSIS_EVENTS,"events","REFUSED_ANALYSIS_LIMIT")
        tag(event,"BTL-TICK-EXECUTION-EVENT-2",EVENT_FIELDS)
        require(type(event["sequence"]) is int and event["sequence"]==count and event["previousHash"]==previous
                and event["eventId"]==content_hash({k:v for k,v in event.items() if k!="eventId"})
                and all(event[k]==state[k] for k in ("engineVersion","sessionId","datasetId","datasetVersion","profileHash"))
                and event["methodHash"]==state["policy"]["definitionHash"],"eventChain","CORRUPT_RECORD")
        previous=event["eventId"];count+=1
        kind,oid,d=event["kind"],event["orderId"],event["detail"]
        require(kind in allowed and event["classification"] in ("OBSERVED_FEED_EVENT","ACCEPTED_COMMAND","UNRESOLVED","SIMULATED_FILL"),"kind","CORRUPT_RECORD")
        require((event["classification"]=="SIMULATED_FILL")== (kind in ("ENTRY_FILL","EXIT_FILL")),"classification","CORRUPT_RECORD")
        if kind=="ORDER_ACCEPTED":
            require(oid in state["orders"] and oid not in orders,"order","CORRUPT_RECORD")
            orders[oid]=deepcopy(d["plan"])
        elif kind in ("ORDER_CANCELLED","EXPIRED_NO_QUOTE"):
            require(oid in orders and orders[oid]["status"]=="PENDING","order","CORRUPT_RECORD")
            orders[oid]["status"]="CANCELLED" if kind=="ORDER_CANCELLED" else "EXPIRED"
        elif kind=="EXIT_REQUESTED":
            require(oid in orders and orders[oid]["status"]=="ACTIVE" and orders[oid]["exitRequest"] is None,"exit","CORRUPT_RECORD")
            orders[oid]["exitRequest"]=deepcopy(d["request"])
        elif kind=="UNRESOLVED":
            for affected in d["affectedOrderIds"]:
                require(affected in orders and orders[affected]["status"] in ("PENDING","ACTIVE"),"unresolved","CORRUPT_RECORD")
                orders[affected].update(status="UNRESOLVED",exitRequest=None)
        if kind not in ("ENTRY_FILL","EXIT_FILL"):continue
        require(oid in orders,"fillOrder","CORRUPT_RECORD");o=orders[oid]
        moment=uint(d["primaryEvidence"]["timeNs"])
        require(last_time<=moment<=int(state["throughNs"]),"fillTime","CORRUPT_RECORD");last_time=moment
        cost,delta=Fraction(d["commissionPosted"]),Fraction(d["cashDelta"])
        require(cost>=0,"cost","CORRUPT_RECORD");fees+=cost;financial_count+=1
        if kind=="ENTRY_FILL":
            require(o["status"]=="PENDING" and o["entryFillRef"] is None and d["quantity"]==o["quantity"] and delta==-cost,"entry","CORRUPT_RECORD")
            o.update(status="ACTIVE",entryPrice=d["price"],entryFillRef=event["eventId"],entryCostPosted=text(cost));entry_times[oid]=moment
        else:
            amount,value=Fraction(d["quantity"]),Fraction(d["grossPosted"])
            require(o["status"]=="ACTIVE" and o["entryFillRef"]==d["entryFillRef"]
                    and 0<amount<=Fraction(o["remaining"]) and Fraction(o["remaining"])-amount==Fraction(d["remaining"])
                    and delta==value-cost,"exit","CORRUPT_RECORD")
            gross+=value
            allocated=fraction(o["allocatedEntryCost"])+fraction(d["entryCostAllocationExact"])
            o.update(remaining=d["remaining"],status="CLOSED" if d["remaining"]=="0" else "ACTIVE",exitRequest=None,
                     allocatedEntryCost=ratio(allocated),exitCostPosted=text(Fraction(o["exitCostPosted"])+cost),grossPosted=text(Fraction(o["grossPosted"])+value))
            if o["status"]=="CLOSED":
                net=Fraction(o["grossPosted"])-Fraction(o["entryCostPosted"])-Fraction(o["exitCostPosted"])
                completed.append(dict(id=oid,net=text(net),durationNs=str(moment-entry_times[oid]),rMultiple=None,rReason="CONFIRMED_R0_NOT_JOINED"))
        balance+=delta;peak=max(peak,balance);dd=peak-balance;max_dd=max(max_dd,dd)
        rate=dd/peak if peak>0 else None
        if rate is not None:max_rate=max(max_rate,rate)
        curve.append(dict(eventId=event["eventId"],orderId=oid,sequence=event["sequence"],timeNs=str(moment),balance=text(balance),drawdown=text(dd),drawdownRate=None if rate is None else ratio(rate)))
    require(count==state["nextEventIndex"] and previous==state["eventHash"] and orders==state["orders"]
            and balance==Fraction(state["balance"]) and gross==Fraction(state["realizedGross"]) and fees==Fraction(state["commission"]),"ledgerHead","CORRUPT_RECORD")
    result=metrics(completed)
    result.update(realizedNetCompleted=text(sum((Fraction(c["net"]) for c in completed),Fraction(0))),
                  totalR=None,rReason="CONFIRMED_R0_NOT_JOINED",maxDrawdown=text(max_dd),maxDrawdownRate=ratio(max_rate),
                  unresolved=sum(o["status"]=="UNRESOLVED" for o in orders.values()),unrealizedExcluded=True)
    return dict(schemaVersion=1,artifact=VERSION,status="COMPLETE",provenance=provenance,metrics=result,completed=completed,
                account=dict(currency="USD",initialBalance=state["initialBalance"],balance=state["balance"],realizedGross=state["realizedGross"],commission=state["commission"],netCashChange=text(balance-Fraction(state["initialBalance"]))),
                balanceCurve=list(curve),curveWindowStart=max(0,financial_count-256),curveBasis="COMMITTED_CASH_POSTINGS",markToMarketAvailable=False)
