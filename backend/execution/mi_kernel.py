"""Multi-instrument reducer (Stage 3 of the multi-pair design). QA-only, authored-synthetic-only, versioned, NOT mounted in any product path.

One Session = one shared account balance (USD), up to 16 instruments on ONE timeline. Orders carry `symbol` and `methodId` from creation. The arithmetic is the existing, tested
v2 arithmetic (entry/exit proposals, USD conversion, cost allocation, crossing and protective rules); this module adds the portfolio state around it:

  * ORDER OF EVENTS: groups arrive from `ticks.multi_timeline.MultiTimeline` in the total order (timeNs, instrumentIndex, rawOrdinal); a group of one instrument only moves THAT instrument's
    orders, then becomes that instrument's latest revealed group. A conversion uses the latest revealed group of the ROUTE instrument at that moment, so nothing later is ever used.
  * NO SILENT PRICES: a conversion needs a fresh route group (maximum age from the profile pin, at most 60 s). A missing or stale one makes the session UNRESOLVED with an explicit code
    (the same rule as the v2 kernel); equity marks such a position UNAVAILABLE instead of inventing a rate.
  * In Stage 3 every conversion route must be a member of the instrument set (one timeline feeds both). Coverage/diagnostic frames of real sources are NOT modelled (synthetic, declared complete).
  * Margin is NOT part of this reducer (see execution/margin.py, informational only).
"""
from copy import deepcopy
from fractions import Fraction

from contracts.canonical import canonical_bytes, content_hash
from contracts.models import MethodPolicy, Observation, validate_action
from contracts.primitives import ContractError, digest, identifier, require, revision
from ticks.contracts import CanonicalTick, keys, tag, uint
from ticks.timeline import make_group

from .contracts import exact, money, policy_from_wire, policy_wire, text
from .conversion import convert_usd, conversion_route
from .engine import crossing, protective
from .finance_v2 import allocate_entry_cost, entry_proposal, exit_proposal, planned_risk, price, quantity, rational
from .profile_set import ProfileSet
from .profile_v2 import ExecutionProfileV2

MI_ENGINE = "BTL-TICK-EXECUTION-MI-1"
MI_STATE = "BTL-TICK-EXECUTION-STATE-MI-1"
MI_COMPACT_STATE = "BTL-TICK-EXECUTION-STATE-MI-COMPACT-1"
MI_COMMAND = "BTL-TICK-EXECUTION-COMMAND-MI-1"
MI_EVENT = "BTL-TICK-EXECUTION-EVENT-MI-1"
MAX_EVENTS, MAX_ORDERS, MAX_METHODS = 256, 128, 16
STATE_FIELDS = ("sessionId engineVersion profiles profileSetHash methods activeMethodId revision initialBalance balance realizedGross commission "
                "startNs throughNs nextGroupIndex nextEventIndex eventHash groups orders unresolved ended financial")
ORDER_FIELDS = ("symbol methodId side orderType workflow entry quantity sl tp riskPercent observations status availableNs remaining entryPrice entryFillRef "
                "entryCostPosted allocatedEntryCost exitCostPosted grossPosted exitRequest")


def _set(state):
    return ProfileSet(state["profiles"])


def _profile(state, symbol):
    for wire in state["profiles"]:
        if wire["symbol"] == symbol:
            return ExecutionProfileV2.from_wire(wire)
    raise ContractError("REFUSED_INSTRUMENT_SET", "symbol")


def route_of(profile):
    w = profile.wire
    return None if w["conversion"] is None else w["conversion"]["symbol"]


def _check_bindings(pset):
    """Every non-USD instrument's conversion pin must be exactly the primary source of its route instrument, which must be a member of the set."""
    by = {p.wire["symbol"]: p.wire for p in pset.profiles}
    for w in by.values():
        if w["conversion"] is None:
            continue
        route = by.get(w["conversion"]["symbol"])
        require(route is not None, "conversion", "REFUSED_INSTRUMENT_SET")
        pin, src = w["conversion"], route["primary"]
        require(all(pin[k] == src[k] for k in ("datasetId", "datasetVersion", "providerId", "feedId", "feedInstrumentId")), "conversion", "REFUSED_INSTRUMENT_SET")


def seed_state(session_id, profile_set, policies, active_method_id, balance, start_ns):
    identifier(session_id, "sessionId")
    require(isinstance(profile_set, ProfileSet), "profiles", "REFUSED_INSTRUMENT_SET")
    _check_bindings(profile_set)
    require(type(policies) is list and 1 <= len(policies) <= MAX_METHODS and all(type(p) is MethodPolicy for p in policies)
            and len({p.method_id for p in policies}) == len(policies), "policies", "REFUSED_METHOD_SET")
    by_id = {p.method_id: p for p in policies}
    require(active_method_id in by_id, "activeMethodId", "REFUSED_METHOD_SET")
    uint(start_ns)
    initial = money(exact(balance, "balance", True), 2)
    methods = {mid: policy_wire(p) for mid, p in sorted(by_id.items())}
    wires = [p.wire for p in profile_set.profiles]
    seed = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-SEED-MI-1", sessionId=session_id, profileSetHash=profile_set.profile_set_hash, methods=methods, initialBalance=initial)
    state = dict(schemaVersion=1, artifact=MI_STATE, sessionId=session_id, engineVersion=MI_ENGINE, profiles=wires, profileSetHash=profile_set.profile_set_hash,
                 methods=methods, activeMethodId=active_method_id, revision=0, initialBalance=initial, balance=initial, realizedGross="0", commission="0",
                 startNs=str(start_ns), throughNs=str(start_ns), nextGroupIndex="0", nextEventIndex=0, eventHash=content_hash(seed),
                 groups={w["symbol"]: None for w in wires}, orders={}, unresolved=False, ended=False, financial=False)
    return validate_state(state)


def seed_hash(state):
    return content_hash(dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-SEED-MI-1", sessionId=state["sessionId"], profileSetHash=state["profileSetHash"],
                             methods=state["methods"], initialBalance=state["initialBalance"]))


def command_wire(raw):
    tag(raw, MI_COMMAND, "sessionId commandId expectedRevision kind payload")
    identifier(raw["sessionId"], "sessionId"); identifier(raw["commandId"], "commandId"); revision(raw["expectedRevision"])
    fields = {"OPEN": "symbol side orderType workflow entry quantity sl tp riskPercent observations", "CLOSE": "orderId quantity", "CANCEL": "orderId",
              "ADVANCE": "targetNs", "END": "", "SET_METHOD": "methodId"}
    require(type(raw["kind"]) is str and raw["kind"] in fields, "kind", "REFUSED_COMMAND")
    keys(raw["payload"], fields[raw["kind"]])
    if raw["kind"] == "ADVANCE":
        uint(raw["payload"]["targetNs"])
    if raw["kind"] in ("CLOSE", "CANCEL"):
        identifier(raw["payload"]["orderId"], "orderId")
    if raw["kind"] == "SET_METHOD":
        identifier(raw["payload"]["methodId"], "methodId")
    if raw["kind"] == "OPEN":
        identifier(raw["payload"]["symbol"], "symbol")
    canonical_bytes(raw)
    return deepcopy(raw)


def ratio(raw):
    keys(raw, "numerator denominator")
    n, d = raw["numerator"], raw["denominator"]
    return Fraction(int(n), int(d))


def validate_state(state):
    compact = type(state) is dict and state.get("artifact") == MI_COMPACT_STATE
    tag(state, MI_COMPACT_STATE if compact else MI_STATE, STATE_FIELDS + (" archived" if compact else ""))
    require(state["engineVersion"] == MI_ENGINE, "engine", "REFUSED_ENGINE_VERSION")
    pset = ProfileSet(state["profiles"])
    require(pset.profile_set_hash == state["profileSetHash"], "profiles", "CORRUPT_RECORD")
    _check_bindings(pset)
    identifier(state["sessionId"], "sessionId"); revision(state["revision"]); revision(state["nextEventIndex"])
    uint(state["startNs"]); uint(state["throughNs"]); uint(state["nextGroupIndex"]); digest(state["eventHash"], "eventHash")
    require(int(state["startNs"]) <= int(state["throughNs"]), "time")
    methods = state["methods"]
    require(type(methods) is dict and 1 <= len(methods) <= MAX_METHODS and state["activeMethodId"] in methods, "methods", "CORRUPT_RECORD")
    for mid, wire in methods.items():
        require(policy_from_wire(wire).method_id == mid, "methods", "CORRUPT_RECORD")
    require(type(state["groups"]) is dict and set(state["groups"]) == set(pset.symbols), "groups", "CORRUPT_RECORD")
    require(all(type(state[k]) is bool for k in ("unresolved", "ended", "financial")), "flags")
    require(type(state["orders"]) is dict and len(state["orders"]) <= MAX_ORDERS, "orders", "REFUSED_STATE_LIMIT")
    for field in ("initialBalance", "balance", "realizedGross", "commission"):
        require(type(state[field]) is str and text(exact(state[field], field)) == state[field], field, "CORRUPT_RECORD")
    gross = fees = Fraction(0)
    archived_fills = 0
    if compact:
        archived = state["archived"]
        keys(archived, "count gross fees filled head")
        revision(archived["count"]); revision(archived["filled"]); digest(archived["head"], "archiveHead")
        require(archived["filled"] <= archived["count"] <= state["nextEventIndex"],
                "archiveCount", "CORRUPT_RECORD")
        gross = exact(archived["gross"], "archiveGross")
        fees = exact(archived["fees"], "archiveFees")
        require(fees >= 0 and (archived["filled"] > 0 or (fees == gross == 0)),
                "archivePosting", "CORRUPT_RECORD")
        archived_fills = archived["filled"]
    for oid, o in state["orders"].items():
        identifier(oid, "orderId"); keys(o, ORDER_FIELDS)
        require(o["symbol"] in pset.symbols and o["methodId"] in methods, "order", "CORRUPT_RECORD")
        p = ExecutionProfileV2.from_wire(next(w for w in state["profiles"] if w["symbol"] == o["symbol"])).wire
        require(o["side"] in ("LONG", "SHORT") and o["orderType"] in ("MARKET", "LIMIT", "STOP") and o["workflow"] in ("QUICK", "PLANNED"), "order")
        total, remaining = quantity(o["quantity"], p), exact(o["remaining"], "remaining")
        require(0 <= remaining <= total and (remaining / exact(p["lotStep"], "step")).denominator == 1, "remaining")
        require(o["status"] in ("PENDING", "ACTIVE", "CLOSED", "CANCELLED", "EXPIRED", "UNRESOLVED"), "status")
        require((o["entryPrice"] is None) == (o["entryFillRef"] is None), "entryRef")
        if o["status"] in ("PENDING", "CANCELLED", "EXPIRED"):
            require(o["entryPrice"] is None and remaining == total, "unfilled")
        if o["status"] == "ACTIVE":
            require(o["entryPrice"] is not None and remaining > 0, "active")
        if o["status"] == "CLOSED":
            require(o["entryPrice"] is not None and remaining == 0, "closed")
        cost, exit_cost = exact(o["entryCostPosted"], "entryCost"), exact(o["exitCostPosted"], "exitCost")
        require(cost >= 0 and exit_cost >= 0, "fees")
        require(ratio(o["allocatedEntryCost"]) == cost * (total - remaining) / total, "allocation", "CORRUPT_RECORD")
        gross += exact(o["grossPosted"], "gross"); fees += cost + exit_cost
    require(exact(state["initialBalance"], "initial", True) + gross - fees == exact(state["balance"], "balance")
            and gross == exact(state["realizedGross"], "gross") and fees == exact(state["commission"], "fees"), "account", "CORRUPT_RECORD")
    require(state["financial"] == (archived_fills > 0 or any(o["entryPrice"] is not None for o in state["orders"].values())), "financial")
    for symbol, group in state["groups"].items():
        require(group is None or (int(group["timeNs"]) <= int(state["throughNs"])), "groups", "REFUSED_FUTURE_EVIDENCE")
    canonical_bytes(state)
    return state


def emit(state, events, kind, *, symbol=None, order_id=None, classification="OBSERVED_FEED_EVENT", **detail):
    require(len(events) < MAX_EVENTS, "events", "REFUSED_EVENT_LIMIT")
    event = dict(schemaVersion=1, artifact=MI_EVENT, engineVersion=MI_ENGINE, sessionId=state["sessionId"], profileSetHash=state["profileSetHash"],
                 methodHash=state["methods"][state["activeMethodId"]]["definitionHash"], symbol=symbol, sequence=state["nextEventIndex"],
                 previousHash=state["eventHash"], kind=kind, classification=classification, orderId=order_id, detail=detail)
    event["eventId"] = content_hash(event)
    state["eventHash"] = event["eventId"]; state["nextEventIndex"] += 1
    events.append(event)
    return event["eventId"]


def _unresolved(state, events, reason, group_id=None):
    if state["unresolved"]:
        return
    affected = []
    for oid, o in state["orders"].items():
        if o["status"] in ("PENDING", "ACTIVE"):
            o.update(status="UNRESOLVED", exitRequest=None); affected.append(oid)
    state["unresolved"] = True
    emit(state, events, "UNRESOLVED", classification="UNRESOLVED", reason=reason, groupId=group_id, affectedOrderIds=affected)


def _compact(proposal):
    result = {k: deepcopy(v) for k, v in proposal.items() if k not in ("evidence", "conversion")}
    result["proofHash"] = content_hash(dict(schemaVersion=1, artifact="BTL-V2-FINANCIAL-PROOF-1", proposal=proposal))
    if "evidence" in proposal:
        e = proposal["evidence"]
        result["primaryEvidence"] = {k: e[k] for k in ("groupId", "timeNs", "order", "side")}
    if proposal.get("conversion") is not None:
        e = proposal["conversion"]["evidence"]
        result["conversionEvidence"] = None if e is None else {k: e[k] for k in ("groupId", "timeNs", "symbol", "operation", "side", "price")}
    return result


def _fx_group(state, profile, same_time=None):
    """The latest revealed group of the route instrument with timeNs <= the moment being processed. `same_time` holds the groups of THIS advance that share the moment:
    a route quote stamped exactly at the fill time is not in the future (the v2 kernel's rule), and it is already part of the evidence handed in for that moment."""
    route = route_of(profile)
    if route is None:
        return None
    if same_time is not None and route in same_time:
        return same_time[route]
    return state["groups"][route]


def _fx_status(state, profile, as_of, same_time=None):
    """IDENTITY (USD quote) | ELIGIBLE_SYNTHETIC | UNRESOLVED_FX_*: evaluated for the instant `as_of`, only from groups already revealed."""
    p = profile.wire
    if p["conversion"] is None:
        return "IDENTITY"
    group = _fx_group(state, profile, same_time)
    if group is None:
        return "UNRESOLVED_FX_MISSING"
    try:
        for amount in ("1", "-1"):
            convert_usd(amount, p["quoteCurrency"], str(as_of), pin=p["conversion"], group=group, money_scale=p["moneyScale"])
    except ContractError as error:
        require(error.code.startswith("UNRESOLVED_"), "conversion", error.code)
        return error.code
    return "ELIGIBLE_SYNTHETIC"


def submit(state, raw):
    validate_state(state)
    command = command_wire(raw)
    require(command["sessionId"] == state["sessionId"], "session", "REFUSED_SESSION_MISMATCH")
    require(command["expectedRevision"] == state["revision"], "revision", "REFUSED_STALE_REVISION")
    state, events = deepcopy(state), []
    kind, payload = command["kind"], command["payload"]
    require(kind == "ADVANCE" or not state["ended"], "ended", "REFUSED_SESSION_ENDED")
    require(kind in ("ADVANCE", "END") or not state["unresolved"], "unresolved", "REFUSED_UNRESOLVED_SESSION")
    policy = policy_from_wire(state["methods"][state["activeMethodId"]])
    if kind == "OPEN":
        require(len(state["orders"]) < MAX_ORDERS and command["commandId"] not in state["orders"], "orders", "REFUSED_STATE_LIMIT")
        require(Fraction(state["balance"]) > 0, "balance", "REFUSED_RISK_BUDGET")
        symbol = payload["symbol"]
        profile = _profile(state, symbol); p = profile.wire
        require(state["groups"][symbol] is not None, "quote", "UNRESOLVED_NO_QUOTE")
        status = _fx_status(state, profile, int(state["throughNs"]))
        require(status in ("IDENTITY", "ELIGIBLE_SYNTHETIC"), "conversion", status)          # no order on a pair whose USD conversion cannot be proven right now
        require(payload["side"] in ("LONG", "SHORT") and payload["orderType"] in ("MARKET", "LIMIT", "STOP") and payload["workflow"] in ("QUICK", "PLANNED")
                and (payload["workflow"] != "QUICK" or payload["orderType"] == "MARKET"), "order")
        require(all(v is None or type(v) is str for v in (payload["entry"], payload["quantity"], payload["sl"], payload["tp"], payload["riskPercent"])), "financialStrings")
        entry, size = price(payload["entry"], p), quantity(payload["quantity"], p)
        sl = None if payload["sl"] is None else price(payload["sl"], p)
        tp = None if payload["tp"] is None else price(payload["tp"], p)
        direction = 1 if payload["side"] == "LONG" else -1
        require((sl is None or direction * (entry - sl) > 0) and (tp is None or direction * (tp - entry) > 0), "geometry", "REFUSED_GEOMETRY")
        require(payload["workflow"] != "PLANNED" or (sl is not None and tp is not None), "planned")
        risk = exact(payload["riskPercent"], "risk", True)
        require(risk <= 100, "risk")
        require(type(payload["observations"]) is list and len(payload["observations"]) <= 64, "observations")
        outcomes = {}
        for item in payload["observations"]:
            keys(item, "conditionId outcome"); seen = Observation(item["conditionId"], item["outcome"])
            require(seen.condition_id not in outcomes and seen.condition_id in policy.conditions, "observations")
            outcomes[seen.condition_id] = seen.outcome
        if policy.kind == "PROTOCOL":                                                       # the ACTIVE Method's rules govern a new order
            require(payload["workflow"] == "PLANNED" and payload["orderType"] in ("LIMIT", "STOP") and risk == Fraction(policy.risk_percent)
                    and abs(tp - entry) == abs(entry - sl) * Fraction(policy.rr), "protocol", "PROTOCOL_BLOCKED")
            budget = Fraction(state["balance"]) * risk / 100
            recommended = planned_risk(profile, payload["side"], text(entry), text(sl), text(budget), state["throughNs"], conversion_group=_fx_group(state, profile))["quantity"]
            require(size == Fraction(recommended) and (not policy.checklist_on or all(outcomes.get(c) == "PASS" for c in policy.conditions)), "protocol", "PROTOCOL_BLOCKED")
        state["orders"][command["commandId"]] = dict(
            symbol=symbol, methodId=state["activeMethodId"], side=payload["side"], orderType=payload["orderType"], workflow=payload["workflow"], entry=text(entry),
            quantity=text(size), sl=None if sl is None else text(sl), tp=None if tp is None else text(tp), riskPercent=text(risk), observations=deepcopy(payload["observations"]),
            status="PENDING", availableNs=state["throughNs"], remaining=text(size), entryPrice=None, entryFillRef=None, entryCostPosted="0",
            allocatedEntryCost=rational(Fraction(0)), exitCostPosted="0", grossPosted="0", exitRequest=None)
        emit(state, events, "ORDER_ACCEPTED", symbol=symbol, order_id=command["commandId"], classification="ACCEPTED_COMMAND",
             plan=deepcopy(state["orders"][command["commandId"]]), methodId=state["activeMethodId"])
    elif kind in ("CANCEL", "CLOSE"):
        o = state["orders"].get(payload["orderId"])
        require(o is not None, "order", "REFUSED_ORDER_UNAVAILABLE")
        order_policy = policy_from_wire(state["methods"][o["methodId"]])                  # trades are governed by the Method they were created under
        p = _profile(state, o["symbol"]).wire
        if kind == "CANCEL":
            require(o["status"] == "PENDING", "order", "REFUSED_NOT_PENDING"); validate_action(order_policy, "CANCEL_PENDING")
            o["status"] = "CANCELLED"
            emit(state, events, "ORDER_CANCELLED", symbol=o["symbol"], order_id=payload["orderId"], classification="ACCEPTED_COMMAND")
        else:
            validate_action(order_policy, "MANUAL_CLOSE" if payload["quantity"] is None else "PARTIAL_CLOSE")
            require(o["status"] == "ACTIVE" and o["exitRequest"] is None, "order", "REFUSED_NOT_ACTIVE")
            size = Fraction(o["remaining"]) if payload["quantity"] is None else quantity(payload["quantity"], p)
            require(0 < size <= Fraction(o["remaining"]) and (payload["quantity"] is None or size < Fraction(o["remaining"])), "partial", "REFUSED_PARTIAL_QUANTITY")
            o["exitRequest"] = dict(quantity=text(size), availableNs=state["throughNs"], commandId=command["commandId"])
            emit(state, events, "EXIT_REQUESTED", symbol=o["symbol"], order_id=payload["orderId"], classification="ACCEPTED_COMMAND", request=deepcopy(o["exitRequest"]))
    elif kind == "SET_METHOD":
        target = payload["methodId"]
        require(target in state["methods"] and target != state["activeMethodId"], "methodId", "REFUSED_METHOD_UNCHANGED")
        previous, state["activeMethodId"] = state["activeMethodId"], target
        emit(state, events, "METHOD_SWITCHED", classification="ACCEPTED_COMMAND", fromMethodId=previous, toMethodId=target)
    elif kind == "END":
        for oid, o in state["orders"].items():
            if o["status"] == "PENDING":
                o["status"] = "EXPIRED"; emit(state, events, "EXPIRED_NO_QUOTE", symbol=o["symbol"], order_id=oid, classification="UNRESOLVED")
        if any(o["status"] == "ACTIVE" for o in state["orders"].values()):
            _unresolved(state, events, "UNRESOLVED_SESSION_END_ACTIVE")
        state["ended"] = True
        emit(state, events, "SESSION_ENDED", classification="ACCEPTED_COMMAND", throughNs=state["throughNs"])
    elif kind != "ADVANCE":
        raise ContractError("REFUSED_COMMAND", "kind")
    validate_state(state)
    return state, events


def _live(state, symbol=None):
    return any(o["status"] in ("PENDING", "ACTIVE") and (symbol is None or o["symbol"] == symbol) for o in state["orders"].values())


def _can_change(state, symbol, row):
    for o in state["orders"].values():
        if o["symbol"] != symbol or int(row["timeNs"]) < int(o["availableNs"]):
            continue
        if o["status"] == "PENDING" and crossing(o, row):
            return True
        if o["status"] == "ACTIVE" and (protective(o, row) is not None or o["exitRequest"] is not None):
            return True
    return False


def _fills(state, events, symbol, group, same_time):
    profile = _profile(state, symbol); p = profile.wire; row = group["events"][0]; t = group["timeNs"]
    fx = _fx_group(state, profile, same_time)
    for oid, o in state["orders"].items():
        if o["symbol"] != symbol or int(t) < int(o["availableNs"]):
            continue
        if o["status"] == "PENDING" and crossing(o, row):
            proposal = entry_proposal(profile, o["side"], o["quantity"], t, group)
            fee = proposal["commissionPosted"]
            o.update(status="ACTIVE", entryPrice=proposal["price"], entryCostPosted=fee)
            state["commission"] = text(Fraction(state["commission"]) + Fraction(fee))
            state["balance"] = text(Fraction(state["balance"]) + Fraction(proposal["cashDelta"]))
            state["financial"] = True
            o["entryFillRef"] = emit(state, events, "ENTRY_FILL", symbol=symbol, order_id=oid, classification="SIMULATED_FILL", **_compact(proposal))
        if o["status"] != "ACTIVE":
            continue
        reason, request = protective(o, row), o["exitRequest"]
        if reason is None and request is not None and int(t) >= int(request["availableNs"]):
            reason = "MANUAL"
        if reason is None:
            continue
        size = Fraction(request["quantity"]) if reason == "MANUAL" else Fraction(o["remaining"])
        proposal = exit_proposal(profile, o["side"], o["entryPrice"], text(size), t, group, conversion_group=fx)
        already = Fraction(o["quantity"]) - Fraction(o["remaining"])
        allocation = allocate_entry_cost(o["entryCostPosted"], o["quantity"], text(already), text(size), o["allocatedEntryCost"])
        remaining = Fraction(o["remaining"]) - size
        o.update(remaining=text(remaining), status="CLOSED" if remaining == 0 else "ACTIVE", exitRequest=None,
                 allocatedEntryCost=rational(ratio(o["allocatedEntryCost"]) + ratio(allocation)),
                 exitCostPosted=text(Fraction(o["exitCostPosted"]) + Fraction(proposal["commissionPosted"])),
                 grossPosted=text(Fraction(o["grossPosted"]) + Fraction(proposal["grossPosted"])))
        state["realizedGross"] = text(Fraction(state["realizedGross"]) + Fraction(proposal["grossPosted"]))
        state["commission"] = text(Fraction(state["commission"]) + Fraction(proposal["commissionPosted"]))
        state["balance"] = text(Fraction(state["balance"]) + Fraction(proposal["cashDelta"]))
        state["financial"] = True
        derived = Fraction(proposal["grossPosted"]) - Fraction(proposal["commissionPosted"]) - ratio(allocation)
        emit(state, events, "EXIT_FILL", symbol=symbol, order_id=oid, classification="SIMULATED_FILL", **_compact(proposal), remaining=text(remaining), reason=reason,
             entryFillRef=o["entryFillRef"], entryCostAllocationExact=allocation, netRealizedDerived=money(derived, p["moneyScale"]), netIsDerived=True)


def advance(state, groups, target_ns):
    """`groups` is the output of MultiTimeline.advance(target): dicts (timeNs:int, instrument, instrumentIndex, events) in total order, none later than the target."""
    validate_state(state)
    target = uint(target_ns)
    require(int(state["throughNs"]) <= target, "time", "REFUSED_FUTURE_EVIDENCE")
    state, events = deepcopy(state), []
    pset = _set(state)
    previous = int(state["throughNs"]); last = {s: (None if g is None else int(g["timeNs"])) for s, g in state["groups"].items()}
    last_key = None
    built, by_time = [], {}
    for item in groups:                                                                    # validate and build every canonical group of this advance first
        keys(item, "timeNs instrument instrumentIndex events")
        symbol, moment = item["instrument"], item["timeNs"]
        require(symbol in pset.symbols and pset.index_of(symbol) == item["instrumentIndex"], "group", "REFUSED_DATASET_MISMATCH")
        source = _profile(state, symbol).wire["primary"]
        rows = [CanonicalTick.from_wire(r).wire for r in item["events"]]
        require(type(moment) is int and rows and all(r["timeNs"] == str(moment) and all(r[k] == source[k] for k in ("datasetId", "datasetVersion", "providerId", "feedId"))
                                                     and r["instrumentId"] == source["feedInstrumentId"] for r in rows), "group", "REFUSED_DATASET_MISMATCH")
        require(len({r["eventId"] for r in rows}) == len(rows), "group")
        built.append((item, rows, make_group(rows, source["datasetVersion"])))
        by_time.setdefault(moment, {})[symbol] = built[-1][2]
    for item, rows, group in built:
        keys(item, "timeNs instrument instrumentIndex events")
        symbol, moment = item["instrument"], item["timeNs"]
        require(symbol in pset.symbols and pset.index_of(symbol) == item["instrumentIndex"], "group", "REFUSED_DATASET_MISMATCH")
        require(type(moment) is int and previous <= moment <= target, "groupTime", "REFUSED_FUTURE_EVIDENCE")
        key = (moment, item["instrumentIndex"])
        require(last_key is None or key > last_key, "groupOrder", "REFUSED_GROUP_ORDER")                       # strict total order: no duplicate, no reordering
        require(last[symbol] is None or moment > last[symbol], "groupTime", "REFUSED_REPEATED_GROUP")
        profile = _profile(state, symbol); p = profile.wire
        same = by_time[moment]
        if group["order"] == "TRUSTED_SEQUENCE":
            seq = [int(r["trustedSequence"]) for r in rows]
            require(seq == sorted(set(seq)), "sequence")
        # The group is evidence from now on (the conversion basis of any LATER fill); it is stored only after its own processing, so it never prices itself ahead of order.
        if _live(state, symbol) and not state["unresolved"] and not state["ended"]:
            bad = any(r["quality"]["quote"] != "VALID" or r["quality"]["freshness"] != "CONFIRMED" or r["quality"]["gapBefore"] not in ("NONE", "KNOWN_SESSION_CLOSED")
                      or r["quality"]["evidenceHash"] is None or r["quality"]["duplicateOf"] is not None for r in rows)
            if bad:
                _unresolved(state, events, "UNRESOLVED_QUOTE_QUALITY", group["groupId"])
            else:
                try:
                    for r in rows:
                        price(r["bid"], p); price(r["ask"], p)
                except ContractError:
                    _unresolved(state, events, "UNRESOLVED_QUOTE_PRECISION", group["groupId"])
                if not state["unresolved"]:
                    equivalent = len({(r["bid"], r["ask"]) for r in rows}) == 1
                    changes = any(_can_change(state, symbol, r) for r in rows)
                    if not equivalent and changes:
                        _unresolved(state, events, "UNRESOLVED_EQUAL_TIME_ORDER", group["groupId"])
                    elif not equivalent:
                        emit(state, events, "CHRONOLOGY_LIMITATION", symbol=symbol, groupId=group["groupId"], timeNs=group["timeNs"], commonOutcome="NO_FINANCIAL_ACTION")
                    elif changes:
                        status = _fx_status(state, profile, moment, same)
                        if status not in ("IDENTITY", "ELIGIBLE_SYNTHETIC"):
                            _unresolved(state, events, status, group["groupId"])
                        else:
                            proposed, proposed_events = deepcopy(state), []
                            try:
                                _fills(proposed, proposed_events, symbol, group, same)
                            except ContractError as error:
                                if error.code.startswith("UNRESOLVED_") or error.code == "REFUSED_FINANCIAL_LIMIT":
                                    _unresolved(state, events, error.code if error.code.startswith("UNRESOLVED_") else "UNRESOLVED_MODEL_LIMIT", group["groupId"])
                                else:
                                    raise
                            else:
                                require(len(events) + len(proposed_events) <= MAX_EVENTS, "events", "REFUSED_EVENT_LIMIT")
                                state, events = proposed, events + proposed_events
        state["groups"][symbol] = group
        last[symbol], last_key, previous = moment, key, moment
        state["throughNs"] = str(moment); state["nextGroupIndex"] = str(int(state["nextGroupIndex"]) + 1)
    state["throughNs"] = str(target)
    validate_state(state)
    return state, events


def equity(state):
    """Balance plus the unrealised result of every ACTIVE position, valued ONLY from revealed data. A position whose USD conversion is missing or stale at `throughNs`
    is listed UNAVAILABLE with the reason and `complete` is False: the number is never completed with an invented rate."""
    validate_state(state)
    as_of = int(state["throughNs"])
    total, rows, complete = Fraction(0), [], True
    for oid, o in state["orders"].items():
        if o["status"] != "ACTIVE":
            continue
        profile = _profile(state, o["symbol"]); p = profile.wire; group = state["groups"][o["symbol"]]
        if group is None or len({(r["bid"], r["ask"]) for r in group["events"]}) != 1:
            rows.append(dict(orderId=oid, symbol=o["symbol"], status="UNAVAILABLE", reason="NO_UNAMBIGUOUS_QUOTE")); complete = False
            continue
        quote = group["events"][0]
        liquidation = Fraction(quote["bid"] if o["side"] == "LONG" else quote["ask"])
        gross_quote = (1 if o["side"] == "LONG" else -1) * (liquidation - Fraction(o["entryPrice"])) * exact(p["contractSize"], "contract") * Fraction(o["remaining"])
        try:
            result = convert_usd(text(gross_quote), p["quoteCurrency"], str(as_of), pin=p["conversion"], group=_fx_group(state, profile), money_scale=p["moneyScale"])
        except ContractError as error:
            rows.append(dict(orderId=oid, symbol=o["symbol"], status="UNAVAILABLE", reason=error.code)); complete = False
            continue
        value = Fraction(int(result["usdExact"]["numerator"]), int(result["usdExact"]["denominator"]))
        total += value
        rows.append(dict(orderId=oid, symbol=o["symbol"], status="OK", unrealizedUsdExact=rational(value), unrealizedUsd=money(value, 2), quoteTimeNs=group["timeNs"]))
    return dict(balance=state["balance"], unrealizedUsdExact=rational(total), unrealizedUsd=money(total, 2), equityUsdExact=rational(Fraction(state["balance"]) + total),
                equityUsd=money(Fraction(state["balance"]) + total, 2), complete=complete, positions=rows, asOfNs=state["throughNs"])
