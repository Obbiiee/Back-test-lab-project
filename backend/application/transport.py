"""Version-1 pure wire handlers; no HTTP route, server, principal or engine."""
import json
import logging
from dataclasses import fields

from contracts.canonical import canonical_bytes
from contracts.models import Command, Observation
from contracts.primitives import ContractError
from .models import ApiResponse, ConfirmAssertions

log = logging.getLogger(__name__)
WIRE = {
    "workspaceId": "workspace_id", "sessionId": "session_id", "requestId": "request_id", "methodId": "method_id",
    "methodHash": "method_hash", "instrumentId": "instrument_id", "feedId": "feed_id", "profileHash": "profile_hash",
    "sessionRevision": "session_revision", "quoteRevision": "quote_revision", "workflow": "workflow", "side": "side",
    "orderType": "order_type", "entry": "entry", "quantity": "quantity", "riskPercent": "risk_percent", "sl": "sl",
    "tp": "tp", "planId": "plan_id", "planRevision": "plan_revision", "observations": "observations",
}
OPTIONAL = {"sl", "tp", "planId", "planRevision", "observations"}
SAFE_FIELDS = set(WIRE) | set(WIRE.values()) | {"request", "body", "depth", "schemaVersion", "confirm", "scope",
    "conditionId", "outcome", "unknownCondition", "duplicateObservations", "quick", "plannedLevels", "marketQuote",
    "orderRelation", "method", "protocolType", "riskPercent", "rr", "checklist", "revisions", "reviewRevisions",
    "review", "receipt", "session", "confirmationTime", "timestamp", "unicode", "payloadHash", "quote", "revision"}


def malformed(field):
    raise ContractError("MALFORMED_REQUEST", field)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            malformed("body")
        result[key] = value
    return result


def _no_number(value):
    malformed("body")


def _decode(data):
    if type(data) is not bytes or not 0 < len(data) <= 65536:
        malformed("body")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        malformed("body")
    # Bound nesting before json allocation, ignoring structural text in strings.
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > 32:
                malformed("depth")
        elif char in "]}":
            depth -= 1
    try:
        body = json.loads(text, object_pairs_hook=_pairs, parse_float=_no_number, parse_constant=_no_number)
    except (ValueError, RecursionError):
        malformed("body")
    if type(body) is not dict:
        malformed("body")
    def scalar_unicode(value):
        if type(value) is str and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            malformed("body")
        if type(value) is dict:
            for key, item in value.items():
                scalar_unicode(key); scalar_unicode(item)
        if type(value) is list:
            for item in value:
                scalar_unicode(item)
    scalar_unicode(body)
    if type(body.get("schemaVersion")) is not int or body["schemaVersion"] != 1:
        malformed("schemaVersion")
    return body


def _shape(body, allowed, required):
    if not set(body).issubset(allowed) or not required.issubset(body):
        malformed("body")


def _command(data):
    body = _decode(data)
    _shape(body, set(WIRE) | {"schemaVersion"}, (set(WIRE) - OPTIONAL) | {"schemaVersion"})
    for key in ("entry", "quantity", "riskPercent", "sl", "tp"):
        if key in body and not (key in {"sl", "tp"} and body[key] is None) and type(body[key]) is not str:
            malformed(key)
    for key in ("sessionRevision", "quoteRevision", "planRevision"):
        if key in body and body[key] is not None and type(body[key]) is not int:
            malformed(key)
    observations = body.get("observations", [])
    if type(observations) is not list or len(observations) > 1024:
        malformed("observations")
    normalized = []
    for item in observations:
        if type(item) is not dict:
            malformed("observations")
        _shape(item, {"conditionId", "outcome"}, {"conditionId", "outcome"})
        normalized.append(Observation(item["conditionId"], item["outcome"]))
    values = {internal: body[wire] for wire, internal in WIRE.items() if wire in body and wire != "observations"}
    values["observations"] = tuple(normalized)
    return Command(**values)


def _confirmation(data):
    body = _decode(data)
    keys = {"schemaVersion", "sessionId", "requestId", "payloadHash", "sessionRevision", "quoteRevision", "confirm"}
    _shape(body, keys, keys)
    if body["confirm"] is not True:
        malformed("confirm")
    for key in ("sessionRevision", "quoteRevision"):
        if type(body[key]) is not int:
            malformed(key)
    return ConfirmAssertions(body["sessionId"], body["requestId"], body["payloadHash"],
                             body["sessionRevision"], body["quoteRevision"])


def _response(status, body):
    return ApiResponse(status, canonical_bytes({"schemaVersion": 1, **body}))


def _project(value):
    return {field.name: getattr(value, field.name) for field in fields(value)}


def _boundary(operation):
    try:
        return operation()
    except ContractError as error:
        statuses = {"MALFORMED_REQUEST": 400, "INVALID_INPUT": 422, "PROTOCOL_BLOCKED": 422,
                    "IDENTITY_MISMATCH": 422, "STALE_REVISION": 409, "IDEMPOTENCY_CONFLICT": 409,
                    "SCOPE_REQUIRED": 403, "SCOPE_MISMATCH": 403, "RESOURCE_UNAVAILABLE": 404}
        status = statuses.get(error.code, 503) if type(error.code) is str else 503
        code = error.code if status != 503 else "BOUNDARY_UNAVAILABLE"
        safe_field = error.field if type(error.field) is str and error.field in SAFE_FIELDS and status != 503 else None
        return _response(status, {"error": {"code": code, "field": safe_field}})
    except Exception as error:
        # Boundary-only sanitization: never return raw exceptions or log private
        # payloads/secrets. Domain code does not swallow exceptions.
        log.error("Unmounted intake boundary failed (%s)", type(error).__name__)
        return _response(503, {"error": {"code": "BOUNDARY_UNAVAILABLE", "field": None}})


def handle_review(json_bytes, trusted_scope, application):
    def operation():
        application.assert_scope(trusted_scope)
        reviewed = application.review_command(trusted_scope, _command(json_bytes))
        return _response(200, {"status": "REVIEWED_NOT_EXECUTED", "executionPerformed": False, "durable": False,
            "source": "PROTOTYPE", "requestId": reviewed.command.request_id, "payloadHash": reviewed.payload_hash,
            "snapshot": reviewed.command.identity_payload(), "reviewedAt": reviewed.reviewed_at,
            "limitations": ["NO_EXECUTION", "NO_DURABLE_STORAGE", "NO_INSTRUMENT_BUDGET_CERTIFICATION"]})
    return _boundary(operation)


def handle_confirm(json_bytes, trusted_scope, application):
    def operation():
        application.assert_scope(trusted_scope)
        result = application.confirm_review(trusted_scope, _confirmation(json_bytes))
        return _response(200, {"status": "INTENT_RECORDED_NOT_EXECUTED", "executionPerformed": False,
            "durable": False, "source": "PROTOTYPE", "receipt": _project(result.receipt),
            "event": _project(result.event), "confirmedAt": result.confirmed.confirmed_at, "duplicate": result.duplicate,
            "limitations": ["NO_EXECUTION", "NO_DURABLE_STORAGE", "NO_INSTRUMENT_BUDGET_CERTIFICATION"]})
    return _boundary(operation)
