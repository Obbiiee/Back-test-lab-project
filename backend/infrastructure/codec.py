"""Versioned canonical bytes for existing immutable DTOs, not a second model."""
import json
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256

from contracts.canonical import canonical_bytes
from contracts.models import (MethodPolicy, SessionContext, Observation, Command,
                              ReviewedRequest, ConfirmedRequest, Receipt, EvidenceEvent,
                              Passport, LineageEntry)
from contracts.primitives import require
from application.models import IntakeResult


def pack(value):
    return canonical_bytes({"schemaVersion": 1, "data": asdict(value)})


def fingerprint(payload):
    return sha256(payload).hexdigest()


def unpack(payload, expected_hash, kind):
    payload = bytes(payload)
    require(fingerprint(payload) == expected_hash, "storedHash", "CORRUPT_RECORD")
    body = json.loads(payload)
    require(type(body.get("schemaVersion")) is int and body["schemaVersion"] == 1, "storedSchema", "CORRUPT_RECORD")
    data = body["data"]
    def time(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    def command(value):
        return Command(**{**value, "observations": tuple(Observation(**o) for o in value["observations"])})
    def reviewed(value):
        return ReviewedRequest(command(value["command"]), value["payload_hash"], time(value["reviewed_at"]))
    def event(value):
        return EvidenceEvent(**{**value, "market_time": time(value["market_time"]), "recorded_at": time(value["recorded_at"])})
    if kind is SessionContext:
        method = {**data["method"], "conditions": tuple(data["method"]["conditions"])}
        return SessionContext(**{**data, "method": MethodPolicy(**method), "revealed_time": time(data["revealed_time"])})
    if kind is ReviewedRequest:
        return reviewed(data)
    if kind is IntakeResult:
        confirmed = ConfirmedRequest(reviewed(data["confirmed"]["reviewed"]), time(data["confirmed"]["confirmed_at"]))
        receipt = Receipt(**{**data["receipt"], "event_ids": tuple(data["receipt"]["event_ids"])})
        return IntakeResult(confirmed, receipt, event(data["event"]), data["duplicate"])
    if kind is Passport:
        return Passport(**{**data, "start": time(data["start"]), "end": time(data["end"])})
    if kind is LineageEntry:
        return LineageEntry(**{**data, "recorded_at": time(data["recorded_at"])})
    raise ValueError("Unsupported stored DTO")
