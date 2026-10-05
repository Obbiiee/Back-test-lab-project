import json
import unittest
from dataclasses import replace, FrozenInstanceError

from application.models import TrustedScope
from application.transport import handle_review, handle_confirm
from tests.test_application import setup
from tests.application_fakes import H


def wire(command):
    return {"schemaVersion": 1, "workspaceId": command.workspace_id, "sessionId": command.session_id,
        "requestId": command.request_id, "methodId": command.method_id, "methodHash": command.method_hash,
        "instrumentId": command.instrument_id, "feedId": command.feed_id, "profileHash": command.profile_hash,
        "sessionRevision": command.session_revision, "quoteRevision": command.quote_revision,
        "workflow": command.workflow, "side": command.side, "orderType": command.order_type,
        "entry": str(command.entry), "quantity": str(command.quantity), "riskPercent": str(command.risk_percent),
        "sl": str(command.sl) if command.sl is not None else None, "tp": str(command.tp) if command.tp is not None else None,
        "planId": command.plan_id, "planRevision": command.plan_revision,
        "observations": [{"conditionId": o.condition_id, "outcome": o.outcome} for o in command.observations]}


def body(response):
    return json.loads(response.body_json_bytes)


def confirmation(review):
    return {"schemaVersion": 1, "sessionId": "session", "requestId": review["requestId"],
        "payloadHash": review["payloadHash"], "sessionRevision": 4, "quoteRevision": 7, "confirm": True}


def encoded(value):
    return json.dumps(value, ensure_ascii=True).encode()


class TransportTests(unittest.TestCase):
    def test_versioned_review_confirm_repeat_labels_and_immutable_response(self):
        app, scope, c = setup()
        response = handle_review(encoded(wire(c)), scope, app)
        self.assertEqual(response.status, 200)
        with self.assertRaises(FrozenInstanceError): response.status = 999
        review = body(response)
        self.assertEqual(review["schemaVersion"], 1)
        self.assertEqual(review["status"], "REVIEWED_NOT_EXECUTED")
        self.assertFalse(review["executionPerformed"]); self.assertFalse(review["durable"])
        payload = encoded(confirmation(review))
        first, duplicate = handle_confirm(payload, scope, app), handle_confirm(payload, scope, app)
        self.assertEqual(first.status, 200); self.assertEqual(duplicate.status, 200)
        self.assertEqual(body(first)["status"], "INTENT_RECORDED_NOT_EXECUTED")
        self.assertFalse(body(first)["duplicate"]); self.assertTrue(body(duplicate)["duplicate"])
        self.assertEqual(body(first)["receipt"], body(duplicate)["receipt"])
        self.assertEqual(body(first)["event"], body(duplicate)["event"])
        self.assertIn("NO_INSTRUMENT_BUDGET_CERTIFICATION", body(first)["limitations"])
        self.assertEqual(len(app.workflow.outcomes), 1)

    def test_malformed_json_types_keys_bounds_and_revision(self):
        app, scope, c = setup()
        base = wire(c)
        bad_bytes = [b'', b'\xff', b'{', b'[]', b'{"schemaVersion":1,"schemaVersion":1}',
                     b'{"schemaVersion":1,"a":NaN}', b'{"schemaVersion":1,"a":Infinity}',
                     b'['*33+b'0'+b']'*33, b' '*65537, b'{"schemaVersion":1,"x":1.2}']
        for raw in bad_bytes:
            with self.subTest(raw=raw[:80]): self.assertEqual(handle_review(raw, scope, app).status, 400)
        for changes in ({"schemaVersion": True}, {"schemaVersion": 2}, {"entry": 100}, {"quantity": True},
                        {"sessionRevision": True}, {"quoteRevision": "7"}, {"extra": "x"},
                        {"observations": {}}, {"observations": [None]}, {"observations": [{"conditionId": "setup"}]}):
            with self.subTest(changes=changes): self.assertEqual(handle_review(encoded({**base, **changes}), scope, app).status, 400)
        missing = dict(base); missing.pop("entry")
        self.assertEqual(handle_review(encoded(missing), scope, app).status, 400)
        self.assertEqual(handle_review(encoded({**base, "requestId": "\ud800"}), scope, app).status, 400)
        for changes in ({"entry": "NaN"}, {"quantity": "0"}, {"sessionRevision": -1}, {"side": "UP"}, {"sl": "102"}):
            with self.subTest(changes=changes): self.assertEqual(handle_review(encoded({**base, **changes}), scope, app).status, 422)
        self.assertEqual(app.workflow.outcomes, ())

    def test_scope_cannot_be_wire_injected_and_errors_are_sanitized(self):
        app, scope, c = setup()
        self.assertEqual(handle_review(encoded(wire(c)), None, app).status, 403)
        self.assertEqual(app.workflow.run_calls, 0)
        self.assertEqual(handle_review(encoded(wire(c)), TrustedScope("other", "actor"), app).status, 403)
        self.assertEqual(handle_review(encoded({**wire(c), "actorRef": "actor"}), scope, app).status, 400)
        for key in ("methodHash", "profileHash"):
            self.assertEqual(handle_review(encoded({**wire(c), key: "b"*64}), scope, app).status, 422)
        self.assertEqual(handle_review(encoded({**wire(c), "sessionId": "foreign"}), scope, app).status, 404)
        review = body(handle_review(encoded(wire(c)), scope, app))
        app.workflow.fail_commit = True
        with self.assertLogs("application.transport", level="ERROR") as logs:
            response = handle_confirm(encoded(confirmation(review)), scope, app)
        self.assertEqual(response.status, 503)
        self.assertNotIn("private staged", response.body_json_bytes.decode())
        self.assertNotIn("private staged", ''.join(logs.output))
        self.assertEqual(app.workflow.outcomes, ())

    def test_confirmation_exact_snapshot_stale_conflict_no_replacement(self):
        app, scope, c = setup()
        missing = {"schemaVersion": 1, "sessionId": "session", "requestId": "missing", "payloadHash": H,
                   "sessionRevision": 4, "quoteRevision": 7, "confirm": True}
        self.assertEqual(handle_confirm(encoded(missing), scope, app).status, 404)
        review = body(handle_review(encoded(wire(c)), scope, app))
        base = confirmation(review)
        for changes in ({"confirm": False}, {"confirm": 1}, {"entry": "101"}, {"scope": {}}, {"sessionRevision": True}):
            self.assertEqual(handle_confirm(encoded({**base, **changes}), scope, app).status, 400)
        for changes in ({"payloadHash": "b"*64}, {"quoteRevision": 8}, {"sessionRevision": 5}):
            self.assertEqual(handle_confirm(encoded({**base, **changes}), scope, app).status, 409)
        app.workflow.contexts[("workspace", "session")] = replace(app.workflow.contexts[("workspace", "session")], quote_revision=8)
        self.assertEqual(handle_confirm(encoded(base), scope, app).status, 409)
        self.assertEqual(app.workflow.outcomes, ())

    def test_protocol_through_transport_on_off_and_float_refusal(self):
        for on in (False, True):
            app, scope, c = setup("PROTOCOL", on)
            base = wire(c)
            failed = {**base, "observations": [{"conditionId": "setup", "outcome": "FAIL"}]}
            response = handle_review(encoded(failed), scope, app)
            self.assertEqual(response.status, 422 if on else 200)
            if not on:
                final = body(handle_confirm(encoded(confirmation(body(response))), scope, app))
                self.assertEqual(app.workflow.outcomes[0].confirmed.reviewed.command.observations[0].outcome, "FAIL")
                self.assertFalse(final["executionPerformed"])
            passed = {**base, "requestId": "passed", "observations": [{"conditionId": "setup", "outcome": "PASS"}]}
            reviewed = body(handle_review(encoded(passed), scope, app))
            self.assertEqual(handle_confirm(encoded(confirmation(reviewed)), scope, app).status, 200)
            for changes in ({"riskPercent": "2"}, {"tp": "103"}, {"orderType": "MARKET", "entry": "101"}):
                self.assertEqual(handle_review(encoded({**passed, "requestId": "blocked", **changes}), scope, app).status, 422)


if __name__ == "__main__": unittest.main()
