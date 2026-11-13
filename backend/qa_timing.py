"""Opt-in, bounded timing fields for local acceptance probes.

The scope contains durations/counts only. It must never record SQL, identities,
tokens, request bodies, or financial values.
"""
from contextlib import contextmanager
from contextvars import ContextVar

_FIELDS = (
    "admissionNs", "connectNs", "sqlNs", "sqlCount", "transactionExitNs",
    "fixtureCacheLockWaitNs", "fixtureRestoreGateWaitNs",
    "fixtureTimelineResumeNs", "fixturePastReadNs",
)
_TIMING = ContextVar("btl_qa_timing", default=None)
_DURATION_FIELDS = frozenset(_FIELDS) - {"sqlCount"}


@contextmanager
def capture_qa_timing():
    metrics = dict.fromkeys(_FIELDS, 0)
    token = _TIMING.set(metrics)
    try:
        yield metrics
    finally:
        _TIMING.reset(token)


def record_qa_timing(field, value):
    if field not in _FIELDS:
        return
    metrics = _TIMING.get()
    if metrics is None:
        return
    if field in _DURATION_FIELDS and (type(value) is not int or value < 0):
        return
    if field == "sqlCount" and (type(value) is not int or value < 0):
        return
    metrics[field] += value


def current_qa_timing():
    return _TIMING.get()
