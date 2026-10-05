"""Documentation/fixture checks only; NOT a provider, timeline or fill engine.

The sole synthetic fixture owner is blueprint 42.15. Real feed certification and
future runtime behavior require separate implementation and behavioral tests.
"""
import json
from pathlib import Path
import re
import unittest
from decimal import Decimal

from contracts.canonical import canonical_bytes, content_hash, decimal_text
from contracts.primitives import decimal


ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = ROOT / "docs/PRODUCT_SYSTEM_ARCHITECTURE_BLUEPRINT.md"


def fixture_matrix():
    text = BLUEPRINT.read_text(encoding="utf-8")
    marker = "<!-- BTL-TICK-CONTRACT-FIXTURES-1 -->"
    if text.count(marker) != 1:
        raise ValueError("one normative fixture owner required")
    match = re.search(r"```json\s*(.*?)\s*```", text.split(marker, 1)[1], re.S)
    if not match:
        raise ValueError("fixture block absent")
    def reject_float(_):
        raise ValueError("authoritative fixture float forbidden")
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result
    return json.loads(match[1], parse_float=reject_float,
                      parse_constant=reject_float, object_pairs_hook=unique_keys)


class TickContractSpecificationTests(unittest.TestCase):
    def setUp(self):
        self.matrix = fixture_matrix()
        self.cases = {case["id"]: case for case in self.matrix["cases"]}

    def test_single_owner_synthetic_and_no_financial_outputs(self):
        self.assertEqual(self.matrix["artifact"], "BTL-TICK-CONTRACT-FIXTURES-1")
        self.assertEqual(self.matrix["schemaVersion"], 1)
        self.assertEqual(self.matrix["evidenceClass"], "SYNTHETIC_CONTRACT_ONLY")
        self.assertEqual(len(self.cases), len(self.matrix["cases"]))
        self.assertEqual(len(self.cases), 15)
        serialized = canonical_bytes(self.matrix)
        self.assertEqual(content_hash(self.matrix), content_hash(json.loads(serialized)))
        for forbidden in ('"fillPrice"', '"pnl"', '"brokerFill"', '"settled"'):
            self.assertNotIn(forbidden, serialized.decode())

    def test_exact_values_and_reused_quote_compatibility(self):
        from precision.evaluator import Quote
        for case in self.cases.values():
            for row in case.get("rows", []):
                self.assertEqual(set(row), {"ordinal", "timeNs", "bid", "ask", "sequence"})
                for key in ("ordinal", "timeNs", "sequence"):
                    value = row[key]
                    if value is not None:
                        self.assertIsInstance(value, str)
                        self.assertRegex(value, r"^(0|[1-9][0-9]*)$")
                        self.assertLessEqual(int(value), 10**22)
                for side in ("bid", "ask"):
                    if row[side] is not None:
                        value = decimal(row[side], positive=True)
                        self.assertEqual(decimal_text(value), row[side])
                # Compatibility projection only: never promote fixture freshness.
                quote = Quote("synthetic:" + row["ordinal"], int(row["timeNs"]),
                              row["bid"], row["ask"],
                              None if row["sequence"] is None else int(row["sequence"]),
                              fresh=False)
                self.assertFalse(quote.fresh)
                self.assertEqual(quote.time_ns, int(row["timeNs"]))

    def test_scenario_preconditions_and_declared_outcomes(self):
        expected = {
            "normal_ordered": "ORDERED_SINGLETONS", "changing_spread": "PRESERVE_SPREAD",
            "trusted_tie": "ATOMIC_TRUSTED_GROUP", "untrusted_tie": "UNRESOLVED_ORDER",
            "duplicate_delivery": "REJECT_DUPLICATE_DELIVERY",
            "repeated_source_quote": "PRESERVE_DISTINCT_EVENTS",
            "timestamp_reversal": "REJECT_ORDER_REVERSAL", "gap": "UNRESOLVED_COVERAGE",
            "missing_side": "UNRESOLVED_QUOTE", "crossed_quote": "UNRESOLVED_QUOTE",
            "market_jump": "OBSERVED_JUMP_NO_FILL", "multiple_levels": "NO_INTERMEDIATE_PATH_OR_FILL",
            "ambiguous_activation": "UNRESOLVED_ACTIVATION",
            "malformed_price": "QUARANTINE_LOCATED_RECORD",
            "unlocated_timestamp": "REJECT_UNLOCATED_INVALID_RECORD",
        }
        self.assertEqual({key: value["expected"] for key, value in self.cases.items()}, expected)
        rows = lambda key: self.cases[key]["rows"]
        self.assertLess(int(rows("normal_ordered")[0]["timeNs"]), int(rows("normal_ordered")[1]["timeNs"]))
        spreads = [Decimal(r["ask"]) - Decimal(r["bid"]) for r in rows("changing_spread")]
        self.assertNotEqual(*spreads)
        for key in ("trusted_tie", "untrusted_tie", "ambiguous_activation"):
            self.assertEqual(rows(key)[0]["timeNs"], rows(key)[1]["timeNs"])
        self.assertLess(int(rows("trusted_tie")[0]["sequence"]), int(rows("trusted_tie")[1]["sequence"]))
        self.assertTrue(all(r["sequence"] is None for r in rows("untrusted_tie")))
        self.assertEqual(*rows("duplicate_delivery"))
        self.assertNotEqual(rows("repeated_source_quote")[0]["ordinal"], rows("repeated_source_quote")[1]["ordinal"])
        self.assertEqual(rows("repeated_source_quote")[0]["bid"], rows("repeated_source_quote")[1]["bid"])
        self.assertGreater(int(rows("timestamp_reversal")[0]["timeNs"]), int(rows("timestamp_reversal")[1]["timeNs"]))
        gap = self.cases["gap"]["gap"]
        self.assertLess(int(rows("gap")[0]["timeNs"]), int(gap["startNs"]))
        self.assertLess(int(gap["startNs"]), int(gap["endNs"]))
        self.assertEqual(gap["endNs"], rows("gap")[1]["timeNs"])
        self.assertIsNone(rows("missing_side")[0]["ask"])
        self.assertGreater(Decimal(rows("crossed_quote")[0]["bid"]), Decimal(rows("crossed_quote")[0]["ask"]))
        for key in ("market_jump", "multiple_levels"):
            for level in self.cases[key]["levels"]:
                self.assertLess(Decimal(rows(key)[0]["bid"]), Decimal(level))
                self.assertGreater(Decimal(rows(key)[1]["bid"]), Decimal(level))
        self.assertEqual(self.cases["ambiguous_activation"]["activationNs"], rows("ambiguous_activation")[0]["timeNs"])
        self.assertEqual(self.cases["ambiguous_activation"]["relation"], "UNKNOWN_SAME_TIME")
        with self.assertRaises(ValueError):
            decimal(self.cases["malformed_price"]["raw"]["bid"], positive=True)
        self.assertFalse(self.cases["unlocated_timestamp"]["raw"]["timeNs"].isdigit())

    def test_contract_reference_and_version_boundary(self):
        text = BLUEPRINT.read_text(encoding="utf-8").split("## 42.15 ", 1)[1]
        for tag in ("BTL-CANONICAL-TICK-1", "BTL-TICK-MANIFEST-1", "BTL-TICK-CHUNK-1",
                    "BTL-TICK-CURSOR-1", "BTL-TICK-REVEAL-1", "BTL-TICK-PAGE-1"):
            self.assertIn(tag, text)
        roadmap = (ROOT / "docs/ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("#4215-", roadmap)
        self.assertIn("UNVERIFIED / NOT ACQUIRED", text)
        self.assertIn("only after separate human authorization", text.lower())


if __name__ == "__main__":
    unittest.main()
