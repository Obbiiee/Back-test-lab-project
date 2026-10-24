"""Additive execution v2 profile codec.

Authored synthetic demos, plus owner-admitted HistData months (2026-10-24,
free beta) through an explicit admission overlay. No v1 dispatch changes.
"""
from dataclasses import dataclass
import json
from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import digest, identifier, require
from market_data.instruments import instrument
from ticks.contracts import keys, uint
from .contracts import exact, text
from .conversion import conversion_route

ENGINE_VERSION = "BTL-TICK-EXECUTION-2"
SYNTHETIC_MODEL, ADMITTED_MODEL = "AUTHORED_SYNTHETIC_ONLY", "HISTORICAL_ADMITTED_V1"
_FIELDS = ("schemaVersion artifact engineVersion model symbol baseCurrency quoteCurrency accountCurrency "
           "primary conversion tickSize priceScale contractSize lotStep minLot maxLot moneyScale "
           "commissionModel commissionPerLotSide commissionCurrency slippageModel latencyModel")


def _source(source, model=SYNTHETIC_MODEL, symbol=None):
    keys(source, "datasetId datasetVersion providerId feedId feedInstrumentId evidenceClass")
    for field in ("datasetId", "providerId", "feedId", "feedInstrumentId"):
        identifier(source[field], field)
    digest(source["datasetVersion"], "datasetVersion")
    if model == ADMITTED_MODEL:
        # Only an admission overlay; raw provider observations stay refused.
        require(source["providerId"] == "histdata" and source["evidenceClass"] == "ADMITTED_OBSERVATION"
                and source["datasetId"].startswith("admitted:histdata:" + symbol + ":")
                and source["feedId"] == "local-unverified:" + symbol and source["feedInstrumentId"] == "histdata:" + symbol,
                "source", "REFUSED_V2_REAL_SOURCE")
        return
    require(source["providerId"] == "SYNTHETIC" and source["datasetId"].startswith("synthetic:")
            and source["evidenceClass"] == "SYNTHETIC_CONTRACT_ONLY", "source", "REFUSED_V2_REAL_SOURCE")


def validate_profile(raw):
    keys(raw, _FIELDS)
    require(type(raw["schemaVersion"]) is int and raw["schemaVersion"] == 1
            and raw["artifact"] == "BTL-EXECUTION-PROFILE-2" and raw["engineVersion"] == ENGINE_VERSION,
            "version", "REFUSED_V2_VERSION")
    require(raw["model"] in (SYNTHETIC_MODEL, ADMITTED_MODEL), "model", "REFUSED_V2_MODEL")
    spec = instrument(raw["symbol"])
    require((raw["baseCurrency"], raw["quoteCurrency"], raw["accountCurrency"]) == (spec.base, spec.quote, "USD"),
            "currencies", "REFUSED_V2_CURRENCY")
    _source(raw["primary"], raw["model"], raw["symbol"])
    conversion = raw["conversion"]
    # Admitted conversion sources are a later checkpoint: USD-quote symbols only.
    require(raw["model"] == SYNTHETIC_MODEL or spec.quote == "USD", "conversion", "REFUSED_V2_ROUTE")
    if spec.quote == "USD":
        require(conversion is None, "conversion", "REFUSED_V2_ROUTE")
    else:
        keys(conversion, "currency symbol datasetId datasetVersion providerId feedId feedInstrumentId maxAgeNs")
        route, _ = conversion_route(spec.quote)
        require(conversion["currency"] == spec.quote and conversion["symbol"] == route,
                "conversion", "REFUSED_V2_ROUTE")
        _source({**{k: conversion[k] for k in ("datasetId", "datasetVersion", "providerId", "feedId", "feedInstrumentId")},
                 "evidenceClass": "SYNTHETIC_CONTRACT_ONLY"})
        require(1 <= uint(conversion["maxAgeNs"], "maxAgeNs") <= 60000000000, "maxAgeNs", "REFUSED_FX_AGE_LIMIT")
    values = {}
    for field in ("tickSize", "priceScale", "contractSize", "lotStep", "minLot", "maxLot", "commissionPerLotSide"):
        require(type(raw[field]) is str, field)
        value = exact(raw[field], field, field != "commissionPerLotSide")
        require(text(value) == raw[field], field, "NONCANONICAL_FINANCIAL_VALUE")
        values[field] = value
    require(values["priceScale"] in {10 ** i for i in range(19)}
            and (values["tickSize"] * values["priceScale"]).denominator == 1, "precision", "REFUSED_PRICE_PRECISION")
    require(values["contractSize"] == (100 if spec.kind == "GOLD" else 100000),
            "contractSize", "REFUSED_SIMULATED_LOT_CONVENTION")
    require(values["minLot"] <= values["maxLot"] and all((values[f] / values["lotStep"]).denominator == 1
            for f in ("minLot", "maxLot")), "lotBounds", "REFUSED_LOT_BOUNDS")
    require(type(raw["moneyScale"]) is int and 0 <= raw["moneyScale"] <= 8, "moneyScale")
    require(raw["commissionModel"] in ("NONE", "FIXED_PER_LOT_SIDE")
            and values["commissionPerLotSide"] >= 0
            and (raw["commissionModel"] != "NONE" or values["commissionPerLotSide"] == 0)
            and raw["commissionCurrency"] == "USD" and raw["slippageModel"] == "NONE"
            and raw["latencyModel"] == "ZERO", "costs", "REFUSED_V2_COST_MODEL")
    return canonical_bytes(raw)


@dataclass(frozen=True)
class ExecutionProfileV2:
    _bytes: bytes

    def __post_init__(self):
        require(type(self._bytes) is bytes and len(self._bytes) <= 16384, "profileBytes")
        require(validate_profile(json.loads(self._bytes)) == self._bytes, "canonicalProfile")

    @classmethod
    def from_wire(cls, raw):
        return cls(validate_profile(raw))

    @property
    def wire(self):
        return json.loads(self._bytes)

    @property
    def profile_hash(self):
        return content_hash(self.wire)
