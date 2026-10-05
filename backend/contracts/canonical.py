"""BTL-CJSON-1, a bounded project format (not RFC 8785 or a signature).

Decimal and aware datetime values become exact normalized JSON strings. Absent
keys remain absent; None is null. Floats, mutable domain objects and ambiguous
numeric coercion are refused. Standard SHA-256 supplies the digest machinery.
"""
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from .primitives import decimal, require, timestamp


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
    require(len(value) <= 65536 and not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "unicode")
    return value


def _normalize(value, depth=0, budget=None):
    if budget is None:
        budget = [16384]
    budget[0] -= 1
    require(budget[0] >= 0, "nodeBudget")
    require(depth <= 32, "depth")
    if value is None or type(value) is bool:
        return value
    if type(value) is str:
        return _text(value)
    if type(value) is int:
        require(abs(value) <= 2**53 - 1, "integer")
        return value
    if type(value) is Decimal:
        return decimal_text(value)
    if type(value) is datetime:
        return utc_text(value)
    if isinstance(value, Mapping):
        require(len(value) <= 4096 and all(type(k) is str for k in value), "object")
        return {_text(k): _normalize(v, depth + 1, budget) for k, v in value.items()}
    if type(value) in (list, tuple):
        require(len(value) <= 4096, "array")
        return [_normalize(v, depth + 1, budget) for v in value]
    require(False, "unsupportedType")


def canonical_bytes(value):
    require(isinstance(value, Mapping) and type(value.get("schemaVersion")) is int and value["schemaVersion"] == 1,
            "schemaVersion")
    result = json.dumps(_normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(result) <= 1048576, "serializedSize")
    return result


def content_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
