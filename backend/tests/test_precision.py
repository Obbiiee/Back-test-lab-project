import unittest
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from decimal import localcontext

from contracts.primitives import ContractError
from precision.evaluator import Quote, Request, evaluate, evidence_bytes, load_evidence


def request(**changes):
    return replace(Request("synthetic", "v1", "a"*64, "XAUUSD", "authored", "liquidation-v1", "LONG",
                           10, 30, "99", "101", 0, 30, True), **changes)


def quote(name, time, bid="100", ask="100.1", **changes):
    return Quote(name, time, bid, ask, **changes)


class PrecisionTests(unittest.TestCase):
    def test_reversed_paths_same_ranges(self):
        tp = evaluate(request(), (quote("a", 11, "102", "102.1"), quote("b", 12, "98", "98.1")))
        sl = evaluate(request(), (quote("a", 11, "98", "98.1"), quote("b", 12, "102", "102.1")))
        self.assertEqual((tp.reason, sl.reason), ("TP", "SL"))
        self.assertEqual(tp.observed_price, "102")  # observed quote, not invented 101 fill

    def test_exit_sides(self):
        q = (quote("a", 11, "100", "102"),)
        self.assertEqual(evaluate(request(), q).classification, "NO_OBSERVED_CROSSING")
        self.assertEqual(evaluate(request(side="SHORT", sl="101", tp="99"), q).reason, "SL")

    def test_ties_and_trusted_sequence(self):
        q = (quote("a", 11, "102", "102.1", source_sequence=1),
             quote("b", 11, "98", "98.1", source_sequence=2))
        self.assertEqual(evaluate(request(), q).reason, "TIMESTAMP_TIE")
        self.assertEqual(evaluate(request(trusted_sequence=True), q).reason, "TP")
        self.assertEqual(evaluate(request(trusted_sequence=True), q[::-1]).reason, "INVALID_SOURCE_SEQUENCE")

    def test_activation(self):
        self.assertEqual(evaluate(request(), (quote("a", 9, "102", "102.1"), quote("b", 11))).classification,
                         "NO_OBSERVED_CROSSING")
        self.assertEqual(evaluate(request(), (quote("a", 10),)).reason, "ACTIVATION_ORDER_UNKNOWN")

    def test_quality_refusal(self):
        for q, expected in ((quote("a", 11, gap_before=True), "COVERAGE_GAP"),
                            (quote("a", 11, ask=None), "MISSING_SIDE"),
                            (quote("a", 11, fresh=False), "STALE_QUOTE"),
                            (quote("a", 11, "102", "100"), "CROSSED_QUOTE")):
            with self.subTest(expected=expected):
                self.assertEqual(evaluate(request(), (q,)).reason, expected)
        self.assertEqual(evaluate(request(coverage_complete=False), ()).reason, "INSUFFICIENT_COVERAGE")
        self.assertEqual(evaluate(request(coverage_end_ns=29), ()).reason, "INSUFFICIENT_COVERAGE")

    def test_chronology_and_duplicates(self):
        for quotes in ((quote("a", 12), quote("b", 11)), (quote("a", 11), quote("a", 12))):
            self.assertEqual(evaluate(request(), quotes).reason, "INVALID_CHRONOLOGY")

    def test_hidden_suffix_and_immutability(self):
        q = (quote("a", 11),)
        before = evaluate(request(), q)
        self.assertEqual(before, evaluate(request(), q + (quote("future", 31, "999", "1000"),)))
        self.assertEqual(before, evaluate(request(), q))
        with self.assertRaises(FrozenInstanceError):
            q[0].bid = "50"
        self.assertNotEqual(before.evidence_hash, evaluate(request(dataset_version="v2"), q).evidence_hash)

    def test_decimal_context_independence(self):
        q = (quote("a", 11, "101.00000000000000000001", "101.00000000000000000002"),)
        with localcontext() as context:
            context.prec = 2
            low = evaluate(request(), q)
        self.assertEqual(low, evaluate(request(), q))
        self.assertEqual(low.observed_price, "101.00000000000000000001")

    def test_invalid_contract_and_bounds(self):
        for make in (lambda: quote("a", 11, 100.1), lambda: quote("a", True),
                     lambda: request(sl="102"), lambda: request(dataset_hash="bad")):
            with self.assertRaises(ContractError):
                make()
        with self.assertRaises(ContractError):
            evaluate(request(), [])
        with self.assertRaises(ContractError):
            evaluate(request(horizon_ns=5000, coverage_end_ns=5000),
                     tuple(quote(str(i), i+11) for i in range(4097)))

    def test_exact_serialization_and_maximum_chunk(self):
        q = (quote("a", 11, "100.000000000000000001", "100.1"),)
        raw = evidence_bytes(request(), q)
        parsed = json.loads(raw)
        self.assertEqual(parsed["quotes"][0]["bid"], "100.000000000000000001")
        self.assertEqual(parsed["quotes"][0]["timeNs"], "11")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), evaluate(request(), q).evidence_hash)
        restored, events = load_evidence(raw, hashlib.sha256(raw).hexdigest())
        self.assertEqual((restored, events), (request(), q))
        self.assertEqual(evaluate(restored, events), evaluate(request(), q))
        q = tuple(quote(str(i), i+11) for i in range(1024))
        self.assertEqual(evaluate(request(horizon_ns=2000, coverage_end_ns=2000), q).classification,
                         "NO_OBSERVED_CROSSING")

    def test_load_refuses_corruption_and_unknown_fields(self):
        raw = evidence_bytes(request(), ())
        with self.assertRaises(ContractError):
            load_evidence(raw + b" ", hashlib.sha256(raw).hexdigest())
        data = json.loads(raw)
        data["unrecognized"] = True
        from contracts.canonical import canonical_bytes
        altered = canonical_bytes(data)
        with self.assertRaises(ContractError):
            load_evidence(altered, hashlib.sha256(altered).hexdigest())
        data.pop("unrecognized")
        data["activationNs"] = "9" * 5000
        altered = canonical_bytes(data)
        with self.assertRaises(ContractError):
            load_evidence(altered, hashlib.sha256(altered).hexdigest())


if __name__ == "__main__":
    unittest.main()
