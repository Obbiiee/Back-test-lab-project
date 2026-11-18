"""Free research-window boundary for a running Session (server-side; the reducer and financial contracts are untouched).

The window of a Session is the UTC calendar month it was activated for (stored by the entitlement ledger). A Pro account is not limited by it. For a Free
account the guard never closes, cancels, rewrites or prices anything; it only refuses commands that would create NEW exposure or reveal MORE market data
than the already-open lifecycle needs:

  before the boundary : ADVANCE/SEEK/replay-to may not cross it (the user steps to the boundary, or uses Jump to Next Event with live orders)
  at/after the boundary: OPEN/confirm refused; ADVANCE/SEEK/replay-to refused; Jump to Next Event refused (owner decision 2026-11-18: no replay continuation
                         past the activated month, with ACTIVE or PENDING orders alike); CANCEL, CLOSE and END stay allowed; results stay readable.
A live order at the window end is not closed or rewritten. Inside the window, the jump orchestration (`execution/research.py`, with the lookup in
`execution/free_window.py`) bounds its search to the last tick of the window BEFORE any tick is processed; ADVANCE/SEEK/replay-to are bounded here
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


def chart_floor_ns(entitlements, workspace_id, session_id):
    """Earliest instant a Free account may see on a chart for this Session (the start of its activated month); None for Pro or a Session without a claim."""
    window = entitlements.session_window(workspace_id, session_id)
    if window is None or window["tier"] == "PRO":
        return None
    return int(window["startNs"])


def command_committed(dsn, workspace_id, session_id, command_id):
    """True when this exact command id is already committed for the Session (an idempotent retry must return its original receipt, not a new refusal)."""
    import psycopg
    with psycopg.connect(dsn) as db:
        return db.execute("SELECT 1 FROM btl.tick_commands WHERE workspace_id=%s AND session_id=%s AND command_id=%s",
                          (str(workspace_id), session_id, command_id)).fetchone() is not None


def check(entitlements, dsn, actor_id, workspace_id, session_id, kind, target_ns=None, command_id=None):
    """kind: OPEN | ADVANCE | JUMP | CLOSE | (CANCEL/END are always allowed). Raises WindowRefused; returns None when the command may proceed."""
    if kind in ("CANCEL", "END", "FORK"):
        return
    window = entitlements.session_window(workspace_id, session_id)
    if window is None or window["tier"] == "PRO":
        return
    end = int(window["endNs"])
    if kind == "CHART_CONTEXT":                                        # candles of the month BEFORE the activated one are Pro-only (owner decision 2026-11-18)
        raise WindowRefused("CHART_CONTEXT_PRO_ONLY", dict(windowStartNs=str(int(window["startNs"])), windowEndNs=str(end)))
    state = live_orders(dsn, workspace_id, actor_id, session_id)
    through, after = state["throughNs"], state["throughNs"] >= end - 1       # window = ticks with time < end; end-1 is the last allowed cursor
    base = dict(windowEndNs=str(end), throughNs=str(through), activeOrders=state["active"], pendingOrders=state["pending"])
    if kind == "CLOSE":
        # Owner decision 2026-11-18: a manual CLOSE fills on the next tick after the cursor, which lies outside a Free window once the boundary is reached.
        # Such a CLOSE is refused explicitly (never accepted and left pending). The positions stay open; END remains available.
        if after and not (command_id is not None and command_committed(dsn, workspace_id, session_id, command_id)):
            raise WindowRefused("WINDOW_CLOSE_REFUSED", {**base, "allowed": "CANCEL_END_OR_WAIT_FOR_NEXT_MONTH_SESSION"})
        return
    if kind == "OPEN":
        if after:
            raise WindowRefused("WINDOW_ENDED", base)
        return
    if kind == "ADVANCE":
        if after:
            raise WindowRefused("WINDOW_ENDED_CONTINUATION_ONLY", {**base, "allowed": "CANCEL_CLOSE_END"})
        if target_ns is not None and int(target_ns) > end - 1:
            raise WindowRefused("WINDOW_BOUNDARY", {**base, "maxTargetNs": str(end - 1)})
        return
    if kind == "JUMP":
        if after:                                       # owner decision 2026-11-18: a Free Session never replays past the activated month
            if state["pending"]:
                raise WindowRefused("PENDING_AT_WINDOW_END", base)
            raise WindowRefused("WINDOW_COMPLETED", base)
        return                                          # inside the window the jump orchestration bounds its search to the window end, see execution/free_window.py
    if kind == "SET_METHOD":
        if after:
            raise WindowRefused("WINDOW_COMPLETED", base)  # a method change cannot open an entry past the window; refused to keep the boundary absolute
        return
    raise ContractError("INVALID_INPUT", "kind")
