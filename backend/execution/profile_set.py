"""Stage 2 of multi-pair: a pinned, ordered SET of per-instrument v2 execution profiles (authored synthetic only; not wired into any Session yet).

The set fixes (a) which instruments a Session may trade, (b) their order (the instrument index used by the multi-instrument timeline tie-break) and
(c) which conversion route every non-USD-quoted instrument needs, and whether that route is itself a member of the set (so one timeline feeds both).
Each member is validated by the existing v2 profile contract (`ExecutionProfileV2`): contract size, lot rules, commission and a conversion pin with its maximum rate age.
"""
from contracts.canonical import content_hash
from contracts.primitives import require
from market_data.instruments import instrument
from .conversion import conversion_route
from .profile_v2 import ExecutionProfileV2

MAX_INSTRUMENTS = 16


class ProfileSet:
    def __init__(self, wires):
        require(type(wires) is list and 1 <= len(wires) <= MAX_INSTRUMENTS, "profiles", "REFUSED_INSTRUMENT_SET")
        profiles = [ExecutionProfileV2.from_wire(w) for w in wires]
        symbols = [p.wire["symbol"] for p in profiles]
        require(len(set(symbols)) == len(symbols), "profiles", "REFUSED_INSTRUMENT_SET")
        self.profiles, self.symbols = profiles, symbols

    @property
    def profile_set_hash(self):
        """Order matters: the position of a profile is its instrument index."""
        return content_hash(dict(schemaVersion=1, artifact="BTL-EXECUTION-PROFILE-SET-1", symbols=self.symbols, profileHashes=[p.profile_hash for p in self.profiles]))

    def index_of(self, symbol):
        require(symbol in self.symbols, "symbol", "REFUSED_INSTRUMENT_SET")
        return self.symbols.index(symbol)

    def conversion_needs(self):
        """symbol -> route symbol, for every instrument whose quote currency is not USD (a USD-quoted instrument needs none)."""
        needs = {}
        for p in self.profiles:
            w = p.wire
            if w["quoteCurrency"] != "USD":
                needs[w["symbol"]] = conversion_route(w["quoteCurrency"])[0]
        return needs

    def conversion_resolution(self):
        """For each non-USD instrument: IN_SET when its route symbol is a member (one shared timeline), otherwise EXTERNAL (a separate conversion feed must be pinned)."""
        return {symbol: ("IN_SET" if route in self.symbols else "EXTERNAL") for symbol, route in self.conversion_needs().items()}

    def conversion_age_limits_ns(self):
        """The maximum accepted age of the conversion quote for each non-USD instrument (from its own pin)."""
        return {p.wire["symbol"]: int(p.wire["conversion"]["maxAgeNs"]) for p in self.profiles if p.wire["conversion"] is not None}
