"""Stage 2 (profile set) and the informational margin arithmetic. No database."""
import json
import unittest
from fractions import Fraction
from pathlib import Path

from contracts.primitives import ContractError
from execution.margin import MarginRules, margin_account, required_margin
from execution.profile_set import ProfileSet
from tests.test_execution_goldens import goldens

VECTORS = json.loads((Path(__file__).parent / "fixtures/execution_profiles_v2.json").read_text())["vectors"]
WIRES = [v["input"] for v in VECTORS]


class Set(unittest.TestCase):
    def test_all_sixteen_instruments_form_one_set_and_every_conversion_route_is_a_member(self):
        s = ProfileSet(WIRES)
        self.assertEqual(len(s.symbols), 16)
        needs = s.conversion_needs()
        self.assertEqual(len(needs), 11)                                           # matches the instrument matrix: 11 of the 16 are not USD-quoted
        self.assertEqual(set(needs.values()), {"GBPUSD", "NZDUSD", "USDJPY", "USDCAD", "USDCHF"})
        self.assertEqual(set(s.conversion_resolution().values()), {"IN_SET"})      # one timeline can feed instrument and conversion
        self.assertTrue(all(1 <= v <= 60_000_000_000 for v in s.conversion_age_limits_ns().values()))
        usd_quoted = {"AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "XAUUSD"}
        self.assertEqual(set(s.symbols) - set(needs), usd_quoted)

    def test_order_is_part_of_the_identity_and_the_index(self):
        a, b = ProfileSet(WIRES), ProfileSet(list(reversed(WIRES)))
        self.assertNotEqual(a.profile_set_hash, b.profile_set_hash)
        self.assertEqual(a.profile_set_hash, ProfileSet(WIRES).profile_set_hash)
        self.assertEqual(a.index_of(a.symbols[3]), 3)

    def test_a_non_usd_instrument_without_its_route_is_reported_external(self):
        subset = [w for w in WIRES if w["symbol"] in ("EURJPY", "EURUSD")]       # EURJPY needs USDJPY, which is not in this set
        self.assertEqual(ProfileSet(subset).conversion_resolution(), {"EURJPY": "EXTERNAL"})

    def test_invalid_sets_are_refused(self):
        for bad in ([], [WIRES[0], WIRES[0]], WIRES + [WIRES[0]], [goldens()["profile"]]):
            with self.assertRaises((ContractError, ValueError), msg=str(len(bad))):
                ProfileSet(bad)


class Margin(unittest.TestCase):
    def test_required_margin_is_exact(self):
        r = MarginRules(leverage=100)
        self.assertEqual(required_margin("0.1", "100", "2000", r), Fraction(200))           # 0.1 lot gold at 2000 with 1:100
        self.assertEqual(required_margin("1", "100000", "1.10", MarginRules(leverage=30)), Fraction(11000, 3))   # EURUSD 1 lot at 1.10 with 1:30 = 3,666.67
        with self.assertRaises(ContractError):
            MarginRules(leverage=0)

    def test_levels_and_status_labels(self):
        r = MarginRules(leverage=100, margin_call_pct=Fraction(100), stop_out_pct=Fraction(50))
        ok = margin_account("10000", "0", "200", r)
        self.assertEqual((ok["freeMargin"], ok["marginLevelPct"], ok["status"]), ("9800", "5000", "OK"))
        call = margin_account("10000", "-9900", "200", r)                                    # equity 100 on 200 used = 50%: at the stop-out level
        self.assertEqual((call["marginLevelPct"], call["status"]), ("50", "STOP_OUT"))
        mid = margin_account("10000", "-9850", "200", r)                                     # equity 150 on 200 = 75%
        self.assertEqual((mid["marginLevelPct"], mid["status"]), ("75", "MARGIN_CALL"))
        none = margin_account("10000", "0", "0", r)
        self.assertEqual((none["marginLevelPct"], none["status"], none["informational"]), (None, "OK", True))

    def test_rules_must_be_ordered(self):
        with self.assertRaises(ContractError):
            MarginRules(leverage=100, margin_call_pct=Fraction(40), stop_out_pct=Fraction(50))


if __name__ == "__main__":
    unittest.main()
