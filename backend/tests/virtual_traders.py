"""Deterministic, test-only virtual-trader cohort descriptors.

This module prepares identities and object IDs for future isolated QA drivers.
It does not register accounts, submit API requests, create Sessions, or run load.
"""
from dataclasses import dataclass
from uuid import UUID, uuid5


COHORT_SIZES = (1, 5, 10, 25, 50, 100)
_NAMESPACE = UUID("0af6fe70-47bb-5f33-bfef-691b0d996fd6")
_FLOW = (
    "AUTHENTICATE",
    "CREATE_WORKSPACE",
    "CREATE_METHOD",
    "CREATE_SESSION",
    "REVIEW",
    "CONFIRM",
    "RECEIPT_LOOKUP",
    "JOURNAL_READ",
)


@dataclass(frozen=True)
class VirtualTrader:
    ordinal: int
    email: str
    identity_key: UUID
    workspace_key: UUID
    method_id: str
    session_id: str
    command_id: str


@dataclass(frozen=True)
class VirtualTraderCohort:
    run_id: UUID
    requested_users: int
    traders: tuple[VirtualTrader, ...]
    flow: tuple[str, ...] = _FLOW


def build_cohort(run_id: UUID | str, requested_users: int) -> VirtualTraderCohort:
    """Build stable, non-secret descriptors for one bounded QA scenario.

    ``run_id`` must be unique per isolated QA run. The generator intentionally
    supports only the approved scenario sizes; it does not imply concurrency
    capacity or create any authenticated identity or financial command.
    """
    if isinstance(run_id, str):
        try:
            run_id = UUID(run_id)
        except (ValueError, AttributeError) as error:
            raise ValueError("run_id must be a UUID") from error
    if not isinstance(run_id, UUID):
        raise ValueError("run_id must be a UUID")
    if type(requested_users) is not int or requested_users not in COHORT_SIZES:
        raise ValueError("requested_users must be one of 1, 5, 10, 25, 50, 100")

    traders = []
    for ordinal in range(1, requested_users + 1):
        seed = f"{run_id}:{ordinal}"
        trader_uuid = uuid5(_NAMESPACE, "trader:" + seed)
        workspace = uuid5(_NAMESPACE, "workspace:" + seed)
        method = uuid5(_NAMESPACE, "method:" + seed)
        session = uuid5(_NAMESPACE, "session:" + seed)
        command = uuid5(_NAMESPACE, "command:" + seed)
        traders.append(VirtualTrader(
            ordinal=ordinal,
            email=f"virtual-trader-{run_id.hex[:12]}-{ordinal:03d}@example.com",
            identity_key=trader_uuid,
            workspace_key=workspace,
            method_id="method:" + str(method),
            session_id="session:" + str(session),
            command_id="order:" + str(command),
        ))
    return VirtualTraderCohort(run_id, requested_users, tuple(traders))


def build_stages(run_id: UUID | str, sizes: tuple[int, ...] = COHORT_SIZES) -> tuple[VirtualTraderCohort, ...]:
    """Build disjoint deterministic cohorts for progressive acceptance stages.

    Every stage gets its own derived run identity, so 1 → 5 → 10 → 25 → 50 →
    100-user runs in one isolated QA database cannot accidentally reuse the
    same synthetic accounts or Sessions. Descriptors create no workload.
    """
    if isinstance(run_id, str):
        try:
            run_id = UUID(run_id)
        except (ValueError, AttributeError) as error:
            raise ValueError("run_id must be a UUID") from error
    if not isinstance(run_id, UUID):
        raise ValueError("run_id must be a UUID")
    if type(sizes) is not tuple or not sizes or any(type(size) is not int for size in sizes):
        raise ValueError("sizes must be a non-empty tuple of supported cohort sizes")
    if tuple(sorted(set(sizes))) != sizes or any(size not in COHORT_SIZES for size in sizes):
        raise ValueError("sizes must be strictly increasing supported cohort sizes")
    return tuple(
        build_cohort(uuid5(run_id, f"riksora-virtual-trader-stage:{size}"), size)
        for size in sizes
    )
