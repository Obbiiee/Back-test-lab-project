import ast
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace, FrozenInstanceError
from datetime import timedelta
from pathlib import Path

from application.models import TrustedScope, ConfirmAssertions
from application.service import IntakeApplication
from contracts.models import Observation, TemporalObservation, time_bounded_view
from contracts.primitives import ContractError
from contracts.canonical import content_hash
from tests.application_fakes import WorkflowFake, FixedClock, FixedIds, sample, H, NOW


def setup(kind="FREE_STYLE", on=False):
    context, command = sample(kind, on)
    workflow, clock, ids = WorkflowFake(context), FixedClock(), FixedIds()
    return IntakeApplication(workflow, clock, ids), TrustedScope("workspace", "actor"), command


def assertions(reviewed):
    c = reviewed.command
    return ConfirmAssertions(c.session_id, c.request_id, reviewed.payload_hash, c.session_revision, c.quote_revision)


class IntakeTests(unittest.TestCase):
    def test_review_confirmation_nonexecution_and_determinism(self):
        outcomes = []
        for _ in range(3):
            app, scope, command = setup()
            reviewed = app.review_command(scope, command)
            self.assertEqual(app.workflow.outcomes, ())
            outcome = app.confirm_review(scope, assertions(reviewed))
            self.assertEqual(outcome.event.kind, "CONFIRMED")
            self.assertEqual(outcome.event.source, "PROTOTYPE")
            self.assertEqual(outcome.event.engine_version, "NO_EXECUTION")
            self.assertEqual(outcome.event.market_time, NOW)
            self.assertEqual(outcome.receipt.committed_revision, 4)
            self.assertEqual(app.workflow.contexts[("workspace", "session")].session_revision, 4)
            self.assertEqual(app.workflow.execution_calls, 0)
            with self.assertRaises(FrozenInstanceError): outcome.duplicate = True
            outcomes.append(outcome)
        self.assertEqual(outcomes[0], outcomes[1]); self.assertEqual(outcomes[1], outcomes[2])

    def test_duplicate_after_context_advances_and_payload_conflict(self):
        app, scope, command = setup()
        reviewed = app.review_command(scope, command)
        first = app.confirm_review(scope, assertions(reviewed))
        app.clock.time += timedelta(seconds=10)
        app.workflow.contexts[("workspace", "session")] = replace(app.workflow.contexts[("workspace", "session")],
                                                                session_revision=5, quote_revision=8)
        clock_calls, id_calls = app.clock.calls, len(app.ids.calls)
        duplicate = app.confirm_review(scope, assertions(reviewed))
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(duplicate.receipt, first.receipt); self.assertEqual(duplicate.event, first.event)
        self.assertEqual(duplicate.confirmed, first.confirmed)
        self.assertEqual((app.clock.calls, len(app.ids.calls)), (clock_calls, id_calls))
        self.assertEqual(len(app.workflow.outcomes), 1)
        with self.assertRaisesRegex(ContractError, "IDEMPOTENCY_CONFLICT"):
            app.confirm_review(scope, replace(assertions(reviewed), payload_hash="b"*64))
        with self.assertRaisesRegex(ContractError, "STALE_REVISION"):
            app.confirm_review(scope, replace(assertions(reviewed), session_revision=5))

    def test_concurrent_same_and_conflicting_confirmations(self):
        app, scope, command = setup()
        reviewed = app.review_command(scope, command)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: app.confirm_review(scope, assertions(reviewed)), range(32)))
        self.assertEqual(sum(not r.duplicate for r in results), 1)
        self.assertEqual(len(app.workflow.outcomes), 1)
        self.assertTrue(all(r.receipt == results[0].receipt and r.event == results[0].event for r in results))
        self.assertEqual(len(app.ids.calls), 2)
        def mixed(index):
            request = assertions(reviewed) if index % 2 == 0 else replace(assertions(reviewed), payload_hash="b"*64)
            try:
                return app.confirm_review(scope, request)
            except ContractError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=8) as pool:
            mixed_results = list(pool.map(mixed, range(16)))
        self.assertEqual(mixed_results[1::2], ["IDEMPOTENCY_CONFLICT"]*8)
        self.assertEqual(len(app.workflow.outcomes), 1)

    def test_scope_and_corrupt_port_records_refuse(self):
        app, scope, command = setup()
        for invalid_scope in (None, {"workspace_id": "workspace"}):
            with self.assertRaisesRegex(ContractError, "SCOPE_REQUIRED"): app.review_command(invalid_scope, command)
        self.assertEqual(app.workflow.run_calls, 0)
        with self.assertRaisesRegex(ContractError, "SCOPE_MISMATCH"):
            app.review_command(TrustedScope("other", "actor"), command)
        with self.assertRaisesRegex(ContractError, "RESOURCE_UNAVAILABLE"):
            app.review_command(scope, replace(command, session_id="foreign"))
        reviewed = app.review_command(scope, command)
        with self.assertRaises(ContractError): app.confirm_review(TrustedScope("other", "actor"), assertions(reviewed))
        app.workflow.reviews[("workspace", "session")]["request"] = replace(reviewed, command=replace(command, request_id="different"),
            payload_hash=content_hash(replace(command, request_id="different").identity_payload()))
        with self.assertRaises(ContractError): app.confirm_review(scope, assertions(reviewed))
        self.assertEqual(app.workflow.outcomes, ())

    def test_stale_invalid_identity_and_unknown_review(self):
        app, scope, command = setup()
        for change in ({"session_revision": 3}, {"quote_revision": 6}, {"method_hash": "b"*64}, {"profile_hash": "b"*64}, {"sl": "101"}):
            with self.subTest(change=change), self.assertRaises(ContractError): app.review_command(scope, replace(command, **change))
        with self.assertRaises(ContractError): app.review_command(scope, object())
        with self.assertRaises(ContractError): app.confirm_review(scope, ConfirmAssertions("session", "missing", H, 4, 7))
        reviewed = app.review_command(scope, command)
        for field in ("session_revision", "quote_revision", "profile_hash", "method"):
            original = app.workflow.contexts[("workspace", "session")]
            value = replace(original.method, definition_hash="b"*64) if field == "method" else "b"*64 if field == "profile_hash" else 9
            app.workflow.contexts[("workspace", "session")] = replace(original, **{field: value})
            with self.assertRaises(ContractError): app.confirm_review(scope, assertions(reviewed))
            app.workflow.contexts[("workspace", "session")] = original
        self.assertEqual(app.workflow.outcomes, ())

    def test_review_idempotence_edit_and_unchanged_snapshot(self):
        app, scope, command = setup()
        original = app.review_command(scope, command)
        app.clock.time += timedelta(seconds=5)
        self.assertIs(app.review_command(scope, command), original)
        with self.assertRaisesRegex(ContractError, "IDEMPOTENCY_CONFLICT"):
            app.review_command(scope, replace(command, quantity="3"))
        edited = app.review_command(scope, replace(command, request_id="edited", quantity="3"))
        self.assertNotEqual(edited.payload_hash, original.payload_hash)
        self.assertEqual(original.command.quantity, command.quantity)
        app.workflow.contexts[("workspace", "session")] = replace(app.workflow.contexts[("workspace", "session")], quote_revision=8)
        with self.assertRaisesRegex(ContractError, "STALE_REVISION"): app.review_command(scope, command)

    def test_protocol_on_off_and_quick(self):
        for on in (False, True):
            app, scope, c = setup("PROTOCOL", on)
            for outcome in ("FAIL", "NOT_ASSESSED"):
                changed = replace(c, request_id=outcome, observations=(Observation("setup", outcome),))
                if on:
                    with self.assertRaises(ContractError): app.review_command(scope, changed)
                else:
                    reviewed = app.review_command(scope, changed)
                    result = app.confirm_review(scope, assertions(reviewed))
                    self.assertEqual(result.confirmed.reviewed.command.observations, changed.observations)
            passed = replace(c, observations=(Observation("setup", "PASS"),))
            self.assertFalse(app.confirm_review(scope, assertions(app.review_command(scope, passed))).duplicate)
            for changes in ({"risk_percent": "2"}, {"tp": "103"}, {"order_type": "MARKET", "entry": "101"},
                            {"workflow": "QUICK", "order_type": "MARKET", "entry": "101", "plan_id": None, "plan_revision": None}):
                with self.assertRaises(ContractError): app.review_command(scope, replace(passed, request_id="invalid", **changes))
        app, scope, c = setup()
        quick = replace(c, workflow="QUICK", order_type="MARKET", entry="101", sl=None, tp=None, plan_id=None, plan_revision=None)
        self.assertFalse(app.confirm_review(scope, assertions(app.review_command(scope, quick))).duplicate)

    def test_failure_rollback_retry_and_context_race(self):
        for fault in ("clock", "id1", "id2", "commit", "race"):
            app, scope, c = setup()
            reviewed = app.review_command(scope, c)
            if fault == "clock": app.clock.fail = True
            if fault.startswith("id"): app.ids.fail_at = int(fault[-1])
            if fault == "commit": app.workflow.fail_commit = True
            if fault == "race":
                app.workflow.commit_hook = lambda workflow: workflow.contexts.update({("workspace", "session"):
                    replace(workflow.contexts[("workspace", "session")], quote_revision=8)})
            with self.subTest(fault=fault), self.assertRaises((ContractError, RuntimeError)):
                app.confirm_review(scope, assertions(reviewed))
            self.assertEqual(app.workflow.outcomes, ())
            self.assertEqual(app.workflow.reviews[("workspace", "session")]["request"], reviewed)
            app.clock.fail = False; app.ids.fail_at = None; app.workflow.fail_commit = False; app.workflow.commit_hook = None
            if fault == "race": app.workflow.contexts[("workspace", "session")] = replace(app.workflow.contexts[("workspace", "session")], quote_revision=7)
            result = app.confirm_review(scope, assertions(reviewed))
            self.assertFalse(result.duplicate); self.assertEqual(len(app.workflow.outcomes), 1)

    def test_future_truncation_and_no_execution_imports(self):
        observations = tuple(TemporalObservation(NOW+timedelta(seconds=i), str(101+i)) for i in range(3))
        outputs = []
        for data in (observations, observations[:1], (observations[0], replace(observations[1], value="999"), observations[2])):
            app, scope, c = setup()
            visible = time_bounded_view(data, NOW)
            app.workflow.contexts[("workspace", "session")] = replace(app.workflow.contexts[("workspace", "session")], quote=visible[-1].value)
            outputs.append(app.confirm_review(scope, assertions(app.review_command(scope, c))))
        self.assertEqual(outputs[0], outputs[1]); self.assertEqual(outputs[1], outputs[2])
        allowed = {"dataclasses", "datetime", "typing", "json", "logging", "contracts"}
        for path in (Path(__file__).parents[1] / "application").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import): self.assertTrue(all(x.name.split('.')[0] in allowed for x in node.names), path)
                if isinstance(node, ast.ImportFrom) and node.level == 0: self.assertIn(node.module.split('.')[0], allowed, path)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name): self.assertNotIn(node.func.id, {"exec", "eval", "__import__", "open"})


if __name__ == "__main__": unittest.main()
