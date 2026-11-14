"""Free research-window boundary for a running Session (server-side; the reducer and financial contracts are untouched).

The window of a Session is the UTC calendar month it was activated for (stored by the entitlement ledger). A Pro account is not limited by it. For a Free
account the guard never closes, cancels, rewrites or prices anything; it only refuses commands that would create NEW exposure or reveal MORE market data
than the already-open lifecycle needs:

  before the boundary : ADVANCE/SEEK/replay-to may not cross it (the user steps to the boundary, or uses Jump to Next Event with live orders)
  at/after the boundary: OPEN/confirm refused; ADVANCE/SEEK/replay-to refused; CANCEL, CLOSE and END stay allowed;
                         Jump to Next Event allowed only with at least one ACTIVE order and no PENDING order (a pending order would be a new entry
                         outside the window: cancel it first). With nothing live the window is complete and says so.
Known limit (documented in the audit report): a PENDING order created inside the window that is still pending when one Jump chunk crosses the boundary
could fill after it. Closing that needs the jump orchestration to receive the window end; until then the guard refuses Jump when a PENDING order exists
and the boundary is nearer than the next-event search could prove (conservative: it refuses a Jump with PENDING orders once the cursor is within one UTC day of the end).
"""
from contracts.primitives import ContractError

NEAR_END_NS = 24 * 3600 * 10**9


class WindowRefused(ContractError):
    def __init__(self, code, detail):
        super().__init__(code, "window")
        self.detail = detail


def live_orders(dsn, workspace_id, actor_id, session_id):
    from application.models import TrustedScope
    from execution.research import ResearchApplication
    from infrastructure.database import connect
    app = ResearchApplication(dsn, TrustedScope(str(workspace_id), str(actor_id)))
    try:
        with connect(dsn) as db:
            _meta, _method, state, _checkpoint = app._session(db, session_id)
        orders = state["orders"].values()
        return dict(throughNs=int(state["throughNs"]), active=sum(o["status"] == "ACTIVE" for o in orders),
                    pending=sum(o["status"] == "PENDING" for o in orders), ended=bool(state["ended"]))
    finally:
        app.close()


def check(entitlements, dsn, actor_id, workspace_id, session_id, kind, target_ns=None):
    """kind: OPEN | ADVANCE | JUMP | (CANCEL/CLOSE/END are always allowed). Raises WindowRefused; returns None when the command may proceed."""
    if kind in ("CANCEL", "CLOSE", "END", "FORK"):
        return
    window = entitlements.session_window(workspace_id, session_id)
    if window is None or window["tier"] == "PRO":
        return
    end = int(window["endNs"])
    state = live_orders(dsn, workspace_id, actor_id, session_id)
    through, after = state["throughNs"], state["throughNs"] >= end
    base = dict(windowEndNs=str(end), throughNs=str(through), activeOrders=state["active"], pendingOrders=state["pending"])
    if kind == "OPEN":
        if after:
            raise WindowRefused("WINDOW_ENDED", base)
        return
    if kind == "ADVANCE":
        if after:
            raise WindowRefused("WINDOW_ENDED_CONTINUATION_ONLY", {**base, "allowed": "JUMP_NEXT_EVENT_WITH_ACTIVE_ORDERS_CANCEL_CLOSE_END"})
        if target_ns is not None and int(target_ns) > end:
            raise WindowRefused("WINDOW_BOUNDARY", {**base, "maxTargetNs": str(end)})
        return
    if kind == "JUMP":
        if after:
            if state["pending"]:
                raise WindowRefused("PENDING_AT_WINDOW_END", base)
            if not state["active"]:
                raise WindowRefused("WINDOW_COMPLETED", base)
            return
        if state["pending"] and end - through <= NEAR_END_NS:
            raise WindowRefused("PENDING_NEAR_WINDOW_END", base)
        return
    raise ContractError("INVALID_INPUT", "kind")
