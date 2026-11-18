"""QA-only checkpoint envelope for the isolated multi-instrument reducer.

This is not mounted in Product Sessions. It binds the reducer state and fan-in
cursor into one versioned, checksummed artifact while keeping market source data
outside the checkpoint. Source pins must be supplied by the caller from its
verified provider when restoring.
"""
from copy import deepcopy

from contracts.canonical import content_hash
from contracts.primitives import require

from ticks.multi_timeline import MultiTimeline

from .mi_kernel import MI_COMPACT_STATE, validate_state

ARTIFACT = "BTL-TICK-EXECUTION-CHECKPOINT-MI-1"
_PIN_FIELDS = ("datasetId", "datasetVersion", "providerId", "feedId", "feedInstrumentId")


def pins_from_state(state):
    """Return the ordered immutable primary-source identity pinned by reducer profiles."""
    validate_state(state)
    return {
        profile["symbol"]: {key: profile["primary"][key] for key in _PIN_FIELDS}
        for profile in state["profiles"]
    }


def _validate_cursor(state, cursor):
    require(type(cursor) is dict and set(cursor) == {"schemaVersion", "artifact", "instruments", "frontierNs", "consumed", "quotes"},
            "cursor", "REFUSED_MI_CHECKPOINT")
    symbols = [profile["symbol"] for profile in state["profiles"]]
    require(cursor["schemaVersion"] == 1 and cursor["artifact"] == "BTL-MULTI-TIMELINE-CURSOR-1"
            and cursor["instruments"] == symbols, "cursor", "REFUSED_MI_CHECKPOINT")
    pristine = int(state["nextGroupIndex"]) == 0 and all(group is None for group in state["groups"].values())
    require((cursor["frontierNs"] == state["throughNs"] or
             (pristine and cursor["frontierNs"] == "0" and state["throughNs"] == state["startNs"]))
            and type(cursor["consumed"]) is dict and set(cursor["consumed"]) == set(symbols), "cursor", "REFUSED_MI_CHECKPOINT")
    require(all(type(count) is int and count >= 0 for count in cursor["consumed"].values())
            and sum(cursor["consumed"].values()) == int(state["nextGroupIndex"]), "cursor", "REFUSED_MI_CHECKPOINT")
    expected_quotes = {}
    for symbol in symbols:
        group = state["groups"][symbol]
        expected_quotes[symbol] = None if group is None else {
            "timeNs": group["timeNs"], "bid": group["events"][-1]["bid"], "ask": group["events"][-1]["ask"]
        }
    require(cursor["quotes"] == expected_quotes, "cursor", "REFUSED_MI_CHECKPOINT")


def _require_folded(state):
    if state["artifact"] == MI_COMPACT_STATE:
        require(all(order["status"] in ("ACTIVE", "PENDING") for order in state["orders"].values()),
                "miActiveOrders", "REFUSED_MI_CHECKPOINT")


def create(state, cursor):
    """Create an immutable-by-convention checkpoint with integrity hashes."""
    state = validate_state(deepcopy(state))
    _require_folded(state)
    cursor = deepcopy(cursor)
    _validate_cursor(state, cursor)
    body = dict(schemaVersion=1, artifact=ARTIFACT, sessionId=state["sessionId"], revision=state["revision"],
                profileSetHash=state["profileSetHash"], sourcePins=pins_from_state(state), stateHash=content_hash(state),
                state=state, cursor=cursor)
    return dict(body, checkpointHash=content_hash(body))


def validate(checkpoint):
    """Check the envelope without opening or exposing historical sources."""
    fields = {"schemaVersion", "artifact", "sessionId", "revision", "profileSetHash", "sourcePins", "stateHash", "state", "cursor", "checkpointHash"}
    require(type(checkpoint) is dict and set(checkpoint) == fields, "checkpoint", "REFUSED_MI_CHECKPOINT")
    body = {key: value for key, value in checkpoint.items() if key != "checkpointHash"}
    require(checkpoint["schemaVersion"] == 1 and checkpoint["artifact"] == ARTIFACT
            and checkpoint["checkpointHash"] == content_hash(body), "checkpoint", "REFUSED_MI_CHECKPOINT")
    state = validate_state(deepcopy(checkpoint["state"]))
    _require_folded(state)
    require(checkpoint["sessionId"] == state["sessionId"] and checkpoint["revision"] == state["revision"]
            and checkpoint["profileSetHash"] == state["profileSetHash"]
            and checkpoint["stateHash"] == content_hash(state), "checkpoint", "REFUSED_MI_CHECKPOINT")
    pins = pins_from_state(state)
    require(checkpoint["sourcePins"] == pins, "sourcePins", "REFUSED_DATASET_MISMATCH")
    _validate_cursor(state, checkpoint["cursor"])
    return state


def restore(checkpoint, sources, *, verified_source_pins):
    """Restore from a verified provider's pins, never from client metadata."""
    state = validate(checkpoint)
    pins = checkpoint["sourcePins"]
    require(verified_source_pins == pins, "sourcePins", "REFUSED_DATASET_MISMATCH")
    require(type(sources) is dict and set(sources) == set(pins), "sources", "REFUSED_DATASET_MISMATCH")
    timeline = MultiTimeline(list(checkpoint["cursor"]["instruments"]), sources, cursor=deepcopy(checkpoint["cursor"]))
    return state, timeline
