"""Fail-closed configuration for the bounded native research worker pool."""
import os


ENVIRONMENT_VARIABLE = "BTL_RESEARCH_WORKERS"
DEFAULT_WORKER_COUNT = 2
MIN_WORKER_COUNT = 1
MAX_WORKER_COUNT = 4


def parse_worker_count(value):
    """Accept only an explicit integer in [1, 4]; never create an unbounded pool."""
    if value is None:
        return DEFAULT_WORKER_COUNT
    if type(value) is not str or value not in ("1", "2", "3", "4"):
        raise ValueError(f"{ENVIRONMENT_VARIABLE} must be one of 1, 2, 3, or 4")
    return int(value)


WORKER_COUNT = parse_worker_count(os.environ.get(ENVIRONMENT_VARIABLE))
