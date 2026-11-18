"""QA-only chronological Jump-to-next-financial-event orchestration for MI.

It never chooses a price or skips a tick: every revealed timestamp group is
processed by the canonical MI reducer. Future timestamps are inspected only by
the controller-private source cursor and are never returned in the result.
"""
from contracts.primitives import require

from . import mi_kernel

FINANCIAL_EVENTS = frozenset(("ENTRY_FILL", "EXIT_FILL", "UNRESOLVED"))
LIVE_STATUSES = frozenset(("PENDING", "ACTIVE"))


def run(state, timeline, session_end_ns, *, max_timestamps=256, cancelled=None):
    """Advance a bounded number of whole timestamp groups until an event or end.

    Return ``(new_state, result)``. ``SEARCHING`` is resumable: the caller can
    persist the returned state together with ``timeline.cursor()`` using the MI
    checkpoint artifact. Cancellation is observed only between atomic timestamp
    groups, after all state changes for an earlier group have been returned.
    """
    mi_kernel.validate_state(state)
    require(type(session_end_ns) is int and session_end_ns >= int(state["throughNs"]), "sessionEnd", "INVALID_INPUT")
    require(type(max_timestamps) is int and 1 <= max_timestamps <= 256, "maxTimestamps", "INVALID_INPUT")
    pinned_symbols = [profile["symbol"] for profile in state["profiles"]]
    require(getattr(timeline, "instruments", None) == pinned_symbols, "timeline", "REFUSED_DATASET_MISMATCH")
    if not any(order["status"] in LIVE_STATUSES for order in state["orders"].values()):
        return state, dict(status="NO_ACTIVE_ORDERS", throughNs=state["throughNs"], processedGroups=0, events=[])

    current, emitted, processed_groups, processed_times = state, [], 0, 0
    while processed_times < max_timestamps:
        if cancelled is not None and cancelled():
            return current, dict(status="CANCELLED", throughNs=current["throughNs"], processedGroups=processed_groups, events=emitted)

        # Controller-private lookahead is used only to choose a causal advance
        # boundary. It is not included in the returned result or reducer state.
        next_time = timeline._controller_next_time()
        if next_time is None or next_time > session_end_ns:
            groups = timeline.advance(session_end_ns)
            current, events = mi_kernel.advance(current, groups, str(session_end_ns))
            emitted.extend(events)
            current["revision"] += 1
            mi_kernel.validate_state(current)
            processed_groups += len(groups)
            return current, dict(status="NO_EVENT_UNTIL_SESSION_END", throughNs=current["throughNs"],
                                 processedGroups=processed_groups, events=emitted)

        # advance(next_time) yields every instrument group with that exact time,
        # in pinned instrument order, so tied events are committed atomically.
        groups = timeline.advance(next_time)
        current, events = mi_kernel.advance(current, groups, str(next_time))
        emitted.extend(events)
        current["revision"] += 1
        mi_kernel.validate_state(current)
        processed_groups += len(groups)
        processed_times += 1
        if any(event["kind"] in FINANCIAL_EVENTS for event in events):
            return current, dict(status="EVENT_FOUND", throughNs=current["throughNs"],
                                 processedGroups=processed_groups, events=emitted)

    return current, dict(status="SEARCHING", throughNs=current["throughNs"], processedGroups=processed_groups, events=emitted)
