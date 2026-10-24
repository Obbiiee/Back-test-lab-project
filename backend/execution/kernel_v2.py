"""Pure synthetic v2 transitions. Only a durable controller may publish fills."""
from copy import deepcopy
from fractions import Fraction
from contracts.canonical import canonical_bytes, content_hash
from contracts.models import Observation, validate_action
from contracts.primitives import ContractError, digest, identifier, require, revision
from ticks.contracts import CanonicalTick, keys, tag, uint
from ticks.timeline import make_group, CURSOR_FIELDS
from ticks.provider import diagnostic_counts
from .contracts import exact, money, text, policy_wire, policy_from_wire
from .engine import crossing, protective, coverage_complete
from .finance_v2 import entry_proposal, exit_proposal, allocate_entry_cost, planned_risk, risk_for_quantity, quantity, price, rational
from .profile_v2 import ExecutionProfileV2, ENGINE_VERSION, ADMITTED_MODEL
from .conversion import convert_usd

MAX_EVENTS, MAX_ORDERS = 256, 128
STATE_FIELDS = ("sessionId datasetId datasetVersion engineVersion profile profileHash policy revision initialBalance balance "
                "realizedGross commission startNs throughNs nextGroupIndex nextEventIndex eventHash sourceCheckpointHash "
                "orders unresolved ended financial parent")
ORDER_FIELDS = ("side orderType workflow entry quantity sl tp riskPercent observations risk status availableNs remaining "
                "entryPrice entryFillRef entryCostPosted allocatedEntryCost exitCostPosted grossPosted exitRequest")


def ratio(raw):
    keys(raw, "numerator denominator")
    n,d=raw["numerator"],raw["denominator"]
    require(all(type(v) is str and 1<=len(v)<=128 for v in (n,d)),"ratio")
    require((n.isascii() and (n.isdigit() or n.startswith("-") and n[1:].isdigit()))
            and d.isascii() and d.isdigit() and d!="0","ratio")
    value=Fraction(int(n),int(d))
    require((str(value.numerator),str(value.denominator))==(n,d),"ratio")
    return value


def command_wire(raw):
    tag(raw,"BTL-TICK-EXECUTION-COMMAND-2","sessionId commandId expectedRevision kind payload")
    identifier(raw["sessionId"],"sessionId");identifier(raw["commandId"],"commandId");revision(raw["expectedRevision"])
    fields={"OPEN":"side orderType workflow entry quantity sl tp riskPercent observations","CLOSE":"orderId quantity",
            "CANCEL":"orderId","ADVANCE":"targetNs","END":"","FORK":"parentSessionId parentRevision"}
    require(type(raw["kind"]) is str and raw["kind"] in fields,"kind","REFUSED_COMMAND")
    keys(raw["payload"],fields[raw["kind"]])
    if raw["kind"]=="ADVANCE":uint(raw["payload"]["targetNs"])
    if raw["kind"] in ("CLOSE","CANCEL"):identifier(raw["payload"]["orderId"],"orderId")
    if raw["kind"]=="FORK":
        identifier(raw["payload"]["parentSessionId"],"parentSessionId");revision(raw["payload"]["parentRevision"])
    return deepcopy(raw)


def validate_state(state):
    tag(state,"BTL-TICK-EXECUTION-STATE-2",STATE_FIELDS)
    require(state["engineVersion"]==ENGINE_VERSION,"engine","REFUSED_ENGINE_VERSION")
    profile=ExecutionProfileV2.from_wire(state["profile"]);p=profile.wire
    require(profile.profile_hash==state["profileHash"] and state["datasetId"]==p["primary"]["datasetId"]
            and state["datasetVersion"]==p["primary"]["datasetVersion"],"profile","CORRUPT_RECORD")
    identifier(state["sessionId"],"sessionId");revision(state["revision"]);revision(state["nextEventIndex"])
    uint(state["startNs"]);uint(state["throughNs"]);uint(state["nextGroupIndex"])
    require(int(state["startNs"])<=int(state["throughNs"]),"time")
    digest(state["eventHash"],"eventHash");digest(state["sourceCheckpointHash"],"sourceCheckpointHash")
    policy=policy_from_wire(state["policy"])
    require(all(type(state[k]) is bool for k in ("unresolved","ended","financial")),"flags")
    require(type(state["orders"]) is dict and len(state["orders"])<=MAX_ORDERS,"orders","REFUSED_STATE_LIMIT")
    for field in ("initialBalance","balance","realizedGross","commission"):
        require(type(state[field]) is str and text(exact(state[field],field))==state[field],field,"CORRUPT_RECORD")
    gross=Fraction(0);fees=Fraction(0)
    for oid,o in state["orders"].items():
        identifier(oid,"orderId");keys(o,ORDER_FIELDS)
        require(o["side"] in ("LONG","SHORT") and o["orderType"] in ("MARKET","LIMIT","STOP")
                and o["workflow"] in ("QUICK","PLANNED"),"order")
        total=quantity(o["quantity"],p);remaining=exact(o["remaining"],"remaining")
        require(0<=remaining<=total and (remaining/exact(p["lotStep"],"step")).denominator==1,"remaining")
        price(o["entry"],p)
        for value in (o["sl"],o["tp"],o["entryPrice"]):
            if value is not None:price(value,p)
        require(o["status"] in ("PENDING","ACTIVE","CLOSED","CANCELLED","EXPIRED","UNRESOLVED"),"status")
        require(type(o["observations"]) is list and len(o["observations"])<=64,"observations")
        require(0<exact(o["riskPercent"],"risk")<=100,"risk")
        require(o["workflow"]!="QUICK" or o["orderType"]=="MARKET","workflow")
        entry=Fraction(o["entry"]);direction=1 if o["side"]=="LONG" else -1
        require((o["sl"] is None or direction*(entry-Fraction(o["sl"]))>0)
                and (o["tp"] is None or direction*(Fraction(o["tp"])-entry)>0),"geometry")
        require(o["workflow"]!="PLANNED" or o["sl"] is not None and o["tp"] is not None,"planned")
        outcomes={}
        for item in o["observations"]:
            keys(item,"conditionId outcome");observed=Observation(item["conditionId"],item["outcome"])
            require(observed.condition_id in policy.conditions and observed.condition_id not in outcomes,"observations")
            outcomes[observed.condition_id]=observed.outcome
        require((o["risk"] is None)==(o["sl"] is None),"risk")
        if policy.kind=="PROTOCOL":
            require(o["workflow"]=="PLANNED" and o["orderType"] in ("LIMIT","STOP")
                    and Fraction(o["riskPercent"])==Fraction(policy.risk_percent)
                    and abs(Fraction(o["tp"])-entry)==abs(entry-Fraction(o["sl"]))*Fraction(policy.rr)
                    and o["risk"] is not None and o["risk"]["recommendedQuantity"]==o["quantity"]
                    and (not policy.checklist_on or all(outcomes.get(c)=="PASS" for c in policy.conditions)),"protocol")
        if o["risk"] is not None:
            keys(o["risk"],"timeNs recommendedQuantity requestedQuantity plannedRequestedLossUsdExact budgetUsd evidenceHash exceedsBudget")
            require(uint(o["risk"]["timeNs"])<=uint(o["availableNs"]),"riskTime")
            require(o["risk"]["requestedQuantity"]==o["quantity"] and ratio(o["risk"]["plannedRequestedLossUsdExact"])>0,"risk")
            if o["risk"]["recommendedQuantity"] is not None:quantity(o["risk"]["recommendedQuantity"],p)
            budget=exact(o["risk"]["budgetUsd"],"riskBudget",True);digest(o["risk"]["evidenceHash"],"riskEvidence")
            require(type(o["risk"]["exceedsBudget"]) is bool and o["risk"]["exceedsBudget"]==(ratio(o["risk"]["plannedRequestedLossUsdExact"])>budget),"riskBudget")
        uint(o["availableNs"])
        require(int(o["availableNs"])<=int(state["throughNs"]),"availableNs")
        cost=exact(o["entryCostPosted"],"entryCost");exit_cost=exact(o["exitCostPosted"],"exitCost")
        require(cost>=0 and exit_cost>=0,"fees")
        allocated=ratio(o["allocatedEntryCost"])
        require(allocated==cost*(total-remaining)/total,"allocation","CORRUPT_RECORD")
        require((o["entryPrice"] is None)==(o["entryFillRef"] is None),"entryRef")
        if o["entryFillRef"] is not None:digest(o["entryFillRef"],"entryFillRef")
        else:require(remaining==total and cost==0 and exit_cost==0 and exact(o["grossPosted"],"gross")==0,"unfilled")
        if o["status"] in ("PENDING","CANCELLED","EXPIRED"):
            require(o["entryPrice"] is None and remaining==total and cost==0 and exit_cost==0,"unfilled")
        if o["status"]=="ACTIVE":require(o["entryPrice"] is not None and remaining>0,"active")
        if o["status"]=="CLOSED":require(o["entryPrice"] is not None and remaining==0,"closed")
        if o["exitRequest"] is not None:
            keys(o["exitRequest"],"quantity availableNs commandId")
            require(o["status"]=="ACTIVE" and 0<quantity(o["exitRequest"]["quantity"],p)<=remaining,"exit")
            require(uint(o["exitRequest"]["availableNs"])<=int(state["throughNs"]),"exitTime");identifier(o["exitRequest"]["commandId"],"commandId")
        for field in ("entry","quantity","riskPercent","remaining","entryCostPosted","exitCostPosted","grossPosted"):
            require(type(o[field]) is str and text(exact(o[field],field))==o[field],field,"CORRUPT_RECORD")
        gross+=exact(o["grossPosted"],"gross");fees+=cost+exit_cost
    require(exact(state["initialBalance"],"initial",True)+gross-fees==exact(state["balance"],"balance")
            and gross==exact(state["realizedGross"],"gross") and fees==exact(state["commission"],"fees"),
            "account","CORRUPT_RECORD")
    require(not state["unresolved"] or not any(o["status"] in ("ACTIVE","PENDING") for o in state["orders"].values()),"unresolved")
    require(not state["ended"] or not any(o["status"] in ("ACTIVE","PENDING") for o in state["orders"].values()),"ended")
    require(state["financial"]==any(o["entryPrice"] is not None for o in state["orders"].values()),"financial")
    if state["parent"] is not None:
        keys(state["parent"],"sessionId revision checkpointHash eventHash timeNs")
        identifier(state["parent"]["sessionId"],"parent");revision(state["parent"]["revision"])
        digest(state["parent"]["checkpointHash"],"parent");digest(state["parent"]["eventHash"],"parent");uint(state["parent"]["timeNs"])
    canonical_bytes(state)
    return state


def eligible_fx(profile):
    """Accepted conversion status for this profile's source class."""
    return "ELIGIBLE_ADMITTED" if profile["model"]==ADMITTED_MODEL else "ELIGIBLE_SYNTHETIC"


def validate_snapshot(state, checkpoint):
    validate_state(state)
    keys(checkpoint,"schemaVersion artifact profileHash primary conversion")
    require(checkpoint["schemaVersion"]==1 and type(checkpoint["schemaVersion"]) is int
            and checkpoint["artifact"]=="BTL-V2-SOURCE-CHECKPOINT-1" and checkpoint["profileHash"]==state["profileHash"]
            and content_hash(checkpoint)==state["sourceCheckpointHash"],"checkpoint","CORRUPT_RECORD")
    p=state["profile"]
    for role,source in (("primary",p["primary"]),("conversion",p["conversion"])):
        cp=checkpoint[role]
        require((cp is None)==(source is None),"source")
        if source is None:continue
        keys(cp,"cursor advanceTargets");cursor=cp["cursor"];tag(cursor,"BTL-TICK-CURSOR-1",CURSOR_FIELDS)
        require(type(cp["advanceTargets"]) is list and len(cp["advanceTargets"])<=256,"recovery")
        require(cursor["datasetId"]==source["datasetId"] and cursor["datasetVersion"]==source["datasetVersion"],"source")
        uint(cursor["throughNs"]);uint(cursor["sessionStartNs"])
    primary=checkpoint["primary"]["cursor"]
    require((primary["sessionStartNs"],primary["throughNs"],primary["nextGroupIndex"])==
            (state["startNs"],state["throughNs"],state["nextGroupIndex"]),"primaryCheckpoint")
    if checkpoint["conversion"] is not None:
        fx=checkpoint["conversion"]["cursor"]
        require(int(fx["throughNs"])<=int(state["throughNs"]) and fx["pendingTargetNs"] is None
                and fx["sessionStartNs"]==str(max(0,int(state["startNs"])-int(p["conversion"]["maxAgeNs"]))),"fxCheckpoint")
    return dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-CHECKPOINT-2",state=state,controller=checkpoint)


def seed_state(session_id, profile, policy, checkpoint, balance="10000"):
    require(type(profile) is ExecutionProfileV2,"profile")
    p=profile.wire;identifier(session_id,"sessionId")
    initial=money(exact(balance,"balance",True),p["moneyScale"]);require(Fraction(initial)>0,"balance")
    cursor=checkpoint["primary"]["cursor"]
    require(cursor["nextGroupIndex"]=="0" and checkpoint["primary"]["advanceTargets"]==[],"initialCheckpoint")
    seed=dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-SEED-2",sessionId=session_id,profileHash=profile.profile_hash,
              policy=policy_wire(policy),initialBalance=initial,sourceCheckpointHash=content_hash(checkpoint))
    state=dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-STATE-2",sessionId=session_id,
               datasetId=p["primary"]["datasetId"],datasetVersion=p["primary"]["datasetVersion"],engineVersion=ENGINE_VERSION,
               profile=p,profileHash=profile.profile_hash,policy=seed["policy"],revision=0,initialBalance=initial,balance=initial,
               realizedGross="0",commission="0",startNs=cursor["sessionStartNs"],throughNs=cursor["throughNs"],nextGroupIndex="0",
               nextEventIndex=0,eventHash=content_hash(seed),sourceCheckpointHash=content_hash(checkpoint),orders={},
               unresolved=False,ended=False,financial=False,parent=None)
    validate_snapshot(state,checkpoint)
    return state


def emit(state, events, kind, *, order_id=None, classification="OBSERVED_FEED_EVENT", **detail):
    require(len(events)<MAX_EVENTS,"events","REFUSED_EVENT_LIMIT")
    event=dict(schemaVersion=1,artifact="BTL-TICK-EXECUTION-EVENT-2",engineVersion=ENGINE_VERSION,sessionId=state["sessionId"],
               datasetId=state["datasetId"],datasetVersion=state["datasetVersion"],profileHash=state["profileHash"],
               methodHash=state["policy"]["definitionHash"],sequence=state["nextEventIndex"],previousHash=state["eventHash"],
               kind=kind,classification=classification,orderId=order_id,detail=detail)
    event["eventId"]=content_hash(event);state["eventHash"]=event["eventId"];state["nextEventIndex"]+=1;events.append(event)
    return event["eventId"]


def unresolved(state,events,reason,group_id=None):
    if state["unresolved"]:return
    affected=[]
    for oid,o in state["orders"].items():
        if o["status"] in ("PENDING","ACTIVE"):
            o.update(status="UNRESOLVED",exitRequest=None);affected.append(oid)
    state["unresolved"]=True
    emit(state,events,"UNRESOLVED",classification="UNRESOLVED",reason=reason,groupId=group_id,affectedOrderIds=affected)


def _compact(proposal):
    # Group IDs + immutable source versions bind complete event sets; full raw
    # source groups remain in their accepted datasets, never duplicated per fill.
    result={k:deepcopy(v) for k,v in proposal.items() if k not in ("evidence","conversion")}
    result["proofHash"]=content_hash(dict(schemaVersion=1,artifact="BTL-V2-FINANCIAL-PROOF-1",proposal=proposal))
    if "evidence" in proposal:
        e=proposal["evidence"]
        result["primaryEvidence"]={k:e[k] for k in ("groupId","timeNs","order","side")}
    if proposal.get("conversion") is not None:
        e=proposal["conversion"]["evidence"]
        result["conversionEvidence"]=None if e is None else {k:e[k] for k in ("groupId","timeNs","symbol","operation","side","price")}
    return result


def submit(state,raw,basis=None):
    validate_state(state);command=command_wire(raw)
    require(command["sessionId"]==state["sessionId"],"session","REFUSED_SESSION_MISMATCH")
    require(command["expectedRevision"]==state["revision"],"revision","REFUSED_STALE_REVISION")
    state=deepcopy(state);events=[];kind,payload=command["kind"],command["payload"]
    require(kind in ("ADVANCE",) or not state["ended"],"ended","REFUSED_SESSION_ENDED")
    require(kind in ("ADVANCE","END") or not state["unresolved"],"unresolved","REFUSED_UNRESOLVED_SESSION")
    profile=ExecutionProfileV2.from_wire(state["profile"]);p=profile.wire;policy=policy_from_wire(state["policy"])
    if kind=="OPEN":
        require(len(state["orders"])<MAX_ORDERS and command["commandId"] not in state["orders"],"orders","REFUSED_STATE_LIMIT")
        require(Fraction(state["balance"])>0,"balance","REFUSED_RISK_BUDGET")
        keys(basis,"schemaVersion artifact profileHash timeNs conversionGroup conversionStatus checkpoint")
        require(basis["schemaVersion"]==1 and basis["artifact"]=="BTL-V2-SOURCE-RISK-1"
                and basis["profileHash"]==state["profileHash"] and basis["timeNs"]==state["throughNs"],"riskBasis")
        require(basis["conversionStatus"]==("IDENTITY" if p["conversion"] is None else eligible_fx(p)),"conversion","UNRESOLVED_FX_INTENT")
        for amount in ("1","-1"):
            convert_usd(amount,p["quoteCurrency"],state["throughNs"],pin=p["conversion"],group=basis["conversionGroup"],money_scale=p["moneyScale"])
        require(payload["side"] in ("LONG","SHORT") and payload["orderType"] in ("MARKET","LIMIT","STOP")
                and payload["workflow"] in ("QUICK","PLANNED")
                and (payload["workflow"]!="QUICK" or payload["orderType"]=="MARKET"),"order")
        require(all(v is None or type(v) is str for v in (payload["entry"],payload["quantity"],payload["sl"],payload["tp"],payload["riskPercent"])),"financialStrings")
        entry=price(payload["entry"],p);size=quantity(payload["quantity"],p)
        sl=None if payload["sl"] is None else price(payload["sl"],p)
        tp=None if payload["tp"] is None else price(payload["tp"],p)
        direction=1 if payload["side"]=="LONG" else -1
        require((sl is None or direction*(entry-sl)>0) and (tp is None or direction*(tp-entry)>0),"geometry","REFUSED_GEOMETRY")
        require(payload["workflow"]!="PLANNED" or sl is not None and tp is not None,"planned")
        risk=exact(payload["riskPercent"],"risk",True);require(risk<=100,"risk")
        require(type(payload["observations"]) is list and len(payload["observations"])<=64,"observations")
        outcomes={}
        for o in payload["observations"]:
            keys(o,"conditionId outcome");observed=Observation(o["conditionId"],o["outcome"])
            require(observed.condition_id not in outcomes and observed.condition_id in policy.conditions,"observations")
            outcomes[observed.condition_id]=observed.outcome
        risk_info=None
        if sl is not None:
            budget=Fraction(state["balance"])*risk/100
            actual=risk_for_quantity(profile,payload["side"],text(entry),text(sl),text(size),state["throughNs"],conversion_group=basis["conversionGroup"])
            recommended=None
            if policy.kind=="PROTOCOL":
                recommended=planned_risk(profile,payload["side"],text(entry),text(sl),text(budget),state["throughNs"],conversion_group=basis["conversionGroup"])["quantity"]
            risk_info=dict(timeNs=state["throughNs"],recommendedQuantity=recommended,requestedQuantity=text(size),
                           plannedRequestedLossUsdExact=actual["plannedLossUsdExact"],budgetUsd=text(budget),
                           exceedsBudget=ratio(actual["plannedLossUsdExact"])>budget,
                           evidenceHash=content_hash(dict(schemaVersion=1,artifact="BTL-V2-RISK-PROOF-1",proposal=actual)))
        if policy.kind=="PROTOCOL":
            require(payload["workflow"]=="PLANNED" and payload["orderType"] in ("LIMIT","STOP") and risk==Fraction(policy.risk_percent)
                    and abs(tp-entry)==abs(entry-sl)*Fraction(policy.rr) and risk_info is not None
                    and size==Fraction(risk_info["recommendedQuantity"])
                    and (not policy.checklist_on or all(outcomes.get(c)=="PASS" for c in policy.conditions)),"protocol","PROTOCOL_BLOCKED")
        order={k:deepcopy(payload[k]) for k in ("side","orderType","workflow","observations")}
        order.update(entry=text(entry),quantity=text(size),sl=None if sl is None else text(sl),tp=None if tp is None else text(tp),
                     riskPercent=text(risk),risk=risk_info,status="PENDING",availableNs=state["throughNs"],remaining=text(size),
                     entryPrice=None,entryFillRef=None,entryCostPosted="0",allocatedEntryCost=rational(Fraction(0)),exitCostPosted="0",grossPosted="0",exitRequest=None)
        state["orders"][command["commandId"]]=order;state["sourceCheckpointHash"]=content_hash(basis["checkpoint"])
        validate_snapshot(state,basis["checkpoint"])
        emit(state,events,"ORDER_ACCEPTED",order_id=command["commandId"],classification="ACCEPTED_COMMAND",plan=deepcopy(order))
    elif kind in ("CANCEL","CLOSE"):
        o=state["orders"].get(payload["orderId"]);require(o is not None,"order","REFUSED_ORDER_UNAVAILABLE")
        if kind=="CANCEL":
            require(o["status"]=="PENDING","order","REFUSED_NOT_PENDING");validate_action(policy,"CANCEL_PENDING")
            o["status"]="CANCELLED";emit(state,events,"ORDER_CANCELLED",order_id=payload["orderId"],classification="ACCEPTED_COMMAND")
        else:
            validate_action(policy,"MANUAL_CLOSE" if payload["quantity"] is None else "PARTIAL_CLOSE")
            require(o["status"]=="ACTIVE" and o["exitRequest"] is None,"order","REFUSED_NOT_ACTIVE")
            size=Fraction(o["remaining"]) if payload["quantity"] is None else quantity(payload["quantity"],p)
            require(0<size<=Fraction(o["remaining"]) and (payload["quantity"] is None or size<Fraction(o["remaining"])),"partial","REFUSED_PARTIAL_QUANTITY")
            o["exitRequest"]=dict(quantity=text(size),availableNs=state["throughNs"],commandId=command["commandId"])
            emit(state,events,"EXIT_REQUESTED",order_id=payload["orderId"],classification="ACCEPTED_COMMAND",request=deepcopy(o["exitRequest"]))
    elif kind=="END":
        for oid,o in state["orders"].items():
            if o["status"]=="PENDING":o["status"]="EXPIRED";emit(state,events,"EXPIRED_NO_QUOTE",order_id=oid,classification="UNRESOLVED")
        if any(o["status"]=="ACTIVE" for o in state["orders"].values()):unresolved(state,events,"UNRESOLVED_SESSION_END_ACTIVE")
        state["ended"]=True;emit(state,events,"SESSION_ENDED",classification="ACCEPTED_COMMAND",throughNs=state["throughNs"])
    elif kind!="ADVANCE":raise ContractError("REFUSED_COMMAND","kind")
    validate_state(state)
    return state,events


def _live(state):
    return any(o["status"] in ("PENDING","ACTIVE") for o in state["orders"].values())


def _can_change(state,row):
    for o in state["orders"].values():
        if int(row["timeNs"])<int(o["availableNs"]):continue
        if o["status"]=="PENDING" and crossing(o,row):return True
        if o["status"]=="ACTIVE" and (protective(o,row) is not None or o["exitRequest"] is not None):return True
    return False


def _fills(state,events,group,fx):
    profile=ExecutionProfileV2.from_wire(state["profile"]);p=profile.wire;row=group["events"][0]
    t=group["timeNs"]
    for oid,o in state["orders"].items():
        if int(t)<int(o["availableNs"]):continue
        if o["status"]=="PENDING" and crossing(o,row):
            proposal=entry_proposal(profile,o["side"],o["quantity"],t,group)
            fee=proposal["commissionPosted"]
            o.update(status="ACTIVE",entryPrice=proposal["price"],entryCostPosted=fee)
            state["commission"]=text(Fraction(state["commission"])+Fraction(fee))
            state["balance"]=text(Fraction(state["balance"])+Fraction(proposal["cashDelta"]))
            state["financial"]=True
            o["entryFillRef"]=emit(state,events,"ENTRY_FILL",order_id=oid,classification="SIMULATED_FILL",**_compact(proposal))
        if o["status"]!="ACTIVE":continue
        reason=protective(o,row);request=o["exitRequest"]
        if reason is None and request is not None and int(t)>=int(request["availableNs"]):reason="MANUAL"
        if reason is None:continue
        size=Fraction(request["quantity"]) if reason=="MANUAL" else Fraction(o["remaining"])
        proposal=exit_proposal(profile,o["side"],o["entryPrice"],text(size),t,group,conversion_group=fx)
        already=Fraction(o["quantity"])-Fraction(o["remaining"])
        allocation=allocate_entry_cost(o["entryCostPosted"],o["quantity"],text(already),text(size),o["allocatedEntryCost"])
        allocated=ratio(o["allocatedEntryCost"])+ratio(allocation)
        remaining=Fraction(o["remaining"])-size
        o.update(remaining=text(remaining),status="CLOSED" if remaining==0 else "ACTIVE",exitRequest=None,
                 allocatedEntryCost=rational(allocated),exitCostPosted=text(Fraction(o["exitCostPosted"])+Fraction(proposal["commissionPosted"])),
                 grossPosted=text(Fraction(o["grossPosted"])+Fraction(proposal["grossPosted"])))
        state["realizedGross"]=text(Fraction(state["realizedGross"])+Fraction(proposal["grossPosted"]))
        state["commission"]=text(Fraction(state["commission"])+Fraction(proposal["commissionPosted"]))
        state["balance"]=text(Fraction(state["balance"])+Fraction(proposal["cashDelta"]))
        state["financial"]=True
        derived=Fraction(proposal["grossPosted"])-Fraction(proposal["commissionPosted"])-ratio(allocation)
        emit(state,events,"EXIT_FILL",order_id=oid,classification="SIMULATED_FILL",**_compact(proposal),
             remaining=text(remaining),reason=reason,entryFillRef=o["entryFillRef"],entryCostAllocationExact=allocation,
             netRealizedDerived=money(derived,p["moneyScale"]),netIsDerived=True)


def advance(state,frame,target_ns):
    validate_state(state)
    tag(frame,"BTL-V2-SOURCE-REVEAL-1","profileHash throughNs pairs conversionGroups primaryCoverage primaryDiagnostics exhaustedThroughBoundary checkpoint")
    through,target=uint(frame["throughNs"]),uint(target_ns)
    require(int(state["throughNs"])<=through<=target and frame["profileHash"]==state["profileHash"],"time","REFUSED_FUTURE_EVIDENCE")
    require(type(frame["exhaustedThroughBoundary"]) is bool and (not frame["exhaustedThroughBoundary"] or through==target),"boundary")
    require(type(frame["pairs"]) is list and len(frame["pairs"])<=64 and type(frame["conversionGroups"]) is dict,"groups")
    coverage=frame["primaryCoverage"];diag=frame["primaryDiagnostics"]
    require(type(coverage) is list and len(coverage)<=2048,"coverage")
    for c in coverage:
        keys(c,"startNs endNs status evidenceHash")
        require(int(state["throughNs"])<=uint(c["startNs"])<uint(c["endNs"])<=through
                and c["status"] in ("DECLARED_COMPLETE","UNKNOWN","INCOMPLETE"),"coverage","REFUSED_FUTURE_EVIDENCE")
        if c["evidenceHash"] is not None:digest(c["evidenceHash"],"coverageHash")
    keys(diag,"records counts truncated")
    require(type(diag["records"]) is list and len(diag["records"])<=128 and diag["truncated"] is False
            and diag["counts"]==diagnostic_counts(diag["records"]),"diagnostics")
    require(all(int(state["throughNs"])<=uint(d["timeNs"])<=through for d in diag["records"]),"diagnostics","REFUSED_FUTURE_EVIDENCE")
    require(frame["checkpoint"]["primary"]["cursor"]["pendingTargetNs"]==(None if frame["exhaustedThroughBoundary"] else target_ns),"target")
    original_count=int(state["nextGroupIndex"]);state=deepcopy(state);events=[];previous=int(state["throughNs"]);refs=set()
    p=state["profile"];source=p["primary"]
    for index,pair in enumerate(frame["pairs"]):
        keys(pair,"primaryGroup conversionGroupId conversionStatus")
        group=pair["primaryGroup"];keys(group,"groupId timeNs order events");moment=uint(group["timeNs"])
        require(previous<=moment<=through and (index==0 or previous<moment)
                and (index!=0 or original_count==0 or previous<moment),"groupTime","REFUSED_FUTURE_EVIDENCE")
        require(type(group["events"]) is list and 1<=len(group["events"])<=1024,"group")
        rows=[CanonicalTick.from_wire(r).wire for r in group["events"]]
        require(all(r["timeNs"]==group["timeNs"] and all(r[k]==source[k] for k in ("datasetId","datasetVersion","providerId","feedId"))
                    and r["instrumentId"]==source["feedInstrumentId"] for r in rows)
                and make_group(rows,source["datasetVersion"])==group,"group","REFUSED_DATASET_MISMATCH")
        require(len({r["eventId"] for r in rows})==len(rows),"group")
        if group["order"]=="TRUSTED_SEQUENCE":
            seq=[int(r["trustedSequence"]) for r in rows];require(seq==sorted(set(seq)),"sequence")
        ref=pair["conversionGroupId"];fx=None
        if p["conversion"] is None:
            require(ref is None and pair["conversionStatus"]=="IDENTITY","conversion")
        elif ref is None:
            require(pair["conversionStatus"]=="UNRESOLVED_FX_MISSING","conversion")
        elif ref is not None:
            digest(ref,"conversionRef");require(ref in frame["conversionGroups"],"conversion")
            fx=frame["conversionGroups"][ref];refs.add(ref)
            require(fx["groupId"]==ref and uint(fx["timeNs"])<=moment,"conversion","REFUSED_FUTURE_EVIDENCE")
            if pair["conversionStatus"]==eligible_fx(p):
                for amount in ("1","-1"):
                    convert_usd(amount,p["quoteCurrency"],group["timeNs"],pin=p["conversion"],group=fx,money_scale=p["moneyScale"])
            else:require(type(pair["conversionStatus"]) is str and pair["conversionStatus"].startswith("UNRESOLVED_FX_"),"conversion")
        active=_live(state) and not state["unresolved"] and not state["ended"]
        if active and not coverage_complete(coverage,previous,moment):unresolved(state,events,"UNRESOLVED_COVERAGE",group["groupId"])
        elif active and any(previous<=int(d["timeNs"])<=moment for d in diag["records"]):unresolved(state,events,"UNRESOLVED_DIAGNOSTIC",group["groupId"])
        elif active:
            bad=any(r["quality"]["quote"]!="VALID" or r["quality"]["freshness"]!="CONFIRMED"
                    or r["quality"]["gapBefore"] not in ("NONE","KNOWN_SESSION_CLOSED")
                    or r["quality"]["evidenceHash"] is None or r["quality"]["duplicateOf"] is not None for r in rows)
            if bad:unresolved(state,events,"UNRESOLVED_QUOTE_QUALITY",group["groupId"])
            else:
                try:
                    for r in rows:price(r["bid"],p);price(r["ask"],p)
                except ContractError:unresolved(state,events,"UNRESOLVED_QUOTE_PRECISION",group["groupId"])
                if not state["unresolved"]:
                    equivalent=len({(r["bid"],r["ask"]) for r in rows})==1
                    changes=any(_can_change(state,r) for r in rows)
                    if not equivalent and changes:unresolved(state,events,"UNRESOLVED_EQUAL_TIME_ORDER",group["groupId"])
                    elif not equivalent:emit(state,events,"CHRONOLOGY_LIMITATION",groupId=group["groupId"],timeNs=group["timeNs"],commonOutcome="NO_FINANCIAL_ACTION")
                    elif changes:
                        if pair["conversionStatus"] not in ("IDENTITY",eligible_fx(p)):
                            require(type(pair["conversionStatus"]) is str and pair["conversionStatus"].startswith("UNRESOLVED_FX_"),"conversionStatus")
                            unresolved(state,events,pair["conversionStatus"],group["groupId"])
                        else:
                            proposed=deepcopy(state);proposed_events=[]
                            try:_fills(proposed,proposed_events,group,fx)
                            except ContractError as error:
                                if error.code.startswith("UNRESOLVED_") or error.code=="REFUSED_FINANCIAL_LIMIT":
                                    unresolved(state,events,error.code if error.code.startswith("UNRESOLVED_") else "UNRESOLVED_MODEL_LIMIT",group["groupId"])
                                else:raise
                            else:
                                require(len(events)+len(proposed_events)<=MAX_EVENTS,"events","REFUSED_EVENT_LIMIT")
                                state=proposed;events.extend(proposed_events)
        previous=moment;state["throughNs"]=group["timeNs"];state["nextGroupIndex"]=str(int(state["nextGroupIndex"])+1)
    require(refs==set(frame["conversionGroups"]),"conversionGroups")
    if _live(state) and not state["unresolved"] and not state["ended"]:
        if not coverage_complete(coverage,previous,through):unresolved(state,events,"UNRESOLVED_COVERAGE")
        elif any(previous<int(d["timeNs"])<=through for d in diag["records"]):unresolved(state,events,"UNRESOLVED_DIAGNOSTIC")
    state["throughNs"]=frame["throughNs"];state["sourceCheckpointHash"]=content_hash(frame["checkpoint"])
    require(int(state["nextGroupIndex"])==original_count+len(frame["pairs"]),"groupCount")
    validate_snapshot(state,frame["checkpoint"])
    return state,events
