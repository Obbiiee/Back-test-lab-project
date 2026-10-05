"""Strict immutable-boundary primitives using only the Python standard library."""
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


class ContractError(ValueError):
    def __init__(self, code, field):
        self.code, self.field = code, field
        super().__init__(f"{code}: {field}")


def require(test, field, code="INVALID_INPUT"):
    if not test:
        raise ContractError(code, field)


def identifier(value, field):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value), field)


def digest(value, field):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), field)


def revision(value, field="revision"):
    require(type(value) is int and 0 <= value <= 2**53 - 1, field)


def category(value, choices, field):
    require(type(value) is str and value in choices, field)


def decimal(value, field="decimal", positive=False):
    # Binary floats/bools are not an exact wire representation. Do not coerce them.
    require(type(value) in (str, int, Decimal), field)
    if type(value) is str:
        require(len(value) <= 1024 and re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", value), field)
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ContractError("INVALID_INPUT", field) from None
    require(result.is_finite(), field)
    parts = result.as_tuple()
    require(len(parts.digits) <= 1000 and abs(parts.exponent) <= 1000, field)
    if positive:
        require(result > 0, field)
    return result


def timestamp(value, field="timestamp"):
    require(type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None, field)
    try:
        return value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise ContractError("INVALID_INPUT", field) from None


def assert_current(expected_session, expected_quote, current_session, current_quote):
    for field, value in (("expectedSessionRevision", expected_session), ("expectedQuoteRevision", expected_quote),
                         ("currentSessionRevision", current_session), ("currentQuoteRevision", current_quote)):
        revision(value, field)
    require(expected_session == current_session and expected_quote == current_quote, "revisions", "STALE_REVISION")
