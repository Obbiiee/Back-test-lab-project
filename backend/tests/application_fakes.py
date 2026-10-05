"""Disposable serialized units/fixed clock/IDs, never runtime adapters."""
from datetime import datetime, timezone
from threading import RLock

from application.models import IntakeResult
from contracts.models import MethodPolicy, SessionContext, Command, validate_confirmation, validate_event_context
from contracts.primitives import ContractError, require

H = "a" * 64
NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def sample(kind="FREE_STYLE", on=False):
    method = MethodPolicy("method", H, kind, on, ("setup",), "1" if kind == "PROTOCOL" else None,
                          "2" if kind == "PROTOCOL" else None)
    context = SessionContext("workspace", "session", method, "XAUUSD", "feed", H, 4, 7, NOW, "101")
    command = Command("workspace", "session", "request", "method", H, "XAUUSD", "feed", H, 4, 7,
                      "PLANNED", "BUY", "LIMIT", "100", "2", "1", "99", "102", "plan", 0)
    return context, command


class FixedClock:
    def __init__(self):
        self.time, self.fail, self.calls = NOW, False, 0

    def now_utc(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("private clock failure")
        return self.time


class FixedIds:
    def __init__(self):
        self.calls, self.fail_at = [], None

    def next_id(self, kind, scope, session_id, request_id):
        self.calls.append((kind, scope.workspace_id, session_id, request_id))
        if len(self.calls) == self.fail_at:
            raise RuntimeError("private ID failure")
        # Fixture IDs are derived from complete scope, not order of concurrency.
        return f"{kind}:{scope.workspace_id}:{session_id}:{request_id}"


class UnitFake:
    def __init__(self, workflow, key):
        self.workflow, self.key = workflow, key
        self.context = workflow.contexts[key]
        self.reviews = dict(workflow.reviews.get(key, {}))
        self.intakes = dict(workflow.intakes.get(key, {}))

    def find_review(self, request_id):
        return self.reviews.get(request_id)

    def put_review(self, reviewed):
        require(reviewed.command.request_id not in self.reviews, "review", "IDEMPOTENCY_CONFLICT")
        self.reviews[reviewed.command.request_id] = reviewed

    def find_receipt(self, request_id):
        return self.intakes.get(request_id)

    def next_sequence(self):
        return len(self.intakes)

    def commit_intake(self, confirmed, receipt, event):
        require(self.reviews.get(receipt.request_id) == confirmed.reviewed, "review", "RESOURCE_UNAVAILABLE")
        validate_confirmation(confirmed, self.context)
        validate_event_context(event, self.context)
        require(receipt.request_id not in self.intakes and
                all(x.event.event_id != event.event_id and x.receipt.receipt_id != receipt.receipt_id for x in self.intakes.values()),
                "receipt", "IDEMPOTENCY_CONFLICT")
        self.intakes[receipt.request_id] = IntakeResult(confirmed, receipt, event)
        if self.workflow.fail_commit:
            # Failure AFTER staging must still publish no partial result.
            raise RuntimeError("private staged commit failure")
        if self.workflow.commit_hook:
            self.workflow.commit_hook(self.workflow)


class WorkflowFake:
    def __init__(self, context):
        self.contexts = {(context.workspace_id, context.session_id): context}
        self.reviews, self.intakes = {}, {}
        self.lock = RLock()
        self.fail_commit, self.commit_hook = False, None
        self.run_calls, self.execution_calls = 0, 0

    def run(self, scope, session_id, operation):
        with self.lock:
            self.run_calls += 1
            key = (scope.workspace_id, session_id)
            if key not in self.contexts:
                raise ContractError("RESOURCE_UNAVAILABLE", "session")
            unit = UnitFake(self, key)
            result = operation(unit)
            require(self.contexts[key] == unit.context, "revisions", "STALE_REVISION")
            # Publication is one lock-scoped operation after all checks succeed.
            self.reviews[key], self.intakes[key] = unit.reviews, unit.intakes
            return result

    @property
    def outcomes(self):
        return tuple(v for records in self.intakes.values() for v in records.values())
