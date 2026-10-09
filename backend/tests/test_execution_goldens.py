"""Authored frozen financial expectations; no engine import or oracle generation."""
import json
from pathlib import Path
import unittest
from decimal import Decimal
from fractions import Fraction

GOLDENS = Path(__file__).with_name("fixtures") / "tick_execution_v1.json"


def goldens():
    return json.loads(GOLDENS.read_text(encoding="utf-8"))


class FinancialMaterializationTests(unittest.TestCase):
    def test_frozen_coverage_and_authored_exact_results(self):
        data = goldens()
        self.assertEqual(data["artifact"], "BTL-TICK-EXECUTION-GOLDENS-1")
        cases = {c["id"]: c for c in data["scenarios"]}
        self.assertEqual(len(cases), 24)
        required = {"market-long", "market-short", "market-next-eligible", "buy-limit-improvement",
                    "sell-limit-improvement", "buy-stop-gap", "sell-stop-gap", "long-sl-gap",
                    "short-sl-gap", "long-tp-gap", "short-tp-gap", "activation-same-event-exit",
                    "trusted-tie", "equivalent-untrusted-tie", "changing-untrusted-tie",
                    "cancel-before-trigger", "trigger-before-cancel", "partial-then-full-fixed-commission",
                    "fixed-commission", "invalid-tick", "invalid-lot", "no-eligible-quote",
                    "unknown-quality", "money-half-even"}
        self.assertEqual(set(cases), required)
        for c in cases.values():
            Decimal(c["balance"])
            self.assertTrue(c["rows"])
            self.assertIn("fills", c)
            for kind, price in c["fills"]:
                self.assertIn(kind, {"ENTRY_FILL", "EXIT_FILL"})
                self.assertGreater(Decimal(price), 0)
        self.assertEqual(len(data["transactionGoldens"]), 7)

    def test_independent_financial_arithmetic(self):
        cases = {c["id"]: c for c in goldens()["scenarios"]}
        for name, c in cases.items():
            if len(c["fills"]) != 2 or name == "money-half-even":
                continue
            direction = 1 if c["open"]["side"] == "LONG" else -1
            gross = direction * (Fraction(c["fills"][1][1]) - Fraction(c["fills"][0][1])) * 100 * Fraction(c["open"]["quantity"])
            cost = 2 * Fraction(c.get("commission", "0")) * Fraction(c["open"]["quantity"])
            self.assertEqual(Fraction(c["balance"]), 10000 + gross - cost, name)
        self.assertEqual(Fraction("0.04") * 100 * (103 - 101) - Fraction("0.16"), Fraction("7.84"))
        self.assertEqual(Fraction("0.06") * 100 * (104 - 101) - Fraction("0.24"), Fraction("17.76"))


if __name__ == "__main__":
    unittest.main()
