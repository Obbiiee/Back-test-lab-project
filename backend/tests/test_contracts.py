import ast
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

from contracts.canonical import canonical_bytes, content_hash, decimal_text, utc_text
from contracts.primitives import ContractError, assert_current, decimal, revision
from contracts.models import (Observation, MethodPolicy, SessionContext, Command, ReviewedRequest, Receipt,
                              EvidenceEvent, Passport, LineageEntry, ResearchJobInput, TemporalObservation,
                              validate_command, validate_action, classify_retry, job_transition, time_bounded_view)
from contracts.models import ConfirmedRequest, validate_confirmation, validate_event_context
from contracts.models import ResearchJobState, validate_job_input

H = "a" * 64
NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def sample(kind="FREE_STYLE", on=False):
    policy = MethodPolicy("method", H, kind, on, ("setup",), "1" if kind == "PROTOCOL" else None,
                          "2" if kind == "PROTOCOL" else None)
    context = SessionContext("workspace", "session", policy, "XAUUSD", "feed", H, 4, 7, NOW, "101")
    command = Command("workspace", "session", "request", "method", H, "XAUUSD", "feed", H, 4, 7,
                      "PLANNED", "BUY", "LIMIT", "100", "2", "1", "99", "102", "plan", 0)
    return policy, context, command


def decode(value):
    if isinstance(value, dict):
        if set(value) == {"$decimal"}:
            return Decimal(value["$decimal"])
        if set(value) == {"$timestamp"}:
            return datetime.fromisoformat(value["$timestamp"].replace("Z", "+00:00"))
        return {k: decode(v) for k, v in value.items()}
    return [decode(v) for v in value] if isinstance(value, list) else value


class CanonicalTests(unittest.TestCase):
    def test_independent_golden_vectors(self):
        vectors = json.loads((Path(__file__).parent / "fixtures" / "contract_hash_vectors.json").read_text(encoding="utf-8"))
        for v in vectors:
            with self.subTest(v["name"]):
                value = decode(v["input"])
                self.assertEqual(canonical_bytes(value).decode(), v["canonical"])
                for _ in range(3):
                    self.assertEqual(content_hash(value), v["sha256"])

    def test_order_null_types_and_schema(self):
        a = {"schemaVersion": 1, "z": None, "a": [1, 2]}
        self.assertEqual(content_hash(a), content_hash(dict(reversed(list(a.items())))))
        self.assertNotEqual(content_hash(a), content_hash({"schemaVersion": 1, "a": [1, 2]}))
        self.assertNotEqual(content_hash(a), content_hash({**a, "a": [2, 1]}))
        for v in (1.0, float("nan"), float("inf"), {1: "key"}, "\ud800", object(), 2**53):
            with self.subTest(v=repr(v)), self.assertRaises(ContractError):
                canonical_bytes({"schemaVersion": 1, "value": v})
        for v in ({}, {"schemaVersion": True}, {"schemaVersion": 2}):
            with self.assertRaises(ContractError): canonical_bytes(v)
        cycle = []; cycle.append(cycle)
        with self.assertRaises(ContractError): canonical_bytes({"schemaVersion": 1, "value": cycle})
        with self.assertRaises(ContractError): canonical_bytes({"schemaVersion": 1, "value": [[0]*4096]*5})

    def test_decimal_and_time_context_independence(self):
        for value, expected in (("-0.000", "0"), ("1.2300", "1.23"), ("1e3", "1000"), ("1e-7", "0.0000001")):
            self.assertEqual(decimal_text(Decimal(value)), expected)
        number = Decimal("123456789012345678901234567890.123456789")
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(decimal_text(number), "123456789012345678901234567890.123456789")
        self.assertEqual(utc_text(NOW.astimezone(timezone(timedelta(hours=7)))), "2024-01-01T00:00:00.000000Z")
        with self.assertRaises(ContractError): utc_text(datetime(2024, 1, 1))
        for v in (True, 1.1, "NaN", Decimal("Infinity"), " 1", "01", "1e1001", "1e-1001"):
            with self.subTest(v=repr(v)), self.assertRaises(ContractError): decimal(v)


class CommandTests(unittest.TestCase):
    def test_immutable_and_independent_scope(self):
        _, ctx, command = sample()
        self.assertIs(validate_command(command, ctx), command)
        with self.assertRaises(FrozenInstanceError): command.entry = Decimal(2)
        with self.assertRaises(ContractError): replace(command, observations=[Observation("setup", "PASS")])
        for name in ("workspace_id", "session_id", "method_id", "instrument_id", "feed_id"):
            with self.subTest(name=name), self.assertRaises(ContractError): validate_command(replace(command, **{name: "other"}), ctx)
        with self.assertRaises(ContractError): replace(command, observations=(Observation("setup", "PASS"), Observation("setup", "FAIL")))
        with self.assertRaises(ContractError): validate_command(replace(command, observations=(Observation("unknown", "PASS"),)), ctx)
        for name, value in (("request_id", ""), ("method_hash", "x"), ("side", "buy"), ("entry", "NaN"),
                            ("quantity", "0"), ("risk_percent", "101"), ("session_revision", True), ("plan_revision", -1)):
            with self.subTest(name=name), self.assertRaises(ContractError): replace(command, **{name: value})

    def test_revision_and_price_relations(self):
        for v in (-1, True, 1.1, "1", 2**53):
            with self.assertRaises(ContractError): revision(v)
        with self.assertRaisesRegex(ContractError, "STALE_REVISION"): assert_current(4, 7, 5, 7)
        _, ctx, c = sample()
        for name, value in (("session_revision", 3), ("quote_revision", 6), ("sl", "100"), ("tp", "99"), ("entry", "101")):
            with self.subTest(name=name), self.assertRaises(ContractError): validate_command(replace(c, **{name: value}), ctx)
        sell = replace(c, side="SELL", order_type="STOP", entry="100", sl="101", tp="98")
        self.assertIs(validate_command(sell, ctx), sell)
        quick = replace(c, workflow="QUICK", order_type="MARKET", entry="101", sl=None, tp=None, plan_id=None, plan_revision=None)
        self.assertIs(validate_command(quick, ctx), quick)
        with self.assertRaises(ContractError): validate_command(replace(quick, entry="102"), ctx)

    def test_protocol_on_off_categorical_and_exact_rr(self):
        for on in (False, True):
            p, ctx, c = sample("PROTOCOL", on)
            if on:
                with self.assertRaisesRegex(ContractError, "PROTOCOL_BLOCKED"): validate_command(c, ctx)
            else:
                self.assertIs(validate_command(c, ctx), c)
            passed = replace(c, observations=(Observation("setup", "PASS"),))
            self.assertIs(validate_command(passed, ctx), passed)
            for outcome in ("FAIL", "NOT_ASSESSED"):
                observation = replace(c, observations=(Observation("setup", outcome),))
                if on:
                    with self.assertRaises(ContractError): validate_command(observation, ctx)
                else:
                    self.assertIs(validate_command(observation, ctx), observation)
            for change in ({"risk_percent": "2"}, {"tp": "103"}, {"order_type": "MARKET", "entry": "101"},
                           {"workflow": "QUICK", "order_type": "MARKET", "entry": "101", "plan_id": None, "plan_revision": None}):
                with self.assertRaises(ContractError): validate_command(replace(passed, **change), ctx)
            for action in ("MANUAL_CLOSE", "PARTIAL_CLOSE", "AMEND_EXITS"):
                with self.assertRaises(ContractError): validate_action(p, action)
            validate_action(p, "CANCEL_PENDING")
            with localcontext() as decimal_context:
                decimal_context.prec = 2
                precise = replace(passed, entry="100.123456789", sl="99.123456789", tp="102.123456789")
                validate_command(precise, ctx)
        with self.assertRaises(ContractError): replace(p, conditions=("setup", "setup"))
        with self.assertRaises(ContractError): Observation("setup", "COMPLIANT")

    def test_review_receipt_conflicts_without_durable_claim(self):
        _, ctx, c = sample()
        reviewed = ReviewedRequest(c, content_hash(c.identity_payload()), NOW)
        self.assertIs(validate_confirmation(ConfirmedRequest(reviewed, NOW), ctx), c)
        with self.assertRaises(ContractError): ConfirmedRequest(reviewed, NOW-timedelta(seconds=1))
        receipt = Receipt("receipt", "workspace", "session", "request", reviewed.payload_hash, 5, ("event",))
        self.assertIs(classify_retry(reviewed, receipt), receipt)
        # Retry comparison remains usable after Session advances; new command is stale.
        with self.assertRaises(ContractError): validate_command(c, replace(ctx, session_revision=5))
        with self.assertRaisesRegex(ContractError, "IDEMPOTENCY_CONFLICT"): classify_retry(reviewed, replace(receipt, payload_hash="b"*64))
        with self.assertRaisesRegex(ContractError, "IDENTITY_MISMATCH"): classify_retry(reviewed, replace(receipt, workspace_id="other"))
        with self.assertRaises(ContractError): ReviewedRequest(c, "b"*64, NOW)
        with self.assertRaises(ContractError): replace(receipt, event_ids=())


class EvidenceTests(unittest.TestCase):
    def test_passport_lineage_event_job_contracts(self):
        passport = Passport("experiment", "workspace", "dataset", "v1", H, H, H, H, "engine1", "calc1", "XAUUSD", "feed", NOW, NOW, 4, "trial")
        self.assertEqual(content_hash(passport.identity_payload()), content_hash(replace(passport, start=NOW.astimezone(timezone(timedelta(hours=7)))).identity_payload()))
        for change in ({"end": NOW-timedelta(seconds=1)}, {"seed": 1}, {"dataset_hash": ""}, {"log_revision": -1}):
            with self.assertRaises(ContractError): replace(passport, **change)
        event = EvidenceEvent("event", "workspace", "session", "request", H, H, 0, 4, "engine1", "REFUSED", "PROTOTYPE", NOW, NOW)
        with self.assertRaises(ContractError): replace(event, source="BROWSER_TRUSTED")
        _, ctx, _ = sample()
        self.assertIs(validate_event_context(event, ctx), event)
        with self.assertRaisesRegex(ContractError, "FUTURE_OBSERVATION"):
            validate_event_context(replace(event, market_time=NOW+timedelta(seconds=1)), ctx)
        lineage = LineageEntry("trial", "workspace", "experiment", "family", H, "EXPLORATORY", "ABANDONED", NOW)
        with self.assertRaises(ContractError): replace(lineage, parent_trial_id="trial")
        job = ResearchJobInput("job", "workspace", H, H, "calc1", H, NOW, 3)
        with self.assertRaises(ContractError): replace(job, max_attempts=True)
        with self.assertRaises(ContractError): replace(job, rng_algorithm="rng")
        bound_job = replace(job, passport_hash=content_hash(passport.identity_payload()), deadline=NOW+timedelta(seconds=5))
        self.assertIs(validate_job_input(bound_job, passport, NOW), bound_job)
        with self.assertRaises(ContractError): validate_job_input(bound_job, passport, NOW+timedelta(seconds=5))
        with self.assertRaises(ContractError): validate_job_input(replace(bound_job, workspace_id="other"), passport, NOW)
        state = ResearchJobState("job", "SUCCEEDED", 1, H)
        with self.assertRaises(ContractError): replace(state, state="RUNNING")
        with self.assertRaises(ContractError): ResearchJobState("job", "FAILED", 1)
        with self.assertRaises(ContractError): ResearchJobState("job", "RUNNING", 0)
        for state, target in (("QUEUED", "RUNNING"), ("RUNNING", "CANCEL_REQUESTED"), ("CANCEL_REQUESTED", "CANCELLED")):
            self.assertEqual(job_transition(state, target), target)
        for state, target in (("SUCCEEDED", "RUNNING"), ("QUEUED", "SUCCEEDED"), ("CANCEL_REQUESTED", "SUCCEEDED"), ("UNKNOWN", "FAILED")):
            with self.assertRaises(ContractError): job_transition(state, target)

    def test_physical_future_truncation_and_future_perturbation(self):
        prefix = tuple(TemporalObservation(NOW+timedelta(seconds=i), str(i)) for i in range(3))
        future = TemporalObservation(NOW+timedelta(seconds=10), "100")
        boundary = NOW+timedelta(seconds=2)
        self.assertEqual(time_bounded_view(prefix+(future,), boundary), time_bounded_view(prefix, boundary))
        changed = replace(future, value="999999999999999")
        self.assertEqual(time_bounded_view(prefix+(changed,), boundary), prefix)
        self.assertEqual(time_bounded_view(prefix+(changed,), NOW-timedelta(seconds=1)), ())
        with self.assertRaises(ContractError): time_bounded_view(tuple(reversed(prefix)), boundary)
        with self.assertRaises(ContractError): TemporalObservation(datetime(2024, 1, 1), "1")

    def test_framework_independence(self):
        allowed = {"re", "datetime", "decimal", "hashlib", "json", "collections", "dataclasses", "fractions"}
        for path in (Path(__file__).parents[1] / "contracts").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(n.name.split('.')[0] in allowed for n in node.names), path.name)
                if isinstance(node, ast.ImportFrom) and not node.level:
                    self.assertIn(node.module.split('.')[0], allowed, path.name)


if __name__ == "__main__":
    unittest.main()
