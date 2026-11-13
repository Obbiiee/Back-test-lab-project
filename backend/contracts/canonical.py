"""BTL-CJSON-1, a bounded project format (not RFC 8785 or a signature).

Decimal and aware datetime values become exact normalized JSON strings. Absent
keys remain absent; None is null. Floats, mutable domain objects and ambiguous
numeric coercion are refused. Standard SHA-256 supplies the digest machinery.
"""
import hashlib
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

import msgspec

from .primitives import ContractError, decimal, require, timestamp

NORMALIZATION_NODE_LIMIT = 16384
_SERIALIZED_SIZE_LIMIT = 1048576


def decimal_text(value):
    value = decimal(value)
    if value == 0:
        return "0"
    # format(f) does not round under the active decimal context.
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def utc_text(value):
    return timestamp(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _text(value):
    if len(value) > 65536 or (not value.isascii() and any(0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ContractError("INVALID_INPUT", "unicode")
    return value


def _normalize(value, depth=0, budget=None):
    if budget is None:
        budget = [NORMALIZATION_NODE_LIMIT]
    budget[0] -= 1
    if budget[0] < 0:
        raise ContractError("INVALID_INPUT", "nodeBudget")
    if depth > 32:
        raise ContractError("INVALID_INPUT", "depth")
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        return _text(value)
    if type(value) is int:
        if abs(value) > 2**53 - 1:
            raise ContractError("INVALID_INPUT", "integer")
        return value
    if type(value) is Decimal:
        return decimal_text(value)
    if type(value) is datetime:
        return utc_text(value)
    if isinstance(value, Mapping):
        if len(value) > 4096 or not all(type(k) is str for k in value):
            raise ContractError("INVALID_INPUT", "object")
        return {_text(k): _normalize(v, depth + 1, budget) for k, v in value.items()}
    if type(value) in (list, tuple):
        if len(value) > 4096:
            raise ContractError("INVALID_INPUT", "array")
        return [_normalize(v, depth + 1, budget) for v in value]
    raise ContractError("INVALID_INPUT", "unsupportedType")


def _encode_normalized(value):
    """Encode a value already produced by _normalize using BTL-CJSON-1."""
    return msgspec.json.encode(value, order="deterministic")


class _CanonicalArrayAccumulator:
    """Incrementally enforce canonical limits for a bounded top-level array.

    Each element is normalized and encoded once. The tracked byte count is
    exact because canonical JSON embeds each encoded element unchanged in the
    array. The shared node budget mirrors normalization of the full envelope.
    This is a size/validation helper; it does not produce a canonical artifact.
    """
    __slots__ = ("_remaining_nodes", "_encoded_length", "_count")

    def __init__(self, artifact, field):
        budget = [NORMALIZATION_NODE_LIMIT]
        envelope = _normalize({"schemaVersion": 1, "artifact": artifact, field: []}, budget=budget)
        encoded = _encode_normalized(envelope)
        require(len(encoded) <= _SERIALIZED_SIZE_LIMIT, "serializedSize")
        self._remaining_nodes = budget[0]
        self._encoded_length = len(encoded)
        self._count = 0

    def append(self, value):
        budget = [self._remaining_nodes]
        normalized = _normalize(value, depth=2, budget=budget)
        encoded = _encode_normalized(normalized)
        next_length = self._encoded_length + len(encoded) + (1 if self._count else 0)
        require(next_length <= _SERIALIZED_SIZE_LIMIT, "serializedSize")
        self._remaining_nodes = budget[0]
        self._encoded_length = next_length
        self._count += 1


def canonical_bytes(value):
    require(isinstance(value, Mapping) and type(value.get("schemaVersion")) is int and value["schemaVersion"] == 1,
            "schemaVersion")
    result = _encode_normalized(_normalize(value))
    require(len(result) <= _SERIALIZED_SIZE_LIMIT, "serializedSize")
    return result


def content_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
