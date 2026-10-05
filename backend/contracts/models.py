"""Request-oriented frozen contracts, never executable account/engine state.

Trusted context is supplied explicitly by a future authorized application layer.
These primitives neither authenticate a caller nor durably record confirmations.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from fractions import Fraction

from .canonical import content_hash
from .primitives import identifier, digest, revision, category, decimal, timestamp, require, assert_current


def exact_tuple(value, cls, field):
    require(type(value) is tuple and len(value) <= 1024 and all(type(v) is cls for v in value), field)


def set_decimal(obj, *fields):
    for field in fields:
        object.__setattr__(obj, field, decimal(getattr(obj, field), field, positive=True))


@dataclass(frozen=True)
class Observation:
    condition_id: str
    outcome: str

    def __post_init__(self):
        identifier(self.condition_id, "conditionId")
        category(self.outcome, {"PASS", "FAIL", "NOT_ASSESSED"}, "outcome")


@dataclass(frozen=True)
class MethodPolicy:
    method_id: str
    definition_hash: str
    kind: str
    checklist_on: bool
    conditions: tuple[str, ...]
    risk_percent: Decimal | None = None
    rr: Decimal | None = None

    def __post_init__(self):
        identifier(self.method_id, "methodId")
        digest(self.definition_hash, "definitionHash")
        category(self.kind, {"FREE_STYLE", "PROTOCOL"}, "kind")
        require(type(self.checklist_on) is bool, "checklistOn")
        exact_tuple(self.conditions, str, "conditions")
        for item in self.conditions:
            identifier(item, "conditionId")
        require(len(set(self.conditions)) == len(self.conditions), "duplicateConditions")
        if self.kind == "PROTOCOL":
            require(len(self.conditions) > 0, "conditions")
            set_decimal(self, "risk_percent", "rr")
            require(self.risk_percent <= 100, "riskPercent")
        else:
            require(not self.checklist_on and self.risk_percent is None and self.rr is None, "freeStylePolicy")


@dataclass(frozen=True)
class SessionContext:
    workspace_id: str
    session_id: str
    method: MethodPolicy
    instrument_id: str
    feed_id: str
    profile_hash: str
    session_revision: int
    quote_revision: int
    revealed_time: datetime
    quote: Decimal

    def __post_init__(self):
        for name in ("workspace_id", "session_id", "instrument_id", "feed_id"):
            identifier(getattr(self, name), name)
        require(type(self.method) is MethodPolicy, "method")
        digest(self.profile_hash, "profileHash")
        revision(self.session_revision); revision(self.quote_revision)
        object.__setattr__(self, "revealed_time", timestamp(self.revealed_time))
        set_decimal(self, "quote")


@dataclass(frozen=True)
class Command:
    workspace_id: str
    session_id: str
    request_id: str
    method_id: str
    method_hash: str
    instrument_id: str
    feed_id: str
    profile_hash: str
    session_revision: int
    quote_revision: int
    workflow: str
    side: str
    order_type: str
    entry: Decimal
    quantity: Decimal
    risk_percent: Decimal
    sl: Decimal | None = None
    tp: Decimal | None = None
    plan_id: str | None = None
    plan_revision: int | None = None
    observations: tuple[Observation, ...] = ()

    def __post_init__(self):
        for name in ("workspace_id", "session_id", "request_id", "method_id", "instrument_id", "feed_id"):
            identifier(getattr(self, name), name)
        digest(self.method_hash, "methodHash"); digest(self.profile_hash, "profileHash")
        revision(self.session_revision); revision(self.quote_revision)
        category(self.workflow, {"QUICK", "PLANNED"}, "workflow")
        category(self.side, {"BUY", "SELL"}, "side")
        category(self.order_type, {"MARKET", "LIMIT", "STOP"}, "orderType")
        set_decimal(self, "entry", "quantity", "risk_percent")
        require(self.risk_percent <= 100, "riskPercent")
        for name in ("sl", "tp"):
            if getattr(self, name) is not None:
                set_decimal(self, name)
        if self.workflow == "PLANNED":
            identifier(self.plan_id, "planId"); revision(self.plan_revision, "planRevision")
            require(self.sl is not None and self.tp is not None, "plannedLevels")
        else:
            require(self.order_type == "MARKET" and self.plan_id is None and self.plan_revision is None, "quick")
        exact_tuple(self.observations, Observation, "observations")
        require(len({v.condition_id for v in self.observations}) == len(self.observations), "duplicateObservations")

    def identity_payload(self):
        # Explicit allowlist: no secrets, display labels or recorded-time metadata.
        return {"schemaVersion": 1, "contract": "COMMAND", **{
            name: getattr(self, name) for name in (
                "workspace_id", "session_id", "request_id", "method_id", "method_hash", "instrument_id", "feed_id",
                "profile_hash", "session_revision", "quote_revision", "workflow", "side", "order_type", "entry",
                "quantity", "risk_percent", "sl", "tp", "plan_id", "plan_revision")},
            "observations": [{"conditionId": v.condition_id, "outcome": v.outcome} for v in self.observations]}


def validate_command(command, context):
    require(type(command) is Command and type(context) is SessionContext, "commandContext")
    method = context.method
    for field in ("workspace_id", "session_id", "instrument_id", "feed_id", "profile_hash"):
        require(getattr(command, field) == getattr(context, field), field, "IDENTITY_MISMATCH")
    require(command.method_id == method.method_id and command.method_hash == method.definition_hash, "method", "IDENTITY_MISMATCH")
    assert_current(command.session_revision, command.quote_revision, context.session_revision, context.quote_revision)
    direction = 1 if command.side == "BUY" else -1
    entry = Fraction(command.entry)
    if command.sl is not None:
        require(direction * (entry - Fraction(command.sl)) > 0, "sl")
    if command.tp is not None:
        require(direction * (Fraction(command.tp) - entry) > 0, "tp")
    if command.order_type == "MARKET":
        require(command.entry == context.quote, "marketQuote")
    else:
        relation = direction * (entry - Fraction(context.quote))
        require(relation < 0 if command.order_type == "LIMIT" else relation > 0, "orderRelation")
    outcomes = {o.condition_id: o.outcome for o in command.observations}
    require(set(outcomes).issubset(method.conditions), "unknownCondition")
    if method.kind == "PROTOCOL":
        require(command.workflow == "PLANNED" and command.order_type in {"LIMIT", "STOP"}, "protocolType", "PROTOCOL_BLOCKED")
        require(command.risk_percent == method.risk_percent, "riskPercent", "PROTOCOL_BLOCKED")
        # Compare exact coefficients without context rounding or division.
        require(abs(Fraction(command.tp) - entry) == abs(entry - Fraction(command.sl)) * Fraction(method.rr),
                "rr", "PROTOCOL_BLOCKED")
        if method.checklist_on:
            require(all(outcomes.get(c) == "PASS" for c in method.conditions), "checklist", "PROTOCOL_BLOCKED")
    return command


def validate_action(method, action):
    require(type(method) is MethodPolicy, "method")
    category(action, {"CONFIRM", "CANCEL_PENDING", "MANUAL_CLOSE", "PARTIAL_CLOSE", "AMEND_EXITS"}, "action")
    require(method.kind != "PROTOCOL" or action in {"CONFIRM", "CANCEL_PENDING"}, "action", "PROTOCOL_BLOCKED")


@dataclass(frozen=True)
class ReviewedRequest:
    command: Command
    payload_hash: str
    reviewed_at: datetime

    def __post_init__(self):
        require(type(self.command) is Command, "command")
        digest(self.payload_hash, "payloadHash")
        require(self.payload_hash == content_hash(self.command.identity_payload()), "payloadHash", "IDENTITY_MISMATCH")
        object.__setattr__(self, "reviewed_at", timestamp(self.reviewed_at))


@dataclass(frozen=True)
class ConfirmedRequest:
    reviewed: ReviewedRequest
    confirmed_at: datetime

    def __post_init__(self):
        require(type(self.reviewed) is ReviewedRequest, "reviewed")
        object.__setattr__(self, "confirmed_at", timestamp(self.confirmed_at))
        require(self.confirmed_at >= self.reviewed.reviewed_at, "confirmationTime")


def validate_confirmation(confirmed, context):
    require(type(confirmed) is ConfirmedRequest, "confirmed")
    return validate_command(confirmed.reviewed.command, context)


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    workspace_id: str
    session_id: str
    request_id: str
    payload_hash: str
    committed_revision: int
    event_ids: tuple[str, ...]

    def __post_init__(self):
        for name in ("receipt_id", "workspace_id", "session_id", "request_id"):
            identifier(getattr(self, name), name)
        digest(self.payload_hash, "payloadHash"); revision(self.committed_revision)
        exact_tuple(self.event_ids, str, "eventIds")
        require(len(self.event_ids) > 0 and len(set(self.event_ids)) == len(self.event_ids), "eventIds")
        for item in self.event_ids:
            identifier(item, "eventId")


def classify_retry(reviewed, receipt):
    require(type(reviewed) is ReviewedRequest and type(receipt) is Receipt, "retry")
    command = reviewed.command
    require((command.workspace_id, command.session_id, command.request_id) ==
            (receipt.workspace_id, receipt.session_id, receipt.request_id), "receiptScope", "IDENTITY_MISMATCH")
    require(reviewed.payload_hash == receipt.payload_hash, "payloadHash", "IDEMPOTENCY_CONFLICT")
    return receipt  # Pure comparison only, not a durable dedup implementation.


@dataclass(frozen=True)
class EvidenceEvent:
    event_id: str
    workspace_id: str
    session_id: str
    request_id: str
    method_hash: str
    payload_hash: str
    sequence: int
    session_revision: int
    engine_version: str
    kind: str
    source: str
    market_time: datetime
    recorded_at: datetime

    def __post_init__(self):
        for name in ("event_id", "workspace_id", "session_id", "request_id", "engine_version"):
            identifier(getattr(self, name), name)
        digest(self.method_hash, "methodHash"); digest(self.payload_hash, "payloadHash")
        revision(self.sequence); revision(self.session_revision)
        category(self.kind, {"CONFIRMED", "REFUSED", "PENDING_CANCELLED", "FILL", "PARTIAL_EXIT", "EXIT", "CORRECTION"}, "kind")
        category(self.source, {"PROTOTYPE", "CANONICAL_EXECUTION"}, "source")
        object.__setattr__(self, "market_time", timestamp(self.market_time))
        object.__setattr__(self, "recorded_at", timestamp(self.recorded_at))


def validate_event_context(event, context):
    require(type(event) is EvidenceEvent and type(context) is SessionContext, "eventContext")
    require((event.workspace_id, event.session_id, event.method_hash, event.session_revision) ==
            (context.workspace_id, context.session_id, context.method.definition_hash, context.session_revision),
            "eventIdentity", "IDENTITY_MISMATCH")
    require(event.market_time <= context.revealed_time, "marketTime", "FUTURE_OBSERVATION")
    return event


@dataclass(frozen=True)
class Passport:
    experiment_id: str
    workspace_id: str
    dataset_id: str
    dataset_version: str
    dataset_hash: str
    method_hash: str
    execution_hash: str
    input_hash: str
    engine_version: str
    calculator_version: str
    instrument_id: str
    feed_id: str
    start: datetime
    end: datetime
    log_revision: int
    trial_id: str
    passport_revision: int = 0
    protocol_hash: str | None = None
    regime_hash: str | None = None
    rng_algorithm: str | None = None
    seed: int | None = None

    def __post_init__(self):
        for name in ("experiment_id", "workspace_id", "dataset_id", "dataset_version", "engine_version",
                     "calculator_version", "instrument_id", "feed_id", "trial_id"):
            identifier(getattr(self, name), name)
        for name in ("dataset_hash", "method_hash", "execution_hash", "input_hash"):
            digest(getattr(self, name), name)
        for name in ("protocol_hash", "regime_hash"):
            if getattr(self, name) is not None:
                digest(getattr(self, name), name)
        revision(self.log_revision); revision(self.passport_revision)
        object.__setattr__(self, "start", timestamp(self.start)); object.__setattr__(self, "end", timestamp(self.end))
        require(self.start <= self.end, "period")
        require((self.rng_algorithm is None) == (self.seed is None), "rng")
        if self.rng_algorithm is not None:
            identifier(self.rng_algorithm, "rngAlgorithm"); revision(self.seed, "seed")

    def identity_payload(self):
        return {"schemaVersion": 1, "contract": "PASSPORT", **vars(self)}


@dataclass(frozen=True)
class LineageEntry:
    trial_id: str
    workspace_id: str
    experiment_id: str
    family_id: str
    definition_hash: str
    research_kind: str
    disposition: str
    recorded_at: datetime
    parent_trial_id: str | None = None

    def __post_init__(self):
        for name in ("trial_id", "workspace_id", "experiment_id", "family_id"):
            identifier(getattr(self, name), name)
        if self.parent_trial_id is not None:
            identifier(self.parent_trial_id, "parentTrialId")
            require(self.parent_trial_id != self.trial_id, "selfParent")
        digest(self.definition_hash, "definitionHash")
        category(self.research_kind, {"EXPLORATORY", "CONFIRMATORY"}, "researchKind")
        category(self.disposition, {"STARTED", "COMPLETED", "FAILED", "ABANDONED", "EXCLUDED"}, "disposition")
        object.__setattr__(self, "recorded_at", timestamp(self.recorded_at))


@dataclass(frozen=True)
class ResearchJobInput:
    job_id: str
    workspace_id: str
    passport_hash: str
    input_hash: str
    calculator_version: str
    parameters_hash: str
    deadline: datetime
    max_attempts: int
    rng_algorithm: str | None = None
    seed: int | None = None

    def __post_init__(self):
        identifier(self.job_id, "jobId"); identifier(self.workspace_id, "workspaceId")
        identifier(self.calculator_version, "calculatorVersion")
        for name in ("passport_hash", "input_hash", "parameters_hash"):
            digest(getattr(self, name), name)
        object.__setattr__(self, "deadline", timestamp(self.deadline))
        require(type(self.max_attempts) is int and 1 <= self.max_attempts <= 100, "maxAttempts")
        require((self.rng_algorithm is None) == (self.seed is None), "rng")
        if self.rng_algorithm is not None:
            identifier(self.rng_algorithm, "rngAlgorithm"); revision(self.seed, "seed")


def job_transition(state, target):
    transitions = {"QUEUED": {"RUNNING", "CANCELLED", "FAILED"}, "RUNNING": {"SUCCEEDED", "FAILED", "CANCEL_REQUESTED"},
                   "CANCEL_REQUESTED": {"CANCELLED", "FAILED"}, "SUCCEEDED": set(), "FAILED": set(), "CANCELLED": set()}
    category(state, transitions, "state"); category(target, transitions, "target")
    require(target in transitions[state], "jobTransition")
    return target


@dataclass(frozen=True)
class ResearchJobState:
    job_id: str
    state: str
    attempt: int
    result_hash: str | None = None
    failure_code: str | None = None

    def __post_init__(self):
        identifier(self.job_id, "jobId")
        category(self.state, {"QUEUED", "RUNNING", "CANCEL_REQUESTED", "SUCCEEDED", "FAILED", "CANCELLED"}, "state")
        revision(self.attempt, "attempt")
        if self.state == "QUEUED":
            require(self.attempt == 0, "queuedAttempt")
        if self.state in {"RUNNING", "CANCEL_REQUESTED", "SUCCEEDED"}:
            require(self.attempt > 0, "startedAttempt")
        require((self.result_hash is not None) == (self.state == "SUCCEEDED"), "resultState")
        if self.result_hash is not None:
            digest(self.result_hash, "resultHash")
        require((self.failure_code is not None) == (self.state == "FAILED"), "failureState")
        if self.failure_code is not None:
            identifier(self.failure_code, "failureCode")


def validate_job_input(job, passport, now):
    require(type(job) is ResearchJobInput and type(passport) is Passport, "jobPassport")
    require(job.workspace_id == passport.workspace_id and job.input_hash == passport.input_hash and
            job.passport_hash == content_hash(passport.identity_payload()) and
            job.calculator_version == passport.calculator_version and
            (job.rng_algorithm, job.seed) == (passport.rng_algorithm, passport.seed), "jobIdentity", "IDENTITY_MISMATCH")
    require(job.deadline > timestamp(now), "deadline", "DEADLINE_EXCEEDED")
    return job


@dataclass(frozen=True)
class TemporalObservation:
    available_at: datetime
    value: Decimal

    def __post_init__(self):
        object.__setattr__(self, "available_at", timestamp(self.available_at))
        object.__setattr__(self, "value", decimal(self.value))


def time_bounded_view(observations, revealed_time):
    exact_tuple(observations, TemporalObservation, "observations")
    bound = timestamp(revealed_time)
    # Project on availability, never inspect future values in a calculation.
    visible = tuple(o for o in observations if o.available_at <= bound)
    require(all(a.available_at < b.available_at for a, b in zip(visible, visible[1:])), "visibleOrder")
    return visible
