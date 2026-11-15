"""Durable multi-chunk replay ("replay run"): one request walks a Session toward a target through MANY short durable commands.

Nothing here is financial logic. Each chunk is the ordinary canonical ADVANCE command (bounded to 64 timestamp groups by the timeline), committed by the
existing controller in its own short transaction, so the reducer, receipts, journal and statistics are exactly those of any other replay. This module only
decides how many chunks one worker job runs before it yields (a wall-clock budget well inside the 30 s native deadline) and names the commands so that every
retry, restart or duplicate worker is idempotent: a chunk's command id is derived from (runId, segment, revision it starts at), so a chunk can only ever be
committed once. The queue chains the next segment durably (see cloud/queue.py); the client never has to re-issue anything.
"""
import os
import re
import time

from contracts.primitives import require, revision
from ticks.contracts import uint

REQUEST_ARTIFACT, RESULT_ARTIFACT = "BTL-REPLAY-RUN-1", "BTL-REPLAY-RUN-RESULT-1"
def budget_seconds():
    """Wall-clock budget of one segment; must stay well below the 30 s native job deadline. Read at call time (the worker is a separate process)."""
    return min(20.0, max(0.0, float(os.environ.get("BTL_REPLAY_RUN_BUDGET_S", "12"))))


def max_chunks():
    return max(1, min(4096, int(os.environ.get("BTL_REPLAY_RUN_MAX_CHUNKS", "4096"))))


MAX_SEGMENTS = 100_000                                                         # a run of 262,144 single-tick groups needs 4,096 chunks; this is a runaway fence
_RUN_ID = re.compile(r"[0-9a-f]{32}")


def validate_request(raw, session_id):
    require(type(raw) is dict and set(raw) == {"schemaVersion", "artifact", "runId", "segment", "sessionId", "expectedRevision", "targetNs"}, "replayRun", "INVALID_INPUT")
    require(raw["schemaVersion"] == 1 and type(raw["schemaVersion"]) is int and raw["artifact"] == REQUEST_ARTIFACT and raw["sessionId"] == session_id, "replayRun", "INVALID_INPUT")
    require(type(raw["runId"]) is str and _RUN_ID.fullmatch(raw["runId"]) is not None, "runId", "INVALID_INPUT")
    require(type(raw["segment"]) is int and 0 <= raw["segment"] < MAX_SEGMENTS, "segment", "INVALID_INPUT")
    revision(raw["expectedRevision"], "expectedRevision")
    uint(raw["targetNs"], "targetNs")
    return raw


def next_request(raw, result):
    """The follow-on segment: same run, next segment number, starting at the revision the finished segment ended on."""
    return dict(raw, segment=raw["segment"] + 1, expectedRevision=result["revision"])


def run_chunks(app, connect, session_id, raw, *, command_artifact, budget=None, chunk_cap=None, clock=time.monotonic):
    """Run chunks until the target is reached, no progress is possible, the budget is spent or the chunk cap is hit. Returns the result artifact."""
    validate_request(raw, session_id)
    budget = budget_seconds() if budget is None else budget
    chunk_cap = max_chunks() if chunk_cap is None else chunk_cap
    target = int(raw["targetNs"])
    prefix = f"command:replay-run:{raw['runId']}:{raw['segment']}:r"
    with connect(app.dsn) as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        _meta, _method, state, _checkpoint = app._session(db, session_id)
        prior = db.execute("SELECT max(revision) FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id LIKE %s",
                           (app.scope.workspace_id, session_id, prefix + "%")).fetchone()[0]
    if prior is None:
        require(state["revision"] == raw["expectedRevision"], "revision", "REFUSED_STALE_REVISION")
    else:
        require(state["revision"] >= prior, "revision", "REFUSED_STALE_REVISION")      # a retry of a partly done segment continues from the durable state
    require(target >= int(state["throughNs"]), "advance", "REFUSED_BACKWARD_ADVANCE")
    started, chunks = clock(), 0
    while chunks < chunk_cap and int(state["throughNs"]) < target and not state["ended"] and (chunks == 0 or clock() - started < budget):
        before = (int(state["nextGroupIndex"]), int(state["throughNs"]))
        command = dict(schemaVersion=1, artifact=command_artifact, sessionId=session_id, commandId=f"{prefix}{state['revision']}",
                       expectedRevision=state["revision"], kind="ADVANCE", payload={"targetNs": str(target)})
        state = app.controller.apply(app.scope, command)["state"]
        chunks += 1
        if (int(state["nextGroupIndex"]), int(state["throughNs"])) == before:
            break                                                                      # the source has nothing more to reveal toward this target
    reached = int(state["throughNs"]) >= target
    return dict(schemaVersion=1, artifact=RESULT_ARTIFACT, runId=raw["runId"], segment=raw["segment"], sessionId=session_id, targetNs=str(target),
                throughNs=state["throughNs"], revision=state["revision"], chunks=chunks, targetReached=reached, ended=bool(state["ended"]),
                unresolved=bool(state["unresolved"]), balance=state["balance"], nextGroupIndex=state["nextGroupIndex"],
                more=(not reached) and (not state["ended"]) and chunks > 0)
