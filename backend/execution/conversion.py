"""Unmounted controller-only conversion primitive; not settlement authority.

Caller must already prove complete group/evidence acceptance through the pinned
provider/timeline. This arithmetic seam cannot authenticate a client quote.
"""
from copy import deepcopy
from contracts.primitives import digest, identifier, require
from ticks.contracts import CanonicalTick, keys, uint
from ticks.timeline import make_group
from .contracts import exact, money, text

_ROUTES = {"GBP": ("GBPUSD", "MULTIPLY"), "NZD": ("NZDUSD", "MULTIPLY"),
           "JPY": ("USDJPY", "DIVIDE"), "CAD": ("USDCAD", "DIVIDE"),
           "CHF": ("USDCHF", "DIVIDE")}
_PIN_FIELDS = "currency symbol datasetId datasetVersion providerId feedId feedInstrumentId maxAgeNs"


def conversion_route(currency):
    """Immutable descriptive route; does not accept evidence or select quotes."""
    require(type(currency) is str and currency in _ROUTES, "currency", "REFUSED_FX_ROUTE")
    return _ROUTES[currency]


def convert_usd(amount, currency, as_of_ns, *, pin=None, group=None, money_scale=2):
    value = exact(amount, "foreignCash")
    as_of = uint(as_of_ns, "asOfNs")
    require(type(money_scale) is int and 0 <= money_scale <= 8, "moneyScale")
    require(type(currency) is str and currency in {"USD", *_ROUTES}, "currency", "REFUSED_FX_ROUTE")
    evidence = None
    if currency == "USD":
        require(pin is None and group is None, "identityEvidence", "REFUSED_FX_IDENTITY")
        converted = value
    else:
        require(pin is not None and group is not None, "evidence", "UNRESOLVED_FX_MISSING")
        keys(pin, _PIN_FIELDS)
        pin = deepcopy(pin)
        for field in ("datasetId", "providerId", "feedId", "feedInstrumentId"):
            identifier(pin[field], field)
        digest(pin["datasetVersion"], "datasetVersion")
        age_limit = uint(pin["maxAgeNs"], "maxAgeNs")
        require(1 <= age_limit <= 60000000000, "maxAgeNs", "REFUSED_FX_AGE_LIMIT")
        symbol, operation = conversion_route(currency)
        require(pin["currency"] == currency and pin["symbol"] == symbol,
                "route", "REFUSED_FX_ROUTE")
        keys(group, "groupId timeNs order events")
        require(type(group["events"]) is list and 1 <= len(group["events"]) <= 1024,
                "group", "UNRESOLVED_FX_GROUP")
        rows = [CanonicalTick.from_wire(row).wire for row in group["events"]]
        moment = uint(group["timeNs"], "groupTimeNs")
        require(moment <= as_of, "time", "UNRESOLVED_FX_FUTURE")
        require(as_of - moment <= age_limit, "time", "UNRESOLVED_FX_STALE")
        seen = set()
        for row in rows:
            require(row["timeNs"] == group["timeNs"], "time", "UNRESOLVED_FX_GROUP")
            require(all(row[field] == pin[field] for field in ("datasetId", "datasetVersion", "providerId", "feedId"))
                    and row["instrumentId"] == pin["feedInstrumentId"], "identity", "UNRESOLVED_FX_IDENTITY")
            require(row["eventId"] not in seen, "eventId", "UNRESOLVED_FX_GROUP")
            seen.add(row["eventId"])
            quality = row["quality"]
            require(quality["quote"] == "VALID" and quality["freshness"] == "CONFIRMED"
                    and quality["gapBefore"] in ("NONE", "KNOWN_SESSION_CLOSED"),
                    "quality", "UNRESOLVED_FX_QUALITY")
        require(make_group(rows, pin["datasetVersion"]) == group, "group", "UNRESOLVED_FX_GROUP")
        require(len({(row["bid"], row["ask"]) for row in rows}) == 1,
                "prices", "UNRESOLVED_FX_AMBIGUOUS")
        side = ("bid" if value >= 0 else "ask") if operation == "MULTIPLY" else ("ask" if value >= 0 else "bid")
        rate = exact(rows[0][side], "conversionRate", True)
        converted = value * rate if operation == "MULTIPLY" else value / rate
        evidence = dict(pin=pin, groupId=group["groupId"], timeNs=group["timeNs"], order=group["order"],
                        events=[dict(eventId=r["eventId"], provenance=deepcopy(r["provenance"]),
                                     evidenceHash=r["quality"]["evidenceHash"]) for r in rows],
                        symbol=symbol, operation=operation, side=side, price=text(rate))
    return dict(artifact="BTL-USD-CONVERSION-FOUNDATION-1", policy="UNMOUNTED_SIMULATION_CONVENTION",
                currency=currency, amount=text(value), asOfNs=as_of_ns, moneyScale=money_scale,
                usdExact=dict(numerator=str(converted.numerator), denominator=str(converted.denominator)),
                usdRounded=money(converted, money_scale), evidence=evidence)
