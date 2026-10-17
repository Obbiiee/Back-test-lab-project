"""Pure authored-v2 financial proposals, never a simulated-fill commit."""
from fractions import Fraction
from contracts.primitives import require
from ticks.contracts import CanonicalTick, keys, uint
from ticks.timeline import make_group
from .contracts import exact, money, text
from .conversion import convert_usd
from .profile_v2 import ExecutionProfileV2


def rational(value):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator))


def _profile(profile):
    require(type(profile) is ExecutionProfileV2, "profile", "REFUSED_V2_PROFILE")
    return profile.wire


def price(value, p):
    value = exact(value, "price", True)
    require((value / exact(p["tickSize"], "tick")).denominator == 1, "price", "REFUSED_PRICE_PRECISION")
    return value


def quantity(value, p):
    value = exact(value, "quantity", True)
    require((value / exact(p["lotStep"], "step")).denominator == 1, "quantity", "REFUSED_LOT_PRECISION")
    require(exact(p["minLot"], "min") <= value <= exact(p["maxLot"], "max"), "quantity", "REFUSED_LOT_BOUNDS")
    return value


def _usd(value, p, as_of, group):
    result = convert_usd(text(value), p["quoteCurrency"], as_of, pin=p["conversion"],
                         group=group, money_scale=p["moneyScale"])
    ratio = result["usdExact"]
    return Fraction(int(ratio["numerator"]), int(ratio["denominator"])), result


def _quote(p, group, side, opening, as_of):
    require(side in ("LONG", "SHORT"), "side")
    keys(group, "groupId timeNs order events")
    require(group["timeNs"] == as_of and uint(as_of) >= 0, "time", "REFUSED_V2_PRIMARY_TIME")
    require(type(group["events"]) is list and 1 <= len(group["events"]) <= 1024, "group")
    rows = [CanonicalTick.from_wire(r).wire for r in group["events"]]
    source = p["primary"]
    seen = set()
    for row in rows:
        require(row["timeNs"] == as_of and row["eventId"] not in seen, "group", "REFUSED_V2_PRIMARY_GROUP")
        seen.add(row["eventId"])
        require(all(row[k] == source[k] for k in ("datasetId", "datasetVersion", "providerId", "feedId"))
                and row["instrumentId"] == source["feedInstrumentId"], "identity", "REFUSED_V2_PRIMARY_IDENTITY")
        q = row["quality"]
        require(q["quote"] == "VALID" and q["freshness"] == "CONFIRMED" and q["gapBefore"] in ("NONE", "KNOWN_SESSION_CLOSED"),
                "quality", "UNRESOLVED_V2_PRIMARY_QUALITY")
        price(row["bid"], p)
        price(row["ask"], p)
    require(make_group(rows, source["datasetVersion"]) == group, "group", "REFUSED_V2_PRIMARY_GROUP")
    require(len({(r["bid"], r["ask"]) for r in rows}) == 1, "group", "UNRESOLVED_V2_PRIMARY_AMBIGUOUS")
    quote_side = "ask" if (side == "LONG") == opening else "bid"
    value = price(rows[0][quote_side], p)
    return value, dict(groupId=group["groupId"], timeNs=as_of, order=group["order"], side=quote_side,
                       eventIds=[r["eventId"] for r in rows])


def entry_proposal(profile, side, lots, as_of_ns, primary_group):
    p = _profile(profile)
    size = quantity(lots, p)
    fill, proof = _quote(p, primary_group, side, True, as_of_ns)
    fee = size * exact(p["commissionPerLotSide"], "fee")
    posted = money(fee, p["moneyScale"])
    return dict(artifact="BTL-V2-ENTRY-PROPOSAL-1", model="AUTHORED_SYNTHETIC_ONLY",
                profileHash=profile.profile_hash, timeNs=as_of_ns, price=text(fill), quantity=text(size),
                commissionExact=rational(fee), commissionPosted=posted, cashDelta=text(-Fraction(posted)), evidence=proof)


def exit_proposal(profile, side, entry_price, lots, as_of_ns, primary_group, *, conversion_group=None):
    p = _profile(profile)
    size, entry = quantity(lots, p), price(entry_price, p)
    fill, proof = _quote(p, primary_group, side, False, as_of_ns)
    gross_quote = (1 if side == "LONG" else -1) * (fill - entry) * exact(p["contractSize"], "contract") * size
    gross_usd, conversion = _usd(gross_quote, p, as_of_ns, conversion_group)
    fee = size * exact(p["commissionPerLotSide"], "fee")
    gross_posted, fee_posted = money(gross_usd, p["moneyScale"]), money(fee, p["moneyScale"])
    return dict(artifact="BTL-V2-EXIT-PROPOSAL-1", model="AUTHORED_SYNTHETIC_ONLY",
                profileHash=profile.profile_hash, timeNs=as_of_ns, price=text(fill), quantity=text(size),
                quoteCurrency=p["quoteCurrency"], grossQuoteExact=rational(gross_quote), grossUsdExact=rational(gross_usd),
                grossPosted=gross_posted, commissionExact=rational(fee), commissionPosted=fee_posted,
                cashDelta=text(Fraction(gross_posted) - Fraction(fee_posted)), evidence=proof, conversion=conversion)


def allocate_entry_cost(posted_cost, original_lots, closed_before, closing_lots, allocated_before):
    cost, total = exact(posted_cost, "entryCost"), exact(original_lots, "originalLots", True)
    before, closing = exact(closed_before, "closedBefore"), exact(closing_lots, "closingLots", True)
    keys(allocated_before, "numerator denominator")
    # Allocation fractions can have more digits than timestamp uints.
    n, d = allocated_before["numerator"], allocated_before["denominator"]
    require(all(type(v) is str and 1 <= len(v) <= 128 and v.isascii() and v.isdigit()
                and str(int(v)) == v for v in (n, d)) and d != "0", "allocation", "REFUSED_V2_COST_ALLOCATION")
    prior = Fraction(int(n), int(d))
    require(str(prior.numerator) == n and str(prior.denominator) == d,
            "allocation", "REFUSED_V2_COST_ALLOCATION")
    require(cost >= 0 and 0 <= before < total and before + closing <= total and prior == cost * before / total,
            "allocation", "REFUSED_V2_COST_ALLOCATION")
    allocated = cost - prior if before + closing == total else cost * closing / total
    return rational(allocated)


def planned_risk(profile, side, entry_price, stop_price, budget_usd, as_of_ns, *, conversion_group=None):
    p = _profile(profile)
    uint(as_of_ns)
    require(side in ("LONG", "SHORT"), "side")
    entry, stop, budget = price(entry_price, p), price(stop_price, p), exact(budget_usd, "budget", True)
    require((1 if side == "LONG" else -1) * (entry - stop) > 0, "stop", "REFUSED_GEOMETRY")
    loss_quote = -abs(entry - stop) * exact(p["contractSize"], "contract")
    loss, conversion = _usd(loss_quote, p, as_of_ns, conversion_group)
    fee, step = exact(p["commissionPerLotSide"], "fee"), exact(p["lotStep"], "step")
    per_lot = -loss + 2 * fee
    require(per_lot > 0, "riskDistance")
    def candidate(available):
        ratio = available / per_lot / step
        return (ratio.numerator // ratio.denominator) * step
    def posted_risk(size):
        return -Fraction(money(loss * size, p["moneyScale"])) + 2 * Fraction(money(fee * size, p["moneyScale"]))
    size = candidate(budget)
    if size > 0 and posted_risk(size) > budget:
        buffer = Fraction(1 + (2 if fee else 0), 2 * 10 ** p["moneyScale"])
        require(budget > buffer, "budget", "REFUSED_LOT_BOUNDS")
        size = candidate(budget - buffer)
    size = quantity(text(size), p)
    require(posted_risk(size) <= budget, "budget", "REFUSED_V2_RISK_BUDGET")
    return dict(artifact="BTL-V2-RISK-PROPOSAL-1", model="AUTHORED_SYNTHETIC_ONLY", profileHash=profile.profile_hash,
                timeNs=as_of_ns, quantity=text(size), budgetUsd=text(budget), lossPerLotUsdExact=rational(-loss),
                plannedLossUsdExact=rational(size * per_lot), hypotheticalPostedRiskUsd=text(posted_risk(size)),
                conversion=conversion, guarantee="NOT_A_FILL_OR_FUTURE_RATE_GUARANTEE")
