"""Conservative disclosure ahead of the existing evaluator; no settlement.

Evidence references are reviewed caller declarations, not provider certification.
They may downgrade existing flags, never promote missing evidence to known.
Legacy BTL-TICK-EVIDENCE-1 bytes/semantics remain unchanged.
"""
from dataclasses import asdict, dataclass, replace
import hashlib

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import digest, identifier, require
from .evaluator import Decision, evaluate, evidence_bytes, load_evidence

VERSION = "BTL-PRECISION-POLICY-1"


@dataclass(frozen=True)
class ReviewedEvidence:
    artifact_hash: str
    coverage_ref: str | None = None
    freshness_ref: str | None = None
    sequence_ref: str | None = None

    def __post_init__(self):
        digest(self.artifact_hash, "artifact_hash")
        for field in ("coverage_ref", "freshness_ref", "sequence_ref"):
            value = getattr(self, field)
            if value is not None:
                identifier(value, field)


@dataclass(frozen=True)
class Assessment:
    status: str
    issues: tuple[str, ...]
    quote_decision: Decision
    input_hash: str
    policy_hash: str
    declared_evidence: ReviewedEvidence | None
    observed_silences: int
    max_interval_ns: str
    silence_warning_ns: str
    policy_version: str = VERSION
    execution_status: str = "NOT_SIMULATED"
    fill_price: None = None
    pnl: None = None
    issue_scope: str = "SUPPLIED_REVEALED_INTERVAL"

    def __post_init__(self):
        require(type(self.quote_decision) is Decision, "quote_decision")
        expected = {"UNRESOLVED": "AMBIGUOUS", "OBSERVED_CROSSING": "OBSERVED_QUOTE_CROSSING",
                    "NO_OBSERVED_CROSSING": "NO_OBSERVED_CROSSING"}
        require(type(self.status) is str and self.status in expected.values() and
                self.status == expected.get(self.quote_decision.classification), "assessment_status")
        require(type(self.issues) is tuple and all(type(issue) is str for issue in self.issues), "issues")
        digest(self.input_hash, "input_hash")
        if self.policy_hash:
            digest(self.policy_hash, "policy_hash")
        require(self.execution_status == "NOT_SIMULATED" and self.fill_price is None and self.pnl is None,
                "no_financial_execution")
        require(self.policy_version == VERSION and self.issue_scope == "SUPPLIED_REVEALED_INTERVAL",
                "policy_version")


def _payload(report):
    return {"schemaVersion": 1, "artifact": report.policy_version,
            "status": report.status, "issues": report.issues,
            "quoteDecision": asdict(report.quote_decision), "inputHash": report.input_hash,
            "declaredEvidence": asdict(report.declared_evidence) if report.declared_evidence else None,
            "observedSilences": report.observed_silences, "maxIntervalNs": report.max_interval_ns,
            "silenceWarningNs": report.silence_warning_ns,
            "executionStatus": report.execution_status, "fillPrice": report.fill_price, "pnl": report.pnl,
            "issueScope": report.issue_scope}


def assessment_bytes(report):
    require(type(report) is Assessment, "assessment")
    payload = _payload(report)
    require(content_hash(payload) == report.policy_hash, "assessment_hash")
    return canonical_bytes({**payload, "policyHash": report.policy_hash})


def assess(request, quotes, reviewed=None, silence_warning_ns=60_000_000_000):
    """Only referenced affirmative claims can retain legacy certainty flags.

    Absence of observed long silences proves neither complete data nor closure.
    Invalid/missing flags cannot be upgraded by a reference. Missing freshness
    means unknown, not evidence that the quote actually was stale.
    """
    require(type(silence_warning_ns) is int and 0 < silence_warning_ns <= 600_000_000_000,
            "silence_warning_ns")
    raw = evidence_bytes(request, quotes)
    fingerprint = hashlib.sha256(raw).hexdigest()
    original, visible = load_evidence(raw, fingerprint)
    require(reviewed is None or type(reviewed) is ReviewedEvidence, "reviewed_evidence")
    if reviewed is not None:
        require(reviewed.artifact_hash == fingerprint, "evidence_scope")
    coverage = bool(reviewed and reviewed.coverage_ref and original.coverage_complete)
    freshness = bool(reviewed and reviewed.freshness_ref)
    sequence = bool(reviewed and reviewed.sequence_ref and original.trusted_sequence)
    effective = replace(original, coverage_complete=coverage, trusted_sequence=sequence)
    effective_quotes = tuple(replace(q, fresh=q.fresh and freshness) for q in visible)
    decision = evaluate(effective, effective_quotes)
    issues = []
    if not coverage:
        issues.append("COVERAGE_UNVERIFIED")
    if original.coverage_start_ns > original.activation_ns or original.coverage_end_ns < original.horizon_ns:
        issues.append("COVERAGE_OUTSIDE_INTERVAL")
    relevant = tuple(q for q in visible if q.time_ns >= original.activation_ns)
    if relevant and (not freshness or any(not q.fresh for q in relevant)):
        issues.append("SIDE_FRESHNESS_UNVERIFIED")
    if any(q.bid is None or q.ask is None for q in relevant):
        issues.append("MISSING_SIDE")
    if any(q.gap_before for q in relevant):
        issues.append("DECLARED_DATA_GAP")
    if any(q.time_ns == original.activation_ns for q in relevant):
        issues.append("ACTIVATION_ORDER_UNKNOWN")
    if not sequence and any(a.time_ns == b.time_ns for a, b in zip(relevant, relevant[1:])):
        issues.append("ORDER_WITHIN_TIMESTAMP_UNVERIFIED")
    if decision.classification == "UNRESOLVED" and decision.reason not in issues:
        issues.append(decision.reason)
    intervals = tuple(b.time_ns-a.time_ns for a, b in zip(relevant, relevant[1:]))
    # Diagnostic only: a long silence is not automatically an outage or closure.
    silences = sum(gap > silence_warning_ns for gap in intervals)
    status = ("AMBIGUOUS" if decision.classification == "UNRESOLVED" else
              "OBSERVED_QUOTE_CROSSING" if decision.classification == "OBSERVED_CROSSING" else
              "NO_OBSERVED_CROSSING")
    report = Assessment(status, tuple(issues), decision, fingerprint, "", reviewed,
                        silences, str(max((0, *intervals))), str(silence_warning_ns))
    return replace(report, policy_hash=content_hash(_payload(report)))


def main():
    """Local read-only audit CLI; never takes caller certainty overrides."""
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Audit exact tick evidence; no fill or PnL simulation")
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    with Path(args.artifact).open("rb") as stream:
        raw = stream.read(1048577)
    request, quotes = load_evidence(raw, args.sha256)
    print(assessment_bytes(assess(request, quotes)).decode("utf-8"))


if __name__ == "__main__":
    main()
