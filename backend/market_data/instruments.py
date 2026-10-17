"""Requested local catalogue only; this does not enable execution profiles."""
from dataclasses import dataclass
from types import MappingProxyType
from contracts.primitives import require

@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    base: str
    quote: str
    kind: str

_SYMBOLS = ("AUDUSD", "EURGBP", "NZDUSD", "USDCHF", "AUDJPY", "CADJPY",
            "EURUSD", "GBPUSD", "NZDJPY", "USDCAD", "CHFJPY", "EURJPY",
            "EURNZD", "GBPJPY", "USDJPY", "XAUUSD")
INSTRUMENTS = MappingProxyType({s: InstrumentSpec(s, s[:3], s[3:],
    "GOLD" if s == "XAUUSD" else "FX") for s in _SYMBOLS})

def instrument(symbol):
    require(type(symbol) is str and symbol in INSTRUMENTS, "symbol", "UNSUPPORTED_INSTRUMENT")
    return INSTRUMENTS[symbol]
