"""Abstract ports only. Runtime adapters/engines/persistence are absent."""
from datetime import datetime
from typing import Callable, Protocol, TypeVar

from contracts.models import SessionContext, ReviewedRequest, ConfirmedRequest, Receipt, EvidenceEvent
from .models import TrustedScope, IntakeResult

T = TypeVar("T")


class WorkflowUnit(Protocol):
    @property
    def context(self) -> SessionContext: ...

    def find_review(self, request_id: str) -> ReviewedRequest | None: ...
    def put_review(self, reviewed: ReviewedRequest) -> None: ...
    # Return the original immutable receipt/evidence bundle, not a rebuilt event.
    def find_receipt(self, request_id: str) -> IntakeResult | None: ...
    def next_sequence(self) -> int: ...
    def commit_intake(self, confirmed: ConfirmedRequest, receipt: Receipt, event: EvidenceEvent) -> None: ...


class WorkflowScopePort(Protocol):
    def run(self, scope: TrustedScope, session_id: str, operation: Callable[[WorkflowUnit], T]) -> T:
        """Scope + serialize read/commit; publish all writes only on success.

        Context identity/revisions must remain stable through the operation.
        Exceptions roll back review/receipt/event writes together. Future durable
        adapters must establish these guarantees independently of the test fake.
        """
        ...


class ClockPort(Protocol):
    def now_utc(self) -> datetime: ...


class IdSourcePort(Protocol):
    def next_id(self, kind: str, scope: TrustedScope, session_id: str, request_id: str) -> str: ...
