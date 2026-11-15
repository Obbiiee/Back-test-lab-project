"""Offline source acceptance records for content-addressed tick sources.

The full acceptance scan of a source (`validate_provider`: every event validated, ordering, ties, duplicate ids, diagnostics) is O(dataset) in time and memory. It is a
property of the immutable content, so it is done ONCE at admission (an operator/ingestion step, outside request deadlines) and recorded under a server-owned directory;
a request-time timeline then only checks the record against the pinned manifest hash. Per-read integrity is unchanged: every chunk is still validated against the
manifest hashes when it is read, so a source whose bytes changed cannot be read. Directory configured (BTL_SOURCE_ACCEPTANCE_DIR) but record missing: the source is
refused (fail closed), never silently re-scanned inside a request.
"""
import json
import os
import tempfile
from pathlib import Path

from contracts.canonical import canonical_bytes, content_hash
from contracts.primitives import require

VALIDATOR = "BTL-TICK-SOURCE-ACCEPTANCE-1"


def directory():
    value = os.environ.get("BTL_SOURCE_ACCEPTANCE_DIR")
    return Path(value) if value else None


def _path(folder, manifest_hash):
    require(isinstance(manifest_hash, str) and len(manifest_hash) == 64 and all(c in "0123456789abcdef" for c in manifest_hash), "manifestHash", "INVALID_INPUT")
    return Path(folder) / f"{manifest_hash}.accepted.json"


def accept_offline(provider, dataset_id, dataset_version, folder):
    """Run the full scan once and persist the record atomically. Returns the record."""
    from .provider import validate_provider
    diagnostics = []
    manifest = validate_provider(provider, dataset_id, dataset_version,
                                 diagnostic_sink=lambda r: diagnostics.append(canonical_bytes(dict(schemaVersion=1, artifact="BTL-TICK-DIAGNOSTIC-CACHE-1", record=r)).decode()))
    manifest_hash = content_hash(provider.describe(dataset_id, dataset_version))
    body = dict(schemaVersion=1, artifact=VALIDATOR, datasetId=dataset_id, datasetVersion=dataset_version, manifestHash=manifest_hash, diagnostics=diagnostics)
    record = dict(body, recordHash=content_hash(body))
    Path(folder).mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w") as out:
        json.dump(record, out, sort_keys=True)
    os.chmod(tmp, 0o600)
    os.replace(tmp, _path(folder, manifest_hash))                      # atomic
    return record


def load(folder, dataset_id, dataset_version, manifest_hash):
    """The accepted diagnostics (tuple of bytes) for this exact source, or ContractError('REFUSED_SOURCE_NOT_ADMITTED')."""
    path = _path(folder, manifest_hash)
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        from contracts.primitives import ContractError
        raise ContractError("REFUSED_SOURCE_NOT_ADMITTED", "source") from None
    body = {k: v for k, v in record.items() if k != "recordHash"}
    require(record.get("recordHash") == content_hash(body) and body.get("artifact") == VALIDATOR and
            (body.get("datasetId"), body.get("datasetVersion"), body.get("manifestHash")) == (dataset_id, dataset_version, manifest_hash), "acceptanceRecord", "REFUSED_SOURCE_NOT_ADMITTED")
    return tuple(d.encode() for d in body["diagnostics"])
