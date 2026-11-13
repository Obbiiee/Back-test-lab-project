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

from .primitives import ContractError, decimal, require, timestamp

NORMALIZATION_NODE_LIMIT = 16384


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
    require(len(value) <= 65536 and (value.isascii() or not any(0xD800 <= ord(c) <= 0xDFFF for c in value)), "unicode")
    return value


def _fail(field):
    raise ContractError("INVALID_INPUT", field)


def _walk(value, depth, budget):
    """Same checks, same order, same errors as the reference walk, with fewer calls.

    The happy path avoids ``require`` calls and generator-based ``all``; leaf
    children (str/None/bool/int) are handled inline. Budget is decremented once
    per node and *before* any other check, exactly as before, so a failure leaves
    the shared budget in the same state.
    """
    n = budget[0] - 1
    budget[0] = n
    if n < 0:
        _fail("nodeBudget")
    if depth > 32:
        _fail("depth")
    t = type(value)
    if t is str:
        if len(value) > 65536 or not (value.isascii() or not any(0xD800 <= ord(c) <= 0xDFFF for c in value)):
            _fail("unicode")
        return value
    if value is None or t is bool:
        return value
    if t is int:
        if abs(value) > 9007199254740991:
            _fail("integer")
        return value
    if t is dict or (t is not list and t is not tuple and isinstance(value, Mapping)):
        if len(value) > 4096:
            _fail("object")
        for k in value:
            if type(k) is not str:
                _fail("object")
        out = {}
        child = depth + 1
        for k, v in value.items():
            if len(k) > 65536 or not (k.isascii() or not any(0xD800 <= ord(c) <= 0xDFFF for c in k)):
                _fail("unicode")
            tv = type(v)
            if tv is str or tv is int or v is None or tv is bool:
                m = budget[0] - 1
                budget[0] = m
                if m < 0:
                    _fail("nodeBudget")
                if child > 32:
                    _fail("depth")
                if tv is str:
                    if len(v) > 65536 or not (v.isascii() or not any(0xD800 <= ord(c) <= 0xDFFF for c in v)):
                        _fail("unicode")
                elif tv is int and abs(v) > 9007199254740991:
                    _fail("integer")
                out[k] = v
            else:
                out[k] = _walk(v, child, budget)
        return out
    if t is list or t is tuple:
        if len(value) > 4096:
            _fail("array")
        child = depth + 1
        return [_walk(v, child, budget) for v in value]
    if t is Decimal:
        return decimal_text(value)
    if t is datetime:
        return utc_text(value)
    _fail("unsupportedType")


def _normalize(value, depth=0, budget=None):
    if budget is None:
        budget = [NORMALIZATION_NODE_LIMIT]
    return _walk(value, depth, budget)


def canonical_bytes(value):
    require(isinstance(value, Mapping) and type(value.get("schemaVersion")) is int and value["schemaVersion"] == 1,
            "schemaVersion")
    result = json.dumps(_normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(result) <= 1048576, "serializedSize")
    return result


def content_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
