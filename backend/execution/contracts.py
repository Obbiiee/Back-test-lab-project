"""Materialization of the frozen financial contract, not a new policy owner."""
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction

from contracts.canonical import canonical_bytes, content_hash, decimal_text
from contracts.models import MethodPolicy, Observation
from contracts.primitives import decimal, digest, identifier, require, revision
from ticks.contracts import keys, tag, uint

ENGINE_VERSION = "BTL-TICK-EXECUTION-1"
MAX_ORDERS = 128
MAX_EVENTS = 256
MAX_STEPS = 256
PROFILE_FIELDS = ("instrumentId providerId feedId feedInstrumentId quoteCurrency accountCurrency "
                  "tickSize priceScale contractSize lotStep minLot maxLot moneyScale "
                  "commissionModel commissionPerLotSide slippageModel latencyModel")


def exact(value, field, positive=False):
    d = decimal(value, field, positive=positive)
    require(len(d.as_tuple().digits) <= 36 and abs(d.as_tuple().exponent) <= 18,
            field, "REFUSED_FINANCIAL_LIMIT")
    return Fraction(d)


def text(value):
    """Only finite base-ten fractions; never a context-rounded authority."""
    value = Fraction(value)
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    require(denominator == 1, "finiteDecimal")
    with localcontext() as ctx:
        ctx.prec = 256
        return decimal_text(Decimal(value.numerator) / Decimal(value.denominator))


def money(value, scale):
    """Exact integer ROUND_HALF_EVEN; independent of Decimal context."""
    scaled = Fraction(value) * 10**scale
    quotient, remainder = divmod(abs(scaled.numerator), scaled.denominator)
    if 2 * remainder > scaled.denominator or (2 * remainder == scaled.denominator and quotient % 2):
        quotient += 1
    sign = -1 if scaled < 0 else 1
    return text(Fraction(sign * quotient, 10**scale))


def profile_wire(raw):
    keys(raw, PROFILE_FIELDS)
    p = deepcopy(raw)
    for name in ("instrumentId", "providerId", "feedId", "feedInstrumentId"):
        identifier(p[name], name)
    require(p["instrumentId"] == "XAUUSD" and p["quoteCurrency"] == p["accountCurrency"] == "USD",
            "profile", "REFUSED_UNSUPPORTED_PROFILE")
    for name in ("tickSize", "priceScale", "contractSize", "lotStep", "minLot", "maxLot"):
        p[name] = text(exact(p[name], name, True))
    require(exact(p["minLot"], "min") <= exact(p["maxLot"], "max"), "lotBounds")
    require((exact(p["tickSize"], "tick") * exact(p["priceScale"], "scale")).denominator == 1,
            "priceScale", "REFUSED_UNSUPPORTED_PROFILE")
    require(type(p["moneyScale"]) is int and 0 <= p["moneyScale"] <= 8, "moneyScale")
    require(p["commissionModel"] in ("NONE", "FIXED_PER_LOT_SIDE") and
            p["slippageModel"] == "NONE" and p["latencyModel"] == "ZERO",
            "costModel", "REFUSED_UNSUPPORTED_PROFILE")
    rate = exact(p["commissionPerLotSide"], "commission")
    require(rate >= 0 and (p["commissionModel"] != "NONE" or rate == 0), "commission")
    p["commissionPerLotSide"] = text(rate)
    return p


def price(value, profile):
    number = exact(value, "price", True)
    require((number / exact(profile["tickSize"], "tickSize")).denominator == 1 and
            (number * exact(profile["priceScale"], "priceScale")).denominator == 1,
            "price", "REFUSED_PRICE_PRECISION")
    return number


def quantity(value, profile):
    number = exact(value, "quantity", True)
    require((number / exact(profile["lotStep"], "step")).denominator == 1,
            "quantity", "REFUSED_LOT_PRECISION")
    require(exact(profile["minLot"], "min") <= number <= exact(profile["maxLot"], "max"),
            "quantity", "REFUSED_LOT_BOUNDS")
    return number


def risk_quantity(budget, entry, stop, profile):
    budget = exact(budget, "riskBudget", True)
    distance = abs(price(entry, profile) - price(stop, profile))
    require(distance > 0, "riskDistance")
    denominator = distance * exact(profile["contractSize"], "contract") + 2 * exact(profile["commissionPerLotSide"], "commission")
    step = exact(profile["lotStep"], "step")
    raw = budget / denominator / step
    return text(quantity(text((raw.numerator // raw.denominator) * step), profile))


def policy_wire(policy):
    require(type(policy) is MethodPolicy, "policy")
    return dict(methodId=policy.method_id, definitionHash=policy.definition_hash, kind=policy.kind,
                checklistOn=policy.checklist_on, conditions=list(policy.conditions),
                riskPercent=None if policy.risk_percent is None else decimal_text(policy.risk_percent),
                rr=None if policy.rr is None else decimal_text(policy.rr))


def policy_from_wire(raw):
    keys(raw, "methodId definitionHash kind checklistOn conditions riskPercent rr")
    return MethodPolicy(raw["methodId"], raw["definitionHash"], raw["kind"], raw["checklistOn"],
                        tuple(raw["conditions"]), raw["riskPercent"], raw["rr"])


def command_wire(raw):
    tag(raw, "BTL-TICK-EXECUTION-COMMAND-1", "sessionId commandId expectedRevision kind payload")
    identifier(raw["sessionId"], "sessionId"); identifier(raw["commandId"], "commandId")
    revision(raw["expectedRevision"])
    fields = {
        "OPEN": "side orderType workflow entry quantity sl tp riskPercent observations",
        "CANCEL": "orderId", "CLOSE": "orderId quantity", "ADVANCE": "targetNs",
        "SEEK": "targetNs", "END": "",
        "FORK": "parentSessionId parentRevision",
    }
    require(raw["kind"] in fields, "kind", "REFUSED_COMMAND")
    keys(raw["payload"], fields[raw["kind"]])
    if raw["kind"] in ("ADVANCE", "SEEK"):
        uint(raw["payload"]["targetNs"])
    if raw["kind"] in ("CANCEL", "CLOSE"):
        identifier(raw["payload"]["orderId"], "orderId")
    if raw["kind"] == "FORK":
        identifier(raw["payload"]["parentSessionId"], "parentSessionId")
        revision(raw["payload"]["parentRevision"])
    canonical_bytes(raw)
    return deepcopy(raw)


def open_payload(raw, profile, policy, balance):
    keys(raw, "side orderType workflow entry quantity sl tp riskPercent observations")
    require(raw["side"] in ("LONG", "SHORT") and raw["orderType"] in ("MARKET", "LIMIT", "STOP"), "order")
    require(raw["workflow"] in ("QUICK", "PLANNED") and
            (raw["workflow"] != "QUICK" or raw["orderType"] == "MARKET"), "workflow")
    entry, size = price(raw["entry"], profile), quantity(raw["quantity"], profile)
    sl = None if raw["sl"] is None else price(raw["sl"], profile)
    tp = None if raw["tp"] is None else price(raw["tp"], profile)
    direction = 1 if raw["side"] == "LONG" else -1
    require((sl is None or direction * (entry - sl) > 0) and
            (tp is None or direction * (tp - entry) > 0), "protectiveGeometry", "REFUSED_GEOMETRY")
    require(raw["workflow"] != "PLANNED" or (sl is not None and tp is not None), "plannedLevels")
    require(type(raw["observations"]) is list and len(raw["observations"]) <= 64, "observations")
    observations = []
    for observation in raw["observations"]:
        keys(observation, "conditionId outcome")
        observations.append(Observation(observation["conditionId"], observation["outcome"]))
    outcomes = {o.condition_id: o.outcome for o in observations}
    require(len(outcomes) == len(observations) and set(outcomes).issubset(policy.conditions), "observations")
    risk = exact(raw["riskPercent"], "riskPercent", True)
    require(risk <= 100, "riskPercent")
    if policy.kind == "PROTOCOL":
        require(raw["workflow"] == "PLANNED" and raw["orderType"] in ("LIMIT", "STOP"), "protocolType", "PROTOCOL_BLOCKED")
        require(risk == Fraction(policy.risk_percent) and abs(tp-entry) == abs(entry-sl) * Fraction(policy.rr),
                "protocolRiskRR", "PROTOCOL_BLOCKED")
        require(size == Fraction(risk_quantity(text(Fraction(balance)*risk/100), raw["entry"], raw["sl"], profile)),
                "protocolQuantity", "PROTOCOL_BLOCKED")
        require(not policy.checklist_on or all(outcomes.get(c) == "PASS" for c in policy.conditions), "checklist", "PROTOCOL_BLOCKED")
    return dict(side=raw["side"], orderType=raw["orderType"], workflow=raw["workflow"],
                entry=text(entry), quantity=text(size), sl=None if sl is None else text(sl),
                tp=None if tp is None else text(tp), riskPercent=text(risk), observations=deepcopy(raw["observations"]))


def seed_state(session_id, dataset_id, dataset_version, start_ns, profile, policy, balance="10000"):
    identifier(session_id, "sessionId"); identifier(dataset_id, "datasetId"); digest(dataset_version, "datasetVersion"); uint(start_ns)
    p = profile_wire(profile)
    initial = money(exact(balance, "balance", True), p["moneyScale"])
    seed = dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-SEED-1", sessionId=session_id,
                datasetId=dataset_id, datasetVersion=dataset_version, profile=p, policy=policy_wire(policy), initialBalance=initial)
    return dict(schemaVersion=1, artifact="BTL-TICK-EXECUTION-STATE-1", sessionId=session_id,
                datasetId=dataset_id, datasetVersion=dataset_version, engineVersion=ENGINE_VERSION,
                profile=p, profileHash=content_hash(dict(schemaVersion=1, artifact="BTL-EXECUTION-PROFILE-1", profile=p)),
                policy=policy_wire(policy), revision=0, initialBalance=initial, balance=initial,
                realizedGross="0", commission="0", throughNs=start_ns, orders={}, unresolved=False,
                ended=False, financial=False, nextGroupIndex="0", nextEventIndex=0,
                eventHash=content_hash(seed), parent=None)


def validate_state(state):
    tag(state, "BTL-TICK-EXECUTION-STATE-1", "sessionId datasetId datasetVersion engineVersion profile profileHash policy revision initialBalance balance realizedGross commission throughNs orders unresolved ended financial nextGroupIndex nextEventIndex eventHash parent")
    require(state["engineVersion"] == ENGINE_VERSION, "engine", "REFUSED_ENGINE_VERSION")
    revision(state["revision"]); revision(state["nextEventIndex"])
    uint(state["throughNs"]); uint(state["nextGroupIndex"])
    identifier(state["sessionId"], "sessionId"); identifier(state["datasetId"], "datasetId")
    digest(state["datasetVersion"], "datasetVersion"); digest(state["eventHash"], "eventHash")
    require(profile_wire(state["profile"]) == state["profile"] and
            content_hash(dict(schemaVersion=1, artifact="BTL-EXECUTION-PROFILE-1", profile=state["profile"])) == state["profileHash"], "profile", "CORRUPT_RECORD")
    policy_from_wire(state["policy"])
    require(type(state["orders"]) is dict and len(state["orders"]) <= MAX_ORDERS, "orders", "REFUSED_STATE_LIMIT")
    require(all(type(state[k]) is bool for k in ("unresolved", "ended", "financial")), "stateFlags")
    require(Fraction(state["balance"]) == Fraction(state["initialBalance"]) + Fraction(state["realizedGross"]) - Fraction(state["commission"]), "account", "CORRUPT_RECORD")
    canonical_bytes(state)
    return state
