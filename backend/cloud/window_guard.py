"""Free research-window boundary for a running Session (server-side; the reducer and financial contracts are untouched).

The window of a Session is the UTC calendar month it was activated for (stored by the entitlement ledger). A Pro account is not limited by it. For a Free
account the guard never closes, cancels, rewrites or prices anything; it only refuses commands that would create NEW exposure or reveal MORE market data
than the already-open lifecycle needs:

  before the boundary : ADVANCE/SEEK/replay-to may not cross it (the user steps to the boundary, or uses Jump to Next Event with live orders)
  at/after the boundary: OPEN/confirm refused; ADVANCE/SEEK/replay-to refused; CANCEL, CLOSE and END stay allowed;
                         Jump to Next Event allowed only with at least one ACTIVE order and no PENDING order (a pending order would be a new entry
                         outside the window: cancel it first). With nothing live the window is complete and says so.
A PENDING order created inside the window is protected where the ticks are consumed: the jump orchestration (`execution/research.py`, with the lookup in
`execution/free_window.py`) bounds its search to the last tick of the window BEFORE any tick that could fill is processed; ADVANCE/SEEK/replay-to are bounded here
(window = ticks with time < end, last allowed cursor end-1). The frozen reducer is not touched.
"""
from contracts.primitives import ContractError


class WindowRefused(ContractError):
    def __init__(self, code, detail):
        super().__init__(code, "window")
        self.detail = detail


def live_orders(dsn, workspace_id, actor_id, session_id):
    """Committed order counts and cursor of a Session. Goes through the same authorised runner as every other read, so it works for every session model
    (fixture, synthetic Monthly, observed) with that model's own source pins; it never builds a provider by itself."""
    from .research import run
    view = run(dsn, actor_id, workspace_id, "inspect", (session_id,))
    state = view["state"]
    orders = state["orders"].values()
    return dict(throughNs=int(state["throughNs"]), active=sum(o["status"] == "ACTIVE" for o in orders),
                pending=sum(o["status"] == "PENDING" for o in orders), ended=bool(state["ended"]))


def check(entitlements, dsn, actor_id, workspace_id, session_id, kind, target_ns=None):
    """kind: OPEN | ADVANCE | JUMP | (CANCEL/CLOSE/END are always allowed). Raises WindowRefused; returns None when the command may proceed."""
    if kind in ("CANCEL", "CLOSE", "END", "FORK"):
        return
    window = entitlements.session_window(workspace_id, session_id)
    if window is None or window["tier"] == "PRO":
        return
    end = int(window["endNs"])
    state = live_orders(dsn, workspace_id, actor_id, session_id)
    through, after = state["throughNs"], state["throughNs"] >= end - 1       # window = ticks with time < end; end-1 is the last allowed cursor
    base = dict(windowEndNs=str(end), throughNs=str(through), activeOrders=state["active"], pendingOrders=state["pending"])
    if kind == "OPEN":
        if after:
            raise WindowRefused("WINDOW_ENDED", base)
        return
    if kind == "ADVANCE":
        if after:
            raise WindowRefused("WINDOW_ENDED_CONTINUATION_ONLY", {**base, "allowed": "JUMP_NEXT_EVENT_WITH_ACTIVE_ORDERS_CANCEL_CLOSE_END"})
        if target_ns is not None and int(target_ns) > end - 1:
            raise WindowRefused("WINDOW_BOUNDARY", {**base, "maxTargetNs": str(end - 1)})
        return
    if kind == "JUMP":
        if after:
            if state["pending"]:
                raise WindowRefused("PENDING_AT_WINDOW_END", base)
            if not state["active"]:
                raise WindowRefused("WINDOW_COMPLETED", base)
            return
        return                                          # a PENDING order is protected inside the jump orchestration (bounded before any fill), see execution/free_window.py
    raise ContractError("INVALID_INPUT", "kind")
