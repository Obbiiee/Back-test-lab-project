"""Bound compatibility catalog arrays while preserving pagination signals."""

from contracts.primitives import require


COMPATIBILITY_CATALOG_WINDOW = 128


def catalog_window(rows, *, limit=COMPATIBILITY_CATALOG_WINDOW):
    """Return a bounded prefix and whether a separate keyset page is needed."""
    require(type(rows) is list and type(limit) is int and limit > 0,
            'catalogWindow', 'CORRUPT_RECORD')
    return rows[:limit], len(rows) > limit
