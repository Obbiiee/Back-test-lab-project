"""Prototype FX profiles for USD-quote pairs (QA only; NOT the frozen XAUUSD profile and not approved for product use).

The reference reducer hard-codes the XAUUSD instrument inside `observed_profile.validate_profile`. To exercise the SAME reducer on FX
we wrap that one validator: every non-instrument rule (model, slippage NONE, commission NONE, silence guard, source identity ...) is still
enforced by the original function (the FX profile is mapped onto the XAUUSD shape for that call); the instrument fields are checked
against the table below. Only pairs whose quote currency is USD are supported, because the profile has `conversion=None`
(no cross-currency P/L conversion exists in the reducer).
"""
import json
import execution.observed_profile as OP
from contracts.canonical import canonical_bytes
from contracts.primitives import require

FX = {  # symbol: (base, tickSize, priceScale, contractSize)
    "EURUSD": ("EUR", "0.00001", "100000", "100000"),
    "GBPUSD": ("GBP", "0.00001", "100000", "100000"),
    "AUDUSD": ("AUD", "0.00001", "100000", "100000"),
    "NZDUSD": ("NZD", "0.00001", "100000", "100000"),
}
_orig = OP.validate_profile


def _validate(raw):
    sym = raw.get("symbol") if isinstance(raw, dict) else None
    if sym not in FX:
        return _orig(raw)
    base, tick, scale, contract = FX[sym]
    require(raw.get("baseCurrency") == base and raw.get("quoteCurrency") == "USD" and raw.get("tickSize") == tick and
            raw.get("priceScale") == scale and raw.get("contractSize") == contract and raw["primary"].get("providerSymbol") == sym,
            "fxInstrument", "REFUSED_OBSERVED_MODEL_ASSUMPTION")
    xau = json.loads(json.dumps(raw))
    xau.update(symbol="XAUUSD", baseCurrency="XAU", tickSize="0.001", priceScale="1000", contractSize="100")
    xau["primary"]["providerSymbol"] = "XAUUSD"
    # QA-only knob: the frozen XAUUSD profile fixes the silence guard at 60 s. FX quotes are only published when the price changes, so
    # quiet minutes are normal; a local session may widen the guard (60 s..1 h). It stays a hard guard: longer silence = UNRESOLVED.
    guard = raw.get("maxObservedSilenceNs")
    require(type(guard) is str and guard.isdigit() and 60 * 10**9 <= int(guard) <= 3600 * 10**9, "maxObservedSilenceNs", "REFUSED_OBSERVED_MODEL_ASSUMPTION")
    xau["maxObservedSilenceNs"] = "60000000000"
    _orig(xau)                         # every remaining rule of the original validator still applies
    result = canonical_bytes(raw)
    require(len(result) <= 16384, "profileBytes")
    return result


def install():
    OP.validate_profile = _validate


def fx_profile_wire(base_wire, symbol, primary, silence_s=None):
    base, tick, scale, contract = FX[symbol]
    raw = json.loads(json.dumps(base_wire))
    raw.update(symbol=symbol, baseCurrency=base, quoteCurrency="USD", tickSize=tick, priceScale=scale, contractSize=contract)
    raw["primary"] = dict(primary, providerSymbol=symbol)
    if silence_s is not None:
        raw["maxObservedSilenceNs"] = str(int(silence_s) * 10**9)
    return raw
