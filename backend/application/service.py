"""Two intent use cases, deliberately disconnected from trading execution."""
from dataclasses import replace

from contracts.canonical import content_hash
from contracts.models import (Command, SessionContext, ReviewedRequest, ConfirmedRequest, Receipt, EvidenceEvent,
                              validate_command, validate_confirmation, validate_event_context, classify_retry)
from contracts.primitives import require
from .models import TrustedScope, ConfirmAssertions, IntakeResult
from .ports import WorkflowScopePort, ClockPort, IdSourcePort


class IntakeApplication:
    def __init__(self, workflow: WorkflowScopePort, clock: ClockPort, ids: IdSourcePort):
        self.workflow, self.clock, self.ids = workflow, clock, ids

    @staticmethod
    def assert_scope(scope):
        require(type(scope) is TrustedScope, "scope", "SCOPE_REQUIRED")

    @staticmethod
    def _context(unit, scope, session_id):
        context = unit.context
        require(type(context) is SessionContext and context.workspace_id == scope.workspace_id and
                context.session_id == session_id, "session", "RESOURCE_UNAVAILABLE")
        return context

    def review_command(self, scope, command):
        self.assert_scope(scope)
        require(type(command) is Command, "command")
        require(command.workspace_id == scope.workspace_id, "workspaceId", "SCOPE_MISMATCH")

        def operation(unit):
            context = self._context(unit, scope, command.session_id)
            payload_hash = content_hash(command.identity_payload())
            previous = unit.find_review(command.request_id)
            if previous is not None:
                require(type(previous) is ReviewedRequest and previous.command.workspace_id == scope.workspace_id and
                        previous.command.session_id == command.session_id, "review", "RESOURCE_UNAVAILABLE")
                require(previous.payload_hash == payload_hash, "payloadHash", "IDEMPOTENCY_CONFLICT")
            validate_command(command, context)
            if previous is not None:
                return previous
            reviewed = ReviewedRequest(command, payload_hash, self.clock.now_utc())
            unit.put_review(reviewed)
            return reviewed

        return self.workflow.run(scope, command.session_id, operation)

    def confirm_review(self, scope, assertions):
        self.assert_scope(scope)
        require(type(assertions) is ConfirmAssertions, "confirmation")

        def operation(unit):
            context = self._context(unit, scope, assertions.session_id)
            reviewed = unit.find_review(assertions.request_id)
            require(type(reviewed) is ReviewedRequest and reviewed.command.workspace_id == scope.workspace_id and
                    reviewed.command.session_id == assertions.session_id and
                    reviewed.command.request_id == assertions.request_id, "review", "RESOURCE_UNAVAILABLE")
            require(assertions.payload_hash == reviewed.payload_hash, "payloadHash", "IDEMPOTENCY_CONFLICT")
            command = reviewed.command
            require((assertions.session_revision, assertions.quote_revision) ==
                    (command.session_revision, command.quote_revision), "reviewRevisions", "STALE_REVISION")
            previous = unit.find_receipt(assertions.request_id)
            if previous is not None:
                require(type(previous) is IntakeResult and previous.confirmed.reviewed == reviewed, "receipt", "RESOURCE_UNAVAILABLE")
                classify_retry(reviewed, previous.receipt)
                return replace(previous, duplicate=True)
            confirmed = ConfirmedRequest(reviewed, self.clock.now_utc())
            validate_confirmation(confirmed, context)
            event_id = self.ids.next_id("event", scope, command.session_id, command.request_id)
            receipt_id = self.ids.next_id("receipt", scope, command.session_id, command.request_id)
            event = EvidenceEvent(event_id, scope.workspace_id, command.session_id, command.request_id,
                                  command.method_hash, reviewed.payload_hash, unit.next_sequence(), context.session_revision,
                                  "NO_EXECUTION", "CONFIRMED", "PROTOTYPE", context.revealed_time, confirmed.confirmed_at)
            validate_event_context(event, context)
            receipt = Receipt(receipt_id, scope.workspace_id, command.session_id, command.request_id,
                              reviewed.payload_hash, context.session_revision, (event_id,))
            result = IntakeResult(confirmed, receipt, event)
            unit.commit_intake(confirmed, receipt, event)
            return result

        return self.workflow.run(scope, assertions.session_id, operation)
