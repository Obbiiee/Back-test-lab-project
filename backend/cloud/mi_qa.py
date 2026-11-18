"""Internal MI worker admission for operator-pinned synthetic QA data."""
import hashlib
import json
import os
from pathlib import Path

from contracts.canonical import canonical_bytes
from contracts.primitives import digest, require
from execution import mi_kernel
from ticks.contracts import CanonicalTick, tag

REQUEST = "BTL-MI-QUEUE-REQUEST-1"
ENVIRONMENT = ("BTL_PRODUCT_PROFILE", "BTL_QA_MI_MANIFEST", "BTL_QA_MI_MANIFEST_SHA256")
MAX_BYTES = 1_048_576
MAX_SOURCE_TICKS = 2048


def enabled():
    return (os.environ.get(ENVIRONMENT[0]) == "development" and
            bool(os.environ.get(ENVIRONMENT[1])) and bool(os.environ.get(ENVIRONMENT[2])))


def request(raw, session_id):
    require(enabled(), "miQa", "REFUSED_SESSION_MODEL")
    tag(raw, REQUEST, "command jump")
    command = mi_kernel.command_wire(raw["command"])
    require(command["sessionId"] == session_id and type(raw["jump"]) is bool and
            (not raw["jump"] or command["kind"] == "ADVANCE"), "miRequest")
    return command


def open_sources(expected_pins):
    """Resolve a local synthetic fixture only. Command inputs cannot select a path."""
    require(enabled(), "miQa", "REFUSED_SESSION_MODEL")
    sha = os.environ[ENVIRONMENT[2]]
    digest(sha, "miManifest")
    path = Path(os.environ[ENVIRONMENT[1]])
    require(path.is_absolute() and path.is_file(), "miManifest", "REFUSED_SOURCE")
    with path.open("rb") as stream:
        blob = stream.read(MAX_BYTES + 1)
    require(len(blob) <= MAX_BYTES and hashlib.sha256(blob).hexdigest() == sha,
            "miManifest", "REFUSED_SOURCE")
    value = json.loads(blob)
    tag(value, "BTL-MI-QA-SOURCE-1", "pins ticks")
    pins, ticks = value["pins"], value["ticks"]
    require(type(pins) is dict and pins == expected_pins and type(ticks) is dict and
            set(ticks) == set(pins), "miManifestPins", "REFUSED_DATASET_MISMATCH")
    require(all(type(rows) is list and rows for rows in ticks.values()) and
            sum(map(len, ticks.values())) <= MAX_SOURCE_TICKS, "miManifestTicks", "REFUSED_SOURCE")
    require(canonical_bytes(value) == blob, "miManifest", "REFUSED_SOURCE")
    sources = {}
    for symbol, rows in ticks.items():
        pin = pins[symbol]
        require(pin["providerId"] == "SYNTHETIC" and pin["datasetId"].startswith("synthetic:"),
                "miSource", "REFUSED_SOURCE")
        starts = []
        last_time = last_ordinal = -1
        for index, raw in enumerate(rows):
            row = CanonicalTick.from_wire(raw).wire
            require(all(row[key] == pin[key] for key in ("datasetId", "datasetVersion", "providerId", "feedId"))
                    and row["instrumentId"] == pin["feedInstrumentId"], "miTick", "REFUSED_DATASET_MISMATCH")
            time, ordinal = int(row["timeNs"]), int(row["rawOrdinal"])
            require(time >= last_time and ordinal > last_ordinal, "miTickOrder", "REFUSED_SOURCE_ORDER")
            if time != last_time:
                starts.append(index)
            last_time, last_ordinal = time, ordinal
        sources[symbol] = _opener(rows, starts)
    return sources, pins, sha


def _opener(rows, starts):
    def open_at(skip):
        require(0 <= skip <= len(starts), "miSourceCursor", "REFUSED_CURSOR_MISMATCH")
        start = starts[skip] if skip < len(starts) else len(rows)
        return (rows[index] for index in range(start, len(rows)))
    return open_at
