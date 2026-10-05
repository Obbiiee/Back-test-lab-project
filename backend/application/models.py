"""Immutable application inputs/results; trusted scope is never a wire DTO."""
from dataclasses import dataclass

from contracts.models import ConfirmedRequest, Receipt, EvidenceEvent
from contracts.primitives import identifier, digest, revision, require


@dataclass(frozen=True)
class TrustedScope:
    workspace_id: str
    actor_ref: str

    def __post_init__(self):
        identifier(self.workspace_id, "workspaceId")
        identifier(self.actor_ref, "actorRef")


@dataclass(frozen=True)
class ConfirmAssertions:
    session_id: str
    request_id: str
    payload_hash: str
    session_revision: int
    quote_revision: int

    def __post_init__(self):
        identifier(self.session_id, "sessionId"); identifier(self.request_id, "requestId")
        digest(self.payload_hash, "payloadHash")
        revision(self.session_revision); revision(self.quote_revision)


@dataclass(frozen=True)
class IntakeResult:
    confirmed: ConfirmedRequest
    receipt: Receipt
    event: EvidenceEvent
    duplicate: bool = False

    def __post_init__(self):
        require(type(self.confirmed) is ConfirmedRequest and type(self.receipt) is Receipt and
                type(self.event) is EvidenceEvent and type(self.duplicate) is bool, "intakeResult")
        reviewed = self.confirmed.reviewed
        command = reviewed.command
        require((self.receipt.workspace_id, self.receipt.session_id, self.receipt.request_id, self.receipt.payload_hash) ==
                (command.workspace_id, command.session_id, command.request_id, reviewed.payload_hash), "receiptIdentity")
        require((self.event.workspace_id, self.event.session_id, self.event.request_id, self.event.payload_hash,
                 self.event.method_hash, self.event.session_revision) ==
                (command.workspace_id, command.session_id, command.request_id, reviewed.payload_hash,
                 command.method_hash, command.session_revision), "eventIdentity")
        require(self.receipt.event_ids == (self.event.event_id,) and
                self.receipt.committed_revision == command.session_revision, "receiptEvent")
        require(self.event.kind == "CONFIRMED" and self.event.source == "PROTOTYPE" and
                self.event.engine_version == "NO_EXECUTION" and
                self.event.recorded_at == self.confirmed.confirmed_at, "nonExecutionEvidence")


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body_json_bytes: bytes

    def __post_init__(self):
        require(type(self.status) is int and 100 <= self.status <= 599 and type(self.body_json_bytes) is bytes, "response")
