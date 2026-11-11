"""Request and command helpers for bounded, durable next-event search.

This module contains orchestration metadata only. Tick selection, event ordering,
and all financial decisions remain in the canonical ADVANCE reducer.
"""
from contracts.primitives import require, revision
from ticks.contracts import keys
from .workspace import TIMEFRAMES


REQUEST_ARTIFACT = "BTL-JUMP-NEXT-EVENT-1"
RESULT_ARTIFACT = "BTL-JUMP-NEXT-EVENT-RESULT-1"
FINANCIAL_EVENT_KINDS = frozenset(("ENTRY_FILL", "EXIT_FILL", "UNRESOLVED"))


def validate_request(raw, session_id):
    keys(raw, "schemaVersion artifact requestId sessionId expectedRevision timeframe")
    require(type(raw["schemaVersion"]) is int and raw["schemaVersion"] == 1 and
            raw["artifact"] == REQUEST_ARTIFACT and raw["sessionId"] == session_id,
            "jumpRequest", "INVALID_INPUT")
    request_id = raw["requestId"]
    require(type(request_id) is str and len(request_id) == 32 and
            all(char in "0123456789abcdef" for char in request_id), "requestId", "INVALID_INPUT")
    revision(raw["expectedRevision"], "expectedRevision")
    require(type(raw["timeframe"]) is str and raw["timeframe"] in TIMEFRAMES,
            "timeframe", "REFUSED_TIMEFRAME")
    return raw


def advance_command(request, revision_number, artifact):
    return dict(schemaVersion=1, artifact=artifact, sessionId=request["sessionId"],
                commandId=f"jump:{request['requestId']}:r{revision_number}",
                expectedRevision=revision_number, kind="ADVANCE",
                payload={"targetNs": request["targetNs"]})


def result(request, *, status, through_ns, advances, processed_groups, events, view):
    return dict(schemaVersion=1, artifact=RESULT_ARTIFACT, requestId=request["requestId"],
                sessionId=request["sessionId"], status=status, throughNs=str(through_ns),
                advances=advances, processedGroups=processed_groups, events=events, view=view)
