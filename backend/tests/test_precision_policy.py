import hashlib
import json
import unittest
import subprocess
import sys
import tempfile
from pathlib import Path
from dataclasses import FrozenInstanceError, replace

from contracts.primitives import ContractError
from precision.evaluator import evidence_bytes
from precision.policy import ReviewedEvidence, assess, assessment_bytes
from tests.test_precision import request, quote


def declared(req, quotes, **overrides):
    values = dict(coverage_ref="authored:coverage", freshness_ref="authored:paired-update",
                  sequence_ref="authored:sequence")
    values.update(overrides)
    return ReviewedEvidence(hashlib.sha256(evidence_bytes(req, quotes)).hexdigest(), **values)


class PrecisionPolicyTests(unittest.TestCase):
    def test_no_reference_no_promotion(self):
        req, quotes = request(), (quote("a", 11, "102", "102.1"),)
        report = assess(req, quotes)
        self.assertEqual(report.status, "AMBIGUOUS")
        self.assertIn("COVERAGE_UNVERIFIED", report.issues)
        self.assertIn("SIDE_FRESHNESS_UNVERIFIED", report.issues)
        self.assertIsNone(report.quote_decision.event_id)

    def test_observed_quote_is_never_broker_fill(self):
        req, quotes = request(), (quote("a", 11, "102", "102.1"),)
        report = assess(req, quotes, declared(req, quotes))
        self.assertEqual(report.status, "OBSERVED_QUOTE_CROSSING")
        self.assertEqual((report.quote_decision.reason, report.quote_decision.observed_price), ("TP", "102"))
        self.assertEqual(report.execution_status, "NOT_SIMULATED")
        self.assertIsNone(report.fill_price)
        self.assertIsNone(report.pnl)

    def test_reference_cannot_upgrade_false_flags(self):
        req, quotes = request(coverage_complete=False), (quote("a", 11, fresh=False),)
        report = assess(req, quotes, declared(req, quotes))
        self.assertEqual(report.status, "AMBIGUOUS")
        self.assertIn("COVERAGE_UNVERIFIED", report.issues)
        self.assertIn("SIDE_FRESHNESS_UNVERIFIED", report.issues)

    def test_freshness_reference_required(self):
        req, quotes = request(), (quote("a", 11, "102", "102.1"),)
        report = assess(req, quotes, declared(req, quotes, freshness_ref=None))
        self.assertEqual(report.status, "AMBIGUOUS")
        self.assertIn("SIDE_FRESHNESS_UNVERIFIED", report.issues)

    def test_ties_require_sequence_reference_and_actual_sequence(self):
        req = request(trusted_sequence=True)
        quotes = (quote("a", 11, "102", "102.1", source_sequence=1),
                  quote("b", 11, "98", "98.1", source_sequence=2))
        unknown = assess(req, quotes, declared(req, quotes, sequence_ref=None))
        self.assertEqual(unknown.status, "AMBIGUOUS")
        self.assertIn("ORDER_WITHIN_TIMESTAMP_UNVERIFIED", unknown.issues)
        self.assertEqual(assess(req, quotes, declared(req, quotes)).quote_decision.reason, "TP")
        quotes = tuple(replace(q, source_sequence=None) for q in quotes)
        self.assertEqual(assess(req, quotes, declared(req, quotes)).status, "AMBIGUOUS")

    def test_silence_is_diagnostic_not_a_completeness_or_closure_proof(self):
        req = request(horizon_ns=100_000_000_000, coverage_end_ns=100_000_000_000)
        quotes = (quote("a", 11), quote("b", 70_000_000_011))
        report = assess(req, quotes)
        self.assertEqual((report.status, report.observed_silences), ("AMBIGUOUS", 1))
        self.assertEqual(report.max_interval_ns, "70000000000")
        no_silence = assess(req, (quotes[0],))
        self.assertEqual((no_silence.status, no_silence.observed_silences), ("AMBIGUOUS", 0))

    def test_gap_activation_and_missing_side_stay_unknown(self):
        for quotes, issue in (((quote("a", 11, gap_before=True),), "DECLARED_DATA_GAP"),
                              ((quote("a", 10),), "ACTIVATION_ORDER_UNKNOWN"),
                              ((quote("a", 11, ask=None),), "MISSING_SIDE")):
            req = request()
            with self.subTest(issue=issue):
                report = assess(req, quotes, declared(req, quotes))
                self.assertEqual(report.status, "AMBIGUOUS")
                self.assertIn(issue, report.issues)

    def test_evidence_cannot_move_between_artifacts(self):
        req, quotes = request(), (quote("a", 11),)
        evidence = declared(req, quotes)
        with self.assertRaises(ContractError):
            assess(request(dataset_version="different"), quotes, evidence)
        with self.assertRaises(ContractError):
            assess(req, (quote("a", 12),), evidence)

    def test_immutable_canonical_report_and_future_invariance(self):
        req, quotes = request(), (quote("a", 11),)
        report = assess(req, quotes)
        self.assertEqual(report, assess(req, quotes + (quote("future", 31, "1000", "1001"),)))
        wire = assessment_bytes(report)
        data = json.loads(wire)
        self.assertEqual((data["status"], data["executionStatus"], data["pnl"]),
                         ("AMBIGUOUS", "NOT_SIMULATED", None))
        self.assertEqual(wire, assessment_bytes(assess(req, quotes)))
        with self.assertRaises(FrozenInstanceError):
            report.status = "TP"
        with self.assertRaises(ContractError):
            assessment_bytes(replace(report, status="TP"))

    def test_no_crossing_is_only_about_observed_quotes(self):
        req, quotes = request(), (quote("a", 11),)
        report = assess(req, quotes, declared(req, quotes))
        self.assertEqual(report.status, "NO_OBSERVED_CROSSING")
        self.assertEqual(report.quote_decision.reason, "SUPPLIED_INTERVAL_ONLY")

    def test_input_bounds(self):
        for value in (True, 0, -1, 600_000_000_001):
            with self.assertRaises(ContractError):
                assess(request(), (), silence_warning_ns=value)

    def test_financial_claims_cannot_be_inserted(self):
        report = assess(request(), ())
        for change in (dict(pnl="10"), dict(fill_price="101"), dict(execution_status="FILLED")):
            with self.assertRaises(ContractError):
                replace(report, **change)

    def test_local_cli_does_not_accept_certainty_overrides(self):
        raw = evidence_bytes(request(), (quote("a", 11, "102", "102.1"),))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"authored.json"
            path.write_bytes(raw)
            result = subprocess.run([sys.executable, "-m", "precision.policy", "--artifact", str(path),
                                     "--sha256", hashlib.sha256(raw).hexdigest()],
                                    capture_output=True, text=True, check=True, timeout=20)
        data = json.loads(result.stdout)
        self.assertEqual((data["status"], data["executionStatus"]), ("AMBIGUOUS", "NOT_SIMULATED"))
        self.assertEqual(data["issueScope"], "SUPPLIED_REVEALED_INTERVAL")


if __name__ == "__main__":
    unittest.main()
